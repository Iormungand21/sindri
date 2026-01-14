# Contributing to Sindri

**Thank you for considering contributing to Sindri!**

This document provides guidelines and instructions for contributing to the project.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Development Setup](#development-setup)
3. [Project Structure](#project-structure)
4. [Making Changes](#making-changes)
5. [Testing](#testing)
6. [Documentation](#documentation)
7. [Pull Request Process](#pull-request-process)
8. [Code Style](#code-style)
9. [Community Guidelines](#community-guidelines)

---

## Getting Started

### Ways to Contribute

- 🐛 **Report bugs** - File issues with detailed reproduction steps
- ✨ **Suggest features** - Propose new capabilities or improvements
- 📝 **Improve docs** - Fix typos, clarify explanations, add examples
- 🔧 **Submit code** - Fix bugs, implement features, optimize performance
- 🧪 **Add tests** - Increase test coverage, add integration tests
- 🎨 **Improve UX** - Enhance TUI, CLI messages, error handling

### Before You Start

1. Check [STATUS.md](STATUS.md) - Current implementation status
2. Review [ROADMAP.md](ROADMAP.md) - Planned features
3. Search [Issues](https://github.com/Iormungand21/sindri/issues) - Avoid duplicates
4. Read [ARCHITECTURE.md](ARCHITECTURE.md) - Understand design patterns

---

## Development Setup

### Prerequisites

- Python 3.11+
- Git
- Ollama (installed and running)
- 8GB+ VRAM (or willingness to use smaller models)

### Clone and Install

```bash
# Fork the repository on GitHub first, then:
git clone https://github.com/YOUR_USERNAME/sindri.git
cd sindri

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev,tui]"

# Install Ollama models (at least one)
ollama pull qwen2.5-coder:3b   # Minimum for testing
ollama pull qwen2.5-coder:14b  # Full functionality

# Verify installation
pytest tests/ -v
sindri run "Create test.txt with 'hello'"
```

### Development Tools

```bash
# Linting
ruff check sindri/

# Type checking
mypy sindri/

# Tests with coverage
pytest --cov=sindri --cov-report=term-missing

# Format code
ruff format sindri/
```

---

## Project Structure

```
sindri/
├── sindri/               # Source code
│   ├── core/            # Core orchestration (schedulers, loops, etc.)
│   ├── agents/          # Agent definitions and prompts
│   ├── tools/           # Tool implementations
│   ├── memory/          # Memory system
│   ├── llm/             # LLM interface
│   ├── persistence/     # Database layer
│   └── tui/             # Terminal UI
├── tests/               # Test suite
├── docs/                # User documentation
├── prompts/             # Historical phase prompts
├── README.md            # Project overview
├── STATUS.md            # Current status
├── ROADMAP.md           # Feature roadmap
└── ARCHITECTURE.md      # Technical design

Key files:
- sindri/core/hierarchical.py - Ralph loop implementation (295 lines)
- sindri/core/orchestrator.py - Main entry point
- sindri/agents/registry.py   - Agent definitions
- sindri/tools/base.py         - Tool interface
```

---

## Making Changes

### 1. Create a Branch

```bash
# Update main
git checkout main
git pull upstream main

# Create feature branch
git checkout -b feature/my-feature

# Or for bug fixes
git checkout -b fix/bug-description
```

### 2. Make Your Changes

Follow these principles:

**Code:**
- ✅ Async everywhere (all I/O should be `async/await`)
- ✅ Type hints on all functions
- ✅ Docstrings on public APIs (Google style)
- ✅ Structured logging (use `structlog`, not `print`)
- ✅ Tools return `ToolResult`, never raise

**Example:**
```python
async def my_function(param: str) -> str:
    """Short description.

    Args:
        param: Description of parameter

    Returns:
        Description of return value

    Raises:
        ValueError: When validation fails
    """
    log.info("function_called", param=param)

    if not param:
        raise ValueError("param cannot be empty")

    result = await async_operation(param)
    return result
```

### 3. Add Tests

**Every change needs tests!**

```bash
# Create test file
tests/test_my_feature.py
```

**Example:**
```python
import pytest
from sindri.my_module import my_function

async def test_my_function_success():
    """Test successful execution."""
    result = await my_function("test")
    assert result == "expected"

async def test_my_function_validation():
    """Test validation error."""
    with pytest.raises(ValueError):
        await my_function("")
```

### 4. Update Documentation

If your change affects users:

- Update [README.md](README.md) - CLI examples, features
- Update [docs/](docs/) - User guides
- Update [STATUS.md](STATUS.md) - Implementation status
- Add docstrings - Public APIs

If your change affects developers:

- Update [ARCHITECTURE.md](ARCHITECTURE.md) - Design patterns
- Update [ROADMAP.md](ROADMAP.md) - Mark features complete
- Add code comments - Complex logic only

### 5. Run Tests

```bash
# All tests
pytest tests/ -v

# Specific test
pytest tests/test_my_feature.py -v

# With coverage
pytest --cov=sindri --cov-report=term-missing

# Type checking
mypy sindri/

# Linting
ruff check sindri/
```

---

## Testing

### Test Requirements

- ✅ Unit tests for all new functions
- ✅ Integration tests for features
- ✅ Edge cases and error paths
- ✅ Type hints in test functions
- ✅ Descriptive test names

### Test Structure

```python
# tests/test_module.py
import pytest
from sindri.module import function

# Use descriptive test names
async def test_given_valid_input_when_called_then_returns_expected():
    """Test successful case."""
    result = await function("valid")
    assert result == "expected"

async def test_given_invalid_input_when_called_then_raises_error():
    """Test error case."""
    with pytest.raises(ValueError):
        await function("invalid")

# Use fixtures for common setup
@pytest.fixture
async def sample_data():
    """Provide sample data."""
    return {"key": "value"}

async def test_with_fixture(sample_data):
    """Test using fixture."""
    result = await function(sample_data)
    assert result is not None
```

### Running Ollama Tests

Some tests require Ollama:

```bash
# Ensure Ollama is running
systemctl status ollama  # or: ollama serve

# Run tests
pytest tests/ -v

# Skip Ollama-dependent tests
pytest tests/ -v -m "not ollama"
```

---

## Documentation

### Types of Documentation

1. **User Docs** (`docs/`)
   - Getting started guides
   - Task-specific tutorials
   - Configuration reference
   - Troubleshooting

2. **Developer Docs**
   - `ARCHITECTURE.md` - Technical design
   - `ROADMAP.md` - Feature roadmap
   - Code comments - Complex logic only
   - Docstrings - Public APIs

3. **Status Docs**
   - `STATUS.md` - What works, what doesn't
   - `README.md` - Project overview

### Documentation Style

**User docs:**
- Clear, concise
- Examples for everything
- Start with simplest case
- Show expected output

**Developer docs:**
- Explain "why" not just "what"
- Include code examples
- Link to actual code files
- Diagram complex flows

**Code comments:**
- Only for non-obvious logic
- Explain intent, not mechanics
- Keep up-to-date or remove

---

## Pull Request Process

### 1. Prepare PR

```bash
# Update your branch
git fetch upstream
git rebase upstream/main

# Run final checks
pytest tests/ -v
mypy sindri/
ruff check sindri/

# Commit changes
git add .
git commit -m "feat: Add feature X"

# Push to your fork
git push origin feature/my-feature
```

### 2. Create PR

On GitHub:

1. Go to your fork
2. Click "Pull Request"
3. Select `main` as base branch
4. Fill in PR template

**PR Title Format:**
- `feat: Add feature X` - New feature
- `fix: Fix bug Y` - Bug fix
- `docs: Update guide Z` - Documentation
- `test: Add tests for X` - Tests
- `refactor: Improve X` - Code refactoring
- `perf: Optimize X` - Performance

**PR Description Should Include:**
- What changed
- Why it changed
- How to test it
- Screenshots (for UI changes)
- Related issues

**Example:**
```markdown
## What
Add `list_directory` tool for agents to explore project structure.

## Why
Agents currently can't see directory contents, limiting their ability to understand codebases.

## How to Test
```bash
pytest tests/test_tools.py::test_list_directory -v
sindri run "List all Python files in this project"
```

## Related
Closes #42
Part of Phase 5 (#50)
```

### 3. Review Process

- Maintainer will review within 1 week
- Address feedback in new commits
- Don't force-push after review starts
- Discussion is encouraged!

### 4. Merge

Once approved:
- Squash commits if requested
- Update STATUS.md if significant change
- Celebrate! 🎉

---

## Code Style

### Python Style

- **PEP 8** - Follow Python conventions
- **Line length** - 100 characters max
- **Imports** - Alphabetical, grouped (stdlib, third-party, local)
- **Naming** - `snake_case` for functions, `PascalCase` for classes

**Example:**
```python
from pathlib import Path
from typing import Optional

import structlog
from pydantic import BaseModel

from sindri.core.tasks import Task
from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()

class MyTool(Tool):
    """Tool docstring."""

    async def execute(self, param: str) -> ToolResult:
        """Execute tool."""
        log.info("executing", param=param)
        return ToolResult(success=True, output="result")
```

### Type Hints

**Required:**
```python
# ✅ Good
async def my_function(name: str, count: int = 0) -> list[str]:
    """Function with type hints."""
    return [name] * count

# ❌ Bad
async def my_function(name, count=0):
    """Function without type hints."""
    return [name] * count
```

### Async/Await

**All I/O should be async:**
```python
# ✅ Good
async def read_file(path: Path) -> str:
    """Async file reading."""
    async with aiofiles.open(path) as f:
        return await f.read()

# ❌ Bad
def read_file(path: Path) -> str:
    """Blocking file reading."""
    with open(path) as f:
        return f.read()
```

### Logging

**Use structured logging:**
```python
import structlog

log = structlog.get_logger()

# ✅ Good
log.info("task_completed", task_id=task.id, duration=elapsed)

# ❌ Bad
print(f"Task {task.id} completed in {elapsed}s")
```

---

## Community Guidelines

### Be Respectful

- Assume good intent
- Be patient with newcomers
- Constructive feedback only
- No harassment or discrimination

### Communication

- **Issues** - Bug reports, feature requests
- **PRs** - Code changes, discussion
- **Discussions** - General questions, ideas

### Getting Help

- 📖 Read [docs/](docs/) first
- 🔍 Search existing issues
- 💬 Open discussion for questions
- 🐛 Open issue for bugs

---

## Development Workflow

### Typical Workflow

1. **Pick an issue** - Comment to claim it
2. **Create branch** - `git checkout -b feature/name`
3. **Implement** - Write code + tests
4. **Test** - `pytest tests/ -v`
5. **Document** - Update relevant docs
6. **Commit** - `git commit -m "feat: ..."`
7. **Push** - `git push origin feature/name`
8. **PR** - Open pull request
9. **Review** - Address feedback
10. **Merge** - Celebrate!

### For Maintainers

**Reviewing PRs:**
- Check code quality
- Run tests locally
- Verify documentation
- Test manually if needed
- Provide constructive feedback

**Merging:**
- Squash if many commits
- Update STATUS.md if needed
- Close related issues
- Thank contributor!

---

## Quick Reference

### Adding a Tool

1. Create `sindri/tools/my_tool.py`:
```python
from sindri.tools.base import Tool, ToolResult

class MyTool(Tool):
    @property
    def schema(self) -> dict:
        return {"name": "my_tool", ...}

    async def execute(self, **params) -> ToolResult:
        return ToolResult(success=True, output="...")
```

2. Register in `sindri/tools/registry.py`
3. Add to agent in `sindri/agents/registry.py`
4. Test in `tests/test_tools.py`
5. Document in `docs/AGENTS.md`

### Adding an Agent

1. Define in `sindri/agents/registry.py`
2. Create prompt in `sindri/agents/prompts.py`
3. Add delegation path in parent agent
4. Test in `tests/test_agents.py`
5. Document in `docs/AGENTS.md`

### Adding a Feature

1. Check ROADMAP.md for design
2. Read ARCHITECTURE.md for patterns
3. Implement following code style
4. Add comprehensive tests
5. Update user documentation
6. Update STATUS.md

---

## Questions?

- 📖 Check [ARCHITECTURE.md](ARCHITECTURE.md)
- 🗺️ See [ROADMAP.md](ROADMAP.md)
- 📊 Review [STATUS.md](STATUS.md)
- 💬 Open a discussion
- 📧 Contact maintainers

**Thank you for contributing to Sindri!** 🔨
