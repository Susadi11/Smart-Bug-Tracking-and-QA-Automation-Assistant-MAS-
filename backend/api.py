"""
FastAPI backend — run-based polling architecture.

Endpoints:
  POST /api/runs       → start pipeline, return run_id
  GET  /api/runs       → list all runs
  GET  /api/runs/{id}  → full run details + agent outputs
  GET  /api/config     → default model from .env
"""

import os

# Bypass system proxy for local Ollama connections (macOS / Windows).
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

import json
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

from agents.bug_analyzer        import bug_analyzer_node
from agents.test_case_generator import test_case_generator_node
from agents.root_cause_analyzer import root_cause_analyzer_node
from agents.bug_report_generator import bug_report_generator_node
from state import AgentState

RUNS_DIR = Path("runs")
LOGS_DIR = Path("logs")
RUNS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

PIPELINE_STEPS = [
    {"key": "bug_analyzer",         "label": "Bug Analyzer"},
    {"key": "test_case_generator",  "label": "Test Case Generator"},
    {"key": "root_cause_analyzer",  "label": "Root Cause Analyzer"},
    {"key": "bug_report_generator", "label": "Bug Report Generator"},
]

AGENT_FNS = [
    bug_analyzer_node,
    test_case_generator_node,
    root_cause_analyzer_node,
    bug_report_generator_node,
]

_lock: threading.Lock = threading.Lock()
_runs: Dict[str, dict] = {}

app = FastAPI(title="Smart Bug Tracking & QA Automation Assistant", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic request / response models

class RunStatus(str, Enum):
    pending   = "pending"
    running   = "running"
    completed = "completed"
    failed    = "failed"


class RunCreateRequest(BaseModel):
    bug_description: str = Field(..., min_length=5, max_length=6000)
    code_snippet:    Optional[str] = None
    platform:        Optional[str] = None
    app_version:     Optional[str] = None
    user_severity:   Optional[str] = None
    model_name:      str  = Field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "phi3:mini"))
    ollama_base_url: str  = Field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    num_ctx:         int  = Field(default=2048, ge=512, le=32768)


class RunSummary(BaseModel):
    run_id:             str
    status:             RunStatus
    progress_percent:   int
    current_step_key:   Optional[str]
    current_step_label: Optional[str]
    started_at:         str
    completed_at:       Optional[str]


class StepResult(BaseModel):
    key:    str
    label:  str
    status: str


class RunDetails(RunSummary):
    steps:    List[StepResult]
    errors:   List[str]
    result:   Dict[str, Any]
    log_path: str


# Helpers

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_run(run: dict) -> None:
    """Persist run state to disk as JSON."""
    path = RUNS_DIR / f"{run['run_id']}.json"
    path.write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")


def _to_summary(run: dict) -> RunSummary:
    return RunSummary(
        run_id=run["run_id"],
        status=run["status"],
        progress_percent=run["progress_percent"],
        current_step_key=run.get("current_step_key"),
        current_step_label=run.get("current_step_label"),
        started_at=run["started_at"],
        completed_at=run.get("completed_at"),
    )


def _to_details(run: dict) -> RunDetails:
    return RunDetails(
        **_to_summary(run).model_dump(),
        steps=run["steps"],
        errors=run["errors"],
        result=run["result"],
        log_path=run["log_path"],
    )


# Background pipeline worker

