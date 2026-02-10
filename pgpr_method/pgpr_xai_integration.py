"""
Integration script: PGPR Recommender + XAI Explainer

Usage example showing how to use XAI to explain PGPR recommendations.
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
    
    # Initialize XAI explainer
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
    language: str = "vi",
) -> dict:
    """
    Generate recommendations cho 1 Project, bao gồm cả:
    - Funders (doanh nghiệp/quỹ tài trợ)
    - Experts (chuyên gia)
    Chỉ chạy PGPR 1 lần (chung 1 engine, 1 explainer).
    """
    pgpr = PGPRRecommender(
        max_path_length=5,
        gamma=0.99,
        top_k_paths=10,
        enable_cache=True,
    )
    explainer = PGPRExplainer(language=language)

    try:
        # 1) Funders cho project
        funder_recs = pgpr.recommend_funders_for_project_pgpr(
            project_id=project_id,
            limit=limit_funders,
        )

        explained_funders = []
        for rec in funder_recs:
            explanation = explainer.explain_recommendation(
                rec,
                rec_type="funder",
                source_context={"source_id": project_id, "source_type": "Project"},
            )
            explained_funders.append(
                {"recommendation": rec, "explanation": explanation}
            )

        # 2) Experts cho project
        expert_recs = pgpr.recommend_experts_for_project_pgpr(
            project_id=project_id,
            limit=limit_experts,
        )

        explained_experts = []
        for rec in expert_recs:
            explanation = explainer.explain_recommendation(
                rec,
                rec_type="expert",
                source_context={"source_id": project_id, "source_type": "Project"},
            )
            explained_experts.append(
                {"recommendation": rec, "explanation": explanation}
            )

        return {
            "project_id": project_id,
            "funders": explained_funders,
            "experts": explained_experts,
        }
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


# ==========================================
# EXAMPLE USAGE
# ==========================================

if __name__ == "__main__":
    # Example: Get funder recommendations with XAI explanations
    print("Generating PGPR recommendations with XAI explanations...")
    
    result = generate_explained_recommendations(
        project_id="PRJ_0004",
        rec_type="funder",
        limit=5,
        language="vi"
    )
    
    # Print to console
    print_explained_recommendations(result)
    
    # Save as HTML
    save_explained_recommendations_html(result, "funder_recommendations_explained.html")
    
    # Save as JSON
    with open("recommendations_with_explanations.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print("\n✅ All outputs generated successfully!")
    print("   - Console output: Above")
    print("   - HTML visualization: funder_recommendations_explained.html")
    print("   - JSON data: recommendations_with_explanations.json")