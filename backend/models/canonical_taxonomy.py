from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from models.research_taxonomy import RESEARCH_TOPIC_LABEL_MAP, research_topic_direction


@dataclass(frozen=True)
class CanonicalTerm:
    id: str
    label: str
    category: str
    direction: Optional[str] = None


CANONICAL_TOPICS: Dict[str, CanonicalTerm] = {
    topic_id: CanonicalTerm(
        id=topic_id,
        label=label,
        category="topic",
        direction=research_topic_direction(topic_id),
    )
    for topic_id, label in RESEARCH_TOPIC_LABEL_MAP.items()
}

CANONICAL_SKILLS: Dict[str, CanonicalTerm] = {
    "python": CanonicalTerm("python", "Python", "skill"),
    "pytorch": CanonicalTerm("pytorch", "PyTorch", "skill"),
    "tensorflow": CanonicalTerm("tensorflow", "TensorFlow", "skill"),
    "scikit-learn": CanonicalTerm("scikit-learn", "Scikit-learn", "skill"),
    "machine-learning": CanonicalTerm("machine-learning", "Machine Learning", "skill"),
    "deep-learning": CanonicalTerm("deep-learning", "Deep Learning", "skill"),
    "computer-vision": CanonicalTerm("computer-vision", "Computer Vision", "skill"),
    "nlp": CanonicalTerm("nlp", "Natural Language Processing", "skill"),
    "knowledge-graph": CanonicalTerm("knowledge-graph", "Knowledge Graph", "skill"),
    "graph-neural-networks": CanonicalTerm("graph-neural-networks", "Graph Neural Networks", "skill"),
    "fastapi": CanonicalTerm("fastapi", "FastAPI", "skill"),
    "react": CanonicalTerm("react", "React", "skill"),
    "neo4j": CanonicalTerm("neo4j", "Neo4j", "skill"),
}

CANONICAL_INDUSTRIES: Dict[str, CanonicalTerm] = {
    "healthcare": CanonicalTerm("healthcare", "Healthcare", "industry"),
    "education": CanonicalTerm("education", "Education Technology", "industry"),
    "finance": CanonicalTerm("finance", "Finance", "industry"),
    "manufacturing": CanonicalTerm("manufacturing", "Manufacturing", "industry"),
    "energy": CanonicalTerm("energy", "Energy", "industry"),
    "agriculture": CanonicalTerm("agriculture", "Agriculture", "industry"),
    "transportation": CanonicalTerm("transportation", "Transportation", "industry"),
    "environment": CanonicalTerm("environment", "Environment", "industry"),
    "ict": CanonicalTerm("ict", "Information and Communication Technology", "industry"),
}


TOPIC_ALIASES = {
    "ai y te": "ai-healthcare",
    "ai trong y te": "ai-healthcare",
    "artificial intelligence in healthcare": "ai-healthcare",
    "health ai": "ai-healthcare",
    "medical ai": "ai-healthcare",
    "ml": "machine-learning",
    "machine learning": "machine-learning",
    "hoc may": "machine-learning",
    "deep learning": "deep-learning",
    "deeplearning": "deep-learning",
    "dl": "deep-learning",
    "computer vision": "computer-vision",
    "thi giac may": "computer-vision",
    "knowledge graph": "knowledge-graph",
    "kg": "knowledge-graph",
    "graph neural network": "graph-neural-networks",
    "graph neural networks": "graph-neural-networks",
    "gnn": "graph-neural-networks",
    "large language model": "large-language-models",
    "large language models": "large-language-models",
    "llm": "large-language-models",
    "llms": "large-language-models",
    "iot": "iot",
    "internet of things": "iot",
}

SKILL_ALIASES = {
    "python": "python",
    "pytorch": "pytorch",
    "torch": "pytorch",
    "tensorflow": "tensorflow",
    "tf": "tensorflow",
    "sklearn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "scikit-learn": "scikit-learn",
    "machine learning": "machine-learning",
    "ml": "machine-learning",
    "deep learning": "deep-learning",
    "computer vision": "computer-vision",
    "cv": "computer-vision",
    "nlp": "nlp",
    "natural language processing": "nlp",
    "knowledge graph": "knowledge-graph",
    "neo4j": "neo4j",
    "fastapi": "fastapi",
    "react": "react",
}

INDUSTRY_ALIASES = {
    "healthcare": "healthcare",
    "health care": "healthcare",
    "medical": "healthcare",
    "y te": "healthcare",
    "education": "education",
    "edtech": "education",
    "education technology": "education",
    "finance": "finance",
    "fintech": "finance",
    "manufacturing": "manufacturing",
    "smart manufacturing": "manufacturing",
    "energy": "energy",
    "renewable energy": "energy",
    "agriculture": "agriculture",
    "transport": "transportation",
    "transportation": "transportation",
    "environment": "environment",
    "ict": "ict",
    "information technology": "ict",
}


def normalize_text(value: object) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[_/|]+", " ", text)
    text = re.sub(r"[^a-z0-9.+# -]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def canonicalize_topic(value: object) -> Optional[CanonicalTerm]:
    key = normalize_text(value)
    if not key:
        return None
    direct = str(value or "").strip()
    topic_id = direct if direct in CANONICAL_TOPICS else TOPIC_ALIASES.get(key)
    if not topic_id and key.replace(" ", "-") in CANONICAL_TOPICS:
        topic_id = key.replace(" ", "-")
    return CANONICAL_TOPICS.get(topic_id or "")


def canonicalize_skill(value: object) -> Optional[CanonicalTerm]:
    key = normalize_text(value)
    if not key:
        return None
    skill_id = str(value or "").strip() if str(value or "").strip() in CANONICAL_SKILLS else SKILL_ALIASES.get(key)
    if not skill_id and key.replace(" ", "-") in CANONICAL_SKILLS:
        skill_id = key.replace(" ", "-")
    return CANONICAL_SKILLS.get(skill_id or "")


def canonicalize_industry(value: object) -> Optional[CanonicalTerm]:
    key = normalize_text(value)
    if not key:
        return None
    industry_id = (
        str(value or "").strip()
        if str(value or "").strip() in CANONICAL_INDUSTRIES
        else INDUSTRY_ALIASES.get(key)
    )
    if not industry_id and key.replace(" ", "-") in CANONICAL_INDUSTRIES:
        industry_id = key.replace(" ", "-")
    return CANONICAL_INDUSTRIES.get(industry_id or "")


def unmapped_values(values: Iterable[object], category: str) -> List[str]:
    mapper = {
        "topic": canonicalize_topic,
        "skill": canonicalize_skill,
        "industry": canonicalize_industry,
    }[category]
    out: List[str] = []
    for value in values:
        if value in (None, "", [], {}):
            continue
        if mapper(value) is None:
            normalized = normalize_text(value)
            if normalized and normalized not in out:
                out.append(normalized)
    return out
