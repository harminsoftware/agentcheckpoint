"""OpenAI Agents SDK integration.

Hooks into Agents/Handoffs/Guardrails primitives to checkpoint
inter-agent handoff state and tool execution results.

Usage:
    from agentcheckpoint.integrations.openai_agents import CheckpointAgentRunner

    runner = CheckpointAgentRunner()
    result = runner.run(agent, input_text)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from agentcheckpoint.core import CheckpointConfig, CheckpointContext, checkpoint

logger = logging.getLogger(__name__)


class CheckpointAgentRunner:
    """Wraps OpenAI Agents SDK execution with checkpoint capture.

    Captures:
    - Agent handoff events between agents
    - Tool execution results
    - Guardrail evaluations
    - Final agent outputs
    """

    def __init__(
        self,
        config: CheckpointConfig | None = None,
        **kwargs,
    ):
        self._config = config or CheckpointConfig(framework="openai_agents")
        self._context: CheckpointContext | None = None

    def run(self, agent: Any, input_text: str, **kwargs) -> Any:
        """Run an OpenAI Agents SDK agent with automatic checkpointing.

        Args:
            agent: An OpenAI Agents SDK Agent instance
            input_text: The user input
            **kwargs: Additional arguments passed to Runner.run()
        """
        try:
            from openai_agents import Runner
        except ImportError:
            raise ImportError(
                "openai-agents is required for OpenAI Agents SDK integration. "
                "Install with: pip install agentcheckpoint[openai-agents]"
            )

        with checkpoint(config=self._config) as cp:
            self._context = cp

            cp.step(
                agent_input=input_text,
                metadata={
                    "event": "agent_start",
                    "agent_name": getattr(agent, "name", "unknown"),
                },
            )

            try:
                result = Runner.run_sync(agent, input_text, **kwargs)

                # Capture the execution trace
                messages = []
                tool_calls = []

                if hasattr(result, "messages"):
                    for msg in result.messages:
                        messages.append({
                            "role": getattr(msg, "role", "unknown"),
                            "content": str(getattr(msg, "content", ""))[:5000],
                        })

                if hasattr(result, "raw_responses"):
                    for resp in result.raw_responses:
                        if hasattr(resp, "tool_calls"):
                            for tc in resp.tool_calls:
                                tool_calls.append({
                                    "tool_name": getattr(tc, "name", ""),
                                    "tool_input": str(getattr(tc, "arguments", "")),
                                })

                cp.step(
                    messages=messages,
                    tool_calls=tool_calls,
                    variables={"output": str(getattr(result, "final_output", ""))[:5000]},
                    metadata={"event": "agent_complete"},
                )

                return result

            except Exception as e:
                cp.capture_error(e)
                raise

    @property
    def checkpoint_context(self) -> CheckpointContext | None:
        return self._context
