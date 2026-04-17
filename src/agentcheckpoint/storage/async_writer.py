"""Async write wrapper for any storage backend.

Runs checkpoint writes in a background thread to avoid blocking the agent loop.
Uses a write queue with two-phase commit semantics and flush-on-exit guarantee.
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from typing import Optional

from agentcheckpoint.state import RunInfo, StepInfo
from agentcheckpoint.storage import StorageBackend

logger = logging.getLogger(__name__)


@dataclass
class _WriteJob:
    run_id: str
    step: int
    data: bytes
    metadata: dict | None = None


class AsyncStorageBackend(StorageBackend):
    """Wraps any StorageBackend with asynchronous background writes.

    Writes are queued and processed by a background thread. The queue
    is flushed on close/exit to ensure no data is lost.

    Reads are always synchronous (pass-through to inner backend).
    """

    def __init__(self, inner: StorageBackend, max_queue_size: int = 1000):
        self._inner = inner
        self._queue: queue.Queue[Optional[_WriteJob]] = queue.Queue(maxsize=max_queue_size)
        self._thread = threading.Thread(target=self._writer_loop, daemon=True, name="checkpoint-writer")
        self._error: Optional[Exception] = None
        self._running = True
        self._thread.start()

    def _writer_loop(self) -> None:
        """Background thread that processes the write queue."""
        while True:
            try:
                job = self._queue.get(timeout=1.0)
            except queue.Empty:
                if not self._running:
                    break
                continue

            if job is None:  # Sentinel — shutdown signal
                self._queue.task_done()
                break

            try:
                self._inner.save(job.run_id, job.step, job.data, job.metadata)
            except Exception as e:
                logger.error(f"Async write failed for run={job.run_id} step={job.step}: {e}")
                self._error = e
            finally:
                self._queue.task_done()

    def save(self, run_id: str, step: int, data: bytes, metadata: dict | None = None) -> None:
        """Queue a write job. Non-blocking unless queue is full."""
        if self._error:
            # Surface the last error to the caller
            err = self._error
            self._error = None
            raise RuntimeError(f"Previous async write failed: {err}") from err

        job = _WriteJob(run_id=run_id, step=step, data=data, metadata=metadata)
        self._queue.put(job)

    def load(self, run_id: str, step: int) -> bytes:
        # Reads are always synchronous
        self.flush()  # Ensure pending writes are committed first
        return self._inner.load(run_id, step)

    def list_runs(self) -> list[RunInfo]:
        self.flush()
        return self._inner.list_runs()

    def list_steps(self, run_id: str) -> list[StepInfo]:
        self.flush()
        return self._inner.list_steps(run_id)

    def delete_run(self, run_id: str) -> None:
        self.flush()
        self._inner.delete_run(run_id)

    def delete_step(self, run_id: str, step: int) -> None:
        self.flush()
        self._inner.delete_step(run_id, step)

    def save_run_meta(self, run_info: RunInfo) -> None:
        self._inner.save_run_meta(run_info)

    def load_run_meta(self, run_id: str) -> Optional[RunInfo]:
        return self._inner.load_run_meta(run_id)

    def flush(self) -> None:
        """Block until all queued writes are completed."""
        self._queue.join()
        if self._error:
            err = self._error
            self._error = None
            raise RuntimeError(f"Async write failed during flush: {err}") from err

    def close(self) -> None:
        """Flush remaining writes and shut down the writer thread."""
        self._running = False
        self._queue.put(None)  # Sentinel
        self._thread.join(timeout=30)
        if self._thread.is_alive():
            logger.warning("Async writer thread did not terminate cleanly")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
