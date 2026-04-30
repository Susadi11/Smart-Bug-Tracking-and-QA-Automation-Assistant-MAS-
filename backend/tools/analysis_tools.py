"""
Analysis tools: keyword extraction, component detection, and static analysis.
"""

import re
import subprocess
from typing import Dict, List


# Regex patterns mapping domain keywords to software component labels.
_COMPONENT_PATTERNS = [
    (r"\b(login|logout|auth(?:entication)?|sign[- ]?in|sign[- ]?out|session|token|jwt|oauth)\b",
     "Authentication"),
    (r"\b(database|db|sql|query|migration|orm|model|schema|postgres|mysql|sqlite|mongo)\b",
     "Database"),
    (r"\b(api|endpoint|rest|graphql|request|response|http|webhook|route|controller)\b",
     "API / Backend"),
    (r"\b(ui|frontend|react|vue|angular|css|style|layout|render|component|page|form|button)\b",
     "UI / Frontend"),
    (r"\b(payment|checkout|cart|order|invoice|stripe|billing|transaction)\b",
     "Payment"),
    (r"\b(upload|download|file|image|video|storage|s3|blob|attachment|media)\b",
     "File / Storage"),
    (r"\b(email|notification|push|sms|alert|message|mail)\b",
     "Notifications"),
    (r"\b(search|filter|sort|index|elasticsearch|algolia)\b",
     "Search"),
    (r"\b(cache|redis|memcache|ttl|invalidat)\b",
     "Cache"),
    (r"\b(deploy|ci|cd|docker|kubernetes|k8s|pipeline|build|server|infra)\b",
     "DevOps / Infrastructure"),
    (r"\b(test|spec|jest|pytest|unit|integration|e2e)\b",
     "Testing"),
    (r"\b(permission|role|access|acl|rbac|admin|policy)\b",
     "Permissions / Access Control"),
]

# Common English stop words excluded from keyword extraction.
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "is", "was", "are", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "it", "its",
    "this", "that", "these", "those", "i", "we", "you", "he",
    "she", "they", "my", "our", "your", "when", "where", "what",
    "how", "why", "which", "then", "not", "no", "can", "get",
    "set", "just", "also", "from", "by", "as", "so", "if",
}


def extract_keywords(text: str) -> List[str]:
    """
    Extract up to 20 unique, meaningful keywords from a bug description.

    Tokenises the input using a regex that matches alphanumeric words of
    three or more characters, filters out common English stop words, and
    returns the remaining tokens in order of first appearance.

    Args:
        text: The raw bug description (may include code snippets).

    Returns:
        A deduplicated list of lowercase keywords, capped at 20 items.
    """
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]{2,}", text.lower())
    seen: set = set()
    keywords: List[str] = []
    for w in words:
        if w not in _STOP_WORDS and w not in seen:
            seen.add(w)
            keywords.append(w)
    return keywords[:20]


def extract_affected_components(text: str) -> List[str]:
    """
    Identify software components likely affected by a bug.

    Scans the input text against a predefined set of regex patterns that
    map domain-specific terms (e.g. 'cart', 'login', 'sql') to
    high-level component labels (e.g. 'Payment', 'Authentication',
    'Database'). Returns ``["General / Unknown"]`` when no pattern matches.

    Args:
        text: The raw bug description to analyse.

    Returns:
        A deduplicated list of matched component labels.
    """
    lower = text.lower()
    found: List[str] = []
    seen: set = set()
    for pattern, label in _COMPONENT_PATTERNS:
        if re.search(pattern, lower) and label not in seen:
            found.append(label)
            seen.add(label)
    return found if found else ["General / Unknown"]


