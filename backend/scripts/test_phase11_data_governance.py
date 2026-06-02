from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.canonical_taxonomy import canonicalize_industry, canonicalize_skill, canonicalize_topic
from services.admin_audit_log_service import AdminAuditLogService
from services.candidate_mask_service import CandidateMaskService
from services.governance_action_service import GovernanceActionService
from services import provisional_status as st
from services.data_quality_service import DataQualityService


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


class InsertOneResult:
    def __init__(self, inserted_id: str) -> None:
        self.inserted_id = inserted_id


class FakeCollection:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def find_one(self, query: dict) -> dict | None:
        for row in self.rows:
            if all(row.get(key) == value for key, value in query.items()):
                return dict(row)
        return None

    def update_one(self, query: dict, update: dict, upsert: bool = False) -> None:
        row = self.find_one(query)
        if row is None:
            if not upsert:
                return
            row = dict(query)
            self.rows.append(row)
        target = self.find_one(query)
        if target is None:
            target = row
        values = update.get("$set", {})
        for existing in self.rows:
            if all(existing.get(key) == value for key, value in query.items()):
                existing.update(values)
                return
        row.update(values)

    def insert_one(self, payload: dict) -> InsertOneResult:
        inserted_id = f"fake_{len(self.rows) + 1}"
        row = dict(payload)
        row["_id"] = inserted_id
        self.rows.append(row)
        return InsertOneResult(inserted_id)


class FakeDb:
    def __init__(self) -> None:
        self.taxonomy_aliases = FakeCollection()
        self.data_quality_requests = FakeCollection()

    def __getitem__(self, key: str) -> FakeCollection:
        return getattr(self, key)


class FakeRepo:
    def __init__(self) -> None:
        self.db = FakeDb()
        self.entities = {
            ("project", "prj_orphan"): {
                "project_id": "prj_orphan",
                "basic_info": {"title": "Orphan"},
                "visibility": "limited",
                "participation_scope": "owner_only",
                "recommendable_as_target": True,
                "allow_as_intermediate_node": True,
            }
        }
        self.audit_logs: list[dict] = []

    def find_entity_by_id(self, entity_type: str, entity_id: str) -> dict | None:
        entity = self.entities.get((entity_type, entity_id))
        return dict(entity) if entity else None

    def get_entity_collection(self, entity_type: str) -> "FakeRepo":
        return self

    def entity_id_field(self, entity_type: str) -> str:
        return {"project": "project_id", "expert": "expert_id", "enterprise": "enterprise_id", "funder": "funder_id"}[entity_type]

    def update_one(self, query: dict, update: dict, upsert: bool = False) -> None:
        entity_type = "project" if "project_id" in query else "expert"
        entity_id = next(iter(query.values()))
        entity = self.entities.setdefault((entity_type, entity_id), dict(query))
        entity.update(update.get("$set", {}))

    def insert_admin_audit_log(self, payload: dict) -> dict:
        payload = dict(payload)
        payload["_id"] = f"audit_{len(self.audit_logs) + 1}"
        self.audit_logs.append(payload)
        return payload

    def _json_safe(self, value):
        return value


class FakeGraphRepo:
    def __init__(self) -> None:
        self.updates: list[tuple[str, str, dict]] = []

    def update_entity_verification_status(self, entity_type: str, entity_id: str, properties: dict) -> None:
        self.updates.append((entity_type, entity_id, dict(properties)))


def test_canonical_taxonomy() -> None:
    assert_true(canonicalize_topic("AI y tế").id == "ai-healthcare", "AI y te alias should map")
    assert_true(canonicalize_topic("ML").id == "machine-learning", "ML alias should map")
    assert_true(canonicalize_skill("torch").id == "pytorch", "torch skill alias should map")
    assert_true(canonicalize_industry("edtech").id == "education", "edtech industry alias should map")
    assert_true(canonicalize_topic("very custom topic") is None, "custom topic should remain unmapped")


def test_data_quality_good_verified_project() -> None:
    service = DataQualityService()
    entity = {
        "project_id": "prj_test",
        "basic_info": {
            "title": "AI Healthcare",
            "research_topics": [{"id": "ai-healthcare", "name": "AI trong y te"}],
            "location": {"country_code": "VN", "region": "Ho Chi Minh"},
        },
        "requirements_and_timeline": {
            "required_skills": [{"name": "Python"}, {"name": "Machine Learning"}],
        },
        "applied_industries": [{"name": "Healthcare"}],
        "relations": {"participants": ["exp_001"]},
        "entity_verification_status": st.ENTITY_VERIFIED,
        "kg_sync_status": st.KG_SYNCED_VERIFIED,
        "participation_scope": st.SCOPE_PUBLIC,
        "trust_weight": 1.0,
        "embedding": {"status": st.EMBEDDING_READY, "signal": st.EMBEDDING_SIGNAL_OK},
    }
    quality = service.evaluate("project", entity)
    assert_true(quality["score"] >= 0.7, f"expected good score, got {quality}")
    assert_true(quality["level"] in {"good", "excellent"}, f"expected good/excellent, got {quality}")
    assert_true(service.review_status("project", entity, quality) == "verified", "verified project should be verified")


