# Handoff: Sindri Development Session

**Date:** 2026-01-21
**Previous Agent:** Claude Opus 4.5

## Summary

This session focused on implementing the "Reproducible Sessions" feature and then debugging/fixing issues to get Sindri running locally with GPU acceleration.

## Completed Work

### 1. Reproducible Sessions Feature (ROADMAP Item 3)
- **Status:** Implemented and reviewed
- **Commit:** `10bda83 fix: Address code review feedback for Reproducible Sessions`
- Created environment snapshot capture at session start
- Added tool output recording for replay
- CLI commands: `sindri replay info|list|run|compare`
- 44 new tests, all passing

### 2. Bug Fixes During Testing

#### Embedding Chunking Fix
- **File:** `sindri/memory/semantic.py`
- **Issue:** Large files exceeded embedding model's context limit
- **Fix:** Added `MAX_CHUNK_CHARS = 2000` and `MAX_LINE_CHARS = 500` limits
- Long lines are now truncated, chunks split by character count

#### Large Project Indexing Fix
- **File:** `sindri/core/hierarchical.py` (lines ~356-385)
- **Issue:** Indexing 300+ files blocked the web server for minutes
- **Fix:** Added file count check - skips synchronous indexing if >50 files
- Logs: `indexing_skipped_large_project`

#### Model Metadata Client Fix
- **File:** `sindri/replay/snapshot.py`
- **Issue:** `async with` on ollama client closed it for subsequent calls
- **Fix:** Use fresh `httpx.AsyncClient()` for version endpoint

## Context Length Optimization (FIXED)

### Problem (was)
Sindri's prompts were **~83,000 tokens** but Ollama default context is **4,096 tokens**.

### Solution Implemented
Two optimizations were applied:

1. **Removed redundant tool descriptions** from system prompts
   - Tools were included twice: as text in prompt AND as schemas to Ollama
   - Removed text descriptions since Ollama already uses schemas
   - Files modified: `sindri/core/context.py`, `sindri/core/hierarchical.py`

2. **Dynamic context sizing based on model**
   - New `get_context_budget(context_length)` function in `sindri/memory/system.py`
   - Adjusts memory limits based on model's context window:
     - 4K context: minimal memory (512 tokens, 1 episode, 2 semantic chunks)
     - 8K context: reduced memory (512 tokens, 2 episodes, 4 semantic chunks)
     - 16K context: moderate memory (2K tokens, 3 episodes, 6 semantic chunks)
     - 32K+ context: full memory (10-16K tokens, 5 episodes, 10 semantic chunks)
   - `Orchestrator.configure_for_model()` auto-configures on first run
   - `OllamaClient.get_model_info()` fetches context length from Ollama

### Still Recommended
Set `OLLAMA_CONTEXT_LENGTH=32768` in Ollama config for best experience:
```
Environment="OLLAMA_CONTEXT_LENGTH=32768"
```

## Ollama GPU Setup (Completed)

User has AMD Radeon RX 6950 XT (16GB VRAM). Fixed GPU acceleration:

1. **Binary:** Changed from `/usr/local/bin/ollama` (manual install, no ROCm) to `/usr/bin/ollama` (package with ROCm)

2. **Service config** (`/etc/systemd/system/ollama.service.d/override.conf`):
```ini
[Service]
Environment="HSA_OVERRIDE_GFX_VERSION=10.3.0"
Environment="HIP_VISIBLE_DEVICES=0"
Environment="OLLAMA_FLASH_ATTENTION=false"
Environment="OLLAMA_CONTEXT_LENGTH=32768"
```

3. **Verification:** `ollama ps` shows `100% GPU`

## Known Issues

1. **Agent "Ratatoskr" not found** - LLM tried to delegate to non-existent agent. Check `sindri/agents/registry.py` for valid agent names.

2. **Vague tasks fail** - Task "Continue working on the project" caused confusion loops. Need specific, actionable task descriptions.

3. **Empty responses** - LLM sometimes returns empty content, causing stuck detection to trigger.

## Files Modified This Session

| File | Changes |
|------|---------|
| `sindri/memory/semantic.py` | Chunking limits for embeddings |
| `sindri/core/hierarchical.py` | Skip indexing for large projects |
| `sindri/core/loop.py` | Added snapshot capture + tool output recording |
| `sindri/replay/snapshot.py` | Fixed httpx client usage |
| `tests/test_memory.py` | Added chunking tests |
| `REVIEWER.md` | Code review summary |

## Next Steps

1. **Immediate:** User needs to apply the `OLLAMA_CONTEXT_LENGTH=32768` fix
2. **Short-term:** Reduce system prompt size to work with smaller context
3. **Testing:** Try `sindri web --port 8765` with a specific task like "Create hello.py that prints Hello World"

## Test Commands

```bash
# Check GPU is working
ollama ps  # Should show 100% GPU

# Quick inference test
curl -s http://localhost:11434/api/generate -d '{"model": "qwen2.5-coder:7b", "prompt": "Say hi", "stream": false}'

# Run Sindri web
.venv/bin/sindri web --port 8765

# Run Sindri CLI
.venv/bin/sindri run --model qwen2.5-coder:7b "Create /tmp/hello.py that prints Hello World"

# Run tests
.venv/bin/pytest tests/ -v --tb=short -q
```

## Reference Docs

- `CLAUDE.md` - Project context and conventions
- `ROADMAP.md` - Feature roadmap
- `STATUS.md` - Current project status
- `REVIEWER.md` - Code review summary for Reproducible Sessions
