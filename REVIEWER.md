# Review Summary: Record Fallback Model in Session Metadata

**Reviewer:** ChatGPT (Senior Reviewer)
**Date:** 2026-01-23
**Author:** Claude Opus 4.5

## Summary

Implemented fallback model recording in session metadata when model degradation occurs. When an agent's primary model can't load due to VRAM constraints and falls back to a smaller model, the session snapshot now records the original model requested, the fallback model used, and the reason for degradation.

## Problem

When model degradation occurred, the session metadata didn't track:
1. Whether fallback was used vs. primary model
2. What the original primary model was
3. Why fallback was needed (e.g., insufficient VRAM)

Additionally, there was a bug in `hierarchical.py:349` where new sessions were created with `agent.model` instead of `model_to_use`, so degraded sessions recorded the wrong model name.

## Solution

1. Added three optional fields to `EnvironmentSnapshot`:
   - `primary_model`: Original requested model (when degradation occurred)
   - `fallback_model_used`: Fallback model used (when degradation occurred)
   - `degradation_reason`: Why fallback was needed

2. Updated `SnapshotCapture.capture()` to accept the new fallback parameters

3. Fixed session creation in `hierarchical.py` to use `model_to_use` instead of `agent.model`

4. Updated snapshot capture call to pass fallback info when degradation detected

## Files Changed

| File | Changes |
|------|---------|
| `sindri/persistence/snapshots.py` | Add 3 fallback fields to `EnvironmentSnapshot`, update `to_dict()` and `from_dict()` |
| `sindri/replay/snapshot.py` | Update `capture()` signature and implementation to accept fallback params |
| `sindri/core/hierarchical.py` | Fix session creation (line 349), add degradation detection, pass fallback info to snapshot |
| `tests/test_model_degradation.py` | Add 9 tests for fallback recording functionality |
| `STATUS.md` | Add entry, update test count to 4,017 |
| `ROADMAP.md` | Mark junior task and item 11 as complete |
| `FACTS.md` | Update test count |

## Key Implementation Details

### 1. EnvironmentSnapshot Fields (`sindri/persistence/snapshots.py:95-100`)
```python
@dataclass
class EnvironmentSnapshot:
    # ... existing fields ...
    # Fallback tracking for model degradation
    primary_model: Optional[str] = None  # Original requested model (when degraded)
    fallback_model_used: Optional[str] = None  # Fallback model used (when degraded)
    degradation_reason: Optional[str] = None  # Why fallback was needed
```

### 2. SnapshotCapture Signature (`sindri/replay/snapshot.py:39-57`)
```python
async def capture(
    self,
    model: str,
    inference_params: Optional[InferenceParams] = None,
    primary_model: Optional[str] = None,
    fallback_model_used: Optional[str] = None,
    degradation_reason: Optional[str] = None,
) -> EnvironmentSnapshot:
```

### 3. Hierarchical Loop Changes (`sindri/core/hierarchical.py:346-372`)
```python
# Fix: Use model_to_use instead of agent.model for new sessions
session = await self.state.create_session(task.description, model_to_use)

# Track degradation and pass to snapshot
degraded = active_model is not None and active_model != agent.model
if is_new_session:
    snapshot = await self._snapshot_capture.capture(
        session.model,
        primary_model=agent.model if degraded else None,
        fallback_model_used=active_model if degraded else None,
        degradation_reason="insufficient_vram" if degraded else None,
    )
```

## Tests Run

```bash
.venv/bin/pytest tests/test_model_degradation.py tests/test_replay.py -v --tb=short
# 63 passed in 1.39s

.venv/bin/pytest tests/ -v --tb=short -q
# 4017 passed, 13 skipped in 31.59s
```

New tests added:
- `TestEnvironmentSnapshotFallback::test_fallback_fields_exist`
- `TestEnvironmentSnapshotFallback::test_fallback_fields_optional`
- `TestEnvironmentSnapshotFallback::test_to_dict_with_fallback`
- `TestEnvironmentSnapshotFallback::test_to_dict_without_fallback`
- `TestEnvironmentSnapshotFallback::test_from_dict_with_fallback`
- `TestEnvironmentSnapshotFallback::test_from_dict_backward_compatible`
- `TestSnapshotCaptureFallback::test_capture_without_fallback`
- `TestSnapshotCaptureFallback::test_capture_with_fallback`
- `TestSnapshotCaptureFallback::test_capture_roundtrip`

## Backward Compatibility

- New fields are Optional with None defaults
- `to_dict()` only includes fallback fields when set (non-None)
- `from_dict()` uses `.get()` so existing snapshots without these fields load correctly
- No database schema migration needed (stored in JSON)

## Files for Focused Review

1. `sindri/persistence/snapshots.py:86-141` - EnvironmentSnapshot class with new fields
2. `sindri/replay/snapshot.py:39-90` - SnapshotCapture.capture() method
3. `sindri/core/hierarchical.py:346-372` - Session creation and snapshot capture
4. `tests/test_model_degradation.py:92-180` - New test classes

## Next Features

Remaining junior tasks from ROADMAP:
- Wire TelemetryCollector to the active orchestrator scheduler/model manager
- Emit `MODEL_LOADED` events to populate telemetry agent to model tracking
