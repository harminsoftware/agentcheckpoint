"""CrewAI integration — hooks into Crew.kickoff() lifecycle.

Captures per-agent and per-task state within multi-agent crews.

Usage:
    from agentcheckpoint.integrations.crewai import CheckpointCrewWrapper

    wrapper = CheckpointCrewWrapper()
    result = wrapper.run(crew)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from agentcheckpoint.core import CheckpointConfig, CheckpointContext, checkpoint

logger = logging.getLogger(__name__)


class CheckpointCrewWrapper:
    """Wraps CrewAI crew execution with checkpoint capture.

    Captures:
    - Task delegation and assignment
    - Per-agent execution state
    - Inter-agent communication
    - Task completion results
    """

    def __init__(
        self,
        config: CheckpointConfig | None = None,
        **kwargs,
    ):
        self._config = config or CheckpointConfig(framework="crewai")
        self._context: CheckpointContext | None = None

    def run(self, crew: Any, **kwargs) -> Any:
        """Run a CrewAI crew with automatic checkpointing.

        Args:
            crew: A CrewAI Crew instance
            **kwargs: Additional arguments passed to crew.kickoff()
        """
        try:
            from crewai import Crew
        except ImportError:
            raise ImportError(
                "crewai is required for CrewAI integration. "
                "Install with: pip install agentcheckpoint[crewai]"
            )

        with checkpoint(config=self._config) as cp:
            self._context = cp

            # Capture crew structure
            agents = []
            tasks = []
            if hasattr(crew, "agents"):
                agents = [
                    {"name": getattr(a, "role", str(a)), "goal": getattr(a, "goal", "")}
                    for a in crew.agents
                ]
            if hasattr(crew, "tasks"):
                tasks = [
                    {"description": getattr(t, "description", str(t))[:500]}
                    for t in crew.tasks
                ]

            cp.step(
                variables={"agents": agents, "tasks": tasks},
                metadata={"event": "crew_start", "agent_count": len(agents), "task_count": len(tasks)},
            )

            try:
                # Use step callback if CrewAI supports it
                original_kickoff = crew.kickoff

                task_results = []

                def _task_callback(task_output):
                    """Called after each task completes."""
                    task_results.append({
                        "task": str(getattr(task_output, "description", ""))[:500],
                        "output": str(getattr(task_output, "raw", ""))[:5000],
                        "agent": str(getattr(task_output, "agent", "")),
                    })
                    cp.step(
                        variables={"completed_tasks": list(task_results)},
                        metadata={
                            "event": "task_complete",
                            "task_number": len(task_results),
                        },
                    )

                # Set callback if supported
                if hasattr(crew, "task_callback"):
                    crew.task_callback = _task_callback

                result = crew.kickoff(**kwargs)

                # Final checkpoint
                cp.step(
                    variables={
                        "result": str(result)[:5000],
                        "completed_tasks": task_results,
                    },
                    metadata={"event": "crew_complete"},
                )

                return result

            except Exception as e:
                cp.capture_error(e)
                raise

    @property
    def checkpoint_context(self) -> CheckpointContext | None:
        return self._context
