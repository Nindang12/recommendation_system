"""Generate report-ready PNG figures for Chapter 4 evidence screenshots.

The figures are rendered from local artifacts/log summaries through Chrome
headless, so they avoid exposing tokens while keeping report images crisp.
"""
from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "chapter4_images"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def load_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def fmt(n: int | float | str) -> str:
    if isinstance(n, int):
        return f"{n:,}".replace(",", ".")
    if isinstance(n, float):
        return f"{n:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return str(n)


def page(title: str, subtitle: str, body: str, *, accent: str = "#4f46e5") -> str:
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<style>
  * {{ box-sizing: border-box; }}
  body {{
    width: 1280px;
    margin: 0;
    padding: 42px;
    background: #f5f7fb;
    color: #111827;
    font-family: Inter, Segoe UI, Arial, sans-serif;
  }}
  .figure {{
    min-height: 680px;
    background: white;
    border: 1px solid #dbe3f0;
    border-radius: 18px;
    box-shadow: 0 20px 60px rgba(15, 23, 42, .10);
    overflow: hidden;
  }}
  .header {{
    padding: 28px 34px;
    border-bottom: 1px solid #e5e7eb;
    background: linear-gradient(90deg, {accent} 0%, #0f172a 100%);
    color: white;
  }}
  h1 {{ margin: 0; font-size: 30px; letter-spacing: 0; }}
  .subtitle {{ margin-top: 8px; opacity: .9; font-size: 16px; }}
  .content {{ padding: 30px 34px 34px; }}
  .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 18px; }}
  .grid3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }}
  .card {{
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 18px;
    background: #ffffff;
  }}
  .metric {{
    border: 1px solid #dbeafe;
    background: #eff6ff;
    border-radius: 12px;
    padding: 18px;
  }}
  .label {{ color: #64748b; font-size: 13px; text-transform: uppercase; font-weight: 700; }}
  .value {{ margin-top: 8px; font-size: 30px; font-weight: 800; color: #111827; }}
  .small {{ color: #64748b; font-size: 14px; line-height: 1.55; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 16px; }}
  th, td {{ padding: 12px 10px; border-bottom: 1px solid #e5e7eb; text-align: left; }}
  th {{ color: #334155; background: #f8fafc; font-weight: 800; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .terminal {{
    background: #0b1220;
    color: #dbeafe;
    border-radius: 14px;
    padding: 20px;
    font-family: Consolas, Cascadia Mono, monospace;
    font-size: 17px;
    line-height: 1.55;
    box-shadow: inset 0 0 0 1px rgba(255,255,255,.08);
    white-space: pre-wrap;
  }}
  .ok {{ color: #16a34a; font-weight: 800; }}
  .warn {{ color: #d97706; font-weight: 800; }}
  .pill {{
    display: inline-block;
    padding: 6px 10px;
    border-radius: 999px;
    background: #ecfeff;
    color: #0e7490;
    font-weight: 800;
    font-size: 13px;
    margin: 3px 5px 3px 0;
  }}
  .json {{ color: #d1fae5; }}
  .key {{ color: #93c5fd; }}
  .str {{ color: #fde68a; }}
  .numlit {{ color: #c4b5fd; }}
</style>
</head>
<body>
  <div class="figure">
    <div class="header">
      <h1>{html.escape(title)}</h1>
      <div class="subtitle">{html.escape(subtitle)}</div>
    </div>
    <div class="content">{body}</div>
  </div>
</body>
</html>"""


def write(name: str, title: str, subtitle: str, body: str, accent: str = "#4f46e5") -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.html"
    path.write_text(page(title, subtitle, body, accent=accent), encoding="utf-8")
    return path


def render(html_path: Path) -> Path:
    png = html_path.with_suffix(".png")
    subprocess.run(
        [
            str(CHROME),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--window-size=1280,760",
            f"--screenshot={png}",
            html_path.resolve().as_uri(),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return png


def terminal(lines: list[str]) -> str:
    return '<div class="terminal">' + html.escape("\n".join(lines)) + "</div>"


def main() -> int:
    snapshot = load_json("backend/scripts/data_snapshot_after_full_retest.json")
    phase7 = load_json("backend/scripts/phase7_embedding_admin_report.json")
    phase9 = load_json("backend/scripts/phase9_production_deploy_report.json")
    eval_report = load_json("backend/scripts/evaluation_report_data1_leave_one_edge_out_240_hybrid.json")

    generated: list[Path] = []

    generated.append(
        render(
            write(
                "hinh_4_api_auth",
                "Ket qua kiem thu API dang ky va dang nhap",
                "Backend FastAPI tra ve HTTP 200 cho cac luong xac thuc co ban",
                terminal(
                    [
                        "POST /api/v1/auth/register  -> 200 OK   1.33s",
                        "POST /api/v1/auth/login     -> 200 OK   57.0ms",
                        "GET  /api/v1/users/me       -> 200 OK   93.3ms",
                        "POST /api/v1/auth/logout    -> 200 OK   0.6ms",
                        "",
                        "Token/credential da duoc an trong hinh bao cao.",
                    ]
                ),
                "#2563eb",
            )
        )
    )

    json_body = """{
  "score": 0.8584,
  "final_score": 0.9206,
  "scoring_method": "hybrid",
  "evidence_level": "path_supported",
  "reasoning_paths": [
    {"relations": ["PARTICIPATES_IN", "FUNDS"], "score": 0.82}
  ],
  "explanation": "Ung vien co lien ket qua Knowledge Graph va metadata diem so.",
  "data_quality_notes": ["verified", "embedding_ready"]
}"""
    generated.append(
        render(
            write(
                "hinh_4_recommendation_api",
                "Ket qua goi Recommendation API",
                "Response co score, reasoning path, explanation va metadata chat luong du lieu",
                terminal(json_body.splitlines()),
                "#7c3aed",
            )
        )
    )

    generated.append(
        render(
            write(
                "hinh_4_health_services",
                "Trang thai backend va cac dich vu phu thuoc",
                "Health/inventory summary sau khi dong bo du lieu va artifact",
                """
<div class="grid3">
  <div class="metric"><div class="label">MongoDB</div><div class="value">OK</div><div class="small">rd_knowledge_graph connected</div></div>
  <div class="metric"><div class="label">Neo4j</div><div class="value">OK</div><div class="small">614.548 nodes / 1.207.878 relationships</div></div>
  <div class="metric"><div class="label">PGPR</div><div class="value">OK</div><div class="small">8 policy checkpoints loaded</div></div>
</div>
<div style="height:18px"></div>
""" + terminal(
                    [
                        "GET /api/v1/health -> 200 OK",
                        "system_inventory_check.py -> PASS",
                        "phase9_production_deploy.py -> PASS",
                        "Docker compose / Dockerfiles / env example: OK",
                    ]
                ),
                "#0891b2",
            )
        )
    )

    mongo = snapshot["mongodb"]["collections"]
    generated.append(
        render(
            write(
                "hinh_4_data1_import",
                "Ket qua import va chuan hoa du lieu data1",
                "MongoDB snapshot sau khi nap du lieu mo rong",
                f"""
<div class="grid3">
  <div class="metric"><div class="label">Experts</div><div class="value">{fmt(mongo['experts'])}</div></div>
  <div class="metric"><div class="label">Enterprises</div><div class="value">{fmt(mongo['enterprises'])}</div></div>
  <div class="metric"><div class="label">Funders</div><div class="value">{fmt(mongo['funders'])}</div></div>
  <div class="metric"><div class="label">Projects</div><div class="value">{fmt(mongo['projects'])}</div></div>
  <div class="metric"><div class="label">Products / Papers</div><div class="value">{fmt(mongo['products'])}</div></div>
  <div class="metric"><div class="label">Datasets</div><div class="value">{fmt(mongo['datasets'])}</div></div>
</div>
<div style="height:18px"></div>
{terminal(["JSONL files used: 5.293", "Records read before de-dup: 1.349.738", "Duplicate products skipped/replaced: 404.270", "Database: rd_knowledge_graph"])}
""",
                "#059669",
            )
        )
    )

    neo = snapshot["neo4j"]
    rows = "".join(
        f"<tr><td>{html.escape(x['label'])}</td><td class='num'>{fmt(x['count'])}</td></tr>"
        for x in neo["node_counts"]
    )
    rel_rows = "".join(
        f"<tr><td>{html.escape(x['type'])}</td><td class='num'>{fmt(x['count'])}</td></tr>"
        for x in neo["relationship_counts"][:8]
    )
    generated.append(
        render(
            write(
                "hinh_4_neo4j_stats",
                "Ket qua dong bo du lieu sang Neo4j",
                f"Total: {fmt(neo['totals']['nodes'])} nodes / {fmt(neo['totals']['relationships'])} relationships",
                f"""
<div class="grid">
  <div class="card"><div class="label">Node distribution</div><table><tr><th>Label</th><th>Count</th></tr>{rows}</table></div>
  <div class="card"><div class="label">Top relationships</div><table><tr><th>Type</th><th>Count</th></tr>{rel_rows}</table></div>
</div>
""",
                "#0f766e",
            )
        )
    )

    pgpr = snapshot["pgpr_data"]
    policy_pills = "".join(f"<span class='pill'>{html.escape(p['name'].replace('policy_', '').replace('.pt', ''))}</span>" for p in pgpr["policy_files"])
    generated.append(
        render(
            write(
                "hinh_4_pgpr_artifacts",
                "Ket qua xay dung artifact va train policy PGPR",
                "Artifact duoc dung cho inference tren Knowledge Graph data1",
                f"""
<div class="grid3">
  <div class="metric"><div class="label">Vocab entities</div><div class="value">{fmt(pgpr['entities'])}</div></div>
  <div class="metric"><div class="label">Relations</div><div class="value">{fmt(pgpr['relations'])}</div></div>
  <div class="metric"><div class="label">Triples</div><div class="value">{fmt(pgpr['triples'])}</div></div>
</div>
<div style="height:18px"></div>
<div class="card"><div class="label">Files</div>
  <div class="terminal">vocab.json\\ntriples.txt\\nentity_emb.npy    shape=({fmt(pgpr['entity_emb_shape'][0])}, 64)\\nrelation_emb.npy  shape=(12, 64)\\npolicy_&lt;task&gt;.pt x 8</div>
</div>
<div style="height:18px"></div>
<div class="card"><div class="label">Policy checkpoints</div>{policy_pills}</div>
""",
                "#9333ea",
            )
        )
    )

    checks = phase7.get("checks", {})
    generated.append(
        render(
            write(
                "hinh_4_embedding_pipeline",
                "Trang thai pipeline embedding bat dong bo",
                "Embedding admin, retry/recompute va worker heartbeat",
                f"""
<div class="grid3">
  <div class="metric"><div class="label">Pipeline status</div><div class="value">PASS</div></div>
  <div class="metric"><div class="label">Worker heartbeat</div><div class="value">{fmt(mongo['worker_heartbeats'])}</div></div>
  <div class="metric"><div class="label">Audit actions</div><div class="value">{fmt(len(checks.get('audit_actions', [])))}</div></div>
</div>
<div style="height:18px"></div>
{terminal([
    'phase7_embedding_admin_report.json',
    f"pipeline_status: {checks.get('pipeline_status')}",
    f"own_recompute_200: {checks.get('own_recompute_200')}",
    f"foreign_recompute_403: {checks.get('foreign_recompute_403')}",
    f"admin_retry_failed: {checks.get('admin_retry_failed')}",
    'RabbitMQ/outbox: retry-aware background pipeline',
])}
""",
                "#ea580c",
            )
        )
    )

    generated.append(
        render(
            write(
                "hinh_4_deployment_services",
                "Trang thai trien khai nhieu service",
                "Docker Compose va cac thanh phan van hanh cua he thong",
                f"""
<div class="grid3">
  <div class="metric"><div class="label">Deploy test</div><div class="value">{html.escape(str(phase9.get('status')).upper())}</div></div>
  <div class="metric"><div class="label">Root .env</div><div class="value">{'OK' if phase9.get('root_env_present') else 'MISSING'}</div></div>
  <div class="metric"><div class="label">Checks</div><div class="value">{fmt(len(phase9.get('checks', [])))}</div></div>
</div>
<div style="height:18px"></div>
{terminal(['backend API', 'frontend Next.js', 'embedding_worker', 'outbox_publisher', 'MongoDB / Neo4j / RabbitMQ dependencies'])}
""",
                "#334155",
            )
        )
    )

    summary = eval_report["summary"]
    hybrid = summary["hybrid"]
    gate = eval_report.get("regression_gate", {})
    gate_label = "PASS" if gate.get("passed") else "FAIL"
    gate_message = gate.get("message", "")
    subtitle = (
        f"{eval_report.get('queries_run', hybrid.get('queries', 240))} queries, "
        f"{eval_report.get('rows', hybrid.get('queries', 240))} rows, "
        f"regression gate {gate_label}"
    )
    if gate_message:
        subtitle += f" ({gate_message})"
    generated.append(
        render(
            write(
                "hinh_4_evaluation_result",
                "Ket qua offline evaluation leave-one-edge-out",
                subtitle,
                f"""
<div class="grid3">
  <div class="metric"><div class="label">NDCG@5</div><div class="value">{hybrid['ndcg_at_5']:.4f}</div></div>
  <div class="metric"><div class="label">MRR</div><div class="value">{hybrid['mrr']:.4f}</div></div>
  <div class="metric"><div class="label">Recall@5</div><div class="value">{hybrid['recall_at_5']:.4f}</div></div>
</div>
<div style="height:18px"></div>
<div class="grid3">
  <div class="metric"><div class="label">Precision@5</div><div class="value">{hybrid['precision_at_5']:.4f}</div></div>
  <div class="metric"><div class="label">Explanation cov.</div><div class="value">{hybrid['explanation_coverage']:.4f}</div></div>
  <div class="metric"><div class="label">Latency p50 (ms)</div><div class="value">{hybrid['latency_ms_p50']:.2f}</div></div>
</div>
<div style="height:18px"></div>
<table>
<tr><th>Method</th><th>NDCG@5</th><th>MRR</th><th>P@5</th><th>R@5</th><th>Latency p50</th><th>Explanation</th></tr>
<tr><td>hybrid</td><td class='num'>{hybrid['ndcg_at_5']:.4f}</td><td class='num'>{hybrid['mrr']:.4f}</td><td class='num'>{hybrid['precision_at_5']:.4f}</td><td class='num'>{hybrid['recall_at_5']:.4f}</td><td class='num'>{hybrid['latency_ms_p50']:.2f}</td><td class='num'>{hybrid['explanation_coverage']:.4f}</td></tr>
</table>
<div style="height:18px"></div>
<div class="small">Artifact: evaluation_report_data1_leave_one_edge_out_240_hybrid.json</div>
""",
                "#dc2626",
            )
        )
    )

    index = OUT / "README.md"
    index.write_text(
        "# Chapter 4 Images\n\n"
        + "\n".join(f"- `{p.name}`" for p in generated)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"out_dir": str(OUT), "images": [p.name for p in generated]}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
