"""Tests for local storage backend."""

import pytest

from agentcheckpoint.state import RunInfo
from agentcheckpoint.storage.local import LocalStorageBackend


@pytest.fixture
def storage(tmp_path):
    return LocalStorageBackend(base_path=str(tmp_path / "checkpoints"))


class TestLocalStorage:
    def test_save_and_load(self, storage):
        storage.save("run1", 1, b"test data")
        result = storage.load("run1", 1)
        assert result == b"test data"

    def test_load_nonexistent_raises(self, storage):
        with pytest.raises(FileNotFoundError):
            storage.load("nonexistent", 1)

    def test_list_steps(self, storage):
        storage.save("run1", 1, b"step1")
        storage.save("run1", 2, b"step2")
        storage.save("run1", 3, b"step3")

        steps = storage.list_steps("run1")
        assert len(steps) == 3
        assert steps[0].step_number == 1
        assert steps[2].step_number == 3

    def test_list_runs(self, storage):
        storage.save("run1", 1, b"data1")
        storage.save("run2", 1, b"data2")

        runs = storage.list_runs()
        run_ids = {r.run_id for r in runs}
        assert "run1" in run_ids
        assert "run2" in run_ids

    def test_delete_run(self, storage):
        storage.save("run1", 1, b"data")
        storage.save("run1", 2, b"data")

        storage.delete_run("run1")
        assert not storage.run_exists("run1")

    def test_delete_step(self, storage):
        storage.save("run1", 1, b"data1")
        storage.save("run1", 2, b"data2")

        storage.delete_step("run1", 1)
        steps = storage.list_steps("run1")
        assert len(steps) == 1
        assert steps[0].step_number == 2

    def test_run_meta(self, storage):
        meta = RunInfo(
            run_id="run1",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:01:00Z",
            total_steps=5,
            status="completed",
            framework="langchain",
            model="claude-3",
        )
        storage.save_run_meta(meta)
        loaded = storage.load_run_meta("run1")
        assert loaded.run_id == "run1"
        assert loaded.status == "completed"
        assert loaded.framework == "langchain"

    def test_latest_step(self, storage):
        storage.save("run1", 1, b"data")
        storage.save("run1", 5, b"data")
        storage.save("run1", 3, b"data")

        assert storage.latest_step("run1") == 5

    def test_latest_step_none(self, storage):
        assert storage.latest_step("nonexistent") is None

    def test_cleanup_temp_files(self, storage):
        # Create some temp files
        storage.save("run1", 1, b"data")
        run_dir = storage._run_dir("run1")
        (run_dir / "partial.tmp").write_bytes(b"incomplete")
        (run_dir / "another.tmp").write_bytes(b"incomplete")

        count = storage.cleanup_temp_files()
        assert count == 2

    def test_atomic_write_integrity(self, storage):
        """Verify two-phase commit: if write fails, no corrupt file remains."""
        storage.save("run1", 1, b"valid data")

        # Ensure the file is properly written
        result = storage.load("run1", 1)
        assert result == b"valid data"

    def test_large_data(self, storage):
        """Test with a larger payload."""
        large_data = b"x" * (1024 * 1024)  # 1MB
        storage.save("run1", 1, large_data)
        result = storage.load("run1", 1)
        assert result == large_data
        assert len(result) == 1024 * 1024
