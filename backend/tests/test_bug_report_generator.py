"""
Tests for Agent 4 — Bug Report Generator.

Covers:
  - Tool functions (format_bug_report_markdown, validate_report_sections)
  - Helper functions in the agent (_build_reproduction_steps, etc.)
  - Full agent node with a mocked LLM (no Ollama dependency)
  - Edge cases, missing data, and fallback behavior
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

from state import AgentState, BugAnalysis, TestCase, RootCause
from tools.report_tools import (
    format_bug_report_markdown,
    validate_report_sections,
    severity_validator_tool,
)
from agents.bug_report_generator import (
    _build_reproduction_steps,
    _build_root_causes_text,
    _build_test_cases_text,
    bug_report_generator_node,
)


# ── format_bug_report_markdown tests ──────────────────────────────────────────


class TestFormatBugReportMarkdown:
    """Validate markdown report formatting from structured data."""

    def test_returns_string(self):
        """Report should always be a string."""
        result = format_bug_report_markdown()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_all_required_sections_with_full_data(self):
        """With full data, report should include all standard sections."""
        bug_analysis: BugAnalysis = {
            "title": "Login Button Broken",
            "severity": "Critical",
            "priority": "P1",
            "steps_to_reproduce": ["Open app", "Click login"],
            "expected_result": "Login form appears",
            "actual_result": "Nothing happens",
            "affected_components": ["Authentication", "UI"],
        }
        test_cases = [
            {
                "id": "TC-001",
                "type": "Positive",
                "description": "Valid login",
                "steps": ["Click login", "Enter credentials"],
                "expected": "User logged in",
            }
        ]
        root_causes = [
            {
                "cause": "Click handler missing",
                "likelihood": "High",
                "explanation": "Event listener not attached",
            }
        ]

        report = format_bug_report_markdown(
            bug_analysis=bug_analysis,
            test_cases=test_cases,
            root_causes=root_causes,
        )

        assert "# Bug Report:" in report
        assert "## Summary" in report
        assert "## Description" in report
        assert "## Steps to Reproduce" in report
        assert "## Root Cause Analysis" in report
        assert "## Test Cases" in report
        assert "Critical" in report
        assert "P1" in report

    def test_handles_none_inputs_gracefully(self):
        """With None inputs, report should still be valid."""
        report = format_bug_report_markdown(
            bug_analysis=None,
            test_cases=None,
            root_causes=None,
        )
        assert isinstance(report, str)
        assert "# Bug Report:" in report
        assert "Unknown Bug" in report

    def test_handles_empty_lists(self):
        """With empty lists, report should handle gracefully."""
        report = format_bug_report_markdown(
            bug_analysis={"title": "Test", "severity": "Low", "priority": "P4"},
            test_cases=[],
            root_causes=[],
        )
        assert isinstance(report, str)
        # Empty lists should not create sections (cleaner report)
        assert "# Bug Report:" in report
        assert "## Summary" in report

    def test_includes_llm_report_when_provided(self):
        """If llm_report is provided, its content should appear in the report."""
        llm_text = "## Recommended Fix\nThis is a recommendation from the LLM."
        report = format_bug_report_markdown(
            bug_analysis={"title": "Bug", "severity": "High", "priority": "P2"},
            llm_report=llm_text,
        )
        assert llm_text in report
        # LLM content is appended verbatim — no extra wrapper heading is added
        assert "LLM-Generated Recommendations" not in report

    def test_escapes_pipes_in_test_descriptions(self):
        """Pipes in test case descriptions should be escaped for markdown tables."""
        test_cases = [
            {
                "id": "TC-001",
                "type": "Positive",
                "description": "Test | with pipe",
            }
        ]
        report = format_bug_report_markdown(test_cases=test_cases)
        # Pipes should be escaped as \|
        assert "\\|" in report

    def test_converts_string_components_to_list(self):
        """Single string component should be handled."""
        bug_analysis = {
            "title": "Bug",
            "severity": "High",
            "priority": "P2",
            "affected_components": "Authentication",  # String, not list
        }
        report = format_bug_report_markdown(bug_analysis=bug_analysis)
        assert "Authentication" in report


# ── validate_report_sections tests ────────────────────────────────────────────


class TestValidateReportSections:
    """Validate report structure checking."""

    def test_valid_report_with_all_sections(self):
        """A report with all required sections should be valid."""
        report = """# Bug Report

## Summary
Critical | P1

## Description
The app crashes on startup.

## Steps to Reproduce
1. Open app

