"""Check whether PGPR re-export/retrain is needed after KG merge/coauthor changes."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repositories.pgpr_graph_repo import PGPRGraphRepository

DATA = ROOT / "pgpr" / "pgpr_data"
TARGETS = ("B60btb4AAAAJ", "uzuvTBQAAAAJ")


def main() -> int:
    vocab = json.loads((DATA / "vocab.json").read_text(encoding="utf-8"))
    e2i = vocab.get("entity2id", {})
    r2i = vocab.get("relation2id", {})
    rel_co = r2i.get("CO_AUTHORED")

    print("=== Vocab ===")
    for eid in TARGETS:
        key = f"Expert::{eid}"
        print(f"  {eid}: in_vocab={key in e2i} entity_id={e2i.get(key)}")
    print(f"  CO_AUTHORED relation_id={rel_co}")

    triple_stats = {"co_authored_total": 0, "touching_targets": 0, "tram_tien_pair": 0}
    ids = {e2i.get(f"Expert::{e}") for e in TARGETS}
    ids.discard(None)
    tram_id = e2i.get("Expert::B60btb4AAAAJ")
    tien_id = e2i.get("Expert::uzuvTBQAAAAJ")
    triples_path = DATA / "triples.txt"
    if triples_path.exists():
        with triples_path.open(encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) != 3:
                    continue
                h, r, t = (int(parts[0]), int(parts[1]), int(parts[2]))
                if r != rel_co:
                    continue
                triple_stats["co_authored_total"] += 1
                if h in ids or t in ids:
                    triple_stats["touching_targets"] += 1
                if tram_id is not None and tien_id is not None:
                    if {h, t} == {tram_id, tien_id}:
                        triple_stats["tram_tien_pair"] += 1
    print("=== triples.txt (PGPR offline KG) ===")
    for k, v in triple_stats.items():
        print(f"  {k}: {v}")

    policies = sorted(DATA.glob("policy*.pt"))
    print("=== Policy files ===")
    for p in policies:
        print(f"  {p.name} ({p.stat().st_size // 1024} KB)")

    graph = PGPRGraphRepository()
    try:
        print("=== Neo4j (live) ===")
        for eid in TARGETS:
            rows = graph.run_read(
                """
                MATCH (e:Expert {expert_id: $eid})-[r:CO_AUTHORED]-(o:Expert)
                RETURN count(o) AS neighbors, sum(coalesce(r.paper_count, 1)) AS papers
                """,
                eid=eid,
            )
            print(f"  {eid}: {rows[0] if rows else {}}")
        link = graph.run_read(
            """
            MATCH (a:Expert {expert_id: $tram})-[r:CO_AUTHORED]-(b:Expert {expert_id: $tien})
            RETURN coalesce(r.paper_count, 1) AS shared_papers
            """,
            tram="B60btb4AAAAJ",
            tien="uzuvTBQAAAAJ",
        )
        print(f"  Tram <-> Tien-Dung CO_AUTHORED: {link[0] if link else 'MISSING'}")
    finally:
        graph.close()

    print("\n=== Recommendation ===")
    if triple_stats["tram_tien_pair"] == 0:
        print("  Neo4j co-author path Tram<->Tien chua co trong triples.txt PGPR.")
    if not link or not link[0]:
        print("  Neo4j van chua co CO_AUTHORED giua canonical Tram va Tien-Dung.")
        print("  -> Uu tien hoan thanh mongo_to_neo4j --coauthors-only truoc.")
    print("  Retrain policy: KHONG BAT BUOC cho gợi ý expert (Cypher fallback + co_authored candidate da co).")
    print("  Re-export step 1: NEN sau khi co-author sync xong, neu muon PGPR policy di duong CO_AUTHORED.")
    print("  Retrain Expert_Expert step 2: TUY CHON, chi khi can reasoning path PGPR qua co-author.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
