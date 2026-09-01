"""Quick verify canonical experts after merge/sync."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repositories.auth_repo import AuthRepository
from repositories.pgpr_graph_repo import PGPRGraphRepository

TARGETS = ("B60btb4AAAAJ", "uzuvTBQAAAAJ", "OA_Tram_Truong-Huu", "OA_Tien-Dung_Cao")
OUT = Path(__file__).resolve().parent / "verify_merge_targets.json"


def main() -> int:
    repo = AuthRepository()
    graph = PGPRGraphRepository()
    report = {}
    try:
        for eid in TARGETS:
            doc = repo.find_entity_by_id("expert", eid) or {}
            develops = graph.run_read(
                "MATCH (e:Expert {expert_id: $eid})-[:DEVELOPS]->(p) RETURN count(p) AS c",
                eid=eid,
            )
            coauth = graph.run_read(
                """
                MATCH (e:Expert {expert_id: $eid})-[r:CO_AUTHORED]-(o:Expert)
                RETURN o.expert_id AS other, coalesce(r.paper_count,1) AS papers
                ORDER BY papers DESC LIMIT 10
                """,
                eid=eid,
            )
            candidates = (
                graph.find_candidate_experts_for_expert(eid, limit=10)
                if eid in ("B60btb4AAAAJ", "uzuvTBQAAAAJ")
                else []
            )
            report[eid] = {
                "mongo": {
                    "kg_sync_status": doc.get("kg_sync_status"),
                    "merged_into": doc.get("merged_into"),
                    "active": doc.get("active"),
                },
                "develops": develops[0] if develops else {},
                "co_authored": coauth,
                "candidates": [
                    {
                        "expert_id": c.get("expert_id"),
                        "sources": c.get("candidate_sources"),
                        "shared_papers": c.get("shared_papers"),
                    }
                    for c in candidates
                ],
            }
    finally:
        graph.close()
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stdout.buffer.write(f"written {OUT}\n".encode("utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
