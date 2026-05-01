"""
Agent 3 — Root Cause Analyzer

Persona: Senior Software Reliability Engineer specialising in post-incident
root cause analysis (RCA) for web and mobile applications.

Responsibility:
  Identifies the most likely TECHNICAL causes of a reported bug — such as
  validation issues, backend failures, UI rendering problems, database
  errors, or concurrency bugs — and ranks them by likelihood.

  This agent bridges Agent 1 (Bug Analyzer) and Agent 4 (Bug Report Generator)
  in the LangGraph pipeline.  It receives the full AgentState (including the
  structured bug_analysis from Agent 1) and writes its findings back to
  state["root_causes"] as a typed List[RootCause].

Tool usage (assignment requirement — each agent must use custom tools):
  1. extract_error_signals  (root_cause_tools) — pre-processes bug text for
     concrete signals (exception types, HTTP codes, null refs, crash keywords)
     BEFORE the LLM call, enriching the prompt with factual evidence.
  2. classify_cause_category (root_cause_tools) — classifies each LLM-produced
     cause into a named technical category AFTER validation, enriching the
     output JSON file for downstream agents and frontend display.
  3. score_root_cause_confidence (root_cause_tools) — assigns a keyword-overlap
     confidence score to each cause so Agent 4 can prioritise them.

Observability:
  Appends a structured JSON entry to the run log after every execution
  (success or failure), satisfying the LLMOps/AgentOps requirement.

Design contract:
  - LLM config is always read from environment variables.
  - Never raises — all exceptions are caught and appended to state["errors"].
  - Writes enriched output to output/root_causes.json for debugging.
"""

import json
import os

# Bypass system proxy for local Ollama connections (macOS / Windows).
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate

from state import AgentState, RootCause
from tools.analysis_tools import extract_keywords, extract_affected_components
from tools.file_tools import save_to_file, append_log
from tools.root_cause_tools import (
    classify_cause_category,
    extract_error_signals,
    score_root_cause_confidence,
)


_OUTPUT_FILE = "output/root_causes.json"

# ── Prompt ────────────────────────────────────────────────────────────────────
# Prompt engineering notes (for the technical report):
#
# 1. PERSONA: Explicit role ("senior software reliability engineer") grounds
#    SLMs that lack QA-specific fine-tuning — tested effective on phi3:mini.
#
# 2. TASK ISOLATION: "Your ONLY job is to identify WHY" prevents the model from
#    offering fixes or rephrasing symptoms (common SLM drift).
#
# 3. CATEGORY ANCHORING: Listing the 10 expected categories constrains the
#    model's output vocabulary and dramatically reduces hallucination on small
#    models (phi3:mini, qwen2:0.5b).
#
# 4. FORMAT CONSTRAINTS: Explicit JSON-only instruction + "Rules" block with
#    capitalisation requirement on 'likelihood' ensures _validate() succeeds
#    without extra normalisation.
#
# 5. FALLBACK INSTRUCTION: "If the bug description is minimal, still produce 3
#    plausible hypotheses" prevents empty-list responses on vague inputs.
#
# 6. ERROR SIGNALS FIELD: Pre-processed concrete signals (exception types, HTTP
#    codes) give the SLM factual anchors so it reasons from evidence rather
#    than guessing from the description alone.

_PROMPT = PromptTemplate.from_template(
    """You are a senior software reliability engineer specialising in root cause analysis (RCA).
Your ONLY job: identify WHY a bug occurred — not to fix it, not to describe symptoms.

=== Bug Report ===
Description: {bug_description}
{code_block}
{env_block}

=== Agent 1 Structured Analysis ===
Title              : {bug_title}
Severity           : {bug_severity}
Affected Components: {affected_components}
Expected Result    : {expected_result}
Actual Result      : {actual_result}

=== Pre-Processed Signals ===
Error signals      : {error_signals}
Keywords           : {keywords}

=== Allowed Root Cause Categories ===
Pick from these technical categories only:
  - Validation / Input Handling
  - Backend / API Failure
  - UI / Frontend
  - Database / Data Layer
  - Authentication / Authorization
  - Configuration / Environment
  - Concurrency / Race Condition
  - Memory / Resource Management
  - Business Logic / Algorithm
  - Third-Party / Dependency

=== Output Format ===
Return ONLY a valid JSON array — no markdown, no prose, no explanation outside the JSON.
Produce 3 to 5 root causes, ordered from most likely (High) to least likely (Low).

[
  {{
    "cause": "<root cause title, max 10 words>",
    "likelihood": "<High | Medium | Low>",
    "explanation": "<1–2 sentences: WHY this is a root cause, referencing specific signals above>"
  }}
]

=== Rules ===
- "likelihood" MUST be exactly "High", "Medium", or "Low" (capitalised first letter)
- Each cause must be a DISTINCT technical hypothesis, not a rephrasing of the same idea
- Reference at least one specific signal (exception type, HTTP code, keyword) in each explanation
- Do NOT suggest fixes — root causes only
- If the bug description is minimal, still produce 3 plausible technical hypotheses
"""
)


