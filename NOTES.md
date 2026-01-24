# Review Notes - Triggers & Automations (Cron)

## Status: All Issues Fixed

All three issues from the ChatGPT review have been addressed.

## Fixes Applied

### 1. Trigger agent setting now used
- **Issue**: `TriggerDefinition.agent` was ignored; executor always used Brokkr.
- **Fix**: Added `root_agent` parameter to `Orchestrator.run()` and passed `trigger.agent` from executor.
- **Files**: `sindri/core/orchestrator.py:302-350`, `sindri/triggers/executor.py:107-110`
- **Test**: `test_executor_uses_trigger_agent`

### 2. Result serialization fixed
- **Issue**: `_truncate()` expected string but `result` could be a dict, causing SQLite errors.
- **Fix**: Normalize result to string via `json.dumps()` before truncation.
- **Files**: `sindri/triggers/executor.py:111-117`
- **Test**: `test_executor_serializes_dict_result`

### 3. Trigger timezone applied in scheduling
- **Issue**: `_calculate_next_run` used UTC and ignored `trigger.timezone`.
- **Fix**: Use `zoneinfo.ZoneInfo` to evaluate cron in trigger's timezone, then convert to UTC.
- **Files**: `sindri/triggers/scheduler.py:300-345`
- **Tests**: `test_scheduler_uses_trigger_timezone`, `test_scheduler_invalid_timezone_fallback`

## Test Results

```bash
.venv/bin/pytest tests/test_triggers.py -v --tb=short
# 54 passed (50 original + 4 regression tests)

.venv/bin/pytest tests/ -v --tb=no -q
# 4090 passed, 13 skipped
```
