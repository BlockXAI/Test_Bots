from datetime import datetime, timezone, timedelta

from config import TIMEZONE


def _tz_offset():
    """Get timezone offset for display. Supports Asia/Kolkata as a common case."""
    offsets = {
        "Asia/Kolkata": timedelta(hours=5, minutes=30),
        "UTC": timedelta(0),
        "US/Eastern": timedelta(hours=-5),
        "US/Pacific": timedelta(hours=-8),
        "Europe/London": timedelta(hours=0),
    }
    return offsets.get(TIMEZONE, timedelta(hours=5, minutes=30))


def _local_time():
    return datetime.now(timezone(_tz_offset())).strftime("%Y-%m-%d %H:%M:%S %Z")


def build_summary_message(run_summary):
    """Build a Telegram-ready summary message from run results."""
    total = run_summary["total_scripts"]
    passed = run_summary.get("passed_scripts", sum(1 for r in run_summary["results"] if r["success"]))
    failed = run_summary.get("failed_scripts", sum(1 for r in run_summary["results"] if not r["success"]))
    all_ok = run_summary["all_passed"]

    icon = "\u2705" if all_ok else "\u274c"
    header = f"{icon} *E2E Test Report*\n"
    header += f"\U0001f552 {_local_time()}\n"
    header += f"\U0001f4ca Scripts: {total} | Pass: {passed} | Fail: {failed}\n"
    header += "\u2500" * 30 + "\n"

    body_lines = []
    for r in run_summary["results"]:
        s_icon = "\u2705" if r["success"] else "\u274c"
        line = f"{s_icon} *{r['script']}* — {r['duration_s']}s"

        report = r.get("report")
        if report:
            t = report.get("total_tests", "?")
            p = report.get("passed", "?")
            f_ = report.get("failed", "?")
            server = report.get("server", "")
            line += f"\n   {p}/{t} tests passed"
            if server:
                line += f" | `{server}`"

        body_lines.append(line)

    msg = header + "\n".join(body_lines)

    if not all_ok:
        msg += "\n\n\u26a0\ufe0f *Failures:*\n"
        msg += build_failure_details(run_summary)

    return msg


def build_failure_details(run_summary):
    """Build detailed failure info for debugging."""
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
                lines.append(f"  \u2022 `{method} {endpoint}` ({elapsed}ms)")
                lines.append(f"    _{_truncate(detail, 200)}_")
        else:
            stderr = r.get("stderr", "").strip()
            if stderr:
                lines.append(f"  ```\n{_truncate(stderr, 500)}\n```")
            else:
                stdout_tail = r.get("stdout", "").strip()[-500:]
                if stdout_tail:
                    lines.append(f"  ```\n{stdout_tail}\n```")
                else:
                    lines.append("  _No output captured_")

    return "\n".join(lines)


def build_single_script_message(result):
    """Build a report message for a single script run."""
    s_icon = "\u2705" if result["success"] else "\u274c"
    msg = f"{s_icon} *{result['script']}*\n"
    msg += f"\U0001f552 {_local_time()} | Duration: {result['duration_s']}s\n"

    report = result.get("report")
    if report:
        t = report.get("total_tests", "?")
        p = report.get("passed", "?")
        f_ = report.get("failed", "?")
        rate = report.get("pass_rate", "?")
        server = report.get("server", "")
        msg += f"\U0001f4ca {p}/{t} passed ({rate})"
        if server:
            msg += f" | `{server}`"
        msg += "\n"

        failed_tests = [r for r in report.get("results", []) if not r.get("status")]
        if failed_tests:
            msg += "\n\u26a0\ufe0f *Failed endpoints:*\n"
            for ft in failed_tests:
                endpoint = ft.get("endpoint", "?")
                method = ft.get("method", "?")
                detail = ft.get("detail", "")
                elapsed = ft.get("elapsed_ms", "?")
                msg += f"  \u2022 `{method} {endpoint}` ({elapsed}ms)\n"
                msg += f"    _{_truncate(detail, 150)}_\n"
    else:
        if not result["success"]:
            stderr = result.get("stderr", "").strip()
            if stderr:
                msg += f"```\n{_truncate(stderr, 500)}\n```"

    return msg


def _truncate(text, max_len):
    text = text.replace("\n", " ").strip()
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text
