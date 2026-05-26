from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from repositories.auth_repo import AuthRepository
from services.entity_matching_service import EntityMatchingService
from services.provisional_kg_sync_service import ProvisionalKGSyncService
from services import provisional_status as st


class AuthService:
    """Business layer for user auth and user-owned projects."""

    def __init__(self, repo: Optional[AuthRepository] = None) -> None:
        self.repo = repo or AuthRepository()
        self.matcher = EntityMatchingService(self.repo)
        self.kg_sync = ProvisionalKGSyncService(self.repo)
        self.secret = os.getenv("APP_AUTH_SECRET", "dev-change-me")

    def register(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        email = payload["email"].strip().lower()
        if self.repo.find_user_by_email(email):
            raise ValueError("Email already exists")
        if len(payload["password"]) < 6:
            raise ValueError("Password must have at least 6 characters")

        password_hash = self._hash_password(payload.pop("password"))
        user = self.repo.create_user(
            {
                **payload,
                "email": email,
                "password_hash": password_hash,
                "role": payload.get("role") or "expert",
                "status": "active",
                "account_verification_status": st.ACCOUNT_EMAIL_UNVERIFIED,
            }
        )
        match_result = self.matcher.match_user_entity(user.get("role", "expert"), user)
        role_entity = self.repo.create_role_entity(user, match_result=match_result)
        if role_entity:
            linked_entity = self._linked_entity_response(
                role_entity,
                user.get("role", ""),
                match_result=match_result,
            )
            user["linked_entity"] = linked_entity
            refreshed = self.repo.set_user_linked_entity(str(user["_id"]), linked_entity)
            if refreshed:
                user = refreshed
            synced_entity = self._sync_role_entity_if_needed(user.get("role", ""), linked_entity)
            if synced_entity:
                linked_entity = self._linked_entity_response(
                    synced_entity,
                    user.get("role", ""),
                    match_result=match_result,
                )
                user = self.repo.set_user_linked_entity(str(user["_id"]), linked_entity) or user
        return self._auth_response(user)

    def login(self, email: str, password: str) -> Dict[str, Any]:
        user = self.repo.find_user_by_email(email)
        if not user or not self._verify_password(password, user.get("password_hash", "")):
            raise PermissionError("Invalid email or password")
        return self._auth_response(user)

    def get_current_user(self, token: str) -> Dict[str, Any]:
        payload = self._decode_token(token)
        user_id = payload.get("sub")
        user = self.repo.find_user_by_id(str(user_id))
        if not user:
            raise PermissionError("Invalid token")
        return self._public_user(user)

    def update_profile(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        user = self.repo.update_user(user_id, payload)
        if not user:
            raise ValueError("User not found")
        role_entity = self.repo.create_role_entity(user)
        if role_entity:
            linked_entity = self._linked_entity_response(role_entity, user.get("role", ""))
            user = self.repo.set_user_linked_entity(user_id, linked_entity) or user
        return self._public_user(user)

    def create_project(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        user = self.repo.find_user_by_id(user_id) or {}
        linked_entity = user.get("linked_entity") or {}
        if linked_entity.get("id"):
            payload["owner_entity_id"] = linked_entity.get("id")
        project = self.repo.create_project(user_id, payload)
        try:
            self.kg_sync.sync_entity_as_unverified("project", str(project.get("project_id")))
            project = self.repo.find_entity_by_id("project", str(project.get("project_id"))) or project
        except Exception:
            # Project creation should remain usable even when Neo4j is temporarily down.
            pass
        return self._project_response(project)

    def list_my_projects(self, user_id: str, limit: int = 50, page: int = 1) -> Dict[str, Any]:
        projects = self.repo.list_user_projects(user_id, limit=limit, page=page)
        return {
            "data": [self._project_response(project) for project in projects],
            "count": self.repo.count_user_projects(user_id),
        }

    def _auth_response(self, user: Dict[str, Any]) -> Dict[str, Any]:
        public = self._public_user(user)
        return {
            "token": self._encode_token({"sub": public["id"], "email": public["email"]}),
            "user": public,
        }

    def _public_user(self, user: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(user.get("_id")),
            "email": user.get("email", ""),
            "full_name": user.get("full_name", ""),
            "username": user.get("username", ""),
            "role": user.get("role", "expert"),
            "organization": user.get("organization", ""),
            "phone": user.get("phone", ""),
            "address": user.get("address", ""),
            "bio": user.get("bio", ""),
            "research_interests": user.get("research_interests", []),
            "custom_research_topics": user.get("custom_research_topics", []),
            "linked_entity": user.get("linked_entity"),
            "account_verification_status": user.get(
                "account_verification_status",
                user.get("verification_status", st.ACCOUNT_EMAIL_UNVERIFIED),
            ),
            "status": user.get("status", "active"),
            "created_at": self._dt(user.get("created_at")),
            "updated_at": self._dt(user.get("updated_at")),
        }

    def _linked_entity_response(
        self,
        entity: Dict[str, Any],
        role: str,
        match_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        id_key = {
            "expert": "expert_id",
            "enterprise": "enterprise_id",
            "funder": "funder_id",
        }.get(str(role).lower(), "id")
        match_result = match_result or {}
        return {
            "id": entity.get(id_key) or str(entity.get("_id")),
            "type": str(role).lower(),
            "name": entity.get("name", ""),
            "kg_sync_status": entity.get("kg_sync_status", st.KG_NOT_SYNCED),
            "entity_verification_status": entity.get("entity_verification_status", st.ENTITY_UNVERIFIED),
            "visibility": entity.get("visibility", st.VISIBILITY_LIMITED),
            "participation_scope": entity.get("participation_scope", st.SCOPE_OWNER_ONLY),
            "allow_as_source": bool(entity.get("allow_as_source", True)),
            "recommendable_as_target": bool(entity.get("recommendable_as_target", False)),
            "allow_as_intermediate_node": bool(entity.get("allow_as_intermediate_node", False)),
            "trust_weight": float(entity.get("trust_weight", 0.5) or 0.5),
            "match_status": match_result.get("match_status") or "existing",
            "duplicate_candidates": entity.get("duplicate_candidates") or match_result.get("candidates") or [],
        }

    def _project_response(self, project: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(project.get("project_id") or project.get("_id")),
            "name": project.get("title") or project.get("name") or "",
            "type": "project",
            "summary": project.get("summary") or project.get("description") or "",
            "metadata": {
                "status": project.get("status", "draft"),
                "field": project.get("field", ""),
                "budget": project.get("budget"),
                "trl": project.get("trl"),
                "owner_id": project.get("owner_id"),
                "owner_entity_id": project.get("owner_entity_id"),
                "entity_verification_status": project.get("entity_verification_status", st.ENTITY_UNVERIFIED),
                "kg_sync_status": project.get("kg_sync_status", st.KG_NOT_SYNCED),
                "visibility": project.get("visibility", st.VISIBILITY_LIMITED),
                "participation_scope": project.get("participation_scope", st.SCOPE_OWNER_ONLY),
                "allow_as_source": bool(project.get("allow_as_source", True)),
                "recommendable_as_target": bool(project.get("recommendable_as_target", False)),
                "allow_as_intermediate_node": bool(project.get("allow_as_intermediate_node", False)),
                "trust_weight": float(project.get("trust_weight", 0.5) or 0.5),
                "created_at": self._dt(project.get("created_at")),
                "updated_at": self._dt(project.get("updated_at")),
            },
        }

    def _sync_role_entity_if_needed(self, role: str, linked_entity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        entity_id = linked_entity.get("id")
        if not entity_id or linked_entity.get("match_status") == "matched_existing":
            return None
        try:
            return self.kg_sync.sync_entity_as_unverified(str(role).lower(), str(entity_id))
        except Exception:
            # Registration remains successful; status is stored as sync_failed for retry.
            return self.repo.find_entity_by_id(str(role).lower(), str(entity_id))

    def _hash_password(self, password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
        return f"{salt}${digest.hex()}"

    def _verify_password(self, password: str, stored: str) -> bool:
        try:
            salt, digest = stored.split("$", 1)
        except ValueError:
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
        return hmac.compare_digest(candidate, digest)

    def _encode_token(self, payload: Dict[str, Any]) -> str:
        body = {
            **payload,
            "iat": int(datetime.now(timezone.utc).timestamp()),
        }
        raw = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).decode().rstrip("=")
        sig = hmac.new(self.secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
        return f"{raw}.{sig}"

    def _decode_token(self, token: str) -> Dict[str, Any]:
        try:
            raw, sig = token.split(".", 1)
        except ValueError as exc:
            raise PermissionError("Invalid token") from exc
        expected = hmac.new(self.secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise PermissionError("Invalid token")
        padded = raw + "=" * (-len(raw) % 4)
        return json.loads(base64.urlsafe_b64decode(padded.encode()).decode())

    def _dt(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return value
