"""
Agent 4 — Bug Report Generator

Generates a final professional markdown bug report from the outputs of previous agents.
Combines bug analysis, test cases, and root causes into a unified report.

Safely handles missing data from upstream agents (especially Agent 3, which may not
be implemented yet) and generates a fallback report when needed.

Design contract:
  - LLM model is always read from environment variables.
  - Never raises — errors are appended to state["errors"].
  - Writes output to output/bug_report.md for reference.
  - Appends a structured entry to the run log.
  - Handles missing bug_analysis, test_cases, or root_causes gracefully.
"""

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Bypass system proxy for local Ollama connections (macOS / Windows).
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate

from state import AgentState
from tools.report_tools import (
    format_bug_report_markdown,
    validate_report_sections,
    severity_validator_tool,
)
from tools.file_tools import save_to_file, append_log


_OUTPUT_FILE = "output/bug_report.md"

_PROMPT = PromptTemplate.from_template("""You are a professional QA lead writing a formal bug report.

Given the following structured bug information, generate a professional markdown 
report with clear recommendations. Respond ONLY with valid markdown — no code blocks, 
no JSON, just markdown content.

## Bug Summary
Title: {bug_title}
Severity: {severity}
Priority: {priority}
Affected Components: {components}

## Analysis
Description: {description}
Expected Result: {expected}

## Reproduction
{reproduction_steps}

## Root Causes
{root_causes}

## Test Cases
{test_cases}

Generate a markdown report with these sections:
1. Executive Summary (2-3 sentences)
2. Recommended Fix (clear, actionable steps)
3. Testing Strategy (how to verify the fix)
4. Risk Assessment (any potential side effects)

Format with ## for section headers and use - for bullet points where appropriate.
Be concise and professional.
""")


def _build_reproduction_steps(steps: Optional[list] = None) -> str:
    """Format reproduction steps for the LLM prompt."""
    if not steps:
        return "No reproduction steps available."
    steps_list = [str(s).strip() for s in steps if s]
    if not steps_list:
        return "No reproduction steps available."
    return "\n".join([f"  {i}. {s}" for i, s in enumerate(steps_list, 1)])


def _build_root_causes_text(root_causes: Optional[list] = None) -> str:
    """Format root causes for the LLM prompt."""
    if not root_causes:
        return "No root cause analysis available yet."
    
    rc_list = []
    for rc in root_causes:
        if isinstance(rc, dict):
            cause = str(rc.get("cause", "")).strip()
            likelihood = str(rc.get("likelihood", "")).strip()
            explanation = str(rc.get("explanation", "")).strip()
            if cause:
                if likelihood and explanation:
                    rc_list.append(f"  - {cause} ({likelihood}): {explanation}")
                elif likelihood:
                    rc_list.append(f"  - {cause} ({likelihood})")
                else:
                    rc_list.append(f"  - {cause}")
    
    return "\n".join(rc_list) if rc_list else "No root causes identified."


def _build_test_cases_text(test_cases: Optional[list] = None) -> str:
    """Format test cases for the LLM prompt."""
    if not test_cases:
        return "No test cases available."
    
    tc_list = []
    for tc in test_cases:
        if isinstance(tc, dict):
            tc_id = str(tc.get("id", "").strip() or "TC-0")
            tc_type = str(tc.get("type", "").strip() or "Unknown")
            tc_desc = str(tc.get("description", "").strip() or "No description")
            tc_list.append(f"  - [{tc_id}] {tc_type}: {tc_desc}")
    
    return "\n".join(tc_list) if tc_list else "No test cases defined."


