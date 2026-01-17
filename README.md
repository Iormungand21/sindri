# Sindri 🔨

**Local-first LLM orchestration for code generation**

Forge code with local LLMs via Ollama, using a hierarchical multi-agent system inspired by Norse mythology. Like the legendary dwarf smith who forged Mjolnir, Sindri crafts your code through iterative refinement.

> **Status:** Production Ready (v0.1.0) - 11 agents, 32 tools, 1284 tests passing. See [STATUS.md](STATUS.md) for details.

## Features

- 🏛️ **Hierarchical Multi-Agent System** - 11 specialized agents delegate tasks to experts
- 🧠 **Five-Tier Memory System** - Working, episodic, semantic, pattern, and analysis memory
- 🎨 **Rich Terminal UI** - Monitor agent activity, task trees, and VRAM usage in real-time
- 🌐 **Web UI** - React dashboard with agent graph, session replay, and code diff viewer
- ⚡ **Parallel Execution** - Independent tasks run concurrently with VRAM-aware batching
- 💾 **Crash Recovery** - Automatic checkpointing and session restoration
- 🔄 **Error Recovery** - Classification, retry, stuck detection, and model fallback
- 📊 **VRAM Management** - Intelligent model loading with LRU eviction and pre-warming
- 🗄️ **Vector Search** - Semantic codebase search with sqlite-vec and local embeddings
- 🔌 **Plugin System** - Custom tools and agents without modifying Sindri
- 🤝 **Collaboration** - Session sharing, comments, and real-time presence

## Installation

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) installed and running
- 16GB VRAM recommended (works with 8GB+ using smaller models)

### Install Sindri

```bash
# Clone repository
git clone https://github.com/Iormungand21/sindri.git
cd sindri

# Install with all dependencies
pip install -e ".[dev,tui,web]"

# Verify installation
sindri --version
sindri doctor --verbose
```

### Pull Required Models

```bash
# Core models
ollama pull qwen2.5-coder:14b       # Orchestrator (Brokkr)
ollama pull qwen2.5-coder:7b        # Coder (Huginn), Tester (Skald)
ollama pull qwen2.5-coder:3b        # Executor (Ratatoskr)
ollama pull llama3.1:8b             # Reviewer (Mimir), Docs (Idunn)

# Memory system
ollama pull nomic-embed-text        # Embeddings

# Optional specialized models
ollama pull deepseek-r1:14b         # Planner (Odin), Debugger (Baldr)
ollama pull sqlcoder:7b             # SQL Expert (Fenrir)
ollama pull codestral:22b           # Multi-language (Vidar)
```

## Quick Start

### Basic Usage

```bash
# Simple task with single agent
sindri run "Create a hello.py file that prints hello world"

# Multi-agent orchestration (recommended for complex tasks)
sindri orchestrate "Build a REST API for a todo list with tests"

# Specify work directory for outputs
sindri orchestrate "Create a blog API" --work-dir ./my_project
```

### Interactive Interfaces

```bash
# Terminal UI
sindri tui

# Web UI (React dashboard)
sindri web --port 8000
# Visit http://localhost:8000
```

### Session Management

```bash
# List past sessions
sindri sessions

# Resume interrupted session
sindri resume <session_id>

# Export session to markdown
sindri export <session_id>

# View performance metrics
sindri metrics
```

## Agent Hierarchy

Sindri uses 11 Norse mythology-themed specialized agents:

| Agent | Role | Model | VRAM |
|-------|------|-------|------|
| **Brokkr** | Master Orchestrator | qwen2.5-coder:14b | ~9GB |
| **Huginn** | Code Implementation | qwen2.5-coder:7b | ~5GB |
| **Mimir** | Code Review | llama3.1:8b | ~5GB |
| **Ratatoskr** | Fast Executor | qwen2.5-coder:3b | ~2GB |
| **Skald** | Test Writer | qwen2.5-coder:7b | ~5GB |
| **Fenrir** | SQL Specialist | sqlcoder:7b | ~5GB |
| **Odin** | Strategic Planner | deepseek-r1:14b | ~9GB |
| **Heimdall** | Security Auditor | qwen3:14b | ~10GB |
| **Baldr** | Debugger | deepseek-r1:14b | ~9GB |
| **Idunn** | Documentation | llama3.1:8b | ~5GB |
| **Vidar** | Multi-language | codestral:22b | ~14GB |

### Delegation Flow

