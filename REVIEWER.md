# Code Review Summary

**Reviewer:** ChatGPT (Senior Team Member)
**Date:** 2026-01-20
**Task:** Phase 15 Junior Task - Respect configured work_dir when indexing memory context

---

## Summary

Fixed a bug where memory indexing in `HierarchicalAgentLoop` used `os.getcwd()` directly instead of respecting the configured `work_dir` from the tool registry. This caused semantic embeddings to be created for the wrong directory when users specified `--work-dir`.

---

## Files Changed

### 1. `sindri/core/hierarchical.py`

**Changes:**
- Added `from pathlib import Path` import (line 5)
- Replaced direct `os.getcwd()` calls with `self.tools.work_dir or Path.cwd()` pattern (lines 302-308)

**Before:**
```python
project_id = f"project_{os.getcwd().replace('/', '_')}"
if self.memory and project_id not in self._indexed_projects:
    log.info("indexing_project", path=os.getcwd())
    indexed = self.memory.index_project(os.getcwd(), project_id)
```

**After:**
```python
# Use configured work_dir or fall back to cwd for memory indexing
project_path = self.tools.work_dir or Path.cwd()
project_id = f"project_{str(project_path.resolve()).replace('/', '_')}"
if self.memory and project_id not in self._indexed_projects:
    log.info("indexing_project", path=str(project_path))
    indexed = self.memory.index_project(str(project_path), project_id)
```

### 2. `tests/test_hierarchical_reliability.py`

**Added:** `TestWorkDirMemoryIndexing` test class with 3 tests:
- `test_memory_indexing_uses_configured_work_dir` - Verifies work_dir is used when set
- `test_memory_indexing_falls_back_to_cwd_when_no_work_dir` - Verifies fallback behavior
- `test_project_id_uses_configured_work_dir_path` - Verifies project_id generation uses custom path

---

## Test Results

All tests pass:
- 28 tests in `test_hierarchical_reliability.py` (including 3 new tests)
- 39 total related tests (hierarchical + memory) - all passing

---

## Review Questions for ChatGPT

1. Is the fallback pattern (`self.tools.work_dir or Path.cwd()`) the correct approach for backward compatibility?
2. Should the `project_path.resolve()` call be necessary, or is it over-engineering?
3. Are the tests comprehensive enough for this change?
4. Any edge cases I might have missed (symlinks, relative paths, etc.)?

---

## Documentation Updated

- `ROADMAP.md` - Marked junior task as complete with checkmark
- `STATUS.md` - Added "Recent Changes" entry for this fix
