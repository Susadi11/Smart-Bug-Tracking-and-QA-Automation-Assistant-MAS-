"""
Report generation tools: markdown formatting and validation.

Provides utilities to build professional bug reports from structured agent outputs,
with safe fallback handling for missing or incomplete data.

Tools exposed:
  - format_bug_report_markdown   : renders structured data into a clean markdown report.
  - validate_report_sections     : checks that the report contains all required sections.
  - severity_validator_tool      : cross-checks bug severity vs. root-cause likelihoods.
"""

import re
from typing import Any, Dict, List, Optional


def format_bug_report_markdown(
    bug_analysis: Optional[Dict[str, Any]] = None,
    test_cases: Optional[List[Dict[str, Any]]] = None,
    root_causes: Optional[List[Dict[str, Any]]] = None,
    llm_report: Optional[str] = None,
) -> str:
    """
    Build a clean markdown bug report from structured bug analysis data.

    Combines data from upstream agents (bug analysis, test cases, root causes)
    and an optional LLM-generated recommendations block into a unified professional
    markdown document.  The LLM content is appended directly (it already carries its
    own ``##`` section headers) rather than being wrapped in a redundant heading.
    If inputs are missing or incomplete, sensible defaults are substituted.

    Args:
        bug_analysis: Structured output from Bug Analyzer agent.
                     Expected keys: title, severity, priority, steps_to_reproduce,
                                   expected_result, actual_result, affected_components.
        test_cases:  List of test case dicts from Test Case Generator agent.
                     Expected keys: id, type, description, steps, expected.
        root_causes: List of root cause dicts from Root Cause Analyzer agent.
                     Expected keys: cause, likelihood, explanation.
        llm_report:  Optional LLM-generated markdown block (already formatted with
                     ``##`` headers).  Appended verbatim after the structured sections.

    Returns:
        A complete markdown bug report string.  Never raises — returns a safe fallback
        report containing placeholder text when inputs are missing.
    """
    if bug_analysis is None:
        bug_analysis = {}
    if test_cases is None:
        test_cases = []
    if root_causes is None:
        root_causes = []

    # Extract fields with safe defaults
    title       = str(bug_analysis.get("title",        "Unknown Bug")).strip()
    severity    = str(bug_analysis.get("severity",     "Unknown")).strip()
    priority    = str(bug_analysis.get("priority",     "Unknown")).strip()
    description = str(bug_analysis.get("actual_result",  "No description available")).strip()
    expected    = str(bug_analysis.get("expected_result", "Not specified")).strip()
    steps       = bug_analysis.get("steps_to_reproduce", [])
    components  = bug_analysis.get("affected_components", [])

    # Coerce strings to single-element lists
    if isinstance(steps, str):
        steps = [steps]
    if isinstance(components, str):
        components = [components]
    steps      = [str(s).strip() for s in steps      if s]
    components = [str(c).strip() for c in components if c]

    lines: List[str] = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines.append(f"# Bug Report: {title}\n")

    # ── Summary ───────────────────────────────────────────────────────────────
    lines.append("## Summary")
    lines.append(f"Severity: {severity} | Priority: {priority}")
    if components:
        lines.append(f"Affected Components: {', '.join(components)}")
    lines.append("")

    # ── Description ───────────────────────────────────────────────────────────
    lines.append("## Description")
    lines.append(description)
    lines.append("")

    # ── Steps to Reproduce ────────────────────────────────────────────────────
    lines.append("## Steps to Reproduce")
    if steps:
        for i, step in enumerate(steps, 1):
            lines.append(f"{i}. {step}")
    else:
        lines.append("No reproduction steps provided.")
    lines.append("")

    # ── Root Cause Analysis ───────────────────────────────────────────────────
    if root_causes:
        lines.append("## Root Cause Analysis")
        for rc in root_causes:
            cause_text  = str(rc.get("cause",        "Unknown")).strip()
            likelihood  = str(rc.get("likelihood",   "Unknown")).strip()
            explanation = str(rc.get("explanation",  "")).strip()
            if explanation:
                lines.append(f"- **{cause_text}** ({likelihood}): {explanation}")
            else:
                lines.append(f"- **{cause_text}** ({likelihood})")
        lines.append("")

    # ── Test Cases ────────────────────────────────────────────────────────────
    if test_cases:
        lines.append("## Test Cases")
        lines.append("| ID | Type | Description |")
        lines.append("|----|------|-------------|")
        for tc in test_cases:
            tc_id   = str(tc.get("id",          "").strip() or "TC-000")
            tc_type = str(tc.get("type",        "").strip() or "Unknown")
            tc_desc = str(tc.get("description", "").strip() or "No description")
            tc_desc = tc_desc.replace("|", "\\|")   # escape markdown table pipes
            lines.append(f"| {tc_id} | {tc_type} | {tc_desc} |")
        lines.append("")

    # ── LLM recommendations (appended verbatim — LLM owns its ## headers) ─────
    if llm_report and llm_report.strip():
        lines.append(llm_report.strip())
        lines.append("")
    else:
        lines.append("## Recommended Fix")
        lines.append(
            "Investigate the root cause(s) identified above and apply appropriate fixes."
        )
        lines.append("Ensure all test cases pass after implementing the fix.")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def validate_report_sections(report: str) -> Dict[str, Any]:
    """
    Validate whether the report contains all required markdown sections.

    Checks for the presence of ``##``-level headings that correspond to the three
    strictly required report sections.  Additional sections (Root Cause Analysis,
    Test Cases, Recommended Fix) are desirable but not enforced.

    Args:
        report: Markdown report string to validate.

    Returns:
        A dictionary with keys:
            - valid (bool):                True if all strictly required sections are present.
            - missing_sections (list[str]): Names of missing strictly required sections.
            - section_count (int):          Total number of ``##`` sections found.
            - sections_found (list[str]):   Names of all ``##`` sections that were found.
    """
    strictly_required = {"Summary", "Description", "Steps to Reproduce"}

    heading_pattern = r"^## (.+)$"
    found_sections: set = set()
    for match in re.finditer(heading_pattern, report, re.MULTILINE):
        found_sections.add(match.group(1).strip())

    strictly_missing = strictly_required - found_sections

    return {
        "valid":            len(strictly_missing) == 0,
        "missing_sections": sorted(list(strictly_missing)),
        "section_count":    len(found_sections),
        "sections_found":   sorted(list(found_sections)),
    }


