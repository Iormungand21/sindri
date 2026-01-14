# Troubleshooting Sindri

Common issues and solutions for Sindri.

## Installation Issues

### Problem: `pip install -e .` fails

**Symptoms:**
```
ERROR: File "setup.py" not found
```

**Solution:**
Ensure you're using Python 3.11+ with a modern pip:
```bash
python --version  # Should be 3.11+
pip install --upgrade pip
pip install -e ".[dev,tui]"
```

---

### Problem: Import errors after installation

**Symptoms:**
```python
ModuleNotFoundError: No module named 'sindri'
```

**Solution:**
1. Verify installation:
```bash
pip show sindri
```

2. If not found, reinstall:
```bash
pip install -e .
```

3. Check you're in the right virtual environment:
```bash
which python
```

---

## Ollama Connection Issues

### Problem: Cannot connect to Ollama

**Symptoms:**
```
ConnectionError: Cannot connect to http://localhost:11434
```

**Solutions:**

1. **Check if Ollama is running:**
```bash
systemctl status ollama  # Linux with systemd
# Or
pgrep ollama
```

2. **Start Ollama:**
```bash
systemctl start ollama  # Linux with systemd
# Or
ollama serve  # Manual start
```

3. **Check Ollama is responding:**
```bash
ollama list
curl http://localhost:11434/api/tags
```

4. **If using custom host, set in config:**
```toml
# sindri.toml
[general]
ollama_host = "http://192.168.1.100:11434"
```

---

### Problem: Model not found

**Symptoms:**
```
Error: model 'qwen2.5-coder:14b' not found
```

**Solution:**
Pull the model first:
```bash
ollama pull qwen2.5-coder:14b
ollama list  # Verify it's there
```

---

## VRAM Issues

### Problem: Out of VRAM

**Symptoms:**
```
Error: Failed to load model - insufficient VRAM
```

**Solutions:**

1. **Check current VRAM usage:**
```bash
# For NVIDIA:
nvidia-smi

# For AMD:
rocm-smi
```

2. **Use smaller models:**
```bash
# Instead of:
sindri orchestrate "task" --vram-gb 16

# Try:
sindri run "task" --model qwen2.5-coder:7b
```

3. **Increase reserve:**
```toml
# sindri.toml
[hardware]
total_vram_gb = 16.0
reserve_vram_gb = 3.0  # More headroom
```

4. **Use quantized models:**
```bash
# Smaller quantization = less VRAM
ollama pull qwen2.5-coder:14b-instruct-q4_K_M  # ~8GB
# vs
ollama pull qwen2.5-coder:14b-instruct-q8_0   # ~15GB
```

---

### Problem: Models not unloading

**Symptoms:**
VRAM stays full even after task completion

**Solution:**
1. Check Ollama's keep-alive setting:
```bash
# Set models to unload after 5 minutes
export OLLAMA_KEEP_ALIVE=5m
systemctl restart ollama
```

2. Force model unload:
```bash
# Restart Ollama
systemctl restart ollama
```

---

## Agent Loop Issues

### Problem: Agent stuck in loop

**Symptoms:**
Agent repeats the same action over and over

**Solution:**
1. **Interrupt with Ctrl+C**, then check the checkpoint:
```bash
sindri recover
sindri recover --session-id <id>
```

2. **Adjust stuck detection:**
```toml
# sindri.toml
[execution]
stuck_threshold = 2  # Detect sooner (default: 3)
```

3. **Review agent prompt** - May need clearer completion criteria

---

### Problem: Max iterations reached

**Symptoms:**
```
Failed: max_iterations_reached after 50 iterations
```

**Solutions:**

1. **Increase iterations:**
```bash
sindri run "complex task" --max-iter 100
```

2. **Or in config:**
```toml
[execution]
default_max_iterations = 100
```

3. **Break down the task:**
```bash
# Instead of:
sindri run "Build complete application"

# Try:
sindri orchestrate "Build complete application"
# Brokkr will break it down into smaller tasks
```

---

## Memory System Issues

### Problem: Codebase indexing fails

**Symptoms:**
```
Error indexing project: <error message>
```

**Solutions:**

1. **Check file permissions:**
```bash
ls -la | grep -v "^d"  # Check file permissions
```

2. **Exclude large files:**
```python
# In sindri/memory/semantic.py, add to EXCLUDE_PATTERNS:
EXCLUDE_PATTERNS = [
    "*.pyc", "__pycache__", ".git",
    "node_modules", "*.min.js",  # Add more
]
```

3. **Limit indexing scope:**
```bash
# Only index specific directories
cd specific/directory
sindri orchestrate "task"
```

---

### Problem: Out of memory during embedding

**Symptoms:**
```
MemoryError: Cannot allocate memory for embeddings
```

**Solutions:**

1. **Process in smaller batches:**
```toml
[memory]
semantic_limit = 5  # Reduce from 10
```

2. **Disable memory if not needed:**
```bash
sindri tui --no-memory
```

---

## TUI Issues

### Problem: TUI won't launch

**Symptoms:**
```
ModuleNotFoundError: No module named 'textual'
```

**Solution:**
Install TUI dependencies:
```bash
pip install -e ".[tui]"
```

---

### Problem: TUI display corruption

**Symptoms:**
Garbled text, incorrect colors, broken layout

**Solutions:**

1. **Check terminal compatibility:**
```bash
echo $TERM  # Should be xterm-256color or similar
```

2. **Set correct TERM:**
```bash
export TERM=xterm-256color
```

