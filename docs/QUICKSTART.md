# Quick Start Guide

**Get Sindri running in 5 minutes**

---

## Prerequisites

- ✅ Python 3.11 or higher
- ✅ [Ollama](https://ollama.ai) installed and running
- ✅ 8GB+ VRAM (or 4GB for smaller models)

---

## 1. Install Sindri

```bash
# Clone repository
git clone https://github.com/Iormungand21/sindri.git
cd sindri

# Create virtual environment (optional but recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with all dependencies
pip install -e ".[dev,tui]"

# Verify installation
sindri --version
```

---

## 2. Install Ollama Models

Sindri requires at least one model. Start with the essentials:

```bash
# Minimum setup (for testing)
ollama pull qwen2.5-coder:3b       # 3.3GB - Fast executor

# Recommended setup (full functionality)
ollama pull qwen2.5-coder:14b      # 9.0GB - Orchestrator (Brokkr)
ollama pull qwen2.5-coder:7b       # 4.7GB - Reviewer (Mimir)
ollama pull nomic-embed-text       # 274MB - Memory system

# Optional (extended capabilities)
ollama pull deepseek-coder-v2:16b  # 10.5GB - Coder (Huginn)
ollama pull llama3.1:8b            # 4.9GB - Test writer (Skald)
```

**Verify models:**
```bash
ollama list
```

---

## 3. First Command

Test with a simple task:

```bash
sindri run "Create a hello.py file that prints 'Hello, Sindri!'"
```

**Expected output:**
```
✓ Task created: Create a hello.py file...
✓ Agent: brokkr loaded (qwen2.5-coder:14b)
  Iteration 1/15: Planning...
  Iteration 2/15: Creating file...
✓ Task complete!

File created: hello.py
```

**Verify:**
```bash
cat hello.py
python hello.py  # Should print: Hello, Sindri!
```

---

## 4. Try the TUI

Launch the interactive Terminal UI:

```bash
sindri tui
```

**TUI Controls:**
- Type your task in the bottom input field
- Press `Enter` to submit
- Press `Ctrl+C` to cancel running task
- Press `q` to quit

**Try these tasks:**
```
Create a calculator.py with add, subtract, multiply, divide functions
Write a README.md for this calculator
Add pytest tests for calculator.py
```

---

## 5. Test Multi-Agent Orchestration

For complex tasks, Sindri automatically delegates to specialist agents:

```bash
sindri tui
```

**Try this task:**
```
Build a simple REST API with FastAPI that has:
- GET /health endpoint
- POST /items endpoint
- Unit tests
```

Watch in the TUI as:
1. **Brokkr** (orchestrator) plans the task
2. **Huginn** (coder) implements the API
3. **Skald** (test writer) creates tests
4. Results bubble back up the chain

---

## 6. Configuration (Optional)

Create `sindri.toml` in your project directory:

```toml
[general]
data_dir = "~/.sindri"
ollama_host = "http://localhost:11434"

[hardware]
total_vram_gb = 16.0      # Adjust to your GPU
reserve_vram_gb = 2.0     # VRAM to reserve for system

[memory]
episodic_limit = 5        # Past task summaries to retrieve
semantic_limit = 10       # Codebase chunks to retrieve
max_context_tokens = 32768

[tui]
theme = "dark"
refresh_rate_ms = 100
```

---

## 7. Enable Memory System

For better context on large projects:

```bash
# Memory is currently disabled by default
# To enable, add flag (feature in development):
sindri orchestrate "Your task" --memory

# Or wait for next release where it's enabled by default
```

---

## Common Commands

```bash
# Simple task with default agent
sindri run "Create a config.py file"

# Launch interactive TUI
sindri tui

# Specify model
sindri run "Write function" --model qwen2.5-coder:7b

# Set max iterations
sindri run "Complex task" --max-iter 100

# Check system health (planned)
sindri doctor

# List available agents (planned)
sindri agents

# View past sessions (planned)
sindri sessions
```

---

## Troubleshooting

### Ollama not running
```bash
# Check status
systemctl status ollama  # Linux
pgrep ollama            # Any OS

# Start Ollama
systemctl start ollama   # Linux
ollama serve            # Manual start
```

### Model not found
```bash
ollama pull qwen2.5-coder:14b
ollama list  # Verify
```

### Out of VRAM
```bash
# Use smaller models
sindri run "Task" --model qwen2.5-coder:3b

# Or adjust reserve in config
[hardware]
reserve_vram_gb = 1.0  # Reduce reserve
```

### Task not completing
- Check if agent hit max iterations (increase with `--max-iter`)
- Try with different agent/model
- Check TUI for error messages

---

## Next Steps

### Learn More
- **[AGENTS.md](AGENTS.md)** - Understanding agents and when to use them
- **[CONFIGURATION.md](CONFIGURATION.md)** - Full configuration reference
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues
- **[README.md](../README.md)** - Full project documentation

### Try Advanced Features
- **Multi-file projects** - Let Brokkr orchestrate complex refactoring
- **Memory system** - Index your codebase for better context
- **Custom agents** - Create specialized agents for your domain

### Get Help
- 📖 Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- 🐛 Report issues on [GitHub](https://github.com/Iormungand21/sindri/issues)
- 💬 Read [STATUS.md](../STATUS.md) for current limitations

---

## Example Workflows

### Code Generation
```bash
sindri tui
# Task: Create a user authentication module with bcrypt password hashing
```

### Refactoring
```bash
sindri tui
# Task: Refactor database.py to use async SQLAlchemy instead of sync
```

### Testing
```bash
sindri tui
# Task: Write comprehensive pytest tests for the auth module with fixtures
```

### SQL Work
```bash
sindri run "Create Alembic migration to add email verification to users table"
```

---

**Total setup time: ~5 minutes** ✨

You're ready to use Sindri! Start with simple tasks and work up to complex multi-agent orchestration.
