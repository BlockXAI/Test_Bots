from datetime import datetime, timezone, timedelta

from config import TIMEZONE, BASE_URL


def _tz_offset():
    offsets = {
        "Asia/Kolkata": timedelta(hours=5, minutes=30),
        "UTC": timedelta(0),
        "US/Eastern": timedelta(hours=-5),
        "US/Pacific": timedelta(hours=-8),
        "Europe/London": timedelta(hours=0),
    }
    return offsets.get(TIMEZONE, timedelta(hours=5, minutes=30))


def _local_time():
    return datetime.now(timezone(_tz_offset())).strftime("%d %b %Y, %I:%M %p IST")


def _format_ms(ms):
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms}ms"


def _health_bar(passed, total):
    if total == 0:
        return ""
    filled = round((passed / total) * 10)
    return "\u2588" * filled + "\u2591" * (10 - filled)


def build_summary_message(run_summary):
    total = run_summary["total_scripts"]
    passed = run_summary.get("passed_scripts", sum(1 for r in run_summary["results"] if r["success"]))
    failed = run_summary.get("failed_scripts", sum(1 for r in run_summary["results"] if not r["success"]))
    all_ok = run_summary["all_passed"]

    status_text = "Everything looks healthy and happy" if all_ok else f"Heads up — {failed} service(s) need attention"
    status_icon = "\u2705" if all_ok else "\U0001f6a8"

    msg = f"{status_icon} *{status_text}*\n"
    msg += f"\U0001f4c5 {_local_time()}\n\n"

    for r in run_summary["results"]:
        report = r.get("report")
        script_name = r["script"].replace("_", " ").title()

        if r["success"]:
            s_icon = "\u2705"
        else:
            s_icon = "\u274c"

        msg += f"{s_icon} *{script_name}*\n"

        if report:
            server = report.get("server", "")
            t = report.get("total_tests", 0)
            p = report.get("passed", 0)
            f_ = report.get("failed", 0)
            rate = report.get("pass_rate", "?")
            total_ms = report.get("total_time_ms", 0)

            if server:
                msg += f"   \U0001f310 `{server}`\n"
            msg += f"   {_health_bar(p, t)}  {p}/{t} passed ({rate})\n"
            msg += f"   \u23f1 Total: {_format_ms(total_ms)}\n"

            if report.get("results"):
                passed_tests = [x for x in report["results"] if x.get("status")]
                slowest = sorted(passed_tests, key=lambda x: x.get("elapsed_ms", 0), reverse=True)[:3]
                if slowest:
                    slow_parts = [f"`{x['method']} {x['endpoint'][:25]}` {_format_ms(x['elapsed_ms'])}" for x in slowest]
                    msg += f"   \U0001f422 Slowest: {', '.join(slow_parts)}\n"

                if f_ > 0:
                    failed_tests = [x for x in report["results"] if not x.get("status")]
                    msg += f"\n   \u26a0\ufe0f *{f_} Failed endpoint(s):*\n"
                    for ft in failed_tests:
                        endpoint = ft.get("endpoint", "?")
                        method = ft.get("method", "?")
                        detail = ft.get("detail", "")
                        elapsed = ft.get("elapsed_ms", 0)
                        msg += f"   \u2022 `{method} {endpoint}`\n"
                        msg += f"     {_format_ms(elapsed)} — {_truncate(detail, 120)}\n"
        else:
            stderr = r.get("stderr", "").strip()
            if stderr:
                msg += f"   ```\n{_truncate(stderr, 300)}\n```\n"
            else:
                msg += f"   \u23f1 {r['duration_s']}s — Script crashed or timed out\n"

        msg += "\n"

    msg += f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"

    total_endpoints = 0
    total_passed_endpoints = 0
    for r in run_summary["results"]:
        report = r.get("report")
        if report:
            total_endpoints += report.get("total_tests", 0)
            total_passed_endpoints += report.get("passed", 0)

    msg += f"\U0001f4ca *{passed}/{total}* scripts passing"
    if total_endpoints > 0:
        msg += f" | *{total_passed_endpoints}/{total_endpoints}* endpoints healthy"
    msg += "\n"

    report_id = run_summary.get("report_id")
    if report_id:
        msg += f"\n\U0001f517 [Full Report]({BASE_URL}/report/{report_id})"

    if all_ok:
        msg += "\n\n\U0001f389 Nice! The bot did a clean sweep this run."
    else:
        msg += "\n\n\U0001f9ef I pinned the failing endpoints above so your team can debug faster."

    return msg


