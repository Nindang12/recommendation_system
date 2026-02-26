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
  result = generate_project_multi_recommendations("PRJ_0001", limit_experts=5, limit_funders=5, limit_enterprises=5, limit_similar_projects=5)
  print_project_multi_recommendations(result)
  save_project_multi_html(result, "my_project_recommendations.html")
"""

from pgpr_recommendation import PGPRRecommender
from pgpr_xai_explainer import PGPRExplainer
import json


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
    limit_similar_projects: int = 5,
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
    - similar_projects: Dự án tương tự để tham khảo/hợp tác

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

        # 4) Dự án tương tự
        similar_recs = pgpr.recommend_projects_for_project_pgpr(
            project_id=project_id,
            limit=limit_similar_projects,
        )
        explained_similar = []
        for rec in similar_recs:
            if explainer:
                explanation = explainer.explain_recommendation(
                    rec,
                    rec_type="project",
                    source_context={"source_id": project_id, "source_type": "Project"},
                )
                explained_similar.append({"recommendation": rec, "explanation": explanation})
            else:
                explained_similar.append({"recommendation": rec, "explanation": None})
        out["similar_projects"] = explained_similar

        return out
    finally:
        pgpr.close()


def generate_expert_multi_recommendations(
    expert_id: str,
    limit_enterprises: int = 5,
    limit_funders: int = 5,
    limit_projects: int = 5,
    language: str = "vi",
) -> dict:
    """
    Generate recommendations cho 1 Expert, bao gồm:
    - Enterprises (doanh nghiệp/đối tác phù hợp)
    - Funders (quỹ tài trợ phù hợp)
    - Projects (dự án phù hợp để tham gia)
    """
    pgpr = PGPRRecommender(
        max_path_length=5,
        gamma=0.99,
        top_k_paths=10,
        enable_cache=True,
    )
    explainer = PGPRExplainer(language=language)

    try:
        # 1) Enterprises cho expert
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

        # 2) Funders cho expert
        funder_recs = pgpr.recommend_funders_for_expert_pgpr(
            expert_id=expert_id,
            limit=limit_funders,
        )

        explained_funders = []
        for rec in funder_recs:
            explanation = explainer.explain_recommendation(
                rec,
                rec_type="funder",
                source_context={"source_id": expert_id, "source_type": "Expert"},
            )
            explained_funders.append(
                {"recommendation": rec, "explanation": explanation}
            )

        # 3) Projects cho expert
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
            "funders": explained_funders,
            "projects": explained_projects,
        }
    finally:
        pgpr.close()


def generate_enterprise_multi_recommendations(
    enterprise_id: str,
    limit_experts: int = 5,
    limit_projects: int = 5,
    language: str = "vi",
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
    explainer = PGPRExplainer(language=language, enable_neo4j=False)
    source_context = {"source_id": enterprise_id, "source_type": "Enterprise"}

    try:
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
    limit_experts: int = 5,
    limit_projects: int = 5,
    language: str = "vi",
) -> dict:
    """
    Đề xuất cho 1 Funder (quỹ tài trợ), gồm:
    - Experts (chuyên gia phù hợp với danh mục quỹ)
    - Projects (dự án phù hợp để tài trợ)
    """
    pgpr = PGPRRecommender(
        max_path_length=5,
        gamma=0.99,
        top_k_paths=10,
        enable_cache=True,
    )
    explainer = PGPRExplainer(language=language, enable_neo4j=False)
    source_context = {"source_id": funder_id, "source_type": "Funder"}

    try:
        expert_recs = pgpr.recommend_experts_for_funder_pgpr(
            funder_id=funder_id,
            limit=limit_experts,
        )
        explained_experts = []
        for rec in expert_recs:
            explanation = explainer.explain_recommendation(
                rec, rec_type="expert", source_context=source_context
            )
            explained_experts.append({"recommendation": rec, "explanation": explanation})

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
            "experts": explained_experts,
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
    In ra console tất cả đề xuất multi cho 1 Project (experts, funders, enterprises, similar_projects).
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
    _section("Dự án tương tự (Similar Projects)", multi_result.get("similar_projects", []), name_key="title")

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
        ("Dự án tương tự", "similar_projects", "title"),
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


# ==========================================
# EXAMPLE USAGE
# ==========================================

if __name__ == "__main__":
    import sys

    # Mặc định: chạy multi cho 1 project và xem đề xuất
    # Cách dùng: python pgpr_xai_integration.py PRJ_0001 [--llm] [--model llama3]
    project_id = "PRJ_0001"
    use_llm = "--llm" in sys.argv
    ollama_model = "llama3"
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) >= 1 and not args[0].startswith("--"):
        project_id = args[0]
    if "--model" in sys.argv:
        idx = sys.argv.index("--model")
        if idx + 1 < len(sys.argv):
            ollama_model = sys.argv[idx + 1]

    print("Chạy Multi-Entity đề xuất cho Project (Experts, Funders, Enterprises, Similar Projects)...")
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
        limit_similar_projects=5,
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
            "similar_projects": [x["recommendation"] for x in multi_result["similar_projects"]],
        }, f, ensure_ascii=False, indent=2)
    print(f"Đã lưu JSON: {json_file}")

    print("\nĐể xem đề xuất: mở file HTML trong trình duyệt:", html_file)