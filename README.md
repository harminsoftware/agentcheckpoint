# 🔄 AgentCheckpoint

**Transparent checkpoint & replay for AI agent workflows. Never lose a step.**

[![PyPI](https://img.shields.io/pypi/v/agentcheckpoint)](https://pypi.org/project/agentcheckpoint/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

AgentCheckpoint wraps any AI agent with crash recovery and step-by-step replay. When your 4-hour agent run crashes at step 47, you resume from step 47 — not from scratch.

## ⚡ 3 Lines of Code

```python
from agentcheckpoint import checkpoint

with checkpoint() as cp:
    result = my_agent.run(task)                      # Your existing agent code
    cp.step(messages=result.messages)                 # Checkpoint saved ✓
```

## 💥 The Problem

```
$ python my_agent.py
Running agent... step 1 ✓ step 2 ✓ ... step 46 ✓ step 47
❌ RateLimitError: Rate limit exceeded
# 2 hours of compute and $15 in API calls — gone forever.
```

## ✅ The Fix

```
$ python my_agent.py                                 # Now with AgentCheckpoint
Running agent... step 1 ✓ step 2 ✓ ... step 46 ✓ step 47
❌ RateLimitError: Rate limit exceeded
💾 Checkpoint saved at step 47

$ agentcheckpoint resume abc123                      # One command
✓ Resumed run: abc123
  Step: 47
  Messages: 94
  Tool Calls: 23
  Continuing from where you left off...
```

## 🚀 Quick Start

```bash
pip install agentcheckpoint
```

### Context Manager

```python
from agentcheckpoint import checkpoint

with checkpoint(framework="langchain", model="claude-3") as cp:
    for task in tasks:
        result = agent.run(task)
        cp.step(
            messages=result.messages,
            tool_calls=result.tool_calls,
            variables={"output": result.output},
        )
```

### Decorator

```python
from agentcheckpoint import checkpointable

@checkpointable(framework="custom")
def my_agent(task: str):
    result = llm.invoke(task)
    return result
```

### Framework Integrations

```python
# LangChain
from agentcheckpoint.integrations.langchain import CheckpointCallbackHandler
agent.run(task, callbacks=[CheckpointCallbackHandler()])

# LangGraph
from agentcheckpoint.integrations.langgraph import CheckpointGraphWrapper
wrapper = CheckpointGraphWrapper()
result = wrapper.run(graph, input_data)

# Claude Agent SDK
from agentcheckpoint.integrations.claude_agent import CheckpointAgentWrapper
wrapper = CheckpointAgentWrapper()
result = wrapper.run(agent, prompt)

# OpenAI Agents SDK
from agentcheckpoint.integrations.openai_agents import CheckpointAgentRunner
runner = CheckpointAgentRunner()
result = runner.run(agent, input_text)

# CrewAI
from agentcheckpoint.integrations.crewai import CheckpointCrewWrapper
wrapper = CheckpointCrewWrapper()
result = wrapper.run(crew)

# Google ADK
from agentcheckpoint.integrations.google_adk import CheckpointADKWrapper
wrapper = CheckpointADKWrapper()
result = wrapper.run(agent, user_input)
```

## 🖥️ CLI

```bash
agentcheckpoint list                         # List all runs
agentcheckpoint inspect <run_id>             # Show steps
agentcheckpoint inspect <run_id> --step 5    # Show state at step 5
agentcheckpoint resume <run_id>              # Resume from last checkpoint
agentcheckpoint resume <run_id> --step 5     # Resume from step 5
agentcheckpoint delete <run_id>              # Delete run
agentcheckpoint dashboard                    # Launch replay dashboard
```

## 🗄️ Storage Backends

| Backend | Install | Latency | Use Case |
|---------|---------|---------|----------|
| **Local Disk** (default) | included | <5ms | Development, single machine |
| **S3/R2/MinIO** | `pip install agentcheckpoint[s3]` | 80-200ms | Production, distributed |
| **PostgreSQL** | `pip install agentcheckpoint[postgres]` | 5-20ms | Production, queryable |

```python
# S3
with checkpoint(storage_backend="s3", s3_bucket="my-bucket") as cp:
    ...

# PostgreSQL
with checkpoint(storage_backend="postgres", pg_conninfo="host=localhost dbname=agents") as cp:
    ...

# Async writes (background thread, doesn't block agent)
with checkpoint(async_writes=True) as cp:
    ...
```

## 📊 Replay Dashboard

```bash
pip install agentcheckpoint[dashboard]
agentcheckpoint dashboard
# → http://localhost:8585
```

## 🏢 Enterprise

Enterprise features (SSO, audit logs, RBAC, auto-resume policies) require a license key:

```bash
export AGENTCHECKPOINT_LICENSE_KEY=<your-key>
```

[Get a license →](https://agentcheckpoint.dev/enterprise)

## 🔒 Privacy

- **Open source**: Zero telemetry. Zero data collection. Period.
- **Enterprise**: Opt-in aggregate metadata only. Never content.

See [PRIVACY.md](PRIVACY.md) for details.

## 📦 Installation Options

```bash
pip install agentcheckpoint                          # Core only
pip install agentcheckpoint[langchain]               # + LangChain
pip install agentcheckpoint[s3,dashboard]             # + S3 + Dashboard
pip install agentcheckpoint[all]                      # Everything
```

## License

MIT — see [LICENSE](LICENSE). Enterprise features under BSL.
