"""Test execution tool — runs pytest on a given file."""

import re
import subprocess


def run_pytest(file_path: str) -> dict:
    """
    Run pytest on a file and return structured results.

    Never raises — returns zero counts on failure.

    Args:
        file_path: Path to the test file to execute.

    Returns:
        Dict with keys: passed, failed, errors (int counts),
        and output (full pytest output string).
    """
    try:
        proc = subprocess.run(
            ["pytest", file_path, "-v", "--tb=short"],
            capture_output=True, text=True, timeout=120,
        )
        output = (proc.stdout + proc.stderr).strip()

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
