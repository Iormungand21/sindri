# Code Review Summary: Context Length Optimization

**Feature:** Dynamic Context Sizing to Prevent Prompt Overflow
**Date:** 2026-01-21
**Author:** Junior Developer (Claude Code)
**Reviewer:** Senior Team Member
**Commit:** `139930a`

## Problem Statement

Sindri's prompts were causing context overflow with local LLMs:
- Ollama's default context is 4,096 tokens
- Sindri prompts could reach ~20,000+ tokens due to:
  - System prompts (1-3K tokens)
  - Tool descriptions duplicated in prompt text (~1,200 tokens)
  - Tool schemas passed to Ollama (~2K tokens)
  - Memory context (up to 16K tokens by default)
  - Conversation history (grows with iterations)

This caused the warning: `truncating input prompt limit=4096 prompt=83369`

## Solution Overview

Two optimizations were implemented:

### 1. Remove Redundant Tool Descriptions

Tool descriptions were included twice:
- As text in the system prompt: `"- tool_name: description"`
- As full schemas passed to Ollama's `tools=` parameter

Since Ollama already uses the schemas for tool calling, the text descriptions were redundant. Removing them saves ~1,200 tokens per request.

### 2. Dynamic Context Sizing Based on Model

A new system that queries the model's context window and adjusts memory budgets accordingly:

| Context Window | Max Memory | Episodic | Semantic | Learning | Analysis |
|---------------|------------|----------|----------|----------|----------|
| ≤4K | 512 | 1 | 2 | No | No |
| ≤8K | 512 | 2 | 4 | Yes | No |
| ≤16K | ~2K | 3 | 6 | Yes | Yes |
| 32K+ | 10-16K | 5 | 10 | Yes | Yes |

## Files Modified

| File | Lines Changed | Changes |
|------|---------------|---------|
| `sindri/core/context.py` | -11/+8 | Removed tool descriptions from `_build_system_prompt()` |
| `sindri/core/hierarchical.py` | -20/+14 | Removed tool descriptions from `_build_messages()` and `_build_system_message()` |
| `sindri/core/orchestrator.py` | +60 | Added `configure_for_model()` method, auto-configuration in `run()` |
| `sindri/llm/client.py` | +72 | Added `get_model_info()` method to query Ollama for context length |
| `sindri/memory/system.py` | +73 | Added `get_context_budget()` function |
| `HANDOFF.md` | +128 | Documentation of all session work |

## Key Code Changes

### sindri/core/context.py

**Before:**
```python
def _build_system_prompt(self, task: str, tools: list[dict]) -> str:
    tool_descriptions = "\n".join([
        f"- {tool['function']['name']}: {tool['function']['description']}"
        for tool in tools
    ])
    return f"""...Available tools:\n{tool_descriptions}..."""
```

**After:**
```python
def _build_system_prompt(self, task: str, tools: list[dict]) -> str:
    """Note: Tool schemas are passed separately to the LLM via the tools= parameter,
    so we don't include tool descriptions in the prompt text to save tokens."""
    _ = tools  # Kept for API compatibility
    return f"""..."""  # No tool descriptions
```

### sindri/llm/client.py - New Method

```python
async def get_model_info(self, model: str) -> dict:
    """Get model information including context length."""
    response = await self._async_client.show(model)
    # Extract context length from model parameters
    # Falls back to family-based defaults if not found
    return {
        "name": model,
        "context_length": context_length,  # e.g., 32768 for qwen2.5
        "family": details.get("family"),
        ...
    }
```

### sindri/memory/system.py - New Function

```python
def get_context_budget(model_context_length: int) -> MemoryConfig:
    """Create a MemoryConfig sized appropriately for the model's context window.

    Reserves ~50% of context for conversation history growth.
    Fixed overhead: ~6K tokens (system prompt + tools + task)
    """
    if model_context_length <= 4096:
        return MemoryConfig(
            max_context_tokens=512,
            episodic_limit=1,
            semantic_limit=2,
            enable_learning=False,
            enable_codebase_analysis=False,
        )
    # ... more tiers for 8K, 16K, 32K+
```

### sindri/core/orchestrator.py - New Method

```python
async def configure_for_model(self, model: str) -> None:
    """Configure memory system based on model's context length."""
    model_info = await self.client.get_model_info(model)
    context_length = model_info.get("context_length", 4096)
    memory_config = get_context_budget(context_length)
    self.memory = MuninnMemory(self._memory_db_path, memory_config)
    self.loop.memory = self.memory
```

Auto-called in `run()`:
```python
async def run(self, user_request: str, parallel: bool = True) -> dict:
    # Auto-configure memory for the default model's context size
    from sindri.agents.registry import AGENTS
    default_model = AGENTS.get("brokkr", {})
    if hasattr(default_model, "model"):
        await self.configure_for_model(default_model.model)
    ...
```

## Test Results

- All 3,871 tests pass
- Model info retrieval verified working:
  - `qwen2.5-coder:7b` → 32,768 context
  - `qwen2.5-coder:14b` → 32,768 context
  - `llama3.1:8b` → 131,072 context

## Verification Commands

```bash
# Run all tests
.venv/bin/pytest tests/ -v --tb=short -q

# Test memory system specifically
.venv/bin/pytest tests/test_memory.py -v

# Verify model info retrieval
.venv/bin/python -c "
import asyncio
from sindri.llm.client import OllamaClient
async def test():
    client = OllamaClient()
    info = await client.get_model_info('qwen2.5-coder:7b')
    print(f'Context length: {info[\"context_length\"]}')
asyncio.run(test())
"

# Test context budget function
.venv/bin/python -c "
from sindri.memory.system import get_context_budget
for ctx in [4096, 8192, 16384, 32768]:
    cfg = get_context_budget(ctx)
    print(f'{ctx}: max={cfg.max_context_tokens}, ep={cfg.episodic_limit}, sem={cfg.semantic_limit}')
"
```

## Design Decisions

1. **Removed tool text, kept schemas** - Ollama's function calling works via the `tools=` parameter, not by reading text from the prompt. Removing duplicate text is safe.

2. **Conservative context allocation** - Reserved 50% of context for conversation growth, plus 6K fixed overhead. This prevents overflow as conversations extend.

3. **Tier-based configuration** - Rather than linear scaling, used discrete tiers that make sense for model capabilities. Small models get minimal memory; large models get full features.

4. **Auto-configuration** - `configure_for_model()` is called automatically on first `run()`, so existing code works without changes.

5. **Graceful fallback** - If model info query fails, defaults to 4K context (most conservative). Errors are logged but don't break execution.

## Potential Concerns for Review

1. **API compatibility** - The `tools` parameter is still accepted in `_build_system_prompt()` and `_build_messages()` but ignored. This maintains backwards compatibility but could be confusing.

2. **Memory reinitialization** - `configure_for_model()` creates a new `MuninnMemory` instance. Any cached data in the old instance is lost. This is acceptable since it's called before any tasks run.

3. **Model family detection** - If Ollama doesn't return context length, we fall back to model family heuristics (qwen=32K, llama=8K, etc.). These may not always be accurate for custom models.

4. **Single configuration** - Memory is configured once for the default model (brokkr). If child agents use models with different context lengths, they still use the parent's memory config. This is a limitation but simplifies the implementation.

## Questions for Reviewer

1. Should we add a CLI flag to override context budget (e.g., `--context-budget small|medium|large`)?

2. Should we warn users when operating with minimal memory (≤4K context)?

3. Is the 50% conversation reserve appropriate, or should it be configurable?

---

*Ready for review. All tests pass.*
