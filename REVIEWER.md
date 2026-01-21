# Phase 15 Junior Task: Sequential Exception Handling Fix

**Date:** 2026-01-20
**Author:** Claude (Junior Coder)
**Reviewer:** ChatGPT (Senior Team Member)
**Task:** Add exception handling to sequential execution path to match parallel error reporting

---

## Summary

Implemented **exception handling in the `_run_sequential()` method** of `sindri/core/orchestrator.py` to ensure consistent error handling between parallel and sequential task execution paths.

---

## Problem Statement

The sequential execution path (`_run_sequential()`) lacked exception handling around `await self.loop.run_task(next_task)`. When a task threw an exception:

| Aspect | Parallel (`_run_parallel_batch()`) | Sequential (`_run_sequential()`) Before |
|--------|-----------------------------------|-----------------------------------------|
| Exception caught | ✅ Yes | ❌ No |
| Task marked FAILED | ✅ Yes | ❌ No |
| Error message stored | ✅ Yes | ❌ No |
| Parent notified via `child_failed()` | ✅ Yes | ❌ No |
| ERROR event emitted | ✅ Yes | ❌ No |

**Result:** Exceptions in sequential mode could crash the orchestrator or leave tasks in inconsistent states.

---

## Implementation

### File Changed: `sindri/core/orchestrator.py`

**Before (lines 315-322):**
```python
result = await self.loop.run_task(next_task)

log.info(
    "task_result",
    task_id=next_task.id,
    success=result.success,
    iterations=result.iterations,
)

return "ok"
```

**After (lines 315-349):**
```python
try:
    result = await self.loop.run_task(next_task)
    log.info(
        "task_result",
        task_id=next_task.id,
        success=result.success,
        iterations=result.iterations,
    )
except Exception as e:
    log.error("task_exception", task_id=next_task.id, error=str(e))
    next_task.status = TaskStatus.FAILED
    next_task.error = str(e)

    # Notify parent task of failure (if this is a child task)
    await self.delegation.child_failed(next_task)

    # Emit error event for TUI/logging
    self.event_bus.emit(
        Event(
            type=EventType.ERROR,
            data={
                "task_id": next_task.id,
                "error": str(e),
                "error_type": "sequential_task_exception",
                "agent": next_task.assigned_agent,
                "description": next_task.description[:100],
            },
        )
    )

return "ok"
```

---

## Tests Added

### File: `tests/test_hierarchical_reliability.py`

Added new test class `TestSequentialExceptionPropagation` with 5 tests:

| Test | Purpose |
|------|---------|
| `test_sequential_exception_marks_task_failed` | Verify task status is set to `TaskStatus.FAILED` |
| `test_sequential_exception_notifies_parent` | Verify parent task is notified via `child_failed()` |
| `test_sequential_exception_emits_error_event` | Verify ERROR event is emitted with correct `error_type` |
| `test_sequential_exception_returns_ok` | Verify method still returns `"ok"` after handling exception |
| `test_sequential_exception_stores_error_details` | Verify event data contains all required fields |

**Test Pattern:** Each test creates an orchestrator, mocks `loop.run_task()` to raise an exception, calls `_run_sequential()`, and verifies the expected behavior.

---

## Test Results

```
$ .venv/bin/pytest tests/test_hierarchical_reliability.py -v --tb=short
...
tests/test_hierarchical_reliability.py::TestSequentialExceptionPropagation::test_sequential_exception_marks_task_failed PASSED
tests/test_hierarchical_reliability.py::TestSequentialExceptionPropagation::test_sequential_exception_notifies_parent PASSED
tests/test_hierarchical_reliability.py::TestSequentialExceptionPropagation::test_sequential_exception_emits_error_event PASSED
tests/test_hierarchical_reliability.py::TestSequentialExceptionPropagation::test_sequential_exception_returns_ok PASSED
tests/test_hierarchical_reliability.py::TestSequentialExceptionPropagation::test_sequential_exception_stores_error_details PASSED

============================== 25 passed in 1.44s ==============================
```

---

## Files Modified

| File | Change |
|------|--------|
| `sindri/core/orchestrator.py` | Added try/except block in `_run_sequential()` |
| `tests/test_hierarchical_reliability.py` | Added `TestSequentialExceptionPropagation` class (5 tests) |
| `STATUS.md` | Added changelog entry |
| `ROADMAP.md` | Marked junior task as complete (✅) |

---

## Documentation Updates

1. **STATUS.md** - Added entry under "Recent Changes" describing the fix
2. **ROADMAP.md** - Marked the junior task with ✅ under "Stability + Bugfixes"

---

## Design Decisions

1. **Error type naming:** Used `"sequential_task_exception"` to distinguish from `"task_exception"` (single parallel) and `"parallel_task_exception"` (batch parallel) for debugging/tracing purposes.

2. **Return value:** Method still returns `"ok"` after handling an exception because a task was processed (even if it failed). This matches the parallel path behavior.

3. **Pattern matching:** Closely followed the existing pattern in `_run_parallel_batch()` for consistency and maintainability.

---

## Potential Review Points

1. **Is `"ok"` the right return value after failure?** The method indicates whether a task was *processed*, not whether it *succeeded*. The caller checks task status separately.

2. **Should we add rate limiting for error events?** If many tasks fail rapidly, we could flood the event bus. Not addressed here as it's a broader concern.

3. **Test coverage:** Tests use mocking rather than integration testing. This matches existing patterns in the test file.

---

## Risk Assessment

- **Low risk:** This is purely additive code that improves error handling
- **No breaking changes:** Method signature and return values unchanged
- **Pattern matching:** Following established pattern from parallel execution
