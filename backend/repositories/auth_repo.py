from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from dotenv import find_dotenv, load_dotenv
from pymongo import ASCENDING, MongoClient
from pymongo.errors import DuplicateKeyError

load_dotenv(find_dotenv())


class AuthRepository:
    """Repository for app users, sessions and user-owned projects in MongoDB."""

    def __init__(self, uri: str | None = None, db_name: str | None = None) -> None:
        uri = uri or os.getenv("MONGO_URI", "mongodb://localhost:27017")
        db_name = db_name or os.getenv("MONGO_DB_NAME", "rd_knowledge_graph")
        self.client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        self.db = self.client[db_name]
        self.users = self.db.app_users
        self.projects = self.db.projects
        self.experts = self.db.experts
        self.enterprises = self.db.enterprises
        self.funders = self.db.funders
        self.audit_logs = self.db.admin_audit_logs
        self.ensure_indexes()

    def ensure_indexes(self) -> None:
        try:
            self.users.create_index([("email", ASCENDING)], unique=True)
            for collection in (self.experts, self.enterprises, self.funders):
                collection.create_index([("email", ASCENDING)], sparse=True)
                collection.create_index([("user_id", ASCENDING)], sparse=True)
                collection.create_index([("name", ASCENDING)], sparse=True)
            self.projects.create_index([("owner_id", ASCENDING)])
            self.projects.create_index([("project_id", ASCENDING)], unique=True, sparse=True)
            self.audit_logs.create_index([("entity_type", ASCENDING), ("entity_id", ASCENDING)])
        except Exception:
            # Index creation should not make the API unusable in local/demo mode.
            pass

    def find_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return self.users.find_one({"email": email.strip().lower()})

    def find_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not ObjectId.is_valid(user_id):
            return None
        return self.users.find_one({"_id": ObjectId(user_id)})

    def create_user(self, user: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        payload = {
            **user,
            "email": user["email"].strip().lower(),
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = self.users.insert_one(payload)
        except DuplicateKeyError as exc:
            raise ValueError("Email already exists") from exc
        payload["_id"] = result.inserted_id
        return payload

    def update_user(self, user_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not ObjectId.is_valid(user_id):
            return None
        payload = {
            key: value
            for key, value in data.items()
            if value is not None and key not in {"id", "_id", "email", "password_hash"}
        }
        payload["updated_at"] = datetime.now(timezone.utc)
        self.users.update_one({"_id": ObjectId(user_id)}, {"$set": payload})
        return self.find_user_by_id(user_id)

    def set_user_linked_entity(self, user_id: str, linked_entity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not ObjectId.is_valid(user_id):
            return None
        self.users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "linked_entity": linked_entity,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return self.find_user_by_id(user_id)

    def relink_users_from_entity(
        self,
        entity_type: str,
        source_entity_id: str,
        target_entity: Dict[str, Any],
    ) -> int:
        target_id = target_entity.get(self.entity_id_field(entity_type)) or str(target_entity.get("_id"))
        linked_entity = {
            "id": target_id,
            "type": entity_type,
            "name": target_entity.get("name") or target_entity.get("title") or "",
            "kg_sync_status": target_entity.get("kg_sync_status"),
            "entity_verification_status": target_entity.get("entity_verification_status"),
            "match_status": "merged_existing",
        }
        result = self.users.update_many(
            {
                "linked_entity.id": source_entity_id,
                "linked_entity.type": entity_type,
            },
            {
                "$set": {
                    "linked_entity": linked_entity,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return int(result.modified_count)

    def get_entity_collection(self, role: str):
        role = str(role or "").lower()
        return {
            "expert": self.experts,
            "enterprise": self.enterprises,
            "funder": self.funders,
            "project": self.projects,
        }.get(role)

    def entity_id_field(self, role: str) -> str:
        return {
            "expert": "expert_id",
            "enterprise": "enterprise_id",
            "funder": "funder_id",
            "project": "project_id",
        }.get(str(role).lower(), "id")

    def find_entity_by_id(self, entity_type: str, entity_id: str) -> Optional[Dict[str, Any]]:
        collection = self.get_entity_collection(entity_type)
        if collection is None:
            return None
        return collection.find_one({self.entity_id_field(entity_type): entity_id})

    def find_strong_entity_match(self, role: str, user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        collection = self.get_entity_collection(role)
        if collection is None:
            return None
        email = str(user.get("email") or "").strip().lower()
        if email:
            found = collection.find_one({"email": email})
            if found:
                return found
        identifiers = user.get("identifiers") or {}
        for key in ("ORCID", "ResearcherID", "website", "domain"):
            value = identifiers.get(key) or user.get(key.lower())
            if value:
                found = collection.find_one({f"identifiers.{key}": value})
                if found:
                    return found
                found = collection.find_one({key.lower(): value})
                if found:
                    return found
        return None

    def find_entity_candidates_by_name(self, role: str, name: str, limit: int = 10) -> List[Dict[str, Any]]:
        collection = self.get_entity_collection(role)
        if collection is None or not name:
            return []
        return list(
            collection.find(
                {"name": {"$regex": name[: max(3, min(len(name), 24))], "$options": "i"}}
            ).limit(limit)
        )

    def create_role_entity(
        self,
        user: Dict[str, Any],
        match_result: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        role = str(user.get("role") or "").lower()
        if role not in {"expert", "enterprise", "funder"}:
            return None

        user_id = str(user.get("_id"))
        now = datetime.now(timezone.utc)
        collection_map = {
            "expert": (self.experts, "expert_id", "user_exp"),
            "enterprise": (self.enterprises, "enterprise_id", "user_ent"),
            "funder": (self.funders, "funder_id", "user_fund"),
        }
        collection, id_field, prefix = collection_map[role]
        existing = collection.find_one({"user_id": user_id})
        if existing:
            return existing

        match_result = match_result or {}
        if match_result.get("match_status") == "matched_existing" and match_result.get("matched_entity"):
            return match_result["matched_entity"]

        entity_id = f"{prefix}_{ObjectId()}"
        is_merge_required = match_result.get("match_status") == "merge_required"
        payload = {
            id_field: entity_id,
            "user_id": user_id,
            "name": user.get("full_name", ""),
            "email": user.get("email", ""),
            "organization": user.get("organization", ""),
            "phone": user.get("phone", ""),
            "address": user.get("address", ""),
            "summary": user.get("bio", ""),
            "research_topics": user.get("research_interests", []),
            "custom_research_topics": user.get("custom_research_topics", []),
            "source": "user_registration",
            "entity_verification_status": "unverified",
            "kg_sync_status": "merge_required" if is_merge_required else "not_synced",
            "visibility": "private" if is_merge_required else "limited",
            "participation_scope": "owner_only",
            "allow_as_source": True,
            "recommendable_as_target": False,
            "allow_as_intermediate_node": False,
            "trust_weight": 0.3 if is_merge_required else 0.5,
            "duplicate_candidates": match_result.get("candidates") or [],
            "matched_existing_entity_id": None,
            "claim_status": "pending_review" if is_merge_required else None,
            "kg_schema_version": 1,
            "provisional_sync_version": 1,
            "created_at": now,
            "updated_at": now,
        }
        result = collection.insert_one(payload)
        payload["_id"] = result.inserted_id
        return payload

    def update_entity_status(self, entity_type: str, entity_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        collection = self.get_entity_collection(entity_type)
        if collection is None:
            return None
        payload = {**data, "updated_at": datetime.now(timezone.utc)}
        collection.update_one(
            {self.entity_id_field(entity_type): entity_id},
            {"$set": payload},
        )
        return self.find_entity_by_id(entity_type, entity_id)

    def create_project(self, user_id: str, project: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        project_id = project.get("project_id") or f"user_prj_{ObjectId()}"
        payload = {
            **project,
            "project_id": str(project_id),
            "owner_id": user_id,
            "created_by": user_id,
            "owner_user_id": user_id,
            "owner_entity_id": project.get("owner_entity_id"),
            "source": "user_created",
            "entity_verification_status": "unverified",
            "kg_sync_status": "not_synced",
            "visibility": "limited",
            "participation_scope": "owner_only",
            "allow_as_source": True,
            "recommendable_as_target": False,
            "allow_as_intermediate_node": False,
            "trust_weight": 0.5,
            "kg_schema_version": 1,
            "provisional_sync_version": 1,
            "created_at": now,
            "updated_at": now,
        }
        result = self.projects.insert_one(payload)
        payload["_id"] = result.inserted_id
        return payload

    def insert_admin_audit_log(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = self.audit_logs.insert_one(payload)
        payload["_id"] = result.inserted_id
        return payload

    def list_user_projects(self, user_id: str, limit: int = 50, page: int = 1) -> List[Dict[str, Any]]:
        skip = max(page - 1, 0) * limit
        cursor = (
            self.projects.find({"owner_id": user_id})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        return list(cursor)

    def count_user_projects(self, user_id: str) -> int:
        return int(self.projects.count_documents({"owner_id": user_id}))

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, ObjectId):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, dict):
            return {key: self._json_safe(item) for key, item in value.items()}
        return value
