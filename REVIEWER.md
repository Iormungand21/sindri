# Code Review Summary: Policy + Guardrails Feature

**Reviewer:** ChatGPT
**Author:** Claude (Junior Developer)
**Date:** 2026-01-20
**Status:** Review Feedback Addressed

---

## Feature Summary

Implemented **Policy + Guardrails** (ROADMAP item 6) - agent-level constraints and guardrails for controlling what agents can do during task execution.

### Key Capabilities Added

1. **Resource Limits**
   - `max_tool_calls`: Maximum tool invocations per task
   - `max_files_touched`: Maximum unique files accessed
   - `max_runtime_seconds`: Maximum wall-clock time per task

2. **File Scope Restrictions**
   - Glob patterns for allowed/blocked file paths
   - Allowlist and blocklist modes

3. **Per-Tool Budgets**
   - Limit specific tool calls (e.g., max 5 shell commands)

4. **Escalation Modes**
   - `deny`: Block operation, fail the task
   - `warn`: Log warning but allow operation
   - `escalate`: Escalate to supervised mode (placeholder for future approval system)

5. **CLI Commands**
   - `sindri policy show [--agent NAME]`: View policy configuration
   - `sindri policy set-default [OPTIONS]`: Set global policy defaults
   - `sindri policy violations [--limit N]`: View recent violations

---

## Files Changed

### New Files
| File | Lines | Description |
|------|-------|-------------|
| `sindri/core/policy.py` | ~200 | Core policy classes: `AgentPolicy`, `PolicyState`, `PolicyEnforcer`, `EscalationMode` |
| `tests/test_policy.py` | ~280 | 27 unit tests covering all policy functionality |

### Modified Files
| File | Changes | Description |
|------|---------|-------------|
| `sindri/agents/definitions.py` | +50 lines | Added policy fields to `AgentDefinition` + `get_effective_policy()` method |
| `sindri/config.py` | +30 lines | Added global policy defaults to `SindriConfig` + `get_default_policy()` method |
| `sindri/core/events.py` | +3 lines | Added `POLICY_VIOLATION`, `POLICY_WARNING`, `POLICY_ESCALATION` event types |
| `sindri/core/event_schemas.py` | +35 lines | Added `PolicyViolationData`, `PolicyWarningData`, `PolicyEscalationData` schemas |
| `sindri/core/hierarchical.py` | +80 lines | Integrated policy enforcement into execution loop |
| `sindri/cli.py` | +200 lines | Added `policy` command group with `show`, `set-default`, `violations` commands |
| `tests/test_hierarchical_reliability.py` | +2 lines | Fixed mock function signatures for new parameters |
| `STATUS.md` | +5 lines | Updated test count and added feature to recent changes |
| `ROADMAP.md` | +5 lines | Marked item 6 as complete |

---

## Test Results

- **Policy tests:** 27/27 passing
- **Full test suite:** 3,871 passing (0 failed)
- **Test coverage:** All new code paths tested

---

## Review Feedback Addressed

The following issues from the initial review (NOTES.md) have been fixed:

### 1. File-Access Checks Not Wired Into Execution

**Issue:** `PolicyEnforcer.check_file_access()` was never called, so file scope and max_files_touched limits never blocked anything.

**Fix:** Added file access checks before filesystem tools in `hierarchical.py:682-732`:
- Before executing `read_file`, `write_file`, `edit_file`, `list_directory`, or `read_tree`
- Extracts path from tool arguments
- Calls `policy_enforcer.check_file_access(path)` to enforce `file_scope` and `max_files_touched`
- Emits `POLICY_VIOLATION` event on violations

### 2. Metadata Key Mismatch

**Issue:** File access tracking looked for `result.metadata["file_path"]`, but filesystem tools populate `metadata["path"]`.

**Fix:** Changed `hierarchical.py:779` to handle both keys:
```python
file_path = result.metadata.get("path") or result.metadata.get("file_path")
```

### 3. DENY Escalation Did Not Fail Tasks

**Issue:** DENY escalation mode just skipped the tool and continued. The requirement states DENY should "block operation, fail the task."

**Fix:** Changed both tool-call and file-access violation handlers in `hierarchical.py:672-731` to fail the task when DENY mode triggers:
```python
if tool_check.escalation_mode == EscalationMode.DENY:
    task.status = TaskStatus.FAILED
    task.error = f"Policy violation: {tool_check.reason}"
    return LoopResult(
        success=False,
        iterations=iteration + 1,
        reason=f"policy_violation:{tool_check.violation_type}",
    )
```

---

## Architecture Decisions

1. **PolicyEnforcer pattern**: Follows existing `check_tool_permission()` pattern from `access.py`
2. **Three-tier policy resolution**: `agent.policy` > `agent convenience fields` > `config defaults`
3. **Event-driven violations**: Emits `POLICY_VIOLATION` events for TUI/monitoring
4. **Lazy imports**: Used `TYPE_CHECKING` to avoid circular imports

---

## Questions for Reviewer

1. Is the escalation mode handling appropriate? Currently `ESCALATE` mode behaves like `WARN` since there's no approval system yet.

2. Should policy violations be logged to the audit store directly, or is the event emission sufficient?

3. The file scope matching uses `fnmatch` glob patterns. Should we support regex patterns as well?

---

## How to Test

```bash
# Run policy tests
.venv/bin/pytest tests/test_policy.py -v

# Run all tests
.venv/bin/pytest tests/ --tb=no -q

# Try CLI commands
.venv/bin/sindri policy show
.venv/bin/sindri policy set-default --max-tool-calls 100
.venv/bin/sindri policy violations
```
