"""Framework integrations registry."""

from __future__ import annotations

SUPPORTED_FRAMEWORKS = {
    "langchain": "agentcheckpoint.integrations.langchain",
    "langgraph": "agentcheckpoint.integrations.langgraph",
    "claude_agent": "agentcheckpoint.integrations.claude_agent",
    "openai_agents": "agentcheckpoint.integrations.openai_agents",
    "crewai": "agentcheckpoint.integrations.crewai",
    "google_adk": "agentcheckpoint.integrations.google_adk",
}


def get_integration(framework: str):
    """Get the integration module for a framework."""
    if framework not in SUPPORTED_FRAMEWORKS:
        raise ValueError(
            f"Unknown framework: {framework!r}. "
            f"Supported: {list(SUPPORTED_FRAMEWORKS.keys())}"
        )
    import importlib
    return importlib.import_module(SUPPORTED_FRAMEWORKS[framework])
