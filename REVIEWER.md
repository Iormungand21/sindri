# Phase 16: Event + API Contract v1 - Implementation Summary

**Date:** 2026-01-20
**Author:** Claude Opus 4.5
**Feature:** ROADMAP Item 1 - API + Contract Stability

---

## Overview

Implemented versioned JSON schemas for all WebSocket events and REST API endpoints, enabling auto-generation of TypeScript types and contract testing.

---

## Changes Made

### 1. Fixed Failing WebSocket Test

**File:** `sindri/web/server.py`

**Problem:** `_broadcast_event_sync()` was calling `asyncio.create_task()` from a synchronous context (the EventBus handler), which failed with "no running event loop" when called from a different thread.

**Solution:**
- Store reference to the server's event loop in `_event_loop` during initialization
- Use `loop.call_soon_threadsafe()` to schedule async broadcasts from any thread
- Handle gracefully when no event loop is available

```python
# Before
def _broadcast_event_sync(self, event: Event):
    asyncio.create_task(self._broadcast_event(event))  # Fails from sync context!

# After
def _broadcast_event_sync(self, event: Event):
    if self._event_loop is None:
        return
    try:
        self._event_loop.call_soon_threadsafe(
            lambda: self._event_loop.create_task(self._broadcast_event(event))
        )
    except RuntimeError:
        log.debug("event_broadcast_skipped_loop_closed", ...)
```

---

### 2. Event Payload Schemas

**New File:** `sindri/core/event_schemas.py` (~350 lines)

Created strongly-typed Pydantic models for all 24 event types:

| Event Type | Model | Required Fields |
|------------|-------|-----------------|
| TASK_CREATED | TaskCreatedData | task_id |
| TASK_STATUS_CHANGED | TaskStatusChangedData | task_id, status |
| AGENT_OUTPUT | AgentOutputData | task_id, agent, text |
| TOOL_CALLED | ToolCalledData | task_id, name, success |
| DELEGATION_START | DelegationStartData | task_id, parent_task_id, parent_agent, child_agent, task |
| DELEGATION_COMPLETE | DelegationCompleteData | task_id, parent_task_id, parent_agent, child_agent, status |
| DELEGATION_FAILED | DelegationFailedData | task_id, parent_task_id, parent_agent, child_agent |
| MODEL_LOADED | ModelLoadedData | model |
| MODEL_UNLOADED | ModelUnloadedData | model |
| MODEL_DEGRADED | ModelDegradedData | task_id, agent, primary_model, fallback_model |
| ERROR | ErrorData | error |
| ITERATION_START | IterationStartData | task_id, iteration, agent |
| ITERATION_END | IterationEndData | task_id, iteration |
| ITERATION_WARNING | IterationWarningData | task_id, remaining, message |
| PARALLEL_BATCH_START | ParallelBatchStartData | batch_id, task_ids, count |
| PARALLEL_BATCH_END | ParallelBatchEndData | batch_id, completed, failed |
| STREAMING_START | StreamingStartData | task_id, agent, model |
| STREAMING_TOKEN | StreamingTokenData | task_id, agent, token |
| STREAMING_END | StreamingEndData | task_id, agent, content_length |
| PLAN_PROPOSED | PlanProposedData | task_id, agent, plan, formatted, step_count |
| PLAN_APPROVED | PlanApprovedData | task_id |
| PLAN_REJECTED | PlanRejectedData | task_id |
| PATTERN_LEARNED | PatternLearnedData | task_id, pattern_id, agent, iterations, tools |
| METRICS_UPDATED | MetricsUpdatedData | task_id, session_id, iteration, duration_seconds |

Helper functions provided:
- `get_event_schema(event_type)` - Get JSON Schema for one event type
- `get_all_event_schemas()` - Get JSON Schema for all event types
- `validate_event_data(event_type, data)` - Validate event data against schema

---

### 3. API Schema Endpoints

**File:** `sindri/web/server.py`

Added three new endpoints:

```
GET /api/version
{
    "version": "1.0.0",
    "compatible_versions": ["1.0.0"],
    "deprecated_versions": []
}

GET /api/schema
{
    "version": "1.0.0",
    "openapi_url": "/openapi.json",
    "event_types": { <24 JSON Schemas> },
    "event_type_list": ["TASK_CREATED", "TASK_STATUS_CHANGED", ...]
}

GET /api/schema/events/{event_type}
{
    "event_type": "TASK_CREATED",
    "schema": { <JSON Schema> }
}
```

---

### 4. API Version Header Middleware

**File:** `sindri/web/server.py`

Added HTTP middleware that adds `X-Sindri-API-Version: 1.0.0` header to all responses.

---

### 5. TypeScript Type Generation

**New File:** `scripts/generate_typescript_types.py`

Script that generates TypeScript types from Pydantic models:
- Converts JSON Schema to TypeScript interfaces
- Generates `EventType` union type
- Creates `EventTypeDataMap` for type-safe event handling
- Generates `TypedWebSocketEvent` discriminated union
- Includes `isEventType()` type guard helper
- Exports `ALL_EVENT_TYPES` constant array

**Generated File:** `sindri/web/static/src/types/events.generated.ts`

Usage: `python scripts/generate_typescript_types.py`

---

### 6. Contract Tests

**New File:** `tests/test_event_contracts.py` (50 tests)

| Test Class | Tests | Coverage |
|------------|-------|----------|
| TestEventSchemaCompleteness | 3 | All EventTypes have schemas |
| TestEventSchemaValidation | 32 | Valid/invalid data validation |
| TestValidateEventDataFunction | 3 | Helper function tests |
| TestGetEventSchema | 3 | JSON Schema generation |
| TestAPIVersioning | 2 | Version format validation |
| TestSchemaAPIEndpoints | 5 | /api/version, /api/schema endpoints |
| TestWebSocketEventContract | 2 | WebSocket message validation |

---

## Test Results

- **Before:** 3734 tests passing, 1 failing
- **After:** 3784 tests passing, 0 failing (+50 new tests)

---

## Files Changed

| File | Change Type | Lines |
|------|-------------|-------|
| `sindri/core/event_schemas.py` | New | ~350 |
| `scripts/generate_typescript_types.py` | New | ~220 |
| `sindri/web/static/src/types/events.generated.ts` | New | ~400 |
| `tests/test_event_contracts.py` | New | ~320 |
| `sindri/web/server.py` | Modified | +60 |
| `STATUS.md` | Modified | +30 |
| `ROADMAP.md` | Modified | +3 |

---

## API Contract Version

**Version:** 1.0.0

This establishes the v1 contract for:
- All 24 WebSocket event payload structures
- REST API response formats (via existing OpenAPI at `/openapi.json`)
- Version header (`X-Sindri-API-Version`) for all HTTP responses

---

## Potential Review Concerns

1. **Event payload schemas are permissive:** Optional fields are used generously to accommodate existing event emissions that may not include all data. Stricter validation could be added as a future enhancement.

2. **TypeScript generation is Python-based:** The script requires running from Python. Could be integrated into npm scripts or converted to a Node.js implementation if needed.

3. **No breaking change detection:** Currently just establishes v1. Future versions would need a mechanism to detect and flag breaking changes.
