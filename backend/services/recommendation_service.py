import asyncio
from typing import Any, Dict, List, Optional

from core.cache import cache
from repositories.mongodb_repo import MongoDBRepository
from repositories.neo4j_repo import Neo4jRepository
from pgpr.pgpr_recommendation import PGPRRecommender
from pgpr.pgpr_xai_explainer import PGPRExplainer
import logging

logger = logging.getLogger(__name__)


ENTITY_LABEL_MAP = {
    "project": "Project",
    "expert": "Expert",
    "funder": "Funder",
    "enterprise": "Enterprise",
}


class RecommendationService:
    """
    Service Layer - orchestrates PGPR, XAI, cache and repositories.
    """

    def __init__(self, recommender: Optional[PGPRRecommender] = None, explainer: Optional[PGPRExplainer] = None) -> None:
        # In a later step you can inject PGPR/XAI implementations here
        self.mongo_repo = MongoDBRepository()
        self.neo4j_repo = Neo4jRepository()

        self.recommender = recommender
        self.explainer = explainer or PGPRExplainer(language="vi")

    async def get_expert_recommendations(
        self,
        project_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        High-level business workflow for expert recommendation.
        This is a skeleton that you can plug existing PGPR/XAI logic into.
        """
        cache_key = f"recommendations:experts:{project_id}:{limit}"

        # 1. Try cache first
        cached = await cache.get(cache_key)
        # IMPORTANT: do not treat an empty list as a cache hit, otherwise
        # one bad/timeout run can poison cache and always return [].
        if isinstance(cached, list) and len(cached) > 0:
            return cached

        # 2. Validate project existence / business rules
        # If MongoDB is not available yet or schema mismatch, allow a fallback so you can still test PGPR/Neo4j flow.
        try:
            project = await self.mongo_repo.get_project(project_id)
        except Exception as e:
            logger.warning(f"Mongo error: {e}")
            project = None

        if not project:
            project = {"project_id": project_id, "title": project_id}

        # You can add more project-level rules here (status, etc.)

        recommendations = await self.get_recommendations_by_policy(
            source_id=project_id,
            source_type="project",
            target_type="expert",
            limit=limit,
            language="vi",
        )
        return recommendations

    async def get_recommendations_by_policy(
        self,
        source_id: str,
        source_type: str,
        target_type: str,
        limit: int = 10,
        language: str = "vi",
    ) -> List[Dict[str, Any]]:
        source_label = self._to_policy_label(source_type)
        target_label = self._to_policy_label(target_type)
        cache_key = (
            f"recommendations:{target_label.lower()}_for_{source_label.lower()}:"
            f"{source_id}:{limit}:{language}"
        )

        cached = await cache.get(cache_key)
        if isinstance(cached, list) and len(cached) > 0:
            return cached

        # Build source context for explainer output.
        source_context = {
            "source_id": source_id,
            "source_type": source_label,
            "source_name": source_id,
        }
        if source_label == "Project":
            try:
                project = await self.mongo_repo.get_project(source_id)
            except Exception as e:
                logger.warning(f"Mongo error: {e}")
                project = None
            if project:
                source_context["source_name"] = project.get("title") or source_id

        recommendations: List[Dict[str, Any]] = await self._run_pgpr_dispatch(
            source_id=source_id,
            source_label=source_label,
            target_label=target_label,
            limit=limit,
        )

        # 4. Enrich with XAI explanations (plug existing XAI here)
        recommendations = await self._enrich_with_xai(
            source_context=source_context,
            target_type=target_label,
            recommendations=recommendations,
            language=language,
        )

        # 5. Normalize response shape for API schemas.
        recommendations = self._normalize_recommendations(
            recommendations=recommendations,
            target_label=target_label,
        )

        # 6. Enrich with extra profile/graph info (keep hook for later).
        recommendations = await self._enrich_with_profiles_and_graph(
            recommendations=recommendations,
        )

        # 7. Save to cache (avoid caching empty results)
        if recommendations:
            await cache.set(cache_key, recommendations)

        # 8. Return results
        return recommendations

    async def _run_pgpr_dispatch(
        self,
        source_id: str,
        source_label: str,
        target_label: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        method_name = (
            f"recommend_{target_label.lower()}s_for_{source_label.lower()}_pgpr"
        )

        def _run() -> List[Dict[str, Any]]:
            pgpr = self.recommender
            is_local = False
            if pgpr is None:
                logger.warning("PGPRRecommender chưa được inject. Đang khởi tạo mới (có thể gây chậm hệ thống)...")
                pgpr = PGPRRecommender(
                    max_path_length=5,
                    gamma=0.99,
                    top_k_paths=10,
                    enable_cache=True,
                )
                is_local = True

            try:
                method = getattr(pgpr, method_name, None)
                if method is None:
                    logger.warning("Unsupported policy pair: %s -> %s", source_label, target_label)
                    return []
                return method(source_id, limit=limit)
            except Exception as e:
                logger.error("Lỗi khi chạy PGPR: %s", e, exc_info=True)
                return []
            finally:
                if is_local:
                    try:
                        pgpr.close()
                    except Exception:
                        pass

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    _run,
                ),
                timeout=60,
            )
        except TimeoutError:
            logger.error("PGPR dispatch timeout")
            return []
        except Exception as e:
            logger.error("PGPR dispatch unhandled error: %s", e, exc_info=True)
            return []

    async def _enrich_with_xai(
        self,
        source_context: Dict[str, Any],
        target_type: str,
        recommendations: List[Dict[str, Any]],
        language: str = "vi",
    ) -> List[Dict[str, Any]]:
        # Phục vụ API chính: Luôn dùng Rule-based để đạt tốc độ phản hồi cực nhanh.
        rule_explainer = PGPRExplainer(language=language, use_llm=False)
        
        out: List[Dict[str, Any]] = []
        for rec in recommendations:
            explanation = rule_explainer.explain_recommendation(
                recommendation=rec,
                rec_type=target_type.lower(),
                source_context=source_context,
            )
            rec = dict(rec)
            if isinstance(explanation, dict) and "natural_language" in explanation:
                rec["explanation"] = {
                    "natural_language": explanation["natural_language"],
                    "visualization": explanation.get("visualization", ""),
                }
                # Backward compatibility for existing consumers.
                rec["xai_explanation"] = explanation["natural_language"]
            else:
                rec["xai_explanation"] = explanation
            out.append(rec)
        return out
        
    async def explain_single_recommendation(
        self,
        recommendation: Dict[str, Any],
        target_type: str,
        source_context: Optional[Dict[str, Any]] = None,
        language: str = "vi"
    ) -> Dict[str, Any]:
        """
        On-demand LLM explanation for a single recommendation.
        """
        import aiohttp
        
        llm_explainer = PGPRExplainer(
            language=language, 
            use_llm=True, 
            ollama_model=self.explainer.ollama_model
        )
        
        try:
            async with aiohttp.ClientSession() as session:
                explanation = await llm_explainer.async_explain_recommendation(
                    recommendation=recommendation,
                    session=session,
                    rec_type=target_type.lower(),
                    source_context=source_context,
                )
                return explanation
        except Exception as e:
            logger.error(f"Lỗi khi sinh XAI On-demand (aiohttp): {e}")
            # Fallback to rule-based if LLM fails
            rule_explainer = PGPRExplainer(language=language, use_llm=False)
            return rule_explainer.explain_recommendation(
                recommendation=recommendation,
                rec_type=target_type.lower(),
                source_context=source_context,
            )

    def _normalize_recommendations(
        self,
        recommendations: List[Dict[str, Any]],
        target_label: str,
    ) -> List[Dict[str, Any]]:
        id_key = f"{target_label.lower()}_id"
        out: List[Dict[str, Any]] = []
        for rec in recommendations:
            item = dict(rec)
            rec_id = (
                item.get("id")
                or item.get(id_key)
                or item.get("expert_id")
                or item.get("project_id")
                or item.get("funder_id")
                or item.get("enterprise_id")
            )
            rec_name = item.get("name") or item.get("title") or str(rec_id or "")
            if rec_id is None:
                continue
            item["id"] = str(rec_id)
            item["name"] = str(rec_name)
            item["metrics"] = item.get("metrics") or item.get("extra")
            out.append(item)
        return out

    async def _enrich_with_profiles_and_graph(
        self,
        recommendations: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Fetch additional expert data from MongoDB and graph metrics from Neo4j.
        """
        # TODO: use self.mongo_repo / self.neo4j_repo to enrich recommendations.
        return recommendations

    def _to_policy_label(self, entity_type: str) -> str:
        key = (entity_type or "").strip().lower()
        if key not in ENTITY_LABEL_MAP:
            raise ValueError(f"Unsupported entity type: {entity_type}")
        return ENTITY_LABEL_MAP[key]

