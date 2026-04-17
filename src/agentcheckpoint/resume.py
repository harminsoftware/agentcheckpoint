"""Resume engine — load checkpoint state and continue from where the agent left off.

Validates state integrity (checksums) before resuming. Supports resuming
from the last successful step or from a specific step number.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from agentcheckpoint.core import CheckpointConfig, CheckpointContext, _build_storage
from agentcheckpoint.serializer import Serializer, get_serializer
from agentcheckpoint.state import AgentState
from agentcheckpoint.storage import StorageBackend

logger = logging.getLogger(__name__)


class ResumeError(Exception):
    """Raised when resume fails."""


class ResumeResult:
    """Result of a resume operation. Contains the loaded state and a checkpoint context
    ready to continue the run.
    """

    def __init__(self, state: AgentState, context: CheckpointContext):
        self.state = state
        self.context = context
        self.run_id = state.run_id
        self.step_number = state.step_number
        self.messages = state.messages
        self.tool_calls = state.tool_calls
        self.variables = state.variables
        self.agent_input = state.agent_input
        self.metadata = state.metadata
        self.error = state.error

    def __repr__(self) -> str:
        return (
            f"ResumeResult(run_id={self.run_id!r}, step={self.step_number}, "
            f"messages={len(self.messages)}, tools={len(self.tool_calls)})"
        )


def resume(
    run_id: str,
    step: int | None = None,
    *,
    config: CheckpointConfig | None = None,
    storage: StorageBackend | None = None,
    serializer: Serializer | None = None,
    verify_checksum: bool = True,
    storage_path: str = "./checkpoints",
    **kwargs,
) -> ResumeResult:
    """Load a checkpoint and prepare to resume the agent run.

    Args:
        run_id: The run to resume.
        step: Step number to resume from. If None, resumes from the last successful step.
        config: Optional CheckpointConfig. Defaults will use local storage.
        storage: Optional pre-built storage backend.
        serializer: Optional serializer. Auto-detected from checkpoint if not provided.
        verify_checksum: Whether to verify state integrity before resuming.
        storage_path: Path for local storage (if no config/storage provided).

    Returns:
        ResumeResult with loaded state and a CheckpointContext to continue the run.

    Raises:
        ResumeError: If the checkpoint is not found, corrupted, or invalid.
    """
    # Build config
    if config is None:
        config = CheckpointConfig(run_id=run_id, storage_path=storage_path, **kwargs)
    else:
        config = config.model_copy(update={"run_id": run_id})

    # Build storage
    if storage is None:
        storage = _build_storage(config)

    # Build serializer
    if serializer is None:
        serializer = get_serializer(config.serializer_format)

    # Determine which step to resume from
    if step is None:
        step = _find_resume_step(storage, run_id)

    if step is None:
        raise ResumeError(f"No checkpoints found for run: {run_id}")

    logger.info(f"Resuming run={run_id} from step={step}")

    # Load the checkpoint data
    try:
        data = storage.load(run_id, step)
    except FileNotFoundError:
        raise ResumeError(f"Checkpoint not found: run={run_id}, step={step}")

    # Deserialize
    try:
        state_dict = serializer.deserialize(data)
        state = AgentState.from_dict(state_dict)
    except Exception as e:
        raise ResumeError(f"Failed to deserialize checkpoint: {e}") from e

    # Verify integrity
    if verify_checksum:
        if not state.verify_checksum():
            raise ResumeError(
                f"Checkpoint integrity check failed: run={run_id}, step={step}. "
                "The checkpoint data may be corrupted."
            )

    # Create a new context that continues from this point
    ctx = CheckpointContext(config=config, storage=storage, serializer=serializer)
    ctx.run_id = run_id
    ctx._step_number = state.step_number
    ctx._is_active = True

    # Update run status
    from agentcheckpoint.state import RunInfo
    from datetime import datetime, timezone

    run_meta = storage.load_run_meta(run_id)
    if run_meta:
        run_meta.status = "running"
        run_meta.updated_at = datetime.now(timezone.utc).isoformat()
        storage.save_run_meta(run_meta)

    logger.info(
        f"Resumed: run={run_id}, step={step}, "
        f"messages={len(state.messages)}, tools={len(state.tool_calls)}"
    )

    return ResumeResult(state=state, context=ctx)


def _find_resume_step(storage: StorageBackend, run_id: str) -> Optional[int]:
    """Find the best step to resume from.

    Strategy: Find the last step that doesn't have an error.
    If all steps have errors, resume from the last step before the error.
    """
    steps = storage.list_steps(run_id)
    if not steps:
        return None

    # Try to find the last non-error step by loading and checking each
    # Start from the latest and work backwards
    serializer = get_serializer("auto")

    for step_info in reversed(steps):
        try:
            data = storage.load(run_id, step_info.step_number)
            state_dict = serializer.deserialize(data)
            state = AgentState.from_dict(state_dict)

            if not state.has_error:
                return step_info.step_number
        except Exception:
            continue

    # If all steps have errors, return the step before the first error
    if len(steps) > 1:
        return steps[-2].step_number

    # Only one step and it has an error — resume from it anyway
    return steps[0].step_number


def list_runs(
    storage: StorageBackend | None = None,
    storage_path: str = "./checkpoints",
) -> list:
    """List all available runs."""
    if storage is None:
        storage = LocalStorageBackend(base_path=storage_path)
    return storage.list_runs()


def inspect_run(
    run_id: str,
    step: int | None = None,
    storage: StorageBackend | None = None,
    storage_path: str = "./checkpoints",
) -> AgentState | list:
    """Inspect a run's state at a specific step, or list all steps.

    If step is None, returns list of StepInfo.
    If step is specified, returns the AgentState at that step.
    """
    if storage is None:
        from agentcheckpoint.storage.local import LocalStorageBackend
        storage = LocalStorageBackend(base_path=storage_path)

    if step is None:
        return storage.list_steps(run_id)

    data = storage.load(run_id, step)
    serializer = get_serializer("auto")
    state_dict = serializer.deserialize(data)
    return AgentState.from_dict(state_dict)


# Re-export for convenience
from agentcheckpoint.storage.local import LocalStorageBackend  # noqa: E402
