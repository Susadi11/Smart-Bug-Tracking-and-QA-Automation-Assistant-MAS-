"""
CLI test runner — tests Agent 1 directly without the API layer.
Usage: python main.py
"""

import json
import os
import uuid
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from state import AgentState
from agents.bug_analyzer import bug_analyzer_node


def run_test(bug_description: str, code_snippet: str = None,
             platform: str = None, app_version: str = None) -> None:
    """Run a single bug analysis and print the result."""
    model = os.getenv("OLLAMA_MODEL", "llama3:8b")
    run_id = str(uuid.uuid4())[:8]
    log_path = f"logs/run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{run_id}.json"

    print(f"\n{'='*60}")
    print(f"  Agent 1 — Bug Analyzer  |  model: {model}")
    print(f"{'='*60}")
    print(f"Input:\n{bug_description}\n")

    state: AgentState = {
        "bug_description": bug_description,
        "code_snippet":    code_snippet,
        "platform":        platform,
        "app_version":     app_version,
        "user_severity":   None,
        "bug_analysis":    None,
        "test_cases":      None,
        "root_causes":     None,
        "bug_report":      None,
        "log_path":        log_path,
        "errors":          [],
    }

    result = bug_analyzer_node(state)

    if result["errors"]:
        print("ERRORS:")
        for e in result["errors"]:
            print(f"  x {e}")
        return

    print("Output:")
    print(json.dumps(dict(result["bug_analysis"]), indent=2))
    print(f"\nSaved : output/bug_analysis.json")
    print(f"Log   : {log_path}")


if __name__ == "__main__":
    run_test(
        bug_description=(
            "When a user tries to log in with valid credentials on the mobile app, "
            "the login button becomes unresponsive after the first failed attempt. "
            "The user has to force-close and reopen the app to try again. "
            "This started happening after the v2.3.1 update."
        ),
        platform="iOS 17",
        app_version="2.3.1",
    )

    run_test(
        bug_description=(
            "The checkout page crashes with a TypeError when the user clicks Pay Now. "
            "This only happens when the cart contains more than 5 items. "
            "The error appears in the browser console and the transaction is not completed."
        ),
        code_snippet=(
            "function processCart(items) {\n"
            "  const total = items.reduce((sum, item) => sum + item.price, 0);\n"
            "  return stripe.charge({ amount: total * 100 });\n"
            "  // TypeError: Cannot read properties of undefined (reading 'charge')\n"
            "}"
        ),
        platform="Chrome 124 / Windows 11",
        app_version="3.0.0",
    )