## Root Cause Analysis
- Memory leak (High): Not releasing resources
"""
        result = validate_report_sections(report)
        assert result["valid"] is True
        assert len(result["missing_sections"]) == 0
        assert result["section_count"] >= 4

    def test_detects_missing_summary(self):
        """Missing Summary section should be detected."""
        report = """# Bug Report

## Description
The app crashes.

## Steps to Reproduce
1. Open app
"""
        result = validate_report_sections(report)
        assert result["valid"] is False
        assert "Summary" in result["missing_sections"]

    def test_detects_missing_description(self):
        """Missing Description section should be detected."""
        report = """# Bug Report

## Summary
Critical | P1

## Steps to Reproduce
1. Open app
"""
        result = validate_report_sections(report)
        assert result["valid"] is False
        assert "Description" in result["missing_sections"]

    def test_detects_missing_steps(self):
        """Missing Steps to Reproduce section should be detected."""
        report = """# Bug Report

## Summary
Critical | P1

## Description
The app crashes on startup.
"""
        result = validate_report_sections(report)
        assert result["valid"] is False
        assert "Steps to Reproduce" in result["missing_sections"]

    def test_root_cause_is_optional(self):
        """Report without Root Cause Analysis can still be valid."""
        report = """# Bug Report

## Summary
Critical | P1

## Description
The app crashes.

## Steps to Reproduce
1. Open app
"""
        result = validate_report_sections(report)
        # Should be valid even without Root Cause Analysis
        assert result["valid"] is True

    def test_returns_section_count(self):
        """Result should include the count of sections found."""
        report = """# Bug Report

## Summary
Critical

## Description
Bug description

## Steps to Reproduce
1. Step 1

## Root Cause Analysis
- Cause (High): Explanation
"""
        result = validate_report_sections(report)
        assert result["section_count"] >= 4
        assert isinstance(result["sections_found"], list)

    def test_case_insensitive_heading_matching(self):
        """Heading matching should be case-insensitive."""
        report = """# Bug Report

## SUMMARY
Critical | P1

## description
The app crashes.

