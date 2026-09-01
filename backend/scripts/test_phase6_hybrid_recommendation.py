"""Phase 6 hybrid recommendation — extended runtime proofs before Phase 7/8."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repositories.auth_repo import AuthRepository  # noqa: E402
from repositories.embedding_repo import EmbeddingRepository  # noqa: E402
from services import provisional_status as st  # noqa: E402
from services.candidate_mask_service import CandidateMaskService  # noqa: E402
from services.embedding_candidate_service import EmbeddingCandidateService  # noqa: E402
from services.hybrid_recommendation_service import HybridRecommendationService  # noqa: E402
from services.recommendation_service import RecommendationService  # noqa: E402

OUT = Path("scripts") / "phase6_hybrid_report.json"
FIXTURES: List[Tuple[str, str]] = []


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def unit_vector(first: float, second: float = 0.0, dimension: int = 128) -> List[float]:
    values = [0.0] * dimension
    values[0] = first
    values[1] = second
    norm = sum(v * v for v in values) ** 0.5
    return [v / norm for v in values] if norm else values


def embedding_doc(
    vector: List[float],
    *,
    status: str = st.EMBEDDING_READY,
    source_hash: str = "phase6_hash",
    signal: str = st.EMBEDDING_SIGNAL_OK,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "status": status,
        "job_id": "job_phase6_test",
        "model": "graphsage_lite_v1",
        "version": 1,
        "dimension": 128,
        "source_hash": source_hash,
        "vector": vector,
        "normalized": True,
        "signal": signal,
        "updated_at": now,
    }


def insert_entity(repo: AuthRepository, entity_type: str, doc: Dict[str, Any]) -> None:
    collection = repo.get_entity_collection(entity_type)
    assert_true(collection is not None, f"no collection for {entity_type}")
    id_field = repo.entity_id_field(entity_type)
    collection.delete_many({id_field: doc[id_field]})
    collection.insert_one(doc)
    FIXTURES.append((entity_type, str(doc[id_field])))


def cleanup_fixtures(repo: AuthRepository, embedding_repo: EmbeddingRepository) -> None:
    for entity_type, entity_id in reversed(FIXTURES):
        collection = repo.get_entity_collection(entity_type)
        if collection is not None:
            collection.delete_many({repo.entity_id_field(entity_type): entity_id})
        try:
            embedding_repo.delete_embedding_record(entity_type, entity_id)
        except AttributeError:
            embedding_repo.embedding_collection.delete_many({"entity_type": entity_type, "entity_id": entity_id})


def finalize_pipeline(
    rs: RecommendationService,
    items: List[Dict[str, Any]],
    *,
    source_id: str,
    source_label: str,
    target_label: str,
    src_ctx: Dict[str, Any],
) -> List[Dict[str, Any]]:
    out = rs._apply_provisional_rules(
        items,
        source_id=source_id,
        source_label=source_label,
        target_label=target_label,
        mode="public",
        current_user_id=None,
    )
    out = rs._apply_scoring_metadata(out, source_context=src_ctx)
    return rs._sync_display_scores(out)


async def run_hybrid(
    hybrid: HybridRecommendationService,
    pgpr_pool: List[Dict[str, Any]],
    *,
    source_type: str,
    source_id: str,
    target_type: str,
    src_ctx: Dict[str, Any] | None = None,
    limit: int = 10,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    return await hybrid.build_hybrid_candidates(
        pgpr_pool,
        source_type=source_type,
        source_id=source_id,
        target_type=target_type,
        limit=limit,
        source_context=src_ctx,
    )


def test_hybrid_ready_new_source(
    repo: AuthRepository,
    embedding_repo: EmbeddingRepository,
    hybrid: HybridRecommendationService,
    rs: RecommendationService,
    suffix: str,
    report: Dict[str, Any],
) -> None:
    source_id = f"phase6_prj_ready_{suffix}"
    emb_only_id = f"phase6_exp_emb_only_{suffix}"
    pgpr_other_id = f"phase6_exp_pgpr_other_{suffix}"

    src_emb = embedding_doc(unit_vector(1.0, 0.0), source_hash=f"src_{suffix}")
    insert_entity(
        repo,
        "project",
        {
            "project_id": source_id,
            "title": "Phase6 Hybrid Ready Project",
            **st.verified_state(),
            "embedding": src_emb,
            "embedding_status": st.EMBEDDING_READY,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
    )
    embedding_repo.upsert_embedding_record("project", source_id, src_emb)

    tgt_emb = embedding_doc(unit_vector(0.99, 0.01), source_hash=f"tgt_emb_{suffix}")
    insert_entity(
        repo,
        "expert",
        {
            "expert_id": emb_only_id,
            "name": "Embedding Only Expert",
            **st.verified_state(),
            "embedding": tgt_emb,
            "embedding_status": st.EMBEDDING_READY,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
    )
    embedding_repo.upsert_embedding_record("expert", emb_only_id, tgt_emb)

    other_emb = embedding_doc(unit_vector(0.2, 0.98), source_hash=f"tgt_other_{suffix}")
    insert_entity(
        repo,
        "expert",
        {
            "expert_id": pgpr_other_id,
            "name": "PGPR Other Expert",
            **st.verified_state(),
            "embedding": other_emb,
            "embedding_status": st.EMBEDDING_READY,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
    )
    embedding_repo.upsert_embedding_record("expert", pgpr_other_id, other_emb)

    src_ctx = hybrid.source_recommendation_context("project", source_id)
    assert_true(src_ctx["recommendation_mode"] == "hybrid_ready", src_ctx)
    assert_true(src_ctx["cold_start"] is False, src_ctx)
    assert_true(src_ctx["embedding_status"] == st.EMBEDDING_READY, src_ctx)

    pgpr_pool = [
        {
            "id": pgpr_other_id,
            "name": "PGPR Other Expert",
            "score": 0.7,
            "reasoning_paths": [{"source": "pgpr", "score": 0.7}],
            "scoring_method": "pgpr_policy",
        }
    ]
    merged, _ = asyncio.run(
        run_hybrid(hybrid, pgpr_pool, source_type="project", source_id=source_id, target_type="expert", src_ctx=src_ctx)
    )
    ids = {str(x["id"]) for x in merged}
    assert_true(emb_only_id in ids, f"embedding-only expert missing from pool: {ids}")
    emb_item = next(x for x in merged if x["id"] == emb_only_id)
    assert_true("embedding" in (emb_item.get("candidate_sources") or []), emb_item)

    final = finalize_pipeline(rs, merged, source_id=source_id, source_label="Project", target_label="Expert", src_ctx=src_ctx)
    report["hybrid_ready_new_source"] = {
        "source_id": source_id,
        "recommendation_mode": src_ctx["recommendation_mode"],
        "embedding_only_in_pool": emb_only_id in {x["id"] for x in final},
        "embedding_only_sources": emb_item.get("candidate_sources"),
    }


def test_embedding_only_caps(
    hybrid: HybridRecommendationService,
    rs: RecommendationService,
    report: Dict[str, Any],
) -> None:
    verified_item = {
        "id": "exp_cap_v",
        "name": "Cap Verified",
        "type": "expert",
        "score": 0.99,
        "reasoning_paths": [],
        "embedding_similarity": 0.95,
        "evidence_level": "embedding_only",
        "scoring_method": "hybrid_embedding",
        "candidate_sources": ["embedding"],
        "uses_provisional_data": False,
    }
    capped_v = hybrid._apply_evidence_cap(dict(verified_item), score=0.99)
    assert_true(float(capped_v["score"]) <= 0.65, capped_v)

    provisional_item = dict(verified_item)
    provisional_item["id"] = "exp_cap_p"
    provisional_item["uses_provisional_data"] = True
    final_p = finalize_pipeline(
        rs,
        [provisional_item],
        source_id="prj_x",
        source_label="Project",
        target_label="Expert",
        src_ctx={
            "cold_start": False,
            "embedding_status": st.EMBEDDING_READY,
            "recommendation_mode": "hybrid_ready",
            "recommendation_readiness": "public_hybrid_ready",
        },
    )
    assert_true(final_p[0]["evidence_level"] == "embedding_only", final_p[0])
    assert_true(len(final_p[0].get("reasoning_paths") or []) == 0, final_p[0])
    assert_true(float(final_p[0]["score"]) <= 0.50, final_p[0])
    assert_true(final_p[0]["score"] == final_p[0]["final_score"], final_p[0])

    report["embedding_only_caps"] = {
        "verified_cap": float(capped_v["score"]),
        "provisional_cap": float(final_p[0]["score"]),
        "score_equals_final": final_p[0]["score"] == final_p[0]["final_score"],
    }


def test_pgpr_anchor_scoring_priority(
    repo: AuthRepository,
    embedding_repo: EmbeddingRepository,
    hybrid: HybridRecommendationService,
    suffix: str,
    report: Dict[str, Any],
) -> None:
    source_id = f"phase6_prj_anchor_{suffix}"
    path_id = f"phase6_exp_path_anchor_{suffix}"
    embedding_only_id = f"phase6_exp_embedding_anchor_{suffix}"

    src_emb = embedding_doc(unit_vector(1.0, 0.0), source_hash=f"anchor_src_{suffix}")
    insert_entity(
        repo,
        "project",
        {
            "project_id": source_id,
            "title": "Anchor Scoring Project",
            **st.verified_state(),
            "embedding": src_emb,
            "embedding_status": st.EMBEDDING_READY,
        },
    )
    embedding_repo.upsert_embedding_record("project", source_id, src_emb)

    path_emb = embedding_doc(unit_vector(0.1, 0.99), source_hash=f"anchor_path_{suffix}")
    insert_entity(
        repo,
        "expert",
        {
            "expert_id": path_id,
            "name": "Strong Path Expert",
            **st.verified_state(),
            "embedding": path_emb,
            "embedding_status": st.EMBEDDING_READY,
        },
    )
    embedding_repo.upsert_embedding_record("expert", path_id, path_emb)

    embedding_only_emb = embedding_doc(unit_vector(0.99, 0.01), source_hash=f"anchor_emb_{suffix}")
    insert_entity(
        repo,
        "expert",
        {
            "expert_id": embedding_only_id,
            "name": "Embedding Similar Expert",
            **st.verified_state(),
            "embedding": embedding_only_emb,
            "embedding_status": st.EMBEDDING_READY,
        },
    )
    embedding_repo.upsert_embedding_record("expert", embedding_only_id, embedding_only_emb)

    src_ctx = hybrid.source_recommendation_context("project", source_id)
    pgpr_pool = [
        {
            "id": path_id,
            "name": "Strong Path Expert",
            "score": 0.72,
            "reasoning_paths": [{"source": "pgpr", "score": 0.72, "relations": ["REQUIRES_SKILL"]}],
            "scoring_method": "pgpr_policy",
        }
    ]
    ranked, _ = asyncio.run(
        run_hybrid(
            hybrid,
            pgpr_pool,
            source_type="project",
            source_id=source_id,
            target_type="expert",
            src_ctx=src_ctx,
            limit=5,
        )
    )
    ids = [str(item.get("id")) for item in ranked]
    assert_true(path_id in ids, ranked)
    assert_true(embedding_only_id in ids, ranked)
    path_index = ids.index(path_id)
    embedding_index = ids.index(embedding_only_id)
    assert_true(
        path_index < embedding_index,
        f"path-supported candidate should stay above embedding-only candidate: {ranked}",
    )
    path_item = next(item for item in ranked if item.get("id") == path_id)
    embedding_item = next(item for item in ranked if item.get("id") == embedding_only_id)
    assert_true(path_item.get("evidence_level") == "path_supported", path_item)
    assert_true(embedding_item.get("evidence_level") == "embedding_only", embedding_item)
    assert_true(float(path_item.get("score") or 0) > float(embedding_item.get("score") or 0), ranked)

    report["pgpr_anchor_scoring_priority"] = {
        "path_id": path_id,
        "embedding_only_id": embedding_only_id,
        "path_index": path_index,
        "embedding_only_index": embedding_index,
        "path_score": path_item.get("score"),
        "embedding_only_score": embedding_item.get("score"),
    }


def test_fallback_status_modes(
    repo: AuthRepository,
    hybrid: HybridRecommendationService,
    suffix: str,
    report: Dict[str, Any],
) -> None:
    cases = [
        (st.EMBEDDING_QUEUED, "fallback_until_embedding_ready", True),
        (st.EMBEDDING_STALE, "fallback_until_embedding_recomputed", True),
        (st.EMBEDDING_FAILED, "fallback_until_embedding_ready", True),
    ]
    results = {}
    for status, expected_mode, expected_cold in cases:
        project_id = f"phase6_prj_{status}_{suffix}"
        insert_entity(
            repo,
            "project",
            {
                "project_id": project_id,
                "title": f"Fallback {status}",
                **st.verified_state(),
                "embedding": embedding_doc(unit_vector(1.0), status=status),
                "embedding_status": status,
            },
        )
        ctx = hybrid.source_recommendation_context("project", project_id)
        assert_true(ctx["recommendation_mode"] == expected_mode, ctx)
        assert_true(ctx["cold_start"] is expected_cold, ctx)
        assert_true(bool(ctx.get("recommendation_message")), ctx)
        if status == st.EMBEDDING_FAILED:
            assert_true("that bai" in str(ctx.get("recommendation_message") or "").lower(), ctx)
        results[status] = {
            "mode": ctx["recommendation_mode"],
            "message": ctx.get("recommendation_message"),
        }
    report["fallback_status_modes"] = results


def test_pgpr_embedding_dedupe(
    repo: AuthRepository,
    embedding_repo: EmbeddingRepository,
    hybrid: HybridRecommendationService,
    rs: RecommendationService,
    suffix: str,
    report: Dict[str, Any],
) -> None:
    source_id = f"phase6_prj_dedupe_{suffix}"
    dup_id = f"phase6_exp_dedupe_{suffix}"
    src_emb = embedding_doc(unit_vector(1.0, 0.0), source_hash=f"dedupe_src_{suffix}")
    dup_emb = embedding_doc(unit_vector(0.98, 0.02), source_hash=f"dedupe_tgt_{suffix}")

    insert_entity(
        repo,
        "project",
        {
            "project_id": source_id,
            "title": "Dedupe Project",
            **st.verified_state(),
            "embedding": src_emb,
            "embedding_status": st.EMBEDDING_READY,
        },
    )
    embedding_repo.upsert_embedding_record("project", source_id, src_emb)
    insert_entity(
        repo,
        "expert",
        {
            "expert_id": dup_id,
            "name": "Dedupe Expert",
            **st.verified_state(),
            "embedding": dup_emb,
            "embedding_status": st.EMBEDDING_READY,
        },
    )
    embedding_repo.upsert_embedding_record("expert", dup_id, dup_emb)

    src_ctx = hybrid.source_recommendation_context("project", source_id)
    pgpr_pool = [
        {
            "id": dup_id,
            "name": "Dedupe Expert",
            "score": 0.82,
            "reasoning_paths": [{"source": "pgpr", "score": 0.82, "relations": ["PARTICIPATES_IN"]}],
            "scoring_method": "pgpr_policy",
        }
    ]
    merged, _ = asyncio.run(
        run_hybrid(hybrid, pgpr_pool, source_type="project", source_id=source_id, target_type="expert", src_ctx=src_ctx)
    )
    dup_rows = [x for x in merged if x["id"] == dup_id]
    assert_true(len(dup_rows) == 1, f"expected 1 deduped row, got {len(dup_rows)}: {merged}")
    row = dup_rows[0]
    assert_true(row.get("evidence_level") == "path_supported", row)
    assert_true(float(row.get("embedding_similarity", 0) or 0) > 0.5, row)
    assert_true("pgpr" in (row.get("candidate_sources") or []), row)
    assert_true("embedding" in (row.get("candidate_sources") or []), row)
    breakdown = row.get("hybrid_score_breakdown") or {}
    assert_true(float(breakdown.get("embedding", 0) or 0) > 0, breakdown)

    final = finalize_pipeline(rs, merged, source_id=source_id, source_label="Project", target_label="Expert", src_ctx=src_ctx)
    dup_final = [x for x in final if x["id"] == dup_id]
    assert_true(len(dup_final) == 1, dup_final)
    report["pgpr_embedding_dedupe"] = {
        "count": len(dup_final),
        "evidence_level": dup_final[0].get("evidence_level"),
        "embedding_similarity": dup_final[0].get("embedding_similarity"),
        "candidate_sources": dup_final[0].get("candidate_sources"),
        "score_equals_final": dup_final[0]["score"] == dup_final[0]["final_score"],
    }


def test_xai_wording(rs: RecommendationService, report: Dict[str, Any]) -> None:
    cases = [
        (
            "embedding_only",
            {"evidence_level": "embedding_only", "cold_start": True, "scoring_method": "hybrid_embedding"},
            ["embedding", "path"],
        ),
        (
            "fallback_only",
            {
                "evidence_level": "fallback_only",
                "cold_start": True,
                "scoring_method": "cypher_fallback",
                "recommendation_mode": "fallback_until_embedding_ready",
            },
            ["fallback", "cold"],
        ),
        (
            "path_supported",
            {"evidence_level": "path_supported", "scoring_method": "pgpr_policy", "reasoning_paths": [{"source": "pgpr"}]},
            [],
        ),
    ]
    xai_results = {}
    for name, rec, must_contain_any in cases:
        text = rs._append_hybrid_xai_notes("Goi y cho muc tieu.", rec, rec)
        if name == "embedding_only":
            assert_true(
                any(token in text.lower() for token in ["embedding", "độ gần", "do gan", "path"]),
                text,
            )
        if name == "fallback_only":
            assert_true(
                any(token in text.lower() for token in ["fallback", "cold-start", "cold start"]),
                text,
            )
        explainer_out = rs._explain_rule(
            {**rec, "name": "Target", "score": 0.4},
            "expert",
            {"source_type": "Project", "source_id": "prj_x"},
            "vi",
        )
        nl = str(explainer_out.get("natural_language") or "")
        xai_results[name] = {"append_notes": text[:200], "explain_snippet": nl[:200]}
    report["xai_wording"] = xai_results


def main() -> int:
    suffix = str(int(time.time() * 1000))
    repo = AuthRepository()
    embedding_repo = EmbeddingRepository(repo)
    hybrid = HybridRecommendationService(repo)
    rs = RecommendationService(recommender=None)
    report: Dict[str, Any] = {
        "status": "passed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "suffix": suffix,
        "tests": {},
    }

    try:
        test_hybrid_ready_new_source(repo, embedding_repo, hybrid, rs, suffix, report)
        test_embedding_only_caps(hybrid, rs, report)
        test_pgpr_anchor_scoring_priority(repo, embedding_repo, hybrid, suffix, report)
        test_fallback_status_modes(repo, hybrid, suffix, report)
        test_pgpr_embedding_dedupe(repo, embedding_repo, hybrid, rs, suffix, report)
        test_xai_wording(rs, report)
    finally:
        cleanup_fixtures(repo, embedding_repo)

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"PASS written {OUT}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        OUT.write_text(
            json.dumps(
                {"status": "failed", "error": str(exc), "created_at": datetime.now(timezone.utc).isoformat()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"FAIL {exc}")
        sys.exit(1)