def severity_validator_tool(
    bug_analysis: Optional[Dict[str, Any]] = None,
    root_causes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Cross-check whether the bug severity from Agent 1 aligns with the root cause
    likelihoods produced by Agent 3.

    Alignment rules:
      - A *Critical* or *High* severity bug should have at least one *High*-likelihood
        root cause.  If all causes are *Low*, the severity may be over-stated.
      - A *Low* severity bug should not have exclusively *High*-likelihood root causes.
        If it does, the severity may be under-stated.
      - *Medium* severity bugs are considered aligned regardless of likelihoods.

    Handles ``None`` inputs and missing dict keys gracefully — never raises.

    Args:
        bug_analysis: Structured output from Bug Analyzer agent (Agent 1).
                      Uses the ``severity`` key (Critical | High | Medium | Low).
        root_causes:  List of root cause dicts from Root Cause Analyzer (Agent 3).
                      Uses the ``likelihood`` key (High | Medium | Low) per item.

    Returns:
        A dictionary with keys:
            - aligned (bool):               True when severity and likelihoods agree.
            - severity (str):               The severity value from bug_analysis.
            - highest_likelihood (str):     The highest likelihood found across all causes.
            - warning (Optional[str]):      Human-readable warning when misaligned, else None.
    """
    severity_order   = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1, "Unknown": 0}
    likelihood_order = {"High": 3, "Medium": 2, "Low": 1, "Unknown": 0}

    # Safe defaults when inputs are missing
    if not bug_analysis:
        return {
            "aligned":            True,
            "severity":           "Unknown",
            "highest_likelihood": "Unknown",
            "warning":            None,
        }

    severity = str(bug_analysis.get("severity", "Unknown")).strip()

    if not root_causes:
        return {
            "aligned":            True,
            "severity":           severity,
            "highest_likelihood": "Unknown",
            "warning":            None,
        }

    likelihoods = [str(rc.get("likelihood", "Unknown")).strip() for rc in root_causes]
    highest_score = max(
        (likelihood_order.get(lh, 0) for lh in likelihoods), default=0
    )
    highest_likelihood = next(
        (lh for lh in ("High", "Medium", "Low") if likelihood_order.get(lh, 0) == highest_score),
        "Unknown",
    )

    sev_score = severity_order.get(severity, 0)
    aligned   = True
    warning: Optional[str] = None

    # Critical/High severity but all root causes are Low likelihood
    if sev_score >= 3 and highest_score <= 1:
        aligned = False
        warning = (
            f"Severity mismatch: bug is marked '{severity}' but all root causes have "
            f"'{highest_likelihood}' likelihood. Consider re-evaluating the severity."
        )
    # Low severity but all root causes are High likelihood
    elif sev_score <= 1 and highest_score >= 3:
        aligned = False
        warning = (
            f"Severity mismatch: bug is marked '{severity}' but root causes suggest "
            f"'{highest_likelihood}' likelihood issues. Consider upgrading the severity."
        )

    return {
        "aligned":            aligned,
        "severity":           severity,
        "highest_likelihood": highest_likelihood,
        "warning":            warning,
    }
