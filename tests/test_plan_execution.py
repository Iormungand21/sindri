"""Tests for Plan-First Execution feature (ROADMAP.md Item 2).

Tests cover:
- Plan and step dataclasses
- Plan persistence (PlanStore)
- Plan executor logic
- Approval workflows
- Checkpoint and resume
"""

import pytest
import asyncio
import tempfile
from datetime import datetime
from pathlib import Path

from sindri.core.plan_execution import (
    PersistentPlan,
    PersistentPlanStep,
    PlanStatus,
    StepStatus,
    StepCheckpoint,
    StepResult,
    ApprovalStatus,
)
from sindri.persistence.plans import PlanStore
from sindri.persistence.database import Database
from sindri.core.plan_executor import PlanExecutor, PlanExecutorConfig
from sindri.core.events import EventBus, EventType


# ============== Fixtures ==============


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


@pytest.fixture
async def initialized_db(temp_db):
    """Initialize database with schema and return Database instance."""
    db = Database(temp_db)
    await db.initialize()
    return db


@pytest.fixture
async def plan_store(initialized_db):
    """Create a PlanStore with initialized database."""
    return PlanStore(database=initialized_db)


@pytest.fixture
def sample_plan():
    """Create a sample plan for testing."""
    steps = [
        PersistentPlanStep(
            step_number=1,
            description="Analyze requirements",
            agent="mimir",
            estimated_iterations=3,
            dependencies=[],
        ),
        PersistentPlanStep(
            step_number=2,
            description="Write code",
            agent="huginn",
            estimated_iterations=10,
            dependencies=[1],
        ),
        PersistentPlanStep(
            step_number=3,
            description="Write tests",
            agent="skald",
            estimated_iterations=5,
            dependencies=[2],
        ),
    ]
    return PersistentPlan(
        task_id="test-task-123",
        task_summary="Implement feature X",
        rationale="Standard implementation approach",
        risks=["May require refactoring"],
        status=PlanStatus.PROPOSED,
        total_estimated_vram_gb=10.0,
        steps=steps,
    )


@pytest.fixture
def event_bus():
    """Create an event bus for testing."""
    return EventBus()


# ============== Dataclass Tests ==============


