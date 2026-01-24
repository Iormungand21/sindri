"""Tests for hierarchical execution reliability fixes.

These tests verify the fixes for ROADMAP Item 0:
- Issue 3: Parallel exception propagation to parents
- Issue 4: VRAM-aware batching with actual free VRAM
- Issue 2: Model load failure propagation to parents
- Issue 6: UUID collision prevention (full UUIDs)
- Sequential exception handling (matching parallel error reporting)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from sindri.core.tasks import Task, TaskStatus
from sindri.core.scheduler import TaskScheduler
from sindri.core.delegation import DelegationManager, DelegationRequest
from sindri.core.orchestrator import Orchestrator
from sindri.core.events import EventBus, Event, EventType
from sindri.llm.manager import ModelManager


# =============================================================================
# Issue 6: UUID Collision Prevention Tests
# =============================================================================


class TestUUIDCollisionPrevention:
    """Tests for full UUID usage instead of truncated."""

    def test_task_id_is_full_uuid(self):
        """Test that task IDs are full UUIDs (36 chars with hyphens)."""
        task = Task(description="Test task", assigned_agent="brokkr")
        # Full UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (36 chars)
        assert len(task.id) == 36
        assert task.id.count("-") == 4

    def test_task_ids_are_unique(self):
        """Test that generated task IDs are unique."""
        ids = set()
        for _ in range(1000):
            task = Task(description="Test task", assigned_agent="brokkr")
            assert task.id not in ids, "UUID collision detected!"
            ids.add(task.id)

    def test_task_id_format_valid(self):
        """Test that task IDs are valid UUID format."""
        import uuid

        task = Task(description="Test task", assigned_agent="brokkr")
        # Should not raise ValueError if valid UUID
        parsed = uuid.UUID(task.id)
        assert str(parsed) == task.id


# =============================================================================
# Issue 4: VRAM-Aware Batching Tests
# =============================================================================


class TestVRAMBatching:
    """Tests for VRAM-aware batching using actual free VRAM."""

    @pytest.fixture
    def model_manager(self):
        """Create a model manager for testing."""
        return ModelManager(total_vram_gb=16.0, reserve_gb=2.0)

    @pytest.fixture
    def scheduler(self, model_manager):
        """Create a scheduler for testing."""
        return TaskScheduler(model_manager)

    def test_get_allocated_models_empty(self, model_manager):
        """Test get_allocated_models with no models loaded."""
        allocated = model_manager.get_allocated_models()
        assert allocated == set()

    def test_get_allocated_models_with_loaded(self, model_manager):
        """Test get_allocated_models includes loaded models."""
        # Simulate loaded model
        from sindri.llm.manager import LoadedModel
        import time

        model_manager.loaded["qwen2.5:7b"] = LoadedModel(
            name="qwen2.5:7b", vram_gb=5.0, last_used=time.time()
        )
        allocated = model_manager.get_allocated_models()
        assert "qwen2.5:7b" in allocated

    @pytest.mark.asyncio
    async def test_get_allocated_models_includes_prewarming(self, model_manager):
        """Test get_allocated_models includes models being pre-warmed."""
        # Create a prewarm task that's not done
        async def slow_prewarm():
            await asyncio.sleep(10)  # Won't complete

        model_manager._prewarm_tasks["codestral:22b"] = asyncio.create_task(
            slow_prewarm()
        )

        allocated = model_manager.get_allocated_models()
        assert "codestral:22b" in allocated

        # Cleanup
        model_manager._prewarm_tasks["codestral:22b"].cancel()
        try:
            await model_manager._prewarm_tasks["codestral:22b"]
        except asyncio.CancelledError:
            pass

    def test_get_free_vram_public_method(self, model_manager):
        """Test public get_free_vram method exists and works."""
        free = model_manager.get_free_vram()
        # Should be available (14GB) minus loaded (0GB) = 14GB
        assert free == 14.0

    def test_scheduler_uses_actual_free_vram(self, model_manager, scheduler):
        """Test that scheduler uses actual free VRAM for batching."""
        from sindri.llm.manager import LoadedModel
        import time

        # Simulate a model already loaded (uses 8GB)
        model_manager.loaded["deepseek-r1:14b"] = LoadedModel(
            name="deepseek-r1:14b", vram_gb=8.0, last_used=time.time()
        )

        # Create a task that needs 7GB
        task = Task(
            description="Task needing 7GB", assigned_agent="brokkr", vram_required=7.0
        )
        scheduler.add_task(task)

        # Actual free: 14 - 8 = 6GB, task needs 7GB
        # Without fix: would use 14GB available, schedule task
        # With fix: uses 6GB free, task won't fit

        batch = scheduler.get_ready_batch()
        # Task should NOT be in batch because actual free (6GB) < required (7GB)
        assert task not in batch

    def test_scheduler_batch_with_shared_model(self, model_manager, scheduler):
        """Test batching accounts for shared models correctly."""
        # Create two tasks using the same model
        task1 = Task(
            description="Task 1",
            assigned_agent="huginn",
            vram_required=5.0,
            model_name="qwen2.5-coder:7b",
        )
        task2 = Task(
            description="Task 2",
            assigned_agent="huginn",
            vram_required=5.0,
            model_name="qwen2.5-coder:7b",
        )

        scheduler.add_task(task1)
        scheduler.add_task(task2)

        batch = scheduler.get_ready_batch()

        # Both tasks should be in batch - they share a model so only 5GB needed
        assert len(batch) == 2


# =============================================================================
# Issue 2: Model Load Failure Propagation Tests
# =============================================================================


class TestModelLoadFailurePropagation:
    """Tests for model load failure notification to parents."""

    @pytest.fixture
    def event_bus(self):
        """Create an event bus for testing."""
        return EventBus()

    @pytest.fixture
    def scheduler(self):
        """Create a scheduler for testing."""
        model_manager = ModelManager(total_vram_gb=16.0, reserve_gb=2.0)
        return TaskScheduler(model_manager)

    @pytest.fixture
    def delegation_manager(self, scheduler, event_bus):
        """Create a delegation manager for testing."""
        return DelegationManager(scheduler, event_bus=event_bus)

    @pytest.mark.asyncio
    async def test_model_load_failure_marks_task_failed(self):
        """Test that model load failure sets task status to FAILED."""
        # This is tested through the hierarchical loop integration
        # Mock the model manager to always fail loading
        with patch("sindri.llm.manager.ModelManager.ensure_loaded") as mock_load:
            mock_load.return_value = False

            orchestrator = Orchestrator(enable_memory=False)

            # Create a task that will fail to load its model
            task = Task(description="Test task", assigned_agent="huginn")
            orchestrator.scheduler.add_task(task)

            # Run the task
            result = await orchestrator.loop.run_task(task)

            assert result.success == False
            assert task.status == TaskStatus.FAILED
            assert "Could not load model" in task.error

    @pytest.mark.asyncio
    async def test_model_load_failure_emits_error_event(self, event_bus):
        """Test that model load failure emits ERROR event."""
        events_received = []

        def on_event(event):
            events_received.append(event)

        # Use subscribe_event to receive full Event objects
        event_bus.subscribe_event(on_event)

        with patch("sindri.llm.manager.ModelManager.ensure_loaded") as mock_load:
            mock_load.return_value = False

            orchestrator = Orchestrator(enable_memory=False, event_bus=event_bus)

            task = Task(description="Test task", assigned_agent="huginn")
            orchestrator.scheduler.add_task(task)

            await orchestrator.loop.run_task(task)

            # Should have received an error event
            error_events = [e for e in events_received if e.type == EventType.ERROR]
            assert len(error_events) >= 1
            assert error_events[0].data["error_type"] == "model_load_failure"

    @pytest.mark.asyncio
    async def test_model_load_failure_marks_existing_session_failed(self):
        """Test that model load failure marks existing session as failed.

        When resuming a task with an existing session_id, model load failure
        should update the session status to 'failed' instead of leaving it 'active'.
        """
        import tempfile
        from pathlib import Path
        from sindri.persistence.database import Database
        from sindri.persistence.state import SessionState

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)
            state = SessionState(db)

            # Create a session first (simulating a resumed task)
            session = await state.create_session("Resumed task", "huginn:model")
            assert session.status == "active"

            with patch("sindri.llm.manager.ModelManager.ensure_loaded") as mock_load:
                mock_load.return_value = False

                orchestrator = Orchestrator(enable_memory=False)
                # Inject our state into the loop
                orchestrator.loop.state = state

                # Create a task with the existing session_id (simulating resume)
                task = Task(description="Resumed task", assigned_agent="huginn")
                task.session_id = session.id
                orchestrator.scheduler.add_task(task)

                # Run the task - should fail due to model load failure
                result = await orchestrator.loop.run_task(task)

                assert result.success == False
                assert task.status == TaskStatus.FAILED
                assert "Could not load model" in task.error

                # Verify the session was marked as failed
                loaded_session = await state.load_session(session.id)
                assert loaded_session.status == "failed"
                assert loaded_session.error is not None
                assert "Could not load model" in loaded_session.error


# =============================================================================
# Issue 3: Parallel Exception Propagation Tests
# =============================================================================


class TestParallelExceptionPropagation:
    """Tests for parallel task exception propagation to parents."""

    @pytest.fixture
    def event_bus(self):
        """Create an event bus for testing."""
        return EventBus()

    @pytest.mark.asyncio
    async def test_parallel_exception_notifies_parent(self, event_bus):
        """Test that parallel task exceptions notify parent via child_failed."""
        orchestrator = Orchestrator(enable_memory=False, event_bus=event_bus)

        # Create parent and child tasks
        parent = Task(description="Parent task", assigned_agent="brokkr")
        child = Task(
            description="Child task", assigned_agent="huginn", parent_id=parent.id
        )

        parent.add_subtask(child.id)
        parent.status = TaskStatus.WAITING

        orchestrator.scheduler.add_task(parent)
        orchestrator.scheduler.add_task(child)

        # Mock run_task to raise an exception for child
        async def mock_run_task(task):
            if task.id == child.id:
                raise RuntimeError("Simulated failure")
            # Return a mock result for other tasks
            from sindri.core.loop import LoopResult
            return LoopResult(success=True, iterations=1)

        orchestrator.loop.run_task = mock_run_task

        # Run parallel batch - child should be selected (it's pending)
        # But parent is WAITING so won't be in the batch
        await orchestrator._run_parallel_batch()

        # Child should be marked failed
        assert child.status == TaskStatus.FAILED
        assert "Simulated failure" in child.error

        # Parent should be notified (marked failed via child_failed)
        assert parent.status == TaskStatus.FAILED
        assert child.id in parent.error

    @pytest.mark.asyncio
    async def test_parallel_exception_emits_error_event(self, event_bus):
        """Test that parallel exceptions emit ERROR events."""
        events_received = []

        def on_event(event):
            events_received.append(event)

        # Use subscribe_event to receive full Event objects
        event_bus.subscribe_event(on_event)

        orchestrator = Orchestrator(enable_memory=False, event_bus=event_bus)

        task = Task(description="Test task", assigned_agent="huginn")
        orchestrator.scheduler.add_task(task)

        # Mock run_task to raise an exception
        async def mock_run_task(t):
            raise RuntimeError("Test exception")

        orchestrator.loop.run_task = mock_run_task

        await orchestrator._run_parallel_batch()

        # Should have received an error event
        error_events = [e for e in events_received if e.type == EventType.ERROR]
        assert len(error_events) >= 1
        # Single task uses "task_exception", multiple tasks use "parallel_task_exception"
        assert error_events[0].data["error_type"] in (
            "task_exception",
            "parallel_task_exception",
        )
        assert "Test exception" in error_events[0].data["error"]

    @pytest.mark.asyncio
    async def test_multiple_parallel_failures_all_notify(self, event_bus):
        """Test that multiple parallel failures all notify their parents."""
        orchestrator = Orchestrator(enable_memory=False, event_bus=event_bus)

        # Create multiple tasks
        task1 = Task(description="Task 1", assigned_agent="huginn")
        task2 = Task(description="Task 2", assigned_agent="mimir")

        orchestrator.scheduler.add_task(task1)
        orchestrator.scheduler.add_task(task2)

        # Mock run_task to raise exceptions
        async def mock_run_task(t):
            raise RuntimeError(f"Failure in {t.id}")

        orchestrator.loop.run_task = mock_run_task

        await orchestrator._run_parallel_batch()

        # Both tasks should be marked failed
        assert task1.status == TaskStatus.FAILED
        assert task2.status == TaskStatus.FAILED


# =============================================================================
# Issue 1: Delegation Wait Handling Tests
# =============================================================================


class TestDelegationWaitHandling:
    """Tests for delegation wait handling (success=None case)."""

    @pytest.fixture
    def event_bus(self):
        """Create an event bus for testing."""
        return EventBus()

    @pytest.mark.asyncio
    async def test_delegation_returns_success_none_keeps_task_waiting(self, event_bus):
        """Test that success=None from delegation doesn't mark parent as FAILED."""
        from sindri.core.loop import LoopResult

        orchestrator = Orchestrator(enable_memory=False, event_bus=event_bus)

        # Create parent task
        parent = Task(description="Parent task", assigned_agent="brokkr")
        orchestrator.scheduler.add_task(parent)

        # Mock run_loop to return success=None (delegation waiting)
        async def mock_run_loop(task, agent, tools, active_model=None, policy_enforcer=None, config=None):
            # Simulate delegation - set task to WAITING
            task.status = TaskStatus.WAITING
            return LoopResult(
                success=None,
                iterations=1,
                reason="delegation_waiting",
                final_output="Waiting for delegated child task",
            )

        orchestrator.loop._run_loop = mock_run_loop

        # Run the task
        result = await orchestrator.loop.run_task(parent)

        # Task should still be WAITING, not FAILED
        assert parent.status == TaskStatus.WAITING
        assert result.success is None
        assert result.reason == "delegation_waiting"

    @pytest.mark.asyncio
    async def test_delegation_waiting_does_not_emit_error_event(self, event_bus):
        """Test that delegation waiting doesn't emit ERROR events."""
        from sindri.core.loop import LoopResult

        events_received = []

        def on_event(event):
            events_received.append(event)

        event_bus.subscribe_event(on_event)

        orchestrator = Orchestrator(enable_memory=False, event_bus=event_bus)

        parent = Task(description="Parent task", assigned_agent="brokkr")
        orchestrator.scheduler.add_task(parent)

        async def mock_run_loop(task, agent, tools, active_model=None, policy_enforcer=None, config=None):
            task.status = TaskStatus.WAITING
            return LoopResult(
                success=None,
                iterations=1,
                reason="delegation_waiting",
            )

        orchestrator.loop._run_loop = mock_run_loop

        await orchestrator.loop.run_task(parent)

        # Should NOT have any ERROR events
        error_events = [e for e in events_received if e.type == EventType.ERROR]
        assert len(error_events) == 0

    @pytest.mark.asyncio
    async def test_parent_resumes_after_child_completes(self):
        """Test that parent task resumes (becomes PENDING) when child completes."""
        orchestrator = Orchestrator(enable_memory=False)

        # Create parent and child tasks
        parent = Task(description="Parent task", assigned_agent="brokkr")
        child = Task(
            description="Child task", assigned_agent="huginn", parent_id=parent.id
        )

        parent.add_subtask(child.id)
        parent.status = TaskStatus.WAITING

        orchestrator.scheduler.add_task(parent)
        orchestrator.scheduler.add_task(child)

        # Complete the child
        child.status = TaskStatus.COMPLETE

        await orchestrator.delegation.child_completed(child)

        # Parent should be resumed (PENDING) not FAILED
        assert parent.status == TaskStatus.PENDING


