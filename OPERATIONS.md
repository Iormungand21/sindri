# Sindri Operations Guide

Fast reference for running and debugging Sindri.

---

## Setup

```bash
cd /home/ryan/projects/sindri
source .venv/bin/activate  # If needed

# Verify Ollama is running
systemctl status ollama

# Check models
ollama list
```

---

## Run Sindri

### CLI Mode (Simple)
```bash
.venv/bin/sindri run "Create hello.txt with 'test'"
```

### TUI Mode (Interactive)
```bash
.venv/bin/sindri tui

# In TUI:
# - Type task description
# - Press Enter
# - Watch output on right
# - Ctrl+C to exit
```

---

## Testing

### Run All Tests
```bash
.venv/bin/pytest tests/ -v
```

### Specific Test Suites
```bash
.venv/bin/pytest tests/test_delegation.py -v  # Delegation
.venv/bin/pytest tests/test_tools.py -v       # Tools
.venv/bin/pytest tests/test_scheduler.py -v   # Scheduler
```

### Custom Test Script
```bash
.venv/bin/python test_task_completion.py
```

---

## Debugging

### View TUI Logs
```bash
cat /tmp/tui_test.log | tail -100
```

### View Session Database
```bash
sqlite3 ~/.sindri/sindri.db

# Useful queries:
SELECT * FROM sessions ORDER BY created_at DESC LIMIT 5;
SELECT * FROM turns WHERE session_id = '<session-id>';
```

### Enable Debug Logging
Edit `sindri/core/hierarchical.py` or any file with structlog:
```python
# Change from INFO to DEBUG
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG)
)
```

### Check Ollama
```bash
# API test
curl http://localhost:11434/api/tags

# Run model directly
ollama run qwen2.5-coder:14b "Say hello"

# Check process
ps aux | grep ollama
```

---

## Common Issues

### "Ollama not responding"
```bash
sudo systemctl restart ollama
# Wait 10 seconds
ollama list
```

### "Model not found"
```bash
ollama pull qwen2.5-coder:14b
ollama pull qwen2.5:3b-instruct-q8_0
```

### "Task hanging/not completing"
- Check if Ollama has too many models loaded
- Restart Ollama: `sudo systemctl restart ollama`
- Check logs: `journalctl -u ollama -f`

### "TUI not showing output"
- Verify EventBus wiring in `sindri/cli.py`
- Check event emissions in `sindri/core/hierarchical.py`
- Look at `/tmp/tui_test.log` for errors

### "Import errors"
```bash
pip install -e ".[dev,tui]"
```

---

## File Locations

| What | Path |
|------|------|
| Project | `/home/ryan/projects/sindri` |
| Main CLI | `sindri/cli.py` |
| Orchestrator | `sindri/core/orchestrator.py` |
| Agent Loop | `sindri/core/hierarchical.py` |
| Delegation | `sindri/core/delegation.py` |
| Agent Config | `sindri/agents/registry.py` |
| Agent Prompts | `sindri/agents/prompts.py` |
| Tools | `sindri/tools/` |
| TUI | `sindri/tui/app.py` |
| Sessions DB | `~/.sindri/sindri.db` |
| Memory DB | `~/.sindri/memory.db` |
| TUI Log | `/tmp/tui_test.log` |

---

## Agent Quick Reference

| Agent | Model | Role | Can Delegate To |
|-------|-------|------|-----------------|
| **Brokkr** | qwen2.5-coder:14b | Orchestrator | All agents |
| **Huginn** | qwen2.5-coder:7b | Coder | Ratatoskr, Skald |
| **Mimir** | llama3.1:8b | Reviewer | None |
| **Ratatoskr** | qwen2.5:3b | Fast executor | None |
| **Skald** | qwen2.5-coder:7b | Test writer | None |
| **Fenrir** | sqlcoder:7b | SQL specialist | None |
| **Odin** | deepseek-r1:8b | Deep reasoning | Huginn, Skald, Fenrir |

---

## Tools Available

| Tool | Description | Parameters |
|------|-------------|------------|
| `read_file` | Read file contents | `path` |
| `write_file` | Write/create file | `path`, `content` |
| `edit_file` | String replacement | `path`, `old_text`, `new_text` |
| `shell` | Execute shell command | `command` |
| `delegate` | Delegate to agent | `agent`, `task`, `context`, `constraints`, `criteria` |

---

## Quick Edits

### Change Agent Behavior
**File:** `sindri/agents/prompts.py`
```python
BROKKR_PROMPT = """You are Brokkr...
[Edit system prompt here]
"""
```

### Change Agent Model
**File:** `sindri/agents/registry.py`
```python
"brokkr": AgentDefinition(
    model="qwen2.5-coder:14b",  # Change this
    max_iterations=20,           # Or this
    ...
)
```

### Add New Tool
1. Create class in `sindri/tools/your_tool.py`
2. Inherit from `Tool` base class
3. Register in `sindri/tools/registry.py`
4. Add to agent's tools list in `sindri/agents/registry.py`

---

## Typical Workflow

1. **Start TUI:** `.venv/bin/sindri tui`
2. **Enter task:** "Create a function to validate email addresses"
3. **Watch execution:**
   - Brokkr analyzes task
   - Brokkr delegates to Huginn
   - Huginn writes code
   - Huginn delegates to Ratatoskr for file write
   - Ratatoskr writes file
   - Results bubble up
4. **Check output:** File should be created in current directory

---

## Emergency Reset

If everything is broken:

```bash
# Stop Ollama
sudo systemctl stop ollama

# Clear databases
rm -rf ~/.sindri/*.db

# Restart Ollama
sudo systemctl start ollama

# Reinstall Sindri
cd /home/ryan/projects/sindri
pip install -e ".[dev,tui]"

# Test
.venv/bin/sindri run "Create test.txt with 'hello'"
```

---

## Performance Tips

- **Use smaller models for testing:** Change agents to use 3b models
- **Disable memory:** Pass `--no-memory` flag
- **Reduce max iterations:** Lower values in `registry.py`
- **Monitor VRAM:** `watch -n 1 rocm-smi` (if ROCm installed)

---

## Next Steps

After verifying basics work:

1. Test more complex tasks (multi-file operations)
2. Try different agents (Mimir for review, Skald for tests)
3. Enable memory system and test RAG features
4. Improve agent prompts based on observed behavior
5. Add more specialized tools

---

**See STATUS.md for detailed project status and architecture.**
