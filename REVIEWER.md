# Code Review Summary: Plan-First Execution Feature

**Feature:** ROADMAP.md Item 2 - Plan-First Execution
**Date:** 2026-01-21
**Author:** Junior Developer (Claude Code)
**Reviewer:** ChatGPT (Senior Team Member)

## Summary

Implemented the Plan-First Execution feature, which adds persistent execution plans with user approval gates, step-level checkpointing, and the ability to re-run individual steps.

## Requirements Addressed

From ROADMAP.md Item 2:
1. **Persist plans with user approval gates** - Plans are saved to SQLite database and require explicit user approval before execution begins
2. **Step-level checkpointing and re-run of individual steps** - Each step can save checkpoints and be re-run independently
3. **Partial results + explicit acceptance per step** - Users can accept or reject step results before proceeding

## Files Created (4 new files)

| File | Lines | Purpose |
|------|-------|---------|
| `sindri/core/plan_execution.py` | ~380 | Dataclasses: PersistentPlan, PersistentPlanStep, StepCheckpoint, StepResult, enums |
| `sindri/persistence/plans.py` | ~330 | PlanStore class for SQLite CRUD operations |
| `sindri/core/plan_executor.py` | ~420 | PlanExecutor class for orchestrating step execution |
| `tests/test_plan_execution.py` | ~500 | 30 comprehensive tests |

## Files Modified (7 existing files)

| File | Changes |
|------|---------|
| `sindri/persistence/database.py` | Added `execution_plans` and `plan_steps` tables; bumped SCHEMA_VERSION to 6 |
| `sindri/core/events.py` | Added 15 new event types for plan/step lifecycle |
| `sindri/core/event_schemas.py` | Added 15 Pydantic payload models for new events |
| `sindri/tools/planning.py` | Updated ProposePlanTool to persist plans and emit events |
| `sindri/tui/app.py` | Added event handlers for plan/step display in TUI |
| `sindri/web/server.py` | Added 10 REST API endpoints for plan management |
| `STATUS.md`, `ROADMAP.md` | Updated documentation |

## Key Design Decisions

1. **Database Schema**: Two new tables (`execution_plans`, `plan_steps`) with proper foreign keys and indexes
2. **Event-Driven Architecture**: 15 new events allow TUI/Web UI to react to plan execution state changes
3. **Approval Flow**: Steps emit `STEP_AWAITING_APPROVAL` and pause until user responds
4. **Checkpoint Storage**: Checkpoints stored as JSON in `checkpoint_json` column for crash recovery
5. **Backward Compatibility**: ProposePlanTool maintains compatibility with existing registry (accepts `work_dir` parameter)

## New REST API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/plans` | GET | List plans with optional status/task_id filtering |
| `/api/plans/{id}` | GET | Get plan details with all steps |
| `/api/plans/{id}/approve` | POST | Approve plan for execution |
| `/api/plans/{id}/reject` | POST | Reject plan |
| `/api/plans/{id}/steps` | GET | List steps for a plan |
| `/api/plans/{id}/steps/{num}` | GET | Get specific step |
| `/api/plans/{id}/steps/{num}/approve` | POST | Approve step execution |
| `/api/plans/{id}/steps/{num}/reject` | POST | Reject/skip step |
| `/api/plans/{id}/steps/{num}/accept` | POST | Accept step result |
| `/api/plans/{id}/steps/{num}/rerun` | POST | Re-run step |

## Test Coverage

- 30 new tests added in `test_plan_execution.py`
- Tests cover: dataclass serialization, PlanStore CRUD, PlanExecutor logic, approval workflows, checkpointing
- All 3,901 tests pass (previously 3,871)

## Potential Areas for Review

1. **Approval Timeout Handling**: Currently defaults to approve on timeout - is this desired behavior?
2. **PlanExecutor Integration**: The executor is mostly standalone; full integration with HierarchicalAgentLoop would require additional work
3. **Concurrent Access**: No explicit locking for database operations - could be an issue with multiple TUI/web clients
4. **Event Payload Size**: Step results in events are truncated to 500 chars - may need adjustment

## Commands to Test

```bash
# Run all tests
.venv/bin/pytest tests/ -v --tb=no -q

# Run plan execution tests specifically
.venv/bin/pytest tests/test_plan_execution.py -v

# Run planning tests
.venv/bin/pytest tests/test_planning.py -v
```
