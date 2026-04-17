"""Tests for resume engine."""

import pytest

from agentcheckpoint.core import checkpoint
from agentcheckpoint.resume import ResumeError, ResumeResult, resume
from agentcheckpoint.storage.local import LocalStorageBackend


@pytest.fixture
def populated_run(tmp_path):
    """Create a run with multiple steps for resume testing."""
    storage_path = str(tmp_path / "checkpoints")

    with checkpoint(storage_path=storage_path, run_id="test-run") as cp:
        cp.step(messages=[{"role": "user", "content": "hello"}])
        cp.step(
            messages=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ],
            tool_calls=[{"tool_name": "search", "tool_input": "test"}],
        )
        cp.step(
            messages=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
                {"role": "user", "content": "search for X"},
            ],
            variables={"result": "found it"},
        )

    return storage_path


class TestResume:
    def test_resume_from_last_step(self, populated_run):
        result = resume("test-run", storage_path=populated_run)
        assert isinstance(result, ResumeResult)
        assert result.run_id == "test-run"
        assert result.step_number == 3
        assert len(result.messages) == 3

    def test_resume_from_specific_step(self, populated_run):
        result = resume("test-run", step=2, storage_path=populated_run)
        assert result.step_number == 2
        assert len(result.messages) == 2
        assert len(result.tool_calls) == 1

    def test_resume_nonexistent_run(self, tmp_path):
        with pytest.raises(ResumeError, match="No checkpoints found"):
            resume("nonexistent", storage_path=str(tmp_path / "checkpoints"))

    def test_resume_nonexistent_step(self, populated_run):
        with pytest.raises(ResumeError, match="Checkpoint not found"):
            resume("test-run", step=99, storage_path=populated_run)

    def test_resume_context_continues(self, populated_run):
        result = resume("test-run", step=2, storage_path=populated_run)
        ctx = result.context

        # Continue the run
        new_step = ctx.step(
            messages=result.messages + [{"role": "assistant", "content": "continued"}],
        )
        assert new_step == 3  # Continues from step 2

    def test_resume_after_failure(self, tmp_path):
        storage_path = str(tmp_path / "checkpoints")

        # Create a run that fails
        try:
            with checkpoint(storage_path=storage_path, run_id="failing-run") as cp:
                cp.step(messages=[{"role": "user", "content": "hello"}])
                cp.step(messages=[{"role": "user", "content": "before crash"}])
                raise ValueError("simulated crash")
        except ValueError:
            pass

        # Resume should pick up from last non-error step
        result = resume("failing-run", storage_path=storage_path)
        # Step 1 is the last clean step (step 2 has the error checkpoint)
        assert result.step_number == 1

    def test_resume_checksum_verification(self, populated_run):
        # Normal resume with verification should work
        result = resume("test-run", storage_path=populated_run, verify_checksum=True)
        assert result.run_id == "test-run"
