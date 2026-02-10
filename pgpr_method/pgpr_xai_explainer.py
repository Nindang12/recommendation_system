"""
XAI (Explainable AI) Module for PGPR Recommendations

Provides human-readable explanations for why recommendations were made,
including visualizations, natural language generation, and interactive exploration.
Optionally connects to Neo4j to fetch concrete evidence (fields, projects, funders)
for more detailed explanations.
"""

from typing import List, Dict, Any, Optional
import json
from collections import defaultdict
import os

from neo4j import GraphDatabase, Driver
from dotenv import load_dotenv


load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


class PGPRExplainer:
    """
    Explainable AI for PGPR recommendations.
    
    Generates:
    - Natural language explanations
    - Visual path diagrams
    - Confidence scores
    - Evidence summaries
    """
    
    def __init__(
        self,
        language: str = "vi",
        enable_neo4j: bool = True,
        neo4j_uri: str = NEO4J_URI,
        neo4j_user: str = NEO4J_USER,
        neo4j_password: str = NEO4J_PASSWORD,
    ):
        """
        Initialize explainer.
        
        Args:
            language: "vi" for Vietnamese, "en" for English
            enable_neo4j: whether to connect to Neo4j for detailed evidence
            neo4j_uri, neo4j_user, neo4j_password: Neo4j connection settings
        """
        self.language = language
        self._load_templates()

        self.enable_neo4j = enable_neo4j
        self._driver: Optional[Driver] = None

        if self.enable_neo4j:
            try:
                self._driver = GraphDatabase.driver(
                    neo4j_uri,
                    auth=(neo4j_user, neo4j_password),
                )
            except Exception:
                # If connection fails, silently fall back to non-DB mode
                self.enable_neo4j = False
    
    def _load_templates(self):
        """Load language templates for explanations."""
        if self.language == "vi":
            self.templates = {
                "funder": {
                    "intro": "Chúng tôi gợi ý **{name}** cho dự án của bạn vì:",
                    "score": "Độ phù hợp tổng thể: **{score:.1%}** ({level})",
                    "diversity": "Tìm thấy **{count} cách khác nhau** để kết nối funder này với dự án",
                    "path_intro": "**Lý do chính:**",
                    "confidence": "Độ tin cậy: {level}",
                },
                "enterprise": {
                    "intro": "Chúng tôi gợi ý doanh nghiệp **{name}** cho bạn vì:",
                    "score": "Độ phù hợp tổng thể: **{score:.1%}** ({level})",
                    "diversity": "Tìm thấy **{count} cách khác nhau** để kết nối doanh nghiệp này với bạn/dự án",
                    "path_intro": "**Lý do chính:**",
                    "confidence": "Độ tin cậy: {level}",
                },
                "expert": {
                    "intro": "Chúng tôi gợi ý **{name}** cho dự án của bạn vì:",
                    "score": "Độ phù hợp tổng thể: **{score:.1%}** ({level})",
                    "diversity": "Tìm thấy **{count} cách khác nhau** để kết nối chuyên gia này với dự án",
                    "path_intro": "**Lý do chính:**",
                    "confidence": "Độ tin cậy: {level}",
                },
                "project": {
                    "intro": "Chúng tôi gợi ý dự án **{name}** cho bạn vì:",
                    "score": "Độ phù hợp tổng thể: **{score:.1%}** ({level})",
                    "diversity": "Tìm thấy **{count} cách khác nhau** để kết nối dự án này với bạn",
                    "path_intro": "**Lý do chính:**",
                    "confidence": "Độ tin cậy: {level}",
                },
                "score_levels": {
                    0.8: "Xuất sắc",
                    0.6: "Rất tốt",
                    0.4: "Tốt",
                    0.2: "Khá",
                    0.0: "Trung bình",
                },
                "confidence_levels": {
                    0.8: "Rất cao - Nhiều bằng chứng mạnh",
                    0.6: "Cao - Bằng chứng đáng tin cậy",
                    0.4: "Trung bình - Bằng chứng hợp lý",
                    0.2: "Thấp - Ít bằng chứng",
                },
                "path_explanations": {
                    # Research Field paths
                    "belongs_to_supports": "Dự án thuộc lĩnh vực mà funder hỗ trợ",
                    "subfield_supports": "Dự án thuộc lĩnh vực con của lĩnh vực funder hỗ trợ",
                    "expertise_supports": "Dự án có chuyên gia trong lĩnh vực funder hỗ trợ",
                    
                    # Collaboration paths
                    "expert_network": "Thông qua mạng lưới chuyên gia và cộng tác viên",
                    "funder_history": "Funder đã tài trợ các dự án tương tự",
                    
                    # Direct paths
                    "direct_connection": "Kết nối trực tiếp qua {relation}",
                },
            }
        else:  # English
            self.templates = {
                "funder": {
                    "intro": "We recommend **{name}** for your project because:",
                    "score": "Overall fit: **{score:.1%}** ({level})",
                    "diversity": "Found **{count} different ways** to connect this funder to your project",
                    "path_intro": "**Main reasons:**",
                    "confidence": "Confidence: {level}",
                },
                "enterprise": {
                    "intro": "We recommend enterprise **{name}** for you because:",
                    "score": "Overall fit: **{score:.1%}** ({level})",
                    "diversity": "Found **{count} different ways** to connect this enterprise to you/your project",
                    "path_intro": "**Main reasons:**",
                    "confidence": "Confidence: {level}",
                },
                "expert": {
                    "intro": "We recommend **{name}** for your project because:",
                    "score": "Overall fit: **{score:.1%}** ({level})",
                    "diversity": "Found **{count} different ways** to connect this expert to your project",
                    "path_intro": "**Main reasons:**",
                    "confidence": "Confidence: {level}",
                },
                "project": {
                    "intro": "We recommend **{name}** for you because:",
                    "score": "Overall fit: **{score:.1%}** ({level})",
                    "diversity": "Found **{count} different ways** to connect this project to you",
                    "path_intro": "**Main reasons:**",
                    "confidence": "Confidence: {level}",
                },
                "score_levels": {
                    0.8: "Excellent",
                    0.6: "Very Good",
                    0.4: "Good",
                    0.2: "Fair",
                    0.0: "Average",
                },
                "confidence_levels": {
                    0.8: "Very High - Strong evidence",
                    0.6: "High - Reliable evidence",
                    0.4: "Medium - Reasonable evidence",
                    0.2: "Low - Limited evidence",
                },
            }
    
    def explain_recommendation(
        self,
        recommendation: Dict[str, Any],
        rec_type: str = "funder",
        source_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate comprehensive explanation for a recommendation.
        
        Args:
            recommendation: Recommendation dict from PGPR
            rec_type: "funder", "expert", or "project"
        
        Returns:
            Dict with natural language explanation, visualizations, and metadata
        """
        name = recommendation.get("name") or recommendation.get("title", "Unknown")
        score = recommendation.get("score", 0.0)
        diversity = recommendation.get("path_diversity", 0)
        reasoning_paths = recommendation.get("reasoning_paths", [])

        # Optional: fetch detailed evidence from Neo4j (fields, projects, funders)
        detailed_evidence: Optional[Dict[str, Any]] = None
        if self.enable_neo4j and self._driver and source_context:
            try:
                detailed_evidence = self._build_detailed_neo4j_evidence(
                    recommendation=recommendation,
                    rec_type=rec_type,
                    source_context=source_context,
                )
            except Exception:
                # Never let XAI queries break main flow
                detailed_evidence = None
        
        # Generate natural language explanation
        nl_explanation = self._generate_natural_language(
            name=name,
            score=score,
            diversity=diversity,
            reasoning_paths=reasoning_paths,
            rec_type=rec_type,
            detailed=detailed_evidence,
        )
        
        # Analyze path patterns
        path_analysis = self._analyze_paths(reasoning_paths)
        
        # Generate visual representation
        visual = self._generate_path_visualization(reasoning_paths[:3])
        
        # Calculate confidence metrics
        confidence = self._calculate_confidence(score, diversity, reasoning_paths)
        
        return {
            "natural_language": nl_explanation,
            "path_analysis": path_analysis,
            "visualization": visual,
            "confidence": confidence,
            "neo4j_details": detailed_evidence,
            "metadata": {
                "score": score,
                "diversity": diversity,
                "num_paths": len(reasoning_paths),
            }
        }
    
    def _generate_natural_language(
        self,
        name: str,
        score: float,
        diversity: int,
        reasoning_paths: List[Dict],
        rec_type: str,
        detailed: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate human-readable explanation in natural language."""
        templates = self.templates[rec_type]
        
        # Introduction
        intro = templates["intro"].format(name=name)
        
        # Overall score with level
        score_level = self._get_score_level(score)
        score_text = templates["score"].format(score=score, level=score_level)
        
        # Path diversity
        diversity_text = templates["diversity"].format(count=diversity)
        
        # Main reasoning paths
        path_intro = templates["path_intro"]
        path_explanations = self._explain_paths(reasoning_paths[:3], rec_type)
        
        # Combine core parts
        explanation = f"""
{intro}

{score_text}

{diversity_text}

{path_intro}

{path_explanations}
        """.strip()

        # Optionally append detailed evidence from Neo4j
        if detailed:
            extra = self._render_detailed_evidence(detailed, rec_type)
            if extra:
                explanation = f"{explanation}\n\n{extra}"
        
        return explanation

    # =========================================================
    # DETAILED EVIDENCE FROM NEO4J
    # =========================================================

    def _build_detailed_neo4j_evidence(
        self,
        recommendation: Dict[str, Any],
        rec_type: str,
        source_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Query Neo4j to get concrete evidence:
        - For expert: matched fields, related projects, shared funders
        - For funder: matched fields, funded related projects
        - For project: matched fields, shared funders
        """
        source_id = source_context.get("source_id")
        source_type = source_context.get("source_type")

        if not source_id or not source_type or not self._driver:
            return None

        if rec_type == "expert":
            return self._explain_expert_with_neo4j(recommendation, source_id, source_type)
        if rec_type == "funder":
            return self._explain_funder_with_neo4j(recommendation, source_id, source_type)
        if rec_type == "project":
            return self._explain_project_with_neo4j(recommendation, source_id, source_type)
        if rec_type == "enterprise":
            return self._explain_enterprise_with_neo4j(recommendation, source_id, source_type)

        return None

    def _explain_expert_with_neo4j(
        self,
        recommendation: Dict[str, Any],
        source_id: str,
        source_type: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Detailed explanation for: recommend Expert for Project.
        
        Assumes:
        - source_type == "Project"
        - recommendation contains "expert_id"
        """
        expert_id = recommendation.get("expert_id")
        if not expert_id or source_type != "Project":
            return None

        with self._driver.session() as session:
            # Basic project info + fields
            proj_row = session.run(
                """
                MATCH (p:Project {project_id: $project_id})
                OPTIONAL MATCH (p)-[:BELONGS_TO]->(pf:ResearchField)
                RETURN p.project_id AS project_id,
                       p.title AS title,
                       collect(DISTINCT pf.name) AS fields
                """,
                project_id=source_id,
            ).single()

            # Basic expert info + expertise fields + past projects
            expert_row = session.run(
                """
                MATCH (e:Expert {expert_id: $expert_id})
                OPTIONAL MATCH (e)-[:HAS_EXPERTISE_IN]->(ef:ResearchField)
                OPTIONAL MATCH (e)-[:PARTICIPATES_IN]->(ep:Project)
                RETURN e.expert_id AS expert_id,
                       e.name AS name,
                       collect(DISTINCT ef.name) AS expertise_fields,
                       collect(DISTINCT ep.title) AS past_projects
                """,
                expert_id=expert_id,
            ).single()

            # Fields that directly match between project and expert
            matched_fields = list(
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})-[:BELONGS_TO]->(pf:ResearchField)
                    MATCH (e:Expert {expert_id: $expert_id})-[:HAS_EXPERTISE_IN]->(ef:ResearchField)
                    WHERE pf = ef
                    RETURN DISTINCT pf.name AS field_name
                    """,
                    project_id=source_id,
                    expert_id=expert_id,
                )
            )

            # Related projects expert worked on that share fields with the current project
            related_projects = list(
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})-[:BELONGS_TO]->(pf:ResearchField)
                    MATCH (e:Expert {expert_id: $expert_id})-[:PARTICIPATES_IN]->(ep:Project)
                    MATCH (ep)-[:BELONGS_TO]->(ef:ResearchField)
                    WHERE pf = ef AND ep.project_id <> $project_id
                    RETURN DISTINCT ep.project_id AS project_id,
                           ep.title AS title
                    LIMIT 5
                    """,
                    project_id=source_id,
                    expert_id=expert_id,
                )
            )

            # Shared funders between current project and expert's past projects
            shared_funders = list(
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})<-[:FUNDS]-(f:Funder)
                    MATCH (e:Expert {expert_id: $expert_id})-[:PARTICIPATES_IN]->(ep:Project)<-[:FUNDS]-(f)
                    WHERE ep.project_id <> $project_id
                    RETURN DISTINCT f.funder_id AS funder_id,
                           f.name AS name
                    LIMIT 5
                    """,
                    project_id=source_id,
                    expert_id=expert_id,
                )
            )

        return {
            "source": dict(proj_row) if proj_row else {},
            "target": dict(expert_row) if expert_row else {},
            "matched_fields": [r["field_name"] for r in matched_fields if r.get("field_name")] if matched_fields else [],
            "related_projects": [dict(r) for r in related_projects],
            "shared_funders": [dict(r) for r in shared_funders],
        }

    def _explain_funder_with_neo4j(
        self,
        recommendation: Dict[str, Any],
        source_id: str,
        source_type: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Detailed explanation for: recommend Funder for Project or Expert.
        """
        funder_id = recommendation.get("funder_id")
        if not funder_id:
            return None

        # Case 1: recommend Funder for Project
        if source_type == "Project":
            with self._driver.session() as session:
                proj_row = session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    OPTIONAL MATCH (p)-[:BELONGS_TO]->(pf:ResearchField)
                    RETURN p.project_id AS project_id,
                           p.title AS title,
                           collect(DISTINCT pf.name) AS fields
                    """,
                    project_id=source_id,
                ).single()

                funder_row = session.run(
                    """
                    MATCH (f:Funder {funder_id: $funder_id})
                    OPTIONAL MATCH (f)-[:SUPPORTS]->(ff:ResearchField)
                    RETURN f.funder_id AS funder_id,
                           f.name AS name,
                           collect(DISTINCT ff.name) AS support_fields
                    """,
                    funder_id=funder_id,
                ).single()

                matched_fields = list(
                    session.run(
                        """
                        MATCH (p:Project {project_id: $project_id})-[:BELONGS_TO]->(pf:ResearchField)
                        MATCH (f:Funder {funder_id: $funder_id})-[:SUPPORTS]->(ff:ResearchField)
                        WHERE pf = ff
                        RETURN DISTINCT pf.name AS field_name
                        """,
                        project_id=source_id,
                        funder_id=funder_id,
                    )
                )

                funded_related_projects = list(
                    session.run(
                        """
                        MATCH (p:Project {project_id: $project_id})-[:BELONGS_TO]->(pf:ResearchField)
                        MATCH (f:Funder {funder_id: $funder_id})-[:FUNDS]->(fp:Project)-[:BELONGS_TO]->(ff:ResearchField)
                        WHERE pf = ff AND fp.project_id <> $project_id
                        RETURN DISTINCT fp.project_id AS project_id,
                               fp.title AS title
                        LIMIT 5
                        """,
                        project_id=source_id,
                        funder_id=funder_id,
                    )
                )

            return {
                "source": dict(proj_row) if proj_row else {},
                "target": dict(funder_row) if funder_row else {},
                "matched_fields": [r["field_name"] for r in matched_fields if r.get("field_name")] if matched_fields else [],
                "funded_related_projects": [dict(r) for r in funded_related_projects],
            }

        # Case 2: recommend Funder/Enterprise for Expert
        if source_type == "Expert":
            with self._driver.session() as session:
                expert_row = session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    OPTIONAL MATCH (e)-[:HAS_EXPERTISE_IN]->(ef:ResearchField)
                    OPTIONAL MATCH (e)-[:PARTICIPATES_IN]->(ep:Project)
                    RETURN e.expert_id AS expert_id,
                           e.name AS name,
                           collect(DISTINCT ef.name) AS expertise_fields,
                           collect(DISTINCT ep.title) AS past_projects
                    """,
                    expert_id=source_id,
                ).single()

                funder_row = session.run(
                    """
                    MATCH (f:Funder {funder_id: $funder_id})
                    OPTIONAL MATCH (f)-[:SUPPORTS]->(ff:ResearchField)
                    RETURN f.funder_id AS funder_id,
                           f.name AS name,
                           collect(DISTINCT ff.name) AS support_fields
                    """,
                    funder_id=funder_id,
                ).single()

                matched_fields = list(
                    session.run(
                        """
                        MATCH (e:Expert {expert_id: $expert_id})-[:HAS_EXPERTISE_IN]->(ef:ResearchField)
                        MATCH (f:Funder {funder_id: $funder_id})-[:SUPPORTS]->(ff:ResearchField)
                        WHERE ef = ff
                        RETURN DISTINCT ef.name AS field_name
                        """,
                        expert_id=source_id,
                        funder_id=funder_id,
                    )
                )

                funded_related_projects = list(
                    session.run(
                        """
                        MATCH (e:Expert {expert_id: $expert_id})-[:PARTICIPATES_IN]->(p:Project)<-[:FUNDS]-(f:Funder {funder_id: $funder_id})
                        RETURN DISTINCT p.project_id AS project_id,
                               p.title AS title
                        LIMIT 5
                        """,
                        expert_id=source_id,
                        funder_id=funder_id,
                    )
                )

            return {
                "source": dict(expert_row) if expert_row else {},
                "target": dict(funder_row) if funder_row else {},
                "matched_fields": [r["field_name"] for r in matched_fields if r.get("field_name")] if matched_fields else [],
                # tái sử dụng key funded_related_projects để renderer dùng chung
                "funded_related_projects": [dict(r) for r in funded_related_projects],
            }

        return None

    def _explain_enterprise_with_neo4j(
        self,
        recommendation: Dict[str, Any],
        source_id: str,
        source_type: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Detailed explanation for: recommend Enterprise for Expert.
        """
        enterprise_id = recommendation.get("enterprise_id")
        if not enterprise_id or source_type != "Expert":
            return None

        with self._driver.session() as session:
            expert_row = session.run(
                """
                MATCH (e:Expert {expert_id: $expert_id})
                OPTIONAL MATCH (e)-[:HAS_APPLICATION_EXPERIENCE_IN]->(i:Industry)
                RETURN e.expert_id AS expert_id,
                       e.name AS name,
                       collect(DISTINCT i.name) AS industries
                """,
                expert_id=source_id,
            ).single()

            enterprise_row = session.run(
                """
                MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                OPTIONAL MATCH (en)-[:OPERATES_IN]->(i:Industry)
                OPTIONAL MATCH (en)-[:PARTNERS_WITH]->(p:Project)
                RETURN en.enterprise_id AS enterprise_id,
                       en.name AS name,
                       collect(DISTINCT i.name) AS industries,
                       collect(DISTINCT p.title) AS partner_projects
                """,
                enterprise_id=enterprise_id,
            ).single()

            matched_industries = list(
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})-[:HAS_APPLICATION_EXPERIENCE_IN]->(ei:Industry)
                    MATCH (en:Enterprise {enterprise_id: $enterprise_id})-[:OPERATES_IN]->(ii:Industry)
                    WHERE ei = ii
                    RETURN DISTINCT ei.name AS industry_name
                    """,
                    expert_id=source_id,
                    enterprise_id=enterprise_id,
                )
            )

            partner_projects = list(
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})-[:PARTICIPATES_IN]->(p:Project)<-[:PARTNERS_WITH]-(en:Enterprise {enterprise_id: $enterprise_id})
                    RETURN DISTINCT p.project_id AS project_id,
                           p.title AS title
                    LIMIT 5
                    """,
                    expert_id=source_id,
                    enterprise_id=enterprise_id,
                )
            )

        return {
            "source": dict(expert_row) if expert_row else {},
            "target": dict(enterprise_row) if enterprise_row else {},
            "matched_industries": [r["industry_name"] for r in matched_industries if r.get("industry_name")] if matched_industries else [],
            "partner_projects": [dict(r) for r in partner_projects],
        }

    def _explain_project_with_neo4j(
        self,
        recommendation: Dict[str, Any],
        source_id: str,
        source_type: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Detailed explanation for: recommend Project for Expert.
        """
        target_project_id = recommendation.get("project_id")
        if not target_project_id or source_type != "Expert":
            return None

        with self._driver.session() as session:
            expert_row = session.run(
                """
                MATCH (e:Expert {expert_id: $expert_id})
                OPTIONAL MATCH (e)-[:HAS_EXPERTISE_IN]->(ef:ResearchField)
                RETURN e.expert_id AS expert_id,
                       e.name AS name,
                       collect(DISTINCT ef.name) AS expertise_fields
                """,
                expert_id=source_id,
            ).single()

            proj_row = session.run(
                """
                MATCH (p:Project {project_id: $project_id})
                OPTIONAL MATCH (p)-[:BELONGS_TO]->(pf:ResearchField)
                RETURN p.project_id AS project_id,
                       p.title AS title,
                       collect(DISTINCT pf.name) AS fields
                """,
                project_id=target_project_id,
            ).single()

            matched_fields = list(
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})-[:HAS_EXPERTISE_IN]->(ef:ResearchField)
                    MATCH (p:Project {project_id: $project_id})-[:BELONGS_TO]->(pf:ResearchField)
                    WHERE ef = pf
                    RETURN DISTINCT pf.name AS field_name
                    """,
                    expert_id=source_id,
                    project_id=target_project_id,
                )
            )

            shared_funders = list(
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})-[:PARTICIPATES_IN]->(ep:Project)<-[:FUNDS]-(f:Funder)
                    MATCH (p:Project {project_id: $project_id})<-[:FUNDS]-(f)
                    WHERE ep.project_id <> $project_id
                    RETURN DISTINCT f.funder_id AS funder_id,
                           f.name AS name
                    LIMIT 5
                    """,
                    expert_id=source_id,
                    project_id=target_project_id,
                )
            )

        return {
            "source": dict(expert_row) if expert_row else {},
            "target": dict(proj_row) if proj_row else {},
            "matched_fields": [r["field_name"] for r in matched_fields if r.get("field_name")] if matched_fields else [],
            "shared_funders": [dict(r) for r in shared_funders],
        }

    def _render_detailed_evidence(
        self,
        detailed: Dict[str, Any],
        rec_type: str,
    ) -> str:
        """Turn structured Neo4j evidence into user-friendly text."""
        if self.language == "vi":
            header = "Chi tiết từ đồ thị tri thức:"
        else:
            header = "Detailed evidence from the knowledge graph:"

        lines: List[str] = []

        if rec_type == "expert":
            src = detailed.get("source", {})
            tgt = detailed.get("target", {})
            matched_fields = detailed.get("matched_fields") or []
            related_projects = detailed.get("related_projects") or []
            shared_funders = detailed.get("shared_funders") or []

            if self.language == "vi":
                if src.get("title"):
                    lines.append(f"- Dự án hiện tại: {src['title']}")
                if tgt.get("name"):
                    lines.append(f"- Chuyên gia được đề xuất: {tgt['name']}")
                if matched_fields:
                    lines.append(
                        "- Lĩnh vực trùng khớp giữa chuyên gia và dự án: "
                        + ", ".join(matched_fields)
                    )
                if related_projects:
                    names = [p.get("title") or p.get("project_id") for p in related_projects]
                    lines.append(
                        "- Chuyên gia từng tham gia các dự án có cùng lĩnh vực: "
                        + ", ".join([n for n in names if n])
                    )
                if shared_funders:
                    fnames = [f.get("name") or f.get("funder_id") for f in shared_funders]
                    lines.append(
                        "- Quỹ tài trợ chung giữa dự án hiện tại và các dự án trước đây của chuyên gia: "
                        + ", ".join([n for n in fnames if n])
                    )
            else:
                if src.get("title"):
                    lines.append(f"- Current project: {src['title']}")
                if tgt.get("name"):
                    lines.append(f"- Recommended expert: {tgt['name']}")
                if matched_fields:
                    lines.append(
                        "- Overlapping fields between expert and project: "
                        + ", ".join(matched_fields)
                    )
                if related_projects:
                    names = [p.get("title") or p.get("project_id") for p in related_projects]
                    lines.append(
                        "- Expert has worked on related projects in the same fields: "
                        + ", ".join([n for n in names if n])
                    )
                if shared_funders:
                    fnames = [f.get("name") or f.get("funder_id") for f in shared_funders]
                    lines.append(
                        "- Shared funders between this project and expert's past projects: "
                        + ", ".join([n for n in fnames if n])
                    )

        elif rec_type == "funder":
            src = detailed.get("source", {})
            tgt = detailed.get("target", {})
            matched_fields = detailed.get("matched_fields") or []
            funded_projects = detailed.get("funded_related_projects") or []

            if self.language == "vi":
                if src.get("title"):
                    lines.append(f"- Dự án: {src['title']}")
                if tgt.get("name"):
                    lines.append(f"- Quỹ tài trợ đề xuất: {tgt['name']}")
                if matched_fields:
                    lines.append(
                        "- Lĩnh vực quỹ đang hỗ trợ trùng với lĩnh vực của dự án: "
                        + ", ".join(matched_fields)
                    )
                if funded_projects:
                    names = [p.get("title") or p.get("project_id") for p in funded_projects]
                    lines.append(
                        "- Quỹ đã từng tài trợ các dự án tương tự: "
                        + ", ".join([n for n in names if n])
                    )
            else:
                if src.get("title"):
                    lines.append(f"- Project: {src['title']}")
                if tgt.get("name"):
                    lines.append(f"- Recommended funder: {tgt['name']}")
                if matched_fields:
                    lines.append(
                        "- Funder's supported fields match the project's field(s): "
                        + ", ".join(matched_fields)
                    )
                if funded_projects:
                    names = [p.get("title") or p.get("project_id") for p in funded_projects]
                    lines.append(
                        "- Funder has previously funded similar projects: "
                        + ", ".join([n for n in names if n])
                    )

        elif rec_type == "project":
            src = detailed.get("source", {})
            tgt = detailed.get("target", {})
            matched_fields = detailed.get("matched_fields") or []
            shared_funders = detailed.get("shared_funders") or []

            if self.language == "vi":
                if src.get("name"):
                    lines.append(f"- Chuyên gia hiện tại: {src['name']}")
                if tgt.get("title"):
                    lines.append(f"- Dự án được gợi ý: {tgt['title']}")
                if matched_fields:
                    lines.append(
                        "- Lĩnh vực dự án trùng với chuyên môn của chuyên gia: "
                        + ", ".join(matched_fields)
                    )
                if shared_funders:
                    fnames = [f.get("name") or f.get("funder_id") for f in shared_funders]
                    lines.append(
                        "- Có quỹ tài trợ chung giữa dự án này và các dự án chuyên gia từng tham gia: "
                        + ", ".join([n for n in fnames if n])
                    )
            else:
                if src.get("name"):
                    lines.append(f"- Current expert: {src['name']}")
                if tgt.get("title"):
                    lines.append(f"- Recommended project: {tgt['title']}")
                if matched_fields:
                    lines.append(
                        "- Project fields match expert's expertise: "
                        + ", ".join(matched_fields)
                    )
                if shared_funders:
                    fnames = [f.get("name") or f.get("funder_id") for f in shared_funders]
                    lines.append(
                        "- Shared funders between this project and expert's previous projects: "
                        + ", ".join([n for n in fnames if n])
                    )

        elif rec_type == "enterprise":
            src = detailed.get("source", {})
            tgt = detailed.get("target", {})
            matched_industries = detailed.get("matched_industries") or []
            partner_projects = detailed.get("partner_projects") or []

            if self.language == "vi":
                if src.get("name"):
                    lines.append(f"- Chuyên gia hiện tại: {src['name']}")
                if tgt.get("name"):
                    lines.append(f"- Doanh nghiệp/đối tác được đề xuất: {tgt['name']}")
                if matched_industries:
                    lines.append(
                        "- Lĩnh vực/industry mà chuyên gia có kinh nghiệm trùng với lĩnh vực doanh nghiệp đang hoạt động: "
                        + ", ".join(matched_industries)
                    )
                if partner_projects:
                    names = [p.get("title") or p.get("project_id") for p in partner_projects]
                    lines.append(
                        "- Các dự án doanh nghiệp đang hợp tác và phù hợp để chuyên gia tham gia: "
                        + ", ".join([n for n in names if n])
                    )
            else:
                if src.get("name"):
                    lines.append(f"- Current expert: {src['name']}")
                if tgt.get("name"):
                    lines.append(f"- Recommended enterprise/partner: {tgt['name']}")
                if matched_industries:
                    lines.append(
                        "- Industries where the expert has application experience that match the enterprise's operations: "
                        + ", ".join(matched_industries)
                    )
                if partner_projects:
                    names = [p.get("title") or p.get("project_id") for p in partner_projects]
                    lines.append(
                        "- Projects where this enterprise partners and the expert has worked on: "
                        + ", ".join([n for n in names if n])
                    )

        if not lines:
            return ""

        return header + "\n" + "\n".join(lines)
    
    def _explain_paths(
        self,
        paths: List[Dict],
        rec_type: str,
    ) -> str:
        """Explain reasoning paths in simple language."""
        explanations = []
        
        for i, path in enumerate(paths, 1):
            path_text = path.get("path", "")
            score = path.get("score", 0.0)
            length = path.get("length", 0)
            
            # Parse path into simple explanation
            simple_explanation = self._simplify_path(path_text, rec_type)
            
            # Format with confidence
            confidence_emoji = self._get_confidence_emoji(score)
            
            explanation = f"""
**{i}. {simple_explanation}** {confidence_emoji}
   - Độ tin cậy: {score:.1%}
   - Độ dài: {length} bước kết nối
            """.strip()
            
            explanations.append(explanation)
        
        return "\n\n".join(explanations)
    
    def _simplify_path(self, path_text: str, rec_type: str) -> str:
        """
        Convert technical path to simple explanation.
        
        Example:
        "belongs to field ResearchField -> supports Funder"
        →
        "Dự án thuộc lĩnh vực mà funder đang hỗ trợ"
        """
        # Common path patterns for funders
        funder_patterns = {
            "belongs to field.*supports": "Dự án thuộc lĩnh vực mà funder đang hỗ trợ",
            "is sub-field of.*supports": "Dự án thuộc lĩnh vực con của lĩnh vực funder hỗ trợ",
            "has expertise in.*supports": "Chuyên gia của dự án có expertise trong lĩnh vực funder hỗ trợ",
            "participates in.*funds": "Thông qua mạng lưới các chuyên gia đã được funder tài trợ",
            "collaborates with.*funds": "Thông qua mạng lưới cộng tác với các dự án funder đã tài trợ",
        }
        
        # Common path patterns for experts
        expert_patterns = {
            "belongs to field.*has expertise in": "Chuyên gia có chuyên môn trong lĩnh vực của dự án",
            "is sub-field of.*has expertise in": "Chuyên gia có chuyên môn trong lĩnh vực liên quan",
            "has skill.*participates in": "Chuyên gia có kỹ năng mà dự án cần",
            "collaborates with.*participates in": "Chuyên gia trong mạng lưới cộng tác với dự án",
        }
        
        patterns = funder_patterns if rec_type == "funder" else expert_patterns
        
        # Match patterns
        import re
        for pattern, explanation in patterns.items():
            if re.search(pattern, path_text, re.IGNORECASE):
                return explanation
        
        # Fallback: return simplified version
        return self._generic_simplification(path_text)
    
    def _generic_simplification(self, path_text: str) -> str:
        """Generic simplification when no pattern matches."""
        # Extract key relations
        relations = []
        
        if "belongs to field" in path_text.lower():
            relations.append("cùng lĩnh vực")
        if "supports" in path_text.lower():
            relations.append("được hỗ trợ")
        if "has expertise" in path_text.lower():
            relations.append("có chuyên môn")
        if "participates" in path_text.lower():
            relations.append("tham gia")
        if "collaborates" in path_text.lower():
            relations.append("cộng tác")
        if "funds" in path_text.lower():
            relations.append("tài trợ")
        
        if relations:
            return "Kết nối qua: " + ", ".join(relations)
        
        return "Có mối liên hệ với dự án"
    
    def _get_score_level(self, score: float) -> str:
        """Get score level description."""
        for threshold, level in sorted(self.templates["score_levels"].items(), reverse=True):
            if score >= threshold:
                return level
        return self.templates["score_levels"][0.0]
    
    def _get_confidence_emoji(self, score: float) -> str:
        """Get emoji based on confidence score."""
        if score >= 0.7:
            return "🌟"
        elif score >= 0.5:
            return "✅"
        elif score >= 0.3:
            return "👍"
        else:
            return "ℹ️"
    
    def _analyze_paths(self, reasoning_paths: List[Dict]) -> Dict[str, Any]:
        """Analyze path patterns and extract insights."""
        if not reasoning_paths:
            return {}
        
        # Extract relation types
        relation_counts = defaultdict(int)
        path_lengths = []
        
        for path in reasoning_paths:
            path_text = path.get("path", "")
            path_lengths.append(path.get("length", 0))
            
            # Count relation types
            if "belongs to field" in path_text.lower():
                relation_counts["field_alignment"] += 1
            if "supports" in path_text.lower():
                relation_counts["funder_support"] += 1
            if "has expertise" in path_text.lower():
                relation_counts["expertise_match"] += 1
            if "participates" in path_text.lower():
                relation_counts["collaboration_network"] += 1
            if "funds" in path_text.lower():
                relation_counts["funding_history"] += 1
        
        # Categorize paths
        categories = {
            "Direct Match": relation_counts["field_alignment"],
            "Funder History": relation_counts["funding_history"],
            "Expert Network": relation_counts["collaboration_network"],
            "Expertise Alignment": relation_counts["expertise_match"],
        }
        
        return {
            "path_categories": {k: v for k, v in categories.items() if v > 0},
            "avg_path_length": sum(path_lengths) / len(path_lengths) if path_lengths else 0,
            "shortest_path": min(path_lengths) if path_lengths else 0,
            "longest_path": max(path_lengths) if path_lengths else 0,
        }
    
    def _generate_path_visualization(self, paths: List[Dict]) -> str:
        """Generate ASCII visualization of reasoning paths."""
        if not paths:
            return "No paths to visualize"
        
        viz = "```\n"
        viz += "Reasoning Paths Visualization:\n"
        viz += "=" * 60 + "\n\n"
        
        for i, path in enumerate(paths, 1):
            path_text = path.get("path", "")
            score = path.get("score", 0.0)
            
            # Create ASCII path
            steps = path_text.split(" -> ")
            
            viz += f"Path {i} (Score: {score:.1%}):\n"
            for j, step in enumerate(steps):
                if j == 0:
                    viz += f"  ┌─ {step}\n"
                elif j == len(steps) - 1:
                    viz += f"  └─> {step}\n"
                else:
                    viz += f"  ├─> {step}\n"
            viz += "\n"
        
        viz += "```"
        return viz
    
    def _calculate_confidence(
        self,
        score: float,
        diversity: int,
        reasoning_paths: List[Dict],
    ) -> Dict[str, Any]:
        """Calculate confidence metrics for the recommendation."""
        # Base confidence from score
        base_confidence = score
        
        # Boost from path diversity
        diversity_boost = min(diversity / 10.0, 0.3)
        
        # Boost from number of high-quality paths
        high_quality_paths = sum(1 for p in reasoning_paths if p.get("score", 0) > 0.5)
        quality_boost = min(high_quality_paths / 5.0, 0.2)
        
        # Combined confidence
        total_confidence = min(base_confidence + diversity_boost + quality_boost, 1.0)
        
        # Get confidence level
        for threshold, level in sorted(self.templates["confidence_levels"].items(), reverse=True):
            if total_confidence >= threshold:
                confidence_level = level
                break
        else:
            confidence_level = self.templates["confidence_levels"][0.2]
        
        return {
            "total": round(total_confidence, 3),
            "level": confidence_level,
            "components": {
                "base_score": round(base_confidence, 3),
                "diversity_boost": round(diversity_boost, 3),
                "quality_boost": round(quality_boost, 3),
            },
            "interpretation": self._interpret_confidence(total_confidence),
        }
    
    def _interpret_confidence(self, confidence: float) -> str:
        """Interpret confidence level for users."""
        if self.language == "vi":
            if confidence >= 0.8:
                return "Rất khuyến nghị - Nhiều bằng chứng mạnh mẽ hỗ trợ gợi ý này"
            elif confidence >= 0.6:
                return "Khuyến nghị - Có đủ bằng chứng tin cậy"
            elif confidence >= 0.4:
                return "Đáng xem xét - Bằng chứng hợp lý nhưng nên tìm hiểu thêm"
            else:
                return "Có thể xem xét - Ít bằng chứng, nên nghiên cứu kỹ"
        else:
            if confidence >= 0.8:
                return "Highly recommended - Strong evidence supports this suggestion"
            elif confidence >= 0.6:
                return "Recommended - Sufficient reliable evidence"
            elif confidence >= 0.4:
                return "Worth considering - Reasonable evidence but investigate further"
            else:
                return "Consider with caution - Limited evidence"
    
    def explain_comparison(
        self,
        recommendations: List[Dict[str, Any]],
        rec_type: str = "funder",
    ) -> str:
        """
        Explain why recommendations are ranked in this order.
        
        Compares top recommendations and explains differences.
        """
        if len(recommendations) < 2:
            return "Only one recommendation available."
        
        top1 = recommendations[0]
        top2 = recommendations[1]
        
        name1 = top1.get("name") or top1.get("title", "First")
        name2 = top2.get("name") or top2.get("title", "Second")
        score1 = top1.get("score", 0.0)
        score2 = top2.get("score", 0.0)
        div1 = top1.get("path_diversity", 0)
        div2 = top2.get("path_diversity", 0)
        
        if self.language == "vi":
            explanation = f"""
### So sánh Top 2 gợi ý:

**1. {name1}** (Score: {score1:.3f})
**2. {name2}** (Score: {score2:.3f})

**Tại sao {name1} được xếp hạng cao hơn?**

"""
            # Analyze differences
            score_diff = score1 - score2
            
            if score_diff > 0.05:
                explanation += f"- **Điểm số cao hơn** ({score_diff:.3f} điểm): "
                if div1 > div2:
                    explanation += f"Có nhiều cách kết nối hơn ({div1} vs {div2})\n"
                else:
                    explanation += f"Chất lượng kết nối tốt hơn\n"
            
            if div1 > div2:
                explanation += f"- **Đa dạng hơn**: {div1} cách kết nối so với {div2} cách\n"
            
            # Best path comparison
            path1 = top1.get("reasoning_paths", [{}])[0]
            path2 = top2.get("reasoning_paths", [{}])[0]
            
            if path1.get("score", 0) > path2.get("score", 0):
                explanation += f"- **Đường dẫn tốt nhất mạnh hơn**: {path1.get('score', 0):.3f} vs {path2.get('score', 0):.3f}\n"
            
            if path1.get("length", 999) < path2.get("length", 999):
                explanation += f"- **Kết nối trực tiếp hơn**: {path1.get('length')} bước vs {path2.get('length')} bước\n"
            
            explanation += f"\n**Kết luận**: {name1} có sự kết hợp tốt hơn giữa độ phù hợp, đa dạng và chất lượng kết nối."
            
        else:  # English
            explanation = f"""
### Comparison of Top 2 Recommendations:

**1. {name1}** (Score: {score1:.3f})
**2. {name2}** (Score: {score2:.3f})

**Why is {name1} ranked higher?**

"""
            score_diff = score1 - score2
            
            if score_diff > 0.05:
                explanation += f"- **Higher score** ({score_diff:.3f} points): "
                if div1 > div2:
                    explanation += f"More connection paths ({div1} vs {div2})\n"
                else:
                    explanation += f"Better connection quality\n"
            
            if div1 > div2:
                explanation += f"- **More diverse**: {div1} connection types vs {div2}\n"
            
            path1 = top1.get("reasoning_paths", [{}])[0]
            path2 = top2.get("reasoning_paths", [{}])[0]
            
            if path1.get("score", 0) > path2.get("score", 0):
                explanation += f"- **Stronger best path**: {path1.get('score', 0):.3f} vs {path2.get('score', 0):.3f}\n"
            
            if path1.get("length", 999) < path2.get("length", 999):
                explanation += f"- **More direct connection**: {path1.get('length')} steps vs {path2.get('length')} steps\n"
            
            explanation += f"\n**Conclusion**: {name1} has a better combination of relevance, diversity, and connection quality."
        
        return explanation
    
    def generate_summary_report(
        self,
        recommendations: List[Dict[str, Any]],
        rec_type: str = "funder",
        project_id: str = "",
    ) -> str:
        """Generate a comprehensive summary report of all recommendations."""
        if not recommendations:
            return "No recommendations to summarize."
        
        total = len(recommendations)
        avg_score = sum(r.get("score", 0) for r in recommendations) / total
        avg_diversity = sum(r.get("path_diversity", 0) for r in recommendations) / total
        
        report = f"""
# 📊 Báo cáo Tổng quan Gợi ý cho {project_id}

## Thống kê chung:
- **Tổng số gợi ý**: {total}
- **Điểm trung bình**: {avg_score:.3f}
- **Đa dạng trung bình**: {avg_diversity:.1f} đường dẫn

## Top 3 gợi ý:

"""
        for i, rec in enumerate(recommendations[:3], 1):
            name = rec.get("name") or rec.get("title", "Unknown")
            score = rec.get("score", 0.0)
            diversity = rec.get("path_diversity", 0)
            
            report += f"""
### {i}. {name}
- **Điểm số**: {score:.3f} ({self._get_score_level(score)})
- **Đường dẫn**: {diversity} cách kết nối
- **Lý do chính**: {self._simplify_path(rec.get('reasoning_paths', [{}])[0].get('path', ''), rec_type)}

"""
        
        # Distribution analysis
        report += "\n## Phân tích phân bố:\n\n"
        
        high_score = sum(1 for r in recommendations if r.get("score", 0) >= 0.6)
        medium_score = sum(1 for r in recommendations if 0.4 <= r.get("score", 0) < 0.6)
        low_score = sum(1 for r in recommendations if r.get("score", 0) < 0.4)
        
        report += f"- **Xuất sắc** (≥0.6): {high_score} gợi ý\n"
        report += f"- **Tốt** (0.4-0.6): {medium_score} gợi ý\n"
        report += f"- **Trung bình** (<0.4): {low_score} gợi ý\n"
        
        return report


