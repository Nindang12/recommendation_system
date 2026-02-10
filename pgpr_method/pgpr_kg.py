"""
PGPR Knowledge Graph: export triples from Neo4j, build entity/relation vocabularies,
and train/load embeddings (TransE or random) for policy state representation.

Reference: PGPR (Xian et al., SIGIR 2019).
"""

import os
import json
import logging
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Neo4j
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# Map Neo4j label -> id property name for that label
LABEL_TO_ID_PROP = {
    "Expert": "expert_id",
    "Project": "project_id",
    "Funder": "funder_id",
    "Enterprise": "enterprise_id",
    "ResearchField": "field_id",
    "Industry": "industry_id",
    "OutputAsset": "asset_id",
    "MethodTechnique": "name",  # MethodTechnique uses name as identifier
}


def _entity_key(label: str, id_val: str) -> str:
    """Unified key for an entity: Label::id_value."""
    return f"{label}::{id_val}"


class KG:
    """
    Knowledge graph: triples (h, r, t), entity2id, relation2id, embeddings.
    """

    def __init__(self, data_dir: str = "pgpr_data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.entity2id: Dict[str, int] = {}
        self.id2entity: Dict[int, str] = {}
        self.relation2id: Dict[str, int] = {}
        self.id2relation: Dict[int, str] = {}
        self.triples: List[Tuple[int, int, int]] = []  # (h, r, t)
        self._triples_set: Optional[set] = None  # (h,r,t) for fast lookup
        self.entity_emb = None  # numpy or torch; set by train_transe or load
        self.relation_emb = None

    def export_from_neo4j(self, driver=None) -> None:
        """Export all (head, relation, tail) triples from Neo4j and build vocabs."""
        if driver is None:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

        # Cypher: get all edges with start/end labels and ids
        # We need to get id property per label; Cypher doesn't have a generic "id" so we collect per label
        query = """
        MATCH (a)-[r]->(b)
        WITH labels(a)[0] AS label_a, a, type(r) AS rel_type, labels(b)[0] AS label_b, b
        RETURN label_a, a, rel_type, label_b, b
        """
        with driver.session() as session:
            result = session.run(query)
            records = list(result)  # Consume result while session is still open

        entity2id = {}
        relation2id = {}
        triples_raw: List[Tuple[str, str, str]] = []

        for record in records:
            label_a = record["label_a"]
            label_b = record["label_b"]
            rel_type = record["rel_type"]
            a_node = record["a"]
            b_node = record["b"]

            id_prop_a = LABEL_TO_ID_PROP.get(label_a)
            id_prop_b = LABEL_TO_ID_PROP.get(label_b)
            if not id_prop_a or not id_prop_b:
                continue
            id_a = a_node.get(id_prop_a)
            id_b = b_node.get(id_prop_b)
            if id_a is None or id_b is None:
                continue

            key_a = _entity_key(label_a, str(id_a))
            key_b = _entity_key(label_b, str(id_b))
            entity2id[key_a] = entity2id.get(key_a, len(entity2id))
            entity2id[key_b] = entity2id.get(key_b, len(entity2id))
            relation2id[rel_type] = relation2id.get(rel_type, len(relation2id))
            triples_raw.append((key_a, rel_type, key_b))

        # Add reverse relations for undirected walk (optional; PGPR often uses directed)
        self.entity2id = entity2id
        self.relation2id = relation2id
        self.id2entity = {v: k for k, v in entity2id.items()}
        self.id2relation = {v: k for k, v in relation2id.items()}
        self.triples = [
            (entity2id[h], relation2id[r], entity2id[t])
            for h, r, t in triples_raw
        ]
        self._triples_set = set(self.triples)
        logger.info(
            "Exported KG: %d entities, %d relations, %d triples",
            len(self.entity2id),
            len(self.relation2id),
            len(self.triples),
        )

    def get_entity_id(self, label: str, id_val: str) -> int:
        """Return integer id for entity Label::id_val. Add if missing (e.g. at inference)."""
        key = _entity_key(label, str(id_val))
        if key not in self.entity2id:
            self.entity2id[key] = len(self.entity2id)
            self.id2entity[self.entity2id[key]] = key
        return self.entity2id[key]

    def get_relation_id(self, relation_type: str) -> int:
        if relation_type not in self.relation2id:
            self.relation2id[relation_type] = len(self.relation2id)
            self.id2relation[self.relation2id[relation_type]] = relation_type
        return self.relation2id[relation_type]

    def entity_key_to_id(self, key: str) -> Optional[int]:
        return self.entity2id.get(key)

    def save_vocab(self) -> None:
        path = os.path.join(self.data_dir, "vocab.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "entity2id": self.entity2id,
                    "relation2id": self.relation2id,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        logger.info("Saved vocab to %s", path)

    def load_vocab(self) -> None:
        path = os.path.join(self.data_dir, "vocab.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Vocab not found: {path}. Run export_from_neo4j first.")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.entity2id = {k: int(v) for k, v in data["entity2id"].items()}
        self.relation2id = {k: int(v) for k, v in data["relation2id"].items()}
        self.id2entity = {v: k for k, v in self.entity2id.items()}
        self.id2relation = {v: k for k, v in self.relation2id.items()}
        logger.info("Loaded vocab: %d entities, %d relations", len(self.entity2id), len(self.relation2id))

    def save_triples(self) -> None:
        path = os.path.join(self.data_dir, "triples.txt")
        with open(path, "w", encoding="utf-8") as f:
            for h, r, t in self.triples:
                f.write(f"{h}\t{r}\t{t}\n")
        logger.info("Saved %d triples to %s", len(self.triples), path)

    def load_triples(self) -> None:
        path = os.path.join(self.data_dir, "triples.txt")
        if not os.path.exists(path):
            return
        self.triples = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) == 3:
                    self.triples.append((int(parts[0]), int(parts[1]), int(parts[2])))
        self._triples_set = set(self.triples)
        logger.info("Loaded %d triples", len(self.triples))

    def train_transe(self, dim: int = 64, n_epoch: int = 100, lr: float = 0.01, margin: float = 1.0) -> None:
        """Simple TransE-style training: minimize ||h + r - t||. Uses numpy for no-torch dependency in KG."""
        import numpy as np

        n_ent = len(self.entity2id)
        n_rel = len(self.relation2id)
        np.random.seed(42)
        entity_emb = np.random.uniform(-0.1, 0.1, (n_ent, dim)).astype(np.float32)
        relation_emb = np.random.uniform(-0.1, 0.1, (n_rel, dim)).astype(np.float32)

        for epoch in range(n_epoch):
            loss_sum = 0.0
            for h, r, t in self.triples:
                pos_score = np.linalg.norm(entity_emb[h] + relation_emb[r] - entity_emb[t])
                # Negative sample: random entity
                t_neg = np.random.randint(0, n_ent)
                neg_score = np.linalg.norm(entity_emb[h] + relation_emb[r] - entity_emb[t_neg])
                loss = max(0, margin + pos_score - neg_score)
                if loss > 0:
                    grad_pos = (entity_emb[h] + relation_emb[r] - entity_emb[t])
                    grad_neg = (entity_emb[h] + relation_emb[r] - entity_emb[t_neg])
                    n_pos = np.linalg.norm(grad_pos) + 1e-8
                    n_neg = np.linalg.norm(grad_neg) + 1e-8
                    entity_emb[h] -= lr * grad_pos / n_pos
                    relation_emb[r] -= lr * grad_pos / n_pos
                    entity_emb[t] += lr * grad_pos / n_pos
                    entity_emb[t_neg] -= lr * grad_neg / n_neg
                    relation_emb[r] += lr * grad_neg / n_neg
                    entity_emb[h] += lr * grad_neg / n_neg
                loss_sum += loss
            if (epoch + 1) % 20 == 0:
                logger.info("TransE epoch %d loss %.4f", epoch + 1, loss_sum / max(len(self.triples), 1))

        self.entity_emb = entity_emb
        self.relation_emb = relation_emb
        self._save_embeddings()

    def _save_embeddings(self) -> None:
        import numpy as np
        path_e = os.path.join(self.data_dir, "entity_emb.npy")
        path_r = os.path.join(self.data_dir, "relation_emb.npy")
        np.save(path_e, self.entity_emb)
        np.save(path_r, self.relation_emb)
        logger.info("Saved embeddings to %s, %s", path_e, path_r)

    def load_embeddings(self) -> None:
        import numpy as np
        path_e = os.path.join(self.data_dir, "entity_emb.npy")
        path_r = os.path.join(self.data_dir, "relation_emb.npy")
        if not os.path.exists(path_e) or not os.path.exists(path_r):
            raise FileNotFoundError("Embeddings not found. Run train_transe first.")
        self.entity_emb = np.load(path_e)
        self.relation_emb = np.load(path_r)
        logger.info("Loaded embeddings: entity %s, relation %s", self.entity_emb.shape, self.relation_emb.shape)


def build_kg_from_neo4j(data_dir: str = "pgpr_data", train_emb: bool = True, emb_dim: int = 64) -> KG:
    """One-shot: export KG from Neo4j, save vocab and triples, optionally train TransE."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    kg = KG(data_dir=data_dir)
    kg.export_from_neo4j(driver)
    kg.save_vocab()
    kg.save_triples()
    driver.close()
    if train_emb:
        kg.train_transe(dim=emb_dim, n_epoch=100, lr=0.01, margin=1.0)
    return kg
