"""
File I/O tools shared across all agents.
"""

import json
import os
from pathlib import Path
from typing import Any


def save_to_file(path: str, content: str) -> bool:
    """
    Write content to path, creating parent dirs if needed.
    Never raises — returns False on error.
    """
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False


def read_from_file(path: str) -> str:
    """Read and return file contents. Raises FileNotFoundError if missing."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return p.read_text(encoding="utf-8")


def append_log(log_path: str, entry: dict) -> None:
    """
    Read existing JSON array from log_path (or start a new one),
    append entry, and write back atomically.
    """
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    existing: list = []
    if p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except (json.JSONDecodeError, ValueError):
            existing = []

    existing.append(entry)

    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
