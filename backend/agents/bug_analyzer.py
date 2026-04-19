"""
Agent 1 — Bug Analyzer
======================
Analyses the user-provided bug description and produces a structured BugAnalysis:
  title, severity, priority, steps_to_reproduce,
  expected_result, actual_result, affected_components.

Follows the MAS design contract:
  - All inputs read from disk first, state as fallback
  - LLM model always from env vars (never hardcoded)
  - Never raises — errors go into state["errors"]
  - Writes output to output/bug_analysis.json
  - Appends a structured entry to the run log
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict

from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate

from state import AgentState, BugAnalysis
from tools.analysis_tools import extract_keywords, extract_affected_components
from tools.file_tools import save_to_file, read_from_file, append_log


# ── Output paths ──────────────────────────────────────────────────────────────

_OUTPUT_FILE = "output/bug_analysis.json"


# ── Prompt ────────────────────────────────────────────────────────────────────

_PROMPT = PromptTemplate.from_template("""You are a senior QA engineer.
Analyse the bug report below and return ONLY a valid JSON object — no markdown, no explanation.

Bug Description:
{bug_description}
{code_block}
{env_block}

Detected keywords : {keywords}
Likely components : {components}

Return this exact JSON structure:
{{
  "title": "<short bug title, max 12 words>",
  "severity": "<Critical | High | Medium | Low>",
  "priority": "<P1 | P2 | P3 | P4>",
  "steps_to_reproduce": ["<step 1>", "<step 2>", "<step 3>"],
  "expected_result": "<what should happen>",
  "actual_result": "<what actually happens>",
  "affected_components": ["<Component A>", "<Component B>"]
}}

Severity: Critical=crash/data-loss, High=major feature broken, Medium=workaround exists, Low=cosmetic
Priority: P1=production blocker, P2=current sprint, P3=next sprint, P4=backlog
""")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_code_block(snippet: str | None) -> str:
    if not snippet or not snippet.strip():
        return ""
    return f"\nCode Snippet:\n```\n{snippet.strip()}\n```"


def _build_env_block(platform: str | None, version: str | None) -> str:
    parts = []
    if platform:
        parts.append(f"Platform: {platform}")
    if version:
        parts.append(f"App Version: {version}")
    return "\n".join(parts)


def _extract_json(raw: str) -> Dict[str, Any]:
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Cannot parse JSON from response:\n{raw[:400]}")


def _validate(data: Dict[str, Any]) -> BugAnalysis:
    required = {
        "title", "severity", "priority",
        "steps_to_reproduce", "expected_result",
        "actual_result", "affected_components",
    }
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Missing keys in model response: {missing}")
    for k in ("steps_to_reproduce", "affected_components"):
        if isinstance(data[k], str):
            data[k] = [data[k]]
    return BugAnalysis(
        title=str(data["title"]),
        severity=str(data["severity"]),
        priority=str(data["priority"]),
        steps_to_reproduce=[str(s) for s in data["steps_to_reproduce"]],
        expected_result=str(data["expected_result"]),
        actual_result=str(data["actual_result"]),
        affected_components=[str(c) for c in data["affected_components"]],
    )


# ── Agent node ────────────────────────────────────────────────────────────────

def bug_analyzer_node(state: AgentState) -> AgentState:
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.time()
    errors: list[str] = []
    analysis: BugAnalysis | None = None

    try:
        # Disk-first: skip LLM if output already exists from a previous run
        try:
            cached = json.loads(read_from_file(_OUTPUT_FILE))
            analysis = _validate(cached)
        except (FileNotFoundError, ValueError, KeyError):
            pass  # not cached — run the LLM

        if analysis is None:
            model      = os.getenv("OLLAMA_MODEL", "llama3:8b")
            base_url   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            num_ctx    = int(os.getenv("OLLAMA_NUM_CTX", "4096"))

            llm = OllamaLLM(
                model=model,
                base_url=base_url,
                num_ctx=num_ctx,
                num_predict=1024,
                num_gpu=99,       # use all GPU layers (Apple Silicon MPS)
                temperature=0.1,
            )

            combined = state["bug_description"] + " " + (state.get("code_snippet") or "")
            keywords   = extract_keywords(combined)
            components = extract_affected_components(combined)

            prompt = _PROMPT.format(
                bug_description=state["bug_description"],
                code_block=_build_code_block(state.get("code_snippet")),
                env_block=_build_env_block(state.get("platform"), state.get("app_version")),
                keywords=", ".join(keywords) or "none",
                components=", ".join(components),
            )

            raw = llm.invoke(prompt)
            parsed = _extract_json(raw)
            analysis = _validate(parsed)

            # Merge any pre-detected components the LLM may have missed
            for c in components:
                if c not in analysis["affected_components"] and c != "General / Unknown":
                    analysis["affected_components"].append(c)

            save_to_file(_OUTPUT_FILE, json.dumps(dict(analysis), indent=2))

        state["bug_analysis"] = analysis

    except Exception as exc:
        msg = f"BugAnalyzer: {exc}"
        errors.append(msg)
        state["errors"].append(msg)

    # Structured log entry
    append_log(state["log_path"], {
        "agent": "BugAnalyzer",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_s": round(time.time() - t0, 2),
        "input_summary": {
            "desc_length": len(state["bug_description"]),
            "has_code": bool(state.get("code_snippet")),
            "platform": state.get("platform"),
        },
        "output_summary": {
            "title": analysis["title"] if analysis else None,
            "severity": analysis["severity"] if analysis else None,
        },
        "errors": errors,
    })

    return state
