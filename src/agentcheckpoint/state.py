"""State snapshot model for agent checkpoints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class ErrorInfo:
    """Captured error information from a failed agent step."""

    error_type: str
    message: str
    traceback: str
    step_number: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ErrorInfo:
        return cls(**data)

    @classmethod
    def from_exception(cls, exc: BaseException, step_number: int) -> ErrorInfo:
        import traceback as tb

        return cls(
            error_type=type(exc).__name__,
            message=str(exc),
            traceback="".join(tb.format_exception(type(exc), exc, exc.__traceback__)),
            step_number=step_number,
        )


@dataclass
class StepInfo:
    """Metadata about a single checkpoint step."""

    step_number: int
    timestamp: str
    checksum: str
    size_bytes: int
    has_error: bool = False


@dataclass
class RunInfo:
    """Metadata about an agent run."""

    run_id: str
    created_at: str
    updated_at: str
    total_steps: int
    status: str  # "running", "completed", "failed"
    framework: str = "generic"
    model: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentState:
    """Complete state snapshot of an agent at a specific step.

    This is the core data structure that gets serialized and stored
    at each checkpoint. It captures everything needed to resume
    an agent run from this exact point.
    """

    run_id: str
    step_number: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_input: Any = None
    messages: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: Optional[ErrorInfo] = None

    # Internal tracking
    _checksum: Optional[str] = field(default=None, repr=False)

    def compute_checksum(self) -> str:
        """Compute SHA-256 checksum of the state for integrity validation."""
        state_dict = self.to_dict()
        state_dict.pop("_checksum", None)
        raw = json.dumps(state_dict, sort_keys=True, default=str).encode("utf-8")
        checksum = hashlib.sha256(raw).hexdigest()
        self._checksum = checksum
        return checksum

    def verify_checksum(self) -> bool:
        """Verify the state hasn't been corrupted."""
        if self._checksum is None:
            return True  # No checksum to verify
        stored = self._checksum
        self._checksum = None
        computed = self.compute_checksum()
        return stored == computed

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> AgentState:
        """Deserialize from dictionary."""
        error_data = data.pop("error", None)
        checksum = data.pop("_checksum", None)
        error = ErrorInfo.from_dict(error_data) if error_data else None
        state = cls(**data, error=error)
        state._checksum = checksum
        return state

    def add_message(self, role: str, content: str, **kwargs) -> None:
        """Add a message to the conversation history."""
        msg = {"role": role, "content": content, **kwargs}
        self.messages.append(msg)

    def add_tool_call(
        self,
        tool_name: str,
        tool_input: Any,
        tool_output: Any = None,
        duration_ms: float = 0,
        **kwargs,
    ) -> None:
        """Record a tool invocation."""
        call = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_output": tool_output,
            "duration_ms": duration_ms,
            **kwargs,
        }
        self.tool_calls.append(call)

    @property
    def has_error(self) -> bool:
        return self.error is not None

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def tool_call_count(self) -> int:
        return len(self.tool_calls)
