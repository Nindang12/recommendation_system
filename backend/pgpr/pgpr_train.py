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
from typing import List, Tuple, Dict

PGPR_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PGPR_DIR.parent
for path in (str(BACKEND_DIR), str(PGPR_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import torch
from neo4j import GraphDatabase

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
    "Expert_Expert": "(s:Expert)-[:HAS_EXPERTISE_IN]->(:ResearchField)<-[:HAS_EXPERTISE_IN]-(t:Expert)",

    # 5. Project - Project
    # Custom query below because "similar project" is defined by multiple signals:
    # shared ResearchTopic, shared ResearchDirection, or shared Funder.
    "Project_Project": "",
}


PROJECT_PROJECT_SIMILARITY_PREDICATE = """
(
    EXISTS {
        MATCH (s)-[:FOCUSES_ON_TOPIC]->(:ResearchTopic)<-[:FOCUSES_ON_TOPIC]-(t)
    }
    OR EXISTS {
        MATCH (s)-[:FOCUSES_ON]->(:ResearchDirection)<-[:FOCUSES_ON]-(t)
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
) -> None:
    """Build KG, collect pairs, train policy with REINFORCE."""
    if task_name not in GROUND_TRUTH_RULES:
        raise ValueError(f"Unsupported task '{task_name}'. Available: {sorted(GROUND_TRUTH_RULES)}")

    source_type, target_type = task_name.split("_", 1)
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
        kg = build_kg_from_neo4j(data_dir=data_dir, train_emb=True, emb_dim=embedding_dim)

    if kg.entity_emb is None:
        import numpy as np
        n_ent = len(kg.entity2id)
        n_rel = len(kg.relation2id)
        np.random.seed(42)
        kg.entity_emb = np.random.uniform(-0.1, 0.1, (n_ent, embedding_dim)).astype(np.float32)
        kg.relation_emb = np.random.uniform(-0.1, 0.1, (n_rel, embedding_dim)).astype(np.float32)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    env = KGEnv(kg, driver=driver, max_path_length=max_path_length)
    policy = PolicyNetwork(kg, embedding_dim=embedding_dim, hidden_dim=hidden_dim)
    policy.to(device)
    optimizer = torch.optim.Adam(policy.parameters(), lr=lr)

    positive_pairs = collect_dynamic_pairs(driver, task_name, is_positive=True, limit=n_positive)
    negative_pairs = collect_dynamic_pairs(driver, task_name, is_positive=False, limit=n_negative)
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
                    save_path="" # Để trống để tự động lưu theo tên task
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
        )
