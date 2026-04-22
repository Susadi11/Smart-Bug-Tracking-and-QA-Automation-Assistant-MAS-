"""File I/O tools shared across all agents."""

import json
from pathlib import Path


def save_to_file(path: str, content: str) -> bool:
    """
    Write content to path, creating parent directories if needed.

    Never raises — returns False on error.

    Args:
        path:    Destination file path (relative or absolute).
        content: String content to write.

    Returns:
        True on success, False on failure.
    """
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False


def read_from_file(path: str) -> str:
    """
    Read and return file contents.

    Args:
        path: File path to read.

    Returns:
        The file's text content.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return p.read_text(encoding="utf-8")


def append_log(log_path: str, entry: dict) -> None:
    """
    Append a structured log entry to a JSON array file.

    Reads the existing array (or starts a new one), appends the entry,
    and writes back atomically via a temporary file.

    Args:
        log_path: Path to the JSON log file.
        entry:    Dict to append.
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