3. **Try different terminal:**
- Use modern terminal: Alacritty, Kitty, WezTerm
- Avoid: Default GNOME Terminal (old versions)

4. **Disable colors if needed:**
```bash
NO_COLOR=1 sindri tui
```

---

## Crash Recovery Issues

### Problem: Cannot recover session

**Symptoms:**
```
No checkpoint found for session abc123
```

**Solutions:**

1. **List all recoverable sessions:**
```bash
sindri recover
```

2. **Check checkpoint directory:**
```bash
ls ~/.sindri/state/*.checkpoint.json
```

3. **Manually inspect checkpoint:**
```bash
cat ~/.sindri/state/abc123.checkpoint.json | jq .
```

4. **If corrupted, delete and restart:**
```bash
rm ~/.sindri/state/abc123.checkpoint.json
```

---

### Problem: Checkpoints filling disk

**Symptoms:**
`~/.sindri/state/` directory is very large

**Solution:**
Clean old checkpoints:
```python
from sindri.core.recovery import RecoveryManager
from sindri.persistence.database import Database

recovery = RecoveryManager(Database("~/.sindri/sindri.db"), "~/.sindri/state")
recovery.cleanup_old_checkpoints(keep=5)
```

---

## Performance Issues

### Problem: Slow response times

**Solutions:**

1. **Check model size:**
```bash
ollama list
# Use smaller models for faster responses
```

2. **Reduce context:**
```toml
[memory]
max_context_tokens = 16384  # Reduce from 32768
```

3. **Monitor CPU/GPU:**
```bash
htop  # CPU usage
nvidia-smi -l 1  # GPU usage (NVIDIA)
```

---

### Problem: High memory usage

**Solution:**
1. **Limit episodic memory:**
```toml
[memory]
episodic_limit = 3  # Reduce from 5
```

2. **Restart Sindri periodically:**
Long-running sessions accumulate memory

---

## Database Issues

### Problem: Database locked

**Symptoms:**
```
sqlite3.OperationalError: database is locked
```

**Solutions:**

1. **Check for multiple Sindri processes:**
```bash
ps aux | grep sindri
# Kill duplicates if needed
```

2. **Delete lock file:**
```bash
rm ~/.sindri/sindri.db-journal
```

3. **Rebuild database:**
```bash
mv ~/.sindri/sindri.db ~/.sindri/sindri.db.backup
# Sindri will create new database on next run
```

---

### Problem: Corrupted database

**Symptoms:**
```
sqlite3.DatabaseError: database disk image is malformed
```

**Solution:**
```bash
# Backup
cp ~/.sindri/sindri.db ~/.sindri/sindri.db.corrupt

# Try recovery
sqlite3 ~/.sindri/sindri.db "PRAGMA integrity_check;"

# If failed, recreate:
rm ~/.sindri/sindri.db
# Sindri recreates on next run
```

---

## Configuration Issues

### Problem: Config not being loaded

**Symptoms:**
Sindri uses defaults despite having `sindri.toml`

**Solutions:**

1. **Check config file location:**
```bash
ls -la sindri.toml        # Project-specific
ls -la ~/.sindri/config.toml  # User default
```

2. **Validate TOML syntax:**
```bash
python -c "import toml; toml.load('sindri.toml')"
```

3. **Check for syntax errors:**
```bash
# Common issues:
# - Missing quotes
# - Incorrect section names
# - Wrong types (string instead of number)
```

---

### Problem: Validation warnings

**Symptoms:**
```bash
sindri doctor
# ⚠ Total agent VRAM exceeds available
```

**Solution:**
```toml
# Reduce VRAM requirements or increase total
[hardware]
total_vram_gb = 24.0  # Increase if you have more VRAM
```

---

## Getting More Help

### Enable Debug Logging

```python
# In your code or config
import logging
logging.basicConfig(level=logging.DEBUG)

# Or environment variable
export SINDRI_LOG_LEVEL=DEBUG
```

### Run Doctor Check

```bash
sindri doctor
# Checks:
# - Ollama connection
# - Available models
# - Config validity
# - Python version
# - Dependencies
```

### Check Logs

```bash
# If configured with log file:
tail -f ~/.sindri/sindri.log

# Or journalctl for systemd:
journalctl -u ollama -f
```

### Collect Debug Info

```bash
# Create a debug report
cat > debug-info.txt << EOF
Sindri Version: $(sindri --version)
Python Version: $(python --version)
Ollama Models: $(ollama list)
VRAM: $(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null || echo "N/A")
Config: $(cat sindri.toml 2>/dev/null || echo "No config")
EOF
```

## Common Error Messages

| Error | Likely Cause | Fix |
|-------|-------------|-----|
| `ConnectionRefusedError` | Ollama not running | `systemctl start ollama` |
| `ModelNotFoundError` | Model not pulled | `ollama pull <model>` |
| `OutOfMemoryError` | Insufficient VRAM | Use smaller model |
| `DatabaseLocked` | Multiple processes | Kill duplicate processes |
| `PermissionError` | Cannot write to data dir | Check permissions |
| `ModuleNotFoundError` | Missing dependency | `pip install -e ".[dev,tui]"` |

## Still Stuck?

1. Check [GitHub Issues](https://github.com/yourusername/sindri/issues)
2. Run `sindri doctor` and share output
3. Open a new issue with:
   - Error message
   - Steps to reproduce
   - Output of `sindri doctor`
   - Debug info (see above)

---

*Most issues are resolved by running `sindri doctor` and following the recommendations.*
