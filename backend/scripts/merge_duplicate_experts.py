"""Merge duplicate Expert nodes (by normalized name / ORCID) into a canonical expert_id.

Dry-run:
    python scripts/merge_duplicate_experts.py

Apply merges + redirect Neo4j edges:
    python scripts/merge_duplicate_experts.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parents[1]
ADD_DATA = ROOT.parent / "add_data"
for path in (ROOT, ADD_DATA):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from expert_identity_utils import (  # noqa: E402
    build_expert_name_index,
    build_orcid_index,
    choose_canonical_expert_id,
    expert_display_name,
    expert_orcid,
    is_oa_prefixed,
    normalize_author_name,
)
from repositories.auth_repo import AuthRepository  # noqa: E402
from repositories.pgpr_graph_repo import PGPRGraphRepository  # noqa: E402
from services import provisional_status as st  # noqa: E402

OUT = Path(__file__).resolve().parent / "merge_duplicate_experts_report.json"


def _neo4j_develops_counts(graph: PGPRGraphRepository, expert_ids: List[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for eid in expert_ids:
        rows = graph.run_read(
            """
            MATCH (e:Expert {expert_id: $eid})-[:DEVELOPS]->(:Product)
            RETURN count(*) AS c
            """,
            eid=eid,
        )
        out[eid] = int((rows[0] if rows else {}).get("c") or 0)
    return out


def _find_duplicate_groups(experts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_name: Dict[str, List[str]] = defaultdict(list)
    docs: Dict[str, Dict[str, Any]] = {}
    for doc in experts:
        eid = str(doc.get("expert_id") or "")
        if not eid:
            continue
        docs[eid] = doc
        key = normalize_author_name(expert_display_name(doc))
        if key:
            by_name[key].append(eid)

    by_orcid: Dict[str, List[str]] = defaultdict(list)
    for doc in experts:
        eid = str(doc.get("expert_id") or "")
        orcid = expert_orcid(doc)
        if eid and orcid:
            by_orcid[orcid].append(eid)

    groups: List[Dict[str, Any]] = []
    seen_sets: Set[frozenset] = set()
    for reason, bucket in (("name", by_name), ("orcid", by_orcid)):
        for key, ids in bucket.items():
            unique_ids = sorted(set(ids))
            if len(unique_ids) < 2:
                continue
            frozen = frozenset(unique_ids)
            if frozen in seen_sets:
                continue
            seen_sets.add(frozen)
            groups.append(
                {
                    "reason": reason,
                    "key": key,
                    "expert_ids": unique_ids,
                    "names": [expert_display_name(docs[i]) for i in unique_ids],
                }
            )
    return groups


def _merge_profile_fields(target: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(target)
    aliases = set(out.get("expert_alias_ids") or [])
    source_id = str(source.get("expert_id") or "")
    if source_id:
        aliases.add(source_id)
    out["expert_alias_ids"] = sorted(aliases)

    rc_t = out.setdefault("research_capacity", {})
    rc_s = source.get("research_capacity") or {}
    interests = list(rc_t.get("research_interests") or [])
    for item in rc_s.get("research_interests") or []:
        if item and item not in interests:
            interests.append(item)
    rc_t["research_interests"] = interests

    topics = list(rc_t.get("research_topics") or [])
    for item in interests:
        topic_name = str(item).strip()
        if not topic_name:
            continue
        if not any(
            isinstance(t, dict) and str(t.get("name") or "").strip().lower() == topic_name.lower()
            for t in topics
        ):
            topics.append({"name": topic_name})
    rc_t["research_topics"] = topics
    out["research_capacity"] = rc_t
    return out


def _redirect_neo4j_edges(graph: PGPRGraphRepository, source_id: str, canonical_id: str) -> Dict[str, int]:
    stats = {"develops": 0, "co_authored": 0}
    rows = graph.run_write(
        """
        MATCH (src:Expert {expert_id: $source})-[r:DEVELOPS]->(p:Product)
        MATCH (tgt:Expert {expert_id: $canonical})
        MERGE (tgt)-[rt:DEVELOPS]->(p)
        SET rt.source = coalesce(rt.source, r.source, 'merge_redirect')
        WITH r
        DELETE r
        RETURN count(*) AS c
        """,
        source=source_id,
        canonical=canonical_id,
    )
    stats["develops"] = int((rows[0] if rows else {}).get("c") or 0)

    rows2 = graph.run_write(
        """
        MATCH (src:Expert {expert_id: $source})-[r:CO_AUTHORED]-(other:Expert)
        WHERE other.expert_id <> $canonical
        MATCH (tgt:Expert {expert_id: $canonical})
        MERGE (tgt)-[rt:CO_AUTHORED]-(other)
        SET rt.paper_count = coalesce(rt.paper_count, r.paper_count, 1),
            rt.updated_at = datetime()
        WITH r
        DELETE r
        RETURN count(*) AS c
        """,
        source=source_id,
        canonical=canonical_id,
    )
    stats["co_authored"] = int((rows2[0] if rows2 else {}).get("c") or 0)

    graph.disable_entity("expert", source_id, merged_into=canonical_id)
    return stats


def _update_product_developer_ids(repo: AuthRepository, source_id: str, canonical_id: str) -> int:
    updated = 0
    cursor = repo.db.products.find(
        {
            "$or": [
                {"developer_ids": source_id},
                {"developed_by": source_id},
            ]
        },
        {"product_id": 1, "developer_ids": 1, "developed_by": 1},
    )
    for doc in cursor:
        dev = [canonical_id if x == source_id else x for x in (doc.get("developer_ids") or [])]
        dev_by = [canonical_id if x == source_id else x for x in (doc.get("developed_by") or [])]
        dev = list(dict.fromkeys([x for x in dev if x]))
        dev_by = list(dict.fromkeys([x for x in dev_by if x]))
        repo.db.products.update_one(
            {"_id": doc["_id"]},
            {"$set": {"developer_ids": dev, "developed_by": dev_by, "updated_at": datetime.now(timezone.utc)}},
        )
        updated += 1
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge duplicate experts into canonical IDs.")
    parser.add_argument("--apply", action="store_true", help="Apply merges (default: dry-run).")
    parser.add_argument("--output", default=str(OUT))
    args = parser.parse_args()

    repo = AuthRepository()
    graph = PGPRGraphRepository()
    experts = list(repo.experts.find({}))
    vocab_keys = set()
    try:
        from pgpr.pgpr_recommendation import PGPRRecommender

        rec = PGPRRecommender(enable_cache=False)
        vocab_keys = set(rec.kg.entity2id.keys())
        rec.close()
    except Exception:
        vocab_keys = set()

    groups = _find_duplicate_groups(experts)
    report: Dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "apply": bool(args.apply),
        "duplicate_groups": len(groups),
        "merges": [],
    }

    try:
        for group in groups:
            ids = group["expert_ids"]
            develops = _neo4j_develops_counts(graph, ids)
            in_vocab = {eid for eid in ids if f"Expert::{eid}" in vocab_keys}
            canonical = choose_canonical_expert_id(
                ids,
                develops_counts=develops,
                in_vocab=in_vocab,
            )
            sources = [eid for eid in ids if eid != canonical]
            row: Dict[str, Any] = {
                **group,
                "canonical_id": canonical,
                "source_ids": sources,
                "develops_counts": develops,
                "in_vocab": sorted(in_vocab),
            }
            if args.apply:
                target_doc = repo.find_entity_by_id("expert", canonical) or {}
                applied = []
                for source_id in sources:
                    source_doc = repo.find_entity_by_id("expert", source_id) or {}
                    merged_doc = _merge_profile_fields(target_doc, source_doc)
                    repo.update_entity_status(
                        "expert",
                        canonical,
                        {
                            "research_capacity": merged_doc.get("research_capacity"),
                            "expert_alias_ids": merged_doc.get("expert_alias_ids"),
                        },
                    )
                    target_doc = repo.find_entity_by_id("expert", canonical) or merged_doc
                    products_updated = _update_product_developer_ids(repo, source_id, canonical)
                    edge_stats = _redirect_neo4j_edges(graph, source_id, canonical)
                    repo.update_entity_status(
                        "expert",
                        source_id,
                        {
                            "kg_sync_status": st.KG_DISABLED,
                            "visibility": st.VISIBILITY_DISABLED,
                            "participation_scope": st.SCOPE_DISABLED,
                            "active": False,
                            "trust_weight": 0,
                            "matched_existing_entity_id": canonical,
                            "merged_into": canonical,
                        },
                    )
                    applied.append(
                        {
                            "source_id": source_id,
                            "products_updated": products_updated,
                            "neo4j": edge_stats,
                        }
                    )
                row["applied"] = applied
            report["merges"].append(row)
    finally:
        graph.close()

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    out_path = Path(args.output)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    sys.stdout.buffer.write(
        (
            f"apply={args.apply} duplicate_groups={report['duplicate_groups']} "
            f"written={out_path}\n"
        ).encode("utf-8", errors="replace")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
