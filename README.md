# Sindri 🔨

**Local-first LLM orchestration for code generation**

Forge code with local LLMs via Ollama, using a hierarchical multi-agent system inspired by Norse mythology. Like the legendary dwarf smith who forged Mjolnir, Sindri crafts your code through iterative refinement.

## Features

- 🏛️ **Hierarchical Multi-Agent System** - Specialized agents delegate tasks to experts
- 🧠 **Three-Tier Memory System** - Working, episodic, and semantic memory with codebase indexing
- 🎨 **Rich Terminal UI** - Monitor agent activity, task trees, and VRAM usage in real-time
- 💾 **Crash Recovery** - Automatic checkpointing and session restoration
- 🔄 **Automatic Retry** - Exponential backoff for transient failures
- 📊 **VRAM Management** - Intelligent model loading with LRU eviction for AMD/NVIDIA GPUs
- 🗄️ **Vector Search** - Semantic codebase search with sqlite-vec and local embeddings

## Installation

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) installed and running
- 8GB+ VRAM recommended (works with less for smaller models)

### Install Sindri

```bash
# Clone repository
git clone https://github.com/yourusername/sindri.git
cd sindri

# Install with dev dependencies
pip install -e ".[dev,tui]"

# Verify installation
sindri --version
sindri doctor
```

### Pull Recommended Models

```bash
# Core models (total ~23GB)
ollama pull qwen2.5-coder:14b       # Orchestrator (Brokkr)
ollama pull deepseek-coder-v2:16b   # Coder (Huginn)
ollama pull qwen2.5-coder:7b        # Reviewer (Mimir)
ollama pull qwen2.5-coder:3b        # Executor (Ratatoskr)

# Memory system
ollama pull nomic-embed-text        # Embeddings
```

## Quick Start

### Basic Usage

```bash
# Simple task
sindri run "Create a hello.py file that prints hello world"

# With specific model
sindri run "Write a binary search function" --model qwen2.5-coder:14b

# Hierarchical orchestration (uses all agents)
sindri orchestrate "Build a REST API for a todo list with tests"
```

### Interactive TUI

```bash
# Launch TUI
sindri tui

# TUI with initial task
sindri tui "Refactor the authentication module"
```

### Crash Recovery

```bash
# List recoverable sessions
sindri recover

# Recover specific session
sindri recover --session-id abc123

# Resume execution
sindri resume abc123
```

## Agent Hierarchy

Sindri uses a Norse mythology-themed agent hierarchy:

| Agent | Role | Model | Delegates To |
|-------|------|-------|--------------|
| **Brokkr** | Master Orchestrator | qwen2.5:14b | All agents |
| **Huginn** | Code Implementation | deepseek-coder:16b | Ratatoskr |
| **Mimir** | Code Review | qwen2.5:7b | - |
| **Ratatoskr** | Fast Executor | qwen2.5:3b | - |
| **Skald** | Test Writer | llama3.1:8b | - |
| **Fenrir** | SQL Specialist | qwen2.5-coder:7b | - |
| **Odin** | Deep Reasoning | deepseek-r1:8b | - |

### Delegation Flow

```
User Task
    ↓
┌───────────┐
│  Brokkr   │ ─ Plans and delegates
└─────┬─────┘
      │
      ├──→ Huginn ──→ Writes implementation ──→ Delegates to Ratatoskr for file ops
      │
      ├──→ Mimir ───→ Reviews code quality
      │
      ├──→ Skald ───→ Generates tests
      │
      └──→ Fenrir ──→ Handles SQL/database tasks
```

## Memory System (Muninn)

Sindri uses a three-tier memory architecture:

1. **Working Memory (60%)** - Recent conversation and immediate context
2. **Episodic Memory (20%)** - Summaries of past tasks and sessions
3. **Semantic Memory (20%)** - Codebase embeddings for relevant file retrieval

### How Memory Works

```bash
# First run on a project - indexes codebase
sindri orchestrate "Add user authentication"
# → Indexes project files, creates embeddings

# Subsequent runs use memory
sindri orchestrate "Add password reset"
# → Retrieves relevant auth files from semantic memory
# → Recalls past auth implementation from episodic memory
```

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

See [CONFIGURATION.md](docs/CONFIGURATION.md) for full options.

