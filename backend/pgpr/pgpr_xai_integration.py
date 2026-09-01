"""
Integration script: PGPR Recommender + XAI Explainer

Xem tất cả đề xuất theo Project (multi-entity):
  python pgpr_xai_integration.py PRJ_0001
  -> In ra console + tạo file HTML (project_multi_PRJ_0001_recommendations.html) để mở trình duyệt xem.

Giải thích XAI bằng Ollama LLM (cần chạy `ollama serve` và `ollama pull llama3`):
  python pgpr_xai_integration.py PRJ_0001 --llm
  python pgpr_xai_integration.py PRJ_0001 --llm --model mistral

Trong code:
  from pgpr_xai_integration import generate_project_multi_recommendations, print_project_multi_recommendations, save_project_multi_html
  result = generate_project_multi_recommendations("PRJ_0001", limit_experts=5, limit_funders=5, limit_enterprises=5)
  print_project_multi_recommendations(result)
  save_project_multi_html(result, "my_project_recommendations.html")
"""

from pgpr_recommendation import PGPRRecommender
from pgpr_xai_explainer import PGPRExplainer
import json

ALLOWED_MULTI_PAIRS = {
    ("Enterprise", "Expert"),
    ("Enterprise", "Project"),
    ("Expert", "Enterprise"),
    ("Expert", "Expert"),
    ("Expert", "Project"),
    ("Funder", "Project"),
    ("Project", "Enterprise"),
    ("Project", "Expert"),
    ("Project", "Funder"),
}


def _ensure_allowed_pair(source_type: str, target_type: str):
    if (source_type, target_type) not in ALLOWED_MULTI_PAIRS:
        raise ValueError(f"Pair not allowed in multi mode: {source_type}->{target_type}")


