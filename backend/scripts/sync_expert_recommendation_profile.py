"""Sync expert recommendation profiles: interests -> topics, paper keywords -> Neo4j topics.

Dry-run:
    python scripts/sync_expert_recommendation_profile.py

Apply Mongo + Neo4j updates:
    python scripts/sync_expert_recommendation_profile.py --apply

Requeue embeddings for updated experts:
    python scripts/sync_expert_recommendation_profile.py --apply --requeue-embeddings --limit 50
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parents[1]
ADD_DATA = ROOT.parent / "add_data"
for path in (ROOT, ADD_DATA):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from repositories.auth_repo import AuthRepository  # noqa: E402
from repositories.pgpr_graph_repo import PGPRGraphRepository  # noqa: E402
from services import provisional_status as st  # noqa: E402
from services.outbox_publisher_service import OutboxPublisherService  # noqa: E402

OUT = Path(__file__).resolve().parent / "sync_expert_recommendation_profile_report.json"


def _topic_names_from_interests(rc: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    seen: Set[str] = set()
    for item in rc.get("research_interests") or []:
        name = str(item.get("name") if isinstance(item, dict) else item).strip()
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return names


def _merge_topics(existing: List[Any], interest_names: List[str]) -> List[Dict[str, str]]:
    topics = [t for t in (existing or []) if isinstance(t, dict)]
    known = {str(t.get("name") or "").strip().lower() for t in topics if str(t.get("name") or "").strip()}
    for name in interest_names:
        if name.lower() not in known:
            topics.append({"name": name})
            known.add(name.lower())
    return topics


def _normalize_keywords(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        items = raw
    else:
        items = re.split(r"[;,]", str(raw))
    out: List[str] = []
    seen: Set[str] = set()
    for item in items:
        name = str(item).strip()
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            out.append(name)
    return out


def _sync_mongo_profiles(repo: AuthRepository, *, apply: bool) -> Dict[str, Any]:
    updated = 0
    rows: List[Dict[str, Any]] = []
    for doc in repo.experts.find({}, {"expert_id": 1, "research_capacity": 1, "kg_sync_status": 1}):
        expert_id = str(doc.get("expert_id") or "")
        rc = dict(doc.get("research_capacity") or {})
        interests = _topic_names_from_interests(rc)
        if not interests:
            continue
        merged_topics = _merge_topics(rc.get("research_topics") or [], interests)
        if merged_topics == (rc.get("research_topics") or []):
            continue
        row = {"expert_id": expert_id, "added_topics": [t["name"] for t in merged_topics if t.get("name")]}
        rows.append(row)
        if apply:
            repo.db.experts.update_one(
                {"expert_id": expert_id},
                {
                    "$set": {
                        "research_capacity.research_topics": merged_topics,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            updated += 1
    return {"mongo_experts_updated": updated, "samples": rows[:20]}


def _sync_interest_topics_neo4j(repo: AuthRepository, graph: PGPRGraphRepository, *, apply: bool) -> Dict[str, Any]:
    topic_edges = 0
    experts_touched: Set[str] = set()
    for doc in repo.experts.find({}, {"expert_id": 1, "research_capacity": 1}):
        expert_id = str(doc.get("expert_id") or "")
        rc = doc.get("research_capacity") or {}
        names = _topic_names_from_interests(rc)
        for topic_name in names:
            experts_touched.add(expert_id)
            if apply:
                graph.run_write(
                    "MERGE (t:ResearchTopic {name: $name}) SET t.updated_at = datetime()",
                    name=topic_name,
                )
                graph.run_write(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (t:ResearchTopic {name: $name})
                    MERGE (e)-[:HAS_EXPERIENCE_IN]->(t)
                    """,
                    expert_id=expert_id,
                    name=topic_name,
                )
            topic_edges += 1
    return {"interest_topic_edges": topic_edges, "experts_touched": len(experts_touched)}


def _sync_paper_keyword_topics(repo: AuthRepository, graph: PGPRGraphRepository, *, apply: bool) -> Dict[str, Any]:
    topic_edges = 0
    experts_touched: Set[str] = set()
    products = repo.db.products.find(
        {
            "$or": [
                {"type": "scientific_paper"},
                {"metadata.source_type": "Scientific Document / Paper"},
            ]
        },
        {"product_id": 1, "developer_ids": 1, "developed_by": 1, "metadata.keywords": 1},
    )
    for product in products:
        keywords = _normalize_keywords((product.get("metadata") or {}).get("keywords"))
        if not keywords:
            continue
        expert_ids = list(dict.fromkeys(product.get("developer_ids") or product.get("developed_by") or []))
        if not expert_ids:
            continue
        for expert_id in expert_ids:
            for topic_name in keywords:
                experts_touched.add(expert_id)
                if apply:
                    graph.run_write(
                        "MERGE (t:ResearchTopic {name: $name}) SET t.updated_at = datetime()",
                        name=topic_name,
                    )
                    graph.run_write(
                        """
                        MATCH (e:Expert {expert_id: $expert_id})
                        MATCH (t:ResearchTopic {name: $name})
                        MERGE (e)-[:HAS_EXPERIENCE_IN]->(t)
                        """,
                        expert_id=expert_id,
                        name=topic_name,
                    )
                topic_edges += 1
    return {
        "paper_keyword_topic_edges": topic_edges,
        "experts_touched": len(experts_touched),
    }


def _requeue_embeddings(repo: AuthRepository, expert_ids: List[str], *, limit: int) -> Dict[str, Any]:
    publisher = OutboxPublisherService(repo)
    queued = 0
    for expert_id in expert_ids[:limit]:
        doc = repo.find_entity_by_id("expert", expert_id)
        if not doc:
            continue
        kg_status = str(doc.get("kg_sync_status") or st.KG_NOT_SYNCED)
        if kg_status not in {st.KG_SYNCED_UNVERIFIED, st.KG_SYNCED_VERIFIED}:
            continue
        result = publisher.enqueue_embedding_event(
            "expert",
            expert_id,
            event_type="kg.embedding.recompute",
            source="scripts.sync_expert_recommendation_profile",
            try_publish_now=True,
        )
        if result.ok:
            queued += 1
    return {"embedding_jobs_queued": queued}


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync expert recommendation profiles.")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--requeue-embeddings", action="store_true")
    parser.add_argument("--skip-paper-keywords", action="store_true")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", default=str(OUT))
    args = parser.parse_args()

    repo = AuthRepository()
    graph = PGPRGraphRepository()
    report: Dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "apply": bool(args.apply),
    }
    try:
        report["mongo"] = _sync_mongo_profiles(repo, apply=bool(args.apply))
        report["neo4j_interests"] = _sync_interest_topics_neo4j(repo, graph, apply=bool(args.apply))
        if not args.skip_paper_keywords:
            report["neo4j"] = _sync_paper_keyword_topics(repo, graph, apply=bool(args.apply))
        if args.requeue_embeddings and args.apply:
            expert_ids = [
                str(doc.get("expert_id"))
                for doc in repo.experts.find(
                    {
                        "$or": [
                            {"research_capacity.research_interests.0": {"$exists": True}},
                            {"expert_alias_ids.0": {"$exists": True}},
                        ]
                    },
                    {"expert_id": 1},
                )
            ]
            report["embeddings"] = _requeue_embeddings(repo, expert_ids, limit=args.limit)
    finally:
        graph.close()

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    out_path = Path(args.output)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    sys.stdout.buffer.write(
        f"apply={args.apply} report={out_path}\n".encode("utf-8", errors="replace")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