```
User Task
    ↓
┌───────────┐
│  Brokkr   │ ─ Plans and delegates
└─────┬─────┘
      │
      ├──→ Huginn ──→ Writes implementation ──→ Delegates to Ratatoskr
      │
      ├──→ Mimir ───→ Reviews code quality
      │
      ├──→ Skald ───→ Generates tests ──→ Delegates to Ratatoskr
      │
      ├──→ Fenrir ──→ Handles SQL/database tasks
      │
      ├──→ Heimdall ─→ Security audit
      │
      └──→ Idunn ───→ Documentation
```

## Tools (32 total)

**Filesystem:** read_file, write_file, edit_file, list_directory, read_tree
**Search:** search_code, find_symbol
**Git:** git_status, git_diff, git_log, git_branch
**HTTP:** http_request, http_get, http_post
**Testing:** run_tests, check_syntax
**Formatting:** format_code, lint_code
**Refactoring:** rename_symbol, extract_function, inline_variable, move_file, batch_rename, split_file, merge_files
**SQL:** execute_query, describe_schema, explain_query
**CI/CD:** generate_workflow, validate_workflow
**Core:** shell, delegate, propose_plan

## Memory System (Muninn)

Five-tier memory architecture for intelligent context:

| Tier | Budget | Purpose |
|------|--------|---------|
| **Working** | 50% | Recent conversation, current task, tool results |
| **Episodic** | 18% | Past task summaries, what worked/didn't |
| **Semantic** | 18% | Codebase embeddings, relevant code chunks |
| **Pattern** | 5% | Learned successful tool sequences |
| **Analysis** | 9% | Codebase architecture, dependencies, style |

```bash
# Memory is enabled by default
sindri orchestrate "Add user authentication"

# Disable memory if needed
sindri orchestrate "Simple task" --no-memory
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `sindri run <task>` | Execute task with single agent |
| `sindri orchestrate <task>` | Execute with hierarchical agents |
| `sindri tui [task]` | Launch terminal UI |
| `sindri web` | Launch web UI server |
| `sindri agents` | List all agents |
| `sindri sessions` | Show past sessions |
| `sindri resume <id>` | Resume a session |
| `sindri export <id>` | Export session to markdown |
| `sindri metrics` | View performance metrics |
| `sindri doctor` | System health check |
| `sindri plugins list` | List installed plugins |
| `sindri projects add <path>` | Register project for cross-project search |
| `sindri share <session>` | Share session with others |
| `sindri feedback <session> <rating>` | Rate session for fine-tuning |

### Options

| Option | Description |
|--------|-------------|
| `--model, -m` | Specify Ollama model |
| `--max-iter` | Maximum iterations (default: 50) |
| `--vram-gb` | Total VRAM available (default: 16.0) |
| `--work-dir` | Output directory for generated files |
| `--no-memory` | Disable memory system |

## Configuration

Create `sindri.toml` in your project or `~/.sindri/config.toml`:

```toml
[general]
data_dir = "~/.sindri"
ollama_host = "http://localhost:11434"
total_vram_gb = 16.0
reserve_vram_gb = 2.0

[memory]
episodic_limit = 5
semantic_limit = 10
max_context_tokens = 32768

[tui]
theme = "dark"
refresh_rate_ms = 100
```

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for full options.

## Documentation

| Document | Purpose |
|----------|---------|
| [ONBOARDING.md](ONBOARDING.md) | Quick start for new contributors |
| [STATUS.md](STATUS.md) | Current state and recent changes |
| [ROADMAP.md](ROADMAP.md) | Future plans and priorities |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Technical design and patterns |
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | User quick start guide |
| [docs/AGENTS.md](docs/AGENTS.md) | Agent capabilities and usage |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues and solutions |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev,tui,web]"

# Run tests (1284 backend + 104 frontend)
pytest tests/ -v
cd sindri/web/static && npm test -- --run

# Type checking
mypy sindri/

# Linting
ruff check sindri/
```

## Troubleshooting

**Ollama not responding:**
```bash
systemctl --user start ollama
ollama list              # Verify models
sindri doctor            # Full health check
```

**Out of VRAM:**
```bash
# Reduce VRAM allocation
sindri orchestrate "task" --vram-gb 12.0
```

**Recover from crash:**
```bash
sindri sessions          # List sessions
sindri resume <id>       # Continue execution
```

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for more solutions.

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE)

## Acknowledgments

- Inspired by Ralph Loop pattern
- Norse mythology for agent naming
- Built with [Ollama](https://ollama.ai), [Textual](https://textual.textualize.io), [FastAPI](https://fastapi.tiangolo.com), [React](https://react.dev), and [sqlite-vec](https://github.com/asg017/sqlite-vec)

---

*Forged in the fires of iteration, like Mjolnir in Sindri's forge.* ⚒️