def bug_report_generator_node(state: AgentState) -> AgentState:
    """
    Run the Bug Report Generator agent: create a markdown report from prior agent outputs.
    
    This agent is designed to work with incomplete upstream data. If bug_analysis,
    test_cases, or root_causes are missing or None, it uses safe defaults and still
    generates a valid report.
    
    Args:
        state: The shared AgentState from the pipeline.
    
    Returns:
        Updated AgentState with bug_report populated and any errors logged.
    """
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.time()
    errors: list[str] = []
    report: Optional[str] = None
    severity_check: dict = {"aligned": True, "warning": None}

    try:
        # Extract upstream agent outputs, with safe defaults
        bug_analysis = state.get("bug_analysis")
        test_cases = state.get("test_cases")
        root_causes = state.get("root_causes")

        # Prepare title, severity, priority, etc. with fallbacks
        title = "Unknown Bug"
        severity = "Unknown"
        priority = "Unknown"
        description = "No description available."
        expected = "Not specified."
        components = []

        if bug_analysis:
            title = str(bug_analysis.get("title", "Unknown Bug")).strip()
            severity = str(bug_analysis.get("severity", "Unknown")).strip()
            priority = str(bug_analysis.get("priority", "Unknown")).strip()
            description = str(bug_analysis.get("actual_result", "No description available.")).strip()
            expected = str(bug_analysis.get("expected_result", "Not specified.")).strip()
            comps = bug_analysis.get("affected_components", [])
            if isinstance(comps, str):
                components = [comps]
            elif isinstance(comps, list):
                components = [str(c).strip() for c in comps if c]

        # Format components for prompt
        components_str = ", ".join(components) if components else "Unknown"

        # Format sections for LLM prompt
        steps_text = _build_reproduction_steps(
            bug_analysis.get("steps_to_reproduce") if bug_analysis else None
        )
        causes_text = _build_root_causes_text(root_causes)
        cases_text = _build_test_cases_text(test_cases)

        # Initialize LLM
        model = os.getenv("OLLAMA_MODEL", "phi3:mini")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "4096"))

        llm = OllamaLLM(
            model=model,
            base_url=base_url,
            num_ctx=num_ctx,
            num_predict=2048,
            num_gpu=99,
            temperature=0.3,
        )

        # Build and invoke prompt
        prompt = _PROMPT.format(
            bug_title=title,
            severity=severity,
            priority=priority,
            components=components_str,
            description=description,
            expected=expected,
            reproduction_steps=steps_text,
            root_causes=causes_text,
            test_cases=cases_text,
        )

        llm_output = llm.invoke(prompt)

        # Use the structured formatter to build the final report
        report = format_bug_report_markdown(
            bug_analysis=bug_analysis,
            test_cases=test_cases,
            root_causes=root_causes,
            llm_report=llm_output,
        )

        # Cross-check severity vs. root-cause likelihoods (custom tool — Agent 4)
        severity_check = severity_validator_tool(
            bug_analysis=bug_analysis,
            root_causes=root_causes,
        )
        if not severity_check["aligned"] and severity_check["warning"]:
            state["errors"].append(
                f"BugReportGenerator (severity): {severity_check['warning']}"
            )

        # Save report to file for debugging
        save_to_file(_OUTPUT_FILE, report)
        state["bug_report"] = report

        # Validate report structure
        validation = validate_report_sections(report)
        if not validation["valid"]:
            msg = f"Report missing sections: {', '.join(validation['missing_sections'])}"
            errors.append(msg)
            # Don't fail, just log the warning
            state["errors"].append(f"BugReportGenerator (warning): {msg}")

    except Exception as exc:
        msg = f"BugReportGenerator: {exc}"
        errors.append(msg)
        state["errors"].append(msg)
        # Generate a fallback report
        report = format_bug_report_markdown(
            bug_analysis=state.get("bug_analysis"),
            test_cases=state.get("test_cases"),
            root_causes=state.get("root_causes"),
            llm_report=None,
        )
        state["bug_report"] = report

    # Log this agent's execution
    append_log(state["log_path"], {
        "agent": "BugReportGenerator",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_s": round(time.time() - t0, 2),
        "tools_called": [
            "severity_validator_tool",
            "format_bug_report_markdown",
            "validate_report_sections",
            "save_to_file",
        ],
        "input_summary": {
            "has_bug_analysis":  bool(state.get("bug_analysis")),
            "test_case_count":   len(state.get("test_cases")   or []),
            "root_cause_count":  len(state.get("root_causes")  or []),
        },
        "output_summary": {
            "report_length":      len(report) if report else 0,
            "has_report":         bool(report),
            "severity_aligned":   severity_check.get("aligned", True),
            "severity_warning":   severity_check.get("warning"),
        },
        "errors": errors,
    })

    return state
