# Code Review Summary: Reproducible Sessions Feature

**Feature:** ROADMAP.md Item 3 - Reproducible Sessions
**Date:** 2026-01-21
**Author:** Junior Developer (Claude Code)
**Reviewer:** ChatGPT (Senior Team Member)

## Summary

Implemented the Reproducible Sessions feature, which enables users to capture complete session execution context, replay sessions for debugging and comparison, and execute tool-only deterministic replays.

## Requirements Addressed

From ROADMAP.md Item 3:
1. **Save model versions, tool params, and environment snapshot** - Environment snapshots captured at session creation including Sindri version, Python version, Ollama version, model metadata (digest, quantization, family), and inference parameters
2. **`sindri replay <session>` to re-run or diff outputs** - Full CLI command group with `info`, `list`, `run`, and `compare` subcommands
3. **Deterministic execution mode for tool-only flows** - Tool-only replay mode uses recorded outputs for deterministic execution

## Files Created (6 new files)

| File | Lines | Purpose |
|------|-------|---------|
| `sindri/persistence/snapshots.py` | ~450 | SnapshotStore and ToolOutputStore classes for persistence; ModelMetadata, InferenceParams, EnvironmentSnapshot dataclasses |
| `sindri/replay/__init__.py` | ~20 | Module exports |
| `sindri/replay/snapshot.py` | ~160 | SnapshotCapture class for capturing environment at session creation |
| `sindri/replay/engine.py` | ~250 | ReplayEngine class with TOOL_ONLY and FULL replay modes; RecordedToolExecutor |
| `sindri/replay/comparator.py` | ~280 | SessionComparator class for comparing sessions; TurnDiff, EnvironmentDiff, SessionComparison dataclasses |
| `tests/test_replay.py` | ~650 | 44 comprehensive tests |

## Files Modified

| File | Changes |
|------|---------|
| `sindri/persistence/database.py` | Added `session_snapshots` and `session_tool_outputs` tables; bumped SCHEMA_VERSION to 7 |
| `sindri/cli.py` | Added `replay` command group with 4 subcommands (info, list, run, compare) |
| `STATUS.md` | Updated snapshot and recent changes section |
| `ROADMAP.md` | Marked Reproducible Sessions as complete; updated changelog |

## Database Schema Changes (v7)

Two new tables added:

### session_snapshots
Stores environment snapshots for sessions:
- `session_id` (FK to sessions)
- `sindri_version`, `sindri_git_commit`
- `python_version`, `ollama_version`, `ollama_host`
- `model_metadata_json` (digest, quantization, family, etc.)
- `inference_params_json` (temperature, top_p, seed, etc.)
- `config_snapshot_json` (full SindriConfig)

### session_tool_outputs
Stores full tool outputs for replay:
- `session_id`, `turn_index`, `tool_index`
- `tool_name`, `arguments_json`
- `output_full` (not truncated, unlike audit log)
- `output_hash` (SHA256 for verification)
- `duration_ms`, `success`

## New CLI Commands

| Command | Purpose |
|---------|---------|
| `sindri replay info <session>` | Show environment snapshot for a session |
| `sindri replay list` | List sessions with replay snapshots |
| `sindri replay run <session> --mode [tool-only\|full]` | Replay a session |
| `sindri replay compare <s1> <s2>` | Compare two sessions |

## Key Classes

### SnapshotCapture
Captures environment at session creation:
- Gets Sindri version (package or git commit)
- Gets Python version
- Gets Ollama version via /api/version
- Gets model metadata via /api/show (digest, quantization, family)
- Serializes SindriConfig

### ReplayEngine
Orchestrates session replay:
- `TOOL_ONLY` mode: Uses recorded tool outputs for deterministic replay
- `FULL` mode: Re-runs with LLM (framework for future implementation)
- `get_replay_info()`: Check if session is replayable

### SessionComparator
Compares two sessions:
- Environment diff (version changes, model changes)
- Turn-by-turn comparison with similarity scores
- Unified diff generation for content changes
- Summary generation

## Test Coverage

- 44 new tests added in `tests/test_replay.py`
- Test categories:
  - ModelMetadata/InferenceParams/EnvironmentSnapshot serialization (8 tests)
  - SnapshotStore/ToolOutputStore persistence (5 tests)
  - SnapshotCapture (3 tests)
  - RecordedToolExecutor (4 tests)
  - ReplayEngine (5 tests)
  - SessionComparator (6 tests)
  - CLI commands (6 tests)
  - Database schema (1 test)
  - End-to-end integration (3 tests)
- All 3,945 tests pass (3,901 existing + 44 new)

## Commands to Test

```bash
# Run all tests
.venv/bin/pytest tests/ -v --tb=no -q

# Run replay tests specifically
.venv/bin/pytest tests/test_replay.py -v

# Test CLI commands
.venv/bin/sindri replay --help
.venv/bin/sindri replay info --help
.venv/bin/sindri replay list
```

## Design Decisions

1. **Separate from session creation** - Snapshot capture is a separate utility class that can be called after session creation, keeping the core state.py simple and backward compatible

2. **Tool outputs not in audit log** - Created separate `session_tool_outputs` table because audit log truncates outputs to 500 chars, but replay needs full outputs

3. **Tool-only replay first** - Full replay with LLM requires deeper orchestrator integration; tool-only mode provides immediate value for deterministic testing

4. **Output hash verification** - SHA256 hash stored with outputs allows verifying replay accuracy
