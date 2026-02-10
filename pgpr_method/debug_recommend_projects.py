"""
Script debug: gom candidate projects từ nhiều nguồn quan hệ và xếp hạng theo độ phù hợp.

Candidate sources:
- field: Expert HAS_EXPERTISE_IN ResearchField ~ Project BELONGS_TO (mở rộng hierarchy SUB_FIELD_OF)
- funder: Expert PARTICIPATES_IN Project <-FUNDS- Funder -FUNDS-> Other Projects
- skill: Expert HAS_SKILL MethodTechnique, match với Project.required_skills (name/tech_id)
- industry: Expert HAS_APPLICATION_EXPERIENCE_IN Industry, match với Enterprise partners của Project
- collab: Expert COLLABORATES_WITH Expert2 PARTICIPATES_IN Project

Chạy:
  python debug_recommend_projects.py --expert_id EXP_0003 --limit 20 --max_path_length 5
"""

from pgpr_recommendation import PGPRRecommender
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv
import argparse
from collections import defaultdict

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def check_expert_exists(expert_id: str):
    """Kiểm tra expert có tồn tại không"""
    with driver.session() as session:
        result = session.run(
            "MATCH (e:Expert {expert_id: $expert_id}) RETURN e",
            expert_id=expert_id
        )
        records = list(result)
        if records:
            expert = dict(records[0]['e'])
            print(f"[OK] Expert {expert_id} tồn tại:")
            print(f"   Name: {expert.get('name', 'N/A')}")
            print(f"   Location: {expert.get('location', 'N/A')}")
            return True
        else:
            print(f"[FAIL] Expert {expert_id} KHÔNG tồn tại trong database")
            return False

def check_expert_expertise(expert_id: str):
    """Kiểm tra chuyên môn của expert"""
    with driver.session() as session:
        result = session.run("""
            MATCH (e:Expert {expert_id: $expert_id})-[:HAS_EXPERTISE_IN]->(rf:ResearchField)
            RETURN rf.field_id as field_id, rf.label as label
        """, expert_id=expert_id)
        
        fields = list(result)
        if fields:
            print(f"\nChuyên môn của {expert_id}:")
            for field in fields:
                print(f"   - {field['field_id']}: {field['label']}")
            return [f['field_id'] for f in fields]
        else:
            print(f"\n[WARN] Expert {expert_id} KHÔNG có chuyên môn nào")
            return []

def check_projects_count():
    """Kiểm tra số lượng projects"""
    with driver.session() as session:
        # Tổng số projects
        total = session.run("MATCH (p:Project) RETURN count(p) as count").single()['count']
        print(f"\nTổng số projects trong database: {total}")
        
        # Projects theo status
        statuses = session.run("""
            MATCH (p:Project)
            RETURN p.status as status, count(p) as count
            ORDER BY count DESC
        """)
        
        print(f"\nProjects theo status:")
        for record in statuses:
            print(f"   - {record['status']}: {record['count']}")
        
        return total

def _merge_candidates(base: dict, incoming: dict, source: str) -> dict:
    """Merge two candidate dicts by project_id and accumulate candidate_sources + feature counters."""
    out = base.copy()
    srcs = set(out.get("candidate_sources") or [])
    srcs.add(source)
    out["candidate_sources"] = sorted(srcs)

    # Merge simple numeric features if present
    for k in ("common_funders", "matched_skills", "matched_industries", "collab_links"):
        if k in incoming and incoming[k] is not None:
            out[k] = max(out.get(k, 0) or 0, incoming[k] or 0)
    return out


def get_candidates_by_field(session, expert_id: str, status_filter: list) -> list[dict]:
    """Field/hierarchy candidate projects (undirected SUB_FIELD_OF to include siblings)."""
    result = session.run(
        """
        MATCH (e:Expert {expert_id: $expert_id})-[:HAS_EXPERTISE_IN]->(rf:ResearchField)
        MATCH (rf)-[:SUB_FIELD_OF*0..2]-(related_rf:ResearchField)<-[:BELONGS_TO]-(p:Project)
        WHERE p.status IN $status_filter
          AND NOT (e)-[:PARTICIPATES_IN]->(p)
        RETURN DISTINCT p.project_id as project_id,
               p.title as title,
               p.status as status,
               p.location as location,
               p.trl as trl,
               p.budget as budget
        LIMIT 200
        """,
        expert_id=expert_id,
        status_filter=status_filter,
    )
    out = [dict(r) for r in result]
    for c in out:
        c["candidate_sources"] = ["field"]
    return out


def get_candidates_by_shared_funder(session, expert_id: str, status_filter: list) -> list[dict]:
    """Candidates via shared funder with expert's participated projects."""
    result = session.run(
        """
        MATCH (e:Expert {expert_id: $expert_id})-[:PARTICIPATES_IN]->(p0:Project)<-[:FUNDS]-(f:Funder)-[:FUNDS]->(p:Project)
        WHERE p.status IN $status_filter
          AND NOT (e)-[:PARTICIPATES_IN]->(p)
        WITH p, count(DISTINCT f) as common_funders
        RETURN DISTINCT p.project_id as project_id,
               p.title as title,
               p.status as status,
               p.location as location,
               p.trl as trl,
               p.budget as budget,
               common_funders
        ORDER BY common_funders DESC
        LIMIT 200
        """,
        expert_id=expert_id,
        status_filter=status_filter,
    )
    out = [dict(r) for r in result]
    for c in out:
        c["candidate_sources"] = ["funder"]
    return out


