# Sindri Development Roadmap

**Vision:** A production-ready, local-first LLM orchestration system that intelligently coordinates specialized agents to build, refactor, and maintain codebases using local inference.

**Current Status:** Production Ready (v0.1.0) - 11 agents, 32 tools, 1335 backend + 104 frontend tests (100% passing)

---

## Quick Start

```bash
# Verify installation
.venv/bin/pytest tests/ -v --tb=no -q    # 1284 tests
cd sindri/web/static && npm test -- --run  # 104 frontend tests
.venv/bin/sindri doctor --verbose

# Try it
.venv/bin/sindri run "Create hello.py"
.venv/bin/sindri orchestrate "Review this project"
.venv/bin/sindri tui                       # Terminal UI
.venv/bin/sindri web --port 8000           # Web UI
```

**Essential Reading:**
- `STATUS.md` - Current state and recent changes
- `PROJECT_HANDOFF.md` - Comprehensive project context
- `docs/QUICKSTART.md` - User guide

---

## Guiding Principles

1. **Local-First:** No cloud dependencies, works offline, user owns all data
2. **Efficient:** Parallel execution, smart caching, minimal VRAM waste
3. **Intelligent:** Memory-augmented, learns from past work, specialized agents
4. **Developer-Friendly:** Great UX, clear feedback, easy to extend
5. **Production-Ready:** Robust error handling, crash recovery, comprehensive tests

---

## Completed Phases (Summary)

### Phase 5: Polish & Production (Complete)
- CLI commands: agents, sessions, recover, resume, doctor, export, metrics
- Directory tools: list_directory, read_tree
- Memory enabled by default, VRAM gauge in TUI
- Error handling with classification, retry, stuck detection, recovery

### Phase 6: Performance & Parallelism (Complete)
- Parallel task execution with VRAM-aware batching
- Model caching with pre-warming and keep-warm
- Streaming responses with real-time token display

### Phase 7: Intelligence & Learning (Complete)
- Enhanced agent specialization (security, testing, SQL patterns)
- Pattern learning from successful completions
- Interactive planning with execution plans
- Codebase understanding (dependencies, architecture, style)

### Phase 8: Extensibility & Platform (Complete)
- Plugin system for custom tools and agents
- Web API (FastAPI) with REST and WebSocket
- Web UI (React) with dashboard, agent graph, session viewer
- Multi-project memory with cross-project search

### Phase 9: Advanced Features (Partial)
- Code Diff Viewer, Timeline View, Session Replay
- Refactoring tools: move, batch rename, split, merge files
- CI/CD Integration: workflow generation and validation
- Agent Fine-Tuning: feedback collection and training export
- Remote Collaboration: session sharing, comments, presence
- Plugin Marketplace: install from git/URL/local, search, update

**Total:** 1335 backend tests + 104 frontend tests (100% passing)

---

## Future Features (Phase 9+)

### High Priority

| Feature | Description | Status |
|---------|-------------|--------|
| Voice Interface | Speech-to-text commands, TTS responses | Planned |
| Plugin Marketplace | Share and discover community plugins | **Complete** |

### Medium Priority

| Feature | Description | Status |
|---------|-------------|--------|
| AST-Based Refactoring | Tree-sitter for precise multi-language refactoring | Idea |
| Dependency Scanner | OWASP/npm audit vulnerability detection | Idea |
| Docker Generator | Auto-generate Dockerfile/docker-compose | Idea |
| API Spec Generator | OpenAPI from route definitions | Idea |
| Coverage Visualization | Code coverage in Web UI | Idea |

### Exploratory

| Feature | Description | Status |
|---------|-------------|--------|
| Team Mode | Multi-user sessions, permissions | Idea |
| IDE Plugins | Neovim, JetBrains support | Idea |
| Fine-Tuning Pipeline | Streamlined feedback → training → deployment | Idea |
| Infrastructure as Code | Terraform/Pulumi generation | Idea |

---

## Development Guidelines

### Code Patterns
- **Async everywhere** - All I/O should be async
- **Structured logging** - Use `structlog`, not print
- **Type hints** - All functions fully typed
- **Pydantic models** - For all data structures
- **Error handling** - Always return ToolResult, never raise in tools
- **Tests** - One test file per module, use pytest fixtures

### Adding Features

**New Tool:**
1. Create class in `sindri/tools/` inheriting from `Tool`
2. Register in `sindri/tools/registry.py`
3. Add to agent tool lists in `sindri/agents/registry.py`
4. Write tests in `tests/test_<tool>.py`

**New Agent:**
1. Define in `sindri/agents/registry.py` with AgentDefinition
2. Create system prompt in `sindri/agents/prompts.py`
3. Add to parent agent's `delegate_to` list
4. Write tests in `tests/test_<agent>.py`

### Testing

```bash
# Run all tests
.venv/bin/pytest tests/ -v

# Run specific test file
.venv/bin/pytest tests/test_tools.py -v

# Run with coverage
.venv/bin/pytest --cov=sindri --cov-report=term-missing

# Frontend tests
cd sindri/web/static && npm test -- --run
```

---

## Changelog (Recent)

| Date | Feature | Tests |
|------|---------|-------|
| 2026-01-17 | Plugin Marketplace (install, search, update, uninstall) | +51 |
| 2026-01-17 | Remote Collaboration (sharing, comments, presence) | +65 |
| 2026-01-17 | Agent Fine-Tuning (feedback, training export) | +36 |
| 2026-01-17 | CI/CD Integration (workflow generation/validation) | +63 |
| 2026-01-16 | MergeFilesTool | +28 |
| 2026-01-16 | SplitFileTool | +28 |
| 2026-01-16 | BatchRenameTool | +32 |
| 2026-01-16 | MoveFileTool | +28 |
| 2026-01-16 | Session Replay | +33 |
| 2026-01-16 | Timeline View | +18 |
| 2026-01-16 | Code Diff Viewer | +25 |
| 2026-01-16 | D3.js Agent Graph | +15 |
| 2026-01-16 | Multi-Project Memory | +47 |
| 2026-01-16 | New Agents (Heimdall, Baldr, Idunn, Vidar) | +53 |

**For complete history, see:** `docs/archive/ROADMAP-full-history.md`

---

## Target Platform

- **OS:** Linux (Arch/EndeavourOS)
- **GPU:** AMD Radeon 6950XT (16GB VRAM)
- **Python:** 3.11+
- **LLM Backend:** Ollama with ROCm

---

**Last Updated:** 2026-01-17
**Maintained By:** Project contributors
