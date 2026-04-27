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
import re

from dotenv import load_dotenv


load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")


_ID_LIKE_RE = re.compile(r"^(EXP|PRJ|FUN|ENT)_\d+$", re.IGNORECASE)


def _is_id_like(name: str) -> bool:
    s = (name or "").strip()
    return bool(s) and bool(_ID_LIKE_RE.match(s))


def _source_label_vi(source_type: str) -> str:
    return {
        "Project": "dự án",
        "Expert": "chuyên gia",
        "Funder": "quỹ",
        "Enterprise": "doanh nghiệp",
    }.get(source_type or "", "nguồn")


def _source_ref_vi(source_context: Optional[Dict[str, Any]]) -> str:
    """
    Vietnamese second-person friendly reference for the source entity.
    - Expert -> "bạn" (or "chuyên gia <name>" if a real name is available)
    - Project -> "dự án của bạn" (or "dự án <name>" if available)
    - Funder -> "quỹ của bạn" (or "quỹ <name>" if available)
    - Enterprise -> "doanh nghiệp của bạn" (or "doanh nghiệp <name>" if available)
    """
    if not source_context:
        return "nguồn của bạn"
    st = source_context.get("source_type", "") or ""
    sid = source_context.get("source_id", "") or ""
    sn = (source_context.get("source_name") or "").strip()
    # If name not provided or looks like an ID, fall back to second-person phrasing.
    if not sn or _is_id_like(sn) or sn == sid:
        if st == "Expert":
            return "bạn"
        if st == "Project":
            return "dự án của bạn"
        if st == "Funder":
            return "quỹ của bạn"
        if st == "Enterprise":
            return "doanh nghiệp của bạn"
        return "nguồn của bạn"

    # If we have a real name, use a named reference.
    label = _source_label_vi(st)
    if st == "Expert":
        return f"{label} {sn}"
    return f"{label} {sn}"


def _format_source_desc(source_context: Optional[Dict[str, Any]], language: str) -> str:
    """Format a short source phrase like 'cho dự án PRJ_0001'."""
    if not source_context:
        return ""
    st = source_context.get("source_type", "")
    sid = source_context.get("source_id", "")
    sn = source_context.get("source_name", sid)
    if language == "vi":
        # Prefer second-person friendly phrasing when source_name is missing or looks like an ID.
        if st == "Expert":
            ref = _source_ref_vi(source_context)
            return " cho bạn" if ref == "bạn" else f" cho {ref}"
        if st == "Project":
            ref = _source_ref_vi(source_context)
            return " cho dự án của bạn" if ref == "dự án của bạn" else f" cho {ref}"
        if st == "Funder":
            ref = _source_ref_vi(source_context)
            return " cho quỹ của bạn" if ref == "quỹ của bạn" else f" cho {ref}"
        if st == "Enterprise":
            ref = _source_ref_vi(source_context)
            return " cho doanh nghiệp của bạn" if ref == "doanh nghiệp của bạn" else f" cho {ref}"
        # Unknown source type
        ref = _source_ref_vi(source_context)
        return f" cho {ref}"
    else:
        if st == "Project":
            return f" for project {sn}"
        if st == "Expert":
            return f" for expert {sn}"
        if st == "Funder":
            return f" for funder {sn}"
        if st == "Enterprise":
            return f" for enterprise {sn}"
        return f" for source {sn}"


