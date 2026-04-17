"""Core checkpoint engine — context manager, decorator, and step interceptor.

This is the heart of the SDK. It provides two integration patterns:

1. Context manager:
    with checkpoint() as cp:
        cp.step(state)  # Manual checkpointing

2. Decorator:
    @checkpointable()
    def my_agent(task):
        ...
"""

from __future__ import annotations

import functools
import logging
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from agentcheckpoint.serializer import AutoSerializer, Serializer, get_serializer
from agentcheckpoint.state import AgentState, ErrorInfo, RunInfo
from agentcheckpoint.storage import StorageBackend
from agentcheckpoint.storage.local import LocalStorageBackend

logger = logging.getLogger(__name__)


class CheckpointConfig(BaseModel):
    """Configuration for checkpoint behavior.

    Zero-config defaults: local disk storage, auto serialization, sync writes.
    """

    storage_backend: Optional[str] = Field(
        default=None,
        description="Storage backend type: 'local', 's3', 'postgres'. Default: local",
    )
    storage_path: str = Field(
        default="./checkpoints",
        description="Base path for local storage",
    )
    serializer_format: str = Field(
        default="auto",
        description="Serialization format: 'auto', 'json', 'pickle', 'compressed'",
    )
    async_writes: bool = Field(
        default=False,
        description="Enable background async writes",
    )
    run_id: Optional[str] = Field(
        default=None,
        description="Custom run ID. Auto-generated if not provided.",
    )
    framework: str = Field(
        default="generic",
        description="Agent framework name for metadata",
    )
    model: str = Field(
        default="",
        description="Model name for metadata",
    )

    # S3 config
    s3_bucket: Optional[str] = None
    s3_prefix: str = "checkpoints"
    s3_endpoint_url: Optional[str] = None
    s3_region: Optional[str] = None

    # Postgres config
    pg_conninfo: Optional[str] = None

    model_config = {"arbitrary_types_allowed": True}


def _build_storage(config: CheckpointConfig) -> StorageBackend:
    """Create a storage backend from config."""
    backend_type = config.storage_backend or "local"

    if backend_type == "local":
        backend = LocalStorageBackend(base_path=config.storage_path)
    elif backend_type == "s3":
        from agentcheckpoint.storage.s3 import S3StorageBackend

        backend = S3StorageBackend(
            bucket=config.s3_bucket or "agentcheckpoint",
            prefix=config.s3_prefix,
            endpoint_url=config.s3_endpoint_url,
            region_name=config.s3_region,
        )
    elif backend_type == "postgres":
        from agentcheckpoint.storage.postgres import PostgresStorageBackend

        backend = PostgresStorageBackend(
            conninfo=config.pg_conninfo or "",
        )
    else:
        raise ValueError(f"Unknown storage backend: {backend_type}")

    if config.async_writes:
        from agentcheckpoint.storage.async_writer import AsyncStorageBackend

        backend = AsyncStorageBackend(inner=backend)

    return backend