# =============================================================================
# Integration Tests
# =============================================================================


class TestHierarchicalReliabilityIntegration:
    """Integration tests for hierarchical execution reliability."""

    @pytest.mark.asyncio
    async def test_delegation_failure_propagates_to_root(self):
        """Test that failures in delegated tasks propagate to root."""
        orchestrator = Orchestrator(enable_memory=False)

        # Create a hierarchy: root -> child
        root = Task(description="Root task", assigned_agent="brokkr")
        child = Task(
            description="Child task", assigned_agent="huginn", parent_id=root.id
        )

        root.add_subtask(child.id)
        root.status = TaskStatus.WAITING

        orchestrator.scheduler.add_task(root)
        orchestrator.scheduler.add_task(child)

        # Fail the child
        child.status = TaskStatus.FAILED
        child.error = "Child failed"

        await orchestrator.delegation.child_failed(child)

        # Root should now be failed
        assert root.status == TaskStatus.FAILED
        assert "Child failed" in root.error

    def test_scheduler_respects_vram_under_load(self):
        """Test scheduler doesn't over-schedule when VRAM is partially used."""
        model_manager = ModelManager(total_vram_gb=16.0, reserve_gb=2.0)
        scheduler = TaskScheduler(model_manager)

        from sindri.llm.manager import LoadedModel
        import time

        # Simulate 10GB of VRAM already used
        model_manager.loaded["large-model"] = LoadedModel(
            name="large-model", vram_gb=10.0, last_used=time.time()
        )

        # Free: 14 - 10 = 4GB
        assert model_manager.get_free_vram() == 4.0

        # Create tasks needing 5GB each (different models)
        task1 = Task(
            description="Task 1",
            assigned_agent="huginn",
            vram_required=5.0,
            model_name="model-a",
        )
        task2 = Task(
            description="Task 2",
            assigned_agent="mimir",
            vram_required=5.0,
            model_name="model-b",
        )

        scheduler.add_task(task1)
        scheduler.add_task(task2)

        batch = scheduler.get_ready_batch()

        # Neither task should fit (only 4GB free, each needs 5GB)
        assert len(batch) == 0

    def test_full_uuid_prevents_lookup_errors(self):
        """Test that full UUIDs prevent task lookup errors."""
        model_manager = ModelManager(total_vram_gb=16.0, reserve_gb=2.0)
        scheduler = TaskScheduler(model_manager)

        # Create many tasks
        tasks = []
        for i in range(100):
            task = Task(description=f"Task {i}", assigned_agent="brokkr")
            scheduler.add_task(task)
            tasks.append(task)

        # All tasks should be retrievable by their unique ID
        for task in tasks:
            retrieved = scheduler.get_task(task.id)
            assert retrieved is not None
            assert retrieved.id == task.id
            assert retrieved.description == task.description


