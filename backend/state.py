"""
Shared global state passed through all agents in the MAS pipeline.
"""

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
    type: str        # Positive | Negative | Edge
    description: str
    steps: List[str]
    expected: str


class RootCause(TypedDict):
    cause: str
    likelihood: str  # High | Medium | Low
    explanation: str


class AgentState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────────────
    bug_description: str
    code_snippet: Optional[str]
    platform: Optional[str]
    app_version: Optional[str]
    user_severity: Optional[str]

    # ── Agent outputs ───────────────────────────────────────────────────────────
    bug_analysis: Optional[BugAnalysis]       # Agent 1
    test_cases: Optional[List[TestCase]]      # Agent 2
    root_causes: Optional[List[RootCause]]    # Agent 3
    bug_report: Optional[str]                 # Agent 4

    # ── Pipeline metadata ────────────────────────────────────────────────────────
    log_path: str
    errors: List[str]