# ── Prompt formatting helpers ─────────────────────────────────────────────────

def _build_code_block(snippet: str | None) -> str:
    """Format an optional code snippet as a labelled markdown fence."""
    if not snippet or not snippet.strip():
        return ""
    return f"\nCode Snippet:\n```\n{snippet.strip()}\n```"


def _build_env_block(platform: str | None, version: str | None) -> str:
    """Format optional platform/version metadata for the prompt."""
    parts = []
    if platform:
        parts.append(f"Platform: {platform}")
    if version:
        parts.append(f"App Version: {version}")
    return "\n".join(parts)


def _format_error_signals(signals: Dict[str, List[str]]) -> str:
    """Render the extract_error_signals dict as a compact inline string."""
    parts = [f"{cat}: {', '.join(vals)}" for cat, vals in signals.items() if vals]
    return "; ".join(parts) if parts else "none detected"


# ── JSON extraction ───────────────────────────────────────────────────────────

def _extract_json_array(raw: str) -> List[Dict[str, Any]]:
    """
    Extract a JSON array from raw LLM output.

    Handles three common SLM output patterns:
      1. Clean ``[...]`` array.
      2. Array wrapped in markdown fences (```json ... ```).
      3. Array wrapped in an object (``{"root_causes": [...]}``)
         produced by models that ignore the format constraint.

    Args:
        raw: The full string returned by the LLM.

    Returns:
        A Python list of dicts parsed from the JSON array.

    Raises:
        ValueError: When no JSON array can be extracted.
    """
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return parsed
        for key in ("root_causes", "causes", "results", "items"):
            if key in parsed and isinstance(parsed[key], list):
                return parsed[key]
    except json.JSONDecodeError:
        pass

    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Cannot parse JSON array from LLM response:\n{raw[:400]}")


# ── Output validation ─────────────────────────────────────────────────────────

def _validate(data: List[Dict[str, Any]]) -> List[RootCause]:
    """
    Validate and normalise the parsed LLM output into typed RootCause dicts.

    Enforces that each item carries the required keys, normalises the
    ``likelihood`` casing to ``{"High", "Medium", "Low"}``, and falls back to
    ``"Medium"`` for unrecognised values so the pipeline never stalls on
    mildly non-conforming model output.

    Args:
        data: Raw list returned by ``_extract_json_array``.

    Returns:
        A validated ``List[RootCause]``.

    Raises:
        ValueError: When ``data`` is empty or an item is missing required keys.
    """
    if not data:
        raise ValueError("Root cause list is empty — model returned no items")

    valid_likelihoods = {"High", "Medium", "Low"}
    results: List[RootCause] = []

    for i, item in enumerate(data):
        missing = {"cause", "likelihood", "explanation"} - item.keys()
        if missing:
            raise ValueError(f"Item {i} missing required keys: {missing}")

        # Normalise: "high" → "High", "HIGH" → "High", unknown → "Medium"
        likelihood = str(item["likelihood"]).strip().capitalize()
        if likelihood not in valid_likelihoods:
            likelihood = "Medium"

        results.append(RootCause(
            cause=str(item["cause"]).strip(),
            likelihood=likelihood,
            explanation=str(item["explanation"]).strip(),
        ))

    return results


# ── Agent node ────────────────────────────────────────────────────────────────

