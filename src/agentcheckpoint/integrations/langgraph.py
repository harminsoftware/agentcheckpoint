"""LangGraph integration — hooks into graph execution for checkpoint capture.

LangGraph is the production standard for stateful agents. This integration
complements LangGraph's built-in persistence with crash-recovery semantics.

Usage:
    from agentcheckpoint.integrations.langgraph import CheckpointGraphWrapper

    wrapper = CheckpointGraphWrapper()
    result = wrapper.run(graph, input_data)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from agentcheckpoint.core import CheckpointConfig, CheckpointContext, checkpoint

logger = logging.getLogger(__name__)


class CheckpointGraphWrapper:
    """Wraps a LangGraph graph execution with checkpoint capture.

    Hooks into LangGraph's graph execution and state channels to capture
    node execution state, conditional edge results, and graph checkpoint data.
    """

    def __init__(
        self,
        config: CheckpointConfig | None = None,
        **kwargs,
    ):
        self._config = config or CheckpointConfig(framework="langgraph")
        self._context: CheckpointContext | None = None

    def run(self, graph: Any, input_data: Any, **kwargs) -> Any:
        """Run a LangGraph graph with automatic checkpointing.

        Args:
            graph: A compiled LangGraph graph
            input_data: Input to the graph
            **kwargs: Additional arguments passed to graph.invoke()
        """
        try:
            from langgraph.graph import CompiledGraph
        except ImportError:
            raise ImportError(
                "langgraph is required for LangGraph integration. "
                "Install with: pip install agentcheckpoint[langgraph]"
            )

        with checkpoint(config=self._config) as cp:
            self._context = cp

            # Capture initial state
            cp.step(
                agent_input=input_data,
                metadata={"event": "graph_start", "graph_type": type(graph).__name__},
            )

            try:
                # Run the graph with streaming to capture intermediate states
                result = None
                step_count = 0

                for event in graph.stream(input_data, **kwargs):
                    step_count += 1
                    # Each event is typically {node_name: output}
                    if isinstance(event, dict):
                        for node_name, node_output in event.items():
                            cp.step(
                                variables={"node": node_name, "output": node_output},
                                metadata={
                                    "event": "node_complete",
                                    "node": node_name,
                                    "step": step_count,
                                },
                            )
                    result = event

                return result

            except Exception as e:
                cp.capture_error(e)
                raise

    @property
    def checkpoint_context(self) -> CheckpointContext | None:
        return self._context
