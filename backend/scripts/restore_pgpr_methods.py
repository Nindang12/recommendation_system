"""Restore policy/scoring/recommend_* methods removed by patch."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
TARGET = BACKEND / "pgpr" / "pgpr_recommendation.py"
MIDDLE = BACKEND / "scripts" / "restored_middle.py"

SKIP_PREFIXES = (
    "_find_all_reachable",
    "_find_candidate",
    "_get_expert_info",
    "_get_generic_entity_info",
)


def extract_middle() -> str:
    text = subprocess.check_output(
        ["git", "show", "HEAD:backend/pgpr/pgpr_recommendation.py"],
        cwd=BACKEND.parent,
    ).decode("utf-8")
    start = text.find("    def _calculate_expert_score(")
    end = text.find("    # ==========================================\n    # EXPLAINABILITY HELPERS")
    return text[start:end]


def filter_methods(middle: str) -> str:
    parts: list[str] = []
    for m in re.finditer(r"\n    def (\w+)\(", middle):
        name = m.group(1)
        start = m.start() + 1
        rest = middle[start + 10 :]
        nxt = re.search(r"\n    def [a-zA-Z_]", rest)
        end = start + 10 + nxt.start() if nxt else len(middle)
        if any(name.startswith(p) for p in SKIP_PREFIXES):
            continue
        body = middle[start:end]
        body = body.replace(
            "with self.driver.session() as session:\n            res = session.run(\n"
            '                "MATCH (e:Expert)-[:PARTICIPATES_IN]->(p:Project {project_id: $pid}) "\n'
            '                "RETURN e.expert_id as eid",\n'
            "                pid=project_id,\n"
            "            )\n"
            "            exclude_keys = [f\"Expert::{record['eid']}\" for record in res]",
            "exclude_keys = [\n"
            '                f"Expert::{eid}" for eid in self.graph_repo.get_expert_participant_ids(project_id)\n'
            "            ]",
        )
        body = body.replace(
            "with self.driver.session() as session:\n                for item in policy_paths[:limit * 2]:\n"
            "                    target_key = item[\"target_entity_key\"]\n"
            "                    if \"::\" not in target_key:\n"
            "                        continue\n"
            "                    _, expert_id = target_key.split(\"::\", 1)\n"
            "                    expert_info = self._get_expert_info(\n"
            "                        session,\n"
            "                        expert_id,\n"
            "                        exclude_project_id=project_id,\n"
            "                    )",
            "for item in policy_paths[:limit * 2]:\n"
            "                target_key = item[\"target_entity_key\"]\n"
            "                if \"::\" not in target_key:\n"
            "                    continue\n"
            "                _, expert_id = target_key.split(\"::\", 1)\n"
            "                expert_info = self.graph_repo.get_expert_info(\n"
            "                    expert_id,\n"
            "                    exclude_project_id=project_id,\n"
            "                )",
        )
        parts.append(body)
    return "\n\n".join(parts)


def splice(keep: str) -> None:
    text = TARGET.read_text(encoding="utf-8")
    marker = "    # ==========================================\n    # EXPLAINABILITY HELPERS"
    if marker not in text:
        raise ValueError("marker not found")
    text = text.replace(marker, keep + "\n\n" + marker, 1)
    TARGET.write_text(text, encoding="utf-8")


def main() -> None:
    middle = extract_middle()
    MIDDLE.write_text(middle, encoding="utf-8")
    keep = filter_methods(middle)
    splice(keep)
    print("restored", len(keep), "chars into", TARGET)


if __name__ == "__main__":
    main()
