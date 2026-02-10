"""
PGPR Training: collect positive/negative (source, target) pairs from Neo4j,
REINFORCE training loop to learn policy that finds paths to target entities.

Reference: PGPR (Xian et al., SIGIR 2019).
"""

import os
import argparse
import logging
import random
from typing import List, Tuple, Optional

import torch
import torch.nn.functional as F
from neo4j import GraphDatabase
from dotenv import load_dotenv

from pgpr_kg import KG, _entity_key, build_kg_from_neo4j
from pgpr_env import KGEnv
from pgpr_policy import PolicyNetwork

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


def collect_positive_pairs_project_expert(driver, limit: int = 500) -> List[Tuple[str, str]]:
    """(source_entity_key, target_entity_key). source=Project, target=Expert where Expert PARTICIPATES_IN Project."""
    query = """
    MATCH (p:Project)<-[:PARTICIPATES_IN]-(e:Expert)
    RETURN p.project_id AS project_id, e.expert_id AS expert_id
    LIMIT $limit
    """
    with driver.session() as session:
        result = session.run(query, limit=limit)
        records = list(result)
    pairs = []
    for record in records:
        proj_id = record["project_id"]
        exp_id = record["expert_id"]
        pairs.append((_entity_key("Project", proj_id), _entity_key("Expert", exp_id)))
    return pairs


def collect_negative_pairs_project_expert(driver, positive_pairs: List[Tuple[str, str]], limit: int = 500) -> List[Tuple[str, str]]:
    """(project_key, expert_key) where expert does NOT participate in project. Random expert."""
    project_keys = list({p[0] for p in positive_pairs})
    with driver.session() as session:
        result = session.run("MATCH (e:Expert) RETURN e.expert_id AS expert_id LIMIT $limit", limit=limit * 2)
        expert_ids = [r["expert_id"] for r in list(result)]
    pos_set = set((p[0], p[1]) for p in positive_pairs)
    negatives = []
    for proj_key in project_keys:
        _, proj_id = proj_key.split("::", 1)
        for _ in range(min(3, limit // max(len(project_keys), 1))):
            exp_id = random.choice(expert_ids)
            pair = (proj_key, _entity_key("Expert", exp_id))
            if pair not in pos_set:
                negatives.append(pair)
    return negatives[:limit]


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
    state, valid_actions = env.reset(source_key, target_type=target_type)
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
                reward = step_reward if step_reward > 0 else (-0.1 if is_positive else 0.1)
            break

    if not log_probs_list:
        reward = -0.1 if is_positive else 0.0
    return path_actions, reward, log_probs_list


def train_pgpr(
    data_dir: str = "pgpr_data",
    max_path_length: int = 5,
    embedding_dim: int = 64,
    hidden_dim: int = 128,
    lr: float = 1e-3,
    n_epoch: int = 50,
    batch_size: int = 32,
    n_positive: int = 200,
    n_negative: int = 200,
    save_path: str = "pgpr_data/policy.pt",
) -> None:
    """Build KG, collect pairs, train policy with REINFORCE."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Device: %s", device)

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

    positive_pairs = collect_positive_pairs_project_expert(driver, limit=n_positive)
    negative_pairs = collect_negative_pairs_project_expert(driver, positive_pairs, limit=n_negative)
    logger.info("Positive pairs: %d, Negative pairs: %d", len(positive_pairs), len(negative_pairs))
    if not positive_pairs:
        logger.warning("No positive pairs. Add PARTICIPATES_IN data in Neo4j or use seed data.")

    all_pairs = positive_pairs + negative_pairs
    rewards_positive = [1.0] * len(positive_pairs) + [0.0] * len(negative_pairs)
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
                target_type = "Expert"
                is_positive = idx < len(positive_pairs)
                path_actions, reward, log_probs_list = run_episode(
                    env, policy, source_key, target_key, target_type, device, max_path_length,
                    deterministic=False, is_positive=is_positive,
                )
                expected_reward = rewards_positive[idx] if is_positive else 0.0
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
    parser = argparse.ArgumentParser(description="Train PGPR policy (REINFORCE)")
    parser.add_argument("--data_dir", default="pgpr_data", help="KG data directory")
    parser.add_argument("--max_path_length", type=int, default=5)
    parser.add_argument("--embedding_dim", type=int, default=64)
    parser.add_argument("--hidden_dim", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--n_epoch", type=int, default=50)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--n_positive", type=int, default=200)
    parser.add_argument("--n_negative", type=int, default=200)
    parser.add_argument("--save_path", default="pgpr_data/policy.pt")
    args = parser.parse_args()
    train_pgpr(
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
