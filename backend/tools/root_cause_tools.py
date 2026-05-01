"""
Custom tools for Agent 3 — Root Cause Analyzer.

Provides three domain-specific utilities used exclusively by the Root Cause
Analyzer agent to pre-process bug reports before LLM invocation and to
enrich LLM output after validation:

  1. extract_error_signals  — scans text for concrete error indicators
  2. classify_cause_category — maps a root cause to a technical category
  3. score_root_cause_confidence — scores keyword overlap between a cause and the bug
"""

import re
from typing import Dict, List, Tuple


# ── Category classification patterns ─────────────────────────────────────────
# Ordered from most to least specific so the first match wins.
# Categories mirror the language in the tech spec: "validation issues,
# backend failures, or UI problems" plus the broader software taxonomy.

_CATEGORY_PATTERNS: List[Tuple[str, str]] = [
    (
        r"\b(null(?:pointer)?|none|undefined|nan|dereference|uninitialized|"
        r"missing.?field|required.?field|type.?error|attribute.?error)\b",
        "Validation / Input Handling",
    ),
    (
        r"\b(auth(?:entication)?|authoriz|session|token|jwt|oauth|"
        r"forbidden|401|403|sign.?in|credential|password)\b",
        "Authentication / Authorization",
    ),
    (
        r"\b(database|db|sql|query|schema|migration|orm|transaction|index|postgres|mysql|sqlite|mongo|connection.?pool)\b",
        "Database / Data Layer",
    ),
    (
        r"\b(api|endpoint|http|request|response|timeout|retry|"
        r"rate.?limit|webhook|network|dns|socket|500|502|503|504)\b",
        "Backend / API Failure",
    ),
    (
        r"\b(ui|frontend|render|display|layout|css|dom|component|"
        r"re.?render|visual|button|form|style|screen|page)\b",
        "UI / Frontend",
    ),
    (
        r"\b(config(?:uration)?|environment|env|setting|flag|"
        r"variable|secret|deploy|infra|docker|k8s)\b",
        "Configuration / Environment",
    ),
    (
        r"\b(race.?condition|concurren|thread|lock|deadlock|"
        r"async|await|mutex|semaphore|synchroni|parallel)\b",
        "Concurrency / Race Condition",
    ),
    (
        r"\b(memory|leak|heap|stack.?overflow|out.?of.?memory|oom|"
        r"buffer|cache.?invalidat|gc|garbage.?collect)\b",
        "Memory / Resource Management",
    ),
    (
        r"\b(third.?party|library|dependency|package|version|"
        r"upgrade|deprecat|sdk|plugin|integration|import)\b",
        "Third-Party / Dependency",
    ),
    (
        r"\b(logic|algorithm|calculation|formula|condition|branch|"
        r"edge.?case|off.?by.?one|overflow|underflow|rounding)\b",
        "Business Logic / Algorithm",
    ),
]

# ── Error signal extraction patterns ─────────────────────────────────────────
# Each entry maps a signal category to a regex that captures relevant tokens.

_ERROR_SIGNAL_PATTERNS: Dict[str, str] = {
    "exception_types": r"\b([A-Z][a-zA-Z]*(?:Error|Exception|Fault|Warning|Panic))\b",
    "http_codes":      r"\b([45]\d{2})\b",
    "null_refs":       r"\b(null|None|undefined|NaN|NullPointerException|TypeError)\b",
    "stack_keywords":  r"(?i)\b(traceback|stack\s*trace|caused\s*by|at line|exception in)\b",
    "crash_keywords":  r"(?i)\b(crash|freeze|hang|unresponsive|timeout|fatal|abort|SIGKILL|SIGSEGV)\b",
}


def extract_error_signals(text: str) -> Dict[str, List[str]]:
    """
    Extract concrete error signals from a bug description or code snippet.

    Scans the input for exception class names, HTTP error codes, null-reference
    keywords, stack-trace markers, and crash keywords.  The returned dict is
    formatted into the LLM prompt so the model can produce more targeted root
    cause hypotheses rather than generic guesses.

    Args:
        text: Raw bug description and/or code snippet concatenated as a single
              string.  May be empty.

    Returns:
        A dict mapping each signal category to a deduplicated list of matched
        strings (preserving original casing of the first occurrence).  Every
        key is always present; the value is an empty list when nothing matched.

        Example::

            {
                "exception_types": ["NullPointerException", "TypeError"],
                "http_codes":      ["500"],
                "null_refs":       ["null"],
                "stack_keywords":  [],
                "crash_keywords":  ["crash"],
            }

    Raises:
        Never.  Returns all-empty lists on any unexpected input.
    """
    results: Dict[str, List[str]] = {}
    for category, pattern in _ERROR_SIGNAL_PATTERNS.items():
        try:
            matches = re.findall(pattern, text)
            seen: set = set()
            unique: List[str] = []
            for m in matches:
                key = m.lower()
                if key not in seen:
                    seen.add(key)
                    unique.append(m)
            results[category] = unique
        except Exception:
            results[category] = []
    return results


def classify_cause_category(cause: str, explanation: str) -> str:
    """
    Map a root cause title and explanation to a named technical category.

    Scans the combined text of ``cause`` and ``explanation`` against an ordered
    set of domain patterns (validation, authentication, database, backend, UI,
    configuration, concurrency, memory, third-party, business logic).  The
    first matching category is returned.

    This function is called once per root cause after LLM validation to add a
    ``"category"`` field to the JSON output file, making the results easier to
    filter and display in the frontend.

    Args:
        cause:       Short root cause title produced by the LLM
                     (e.g. "Null pointer in auth module").
        explanation: Detailed explanation sentence(s) produced by the LLM.

    Returns:
        A category label string such as ``"Validation / Input Handling"`` or
        ``"Backend / API Failure"``.  Returns ``"General / Unknown"`` when no
        pattern matches.

    Raises:
        Never.
    """
    combined = (cause + " " + explanation).lower()
    for pattern, label in _CATEGORY_PATTERNS:
        try:
            if re.search(pattern, combined):
                return label
        except Exception:
            continue
    return "General / Unknown"


def score_root_cause_confidence(
    cause: str,
    explanation: str,
    keywords: List[str],
    affected_components: List[str],
) -> float:
    """
    Score the relevance of a root cause against extracted bug keywords.

    Computes how many of the keywords and affected-component labels extracted
    from the bug description appear in the cause text.  This produces a simple
    confidence score in [0.0, 1.0] that is stored in the output JSON alongside
    each root cause so downstream agents (e.g. the Bug Report Generator) can
    present the highest-confidence causes first.

    Args:
        cause:               Short root cause title (LLM output).
        explanation:         Root cause explanation (LLM output).
        keywords:            Keywords extracted by ``extract_keywords`` from
                             the bug description (Agent 1 shared tool).
        affected_components: Component labels from ``extract_affected_components``
                             or from the Agent 1 ``bug_analysis`` output.

    Returns:
        A float in [0.0, 1.0].  Returns ``0.0`` when both ``keywords`` and
        ``affected_components`` are empty.

    Raises:
        Never.
    """
    total_signals = len(keywords) + len(affected_components)
    if total_signals == 0:
        return 0.0

    combined = (cause + " " + explanation).lower()

    keyword_hits = sum(1 for kw in keywords if kw.lower() in combined)
    component_hits = sum(
        1
        for comp in affected_components
        if any(word.lower() in combined for word in comp.split())
    )

    raw_score = (keyword_hits + component_hits) / total_signals
    return round(min(raw_score, 1.0), 3)
