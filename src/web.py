import os
import json
import glob
import html
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from config import REPORTS_DIR, TIMEZONE
from src.storage import get_report, list_reports

app = FastAPI(title="E2E Test Dashboard", docs_url=None, redoc_url=None)


def _tz_offset():
    offsets = {
        "Asia/Kolkata": timedelta(hours=5, minutes=30),
        "UTC": timedelta(0),
    }
    return offsets.get(TIMEZONE, timedelta(hours=5, minutes=30))


def _local_stamp(value=None):
    if value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.astimezone(timezone(_tz_offset())).strftime("%d %b %Y, %I:%M %p")
        except Exception:
            pass
    return datetime.now(timezone(_tz_offset())).strftime("%d %b %Y, %I:%M %p")


def _load_report_from_file(report_id):
    path = os.path.join(REPORTS_DIR, f"{report_id}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _load_report(report_id):
    db_report = get_report(report_id)
    if db_report:
        return db_report
    return _load_report_from_file(report_id)


def _list_reports_from_file(limit=20):
    pattern = os.path.join(REPORTS_DIR, "run_*.json")
    files = sorted(glob.glob(pattern), reverse=True)[:limit]
    reports = []
    for path in files:
        report_id = os.path.splitext(os.path.basename(path))[0]
        data = _load_report_from_file(report_id)
        if data:
            reports.append({"id": report_id, "data": data})
    return reports


def _recent_reports(limit=20):
    reports = list_reports(limit)
    if reports:
        return reports
    return _list_reports_from_file(limit)


def _report_metrics(data):
    total_scripts = data.get("total_scripts", 0)
    passed_scripts = data.get("passed_scripts", sum(1 for x in data.get("results", []) if x.get("success")))
    failed_scripts = data.get("failed_scripts", total_scripts - passed_scripts)
    total_endpoints = 0
    passed_endpoints = 0
    slowest = []
    for result in data.get("results", []):
        report = result.get("report")
        if not report:
            continue
        total_endpoints += report.get("total_tests", 0)
        passed_endpoints += report.get("passed", 0)
        slowest.extend(report.get("results", []))
    slowest = sorted(slowest, key=lambda x: x.get("elapsed_ms", 0), reverse=True)[:3]
    return total_scripts, passed_scripts, failed_scripts, total_endpoints, passed_endpoints, slowest


def _pretty_json(value):
    if value is None:
        return ""
    try:
        if isinstance(value, str):
            return html.escape(value)
        return html.escape(json.dumps(value, indent=2, sort_keys=True, default=str))
    except Exception:
        return html.escape(str(value))


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    reports = _recent_reports(30)
    hero_stats = {"reports": len(reports), "healthy": 0, "degraded": 0, "endpoints": 0}
    rows = ""

    for report in reports:
        data = report["data"]
        total_scripts, passed_scripts, failed_scripts, total_endpoints, passed_endpoints, slowest = _report_metrics(data)
        healthy = data.get("all_passed", False)
        hero_stats["healthy"] += 1 if healthy else 0
        hero_stats["degraded"] += 0 if healthy else 1
        hero_stats["endpoints"] += total_endpoints
        status_text = "Healthy" if healthy else "Needs Attention"
        row_class = "healthy" if healthy else "degraded"
        slow_hint = " · ".join(f"{x.get('method', '?')} {x.get('endpoint', '?')[:16]} {x.get('elapsed_ms', 0)}ms" for x in slowest[:2])
        rows += f"""
        <tr class="report-row {row_class}" onclick="window.location='/report/{report['id']}'">
            <td><span class="pill {row_class}">{status_text}</span></td>
            <td>{_local_stamp(data.get('ran_at'))}</td>
            <td>{passed_scripts}/{total_scripts}</td>
            <td>{passed_endpoints}/{total_endpoints}</td>
            <td>{slow_hint or 'No latency spikes recorded'}</td>
        </tr>
        """

    body = f"""
    <header class="hero">
        <div class="eyebrow">Chinku Reliability Console</div>
        <h1>Production health,<br><em>without the panic scroll.</em></h1>
        <p class="subtitle">A lightweight internal dashboard for scheduled e2e runs, failure triage, and fast debugging after deploys.</p>
        <div class="hero-metrics">
            <div class="metric"><span class="metric-label">Saved Runs</span><span class="metric-value">{hero_stats['reports']}</span></div>
            <div class="metric"><span class="metric-label">Healthy Runs</span><span class="metric-value">{hero_stats['healthy']}</span></div>
            <div class="metric"><span class="metric-label">Degraded Runs</span><span class="metric-value">{hero_stats['degraded']}</span></div>
            <div class="metric"><span class="metric-label">Tracked Endpoints</span><span class="metric-value">{hero_stats['endpoints']}</span></div>
        </div>
    </header>
    <section class="panel">
        <div class="panel-head">
            <div>
                <div class="section-tag">Recent activity</div>
                <h2>Latest test sessions</h2>
            </div>
            <div class="stamp">Updated {_local_stamp()}</div>
        </div>
        <table class="report-table">
            <thead>
                <tr>
                    <th>Status</th>
                    <th>When</th>
                    <th>Scripts</th>
                    <th>Endpoints</th>
                    <th>Slowest clues</th>
                </tr>
            </thead>
            <tbody>
                {rows if rows else '<tr><td colspan="5" class="empty">No test runs saved yet.</td></tr>'}
            </tbody>
        </table>
    </section>
    """
    return HTMLResponse(_page_template("Chinku Reliability Console", body))


@app.get("/report/{report_id}", response_class=HTMLResponse)
async def view_report(report_id: str):
    data = _load_report(report_id)
    if not data:
        return HTMLResponse(_page_template("Report not found", "<section class='panel'><h1>Report not found</h1></section>"), status_code=404)

    total_scripts, passed_scripts, failed_scripts, total_endpoints, passed_endpoints, slowest = _report_metrics(data)
    all_ok = data.get("all_passed", False)
    summary_cards = f"""
    <div class="hero hero-compact">
        <a href="/" class="back-link">← Back to all runs</a>
        <div class="eyebrow">Stored report</div>
        <h1>{'Everything held up nicely' if all_ok else 'A few pieces need attention'}</h1>
        <p class="subtitle">Run `{report_id}` · {_local_stamp(data.get('ran_at'))}</p>
        <div class="hero-metrics">
            <div class="metric"><span class="metric-label">Scripts Passing</span><span class="metric-value">{passed_scripts}/{total_scripts}</span></div>
            <div class="metric"><span class="metric-label">Endpoints Healthy</span><span class="metric-value">{passed_endpoints}/{total_endpoints}</span></div>
            <div class="metric"><span class="metric-label">Failed Scripts</span><span class="metric-value">{failed_scripts}</span></div>
            <div class="metric"><span class="metric-label">Run State</span><span class="metric-value">{'Healthy' if all_ok else 'Degraded'}</span></div>
        </div>
    </div>
    """

    blocks = ""
    for result in data.get("results", []):
        script_name = result.get("script", "unknown").replace("_", " ").title()
        success = result.get("success", False)
        report = result.get("report")
        tone = "healthy" if success else "degraded"
        blocks += f"<section class='panel detail-card {tone}'>"
        blocks += f"<div class='panel-head'><div><div class='section-tag'>Service</div><h2>{script_name}</h2></div><div class='stamp'>{result.get('duration_s', 0)}s</div></div>"
        if report:
            blocks += f"<p class='mono-link'>{report.get('server', '')}</p>"
            blocks += f"<div class='progress-shell'><div class='progress-bar {tone}' style='width:{report.get('passed', 0) / max(report.get('total_tests', 1), 1) * 100:.0f}%'></div></div>"
            blocks += f"<p class='report-stats'>{report.get('passed', 0)}/{report.get('total_tests', 0)} passed · {report.get('pass_rate', '?')} · {report.get('total_time_ms', 0)}ms total</p>"
            blocks += "<table class='report-table compact'><thead><tr><th></th><th>Method</th><th>Endpoint</th><th>Time</th><th>Detail</th><th>Payloads</th></tr></thead><tbody>"
            for item in report.get("results", []):
                status = item.get("status", False)
                row_class = "healthy" if status else "degraded"
                detail = html.escape(str(item.get("detail", "")))
                detail = detail[:160] + "..." if len(detail) > 160 else detail
                method = html.escape(str(item.get('method', '?')))
                endpoint = html.escape(str(item.get('endpoint', '?')))
                request_blob = _pretty_json(item.get('request'))
                response_blob = _pretty_json(item.get('response'))
                response_headers_blob = _pretty_json(item.get('response_headers'))
                traces = item.get('traces') or []
                trace_html = ""
                if traces:
                    trace_parts = []
                    for idx, trace in enumerate(traces, start=1):
                        trace_parts.append(
                            f"<details class='trace-block'><summary>Trace {idx}: {html.escape(str(trace.get('method', '?')))} {html.escape(str(trace.get('endpoint', '?')))}</summary>"
                            f"<div class='payload-grid'><div><div class='payload-label'>Request</div><pre>{_pretty_json(trace.get('request'))}</pre></div>"
                            f"<div><div class='payload-label'>Response</div><pre>{_pretty_json(trace.get('response'))}</pre></div></div></details>"
                        )
                    trace_html = "".join(trace_parts)
                payloads = (
                    "<details class='payload-block'><summary>View full input/output</summary>"
                    f"<div class='payload-grid'><div><div class='payload-label'>Request</div><pre>{request_blob or 'No request body recorded.'}</pre></div>"
                    f"<div><div class='payload-label'>Response</div><pre>{response_blob or 'No response body recorded.'}</pre></div></div>"
                    f"<div class='payload-label'>Response Headers</div><pre>{response_headers_blob or 'No response headers recorded.'}</pre>"
                    f"{trace_html}</details>"
                )
                blocks += f"<tr class='{row_class}'><td>{'✅' if status else '❌'}</td><td><code>{method}</code></td><td><code>{endpoint[:56]}</code></td><td>{item.get('elapsed_ms', 0)}ms</td><td class='detail'>{detail}</td><td class='payload-cell'>{payloads}</td></tr>"
            blocks += "</tbody></table>"
        else:
            stderr = (result.get("stderr") or "").strip()
            blocks += f"<pre class='error-box'>{stderr[:1200] if stderr else 'No structured report was produced for this script.'}</pre>"
        blocks += "</section>"

    body = summary_cards + blocks
    return HTMLResponse(_page_template(f"Report {report_id}", body))


@app.get("/health")
async def health():
    return {"status": "ok", "service": "e2e-test-bot"}


def _page_template(title, body):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,500&family=Instrument+Sans:wght@400;500;600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{ --cream:#faf8f3; --warm:#f5f2ea; --sand:#e8e0d0; --stone:#c9bfab; --ink:#1a1714; --soft:#6b6157; --ghost:#9e9386; --green:#2d6a4f; --green-light:#52b788; --green-pale:#d8f3dc; --amber:#9b5e00; --amber-light:#f4a261; --amber-pale:#fef3e2; --rose:#6b2737; --rose-light:#e07a5f; --rose-pale:#fdecea; --rule:#d4cbbe; }}
        * {{ box-sizing:border-box; margin:0; padding:0; }}
        body {{ background:var(--cream); color:var(--ink); font-family:'Instrument Sans', sans-serif; min-height:100vh; line-height:1.65; }}
        body::before {{ content:''; position:fixed; inset:0; background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.03'/%3E%3C/svg%3E"); pointer-events:none; opacity:0.35; }}
        .hero, .panel {{ max-width:1100px; margin:0 auto; padding:40px 28px; position:relative; z-index:1; }}
        .hero {{ padding-top:72px; }}
        .hero-compact {{ padding-top:48px; }}
        .eyebrow, .section-tag, .stamp {{ font-family:'DM Mono', monospace; font-size:11px; letter-spacing:0.12em; text-transform:uppercase; color:var(--green); }}
        h1 {{ font-family:'Fraunces', serif; font-size:clamp(38px, 6vw, 68px); font-weight:300; line-height:1.06; letter-spacing:-0.02em; margin:18px 0 18px; }}
        h1 em {{ color:var(--green); font-style:italic; }}
        h2 {{ font-family:'Fraunces', serif; font-size:28px; font-weight:400; margin-top:6px; }}
        .subtitle {{ max-width:760px; color:var(--soft); border-left:2px solid var(--green-light); padding-left:16px; font-size:17px; margin-bottom:28px; }}
        .hero-metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; }}
        .metric {{ background:rgba(255,255,255,0.72); backdrop-filter:blur(8px); border:1px solid var(--sand); border-radius:16px; padding:18px; box-shadow:0 10px 24px rgba(0,0,0,0.04); }}
        .metric-label {{ display:block; font-family:'DM Mono', monospace; font-size:10px; color:var(--ghost); text-transform:uppercase; letter-spacing:0.08em; margin-bottom:6px; }}
        .metric-value {{ font-size:28px; font-weight:600; color:var(--ink); }}
        .panel {{ background:rgba(255,255,255,0.7); border:1px solid var(--sand); border-radius:24px; backdrop-filter:blur(8px); margin-bottom:24px; box-shadow:0 18px 42px rgba(0,0,0,0.05); }}
        .panel-head {{ display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:22px; }}
        .report-table {{ width:100%; border-collapse:collapse; overflow:hidden; }}
        .report-table th {{ text-align:left; padding:14px 16px; border-bottom:1px solid var(--rule); color:var(--ghost); font-family:'DM Mono', monospace; font-size:10px; letter-spacing:0.08em; text-transform:uppercase; }}
        .report-table td {{ padding:14px 16px; border-bottom:1px solid rgba(212,203,190,0.65); font-size:14px; color:var(--soft); vertical-align:top; }}
        .report-row {{ cursor:pointer; transition:background 0.16s ease; }}
        .report-row:hover {{ background:rgba(255,255,255,0.65); }}
        .pill {{ display:inline-flex; padding:5px 10px; border-radius:999px; font-size:11px; font-weight:600; }}
        .pill.healthy {{ background:var(--green-pale); color:var(--green); }}
        .pill.degraded {{ background:var(--amber-pale); color:var(--amber); }}
        .empty {{ text-align:center; padding:42px; color:var(--ghost); }}
        .back-link {{ text-decoration:none; color:var(--green); font-size:13px; }}
        .mono-link {{ font-family:'DM Mono', monospace; font-size:12px; color:var(--soft); margin-bottom:12px; word-break:break-all; }}
        .progress-shell {{ width:100%; height:10px; border-radius:999px; background:var(--warm); overflow:hidden; border:1px solid var(--sand); margin:14px 0 10px; }}
        .progress-bar {{ height:100%; border-radius:999px; }}
        .progress-bar.healthy {{ background:linear-gradient(90deg,var(--green),var(--green-light)); }}
        .progress-bar.degraded {{ background:linear-gradient(90deg,var(--amber),var(--amber-light)); }}
        .report-stats {{ color:var(--soft); margin-bottom:16px; }}
        .detail-card.healthy {{ border-left:4px solid var(--green-light); }}
        .detail-card.degraded {{ border-left:4px solid var(--rose-light); }}
        .report-table.compact tr.healthy td {{ background:rgba(216,243,220,0.22); }}
        .report-table.compact tr.degraded td {{ background:rgba(253,236,234,0.45); }}
        code {{ background:var(--warm); border:1px solid var(--sand); border-radius:6px; padding:2px 6px; font-size:12px; color:var(--ink); }}
        .detail {{ max-width:420px; word-break:break-word; }}
        .payload-cell {{ min-width:320px; }}
        .payload-block, .trace-block {{ border:1px solid var(--sand); border-radius:12px; background:rgba(255,255,255,0.6); padding:8px 10px; }}
        .payload-block summary, .trace-block summary {{ cursor:pointer; color:var(--green); font-weight:600; }}
        .payload-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin-top:10px; }}
        .payload-label {{ font-family:'DM Mono', monospace; font-size:10px; text-transform:uppercase; letter-spacing:0.08em; color:var(--ghost); margin:8px 0 6px; }}
        .payload-block pre, .trace-block pre {{ background:#221d19; color:#f6efe7; border-radius:10px; padding:12px; overflow:auto; white-space:pre-wrap; word-break:break-word; font-size:12px; max-height:340px; }}
        .error-box {{ background:#221d19; color:#f7d5cd; border-radius:16px; padding:18px; overflow:auto; font-size:12px; white-space:pre-wrap; }}
        @media (max-width: 768px) {{ .hero,.panel {{ padding:24px 16px; }} .panel-head {{ flex-direction:column; }} .detail {{ max-width:220px; }} }}
    </style>
</head>
<body>
    {body}
</body>
</html>"""
