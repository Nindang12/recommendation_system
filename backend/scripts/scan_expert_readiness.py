"""Scan which experts are ready to act as recommendation sources."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from pgpr.pgpr_recommendation import PGPRRecommender
from repositories.auth_repo import AuthRepository
from services.hybrid_recommendation_service import HybridRecommendationService

OUT = Path(__file__).resolve().parent / "expert_readiness_report.json"


def has_topics_skills(doc: dict) -> bool:
    paths = [
        doc.get("skills"),
        doc.get("technology"),
        doc.get("research_interests"),
        doc.get("research_topics"),
        (doc.get("research_capacity") or {}).get("research_topics"),
        (doc.get("research_capacity") or {}).get("technology"),
    ]
    for value in paths:
        if isinstance(value, list) and value:
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


def kg_has_direct_reco_links(kg, expert_id: str) -> bool:
    key = f"Expert::{expert_id}"
    if key not in kg.entity2id:
        return False
    eid = kg.entity2id[key]
    for _, target in kg.adj_list.get(eid, []):
        target_key = kg.id2entity[target]
        if target_key.startswith(("Project::", "ResearchTopic::", "ResearchDirection::")):
            return True
    return False


def neo4j_signal_map(graph) -> dict[str, dict]:
    rows = graph.run_read(
        """
        MATCH (e:Expert)
        OPTIONAL MATCH (e)-[:HAS_EXPERIENCE_IN]->(t:ResearchTopic)
        WITH e, count(t) AS topics
        OPTIONAL MATCH (e)-[:RESEARCHES]->(d:ResearchDirection)
        WITH e, topics, count(d) AS directions
        OPTIONAL MATCH (e)-[:PARTICIPATES_IN]->(p:Project)
        RETURN e.expert_id AS expert_id,
               topics AS topics,
               directions AS directions,
               count(p) AS projects
        """,
    )
    out: dict[str, dict] = {}
    for row in rows:
        expert_id = str(row.get("expert_id") or "")
        if not expert_id:
            continue
        out[expert_id] = row
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    repo = AuthRepository()
    hybrid = HybridRecommendationService(auth_repo=repo)
    rec = PGPRRecommender(enable_cache=False)
    kg = rec.kg
    graph = rec.graph_repo
    neo_map = neo4j_signal_map(graph)

    total = repo.experts.count_documents({})
    cats: Counter[str] = Counter()
    examples: dict[str, list] = defaultdict(list)
    ready_public: list[dict] = []
    ready_personal: list[dict] = []
    ready_pgpr: list[dict] = []
    ready_topic_only: list[dict] = []
    not_ready: list[dict] = []

    for doc in repo.experts.find(
        {},
        {
            "expert_id": 1,
            "basic_info.name": 1,
            "embedding": 1,
            "embedding_status": 1,
            "entity_verification_status": 1,
            "participation_scope": 1,
            "research_capacity.research_topics": 1,
            "skills": 1,
        },
    ):
        expert_id = str(doc.get("expert_id") or "")
        if not expert_id:
            continue
        name = (doc.get("basic_info") or {}).get("name") or expert_id
        ctx = hybrid.source_recommendation_context("expert", expert_id)
        readiness = ctx.get("recommendation_readiness")
        in_vocab = f"Expert::{expert_id}" in kg.entity2id
        topic_skill = has_topics_skills(doc)
        kg_links = kg_has_direct_reco_links(kg, expert_id)
        neo_stats = neo_map.get(expert_id) or {}
        neo_ok = (
            neo_stats.get("topics", 0) > 0
            or neo_stats.get("directions", 0) > 0
            or neo_stats.get("projects", 0) > 0
        )

        if readiness == "public_hybrid_ready":
            tier = "public_hybrid_ready"
            ready_public.append({"expert_id": expert_id, "name": name})
        elif readiness == "personal_hybrid_ready":
            tier = "personal_hybrid_ready"
            ready_personal.append({"expert_id": expert_id, "name": name})
        elif neo_ok or kg_links:
            tier = "pgpr_cypher_only"
            ready_pgpr.append({"expert_id": expert_id, "name": name, "neo": neo_stats})
        elif topic_skill:
            tier = "topic_skill_fallback_only"
            ready_topic_only.append({"expert_id": expert_id, "name": name})
        else:
            tier = "not_ready"
            not_ready.append({"expert_id": expert_id, "name": name, "in_vocab": in_vocab})

        cats[tier] += 1
        if len(examples[tier]) < 8:
            examples[tier].append(
                {
                    "expert_id": expert_id,
                    "name": name,
                    "mode": ctx.get("recommendation_mode"),
                    "in_vocab": in_vocab,
                    "neo": neo_stats if neo_ok else None,
                }
            )

    rec.close()

    report = {
        "total_experts": total,
        "summary": dict(cats),
        "can_recommend_as_source": {
            "public_hybrid_ready": len(ready_public),
            "personal_hybrid_ready": len(ready_personal),
            "pgpr_cypher_only": len(ready_pgpr),
            "topic_skill_fallback_only": len(ready_topic_only),
            "not_ready": len(not_ready),
        },
        "examples": examples,
        "public_hybrid_ready_list": ready_public,
        "personal_hybrid_ready_list": ready_personal,
        "pgpr_cypher_only_list": ready_pgpr,
        "topic_skill_fallback_only_list": ready_topic_only,
        "not_ready_sample": not_ready[:30],
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": report["summary"], "out": str(OUT)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
