"""
Analysis tools: keyword/component extraction and static analysis.
"""

import re
import subprocess
from typing import List


# ── Keyword & component extraction ────────────────────────────────────────────

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
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]{2,}", text.lower())
    seen: set = set()
    keywords: List[str] = []
    for w in words:
        if w not in _STOP_WORDS and w not in seen:
            seen.add(w)
            keywords.append(w)
    return keywords[:20]


def extract_affected_components(text: str) -> List[str]:
    lower = text.lower()
    found: List[str] = []
    seen: set = set()
    for pattern, label in _COMPONENT_PATTERNS:
        if re.search(pattern, lower) and label not in seen:
            found.append(label)
            seen.add(label)
    return found if found else ["General / Unknown"]


# ── Static analysis (flake8) ──────────────────────────────────────────────────

def run_static_analysis(file_path: str) -> dict:
    """
    Run flake8 on file_path with --max-line-length=120.
    Never raises. Returns issues list, count, and raw output.
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
