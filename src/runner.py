import os
import sys
import json
import glob
import logging
import subprocess
import time
from datetime import datetime

from config import SCRIPTS_DIR, REPORTS_DIR
from src.storage import save_report


logger = logging.getLogger("e2e_bot.runner")


def discover_scripts():
    """Find all .py files in the scripts directory."""
    pattern = os.path.join(SCRIPTS_DIR, "*.py")
    scripts = []
    for path in sorted(glob.glob(pattern)):
        basename = os.path.basename(path)
        if basename.startswith("_") or basename == "__init__.py" or basename.endswith("_impl.py"):
            continue
        scripts.append(path)
    return scripts


def run_single_script(script_path):
    """
    Run a single e2e test script as a subprocess.
    Returns a dict with exit_code, stdout, stderr, duration, and parsed report if available.
    """
    script_name = os.path.splitext(os.path.basename(script_path))[0]
    script_dir = os.path.dirname(script_path)

    start = time.time()
    logger.info("Starting script: %s", script_name)
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=script_dir,
        )
        duration_s = round(time.time() - start, 2)

        _log_script_output(script_name, result.stdout, result.stderr)

        report_data = _extract_report(script_dir, script_name, result.stdout)
        if not report_data:
            raise ValueError(f"{script_name} did not emit a valid structured JSON report")
        success = _determine_success(result.returncode, report_data)
        logger.info(
            "Finished script: %s | exit_code=%s | success=%s | duration=%.2fs",
            script_name,
            result.returncode,
            success,
            duration_s,
        )

        return {
            "script": script_name,
            "script_path": script_path,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_s": duration_s,
            "report": report_data,
            "success": success,
            "ran_at": datetime.utcnow().isoformat(),
        }
    except subprocess.TimeoutExpired:
        duration_s = round(time.time() - start, 2)
        logger.exception("Script timed out: %s after %.2fs", script_name, duration_s)
        return {
            "script": script_name,
            "script_path": script_path,
            "exit_code": -1,
            "stdout": "",
            "stderr": "Script timed out after 600s",
            "duration_s": duration_s,
            "report": None,
            "success": False,
            "ran_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        duration_s = round(time.time() - start, 2)
        logger.exception("Script failed before producing a valid report: %s", script_name)
        return {
            "script": script_name,
            "script_path": script_path,
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "duration_s": duration_s,
            "report": None,
            "success": False,
            "ran_at": datetime.utcnow().isoformat(),
        }


def _extract_report(directory, script_name, stdout):
    report_data = _find_json_report(directory, script_name)
    if report_data:
        return report_data
    return _parse_json_from_stdout(stdout)


def _find_json_report(directory, script_name):
    """Look for a JSON report file the script may have written."""
    candidates = [
        os.path.join(directory, f"{script_name}_results.json"),
        os.path.join(directory, "test_live_server_results.json"),
    ]
    for pattern in glob.glob(os.path.join(directory, "*_results.json")):
        if pattern not in candidates:
            candidates.append(pattern)

    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                os.remove(path)
                return data
            except (json.JSONDecodeError, OSError):
                continue
    return None


def _parse_json_from_stdout(stdout):
    if not stdout:
        return None

    text = stdout.strip()
    if not text:
        return None

    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _determine_success(exit_code, report_data):
    if report_data and isinstance(report_data, dict):
        if "success" in report_data:
            return bool(report_data.get("success"))
        if "all_passed" in report_data:
            return bool(report_data.get("all_passed"))
        total = report_data.get("total_tests")
        failed = report_data.get("failed")
        if isinstance(total, int) and isinstance(failed, int):
            return failed == 0
    return exit_code == 0


def _log_script_output(script_name, stdout, stderr):
    if stdout:
        for line in stdout.splitlines():
            if line.strip():
                logger.info("[%s][stdout] %s", script_name, line)
    if stderr:
        for line in stderr.splitlines():
            if line.strip():
                logger.warning("[%s][stderr] %s", script_name, line)


def run_all_scripts():
    """Run every discovered script and collect results."""
    scripts = discover_scripts()
    if not scripts:
        return {
            "ran_at": datetime.utcnow().isoformat(),
            "total_scripts": 0,
            "results": [],
            "all_passed": True,
        }

    results = []
    for script_path in scripts:
        result = run_single_script(script_path)
        results.append(result)

    all_passed = all(r["success"] for r in results)
    total_tests = sum(r.get("report", {}).get("total_tests", 0) for r in results if r.get("report"))
    total_passed = sum(r.get("report", {}).get("passed", 0) for r in results if r.get("report"))
    total_failed = sum(r.get("report", {}).get("failed", 0) for r in results if r.get("report"))

    run_summary = {
        "ran_at": datetime.utcnow().isoformat(),
        "total_scripts": len(results),
        "passed_scripts": sum(1 for r in results if r["success"]),
        "failed_scripts": sum(1 for r in results if not r["success"]),
        "total_tests": total_tests,
        "passed": total_passed,
        "failed": total_failed,
        "results": results,
        "all_passed": all_passed,
    }

    report_id = _save_run_report(run_summary)
    run_summary["report_id"] = report_id
    return run_summary


def run_script_by_name(name):
    """Run a single script by its filename (without .py)."""
    script_path = os.path.join(SCRIPTS_DIR, f"{name}.py")
    if not os.path.isfile(script_path):
        return None
    result = run_single_script(script_path)
    report = result.get("report") or {}
    summary = {
        "ran_at": result["ran_at"],
        "total_scripts": 1,
        "passed_scripts": 1 if result["success"] else 0,
        "failed_scripts": 0 if result["success"] else 1,
        "total_tests": report.get("total_tests", 0),
        "passed": report.get("passed", 0),
        "failed": report.get("failed", 0),
        "results": [result],
        "all_passed": result["success"],
    }
    report_id = _save_run_report(summary)
    result["report_id"] = report_id
    return result


def _save_run_report(summary):
    """Persist run report to the reports directory. Returns the report_id."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report_id = f"run_{ts}"
    path = os.path.join(REPORTS_DIR, f"{report_id}.json")
    with open(path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    save_report(report_id, summary)
    return report_id