class CheckpointContext:
    """Manages the lifecycle of a checkpointed agent run.

    Tracks steps, captures state, handles errors, and writes checkpoints
    to the configured storage backend.
    """

    def __init__(
        self,
        config: CheckpointConfig | None = None,
        storage: StorageBackend | None = None,
        serializer: Serializer | None = None,
    ):
        self.config = config or CheckpointConfig()
        self.run_id = self.config.run_id or str(uuid.uuid4())[:12]
        self._storage = storage or _build_storage(self.config)
        self._serializer = serializer or get_serializer(self.config.serializer_format)
        self._step_number = 0
        self._started_at = datetime.now(timezone.utc)
        self._current_state: AgentState | None = None
        self._is_active = False

    @property
    def step_number(self) -> int:
        return self._step_number

    @property
    def storage(self) -> StorageBackend:
        return self._storage

    def start(self) -> None:
        """Initialize the run."""
        self._is_active = True
        self._started_at = datetime.now(timezone.utc)

        # Save initial run metadata
        run_info = RunInfo(
            run_id=self.run_id,
            created_at=self._started_at.isoformat(),
            updated_at=self._started_at.isoformat(),
            total_steps=0,
            status="running",
            framework=self.config.framework,
            model=self.config.model,
        )
        self._storage.save_run_meta(run_info)
        logger.info(f"Started checkpoint run: {self.run_id}")

    def step(
        self,
        messages: list[dict] | None = None,
        tool_calls: list[dict] | None = None,
        variables: dict[str, Any] | None = None,
        agent_input: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Record a checkpoint at the current step.

        Returns the step number.
        """
        if not self._is_active:
            raise RuntimeError("Checkpoint context is not active. Use 'with checkpoint() as cp:'")

        self._step_number += 1

        state = AgentState(
            run_id=self.run_id,
            step_number=self._step_number,
            agent_input=agent_input,
            messages=messages or [],
            tool_calls=tool_calls or [],
            variables=variables or {},
            metadata={
                "framework": self.config.framework,
                "model": self.config.model,
                **(metadata or {}),
            },
        )

        state.compute_checksum()
        self._current_state = state
        self._save_state(state)

        logger.debug(f"Checkpoint saved: run={self.run_id}, step={self._step_number}")
        return self._step_number

    def save_state(self, state: AgentState) -> int:
        """Save a fully-constructed AgentState directly.

        Useful for framework integrations that build state externally.
        """
        if not self._is_active:
            raise RuntimeError("Checkpoint context is not active.")

        self._step_number = state.step_number
        state.compute_checksum()
        self._current_state = state
        self._save_state(state)

        return state.step_number

    def capture_error(self, error: BaseException) -> None:
        """Capture an error and save it as part of the current state."""
        error_info = ErrorInfo.from_exception(error, self._step_number)

        if self._current_state:
            self._current_state.error = error_info
            self._current_state.compute_checksum()
            self._save_state(self._current_state)
        else:
            # Create a minimal error state
            state = AgentState(
                run_id=self.run_id,
                step_number=self._step_number,
                error=error_info,
                metadata={"framework": self.config.framework, "model": self.config.model},
            )
            state.compute_checksum()
            self._save_state(state)

    def complete(self) -> None:
        """Mark the run as completed."""
        self._is_active = False
        now = datetime.now(timezone.utc)
        run_info = RunInfo(
            run_id=self.run_id,
            created_at=self._started_at.isoformat(),
            updated_at=now.isoformat(),
            total_steps=self._step_number,
            status="completed",
            framework=self.config.framework,
            model=self.config.model,
        )
        self._storage.save_run_meta(run_info)
        logger.info(f"Run completed: {self.run_id} ({self._step_number} steps)")

    def fail(self, error: BaseException | None = None) -> None:
        """Mark the run as failed."""
        self._is_active = False
        if error:
            self.capture_error(error)
        now = datetime.now(timezone.utc)
        run_info = RunInfo(
            run_id=self.run_id,
            created_at=self._started_at.isoformat(),
            updated_at=now.isoformat(),
            total_steps=self._step_number,
            status="failed",
            framework=self.config.framework,
            model=self.config.model,
        )
        self._storage.save_run_meta(run_info)
        logger.info(f"Run failed: {self.run_id} at step {self._step_number}")

    def _save_state(self, state: AgentState) -> None:
        """Serialize and persist state."""
        data = self._serializer.serialize(state.to_dict())
        self._storage.save(
            run_id=state.run_id,
            step=state.step_number,
            data=data,
            metadata={"checksum": state._checksum or ""},
        )

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.fail(exc_val)
        else:
            self.complete()

        # Close async writer if applicable
        from agentcheckpoint.storage.async_writer import AsyncStorageBackend

        if isinstance(self._storage, AsyncStorageBackend):
            self._storage.close()

        return False  # Don't suppress exceptions


def checkpoint(
    config: CheckpointConfig | None = None,
    *,
    run_id: str | None = None,
    storage_path: str = "./checkpoints",
    serializer_format: str = "auto",
    async_writes: bool = False,
    framework: str = "generic",
    model: str = "",
    **kwargs,
) -> CheckpointContext:
    """Create a checkpoint context manager.

    Usage:
        with checkpoint() as cp:
            result = agent.run(task)
            cp.step(messages=result.messages)

    Or with configuration:
        with checkpoint(storage_path="/data/checkpoints", framework="langchain") as cp:
            ...
    """
    if config is None:
        config = CheckpointConfig(
            run_id=run_id,
            storage_path=storage_path,
            serializer_format=serializer_format,
            async_writes=async_writes,
            framework=framework,
            model=model,
            **kwargs,
        )
    return CheckpointContext(config=config)


def checkpointable(
    config: CheckpointConfig | None = None,
    *,
    capture_args: bool = True,
    capture_return: bool = True,
    **checkpoint_kwargs,
) -> Callable:
    """Decorator that auto-checkpoints a function's execution.

    Usage:
        @checkpointable()
        def my_agent(task: str):
            # Each call to this function creates a checkpoint step
            result = llm.invoke(task)
            return result

    The decorator wraps the function in a checkpoint context. Each
    invocation creates a new step with the function's args and return value.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            ctx = checkpoint(config=config, **checkpoint_kwargs)

            with ctx as cp:
                # Capture input
                agent_input = None
                if capture_args:
                    agent_input = {"args": list(args), "kwargs": kwargs}

                try:
                    result = func(*args, **kwargs)

                    # Checkpoint the result
                    variables = {}
                    if capture_return:
                        variables["return_value"] = result

                    cp.step(
                        agent_input=agent_input,
                        variables=variables,
                    )

                    return result
                except Exception as e:
                    cp.capture_error(e)
                    raise

        # Expose the checkpoint context for advanced usage
        wrapper._checkpoint_config = config
        return wrapper

    return decorator