def build_failure_details(run_summary):
    lines = []
    for r in run_summary["results"]:
        if r["success"]:
            continue

        lines.append(f"\n\u274c *{r['script']}*")

        report = r.get("report")
        if report and report.get("results"):
            failed_tests = [t for t in report["results"] if not t.get("status")]
            for t in failed_tests:
                endpoint = t.get("endpoint", "?")
                method = t.get("method", "?")
                detail = t.get("detail", "no detail")
                elapsed = t.get("elapsed_ms", "?")
                lines.append(f"  \u2022 `{method} {endpoint}` ({_format_ms(elapsed)})")
                lines.append(f"    {_truncate(detail, 200)}")
        else:
            stderr = r.get("stderr", "").strip()
            if stderr:
                lines.append(f"  ```\n{_truncate(stderr, 400)}\n```")
            else:
                stdout_tail = r.get("stdout", "").strip()[-400:]
                if stdout_tail:
                    lines.append(f"  ```\n{stdout_tail}\n```")

    return "\n".join(lines)


def build_single_script_message(result):
    script_name = result["script"].replace("_", " ").title()
    s_icon = "\u2705" if result["success"] else "\u274c"
    msg = f"{s_icon} *{script_name}*\n"
    msg += f"\U0001f4c5 {_local_time()}\n\n"

    report = result.get("report")
    if report:
        server = report.get("server", "")
        t = report.get("total_tests", 0)
        p = report.get("passed", 0)
        f_ = report.get("failed", 0)
        rate = report.get("pass_rate", "?")
        total_ms = report.get("total_time_ms", 0)

        if server:
            msg += f"\U0001f310 `{server}`\n"
        msg += f"{_health_bar(p, t)}  {p}/{t} passed ({rate})\n"
        msg += f"\u23f1 Total: {_format_ms(total_ms)}\n"

        if report.get("results"):
            passed_tests = [x for x in report["results"] if x.get("status")]
            if passed_tests:
                avg_ms = sum(x.get("elapsed_ms", 0) for x in passed_tests) // len(passed_tests)
                msg += f"\U0001f4c8 Avg response: {_format_ms(avg_ms)}\n"

            slowest = sorted(passed_tests, key=lambda x: x.get("elapsed_ms", 0), reverse=True)[:3]
            if slowest:
                msg += f"\n\U0001f422 *Slowest endpoints:*\n"
                for x in slowest:
                    msg += f"  \u2022 `{x['method']} {x['endpoint'][:30]}` — {_format_ms(x['elapsed_ms'])}\n"

            if f_ > 0:
                failed_tests = [x for x in report["results"] if not x.get("status")]
                msg += f"\n\U0001f6a8 *{f_} Failed:*\n"
                for ft in failed_tests:
                    endpoint = ft.get("endpoint", "?")
                    method = ft.get("method", "?")
                    detail = ft.get("detail", "")
                    elapsed = ft.get("elapsed_ms", 0)
                    msg += f"  \u274c `{method} {endpoint}`\n"
                    msg += f"     {_format_ms(elapsed)} — {_truncate(detail, 150)}\n"
            else:
                msg += f"\n\u2705 All endpoints healthy"
    else:
        if not result["success"]:
            stderr = result.get("stderr", "").strip()
            if stderr:
                msg += f"```\n{_truncate(stderr, 400)}\n```"
            else:
                msg += f"Script crashed after {result['duration_s']}s"

    report_id = result.get("report_id")
    if report_id:
        msg += f"\n\n\U0001f517 [Full Report]({BASE_URL}/report/{report_id})"

    if result["success"]:
        msg += "\n\n\U0001f389 This product looks good right now."
    else:
        msg += "\n\n\U0001f527 A few things look off — full details are linked above."

    return msg


def _truncate(text, max_len):
    text = text.replace("\n", " ").strip()
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text
