# Code Review Summary

**Feature:** Tighten ModelManager.can_load() VRAM Check
**Date:** 2026-01-20
**Author:** Junior Claude
**Reviewer:** ChatGPT (Senior)

---

## Problem

The `ModelManager.can_load()` method in `sindri/llm/manager.py` had a bug that caused **false positives** - it would incorrectly return `True` when there wasn't actually enough VRAM available.

### The Bug (Line 101)

```python
can = free_vram >= required_vram or len(self.loaded) > 0
```

The condition `len(self.loaded) > 0` assumed any loaded model could be evicted to make space. This ignored:
1. Models in `keep_warm` set that **cannot** be evicted
2. Even after evicting all evictable models, freed VRAM might still be insufficient

### Impact

The scheduler would over-schedule tasks beyond available VRAM, risking OOM crashes or system instability.

---

## Solution

### 1. Added Helper Method: `_calculate_potential_free_vram()`

Location: `sindri/llm/manager.py:124-139`

```python
def _calculate_potential_free_vram(self) -> float:
    """Calculate maximum VRAM available if all evictable models were unloaded."""
    current_free = self._get_free_vram()
    evictable_vram = sum(
        m.vram_gb
        for m in self.loaded.values()
        if m.name not in self.keep_warm
    )
    return current_free + evictable_vram
```

This calculates the **potential** free VRAM by adding the current free VRAM plus the VRAM from models that CAN be evicted (not in `keep_warm`).

### 2. Fixed `can_load()` Logic

Location: `sindri/llm/manager.py:91-139`

The method now returns `True` ONLY if:
1. Model is already loaded, OR
2. Free VRAM >= required, OR
3. Evicting non-keep_warm models would free enough space

---

## Files Changed

| File | Changes |
|------|---------|
| `sindri/llm/manager.py` | Added `_calculate_potential_free_vram()` helper, fixed `can_load()` logic |
| `tests/test_model_caching.py` | Added `TestCanLoadAccuracy` class with 12 new tests |
| `STATUS.md` | Updated test count (3784 -> 3804), added recent change |
| `ROADMAP.md` | Marked junior task as complete |

---

## Tests Added (12 new tests)

All in `tests/test_model_caching.py::TestCanLoadAccuracy`:

1. `test_can_load_already_loaded_model` - Already loaded models always return True
2. `test_can_load_sufficient_free_vram` - Returns True when free VRAM is sufficient
3. `test_can_load_insufficient_free_vram_no_models` - Returns False when no evictable models
4. `test_can_load_false_when_all_keep_warm` - Returns False when all models are keep_warm
5. `test_can_load_true_when_eviction_helps` - Returns True when eviction frees enough
6. `test_can_load_false_when_eviction_insufficient` - Returns False even after eviction
7. `test_can_load_mixed_keep_warm_and_evictable` - Handles mixed scenarios
8. `test_can_load_partial_vram_used_evictable` - Original bug scenario (evictable model)
9. `test_can_load_partial_vram_used_keep_warm` - Corrected scenario (keep_warm model)
10. `test_calculate_potential_free_vram_no_models` - Helper returns available when empty
11. `test_calculate_potential_free_vram_with_evictable` - Helper includes evictable VRAM
12. `test_calculate_potential_free_vram_with_keep_warm` - Helper excludes keep_warm VRAM

---

## Test Results

```
tests/test_model_caching.py: 37 passed
All tests: 3804 passed, 13 skipped, 8 warnings
```

---

## Edge Cases Handled

| Scenario | Expected | Tested |
|----------|----------|--------|
| Model already loaded | True | Yes |
| Sufficient free VRAM | True | Yes |
| No models, insufficient VRAM | False | Yes |
| All models keep_warm, insufficient | False | Yes |
| Eviction would free enough | True | Yes |
| Eviction still insufficient | False | Yes |
| Required > total available | False | Yes |
| Mixed keep_warm and evictable | Correct | Yes |

---

## Potential Concerns for Review

1. **Performance**: The new check is still O(n) where n = number of loaded models. This is unchanged from the original.

2. **Non-locking**: The method remains a non-locking check as required for scheduler use. It does not acquire any locks or modify state.

3. **Backward Compatibility**: This is a behavioral fix that makes `can_load()` more restrictive. The previous behavior was incorrect (false positives), so existing code should benefit from the fix.

4. **Thread Safety**: The `keep_warm` set is read-only during the check. Write operations (`add_keep_warm`, `remove_keep_warm`) are separate methods that should be called before scheduling starts.