def _build_task_instructions(
    *,
    recommendation_name: str,
    rec_type: str,
    source_context: Optional[Dict[str, Any]],
    language: str,
    role_vi: str,
    label_vi: str,
    label_en: str,
) -> str:
    """
    Build rec_type- & source_type-aware instructions for the LLM.

    Motivation: the same rec_type can be used with different sources:
    - source=Project -> recommend Expert/Funder/Enterprise/SimilarProject
    - source=Expert -> recommend Enterprise/Funder/Project
    - source=Enterprise -> recommend Expert/Project
    - source=Funder -> recommend Expert/Project
    """
    st = (source_context or {}).get("source_type") or "Source"

    if language == "vi":
        source_labels = {
            "Project": "dự án",
            "Expert": "chuyên gia",
            "Funder": "quỹ tài trợ",
            "Enterprise": "doanh nghiệp",
            "Source": "nguồn",
        }
        src = source_labels.get(st, "nguồn")

        common = f"""YÊU CẦU CHUNG:
- Mỗi đường dẫn là một bằng chứng kết nối giữa {src} và {label_vi} **{recommendation_name}**.
- Với MỖI đường dẫn: viết 1–2 câu tiếng Việt, dễ hiểu, diễn giải ý nghĩa thực tế (không chép lại nguyên văn đường dẫn).
- Chỉ sử dụng thông tin có thể suy ra trực tiếp từ đường dẫn; không bịa thêm chi tiết bên ngoài.
- Nếu đường dẫn không thể hiện AI/công nghệ cụ thể thì không suy diễn theo hướng AI; hãy mô tả đúng theo lĩnh vực/chủ đề/ứng dụng xuất hiện.
- Tránh thuật ngữ kỹ thuật như "node", "edge", "KG", "đồ thị tri thức".
- Sau khi giải thích từng đường dẫn, viết 1 đoạn tổng kết 1–3 câu dựa trên TẤT CẢ đường dẫn."""

        if rec_type == "expert":
            if st == "Project":
                focus = f"""TRỌNG TÂM (Project → Expert):
- Nêu {src} thuộc/bắt nguồn từ lĩnh vực/chủ đề nào (suy ra từ đường dẫn). Nếu đường dẫn có nhắc AI/ML hoặc kỹ thuật/công nghệ cụ thể thì nêu; nếu không thì chỉ mô tả đúng theo lĩnh vực/chủ đề xuất hiện.
- Giải thích {label_vi} **{recommendation_name}** phù hợp ra sao (chuyên môn/kỹ năng/mạng lưới cộng tác/các dự án đã tham gia).
- Nếu có chuyên gia/quỹ/dự án trung gian trong đường dẫn, nêu vai trò cầu nối của họ."""
            elif st == "Enterprise":
                focus = f"""TRỌNG TÂM (Enterprise → Expert):
- Nêu doanh nghiệp đang quan tâm/nghiệp vụ/industry nào (suy ra từ đường dẫn). Nếu đường dẫn thể hiện nhu cầu công nghệ (AI hoặc công nghệ khác) thì nêu rõ; nếu không thì chỉ mô tả đúng theo lĩnh vực/ứng dụng xuất hiện trong đường dẫn.
- Giải thích {label_vi} **{recommendation_name}** có chuyên môn phù hợp để giải quyết bài toán/ứng dụng, hoặc từng hợp tác với các dự án/đối tác tương tự.
- Nếu có dự án/chuyên gia trung gian, làm rõ bối cảnh hợp tác/ứng dụng và cách nó kết nối tới doanh nghiệp."""
            elif st == "Funder":
                focus = f"""TRỌNG TÂM (Funder → Expert):
- Nêu quỹ đang hỗ trợ những hướng/lĩnh vực nào (suy ra từ đường dẫn). Nếu đường dẫn có nhắc AI/công nghệ cụ thể thì nêu; nếu không thì không suy diễn.
- Giải thích {label_vi} **{recommendation_name}** phù hợp để tham gia các dự án/cụm nghiên cứu mà quỹ thường hỗ trợ.
- Nếu có dự án/chuyên gia trung gian, nêu lịch sử tài trợ/cộng tác như một bằng chứng."""
            else:
                focus = f"""TRỌNG TÂM:
- Làm rõ điểm giao nhau về lĩnh vực/chủ đề/nhóm cộng tác khiến {label_vi} **{recommendation_name}** phù hợp với {src}."""

        elif rec_type == "funder":
            if st == "Project":
                focus = f"""TRỌNG TÂM (Project → Funder):
- Nêu {src} thuộc lĩnh vực nào và trùng/liên quan thế nào với danh mục lĩnh vực quỹ hỗ trợ.
- Nếu có bằng chứng quỹ đã tài trợ dự án/chuyên gia tương tự, hãy diễn giải như một tiền lệ phù hợp."""
            elif st == "Expert":
                focus = f"""TRỌNG TÂM (Expert → Funder):
- Nêu chuyên gia tập trung hướng nghiên cứu nào (suy ra từ đường dẫn) và hướng đó khớp với danh mục quỹ ra sao.
- Nếu có lịch sử quỹ tài trợ các dự án/chuyên gia cùng hướng, hãy nhấn mạnh tính liên thông trong mạng lưới nghiên cứu."""
            elif st == "Enterprise":
                focus = f"""TRỌNG TÂM (Enterprise → Funder):
- Nêu nhu cầu R&D/đổi mới/ứng dụng của doanh nghiệp (suy ra từ đường dẫn) và vì sao phù hợp với định hướng quỹ.
- Nếu có dự án/chuyên gia trung gian, diễn giải như một ví dụ quỹ có thể tạo tác động/đồng hành."""
            else:
                focus = f"""TRỌNG TÂM:
- Làm rõ vì sao quỹ **{recommendation_name}** phù hợp với {src} về lĩnh vực và lịch sử tài trợ."""

        elif rec_type == "enterprise":
            if st == "Project":
                focus = f"""TRỌNG TÂM (Project → Enterprise):
- Nêu {src} thuộc lĩnh vực/ứng dụng nào và liên quan thế nào tới ngành/industry doanh nghiệp đang hoạt động.
- Nếu đường dẫn cho thấy doanh nghiệp từng hợp tác dự án tương tự hoặc có chuyên gia liên quan, hãy diễn giải như kinh nghiệm phù hợp."""
            elif st == "Expert":
                focus = f"""TRỌNG TÂM (Expert → Enterprise):
- Nêu chuyên gia có thể đóng góp công nghệ/chuyên môn gì (suy ra từ đường dẫn) và vì sao phù hợp với bài toán/industry của doanh nghiệp.
- Nếu có dự án trung gian, nêu đó là ví dụ cho khả năng chuyển giao/ứng dụng thực tế."""
            elif st == "Funder":
                focus = f"""TRỌNG TÂM (Funder → Enterprise):
- Nêu doanh nghiệp phù hợp để ứng dụng/thương mại hoá/chuyển giao kết quả các dự án mà quỹ quan tâm (suy ra từ đường dẫn).
- Nếu có dự án/chuyên gia trung gian, diễn giải mối liên kết như chuỗi "nghiên cứu → ứng dụng"."""
            else:
                focus = f"""TRỌNG TÂM:
- Làm rõ vì sao doanh nghiệp **{recommendation_name}** phù hợp với {src} dựa trên lĩnh vực và lịch sử hợp tác."""

        else:  # project
            if st == "Project":
                focus = f"""TRỌNG TÂM (Project → Similar Project):
- Nêu hai dự án giống nhau ở điểm nào (cùng lĩnh vực, cùng quỹ tài trợ, cùng chuyên gia tham gia, v.v.)."""
            elif st == "Expert":
                focus = f"""TRỌNG TÂM (Expert → Project):
- Nêu dự án thuộc lĩnh vực/ứng dụng nào và vì sao phù hợp để chuyên gia tham gia (đúng chuyên môn, có nhóm/đối tác liên quan).
- Nếu có quỹ/doanh nghiệp/dự án trung gian, nêu chúng như bằng chứng về mạng lưới hợp tác."""
            elif st == "Funder":
                focus = f"""TRỌNG TÂM (Funder → Project):
- Nêu dự án thuộc lĩnh vực nào và vì sao phù hợp chiến lược tài trợ của quỹ (chủ đề, tính ứng dụng/tác động, liên thông mạng lưới)."""
            elif st == "Enterprise":
                focus = f"""TRỌNG TÂM (Enterprise → Project):
- Nêu dự án có ứng dụng/bài toán nào phù hợp nhu cầu doanh nghiệp, và bằng chứng doanh nghiệp/đối tác đã từng tham gia mảng này."""
            else:
                focus = f"""TRỌNG TÂM:
- Nêu vì sao dự án **{recommendation_name}** phù hợp với {src} dựa trên các liên hệ trong đường dẫn."""

        return f"""{common}

{focus}

KẾT LUẬN:
- Kết lại bằng 1–2 câu: vì sao {label_vi} **{recommendation_name}** là {role_vi} phù hợp với {src}."""

    source_labels_en = {
        "Project": "the project",
        "Expert": "the expert",
        "Funder": "the funder",
        "Enterprise": "the enterprise",
        "Source": "the source",
    }
    src_en = source_labels_en.get(st, "the source")

    common_en = f"""GENERAL RULES:
- Each path is evidence connecting {src_en} to the {label_en} **{recommendation_name}**.
- For EACH path: write 1–2 clear sentences. Do not copy the path verbatim.
- Only use what can be inferred from the paths; do not invent external details.
- If the paths do not show AI/ML or a specific technology, do not assume it—describe the domain/application exactly as stated.
- Avoid technical terms like node/edge/KG/knowledge graph.
- Then write a 1–3 sentence summary using ALL paths."""

    if rec_type == "expert":
        focus_en = "FOCUS: domain fit, expertise/skills, collaboration network, and any bridging intermediaries shown by the paths."
    elif rec_type == "funder":
        focus_en = "FOCUS: alignment with funding priorities and any evidence of funding similar projects/teams."
    elif rec_type == "enterprise":
        focus_en = "FOCUS: industry/application alignment and evidence of collaboration/technology transfer potential."
    else:
        focus_en = "FOCUS: practical similarity/fit (domain, shared collaborators, shared funders, or related projects)."

    return f"""{common_en}

{focus_en}

CONCLUSION: End with 1–2 sentences explaining why the {label_en} **{recommendation_name}** is a good match for {src_en}."""


