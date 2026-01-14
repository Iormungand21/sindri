# TUI Task Cancellation Feature - 2026-01-14

## Overview

Added the ability to cancel running tasks in the Sindri TUI, allowing users to stop long-running or stuck operations gracefully.

---

## Feature Summary

**What:** Task cancellation system with Ctrl+C keybinding in TUI
**Why:** Users need to stop long-running tasks without killing the entire application
**How:** Cooperative cancellation using flag checking at iteration boundaries

---

## Implementation Details

### Components Modified

1. **Task Model** (`sindri/core/tasks.py`)
   - Added `CANCELLED` status to `TaskStatus` enum
   - Added `cancel_requested: bool` flag to Task dataclass

2. **Orchestrator** (`sindri/core/orchestrator.py`)
   - `cancel_task(task_id)` - Request cancellation of specific task + subtasks
   - `cancel_all()` - Cancel all tasks in scheduler
   - Cancellation check in main orchestration loop

3. **Hierarchical Loop** (`sindri/core/hierarchical.py`)
   - Cancellation check at start of each iteration
   - Cancellation check after LLM call returns
   - Proper status handling (don't override CANCELLED with FAILED)

4. **TUI** (`sindri/tui/app.py`)
   - Added Ctrl+C keybinding
   - Added `action_cancel()` handler
   - Added ⊗ icon for cancelled tasks
   - Track root task ID for cancellation
   - Help text updated with cancellation instructions

---

## Usage

### In TUI

1. **Start a task** - Enter task and press Enter
2. **Cancel task** - Press `Ctrl+C` while task is running
3. **Observe** - Task will cancel after current LLM call finishes

**Visual Feedback:**
- Notification: "Task cancellation requested"
- Output log: "⊗ Cancelling task..."
- Task tree: Task icon changes to ⊗ (cancelled)

### Programmatically

```python
from sindri.core.orchestrator import Orchestrator

# Create orchestrator
orchestrator = Orchestrator()

# Start task in background
task_future = asyncio.create_task(orchestrator.run("Long task..."))

# Later, cancel the task
orchestrator.cancel_all()
# or
orchestrator.cancel_task(specific_task_id)

# Wait for cancellation to complete
result = await task_future
# result['success'] == False
# result['error'] == "Task cancelled by user"
```

---

## How It Works

### Cancellation Flow

```
User presses Ctrl+C in TUI
    ↓
action_cancel() called
    ↓
orchestrator.cancel_task(root_task_id)
    ↓
Sets task.cancel_requested = True (+ all subtasks recursively)
    ↓
Orchestrator main loop checks flag
    ↓
HierarchicalLoop checks flag at 2 points:
    1. Start of each iteration
    2. After LLM call returns
    ↓
If cancelled: Set status=CANCELLED, return LoopResult(success=False)
    ↓
Orchestrator returns with error="Task cancelled by user"
    ↓
TUI shows cancellation in output log
```

### Cooperative Cancellation

**Important:** Sindri uses **cooperative cancellation**, not forceful termination.

- ✅ **Cancellation is checked** at natural break points:
  - Before each iteration
  - After LLM calls return
  - Before tool execution

- ❌ **Cancellation does NOT interrupt**:
  - LLM generation mid-stream (must finish current response)
  - Running shell commands
  - File I/O operations

**Timing:** Cancellation typically takes 1-30 seconds depending on LLM response time.

---

## Testing

### Test Script

```bash
.venv/bin/python test_cancellation.py
```

**What it tests:**
1. Start a multi-iteration task
2. Request cancellation after 5 seconds
3. Wait for task to abort (up to 60 seconds for LLM to finish)
4. Verify status = CANCELLED
5. Verify error message = "Task cancelled by user"

### Test Results

```
✅ Task marked as cancelled
✅ Cancel requested flag set
✅ Error message set
✅ Result indicates failure
✅ Cancellation message in output

🎉 CANCELLATION TEST PASSED
Task was properly cancelled and status updated
```

---

## Status Icons

| Status | Icon | Description |
|--------|------|-------------|
| PENDING | · | Task queued |
| PLANNING | ○ | Task being planned |
| WAITING | ◔ | Waiting for subtasks |
| RUNNING | ▶ | Currently executing |
| COMPLETE | ✓ | Successfully completed |
| FAILED | ✗ | Failed with error |
| BLOCKED | ⚠ | Blocked by dependency |
| **CANCELLED** | **⊗** | **User cancelled** |

---

## Keybindings

| Key | Action | Description |
|-----|--------|-------------|
| q | Quit | Exit application |
| ? | Help | Show help screen |
| **Ctrl+C** | **Cancel** | **Cancel running task** |
| Enter | Submit | Start new task (in input field) |

---

## Architecture Details

### Why Not Forceful Cancellation?

**Considered approaches:**
1. ❌ **Kill thread/process** - Unsafe, leaves resources in inconsistent state
2. ❌ **asyncio.cancel()** - Doesn't play well with Ollama's blocking calls
3. ✅ **Cooperative flags** - Safe, predictable, testable

**Trade-off:** Cancellation isn't instant, but it's reliable and safe.

### Recursive Cancellation

When a parent task is cancelled, all its subtasks are also cancelled:

```python
def cancel_task(self, task_id: str):
    task = self.scheduler.tasks.get(task_id)
    if task:
        task.cancel_requested = True
        # Recursively cancel all children
        for subtask_id in task.subtask_ids:
            self.cancel_task(subtask_id)
```

This ensures clean shutdown of entire task hierarchies.

### Status Preservation

Critical: Don't override CANCELLED with FAILED:

```python
elif task.status != TaskStatus.CANCELLED:
    # Only mark as FAILED if not already CANCELLED
    task.status = TaskStatus.FAILED
```

Without this check, cancelled tasks would appear as "failed" in the UI.

---

## Edge Cases Handled

### 1. No Task Running
**User presses Ctrl+C with no active task**
- Action: Show notification "No task running"
- Behavior: No-op, UI remains responsive

### 2. Task Already Finishing
**Cancellation requested just as task completes**
- Action: Task completes normally
- Behavior: Cancellation flag ignored (task already done)

### 3. LLM Mid-Generation
**Cancellation requested while LLM is generating**
- Action: Wait for LLM to finish current response
- Behavior: Cancellation processed after response returns
- Timing: 1-30 seconds depending on response length

### 4. Multiple Cancellation Requests
**User spams Ctrl+C multiple times**
- Action: Additional requests are no-ops
- Behavior: Flag already set, nothing changes

### 5. Subtask Cancellation
**Parent cancelled, child currently running**
- Action: Child's cancel_requested flag set
- Behavior: Child checks flag at next iteration
- Result: Both parent and child marked CANCELLED

---

## Known Limitations

1. **LLM Responses Can't Be Interrupted**
   - Must wait for current generation to complete
   - Typical wait: 1-30 seconds
   - Workaround: Use shorter max_tokens if cancellation speed is critical

2. **Shell Commands Run to Completion**
   - No mid-command cancellation
   - If shell runs `sleep 3600`, must wait full hour
   - Workaround: Use timeouts in shell tool

3. **No Undo**
   - File changes, shell commands already executed can't be rolled back
   - Cancellation only prevents future operations
   - Workaround: Design tasks to be idempotent

---

## Future Enhancements

### Potential Improvements

1. **Progress Bar**
   - Show "Cancelling... (waiting for LLM)" message
   - Countdown timer showing how long we've been waiting

2. **Force Kill**
   - After 30 seconds, offer "Force Quit" option
   - Risks: Resource leaks, inconsistent state
   - Use case: When LLM is truly stuck

3. **Checkpoint/Resume**
   - Save state at iteration boundaries
   - Allow resuming cancelled tasks later
   - Use case: Long-running tasks that get accidentally cancelled

4. **Selective Cancellation**
   - Cancel specific subtasks, not entire hierarchy
   - UI: Click task in tree to cancel just that branch
   - Use case: One subtask is stuck, others are fine

---

## Comparison with Other Systems

### VS Code Extension
- **VS Code**: `Escape` key cancels, instant abort
- **Sindri**: `Ctrl+C` requests cancel, waits for safe point
- **Why different**: VS Code controls extension, Sindri uses external LLM

### Claude Code CLI
- **Claude Code**: Ctrl+C kills entire process
- **Sindri**: Ctrl+C cancels task, TUI stays running
- **Why different**: Sindri is a persistent TUI app

### Cursor
- **Cursor**: Stop button in UI, cancels generation
- **Sindri**: Keyboard shortcut for CLI power users
- **Why similar**: Both need graceful cancellation

---

## Debugging Cancellation Issues

### Enable Verbose Logging

```python
import structlog
import logging

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG)
)
```

### Key Log Messages

Look for these in logs:

```
task_cancellation_requested   task_id=...
task_cancelled_in_loop        task_id=... iteration=N
task_cancelled_after_llm      task_id=...
orchestrator_cancelled        task_id=...
```

### Common Issues

**Problem:** Task not cancelling
**Check:** Is `cancel_requested` flag being set?
**Fix:** Verify `orchestrator.cancel_task()` is being called

**Problem:** Task shows FAILED instead of CANCELLED
**Check:** Status preservation logic
**Fix:** Ensure `elif task.status != TaskStatus.CANCELLED` check exists

**Problem:** Cancellation takes too long
**Check:** Is LLM generating a very long response?
**Fix:** Reduce `max_tokens` in agent configuration

---

## Code Locations

| Component | File | Lines |
|-----------|------|-------|
| TaskStatus.CANCELLED | sindri/core/tasks.py | 19 |
| Task.cancel_requested | sindri/core/tasks.py | 55 |
| Orchestrator.cancel_task() | sindri/core/orchestrator.py | 72-81 |
| Loop cancellation checks | sindri/core/hierarchical.py | 166-178, 238-249 |
| TUI action_cancel() | sindri/tui/app.py | 274-290 |
| Ctrl+C keybinding | sindri/tui/app.py | 61 |
| Cancelled status icon | sindri/tui/app.py | 23 |

---

## Related Documentation

- `STATUS.md` - Overall project status
- `CLAUDE.md` - Project context for development
- `test_cancellation.py` - Automated test script
- `sindri/tui/app.py` - TUI implementation

---

## Summary

**Status:** ✅ **Production Ready**

Task cancellation is fully implemented and tested. Users can safely cancel running tasks in the TUI without leaving inconsistent state or requiring app restart.

**Key Features:**
- Ctrl+C keybinding in TUI
- Recursive cancellation of subtasks
- Proper status tracking (CANCELLED ≠ FAILED)
- Safe cooperative cancellation
- Visual feedback in task tree

**Limitations:**
- Must wait for LLM to finish current response (1-30s)
- No rollback of completed operations
- No mid-operation interruption

**Next Steps:**
- Add progress feedback ("Cancelling... please wait")
- Consider force-kill option after timeout
- Test with more complex delegation scenarios

---

**Implemented:** 2026-01-14
**Tested:** Yes - All checks passing
**Status:** Ready for use

---

**Test Command:**
```bash
.venv/bin/python test_cancellation.py
```

**Live Usage:**
```bash
sindri tui
# Start a task
# Press Ctrl+C to cancel
```