class TestPlanExecution:
    """Tests for plan execution dataclasses."""

    def test_plan_status_enum(self):
        """Test PlanStatus enum values."""
        assert PlanStatus.PROPOSED.value == "proposed"
        assert PlanStatus.APPROVED.value == "approved"
        assert PlanStatus.EXECUTING.value == "executing"
        assert PlanStatus.COMPLETED.value == "completed"

    def test_step_status_enum(self):
        """Test StepStatus enum values."""
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.RUNNING.value == "running"
        assert StepStatus.COMPLETED.value == "completed"
        assert StepStatus.SKIPPED.value == "skipped"

    def test_step_checkpoint_serialization(self):
        """Test StepCheckpoint to_dict and from_dict."""
        checkpoint = StepCheckpoint(
            step_id="step-1",
            iteration=5,
            session_id="session-123",
            messages=[{"role": "user", "content": "test"}],
            tool_results=[{"tool": "read_file", "result": "ok"}],
        )
        data = checkpoint.to_dict()
        restored = StepCheckpoint.from_dict(data)

        assert restored.step_id == checkpoint.step_id
        assert restored.iteration == checkpoint.iteration
        assert restored.session_id == checkpoint.session_id
        assert restored.messages == checkpoint.messages
        assert restored.tool_results == checkpoint.tool_results

    def test_step_result_serialization(self):
        """Test StepResult to_dict and from_dict."""
        result = StepResult(
            success=True,
            output="Task completed",
            iterations_used=5,
            tool_calls=[{"name": "write_file"}],
            files_modified=["src/main.py"],
            error=None,
            metadata={"key": "value"},
        )
        data = result.to_dict()
        restored = StepResult.from_dict(data)

        assert restored.success == result.success
        assert restored.output == result.output
        assert restored.iterations_used == result.iterations_used
        assert restored.files_modified == result.files_modified

    def test_persistent_plan_step_is_ready(self):
        """Test step dependency checking."""
        step = PersistentPlanStep(
            step_number=2,
            description="Test",
            agent="huginn",
            dependencies=[1],
        )

        # Not ready without dependency
        assert not step.is_ready(set())

        # Ready with dependency completed
        assert step.is_ready({1})

    def test_persistent_plan_get_step(self):
        """Test getting step by number."""
        plan = PersistentPlan(
            task_summary="Test",
            steps=[
                PersistentPlanStep(step_number=1, description="A", agent="a"),
                PersistentPlanStep(step_number=2, description="B", agent="b"),
            ],
        )

        step1 = plan.get_step(1)
        assert step1 is not None
        assert step1.description == "A"

        step2 = plan.get_step(2)
        assert step2 is not None
        assert step2.description == "B"

        step3 = plan.get_step(3)
        assert step3 is None

    def test_persistent_plan_get_next_ready_step(self):
        """Test getting next ready step."""
        plan = PersistentPlan(
            task_summary="Test",
            steps=[
                PersistentPlanStep(
                    step_number=1, description="A", agent="a", dependencies=[]
                ),
                PersistentPlanStep(
                    step_number=2, description="B", agent="b", dependencies=[1]
                ),
            ],
        )

        # First step should be ready
        next_step = plan.get_next_ready_step()
        assert next_step is not None
        assert next_step.step_number == 1

        # After completing step 1, step 2 should be ready
        plan.steps[0].status = StepStatus.COMPLETED
        next_step = plan.get_next_ready_step()
        assert next_step is not None
        assert next_step.step_number == 2

    def test_persistent_plan_all_steps_complete(self):
        """Test all_steps_complete check."""
        plan = PersistentPlan(
            task_summary="Test",
            steps=[
                PersistentPlanStep(step_number=1, description="A", agent="a"),
                PersistentPlanStep(step_number=2, description="B", agent="b"),
            ],
        )

        assert not plan.all_steps_complete()

        plan.steps[0].status = StepStatus.COMPLETED
        assert not plan.all_steps_complete()

        plan.steps[1].status = StepStatus.COMPLETED
        assert plan.all_steps_complete()

        # Skipped also counts as complete
        plan.steps[1].status = StepStatus.SKIPPED
        assert plan.all_steps_complete()

    def test_persistent_plan_serialization(self, sample_plan):
        """Test PersistentPlan to_dict and from_dict."""
        data = sample_plan.to_dict()
        restored = PersistentPlan.from_dict(data)

        assert restored.id == sample_plan.id
        assert restored.task_summary == sample_plan.task_summary
        assert restored.rationale == sample_plan.rationale
        assert restored.risks == sample_plan.risks
        assert len(restored.steps) == len(sample_plan.steps)
        assert restored.steps[0].description == sample_plan.steps[0].description


# ============== PlanStore Tests ==============


