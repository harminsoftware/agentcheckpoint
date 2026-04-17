"""Storage backend abstract interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from agentcheckpoint.state import RunInfo, StepInfo


class StorageBackend(ABC):
    """Abstract base class for checkpoint storage backends.

    All storage backends must implement these methods. The interface
    is intentionally simple — save/load bytes, list/delete runs.
    """

    @abstractmethod
    def save(self, run_id: str, step: int, data: bytes, metadata: dict | None = None) -> None:
        """Save checkpoint data for a specific run and step.

        Must be atomic — either the full data is written or nothing is.
        Implementations should use two-phase commit (write temp, rename).
        """

    @abstractmethod
    def load(self, run_id: str, step: int) -> bytes:
        """Load checkpoint data for a specific run and step.

        Raises FileNotFoundError if the checkpoint doesn't exist.
        """

    @abstractmethod
    def list_runs(self) -> list[RunInfo]:
        """List all available runs."""

    @abstractmethod
    def list_steps(self, run_id: str) -> list[StepInfo]:
        """List all checkpoint steps for a run, ordered by step number."""

    @abstractmethod
    def delete_run(self, run_id: str) -> None:
        """Delete all checkpoints for a run."""

    @abstractmethod
    def delete_step(self, run_id: str, step: int) -> None:
        """Delete a single checkpoint step."""

    def latest_step(self, run_id: str) -> Optional[int]:
        """Get the latest step number for a run. Returns None if no steps exist."""
        steps = self.list_steps(run_id)
        if not steps:
            return None
        return max(s.step_number for s in steps)

    def run_exists(self, run_id: str) -> bool:
        """Check if a run exists."""
        try:
            steps = self.list_steps(run_id)
            return len(steps) > 0
        except (FileNotFoundError, KeyError):
            return False

    def save_run_meta(self, run_info: RunInfo) -> None:
        """Save run-level metadata. Default implementation is a no-op.

        Backends that support rich metadata (Postgres, S3) should override this.
        """

    def load_run_meta(self, run_id: str) -> Optional[RunInfo]:
        """Load run-level metadata. Default returns None."""
        return None
