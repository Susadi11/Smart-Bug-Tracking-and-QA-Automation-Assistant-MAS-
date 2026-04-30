"""
Agent 2 — Test Case Generator

Consumes Agent 1 bug_analysis and produces structured test cases.

Design contract:
  - Never raises — appends errors to state["errors"].
  - Returns 3-5 test cases whenever possible.
  - Writes output to output/test_cases.json for debugging.
  - Appends a structured entry to the run log.
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

from langchain_core.prompts import PromptTemplate
from langchain_ollama import OllamaLLM

from state import AgentState, TestCase
from tools.analysis_tools import generate_test_case_skeletons, evaluate_test_step_alignment
from tools.file_tools import append_log, save_to_file


_OUTPUT_FILE = "output/test_cases.json"

_PROMPT = PromptTemplate.from_template("""You are a senior QA test engineer.
Based on the bug analysis below, generate exactly 3 to 5 practical test cases.

Bug Analysis JSON:
{bug_analysis_json}

Reference templates (for style only):
{template_json}

Return ONLY valid JSON in this exact structure:
{{
  "test_cases": [
    {{
      "id": "TC-001",
      "type": "Positive",
      "description": "<short description>",
      "steps": ["<step 1>", "<step 2>", "<step 3>"],
      "expected": "<expected result>"
    }}
  ]
}}

Rules:
- type must be one of: Positive, Negative, Edge
- steps must be actionable and concise
- test cases must reflect bug steps and affected components
- return JSON only, no markdown or explanations
""")


def _extract_json(raw: str) -> Dict[str, Any]:
    """Extract JSON object from LLM output, with multiple fallback strategies."""
    # Strategy 1: Try direct parse
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Find first { and attempt to build valid JSON by matching braces
    start_idx = cleaned.find("{")
    if start_idx != -1:
        for end_idx in range(len(cleaned), start_idx, -1):
            candidate = cleaned[start_idx:end_idx]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    
    # Strategy 3: Try extracting "test_cases": [ ... ] array part
    match = re.search(r'"test_cases"\s*:\s*\[.*\]', cleaned, re.DOTALL)
    if match:
        try:
            partial = "{" + match.group() + "}"
            return json.loads(partial)
        except json.JSONDecodeError:
            pass
    
    raise ValueError(f"Cannot parse JSON from response:\n{raw[:500]}")


def _normalize_type(value: str) -> str:
    """Normalize raw type labels to Positive / Negative / Edge."""
    raw = (value or "").strip().lower()
    if raw.startswith("pos"):
        return "Positive"
    if raw.startswith("neg"):
        return "Negative"
    if raw.startswith("edge"):
        return "Edge"
    return "Edge"


def _validate_test_case(item: Dict[str, Any], index: int) -> TestCase:
    """Validate and coerce a single test case item."""
    required = {"id", "type", "description", "steps", "expected"}
    missing = required - item.keys()
    if missing:
        raise ValueError(f"Test case #{index} missing keys: {missing}")

    steps = item.get("steps")
    if isinstance(steps, str):
        steps = [steps]
    if not isinstance(steps, list) or not steps:
        raise ValueError(f"Test case #{index} has invalid or empty steps")

    return TestCase(
        id=str(item["id"]).strip() or f"TC-{index:03d}",
        type=_normalize_type(str(item["type"])),
        description=str(item["description"]).strip(),
        steps=[str(step).strip() for step in steps if str(step).strip()],
        expected=str(item["expected"]).strip(),
    )


def _validate_cases(payload: Dict[str, Any]) -> List[TestCase]:
    """Validate model payload and return a typed list of test cases."""
    if "test_cases" not in payload:
        raise ValueError("Missing 'test_cases' in model response")
    raw_cases = payload["test_cases"]
    if not isinstance(raw_cases, list):
        raise ValueError("'test_cases' must be a list")

    validated = [_validate_test_case(item, i + 1) for i, item in enumerate(raw_cases)]
    if len(validated) < 3:
        raise ValueError("At least 3 test cases are required")
    if len(validated) > 5:
        validated = validated[:5]

    return validated


def test_case_generator_node(state: AgentState) -> AgentState:
    """Run Agent 2 to generate test cases from bug analysis."""
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.time()
    errors: List[str] = []
    generated: List[TestCase] = []
    alignment: Dict[str, Any] = {}

    try:
        bug_analysis = state.get("bug_analysis")
        if not bug_analysis:
            raise ValueError("Missing bug_analysis from Agent 1")

        model = os.getenv("OLLAMA_MODEL", "phi3:mini")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "4096"))

        llm = OllamaLLM(
            model=model,
            base_url=base_url,
            num_ctx=num_ctx,
            num_predict=2048,
            num_gpu=99,
            temperature=0.2,
        )

        templates = generate_test_case_skeletons(dict(bug_analysis), count=3)
        prompt = _PROMPT.format(
            bug_analysis_json=json.dumps(dict(bug_analysis), indent=2, ensure_ascii=False),
            template_json=json.dumps(templates, indent=2, ensure_ascii=False),
        )

        raw = llm.invoke(prompt)
        try:
            parsed = _extract_json(raw)
            generated = _validate_cases(parsed)
        except Exception as parse_err:
            # JSON parsing failed; use skeleton fallback immediately
            generated = []
            fallback = generate_test_case_skeletons(dict(bug_analysis), count=3)
            for i, fb in enumerate(fallback, start=1):
                try:
                    generated.append(_validate_test_case(fb, i))
                except Exception:
                    pass
            if not generated:
                raise ValueError(f"Failed to parse LLM response and skeletons failed: {parse_err}")

        alignment = evaluate_test_step_alignment(
            bug_steps=list(bug_analysis.get("steps_to_reproduce", [])),
            test_cases=[dict(tc) for tc in generated],
        )

        state["test_cases"] = generated
        save_to_file(_OUTPUT_FILE, json.dumps([dict(tc) for tc in generated], indent=2, ensure_ascii=False))

    except Exception as exc:
        msg = f"TestCaseGenerator: {exc}"
        errors.append(msg)
        state["errors"].append(msg)

    append_log(state["log_path"], {
        "agent": "TestCaseGenerator",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_s": round(time.time() - t0, 2),
        "input_summary": {
            "has_bug_analysis": bool(state.get("bug_analysis")),
            "bug_title": (state.get("bug_analysis") or {}).get("title") if state.get("bug_analysis") else None,
        },
        "output_summary": {
            "test_case_count": len(generated),
            "types": sorted(list({tc["type"] for tc in generated})) if generated else [],
            "step_alignment": alignment,
        },
        "errors": errors,
    })

    return state