def _pipeline_worker(run_id: str, req: RunCreateRequest) -> None:
    """Execute all agents sequentially in a background thread."""
    with _lock:
        run = _runs[run_id]
        run["status"] = RunStatus.running
        _save_run(run)

    try:
        os.environ["OLLAMA_MODEL"]    = req.model_name
        os.environ["OLLAMA_BASE_URL"] = req.ollama_base_url
        os.environ["OLLAMA_NUM_CTX"]  = str(req.num_ctx)

        # Pull model if not already available (best-effort, non-blocking)
        try:
            with httpx.Client(timeout=10) as client:
                tags = client.get(f"{req.ollama_base_url}/api/tags").json()
                names = [m["name"] for m in tags.get("models", [])]
                if not any(req.model_name in n or n in req.model_name for n in names):
                    client.post(
                        f"{req.ollama_base_url}/api/pull",
                        json={"name": req.model_name},
                        timeout=600,
                    )
        except Exception:
            pass

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_path = str(LOGS_DIR / f"run_{ts}_{run_id[:8]}.json")

        state: AgentState = {
            "bug_description": req.bug_description,
            "code_snippet":    req.code_snippet,
            "platform":        req.platform,
            "app_version":     req.app_version,
            "user_severity":   req.user_severity,
            "bug_analysis":    None,
            "test_cases":      None,
            "root_causes":     None,
            "bug_report":      None,
            "log_path":        log_path,
            "errors":          [],
        }

        for i, (step, agent_fn) in enumerate(zip(PIPELINE_STEPS, AGENT_FNS)):
            with _lock:
                run["steps"][i]["status"]   = "running"
                run["current_step_key"]     = step["key"]
                run["current_step_label"]   = step["label"]
                _save_run(run)

            state = agent_fn(state)

            # Build result incrementally so the frontend can read it mid-pipeline.
            intermediate: Dict[str, Any] = {}
            if state.get("bug_analysis"):
                intermediate["bug_analysis"] = dict(state["bug_analysis"])
            if state.get("test_cases"):
                intermediate["test_cases"] = [dict(tc) for tc in state["test_cases"]]
            if state.get("root_causes"):
                intermediate["root_causes"] = [dict(rc) for rc in state["root_causes"]]
            if state.get("bug_report"):
                intermediate["bug_report"] = state["bug_report"]

            with _lock:
                run["steps"][i]["status"] = "completed"
                run["progress_percent"]   = (i + 1) * 25
                run["result"]             = intermediate
                _save_run(run)

        with _lock:
            run["status"]       = RunStatus.completed
            run["completed_at"] = _now()
            run["result"]       = intermediate
            run["errors"]       = state.get("errors", [])
            _save_run(run)

    except Exception as exc:
        with _lock:
            run["status"]       = RunStatus.failed
            run["completed_at"] = _now()
            run["errors"].append(f"Pipeline error: {exc}")
            _save_run(run)


# Startup — reload persisted runs from disk

@app.on_event("startup")
def _load_runs() -> None:
    for f in RUNS_DIR.glob("*.json"):
        try:
            run = json.loads(f.read_text(encoding="utf-8"))
            if run.get("status") == RunStatus.running:
                run["status"] = RunStatus.failed
                run["errors"].append("Server restarted during execution")
                f.write_text(json.dumps(run, indent=2), encoding="utf-8")
            _runs[run["run_id"]] = run
        except Exception:
            pass


# Endpoints

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    """Return backend configuration for the frontend."""
    return {
        "default_model": os.getenv("OLLAMA_MODEL", "phi3:mini"),
        "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    }


@app.post("/api/runs", response_model=RunSummary, status_code=201)
def create_run(req: RunCreateRequest):
    run_id = str(uuid.uuid4())

    run = {
        "run_id":             run_id,
        "status":             RunStatus.pending,
        "progress_percent":   0,
        "current_step_key":   None,
        "current_step_label": None,
        "started_at":         _now(),
        "completed_at":       None,
        "steps":              [{"key": s["key"], "label": s["label"], "status": "pending"}
                               for s in PIPELINE_STEPS],
        "errors":             [],
        "result":             {},
        "log_path":           "",
    }

    with _lock:
        _runs[run_id] = run
        _save_run(run)

    threading.Thread(target=_pipeline_worker, args=(run_id, req), daemon=True).start()
    return _to_summary(run)


@app.get("/api/runs", response_model=List[RunSummary])
def list_runs():
    with _lock:
        return [_to_summary(r) for r in _runs.values()]


@app.get("/api/runs/{run_id}", response_model=RunDetails)
def get_run(run_id: str):
    with _lock:
        run = _runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _to_details(run)
