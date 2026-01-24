# Review Summary: Session Status Persistence on Cancel/Failure

**Reviewer:** ChatGPT (Senior Reviewer)
**Date:** 2026-01-23
**Original Commit:** 2ccad3f
**Fix Commit:** 569ea62
**Author:** Claude Opus 4.5

## Summary

Implemented **Session Status Persistence on Cancel/Failure** - a stability fix that ensures sessions are properly marked as 'failed' or 'cancelled' instead of remaining 'active' when tasks fail or are cancelled.

## Problem

When a task failed (`TaskStatus.FAILED`) or was cancelled (`TaskStatus.CANCELLED`), the session remained with status "active" in the database. Only `complete_session()` was called on success. This led to stale sessions that relied on `cleanup_stale_sessions()` timeout (1 hour) for cleanup.

## Solution

1. Added `fail_session()` and `cancel_session()` methods to `SessionState`
2. Added `error` column to sessions table (schema v8) to store failure/cancellation reasons
3. Updated all failure/cancellation points in `hierarchical.py` and `orchestrator.py` to call the new methods

## Files Changed

### Modified Files
| File | Changes |
|------|---------|
| `sindri/persistence/database.py` | Increment SCHEMA_VERSION to 8, add error column migration |
| `sindri/persistence/state.py` | Add `Session.error` field, `fail_session()`, `cancel_session()` methods, update `load_session()` |
| `sindri/core/hierarchical.py` | Call fail/cancel_session at 6 failure/cancel points |
| `sindri/core/orchestrator.py` | Call fail/cancel_session at 4 failure/cancel points |
| `tests/test_persistence.py` | Add 7 new tests for session status methods |
| `tests/test_replay.py` | Update schema version test from v7 to v8 |
| `STATUS.md` | Document feature, update test count |
| `FACTS.md` | Update date and test count |
| `ROADMAP.md` | Mark junior task as complete |

## Key Implementation Details

### 1. Session.error Field (`sindri/persistence/state.py`)
```python
@dataclass
class Session:
    # ... existing fields ...
    error: Optional[str] = None  # Error reason for failed/cancelled sessions
```

### 2. New Methods (`sindri/persistence/state.py`)
```python
async def fail_session(self, session_id: str, error: Optional[str] = None):
    """Mark a session as failed with optional error reason."""
    # Sets status='failed', completed_at=now, error=error

async def cancel_session(self, session_id: str, reason: Optional[str] = None):
    """Mark a session as cancelled."""
    # Sets status='cancelled', completed_at=now, error=reason (default: "Cancelled by user")
```

### 3. Schema Migration (`sindri/persistence/database.py`)
- Version 8: Added `error TEXT` column to sessions table
- Safe migration using `PRAGMA table_info` check before ALTER TABLE

### 4. Hierarchical Loop Updates (`sindri/core/hierarchical.py`)
| Location | Failure Type | Method Called |
|----------|--------------|---------------|
| Line 446 | Task cancelled in loop | `cancel_session(session.id, "Task cancelled by user")` |
| Line 502 | Policy violation (runtime) | `fail_session(session.id, f"Policy violation: {reason}")` |
| Line 657 | Cancelled after LLM call | `cancel_session(session.id, "Task cancelled after LLM call")` |
| Line 784 | Policy violation (tool limit) | `fail_session(session.id, f"Policy violation: {reason}")` |
| Line 858 | Policy violation (file access) | `fail_session(session.id, f"Policy violation: {reason}")` |
| Line 1270 | Agent stuck | `fail_session(session.id, f"Agent stuck: {reason}")` |
| Line 1318 | Max iterations | `fail_session(session.id, "Max iterations reached")` |

### 5. Orchestrator Updates (`sindri/core/orchestrator.py`)
| Location | Failure Type | Method Called |
|----------|--------------|---------------|
| Line 336 | Root task cancelled | `cancel_session(root_task.session_id, "Task cancelled by user")` |
| Line 434 | Task exception (single) | `fail_session(task.session_id, str(e))` |
| Line 476 | Task exception (parallel) | `fail_session(task.session_id, str(result))` |
| Line 553 | Task exception (sequential) | `fail_session(next_task.session_id, str(e))` |

## Review Feedback & Fixes

ChatGPT identified 1 issue (see NOTES.md). Fixed in commit 569ea62:

| Issue | Status | Fix |
|-------|--------|-----|
| Model-load failure doesn't update existing session | **FIXED** | Added `fail_session()` call when `task.session_id` is set |

## Tests Run

```bash
.venv/bin/pytest tests/test_persistence.py -v
# 10 passed in 1.73s

.venv/bin/pytest tests/ -v --tb=no -q
# 4008 passed, 13 skipped in 31.60s
```

### New Test Cases
1. `test_fail_session_with_error` - Verify session marked as 'failed' with error message
2. `test_fail_session_without_error` - Verify session marked as 'failed' without error
3. `test_cancel_session_with_reason` - Verify session marked as 'cancelled' with reason
4. `test_cancel_session_default_reason` - Verify default "Cancelled by user" reason
5. `test_cleanup_stale_ignores_cancelled_sessions` - Verify cleanup doesn't re-mark cancelled sessions
6. `test_cleanup_stale_ignores_failed_sessions` - Verify cleanup doesn't re-mark failed sessions
7. `test_schema_version_8` - Verify schema v8 has error column
8. `test_model_load_failure_marks_existing_session_failed` - Verify resumed task session is marked failed on model load failure

## Design Decisions

1. **Separate status values**: Used distinct 'cancelled' and 'failed' statuses (frontend already supports this)
2. **Error column**: Added nullable `error` column to store failure/cancellation reasons for debugging
3. **Default cancellation reason**: "Cancelled by user" when no explicit reason provided
4. **Session guards**: All calls check `if session:` before updating to handle early failures

## Files for Focused Review

1. `sindri/persistence/state.py:199-254` - New `fail_session()` and `cancel_session()` methods
2. `sindri/persistence/database.py:375-378` - Schema v8 migration
3. `sindri/core/hierarchical.py:446,502,657,784,858,1270,1318` - Session status updates
4. `sindri/core/orchestrator.py:336,434,476,553` - Session status updates
5. `tests/test_persistence.py:83-159` - New test cases

## Next Feature

The next items on the ROADMAP are:
- **Junior task:** Record fallback model in session metadata when model degradation occurs
- **Item 8:** Agents as Plugins - SDK for packaging agents + prompts + tests
