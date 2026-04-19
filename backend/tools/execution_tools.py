"""
Test execution tool — runs pytest on a given file.
"""

import re
import subprocess


def run_pytest(file_path: str) -> dict:
    """
    Run pytest on file_path and parse the summary line.
    Never raises. Returns passed/failed/errors counts and full output.
    """
    try:
        proc = subprocess.run(
            ["pytest", file_path, "-v", "--tb=short"],
            capture_output=True, text=True, timeout=120,
        )
        output = (proc.stdout + proc.stderr).strip()

        # Parse "X passed, Y failed, Z error" from the summary line
        passed = failed = errors = 0
        summary_match = re.search(
            r"(\d+) passed|(\d+) failed|(\d+) error", output
        )
        if summary_match:
            p = re.search(r"(\d+) passed", output)
            f = re.search(r"(\d+) failed", output)
            e = re.search(r"(\d+) error", output)
            passed  = int(p.group(1)) if p else 0
            failed  = int(f.group(1)) if f else 0
            errors  = int(e.group(1)) if e else 0

        return {"passed": passed, "failed": failed, "errors": errors, "output": output}
    except Exception as exc:
        return {"passed": 0, "failed": 0, "errors": 1, "output": str(exc)}