# ==========================================
# USAGE EXAMPLE
# ==========================================

if __name__ == "__main__":
    # Example recommendation from PGPR
    sample_recommendation = {
        "name": "LegalTech Fund",
        "score": 0.433,
        "path_diversity": 10,
        "reasoning_paths": [
            {
                "path": "participates in Expert -> collaborates with Expert -> has expertise in ResearchField -> supports Funder",
                "score": 0.333,
                "length": 4,
            },
            {
                "path": "participates in Expert -> collaborates with Expert -> participates in Project -> funds Funder",
                "score": 0.301,
                "length": 4,
            },
            {
                "path": "belongs to field ResearchField -> has expertise in Expert -> collaborates with Expert -> has expertise in ResearchField -> supports Funder",
                "score": 0.259,
                "length": 5,
            },
        ],
    }
    
    # Initialize explainer
    explainer = PGPRExplainer(language="vi")
    
    # Generate explanation
    explanation = explainer.explain_recommendation(sample_recommendation, rec_type="funder")
    
    print("="*80)
    print("NATURAL LANGUAGE EXPLANATION")
    print("="*80)
    print(explanation["natural_language"])
    
    print("\n" + "="*80)
    print("PATH VISUALIZATION")
    print("="*80)
    print(explanation["visualization"])
    
    print("\n" + "="*80)
    print("CONFIDENCE ANALYSIS")
    print("="*80)
    print(f"Total Confidence: {explanation['confidence']['total']:.1%}")
    print(f"Level: {explanation['confidence']['level']}")
    print(f"Interpretation: {explanation['confidence']['interpretation']}")
    
    print("\n" + "="*80)
    print("PATH ANALYSIS")
    print("="*80)
    print(json.dumps(explanation["path_analysis"], indent=2, ensure_ascii=False))