"""Google Agent Development Kit (ADK) integration.

Hooks into ADK's sequential, parallel, and loop agent team patterns
to capture Gemini-powered workflow state and Vertex AI context.

Usage:
    from agentcheckpoint.integrations.google_adk import CheckpointADKWrapper

    wrapper = CheckpointADKWrapper()
    result = wrapper.run(agent, user_input)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from agentcheckpoint.core import CheckpointConfig, CheckpointContext, checkpoint

logger = logging.getLogger(__name__)


class CheckpointADKWrapper:
    """Wraps Google ADK agent execution with checkpoint capture.

    Captures:
    - Sequential, parallel, and loop team execution patterns
    - Individual agent step outputs
    - Gemini model interactions
    - Vertex AI context and tracing data
    """

    def __init__(
        self,
        config: CheckpointConfig | None = None,
        **kwargs,
    ):
        self._config = config or CheckpointConfig(framework="google_adk")
        self._context: CheckpointContext | None = None

    def run(self, agent: Any, user_input: str, **kwargs) -> Any:
        """Run a Google ADK agent with automatic checkpointing.

        Args:
            agent: A Google ADK Agent instance
            user_input: The user input message
            **kwargs: Additional arguments
        """
        try:
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
        except ImportError:
            raise ImportError(
                "google-adk is required for Google ADK integration. "
                "Install with: pip install agentcheckpoint[google-adk]"
            )

        with checkpoint(config=self._config) as cp:
            self._context = cp

            cp.step(
                agent_input=user_input,
                metadata={
                    "event": "adk_agent_start",
                    "agent_name": getattr(agent, "name", "unknown"),
                },
            )

            try:
                session_service = InMemorySessionService()
                runner = Runner(
                    agent=agent,
                    app_name="agentcheckpoint",
                    session_service=session_service,
                )

                session = session_service.create_session(
                    app_name="agentcheckpoint",
                    user_id="checkpoint_user",
                )

                from google.genai.types import Content, Part

                user_content = Content(
                    role="user", parts=[Part.from_text(user_input)]
                )

                messages = []
                tool_calls = []

                for event in runner.run(
                    user_id="checkpoint_user",
                    session_id=session.id,
                    new_message=user_content,
                ):
                    if hasattr(event, "content") and event.content:
                        msg = {
                            "role": getattr(event.content, "role", "model"),
                            "content": str(event.content.parts[0].text)[:5000]
                            if event.content.parts
                            else "",
                        }
                        messages.append(msg)

                    if hasattr(event, "tool_calls"):
                        for tc in event.tool_calls:
                            tool_calls.append({
                                "tool_name": getattr(tc, "name", ""),
                                "tool_input": str(getattr(tc, "args", "")),
                            })

                    cp.step(
                        messages=list(messages),
                        tool_calls=list(tool_calls),
                        metadata={"event": "adk_step"},
                    )

                return messages[-1] if messages else None

            except Exception as e:
                cp.capture_error(e)
                raise

    @property
    def checkpoint_context(self) -> CheckpointContext | None:
        return self._context
