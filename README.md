# Sindri 🔨

**Local-first LLM orchestration for code + ops**

Forge code with local LLMs via Ollama, using a hierarchical multi-agent system inspired by Norse mythology. Like the legendary dwarf smith who forged Mjolnir, Sindri crafts your work through iterative refinement.

> **Status:** Internal-only, single-user mode complete. See [STATUS.md](STATUS.md) and [FACTS.md](FACTS.md) for current counts.

## Features

- 🏛️ **Hierarchical Multi-Agent System** - 27 specialized agents delegate tasks to experts
- 🧠 **Five-Tier Memory System** - Working, episodic, semantic, pattern, and analysis memory
- 🎨 **Rich Terminal UI** - Monitor agent activity, task trees, and VRAM usage in real-time
- 🌐 **Web UI** - React dashboard with agent graph, session replay, and code diff viewer
- 🗣️ **Voice Interface** - Local STT/TTS integration for hands-free workflows
- ⚡ **Parallel Execution** - Independent tasks run concurrently with VRAM-aware batching
- 💾 **Crash Recovery** - Automatic checkpointing and session restoration
- 🔄 **Error Recovery** - Classification, retry, stuck detection, and model fallback
- 📊 **VRAM Management** - Intelligent model loading with LRU eviction and pre-warming
- 🗄️ **Vector Search** - Semantic codebase search with sqlite-vec and local embeddings
- 🛡️ **System Access Controls** - Restricted/supervised/full modes with approvals
- 🧰 **Self-Management & Scheduling** - Service control, cron/systemd timers, model management
- 🔌 **Plugin System + Local Marketplace** - Extend tools/agents from local paths

## Installation

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) installed and running
- Go 1.22+ (for the TUI)
- 16GB VRAM recommended (works with 8GB+ using smaller models)

### Install Sindri

```bash
# Clone repository
git clone https://github.com/Iormungand21/sindri.git
cd sindri

# Install with core + dev tools
pip install -e ".[dev,web]"

# Optional extras
# voice, ast, media, profiling, browser, network
pip install -e ".[voice,ast,media,profiling,browser,network]"

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
ollama pull qwen3:14b               # Security (Heimdall)

# Memory system
ollama pull nomic-embed-text        # Embeddings

# Optional specialized models
ollama pull deepseek-r1:14b         # Planner (Odin), Debugger (Baldr)
ollama pull sqlcoder:7b             # SQL Expert (Fenrir)
ollama pull codestral:22b-v0.1-q4_K_M  # Multi-language (Vidar)
ollama pull mathstral:7b            # Math/Scientific (Nidhogg)
ollama pull granite3.2-vision:2b    # Vision docs (Groa)
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
# Terminal UI (Go + Bubble Tea)
cd tui && go build -o bin/sindri-tui ./cmd/sindri-tui
sindri tui

# Gateway-only mode (debugging)
sindri tui --gateway-only --gateway-timeout 5

# Web UI (React dashboard)
sindri web --port 8000
# Visit http://localhost:8000

# Web UI with authentication (recommended for shared networks)
sindri web --token my-secret-token

# Web UI for remote access (use with caution)
sindri web --host 0.0.0.0 --token my-secret-token \
    --allow-origin https://myapp.example.com

# Voice interface
sindri voice
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

Sindri uses 27 Norse-themed specialized agents with a master orchestrator (Brokkr) delegating to experts (coding, testing, review, security, SQL, docs, etc.). See [docs/AGENTS.md](docs/AGENTS.md) for the full roster and models.

## Tools (268 total)

Tooling spans code, infra, and creative domains:

- **Filesystem + Search + Git:** read/write/edit, tree, search, git status/diff/log/branch, git automation
- **Testing + Docs + Formatting:** run tests, test generation, docstrings/readme/api docs, lint/format
- **Refactoring + AST:** rename/extract/move/split/merge, AST parsing and refactors
- **Data + SQL:** query/plan/seed, SQL optimization, schema diff/index analysis, backups
- **CI/CD + Dependencies:** workflow gen/validation, SBOM, vulnerability scan, outdated deps
- **Infra + Ops:** Docker (build/run/compose), Terraform/Pulumi, migrations, services, scheduling
- **Networking + Web:** HTTP, DNS, TLS analysis, scraping, browser automation
- **Media + Docs + Images:** PDFs, OCR, spreadsheets, image ops, audio/video tools, TTS/STT
- **Math + Crypto + Compression:** symbolic math, stats/plots, hashing/encoding, archives
- **Diagrams + LaTeX + OpenSCAD + Dataviz:** Mermaid/PlantUML/D2, LaTeX, 3D modeling, charts
- **Creative/Domain:** music composition, game level design, Blender automation, KiCad design

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
| `sindri voice` | Launch voice interface |
| `sindri agents` | List all agents |
| `sindri sessions` | Show past sessions |
| `sindri resume <id>` | Resume a session |
| `sindri export <id>` | Export session to markdown |
| `sindri metrics` | View performance metrics |
| `sindri doctor` | System health check |
| `sindri access ...` | Configure system access mode |
| `sindri service ...` | Manage local services |
| `sindri schedule ...` | Cron/systemd scheduling helpers |
| `sindri self ...` | Self-management (models, version, VRAM) |
| `sindri plugins ...` | Manage plugins |
| `sindri marketplace ...` | Local-only plugin marketplace |
| `sindri finetune ...` | Fine-tuning workflows |
| `sindri feedback ...` | Collect training feedback |

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

```

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for full options.

## Documentation

| Document | Purpose |
|----------|---------|
| [ONBOARDING.md](ONBOARDING.md) | Quick start for new contributors |
| [docs/LLM_INDEX.md](docs/LLM_INDEX.md) | LLM agent entrypoint and workflow |
| [STATUS.md](STATUS.md) | Current state and recent changes |
| [ROADMAP.md](ROADMAP.md) | Future plans and priorities |
| [docs/prds/README.md](docs/prds/README.md) | Detailed PRDs and epics |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Technical design and patterns |
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | User quick start guide |
| [docs/AGENTS.md](docs/AGENTS.md) | Agent capabilities and usage |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues and solutions |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev,web]"

# Run tests (3713 backend + 104 frontend)
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
- Built with [Ollama](https://ollama.ai), [Bubble Tea](https://github.com/charmbracelet/bubbletea), [FastAPI](https://fastapi.tiangolo.com), [React](https://react.dev), and [sqlite-vec](https://github.com/asg017/sqlite-vec)

---

*Forged in the fires of iteration, like Mjolnir in Sindri's forge.* ⚒️