class TestPlanStore:
    """Tests for plan persistence."""

    @pytest.mark.asyncio
    async def test_save_and_load_plan(self, plan_store, sample_plan):
        """Test saving and loading a plan."""
        plan_id = await plan_store.save_plan(sample_plan)
        assert plan_id == sample_plan.id

        loaded = await plan_store.load_plan(plan_id)
        assert loaded is not None
        assert loaded.id == sample_plan.id
        assert loaded.task_summary == sample_plan.task_summary
        assert len(loaded.steps) == 3

    @pytest.mark.asyncio
    async def test_update_plan_status(self, plan_store, sample_plan):
        """Test updating plan status."""
        await plan_store.save_plan(sample_plan)

        # Update to approved
        now = datetime.now()
        success = await plan_store.update_plan_status(
            sample_plan.id, PlanStatus.APPROVED, approved_at=now
        )
        assert success

        loaded = await plan_store.load_plan(sample_plan.id)
        assert loaded.status == PlanStatus.APPROVED
        assert loaded.approved_at is not None

    @pytest.mark.asyncio
    async def test_list_plans(self, plan_store, sample_plan):
        """Test listing plans."""
        await plan_store.save_plan(sample_plan)

        # List all
        plans = await plan_store.list_plans()
        assert len(plans) == 1

        # List by status
        plans = await plan_store.list_plans(status=PlanStatus.PROPOSED)
        assert len(plans) == 1

        plans = await plan_store.list_plans(status=PlanStatus.APPROVED)
        assert len(plans) == 0

    @pytest.mark.asyncio
    async def test_list_pending_plans(self, plan_store, sample_plan):
        """Test listing pending plans."""
        await plan_store.save_plan(sample_plan)

        pending = await plan_store.list_pending_plans()
        assert len(pending) == 1
        assert pending[0].id == sample_plan.id

    @pytest.mark.asyncio
    async def test_delete_plan(self, plan_store, sample_plan):
        """Test deleting a plan."""
        await plan_store.save_plan(sample_plan)

        success = await plan_store.delete_plan(sample_plan.id)
        assert success

        loaded = await plan_store.load_plan(sample_plan.id)
        assert loaded is None

    @pytest.mark.asyncio
    async def test_save_and_load_step(self, plan_store, sample_plan):
        """Test saving and loading individual steps."""
        await plan_store.save_plan(sample_plan)
        step = sample_plan.steps[0]

        # Update step
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now()
        await plan_store.save_step(step)

        # Load and verify
        loaded = await plan_store.load_step(step.id)
        assert loaded is not None
        assert loaded.status == StepStatus.RUNNING
        assert loaded.started_at is not None

    @pytest.mark.asyncio
    async def test_update_step_status(self, plan_store, sample_plan):
        """Test updating step status."""
        await plan_store.save_plan(sample_plan)
        step = sample_plan.steps[0]

        now = datetime.now()
        success = await plan_store.update_step_status(
            step.id,
            StepStatus.COMPLETED,
            completed_at=now,
            iterations_used=5,
        )
        assert success

        loaded = await plan_store.load_step(step.id)
        assert loaded.status == StepStatus.COMPLETED
        assert loaded.iterations_used == 5

    @pytest.mark.asyncio
    async def test_save_step_checkpoint(self, plan_store, sample_plan):
        """Test saving and loading step checkpoints."""
        await plan_store.save_plan(sample_plan)
        step = sample_plan.steps[0]

        checkpoint = StepCheckpoint(
            step_id=step.id,
            iteration=3,
            session_id="test-session",
            messages=[{"role": "user", "content": "test"}],
        )
        await plan_store.save_step_checkpoint(step.id, checkpoint)

        loaded = await plan_store.load_step_checkpoint(step.id)
        assert loaded is not None
        assert loaded.iteration == 3
        assert loaded.session_id == "test-session"

    @pytest.mark.asyncio
    async def test_save_step_result(self, plan_store, sample_plan):
        """Test saving step results."""
        await plan_store.save_plan(sample_plan)
        step = sample_plan.steps[0]

        result = StepResult(
            success=True,
            output="Analysis complete",
            iterations_used=3,
            files_modified=["analysis.md"],
        )
        success = await plan_store.save_step_result(step.id, result)
        assert success

        loaded = await plan_store.load_step(step.id)
        assert loaded.result is not None
        assert loaded.result.success
        assert loaded.result.output == "Analysis complete"

    @pytest.mark.asyncio
    async def test_update_step_approval(self, plan_store, sample_plan):
        """Test updating step approval status."""
        await plan_store.save_plan(sample_plan)
        step = sample_plan.steps[0]

        now = datetime.now()
        success = await plan_store.update_step_approval(
            step.id, ApprovalStatus.APPROVED, approved_at=now
        )
        assert success

        loaded = await plan_store.load_step(step.id)
        assert loaded.approval_status == ApprovalStatus.APPROVED
        assert loaded.approved_at is not None

    @pytest.mark.asyncio
    async def test_get_steps_for_plan(self, plan_store, sample_plan):
        """Test getting all steps for a plan."""
        await plan_store.save_plan(sample_plan)

        steps = await plan_store.get_steps_for_plan(sample_plan.id)
        assert len(steps) == 3
        assert steps[0].step_number == 1
        assert steps[1].step_number == 2
        assert steps[2].step_number == 3


# ============== PlanExecutor Tests ==============


