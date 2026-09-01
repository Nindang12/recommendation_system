"""Audit skill name consistency across Expert/Project (Mongo + Neo4j)."""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repositories.auth_repo import AuthRepository
from repositories.pgpr_graph_repo import PGPRGraphRepository

OUT = Path(__file__).resolve().parent / "skill_consistency_audit.json"


def normalize_skill_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("‐", "-").replace("‑", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().lower()
    return re.sub(r"\s+", " ", text)


def slug_key(value: Any) -> str:
    return normalize_skill_key(str(value or "").replace("_", " ").replace("-", " "))


def skill_names_from_expert(doc: Dict[str, Any]) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    rc = doc.get("research_capacity") or {}
    for sm in rc.get("skills_methods") or []:
        if isinstance(sm, dict):
            name = str(sm.get("name") or "").strip()
            if name:
                rows.append(("expert.skills_methods", name))
        elif sm:
            rows.append(("expert.skills_methods", str(sm).strip()))
    for tech in rc.get("technology") or []:
        if tech:
            rows.append(("expert.technology", str(tech).strip()))
    return rows


def skill_names_from_project(doc: Dict[str, Any]) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    req = doc.get("requirements_and_timeline") or {}
    for sk in req.get("required_skills") or []:
        if isinstance(sk, dict):
            name = str(sk.get("name") or "").strip()
            if name:
                rows.append(("project.required_skills", name))
        elif sk:
            rows.append(("project.required_skills", str(sk).strip()))
    return rows


def collect_mongo_skills(repo: AuthRepository) -> Dict[str, Any]:
    by_norm: Dict[str, Set[str]] = defaultdict(set)
    by_source: Dict[str, Set[str]] = defaultdict(set)
    expert_only_norm: Set[str] = set()
    project_only_norm: Set[str] = set()
    both_norm: Set[str] = set()

    expert_norms: Set[str] = set()
    project_norms: Set[str] = set()

    for doc in repo.experts.find({}, {"expert_id": 1, "research_capacity": 1}):
        for source, name in skill_names_from_expert(doc):
            key = normalize_skill_key(name)
            if not key:
                continue
            by_norm[key].add(name)
            by_source[source].add(name)
            expert_norms.add(key)

    for doc in repo.projects.find({}, {"project_id": 1, "requirements_and_timeline": 1}):
        for source, name in skill_names_from_project(doc):
            key = normalize_skill_key(name)
            if not key:
                continue
            by_norm[key].add(name)
            by_source[source].add(name)
            project_norms.add(key)

    for key in expert_norms:
        if key in project_norms:
            both_norm.add(key)
        else:
            expert_only_norm.add(key)
    for key in project_norms - expert_norms:
        project_only_norm.add(key)

    duplicate_groups = [
        {"normalized": k, "variants": sorted(v)}
        for k, v in sorted(by_norm.items())
        if len(v) > 1
    ]

    return {
        "expert_skill_norm_count": len(expert_norms),
        "project_skill_norm_count": len(project_norms),
        "shared_norm_count": len(both_norm),
        "expert_only_norm_count": len(expert_only_norm),
        "project_only_norm_count": len(project_only_norm),
        "duplicate_format_groups": len(duplicate_groups),
        "duplicate_format_samples": duplicate_groups[:40],
        "sources_unique_raw": {k: len(v) for k, v in by_source.items()},
    }


def collect_neo4j_skills(graph: PGPRGraphRepository) -> Dict[str, Any]:
    skill_rows = graph.run_read(
        """
        MATCH (s:Skill)
        RETURN s.skill_id AS skill_id, s.name AS name, s.label AS label
        """
    )
    mt_rows = graph.run_read(
        """
        MATCH (m:MethodTechnique)
        RETURN m.name AS name
        """
    )

    skill_by_norm: Dict[str, Set[str]] = defaultdict(set)
    for row in skill_rows:
        for field in ("name", "label", "skill_id"):
            raw = row.get(field)
            if raw in (None, ""):
                continue
            skill_by_norm[normalize_skill_key(raw)].add(f"Skill.{field}={raw}")

    mt_by_norm: Dict[str, Set[str]] = defaultdict(set)
    for row in mt_rows:
        raw = row.get("name")
        if raw:
            mt_by_norm[normalize_skill_key(raw)].add(f"MethodTechnique.name={raw}")

    skill_dupes = [
        {"normalized": k, "variants": sorted(v)}
        for k, v in sorted(skill_by_norm.items())
        if len(v) > 1
    ]

    cross_label = []
    all_norms = set(skill_by_norm) | set(mt_by_norm)
    for key in sorted(all_norms):
        s = skill_by_norm.get(key, set())
        m = mt_by_norm.get(key, set())
        if s and m:
            cross_label.append({"normalized": key, "skill": sorted(s), "method_technique": sorted(m)})

    # Project REQUIRES_SKILL vs Expert HAS_SKILL overlap on live graph
    overlap = graph.run_read(
        """
        MATCH (p:Project)-[:REQUIRES_SKILL]->(s)
        MATCH (e:Expert)-[:HAS_SKILL]->(t)
        WHERE toLower(trim(coalesce(s.name, s.skill_id, s.label, ''))) =
              toLower(trim(coalesce(t.name, t.skill_id, t.label, '')))
          AND coalesce(s.name, s.skill_id, '') <> ''
        RETURN DISTINCT
            coalesce(s.name, s.skill_id, s.label) AS skill_name,
            count(DISTINCT p) AS projects,
            count(DISTINCT e) AS experts
        ORDER BY experts DESC
        LIMIT 30
        """
    )

    project_skill_nodes = graph.run_read(
        """
        MATCH (p:Project)-[:REQUIRES_SKILL]->(s)
        RETURN DISTINCT coalesce(s.name, s.skill_id, s.label) AS skill, labels(s) AS labels
        """
    )
    expert_skill_nodes = graph.run_read(
        """
        MATCH (e:Expert)-[:HAS_SKILL]->(s)
        RETURN DISTINCT coalesce(s.name, s.skill_id, s.label) AS skill, labels(s) AS labels
        LIMIT 5000
        """
    )

    project_labels = defaultdict(set)
    expert_labels = defaultdict(set)
    for row in project_skill_nodes:
        skill = str(row.get("skill") or "")
        if skill:
            project_labels[normalize_skill_key(skill)].add(skill)
    for row in expert_skill_nodes:
        skill = str(row.get("skill") or "")
        if skill:
            expert_labels[normalize_skill_key(skill)].add(skill)

    graph_dupes = [
        {"normalized": k, "project_variants": sorted(project_labels[k]), "expert_variants": sorted(expert_labels[k])}
        for k in sorted(set(project_labels) & set(expert_labels))
        if project_labels[k] != expert_labels[k]
    ]

    return {
        "skill_nodes": len(skill_rows),
        "method_technique_nodes": len(mt_rows),
        "skill_internal_duplicate_groups": len(skill_dupes),
        "skill_internal_duplicate_samples": skill_dupes[:30],
        "skill_vs_method_technique_overlap": len(cross_label),
        "skill_vs_method_technique_samples": cross_label[:30],
        "requires_has_skill_overlap_top": overlap,
        "project_expert_variant_mismatch_groups": len(graph_dupes),
        "project_expert_variant_mismatch_samples": graph_dupes[:30],
    }


def main() -> int:
    repo = AuthRepository()
    graph = PGPRGraphRepository()
    report = {
        "mongo": collect_mongo_skills(repo),
        "neo4j": {},
    }
    try:
        report["neo4j"] = collect_neo4j_skills(graph)
    finally:
        graph.close()

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    sys.stdout.buffer.write(f"written {OUT}\n".encode("utf-8", errors="replace"))
    m = report["mongo"]
    n = report["neo4j"]
    sys.stdout.buffer.write(
        (
            f"mongo_duplicate_groups={m['duplicate_format_groups']} "
            f"neo4j_skill_dupes={n.get('skill_internal_duplicate_groups')} "
            f"skill_vs_method={n.get('skill_vs_method_technique_overlap')} "
            f"project_expert_mismatch={n.get('project_expert_variant_mismatch_groups')}\n"
        ).encode("utf-8", errors="replace")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
