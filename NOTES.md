# Review Notes - Multi-Project Workspace Index

Status: **RESOLVED**

## Original Findings (ChatGPT Review)

1. **Active/pinned project context never injected** - `GlobalMemoryStore.get_active_project_context()` and `IndexerConfig.include_active_in_context` were unused.

2. **Background indexer standalone** - Not started anywhere (no orchestrator/TUI/web integration). `IndexerConfig.auto_start` and `schedule_interval_minutes` were unused.

3. **Pattern matching used absolute paths** - `include_patterns` / `exclude_patterns` were matched against absolute paths instead of project-relative paths.

## Fixes Applied

### 1. Active Project Context Injection
**Files modified:** `sindri/memory/system.py`

- Extended `MuninnMemory.__init__()` to accept optional `GlobalMemoryStore` parameter
- Added `enable_active_projects` and `active_project_tokens` to `MemoryConfig`
- Modified `build_context()` to include cross-project context as the first tier:
  - Allocates 9% of token budget to cross-project context
  - Calls `global_memory.get_active_project_context()` when enabled
  - Excludes current project from cross-project search

### 2. BackgroundIndexer Integration with Orchestrator
**Files modified:** `sindri/core/orchestrator.py`

- Added imports for `GlobalMemoryStore`, `BackgroundIndexer`, `ProjectRegistry`, `SindriConfig`
- Created `GlobalMemoryStore` and `ProjectRegistry` in orchestrator init
- Passed `global_memory` to `MuninnMemory` for context injection
- Created `BackgroundIndexer` when `config.memory.indexer.enabled` is True
- Added `start_background_indexer()` and `stop_background_indexer()` methods
- Modified `run()` to auto-start indexer when `config.memory.indexer.auto_start` is True
- Updated `configure_for_model()` to propagate indexer settings to memory config

### 3. Pattern Matching with Relative Paths
**Files modified:** `sindri/memory/global_memory.py`

- Updated `_should_include_file()` signature to accept `rel_path` parameter
- Patterns now matched against project-relative paths (e.g., `src/*`, `*.min.js`)
- Updated call site in `index_project_incremental()` to pass `rel_path`

## Tests Verified

```bash
.venv/bin/pytest tests/test_workspace_index.py -v
# Result: 47 passed

.venv/bin/pytest tests/ -v --tb=short -q
# Result: 3994 passed, 13 skipped, 12 warnings
```

## Summary

All three issues from the ChatGPT review have been addressed:
- Cross-project context is now injected into agent prompts via `MuninnMemory.build_context()`
- BackgroundIndexer lifecycle is wired to the Orchestrator with auto_start support
- Include/exclude patterns now work correctly with project-relative paths