class TestPlanExecutor:
    """Tests for plan execution logic."""

    @pytest.mark.asyncio
    async def test_approve_plan(self, plan_store, sample_plan, event_bus):
        """Test approving a plan."""
        await plan_store.save_plan(sample_plan)
        executor = PlanExecutor(plan_store, event_bus=event_bus)

        # Track events
        events = []
        event_bus.subscribe(EventType.PLAN_APPROVED, lambda d: events.append(d))

        success = await executor.approve_plan(sample_plan.id)
        assert success

        # Verify plan status changed
        loaded = await plan_store.load_plan(sample_plan.id)
        assert loaded.status == PlanStatus.APPROVED

        # Verify event emitted
        assert len(events) == 1
        assert events[0]["plan_id"] == sample_plan.id

    @pytest.mark.asyncio
    async def test_reject_plan(self, plan_store, sample_plan, event_bus):
        """Test rejecting a plan."""
        await plan_store.save_plan(sample_plan)
        executor = PlanExecutor(plan_store, event_bus=event_bus)

        # Track events
        events = []
        event_bus.subscribe(EventType.PLAN_REJECTED, lambda d: events.append(d))

        success = await executor.reject_plan(sample_plan.id, reason="Not needed")
        assert success

        loaded = await plan_store.load_plan(sample_plan.id)
        assert loaded.status == PlanStatus.REJECTED

        assert len(events) == 1
        assert events[0]["reason"] == "Not needed"

    @pytest.mark.asyncio
    async def test_execute_step_success(self, plan_store, sample_plan, event_bus):
        """Test executing a step successfully."""
        await plan_store.save_plan(sample_plan)
        step = sample_plan.steps[0]

        # Create executor with mock step executor
        async def mock_executor(step):
            return StepResult(
                success=True, output="Done", iterations_used=3, files_modified=[]
            )

        executor = PlanExecutor(
            plan_store, event_bus=event_bus, step_executor=mock_executor
        )

        # Track events
        started_events = []
        completed_events = []
        event_bus.subscribe(EventType.STEP_STARTED, lambda d: started_events.append(d))
        event_bus.subscribe(
            EventType.STEP_COMPLETED, lambda d: completed_events.append(d)
        )

        result = await executor.execute_step(step)
        assert result.success
        assert result.output == "Done"

        # Verify events
        assert len(started_events) == 1
        assert len(completed_events) == 1

        # Verify step status in database
        loaded = await plan_store.load_step(step.id)
        assert loaded.status == StepStatus.COMPLETED
        assert loaded.iterations_used == 3

    @pytest.mark.asyncio
    async def test_execute_step_failure(self, plan_store, sample_plan, event_bus):
        """Test executing a step that fails."""
        await plan_store.save_plan(sample_plan)
        step = sample_plan.steps[0]

        async def failing_executor(step):
            return StepResult(success=False, output="", iterations_used=1, error="Test error")

        executor = PlanExecutor(
            plan_store, event_bus=event_bus, step_executor=failing_executor
        )

        failed_events = []
        event_bus.subscribe(EventType.STEP_FAILED, lambda d: failed_events.append(d))

        result = await executor.execute_step(step)
        assert not result.success
        assert result.error == "Test error"

        # Verify event
        assert len(failed_events) == 1
        assert failed_events[0]["error"] == "Test error"

        # Verify step status
        loaded = await plan_store.load_step(step.id)
        assert loaded.status == StepStatus.FAILED

    @pytest.mark.asyncio
    async def test_save_checkpoint(self, plan_store, sample_plan, event_bus):
        """Test saving a checkpoint during execution."""
        await plan_store.save_plan(sample_plan)
        step = sample_plan.steps[0]

        executor = PlanExecutor(plan_store, event_bus=event_bus)

        checkpoint_events = []
        event_bus.subscribe(
            EventType.STEP_CHECKPOINTED, lambda d: checkpoint_events.append(d)
        )

        checkpoint = StepCheckpoint(
            step_id=step.id,
            iteration=5,
            session_id="sess-123",
            messages=[{"role": "user", "content": "progress"}],
        )
        await executor.save_checkpoint(step, checkpoint)

        # Verify event
        assert len(checkpoint_events) == 1
        assert checkpoint_events[0]["iteration"] == 5

        # Verify checkpoint saved
        loaded = await plan_store.load_step_checkpoint(step.id)
        assert loaded is not None
        assert loaded.iteration == 5

    @pytest.mark.asyncio
    async def test_rerun_step(self, plan_store, sample_plan, event_bus):
        """Test re-running a step."""
        await plan_store.save_plan(sample_plan)
        step = sample_plan.steps[0]

        # First, complete the step
        step.status = StepStatus.COMPLETED
        step.iterations_used = 5
        await plan_store.save_step(step)

        # Create executor with mock
        async def mock_executor(s):
            return StepResult(success=True, output="Rerun done", iterations_used=3)

        executor = PlanExecutor(
            plan_store, event_bus=event_bus, step_executor=mock_executor
        )

        rerun_events = []
        event_bus.subscribe(
            EventType.STEP_RERUN_REQUESTED, lambda d: rerun_events.append(d)
        )

        result = await executor.rerun_step(step.id)
        assert result is not None
        assert result.success
        assert result.output == "Rerun done"

        # Verify rerun event
        assert len(rerun_events) == 1

    @pytest.mark.asyncio
    async def test_execute_plan_all_steps(self, plan_store, event_bus):
        """Test executing a complete plan with all steps."""
        # Create a simple plan with no approval required
        steps = [
            PersistentPlanStep(
                step_number=1,
                description="Step 1",
                agent="huginn",
                dependencies=[],
                approval_required=False,
            ),
            PersistentPlanStep(
                step_number=2,
                description="Step 2",
                agent="huginn",
                dependencies=[1],
                approval_required=False,
            ),
        ]
        plan = PersistentPlan(
            task_id="test",
            task_summary="Test plan",
            status=PlanStatus.APPROVED,  # Pre-approved
            steps=steps,
        )
        await plan_store.save_plan(plan)

        # Mock executor that succeeds
        call_count = [0]

        async def mock_executor(step):
            call_count[0] += 1
            return StepResult(
                success=True, output=f"Step {step.step_number} done", iterations_used=1
            )

        config = PlanExecutorConfig(auto_approve_simple_steps=True)
        executor = PlanExecutor(
            plan_store, event_bus=event_bus, config=config, step_executor=mock_executor
        )

        result = await executor.execute_plan(plan)

        assert result.success
        assert result.completed_steps == 2
        assert result.failed_steps == 0
        assert call_count[0] == 2

        # Verify plan completed
        loaded = await plan_store.load_plan(plan.id)
        assert loaded.status == PlanStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_plan_with_failure(self, plan_store, event_bus):
        """Test plan execution with a failing step."""
        steps = [
            PersistentPlanStep(
                step_number=1,
                description="Fails",
                agent="huginn",
                dependencies=[],
                approval_required=False,
            ),
            PersistentPlanStep(
                step_number=2,
                description="Never runs",
                agent="huginn",
                dependencies=[1],
                approval_required=False,
            ),
        ]
        plan = PersistentPlan(
            task_id="test",
            task_summary="Failing plan",
            status=PlanStatus.APPROVED,
            steps=steps,
        )
        await plan_store.save_plan(plan)

        async def failing_executor(step):
            return StepResult(success=False, output="", iterations_used=1, error="Failed")

        config = PlanExecutorConfig(auto_approve_simple_steps=True)
        executor = PlanExecutor(
            plan_store, event_bus=event_bus, config=config, step_executor=failing_executor
        )

        result = await executor.execute_plan(plan)

        assert not result.success
        assert result.failed_steps == 1
        assert result.completed_steps == 0

        # Plan should be failed
        loaded = await plan_store.load_plan(plan.id)
        assert loaded.status == PlanStatus.FAILED


