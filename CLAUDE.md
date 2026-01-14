# CLAUDE.md - Sindri Project Context

## Project Overview

**Sindri** is a local-first, hierarchical LLM orchestration CLI tool. Like the Norse dwarf smith who forged Mjolnir, Sindri forges code using local LLMs via Ollama.

## Quick Commands

```bash
# Install dependencies
pip install -e ".[dev,tui]"

# Run tests
pytest tests/ -v

# Run linter
ruff check sindri/

# Type check
mypy sindri/

# Run a simple test
sindri run "Create hello.py that prints hello"

# Launch TUI
sindri tui
```

## Architecture

```
sindri/
├── cli.py                  # Click CLI entry point
├── config.py               # Pydantic config with TOML loading
├── core/
│   ├── loop.py             # Ralph-style iteration loop (CORE)
│   ├── completion.py       # Completion detection
│   ├── context.py          # Prompt building
│   ├── tasks.py            # Task data model
│   ├── scheduler.py        # Priority queue with dependencies
│   └── delegation.py       # Parent→child task spawning
├── agents/
│   ├── definitions.py      # AgentDefinition dataclass
│   ├── registry.py         # AGENTS dict with all agent configs
│   └── prompts.py          # System prompts for each agent
├── llm/
│   ├── client.py           # Async Ollama wrapper
│   └── manager.py          # VRAM-aware model loading
├── tools/
│   ├── base.py             # Tool ABC
│   ├── registry.py         # Tool registry
│   ├── filesystem.py       # read_file, write_file, edit_file
│   └── shell.py            # shell execution
├── memory/
│   ├── system.py           # MuninnMemory orchestrator
│   ├── episodic.py         # Session history
│   ├── semantic.py         # Codebase embeddings
│   └── embedder.py         # nomic-embed-text client
├── persistence/
│   ├── database.py         # SQLite setup
│   ├── state.py            # Session state
│   └── vectors.py          # sqlite-vec for embeddings
└── tui/
    ├── app.py              # Textual app
    └── widgets/            # Task tree, output, etc.
```

## Agent Hierarchy (Norse Theme)

| Agent | Role | Model | Delegates To |
|-------|------|-------|--------------|
| **Brokkr** | Orchestrator | qwen2.5:14b | huginn, mimir, ratatoskr |
| **Huginn** | Coder (Thought) | deepseek-coder:16b | ratatoskr |
| **Mimir** | Reviewer (Wisdom) | qwen2.5:7b | - |
| **Ratatoskr** | Executor (Messenger) | qwen2.5:3b | - |

## Key Patterns

### The Ralph Loop
The core of Sindri is a Ralph-style iteration loop:
```python
for iteration in range(max_iterations):
    response = await llm.chat(model, messages)
    if "<sindri:complete/>" in response:
        return Success
    tool_results = await execute_tools(response)
    messages.append(response, tool_results)
```

### Delegation as Nested Loops
When an agent delegates, it spawns a child loop:
```python
if tool_call.name == "delegate":
    child_task = create_child_task(...)
    child_result = await child_loop.run(child_task)
    return child_result
```

### Memory-Augmented Context
Each iteration builds context from three memory tiers:
1. **Working** (recent conversation)
2. **Episodic** (past task summaries)
3. **Semantic** (codebase embeddings)

## Development Phases

This project is built iteratively using the Ralph loop technique with Claude Code:

1. **Phase 1**: Foundation - Basic single-agent loop ✓/○
2. **Phase 2**: Hierarchical Agents - Multi-agent delegation ○
3. **Phase 3**: Memory System - Muninn ○
4. **Phase 4**: TUI - Textual interface ○
5. **Phase 5**: Polish - Error handling, tests, docs ○

Each phase has a dedicated prompt in `prompts/PHASE*.md`.

## Important Files

- `prompts/PHASE1.md` - Current phase prompt (start here)
- `pyproject.toml` - Dependencies and package config
- `sindri/core/loop.py` - The heart of the system
- `sindri/agents/registry.py` - Agent definitions

## Conventions

- **Async everywhere**: Use `async/await` for all I/O
- **Structured logging**: Use `structlog` not print
- **Type hints**: All functions should be typed
- **Pydantic models**: For all data structures
- **Tool schemas**: Match Ollama's function calling format

## Testing

```bash
# Run specific test
pytest tests/test_loop.py -v

# Run with coverage
pytest --cov=sindri --cov-report=term-missing

# Quick smoke test
python -c "from sindri import AgentLoop; print('OK')"
```

## Common Tasks

### Add a new tool
1. Create class in `sindri/tools/` inheriting from `Tool`
2. Register in `sindri/tools/registry.py`
3. Add to appropriate agent's tool list in `agents/registry.py`

### Add a new agent
1. Define in `agents/registry.py` with AgentDefinition
2. Create system prompt in `agents/prompts.py`
3. Add to parent agent's `delegate_to` list

### Debug agent behavior
```python
# Enable verbose logging
import structlog
structlog.configure(...)

# Or check session state
from sindri.persistence.state import SessionState
state = SessionState()
session = state.load("session-id")
print(session.turns)
```

## Target Platform

- **OS**: Linux (EndeavourOS/Arch)
- **GPU**: AMD Radeon 6950XT (16GB VRAM)
- **Python**: 3.11+
- **LLM Backend**: Ollama with ROCm

## Completion Markers

Each phase uses a completion promise:
- Phase 1: `<promise>PHASE1_COMPLETE</promise>`
- Phase 2: `<promise>PHASE2_COMPLETE</promise>`
- Phase 3: `<promise>PHASE3_COMPLETE</promise>`
- Phase 4: `<promise>PHASE4_COMPLETE</promise>`
- Phase 5: `<promise>SINDRI_COMPLETE</promise>`

---

*When in doubt, check the phase prompt in `prompts/`.*
