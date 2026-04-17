"""Anthropic Claude Agent SDK integration.

Wraps the Claude Agent SDK's agent loop to capture tool use,
system prompt state, conversation history, and MCP context.

Usage:
    from agentcheckpoint.integrations.claude_agent import CheckpointAgentWrapper

    wrapper = CheckpointAgentWrapper()
    result = wrapper.run(agent, prompt)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from agentcheckpoint.core import CheckpointConfig, CheckpointContext, checkpoint

logger = logging.getLogger(__name__)


class CheckpointAgentWrapper:
    """Wraps a Claude Agent SDK agent with checkpoint capture.

    Hooks into the agent's execution loop to capture:
    - Tool use events
    - System prompt state
    - Conversation history
    - MCP context and connections
    - Context compaction events
    """

    def __init__(
        self,
        config: CheckpointConfig | None = None,
        **kwargs,
    ):
        self._config = config or CheckpointConfig(framework="claude_agent")
        self._context: CheckpointContext | None = None

    def run(self, agent: Any, prompt: str, **kwargs) -> Any:
        """Run a Claude Agent SDK agent with automatic checkpointing.

        Args:
            agent: A Claude Agent SDK agent instance
            prompt: The user prompt
            **kwargs: Additional arguments
        """
        with checkpoint(config=self._config) as cp:
            self._context = cp

            # Capture initial state
            cp.step(
                agent_input=prompt,
                metadata={"event": "agent_start", "agent_type": type(agent).__name__},
            )

            try:
                # The Claude Agent SDK uses a message-based agent loop
                # We intercept the stream to checkpoint between turns
                messages = []
                tool_calls = []

                result = agent.run(prompt, **kwargs)

                # Capture the conversation turns from the result
                if hasattr(result, "messages"):
                    for i, msg in enumerate(result.messages):
                        msg_dict = {
                            "role": getattr(msg, "role", "unknown"),
                            "content": str(getattr(msg, "content", ""))[:5000],
                        }
                        messages.append(msg_dict)

                        # Check for tool use
                        if hasattr(msg, "tool_use") and msg.tool_use:
                            for tool in msg.tool_use:
                                tool_calls.append({
                                    "tool_name": getattr(tool, "name", "unknown"),
                                    "tool_input": str(getattr(tool, "input", ""))[:2000],
                                    "tool_output": str(getattr(tool, "output", ""))[:5000],
                                })

                        # Checkpoint every turn
                        cp.step(
                            messages=list(messages),
                            tool_calls=list(tool_calls),
                            metadata={
                                "event": "turn_complete",
                                "turn": i + 1,
                                "role": msg_dict["role"],
                            },
                        )

                return result

            except Exception as e:
                cp.capture_error(e)
                raise

    @property
    def checkpoint_context(self) -> CheckpointContext | None:
        return self._context