def build_prompt_from_paths(
    recommendation: Dict[str, Any],
    rec_type: str,
    source_context: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
    language: str = "vi",
) -> str:
    """
    Build a prompt for LLM to explain recommendation reasoning paths.

    Ý tưởng chung:
    - Bắt LLM giải thích TỪNG đường dẫn (path-level), sau đó tổng kết lại.
    - Tùy loại gợi ý (expert / funder / enterprise / project) mà wording khác nhau.
    """
    name = recommendation.get("name") or recommendation.get("title", "Unknown")
    score = recommendation.get("score", 0.0)
    paths = recommendation.get("reasoning_paths", [])[:top_k]
    metrics = recommendation.get("metrics") or {}

    rec_labels = {
        "expert": ("chuyên gia", "expert", "chuyên gia tham gia dự án"),
        "funder": ("quỹ tài trợ", "funder", "quỹ tài trợ phù hợp"),
        "project": ("dự án", "project", "dự án tương tự để tham khảo/hợp tác"),
        "enterprise": ("doanh nghiệp", "enterprise", "doanh nghiệp/đối tác ứng dụng"),
    }
    label_vi, label_en, role_vi = rec_labels.get(
        rec_type, ("đề xuất", "recommendation", "đề xuất")
    )

    source_desc = _format_source_desc(source_context, language)

    # Chuẩn bị block đường dẫn
    path_lines: List[str] = []
    for i, p in enumerate(paths, 1):
        path_str = p.get("path", "") or p.get("explanation", "")
        sc = p.get("score", 0.0)
        length = p.get("length", 0)
        if path_str:
            path_lines.append(
                f"{i}. Đường dẫn (score {sc:.2f}, length {length}): {path_str}"
            )
    paths_block = "\n".join(path_lines) if path_lines else "(không có đường dẫn)"

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

    task = _build_task_instructions(
        recommendation_name=name,
        rec_type=rec_type,
        source_context=source_context,
        language=language,
        role_vi=role_vi,
        label_vi=label_vi,
        label_en=label_en,
    )

    if language == "vi":
        prompt = f"""Bạn là trợ lý giải thích gợi ý trong hệ thống đề xuất dựa trên đồ thị tri thức.

Gợi ý: {label_vi} **{name}**{source_desc}
Độ phù hợp tổng thể: khoảng {score:.0%}
{metrics_vi if metrics_vi else ""}

Các đường dẫn lý luận (từ nguồn tới {label_vi} này):
{paths_block}

{task}"""
    else:
        prompt = f"""You are an assistant explaining a recommendation in a knowledge-graph-based system.

Recommendation: {label_en} **{name}**{source_desc}
Overall relevance score: about {score:.0%}
{metrics_en if metrics_en else ""}

Reasoning paths (from the source to this {label_en}):
{paths_block}

{task}"""

    return prompt


