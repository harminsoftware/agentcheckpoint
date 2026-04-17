# Contributing to AgentCheckpoint

Welcome, and thank you for your interest in contributing to **AgentCheckpoint**! Whether you are fixing a bug, adding a new framework wrapper, or tweaking the UI, this guide will help you get started.

## 1. Development Setup

### Python Core & Backend
```bash
git clone https://github.com/harminsoftware/agentcheckpoint.git
cd agentcheckpoint

# Create virtual environment
python3.9 -m venv .venv
source .venv/bin/activate

# Install the package in editable mode with ALL dependencies
pip install -e ".[all]"
```

### React Dashboard (UI)
The dashboard uses Vite, React, and TypeScript.
```bash
cd frontend
npm install
npm run dev
```
In a separate terminal, start the FastAPI proxy backend:
```bash
agentcheckpoint dashboard
```

## 2. Testing
We use `pytest` for unit testing the Checkpoint serialization engine, backends, and resume logic.
```bash
pytest
```
Ensure all tests pass before submitting a Pull Request.

## 3. Modifying Enterprise Features
Important: The `src/agentcheckpoint/enterprise/` directory is licensed under the **Business Source License (BSL)**. External contributions to this directory require assignment of IP, but practically, most community contributions should be made to the Open-Source (MIT) portions of the codebase (like SDK framework wrappers).

## 4. Releasing & Publishing to PyPI
*This section is primarily for core maintainers (Harmin Software).*

When you are ready to publish a new version of the SDK, follow these exact steps:

**Step 1: Bump the Version**
Update the `version` field in both `pyproject.toml` and `src/agentcheckpoint/__init__.py`.

**Step 2: Build the Frontend**
If any changes were made to the React Dashboard, you must compile them so they are bundled into the Python package.
```bash
cd frontend
npm run build
cd ..
```

**Step 3: Build the Wheel**
```bash
pip install build twine
python -m build
```
This generates `.tar.gz` and `.whl` files inside the `dist/` directory.

**Step 4: Upload to PyPI**
```bash
twine upload dist/*
```
When prompted:
- **Username**: `__token__`
- **Password**: `<your-pypi-api-token>`

**Step 5: Cut a GitHub Release**
Tag the commit with `v0.1.X` and create a matching release on GitHub so developers can track the changelog.