def root_cause_analyzer_node(state: AgentState) -> AgentState:
    """
    LangGraph node — Agent 3: Root Cause Analyzer.

    Execution flow:
      1. [Tool] ``extract_error_signals``   — mine bug text for concrete signals.
      2. [Tool] ``extract_keywords``        — shared keyword extractor.
      3. [Tool] ``extract_affected_components`` — shared component detector.
      4. Build structured prompt using Agent 1 output + tool results.
      5. Invoke local Ollama LLM.
      6. Parse (``_extract_json_array``) and validate (``_validate``) output.
      7. [Tool] ``classify_cause_category``    — label each cause with a category.
      8. [Tool] ``score_root_cause_confidence`` — add confidence scores.
      9. Persist enriched JSON to disk; update state["root_causes"].
     10. Append structured log entry (LLMOps observability).

    Args:
        state: Shared ``AgentState`` from the LangGraph pipeline.  Expects
               ``state["bug_description"]`` to be set; all other fields are
               optional and handled gracefully when absent.

    Returns:
        The updated ``AgentState`` with ``state["root_causes"]`` populated on
        success, or unchanged (with an error in ``state["errors"]``) on failure.
    """
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.time()
    errors: List[str] = []
    root_causes: List[RootCause] | None = None
    error_signals: Dict[str, List[str]] = {}

    try:
        model    = os.getenv("OLLAMA_MODEL", "phi3:mini")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        num_ctx  = int(os.getenv("OLLAMA_NUM_CTX", "4096"))

        llm = OllamaLLM(
            model=model,
            base_url=base_url,
            num_ctx=num_ctx,
            num_predict=1024,
            num_gpu=99,
            temperature=0.1,
        )

        combined_text = (
            state["bug_description"] + " " + (state.get("code_snippet") or "")
        )

        # ── Tool calls (pre-LLM) ──────────────────────────────────────────
        error_signals = extract_error_signals(combined_text)         # custom tool
        keywords      = extract_keywords(combined_text)              # shared tool
        components    = extract_affected_components(combined_text)   # shared tool

        # Prefer Agent 1's richer component list when available
        bug_analysis = state.get("bug_analysis") or {}
        affected_str = ", ".join(
            bug_analysis.get("affected_components") or components
        )

        prompt = _PROMPT.format(
            bug_description=state["bug_description"],
            code_block=_build_code_block(state.get("code_snippet")),
            env_block=_build_env_block(state.get("platform"), state.get("app_version")),
            bug_title=bug_analysis.get("title", "Unknown"),
            bug_severity=bug_analysis.get("severity", "Unknown"),
            affected_components=affected_str,
            expected_result=bug_analysis.get("expected_result", "N/A"),
            actual_result=bug_analysis.get("actual_result", "N/A"),
            error_signals=_format_error_signals(error_signals),
            keywords=", ".join(keywords) or "none",
        )

        raw         = llm.invoke(prompt)
        parsed      = _extract_json_array(raw)
        root_causes = _validate(parsed)

        # ── Tool calls (post-LLM enrichment) ─────────────────────────────
        enriched = []
        for rc in root_causes:
            category   = classify_cause_category(rc["cause"], rc["explanation"])
            confidence = score_root_cause_confidence(
                rc["cause"], rc["explanation"], keywords, components
            )
            enriched.append({**dict(rc), "category": category, "confidence": confidence})

        save_to_file(_OUTPUT_FILE, json.dumps(enriched, indent=2))
        state["root_causes"] = root_causes

    except Exception as exc:
        msg = f"RootCauseAnalyzer: {exc}"
        errors.append(msg)
        state["errors"].append(msg)

    signals_count = sum(len(v) for v in error_signals.values())

    append_log(state["log_path"], {
        "agent": "RootCauseAnalyzer",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_s": round(time.time() - t0, 2),
        "tools_called": [
            "extract_error_signals",
            "extract_keywords",
            "extract_affected_components",
            "classify_cause_category",
            "score_root_cause_confidence",
        ],
        "input_summary": {
            "desc_length": len(state["bug_description"]),
            "has_code": bool(state.get("code_snippet")),
            "has_bug_analysis": bool(state.get("bug_analysis")),
            "error_signals_found": signals_count,
        },
        "output_summary": {
            "cause_count": len(root_causes) if root_causes else 0,
            "likelihoods": [rc["likelihood"] for rc in root_causes] if root_causes else [],
        },
        "errors": errors,
    })

    return state
