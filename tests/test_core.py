"""Tests for the core checkpoint engine."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from agentcheckpoint.core import CheckpointConfig, CheckpointContext, checkpoint, checkpointable
from agentcheckpoint.state import AgentState
from agentcheckpoint.storage.local import LocalStorageBackend


@pytest.fixture
def tmp_storage(tmp_path):
    """Temporary storage path for tests."""
    return str(tmp_path / "checkpoints")


class TestCheckpointConfig:
    def test_default_config(self):
        config = CheckpointConfig()
        assert config.storage_path == "./checkpoints"
        assert config.serializer_format == "auto"
        assert config.async_writes is False
        assert config.framework == "generic"

    def test_custom_config(self):
        config = CheckpointConfig(
            storage_path="/tmp/test",
            serializer_format="json",
            framework="langchain",
            model="claude-3",
        )
        assert config.storage_path == "/tmp/test"
        assert config.serializer_format == "json"
        assert config.framework == "langchain"
        assert config.model == "claude-3"


class TestCheckpointContext:
    def test_context_manager_creates_run(self, tmp_storage):
        with checkpoint(storage_path=tmp_storage) as cp:
            assert cp.run_id
            assert cp._is_active

    def test_step_increments(self, tmp_storage):
        with checkpoint(storage_path=tmp_storage) as cp:
            s1 = cp.step(messages=[{"role": "user", "content": "hello"}])
            s2 = cp.step(messages=[{"role": "assistant", "content": "hi"}])
            s3 = cp.step()
            assert s1 == 1
            assert s2 == 2
            assert s3 == 3

    def test_step_saves_data(self, tmp_storage):
        with checkpoint(storage_path=tmp_storage) as cp:
            cp.step(
                messages=[{"role": "user", "content": "test"}],
                tool_calls=[{"tool_name": "search", "tool_input": "query"}],
                variables={"key": "value"},
            )
            run_id = cp.run_id

        # Verify data was saved
        storage = LocalStorageBackend(base_path=tmp_storage)
        steps = storage.list_steps(run_id)
        assert len(steps) == 1
        assert steps[0].step_number == 1

    def test_error_capture(self, tmp_storage):
        with pytest.raises(ValueError, match="test error"):
            with checkpoint(storage_path=tmp_storage) as cp:
                cp.step(messages=[{"role": "user", "content": "before error"}])
                run_id = cp.run_id
                raise ValueError("test error")

        # Verify error was captured
        storage = LocalStorageBackend(base_path=tmp_storage)
        meta = storage.load_run_meta(run_id)
        assert meta.status == "failed"

    def test_completed_status(self, tmp_storage):
        with checkpoint(storage_path=tmp_storage) as cp:
            cp.step()
            run_id = cp.run_id

        storage = LocalStorageBackend(base_path=tmp_storage)
        meta = storage.load_run_meta(run_id)
        assert meta.status == "completed"

    def test_custom_run_id(self, tmp_storage):
        with checkpoint(storage_path=tmp_storage, run_id="my-custom-run") as cp:
            cp.step()
            assert cp.run_id == "my-custom-run"

    def test_multiple_steps_with_growing_state(self, tmp_storage):
        messages = []
        with checkpoint(storage_path=tmp_storage) as cp:
            for i in range(5):
                messages.append({"role": "user", "content": f"message {i}"})
                cp.step(messages=list(messages))
            run_id = cp.run_id

        storage = LocalStorageBackend(base_path=tmp_storage)
        steps = storage.list_steps(run_id)
        assert len(steps) == 5


class TestCheckpointableDecorator:
    def test_decorator_wraps_function(self, tmp_storage):
        @checkpointable(storage_path=tmp_storage)
        def my_agent(task: str):
            return f"completed: {task}"

        result = my_agent("test task")
        assert result == "completed: test task"

    def test_decorator_creates_checkpoint(self, tmp_storage):
        @checkpointable(storage_path=tmp_storage)
        def my_agent(task: str):
            return {"output": task}

        my_agent("hello")

        storage = LocalStorageBackend(base_path=tmp_storage)
        runs = storage.list_runs()
        assert len(runs) >= 1

    def test_decorator_captures_exception(self, tmp_storage):
        @checkpointable(storage_path=tmp_storage)
        def failing_agent():
            raise RuntimeError("agent crashed")

        with pytest.raises(RuntimeError, match="agent crashed"):
            failing_agent()