# =============================================================================
# Sequential Exception Handling Tests
# =============================================================================


class TestSequentialExceptionPropagation:
    """Tests for sequential task exception propagation to parents.

    These tests verify that the sequential execution path (_run_sequential)
    handles exceptions the same way as the parallel execution path.
    """

    @pytest.fixture
    def event_bus(self):
        """Create an event bus for testing."""
        return EventBus()

    @pytest.mark.asyncio
    async def test_sequential_exception_marks_task_failed(self, event_bus):
        """Test that sequential task exceptions mark the task as FAILED."""
        orchestrator = Orchestrator(enable_memory=False, event_bus=event_bus)

        task = Task(description="Test task", assigned_agent="huginn")
        orchestrator.scheduler.add_task(task)

        # Mock run_task to raise an exception
        async def mock_run_task(t):
            raise RuntimeError("Simulated sequential failure")

        orchestrator.loop.run_task = mock_run_task

        await orchestrator._run_sequential()

        # Task should be marked failed with error message
        assert task.status == TaskStatus.FAILED
        assert "Simulated sequential failure" in task.error

    @pytest.mark.asyncio
    async def test_sequential_exception_notifies_parent(self, event_bus):
        """Test that sequential task exceptions notify parent via child_failed."""
        orchestrator = Orchestrator(enable_memory=False, event_bus=event_bus)

        # Create parent and child tasks
        parent = Task(description="Parent task", assigned_agent="brokkr")
        child = Task(
            description="Child task", assigned_agent="huginn", parent_id=parent.id
        )

        parent.add_subtask(child.id)
        parent.status = TaskStatus.WAITING

        orchestrator.scheduler.add_task(parent)
        orchestrator.scheduler.add_task(child)

        # Mock run_task to raise an exception for child
        async def mock_run_task(task):
            if task.id == child.id:
                raise RuntimeError("Simulated child failure")
            # Return a mock result for other tasks
            from sindri.core.loop import LoopResult

            return LoopResult(success=True, iterations=1)

        orchestrator.loop.run_task = mock_run_task

        # Run sequential - child should be selected (it's pending)
        await orchestrator._run_sequential()

        # Child should be marked failed
        assert child.status == TaskStatus.FAILED
        assert "Simulated child failure" in child.error

        # Parent should be notified (marked failed via child_failed)
        assert parent.status == TaskStatus.FAILED
        assert child.id in parent.error

    @pytest.mark.asyncio
    async def test_sequential_exception_emits_error_event(self, event_bus):
        """Test that sequential exceptions emit ERROR events."""
        events_received = []

        def on_event(event):
            events_received.append(event)

        # Use subscribe_event to receive full Event objects
        event_bus.subscribe_event(on_event)

        orchestrator = Orchestrator(enable_memory=False, event_bus=event_bus)

        task = Task(description="Test task", assigned_agent="huginn")
        orchestrator.scheduler.add_task(task)

        # Mock run_task to raise an exception
        async def mock_run_task(t):
            raise RuntimeError("Test sequential exception")

        orchestrator.loop.run_task = mock_run_task

        await orchestrator._run_sequential()

        # Should have received an error event
        error_events = [e for e in events_received if e.type == EventType.ERROR]
        assert len(error_events) >= 1
        assert error_events[0].data["error_type"] == "sequential_task_exception"
        assert "Test sequential exception" in error_events[0].data["error"]

    @pytest.mark.asyncio
    async def test_sequential_exception_returns_ok(self, event_bus):
        """Test that _run_sequential returns 'ok' even after exception."""
        orchestrator = Orchestrator(enable_memory=False, event_bus=event_bus)

        task = Task(description="Test task", assigned_agent="huginn")
        orchestrator.scheduler.add_task(task)

        # Mock run_task to raise an exception
        async def mock_run_task(t):
            raise RuntimeError("Test exception")

        orchestrator.loop.run_task = mock_run_task

        result = await orchestrator._run_sequential()

        # Should return "ok" to indicate a task was processed
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_sequential_exception_stores_error_details(self, event_bus):
        """Test that sequential exceptions store full error details in event."""
        events_received = []

        def on_event(event):
            events_received.append(event)

        event_bus.subscribe_event(on_event)

        orchestrator = Orchestrator(enable_memory=False, event_bus=event_bus)

        task = Task(description="Detailed test task", assigned_agent="mimir")
        orchestrator.scheduler.add_task(task)

        async def mock_run_task(t):
            raise ValueError("Detailed error message")

        orchestrator.loop.run_task = mock_run_task

        await orchestrator._run_sequential()

        # Check event contains all required fields
        error_events = [e for e in events_received if e.type == EventType.ERROR]
        assert len(error_events) == 1

        event_data = error_events[0].data
        assert event_data["task_id"] == task.id
        assert event_data["error"] == "Detailed error message"
        assert event_data["error_type"] == "sequential_task_exception"
        assert event_data["agent"] == "mimir"
        assert "Detailed test task" in event_data["description"]


