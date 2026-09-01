"""Shared expert identity helpers for seed, Neo4j sync, and merge scripts."""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set


def normalize_author_name(value: Any) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("‐", "-").replace("‑", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().lower()
    return re.sub(r"\s+", " ", text)


def expert_display_name(doc: Dict[str, Any]) -> str:
    basic = doc.get("basic_info") or {}
    return str(basic.get("name") or doc.get("name") or "").strip()


def expert_orcid(doc: Dict[str, Any]) -> str:
    identifiers = doc.get("identifiers") or {}
    return str(identifiers.get("ORCID") or "").strip()


def is_oa_prefixed(expert_id: str) -> bool:
    return str(expert_id or "").startswith("OA_")


def looks_like_scholar_id(expert_id: str) -> bool:
    eid = str(expert_id or "")
    return bool(eid) and not is_oa_prefixed(eid) and "AAAAJ" in eid


def choose_canonical_expert_id(
    expert_ids: Iterable[str],
    *,
    develops_counts: Optional[Dict[str, int]] = None,
    in_vocab: Optional[Set[str]] = None,
) -> str:
    """Pick the canonical expert_id for a duplicate name group."""
    ids = sorted({str(x) for x in expert_ids if x})
    if not ids:
        raise ValueError("empty expert id group")
    if len(ids) == 1:
        return ids[0]

    develops_counts = develops_counts or {}
    in_vocab = in_vocab or set()

    def score(eid: str) -> tuple:
        return (
            1 if eid in in_vocab else 0,
            1 if looks_like_scholar_id(eid) else 0,
            0 if is_oa_prefixed(eid) else 1,
            develops_counts.get(eid, 0),
            eid,
        )

    return max(ids, key=score)


def build_expert_name_index(experts: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
    index: Dict[str, List[str]] = defaultdict(list)
    for doc in experts:
        expert_id = str(doc.get("expert_id") or "").strip()
        if not expert_id:
            continue
        name_key = normalize_author_name(expert_display_name(doc))
        if name_key and expert_id not in index[name_key]:
            index[name_key].append(expert_id)
        for alias in doc.get("expert_alias_ids") or []:
            alias_id = str(alias).strip()
            if alias_id and alias_id not in index[name_key]:
                index[name_key].append(alias_id)
    return dict(index)


def build_orcid_index(experts: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
    index: Dict[str, List[str]] = defaultdict(list)
    for doc in experts:
        expert_id = str(doc.get("expert_id") or "").strip()
        orcid = expert_orcid(doc)
        if expert_id and orcid:
            if expert_id not in index[orcid]:
                index[orcid].append(expert_id)
    return dict(index)


def resolve_author_names_to_expert_ids(
    authors: Iterable[Any],
    *,
    name_index: Dict[str, List[str]],
    seed_ids: Optional[Iterable[str]] = None,
) -> List[str]:
    resolved: List[str] = []
    seen: Set[str] = set()
    for raw in seed_ids or []:
        eid = str(raw or "").strip()
        if eid and eid not in seen:
            seen.add(eid)
            resolved.append(eid)
    for author in authors or []:
        key = normalize_author_name(author)
        if not key:
            continue
        for eid in name_index.get(key, []):
            if eid not in seen:
                seen.add(eid)
                resolved.append(eid)
    return resolved


def paper_authors_from_product(product: Dict[str, Any]) -> List[str]:
    metadata = product.get("metadata") or {}
    authors = metadata.get("authors") or []
    if isinstance(authors, str):
        authors = re.split(r"[;,]", authors)
    if not isinstance(authors, list):
        return []
    clean: List[str] = []
    for author in authors:
        name = str(author).strip()
        if name and name != "...":
            clean.append(name)
    return clean
