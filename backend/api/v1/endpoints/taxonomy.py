from __future__ import annotations

from fastapi import APIRouter

from models.canonical_taxonomy import CANONICAL_INDUSTRIES, CANONICAL_SKILLS, CANONICAL_TOPICS
from models.research_taxonomy import RESEARCH_DIRECTIONS, RESEARCH_TOPICS

router = APIRouter()


@router.get("/research-topics")
def list_research_topics():
    return {
        "status": "success",
        "data": {
            "directions": RESEARCH_DIRECTIONS,
            "topics": RESEARCH_TOPICS,
        },
        "count": len(RESEARCH_TOPICS),
    }


@router.get("/canonical")
def list_canonical_taxonomy():
    def dump(items):
        return [
            {
                "id": item.id,
                "label": item.label,
                "category": item.category,
                "direction": item.direction,
            }
            for item in sorted(items.values(), key=lambda row: row.label.lower())
        ]

    return {
        "status": "success",
        "data": {
            "topics": dump(CANONICAL_TOPICS),
            "skills": dump(CANONICAL_SKILLS),
            "industries": dump(CANONICAL_INDUSTRIES),
        },
    }
