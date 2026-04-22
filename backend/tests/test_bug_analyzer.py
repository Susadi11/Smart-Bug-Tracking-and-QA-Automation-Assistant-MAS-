"""
Tests for Agent 1 — Bug Analyzer.

Covers:
  - Tool functions (extract_keywords, extract_affected_components)
  - Internal helpers (_build_code_block, _build_env_block, _extract_json, _validate)
  - Full agent node with a mocked LLM (no Ollama dependency)
  - Edge cases, malformed input, and security validations
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure backend root is on the import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from state import AgentState, BugAnalysis
from tools.analysis_tools import extract_keywords, extract_affected_components
from agents.bug_analyzer import (
    _build_code_block,
    _build_env_block,
    _extract_json,
    _validate,
    bug_analyzer_node,
)


# ── extract_keywords tests ────────────────────────────────────────────────────


class TestExtractKeywords:
    """Validate keyword extraction from bug descriptions."""

    def test_filters_stop_words(self):
        text = "the user is not able to login"
        keywords = extract_keywords(text)
        assert "the" not in keywords
        assert "not" not in keywords
        assert "user" in keywords
        assert "able" in keywords
        assert "login" in keywords

    def test_returns_max_20_keywords(self):
        text = " ".join(f"word{i}" for i in range(50))
        keywords = extract_keywords(text)
        assert len(keywords) <= 20

    def test_deduplicates_keywords(self):
        text = "error error error crash crash"
        keywords = extract_keywords(text)
        assert keywords.count("error") == 1
        assert keywords.count("crash") == 1

    def test_empty_input_returns_empty_list(self):
        assert extract_keywords("") == []

    def test_short_words_excluded(self):
        text = "a an it ok go no"
        keywords = extract_keywords(text)
        assert len(keywords) == 0

    def test_preserves_order_of_first_appearance(self):
        text = "crash then error then crash again"
        keywords = extract_keywords(text)
        assert keywords.index("crash") < keywords.index("error")

    def test_handles_code_mixed_with_text(self):
        text = "TypeError in calculateTotal function when processing cart items"
        keywords = extract_keywords(text)
        assert "typeerror" in keywords
        assert "calculatetotal" in keywords


# ── extract_affected_components tests ─────────────────────────────────────────


class TestExtractAffectedComponents:
    """Validate component detection from bug descriptions."""

    def test_detects_payment_component(self):
        text = "The checkout page crashes when processing cart items"
        components = extract_affected_components(text)
        assert "Payment" in components

    def test_detects_auth_component(self):
        text = "Login fails after entering valid credentials with JWT token"
        components = extract_affected_components(text)
        assert "Authentication" in components

    def test_detects_database_component(self):
        text = "SQL query returns stale data from postgres"
        components = extract_affected_components(text)
        assert "Database" in components

    def test_detects_multiple_components(self):
        text = "User cannot login and the payment page shows wrong total"
        components = extract_affected_components(text)
        assert len(components) >= 2

    def test_unknown_domain_returns_general(self):
        text = "Something is broken but no specific details available"
        components = extract_affected_components(text)
        assert components == ["General / Unknown"]

    def test_deduplicates_component_labels(self):
        text = "login auth session token jwt oauth sign-in"
        components = extract_affected_components(text)
        assert components.count("Authentication") == 1

    def test_case_insensitive_matching(self):
        text = "The DATABASE query on POSTGRES returns wrong results"
        components = extract_affected_components(text)
        assert "Database" in components


# ── _build_code_block tests ───────────────────────────────────────────────────


class TestBuildCodeBlock:
    """Validate code block formatting for the LLM prompt."""

    def test_returns_empty_for_none(self):
        assert _build_code_block(None) == ""

    def test_returns_empty_for_whitespace(self):
        assert _build_code_block("   ") == ""

    def test_wraps_snippet_in_markdown_fence(self):
        result = _build_code_block("x = 1")
        assert "```" in result
        assert "x = 1" in result

    def test_strips_surrounding_whitespace(self):
        result = _build_code_block("  code  \n  ")
        assert "code" in result


# ── _build_env_block tests ────────────────────────────────────────────────────


class TestBuildEnvBlock:
    """Validate environment block formatting."""

    def test_both_fields(self):
        result = _build_env_block("iOS 17", "2.3.1")
        assert "iOS 17" in result
        assert "2.3.1" in result

    def test_platform_only(self):
        result = _build_env_block("Windows 11", None)
        assert "Windows 11" in result
        assert "App Version" not in result

    def test_no_fields(self):
        assert _build_env_block(None, None) == ""


# ── _extract_json tests ──────────────────────────────────────────────────────


class TestExtractJson:
    """Validate JSON extraction from raw LLM responses."""

    def test_parses_clean_json(self):
        raw = '{"title": "Bug", "severity": "High"}'
        result = _extract_json(raw)
        assert result["title"] == "Bug"

    def test_strips_markdown_fences(self):
        raw = '```json\n{"title": "Bug"}\n```'
        result = _extract_json(raw)
        assert result["title"] == "Bug"

    def test_extracts_json_from_surrounding_text(self):
        raw = 'Here is the result:\n{"title": "Bug"}\nEnd.'
        result = _extract_json(raw)
        assert result["title"] == "Bug"

    def test_raises_on_invalid_json(self):
        with pytest.raises(ValueError, match="Cannot parse JSON"):
            _extract_json("this is not json at all")

    def test_raises_on_empty_input(self):
        with pytest.raises(ValueError):
            _extract_json("")


# ── _validate tests ──────────────────────────────────────────────────────────


class TestValidate:
    """Validate the BugAnalysis structure validator."""

    def _valid_data(self) -> dict:
        return {
            "title": "Cart total bug",
            "severity": "High",
            "priority": "P2",
            "steps_to_reproduce": ["Add item", "Check total"],
            "expected_result": "Correct total",
            "actual_result": "Wrong total",
            "affected_components": ["Payment", "Cart"],
        }

    def test_valid_data_returns_bug_analysis(self):
        result = _validate(self._valid_data())
        assert result["title"] == "Cart total bug"
        assert result["severity"] == "High"

    def test_missing_key_raises_value_error(self):
        data = self._valid_data()
        del data["title"]
        with pytest.raises(ValueError, match="Missing keys"):
            _validate(data)

    def test_coerces_string_steps_to_list(self):
        data = self._valid_data()
        data["steps_to_reproduce"] = "Single step"
        result = _validate(data)
        assert isinstance(result["steps_to_reproduce"], list)
        assert result["steps_to_reproduce"] == ["Single step"]

    def test_coerces_string_components_to_list(self):
        data = self._valid_data()
        data["affected_components"] = "Payment"
        result = _validate(data)
        assert isinstance(result["affected_components"], list)

    def test_all_values_cast_to_strings(self):
        data = self._valid_data()
        data["title"] = 12345
        result = _validate(data)
        assert isinstance(result["title"], str)


# ── Full agent node tests (LLM mocked) ──────────────────────────────────────


class TestBugAnalyzerNode:
    """Integration tests for the bug_analyzer_node with mocked LLM."""

    def _make_state(self, description: str = "App crashes on login",
                    code: str = None) -> AgentState:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            log_path = f.name
        return {
            "bug_description": description,
            "code_snippet": code,
            "platform": "Windows 11",
            "app_version": "1.0.0",
            "user_severity": None,
            "bug_analysis": None,
            "test_cases": None,
            "root_causes": None,
            "bug_report": None,
            "log_path": log_path,
            "errors": [],
        }

    def _mock_llm_response(self) -> str:
        return json.dumps({
            "title": "Login crash on startup",
            "severity": "Critical",
            "priority": "P1",
            "steps_to_reproduce": ["Open app", "Click login", "App crashes"],
            "expected_result": "User is logged in",
            "actual_result": "App crashes with error",
            "affected_components": ["Authentication"],
        })

    @patch("agents.bug_analyzer.OllamaLLM")
    def test_successful_analysis(self, MockLLM):
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = self._mock_llm_response()
        MockLLM.return_value = mock_instance

        state = self._make_state()
        result = bug_analyzer_node(state)

        assert result["bug_analysis"] is not None
        assert result["bug_analysis"]["title"] == "Login crash on startup"
        assert result["bug_analysis"]["severity"] == "Critical"
        assert result["errors"] == []

    @patch("agents.bug_analyzer.OllamaLLM")
    def test_llm_connection_error_captured(self, MockLLM):
        mock_instance = MagicMock()
        mock_instance.invoke.side_effect = ConnectionError("Connection refused")
        MockLLM.return_value = mock_instance

        state = self._make_state()
        result = bug_analyzer_node(state)

        assert result["bug_analysis"] is None
        assert len(result["errors"]) > 0
        assert "Connection refused" in result["errors"][0]

    @patch("agents.bug_analyzer.OllamaLLM")
    def test_malformed_llm_output_captured(self, MockLLM):
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = "Not valid JSON at all"
        MockLLM.return_value = mock_instance

        state = self._make_state()
        result = bug_analyzer_node(state)

        assert result["bug_analysis"] is None
        assert len(result["errors"]) > 0

    @patch("agents.bug_analyzer.OllamaLLM")
    def test_state_preserves_input_fields(self, MockLLM):
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = self._mock_llm_response()
        MockLLM.return_value = mock_instance

        state = self._make_state(description="Test bug", code="x = 1")
        result = bug_analyzer_node(state)

        assert result["bug_description"] == "Test bug"
        assert result["code_snippet"] == "x = 1"
        assert result["platform"] == "Windows 11"

    @patch("agents.bug_analyzer.OllamaLLM")
    def test_log_entry_written(self, MockLLM):
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = self._mock_llm_response()
        MockLLM.return_value = mock_instance

        state = self._make_state()
        result = bug_analyzer_node(state)

        log_content = Path(result["log_path"]).read_text()
        log_data = json.loads(log_content)
        assert isinstance(log_data, list)
        assert log_data[0]["agent"] == "BugAnalyzer"

    @patch("agents.bug_analyzer.OllamaLLM")
    def test_handles_code_snippet_in_prompt(self, MockLLM):
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = self._mock_llm_response()
        MockLLM.return_value = mock_instance

        state = self._make_state(
            description="Total price is wrong",
            code="function calc(items) { return items.reduce((s,i) => s+i.price, 0); }",
        )
        result = bug_analyzer_node(state)
        assert result["bug_analysis"] is not None

    @patch("agents.bug_analyzer.OllamaLLM")
    def test_xss_in_description_does_not_break(self, MockLLM):
        """Security: ensure script injection in input doesn't crash the agent."""
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = self._mock_llm_response()
        MockLLM.return_value = mock_instance

        state = self._make_state(
            description='<script>alert("xss")</script> Bug in login page'
        )
        result = bug_analyzer_node(state)
        assert result["bug_analysis"] is not None
        assert len(result["errors"]) == 0
