# Critical Fixes Applied (2026-01-14)

This document records the fixes applied during the debugging session to get Sindri working.

---

## Problem: Tasks Not Completing

**Symptom:** TUI showed tasks starting, agents outputting dialogue, tools executing successfully, but tasks marked as FAILED with "max_iterations_reached". No files actually created.

**Root Cause:** When a parent task delegated to a child, the child would complete successfully, but the parent didn't know what happened. Parent kept iterating trying to figure out what to do next until hitting max_iterations.

---

## Fix 1: Child Result Injection (CRITICAL)

**What:** When a child task completes, inject its result into the parent's session as a tool message.

**Files Modified:**
1. `sindri/core/delegation.py`:
   - Added `state` parameter to `__init__`
   - Modified `child_completed()` to load parent session and inject result

2. `sindri/core/orchestrator.py`:
   - Pass `SessionState` to `DelegationManager`

3. `sindri/core/tasks.py`:
   - Added `session_id: Optional[str]` field

4. `sindri/core/hierarchical.py`:
   - Store `session.id` on `task.session_id` after creating session

**Code Changes:**

```python
# sindri/core/delegation.py
class DelegationManager:
    def __init__(self, scheduler: TaskScheduler, state=None):
        self.scheduler = scheduler
        self.state = state  # NEW: Store SessionState reference

    async def child_completed(self, child: Task):
        # ... existing code ...

        # NEW: Inject child result into parent's session
        if self.state and hasattr(parent, 'session_id'):
            parent_session = await self.state.load_session(parent.session_id)
            if parent_session:
                result_text = (
                    f"Child task completed successfully!\n"
                    f"Agent: {child.assigned_agent}\n"
                    f"Task: {child.description}\n"
                    f"Result: {child.result.get('output', 'Task completed')}"
                )
                parent_session.add_turn("tool", result_text)
                await self.state.save_session(parent_session)
```

```python
# sindri/core/tasks.py
@dataclass
class Task:
    # ... existing fields ...
    session_id: Optional[str] = None  # NEW: Link to session
```

```python
# sindri/core/hierarchical.py
async def _run_loop(self, task: Task, agent, task_tools: ToolRegistry):
    session = await self.state.create_session(task.description, agent.model)
    task.session_id = session.id  # NEW: Store session ID on task
```

**Result:** Parents now know when children complete and what they accomplished.

---

## Fix 2: ToolCall Serialization Error

**What:** Native Ollama `ToolCall` objects couldn't be JSON serialized when saving sessions.

**Error:**
```
TypeError: Object of type ToolCall is not JSON serializable
```

**File Modified:** `sindri/persistence/state.py`

**Code Changes:**

```python
# NEW helper function
def serialize_tool_calls(tool_calls):
    """Convert tool calls to JSON-serializable format."""
    if not tool_calls:
        return None

    serialized = []
    for call in tool_calls:
        # Handle ollama native ToolCall objects
        if hasattr(call, 'function'):
            serialized.append({
                'function': {
                    'name': call.function.name,
                    'arguments': call.function.arguments
                }
            })
        # Handle dict format
        elif isinstance(call, dict):
            serialized.append(call)
        else:
            serialized.append(str(call))

    return json.dumps(serialized)

# Modified save_session method
async def save_session(self, session: Session):
    for turn in session.turns:
        tool_calls_json = serialize_tool_calls(turn.tool_calls)  # NEW
        # ... rest of save logic
```

**Result:** Sessions can be saved without JSON serialization errors.

---

## Fix 3: Event Bus Wiring

**What:** Events emitted by orchestrator weren't reaching TUI.

**Cause:** Orchestrator created its own EventBus in `__init__`, TUI tried to replace it but HierarchicalAgentLoop already had reference to old EventBus.

**Files Modified:**
1. `sindri/cli.py` - Create shared EventBus before orchestrator
2. `sindri/tui/app.py` - Accept event_bus parameter

**Code Changes:**

```python
# sindri/cli.py
@cli.command()
def tui(task: str = None, no_memory: bool = False):
    from sindri.tui.app import run_tui
    from sindri.core.orchestrator import Orchestrator
    from sindri.core.events import EventBus

    # NEW: Create shared event bus
    event_bus = EventBus()
    orchestrator = Orchestrator(enable_memory=not no_memory, event_bus=event_bus)
    run_tui(task=task, orchestrator=orchestrator, event_bus=event_bus)
```

```python
# sindri/tui/app.py
def __init__(self, task: Optional[str] = None, orchestrator=None,
             event_bus=None, **kwargs):  # NEW: event_bus parameter
    super().__init__(**kwargs)
    self.event_bus = event_bus or EventBus()  # Use provided or create new
    # ...

def run_tui(task: Optional[str] = None, orchestrator=None,
            event_bus=None):  # NEW: event_bus parameter
    app = SindriApp(task=task, orchestrator=orchestrator, event_bus=event_bus)
    app.run()
```

**Result:** TUI receives all events from orchestrator.

---

## Fix 4: Missing Event Emissions

**What:** HierarchicalAgentLoop only emitted TASK_STATUS_CHANGED events, missing AGENT_OUTPUT, TOOL_CALLED, ITERATION_START.