# =============================================================================
# Work Directory Memory Indexing Tests
# =============================================================================


class TestWorkDirMemoryIndexing:
    """Tests for respecting configured work_dir when indexing memory context.

    These tests verify that memory indexing uses the configured work_dir
    from the tool registry instead of os.getcwd().
    """

    def test_memory_indexing_uses_configured_work_dir(self, tmp_path):
        """Test that memory indexing respects configured work_dir."""
        from pathlib import Path
        from sindri.tools.registry import ToolRegistry

        # Create a temp directory as our "project"
        project_dir = tmp_path / "my_project"
        project_dir.mkdir()
        (project_dir / "test.py").write_text("print('hello')")

        # Create tool registry with custom work_dir
        tools = ToolRegistry(work_dir=project_dir)

        # Verify the work_dir is set correctly
        assert tools.work_dir == project_dir

        # Test that the work_dir pattern produces correct path
        # This simulates what hierarchical.py does: self.tools.work_dir or Path.cwd()
        project_path = tools.work_dir or Path.cwd()
        assert project_path == project_dir

        # Verify the project_id would include the custom directory name
        project_id = f"project_{str(project_path.resolve()).replace('/', '_')}"
        assert "my_project" in project_id

    def test_memory_indexing_falls_back_to_cwd_when_no_work_dir(self):
        """Test that memory indexing falls back to cwd when work_dir is None."""
        from pathlib import Path
        from sindri.tools.registry import ToolRegistry

        # Create tool registry without work_dir
        tools = ToolRegistry(work_dir=None)

        # Verify work_dir is None
        assert tools.work_dir is None

        # The fallback pattern: self.tools.work_dir or Path.cwd()
        project_path = tools.work_dir or Path.cwd()

        # Should fall back to current working directory
        assert project_path == Path.cwd()

    def test_project_id_uses_configured_work_dir_path(self, tmp_path):
        """Test that project_id is generated from configured work_dir, not os.getcwd()."""
        from pathlib import Path
        from sindri.tools.registry import ToolRegistry

        # Create a temp directory as our "project"
        project_dir = tmp_path / "custom_project"
        project_dir.mkdir()

        # Create tool registry with custom work_dir
        tools = ToolRegistry(work_dir=project_dir)

        # Simulate the project_id generation logic from hierarchical.py
        project_path = tools.work_dir or Path.cwd()
        project_id = f"project_{str(project_path.resolve()).replace('/', '_')}"

        # The project_id should contain our custom project path
        assert "custom_project" in project_id
        assert str(tmp_path).replace("/", "_") in project_id
