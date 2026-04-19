"""
FastAPI backend — run-based polling architecture.
POST /api/runs  → start pipeline in background thread
GET  /api/runs  → list all runs
GET  /api/runs/{run_id} → get run details + agent outputs
"""

import json
import os
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

from graph import build_graph
from state import AgentState

# ── Config ─────────────────────────────────────────────────────────────────────

RUNS_DIR  = Path("runs")
LOGS_DIR  = Path("logs")
RUNS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

PIPELINE_STEPS = [
    {"key": "bug_analyzer",        "label": "Bug Analyzer"},
    {"key": "test_case_generator", "label": "Test Case Generator"},
    {"key": "root_cause_analyzer", "label": "Root Cause Analyzer"},
    {"key": "bug_report_generator","label": "Bug Report Generator"},
]

_lock: threading.Lock = threading.Lock()
_runs: Dict[str, dict] = {}

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Smart Bug Tracking & QA Automation Assistant", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic models ────────────────────────────────────────────────────────────

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
    model_name:      str = Field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3:8b"))
    ollama_base_url: str = Field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    num_ctx:         int = Field(default=2048, ge=512, le=32768)


class RunSummary(BaseModel):
    run_id:            str
    status:            RunStatus
    progress_percent:  int
    current_step_key:  Optional[str]
    current_step_label:Optional[str]
    started_at:        str
    completed_at:      Optional[str]


class StepResult(BaseModel):
    key:    str
    label:  str
    status: str   # pending | running | completed | failed


class RunDetails(RunSummary):
    steps:    List[StepResult]
    errors:   List[str]
    result:   Dict[str, Any]
    log_path: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_run(run: dict) -> None:
    path = RUNS_DIR / f"{run['run_id']}.json"
    path.write_text(json.dumps(run, indent=2), encoding="utf-8")


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


# ── Background worker ──────────────────────────────────────────────────────────

def _pipeline_worker(run_id: str, req: RunCreateRequest) -> None:
    with _lock:
        run = _runs[run_id]
        run["status"] = RunStatus.running
        _save_run(run)

    try:
        # Set env vars for agents to pick up
        os.environ["OLLAMA_MODEL"]      = req.model_name
        os.environ["OLLAMA_BASE_URL"]   = req.ollama_base_url
        os.environ["OLLAMA_NUM_CTX"]    = str(req.num_ctx)

        # Pull model if not already available
        try:
            with httpx.Client(timeout=10) as client:
                tags_resp = client.get(f"{req.ollama_base_url}/api/tags")
                names = [m["name"] for m in tags_resp.json().get("models", [])]
                # normalise: "llama3:8b" and "llama3" both match "llama3:8b"
                if not any(req.model_name in n or n in req.model_name for n in names):
                    client.post(
                        f"{req.ollama_base_url}/api/pull",
                        json={"name": req.model_name},
                        timeout=600,
                    )
        except Exception:
            pass  # best-effort; the LLM call itself will surface any real error

        log_path = run["log_path"]
        graph = build_graph()

        initial_state: AgentState = {
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

        # Stream node-by-node so we can update progress after each agent
        step_keys = [s["key"] for s in PIPELINE_STEPS]
        final_state = initial_state

        for chunk in graph.stream(initial_state, stream_mode="updates"):
            for node_name, state_update in chunk.items():
                if node_name not in step_keys:
                    continue
                final_state = {**final_state, **state_update}
                idx = step_keys.index(node_name)

                with _lock:
                    run["steps"][idx]["status"] = "completed"
                    run["progress_percent"] = (idx + 1) * 25
                    run["current_step_key"]   = node_name
                    run["current_step_label"] = PIPELINE_STEPS[idx]["label"]
                    _save_run(run)

        # Build result payload
        result: Dict[str, Any] = {}
        if final_state.get("bug_analysis"):
            result["bug_analysis"] = dict(final_state["bug_analysis"])
        if final_state.get("test_cases"):
            result["test_cases"] = [dict(tc) for tc in final_state["test_cases"]]
        if final_state.get("root_causes"):
            result["root_causes"] = [dict(rc) for rc in final_state["root_causes"]]
        if final_state.get("bug_report"):
            result["bug_report"] = final_state["bug_report"]

        with _lock:
            run["status"]       = RunStatus.completed
            run["completed_at"] = _now()
            run["result"]       = result
            run["errors"]       = final_state.get("errors", [])
            _save_run(run)

    except Exception as exc:
        with _lock:
            run["status"]       = RunStatus.failed
            run["completed_at"] = _now()
            run["errors"].append(f"Pipeline error: {exc}")
            _save_run(run)


# ── Startup: reload persisted runs ────────────────────────────────────────────

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


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/runs", response_model=RunSummary, status_code=201)
def create_run(req: RunCreateRequest):
    run_id   = str(uuid.uuid4())
    ts       = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = str(LOGS_DIR / f"run_{ts}_{run_id[:8]}.json")

    run = {
        "run_id":            run_id,
        "status":            RunStatus.pending,
        "progress_percent":  0,
        "current_step_key":  None,
        "current_step_label":None,
        "started_at":        _now(),
        "completed_at":      None,
        "steps":             [{"key": s["key"], "label": s["label"], "status": "pending"}
                               for s in PIPELINE_STEPS],
        "errors":            [],
        "result":            {},
        "log_path":          log_path,
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
