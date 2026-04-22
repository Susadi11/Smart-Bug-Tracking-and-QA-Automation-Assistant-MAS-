"""Structured logging tool — writes timestamped entries to logs/pipeline.log."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


def _ensure_logs_dir() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def log_agent_event(agent_name: str, event: str, payload: Dict[str, Any] | None = None) -> None:
    """
    Append a structured JSON log line to logs/pipeline.log.

    Args:
        agent_name: Name of the agent (e.g. "BugAnalyzer").
        event:      Event type (e.g. "start", "success", "error").
        payload:    Optional dict with extra context. Large string values
                    are truncated to 200 characters for readability.
    """
    _ensure_logs_dir()

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent_name,
        "event": event,
    }
    if payload:
        entry["data"] = {
            k: (v[:200] + "…" if isinstance(v, str) and len(v) > 200 else v)
            for k, v in payload.items()
        }

    log_path = LOGS_DIR / "pipeline.log"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