# ============== Event Tests ==============


class TestPlanExecutionEvents:
    """Tests for event emission during plan execution."""

    def test_event_types_exist(self):
        """Test that all new event types are defined."""
        # Plan-level events
        assert hasattr(EventType, "PLAN_PERSISTED")
        assert hasattr(EventType, "PLAN_EXECUTION_STARTED")
        assert hasattr(EventType, "PLAN_EXECUTION_PAUSED")

        # Step-level events
        assert hasattr(EventType, "STEP_AWAITING_APPROVAL")
        assert hasattr(EventType, "STEP_APPROVED")
        assert hasattr(EventType, "STEP_REJECTED")
        assert hasattr(EventType, "STEP_STARTED")
        assert hasattr(EventType, "STEP_CHECKPOINTED")
        assert hasattr(EventType, "STEP_COMPLETED")
        assert hasattr(EventType, "STEP_FAILED")
        assert hasattr(EventType, "STEP_RESULT_PENDING")
        assert hasattr(EventType, "STEP_RESULT_ACCEPTED")
        assert hasattr(EventType, "STEP_RESULT_REJECTED")
        assert hasattr(EventType, "STEP_RERUN_REQUESTED")

    @pytest.mark.asyncio
    async def test_plan_execution_events_emitted(self, plan_store, event_bus):
        """Test that plan execution emits expected events."""
        plan = PersistentPlan(
            task_id="test",
            task_summary="Event test",
            status=PlanStatus.APPROVED,
            steps=[
                PersistentPlanStep(
                    step_number=1,
                    description="Test",
                    agent="huginn",
                    approval_required=False,
                )
            ],
        )
        await plan_store.save_plan(plan)

        events = []

        def capture_all(event):
            events.append(event.type)

        event_bus.subscribe_event(capture_all)

        async def mock_executor(step):
            return StepResult(success=True, output="Done", iterations_used=1)

        config = PlanExecutorConfig(auto_approve_simple_steps=True)
        executor = PlanExecutor(
            plan_store, event_bus=event_bus, config=config, step_executor=mock_executor
        )

        await executor.execute_plan(plan)

        # Verify key events were emitted
        assert EventType.PLAN_EXECUTION_STARTED in events
        assert EventType.STEP_STARTED in events
        assert EventType.STEP_COMPLETED in events
