"""Rewire CO_AUTHORED edges from disabled merged experts to canonical IDs."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repositories.auth_repo import AuthRepository
from repositories.pgpr_graph_repo import PGPRGraphRepository


def main() -> int:
    repo = AuthRepository()
    graph = PGPRGraphRepository()
    moved = 0
    try:
        for doc in repo.experts.find(
            {"merged_into": {"$exists": True, "$ne": None}},
            {"expert_id": 1, "merged_into": 1},
        ):
            source = str(doc.get("expert_id") or "")
            canonical = str(doc.get("merged_into") or "")
            if not source or not canonical or source == canonical:
                continue
            rows = graph.run_write(
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
                source=source,
                canonical=canonical,
            )
            moved += int((rows[0] if rows else {}).get("c") or 0)
    finally:
        graph.close()
    sys.stdout.buffer.write(f"rewired_coauthored_edges={moved}\n".encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
