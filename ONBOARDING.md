# Sindri Onboarding Guide

Welcome! This document will help you quickly understand the Sindri project and get productive.

---

## PRIORITY: Architecture Transformation

**Before starting any other work, read the approved architectural change plan:**

```
/home/ryan/.claude/plans/silly-kindling-parnas.md
```

Sindri is being transformed from a multi-user tool to an **internal-only research machine assistant**.

### Completed (All Milestones)
- ✅ **Milestone 1:** Removed `sindri/collaboration/` (~16,200 lines, 28+ CLI commands, 50+ API endpoints)
- ✅ **Milestone 2:** Removed `sindri/ide/` (~2,100 lines, 2 CLI commands)
- ✅ **Milestone 3:** Simplified marketplace to local-only (~220 lines removed)
- ✅ **Milestone 4:** Relaxed security restrictions (localhost/private IPs now allowed)
- ✅ **Milestone 5:** Added system access configuration (SystemAccessLevel enum, CLI commands, +37 tests)
- ✅ **Milestone 6:** Added self-management tools (26 tools, sindri_admin agent, service/schedule/self CLI commands, +87 tests)
- ✅ **Milestone 7:** Web UI cleanup (verified - no auth/collab UI existed)
- ✅ **Milestone 8:** Documentation update (README, ARCHITECTURE, STATUS, ROADMAP updated)

### Architecture Transformation Complete
Sindri is now fully configured as an **internal-only research machine assistant**.

See `STATUS.md` and `ROADMAP.md` for full details.

---

## What is Sindri?

**Sindri** is a local-first, hierarchical LLM orchestration CLI that coordinates specialized agents (Norse-themed) to build, refactor, and maintain code using Ollama. Think of it as a multi-agent coding assistant running entirely on your machine with a 16GB VRAM GPU.

**Key Facts:**
- **Status:** Architecture Transformation COMPLETE (Internal-Only Mode)
- **Tests:** 2726 backend + 104 frontend
- **Agents:** 18 specialized agents (including sindri_admin)
- **Tools:** 155+ tools (26 new in Milestone 6)
- **Interfaces:** CLI, TUI (Textual), Web UI (React), Voice

---

## Quick Verification

Before starting work, verify the environment:

```bash
cd /home/ryan/projects/sindri

# Run tests (should see 2726 passed)
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
├── tools/         # All 155+ tool implementations
├── memory/        # 5-tier memory system
├── persistence/   # Database, metrics, feedback
├── tui/           # Terminal UI (Textual)
├── web/           # FastAPI + React frontend
├── plugins/       # Plugin system (to be simplified in Milestone 3)
├── voice/         # Voice interface (STT/TTS)
└── analysis/      # Codebase understanding

tests/             # Pytest tests (~2726 tests)
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

**Last Updated:** 2026-01-19 (Docker Runtime Tools Added)