def build_prompt_expert(
    recommendation: Dict[str, Any],
    source_context: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
    language: str = "vi",
) -> str:
    return build_prompt_from_paths(
        recommendation=recommendation,
        rec_type="expert",
        source_context=source_context,
        top_k=top_k,
        language=language,
    )


def build_prompt_funder(
    recommendation: Dict[str, Any],
    source_context: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
    language: str = "vi",
) -> str:
    return build_prompt_from_paths(
        recommendation=recommendation,
        rec_type="funder",
        source_context=source_context,
        top_k=top_k,
        language=language,
    )


def build_prompt_enterprise(
    recommendation: Dict[str, Any],
    source_context: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
    language: str = "vi",
) -> str:
    return build_prompt_from_paths(
        recommendation=recommendation,
        rec_type="enterprise",
        source_context=source_context,
        top_k=top_k,
        language=language,
    )


def build_prompt_project(
    recommendation: Dict[str, Any],
    source_context: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
    language: str = "vi",
) -> str:
    return build_prompt_from_paths(
        recommendation=recommendation,
        rec_type="project",
        source_context=source_context,
        top_k=top_k,
        language=language,
    )


# ==========================================
# OLLAMA CONFIGURATION + POST-PROCESSING
# ==========================================


class OllamaConfig:
    """Model-specific default generation options for Ollama."""

    MODELS: Dict[str, Dict[str, Any]] = {
        "llama3": {
            "temperature": 0.3,
            "top_p": 0.9,
            "top_k": 40,
            "num_predict": 420,
            "stop": ["\n\n\n", "===", "Ví dụ", "VÍ DỤ"],
        },
        "qwen": {
            "temperature": 0.3,
            "top_p": 0.9,
            "top_k": 40,
            "num_predict": 480,
            "stop": ["\n\n\n", "===", "Ví dụ", "VÍ DỤ"],
        },
        "mistral": {
            "temperature": 0.4,
            "top_p": 0.9,
            "top_k": 40,
            "num_predict": 420,
            "stop": ["\n\n\n", "==="],
        },
        "gemma": {
            "temperature": 0.35,
            "top_p": 0.85,
            "top_k": 30,
            "num_predict": 380,
            "stop": ["\n\n\n", "==="],
        },
    }

    @classmethod
    def get_config(cls, model: str) -> Dict[str, Any]:
        base = (model or "llama3").split(":")[0].strip().lower()
        return dict(cls.MODELS.get(base, cls.MODELS["llama3"]))


