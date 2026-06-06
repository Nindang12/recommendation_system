"""Synthetic tests for the Inductive PGPR candidate prototype."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pgpr.inductive_action_schema import ALLOWED_ACTION_RELATIONS, validate_action_schema  # noqa: E402
from pgpr.inductive_pgpr_env import InductiveAction, InductiveKGEnv  # noqa: E402
from pgpr.inductive_pgpr_policy import InductivePolicyNetwork  # noqa: E402
from pgpr.inductive_shadow import InductivePGPRShadowRunner  # noqa: E402


def _synthetic_snapshot() -> dict:
    nodes = [
        _node("n_exp", "Expert", {"expert_id": "exp_new", "name": "Cold Start Expert"}),
        _node("n_topic", "ResearchTopic", {"topic_id": "topic_ai", "name": "AI"}),
        _node("n_project", "Project", {"project_id": "prj_ai", "title": "AI Project"}),
        _node("n_skill", "Skill", {"skill_id": "skill_python", "name": "Python"}),
        _node("n_enterprise", "Enterprise", {"enterprise_id": "ent_private", "name": "Private Enterprise"}),
        _node("n_funder", "Funder", {"funder_id": "fnd_ai", "name": "AI Funder"}),
        _node("n_rejected", "Expert", {"expert_id": "exp_rejected", "name": "Rejected Expert", "entity_verification_status": "rejected"}),
        _node(
            "n_owner_other",
            "Expert",
            {
                "expert_id": "exp_owner_other",
                "name": "Other Owner Expert",
                "participation_scope": "owner_only",
                "owner_user_id": "user_other",
            },
        ),
        _node(
            "n_owner_self",
            "Expert",
            {
                "expert_id": "exp_owner_self",
                "name": "Self Owner Expert",
                "participation_scope": "owner_only",
                "owner_user_id": "user_self",
            },
        ),
    ]
    edges = [
        _edge("e1", "n_exp", "n_topic", "HAS_EXPERIENCE_IN"),
        _edge("e2", "n_project", "n_topic", "FOCUSES_ON_TOPIC"),
        _edge("e3", "n_project", "n_skill", "REQUIRES_SKILL"),
        _edge("e4", "n_enterprise", "n_project", "WORK_FOR"),
        _edge("e5", "n_funder", "n_project", "FUNDS"),
        _edge("e6", "n_rejected", "n_topic", "HAS_EXPERIENCE_IN"),
        _edge("e7", "n_owner_other", "n_topic", "HAS_EXPERIENCE_IN"),
        _edge("e8", "n_owner_self", "n_topic", "HAS_EXPERIENCE_IN"),
    ]
    return {
        "schema_version": 1,
        "snapshot_id": "synthetic_inductive_pgpr",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "privacy": {"sanitized": True},
        "metadata": {"node_count": len(nodes), "edge_count": len(edges)},
        "nodes": nodes,
        "edges": edges,
    }


def _node(element_id: str, label: str, properties: dict) -> dict:
    return {
        "element_id": element_id,
        "id": element_id,
        "labels": [label],
        "primary_label": label,
        "properties": properties,
    }


def _edge(element_id: str, source: str, target: str, relation: str) -> dict:
    return {
        "element_id": element_id,
        "source": source,
        "target": target,
        "type": relation,
        "properties": {},
    }


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_tests() -> dict:
    snapshot = _synthetic_snapshot()
    schema = validate_action_schema(edge["type"] for edge in snapshot["edges"])
    _assert("WORK_FOR" in schema["blocked_relations"], "WORK_FOR must stay outside policy action space.")
    _assert("HAS_EXPERIENCE_IN" in ALLOWED_ACTION_RELATIONS, "Expected expert-topic relation in allowed schema.")

    env = InductiveKGEnv(snapshot, max_path_length=3)
    _assert(env.node_count == 9, "Synthetic graph should index all nodes for mode-aware masking.")
    _assert(env.action_edge_count == 13, "Direction policy should index reversible edges plus forward-only FUNDS.")

    funder_actions = env.filtered_actions("Project::prj_ai", target_type="Expert")
    _assert(
        not any(action.next_key == "Funder::fnd_ai" for action in funder_actions),
        "FUNDS is forward-only, so Project should not reverse-walk to Funder.",
    )

    state, actions = env.reset("Expert::exp_new", target_type="Project")
    _assert(state[0] == "Expert::exp_new", "Reset should keep source key.")
    _assert(actions == [InductiveAction("HAS_EXPERIENCE_IN", "ResearchTopic::topic_ai", "out")], "Expert should have one valid topic action.")

    state, actions, reward, done = env.step(actions[0])
    _assert(state[0] == "ResearchTopic::topic_ai", "First step should reach topic.")
    _assert(not done and reward == 0.0, "Intermediate topic should not finish Project recommendation.")
    project_actions = [action for action in actions if action.next_key == "Project::prj_ai"]
    _assert(project_actions, "Topic should expose reverse path to project.")
    _assert(
        not any(action.next_key == "Expert::exp_rejected" for action in actions),
        "Rejected expert must not appear in public valid actions.",
    )
    _assert(
        not any(action.next_key == "Expert::exp_owner_other" for action in actions),
        "Owner-only expert from another user must not appear in public valid actions.",
    )

    current_embedding = env.encode_node(state[0])
    payloads = env.action_payloads(actions)
    policy = InductivePolicyNetwork(embedding_dim=env.encoder.dimension)
    log_probs, entropy = policy(current_embedding, [], payloads)
    _assert(log_probs.numel() == len(actions), "Policy must score every valid action.")
    _assert(bool(log_probs.isfinite().all()), "Policy log probabilities must be finite.")
    _assert(float(entropy.item()) >= 0.0, "Policy entropy should be non-negative.")

    state, actions, reward, done = env.step(project_actions[0])
    _assert(done and reward == 1.0, "Path should finish when Project target type is reached.")
    validity = env.validate_path()
    _assert(validity["valid"], f"Path should pass validity gate: {validity}")

    shadow = InductivePGPRShadowRunner(InductiveKGEnv(snapshot, max_path_length=3), enabled=False)
    shadow_report = shadow.recommend_shadow(source_key="Expert::exp_new", target_type="Project", limit=3, max_steps=2)
    _assert(shadow_report["runtime_enabled"] is False, "Shadow runner must not enable runtime.")
    _assert(shadow_report["prototype_only"] is True, "Shadow runner should be marked prototype-only.")
    beam_report = shadow.recommend_beam_shadow(source_key="Project::prj_ai", target_type="Expert", beam_width=5, max_hops=3)
    _assert(beam_report["runtime_enabled"] is False, "Beam shadow must not enable runtime.")
    _assert(beam_report["candidate_count"] >= 1, "Beam search should find at least one expert candidate.")
    _assert(
        beam_report["candidates"][0]["reasoning_path"],
        "Beam search candidate should include a reasoning path.",
    )
    public_ids = {item["entity_key"] for item in beam_report["candidates"]}
    _assert("Expert::exp_owner_other" not in public_ids, "Public beam must block owner_only of another user.")
    _assert("Expert::exp_owner_self" not in public_ids, "Public beam must block owner_only without personal context.")

    personal_shadow = InductivePGPRShadowRunner(
        InductiveKGEnv(snapshot, max_path_length=3, mode="personal", current_user_id="user_self"),
        enabled=False,
    )
    personal_report = personal_shadow.recommend_beam_shadow(
        source_key="Project::prj_ai",
        target_type="Expert",
        beam_width=10,
        max_hops=3,
        limit=10,
    )
    personal_ids = {item["entity_key"] for item in personal_report["candidates"]}
    _assert("Expert::exp_owner_self" in personal_ids, "Personal mode should allow owner_only owned by current user.")
    _assert("Expert::exp_owner_other" not in personal_ids, "Personal mode should block owner_only from other users.")

    admin_shadow = InductivePGPRShadowRunner(
        InductiveKGEnv(snapshot, max_path_length=3, mode="admin_debug", current_user_id="admin"),
        enabled=False,
    )
    admin_report = admin_shadow.recommend_beam_shadow(
        source_key="Project::prj_ai",
        target_type="Expert",
        beam_width=10,
        max_hops=3,
        limit=10,
    )
    admin_ids = {item["entity_key"] for item in admin_report["candidates"]}
    _assert("Expert::exp_owner_other" in admin_ids, "Admin debug should be able to inspect owner_only candidates.")
    _assert(admin_report["status"] == "shadow_disabled", "Admin debug inspection must still keep runtime disabled.")

    return {
        "status": "passed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tests": {
            "action_schema_freeze": "passed",
            "snapshot_env": "passed",
            "policy_forward_pass": "passed",
            "shadow_interface_runtime_disabled": "passed",
            "beam_search_shadow": "passed",
            "owner_only_public_personal_admin_mask": "passed",
        },
        "synthetic_graph": {
            "node_count": env.node_count,
            "action_edge_count": env.action_edge_count,
            "blocked_relations": schema["blocked_relations"],
            "path_entities": env.path_entity_keys(),
            "path_relations": env.path_relation_tokens(),
        },
        "shadow": {
            "status": shadow_report["status"],
            "candidate_count": shadow_report["candidate_count"],
            "trace_length": len(shadow_report["trace"]),
            "beam_candidate_count": beam_report["candidate_count"],
            "beam_latency_ms": beam_report["latency_ms"],
            "personal_beam_candidate_count": personal_report["candidate_count"],
            "admin_beam_candidate_count": admin_report["candidate_count"],
        },
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    report = run_tests()
    output = ROOT / "scripts" / "inductive_pgpr_prototype_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "passed", "output": str(output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
