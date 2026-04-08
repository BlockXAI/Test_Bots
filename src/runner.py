import os
import sys
import json
import glob
import subprocess
import time
from datetime import datetime

from config import SCRIPTS_DIR, REPORTS_DIR
from src.storage import save_report


def discover_scripts():
    """Find all .py files in the scripts directory."""
    pattern = os.path.join(SCRIPTS_DIR, "*.py")
    scripts = []
    for path in sorted(glob.glob(pattern)):
        basename = os.path.basename(path)
        if basename.startswith("_"):
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
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=script_dir,
        )
        duration_s = round(time.time() - start, 2)

        report_data = _find_json_report(script_dir, script_name)

        return {
            "script": script_name,
            "script_path": script_path,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_s": duration_s,
            "report": report_data,
            "success": result.returncode == 0,
            "ran_at": datetime.utcnow().isoformat(),
        }
    except subprocess.TimeoutExpired:
        duration_s = round(time.time() - start, 2)
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

    run_summary = {
        "ran_at": datetime.utcnow().isoformat(),
        "total_scripts": len(results),
        "passed_scripts": sum(1 for r in results if r["success"]),
        "failed_scripts": sum(1 for r in results if not r["success"]),
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
    summary = {"ran_at": result["ran_at"], "total_scripts": 1, "results": [result], "all_passed": result["success"]}
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