def run_static_analysis(file_path: str) -> dict:
    """
    Run flake8 on a Python file and return structured results.

    Never raises — returns an empty issues list on failure.

    Args:
        file_path: Absolute or relative path to the Python file.

    Returns:
        Dict with keys ``issues`` (list of strings), ``issue_count`` (int),
        and ``raw_output`` (str).
    """
    try:
        proc = subprocess.run(
            ["flake8", "--max-line-length=120", file_path],
            capture_output=True, text=True, timeout=30,
        )
        raw = (proc.stdout + proc.stderr).strip()
        issues = [line for line in raw.splitlines() if line.strip()]
        return {"issues": issues, "issue_count": len(issues), "raw_output": raw}
    except Exception as exc:
        return {"issues": [], "issue_count": 0, "raw_output": str(exc)}


def generate_test_case_skeletons(bug_analysis: dict, count: int = 3) -> List[Dict[str, object]]:
    """
    Generate deterministic test-case skeletons from bug analysis.

    This is useful as:
      1) a scaffold shown to the LLM in prompts,
      2) a fallback when model output is partial or malformed.

    Args:
        bug_analysis: Agent 1 output dict.
        count: Number of skeletons to return (minimum 3 recommended).

    Returns:
        A list of skeleton dicts with keys: id, type, description, steps, expected.
    """
    title = str(bug_analysis.get("title", "Bug scenario")).strip() or "Bug scenario"
    bug_steps = bug_analysis.get("steps_to_reproduce") or []
    steps = [str(s).strip() for s in bug_steps if str(s).strip()]

    base_steps = steps if steps else ["Open the feature", "Perform the action", "Observe system behavior"]

    templates = [
        {
            "id": "TC-001",
            "type": "Positive",
            "description": f"Verify expected behavior for {title}",
            "steps": base_steps,
            "expected": str(bug_analysis.get("expected_result", "System behaves as expected")),
        },
        {
            "id": "TC-002",
            "type": "Negative",
            "description": f"Verify invalid or unexpected input handling for {title}",
            "steps": base_steps[:2] + ["Provide invalid/unsupported input and repeat action"],
            "expected": "System rejects invalid input with a clear error message and remains stable",
        },
        {
            "id": "TC-003",
            "type": "Edge",
            "description": f"Verify boundary conditions related to {title}",
            "steps": base_steps[:2] + ["Execute at boundary/extreme limits and observe behavior"],
            "expected": "System handles boundary conditions without crash or incorrect result",
        },
    ]

    return templates[:max(1, count)]


def evaluate_test_step_alignment(bug_steps: List[str], test_cases: List[dict]) -> Dict[str, object]:
    """
    Evaluate whether generated test-case steps cover the original bug steps.

    Matching is keyword-based and intentionally lightweight.

    Args:
        bug_steps: Original steps_to_reproduce from bug analysis.
        test_cases: Generated test cases.

    Returns:
        Dict with keys: coverage_ratio (float), covered_steps (int), total_steps (int),
        and uncovered_steps (list[str]).
    """
    normalized_bug_steps = [str(step).strip() for step in bug_steps if str(step).strip()]
    if not normalized_bug_steps:
        return {
            "coverage_ratio": 1.0,
            "covered_steps": 0,
            "total_steps": 0,
            "uncovered_steps": [],
        }

    all_test_steps_text = " ".join(
        " ".join(str(s) for s in (tc.get("steps") or []))
        for tc in test_cases
    ).lower()

    covered = []
    uncovered = []
    for bug_step in normalized_bug_steps:
        keywords = [k for k in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", bug_step.lower()) if k not in _STOP_WORDS]
        if not keywords:
            uncovered.append(bug_step)
            continue
        if any(keyword in all_test_steps_text for keyword in keywords):
            covered.append(bug_step)
        else:
            uncovered.append(bug_step)

    total = len(normalized_bug_steps)
    covered_count = len(covered)
    ratio = covered_count / total if total else 1.0
    return {
        "coverage_ratio": round(ratio, 2),
        "covered_steps": covered_count,
        "total_steps": total,
        "uncovered_steps": uncovered,
    }