def get_candidates_by_skill_match(session, expert_id: str, status_filter: list) -> list[dict]:
    """Candidates by matching expert skills (MethodTechnique) with project.required_skills list."""
    result = session.run(
        """
        MATCH (e:Expert {expert_id: $expert_id})-[:HAS_SKILL]->(m:MethodTechnique)
        MATCH (p:Project)
        WHERE p.status IN $status_filter
          AND NOT (e)-[:PARTICIPATES_IN]->(p)
          AND p.required_skills IS NOT NULL
          AND (m.name IN p.required_skills OR m.tech_id IN p.required_skills)
        WITH p, count(DISTINCT m) as matched_skills
        RETURN DISTINCT p.project_id as project_id,
               p.title as title,
               p.status as status,
               p.location as location,
               p.trl as trl,
               p.budget as budget,
               matched_skills
        ORDER BY matched_skills DESC
        LIMIT 200
        """,
        expert_id=expert_id,
        status_filter=status_filter,
    )
    out = [dict(r) for r in result]
    for c in out:
        c["candidate_sources"] = ["skill"]
    return out


def get_candidates_by_industry_match(session, expert_id: str, status_filter: list) -> list[dict]:
    """
    Candidates by industry application experience:
      Expert -HAS_APPLICATION_EXPERIENCE_IN-> Industry <-OPERATES_IN- Enterprise -PARTNERS_WITH-> Project
    """
    result = session.run(
        """
        MATCH (e:Expert {expert_id: $expert_id})-[:HAS_APPLICATION_EXPERIENCE_IN]->(i:Industry)
        MATCH (en:Enterprise)-[:OPERATES_IN]->(i)
        MATCH (en)-[:PARTNERS_WITH]->(p:Project)
        WHERE p.status IN $status_filter
          AND NOT (e)-[:PARTICIPATES_IN]->(p)
        WITH p, count(DISTINCT i) as matched_industries
        RETURN DISTINCT p.project_id as project_id,
               p.title as title,
               p.status as status,
               p.location as location,
               p.trl as trl,
               p.budget as budget,
               matched_industries
        ORDER BY matched_industries DESC
        LIMIT 200
        """,
        expert_id=expert_id,
        status_filter=status_filter,
    )
    out = [dict(r) for r in result]
    for c in out:
        c["candidate_sources"] = ["industry"]
    return out


def get_candidates_by_collaboration(session, expert_id: str, status_filter: list) -> list[dict]:
    """Candidates via collaboration network."""
    result = session.run(
        """
        MATCH (e:Expert {expert_id: $expert_id})-[:COLLABORATES_WITH]-(o:Expert)-[:PARTICIPATES_IN]->(p:Project)
        WHERE p.status IN $status_filter
          AND NOT (e)-[:PARTICIPATES_IN]->(p)
        WITH p, count(DISTINCT o) as collab_links
        RETURN DISTINCT p.project_id as project_id,
               p.title as title,
               p.status as status,
               p.location as location,
               p.trl as trl,
               p.budget as budget,
               collab_links
        ORDER BY collab_links DESC
        LIMIT 200
        """,
        expert_id=expert_id,
        status_filter=status_filter,
    )
    out = [dict(r) for r in result]
    for c in out:
        c["candidate_sources"] = ["collab"]
    return out


def collect_all_candidates(expert_id: str, status_filter: list) -> list[dict]:
    """Collect and merge candidates from all sources."""
    with driver.session() as session:
        sources = {
            "field": get_candidates_by_field(session, expert_id, status_filter),
            "funder": get_candidates_by_shared_funder(session, expert_id, status_filter),
            "skill": get_candidates_by_skill_match(session, expert_id, status_filter),
            "industry": get_candidates_by_industry_match(session, expert_id, status_filter),
            "collab": get_candidates_by_collaboration(session, expert_id, status_filter),
        }

        merged: dict[str, dict] = {}
        for source_name, cand_list in sources.items():
            for c in cand_list:
                pid = c["project_id"]
                if pid in merged:
                    merged[pid] = _merge_candidates(merged[pid], c, source_name)
                else:
                    merged[pid] = c

        # Print quick stats
        print("\nCandidate counts by source:")
        for source_name, cand_list in sources.items():
            print(f"  - {source_name}: {len(cand_list)}")
        print(f"  => merged unique candidates: {len(merged)}")

        return list(merged.values())


