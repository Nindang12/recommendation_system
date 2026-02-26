"""
XAI (Explainable AI) Module for PGPR Recommendations

Provides human-readable explanations for why recommendations were made,
including visualizations, natural language generation, and interactive exploration.
Explanations are built directly từ các reasoning paths do PGPR tạo ra.
"""

from typing import List, Dict, Any, Optional
import json
from collections import defaultdict
import os
import urllib.request
import urllib.error

from dotenv import load_dotenv


load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")


def build_prompt_from_paths(
    recommendation: Dict[str, Any],
    rec_type: str,
    source_context: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
    language: str = "vi",
) -> str:
    """
    Build a prompt for LLM to explain recommendation reasoning paths.

    Ý tưởng: bắt LLM phải giải thích TỪNG đường dẫn một
    (path-level), sau đó tổng kết lại lý do chung.
    """
    name = recommendation.get("name") or recommendation.get("title", "Unknown")
    score = recommendation.get("score", 0.0)
    paths = recommendation.get("reasoning_paths", [])[:top_k]
    metrics = recommendation.get("metrics") or {}

    rec_labels = {
        "expert": ("chuyên gia", "expert"),
        "funder": ("quỹ tài trợ", "funder"),
        "project": ("dự án", "project"),
        "enterprise": ("doanh nghiệp", "enterprise"),
    }
    label_vi, label_en = rec_labels.get(rec_type, ("đề xuất", "recommendation"))

    # Source description (project / expert / funder / enterprise phía nguồn)
    source_desc_vi = ""
    source_desc_en = ""
    if source_context:
        st = source_context.get("source_type", "")
        sid = source_context.get("source_id", "")
        sn = source_context.get("source_name", sid)
        if st == "Project":
            source_desc_vi = f" cho dự án {sn}"
            source_desc_en = f" for project {sn}"
        elif st == "Expert":
            source_desc_vi = f" cho chuyên gia {sn}"
            source_desc_en = f" for expert {sn}"
        elif st == "Funder":
            source_desc_vi = f" cho quỹ {sn}"
            source_desc_en = f" for funder {sn}"
        elif st == "Enterprise":
            source_desc_vi = f" cho doanh nghiệp {sn}"
            source_desc_en = f" for enterprise {sn}"

    # Chuẩn bị block đường dẫn
    path_lines_vi: List[str] = []
    for i, p in enumerate(paths, 1):
        path_str = p.get("path", "") or p.get("explanation", "")
        sc = p.get("score", 0.0)
        length = p.get("length", 0)
        if path_str:
            path_lines_vi.append(
                f"{i}. Đường dẫn (score {sc:.2f}, length {length}): {path_str}"
            )
    paths_block_vi = "\n".join(path_lines_vi) if path_lines_vi else "(không có đường dẫn)"

    # Thêm metrics cho expert nếu có
    metrics_vi = ""
    metrics_en = ""
    if rec_type == "expert" and metrics:
        h = metrics.get("h_index")
        c = metrics.get("citations")
        pcount = metrics.get("publications")
        m_parts_vi = []
        m_parts_en = []
        if h is not None:
            m_parts_vi.append(f"h-index: {h}")
            m_parts_en.append(f"h-index: {h}")
        if c is not None:
            m_parts_vi.append(f"số trích dẫn: {c}")
            m_parts_en.append(f"citations: {c}")
        if pcount is not None:
            m_parts_vi.append(f"số công bố: {pcount}")
            m_parts_en.append(f"publications: {pcount}")
        if m_parts_vi:
            metrics_vi = "Chỉ số chuyên gia: " + ", ".join(m_parts_vi)
            metrics_en = "Expert metrics: " + ", ".join(m_parts_en)

    if language == "vi":
        prompt = f"""Bạn là trợ lý giải thích gợi ý trong hệ thống đề xuất dựa trên đồ thị tri thức.

Gợi ý: {label_vi} **{name}**{source_desc_vi}
Độ phù hợp tổng thể: khoảng {score:.0%}
{metrics_vi if metrics_vi else ""}

Các đường dẫn lý luận (từ dự án/nguồn tới {label_vi} này):
{paths_block_vi}

YÊU CẦU:
1. Với MỖI đường dẫn ở trên, hãy viết 1–2 câu tiếng Việt, dễ hiểu, giải thích cụ thể đường dẫn đó có ý nghĩa gì.
   - Nói rõ mối quan hệ giữa lĩnh vực, dự án, chuyên gia/quỹ/doanh nghiệp.
   - Sử dụng lại tên thực thể trong đường dẫn (ví dụ: Thị giác máy tính, Trí tuệ nhân tạo, Quỹ NAFOSTED, PGS.TS. Nguyễn Thị Huyền...).
2. Sau đó, viết 1–2 câu tổng kết tại sao {label_vi} **{name}** phù hợp với nguồn (dự án/chuyên gia/quỹ/doanh nghiệp), dựa trên TẤT CẢ các đường dẫn trên.
3. Không dùng thuật ngữ kỹ thuật như "node", "edge", "KG", "đồ thị tri thức". Không liệt kê lại nguyên văn đường dẫn, mà diễn giải bằng ngôn ngữ tự nhiên.
4. Viết dưới dạng đoạn văn hoàn chỉnh, không cần đánh số lại các đường dẫn."""
    else:
        prompt = f"""You are an assistant explaining a recommendation in a knowledge-graph-based system.

Recommendation: {label_en} **{name}**{source_desc_en}
Overall relevance score: about {score:.0%}
{metrics_en if metrics_en else ""}

Reasoning paths (from source to this {label_en}):
{paths_block_vi}

TASK:
1. For EACH path above, write 1–2 clear sentences explaining what this path means in practice (how the fields, projects, experts, funders, or enterprises are connected).
2. Then write 1–2 summary sentences explaining why {label_en} **{name}** is a good match for the source, based on ALL these paths.
3. Do NOT use technical terms like node, edge, KG, knowledge graph. Do not repeat the paths verbatim; paraphrase them into natural language.
4. Answer as a coherent paragraph (or a few short paragraphs), without re-numbering the paths."""

    return prompt


