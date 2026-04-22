"""Shared global state passed through all agents in the MAS pipeline."""

from typing import TypedDict, Optional, List


class BugAnalysis(TypedDict):
    title: str
    severity: str
    priority: str
    steps_to_reproduce: List[str]
    expected_result: str
    actual_result: str
    affected_components: List[str]


class TestCase(TypedDict):
    id: str
    type: str           # Positive | Negative | Edge
    description: str
    steps: List[str]
    expected: str


class RootCause(TypedDict):
    cause: str
    likelihood: str     # High | Medium | Low
    explanation: str


class AgentState(TypedDict):
    # Input fields
    bug_description: str
    code_snippet: Optional[str]
    platform: Optional[str]
    app_version: Optional[str]
    user_severity: Optional[str]

    # Agent outputs
    bug_analysis: Optional[BugAnalysis]
    test_cases: Optional[List[TestCase]]
    root_causes: Optional[List[RootCause]]
    bug_report: Optional[str]

    # Pipeline metadata
    log_path: str
    errors: List[str]
