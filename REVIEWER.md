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

## Code Review Fixes Applied

### Round 1 (Initial Review)
- **PlanStore database initialization**: Changed to use `Database` instance and call `await self.db.initialize()` before all CRUD operations
- **ProposePlanTool registry wiring**: `ToolRegistry.default()` now creates a default `PlanStore()` and passes it to `ProposePlanTool`

### Round 2 (Re-review)
- **Event context propagation**: Added `ToolRegistry.set_task_context()` to propagate `task_id`, `session_id`, `event_bus` to tools like `ProposePlanTool`
- **Plan approval gates in orchestration**: Task pauses with `WAITING` status after `propose_plan`, emits `PLAN_AWAITING_APPROVAL` event
- **DelegationManager integration**: Added `plan_approved()` and `plan_rejected()` methods to resume/fail waiting tasks

### Round 3 (Final Review)
- **Event subscription wiring**: Orchestrator now subscribes to `PLAN_APPROVED` and `PLAN_REJECTED` events and calls `DelegationManager.plan_approved()`/`.plan_rejected()`
- **Event data includes task_id**: `PlanExecutor` now includes `task_id` in event data for approval/rejection
- **Documented two modes of plan execution**: Agent-guided (default) vs step-by-step (PlanExecutor)

## Two Modes of Plan Execution

### Mode 1: Agent-Guided Execution (Default)
When an agent proposes a plan via ProposePlanTool:
- The plan is persisted to the database with PROPOSED status
- The task pauses with WAITING status until the user approves
- On approval, the task resumes and the agent continues execution
- The agent uses the plan as guidance but executes autonomously
- This integrates with the main HierarchicalAgentLoop orchestration

### Mode 2: Step-by-Step Execution (PlanExecutor)
For fine-grained control, use PlanExecutor directly:
- Execute plans step-by-step with approval gates per step
- Checkpoint support for crash recovery and resume
- Re-run individual steps that failed
- Explicit acceptance/rejection of step results

## Files Created (4 new files)

| File | Lines | Purpose |
|------|-------|---------|
| `sindri/core/plan_execution.py` | ~400 | Dataclasses: PersistentPlan, PersistentPlanStep, StepCheckpoint, StepResult, enums |
| `sindri/persistence/plans.py` | ~350 | PlanStore class for SQLite CRUD operations |
| `sindri/core/plan_executor.py` | ~420 | PlanExecutor class for orchestrating step execution |
| `tests/test_plan_execution.py` | ~500 | 30 comprehensive tests |

## Files Modified

| File | Changes |
|------|---------|
| `sindri/persistence/database.py` | Added `execution_plans` and `plan_steps` tables; bumped SCHEMA_VERSION to 6 |
| `sindri/core/events.py` | Added 16 new event types for plan/step lifecycle (including `PLAN_AWAITING_APPROVAL`) |
| `sindri/core/event_schemas.py` | Added 16 Pydantic payload models for new events |
| `sindri/tools/planning.py` | Updated ProposePlanTool with `set_task_context()` method |
| `sindri/tools/registry.py` | Added `set_task_context()` method; passes `event_bus` and creates `PlanStore` |
| `sindri/core/orchestrator.py` | Subscribes to `PLAN_APPROVED`/`PLAN_REJECTED` events; passes `event_bus` to registry |
| `sindri/core/hierarchical.py` | Calls `tools.set_task_context()` before each task; pauses on plan proposal |
| `sindri/core/delegation.py` | Added `plan_approved()` and `plan_rejected()` methods |
| `sindri/tui/app.py` | Added event handlers for plan/step display in TUI |
| `sindri/web/server.py` | Added 10 REST API endpoints for plan management |

## New REST API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/plans` | GET | List plans with optional status/task_id filtering |
| `/api/plans/{id}` | GET | Get plan details with all steps |
| `/api/plans/{id}/approve` | POST | Approve plan for execution (returns task_id) |
| `/api/plans/{id}/reject` | POST | Reject plan (returns task_id) |
| `/api/plans/{id}/steps` | GET | List steps for a plan |
| `/api/plans/{id}/steps/{num}` | GET | Get specific step |
| `/api/plans/{id}/steps/{num}/approve` | POST | Approve step execution |
| `/api/plans/{id}/steps/{num}/reject` | POST | Reject/skip step |
| `/api/plans/{id}/steps/{num}/accept` | POST | Accept step result |
| `/api/plans/{id}/steps/{num}/rerun` | POST | Re-run step |

## Test Coverage

- 30 new tests added in `test_plan_execution.py`
- Tests cover: dataclass serialization, PlanStore CRUD, PlanExecutor logic, approval workflows, checkpointing
- All 3,901 tests pass

## Commands to Test

```bash
# Run all tests
.venv/bin/pytest tests/ -v --tb=no -q

# Run plan execution tests specifically
.venv/bin/pytest tests/test_plan_execution.py -v

# Run planning tests
.venv/bin/pytest tests/test_planning.py -v

# Run delegation tests
.venv/bin/pytest tests/test_delegation.py -v
```
