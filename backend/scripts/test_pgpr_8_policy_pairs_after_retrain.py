"""Runtime smoke test for the 8 retrained PGPR policy pairs.

This script validates two cases per task:
- a positive runtime case: source is sampled from Neo4j positive pairs and
  the loaded policy should produce at least one target-type candidate;
- a no-result case: source id is intentionally missing from PGPR vocab and
  the policy call should return an empty list without crashing.

Run from repository root:
    python backend/scripts/test_pgpr_8_policy_pairs_after_retrain.py
"""
from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "pgpr") not in sys.path:
    sys.path.insert(0, str(ROOT / "pgpr"))

from core.env import load_project_env  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402
from pgpr.pgpr_recommendation import PGPRRecommender  # noqa: E402
from pgpr.pgpr_train import collect_dynamic_pairs  # noqa: E402

import os  # noqa: E402


TASKS = (
    "Project_Expert",
    "Expert_Project",
    "Project_Funder",
    "Funder_Project",
    "Expert_Expert",
    "Project_Project",
    "Expert_Enterprise",
    "Enterprise_Expert",
)

DATA_DIR = ROOT / "pgpr" / "pgpr_data"
OUT_JSON = ROOT / "scripts" / "pgpr_8_policy_pairs_after_retrain.json"
OUT_MD = ROOT / "scripts" / "pgpr_8_policy_pairs_after_retrain.md"


def _split_key(entity_key: str) -> tuple[str, str]:
    if "::" not in entity_key:
        raise ValueError(f"Invalid entity key: {entity_key}")
    return tuple(entity_key.split("::", 1))  # type: ignore[return-value]


def _finite_scores(paths: list[dict[str, Any]]) -> bool:
    for item in paths:
        score = item.get("score")
        if score is not None and not math.isfinite(float(score)):
            return False
        for path in item.get("top_paths") or []:
            path_score = path.get("path_score")
            if path_score is not None and not math.isfinite(float(path_score)):
                return False
    return True


def _policy_file(task: str) -> Path:
    return DATA_DIR / f"policy_{task}.pt"


def _run_positive_case(
    engine: PGPRRecommender,
    driver: Any,
    task: str,
    *,
    n_rollouts: int,
) -> dict[str, Any]:
    source_type, target_type = task.split("_", 1)
    started = time.perf_counter()
    positive_pairs = collect_dynamic_pairs(driver, task, is_positive=True, limit=20)
    negative_pairs = collect_dynamic_pairs(driver, task, is_positive=False, limit=20)
    pair_ms = (time.perf_counter() - started) * 1000.0

    row: dict[str, Any] = {
        "task": task,
        "source_type": source_type,
        "target_type": target_type,
        "policy_file": str(_policy_file(task).relative_to(REPO_ROOT)),
        "policy_file_exists": _policy_file(task).exists(),
        "positive_pair_count_sample": len(positive_pairs),
        "negative_pair_count_sample": len(negative_pairs),
        "pair_collection_latency_ms": round(pair_ms, 2),
    }
    if not positive_pairs:
        row.update(
            {
                "status": "failed",
                "reason": "no_positive_pairs",
                "candidate_count": 0,
                "latency_ms": 0,
            }
        )
        return row

    source_key, expected_target_key = positive_pairs[0]
    key_type, source_id = _split_key(source_key)
    if key_type != source_type:
        row.update(
            {
                "status": "failed",
                "reason": f"source_type_mismatch:{key_type}",
                "candidate_count": 0,
                "latency_ms": 0,
            }
        )
        return row

    started = time.perf_counter()
    paths = engine.policy_guided_paths(
        source_id=source_id,
        source_type=source_type,
        target_type=target_type,
        n_rollouts=n_rollouts,
        deterministic=False,
    )
    if not paths:
        paths = engine.policy_guided_paths(
            source_id=source_id,
            source_type=source_type,
            target_type=target_type,
            n_rollouts=max(5, min(20, n_rollouts)),
            deterministic=True,
        )
    latency_ms = (time.perf_counter() - started) * 1000.0

    target_prefix = f"{target_type}::"
    target_type_ok = all(str(item.get("target_entity_key", "")).startswith(target_prefix) for item in paths)
    top = paths[0] if paths else {}
    top_paths = top.get("top_paths") or []
    first_path = top_paths[0] if top_paths else {}
    row.update(
        {
            "status": "passed" if paths and target_type_ok and _finite_scores(paths) else "failed",
            "reason": "" if paths else "no_candidate_from_policy",
            "source_key": source_key,
            "expected_positive_target_key": expected_target_key,
            "candidate_count": len(paths),
            "latency_ms": round(latency_ms, 2),
            "target_type_ok": target_type_ok,
            "finite_scores": _finite_scores(paths),
            "top_target_key": top.get("target_entity_key"),
            "top_score": round(float(top.get("score") or 0.0), 6) if top else None,
            "top_path_relations": first_path.get("path_relations") or [],
            "top_path_entities": first_path.get("path_entities") or [],
        }
    )
    return row