def rank_candidates(engine: PGPRRecommender, expert_id: str, candidates: list[dict], max_path_length: int) -> list[dict]:
    """
    Rank candidates by the same suitability metric used in recommender:
    score derived from reasoning paths (max/avg/diversity).
    """
    ranked = []
    for c in candidates:
        pid = c["project_id"]
        paths = engine.find_reasoning_paths(
            source_id=expert_id,
            source_type="Expert",
            target_id=pid,
            target_type="Project",
            max_length=max_path_length,
        )
        if not paths:
            # still keep but with score 0 for inspection
            ranked.append({**c, "score": 0.0, "path_diversity": 0, "top_paths": []})
            continue
        score = engine._calculate_project_score(paths, c)
        ranked.append({
            **c,
            "score": round(float(score), 3),
            "path_diversity": len(set(tuple(p["relations"]) for p in paths)),
            "top_paths": paths[:3],
        })
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked

def check_paths_exist(expert_id: str, project_id: str):
    """Kiểm tra có paths giữa expert và project không"""
    with driver.session() as session:
        result = session.run("""
            MATCH path = (e:Expert {expert_id: $expert_id})-[*1..5]-(p:Project {project_id: $project_id})
            RETURN path, length(path) as path_length
            LIMIT 5
        """, expert_id=expert_id, project_id=project_id)
        
        paths = list(result)
        if paths:
            print(f"\n[OK] Tìm thấy {len(paths)} paths giữa {expert_id} và {project_id}")
            for i, path_record in enumerate(paths, 1):
                print(f"   Path {i}: Length = {path_record['path_length']}")
            return True
        else:
            print(f"\n[FAIL] KHÔNG tìm thấy paths giữa {expert_id} và {project_id}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Debug + rank candidate projects for an expert")
    parser.add_argument("--expert_id", default="EXP_0003", help="Expert ID, e.g., EXP_0003")
    parser.add_argument("--limit", type=int, default=20, help="Top-N to print")
    parser.add_argument("--max_path_length", type=int, default=5, help="Max path length for reasoning paths")
    parser.add_argument(
        "--status_filter",
        default="planning,recruiting,ongoing",
        help="Comma-separated statuses; use 'ALL' for no filter",
    )
    args = parser.parse_args()

    expert_id = args.expert_id
    limit = args.limit
    max_path_length = args.max_path_length
    if args.status_filter.strip().upper() == "ALL":
        status_filter = ["planning", "recruiting", "ongoing", "completed", "suspended"]
    else:
        status_filter = [s.strip() for s in args.status_filter.split(",") if s.strip()]
    
    print("="*80)
    print(f"DEBUG: Kiểm tra recommendations cho {expert_id}")
    print("="*80)
    
    # 1. Kiểm tra expert có tồn tại không
    if not check_expert_exists(expert_id):
        print("\n⚠️ Vui lòng kiểm tra lại expert_id")
        driver.close()
        return
    
    # 2. Kiểm tra chuyên môn của expert
    expertise_fields = check_expert_expertise(expert_id)
    
    # 3. Kiểm tra số lượng projects
    total_projects = check_projects_count()
    
    if total_projects == 0:
        print("\n⚠️ KHÔNG có projects nào trong database!")
        print("   Hãy chạy seed_data.py để thêm dữ liệu mẫu")
        driver.close()
        return
    
    # 4. Collect candidates from all relevant sources
    print(f"\n{'='*80}")
    print("Collect candidates from: field, funder, skill, industry, collab")
    print("="*80)
    candidates = collect_all_candidates(expert_id, status_filter)

    # 5. Rank candidates using reasoning-path suitability score
    print(f"\n{'='*80}")
    print("Rank candidates by suitability score (reasoning paths)")
    print("="*80)
    
    engine = PGPRRecommender(max_path_length=max_path_length, data_dir="pgpr_data")
    ranked = rank_candidates(engine, expert_id, candidates, max_path_length=max_path_length)

    # Print top-N
    print(f"\nTop {min(limit, len(ranked))} recommendations:")
    for idx, r in enumerate(ranked[:limit], 1):
        print(f"\n{idx}. {r.get('title','N/A')} ({r.get('project_id','N/A')})")
        print(f"   Score: {r.get('score')}")
        print(f"   Status: {r.get('status')}, Location: {r.get('location')}, TRL: {r.get('trl')}, Budget: {r.get('budget')}")
        print(f"   Candidate sources: {r.get('candidate_sources')}")
        if r.get("common_funders"):
            print(f"   common_funders: {r.get('common_funders')}")
        if r.get("matched_skills"):
            print(f"   matched_skills: {r.get('matched_skills')}")
        if r.get("matched_industries"):
            print(f"   matched_industries: {r.get('matched_industries')}")
        if r.get("collab_links"):
            print(f"   collab_links: {r.get('collab_links')}")
        print(f"   Path diversity: {r.get('path_diversity')}")

        if r.get("top_paths"):
            print("   Top reasoning paths:")
            for i, p in enumerate(r["top_paths"], 1):
                print(f"     - Path {i}: {p.get('explanation')} (score={round(p.get('score',0.0),3)}, len={p.get('length')})")
    
    engine.close()
    driver.close()
    
    print("\n" + "="*80)
    print("Kết thúc debug")
    print("="*80)

if __name__ == "__main__":
    main()
