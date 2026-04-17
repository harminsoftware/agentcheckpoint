"""LangChain integration — CallbackHandler for automatic checkpointing.

Usage:
    from agentcheckpoint.integrations.langchain import CheckpointCallbackHandler

    handler = CheckpointCallbackHandler()
    agent.run(task, callbacks=[handler])

    # Or with custom config:
    handler = CheckpointCallbackHandler(
        config=CheckpointConfig(storage_path="/data/checkpoints")
    )
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from agentcheckpoint.core import CheckpointConfig, CheckpointContext, checkpoint
from agentcheckpoint.state import AgentState

logger = logging.getLogger(__name__)

try:
    from langchain_core.callbacks import BaseCallbackHandler
except ImportError:
    raise ImportError(
        "langchain-core is required for LangChain integration. "
        "Install with: pip install agentcheckpoint[langchain]"
    )


class CheckpointCallbackHandler(BaseCallbackHandler):
    """LangChain callback handler that creates checkpoints between agent steps.

    Hooks into the LangChain callback system to capture:
    - LLM calls (input/output)
    - Tool invocations (name, args, result)
    - Chain completion states
    """

    name = "agentcheckpoint"

    def __init__(
        self,
        config: CheckpointConfig | None = None,
        context: CheckpointContext | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._config = config or CheckpointConfig(framework="langchain")
        self._context = context
        self._messages: list[dict] = []
        self._tool_calls: list[dict] = []
        self._step_count = 0
        self._owns_context = context is None

    def _ensure_context(self) -> CheckpointContext:
        if self._context is None:
            self._context = checkpoint(config=self._config)
            self._context.start()
        return self._context

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs,
    ) -> None:
        """Capture LLM call start."""
        self._messages.append({
            "role": "system",
            "content": f"LLM invocation started",
            "prompts": prompts[:3],  # Cap for size
            "model": serialized.get("kwargs", {}).get("model_name", ""),
        })

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs) -> None:
        """Checkpoint after each LLM call completes."""
        ctx = self._ensure_context()

        # Extract response text
        output_text = ""
        if hasattr(response, "generations") and response.generations:
            for gen_list in response.generations:
                for gen in gen_list:
                    output_text += gen.text if hasattr(gen, "text") else str(gen)

        self._messages.append({
            "role": "assistant",
            "content": output_text[:5000],  # Cap large outputs
        })

        self._step_count += 1
        ctx.step(
            messages=list(self._messages),
            tool_calls=list(self._tool_calls),
            metadata={"langchain_step": self._step_count},
        )

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs,
    ) -> None:
        """Capture tool invocation start."""
        self._tool_calls.append({
            "tool_name": serialized.get("name", "unknown"),
            "tool_input": input_str[:2000],
            "tool_output": None,
            "status": "running",
        })

    def on_tool_end(self, output: str, *, run_id: UUID, **kwargs) -> None:
        """Checkpoint after tool execution."""
        ctx = self._ensure_context()

        # Update the last tool call with output
        if self._tool_calls:
            self._tool_calls[-1]["tool_output"] = str(output)[:5000]
            self._tool_calls[-1]["status"] = "completed"

        self._step_count += 1
        ctx.step(
            messages=list(self._messages),
            tool_calls=list(self._tool_calls),
            metadata={"langchain_step": self._step_count},
        )

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs) -> None:
        """Capture tool errors."""
        if self._tool_calls:
            self._tool_calls[-1]["status"] = "error"
            self._tool_calls[-1]["tool_output"] = str(error)[:2000]

        ctx = self._ensure_context()
        ctx.capture_error(error)

    def on_chain_end(self, outputs: dict[str, Any], *, run_id: UUID, **kwargs) -> None:
        """Checkpoint on chain completion."""
        pass  # Main checkpointing is done on LLM/tool end

    def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs) -> None:
        """Capture chain-level errors."""
        ctx = self._ensure_context()
        ctx.capture_error(error)

    def close(self) -> None:
        """Complete the run and clean up."""
        if self._context and self._owns_context:
            self._context.complete()

    @property
    def checkpoint_context(self) -> CheckpointContext | None:
        return self._context
