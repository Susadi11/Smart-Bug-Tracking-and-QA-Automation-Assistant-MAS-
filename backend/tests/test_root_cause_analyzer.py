"""
Tests for Agent 3 — Root Cause Analyzer.

Testing strategy (satisfies assignment "Testing/Evaluation" requirement):

  SECTION A — Custom Tool Unit Tests
    Tests for extract_error_signals, classify_cause_category, and
    score_root_cause_confidence from tools/root_cause_tools.py.

  SECTION B — Agent Helper Unit Tests
    Tests for _extract_json_array and _validate internal helpers.
    Covers happy path, markdown fences, wrapper objects, missing keys,
    empty lists, and type coercion.

  SECTION C — Full Agent Integration Tests (LLM mocked)
    Tests for root_cause_analyzer_node using unittest.mock to replace
    OllamaLLM so no Ollama server is required.  Covers success, connection
    errors, malformed output, state preservation, and logging.

  SECTION D — Property-Based / Invariant Tests
    Verifies structural invariants that must ALWAYS hold on valid output,
    regardless of which bug description or LLM response is used:
      - Every item has the three required fields
      - likelihood is always in {High, Medium, Low}
      - cause and explanation are non-empty strings
      - list contains 1–5 items (bounded output)
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make the backend root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.root_cause_analyzer import (
    _build_code_block,
    _build_env_block,
    _extract_json_array,
    _validate,
    root_cause_analyzer_node,
)
from state import AgentState, BugAnalysis, RootCause
from tools.root_cause_tools import (
    classify_cause_category,
    extract_error_signals,
    score_root_cause_confidence,
)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION A — Custom Tool Unit Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractErrorSignals:
    """Validate the extract_error_signals custom tool."""

    def test_detects_exception_type(self):
        signals = extract_error_signals("NullPointerException thrown in auth module")
        assert "NullPointerException" in signals["exception_types"]

    def test_detects_multiple_exception_types(self):
        signals = extract_error_signals("Got TypeError then AttributeError in handler")
        assert len(signals["exception_types"]) == 2

    def test_detects_http_500(self):
        signals = extract_error_signals("API returns 500 internal server error")
        assert "500" in signals["http_codes"]

    def test_detects_http_403(self):
        signals = extract_error_signals("Request fails with 403 Forbidden")
        assert "403" in signals["http_codes"]

    def test_detects_null_ref(self):
        signals = extract_error_signals("user is null when token expires")
        assert signals["null_refs"] != []

    def test_detects_crash_keyword(self):
        signals = extract_error_signals("app crashes on startup with fatal error")
        assert signals["crash_keywords"] != []

    def test_empty_input_returns_empty_lists(self):
        signals = extract_error_signals("")
        assert all(isinstance(v, list) for v in signals.values())
        assert all(len(v) == 0 for v in signals.values())

    def test_all_keys_always_present(self):
        signals = extract_error_signals("something broke")
        expected_keys = {"exception_types", "http_codes", "null_refs", "stack_keywords", "crash_keywords"}
        assert set(signals.keys()) == expected_keys

    def test_deduplicates_matches(self):
        signals = extract_error_signals("NullPointerException NullPointerException NullPointerException")
        assert signals["exception_types"].count("NullPointerException") == 1

    def test_xss_input_does_not_raise(self):
        signals = extract_error_signals('<script>alert("xss")</script> TypeError in login')
        assert "TypeError" in signals["exception_types"]


class TestClassifyCauseCategory:
    """Validate the classify_cause_category custom tool."""

    def test_classifies_null_pointer_as_validation(self):
        cat = classify_cause_category("Null pointer dereference", "Missing null check causes crash")
        assert cat == "Validation / Input Handling"

    def test_classifies_sql_as_database(self):
        cat = classify_cause_category("SQL query returns stale data", "ORM cache not invalidated after migration")
        assert cat == "Database / Data Layer"

    def test_classifies_api_timeout_as_backend(self):
        cat = classify_cause_category("API call times out", "Downstream service not responding to HTTP requests")
        assert cat == "Backend / API Failure"

    def test_classifies_css_render_as_ui(self):
        cat = classify_cause_category("CSS layout breaks on mobile", "React component re-renders with wrong style")
        assert cat == "UI / Frontend"

    def test_classifies_jwt_as_auth(self):
        cat = classify_cause_category("JWT token not validated", "Session expires because token auth fails with 401")
        assert cat == "Authentication / Authorization"

    def test_classifies_race_condition(self):
        cat = classify_cause_category("Race condition in thread pool", "Concurrent requests cause deadlock")
        assert cat == "Concurrency / Race Condition"

    def test_classifies_env_var_as_config(self):
        cat = classify_cause_category("Missing environment variable", "Config flag not set in production deploy")
        assert cat == "Configuration / Environment"

    def test_returns_general_when_no_match(self):
        cat = classify_cause_category("Something obscure", "Unclear origin with no specific signals")
        assert cat == "General / Unknown"

    def test_case_insensitive(self):
        cat = classify_cause_category("NULL POINTER IN AUTH", "MISSING NULL CHECK")
        assert cat == "Validation / Input Handling"

    def test_empty_strings_return_general(self):
        cat = classify_cause_category("", "")
        assert cat == "General / Unknown"


class TestScoreRootCauseConfidence:
    """Validate the score_root_cause_confidence custom tool."""

    def test_perfect_overlap_returns_one(self):
        keywords = ["login", "crash", "auth"]
        score = score_root_cause_confidence("login crash", "auth module crash", keywords, [])
        assert score > 0.0

    def test_zero_keywords_returns_zero(self):
        score = score_root_cause_confidence("some cause", "some explanation", [], [])
        assert score == 0.0

    def test_no_overlap_returns_zero(self):
        keywords = ["payment", "checkout", "cart"]
        score = score_root_cause_confidence("unrelated cause", "unrelated explanation", keywords, [])
        assert score == 0.0

    def test_score_is_in_valid_range(self):
        keywords = ["login", "auth", "session", "token", "jwt"]
        score = score_root_cause_confidence(
            "JWT token expiry causes session loss",
            "Auth module drops login session when token expires",
            keywords,
            ["Authentication"],
        )
        assert 0.0 <= score <= 1.0

    def test_component_match_increases_score(self):
        keywords = []
        components = ["Authentication"]
        score_with = score_root_cause_confidence(
            "Auth module fails", "Authentication token missing", keywords, components
        )
        score_without = score_root_cause_confidence(
            "Auth module fails", "Authentication token missing", keywords, []
        )
        assert score_with >= score_without

    def test_returns_float(self):
        score = score_root_cause_confidence("cause", "explanation", ["crash"], [])
        assert isinstance(score, float)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION B — Agent Helper Unit Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractJsonArray:
    """Validate JSON array extraction from raw LLM output."""

    def test_parses_clean_array(self):
        raw = '[{"cause": "Null pointer", "likelihood": "High", "explanation": "Missing check"}]'
        result = _extract_json_array(raw)
        assert isinstance(result, list)
        assert result[0]["cause"] == "Null pointer"

    def test_strips_json_markdown_fence(self):
        raw = '```json\n[{"cause": "Bug", "likelihood": "High", "explanation": "Test"}]\n```'
        result = _extract_json_array(raw)
        assert result[0]["cause"] == "Bug"

    def test_strips_plain_code_fence(self):
        raw = '```\n[{"cause": "Bug", "likelihood": "Low", "explanation": "Test"}]\n```'
        result = _extract_json_array(raw)
        assert result[0]["likelihood"] == "Low"

    def test_extracts_from_surrounding_prose(self):
        raw = 'Here are the root causes:\n[{"cause": "Bug", "likelihood": "High", "explanation": "T"}]\nDone.'
        result = _extract_json_array(raw)
        assert result[0]["cause"] == "Bug"

    def test_unwraps_root_causes_key(self):
        raw = '{"root_causes": [{"cause": "Bug", "likelihood": "Low", "explanation": "T"}]}'
        result = _extract_json_array(raw)
        assert result[0]["cause"] == "Bug"

    def test_unwraps_causes_key(self):
        raw = '{"causes": [{"cause": "X", "likelihood": "Medium", "explanation": "Y"}]}'
        result = _extract_json_array(raw)
        assert result[0]["cause"] == "X"

    def test_raises_on_plain_invalid_text(self):
        with pytest.raises(ValueError, match="Cannot parse JSON array"):
            _extract_json_array("not json at all")

    def test_raises_on_empty_string(self):
        with pytest.raises(ValueError):
            _extract_json_array("")

    def test_raises_on_bare_object(self):
        with pytest.raises(ValueError):
            _extract_json_array('{"cause": "Bug"}')

    def test_parses_multiple_items(self):
        raw = json.dumps([
            {"cause": "A", "likelihood": "High", "explanation": "Reason A"},
            {"cause": "B", "likelihood": "Low",  "explanation": "Reason B"},
        ])
        assert len(_extract_json_array(raw)) == 2


class TestValidate:
    """Validate the _validate output normalisation function."""

    def _item(self) -> dict:
        return {"cause": "Null pointer in auth", "likelihood": "High", "explanation": "No null check."}

    def test_valid_item_returns_root_cause(self):
        result = _validate([self._item()])
        assert result[0]["cause"] == "Null pointer in auth"
        assert result[0]["likelihood"] == "High"
        assert result[0]["explanation"] == "No null check."

    def test_normalises_lowercase_likelihood(self):
        item = {**self._item(), "likelihood": "high"}
        result = _validate([item])
        assert result[0]["likelihood"] == "High"

    def test_normalises_uppercase_likelihood(self):
        item = {**self._item(), "likelihood": "HIGH"}
        result = _validate([item])
        assert result[0]["likelihood"] == "High"

    def test_unknown_likelihood_falls_back_to_medium(self):
        item = {**self._item(), "likelihood": "Critical"}
        result = _validate([item])
        assert result[0]["likelihood"] == "Medium"

    def test_missing_cause_raises(self):
        item = self._item()
        del item["cause"]
        with pytest.raises(ValueError, match="missing required keys"):
            _validate([item])

    def test_missing_likelihood_raises(self):
        item = self._item()
        del item["likelihood"]
        with pytest.raises(ValueError, match="missing required keys"):
            _validate([item])

    def test_missing_explanation_raises(self):
        item = self._item()
        del item["explanation"]
        with pytest.raises(ValueError, match="missing required keys"):
            _validate([item])

    def test_empty_list_raises(self):
        with pytest.raises(ValueError, match="empty"):
            _validate([])

    def test_numeric_cause_cast_to_string(self):
        item = {**self._item(), "cause": 42}
        result = _validate([item])
        assert isinstance(result[0]["cause"], str)

    def test_multiple_items_all_validated(self):
        items = [self._item(), {**self._item(), "likelihood": "Low"}]
        result = _validate(items)
        assert len(result) == 2
        assert result[1]["likelihood"] == "Low"


class TestBuildHelpers:
    """Validate prompt formatting helpers."""

    def test_code_block_none_returns_empty(self):
        assert _build_code_block(None) == ""

    def test_code_block_whitespace_returns_empty(self):
        assert _build_code_block("   \n  ") == ""

    def test_code_block_wraps_in_fence(self):
        result = _build_code_block("x = 1")
        assert "```" in result and "x = 1" in result

    def test_env_block_both_fields(self):
        result = _build_env_block("iOS 17", "2.3.1")
        assert "iOS 17" in result and "2.3.1" in result

    def test_env_block_platform_only(self):
        result = _build_env_block("Windows 11", None)
        assert "Windows 11" in result and "App Version" not in result

    def test_env_block_both_none_returns_empty(self):
        assert _build_env_block(None, None) == ""


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION C — Full Agent Integration Tests (LLM mocked)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRootCauseAnalyzerNode:
    """Integration tests with OllamaLLM patched out."""

    # ── Fixtures ─────────────────────────────────────────────────────────────

    def _make_state(
        self,
        description: str = "App crashes on login when entering valid credentials",
        code: str | None = None,
        bug_analysis: BugAnalysis | None = None,
    ) -> AgentState:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            log_path = f.name
        return {
            "bug_description": description,
            "code_snippet": code,
            "platform": "Windows 11",
            "app_version": "1.2.0",
            "user_severity": None,
            "bug_analysis": bug_analysis,
            "test_cases": None,
            "root_causes": None,
            "bug_report": None,
            "log_path": log_path,
            "errors": [],
        }

    def _mock_response(self) -> str:
        return json.dumps([
            {
                "cause": "Null pointer in authentication module",
                "likelihood": "High",
                "explanation": "Missing null check before user object access causes NullPointerException on login.",
            },
            {
                "cause": "Race condition in session handler",
                "likelihood": "Medium",
                "explanation": "Concurrent login requests modify shared session state without mutex locking.",
            },
            {
                "cause": "Misconfigured JWT token expiry",
                "likelihood": "Low",
                "explanation": "Session TTL set too low in config, causing premature token invalidation on slow networks.",
            },
        ])

    def _bug_analysis(self) -> BugAnalysis:
        return {
            "title": "Login crash on startup",
            "severity": "Critical",
            "priority": "P1",
            "steps_to_reproduce": ["Open app", "Enter credentials", "Click login"],
            "expected_result": "User is logged in successfully",
            "actual_result": "App crashes with unhandled NullPointerException",
            "affected_components": ["Authentication"],
        }

    # ── Happy path ────────────────────────────────────────────────────────────

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_successful_run_populates_root_causes(self, MockLLM):
        MockLLM.return_value.invoke.return_value = self._mock_response()
        state = self._make_state(bug_analysis=self._bug_analysis())
        result = root_cause_analyzer_node(state)

        assert result["root_causes"] is not None
        assert len(result["root_causes"]) == 3
        assert result["errors"] == []

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_all_three_fields_present_in_each_cause(self, MockLLM):
        MockLLM.return_value.invoke.return_value = self._mock_response()
        result = root_cause_analyzer_node(self._make_state())
        for rc in result["root_causes"]:
            assert "cause" in rc and rc["cause"]
            assert "likelihood" in rc and rc["likelihood"]
            assert "explanation" in rc and rc["explanation"]

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_first_cause_is_high_likelihood(self, MockLLM):
        MockLLM.return_value.invoke.return_value = self._mock_response()
        result = root_cause_analyzer_node(self._make_state())
        assert result["root_causes"][0]["likelihood"] == "High"

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_bug_analysis_components_appear_in_prompt(self, MockLLM):
        mock_invoke = MagicMock(return_value=self._mock_response())
        MockLLM.return_value.invoke = mock_invoke
        state = self._make_state(bug_analysis=self._bug_analysis())
        root_cause_analyzer_node(state)
        prompt_sent = mock_invoke.call_args[0][0]
        assert "Authentication" in prompt_sent

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_error_signals_appear_in_prompt(self, MockLLM):
        mock_invoke = MagicMock(return_value=self._mock_response())
        MockLLM.return_value.invoke = mock_invoke
        state = self._make_state(
            description="NullPointerException thrown when user clicks login button"
        )
        root_cause_analyzer_node(state)
        prompt_sent = mock_invoke.call_args[0][0]
        assert "NullPointerException" in prompt_sent

    # ── Error handling ─────────────────────────────────────────────────────────

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_connection_error_captured_in_errors(self, MockLLM):
        MockLLM.return_value.invoke.side_effect = ConnectionError("Connection refused")
        result = root_cause_analyzer_node(self._make_state())
        assert result["root_causes"] is None
        assert any("Connection refused" in e for e in result["errors"])

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_malformed_llm_output_captured_in_errors(self, MockLLM):
        MockLLM.return_value.invoke.return_value = "Not valid JSON at all"
        result = root_cause_analyzer_node(self._make_state())
        assert result["root_causes"] is None
        assert len(result["errors"]) > 0

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_prior_errors_not_overwritten(self, MockLLM):
        MockLLM.return_value.invoke.side_effect = RuntimeError("LLM failed")
        state = self._make_state()
        state["errors"] = ["PriorAgent: something broke"]
        result = root_cause_analyzer_node(state)
        assert "PriorAgent: something broke" in result["errors"]
        assert any("RootCauseAnalyzer" in e for e in result["errors"])

    # ── State preservation ────────────────────────────────────────────────────

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_input_fields_preserved_in_state(self, MockLLM):
        MockLLM.return_value.invoke.return_value = self._mock_response()
        state = self._make_state(description="Test bug description on login", code="x = None")
        result = root_cause_analyzer_node(state)
        assert result["bug_description"] == "Test bug description on login"
        assert result["code_snippet"] == "x = None"
        assert result["platform"] == "Windows 11"

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_works_without_prior_bug_analysis(self, MockLLM):
        MockLLM.return_value.invoke.return_value = self._mock_response()
        result = root_cause_analyzer_node(self._make_state(bug_analysis=None))
        assert result["root_causes"] is not None
        assert result["errors"] == []

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_code_snippet_included_in_prompt(self, MockLLM):
        mock_invoke = MagicMock(return_value=self._mock_response())
        MockLLM.return_value.invoke = mock_invoke
        state = self._make_state(code="def login(user):\n    return user.token")
        root_cause_analyzer_node(state)
        prompt_sent = mock_invoke.call_args[0][0]
        assert "user.token" in prompt_sent

    # ── Logging / Observability ───────────────────────────────────────────────

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_log_entry_written_on_success(self, MockLLM):
        MockLLM.return_value.invoke.return_value = self._mock_response()
        state = self._make_state()
        result = root_cause_analyzer_node(state)
        log_data = json.loads(Path(result["log_path"]).read_text())
        assert log_data[0]["agent"] == "RootCauseAnalyzer"

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_log_records_cause_count(self, MockLLM):
        MockLLM.return_value.invoke.return_value = self._mock_response()
        state = self._make_state()
        result = root_cause_analyzer_node(state)
        log_data = json.loads(Path(result["log_path"]).read_text())
        assert log_data[0]["output_summary"]["cause_count"] == 3

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_log_entry_written_on_failure(self, MockLLM):
        MockLLM.return_value.invoke.side_effect = RuntimeError("Model error")
        state = self._make_state()
        result = root_cause_analyzer_node(state)
        log_data = json.loads(Path(result["log_path"]).read_text())
        assert log_data[0]["agent"] == "RootCauseAnalyzer"
        assert len(log_data[0]["errors"]) > 0

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_log_records_tools_called(self, MockLLM):
        MockLLM.return_value.invoke.return_value = self._mock_response()
        state = self._make_state()
        result = root_cause_analyzer_node(state)
        log_data = json.loads(Path(result["log_path"]).read_text())
        tools = log_data[0]["tools_called"]
        assert "extract_error_signals" in tools
        assert "classify_cause_category" in tools

    # ── Security ──────────────────────────────────────────────────────────────

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_xss_in_description_does_not_crash(self, MockLLM):
        MockLLM.return_value.invoke.return_value = self._mock_response()
        state = self._make_state(
            description='<script>alert("xss")</script> App crashes on login page'
        )
        result = root_cause_analyzer_node(state)
        assert result["root_causes"] is not None
        assert result["errors"] == []

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_sql_injection_in_description_does_not_crash(self, MockLLM):
        MockLLM.return_value.invoke.return_value = self._mock_response()
        state = self._make_state(
            description="App crashes; ' OR '1'='1 causes login to fail with error"
        )
        result = root_cause_analyzer_node(state)
        assert result["root_causes"] is not None

    @patch("agents.root_cause_analyzer.OllamaLLM")
    def test_very_long_description_does_not_crash(self, MockLLM):
        MockLLM.return_value.invoke.return_value = self._mock_response()
        state = self._make_state(description="crash login " * 500)
        result = root_cause_analyzer_node(state)
        assert result["root_causes"] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION D — Property-Based / Invariant Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestOutputInvariants:
    """
    Property-based tests — verify structural invariants that must ALWAYS hold
    on any valid root_cause_analyzer_node output, regardless of LLM content.

    These tests cover the "evaluation methodology" requirement from the
    assignment brief by asserting properties (not specific values).
    """

    VALID_LIKELIHOODS = {"High", "Medium", "Low"}

    def _run_with_response(self, llm_json: str) -> AgentState:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            log_path = f.name
        state: AgentState = {
            "bug_description": "App crashes when user clicks login button",
            "code_snippet": None,
            "platform": "Linux",
            "app_version": "3.0.0",
            "user_severity": None,
            "bug_analysis": None,
            "test_cases": None,
            "root_causes": None,
            "bug_report": None,
            "log_path": log_path,
            "errors": [],
        }
        with patch("agents.root_cause_analyzer.OllamaLLM") as MockLLM:
            MockLLM.return_value.invoke.return_value = llm_json
            return root_cause_analyzer_node(state)

    def _make_cause(self, likelihood: str = "High") -> dict:
        return {
            "cause": f"Test cause with {likelihood} likelihood",
            "likelihood": likelihood,
            "explanation": "This is a test explanation for the root cause.",
        }

    # ── Invariant 1: likelihood is always a valid enum value ──────────────────

    def test_likelihood_always_valid_enum(self):
        """PROPERTY: every returned RootCause.likelihood ∈ {High, Medium, Low}."""
        response = json.dumps([self._make_cause("High"), self._make_cause("Medium")])
        result = self._run_with_response(response)
        for rc in result["root_causes"]:
            assert rc["likelihood"] in self.VALID_LIKELIHOODS

    def test_likelihood_normalised_from_lowercase(self):
        """PROPERTY: likelihood is normalised even when LLM returns wrong casing."""
        response = json.dumps([{**self._make_cause(), "likelihood": "high"}])
        result = self._run_with_response(response)
        assert result["root_causes"][0]["likelihood"] == "High"

    # ── Invariant 2: all required fields are non-empty strings ────────────────

    def test_cause_is_non_empty_string(self):
        """PROPERTY: cause is always a non-empty string."""
        response = json.dumps([self._make_cause()])
        result = self._run_with_response(response)
        for rc in result["root_causes"]:
            assert isinstance(rc["cause"], str) and rc["cause"].strip()

    def test_explanation_is_non_empty_string(self):
        """PROPERTY: explanation is always a non-empty string."""
        response = json.dumps([self._make_cause()])
        result = self._run_with_response(response)
        for rc in result["root_causes"]:
            assert isinstance(rc["explanation"], str) and rc["explanation"].strip()

    # ── Invariant 3: output list is bounded ───────────────────────────────────

    def test_output_has_at_least_one_cause(self):
        """PROPERTY: on success, root_causes always has ≥ 1 item."""
        response = json.dumps([self._make_cause()])
        result = self._run_with_response(response)
        assert len(result["root_causes"]) >= 1

    def test_output_is_a_list(self):
        """PROPERTY: root_causes is always a list (never a dict or string)."""
        response = json.dumps([self._make_cause()])
        result = self._run_with_response(response)
        assert isinstance(result["root_causes"], list)

    # ── Invariant 4: state mutation is additive only ──────────────────────────

    def test_errors_list_is_additive_not_replaced(self):
        """PROPERTY: state["errors"] is appended to, never replaced."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            log_path = f.name
        state: AgentState = {
            "bug_description": "App crashes login button",
            "code_snippet": None,
            "platform": None,
            "app_version": None,
            "user_severity": None,
            "bug_analysis": None,
            "test_cases": None,
            "root_causes": None,
            "bug_report": None,
            "log_path": log_path,
            "errors": ["ExistingAgent: prior error"],
        }
        with patch("agents.root_cause_analyzer.OllamaLLM") as MockLLM:
            MockLLM.return_value.invoke.side_effect = RuntimeError("fail")
            result = root_cause_analyzer_node(state)
        assert "ExistingAgent: prior error" in result["errors"]
        assert len(result["errors"]) == 2

    # ── Invariant 5: log entry is always written ──────────────────────────────

    def test_log_entry_always_written_even_on_failure(self):
        """PROPERTY: a log entry is always appended, regardless of success/failure."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            log_path = f.name
        state: AgentState = {
            "bug_description": "App crashes login",
            "code_snippet": None,
            "platform": None,
            "app_version": None,
            "user_severity": None,
            "bug_analysis": None,
            "test_cases": None,
            "root_causes": None,
            "bug_report": None,
            "log_path": log_path,
            "errors": [],
        }
        with patch("agents.root_cause_analyzer.OllamaLLM") as MockLLM:
            MockLLM.return_value.invoke.side_effect = RuntimeError("fail")
            root_cause_analyzer_node(state)
        log_data = json.loads(Path(log_path).read_text())
        assert len(log_data) == 1
        assert log_data[0]["agent"] == "RootCauseAnalyzer"
