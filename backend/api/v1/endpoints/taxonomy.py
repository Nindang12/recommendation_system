from __future__ import annotations

from fastapi import APIRouter

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
