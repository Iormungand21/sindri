# Review Summary: Performance Telemetry Stream (ROADMAP Item 7)

**Reviewer:** ChatGPT (Senior Reviewer)
**Date:** 2026-01-21
**Original Commit:** f90246a
**Fix Commit:** ec11aaa
**Author:** Claude Opus 4.5

## Summary

Implemented **Performance Telemetry Stream** - real-time telemetry streaming with SSE endpoint, rolling statistics for agents/tools, VRAM and concurrency time-series history, and exportable traces for profiling and regression checks.

## Review Feedback & Fixes

ChatGPT identified 4 integration issues (see NOTES.md). All fixed in commit ec11aaa:

| Issue | Status | Fix |
|-------|--------|-----|
| TelemetryCollector never started | **FIXED** | Start in `SindriAPI.initialize()`, stop in `shutdown()` |
| ITERATION_END never emitted | **FIXED** | Emit with `duration_ms` after each iteration |
| TOOL_CALLED lacks duration_ms | **FIXED** | Add `duration_ms` to event payload |
| include_tool_outputs ignored | **FIXED** | Load from ToolOutputStore when flag is True |

## Files Changed

### New Files
| File | Purpose | Lines |
|------|---------|-------|
| `sindri/telemetry/__init__.py` | Package exports | 10 |
| `sindri/telemetry/collector.py` | TelemetryCollector with EventBus subscription, rolling stats | 370 |
| `sindri/telemetry/exporter.py` | TraceExporter for JSON export and regression comparison | 285 |
| `tests/test_telemetry.py` | 39 unit tests | 550 |

### Modified Files
| File | Changes |
|------|---------|
| `sindri/core/events.py` | Added `TELEMETRY_TICK`, `TELEMETRY_SNAPSHOT` event types |
| `sindri/core/event_schemas.py` | Added 6 Pydantic models: `VRAMSnapshot`, `ConcurrencySnapshot`, `AgentTimingStats`, `ToolTimingStats`, `TelemetryTickData`, `TelemetrySnapshotData` |
| `sindri/core/hierarchical.py` | Emit ITERATION_END with duration_ms, add duration_ms to TOOL_CALLED |
| `sindri/web/server.py` | Added SSE endpoint `/api/metrics/live`, snapshot/history endpoints, TelemetryCollector lifecycle |
| `sindri/cli.py` | Added `sindri telemetry` command group (stream/snapshot/export/compare) |
| `STATUS.md` | Updated with feature and test count (4,036) |
| `ROADMAP.md` | Marked Item 7 complete |
| `FACTS.md` | Updated test count and capabilities |

## Key Implementation Details

### 1. TelemetryCollector (`sindri/telemetry/collector.py`)
- Subscribes to EventBus: `ITERATION_START/END`, `TOOL_CALLED`, `MODEL_LOADED`, `TASK_STATUS_CHANGED`
- `RollingStats` helper class: sliding 100-sample window for avg/p95/success_rate
- Time-series history: 5 minutes of VRAM and concurrency snapshots (150 samples at 2s intervals)
- Periodic `TELEMETRY_TICK` events emitted every 2 seconds via async loop
- Callbacks for SSE streaming (`add_tick_callback()`, `remove_tick_callback()`)
- **NEW:** Optional session_id in `start()`, `set_session()` method for later binding

### 2. TraceExporter (`sindri/telemetry/exporter.py`)
- `export_session_trace()`: Exports metrics, environment snapshot, audit log to JSON
- **NEW:** `include_tool_outputs=True` loads full tool outputs from ToolOutputStore
- `compare_traces()`: Detects regressions (>20% slower) and improvements (>10% faster)
- `get_trace_summary()`: Quick overview of trace contents

### 3. SSE Endpoint (`sindri/web/server.py`)
- `GET /api/metrics/live`: Server-Sent Events stream for real-time telemetry
- `GET /api/metrics/telemetry/snapshot`: On-demand full snapshot
- `GET /api/metrics/vram/history`: VRAM time-series for charts
- `GET /api/metrics/concurrency/history`: Concurrency time-series for charts
- **NEW:** TelemetryCollector started on API init, uses real stats instead of synthetic

### 4. Event Emission (`sindri/core/hierarchical.py`)
- **NEW:** ITERATION_END emitted with `duration_ms` after each iteration
- **NEW:** TOOL_CALLED includes `duration_ms` field

### 5. CLI Commands (`sindri/cli.py`)
- `sindri telemetry stream [--url URL] [--format table|json]` - Stream live telemetry
- `sindri telemetry snapshot [--url URL]` - Get current snapshot
- `sindri telemetry export <session_id> [-o FILE]` - Export trace to JSON
- `sindri telemetry compare <baseline> <current>` - Regression checking

## Tests Run

```bash
.venv/bin/pytest tests/test_telemetry.py -v
# 39 passed in 2.33s

.venv/bin/pytest tests/ -v --tb=no -q
# 4036 passed, 13 skipped in 29.50s
```

### Test Coverage Areas
- `RollingStats`: add_sample, avg_ms, p95_ms, success_rate, rolling window
- `TelemetryCollector`: start/stop, iteration tracking, tool tracking, tick emission, callbacks
- Pydantic schemas: all 6 new models serialization
- `TraceExporter`: export, compare, regression/improvement detection
- EventBus: unsubscribe functionality
- Event type registration

## Design Decisions

1. **SSE over WebSocket**: Browser-friendly, works with `curl -N`, simpler client code
2. **Rolling window (100 samples)**: Provides recent p95 while preserving total counts
3. **2-second tick interval**: Balances responsiveness with overhead
4. **Regression threshold**: 20% slowdown = regression, 10% speedup = improvement
5. **Optional session_id**: Allows TelemetryCollector to start before any session begins

## Usage Examples

```bash
# Stream live telemetry in table format
sindri telemetry stream --url http://localhost:8000

# Export session trace with full tool outputs
sindri telemetry export abc12345 -o trace.json --include-outputs

# Compare traces for regression
sindri telemetry compare baseline.json current.json

# curl SSE endpoint
curl -N http://localhost:8000/api/metrics/live
```

## Files for Focused Review

1. `sindri/telemetry/collector.py:134-170` - TelemetryCollector start/stop and set_session
2. `sindri/telemetry/collector.py:182-220` - Tick loop and snapshot generation
3. `sindri/telemetry/exporter.py:140-175` - include_tool_outputs implementation
4. `sindri/web/server.py:287-297` - TelemetryCollector lifecycle in SindriAPI
5. `sindri/core/hierarchical.py:1044-1060` - ITERATION_END emission

## Next Feature

The next item on the ROADMAP is **Item 8: Agents as Plugins** - SDK for packaging agents + prompts + tests, compatibility validation, marketplace metadata.
