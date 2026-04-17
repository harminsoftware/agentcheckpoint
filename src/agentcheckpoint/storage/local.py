"""Local disk storage adapter — the zero-config default.

Stores checkpoints as files on the local filesystem:
    ./checkpoints/{run_id}/step_{N}.ckpt
    ./checkpoints/{run_id}/run_meta.json

Uses two-phase commit (write .tmp → atomic rename) to prevent corruption.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agentcheckpoint.state import RunInfo, StepInfo
from agentcheckpoint.storage import StorageBackend


class LocalStorageBackend(StorageBackend):
    """File-based storage backend. Near-zero latency. Zero configuration needed."""

    DEFAULT_PATH = "./checkpoints"

    def __init__(self, base_path: str | Path | None = None):
        self.base_path = Path(base_path or self.DEFAULT_PATH).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _run_dir(self, run_id: str) -> Path:
        return self.base_path / run_id

    def _step_path(self, run_id: str, step: int) -> Path:
        return self._run_dir(run_id) / f"step_{step:06d}.ckpt"

    def _meta_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "run_meta.json"

    def save(self, run_id: str, step: int, data: bytes, metadata: dict | None = None) -> None:
        """Atomic write using two-phase commit: write to temp file, then rename."""
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        target = self._step_path(run_id, step)

        # Two-phase commit: write to temp file first
        fd, tmp_path = tempfile.mkstemp(dir=run_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            # Atomic rename (same filesystem)
            os.rename(tmp_path, target)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def load(self, run_id: str, step: int) -> bytes:
        target = self._step_path(run_id, step)
        if not target.exists():
            raise FileNotFoundError(f"Checkpoint not found: run={run_id}, step={step}")
        return target.read_bytes()

    def list_runs(self) -> list[RunInfo]:
        runs = []
        if not self.base_path.exists():
            return runs

        for entry in sorted(self.base_path.iterdir()):
            if not entry.is_dir():
                continue
            run_id = entry.name
            meta = self.load_run_meta(run_id)
            if meta:
                runs.append(meta)
            else:
                # Build from files
                steps = self.list_steps(run_id)
                if steps:
                    runs.append(
                        RunInfo(
                            run_id=run_id,
                            created_at=steps[0].timestamp,
                            updated_at=steps[-1].timestamp,
                            total_steps=len(steps),
                            status="unknown",
                        )
                    )
        return runs

    def list_steps(self, run_id: str) -> list[StepInfo]:
        run_dir = self._run_dir(run_id)
        if not run_dir.exists():
            return []

        steps = []
        for f in sorted(run_dir.iterdir()):
            if not f.name.endswith(".ckpt"):
                continue
            # Parse step number from filename: step_000005.ckpt
            try:
                step_num = int(f.stem.split("_")[1])
            except (IndexError, ValueError):
                continue

            stat = f.stat()
            data = f.read_bytes()
            checksum = hashlib.sha256(data).hexdigest()[:16]

            steps.append(
                StepInfo(
                    step_number=step_num,
                    timestamp=datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(),
                    checksum=checksum,
                    size_bytes=stat.st_size,
                )
            )
        return sorted(steps, key=lambda s: s.step_number)

    def delete_run(self, run_id: str) -> None:
        run_dir = self._run_dir(run_id)
        if run_dir.exists():
            shutil.rmtree(run_dir)

    def delete_step(self, run_id: str, step: int) -> None:
        target = self._step_path(run_id, step)
        if target.exists():
            target.unlink()

    def save_run_meta(self, run_info: RunInfo) -> None:
        meta_path = self._meta_path(run_info.run_id)
        meta_path.parent.mkdir(parents=True, exist_ok=True)

        from dataclasses import asdict
        data = json.dumps(asdict(run_info), indent=2, default=str)

        fd, tmp_path = tempfile.mkstemp(dir=meta_path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.rename(tmp_path, meta_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def load_run_meta(self, run_id: str) -> Optional[RunInfo]:
        meta_path = self._meta_path(run_id)
        if not meta_path.exists():
            return None
        data = json.loads(meta_path.read_text())
        return RunInfo(**data)

    def cleanup_temp_files(self) -> int:
        """Remove incomplete .tmp files left by interrupted writes. Returns count removed."""
        count = 0
        if not self.base_path.exists():
            return count
        for tmp_file in self.base_path.rglob("*.tmp"):
            tmp_file.unlink()
            count += 1
        return count