def post_process_llm_response(text: str) -> str:
    """Clean repetitive prefixes and formatting from LLM output."""
    if not text:
        return text

    s = text.strip()

    # Strip common meta/preamble phrases to keep output direct.
    unwanted_prefixes = (
        "Tôi nghĩ rằng",
        "Theo phân tích",
        "Dựa trên phân tích",
        "Dựa vào đồ thị tri thức",
        "Theo đồ thị tri thức",
        "Dựa trên knowledge graph",
        "Hệ thống đề xuất",
        "Chúng tôi đề xuất",
        "Chúng tôi khuyến nghị",
    )
    for p in unwanted_prefixes:
        if s.startswith(p):
            s = s[len(p) :].lstrip(" :,-\n\t")
            break

    # Drop accidental appended examples.
    for marker in ("====", "Ví dụ input:", "VÍ DỤ"):
        if marker in s:
            s = s.split(marker, 1)[0].strip()

    while "\n\n\n" in s:
        s = s.replace("\n\n\n", "\n\n")

    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        s = s[1:-1].strip()

    # Ensure sentence-like ending.
    if s and s[-1] not in ".!?…":
        s += "."

    return s


# ==========================================
# IMPROVED PROMPT (Few-shot, consistent tone)
# ==========================================


def _format_paths_for_prompt(paths: List[Dict[str, Any]], language: str) -> str:
    lines: List[str] = []
    for i, p in enumerate(paths, 1):
        sc = p.get("score", 0.0)
        node_names = p.get("node_names") or []
        if isinstance(node_names, list) and len(node_names) >= 2:
            arrow = " → " if language == "vi" else " -> "
            chain = arrow.join(str(x) for x in node_names)
            lines.append(f"{i}. {chain} (độ tin cậy: {sc:.0%})" if language == "vi" else f"{i}. {chain} (confidence: {sc:.0%})")
            continue

        path_str = (p.get("path") or p.get("explanation") or "").strip()
        if path_str:
            lines.append(f"{i}. {path_str} (độ tin cậy: {sc:.0%})" if language == "vi" else f"{i}. {path_str} (confidence: {sc:.0%})")

    if not lines:
        return "(không có đường dẫn)" if language == "vi" else "(no paths)"
    return "\n".join(lines)