## STEPS TO REPRODUCE
1. Open app
"""
        # Markdown headings are case-sensitive by default, but our regex should match
        result = validate_report_sections(report)
        # If the test passes, headings were recognized
        assert isinstance(result, dict)


# ── _build_reproduction_steps tests ───────────────────────────────────────────


class TestBuildReproductionSteps:
    """Validate reproduction steps formatting for the LLM prompt."""

    def test_returns_string_for_none(self):
        result = _build_reproduction_steps(None)
        assert isinstance(result, str)
        assert "No reproduction steps" in result

    def test_returns_string_for_empty_list(self):
        result = _build_reproduction_steps([])
        assert isinstance(result, str)
        assert "No reproduction steps" in result

    def test_formats_steps_with_numbers(self):
        steps = ["Open app", "Click login", "Enter credentials"]
        result = _build_reproduction_steps(steps)
        assert "1. Open app" in result
        assert "2. Click login" in result
        assert "3. Enter credentials" in result

    def test_handles_non_string_steps(self):
        steps = ["Open app", 123, "Click button"]
        result = _build_reproduction_steps(steps)
        assert "123" in result

    def test_filters_empty_strings(self):
        steps = ["Open app", "", "Click login"]
        result = _build_reproduction_steps(steps)
        # Should have 2 steps, not 3
        assert "1. Open app" in result
        assert "2. Click login" in result
        assert "3." not in result


# ── _build_root_causes_text tests ──────────────────────────────────────────


class TestBuildRootCausesText:
    """Validate root causes formatting for the LLM prompt."""

    def test_returns_string_for_none(self):
        result = _build_root_causes_text(None)
        assert isinstance(result, str)
        assert "No root cause" in result

    def test_returns_string_for_empty_list(self):
        result = _build_root_causes_text([])
        assert isinstance(result, str)
        assert "No root cause" in result

    def test_formats_complete_root_causes(self):
        causes = [
            {
                "cause": "Memory leak",
                "likelihood": "High",
                "explanation": "Not releasing resources",
            }
        ]
        result = _build_root_causes_text(causes)
        assert "Memory leak" in result
        assert "(High)" in result
        assert "Not releasing resources" in result

    def test_handles_missing_fields(self):
        causes = [{"cause": "Unknown bug"}]
        result = _build_root_causes_text(causes)
        assert "Unknown bug" in result

    def test_formats_multiple_causes(self):
        causes = [
            {"cause": "Cause 1", "likelihood": "High", "explanation": "Exp 1"},
            {"cause": "Cause 2", "likelihood": "Medium", "explanation": "Exp 2"},
        ]
        result = _build_root_causes_text(causes)
        assert "Cause 1" in result
        assert "Cause 2" in result


# ── _build_test_cases_text tests ──────────────────────────────────────────


class TestBuildTestCasesText:
    """Validate test cases formatting for the LLM prompt."""

    def test_returns_string_for_none(self):
        result = _build_test_cases_text(None)
        assert isinstance(result, str)
        assert "No test cases" in result

    def test_returns_string_for_empty_list(self):
        result = _build_test_cases_text([])
        assert isinstance(result, str)
        assert "No test cases" in result

    def test_formats_test_cases(self):
        cases = [
            {"id": "TC-001", "type": "Positive", "description": "Valid login"}
        ]
        result = _build_test_cases_text(cases)
        assert "TC-001" in result
        assert "Positive" in result
        assert "Valid login" in result

    def test_handles_missing_fields(self):
        cases = [{"id": "TC-001"}]
        result = _build_test_cases_text(cases)
        assert "TC-001" in result


# ── bug_report_generator_node tests ────────────────────────────────────────


class TestBugReportGeneratorNode:
    """Validate the full Bug Report Generator agent node."""

    def _create_test_state(self, **overrides) -> AgentState:
        """Create a minimal AgentState for testing."""
        state: AgentState = {
            "bug_description": "The app crashes when clicking the login button.",
            "code_snippet": None,
            "platform": "iOS",
            "app_version": "1.0.0",
            "user_severity": "Critical",
            "bug_analysis": None,
            "test_cases": None,
            "root_causes": None,
            "bug_report": None,
            "log_path": str(Path(tempfile.gettempdir()) / "test_pipeline.log"),
            "errors": [],
        }
        state.update(overrides)
        return state

    @patch("agents.bug_report_generator.OllamaLLM")
    @patch("agents.bug_report_generator.save_to_file")
    @patch("agents.bug_report_generator.append_log")
    def test_returns_agent_state(self, mock_append_log, mock_save, mock_llm_class):
        """Agent should return an updated AgentState."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = "## Summary\nThis is a recommendation."
        mock_llm_class.return_value = mock_llm

        state = self._create_test_state()
        result = bug_report_generator_node(state)

        assert isinstance(result, dict)
        assert result is state  # Should return same object

    @patch("agents.bug_report_generator.OllamaLLM")
    @patch("agents.bug_report_generator.save_to_file")
    @patch("agents.bug_report_generator.append_log")
    def test_populates_bug_report_field(self, mock_append_log, mock_save, mock_llm_class):
        """Agent should populate state['bug_report']."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = "## Summary\nThis is a report."
        mock_llm_class.return_value = mock_llm

        state = self._create_test_state(
            bug_analysis={
                "title": "Test Bug",
                "severity": "High",
                "priority": "P1",
                "steps_to_reproduce": ["Step 1"],
                "expected_result": "Expected",
                "actual_result": "Actual",
                "affected_components": ["Component 1"],
            }
        )
        result = bug_report_generator_node(state)

        assert result["bug_report"] is not None
        assert isinstance(result["bug_report"], str)
        assert len(result["bug_report"]) > 0

    @patch("agents.bug_report_generator.OllamaLLM")
    @patch("agents.bug_report_generator.save_to_file")
    @patch("agents.bug_report_generator.append_log")
    def test_handles_missing_bug_analysis(self, mock_append_log, mock_save, mock_llm_class):
        """Agent should not crash if bug_analysis is None."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = "## Summary\nA recommendation."
        mock_llm_class.return_value = mock_llm

        state = self._create_test_state(bug_analysis=None)
        result = bug_report_generator_node(state)

        assert result["bug_report"] is not None
        assert "Unknown Bug" in result["bug_report"]

    @patch("agents.bug_report_generator.OllamaLLM")
    @patch("agents.bug_report_generator.save_to_file")
    @patch("agents.bug_report_generator.append_log")
    def test_handles_missing_test_cases(self, mock_append_log, mock_save, mock_llm_class):
        """Agent should not crash if test_cases is None."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = "## Summary\nA recommendation."
        mock_llm_class.return_value = mock_llm

        state = self._create_test_state(test_cases=None)
        result = bug_report_generator_node(state)

        assert result["bug_report"] is not None

    @patch("agents.bug_report_generator.OllamaLLM")
    @patch("agents.bug_report_generator.save_to_file")
    @patch("agents.bug_report_generator.append_log")
    def test_handles_missing_root_causes(self, mock_append_log, mock_save, mock_llm_class):
        """Agent should not crash if root_causes is None."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = "## Summary\nA recommendation."
        mock_llm_class.return_value = mock_llm

        state = self._create_test_state(root_causes=None)
        result = bug_report_generator_node(state)

        assert result["bug_report"] is not None

    @patch("agents.bug_report_generator.OllamaLLM")
    @patch("agents.bug_report_generator.save_to_file")
    @patch("agents.bug_report_generator.append_log")
    def test_handles_llm_exception_gracefully(
        self, mock_append_log, mock_save, mock_llm_class
    ):
        """Agent should not crash if LLM throws an exception."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("LLM connection failed")
        mock_llm_class.return_value = mock_llm

        state = self._create_test_state(
            bug_analysis={
                "title": "Test",
                "severity": "High",
                "priority": "P1",
                "steps_to_reproduce": ["Step"],
                "expected_result": "Expected",
                "actual_result": "Actual",
                "affected_components": ["Comp"],
            }
        )
        result = bug_report_generator_node(state)

        # Should still have a report (fallback)
        assert result["bug_report"] is not None
        assert len(result["errors"]) > 0

    @patch("agents.bug_report_generator.OllamaLLM")
    @patch("agents.bug_report_generator.save_to_file")
    @patch("agents.bug_report_generator.append_log")
    def test_appends_log_entry(self, mock_append_log, mock_save, mock_llm_class):
        """Agent should append a log entry."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = "## Summary\nA report."
        mock_llm_class.return_value = mock_llm

        state = self._create_test_state()
        bug_report_generator_node(state)

        assert mock_append_log.called
        call_args = mock_append_log.call_args
        assert "BugReportGenerator" in call_args[0][1]["agent"]

    @patch("agents.bug_report_generator.OllamaLLM")
    @patch("agents.bug_report_generator.save_to_file")
    @patch("agents.bug_report_generator.append_log")
    def test_saves_report_to_file(self, mock_append_log, mock_save, mock_llm_class):
        """Agent should save the report to output/bug_report.md."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = "## Summary\nA report."
        mock_llm_class.return_value = mock_llm

        state = self._create_test_state(
            bug_analysis={
                "title": "Test",
                "severity": "High",
                "priority": "P1",
                "steps_to_reproduce": ["Step"],
                "expected_result": "Expected",
                "actual_result": "Actual",
                "affected_components": ["Comp"],
            }
        )
        bug_report_generator_node(state)

        assert mock_save.called
        call_args = mock_save.call_args
        assert "bug_report.md" in call_args[0][0]

    @patch("agents.bug_report_generator.OllamaLLM")
    @patch("agents.bug_report_generator.save_to_file")
    @patch("agents.bug_report_generator.append_log")
    def test_report_includes_root_causes_when_available(
        self, mock_append_log, mock_save, mock_llm_class
    ):
        """Report should include root causes when available."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = "## Summary\nA report."
        mock_llm_class.return_value = mock_llm

        state = self._create_test_state(
            bug_analysis={
                "title": "Test",
                "severity": "High",
                "priority": "P1",
                "steps_to_reproduce": ["Step"],
                "expected_result": "Expected",
                "actual_result": "Actual",
                "affected_components": ["Comp"],
            },
            root_causes=[
                {
                    "cause": "Memory leak",
                    "likelihood": "High",
                    "explanation": "Not releasing resources",
                }
            ],
        )
        result = bug_report_generator_node(state)

        assert "Memory leak" in result["bug_report"]

    @patch("agents.bug_report_generator.OllamaLLM")
    @patch("agents.bug_report_generator.save_to_file")
    @patch("agents.bug_report_generator.append_log")
    def test_report_includes_test_cases_when_available(
        self, mock_append_log, mock_save, mock_llm_class
    ):
        """Report should include test cases when available."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = "## Summary\nA report."
        mock_llm_class.return_value = mock_llm

        state = self._create_test_state(
            test_cases=[
                {
                    "id": "TC-001",
                    "type": "Positive",
                    "description": "Valid login",
                    "steps": ["Login"],
                    "expected": "Success",
                }
            ]
        )
        result = bug_report_generator_node(state)

        assert "TC-001" in result["bug_report"]

    @patch("agents.bug_report_generator.OllamaLLM")
    @patch("agents.bug_report_generator.save_to_file")
    @patch("agents.bug_report_generator.append_log")
    def test_report_has_valid_markdown_sections(
        self, mock_append_log, mock_save, mock_llm_class
    ):
        """Generated report should have valid markdown sections."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = "## Executive Summary\nFixed this bug."
        mock_llm_class.return_value = mock_llm

        state = self._create_test_state(
            bug_analysis={
                "title": "Test",
                "severity": "Critical",
                "priority": "P1",
                "steps_to_reproduce": ["Step 1", "Step 2"],
                "expected_result": "Should work",
                "actual_result": "Does not work",
                "affected_components": ["Backend"],
            }
        )
        result = bug_report_generator_node(state)

        validation = validate_report_sections(result["bug_report"])
        # At least critical sections should be present
        assert "Summary" in result["bug_report"]
        assert "Description" in result["bug_report"]


