# Review Notes - Performance Telemetry Stream

## Findings (All Resolved)

1) ~~TelemetryCollector is never instantiated or started~~ **FIXED**
- Fixed: TelemetryCollector now starts in `SindriAPI.initialize()` and stops in `shutdown()`
- Made `session_id` optional in `start()` for pre-session metrics
- Added `set_session()` method to update session ID when tasks begin
- Files changed: `sindri/telemetry/collector.py`, `sindri/web/server.py`

2) ~~ITERATION_END events are never emitted~~ **FIXED**
- Fixed: ITERATION_END event now emitted after each iteration with `duration_ms`
- Tracks `iteration_start_time` and calculates duration at iteration end
- Files changed: `sindri/core/hierarchical.py`

3) ~~TOOL_CALLED event lacks duration_ms~~ **FIXED**
- Fixed: `duration_ms` now included in TOOL_CALLED event payload
- Uses already-calculated `tool_duration_ms` value
- Files changed: `sindri/core/hierarchical.py`

4) ~~TraceExporter ignores include_tool_outputs~~ **FIXED**
- Fixed: `include_tool_outputs=True` now loads full tool outputs from ToolOutputStore
- Added `_tool_output_store` attribute and `_get_tool_output_store()` lazy-loader
- Outputs included in trace as `tool_outputs` field
- Files changed: `sindri/telemetry/exporter.py`

## Suggested Follow-ups (Pending)
- Add integration tests that start a session and verify telemetry ticks and snapshots are non-empty.
- Add a regression test that validates tool duration appears in telemetry when TOOL_CALLED is emitted.

## Resolution
All four issues fixed in commit ec11aaa. All 4,036 tests pass.