def build_improved_prompt_from_paths(
    recommendation: Dict[str, Any],
    rec_type: str,
    source_context: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
    language: str = "vi",
) -> str:
    """
    Improved prompt inspired by your sample:
    - clear rules
    - few-shot example
    - short, natural output (4–6 sentences)
    - avoids KG jargon + avoids hallucinating AI
    """
    name = recommendation.get("name") or recommendation.get("title", "Unknown")
    score = float(recommendation.get("score", 0.0) or 0.0)
    paths = (recommendation.get("reasoning_paths") or [])[:top_k]
    metrics = recommendation.get("metrics") or {}

    st = (source_context or {}).get("source_type") or ""
    sid = (source_context or {}).get("source_id") or ""
    sn = (source_context or {}).get("source_name") or sid

    rec_labels = {
        "expert": ("chuyên gia", "expert"),
        "funder": ("quỹ tài trợ", "funder"),
        "project": ("dự án", "project"),
        "enterprise": ("doanh nghiệp", "enterprise"),
    }
    label_vi, label_en = rec_labels.get(rec_type, ("đề xuất", "recommendation"))

    source_desc = _format_source_desc(source_context, language)
    paths_block = _format_paths_for_prompt(paths, language)

    metrics_text = ""
    if rec_type == "expert" and metrics and language == "vi":
        m_parts = []
        if metrics.get("h_index") is not None:
            m_parts.append(f"h-index: {metrics.get('h_index')}")
        if metrics.get("citations") is not None:
            m_parts.append(f"{metrics.get('citations')} trích dẫn")
        if metrics.get("publications") is not None:
            m_parts.append(f"{metrics.get('publications')} công bố")
        if m_parts:
            metrics_text = "\nThành tích (nếu có): " + ", ".join(m_parts)

    if language != "vi":
        # Keep it simple for English; can extend later similarly.
        return build_prompt_from_paths(
            recommendation=recommendation,
            rec_type=rec_type,
            source_context=source_context,
            top_k=top_k,
            language=language,
        )

    # ---- Vietnamese few-shot templates ----
    rules = f"""BẠN LÀ: Trợ lý giải thích gợi ý trong hệ thống đề xuất.

QUY TẮC BẮT BUỘC:
1. Viết 4–6 câu tiếng Việt tự nhiên, dễ hiểu.
2. KHÔNG dùng thuật ngữ kỹ thuật (node, edge, KG, đồ thị tri thức).
3. Chỉ dựa vào thông tin có trong đường dẫn; không bịa thêm chi tiết bên ngoài.
4. Nếu đường dẫn không nói về AI/công nghệ thì KHÔNG suy diễn theo hướng AI/công nghệ.
5. Tránh mở đầu bằng “Tôi…”, “Chúng tôi…”, “Hệ thống…”.
6. Ưu tiên giải thích theo cấu trúc: (bối cảnh nguồn) → (bằng chứng kết nối) → (ý nghĩa hợp tác/tài trợ/phù hợp)."""

    source_ref = _source_ref_vi(source_context)

    if rec_type == "expert":
        few_shot = """===== VÍ DỤ MẪU (expert) =====
Gợi ý: chuyên gia PGS.TS. Trần Văn A cho dự án Smart City IoT
Đường dẫn:
1. Smart City IoT → IoT → PGS.TS. Trần Văn A (độ tin cậy: 65%)
2. Nhóm nghiên cứu B → PGS.TS. Trần Văn A (độ tin cậy: 55%)
Thành tích (nếu có): h-index: 35, 1200 trích dẫn

Output mẫu:
PGS.TS. Trần Văn A có chuyên môn đúng mảng IoT mà dự án Smart City IoT đang theo đuổi. Đường dẫn cũng cho thấy ông có liên hệ với Nhóm nghiên cứu B, giúp tăng khả năng phối hợp triển khai. Với thành tích học thuật tốt, chuyên gia này phù hợp để tư vấn và dẫn dắt phần nghiên cứu cốt lõi. Nhìn chung, đây là lựa chọn đáng cân nhắc nếu dự án cần người có nền tảng sâu và mạng lưới hợp tác sẵn có."""
        task = f"""===== NHIỆM VỤ =====
Gợi ý: {label_vi} **{name}**{source_desc}
Độ phù hợp: {score:.0%}{metrics_text}

Đường dẫn:
{paths_block}

Hãy giải thích vì sao {label_vi} **{name}** phù hợp với {source_ref} bằng 4–6 câu, tập trung vào chuyên môn/kỹ năng, kinh nghiệm, và bằng chứng kết nối."""
        return f"{rules}\n\n{few_shot}\n\n{task}"

    if rec_type == "funder":
        few_shot = """===== VÍ DỤ MẪU (funder) =====
Gợi ý: quỹ NAFOSTED cho dự án A
Đường dẫn:
1. Dự án A → Thị giác máy tính → NAFOSTED (độ tin cậy: 60%)
2. PGS.TS. Nguyễn B → NAFOSTED (độ tin cậy: 45%)

Output mẫu:
Dự án A thuộc hướng Thị giác máy tính, đúng với mảng mà NAFOSTED có liên hệ hỗ trợ trong các đường dẫn. Ngoài ra, PGS.TS. Nguyễn B cũng xuất hiện như một mắt xích kết nối với quỹ, cho thấy mạng lưới nghiên cứu có sự giao thoa. Điều này gợi ý cơ hội tiếp cận kênh tài trợ phù hợp về chủ đề. Tổng thể, NAFOSTED là lựa chọn đáng xem xét nếu dự án muốn tìm nguồn tài trợ gần với hướng nghiên cứu hiện tại."""
        task = f"""===== NHIỆM VỤ =====
Gợi ý: {label_vi} **{name}**{source_desc}
Độ phù hợp: {score:.0%}

Đường dẫn:
{paths_block}

Hãy giải thích vì sao {label_vi} **{name}** phù hợp với {source_ref} bằng 4–6 câu, nhấn mạnh sự khớp lĩnh vực và các bằng chứng về lịch sử/chuỗi hỗ trợ-tài trợ (nếu có)."""
        return f"{rules}\n\n{few_shot}\n\n{task}"

    if rec_type == "project":
        few_shot = """===== VÍ DỤ MẪU (project) =====
Gợi ý: dự án Smart Agriculture Platform cho dự án Smart City IoT
Đường dẫn:
1. IoT Sensors → Smart Agriculture Platform (độ tin cậy: 68%)
2. Dr. Nguyen → Smart Agriculture Platform (độ tin cậy: 55%)

Output mẫu:
Smart Agriculture Platform có điểm giao với dự án hiện tại qua cùng chủ đề IoT Sensors. Đường dẫn cũng cho thấy có nhân sự/nhóm (Dr. Nguyen) liên quan, giúp hai dự án dễ trao đổi kinh nghiệm triển khai. Vì vậy dự án này đáng tham khảo nếu bạn muốn học cách thiết kế hệ thống thu thập dữ liệu và vận hành thực tế. Tổng thể, đây là lựa chọn phù hợp để tìm bài học kinh nghiệm hoặc khả năng hợp tác."""
        task = f"""===== NHIỆM VỤ =====
Gợi ý: {label_vi} **{name}**{source_desc}
Độ liên quan: {score:.0%}

Đường dẫn:
{paths_block}

Hãy giải thích vì sao {label_vi} **{name}** đáng tham khảo/hợp tác với {source_ref} bằng 4–6 câu, tập trung vào điểm tương đồng và giá trị thực tế."""
        return f"{rules}\n\n{few_shot}\n\n{task}"

    # enterprise
    few_shot = """===== VÍ DỤ MẪU (enterprise) =====
Gợi ý: doanh nghiệp Công ty MedTech X cho chuyên gia EXP_0001
Đường dẫn:
1. Thiết bị y tế → Công ty MedTech X (độ tin cậy: 50%)
2. Thị giác máy tính → AI hỗ trợ chẩn đoán X-quang → Công ty MedTech X (độ tin cậy: 44%)

Output mẫu:
Bên bạn có kinh nghiệm trong mảng Thiết bị y tế, cũng là lĩnh vực doanh nghiệp này đang hoạt động. Một đường dẫn khác cho thấy chuyên môn Thị giác máy tính liên quan tới bài toán AI hỗ trợ chẩn đoán X-quang và có liên kết tới doanh nghiệp. Điều này gợi ý tiềm năng phối hợp để đưa nghiên cứu vào ứng dụng hoặc triển khai sản phẩm. Tổng thể, đây là đối tác đáng cân nhắc nếu bạn muốn mở rộng hợp tác theo đúng mảng chuyên môn hiện có."""
    task = f"""===== NHIỆM VỤ =====
Gợi ý: {label_vi} **{name}**{source_desc}
Độ phù hợp: {score:.0%}

Đường dẫn:
{paths_block}

Hãy giải thích vì sao {label_vi} **{name}** là đối tác tiềm năng cho {source_ref} bằng 4–6 câu, tập trung vào mảng hoạt động/nhu cầu hợp tác và bằng chứng kết nối."""
    return f"{rules}\n\n{few_shot}\n\n{task}"


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
    options = OllamaConfig.get_config(model)
    body = json.dumps(
        {"model": model, "prompt": prompt, "stream": False, "options": options}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return post_process_llm_response((data.get("response") or "").strip())
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
            prompt = build_improved_prompt_from_paths(
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
                    llm_text, name, score, diversity, rec_type, source_context
                )
            else:
                nl_explanation = self._generate_natural_language(
                    name=name,
                    score=score,
                    diversity=diversity,
                    reasoning_paths=reasoning_paths,
                    rec_type=rec_type,
                    source_context=source_context,
                )
        else:
            nl_explanation = self._generate_natural_language(
                name=name,
                score=score,
                diversity=diversity,
                reasoning_paths=reasoning_paths,
                rec_type=rec_type,
                source_context=source_context,
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
        source_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate human-readable explanation in natural language."""
        templates = self.templates[rec_type]
        
        # Introduction (make it consistent with source type)
        intro = self._build_intro(name=name, rec_type=rec_type, source_context=source_context)
        
        # Overall score with level
        score_level = self._get_score_level(score)
        score_text = templates["score"].format(score=score, level=score_level)
        
        # Path diversity (source-aware wording)
        diversity_text = self._build_diversity_text(
            diversity=diversity, rec_type=rec_type, source_context=source_context
        )
        
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
        source_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Wrap LLM-generated explanation with intro, score, diversity."""
        templates = self.templates.get(rec_type, self.templates.get("expert", {}))
        intro = self._build_intro(name=name, rec_type=rec_type, source_context=source_context)
        score_level = self._get_score_level(score)
        score_text = templates.get("score", "Độ phù hợp: **{score:.1%}** ({level})").format(
            score=score, level=score_level
        )
        diversity_text = self._build_diversity_text(
            diversity=diversity, rec_type=rec_type, source_context=source_context
        )
        return f"""{intro}

{score_text}
{diversity_text}

**Giải thích chi tiết:**
{llm_text}"""

    def _build_intro(
        self,
        *,
        name: str,
        rec_type: str,
        source_context: Optional[Dict[str, Any]],
    ) -> str:
        """Create a header that matches the current source entity (Project/Expert/Funder/Enterprise)."""
        if self.language != "vi":
            templates = self.templates.get(rec_type, self.templates.get("expert", {}))
            return templates.get("intro", "We recommend **{name}**:").format(name=name)

        label_map = {
            "expert": "chuyên gia",
            "funder": "quỹ tài trợ",
            "enterprise": "doanh nghiệp",
            "project": "dự án",
        }
        label = label_map.get(rec_type, "đề xuất")
        src_desc = _format_source_desc(source_context, "vi")
        return f"Chúng tôi gợi ý {label} **{name}**{src_desc} vì:"

    def _build_diversity_text(
        self,
        *,
        diversity: int,
        rec_type: str,
        source_context: Optional[Dict[str, Any]],
    ) -> str:
        """Create a diversity line without hard-coding 'dự án'."""
        if self.language != "vi":
            templates = self.templates.get(rec_type, self.templates.get("expert", {}))
            return templates.get("diversity", "Found **{count}** connections").format(
                count=diversity
            )

        label_map = {
            "expert": "chuyên gia",
            "funder": "quỹ",
            "enterprise": "doanh nghiệp",
            "project": "dự án",
        }
        label = label_map.get(rec_type, "thực thể")
        st = (source_context or {}).get("source_type") or ""
        src_vi = {
            "Project": "dự án",
            "Expert": "chuyên gia",
            "Funder": "quỹ",
            "Enterprise": "doanh nghiệp",
        }.get(st, "nguồn")
        return f"Tìm thấy **{diversity} cách khác nhau** để kết nối {label} này với {src_vi}"

    
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
        """Narrate path for enterprise recommendation.

        Mục tiêu: giải thích rõ mối quan hệ giữa
        - lĩnh vực / dự án của người dùng
        - các dự án mà doanh nghiệp đang hợp tác
        - (nếu có) chuyên gia liên quan.
        """
        source_field: Optional[str] = None
        related_fields: List[str] = []
        industries_raw: List[str] = []
        partner_projects_raw: List[str] = []
        expertise_areas: List[str] = []
        experiences: List[str] = []
        support_entities: List[str] = []  # e.g. funders
        funded_entities: List[str] = []  # e.g. projects/fields being funded

        for key, entity in steps:
            if key == "belongs_to_field":
                if source_field is None:
                    source_field = entity
                else:
                    related_fields.append(entity)
            elif key == "operates_in":
                industries_raw.append(entity)
            elif key == "partners_with":
                partner_projects_raw.append(entity)
            elif key == "has_expertise_in":
                expertise_areas.append(entity)
            elif key == "has_experience_in":
                experiences.append(entity)
            elif key == "supports":
                support_entities.append(entity)
            elif key == "funds":
                funded_entities.append(entity)
            elif key == "participates_in":
                # thường là tên dự án mà expert/enterprise tham gia
                partner_projects_raw.append(entity)

        enterprise_name = target_name or "doanh nghiệp này"
        sentences: List[str] = []

        def _looks_like_enterprise_name(x: str) -> bool:
            s = (x or "").strip().lower()
            en = (enterprise_name or "").strip().lower()
            return bool(s) and bool(en) and (s == en or en in s or s in en)

        # Clean up noisy entities coming from imperfect paths (e.g. industry=enterprise_name)
        industries = [x for x in industries_raw if x and not _looks_like_enterprise_name(x)]
        partner_projects = [x for x in partner_projects_raw if x and not _looks_like_enterprise_name(x)]
        linked_to_target = any(_looks_like_enterprise_name(x) for x in partner_projects_raw if x)

        if source_field:
            sentences.append(f"Bên bạn đang gắn với lĩnh vực {source_field}.")

        if partner_projects:
            proj_list = ", ".join(partner_projects[:2])
            sentences.append(
                f"{enterprise_name} đang/đã hợp tác trong các dự án/đối tác như {proj_list}, "
                "cho thấy doanh nghiệp có liên hệ trực tiếp với chủ đề/lĩnh vực được nêu trong đường dẫn."
            )

        # If the path explicitly contains "partners with <enterprise>", state the direct link.
        if linked_to_target:
            sentences.append(
                f"Đường dẫn cũng cho thấy có liên kết/đối tác trực tiếp với {enterprise_name}."
            )

        # Prefer describing these as expertise areas (not "experts"), because the entity can be a field.
        if expertise_areas:
            areas = ", ".join(expertise_areas[:2])
            if source_field:
                sentences.append(
                    f"Điều này đi kèm với chuyên môn/hướng chuyên môn {areas}, phù hợp với lĩnh vực vừa nêu."
                )
            else:
                sentences.append(
                    f"Bằng chứng còn cho thấy bên bạn có chuyên môn/hướng chuyên môn {areas} liên quan tới nhu cầu hợp tác."
                )

        # Mention funders/funding chain when present (common in enterprise<->expert paths).
        if support_entities or funded_entities:
            sup = ", ".join(support_entities[:1]) if support_entities else ""
            fun = ", ".join(funded_entities[:1]) if funded_entities else ""
            if sup and fun:
                sentences.append(
                    f"Có thể thấy chuỗi liên quan tới {sup} hỗ trợ/tài trợ cho {fun}, và {enterprise_name} xuất hiện ở phía hợp tác/ứng dụng."
                )
            elif sup:
                sentences.append(f"Đường dẫn còn nhắc tới {sup} như một mắt xích hỗ trợ/tài trợ liên quan.")
            elif fun:
                sentences.append(f"Đường dẫn còn nhắc tới hạng mục được tài trợ {fun} liên quan tới hợp tác/ứng dụng.")

        if industries and not sentences:
            ind_list = ", ".join(industries[:2])
            sentences.append(
                f"{enterprise_name} hoạt động trong lĩnh vực {ind_list}. Vì vậy đây có thể là đối tác phù hợp theo đúng mảng được thể hiện trong đường dẫn."
            )

        # Fallback for paths like:
        # "has experience in Thiết bị y tế -> operates in industry <enterprise_name>"
        if experiences and not sentences:
            exp = ", ".join(experiences[:2])
            if industries_raw:
                sentences.append(
                    f"Bên bạn có kinh nghiệm trong {exp} mà {enterprise_name} đang hoạt động. Đây là bằng chứng cho thấy {enterprise_name} phù hợp để hợp tác trong cùng mảng này."
                )
            else:
                sentences.append(
                    f"Bên bạn có kinh nghiệm trong {exp}, vì vậy {enterprise_name} có thể là đối tác phù hợp theo hướng này."
                )

        if sentences:
            return " ".join(sentences)

        return self._generic_simplification(" -> ".join(f"{k}: {v}" for k, v in steps))

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