**File Modified:** `sindri/core/hierarchical.py`

**Code Changes:**

```python
# Line ~162: ITERATION_START
for iteration in range(agent.max_iterations):
    # ... existing code ...

    # NEW: Emit iteration start event
    self.event_bus.emit(Event(
        type=EventType.ITERATION_START,
        data={
            "task_id": task.id,
            "iteration": iteration + 1,
            "agent": agent.name
        }
    ))

# Line ~220: AGENT_OUTPUT
assistant_content = response.message.content
# ... existing code ...

# NEW: Emit agent output event
self.event_bus.emit(Event(
    type=EventType.AGENT_OUTPUT,
    data={
        "task_id": task.id,
        "agent": agent.name,
        "text": assistant_content
    }
))

# Line ~325: TOOL_CALLED
# ... existing code ...

# NEW: Emit tool called event
self.event_bus.emit(Event(
    type=EventType.TOOL_CALLED,
    data={
        "task_id": task.id,
        "name": call.function.name,
        "success": result.success,
        "result": result.output if result.success else result.error
    }
))
```

**Result:** TUI shows iteration markers, agent output, and tool results in real-time.

---

## Testing

**Test Case:** "Create a file called test_completion.txt with the text 'Delegation works!'"

**Expected Flow:**
1. Brokkr receives task
2. Brokkr delegates to Ratatoskr
3. Ratatoskr writes file with write_file tool
4. Ratatoskr completes with `<sindri:complete/>`
5. Child result injected to Brokkr's session ← **KEY FIX**
6. Brokkr resumes, sees child completed
7. Brokkr marks complete
8. File exists with correct content

**Test Results:** ✅ PASSED

```bash
.venv/bin/python test_task_completion.py

# Output shows:
# - file_written path=/home/ryan/projects/sindri/test_completion.txt size=17
# - injected_child_result_to_parent child_id=... parent_id=...
# - task_completed task_id=... iterations=2

$ cat test_completion.txt
Delegation works!
```

---

## Before vs After

### Before Fixes
```
1. Brokkr delegates to Ratatoskr
2. Ratatoskr writes file ✓
3. Ratatoskr completes ✓
4. Brokkr resumes ✓
5. Brokkr: "Wait, what happened? Let me delegate again..."
6. Brokkr creates new child tasks
7. Max iterations reached (20 iterations)
8. Task marked FAILED ✗
9. No file created ✗
```

### After Fixes
```
1. Brokkr delegates to Ratatoskr
2. Ratatoskr writes file ✓
3. Ratatoskr completes ✓
4. Result injected: "Child task completed! Result: file created" ← NEW
5. Brokkr resumes, reads injected result ✓
6. Brokkr: "Child succeeded, task complete!"
7. Brokkr marks complete (2-3 iterations) ✓
8. Task marked COMPLETE ✓
9. File exists ✓
```

---

## Known Remaining Issues

1. **Brokkr creates new session on resume**
   - Should reuse existing session instead of creating new one
   - Workaround: Result injection provides context
   - Proper fix: Check for `task.session_id` before creating session

2. **Brokkr delegates unnecessarily**
   - Even simple file creation gets delegated
   - Should handle trivial tasks directly
   - Fix: Improve Brokkr prompt

3. **Brokkr verification loops**
   - After delegation, tries to verify by delegating again
   - Should trust child completion or use tools directly
   - Fix: Improve Brokkr prompt

---

## Files Changed Summary

| File | Lines Changed | Purpose |
|------|---------------|---------|
| `sindri/core/delegation.py` | ~25 | Child result injection |
| `sindri/core/orchestrator.py` | 3 | Pass state to DelegationManager |
| `sindri/core/tasks.py` | 1 | Add session_id field |
| `sindri/core/hierarchical.py` | ~45 | Store session_id, emit events |
| `sindri/persistence/state.py` | ~25 | ToolCall serialization |
| `sindri/cli.py` | ~10 | Shared EventBus creation |
| `sindri/tui/app.py` | ~5 | Accept event_bus parameter |

**Total:** ~114 lines changed across 7 files

---

## Git Commit Message (if needed)

```
fix: implement child result injection for hierarchical delegation

When a parent task delegated to a child, the child would complete but
the parent never knew what happened. Parent would keep iterating trying
to figure out next steps, eventually hitting max_iterations and failing.

Changes:
- Add session_id field to Task model
- Store session.id on tasks when creating sessions
- Pass SessionState to DelegationManager
- Inject child results into parent sessions as tool messages
- Add serialize_tool_calls helper for native ToolCall objects
- Create shared EventBus in CLI before creating orchestrator
- Add missing event emissions (ITERATION_START, AGENT_OUTPUT, TOOL_CALLED)

Result: Parent tasks now receive child completion results and can mark
themselves complete after successful delegation. Simple file creation
tasks complete in 2-3 iterations instead of failing at max_iterations.

Tested: File creation via Brokkr → Ratatoskr delegation works end-to-end.
```

---

**Date Applied:** 2026-01-14
**Status:** All fixes verified working
**Next Step:** Test more complex multi-step tasks
