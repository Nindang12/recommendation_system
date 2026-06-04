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
from services.outbox_publisher_service import OutboxPublisherService
from services.provisional_kg_sync_service import ProvisionalKGSyncService
from services import provisional_status as st


class AuthService:
    """Business layer for user auth and user-owned projects."""

    def __init__(self, repo: Optional[AuthRepository] = None) -> None:
        self.repo = repo or AuthRepository()
        self.matcher = EntityMatchingService(self.repo)
        self.kg_sync = ProvisionalKGSyncService(self.repo)
        self.event_publisher = OutboxPublisherService(self.repo)
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
                "account_role": "user",
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
                self._publish_embedding_event_if_ready(
                    str(user.get("role", "")),
                    str(synced_entity.get(self.repo.entity_id_field(str(user.get("role", "")))) or linked_entity.get("id")),
                    event_type="kg.entity.created",
                    source="user_registration",
                )
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
        role_entity = self.repo.update_role_entity_from_user(user) or role_entity
        if role_entity:
            linked_entity = self._linked_entity_response(role_entity, user.get("role", ""))
            user = self.repo.set_user_linked_entity(user_id, linked_entity) or user
            if linked_entity.get("match_status") != "matched_existing":
                synced_entity = self._sync_role_entity_if_needed(user.get("role", ""), linked_entity)
                if synced_entity and self._should_publish_update_embedding_event(synced_entity):
                    self._publish_embedding_event_if_ready(
                        str(user.get("role", "")),
                        str(synced_entity.get(self.repo.entity_id_field(str(user.get("role", "")))) or linked_entity.get("id")),
                        event_type="kg.entity.updated",
                        source="profile_update",
                    )
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
            self._publish_embedding_event_if_ready(
                "project",
                str(project.get("project_id")),
                event_type="kg.project.created",
                source="user_project_create",
            )
        except Exception:
            # Project creation should remain usable even when Neo4j is temporarily down.
            pass
        return self._project_response(project, current_user_id=user_id)

    def list_my_projects(self, user_id: str, limit: int = 50, page: int = 1) -> Dict[str, Any]:
        user = self.repo.find_user_by_id(user_id) or {}
        linked_entity = user.get("linked_entity") or {}
        owned_projects = self.repo.list_user_projects(user_id, limit=200, page=1)
        for project in owned_projects:
            project["_my_project_relation"] = "owner"

        linked_projects: List[Dict[str, Any]] = []
        if linked_entity.get("id") and linked_entity.get("type"):
            linked_projects = self.repo.list_projects_related_to_entity(
                str(linked_entity.get("type")),
                str(linked_entity.get("id")),
                limit=200,
            )

        projects_by_id: Dict[str, Dict[str, Any]] = {}
        for project in linked_projects + owned_projects:
            project_id = str(project.get("project_id") or project.get("_id"))
            if not project_id:
                continue
            existing = projects_by_id.get(project_id)
            if existing and existing.get("_my_project_relation") == "owner":
                continue
            projects_by_id[project_id] = project

        merged_projects = list(projects_by_id.values())
        merged_projects.sort(
            key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
            reverse=True,
        )
        start = max(page - 1, 0) * limit
        projects = merged_projects[start : start + limit]
        return {
            "data": [self._project_response(project, current_user_id=user_id) for project in projects],
            "count": len(merged_projects),
        }

    def delete_project(self, user_id: str, project_id: str) -> Dict[str, Any]:
        project = self.repo.soft_delete_user_project(user_id, project_id)
        if not project:
            raise ValueError("Project not found or you are not the owner")
        try:
            self.kg_sync.disable_entity("project", project_id)
            refreshed = self.repo.find_entity_by_id("project", project_id)
            if refreshed:
                project = refreshed
        except Exception:
            # The user-facing delete should still hide the MongoDB project if Neo4j is down.
            pass
        return self._project_response(project, current_user_id=user_id)

    def _auth_response(self, user: Dict[str, Any]) -> Dict[str, Any]:
        public = self._public_user(user)
        return {
            "token": self._encode_token({"sub": public["id"], "email": public["email"]}),
            "user": public,
        }

    def _public_user(self, user: Dict[str, Any]) -> Dict[str, Any]:
        linked_entity = self._fresh_linked_entity(user)
        entity = self._linked_entity_document(user, linked_entity)
        profile_data = self._merged_profile_data(user, entity)
        social_links = self._merged_social_links(user, entity, profile_data)
        return {
            "id": str(user.get("_id")),
            "email": user.get("email", ""),
            "full_name": self._first_value(
                user.get("full_name"),
                self._get_path(entity, "basic_info.name"),
                self._get_path(entity, "basic_info.title"),
                entity.get("name") if entity else None,
            ),
            "username": user.get("username", ""),
            "role": user.get("role", "expert"),
            "account_role": user.get("account_role", "user"),
            "organization": self._first_value(
                user.get("organization"),
                self._get_path(entity, "organization"),
                self._get_path(entity, "academic_profile.current_affiliation.org_name"),
            ),
            "phone": self._first_value(
                user.get("phone"),
                self._get_path(entity, "phone"),
                self._get_path(entity, "contact_info.phone"),
                self._first_list_value(self._get_path(entity, "contact_info.phones")),
                self._first_list_value(self._get_path(entity, "representatives")),
                self._get_path(entity, "representatives.phone"),
            ),
            "address": self._first_value(user.get("address"), self._get_path(entity, "address")),
            "country": self._first_value(
                user.get("country"),
                self._get_path(entity, "country"),
                self._get_path(entity, "basic_info.location.country_code"),
                "VN",
            ),
            "province": self._first_value(
                user.get("province"),
                self._get_path(entity, "province"),
                self._get_path(entity, "basic_info.location.region"),
            ),
            "district": self._first_value(
                user.get("district"),
                self._get_path(entity, "district"),
                self._get_path(entity, "basic_info.location.city"),
            ),
            "skills": self._first_list(user.get("skills"), self._extract_entity_skills(entity)),
            "custom_skills": self._first_list(user.get("custom_skills")),
            "bio": self._first_value(user.get("bio"), self._get_path(entity, "summary"), self._get_path(entity, "bio")),
            "social_links": social_links,
            "profile_data": profile_data,
            "research_interests": self._first_list(
                user.get("research_interests"),
                self._extract_entity_topics(entity),
            ),
            "custom_research_topics": self._first_list(user.get("custom_research_topics")),
            "linked_entity": linked_entity,
            "account_verification_status": user.get(
                "account_verification_status",
                user.get("verification_status", st.ACCOUNT_EMAIL_UNVERIFIED),
            ),
            "status": user.get("status", "active"),
            "created_at": self._dt(user.get("created_at")),
            "updated_at": self._dt(user.get("updated_at")),
        }

    def _fresh_linked_entity(self, user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        linked_entity = user.get("linked_entity")
        if not isinstance(linked_entity, dict):
            return linked_entity

        entity_id = linked_entity.get("id")
        entity_type = linked_entity.get("type") or user.get("role")
        if not entity_id or not entity_type:
            return linked_entity

        entity = self.repo.find_entity_by_id(str(entity_type), str(entity_id))
        if not entity:
            return linked_entity

        refreshed = self._linked_entity_response(
            entity,
            str(entity_type),
            match_result={"match_status": linked_entity.get("match_status") or "existing"},
        )
        if refreshed != linked_entity:
            self.repo.set_user_linked_entity(str(user.get("_id")), refreshed)
        return refreshed

    def _linked_entity_document(
        self,
        user: Dict[str, Any],
        linked_entity: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not isinstance(linked_entity, dict):
            return {}
        entity_id = linked_entity.get("id")
        entity_type = linked_entity.get("type") or user.get("role")
        if not entity_id or not entity_type:
            return {}
        return self.repo.find_entity_by_id(str(entity_type), str(entity_id)) or {}

    def _merged_profile_data(self, user: Dict[str, Any], entity: Dict[str, Any]) -> Dict[str, Any]:
        sections = [
            "basic_info",
            "identifiers",
            "contact_info",
            "academic_profile",
            "research_capacity",
            "academic_metrics",
            "activities_and_outputs",
            "funding_strategy",
            "rd_profile",
            "organization_metrics",
            "investment_mandates",
            "programs",
            "relations",
            "governance",
        ]
        entity_profile = dict(entity.get("profile_data") or {})
        for section in sections:
            if isinstance(entity.get(section), (dict, list)) and section not in entity_profile:
                entity_profile[section] = entity.get(section)
        return self._deep_merge(entity_profile, user.get("profile_data") or {})

    def _merged_social_links(
        self,
        user: Dict[str, Any],
        entity: Dict[str, Any],
        profile_data: Dict[str, Any],
    ) -> Dict[str, str]:
        entity_links: Dict[str, str] = {}
        for source in (
            self._get_path(entity, "social_links"),
            self._get_path(entity, "contact_info.social_links"),
            self._get_path(profile_data, "contact_info.social_links"),
        ):
            if isinstance(source, dict):
                entity_links.update({str(k): str(v) for k, v in source.items() if self._has_value(v)})
        website = self._first_value(
            self._get_path(entity, "website"),
            self._get_path(entity, "contact_info.website"),
            self._get_path(profile_data, "contact_info.website"),
        )
        if website:
            entity_links.setdefault("website", website)
        orcid = self._first_value(
            self._get_path(entity, "identifiers.ORCID"),
            self._get_path(profile_data, "identifiers.ORCID"),
        )
        if orcid:
            entity_links.setdefault("orcid", orcid)
        return {**entity_links, **{k: v for k, v in (user.get("social_links") or {}).items() if self._has_value(v)}}

    def _extract_entity_skills(self, entity: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        for value in (
            entity.get("skills"),
            entity.get("technology"),
            entity.get("skill_methods"),
            self._get_path(entity, "research_capacity.technology"),
            self._get_path(entity, "research_capacity.skills_methods"),
            self._get_path(entity, "requirements_and_timeline.required_skills"),
        ):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        out.append(str(item.get("name") or item.get("skill") or item.get("technology") or ""))
                    else:
                        out.append(str(item))
            elif self._has_value(value):
                out.append(str(value))
        return [item for item in out if item]

    def _extract_entity_topics(self, entity: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        for value in (
            entity.get("research_interests"),
            entity.get("research_topics"),
            entity.get("focus_topics"),
            self._get_path(entity, "basic_info.research_topics"),
            self._get_path(entity, "research_capacity.research_topics"),
            self._get_path(entity, "rd_profile.rd_focus_topics"),
            self._get_path(entity, "funding_strategy.funding_topics"),
        ):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        out.append(str(item.get("id") or item.get("name") or item.get("topic") or ""))
                    else:
                        out.append(str(item))
            elif self._has_value(value):
                out.append(str(value))
        return [item for item in out if item]

    def _get_path(self, data: Optional[Dict[str, Any]], path: str) -> Any:
        current: Any = data or {}
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    @staticmethod
    def _has_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, dict)):
            return bool(value)
        return True

    def _first_value(self, *values: Any) -> str:
        for value in values:
            if self._has_value(value):
                return str(value).strip() if isinstance(value, str) else str(value)
        return ""

    def _first_list(self, *values: Any) -> List[Any]:
        for value in values:
            if isinstance(value, list) and value:
                return value
        return []

    @staticmethod
    def _first_list_value(value: Any) -> Any:
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, dict):
                return first.get("phone") or first.get("email") or first.get("name")
            return first
        return None

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._deep_merge(result[key], value)
            elif self._has_value(value):
                result[key] = value
        return result

    def create_admin_user(self, payload: Dict[str, Any], account_role: str = "admin") -> Dict[str, Any]:
        account_role = account_role if account_role in {"admin", "root_admin"} else "admin"
        email = payload["email"].strip().lower()
        if self.repo.find_user_by_email(email):
            raise ValueError("Email already exists")
        if len(payload["password"]) < 6:
            raise ValueError("Password must have at least 6 characters")

        password_hash = self._hash_password(payload["password"])
        user = self.repo.create_user(
            {
                "email": email,
                "password_hash": password_hash,
                "full_name": payload.get("full_name") or "System Admin",
                "username": payload.get("username", ""),
                "role": payload.get("role") or "expert",
                "account_role": account_role,
                "organization": payload.get("organization", ""),
                "phone": payload.get("phone", ""),
                "address": payload.get("address", ""),
                "country": payload.get("country", "VN"),
                "province": payload.get("province", ""),
                "district": payload.get("district", ""),
                "skills": payload.get("skills", []),
                "custom_skills": payload.get("custom_skills", []),
                "bio": payload.get("bio", ""),
                "social_links": payload.get("social_links", {}),
                "profile_data": payload.get("profile_data", {}),
                "research_interests": payload.get("research_interests", []),
                "custom_research_topics": payload.get("custom_research_topics", []),
                "status": "active",
                "account_verification_status": st.ACCOUNT_EMAIL_VERIFIED,
            }
        )
        return self._public_user(user)

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
        match_status = match_result.get("match_status") or "existing"
        duplicate_candidates = []
        if match_status == "merge_required" or entity.get("kg_sync_status") == st.KG_MERGE_REQUIRED:
            duplicate_candidates = entity.get("duplicate_candidates") or match_result.get("candidates") or []
        is_matched_existing = match_status == "matched_existing"
        return {
            "id": entity.get(id_key) or str(entity.get("_id")),
            "type": str(role).lower(),
            "name": self._first_value(
                entity.get("name"),
                entity.get("title"),
                self._get_path(entity, "basic_info.name"),
                self._get_path(entity, "basic_info.title"),
            ),
            "kg_sync_status": entity.get(
                "kg_sync_status",
                st.KG_SYNCED_VERIFIED if is_matched_existing else st.KG_NOT_SYNCED,
            ),
            "entity_verification_status": entity.get(
                "entity_verification_status",
                st.ENTITY_VERIFIED if is_matched_existing else st.ENTITY_UNVERIFIED,
            ),
            "visibility": entity.get("visibility", st.VISIBILITY_PUBLIC if is_matched_existing else st.VISIBILITY_LIMITED),
            "participation_scope": entity.get(
                "participation_scope",
                st.SCOPE_PUBLIC if is_matched_existing else st.SCOPE_OWNER_ONLY,
            ),
            "allow_as_source": bool(entity.get("allow_as_source", True)),
            "recommendable_as_target": bool(entity.get("recommendable_as_target", True if is_matched_existing else False)),
            "allow_as_intermediate_node": bool(entity.get("allow_as_intermediate_node", True if is_matched_existing else False)),
            "trust_weight": float(entity.get("trust_weight", 1.0 if is_matched_existing else 0.5) or 0.5),
            "match_status": match_status,
            "duplicate_candidates": duplicate_candidates,
        }

    def _project_response(self, project: Dict[str, Any], current_user_id: Optional[str] = None) -> Dict[str, Any]:
        owner_id = project.get("owner_id")
        can_delete = bool(current_user_id and owner_id == current_user_id and not project.get("deleted_at"))
        relation = project.get("_my_project_relation") or ("owner" if can_delete else None)
        embedding = self._embedding_metadata(project)
        return {
            "id": str(project.get("project_id") or project.get("_id")),
            "name": self._first_value(
                project.get("title"),
                project.get("name"),
                self._get_path(project, "basic_info.title"),
                self._get_path(project, "basic_info.name"),
            ),
            "type": "project",
            "summary": self._first_value(
                project.get("summary"),
                project.get("description"),
                self._get_path(project, "basic_info.description"),
            ),
            "metadata": {
                "status": self._first_value(
                    project.get("status"),
                    self._get_path(project, "requirements_and_timeline.status"),
                    "draft",
                ),
                "field": project.get("field") or self._first_list_value(
                    self._get_path(project, "basic_info.research_directions")
                ),
                "budget": project.get("budget") or self._get_path(project, "requirements_and_timeline.budget.amount"),
                "trl": project.get("trl")
                or self._get_path(project, "requirements_and_timeline.technology_readiness_level"),
                "owner_id": owner_id,
                "owner_entity_id": project.get("owner_entity_id"),
                "can_delete": can_delete,
                "my_project_relation": relation,
                "linked_entity_role": project.get("_linked_entity_role"),
                "linked_entity_status": project.get("_linked_entity_status"),
                "linked_entity_period": project.get("_linked_entity_period"),
                "entity_verification_status": project.get("entity_verification_status", st.ENTITY_UNVERIFIED),
                "kg_sync_status": project.get("kg_sync_status", st.KG_NOT_SYNCED),
                "visibility": project.get("visibility", st.VISIBILITY_LIMITED),
                "participation_scope": project.get("participation_scope", st.SCOPE_OWNER_ONLY),
                "allow_as_source": bool(project.get("allow_as_source", True)),
                "recommendable_as_target": bool(project.get("recommendable_as_target", False)),
                "allow_as_intermediate_node": bool(project.get("allow_as_intermediate_node", False)),
                "trust_weight": float(project.get("trust_weight", 0.5) or 0.5),
                "embedding": embedding,
                "embedding_status": embedding.get("status"),
                "created_at": self._dt(project.get("created_at")),
                "updated_at": self._dt(project.get("updated_at")),
            },
        }

    def _embedding_metadata(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        embedding = entity.get("embedding")
        if not isinstance(embedding, dict):
            status = entity.get("embedding_status")
            return {"status": status} if status else {}
        return {
            "status": embedding.get("status"),
            "model": embedding.get("model"),
            "version": embedding.get("version"),
            "dimension": embedding.get("dimension"),
            "normalized": embedding.get("normalized"),
            "signal": embedding.get("signal"),
            "updated_at": self._dt(embedding.get("updated_at")),
            "last_queued_at": self._dt(embedding.get("last_queued_at")),
            "last_processed_at": self._dt(embedding.get("last_processed_at")),
            "error": embedding.get("error"),
            "error_type": embedding.get("error_type"),
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

    def _publish_embedding_event_if_ready(
        self,
        entity_type: str,
        entity_id: str,
        *,
        event_type: str,
        source: str,
    ) -> None:
        try:
            self.event_publisher.enqueue_embedding_event(
                entity_type,
                entity_id,
                event_type=event_type,  # type: ignore[arg-type]
                source=source,
            )
        except Exception:
            # Embedding queue is optional in Phase 2; user-facing flows must not fail.
            return

    @staticmethod
    def _should_publish_update_embedding_event(entity: Dict[str, Any]) -> bool:
        embedding = entity.get("embedding") or {}
        return embedding.get("status") == st.EMBEDDING_STALE

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
