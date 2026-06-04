import asyncio
import re
from typing import Any, Dict, List, Optional

from core.cache import cache
from repositories.mongodb_repo import MongoDBRepository
from repositories.neo4j_repo import Neo4jRepository
from pgpr.pgpr_recommendation import PGPRRecommender
from pgpr.pgpr_xai_explainer import PGPRExplainer
from services.candidate_mask_service import CandidateMaskService
from services.hybrid_recommendation_service import HybridRecommendationService
from services import provisional_status as st
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
        self.candidate_mask = CandidateMaskService()
        self.hybrid = HybridRecommendationService()

    async def get_expert_recommendations(
        self,
        project_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        High-level business workflow for expert recommendation.
        This is a skeleton that you can plug existing PGPR/XAI logic into.
        """
        cache_key = f"recommendations:v2:experts:{project_id}:{limit}"

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
        mode: str = "public",
        current_user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        source_label = self._to_policy_label(source_type)
        target_label = self._to_policy_label(target_type)
        cache_key = (
            f"recommendations:v8:structured-xai:{target_label.lower()}_for_{source_label.lower()}:"
            f"{source_id}:{limit}:{language}:{mode}:{current_user_id or ''}"
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
                source_context["source_name"] = (
                    project.get("title")
                    or (project.get("basic_info") or {}).get("title")
                    or project.get("name")
                    or source_id
                )

        pgpr_pool_limit = max(limit * 3, 30)
        pgpr_candidates: List[Dict[str, Any]] = await self._run_pgpr_dispatch(
            source_id=source_id,
            source_label=source_label,
            target_label=target_label,
            limit=pgpr_pool_limit,
        )

        src_reco_ctx = self.hybrid.source_recommendation_context(source_type, source_id)
        recommendations, _ = await self.hybrid.build_hybrid_candidates(
            pgpr_candidates,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            limit=max(limit * 3, 30),
            mode=mode,
            current_user_id=current_user_id,
            source_context=src_reco_ctx,
        )

        recommendations = self._apply_provisional_rules(
            recommendations=recommendations,
            source_id=source_id,
            source_label=source_label,
            target_label=target_label,
            mode=mode,
            current_user_id=current_user_id,
        )
        recommendations = await self._exclude_existing_relationships(
            recommendations,
            source_id=source_id,
            source_type=source_type,
            target_type=target_type,
        )
        recommendations = recommendations[:limit]

        # 4. Enrich with XAI explanations (plug existing XAI here)
        recommendations = await self._enrich_with_xai(
            source_context={**source_context, **src_reco_ctx},
            target_type=target_label,
            recommendations=recommendations,
            language=language,
        )

        # 5. Normalize response shape for API schemas.
        recommendations = self._normalize_recommendations(
            recommendations=recommendations,
            target_label=target_label,
        )
        recommendations = self._apply_scoring_metadata(recommendations, source_context=src_reco_ctx)
        recommendations = self._sync_display_scores(recommendations)

        # 6. Enrich with extra profile/graph info (keep hook for later).
        recommendations = await self._enrich_with_profiles_and_graph(
            recommendations=recommendations,
        )

        method_counts: Dict[str, int] = {}
        for rec in recommendations:
            method = str(rec.get("scoring_method") or "unknown")
            method_counts[method] = method_counts.get(method, 0) + 1
        logger.info(
            "Recommendation %s -> %s mode=%s count=%d methods=%s",
            source_label,
            target_label,
            mode,
            len(recommendations),
            method_counts,
        )

        # 7. Save to cache (avoid caching empty results)
        if recommendations:
            await cache.set(cache_key, recommendations)

        # 8. Return results
        return recommendations

    async def _exclude_existing_relationships(
        self,
        recommendations: List[Dict[str, Any]],
        *,
        source_id: str,
        source_type: str,
        target_type: str,
    ) -> List[Dict[str, Any]]:
        """Keep recommendation results focused on new collaboration opportunities."""
        source_type = source_type.strip().lower()
        target_type = target_type.strip().lower()
        try:
            source = await self.mongo_repo.get_entity(source_type, source_id)
        except Exception as exc:
            logger.warning(
                "Could not load source relation context for %s/%s: %s",
                source_type,
                source_id,
                exc,
            )
            return recommendations

        raw = (source or {}).get("raw") if isinstance(source, dict) else None
        if not isinstance(raw, dict):
            return recommendations

        relation_paths = {
            ("project", "expert"): [
                ("relations.participants", "expert_id"),
            ],
            ("project", "enterprise"): [
                ("relations.enterprise_partners", "enterprise_id"),
            ],
            ("project", "funder"): [
                ("relations.funders", "funder_id"),
            ],
            ("project", "project"): [
                ("relations.related_projects", "project_id"),
            ],
            ("expert", "project"): [
                ("activities_and_outputs.projects_participation", "project_id"),
                ("activities_and_outputs.grant_history", "linked_project_id"),
            ],
            ("expert", "expert"): [
                ("activities_and_outputs.collaborators", "expert_id"),
            ],
            ("enterprise", "project"): [
                ("relations.rd_projects", "project_id"),
            ],
            ("enterprise", "expert"): [
                ("relations.worked_experts", "expert_id"),
            ],
            ("funder", "project"): [
                ("funding_history.funded_projects", "project_id"),
            ],
        }
        existing_ids: set[str] = set()
        if source_type == target_type:
            existing_ids.add(str(source_id))
        for path, id_field in relation_paths.get((source_type, target_type), []):
            existing_ids.update(self._relation_ids(raw, path, id_field))

        if not existing_ids:
            return recommendations

        filtered: List[Dict[str, Any]] = []
        removed: List[str] = []
        for item in recommendations:
            candidate_id = str(
                item.get("id")
                or item.get(f"{target_type}_id")
                or item.get("expert_id")
                or item.get("project_id")
                or item.get("funder_id")
                or item.get("enterprise_id")
                or ""
            )
            if candidate_id and candidate_id in existing_ids:
                removed.append(candidate_id)
                continue
            filtered.append(item)

        if removed:
            logger.info(
                "Excluded existing relationships from %s/%s -> %s: %s",
                source_type,
                source_id,
                target_type,
                sorted(set(removed)),
            )
        return filtered

    @staticmethod
    def _relation_ids(raw: Dict[str, Any], path: str, id_field: str) -> set[str]:
        value: Any = raw
        for part in path.split("."):
            if not isinstance(value, dict):
                return set()
            value = value.get(part)

        values = value if isinstance(value, list) else [value]
        ids: set[str] = set()
        for item in values:
            if isinstance(item, dict):
                relation_id = item.get(id_field)
            elif id_field in {"project_id", "expert_id", "enterprise_id", "funder_id"}:
                relation_id = item
            else:
                relation_id = None
            if relation_id not in (None, ""):
                ids.add(str(relation_id))
        return ids

    async def get_project_overview(
        self,
        project_id: str,
        limit: int = 3,
        language: str = "vi",
    ) -> Dict[str, Any]:
        """
        Build dashboard-friendly recommendations for one project.
        Partial failures are captured per group so the UI can still render.
        """
        limit = max(1, min(limit, 10))
        source = {
            "id": project_id,
            "type": "project",
            "name": project_id,
        }
        try:
            project = await self.mongo_repo.get_project(project_id)
        except Exception as exc:
            logger.warning("Mongo error while loading project overview source: %s", exc)
            project = None
        if project:
            source["name"] = project.get("title") or project.get("name") or project_id
            embedding = self._embedding_metadata(project)
            if embedding:
                source["metadata"] = {
                    "embedding": embedding,
                    "embedding_status": embedding.get("status"),
                }

        async def _recommend_group(target_type: str) -> Any:
            try:
                return await self.get_recommendations_by_policy(
                    source_id=project_id,
                    source_type="project",
                    target_type=target_type,
                    limit=limit,
                    language=language,
                    mode="public",
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Project overview group failed: %s", target_type)
                return {
                    "error": str(exc),
                    "data": [],
                }

        experts, funders, enterprises, similar_projects = await asyncio.gather(
            _recommend_group("expert"),
            _recommend_group("funder"),
            _recommend_group("enterprise"),
            _recommend_group("project"),
        )

        return {
            "status": "success",
            "source": source,
            "data": {
                "experts": self._group_data(experts),
                "funders": self._group_data(funders),
                "enterprises": self._group_data(enterprises),
                "similar_projects": self._group_data(similar_projects),
            },
            "errors": {
                "experts": self._group_error(experts),
                "funders": self._group_error(funders),
                "enterprises": self._group_error(enterprises),
                "similar_projects": self._group_error(similar_projects),
            },
        }

    def _embedding_metadata(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        embedding = entity.get("embedding")
        if not isinstance(embedding, dict):
            status = entity.get("embedding_status")
            return {"status": status} if status else {}
        return {
            "status": embedding.get("status"),
            "model": embedding.get("model"),
            "version": embedding.get("version"),
            "dimension": embedding.get("dimension"),
            "normalized": embedding.get("normalized"),
            "signal": embedding.get("signal"),
            "updated_at": embedding.get("updated_at"),
            "last_queued_at": embedding.get("last_queued_at"),
            "last_processed_at": embedding.get("last_processed_at"),
            "error": embedding.get("error"),
            "error_type": embedding.get("error_type"),
        }

    async def evaluate_target_entity(
        self,
        source_id: str,
        source_type: str,
        target_id: str,
        target_type: str,
        language: str = "vi",
        mode: str = "public",
        current_user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        source_label = self._to_policy_label(source_type)
        target_label = self._to_policy_label(target_type)

        ranked_candidates = await self.get_recommendations_by_policy(
            source_id=source_id,
            source_type=source_type,
            target_type=target_type,
            limit=100,
            language=language,
            mode=mode,
            current_user_id=current_user_id,
        )
        for rank, candidate in enumerate(ranked_candidates, start=1):
            if str(candidate.get("id")) == str(target_id):
                item = dict(candidate)
                item["requested_target_id"] = target_id
                item["matched_requested_entity"] = True
                item["matched_rank"] = rank
                return [item]

        relation_check = await self._exclude_existing_relationships(
            [{"id": target_id}],
            source_id=source_id,
            source_type=source_type,
            target_type=target_type,
        )
        if not relation_check:
            logger.info(
                "Skipped direct recommendation for existing relationship %s/%s -> %s/%s",
                source_type,
                source_id,
                target_type,
                target_id,
            )
            return []

        try:
            target_entity = await self.mongo_repo.get_entity(target_type, target_id)
        except Exception as exc:
            logger.warning("Mongo error while loading target entity %s/%s: %s", target_type, target_id, exc)
            target_entity = None

        target_name = (
            (target_entity or {}).get("name")
            or (target_entity or {}).get("title")
            or (target_entity or {}).get("summary")
            or target_id
        )

        graph_repo = getattr(self.recommender, "graph_repo", None)
        paths: List[Dict[str, Any]] = []
        if graph_repo is not None and hasattr(self.recommender, "find_reasoning_paths_cypher"):
            try:
                paths = self.recommender.find_reasoning_paths_cypher(
                    source_id=source_id,
                    source_type=source_label,
                    target_id=target_id,
                    target_type=target_label,
                    limit=5,
                    mode=mode,
                    current_user_id=current_user_id,
                )
            except Exception as exc:
                logger.warning(
                    "Could not evaluate target entity path %s/%s -> %s/%s: %s",
                    source_type,
                    source_id,
                    target_type,
                    target_id,
                    exc,
                )

        top_path_score = 0.0
        if paths:
            top_path_score = max(float(path.get("score", 0.0) or 0.0) for path in paths)

        item: Dict[str, Any] = {
            "id": target_id,
            "name": str(target_name),
            "type": target_type,
            "score": round(min(max(top_path_score, 0.0), 0.65), 6),
            "reasoning_paths": paths,
            "path_diversity": len(paths),
            "scoring_method": "target_path_analysis",
            "requested_target_id": target_id,
            "matched_requested_entity": False,
        }
        if not paths:
            item["fallback_reason"] = (
                "Khong tim thay reasoning path truc tiep giua source va target trong KG hien tai. "
                "Entity nay khong nam trong top recommendation theo target type."
            )

        evaluated = self._apply_provisional_rules(
            recommendations=[item],
            source_id=source_id,
            source_label=source_label,
            target_label=target_label,
            mode=mode,
            current_user_id=current_user_id,
        )
        src_reco_ctx = self.hybrid.source_recommendation_context(source_type, source_id)
        evaluated = await self._enrich_with_xai(
            source_context={
                "source_id": source_id,
                "source_type": source_label,
                "source_name": source_id,
                **src_reco_ctx,
            },
            target_type=target_label,
            recommendations=evaluated,
            language=language,
        )
        evaluated = self._normalize_recommendations(evaluated, target_label)
        evaluated = self._apply_scoring_metadata(evaluated, source_context=src_reco_ctx)
        evaluated = self._sync_display_scores(evaluated)
        return evaluated

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
                text = self._build_concise_xai_summary(
                    rec,
                    target_type=target_type,
                    source_context=source_context,
                    language=language,
                )
                text = self._append_hybrid_xai_notes(text, rec, source_context)
                rec["explanation"] = {
                    "natural_language": text,
                    "visualization": explanation.get("visualization", ""),
                }
                rec["xai_explanation"] = text
            else:
                rec["xai_explanation"] = self._append_hybrid_xai_notes(
                    str(explanation), rec, source_context
                )
            out.append(rec)
        return out

    @staticmethod
    def _append_hybrid_xai_notes(
        text: str,
        recommendation: Dict[str, Any],
        source_context: Optional[Dict[str, Any]],
    ) -> str:
        notes: List[str] = []
        source_context = source_context or {}
        if source_context.get("cold_start") or recommendation.get("cold_start"):
            mode = recommendation.get("recommendation_mode") or source_context.get("recommendation_mode")
            if mode == "fallback_until_embedding_recomputed":
                notes.append(
                    "Ho so vua thay doi; he thong dang cap nhat embedding truoc khi goi y hybrid day du."
                )
            else:
                notes.append(
                    "Ket qua dang o che do cold-start/fallback vi embedding chua san sang hoac chua co path KG day du."
                )
        evidence = str(recommendation.get("evidence_level") or "")
        if evidence == "embedding_only":
            notes.append(
                "Diem so chu yeu tu embedding similarity; chua co reasoning path manh — khong nen coi la ket qua chac chan."
            )
        elif evidence == "fallback_only":
            notes.append("Ket qua dang dung heuristic/Cypher fallback; do tin cay thap hon PGPR policy.")
        if recommendation.get("recommendation_message"):
            notes.append(str(recommendation["recommendation_message"]))
        if recommendation.get("uses_provisional_data"):
            notes.append("Goi y co su dung du lieu chua xac thuc; ket qua co the thay doi sau khi duyet.")
        out = text or ""
        for note in notes:
            if note and note not in out:
                out = f"{out}\n\n{note}" if out else note
        return out
        
    async def explain_recommendation(
        self,
        recommendation: Dict[str, Any],
        target_type: str,
        source_context: Optional[Dict[str, Any]] = None,
        language: str = "vi",
        mode: str = "llm",
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Explain one recommendation. mode: rule | llm | auto (llm with rule fallback).
        """
        mode = (mode or "llm").lower()
        if mode not in ("rule", "llm", "auto"):
            raise ValueError(f"Unsupported explanation mode: {mode}")

        cache_key = self._build_explanation_cache_key(
            recommendation=recommendation,
            target_type=target_type,
            source_context=source_context,
            language=language,
            mode=mode,
        )

        if not force_refresh:
            cached = await cache.get(cache_key)
            if isinstance(cached, dict):
                cached["_cache"] = {
                    "hit": True,
                    "key": cache_key,
                    "scope": "service",
                }
                return cached

        if mode == "rule":
            explanation = self._explain_rule(
                recommendation, target_type, source_context, language
            )
            await self._save_explanation_cache(cache_key, explanation)
            explanation["_cache"] = {
                "hit": False,
                "key": cache_key,
                "scope": "service",
            }
            return explanation

        try:
            explanation = await self._explain_llm(
                recommendation, target_type, source_context, language
            )
            explanation["summary_style"] = "xai_model_generated"
            explanation["model_generated"] = True
            await self._save_explanation_cache(cache_key, explanation)
            explanation["_cache"] = {
                "hit": False,
                "key": cache_key,
                "scope": "service",
            }
            return explanation
        except Exception as e:
            logger.warning("LLM explanation failed (%s), fallback to rule", e)
            if mode == "llm":
                raise
            explanation = self._explain_rule(
                recommendation, target_type, source_context, language
            )
            await self._save_explanation_cache(cache_key, explanation)
            explanation["_cache"] = {
                "hit": False,
                "key": cache_key,
                "scope": "service",
                "fallback": "rule",
            }
            return explanation

    async def explain_single_recommendation(
        self,
        recommendation: Dict[str, Any],
        target_type: str,
        source_context: Optional[Dict[str, Any]] = None,
        language: str = "vi",
    ) -> Dict[str, Any]:
        """Backward-compatible alias: defaults to LLM with rule fallback."""
        return await self.explain_recommendation(
            recommendation=recommendation,
            target_type=target_type,
            source_context=source_context,
            language=language,
            mode="auto",
        )

    async def _save_explanation_cache(self, cache_key: str, explanation: Dict[str, Any]) -> None:
        payload = dict(explanation)
        payload.pop("_cache", None)
        await cache.set(cache_key, payload, ttl=3600)

    def _build_explanation_cache_key(
        self,
        recommendation: Dict[str, Any],
        target_type: str,
        source_context: Optional[Dict[str, Any]],
        language: str,
        mode: str,
    ) -> str:
        source_context = source_context or {}
        source_type = str(source_context.get("source_type") or "unknown").lower()
        source_id = str(source_context.get("source_id") or "unknown")
        rec_id = (
            recommendation.get("id")
            or recommendation.get("expert_id")
            or recommendation.get("project_id")
            or recommendation.get("funder_id")
            or recommendation.get("enterprise_id")
            or recommendation.get("name")
            or "unknown"
        )

        parts = [
            "explanation",
            "v6_no_diversity_confidence",
            str(language or "vi").lower(),
            str(mode or "rule").lower(),
            source_type,
            source_id,
            str(target_type or "unknown").lower(),
            str(rec_id),
        ]
        safe_parts = [re.sub(r"[^a-zA-Z0-9_.:-]+", "_", part) for part in parts]
        return ":".join(safe_parts)

    def _explain_rule(
        self,
        recommendation: Dict[str, Any],
        target_type: str,
        source_context: Optional[Dict[str, Any]],
        language: str,
    ) -> Dict[str, Any]:
        rule_explainer = PGPRExplainer(language=language, use_llm=False)
        explanation = rule_explainer.explain_recommendation(
            recommendation=recommendation,
            rec_type=target_type.lower(),
            source_context=source_context,
        )
        if isinstance(explanation, dict):
            explanation["uses_provisional_data"] = bool(recommendation.get("uses_provisional_data"))
            explanation["data_quality_level"] = recommendation.get("data_quality_level", "high")
            explanation["provisional_nodes_count"] = int(recommendation.get("provisional_nodes_count", 0) or 0)
            explanation["data_quality_notes"] = recommendation.get("data_quality_notes") or []
            explanation["verification_badges"] = recommendation.get("verification_badges") or {}
            explanation["scoring_method"] = recommendation.get("scoring_method")
            explanation["fallback_reason"] = recommendation.get("fallback_reason")
            explanation["hybrid_score_breakdown"] = recommendation.get("hybrid_score_breakdown") or {}
            explanation["evidence_level"] = recommendation.get("evidence_level")
            explanation["natural_language"] = self._build_concise_xai_summary(
                recommendation,
                target_type=target_type,
                source_context=source_context,
                language=language,
            )
            if recommendation.get("uses_provisional_data"):
                note = (
                    "Goi y nay co su dung du lieu chua xac thuc. "
                    "Ket qua co the thay doi sau khi ho so duoc duyet."
                )
                existing = explanation.get("natural_language")
                if isinstance(existing, str) and note not in existing:
                    explanation["natural_language"] = f"{existing}\n\n{note}"
            scoring_method = str(recommendation.get("scoring_method") or "")
            if scoring_method in {"cypher_fallback", "hybrid_embedding"}:
                if scoring_method == "cypher_fallback":
                    fallback_note = (
                        "Diem so va giai thich dua tren heuristic/Cypher tren do thi, "
                        "khong phai PGPR policy day du. Khong nen coi la ket qua chac chan."
                    )
                else:
                    fallback_note = (
                        "Kết quả hybrid có sử dụng embedding nhưng bằng chứng đường đi còn hạn chế."
                    )
                if recommendation.get("fallback_reason"):
                    fallback_note = f"{fallback_note}\n\n{recommendation['fallback_reason']}"
                existing = explanation.get("natural_language")
                if isinstance(existing, str) and fallback_note not in existing:
                    explanation["natural_language"] = f"{existing}\n\n{fallback_note}"
            evidence = str(recommendation.get("evidence_level") or "")
            if evidence == "embedding_only":
                note = "Canh bao: evidence_level=embedding_only — khong co path KG manh."
                existing = explanation.get("natural_language")
                if isinstance(existing, str) and note not in existing:
                    explanation["natural_language"] = f"{existing}\n\n{note}"
        return explanation

    def _apply_concise_explanation_contract(
        self,
        explanation: Dict[str, Any],
        *,
        recommendation: Dict[str, Any],
        target_type: str,
        source_context: Optional[Dict[str, Any]],
        language: str,
    ) -> Dict[str, Any]:
        """Keep model analysis for diagnostics while exposing one concise user-facing conclusion."""
        result = dict(explanation or {})
        generated_detail = result.get("natural_language")
        if isinstance(generated_detail, str) and generated_detail.strip():
            result["model_analysis_detail"] = generated_detail
        result["natural_language"] = self._build_concise_xai_summary(
            recommendation,
            target_type=target_type,
            source_context=source_context,
            language=language,
        )
        result["summary_style"] = "concise_aggregated"
        return result

    @staticmethod
    def _build_concise_xai_summary(
        recommendation: Dict[str, Any],
        *,
        target_type: str,
        source_context: Optional[Dict[str, Any]],
        language: str,
    ) -> str:
        """Summarize all reasoning paths into a short conclusion; paths are rendered separately."""
        if language != "vi":
            return str(recommendation.get("xai_explanation") or recommendation.get("explanation") or "")

        source_context = source_context or {}
        source_name = str(source_context.get("source_name") or source_context.get("source_id") or "nguồn hiện tại")
        target_name = str(
            recommendation.get("name")
            or recommendation.get("title")
            or recommendation.get("id")
            or "thực thể được đề xuất"
        )
        target_type = target_type.lower()
        target_label = {
            "expert": "chuyên gia",
            "project": "dự án",
            "funder": "quỹ tài trợ",
            "enterprise": "doanh nghiệp",
        }.get(target_type, "thực thể")

        paths = recommendation.get("reasoning_paths") or []
        source_id = str(source_context.get("source_id") or "")
        target_id = str(
            recommendation.get("id")
            or recommendation.get(f"{target_type}_id")
            or ""
        )
        categories: Dict[str, List[str]] = {
            "domain": [],
            "people": [],
            "organizations": [],
            "location": [],
        }
        for path in paths:
            for entity in path.get("entities") or []:
                if not isinstance(entity, dict):
                    continue
                entity_id = str(entity.get("id") or "")
                name = str(entity.get("name") or entity_id)
                entity_type = str(entity.get("type") or "").lower()
                if not name or entity_id in {source_id, target_id} or name in {source_name, target_name}:
                    continue
                if entity_type in {"researchtopic", "researchdirection", "skill", "industry", "technology"}:
                    bucket = "domain"
                elif entity_type == "expert":
                    bucket = "people"
                elif entity_type in {"enterprise", "funder", "project"}:
                    bucket = "organizations"
                elif entity_type == "location":
                    bucket = "location"
                else:
                    continue
                if name not in categories[bucket]:
                    categories[bucket].append(name)

        evidence_parts: List[str] = []
        if categories["domain"]:
            evidence_parts.append("điểm giao về " + ", ".join(categories["domain"][:3]))
        bridges = categories["people"][:2] + categories["organizations"][:2]
        if bridges:
            evidence_parts.append("mạng lưới kết nối qua " + ", ".join(bridges[:3]))
        if categories["location"]:
            evidence_parts.append("phạm vi hoạt động tại " + ", ".join(categories["location"][:1]))

        if evidence_parts:
            reason = "; ".join(evidence_parts)
        elif recommendation.get("embedding_similarity"):
            reason = "hồ sơ và đặc trưng nghiên cứu có độ tương đồng đáng kể"
        else:
            reason = "dữ liệu hồ sơ và mạng lưới hiện tại cho thấy mức độ liên quan"

        score = float(recommendation.get("score", 0.0) or 0.0)
        path_count = len(paths)
        evidence_note = (
            f"Kết luận này được tổng hợp từ {path_count} bằng chứng trên Knowledge Graph"
            if path_count
            else "Kết luận này hiện chủ yếu dựa trên dữ liệu hồ sơ và tín hiệu tương đồng"
        )
        return (
            f"Hệ thống đề xuất {target_label} {target_name} cho {source_name} vì {reason}. "
            f"{evidence_note}; điểm xếp hạng tổng hợp là {score:.1%}."
        )

    @staticmethod
    def _prepend_score_explanation(
        natural_language: str,
        recommendation: Dict[str, Any],
        *,
        language: str,
    ) -> str:
        if language != "vi":
            return natural_language

        natural_language = natural_language.replace(
            "Độ phù hợp tổng thể:",
            "Điểm xếp hạng tổng hợp:",
        )

        method = str(recommendation.get("scoring_method") or "")
        evidence = str(recommendation.get("evidence_level") or "")
        pgpr_score = float(recommendation.get("pgpr_score", 0.0) or 0.0)
        embedding_similarity = float(recommendation.get("embedding_similarity", 0.0) or 0.0)
        topic_overlap = float(recommendation.get("topic_overlap", 0.0) or 0.0)
        path_count = len(recommendation.get("reasoning_paths") or [])

        signals: List[str] = []
        if pgpr_score > 0:
            signals.append(f"điểm PGPR policy {pgpr_score:.1%}")
        if embedding_similarity > 0:
            signals.append(f"độ tương đồng embedding {embedding_similarity:.1%}")
        if topic_overlap > 0:
            signals.append(f"mức trùng khớp topic/kỹ năng {topic_overlap:.1%}")
        if path_count:
            signals.append(f"{path_count} bằng chứng đường đi trên Knowledge Graph")

        if not signals:
            return natural_language

        if method == "hybrid_embedding_path":
            header = (
                "Điểm phù hợp tổng thể là điểm hybrid được tổng hợp từ "
                + ", ".join(signals)
                + ". Trọng số ghi trên từng bằng chứng bên dưới chỉ thể hiện sức mạnh của riêng đường đi đó, "
                "không phải toàn bộ điểm recommendation."
            )
        elif evidence == "path_supported":
            header = (
                "Điểm phù hợp được xếp hạng chủ yếu từ "
                + ", ".join(signals)
                + ". Điểm của từng bằng chứng bên dưới không phải điểm tổng."
            )
        else:
            header = "Điểm phù hợp được tổng hợp từ " + ", ".join(signals) + "."

        return f"{header}\n\n{natural_language}" if natural_language else header

    async def _explain_llm(
        self,
        recommendation: Dict[str, Any],
        target_type: str,
        source_context: Optional[Dict[str, Any]],
        language: str,
    ) -> Dict[str, Any]:
        import aiohttp

        llm_explainer = PGPRExplainer(
            language=language,
            use_llm=True,
            ollama_model=self.explainer.ollama_model,
        )
        async with aiohttp.ClientSession() as session:
            return await llm_explainer.async_explain_recommendation(
                recommendation=recommendation,
                session=session,
                rec_type=target_type.lower(),
                source_context=source_context,
            )

    @staticmethod
    def _cap_score_after_trust(
        score: float,
        item: Dict[str, Any],
        source_status: Dict[str, Any],
        target_status: Dict[str, Any],
    ) -> float:
        """Re-apply hybrid evidence caps after trust weights so API score stays frontend-safe."""
        evidence = str(item.get("evidence_level") or "")
        paths = item.get("reasoning_paths") or []
        provisional = bool(
            item.get("uses_provisional_data")
            or CandidateMaskService.is_provisional(source_status)
            or CandidateMaskService.is_provisional(target_status)
        )
        cap = 1.0
        if evidence == "embedding_only" or (
            not paths and float(item.get("embedding_similarity", 0) or 0) > 0
        ):
            cap = 0.50 if provisional else 0.65
        elif evidence == "fallback_only" or not paths:
            cap = 0.45 if provisional else 0.55
        if item.get("embedding_signal") in {st.EMBEDDING_SIGNAL_NONE, "no_signal"}:
            cap = min(cap, 0.40)
        return round(min(max(float(score), 0.0), cap), 6)

    @staticmethod
    def _sync_display_scores(recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Frontend legacy consumers read `score`; keep it identical to capped final_score."""
        out: List[Dict[str, Any]] = []
        for rec in recommendations:
            item = dict(rec)
            final_score = item.get("final_score")
            if final_score is None:
                final_score = item.get("score", 0.0)
            item["final_score"] = round(float(final_score or 0.0), 6)
            item["score"] = item["final_score"]
            out.append(item)
        return out

    def _apply_scoring_metadata(
        self,
        recommendations: List[Dict[str, Any]],
        source_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Infer scoring_method, evidence_level, caps and source-level hybrid metadata."""
        source_context = source_context or {}
        out: List[Dict[str, Any]] = []
        for rec in recommendations:
            item = dict(rec)
            paths = item.get("reasoning_paths") or []
            method = item.get("scoring_method")
            if not method:
                if paths and any((p.get("source") == "cypher_fallback") for p in paths if isinstance(p, dict)):
                    method = "cypher_fallback"
                elif paths:
                    method = "pgpr_policy"
                else:
                    method = "cypher_fallback"
                item["scoring_method"] = method
            if not item.get("evidence_level"):
                if paths and method not in {"cypher_fallback", "hybrid_embedding"}:
                    item["evidence_level"] = "path_supported"
                elif item.get("embedding_similarity"):
                    item["evidence_level"] = "embedding_only"
                else:
                    item["evidence_level"] = "fallback_only"
            if not paths and not item.get("fallback_reason"):
                item["fallback_reason"] = (
                    "Khong tim thay duong ly do tren Knowledge Graph. "
                    "Diem so co the tu heuristic va chua du tin cay."
                )
            evidence = str(item.get("evidence_level") or "fallback_only")
            cap = 0.55
            if evidence == "path_supported" and paths:
                cap = 1.0
            elif evidence == "embedding_only":
                cap = 0.50 if item.get("uses_provisional_data") else 0.65
            elif item.get("uses_provisional_data"):
                cap = 0.45
            if not paths:
                capped = min(float(item.get("score", 0.0) or 0.0), cap)
                item["score"] = round(capped, 6)
                if item.get("final_score") is not None:
                    item["final_score"] = round(
                        min(float(item.get("final_score", capped) or capped), cap),
                        6,
                    )
            for field in (
                "cold_start",
                "embedding_status",
                "recommendation_mode",
                "recommendation_readiness",
                "recommendation_message",
            ):
                if field not in item and field in source_context:
                    item[field] = source_context.get(field)
            out.append(item)
        return out

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

    def _apply_provisional_rules(
        self,
        recommendations: List[Dict[str, Any]],
        source_id: str,
        source_label: str,
        target_label: str,
        mode: str,
        current_user_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        mode = mode if mode in {"public", "personal", "admin_debug"} else "public"
        source_status = self.candidate_mask.get_entity_status(source_label.lower(), source_id)
        source_decision = self.candidate_mask.evaluate_source_status(
            source_status,
            mode=mode,
            current_user_id=current_user_id,
        )
        if not source_decision.allowed and mode != "admin_debug":
            logger.info(
                "Blocked source %s/%s mode=%s reasons=%s",
                source_label,
                source_id,
                mode,
                source_decision.reasons,
            )
            return []
        source_runtime_weight, source_override_reason = self.candidate_mask.runtime_source_weight(
            source_status,
            mode=mode,
            current_user_id=current_user_id,
        )

        out: List[Dict[str, Any]] = []
        for rec in recommendations:
            item = dict(rec)
            target_id = str(
                item.get("id")
                or item.get(f"{target_label.lower()}_id")
                or item.get("expert_id")
                or item.get("project_id")
                or item.get("funder_id")
                or item.get("enterprise_id")
                or ""
            )
            target_status = self.candidate_mask.get_entity_status(target_label.lower(), target_id) if target_id else {}
            target_decision = self.candidate_mask.evaluate_target_status(
                target_status,
                mode=mode,
                current_user_id=current_user_id,
            )
            if not target_decision.allowed:
                if mode == "admin_debug":
                    item["candidate_mask"] = {
                        "allowed": False,
                        "reasons": target_decision.reasons,
                        "status": target_decision.status,
                    }
                else:
                    continue
            else:
                item["candidate_mask"] = {"allowed": True}

            if mode != "admin_debug" and not target_decision.allowed:
                continue

            target_weight = float(target_status.get("trust_weight", 1.0) or 1.0)
            stored_source_weight = float(source_status.get("trust_weight", 1.0) or 1.0)
            base_score = float(item.get("score", 0.0) or 0.0)
            final_score = round(base_score * source_runtime_weight * target_weight, 6)

            provisional_count = int(self.candidate_mask.is_provisional(source_status)) + int(self.candidate_mask.is_provisional(target_status))
            notes: List[str] = []
            if self.candidate_mask.is_provisional(source_status):
                notes.append("Source entity is unverified or provisional")
            if self.candidate_mask.is_provisional(target_status):
                notes.append("Target entity is unverified or provisional")
            if provisional_count:
                notes.append("This recommendation uses provisional KG data")

            item["raw_score"] = base_score
            capped_score = self._cap_score_after_trust(
                final_score,
                item,
                source_status,
                target_status,
            )
            item["score"] = capped_score
            item["final_score"] = capped_score
            item["stored_trust_weight"] = stored_source_weight
            item["runtime_source_weight"] = source_runtime_weight
            item["trust_override_reason"] = source_override_reason
            item["uses_provisional_data"] = bool(provisional_count)
            item["provisional_nodes_count"] = provisional_count
            item["data_quality_level"] = self.candidate_mask.data_quality_level(source_status, target_status)
            item["data_quality_notes"] = notes
            item["verification_badges"] = {
                "source": source_status.get("entity_verification_status", "verified"),
                "target": target_status.get("entity_verification_status", "verified"),
            }
            out.append(item)

        out.sort(key=lambda rec: float(rec.get("score", 0.0) or 0.0), reverse=True)
        return out

    def _to_policy_label(self, entity_type: str) -> str:
        key = (entity_type or "").strip().lower()
        if key not in ENTITY_LABEL_MAP:
            raise ValueError(f"Unsupported entity type: {entity_type}")
        return ENTITY_LABEL_MAP[key]

    def _group_data(self, value: Any) -> Any:
        if isinstance(value, dict) and "data" in value:
            return value["data"]
        return value

    def _group_error(self, value: Any) -> Optional[str]:
        if isinstance(value, dict) and "error" in value:
            return value["error"]
        return None
