"""Shared skill identity helpers for seed, Neo4j sync, and registration."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple

ACRONYM_WORDS = {
    "ai": "AI",
    "api": "API",
    "aws": "AWS",
    "bi": "BI",
    "cd": "CD",
    "ci": "CI",
    "cnn": "CNN",
    "cpu": "CPU",
    "crm": "CRM",
    "css": "CSS",
    "cv": "CV",
    "dna": "DNA",
    "erp": "ERP",
    "etl": "ETL",
    "gpu": "GPU",
    "html": "HTML",
    "http": "HTTP",
    "iot": "IoT",
    "js": "JS",
    "json": "JSON",
    "ml": "ML",
    "nlp": "NLP",
    "ocr": "OCR",
    "orm": "ORM",
    "pdf": "PDF",
    "rnn": "RNN",
    "sql": "SQL",
    "ui": "UI",
    "ux": "UX",
    "xml": "XML",
}

SPECIAL_PHRASES = {
    "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "natural language processing": "Natural Language Processing",
    "computer vision": "Computer Vision",
    "data science": "Data Science",
    "data mining": "Data Mining",
    "neural network": "Neural Network",
    "neural networks": "Neural Networks",
    "reinforcement learning": "Reinforcement Learning",
    "graph neural network": "Graph Neural Network",
    "graph neural networks": "Graph Neural Networks",
    "knowledge graph": "Knowledge Graph",
    "large language model": "Large Language Model",
    "large language models": "Large Language Models",
}

BRAND_WORDS = {
    "github": "GitHub",
    "gitlab": "GitLab",
    "graphql": "GraphQL",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "mongodb": "MongoDB",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "reactjs": "React",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "scikitlearn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "powerbi": "Power BI",
    "power bi": "Power BI",
}


def normalize_skill_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("‐", "-").replace("‑", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().lower()
    return re.sub(r"\s+", " ", text)


def compact_skill_key(value: Any) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "", normalize_skill_key(value))


def skill_id_from_name(name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", str(name or "").strip()).strip("_")
    return f"SKILL_{base.upper()}" if base else "SKILL_UNKNOWN"


def canonical_skill_display(raw_name: str) -> str:
    raw = str(raw_name or "").strip()
    if not raw:
        return ""
    key = normalize_skill_key(raw)
    if key in SPECIAL_PHRASES:
        return SPECIAL_PHRASES[key]
    if key in BRAND_WORDS:
        return BRAND_WORDS[key]
    parts = []
    for word in key.split():
        lower_word = word.lower()
        if lower_word in BRAND_WORDS:
            parts.append(BRAND_WORDS[lower_word])
        elif lower_word in ACRONYM_WORDS:
            parts.append(ACRONYM_WORDS[lower_word])
        else:
            parts.append(word.capitalize())
    return BRAND_WORDS.get(key, " ".join(parts))


def build_skill_taxonomy_maps(
    methods: Iterable[Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], Dict[str, str]]:
    skill_map: Dict[str, Dict[str, Any]] = {}
    by_compact: Dict[str, str] = {}
    by_norm_key: Dict[str, str] = {}
    for method in methods:
        skill_id = method.get("tech_id") or method.get("skill_id")
        name = method.get("name")
        if not skill_id or not name:
            continue
        record = {
            "skill_id": skill_id,
            "name": name,
            "category": method.get("category"),
            "ontology_ref": method.get("standard_ref"),
        }
        skill_map[skill_id] = record
        by_compact[compact_skill_key(name)] = skill_id
        by_norm_key[normalize_skill_key(name)] = skill_id
    return skill_map, by_compact, by_norm_key


def resolve_skill_record(
    raw_name: Any,
    *,
    skill_map: Optional[Dict[str, Dict[str, Any]]] = None,
    by_compact: Optional[Dict[str, str]] = None,
    by_norm_key: Optional[Dict[str, str]] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    raw = str(raw_name or "").strip()
    if not raw:
        return {"skill_id": None, "name": None, "category": category, "ontology_ref": None}

    skill_map = skill_map or {}
    by_compact = by_compact or {}
    by_norm_key = by_norm_key or {}

    norm = normalize_skill_key(raw)
    compact = compact_skill_key(raw)
    skill_id = by_norm_key.get(norm) or by_compact.get(compact)
    if skill_id and skill_id in skill_map:
        record = skill_map[skill_id]
        return {
            "skill_id": record["skill_id"],
            "name": record["name"],
            "category": record.get("category") or category or "unknown",
            "ontology_ref": record.get("ontology_ref"),
        }

    if compact and by_compact:
        for compact_key, matched_id in by_compact.items():
            if compact in compact_key or compact_key in compact:
                record = skill_map[matched_id]
                return {
                    "skill_id": record["skill_id"],
                    "name": record["name"],
                    "category": record.get("category") or category or "unknown",
                    "ontology_ref": record.get("ontology_ref"),
                }

    canonical_name = canonical_skill_display(raw)
    return {
        "skill_id": skill_id_from_name(canonical_name),
        "name": canonical_name,
        "category": category or "unknown",
        "ontology_ref": None,
    }


def normalize_skill_dict(
    skill_obj: Dict[str, Any],
    *,
    skill_map: Optional[Dict[str, Dict[str, Any]]] = None,
    by_compact: Optional[Dict[str, str]] = None,
    by_norm_key: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    if not isinstance(skill_obj, dict):
        return None
    name = skill_obj.get("name") or skill_obj.get("skill") or skill_obj.get("technology")
    if not name:
        return None
    resolved = resolve_skill_record(
        name,
        skill_map=skill_map,
        by_compact=by_compact,
        by_norm_key=by_norm_key,
        category=skill_obj.get("category"),
    )
    normalized = {
        "skill_id": resolved["skill_id"],
        "name": resolved["name"],
        "category": resolved.get("category") or skill_obj.get("category") or "unknown",
    }
    level = skill_obj.get("proficiency_level") or skill_obj.get("level")
    if level:
        normalized["proficiency_level"] = level
    return normalized


def dedupe_skill_names(names: Iterable[Any], **resolve_kwargs: Any) -> List[str]:
    seen: set[str] = set()
    output: List[str] = []
    for raw in names:
        if isinstance(raw, dict):
            record = normalize_skill_dict(raw, **resolve_kwargs)
            name = record.get("name") if record else None
        else:
            resolved = resolve_skill_record(str(raw), **resolve_kwargs)
            name = resolved.get("name")
        if not name:
            continue
        key = normalize_skill_key(name)
        if key in seen:
            continue
        seen.add(key)
        output.append(name)
    return output
