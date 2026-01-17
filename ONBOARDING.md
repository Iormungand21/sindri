# Sindri Onboarding Guide

Welcome! This document will help you quickly understand the Sindri project and get productive.

---

## What is Sindri?

**Sindri** is a local-first, hierarchical LLM orchestration CLI that coordinates specialized agents (Norse-themed) to build, refactor, and maintain code using Ollama. Think of it as a multi-agent coding assistant running entirely on your machine with a 16GB VRAM GPU.

**Key Facts:**
- **Status:** Production Ready (v0.1.0)
- **Tests:** 1743 backend + 104 frontend (100% passing)
- **Agents:** 11 specialized agents
- **Tools:** 48 tools
- **Interfaces:** CLI, TUI (Textual), Web UI (React), Voice

---

## Quick Verification

Before starting work, verify the environment:

```bash
cd /home/ryan/projects/sindri

# Run tests (should see 1743 passed)
.venv/bin/pytest tests/ -v --tb=no -q

# Check system health
.venv/bin/sindri doctor --verbose

# List agents
.venv/bin/sindri agents

# Check voice interface
.venv/bin/sindri voice-status
```

---

## Essential Documents

Read these in order for full context:

### 1. CLAUDE.md (5 min)
**What:** Project conventions and quick commands
**Why:** Understand coding standards, testing approach, and common patterns
**Key Sections:** Architecture overview, quick commands, development phases

### 2. STATUS.md (5 min)
**What:** Current state and recent changes
**Why:** Know what exists, what was just added, and what commands are available
**Key Sections:** Recent Changes, Project Summary (agents, tools), Quick Commands

### 3. ROADMAP.md (5 min)
**What:** Vision, principles, and future plans
**Why:** Understand project direction and what features to prioritize next
**Key Sections:** Guiding Principles, Future Features, Development Guidelines

### 4. ARCHITECTURE.md (10 min)
**What:** Technical design and patterns
**Why:** Understand how components interact before making changes
**Key Sections:** Core Concepts (Ralph Loop, Delegation), Directory Structure, Design Patterns

---

## Document Quick Reference

| Document | Purpose | When to Read | When to Update |
|----------|---------|--------------|----------------|
| **ONBOARDING.md** | Entry point for new agents | First | When docs change |
| **STATUS.md** | Current state, recent changes | Starting session | After completing features |
| **ROADMAP.md** | Future plans, priorities | Choosing what to build | After major features |
| **ARCHITECTURE.md** | Technical design | Before major changes | After architectural changes |
| **CLAUDE.md** | Conventions, commands | Reference | Rarely |
| **README.md** | User documentation | Reference | After user-facing changes |

---

## Typical Workflow

### Starting a Session

1. **Read ONBOARDING.md** (this file) - understand project context
2. **Read STATUS.md** - see current state and recent changes
3. **Check ROADMAP.md** - identify next feature to implement
4. **Run tests** - verify everything works before changes

### Implementing a Feature

1. **Understand the feature** - check if similar patterns exist
2. **Write tests first** (TDD) - one test file per module
3. **Implement the feature** - follow existing patterns
4. **Run tests** - ensure all pass
5. **Update docs** - STATUS.md at minimum

### Ending a Session

1. **Update STATUS.md:**
   - Add recent changes section
   - Update test counts
   - Note any issues or next steps

2. **Update ROADMAP.md** (if applicable):
   - Mark completed features
   - Add to changelog

3. **Commit with clear message:**
   ```bash
   git add -A
   git commit -m "feat: Add <feature name>

   - <change 1>
   - <change 2>
   - Tests: X new tests (total: Y passing)"
   ```

---

## Key Directories

```
sindri/
├── core/          # Orchestration, delegation, events
├── agents/        # Agent definitions and prompts
├── tools/         # All 48 tool implementations
├── memory/        # 5-tier memory system
├── persistence/   # Database, metrics, feedback
├── tui/           # Terminal UI (Textual)
├── web/           # FastAPI + React frontend
├── plugins/       # Plugin system
├── collaboration/ # Session sharing, comments
├── voice/         # Voice interface (STT/TTS)
└── analysis/      # Codebase understanding

tests/             # Pytest tests (1743 tests)
docs/              # User documentation
docs/archive/      # Historical documents
```

---

## Common Tasks

### Add a New Tool

1. Create `sindri/tools/<name>.py` with Tool subclass
2. Register in `sindri/tools/registry.py`
3. Add to agents in `sindri/agents/registry.py`
4. Write `tests/test_<name>.py`

### Add a New Agent

1. Define in `sindri/agents/registry.py`
2. Add prompt in `sindri/agents/prompts.py`
3. Add to parent's `delegate_to` list

### Fix a Bug

1. Write failing test first
2. Fix the bug
3. Verify test passes
4. Check no regressions: `pytest tests/ -v`

---

## Testing Commands

```bash
# All tests
.venv/bin/pytest tests/ -v

# Specific file
.venv/bin/pytest tests/test_tools.py -v

# With coverage
.venv/bin/pytest --cov=sindri --cov-report=term-missing

# Frontend tests
cd sindri/web/static && npm test -- --run
```

---

## Things to Know

### Code Patterns
- **Async everywhere** - All I/O uses async/await
- **Type hints** - All functions have type annotations
- **ToolResult** - Tools return ToolResult, never raise exceptions
- **Structured logging** - Use structlog, not print
- **Pydantic models** - For all data structures

### Agent Model Sizes (for VRAM planning)
- Small (2-3GB): qwen2.5-coder:3b
- Medium (5GB): qwen2.5-coder:7b, llama3.1:8b
- Large (9-10GB): qwen2.5-coder:14b, deepseek-r1:14b
- XLarge (14GB): codestral:22b

### Event-Driven Architecture
The TUI and Web UI subscribe to events from the orchestrator. When adding features that need UI updates, emit appropriate events via EventBus.

---

## Archived Documents

Historical documents are in `docs/archive/`:
- Phase prompts (PHASE1-5.md)
- Bug fix records
- Session summaries
- Full history of STATUS.md and ROADMAP.md

---

## Need Help?

- **Tests:** Look at existing tests for patterns
- **Similar feature:** Search codebase with `grep -r "pattern" sindri/`
- **Architecture question:** Check ARCHITECTURE.md
- **User-facing:** Check README.md and docs/

---

**Last Updated:** 2026-01-17
