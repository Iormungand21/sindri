# Sindri Development Roadmap

**Vision:** A production-ready, local-first LLM orchestration system that intelligently coordinates specialized agents to build, refactor, and maintain codebases using local inference.

**Current Status:** Production Ready (v0.1.0) - 11 agents, 48 tools, 2124 backend + 104 frontend tests (100% passing)

---

## Quick Start

```bash
# Verify installation
.venv/bin/pytest tests/ -v --tb=no -q    # 2011 tests
cd sindri/web/static && npm test -- --run  # 104 frontend tests
.venv/bin/sindri doctor --verbose

# Try it
.venv/bin/sindri run "Create hello.py"
.venv/bin/sindri orchestrate "Review this project"
.venv/bin/sindri tui                       # Terminal UI
.venv/bin/sindri web --port 8000           # Web UI
.venv/bin/sindri voice                     # Voice interface
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

### Phase 9: Advanced Features (Complete)
- Code Diff Viewer, Timeline View, Session Replay
- Refactoring tools: move, batch rename, split, merge files
- CI/CD Integration: workflow generation and validation
- Agent Fine-Tuning: feedback collection and training export
- Remote Collaboration: session sharing, comments, presence
- Plugin Marketplace: install from git/URL/local, search, update
- Voice Interface: Whisper STT, multi-engine TTS, wake word
- Dependency Scanner: pip-audit, npm audit, cargo audit, govulncheck, SBOM
- Team Mode: user accounts, team management, role-based permissions

### Phase 10: Advanced Team Collaboration (In Progress)
- Notification System: mentions, comments, team invites, session activity
- User notification preferences with quiet hours
- CLI commands for notification management
- Activity Feed: team activity timeline with filtering and statistics
- Activity Feed API endpoints for web/mobile integration
- Webhooks: external integrations with Slack, Discord, and generic HTTP
- HMAC-SHA256 signature verification for webhook security
- Retry logic with exponential backoff for reliable delivery

**Total:** 2124 backend tests + 104 frontend tests (100% passing)

---

## Future Features (Phase 9+)

### High Priority

| Feature | Description | Status |
|---------|-------------|--------|
| Voice Interface | Speech-to-text commands, TTS responses | **Complete** |
| Plugin Marketplace | Share and discover community plugins | **Complete** |

### Medium Priority

| Feature | Description | Status |
|---------|-------------|--------|
| AST-Based Refactoring | Tree-sitter for precise multi-language refactoring | **Complete** |
| Dependency Scanner | OWASP/npm audit vulnerability detection | **Complete** |
| Docker Generator | Auto-generate Dockerfile/docker-compose | **Complete** |
| API Spec Generator | OpenAPI from route definitions | **Complete** |
| Coverage Visualization | Code coverage in Web UI | **Complete** |

### Exploratory

| Feature | Description | Status |
|---------|-------------|--------|
| Infrastructure as Code | Terraform/Pulumi generation for AWS/GCP/Azure | **Complete** |
| IDE Plugins | Neovim plugin, JSON-RPC server | **Complete** |
| Fine-Tuning Pipeline | Streamlined feedback → training → deployment | **Complete** |
| Team Mode | Multi-user sessions, role-based permissions | **Complete** |

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
| 2026-01-17 | Webhooks (Slack/Discord/Generic HTTP, HMAC signatures, retry logic) | +57 |
| 2026-01-17 | Activity Feed (team timeline, filtering, stats, API endpoints) | +56 |
| 2026-01-17 | Notification System (mentions, comments, team invites, preferences) | +56 |
| 2026-01-17 | Team Mode (user accounts, teams, role-based permissions) | +84 |
| 2026-01-17 | Fine-Tuning Pipeline (curation, registry, training, evaluation) | +72 |
| 2026-01-17 | IDE Integration (JSON-RPC server, Neovim plugin) | +56 |
| 2026-01-17 | Infrastructure as Code (Terraform AWS/GCP/Azure, Pulumi Python/TS) | +73 |
| 2026-01-17 | Coverage Visualization (Cobertura XML, LCOV, JSON; Web UI) | +40 |
| 2026-01-17 | AST-Based Refactoring (tree-sitter, Python/JS/TS/Rust/Go) | +55 |
| 2026-01-17 | API Spec Generator (OpenAPI 3.0 from Flask/FastAPI/Express/Django/Gin/Echo) | +62 |
| 2026-01-17 | Docker Generator (Dockerfile, docker-compose, validation) | +64 |
| 2026-01-17 | Dependency Scanner (pip-audit, npm audit, cargo audit, SBOM) | +58 |
| 2026-01-17 | Voice Interface (Whisper STT, multi-engine TTS) | +56 |
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
