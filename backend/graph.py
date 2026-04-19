from langgraph.graph import StateGraph, START, END

from state import AgentState
from agents.bug_analyzer import bug_analyzer_node
from agents.test_case_generator import test_case_generator_node
from agents.root_cause_analyzer import root_cause_analyzer_node
from agents.bug_report_generator import bug_report_generator_node


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("bug_analyzer", bug_analyzer_node)
    g.add_node("test_case_generator", test_case_generator_node)
    g.add_node("root_cause_analyzer", root_cause_analyzer_node)
    g.add_node("bug_report_generator", bug_report_generator_node)
    g.add_edge(START, "bug_analyzer")
    g.add_edge("bug_analyzer", "test_case_generator")
    g.add_edge("test_case_generator", "root_cause_analyzer")
    g.add_edge("root_cause_analyzer", "bug_report_generator")
    g.add_edge("bug_report_generator", END)
    return g.compile()