def llm_explain_paths_ollama(
    prompt: str,
    model: str = "llama3",
    ollama_url: str = OLLAMA_URL,
    timeout: int = 30,
) -> Optional[str]:
    """
    Call Ollama API to generate natural language explanation.

    Args:
        prompt: The prompt for the LLM
        model: Ollama model name (e.g. llama3, mistral, phi)
        ollama_url: Base URL (e.g. http://localhost:11434)
        timeout: Request timeout in seconds

    Returns:
        Generated text or None on error
    """
    url = f"{ollama_url.rstrip('/')}/api/generate"
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return (data.get("response") or "").strip()
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
        return None


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
        use_llm: bool = False,
        ollama_model: str = "llama3",
        ollama_url: str = OLLAMA_URL,
    ):
        """
        Initialize explainer.

        Args:
            language: "vi" for Vietnamese, "en" for English
            use_llm: if True, use Ollama LLM for natural language explanations
            ollama_model: Ollama model name (e.g. llama3, mistral)
            ollama_url: Ollama base URL
        """
        self.language = language
        self.use_llm = use_llm
        self.ollama_model = ollama_model
        self.ollama_url = ollama_url
        self._load_templates()
    
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

        # Generate natural language explanation (LLM or template)
        nl_explanation: str
        if self.use_llm:
            prompt = build_prompt_from_paths(
                recommendation=recommendation,
                rec_type=rec_type,
                source_context=source_context,
                top_k=5,
                language=self.language,
            )
            llm_text = llm_explain_paths_ollama(
                prompt=prompt,
                model=self.ollama_model,
                ollama_url=self.ollama_url,
                timeout=30,
            )
            if llm_text:
                nl_explanation = self._wrap_llm_explanation(
                    llm_text, name, score, diversity, rec_type
                )
            else:
                nl_explanation = self._generate_natural_language(
                    name=name,
                    score=score,
                    diversity=diversity,
                    reasoning_paths=reasoning_paths,
                    rec_type=rec_type,
                )
        else:
            nl_explanation = self._generate_natural_language(
                name=name,
                score=score,
                diversity=diversity,
                reasoning_paths=reasoning_paths,
                rec_type=rec_type,
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
        path_explanations = self._explain_paths(
            reasoning_paths[:3], rec_type, target_name=name
        )
        
        # Combine core parts
        explanation = f"""
{intro}

{score_text}

{diversity_text}

{path_intro}

{path_explanations}
        """.strip()

        return explanation

    def _wrap_llm_explanation(
        self,
        llm_text: str,
        name: str,
        score: float,
        diversity: int,
        rec_type: str,
    ) -> str:
        """Wrap LLM-generated explanation with intro, score, diversity."""
        templates = self.templates.get(rec_type, self.templates.get("expert", {}))
        intro = templates.get("intro", "Chúng tôi gợi ý **{name}**:").format(name=name)
        score_level = self._get_score_level(score)
        score_text = templates.get("score", "Độ phù hợp: **{score:.1%}** ({level})").format(
            score=score, level=score_level
        )
        diversity_text = templates.get(
            "diversity", "Tìm thấy **{count}** cách kết nối"
        ).format(count=diversity)
        return f"""{intro}

{score_text}
{diversity_text}

**Giải thích chi tiết:**
{llm_text}"""

    
    def _explain_paths(
        self,
        paths: List[Dict],
        rec_type: str,
        target_name: Optional[str] = None,
    ) -> str:
        """Explain reasoning paths in natural Vietnamese narrative."""
        explanations = []
        for i, path in enumerate(paths, 1):
            path_text = path.get("path", "") or path.get("explanation", "")
            score = path.get("score", 0.0)
            label = "mạnh nhất" if i == 1 else f"độ tin cậy {score:.0%}"
            narrative = self._narrate_path(path_text, rec_type, target_name)
            explanations.append(
                f"**Đường dẫn {i} ({label} – score {score:.2f})**\n{narrative}"
            )
        return "\n\n".join(explanations)

    def _parse_path_steps(self, path_text: str) -> List[tuple]:
        """
        Parse path string into (relation_key, entity) steps.
        E.g. "belongs to field X -> is sub-field of Y -> has expertise in Z"
        -> [("belongs_to_field", "X"), ("sub_field_of", "Y"), ("has_expertise_in", "Z")]
        """
        import re
        steps = []
        parts = [p.strip() for p in path_text.split("->") if p.strip()]
        rel_patterns = [
            (r"^belongs to field (.+)$", "belongs_to_field"),
            (r"^is sub-field of (.+)$", "sub_field_of"),
            (r"^is under field (.+)$", "under_field"),
            (r"^has expertise in (.+)$", "has_expertise_in"),
            (r"^has skill in (.+)$", "has_skill_in"),
            (r"^participates in (.+)$", "participates_in"),
            (r"^funds (.+)$", "funds"),
            (r"^supports (.+)$", "supports"),
            (r"^operates in industry (.+)$", "operates_in"),
            (r"^partners with (.+)$", "partners_with"),
            (r"^has experience in (.+)$", "has_experience_in"),
            (r"^collaborates with (.+)$", "collaborates_with"),
            (r"^produces (.+)$", "produces"),
            (r"^commercializes (.+)$", "commercializes"),
        ]
        for part in parts:
            for pat, key in rel_patterns:
                m = re.match(pat, part, re.IGNORECASE)
                if m:
                    steps.append((key, m.group(1).strip()))
                    break
            else:
                steps.append(("unknown", part))
        return steps

    def _narrate_path(
        self, path_text: str, rec_type: str, target_name: Optional[str] = None
    ) -> str:
        """
        Convert path to natural Vietnamese narrative.
        E.g. "belongs to field Thị giác máy tính -> is sub-field of Trí tuệ nhân tạo -> has expertise in PGS.TS. Nguyễn Thị Huyền"
        -> "Dự án nằm trong lĩnh vực Thị giác máy tính, đây là một nhánh thuộc Trí tuệ nhân tạo.
            PGS.TS. Nguyễn Thị Huyền có chuyên môn đúng trong lĩnh vực này, vì vậy hệ thống đánh giá chuyên gia này phù hợp với dự án."
        """
        steps = self._parse_path_steps(path_text)
        if not steps:
            return self._simplify_path(path_text, rec_type)

        if rec_type == "expert":
            return self._narrate_path_expert(steps, target_name)
        if rec_type == "funder":
            return self._narrate_path_funder(steps, target_name)
        if rec_type == "enterprise":
            return self._narrate_path_enterprise(steps, target_name)
        if rec_type == "project":
            return self._narrate_path_project(steps, target_name)
        return self._generic_simplification(path_text)

    def _narrate_path_expert(
        self, steps: List[tuple], target_name: Optional[str]
    ) -> str:
        """Narrate path for expert recommendation.
        Last step is the recommended expert; earlier steps build context.
        """
        intro_parts = []
        expert_name = None
        for key, entity in steps:
            if key == "belongs_to_field":
                intro_parts.append(f"Dự án nằm trong lĩnh vực {entity}")
            elif key == "sub_field_of":
                intro_parts.append(f"đây là một nhánh thuộc {entity}")
            elif key == "under_field":
                intro_parts.append(f"liên quan tới kỹ thuật {entity}")
            elif key == "has_expertise_in":
                expert_name = entity
            elif key == "has_skill_in":
                expert_name = entity
            elif key == "participates_in":
                intro_parts.append(f"thông qua chuyên gia {entity} (đã tham gia dự án liên quan)")
            elif key == "funds":
                intro_parts.append(f"quỹ {entity}")
            elif key == "supports":
                intro_parts.append(f"lĩnh vực {entity} được hỗ trợ")
        if expert_name:
            intro = ", ".join(intro_parts) + "." if intro_parts else "Dự án có liên quan đến chuyên môn."
            return f"{intro} {expert_name} có chuyên môn đúng trong lĩnh vực này, vì vậy hệ thống đánh giá chuyên gia này phù hợp với dự án."
        if intro_parts:
            return "Dự án kết nối qua: " + " → ".join(intro_parts) + "."
        return self._generic_simplification(
            " -> ".join(f"{k}: {v}" for k, v in steps)
        )

    def _narrate_path_funder(
        self, steps: List[tuple], target_name: Optional[str]
    ) -> str:
        """Narrate path for funder recommendation."""
        parts = []
        for key, entity in steps:
            if key == "belongs_to_field":
                parts.append(f"Dự án thuộc lĩnh vực {entity}.")
            elif key == "sub_field_of":
                parts.append(f"Đây là nhánh thuộc {entity}.")
            elif key == "supports":
                parts.append(f"Quỹ tài trợ đang hỗ trợ lĩnh vực {entity}.")
            elif key == "funds":
                parts.append(f"Quỹ đã tài trợ dự án/chuyên gia liên quan ({entity}).")
            elif key == "participates_in":
                parts.append(f"Thông qua mạng lưới chuyên gia {entity} đã tham gia các dự án được quỹ tài trợ.")
        if parts:
            return " ".join(parts) + " Vì vậy quỹ này phù hợp để tài trợ dự án."
        return self._generic_simplification(
            " -> ".join(f"{k}: {v}" for k, v in steps)
        )

    def _narrate_path_enterprise(
        self, steps: List[tuple], target_name: Optional[str]
    ) -> str:
        """Narrate path for enterprise recommendation."""
        parts = []
        for key, entity in steps:
            if key == "belongs_to_field":
                parts.append(f"Dự án thuộc lĩnh vực {entity}.")
            elif key == "operates_in":
                parts.append(f"Doanh nghiệp hoạt động trong lĩnh vực {entity}.")
            elif key == "partners_with":
                parts.append(f"Doanh nghiệp hợp tác với {entity}.")
            elif key == "has_expertise_in":
                parts.append(f"Chuyên gia {entity} có chuyên môn phù hợp với doanh nghiệp.")
            elif key == "participates_in":
                parts.append(f"Qua dự án {entity} mà doanh nghiệp quan tâm.")
        if parts:
            return " ".join(parts) + " Hệ thống đánh giá doanh nghiệp này phù hợp để hợp tác."
        return self._generic_simplification(
            " -> ".join(f"{k}: {v}" for k, v in steps)
        )

    def _narrate_path_project(
        self, steps: List[tuple], target_name: Optional[str]
    ) -> str:
        """Narrate path for similar project recommendation."""
        parts = []
        for key, entity in steps:
            if key == "belongs_to_field":
                parts.append(f"Cả hai dự án đều thuộc lĩnh vực {entity}.")
            elif key == "sub_field_of":
                parts.append(f"Lĩnh vực này là nhánh của {entity}.")
            elif key == "participates_in":
                parts.append(f"Cùng có chuyên gia {entity} tham gia.")
            elif key == "funds":
                parts.append(f"Cùng được quỹ {entity} tài trợ.")
            elif key == "supports":
                parts.append(f"Lĩnh vực {entity} liên quan đến cả hai dự án.")
        if parts:
            return " ".join(parts) + " Vì vậy đây là dự án tương tự để tham khảo."
        return self._generic_simplification(
            " -> ".join(f"{k}: {v}" for k, v in steps)
        )
    
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