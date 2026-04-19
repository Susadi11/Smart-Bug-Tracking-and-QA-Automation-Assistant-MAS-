"""
Structured logging tool for all agents.
Each agent call writes a timestamped entry to logs/pipeline.log.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


def _ensure_logs_dir() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def log_agent_event(agent_name: str, event: str, payload: Dict[str, Any] | None = None) -> None:
    """
    Append a structured log line to logs/pipeline.log.

    Args:
        agent_name: e.g. "BugAnalyzer"
        event:      e.g. "start", "success", "error"
        payload:    optional dict with extra context (truncated for brevity)
    """
    _ensure_logs_dir()

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent_name,
        "event": event,
    }
    if payload:
        # Truncate large string values so logs stay readable
        entry["data"] = {
            k: (v[:200] + "…" if isinstance(v, str) and len(v) > 200 else v)
            for k, v in payload.items()
        }

    log_path = LOGS_DIR / "pipeline.log"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
