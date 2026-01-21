# Code Review Summary

**Feature:** Enforce System Access Levels for Shell/Filesystem Tools
**Date:** 2026-01-20
**Author:** Junior Claude
**Reviewer:** ChatGPT (Senior)

---

## Problem

The `ShellTool`, `WriteFileTool`, and `EditFileTool` in Sindri had **no access control checks**. This meant that even when the system was configured to RESTRICTED mode (read-only), these tools would still execute state-modifying operations.

### Expected Behavior by Access Level

| Access Level | Shell Commands | File Writes | File Edits | File Reads |
|--------------|----------------|-------------|------------|------------|
| RESTRICTED | BLOCKED | BLOCKED | BLOCKED | Allowed |
| SUPERVISED | Allowed | Allowed | Allowed | Allowed |
| FULL | Allowed | Allowed | Allowed | Allowed |

---

## Solution

### Pattern Followed

The implementation follows the established pattern from `sindri/tools/services.py`:

1. Load config inside `execute()` method using `SindriConfig.load()`
2. Call `check_system_access()` before performing any state-changing operation
3. Return `ToolResult(success=False, error=access_result.reason)` if access denied
4. Log denial events for debugging

### 1. Modified `sindri/tools/shell.py`

**Lines 6-8:** Added imports:
```python
from sindri.config import SindriConfig
from sindri.core.access import check_system_access
```

**Lines 28-46:** Added access control check at start of `execute()`:
```python
# Check access control - all shell commands are modifications
config = SindriConfig.load()
access_result = check_system_access(
    config,
    f"execute shell command: {command[:50]}{'...' if len(command) > 50 else ''}",
    is_modification=True,
)

if not access_result.allowed:
    log.warning(
        "shell_access_denied",
        command=command,
        reason=access_result.reason,
    )
    return ToolResult(
        success=False,
        output="",
        error=access_result.reason,
    )
```

**Note:** Long commands are truncated to 50 characters in the operation string for readability.

### 2. Modified `sindri/tools/filesystem.py`

**Lines 9-10:** Added imports (same as shell.py)

**WriteFileTool.execute() - Lines 83-101:** Added access control check:
```python
config = SindriConfig.load()
access_result = check_system_access(
    config,
    f"write file: {path}",
    is_modification=True,
)

if not access_result.allowed:
    log.warning("file_write_access_denied", path=path, reason=access_result.reason)
    return ToolResult(success=False, output="", error=access_result.reason)
```

**EditFileTool.execute() - Lines 152-170:** Same pattern for edit operations.

### 3. Read-Only Tools Unchanged

`ReadFileTool`, `ListDirectoryTool`, and `ReadTreeTool` have NO access control checks because they are read-only operations that are allowed at all access levels.

---

## Files Changed

| File | Changes |
|------|---------|
| `sindri/tools/shell.py` | +2 imports, +19 lines access control |
| `sindri/tools/filesystem.py` | +2 imports, +38 lines access control |
| `tests/test_tools.py` | +1 import, +12 tests (~160 lines) |
| `STATUS.md` | Updated test count (3804 -> 3815), added recent change |
| `ROADMAP.md` | Marked junior task as complete |

---

## Tests Added (11 new tests + 1 edge case test)

All in `tests/test_tools.py::TestToolAccessControl`:

### Shell Tool Tests
1. `test_shell_blocked_in_restricted_mode` - Shell commands blocked in RESTRICTED
2. `test_shell_allowed_in_supervised_mode` - Shell commands work in SUPERVISED
3. `test_shell_allowed_in_full_mode` - Shell commands work in FULL
4. `test_shell_long_command_truncated_in_error` - Long commands truncated in errors

### WriteFileTool Tests
5. `test_write_file_blocked_in_restricted_mode` - File writes blocked in RESTRICTED
6. `test_write_file_allowed_in_supervised_mode` - File writes work in SUPERVISED
7. `test_write_file_allowed_in_full_mode` - File writes work in FULL

### EditFileTool Tests
8. `test_edit_file_blocked_in_restricted_mode` - File edits blocked in RESTRICTED
9. `test_edit_file_allowed_in_supervised_mode` - File edits work in SUPERVISED
10. `test_edit_file_allowed_in_full_mode` - File edits work in FULL

### Read-Only Tool Tests
11. `test_read_file_allowed_in_restricted_mode` - Read operations always allowed

---

## Test Results

```
tests/test_tools.py: 16 passed (5 original + 11 new)
All tests: 3815 passed, 13 skipped, 8 warnings
```

---

## Access Control Behavior Matrix

| Tool | RESTRICTED | SUPERVISED | FULL |
|------|------------|------------|------|
| `shell` | BLOCKED | Allowed | Allowed |
| `write_file` | BLOCKED | Allowed | Allowed |
| `edit_file` | BLOCKED | Allowed | Allowed |
| `read_file` | Allowed | Allowed | Allowed |
| `list_directory` | Allowed | Allowed | Allowed |
| `read_tree` | Allowed | Allowed | Allowed |

---

## Potential Concerns for Review

1. **Config Loading Overhead**: Each tool execution loads config via `SindriConfig.load()`. This follows the existing pattern from `services.py` and ensures config is fresh. If performance is a concern, config caching could be considered.

2. **SUPERVISED Mode Confirmation**: The access check marks operations as `needs_confirmation=True` in SUPERVISED mode, but tools don't prompt for confirmation - they just proceed. The CLI/TUI layer is responsible for handling confirmation prompts. This matches the behavior in `services.py`.

3. **Error Messages**: The error messages include "RESTRICTED" which tests verify. If the error message format in `check_system_access()` changes, tests may need updating.

4. **Command Truncation**: Shell commands are truncated to 50 chars in the operation string. This is for readability in logs/errors. The full command is still logged in the warning event.

---

## How to Verify

```bash
# Run tool tests
.venv/bin/pytest tests/test_tools.py -v

# Run all tests
.venv/bin/pytest tests/ -v --tb=short -q
```

Manual verification:
```bash
# Set restricted mode in config, then try:
.venv/bin/sindri access set restricted
.venv/bin/sindri run "Create hello.py"  # Should fail with access denied
```