def _run_no_result_case(engine: PGPRRecommender, task: str) -> dict[str, Any]:
    source_type, target_type = task.split("_", 1)
    missing_id = f"__missing_{task.lower()}__"
    started = time.perf_counter()
    error = ""
    try:
        paths = engine.policy_guided_paths(
            source_id=missing_id,
            source_type=source_type,
            target_type=target_type,
            n_rollouts=20,
            deterministic=True,
        )
    except Exception as exc:  # noqa: BLE001
        paths = []
        error = str(exc)
    latency_ms = (time.perf_counter() - started) * 1000.0
    return {
        "task": task,
        "source_key": f"{source_type}::{missing_id}",
        "target_type": target_type,
        "status": "passed" if not error and not paths else "failed",
        "reason": error or ("" if not paths else "unexpected_candidate_for_missing_source"),
        "candidate_count": len(paths),
        "latency_ms": round(latency_ms, 2),
    }


def _write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# PGPR 8 Policy Pair Runtime Test\n")
    lines.append(f"- Generated: {report['generated_at']}")
    lines.append(f"- Data dir: `{report['data_dir']}`")
    lines.append(f"- Tasks: {report['task_count']}")
    lines.append(f"- Passed positive cases: {report['summary']['positive_passed']}/{report['task_count']}")
    lines.append(f"- Passed no-result cases: {report['summary']['no_result_passed']}/{report['task_count']}")
    lines.append("")
    lines.append("## Positive Runtime Cases\n")
    lines.append("| Task | Status | Candidates | Latency ms | Top target | Top path relations |")
    lines.append("|---|---|---:|---:|---|---|")
    for row in report["positive_cases"]:
        rels = " -> ".join(row.get("top_path_relations") or [])
        lines.append(
            f"| `{row['task']}` | {row['status']} | {row.get('candidate_count', 0)} | "
            f"{row.get('latency_ms', 0)} | `{row.get('top_target_key') or ''}` | {rels} |"
        )
    lines.append("")
    lines.append("## No-Result Cases\n")
    lines.append("| Task | Status | Candidates | Latency ms | Reason |")
    lines.append("|---|---|---:|---:|---|")
    for row in report["no_result_cases"]:
        lines.append(
            f"| `{row['task']}` | {row['status']} | {row.get('candidate_count', 0)} | "
            f"{row.get('latency_ms', 0)} | {row.get('reason') or ''} |"
        )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    load_project_env()
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    engine = PGPRRecommender(max_path_length=5, data_dir=str(DATA_DIR), enable_cache=True)

    positive_cases: list[dict[str, Any]] = []
    no_result_cases: list[dict[str, Any]] = []
    try:
        for task in TASKS:
            positive_cases.append(_run_positive_case(engine, driver, task, n_rollouts=200))
            no_result_cases.append(_run_no_result_case(engine, task))
    finally:
        engine.close()
        driver.close()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_dir": str(DATA_DIR.relative_to(REPO_ROOT)),
        "task_count": len(TASKS),
        "tasks": list(TASKS),
        "positive_cases": positive_cases,
        "no_result_cases": no_result_cases,
        "summary": {
            "positive_passed": sum(1 for row in positive_cases if row.get("status") == "passed"),
            "no_result_passed": sum(1 for row in no_result_cases if row.get("status") == "passed"),
        },
    }
    report["status"] = (
        "passed"
        if report["summary"]["positive_passed"] == len(TASKS)
        and report["summary"]["no_result_passed"] == len(TASKS)
        else "failed"
    )

    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(report)
    print(json.dumps({"status": report["status"], "json": str(OUT_JSON), "md": str(OUT_MD)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