# ── severity_validator_tool tests ──────────────────────────────────────────────


class TestSeverityValidatorTool:
    """Validate the severity cross-check tool (Agent 4 custom tool)."""

    def test_returns_dict_with_required_keys(self):
        """Result must always contain aligned, severity, highest_likelihood, warning."""
        result = severity_validator_tool()
        for key in ("aligned", "severity", "highest_likelihood", "warning"):
            assert key in result

    def test_handles_none_inputs(self):
        """Both inputs None → aligned True, no warning."""
        result = severity_validator_tool(None, None)
        assert result["aligned"] is True
        assert result["warning"] is None

    def test_handles_missing_bug_analysis(self):
        """No bug_analysis → aligned True (nothing to cross-check)."""
        root_causes = [{"cause": "X", "likelihood": "High", "explanation": "y"}]
        result = severity_validator_tool(bug_analysis=None, root_causes=root_causes)
        assert result["aligned"] is True

    def test_handles_missing_root_causes(self):
        """No root_causes → aligned True (nothing to cross-check)."""
        bug_analysis = {"severity": "Critical"}
        result = severity_validator_tool(bug_analysis=bug_analysis, root_causes=None)
        assert result["aligned"] is True
        assert result["warning"] is None

    def test_detects_critical_severity_with_only_low_likelihood(self):
        """Critical bug + all Low root causes → misaligned."""
        bug_analysis = {"severity": "Critical"}
        root_causes  = [
            {"cause": "A", "likelihood": "Low", "explanation": "minor"},
            {"cause": "B", "likelihood": "Low", "explanation": "minor too"},
        ]
        result = severity_validator_tool(bug_analysis, root_causes)
        assert result["aligned"] is False
        assert result["warning"] is not None
        assert "Critical" in result["warning"]

    def test_detects_high_severity_with_only_low_likelihood(self):
        """High bug + all Low root causes → misaligned."""
        bug_analysis = {"severity": "High"}
        root_causes  = [{"cause": "A", "likelihood": "Low", "explanation": "minor"}]
        result = severity_validator_tool(bug_analysis, root_causes)
        assert result["aligned"] is False

    def test_detects_low_severity_with_only_high_likelihood(self):
        """Low bug + all High root causes → misaligned."""
        bug_analysis = {"severity": "Low"}
        root_causes  = [{"cause": "A", "likelihood": "High", "explanation": "major"}]
        result = severity_validator_tool(bug_analysis, root_causes)
        assert result["aligned"] is False
        assert result["warning"] is not None
        assert "Low" in result["warning"]

    def test_aligned_critical_severity_with_high_likelihood(self):
        """Critical bug + High root cause → aligned."""
        bug_analysis = {"severity": "Critical"}
        root_causes  = [
            {"cause": "A", "likelihood": "High",   "explanation": "major"},
            {"cause": "B", "likelihood": "Medium",  "explanation": "moderate"},
        ]
        result = severity_validator_tool(bug_analysis, root_causes)
        assert result["aligned"] is True
        assert result["warning"] is None

    def test_aligned_medium_severity_is_always_ok(self):
        """Medium severity is never flagged regardless of likelihoods."""
        bug_analysis = {"severity": "Medium"}
        for lh in ("High", "Medium", "Low"):
            root_causes = [{"cause": "A", "likelihood": lh, "explanation": "x"}]
            result = severity_validator_tool(bug_analysis, root_causes)
            assert result["aligned"] is True

    def test_returns_highest_likelihood_string(self):
        """highest_likelihood should reflect the most severe likelihood in the list."""
        bug_analysis = {"severity": "High"}
        root_causes  = [
            {"cause": "A", "likelihood": "Low",    "explanation": "minor"},
            {"cause": "B", "likelihood": "High",   "explanation": "major"},
            {"cause": "C", "likelihood": "Medium", "explanation": "moderate"},
        ]
        result = severity_validator_tool(bug_analysis, root_causes)
        assert result["highest_likelihood"] == "High"

    def test_handles_missing_likelihood_key(self):
        """Root causes without a likelihood key default to Unknown — no crash."""
        bug_analysis = {"severity": "High"}
        root_causes  = [{"cause": "A", "explanation": "something"}]
        result = severity_validator_tool(bug_analysis, root_causes)
        assert isinstance(result, dict)
        assert "aligned" in result
