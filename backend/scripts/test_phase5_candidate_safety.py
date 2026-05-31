"""Smoke test Phase 5 candidate mask and embedding candidate search."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repositories.auth_repo import AuthRepository  # noqa: E402
from repositories.embedding_repo import EmbeddingRepository  # noqa: E402
from repositories.pgpr_graph_repo import PGPRGraphRepository  # noqa: E402
from services import provisional_status as st  # noqa: E402
from services.candidate_mask_service import CandidateMaskService  # noqa: E402
from services.embedding_candidate_service import EmbeddingCandidateService  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402


OUT = Path("scripts") / "phase5_candidate_safety_report.json"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def unit_vector(first: float, second: float = 0.0, dimension: int = 128) -> List[float]:
    values = [0.0] * dimension
    values[0] = first
    values[1] = second
    norm = sum(v * v for v in values) ** 0.5
    return [v / norm for v in values] if norm else values


def embedding(vector: List[float], source_hash: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "status": st.EMBEDDING_READY,
        "job_id": "job_phase5_seed",
        "last_event_id": "evt_phase5_seed",
        "retry_count": 0,
        "max_retry": 3,
        "model": "graphsage_lite_v1",
        "version": 1,
        "dimension": 128,
        "source_hash": source_hash,
        "last_queued_at": now,
        "last_processed_at": now,
        "updated_at": now,
        "error": None,
        "error_type": None,
        "vector": vector,
        "normalized": True,
        "signal": st.EMBEDDING_SIGNAL_OK,
    }


def insert_entity(repo: AuthRepository, entity_type: str, doc: Dict[str, Any]) -> None:
    collection = repo.get_entity_collection(entity_type)
    assert_true(collection is not None, f"missing collection for {entity_type}")
    id_field = repo.entity_id_field(entity_type)
    collection.delete_many({id_field: doc[id_field]})
    collection.insert_one(doc)


def main() -> int:
    repo = AuthRepository()
    embedding_repo = EmbeddingRepository(repo)
    mask = CandidateMaskService(repo)
    candidate_service = EmbeddingCandidateService(embedding_repo, mask)
    suffix = str(int(time.time() * 1000))
    owner = f"owner_phase5_{suffix}"
    other_owner = f"other_phase5_{suffix}"

    source_id = f"phase5_exp_{suffix}"
    source_embedding = embedding(unit_vector(1.0), "source_hash")
    insert_entity(
        repo,
        "expert",
        {
            "expert_id": source_id,
            "basic_info": {"name": "Phase5 Source Expert"},
            "user_id": owner,
            **st.default_unverified_state(),
            "kg_sync_status": st.KG_SYNCED_UNVERIFIED,
            "embedding": source_embedding,
            "embedding_status": st.EMBEDDING_READY,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
    )
    embedding_repo.upsert_embedding_record("expert", source_id, source_embedding)

    candidates = [
        (
            "public",
            {
                **st.verified_state(),
                "project_id": f"phase5_prj_public_{suffix}",
                "basic_info": {"title": "Public verified project"},
                "owner_id": "public_owner",
                "embedding": embedding(unit_vector(0.99, 0.01), "public_hash"),
            },
        ),
        (
            "owner_only_other",
            {
                **st.default_unverified_state(),
                "project_id": f"phase5_prj_owner_other_{suffix}",
                "basic_info": {"title": "Owner-only project from another user"},
                "owner_id": other_owner,
                "kg_sync_status": st.KG_SYNCED_UNVERIFIED,
                "embedding": embedding(unit_vector(0.98, 0.02), "owner_other_hash"),
            },
        ),
        (
            "owner_only_self",
            {
                **st.default_unverified_state(),
                "project_id": f"phase5_prj_owner_self_{suffix}",
                "basic_info": {"title": "Owner-only current user project"},
                "owner_id": owner,
                "kg_sync_status": st.KG_SYNCED_UNVERIFIED,
                "embedding": embedding(unit_vector(0.97, 0.03), "owner_self_hash"),
            },
        ),
        (
            "rejected",
            {
                **st.default_unverified_state(),
                "project_id": f"phase5_prj_rejected_{suffix}",
                "basic_info": {"title": "Rejected project"},
                "owner_id": owner,
                "entity_verification_status": st.ENTITY_REJECTED,
                "kg_sync_status": st.KG_REJECTED,
                "embedding": embedding(unit_vector(0.96, 0.04), "rejected_hash"),
            },
        ),
        (
            "hidden",
            {
                **st.verified_state(),
                "project_id": f"phase5_prj_hidden_{suffix}",
                "basic_info": {"title": "Hidden project"},
                "visibility": st.VISIBILITY_HIDDEN,
                "embedding": embedding(unit_vector(0.95, 0.05), "hidden_hash"),
            },
        ),
        (
            "target_false",
            {
                **st.verified_state(),
                "project_id": f"phase5_prj_target_false_{suffix}",
                "basic_info": {"title": "Not recommendable target"},
                "recommendable_as_target": False,
                "embedding": embedding(unit_vector(0.94, 0.06), "target_false_hash"),
            },
        ),
        (
            "merge_required",
            {
                **st.default_unverified_state(0.3),
                "project_id": f"phase5_prj_merge_{suffix}",
                "basic_info": {"title": "Merge required project"},
                "owner_id": owner,
                "kg_sync_status": st.KG_MERGE_REQUIRED,
                "embedding": embedding(unit_vector(0.93, 0.07), "merge_hash"),
            },
        ),
    ]

    for _, doc in candidates:
        doc["embedding_status"] = st.EMBEDDING_READY
        doc["created_at"] = datetime.now(timezone.utc)
        doc["updated_at"] = datetime.now(timezone.utc)
        insert_entity(repo, "project", doc)
        embedding_repo.upsert_embedding_record("project", doc["project_id"], doc["embedding"])

    public_results = candidate_service.nearest_candidates(
        "expert",
        source_id,
        "project",
        mode="public",
        current_user_id=None,
        limit=20,
        candidate_pool_limit=100,
    )
    public_ids = {item["id"] for item in public_results}
    assert_true(f"phase5_prj_public_{suffix}" in public_ids, f"public verified missing: {public_ids}")
    assert_true(f"phase5_prj_owner_other_{suffix}" not in public_ids, "owner_only other leaked in public")
    assert_true(f"phase5_prj_owner_self_{suffix}" not in public_ids, "owner_only self leaked in public")
    assert_true(f"phase5_prj_rejected_{suffix}" not in public_ids, "rejected leaked in public")
    assert_true(f"phase5_prj_hidden_{suffix}" not in public_ids, "hidden leaked in public")
    assert_true(f"phase5_prj_target_false_{suffix}" not in public_ids, "recommendable_as_target=false leaked in public")

    personal_results = candidate_service.nearest_candidates(
        "expert",
        source_id,
        "project",
        mode="personal",
        current_user_id=owner,
        limit=20,
        candidate_pool_limit=100,
    )
    personal_ids = {item["id"] for item in personal_results}
    assert_true(f"phase5_prj_owner_self_{suffix}" in personal_ids, f"owner self missing in personal: {personal_ids}")
    assert_true(f"phase5_prj_owner_other_{suffix}" not in personal_ids, "owner_only other leaked in personal")

    merge_decision = mask.intermediate_decision("project", f"phase5_prj_merge_{suffix}", mode="personal", current_user_id=owner)
    assert_true(not merge_decision.allowed, f"merge_required allowed as intermediate: {merge_decision}")
    assert_true("merge_required_not_intermediate" in merge_decision.reasons, f"missing merge reason: {merge_decision.reasons}")

    admin_debug_results = candidate_service.nearest_candidates(
        "expert",
        source_id,
        "project",
        mode="admin_debug",
        current_user_id=owner,
        limit=200,
        candidate_pool_limit=1000,
        admin_debug=True,
    )
    admin_by_id = {item["id"]: item for item in admin_debug_results}
    rejected = admin_by_id.get(f"phase5_prj_rejected_{suffix}")
    hidden = admin_by_id.get(f"phase5_prj_hidden_{suffix}")
    target_false = admin_by_id.get(f"phase5_prj_target_false_{suffix}")
    assert_true(rejected is not None, "admin_debug should include rejected candidate")
    assert_true("entity_rejected" in (rejected.get("candidate_mask") or {}).get("reasons", []), rejected)
    assert_true(hidden is not None, "admin_debug should include hidden candidate")
    assert_true("visibility_hidden" in (hidden.get("candidate_mask") or {}).get("reasons", []), hidden)
    assert_true(target_false is not None, "admin_debug should include target false candidate")
    assert_true("target_not_recommendable" in (target_false.get("candidate_mask") or {}).get("reasons", []), target_false)

    # Embedding candidate edge cases should fail closed, not crash.
    no_vector_source = f"phase5_exp_no_vector_{suffix}"
    insert_entity(
        repo,
        "expert",
        {
            "expert_id": no_vector_source,
            "basic_info": {"name": "No vector source"},
            "user_id": owner,
            **st.default_unverified_state(),
            "kg_sync_status": st.KG_SYNCED_UNVERIFIED,
            "embedding": {
                **source_embedding,
                "status": st.EMBEDDING_PENDING,
                "vector": None,
                "normalized": False,
            },
            "embedding_status": st.EMBEDDING_PENDING,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
    )
    assert_true(
        candidate_service.nearest_candidates("expert", no_vector_source, "project", mode="personal", current_user_id=owner) == [],
        "source without ready vector should return empty candidates",
    )

    bad_targets = [
        (
            "not_normalized",
            {
                **st.verified_state(),
                "project_id": f"phase5_prj_not_normalized_{suffix}",
                "basic_info": {"title": "Not normalized embedding"},
                "embedding": {**embedding(unit_vector(0.9, 0.1), "not_normalized"), "normalized": False},
            },
        ),
        (
            "wrong_dimension",
            {
                **st.verified_state(),
                "project_id": f"phase5_prj_wrong_dimension_{suffix}",
                "basic_info": {"title": "Wrong dimension embedding"},
                "embedding": {**embedding([1.0, 0.0], "wrong_dimension"), "dimension": 2},
            },
        ),
        (
            "no_signal",
            {
                **st.verified_state(),
                "project_id": f"phase5_prj_no_signal_{suffix}",
                "basic_info": {"title": "No signal embedding"},
                "embedding": {**embedding([0.0] * 128, "no_signal"), "signal": st.EMBEDDING_SIGNAL_NONE},
            },
        ),
    ]
    for _, doc in bad_targets:
        doc["embedding_status"] = doc["embedding"]["status"]
        doc["created_at"] = datetime.now(timezone.utc)
        doc["updated_at"] = datetime.now(timezone.utc)
        insert_entity(repo, "project", doc)
        embedding_repo.upsert_embedding_record("project", doc["project_id"], doc["embedding"])

    edge_results = candidate_service.nearest_candidates(
        "expert",
        source_id,
        "project",
        mode="public",
        current_user_id=None,
        limit=50,
        candidate_pool_limit=200,
    )
    edge_ids = {item["id"] for item in edge_results}
    assert_true(f"phase5_prj_not_normalized_{suffix}" not in edge_ids, "not normalized vector leaked")
    assert_true(f"phase5_prj_wrong_dimension_{suffix}" not in edge_ids, "wrong dimension vector leaked")
    assert_true(f"phase5_prj_no_signal_{suffix}" not in edge_ids, "no_signal vector leaked")

    graph_repo = PGPRGraphRepository()
    graph_source_id = f"phase5_graph_exp_{suffix}"
    graph_nodes = [
        (
            "expert",
            graph_source_id,
            {
                "name": "Phase5 Graph Source",
                "user_id": owner,
                **st.default_unverified_state(),
                "kg_sync_status": st.KG_SYNCED_UNVERIFIED,
            },
        ),
        (
            "project",
            f"phase5_graph_public_{suffix}",
            {
                "name": "Phase5 Graph Public",
                **st.verified_state(),
            },
        ),
        (
            "project",
            f"phase5_graph_owner_other_{suffix}",
            {
                "name": "Phase5 Graph Other Owner",
                "owner_user_id": other_owner,
                **st.default_unverified_state(),
                "kg_sync_status": st.KG_SYNCED_UNVERIFIED,
            },
        ),
        (
            "project",
            f"phase5_graph_owner_self_{suffix}",
            {
                "name": "Phase5 Graph Self Owner",
                "owner_user_id": owner,
                **st.default_unverified_state(),
                "kg_sync_status": st.KG_SYNCED_UNVERIFIED,
            },
        ),
        (
            "project",
            f"phase5_graph_hidden_{suffix}",
            {
                "name": "Phase5 Graph Hidden",
                **st.verified_state(),
                "visibility": st.VISIBILITY_HIDDEN,
            },
        ),
        (
            "project",
            f"phase5_graph_rejected_{suffix}",
            {
                "name": "Phase5 Graph Rejected",
                **st.default_unverified_state(),
                "entity_verification_status": st.ENTITY_REJECTED,
                "kg_sync_status": st.KG_REJECTED,
            },
        ),
    ]
    for entity_type, entity_id, props in graph_nodes:
        graph_repo.upsert_provisional_entity(entity_type, entity_id, props)
    for _, entity_id, _ in graph_nodes[1:]:
        graph_repo.run_write(
            """
            MATCH (s:Expert {expert_id: $source_id})
            MATCH (p:Project {project_id: $project_id})
            MERGE (s)-[r:PHASE5_TEST_LINK]->(p)
            SET r.updated_at = datetime()
            """,
            source_id=graph_source_id,
            project_id=entity_id,
        )
    public_graph = graph_repo.find_entity_neighbors(
        "Expert",
        graph_source_id,
        depth=1,
        limit=50,
        mode="public",
    )
    public_graph_ids = {node["id"] for node in public_graph.get("nodes") or []}
    assert_true(f"phase5_graph_public_{suffix}" in public_graph_ids, public_graph_ids)
    assert_true(f"phase5_graph_owner_other_{suffix}" not in public_graph_ids, "graph leaked owner_only other in public")
    assert_true(f"phase5_graph_owner_self_{suffix}" not in public_graph_ids, "graph leaked owner_only self in public")
    assert_true(f"phase5_graph_hidden_{suffix}" not in public_graph_ids, "graph leaked hidden in public")
    assert_true(f"phase5_graph_rejected_{suffix}" not in public_graph_ids, "graph leaked rejected in public")
    personal_graph = graph_repo.find_entity_neighbors(
        "Expert",
        graph_source_id,
        depth=1,
        limit=50,
        mode="personal",
        current_user_id=owner,
    )
    personal_graph_ids = {node["id"] for node in personal_graph.get("nodes") or []}
    assert_true(f"phase5_graph_owner_self_{suffix}" in personal_graph_ids, personal_graph_ids)
    assert_true(f"phase5_graph_owner_other_{suffix}" not in personal_graph_ids, "graph leaked owner_only other in personal")

    with TestClient(app) as client:
        admin_debug_recommendation = client.post(
            "/api/v1/recommendations/policy",
            json={
                "source_id": source_id,
                "source_type": "expert",
                "target_type": "project",
                "mode": "admin_debug",
                "limit": 1,
            },
        )
        assert_true(
            admin_debug_recommendation.status_code == 403,
            f"admin_debug recommendation should require admin: {admin_debug_recommendation.status_code}",
        )
        admin_debug_graph = client.get(
            f"/api/v1/graph/entities/expert/{source_id}/neighbors?mode=admin_debug&depth=1&limit=10"
        )
        assert_true(
            admin_debug_graph.status_code == 403,
            f"admin_debug graph should require admin: {admin_debug_graph.status_code}",
        )

    report = {
        "status": "passed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_id": source_id,
        "public_ids": sorted(public_ids),
        "personal_ids": sorted(personal_ids),
        "admin_debug_count": len(admin_debug_results),
        "merge_intermediate_reasons": merge_decision.reasons,
        "embedding_edge_ids": sorted(edge_ids),
        "graph_public_ids": sorted(public_graph_ids),
        "graph_personal_ids": sorted(personal_graph_ids),
        "admin_debug_requires_admin": True,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"PASS written {OUT}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        OUT.write_text(
            json.dumps(
                {
                    "status": "failed",
                    "error": str(exc),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        print(f"FAIL {exc}")
        sys.exit(1)