def test_data_quality_flags_provisional_sparse_entity() -> None:
    service = DataQualityService()
    entity = {
        "expert_id": "exp_sparse",
        "basic_info": {"name": "Sparse Expert"},
        "entity_verification_status": st.ENTITY_UNVERIFIED,
        "kg_sync_status": st.KG_MERGE_REQUIRED,
        "participation_scope": st.SCOPE_OWNER_ONLY,
        "trust_weight": 0.3,
        "embedding": {"status": st.EMBEDDING_FAILED, "signal": st.EMBEDDING_SIGNAL_NONE},
        "duplicate_candidates": [{"entity_id": "exp_001"}],
    }
    quality = service.evaluate("expert", entity)
    assert_true(quality["score"] < 0.5, f"expected poor score, got {quality}")
    assert_true("research_topics" in quality["missing_fields"], "missing topics should be flagged")
    assert_true("merge_required" in quality["warnings"], "merge_required should be flagged")
    assert_true(service.review_status("expert", entity, quality) == "merge_required", "duplicate should need merge")


def test_governance_actions_and_masking() -> None:
    repo = FakeRepo()
    graph = FakeGraphRepo()
    service = GovernanceActionService(repo=repo, graph_repo=graph)

    try:
        service.map_taxonomy_alias(
            taxonomy_type="topic",
            raw_value="AI y te custom",
            canonical_id="ai-healthcare",
            reason="",
            admin_user_id="admin_1",
        )
        raise AssertionError("missing reason should fail")
    except ValueError:
        pass

    try:
        service.map_taxonomy_alias(
            taxonomy_type="topic",
            raw_value="AI y te custom",
            canonical_id="missing-topic",
            reason="test",
            admin_user_id="admin_1",
        )
        raise AssertionError("invalid canonical_id should fail")
    except ValueError:
        pass

    alias_result = service.map_taxonomy_alias(
        taxonomy_type="topic",
        raw_value="AI y te custom",
        canonical_id="ai-healthcare",
        reason="Vietnamese alias",
        admin_user_id="admin_1",
    )
    assert_true(alias_result["after"]["canonical_id"] == "ai-healthcare", "taxonomy alias should be stored")
    AdminAuditLogService(repo).log(
        admin_user_id="admin_1",
        action="map_taxonomy_alias",
        entity_type="taxonomy:topic",
        entity_id="AI y te custom",
        before=alias_result["before"],
        after=alias_result["after"],
        reason="Vietnamese alias",
    )
    assert_true(repo.audit_logs[-1]["action"] == "map_taxonomy_alias", "taxonomy action should be auditable")

    info_result = service.request_more_information(
        entity_type="project",
        entity_id="prj_orphan",
        requested_fields=["research_topics", "skills_or_technology"],
        admin_note="Missing core recommendation fields",
        reason="low quality",
        admin_user_id="admin_1",
    )
    assert_true(info_result["after"]["latest_data_quality_request"]["status"] == "open", "request should be linked")
    assert_true(len(repo.db.data_quality_requests.rows) == 1, "request should be inserted")

    mark_result = service.mark_orphan_cleanup_candidate(
        entity_type="project",
        entity_id="prj_orphan",
        reason="orphan smoke test",
        admin_user_id="admin_1",
    )
    assert_true(mark_result["after"]["cleanup_candidate"] is True, "orphan should be marked cleanup candidate")
    assert_true(graph.updates[-1][2]["cleanup_candidate"] is True, "graph node should be marked")

    disabled = service.disable_orphan_from_recommendation(
        entity_type="project",
        entity_id="prj_orphan",
        reason="orphan should not be recommended",
        admin_user_id="admin_1",
    )
    assert_true(disabled["after"]["visibility"] == st.VISIBILITY_HIDDEN, "soft-disabled node should be hidden")
    assert_true(disabled["after"]["participation_scope"] == st.SCOPE_DISABLED, "soft-disabled node scope should be disabled")
    decision = CandidateMaskService(repo=None).evaluate_target_status(
        {
            "entity_type": "project",
            "entity_id": "prj_orphan",
            "visibility": disabled["after"]["visibility"],
            "participation_scope": disabled["after"]["participation_scope"],
            "entity_verification_status": st.ENTITY_UNVERIFIED,
            "kg_sync_status": st.KG_SYNCED_UNVERIFIED,
            "recommendable_as_target": disabled["after"]["recommendable_as_target"],
            "allow_as_intermediate_node": disabled["after"]["allow_as_intermediate_node"],
        },
        mode="public",
    )
    assert_true(not decision.allowed, "soft-disabled orphan should be blocked by CandidateMaskService")


def main() -> int:
    test_canonical_taxonomy()
    test_data_quality_good_verified_project()
    test_data_quality_flags_provisional_sparse_entity()
    test_governance_actions_and_masking()
    print("Phase 11 data governance tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
