"""
PGPR Training: collect positive/negative (source, target) pairs from Neo4j,
REINFORCE training loop to learn policy that finds paths to target entities.

Reference: PGPR (Xian et al., SIGIR 2019).
"""

import os
import argparse
import logging
import random
import sys
from pathlib import Path
from collections import defaultdict
from typing import List, Tuple, Dict, Optional, Set

PGPR_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PGPR_DIR.parent
for path in (str(BACKEND_DIR), str(PGPR_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import torch
try:
    from neo4j import GraphDatabase
except ImportError:  # Offline mode can train from vocab/triples only.
    GraphDatabase = None

from core.env import load_project_env
from pgpr_kg import KG, _entity_key, build_kg_from_neo4j, LABEL_TO_ID_PROP
from pgpr_env import KGEnv
from pgpr_policy import PolicyNetwork

load_project_env()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


def _configure_stdout() -> None:
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


GROUND_TRUTH_RULES: Dict[str, str] = {
    # 1. Project - Expert (2 chiều)
    "Project_Expert": "(s:Project)<-[:PARTICIPATES_IN]-(t:Expert)",
    "Expert_Project": "(s:Expert)-[:PARTICIPATES_IN]->(t:Project)",

    # 2. Enterprise - Project (2 chiều)
    "Enterprise_Project": "(s:Enterprise)-[:PARTNERS_WITH]->(t:Project)",
    "Project_Enterprise": "(s:Project)<-[:PARTNERS_WITH]-(t:Enterprise)",

    # 3. Funder - Project (2 chiều)
    "Funder_Project": "(s:Funder)-[:FUNDS]->(t:Project)",
    "Project_Funder": "(s:Project)<-[:FUNDS]-(t:Funder)",

    # 4. Expert - Enterprise (2 chiều)
    "Expert_Enterprise": "(s:Expert)-[:HAS_APPLICATION_EXPERIENCE_IN]->(:Industry)<-[:OPERATES_IN]-(t:Enterprise)",
    "Enterprise_Expert": "(s:Enterprise)-[:OPERATES_IN]->(:Industry)<-[:HAS_APPLICATION_EXPERIENCE_IN]-(t:Expert)",

    # Thêm nếu cần:
    "Expert_Expert": "(s:Expert)-[:CO_AUTHORED]-(t:Expert)",

    # 5. Project - Project
    # Custom query below because "similar project" is defined by graph signals:
    # shared participant Expert or shared Funder.
    "Project_Project": "",
}


PROJECT_PROJECT_SIMILARITY_PREDICATE = """
(
    EXISTS {
        MATCH (s)<-[:PARTICIPATES_IN]-(:Expert)-[:PARTICIPATES_IN]->(t)
    }
    OR EXISTS {
        MATCH (s)<-[:FUNDS]-(:Funder)-[:FUNDS]->(t)
    }
)
"""


def _id_prop_for_label(label: str) -> str:
    return LABEL_TO_ID_PROP.get(label, f"{label.lower()}_id")


def collect_dynamic_pairs(
    driver,
    task_name: str,
    is_positive: bool = True,
    limit: int = 500,
) -> List[Tuple[str, str]]:
    """Collect positive/negative (source_key, target_key) pairs for a task."""
    if task_name not in GROUND_TRUTH_RULES:
        raise ValueError(f"Unsupported task '{task_name}'. Available: {sorted(GROUND_TRUTH_RULES)}")
    if limit <= 0:
        return []

    source_type, target_type = task_name.split("_", 1)
    s_id_prop = _id_prop_for_label(source_type)
    t_id_prop = _id_prop_for_label(target_type)

    if task_name == "Project_Project":
        similarity_predicate = PROJECT_PROJECT_SIMILARITY_PREDICATE
        if is_positive:
            query = f"""
            MATCH (s:Project)
            WHERE s.{s_id_prop} IS NOT NULL
            WITH s ORDER BY rand() LIMIT 2000

            MATCH (t:Project)
            WHERE t.{t_id_prop} IS NOT NULL
              AND s <> t
              AND {similarity_predicate}

            WITH DISTINCT s, t ORDER BY rand()
            RETURN s.{s_id_prop} AS s_id, t.{t_id_prop} AS t_id
            LIMIT $limit
            """
        else:
            query = f"""
            MATCH (s:Project)
            WHERE s.{s_id_prop} IS NOT NULL
            WITH s ORDER BY rand() LIMIT 2000

            MATCH (t:Project)
            WHERE t.{t_id_prop} IS NOT NULL
              AND s <> t
              AND NOT {similarity_predicate}

            WITH DISTINCT s, t ORDER BY rand()
            RETURN s.{s_id_prop} AS s_id, t.{t_id_prop} AS t_id
            LIMIT $limit
            """
    elif is_positive:
        rule_pattern = GROUND_TRUTH_RULES[task_name]
        query = f"""
        MATCH {rule_pattern}
        WHERE s.{s_id_prop} IS NOT NULL AND t.{t_id_prop} IS NOT NULL
          AND s <> t
        RETURN s.{s_id_prop} AS s_id, t.{t_id_prop} AS t_id
        LIMIT $limit
        """
    else:
        rule_pattern = GROUND_TRUTH_RULES[task_name]
        query = f"""
        MATCH (s:{source_type})
        WHERE s.{s_id_prop} IS NOT NULL
        WITH s ORDER BY rand() LIMIT 2000

        MATCH (t:{target_type})
        WHERE t.{t_id_prop} IS NOT NULL
          AND s <> t
          AND NOT EXISTS {{ MATCH {rule_pattern} }}

        WITH s, t ORDER BY rand()
        RETURN s.{s_id_prop} AS s_id, t.{t_id_prop} AS t_id
        LIMIT $limit
        """

    with driver.session() as session:
        result = session.run(query, limit=limit)
        records = list(result)

    pairs: List[Tuple[str, str]] = []
    for record in records:
        s_id = record["s_id"]
        t_id = record["t_id"]
        if s_id is None or t_id is None:
            continue
        pairs.append((_entity_key(source_type, str(s_id)), _entity_key(target_type, str(t_id))))
    return pairs


def _entity_ids_by_type(kg: KG, label: str) -> List[int]:
    prefix = f"{label}::"
    return [entity_id for entity_id, key in kg.id2entity.items() if key.startswith(prefix)]


def _relation_id(kg: KG, relation_name: str) -> Optional[int]:
    return kg.relation2id.get(relation_name)


def _add_pair(mapping: Dict[int, Set[int]], src: int, dst: int) -> None:
    mapping[src].add(dst)


def _build_positive_pair_map(kg: KG, task_name: str) -> Dict[int, Set[int]]:
    """
    Build source->valid targets directly from vocab/triples.

    This keeps offline training aligned with the semantics of the online Cypher sampler.
    """
    source_type, target_type = task_name.split("_", 1)
    positives: Dict[int, Set[int]] = defaultdict(set)

    if task_name in {"Project_Expert", "Expert_Project"}:
        rel_id = _relation_id(kg, "PARTICIPATES_IN")
        if rel_id is None:
            return positives
        for h, r, t in kg.triples:
            if r != rel_id:
                continue
            hk = kg.id2entity.get(h, "")
            tk = kg.id2entity.get(t, "")
            if hk.startswith("Expert::") and tk.startswith("Project::"):
                if task_name == "Expert_Project":
                    _add_pair(positives, h, t)
                else:
                    _add_pair(positives, t, h)
        return positives

    if task_name in {"Funder_Project", "Project_Funder"}:
        rel_id = _relation_id(kg, "FUNDS")
        if rel_id is None:
            return positives
        for h, r, t in kg.triples:
            if r != rel_id:
                continue
            hk = kg.id2entity.get(h, "")
            tk = kg.id2entity.get(t, "")
            if hk.startswith("Funder::") and tk.startswith("Project::"):
                if task_name == "Funder_Project":
                    _add_pair(positives, h, t)
                else:
                    _add_pair(positives, t, h)
        return positives

    if task_name == "Expert_Expert":
        rel_id = _relation_id(kg, "CO_AUTHORED")
        if rel_id is None:
            return positives
        for h, r, t in kg.triples:
            if r != rel_id:
                continue
            hk = kg.id2entity.get(h, "")
            tk = kg.id2entity.get(t, "")
            if hk.startswith("Expert::") and tk.startswith("Expert::") and h != t:
                _add_pair(positives, h, t)
                _add_pair(positives, t, h)
        return positives

    if task_name in {"Enterprise_Project", "Project_Enterprise"}:
        rel_id = _relation_id(kg, "PARTNERS_WITH")
        if rel_id is None:
            return positives
        for h, r, t in kg.triples:
            if r != rel_id:
                continue
            hk = kg.id2entity.get(h, "")
            tk = kg.id2entity.get(t, "")
            if hk.startswith("Enterprise::") and tk.startswith("Project::"):
                if task_name == "Enterprise_Project":
                    _add_pair(positives, h, t)
                else:
                    _add_pair(positives, t, h)
        return positives

    if task_name in {"Expert_Enterprise", "Enterprise_Expert"}:
        exp_rel = _relation_id(kg, "HAS_APPLICATION_EXPERIENCE_IN")
        ent_rel = _relation_id(kg, "OPERATES_IN")
        if exp_rel is None or ent_rel is None:
            return positives
        experts_by_industry: Dict[int, Set[int]] = defaultdict(set)
        enterprises_by_industry: Dict[int, Set[int]] = defaultdict(set)
        for h, r, t in kg.triples:
            hk = kg.id2entity.get(h, "")
            tk = kg.id2entity.get(t, "")
            if r == exp_rel and hk.startswith("Expert::") and tk.startswith("Industry::"):
                experts_by_industry[t].add(h)
            elif r == ent_rel and hk.startswith("Enterprise::") and tk.startswith("Industry::"):
                enterprises_by_industry[t].add(h)
        for industry_id, experts in experts_by_industry.items():
            enterprises = enterprises_by_industry.get(industry_id) or set()
            if not enterprises:
                continue
            for expert_id in experts:
                for enterprise_id in enterprises:
                    if task_name == "Expert_Enterprise":
                        _add_pair(positives, expert_id, enterprise_id)
                    else:
                        _add_pair(positives, enterprise_id, expert_id)
        return positives

    if task_name == "Project_Project":
        part_rel = _relation_id(kg, "PARTICIPATES_IN")
        fund_rel = _relation_id(kg, "FUNDS")
        shared_projects: Dict[int, Set[int]] = defaultdict(set)
        projects_by_expert: Dict[int, Set[int]] = defaultdict(set)
        projects_by_funder: Dict[int, Set[int]] = defaultdict(set)

        for h, r, t in kg.triples:
            hk = kg.id2entity.get(h, "")
            tk = kg.id2entity.get(t, "")
            if r == part_rel and hk.startswith("Expert::") and tk.startswith("Project::"):
                projects_by_expert[h].add(t)
            elif r == fund_rel and hk.startswith("Funder::") and tk.startswith("Project::"):
                projects_by_funder[h].add(t)

        for project_sets in list(projects_by_expert.values()) + list(projects_by_funder.values()):
            project_list = list(project_sets)
            for i, source_id in enumerate(project_list):
                for j, target_id in enumerate(project_list):
                    if i == j or source_id == target_id:
                        continue
                    _add_pair(shared_projects, source_id, target_id)
        return shared_projects

    # Unsupported task falls back to empty set.
    logger.warning("Offline sampler does not support task %s", task_name)
    return positives


def _sample_pairs_from_map(
    kg: KG,
    pair_map: Dict[int, Set[int]],
    task_name: str,
    *,
    is_positive: bool,
    limit: int,
) -> List[Tuple[str, str]]:
    if limit <= 0:
        return []

    source_type, target_type = task_name.split("_", 1)
    source_ids = [src for src, targets in pair_map.items() if targets]
    target_ids = _entity_ids_by_type(kg, target_type)
    if not source_ids or not target_ids:
        return []

    pairs: List[Tuple[str, str]] = []
    if is_positive:
        all_positive: List[Tuple[int, int]] = []
        for src, targets in pair_map.items():
            all_positive.extend((src, dst) for dst in targets if src != dst)
        random.shuffle(all_positive)
        for src, dst in all_positive[:limit]:
            pairs.append((kg.id2entity[src], kg.id2entity[dst]))
        return pairs

    max_attempts = max(limit * 20, 200)
    seen: Set[Tuple[int, int]] = set()
    attempts = 0
    while len(pairs) < limit and attempts < max_attempts:
        attempts += 1
        src = random.choice(source_ids)
        dst = random.choice(target_ids)
        if src == dst or dst in pair_map.get(src, set()) or (src, dst) in seen:
            continue
        seen.add((src, dst))
        pairs.append((kg.id2entity[src], kg.id2entity[dst]))
    return pairs


def collect_offline_pairs(
    kg: KG,
    task_name: str,
    *,
    is_positive: bool = True,
    limit: int = 500,
) -> List[Tuple[str, str]]:
    """Collect positive/negative pairs from local vocab/triples without Neo4j."""
    if task_name not in GROUND_TRUTH_RULES:
        raise ValueError(f"Unsupported task '{task_name}'. Available: {sorted(GROUND_TRUTH_RULES)}")
    pair_map = _build_positive_pair_map(kg, task_name)
    return _sample_pairs_from_map(kg, pair_map, task_name, is_positive=is_positive, limit=limit)


def run_episode(
    env: KGEnv,
    policy: PolicyNetwork,
    source_key: str,
    target_key: str,
    target_type: str,
    device: torch.device,
    max_steps: int,
    deterministic: bool = False,
    is_positive: bool = True,
) -> Tuple[List[Tuple[int, int]], float, List[torch.Tensor]]:
    """
    Run one episode: start at source_key, use policy to step until we reach target_type or max_steps.
    Returns: (path_actions, reward, list of log_probs for REINFORCE).
    is_positive: True = (source, target) is a positive pair → reward 1 if reach target_key else -0.1.
    is_positive: False = negative pair → reward -0.5 if reach target_key else 0.1.
    """
    state, valid_actions = env.reset(
        source_key,
        target_entity_key=target_key,
        target_type=target_type,
    )
    current_ent, path = state
    log_probs_list = []
    path_actions = []
    reward = -0.1

    for step in range(max_steps - 1):
        if not valid_actions:
            break
        action_idx, log_prob = policy.select_action(
            current_ent, path, valid_actions, device, deterministic=deterministic
        )
        if action_idx < 0:
            break
        log_probs_list.append(log_prob)
        action = valid_actions[action_idx]
        path_actions.append(action)
        next_state, valid_actions, step_reward, done = env.step(action)
        current_ent, path = next_state
        if done:
            reached_entity = env.get_path_entity_keys()[-1] if env.get_path_entity_keys() else None
            if reached_entity == target_key:
                reward = 1.0 if is_positive else -0.5
            else:
                reward = -0.1 if is_positive else 0.1
            break

    if not log_probs_list:
        reward = -0.1 if is_positive else 0.0
    return path_actions, reward, log_probs_list


def train_pgpr(
    task_name: str = "Project_Expert",
    data_dir: str = "pgpr_data",
    max_path_length: int = 5,
    embedding_dim: int = 64,
    hidden_dim: int = 128,
    lr: float = 1e-3,
    n_epoch: int = 50,
    batch_size: int = 32,
    n_positive: int = 200,
    n_negative: int = 200,
    save_path: str = "",
    mode: str = "auto",
) -> None:
    """Build KG, collect pairs, train policy with REINFORCE."""
    if task_name not in GROUND_TRUTH_RULES:
        raise ValueError(f"Unsupported task '{task_name}'. Available: {sorted(GROUND_TRUTH_RULES)}")

    source_type, target_type = task_name.split("_", 1)
    mode = (mode or "auto").lower()
    if mode not in {"auto", "online", "offline"}:
        raise ValueError("mode must be one of: auto, online, offline")
    if not save_path:
        save_path = os.path.join(data_dir, f"policy_{task_name}.pt")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Device: %s | Task: %s (%s -> %s)", device, task_name, source_type, target_type)

    # KG: load or build
    kg = KG(data_dir=data_dir)
    if os.path.exists(os.path.join(data_dir, "vocab.json")):
        kg.load_vocab()
        kg.load_triples()
        if os.path.exists(os.path.join(data_dir, "entity_emb.npy")):
            kg.load_embeddings()
    else:
        if mode == "offline":
            raise FileNotFoundError(
                f"Offline mode requires existing vocab/triples in {data_dir}. "
                "Run KG export beforehand."
            )
        kg = build_kg_from_neo4j(data_dir=data_dir, train_emb=True, emb_dim=embedding_dim)

    if kg.entity_emb is None:
        import numpy as np
        n_ent = len(kg.entity2id)
        n_rel = len(kg.relation2id)
        np.random.seed(42)
        kg.entity_emb = np.random.uniform(-0.1, 0.1, (n_ent, embedding_dim)).astype(np.float32)
        kg.relation_emb = np.random.uniform(-0.1, 0.1, (n_rel, embedding_dim)).astype(np.float32)

    use_online_pairs = mode == "online" or (
        mode == "auto" and GraphDatabase is not None
    )
    driver = None
    if use_online_pairs and GraphDatabase is not None:
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            driver.verify_connectivity()
            logger.info("Pair sampling mode: online (Neo4j)")
        except Exception as exc:
            if mode == "online":
                raise
            logger.warning(
                "Could not use Neo4j for pair sampling (%s). Falling back to offline mode.",
                exc,
            )
            driver = None
    else:
        logger.info("Pair sampling mode: offline (vocab/triples)")

    env = KGEnv(kg, driver=driver, max_path_length=max_path_length) if driver is not None else KGEnv(kg, max_path_length=max_path_length)
    policy = PolicyNetwork(kg, embedding_dim=embedding_dim, hidden_dim=hidden_dim)
    policy.to(device)
    optimizer = torch.optim.Adam(policy.parameters(), lr=lr)

    if driver is not None:
        positive_pairs = collect_dynamic_pairs(driver, task_name, is_positive=True, limit=n_positive)
        negative_pairs = collect_dynamic_pairs(driver, task_name, is_positive=False, limit=n_negative)
    else:
        positive_pairs = collect_offline_pairs(kg, task_name, is_positive=True, limit=n_positive)
        negative_pairs = collect_offline_pairs(kg, task_name, is_positive=False, limit=n_negative)
    logger.info("Positive pairs: %d, Negative pairs: %d", len(positive_pairs), len(negative_pairs))
    if not positive_pairs:
        logger.warning("No positive pairs found for task %s.", task_name)

    all_pairs = positive_pairs + negative_pairs
    baseline = 0.0
    baseline_decay = 0.99

    for epoch in range(n_epoch):
        policy.train()
        indices = list(range(len(all_pairs)))
        random.shuffle(indices)
        epoch_loss = 0.0
        n_batches = 0
        for i in range(0, len(indices), batch_size):
            batch_idx = indices[i : i + batch_size]
            batch_loss = torch.tensor(0.0, device=device)
            for idx in batch_idx:
                source_key, target_key = all_pairs[idx]
                is_positive = idx < len(positive_pairs)
                path_actions, reward, log_probs_list = run_episode(
                    env, policy, source_key, target_key, target_type, device, max_path_length,
                    deterministic=False, is_positive=is_positive,
                )
                if path_actions and log_probs_list:
                    # REINFORCE: loss = -sum(log_prob) * (reward - baseline)
                    log_prob_sum = sum(log_probs_list)
                    advantage = reward - baseline
                    batch_loss = batch_loss - log_prob_sum * advantage
                baseline = baseline_decay * baseline + (1 - baseline_decay) * reward
            if batch_idx:
                batch_loss = batch_loss / len(batch_idx)
                if batch_loss.requires_grad:
                    optimizer.zero_grad()
                    batch_loss.backward()
                    torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
                    optimizer.step()
                epoch_loss += batch_loss.detach().item()
                n_batches += 1

        if n_batches:
            logger.info("Epoch %d loss %.4f", epoch + 1, epoch_loss / n_batches)
        if (epoch + 1) % 10 == 0:
            os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
            torch.save({
                "model_state_dict": policy.state_dict(),
                "embedding_dim": embedding_dim,
                "epoch": epoch + 1,
            }, save_path)
            logger.info("Saved checkpoint to %s", save_path)

    env.close()
    if driver is not None:
        driver.close()
    torch.save({
        "model_state_dict": policy.state_dict(),
        "embedding_dim": embedding_dim,
    }, save_path)
    logger.info("Training done. Policy saved to %s", save_path)


if __name__ == "__main__":
    _configure_stdout()
    parser = argparse.ArgumentParser(description="Train PGPR policy (REINFORCE)")
    parser.add_argument("--task", default="Project_Expert", help=f"Training task name. Available: {', '.join(sorted(GROUND_TRUTH_RULES))}")
    parser.add_argument("--data_dir", default="pgpr_data", help="KG data directory")
    parser.add_argument("--max_path_length", type=int, default=5)
    parser.add_argument("--embedding_dim", type=int, default=64)
    parser.add_argument("--hidden_dim", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--n_epoch", type=int, default=50)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--n_positive", type=int, default=200)
    parser.add_argument("--n_negative", type=int, default=200)
    parser.add_argument("--save_path", default="", help="Optional explicit output path. Default: pgpr_data/policy_<task>.pt")
    parser.add_argument("--mode", default="auto", choices=["auto", "online", "offline"], help="Pair sampling mode. offline uses local vocab/triples only.")
    args = parser.parse_args()
    
    # NẾU GÕ LỆNH "all", SẼ LẶP QUA TOÀN BỘ TỪ ĐIỂN LUẬT
    if args.task.lower() == "all":
        logger.info(f"BẮT ĐẦU TRAIN TỰ ĐỘNG TOÀN BỘ {len(GROUND_TRUTH_RULES)} BỘ NÃO...")
        for task_key in GROUND_TRUTH_RULES.keys():
            print(f"\n{'='*60}\n🚀 ĐANG TRAIN TASK: {task_key}\n{'='*60}")
            try:
                train_pgpr(
                    task_name=task_key,
                    data_dir=args.data_dir,
                    max_path_length=args.max_path_length,
                    embedding_dim=args.embedding_dim,
                    hidden_dim=args.hidden_dim,
                    lr=args.lr,
                    n_epoch=args.n_epoch,
                    batch_size=args.batch_size,
                    n_positive=args.n_positive,
                    n_negative=args.n_negative,
                    save_path="", # Để trống để tự động lưu theo tên task
                    mode=args.mode,
                )
            except Exception as e:
                logger.error(f"Lỗi khi train task {task_key}: {e}")
                continue # Lỗi task này thì bỏ qua chạy tiếp task khác
    else:
        # Chạy 1 task bình thường như cũ
        train_pgpr(
            task_name=args.task,
            data_dir=args.data_dir,
            max_path_length=args.max_path_length,
            embedding_dim=args.embedding_dim,
            hidden_dim=args.hidden_dim,
            lr=args.lr,
            n_epoch=args.n_epoch,
            batch_size=args.batch_size,
            n_positive=args.n_positive,
            n_negative=args.n_negative,
            save_path=args.save_path,
            mode=args.mode,
        )
