"""
Tests for Agent 2 — Test Case Generator.

Covers:
  - Utility tools used by Agent 2
  - JSON parsing and validation helpers
  - Full node execution with mocked LLM (no Ollama dependency)
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure backend root is on the import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.test_case_generator import (
	_extract_json,
	_normalize_type,
	_validate_cases,
	test_case_generator_node,
)
from tools.analysis_tools import (
	evaluate_test_step_alignment,
	generate_test_case_skeletons,
)


def _sample_bug_analysis() -> dict:
	return {
		"title": "Checkout total mismatch",
		"severity": "High",
		"priority": "P2",
		"steps_to_reproduce": [
			"Add 3 items to cart",
			"Proceed to checkout",
			"Click Pay Now",
		],
		"expected_result": "Total equals sum of prices",
		"actual_result": "Total is incorrect",
		"affected_components": ["Payment", "UI / Frontend"],
	}


class TestAgent2Tools:
	def test_generate_test_case_skeletons_returns_minimum_templates(self):
		templates = generate_test_case_skeletons(_sample_bug_analysis(), count=3)
		assert len(templates) == 3
		assert templates[0]["type"] == "Positive"
		assert templates[1]["type"] == "Negative"
		assert templates[2]["type"] == "Edge"

	def test_evaluate_test_step_alignment_reports_coverage(self):
		bug_steps = _sample_bug_analysis()["steps_to_reproduce"]
		test_cases = [
			{
				"id": "TC-001",
				"type": "Positive",
				"description": "Happy path",
				"steps": ["Add 3 items to cart", "Proceed to checkout"],
				"expected": "Works",
			}
		]
		report = evaluate_test_step_alignment(bug_steps, test_cases)
		assert "coverage_ratio" in report
		assert report["total_steps"] == 3


class TestAgent2Helpers:
	def test_extract_json_from_markdown_fence(self):
		raw = '```json\n{"test_cases": []}\n```'
		out = _extract_json(raw)
		assert "test_cases" in out

	def test_extract_json_invalid_raises(self):
		with pytest.raises(ValueError):
			_extract_json("not-json")

	def test_normalize_type_maps_variants(self):
		assert _normalize_type("positive") == "Positive"
		assert _normalize_type("NEGATIVE") == "Negative"
		assert _normalize_type("edge case") == "Edge"
		assert _normalize_type("random") == "Edge"

	def test_validate_cases_requires_three_or_more(self):
		payload = {
			"test_cases": [
				{
					"id": "TC-001",
					"type": "Positive",
					"description": "Case 1",
					"steps": ["A", "B"],
					"expected": "X",
				}
			]
		}
		with pytest.raises(ValueError, match="At least 3 test cases"):
			_validate_cases(payload)


class TestTestCaseGeneratorNode:
	def _make_state(self) -> dict:
		with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
			log_path = f.name
		return {
			"bug_description": "Checkout total wrong when paying",
			"code_snippet": None,
			"platform": "Web — Chrome",
			"app_version": "3.0.0",
			"user_severity": "High",
			"bug_analysis": _sample_bug_analysis(),
			"test_cases": None,
			"root_causes": None,
			"bug_report": None,
			"log_path": log_path,
			"errors": [],
		}

	def _mock_llm_response(self) -> str:
		return json.dumps(
			{
				"test_cases": [
					{
						"id": "TC-001",
						"type": "Positive",
						"description": "Verify correct total with valid items",
						"steps": [
							"Add 3 items to cart",
							"Click checkout",
							"Click Pay Now",
						],
						"expected": "Total equals sum of item prices",
					},
					{
						"id": "TC-002",
						"type": "Negative",
						"description": "Verify handling of empty cart",
						"steps": ["Open empty cart", "Click checkout"],
						"expected": "Show cart is empty message",
					},
					{
						"id": "TC-003",
						"type": "Edge",
						"description": "Verify total with maximum items",
						"steps": ["Add 100 items", "Proceed to checkout"],
						"expected": "Total calculated correctly",
					},
				]
			}
		)

	@patch("agents.test_case_generator.OllamaLLM")
	def test_successful_generation(self, MockLLM):
		mock_instance = MagicMock()
		mock_instance.invoke.return_value = self._mock_llm_response()
		MockLLM.return_value = mock_instance

		state = self._make_state()
		result = test_case_generator_node(state)

		assert result["test_cases"] is not None
		assert len(result["test_cases"]) >= 3
		assert result["errors"] == []

	@patch("agents.test_case_generator.OllamaLLM")
	def test_missing_bug_analysis_is_captured(self, MockLLM):
		mock_instance = MagicMock()
		mock_instance.invoke.return_value = self._mock_llm_response()
		MockLLM.return_value = mock_instance

		state = self._make_state()
		state["bug_analysis"] = None
		result = test_case_generator_node(state)

		assert result["test_cases"] is None
		assert len(result["errors"]) > 0
		assert "Missing bug_analysis" in result["errors"][0]

	@patch("agents.test_case_generator.OllamaLLM")
	def test_malformed_response_is_captured(self, MockLLM):
		mock_instance = MagicMock()
		mock_instance.invoke.return_value = "invalid"
		MockLLM.return_value = mock_instance

		state = self._make_state()
		result = test_case_generator_node(state)

		assert result["test_cases"] is None
		assert len(result["errors"]) > 0
