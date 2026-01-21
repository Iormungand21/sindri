# Code Review Summary - Phase 15: Hierarchical Execution Reliability Fixes

**Date:** 2026-01-20
**Author:** Claude Opus 4.5
**Feature:** ROADMAP Item 0 - Stability + Bugfixes

---

## Overview

This phase implements critical reliability fixes for Sindri's hierarchical task execution system. Four bugs were identified and fixed that could cause parent tasks to hang indefinitely, tasks to be over-scheduled, or task lookup errors.

---

## Changes Made

### 1. UUID Collision Prevention (Issue 6)

**File:** `sindri/core/tasks.py` (line 28)

**Problem:** Task IDs were truncated to 8 characters (`str(uuid.uuid4())[:8]`), creating collision risk at ~100k tasks.

**Fix:** Use full 36-character UUIDs.

```python
# Before
id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

# After
id: str = field(default_factory=lambda: str(uuid.uuid4()))
```

---

### 2. VRAM-Aware Batching (Issue 4)

**Files:**
- `sindri/llm/manager.py` (added 2 methods)
- `sindri/core/scheduler.py` (lines 94-103)

**Problem:** Scheduler used static `available` VRAM (14GB) instead of actual free VRAM, causing OOM errors when models were already loaded.

**Fix:**
1. Added `get_free_vram()` public method to ModelManager
2. Added `get_allocated_models()` method to include models being pre-warmed
3. Updated scheduler to use actual free VRAM for batching

```python
# scheduler.py - Before
max_vram = self.model_manager.available  # Static 14GB
loaded_models = set(self.model_manager.loaded.keys())

# scheduler.py - After
max_vram = self.model_manager.get_free_vram()  # Actual free VRAM
loaded_models = self.model_manager.get_allocated_models()  # Includes pre-warming
```

---

### 3. Model Load Failure Propagation (Issue 2)

**File:** `sindri/core/hierarchical.py` (lines 122-140)

**Problem:** When model loading failed, the task was not marked as FAILED and parent tasks were not notified.

**Fix:** Added proper status setting, parent notification, and error event emission.

```python
# Added before returning LoopResult
task.status = TaskStatus.FAILED
task.error = error_reason
await self.delegation.child_failed(task)
self.event_bus.emit(Event(type=EventType.ERROR, data={...}))
```

---

### 4. Exception Propagation (Issue 3)

**File:** `sindri/core/orchestrator.py` (lines 198-256)

**Problem:**
- Parallel task exceptions were caught but not propagated to parents
- Single task exceptions weren't caught at all

**Fix:**
1. Added exception handling to single-task path
2. Both paths now call `delegation.child_failed(task)` and emit ERROR events

---

## Test Coverage

**New test file:** `tests/test_hierarchical_reliability.py` (17 tests)

| Test Class | Tests | Coverage |
|------------|-------|----------|
| TestUUIDCollisionPrevention | 3 | Full UUID format validation |
| TestVRAMBatching | 6 | Free VRAM, allocated models, batching behavior |
| TestModelLoadFailurePropagation | 2 | Task status and error events |
| TestParallelExceptionPropagation | 3 | Exception handling and parent notification |
| TestHierarchicalReliabilityIntegration | 3 | End-to-end reliability scenarios |

**Test results:** 3744 total tests, 3743 passing (1 pre-existing flaky websocket test)

---

## Files Modified

| File | Changes |
|------|---------|
| `sindri/core/tasks.py` | +0/-6 chars (UUID change) |
| `sindri/llm/manager.py` | +20 lines (2 new methods) |
| `sindri/core/scheduler.py` | +3/-3 lines (VRAM batching fix) |
| `sindri/core/hierarchical.py` | +17 lines (model load failure fix) |
| `sindri/core/orchestrator.py` | +21 lines (exception handling) |
| `tests/test_hierarchical_reliability.py` | +370 lines (new test file) |
| `tests/test_recovery_integration.py` | +1 line (fix mock for async) |
| `STATUS.md` | Updated test count and feature list |
| `ROADMAP.md` | Marked item 0 complete |

---

## Potential Review Concerns

1. **Single vs Parallel error_type:** Single task exceptions use `task_exception`, parallel use `parallel_task_exception`. This is intentional for debugging but could be unified if desired.

2. **Pre-warm behavior not changed:** The pre-warm method still fires async and doesn't block. The existing `wait_for_prewarm()` method should be used if blocking behavior is needed. This is documented in ROADMAP.md.

3. **Flaky websocket test:** `test_websocket_event_contract` has a race condition unrelated to these changes (heartbeat arrives before event).

---

---

## Follow-up Fix: Delegation Wait Handling (Issue 1)

**File:** `sindri/core/hierarchical.py` (lines 198-227)

**Problem identified in review:** When `_run_loop` returns `LoopResult(success=None)` for delegation, `run_task` incorrectly treated it as failure because `None` is falsy in Python.

**Fix:** Changed `if result.success:` to `if result.success is True:` and added explicit handling for `success=None`:

```python
# Before
if result.success:  # None is falsy, so this fails for delegation!
    # ... mark complete
elif task.status != TaskStatus.CANCELLED:
    # ... mark FAILED (BUG: delegation waiting got here!)

# After
if result.success is True:
    # ... mark complete
elif result.success is None:
    # Delegation in progress - task is WAITING for children
    # Don't mark as failed, just return the result
    log.info("task_waiting_for_delegation", ...)
elif task.status != TaskStatus.CANCELLED:
    # ... mark FAILED (only for actual failures)
```

**New tests added:**
- `test_delegation_returns_success_none_keeps_task_waiting`
- `test_delegation_waiting_does_not_emit_error_event`
- `test_parent_resumes_after_child_completes`

---

## Summary of Impact

- **Reliability:** Parent tasks will no longer hang when children fail
- **Delegation:** Parent tasks correctly wait for children without being marked FAILED
- **Safety:** Tasks won't be over-scheduled when VRAM is partially used
- **Correctness:** Task IDs are now collision-resistant for long-running systems
- **Observability:** All failure paths now emit proper ERROR events