def _ensure_utf8_console():
    """
    Prevent UnicodeEncodeError when printing Vietnamese on Windows consoles.
    Tries sys.stdout/stderr.reconfigure; falls back to wrapping buffers with UTF-8.
    """
    import sys
    import io

    def _wrap(stream):
        if not stream:
            return stream
        # Try Python 3.7+ reconfigure first
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
                return stream
            except Exception:
                pass
        # Fallback: wrap the underlying buffer
        buf = getattr(stream, "buffer", None)
        if buf is None:
            return stream
        try:
            return io.TextIOWrapper(buf, encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            return stream

    sys.stdout = _wrap(sys.stdout)
    sys.stderr = _wrap(sys.stderr)


def generate_explained_recommendations(
    project_id: str,
    rec_type: str = "funder",
    limit: int = 5,
    language: str = "vi",
):
    """
    Generate recommendations with XAI explanations.
    
    Args:
        project_id: Project ID to get recommendations for
        rec_type: Type of recommendation ("funder", "expert", "project")
        limit: Number of recommendations
        language: "vi" or "en"
    
    Returns:
        List of recommendations with explanations
    """
    # Initialize PGPR recommender
    pgpr = PGPRRecommender(
        max_path_length=5,
        gamma=0.99,
        top_k_paths=10,
        enable_cache=True,
    )
    
    # Initialize XAI explainer (use reasoning paths từ recommender, không truy vấn Neo4j)
    explainer = PGPRExplainer(language=language)
    
    try:
        # Get recommendations based on type
        if rec_type == "funder":
            recommendations = pgpr.recommend_funders_for_project_pgpr(
                project_id=project_id,
                limit=limit
            )
        elif rec_type == "expert":
            recommendations = pgpr.recommend_experts_for_project_pgpr(
                project_id=project_id,
                limit=limit
            )
        elif rec_type == "project":
            # For expert recommending projects
            recommendations = pgpr.recommend_projects_for_expert_pgpr(
                expert_id=project_id,  # Reuse parameter
                limit=limit
            )
        else:
            raise ValueError(f"Unknown recommendation type: {rec_type}")
        
        # Add XAI explanations to each recommendation
        explained_recs = []
        
        for rec in recommendations:
            # Build source context so XAI can query Neo4j for concrete evidence
            if rec_type in ("funder", "expert"):
                source_context = {
                    "source_id": project_id,
                    "source_type": "Project",
                }
            elif rec_type == "project":
                # In this mode, project_id actually stores expert_id (see comment above)
                source_context = {
                    "source_id": project_id,
                    "source_type": "Expert",
                }
            else:
                source_context = None

            # Generate comprehensive explanation
            explanation = explainer.explain_recommendation(
                rec,
                rec_type=rec_type,
                source_context=source_context,
            )
            
            # Combine recommendation with explanation
            explained_rec = {
                "recommendation": rec,
                "explanation": explanation,
            }
            
            explained_recs.append(explained_rec)
        
        # Generate comparison for top 2
        if len(recommendations) >= 2:
            comparison = explainer.explain_comparison(recommendations, rec_type=rec_type)
        else:
            comparison = None
        
        # Generate summary report
        summary = explainer.generate_summary_report(
            recommendations,
            rec_type=rec_type,
            project_id=project_id
        )
        
        return {
            "recommendations": explained_recs,
            "comparison": comparison,
            "summary": summary,
            "metadata": {
                "project_id": project_id,
                "rec_type": rec_type,
                "total_recommendations": len(recommendations),
            }
        }
        
    finally:
        pgpr.close()


def generate_project_multi_recommendations(
    project_id: str,
    limit_funders: int = 5,
    limit_experts: int = 5,
    limit_enterprises: int = 5,
    language: str = "vi",
    include_xai: bool = True,
    use_llm: bool = False,
    ollama_model: str = "llama3",
) -> dict:
    """
    Multi-entity: Tất cả đề xuất cho 1 Project (xem MULTI_ENTITY_PGPR_FRAMEWORK.md).

    Trả về:
    - experts: Chuyên gia phù hợp tham gia dự án
    - funders: Quỹ tài trợ phù hợp
    - enterprises: Doanh nghiệp hợp tác/chuyển giao công nghệ
    (Chỉ giữ các cặp trong ALLOWED_MULTI_PAIRS; không dùng Project->Project)

    Nếu include_xai=True (mặc định), mỗi đề xuất có thêm explanation từ XAI Explainer.
    use_llm=True: dùng Ollama LLM để tạo giải thích (cần chạy ollama serve + pull model).
    """
    pgpr = PGPRRecommender(
        max_path_length=5,
        gamma=0.99,
        top_k_paths=10,
        enable_cache=True,
    )
    explainer = (
        PGPRExplainer(
            language=language,
            use_llm=use_llm,
            ollama_model=ollama_model,
        )
        if include_xai
        else None
    )

    try:
        out = {"project_id": project_id}

        # 1) Experts cho project
        _ensure_allowed_pair("Project", "Expert")
        expert_recs = pgpr.recommend_experts_for_project_pgpr(
            project_id=project_id,
            limit=limit_experts,
        )
        explained_experts = []
        for rec in expert_recs:
            if explainer:
                explanation = explainer.explain_recommendation(
                    rec,
                    rec_type="expert",
                    source_context={"source_id": project_id, "source_type": "Project"},
                )
                explained_experts.append({"recommendation": rec, "explanation": explanation})
            else:
                explained_experts.append({"recommendation": rec, "explanation": None})
        out["experts"] = explained_experts

        # 2) Funders cho project
        _ensure_allowed_pair("Project", "Funder")
        funder_recs = pgpr.recommend_funders_for_project_pgpr(
            project_id=project_id,
            limit=limit_funders,
        )
        explained_funders = []
        for rec in funder_recs:
            if explainer:
                explanation = explainer.explain_recommendation(
                    rec,
                    rec_type="funder",
                    source_context={"source_id": project_id, "source_type": "Project"},
                )
                explained_funders.append({"recommendation": rec, "explanation": explanation})
            else:
                explained_funders.append({"recommendation": rec, "explanation": None})
        out["funders"] = explained_funders

        # 3) Enterprises cho project (hợp tác / chuyển giao công nghệ)
        _ensure_allowed_pair("Project", "Enterprise")
        enterprise_recs = pgpr.recommend_enterprises_for_project_pgpr(
            project_id=project_id,
            limit=limit_enterprises,
        )
        explained_enterprises = []
        for rec in enterprise_recs:
            if explainer:
                explanation = explainer.explain_recommendation(
                    rec,
                    rec_type="enterprise",
                    source_context={"source_id": project_id, "source_type": "Project"},
                )
                explained_enterprises.append({"recommendation": rec, "explanation": explanation})
            else:
                explained_enterprises.append({"recommendation": rec, "explanation": None})
        out["enterprises"] = explained_enterprises

        return out
    finally:
        pgpr.close()


def generate_expert_multi_recommendations(
    expert_id: str,
    limit_enterprises: int = 5,
    limit_experts: int = 5,
    limit_projects: int = 5,
    language: str = "vi",
    use_llm: bool = False,
    ollama_model: str = "llama3",
) -> dict:
    """
    Generate recommendations cho 1 Expert, bao gồm:
    - Enterprises (doanh nghiệp/đối tác phù hợp)
    - Experts (chuyên gia phù hợp để cộng tác)
    - Projects (dự án phù hợp để tham gia)
    """
    pgpr = PGPRRecommender(
        max_path_length=5,
        gamma=0.99,
        top_k_paths=10,
        enable_cache=True,
    )
    explainer = PGPRExplainer(language=language, use_llm=use_llm, ollama_model=ollama_model)

    try:
        # 1) Enterprises cho expert
        _ensure_allowed_pair("Expert", "Enterprise")
        enterprise_recs = pgpr.recommend_enterprises_for_expert_pgpr(
            expert_id=expert_id,
            limit=limit_enterprises,
        )

        explained_enterprises = []
        for rec in enterprise_recs:
            explanation = explainer.explain_recommendation(
                rec,
                rec_type="enterprise",
                source_context={"source_id": expert_id, "source_type": "Expert"},
            )
            explained_enterprises.append(
                {"recommendation": rec, "explanation": explanation}
            )

        # 2) Experts cho expert
        _ensure_allowed_pair("Expert", "Expert")
        expert_recs = pgpr.recommend_experts_for_expert_pgpr(
            expert_id=expert_id,
            limit=limit_experts,
        )

        explained_experts = []
        for rec in expert_recs:
            explanation = explainer.explain_recommendation(
                rec,
                rec_type="expert",
                source_context={"source_id": expert_id, "source_type": "Expert"},
            )
            explained_experts.append(
                {"recommendation": rec, "explanation": explanation}
            )

        # 3) Projects cho expert
        _ensure_allowed_pair("Expert", "Project")
        project_recs = pgpr.recommend_projects_for_expert_pgpr(
            expert_id=expert_id,
            limit=limit_projects,
        )

        explained_projects = []
        for rec in project_recs:
            explanation = explainer.explain_recommendation(
                rec,
                rec_type="project",
                source_context={"source_id": expert_id, "source_type": "Expert"},
            )
            explained_projects.append(
                {"recommendation": rec, "explanation": explanation}
            )

        return {
            "expert_id": expert_id,
            "enterprises": explained_enterprises,
            "experts": explained_experts,
            "projects": explained_projects,
        }
    finally:
        pgpr.close()


def generate_enterprise_multi_recommendations(
    enterprise_id: str,
    limit_experts: int = 5,
    limit_projects: int = 5,
    language: str = "vi",
    use_llm: bool = False,
    ollama_model: str = "llama3",
) -> dict:
    """
    Đề xuất cho 1 Enterprise (doanh nghiệp), gồm:
    - Experts (chuyên gia phù hợp)
    - Projects (dự án phù hợp để hợp tác)
    """
    pgpr = PGPRRecommender(
        max_path_length=5,
        gamma=0.99,
        top_k_paths=10,
        enable_cache=True,
    )
    explainer = PGPRExplainer(language=language, use_llm=use_llm, ollama_model=ollama_model)
    source_context = {"source_id": enterprise_id, "source_type": "Enterprise"}

    try:
        _ensure_allowed_pair("Enterprise", "Expert")
        expert_recs = pgpr.recommend_experts_for_enterprise_pgpr(
            enterprise_id=enterprise_id,
            limit=limit_experts,
        )
        explained_experts = []
        for rec in expert_recs:
            explanation = explainer.explain_recommendation(
                rec, rec_type="expert", source_context=source_context
            )
            explained_experts.append({"recommendation": rec, "explanation": explanation})

        _ensure_allowed_pair("Enterprise", "Project")
        project_recs = pgpr.recommend_projects_for_enterprise_pgpr(
            enterprise_id=enterprise_id,
            limit=limit_projects,
        )
        explained_projects = []
        for rec in project_recs:
            explanation = explainer.explain_recommendation(
                rec, rec_type="project", source_context=source_context
            )
            explained_projects.append({"recommendation": rec, "explanation": explanation})

        return {
            "enterprise_id": enterprise_id,
            "experts": explained_experts,
            "projects": explained_projects,
        }
    finally:
        pgpr.close()


def generate_funder_multi_recommendations(
    funder_id: str,
    limit_projects: int = 5,
    language: str = "vi",
    use_llm: bool = False,
    ollama_model: str = "llama3",
) -> dict:
    """
    Đề xuất cho 1 Funder (quỹ tài trợ), gồm:
    - Projects (dự án phù hợp để tài trợ)
    """
    pgpr = PGPRRecommender(
        max_path_length=5,
        gamma=0.99,
        top_k_paths=10,
        enable_cache=True,
    )
    explainer = PGPRExplainer(language=language, use_llm=use_llm, ollama_model=ollama_model)
    source_context = {"source_id": funder_id, "source_type": "Funder"}

    try:
        _ensure_allowed_pair("Funder", "Project")
        project_recs = pgpr.recommend_projects_for_funder_pgpr(
            funder_id=funder_id,
            limit=limit_projects,
        )
        explained_projects = []
        for rec in project_recs:
            explanation = explainer.explain_recommendation(
                rec, rec_type="project", source_context=source_context
            )
            explained_projects.append({"recommendation": rec, "explanation": explanation})

        return {
            "funder_id": funder_id,
            "projects": explained_projects,
        }
    finally:
        pgpr.close()


def print_explained_recommendations(result: dict):
    """Pretty print explained recommendations."""
    print("\n" + "="*80)
    print("PGPR RECOMMENDATIONS WITH XAI EXPLANATIONS")
    print("="*80)
    
    # Print summary
    print("\n" + result["summary"])
    
    # Print each recommendation with explanation
    for i, item in enumerate(result["recommendations"], 1):
        rec = item["recommendation"]
        exp = item["explanation"]
        
        print("\n" + "="*80)
        print(f"RECOMMENDATION #{i}")
        print("="*80)
        
        # Natural language explanation
        print("\n" + exp["natural_language"])
        
        # Path visualization
        print("\n" + exp["visualization"])
        
        # Confidence analysis
        conf = exp["confidence"]
        print(f"\n💡 CONFIDENCE ANALYSIS:")
        print(f"   Overall Confidence: {conf['total']:.1%}")
        print(f"   Level: {conf['level']}")
        print(f"   {conf['interpretation']}")
        
        # Path analysis
        if exp.get("path_analysis"):
            print(f"\n📊 PATH ANALYSIS:")
            analysis = exp["path_analysis"]
            
            if "path_categories" in analysis:
                print(f"   Categories:")
                for category, count in analysis["path_categories"].items():
                    print(f"     - {category}: {count} paths")
            
            print(f"   Average path length: {analysis.get('avg_path_length', 0):.1f} steps")
            print(f"   Shortest path: {analysis.get('shortest_path', 0)} steps")
    
    # Print comparison
    if result.get("comparison"):
        print("\n" + "="*80)
        print("COMPARISON OF TOP RECOMMENDATIONS")
        print("="*80)
        print(result["comparison"])


def print_project_multi_recommendations(multi_result: dict):
    """
    In ra console tất cả đề xuất multi cho 1 Project (experts, funders, enterprises).
    Dùng sau khi gọi generate_project_multi_recommendations(project_id).
    """
    pid = multi_result.get("project_id", "?")
    print("\n" + "="*80)
    print(f"  MULTI-ENTITY ĐỀ XUẤT CHO DỰ ÁN: {pid}")
    print("="*80)

    def _section(title: str, items: list, name_key: str = "name", score_key: str = "score"):
        print(f"\n--- {title} ---")
        if not items:
            print("  (Không có đề xuất)")
            return
        for i, item in enumerate(items, 1):
            rec = item.get("recommendation", item)
            name = rec.get(name_key) or rec.get("title") or rec.get("enterprise_id") or rec.get("project_id", "N/A")
            score = rec.get(score_key, 0)
            print(f"  {i}. {name}  (score: {score})")
            exp = item.get("explanation") or {}
            if exp.get("natural_language"):
                txt = (exp["natural_language"] or "")[:120]
                print(f"     -> {txt}..." if len((exp["natural_language"] or "")) > 120 else f"     -> {txt}")
            elif rec.get("reasoning_paths"):
                p = rec["reasoning_paths"][0].get("path", "")[:80]
                print(f"     Path: {p}...")

    _section("Chuyên gia đề xuất (Experts)", multi_result.get("experts", []))
    _section("Quỹ tài trợ đề xuất (Funders)", multi_result.get("funders", []))
    _section("Doanh nghiệp đề xuất (Enterprises)", multi_result.get("enterprises", []))
    print("\n" + "="*80)


def save_explained_recommendations_html(
    result: dict,
    output_file: str = "pgpr_recommendations_explained.html"
):
    """
    Save explained recommendations as interactive HTML.
    
    This generates a custom HTML file based on the recommendations.
    """
    # Get recommendations
    recs = result["recommendations"]
    
    if not recs:
        print("No recommendations to save.")
        return
    
    # Generate HTML content
    html_content = f"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PGPR XAI - Giải thích Gợi ý</title>
    <style>
        /* Same CSS as pgpr_xai_visualization.html */
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .content {{ padding: 30px; }}
        .recommendation-card {{
            background: #f8f9fa;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 20px;
            border-left: 5px solid #667eea;
        }}
        .rec-title {{
            font-size: 1.5em;
            color: #2c3e50;
            font-weight: bold;
            margin-bottom: 15px;
        }}
        .explanation {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin: 15px 0;
            line-height: 1.8;
        }}
        .confidence-box {{
            background: #e3f2fd;
            padding: 15px;
            border-radius: 10px;
            margin: 10px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🧠 PGPR XAI - Giải thích Gợi ý Thông minh</h1>
            <p>Dự án: {result['metadata']['project_id']}</p>
        </div>
        
        <div class="content">
    """
    
    # Add each recommendation
    for i, item in enumerate(recs, 1):
        rec = item["recommendation"]
        exp = item["explanation"]
        
        name = rec.get("name") or rec.get("title", "Unknown")
        score = rec.get("score", 0) * 100
        
        html_content += f"""
            <div class="recommendation-card">
                <div class="rec-title">
                    #{i}: {name} (Score: {score:.1f}%)
                </div>
                
                <div class="explanation">
                    <pre style="white-space: pre-wrap; font-family: inherit;">
{exp['natural_language']}
                    </pre>
                </div>
                
                <div class="confidence-box">
                    <strong>Độ tin cậy: {exp['confidence']['total']:.1%}</strong><br>
                    {exp['confidence']['interpretation']}
                </div>
            </div>
        """
    
    html_content += """
        </div>
    </div>
</body>
</html>
    """
    
    # Save to file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"\n✅ Saved explained recommendations to: {output_file}")


def save_project_multi_html(multi_result: dict, output_file: str = "project_multi_recommendations.html"):
    """
    Lưu tất cả đề xuất multi cho 1 Project ra file HTML để mở trình duyệt xem.
    """
    pid = multi_result.get("project_id", "?")
    sections = [
        ("Chuyên gia đề xuất", "experts", "name"),
        ("Quỹ tài trợ đề xuất", "funders", "name"),
        ("Doanh nghiệp đề xuất", "enterprises", "name"),
    ]

    blocks = []
    for title, key, name_key in sections:
        items = multi_result.get(key, [])
        if not items:
            blocks.append(f"<h2>{title}</h2><p>Không có đề xuất.</p>")
            continue
        cards = []
        for i, item in enumerate(items, 1):
            rec = item.get("recommendation", item)
            name = rec.get(name_key) or rec.get("name") or rec.get("title", "N/A")
            score = (rec.get("score") or 0) * 100
            exp = item.get("explanation") or {}
            nl = (exp.get("natural_language") or "").replace("<", "&lt;").replace(">", "&gt;")
            path = (rec.get("reasoning_paths") or [{}])[0].get("path", "")
            cards.append(f"""
            <div class="recommendation-card">
                <div class="rec-title">#{i}: {name} (Score: {score:.1f}%)</div>
                <div class="explanation"><pre>{nl or path}</pre></div>
            </div>""")
        blocks.append(f"<h2>{title}</h2>" + "\n".join(cards))

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Đề xuất Multi cho Project {pid}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', sans-serif; background: #f0f2f5; padding: 20px; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: white; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 24px; text-align: center; }}
        .content {{ padding: 24px; }}
        h2 {{ margin: 24px 0 12px; color: #2c3e50; font-size: 1.25em; }}
        .recommendation-card {{ background: #f8f9fa; border-radius: 12px; padding: 16px; margin-bottom: 12px; border-left: 4px solid #667eea; }}
        .rec-title {{ font-weight: bold; color: #1a202c; margin-bottom: 8px; }}
        .explanation {{ font-size: 0.9em; color: #4a5568; }}
        pre {{ white-space: pre-wrap; font-family: inherit; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Đề xuất Multi cho Dự án: {pid}</h1>
            <p>Chuyên gia · Quỹ tài trợ · Doanh nghiệp · Dự án tương tự</p>
        </div>
        <div class="content">
            {"".join(blocks)}
        </div>
    </div>
</body>
</html>"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Đã lưu: {output_file}")


def save_expert_multi_html(multi_result: dict, output_file: str = "expert_multi_recommendations.html"):
    """
    Lưu tất cả đề xuất multi cho 1 Expert ra file HTML để mở trình duyệt xem.
    Gồm 3 phần: Enterprises, Experts, Projects.
    """
    eid = multi_result.get("expert_id", "?")
    sections = [
        ("Doanh nghiệp đề xuất (Enterprises)", "enterprises", "name"),
        ("Chuyên gia đề xuất (Experts)", "experts", "name"),
        ("Dự án đề xuất (Projects)", "projects", "title"),
    ]

    blocks = []
    for title, key, name_key in sections:
        items = multi_result.get(key, [])
        if not items:
            blocks.append(f"<h2>{title}</h2><p>Không có đề xuất.</p>")
            continue
        cards = []
        for i, item in enumerate(items, 1):
            rec = item.get("recommendation", item)
            name = rec.get(name_key) or rec.get("name") or rec.get("title") or rec.get("enterprise_id") or rec.get("project_id", "N/A")
            score = (rec.get("score") or 0) * 100
            exp = item.get("explanation") or {}
            nl = (exp.get("natural_language") or "").replace("<", "&lt;").replace(">", "&gt;")
            path = (rec.get("reasoning_paths") or [{}])[0].get("path", "")
            cards.append(f"""
            <div class="recommendation-card">
                <div class="rec-title">#{i}: {name} (Score: {score:.1f}%)</div>
                <div class="explanation"><pre>{nl or path}</pre></div>
            </div>""")
        blocks.append(f"<h2>{title}</h2>" + "\n".join(cards))

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Đề xuất Multi cho Expert {eid}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', sans-serif; background: #f0f2f5; padding: 20px; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: white; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 24px; text-align: center; }}
        .content {{ padding: 24px; }}
        h2 {{ margin: 24px 0 12px; color: #2c3e50; font-size: 1.25em; }}
        .recommendation-card {{ background: #f8f9fa; border-radius: 12px; padding: 16px; margin-bottom: 12px; border-left: 4px solid #667eea; }}
        .rec-title {{ font-weight: bold; color: #1a202c; margin-bottom: 8px; }}
        .explanation {{ font-size: 0.9em; color: #4a5568; }}
        pre {{ white-space: pre-wrap; font-family: inherit; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Đề xuất Multi cho Expert: {eid}</h1>
            <p>Doanh nghiệp · Chuyên gia · Dự án phù hợp</p>
        </div>
        <div class="content">
            {"".join(blocks)}
        </div>
    </div>
</body>
</html>"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Đã lưu: {output_file}")


def save_enterprise_multi_html(multi_result: dict, output_file: str = "enterprise_multi_recommendations.html"):
    """
    Lưu tất cả đề xuất multi cho 1 Enterprise ra file HTML để mở trình duyệt xem.
    Gồm 2 phần: Experts, Projects.
    """
    eid = multi_result.get("enterprise_id", "?")
    sections = [
        ("Chuyên gia đề xuất (Experts)", "experts", "name"),
        ("Dự án đề xuất (Projects)", "projects", "title"),
    ]

    blocks = []
    for title, key, name_key in sections:
        items = multi_result.get(key, [])
        if not items:
            blocks.append(f"<h2>{title}</h2><p>Không có đề xuất.</p>")
            continue
        cards = []
        for i, item in enumerate(items, 1):
            rec = item.get("recommendation", item)
            name = rec.get(name_key) or rec.get("name") or rec.get("title") or rec.get("expert_id") or rec.get("project_id", "N/A")
            score = (rec.get("score") or 0) * 100
            exp = item.get("explanation") or {}
            nl = (exp.get("natural_language") or "").replace("<", "&lt;").replace(">", "&gt;")
            path = (rec.get("reasoning_paths") or [{}])[0].get("path", "")
            cards.append(f"""
            <div class="recommendation-card">
                <div class="rec-title">#{i}: {name} (Score: {score:.1f}%)</div>
                <div class="explanation"><pre>{nl or path}</pre></div>
            </div>""")
        blocks.append(f"<h2>{title}</h2>" + "\n".join(cards))

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Đề xuất Multi cho Enterprise {eid}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', sans-serif; background: #f0f2f5; padding: 20px; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: white; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 24px; text-align: center; }}
        .content {{ padding: 24px; }}
        h2 {{ margin: 24px 0 12px; color: #2c3e50; font-size: 1.25em; }}
        .recommendation-card {{ background: #f8f9fa; border-radius: 12px; padding: 16px; margin-bottom: 12px; border-left: 4px solid #667eea; }}
        .rec-title {{ font-weight: bold; color: #1a202c; margin-bottom: 8px; }}
        .explanation {{ font-size: 0.9em; color: #4a5568; }}
        pre {{ white-space: pre-wrap; font-family: inherit; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Đề xuất Multi cho Enterprise: {eid}</h1>
            <p>Chuyên gia · Dự án phù hợp</p>
        </div>
        <div class="content">
            {"".join(blocks)}
        </div>
    </div>
</body>
</html>"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Đã lưu: {output_file}")


def save_funder_multi_html(multi_result: dict, output_file: str = "funder_multi_recommendations.html"):
    """
    Lưu tất cả đề xuất multi cho 1 Funder ra file HTML để mở trình duyệt xem.
    Gồm 1 phần: Projects.
    """
    fid = multi_result.get("funder_id", "?")
    sections = [
        ("Dự án đề xuất (Projects)", "projects", "title"),
    ]

    blocks = []
    for title, key, name_key in sections:
        items = multi_result.get(key, [])
        if not items:
            blocks.append(f"<h2>{title}</h2><p>Không có đề xuất.</p>")
            continue
        cards = []
        for i, item in enumerate(items, 1):
            rec = item.get("recommendation", item)
            name = rec.get(name_key) or rec.get("name") or rec.get("title") or rec.get("expert_id") or rec.get("project_id", "N/A")
            score = (rec.get("score") or 0) * 100
            exp = item.get("explanation") or {}
            nl = (exp.get("natural_language") or "").replace("<", "&lt;").replace(">", "&gt;")
            path = (rec.get("reasoning_paths") or [{}])[0].get("path", "")
            cards.append(f"""
            <div class="recommendation-card">
                <div class="rec-title">#{i}: {name} (Score: {score:.1f}%)</div>
                <div class="explanation"><pre>{nl or path}</pre></div>
            </div>""")
        blocks.append(f"<h2>{title}</h2>" + "\n".join(cards))

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Đề xuất Multi cho Funder {fid}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', sans-serif; background: #f0f2f5; padding: 20px; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: white; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 24px; text-align: center; }}
        .content {{ padding: 24px; }}
        h2 {{ margin: 24px 0 12px; color: #2c3e50; font-size: 1.25em; }}
        .recommendation-card {{ background: #f8f9fa; border-radius: 12px; padding: 16px; margin-bottom: 12px; border-left: 4px solid #667eea; }}
        .rec-title {{ font-weight: bold; color: #1a202c; margin-bottom: 8px; }}
        .explanation {{ font-size: 0.9em; color: #4a5568; }}
        pre {{ white-space: pre-wrap; font-family: inherit; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Đề xuất Multi cho Funder: {fid}</h1>
            <p>Dự án phù hợp với chiến lược quỹ</p>
        </div>
        <div class="content">
            {"".join(blocks)}
        </div>
    </div>
</body>
</html>"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Đã lưu: {output_file}")


# ==========================================
# EXAMPLE USAGE
# ==========================================

if __name__ == "__main__":
    import sys

    _ensure_utf8_console()

    # Các mode CLI hỗ trợ:
    # - Project multi-entity (mặc định):
    #     python pgpr_xai_integration.py PRJ_0001 [--llm] [--model llama3]
    # - Expert multi-entity:
    #     python pgpr_xai_integration.py --expert EXP_0001
    # - Enterprise multi-entity:
    #     python pgpr_xai_integration.py --enterprise ENT_0001
    # - Funder multi-entity:
    #     python pgpr_xai_integration.py --funder FUN_0001

    args = sys.argv[1:]

    # Global flags (apply to all modes)
    use_llm = "--llm" in sys.argv
    ollama_model = "llama3"
    if "--model" in sys.argv:
        try:
            idx = sys.argv.index("--model")
            if idx + 1 < len(sys.argv):
                ollama_model = sys.argv[idx + 1]
        except ValueError:
            pass

    # Mode expert: đề xuất cho 1 Expert (enterprises, experts, projects)
    if "--expert" in args:
        try:
            idx = args.index("--expert")
            expert_id = args[idx + 1]
        except (ValueError, IndexError):
            print("Cách dùng: python pgpr_xai_integration.py --expert EXP_0001")
            sys.exit(1)

        print("Chạy Multi-Entity đề xuất cho Expert (Enterprises, Experts, Projects)...")
        print(f"Expert ID: {expert_id}\n")

        result = generate_expert_multi_recommendations(
            expert_id=expert_id,
            limit_enterprises=5,
            limit_experts=5,
            limit_projects=5,
            language="vi",
            use_llm=use_llm,
            ollama_model=ollama_model,
        )

        # In ra console đơn giản
        print(f"=== ENTERPRISES cho Expert {expert_id} ===")
        for i, item in enumerate(result.get("enterprises", []), 1):
            rec = item.get("recommendation", {})
            print(f"{i}. {rec.get('name') or rec.get('enterprise_id', 'N/A')}  (score: {rec.get('score', 0)})")

        print(f"\n=== EXPERTS cho Expert {expert_id} ===")
        for i, item in enumerate(result.get("experts", []), 1):
            rec = item.get("recommendation", {})
            print(f"{i}. {rec.get('name') or rec.get('expert_id', 'N/A')}  (score: {rec.get('score', 0)})")

        print(f"\n=== PROJECTS cho Expert {expert_id} ===")
        for i, item in enumerate(result.get("projects", []), 1):
            rec = item.get("recommendation", {})
            print(f"{i}. {rec.get('title') or rec.get('project_id', 'N/A')}  (score: {rec.get('score', 0)})")

        # Lưu HTML để xem trong trình duyệt
        html_file = f"expert_multi_{expert_id}_recommendations.html"
        save_expert_multi_html(result, html_file)

        # Lưu JSON thô để phân tích thêm nếu cần
        out_json = f"expert_multi_{expert_id}.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nĐã lưu JSON: {out_json}")
        print("Để xem đề xuất: mở file HTML trong trình duyệt:", html_file)

    # Mode enterprise: đề xuất cho 1 Enterprise (experts, projects)
    elif "--enterprise" in args:
        try:
            idx = args.index("--enterprise")
            enterprise_id = args[idx + 1]
        except (ValueError, IndexError):
            print("Cách dùng: python pgpr_xai_integration.py --enterprise ENT_0001")
            sys.exit(1)

        print("Chạy Multi-Entity đề xuất cho Enterprise (Experts, Projects)...")
        print(f"Enterprise ID: {enterprise_id}\n")

        result = generate_enterprise_multi_recommendations(
            enterprise_id=enterprise_id,
            limit_experts=5,
            limit_projects=5,
            language="vi",
            use_llm=use_llm,
            ollama_model=ollama_model,
        )

        print(f"=== EXPERTS cho Enterprise {enterprise_id} ===")
        for i, item in enumerate(result.get("experts", []), 1):
            rec = item.get("recommendation", {})
            print(f"{i}. {rec.get('name') or rec.get('expert_id', 'N/A')}  (score: {rec.get('score', 0)})")

        print(f"\n=== PROJECTS cho Enterprise {enterprise_id} ===")
        for i, item in enumerate(result.get("projects", []), 1):
            rec = item.get("recommendation", {})
            print(f"{i}. {rec.get('title') or rec.get('project_id', 'N/A')}  (score: {rec.get('score', 0)})")

        html_file = f"enterprise_multi_{enterprise_id}_recommendations.html"
        save_enterprise_multi_html(result, html_file)

        out_json = f"enterprise_multi_{enterprise_id}.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nĐã lưu JSON: {out_json}")
        print("Để xem đề xuất: mở file HTML trong trình duyệt:", html_file)

    # Mode funder: đề xuất cho 1 Funder (projects)
    elif "--funder" in args:
        try:
            idx = args.index("--funder")
            funder_id = args[idx + 1]
        except (ValueError, IndexError):
            print("Cách dùng: python pgpr_xai_integration.py --funder FUN_0001")
            sys.exit(1)

        print("Chạy Multi-Entity đề xuất cho Funder (Projects)...")
        print(f"Funder ID: {funder_id}\n")

        result = generate_funder_multi_recommendations(
            funder_id=funder_id,
            limit_projects=5,
            language="vi",
            use_llm=use_llm,
            ollama_model=ollama_model,
        )

        print(f"=== PROJECTS cho Funder {funder_id} ===")
        for i, item in enumerate(result.get("projects", []), 1):
            rec = item.get("recommendation", {})
            print(f"{i}. {rec.get('title') or rec.get('project_id', 'N/A')}  (score: {rec.get('score', 0)})")

        html_file = f"funder_multi_{funder_id}_recommendations.html"
        save_funder_multi_html(result, html_file)

        out_json = f"funder_multi_{funder_id}.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nĐã lưu JSON: {out_json}")
        print("Để xem đề xuất: mở file HTML trong trình duyệt:", html_file)

    else:
        # Mặc định: chạy multi cho 1 project và xem đề xuất
        # Cách dùng: python pgpr_xai_integration.py PRJ_0001 [--llm] [--model llama3]
        project_id = "PRJ_0001"
        positional = [a for a in args if not a.startswith("--")]
        if len(positional) >= 1 and not positional[0].startswith("--"):
            project_id = positional[0]

        print("Chạy Multi-Entity đề xuất cho Project (Experts, Funders, Enterprises)...")
        print(f"Project ID: {project_id}")
        if use_llm:
            print(f"Chế độ XAI: Ollama LLM (model: {ollama_model})")
        print()

        # Multi: tất cả đề xuất với project
        multi_result = generate_project_multi_recommendations(
            project_id=project_id,
            limit_experts=5,
            limit_funders=5,
            limit_enterprises=5,
            language="vi",
            include_xai=True,
            use_llm=use_llm,
            ollama_model=ollama_model,
        )

        # In ra console để xem
        print_project_multi_recommendations(multi_result)

        # Lưu HTML để mở trình duyệt xem
        html_file = f"project_multi_{project_id}_recommendations.html"
        save_project_multi_html(multi_result, html_file)

        # Lưu JSON
        json_file = f"project_multi_{project_id}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({
                "project_id": multi_result["project_id"],
                "experts": [x["recommendation"] for x in multi_result["experts"]],
                "funders": [x["recommendation"] for x in multi_result["funders"]],
                "enterprises": [x["recommendation"] for x in multi_result["enterprises"]],
            }, f, ensure_ascii=False, indent=2)
        print(f"Đã lưu JSON: {json_file}")

        print("\nĐể xem đề xuất: mở file HTML trong trình duyệt:", html_file)