## CLI Reference

### Commands

| Command | Description |
|---------|-------------|
| `sindri run <task>` | Execute task with single agent |
| `sindri orchestrate <task>` | Execute with hierarchical agents |
| `sindri tui [task]` | Launch interactive terminal UI |
| `sindri agents` | List all available agents |
| `sindri sessions` | Show recent sessions |
| `sindri recover` | List/recover interrupted sessions |
| `sindri resume <id>` | Resume a session |
| `sindri doctor` | Verify installation and config |

### Options

| Option | Description |
|--------|-------------|
| `--model, -m` | Specify Ollama model |
| `--max-iter` | Maximum iterations (default: 50) |
| `--vram-gb` | Total VRAM available (default: 16.0) |
| `--no-memory` | Disable memory system |

## Examples

### Code Generation

```bash
# Generate a module
sindri run "Create a user authentication module with JWT"

# With orchestration (better for complex tasks)
sindri orchestrate "Create a REST API with FastAPI for a blog"
```

### Refactoring

```bash
sindri orchestrate "Refactor database.py to use async SQLAlchemy"
```

### Testing

```bash
sindri run "Write pytest tests for the auth module" --model llama3.1:8b
```

### SQL Tasks

```bash
sindri run "Create a migration to add user_roles table"
```

## Architecture

```
sindri/
├── cli.py              # Click CLI
├── config.py           # Configuration with validation
├── core/
│   ├── loop.py         # Ralph-style iteration loop
│   ├── scheduler.py    # Priority queue with dependencies
│   ├── delegation.py   # Parent→child task management
│   ├── recovery.py     # Crash recovery
│   ├── retry.py        # Retry logic with backoff
│   └── events.py       # Event bus for TUI
├── agents/
│   ├── definitions.py  # AgentDefinition dataclass
│   ├── registry.py     # All agent configs
│   └── prompts.py      # System prompts
├── llm/
│   ├── client.py       # Async Ollama wrapper
│   ├── manager.py      # VRAM-aware model loading
│   └── tool_parser.py  # Text-based tool call parsing
├── tools/
│   ├── filesystem.py   # File operations
│   └── shell.py        # Shell execution
├── memory/
│   ├── system.py       # MuninnMemory orchestrator
│   ├── episodic.py     # Session history
│   ├── semantic.py     # Codebase embeddings
│   └── embedder.py     # Local embedding client
├── persistence/
│   ├── database.py     # SQLite setup
│   ├── vectors.py      # sqlite-vec integration
│   └── state.py        # Session state
└── tui/
    ├── app.py          # Textual application
    └── widgets/        # Custom widgets
```

## How It Works

### The Ralph Loop

Sindri's core is based on the "Ralph loop" pattern:

```python
for iteration in range(max_iterations):
    response = await llm.chat(messages)

    if "<sindri:complete/>" in response:
        return Success

    tool_results = await execute_tools(response)
    messages.append(response, tool_results)
```

### Delegation as Nested Loops

When an agent delegates, it spawns a child loop:

```python
if tool_call.name == "delegate":
    child_task = create_child(target_agent, task_description)
    child_result = await run_child_loop(child_task)
    return child_result  # Parent resumes with child's result
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev,tui]"

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest --cov=sindri --cov-report=term-missing

# Type checking
mypy sindri/

# Linting
ruff check sindri/
```

## Troubleshooting

See [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common issues.

### Quick Fixes

**Ollama not responding:**
```bash
systemctl status ollama  # Check if running
ollama list              # Verify models
```

**Out of VRAM:**
```bash
# Use smaller models or reduce reserve
sindri orchestrate "task" --vram-gb 12.0
```

**Recover from crash:**
```bash
sindri recover           # List checkpoints
sindri resume <id>       # Continue execution
```

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE)

## Acknowledgments

- Inspired by Ralph Loop pattern from [Ralph](https://github.com/anthropics/ralph)
- Norse mythology for agent naming
- Built with [Ollama](https://ollama.ai), [Textual](https://textual.textualize.io), and [sqlite-vec](https://github.com/asg017/sqlite-vec)

---

*Forged in the fires of iteration, like Mjolnir in Sindri's forge.* ⚒️
