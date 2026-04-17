"""FastAPI backend for the AgentCheckpoint replay dashboard.

Provides REST API + WebSocket for inspecting and replaying agent runs.
"""

from __future__ import annotations

import json
from typing import Optional

from agentcheckpoint.resume import inspect_run, list_runs
from agentcheckpoint.serializer import get_serializer
from agentcheckpoint.state import AgentState
from agentcheckpoint.storage.local import LocalStorageBackend


def create_app(storage_path: str = "./checkpoints"):
    """Create the FastAPI application.

    Requires: pip install agentcheckpoint[dashboard]
    """
    try:
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse
    except ImportError:
        raise ImportError(
            "FastAPI is required for the dashboard. "
            "Install with: pip install agentcheckpoint[dashboard]"
        )

    app = FastAPI(
        title="AgentCheckpoint Dashboard",
        description="Replay dashboard for AI agent checkpoints",
        version="0.1.0",
    )

    # CORS for React frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    storage = LocalStorageBackend(base_path=storage_path)
    serializer = get_serializer("auto")

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/runs")
    async def get_runs():
        """List all checkpoint runs."""
        runs = storage.list_runs()
        from dataclasses import asdict
        return {"runs": [asdict(r) for r in runs], "total": len(runs)}

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str):
        """Get run details and step list."""
        meta = storage.load_run_meta(run_id)
        steps = storage.list_steps(run_id)

        if not steps and not meta:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

        from dataclasses import asdict
        return {
            "run": asdict(meta) if meta else {"run_id": run_id, "status": "unknown"},
            "steps": [asdict(s) for s in steps],
            "total_steps": len(steps),
        }

    @app.get("/api/runs/{run_id}/steps/{step}")
    async def get_step(run_id: str, step: int):
        """Get full state at a specific step."""
        try:
            data = storage.load(run_id, step)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Step not found: run={run_id}, step={step}",
            )

        state_dict = serializer.deserialize(data)
        state = AgentState.from_dict(state_dict)
        return {"state": state.to_dict()}

    @app.get("/api/runs/{run_id}/diff/{step1}/{step2}")
    async def get_diff(run_id: str, step1: int, step2: int):
        """Get diff between two steps."""
        try:
            data1 = storage.load(run_id, step1)
            data2 = storage.load(run_id, step2)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

        state1 = AgentState.from_dict(serializer.deserialize(data1))
        state2 = AgentState.from_dict(serializer.deserialize(data2))

        # Compute differences
        diff = {
            "step1": step1,
            "step2": step2,
            "new_messages": state2.messages[len(state1.messages):],
            "new_tool_calls": state2.tool_calls[len(state1.tool_calls):],
            "changed_variables": {
                k: {"old": state1.variables.get(k), "new": v}
                for k, v in state2.variables.items()
                if state1.variables.get(k) != v
            },
            "metadata_diff": {
                k: {"old": state1.metadata.get(k), "new": v}
                for k, v in state2.metadata.items()
                if state1.metadata.get(k) != v
            },
        }
        return {"diff": diff}

    @app.post("/api/runs/{run_id}/resume")
    async def resume_run(run_id: str, step: Optional[int] = None):
        """Trigger resume for a run."""
        from agentcheckpoint.resume import resume

        try:
            result = resume(run_id=run_id, step=step, storage_path=storage_path)
            return {
                "status": "resumed",
                "run_id": result.run_id,
                "from_step": result.step_number,
                "messages": len(result.messages),
                "tool_calls": len(result.tool_calls),
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.delete("/api/runs/{run_id}")
    async def delete_run(run_id: str):
        """Delete all checkpoints for a run."""
        if not storage.run_exists(run_id):
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

        steps = storage.list_steps(run_id)
        storage.delete_run(run_id)
        return {"status": "deleted", "run_id": run_id, "steps_deleted": len(steps)}

    return app
