from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from dotenv import find_dotenv, load_dotenv
from pymongo import ASCENDING, MongoClient
from pymongo.errors import DuplicateKeyError

from models.research_taxonomy import RESEARCH_TOPIC_LABEL_MAP, research_direction_label, research_topic_direction

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
                collection.create_index([("contact_info.emails", ASCENDING)], sparse=True)
                collection.create_index([("user_id", ASCENDING)], sparse=True)
                collection.create_index([("basic_info.name", ASCENDING)], sparse=True)
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

    def list_users_for_admin(self, limit: int = 50, page: int = 1) -> List[Dict[str, Any]]:
        skip = max(page - 1, 0) * limit
        cursor = (
            self.users.find({}, {"password_hash": 0})
            .sort("updated_at", -1)
            .skip(skip)
            .limit(limit)
        )
        return list(cursor)

    def set_user_account_role(self, user_id: str, account_role: str) -> Optional[Dict[str, Any]]:
        if not ObjectId.is_valid(user_id):
            return None
        self.users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "account_role": account_role,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        user = self.find_user_by_id(user_id)
        if user:
            user.pop("password_hash", None)
        return user

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
            "name": self._display_name(target_entity),
            "kg_sync_status": target_entity.get("kg_sync_status"),
            "entity_verification_status": target_entity.get("entity_verification_status"),
            "visibility": target_entity.get("visibility"),
            "participation_scope": target_entity.get("participation_scope"),
            "allow_as_source": target_entity.get("allow_as_source", True),
            "recommendable_as_target": target_entity.get("recommendable_as_target", False),
            "allow_as_intermediate_node": target_entity.get("allow_as_intermediate_node", False),
            "trust_weight": target_entity.get("trust_weight", 1.0),
            "match_status": "merged_existing",
            "duplicate_candidates": [],
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
            found = collection.find_one(
                {"$or": [{"email": email}, {"contact_info.emails": email}, {"contact_info.email": email}]}
            )
            if found:
                return found
        identifiers = user.get("identifiers") or self._get_nested(user, "profile_data.identifiers") or {}
        social_links = user.get("social_links") or {}
        for key in ("ORCID", "ResearcherID", "Scopus_ID", "website", "domain"):
            value = (
                identifiers.get(key)
                or identifiers.get(key.lower())
                or user.get(key.lower())
                or social_links.get(key.lower())
            )
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
                {
                    "$or": [
                        {"name": {"$regex": name[: max(3, min(len(name), 24))], "$options": "i"}},
                        {"basic_info.name": {"$regex": name[: max(3, min(len(name), 24))], "$options": "i"}},
                    ]
                }
            ).limit(limit)
        )

    def _get_nested(self, data: Optional[Dict[str, Any]], path: str) -> Any:
        current: Any = data or {}
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _first_non_empty(self, *values: Any) -> Any:
        for value in values:
            if value not in (None, "", [], {}):
                return value
        return None

    def _display_name(self, doc: Dict[str, Any]) -> str:
        return str(
            self._first_non_empty(
                doc.get("name"),
                doc.get("title"),
                self._get_nested(doc, "basic_info.name"),
                self._get_nested(doc, "basic_info.title"),
            )
            or ""
        )

    def _display_email(self, doc: Dict[str, Any]) -> Optional[str]:
        emails = self._get_nested(doc, "contact_info.emails")
        if isinstance(emails, list) and emails:
            return str(emails[0])
        return self._first_non_empty(
            doc.get("email"),
            self._get_nested(doc, "contact_info.email"),
        )

    def _location_from_user(self, user: Dict[str, Any]) -> Dict[str, Any]:
        country = user.get("country") or "VN"
        return {
            "country_code": country,
            "country_name": "Vietnam" if str(country).upper() == "VN" else str(country),
            "region": user.get("province", ""),
            "city": user.get("district", ""),
            "coordinates": {},
        }

    def _topic_objects(self, user: Dict[str, Any]) -> List[Dict[str, Any]]:
        topics: List[Dict[str, Any]] = []
        for item in list(user.get("research_interests") or []):
            if isinstance(item, dict):
                name = item.get("name") or item.get("topic") or item.get("id")
                value = item.get("id") or item.get("value") or name
                parent = item.get("parent_direction") or research_topic_direction(str(value))
            else:
                value = str(item)
                name = RESEARCH_TOPIC_LABEL_MAP.get(value, value)
                parent = research_topic_direction(value)
            if name:
                topics.append(
                    {
                        "id": value,
                        "name": name,
                        "parent_direction": parent,
                        "parent_direction_label": research_direction_label(parent),
                    }
                )
        for item in list(user.get("custom_research_topics") or []):
            name = item.get("name") if isinstance(item, dict) else str(item)
            if name:
                topics.append(
                    {
                        "name": name,
                        "parent_direction": "custom_pending_mapping",
                        "parent_direction_label": "Can admin mapping",
                        "mapping_status": "pending_review",
                    }
                )
        return topics

    def _skill_objects(self, user: Dict[str, Any]) -> List[Dict[str, Any]]:
        skills: List[Dict[str, Any]] = []
        for item in list(user.get("skills") or []) + list(user.get("custom_skills") or []):
            if isinstance(item, dict):
                name = item.get("name") or item.get("skill") or item.get("technology")
                category = item.get("category") or item.get("type") or "unknown"
                level = item.get("proficiency_level") or item.get("level") or "intermediate"
            else:
                name = str(item)
                category = "custom" if item in (user.get("custom_skills") or []) else "unknown"
                level = "intermediate"
            if name:
                skills.append({"name": name, "category": category, "proficiency_level": level})
        return skills

    def _default_governance(self, now: datetime) -> Dict[str, Any]:
        return {
            "privacy": {
                "privacy_level": "limited",
                "field_privacy": {},
                "consent": {"status": "pending", "date": now},
            },
            "temporal_freshness": {
                "last_update": now,
                "update_source": "user_input",
                "freshness_score": 1.0,
            },
        }

    def _system_entity_fields(
        self,
        user: Dict[str, Any],
        match_result: Dict[str, Any],
        is_merge_required: bool,
        now: datetime,
    ) -> Dict[str, Any]:
        return {
            "user_id": str(user.get("_id")),
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

    def _role_profile_sections(self, user: Dict[str, Any]) -> Dict[str, Any]:
        return user.get("profile_data") or {}

    def _build_role_entity_payload(
        self,
        role: str,
        user: Dict[str, Any],
        entity_id: str,
        match_result: Dict[str, Any],
        now: datetime,
    ) -> Dict[str, Any]:
        profile = self._role_profile_sections(user)
        location = self._location_from_user(user)
        topics = self._topic_objects(user)
        skills = self._skill_objects(user)
        social_links = user.get("social_links") or {}
        phone = user.get("phone")
        email = user.get("email")
        system_fields = self._system_entity_fields(
            user,
            match_result,
            match_result.get("match_status") == "merge_required",
            now,
        )

        if role == "expert":
            identifiers = dict(profile.get("identifiers") or {})
            if social_links.get("orcid") and not identifiers.get("ORCID"):
                identifiers["ORCID"] = social_links.get("orcid")
            return {
                "expert_id": entity_id,
                "basic_info": {
                    "name": user.get("full_name", ""),
                    "location": location,
                },
                "identifiers": identifiers,
                "contact_info": {
                    "phones": [phone] if phone else [],
                    "emails": [email] if email else [],
                    "preferred_contact_method": None,
                    "social_links": social_links,
                },
                "academic_profile": profile.get("academic_profile") or {},
                "research_capacity": {
                    **(profile.get("research_capacity") or {}),
                    "research_directions": self._get_nested(profile, "research_capacity.research_directions") or [],
                    "research_topics": topics,
                    "technology": list(user.get("skills") or []) + list(user.get("custom_skills") or []),
                    "skills_methods": skills,
                },
                "academic_metrics": profile.get("academic_metrics") or {},
                "activities_and_outputs": profile.get("activities_and_outputs")
                or {
                    "list_outputs": [],
                    "owned_dataset_ids": [],
                    "accessible_dataset_ids": [],
                    "collaborators": [],
                    "grant_history": [],
                    "projects_participation": [],
                },
                "governance": profile.get("governance") or self._default_governance(now),
                **system_fields,
            }

        if role == "enterprise":
            return {
                "enterprise_id": entity_id,
                "basic_info": {
                    "name": user.get("full_name", ""),
                    "location": location,
                    "industries": self._get_nested(profile, "basic_info.industries") or [],
                },
                "representatives": profile.get("representatives")
                or {
                    "contact_person": {
                        "name": user.get("full_name", ""),
                        "email": email,
                        "phone": phone,
                    }
                },
                "rd_profile": {
                    **(profile.get("rd_profile") or {}),
                    "rd_focus_directions": self._get_nested(profile, "rd_profile.rd_focus_directions") or [],
                    "rd_focus_topics": topics,
                    "technology_needs": self._get_nested(profile, "rd_profile.technology_needs") or [],
                },
                "outputs_and_transfers": profile.get("outputs_and_transfers")
                or {
                    "commercialized_assets": [],
                    "patent_outputs": [],
                    "transfers_history": [],
                },
                "relations": profile.get("relations")
                or {"rd_projects": [], "worked_experts": [], "partnerships_history": []},
                "governance": profile.get("governance") or self._default_governance(now),
                **system_fields,
            }

        return {
            "funder_id": entity_id,
            "basic_info": {
                "name": user.get("full_name", ""),
                "type": None,
                "location": location,
                "budget_capacity": None,
            },
            "representatives": profile.get("representatives")
            or [
                {
                    "name": user.get("full_name", ""),
                    "position": None,
                    "email": email,
                    "phone": phone,
                }
            ],
            "funding_strategy": {
                **(profile.get("funding_strategy") or {}),
                "funding_directions": self._get_nested(profile, "funding_strategy.funding_directions") or [],
                "funding_topics": topics,
                "focus_regions": [user.get("province")] if user.get("province") else [],
                "focus_sectors": self._get_nested(profile, "funding_strategy.focus_sectors") or [],
                "trl_range_focus": self._get_nested(profile, "funding_strategy.trl_range_focus")
                or {"min": None, "max": None},
            },
            "programs": profile.get("programs") or [],
            "funding_history": profile.get("funding_history") or {"funded_projects": []},
            "impact_metrics": profile.get("impact_metrics") or {},
            "relations": profile.get("relations")
            or {"invests_in_enterprise_ids": [], "collaborates_with_funder_ids": []},
            "governance": profile.get("governance") or self._default_governance(now),
            **system_fields,
        }

    def _build_role_entity_update(self, role: str, user: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        profile = self._role_profile_sections(user)
        social_links = user.get("social_links") or {}
        phone = user.get("phone")
        email = user.get("email")
        update: Dict[str, Any] = {
            "basic_info.name": user.get("full_name", ""),
            "basic_info.location": self._location_from_user(user),
            "governance.temporal_freshness.last_update": now,
            "governance.temporal_freshness.update_source": "user_input",
            "updated_at": now,
        }
        if role == "expert":
            identifiers = dict(profile.get("identifiers") or {})
            if social_links.get("orcid") and not identifiers.get("ORCID"):
                identifiers["ORCID"] = social_links.get("orcid")
            if isinstance(profile.get("basic_info"), dict):
                for key, value in profile["basic_info"].items():
                    if key not in {"name", "location"}:
                        update[f"basic_info.{key}"] = value
            update.update(
                {
                    "identifiers": identifiers,
                    "contact_info.phones": [phone] if phone else [],
                    "contact_info.emails": [email] if email else [],
                    "contact_info.social_links": social_links,
                    "research_capacity.research_topics": self._topic_objects(user),
                    "research_capacity.technology": list(user.get("skills") or [])
                    + list(user.get("custom_skills") or []),
                    "research_capacity.skills_methods": self._skill_objects(user),
                }
            )
            for section in (
                "academic_profile",
                "academic_metrics",
                "activities_and_outputs",
                "governance",
            ):
                if isinstance(profile.get(section), dict):
                    update[section] = profile[section]
            if isinstance(profile.get("research_capacity"), dict):
                for key in (
                    "research_capacity.research_topics",
                    "research_capacity.technology",
                    "research_capacity.skills_methods",
                ):
                    update.pop(key, None)
                merged_research_capacity = dict(profile["research_capacity"])
                merged_research_capacity["research_topics"] = self._topic_objects(user)
                merged_research_capacity["technology"] = list(user.get("skills") or []) + list(user.get("custom_skills") or [])
                merged_research_capacity["skills_methods"] = self._skill_objects(user)
                update["research_capacity"] = merged_research_capacity
        elif role == "enterprise":
            if isinstance(profile.get("basic_info"), dict):
                for key, value in profile["basic_info"].items():
                    if key not in {"name", "location"}:
                        update[f"basic_info.{key}"] = value
            update.update(
                {
                    "rd_profile.rd_focus_topics": self._topic_objects(user),
                    "rd_profile.technology_needs": self._get_nested(profile, "rd_profile.technology_needs") or [],
                }
            )
            if isinstance(profile.get("representatives"), dict):
                for key, value in profile["representatives"].items():
                    update[f"representatives.{key}"] = value
            else:
                update["representatives.contact_person"] = {
                    "name": user.get("full_name", ""),
                    "email": email,
                    "phone": phone,
                }
            for section in (
                "organization_metrics",
                "investment_and_markets",
                "outputs_and_transfers",
                "relations",
                "governance",
            ):
                if isinstance(profile.get(section), dict):
                    update[section] = profile[section]
            if isinstance(profile.get("rd_profile"), dict):
                for key in (
                    "rd_profile.rd_focus_topics",
                    "rd_profile.technology_needs",
                ):
                    update.pop(key, None)
                merged_rd_profile = dict(profile["rd_profile"])
                merged_rd_profile["rd_focus_topics"] = self._topic_objects(user)
                update["rd_profile"] = merged_rd_profile
        elif role == "funder":
            if isinstance(profile.get("basic_info"), dict):
                for key, value in profile["basic_info"].items():
                    if key not in {"name", "location"}:
                        update[f"basic_info.{key}"] = value
            update.update(
                {
                    "representatives": [
                        {
                            "name": user.get("full_name", ""),
                            "position": None,
                            "email": email,
                            "phone": phone,
                        }
                    ],
                    "funding_strategy.funding_topics": self._topic_objects(user),
                    "funding_strategy.focus_regions": [user.get("province")] if user.get("province") else [],
                }
            )
            for section in (
                "representatives",
                "programs",
                "funding_history",
                "impact_metrics",
                "relations",
                "governance",
            ):
                if isinstance(profile.get(section), (dict, list)):
                    update[section] = profile[section]
            if isinstance(profile.get("funding_strategy"), dict):
                for key in (
                    "funding_strategy.funding_topics",
                    "funding_strategy.focus_regions",
                ):
                    update.pop(key, None)
                merged_funding_strategy = dict(profile["funding_strategy"])
                merged_funding_strategy["funding_topics"] = self._topic_objects(user)
                update["funding_strategy"] = merged_funding_strategy
        return update

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
        payload = self._build_role_entity_payload(role, user, entity_id, match_result, now)
        payload[id_field] = entity_id
        result = collection.insert_one(payload)
        payload["_id"] = result.inserted_id
        return payload

    def update_role_entity_from_user(self, user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        role = str(user.get("role") or "").lower()
        collection = self.get_entity_collection(role)
        if collection is None or role not in {"expert", "enterprise", "funder"}:
            return None
        user_id = str(user.get("_id"))
        update = self._build_role_entity_update(role, user)
        collection.update_one({"user_id": user_id}, {"$set": update})
        return collection.find_one({"user_id": user_id})

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
        keywords = list(project.get("keywords") or [])
        topics = [
            {
                "id": item,
                "name": RESEARCH_TOPIC_LABEL_MAP.get(str(item), str(item)),
                "parent_direction": research_topic_direction(str(item)) or project.get("field") or None,
                "parent_direction_label": research_direction_label(
                    research_topic_direction(str(item)) or project.get("field") or None
                ),
            }
            for item in keywords
            if item
        ]
        payload = {
            "project_id": str(project_id),
            "basic_info": {
                "title": project.get("title", ""),
                "description": project.get("description") or project.get("summary") or "",
                "research_directions": [project.get("field")] if project.get("field") else [],
                "research_topics": topics,
                "keywords": keywords,
                "location": {
                    "country_code": "VN",
                    "country_name": "Vietnam",
                    "region": project.get("location", ""),
                    "city": "",
                    "coordinates": {},
                },
            },
            "requirements_and_timeline": {
                "status": project.get("status", "draft"),
                "required_skills": [],
                "technology_readiness_level": project.get("trl"),
                "budget": {
                    "amount": project.get("budget"),
                    "currency": "VND",
                    "budget_type": None,
                },
                "timeline": {},
            },
            "rd_profile": {"required_dataset_ids": []},
            "relations": {"participants": [], "enterprise_partners": [], "funders": []},
            "follow_up_opportunities": {},
            "governance": self._default_governance(now),
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

    def list_entities_for_admin(
        self,
        entity_type: Optional[str] = None,
        kg_sync_status: Optional[str] = None,
        entity_verification_status: Optional[str] = None,
        limit: int = 50,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """List business entities for admin review screens."""
        types = [entity_type] if entity_type else ["expert", "enterprise", "funder", "project"]
        query: Dict[str, Any] = {}
        if kg_sync_status:
            query["kg_sync_status"] = kg_sync_status
        if entity_verification_status:
            query["entity_verification_status"] = entity_verification_status

        skip = max(page - 1, 0) * limit
        rows: List[Dict[str, Any]] = []
        per_type_limit = max(limit, 10)

        for role in types:
            collection = self.get_entity_collection(role)
            if collection is None:
                continue
            id_field = self.entity_id_field(role)
            for doc in collection.find(query).sort("updated_at", -1).limit(per_type_limit):
                rows.append(
                    {
                        "entity_type": role,
                        "entity_id": doc.get(id_field) or str(doc.get("_id")),
                        "name": self._display_name(doc),
                        "email": self._display_email(doc),
                        "kg_sync_status": doc.get("kg_sync_status"),
                        "entity_verification_status": doc.get("entity_verification_status"),
                        "visibility": doc.get("visibility"),
                        "participation_scope": doc.get("participation_scope"),
                        "trust_weight": doc.get("trust_weight"),
                        "sync_error": doc.get("sync_error"),
                        "duplicate_candidates": doc.get("duplicate_candidates") or [],
                        "matched_existing_entity_id": doc.get("matched_existing_entity_id"),
                        "merged_into": doc.get("merged_into"),
                        "updated_at": doc.get("updated_at"),
                    }
                )

        rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return rows[skip : skip + limit]

    def list_admin_audit_logs(self, limit: int = 50, page: int = 1) -> List[Dict[str, Any]]:
        skip = max(page - 1, 0) * limit
        cursor = self.audit_logs.find({}).sort("created_at", -1).skip(skip).limit(limit)
        return list(cursor)

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
