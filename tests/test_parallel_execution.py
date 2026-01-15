"""Tests for Phase 6.1 parallel task execution."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from sindri.core.tasks import Task, TaskStatus
from sindri.core.scheduler import TaskScheduler
from sindri.llm.manager import ModelManager


class TestTaskVRAMFields:
    """Test Task model VRAM-related fields."""

    def test_task_has_vram_fields(self):
        """Task should have vram_required and model_name fields."""
        task = Task(description="Test task")
        assert hasattr(task, 'vram_required')
        assert hasattr(task, 'model_name')
        assert task.vram_required == 0.0
        assert task.model_name is None

    def test_task_vram_fields_can_be_set(self):
        """Task VRAM fields can be set."""
        task = Task(
            description="Test task",
            vram_required=5.0,
            model_name="qwen2.5-coder:7b"
        )
        assert task.vram_required == 5.0
        assert task.model_name == "qwen2.5-coder:7b"

    def test_can_run_parallel_with_self(self):
        """Task cannot run in parallel with itself."""
        task = Task(description="Test task")
        assert not task.can_run_parallel_with(task)

    def test_can_run_parallel_independent_tasks(self):
        """Independent tasks can run in parallel."""
        task1 = Task(id="task1", description="Task 1")
        task2 = Task(id="task2", description="Task 2")
        assert task1.can_run_parallel_with(task2)
        assert task2.can_run_parallel_with(task1)

    def test_cannot_run_parallel_with_dependency(self):
        """Tasks with dependencies cannot run in parallel."""
        task1 = Task(id="task1", description="Task 1")
        task2 = Task(id="task2", description="Task 2", depends_on=["task1"])
        assert not task2.can_run_parallel_with(task1)

    def test_cannot_run_parallel_parent_child(self):
        """Parent-child tasks cannot run in parallel."""
        parent = Task(id="parent", description="Parent")
        child = Task(id="child", description="Child", parent_id="parent")
        assert not child.can_run_parallel_with(parent)
        assert not parent.can_run_parallel_with(child)

    def test_shares_model_with(self):
        """Test model sharing detection."""
        task1 = Task(id="task1", model_name="qwen2.5-coder:7b")
        task2 = Task(id="task2", model_name="qwen2.5-coder:7b")
        task3 = Task(id="task3", model_name="llama3.1:8b")
        task4 = Task(id="task4", model_name=None)

        assert task1.shares_model_with(task2)
        assert not task1.shares_model_with(task3)
        assert not task1.shares_model_with(task4)


class TestSchedulerBatching:
    """Test scheduler batch scheduling for parallel execution."""

    @pytest.fixture
    def model_manager(self):
        """Create a mock model manager."""
        manager = ModelManager(total_vram_gb=16.0, reserve_gb=2.0)
        return manager

    @pytest.fixture
    def scheduler(self, model_manager):
        """Create a scheduler with mock model manager."""
        return TaskScheduler(model_manager)

    def test_scheduler_populates_vram_fields(self, scheduler):
        """Scheduler should populate VRAM fields from agent registry."""
        task = Task(description="Test", assigned_agent="huginn")
        scheduler.add_task(task)

        assert task.vram_required == 5.0
        assert task.model_name == "qwen2.5-coder:7b"

    def test_get_ready_batch_single_task(self, scheduler):
        """get_ready_batch should return single ready task."""
        task = Task(description="Test", assigned_agent="huginn")
        scheduler.add_task(task)

        batch = scheduler.get_ready_batch()
        assert len(batch) == 1
        assert batch[0].id == task.id

    def test_get_ready_batch_multiple_independent(self, scheduler):
        """get_ready_batch should return multiple independent tasks."""
        task1 = Task(id="t1", description="Task 1", assigned_agent="huginn")
        task2 = Task(id="t2", description="Task 2", assigned_agent="skald")

        scheduler.add_task(task1)
        scheduler.add_task(task2)

        batch = scheduler.get_ready_batch()
        assert len(batch) == 2

    def test_get_ready_batch_respects_vram_limit(self, scheduler):
        """get_ready_batch should respect VRAM limits."""
        # Create tasks that exceed VRAM limit when combined
        task1 = Task(id="t1", description="Task 1", assigned_agent="brokkr")  # 9GB
        task2 = Task(id="t2", description="Task 2", assigned_agent="odin")    # 6GB
        # Total 15GB > 14GB available

        scheduler.add_task(task1)
        scheduler.add_task(task2)

        batch = scheduler.get_ready_batch()
        # Should only get one task due to VRAM limit
        assert len(batch) == 1

    def test_get_ready_batch_shares_model_vram(self, scheduler):
        """Tasks sharing same model should share VRAM allocation."""
        # Both use qwen2.5-coder:7b (5GB each, but shared = 5GB total)
        task1 = Task(id="t1", description="Task 1", assigned_agent="huginn")
        task2 = Task(id="t2", description="Task 2", assigned_agent="skald")

        scheduler.add_task(task1)
        scheduler.add_task(task2)

        batch = scheduler.get_ready_batch()
        # Both should be included because they share the model
        assert len(batch) == 2

    def test_get_ready_batch_respects_dependencies(self, scheduler):
        """get_ready_batch should not include tasks with unmet dependencies."""
        task1 = Task(id="t1", description="Task 1", assigned_agent="huginn")
        task2 = Task(id="t2", description="Task 2", assigned_agent="skald", depends_on=["t1"])

        scheduler.add_task(task1)
        scheduler.add_task(task2)

        batch = scheduler.get_ready_batch()
        # Only task1 should be ready
        assert len(batch) == 1
        assert batch[0].id == "t1"

    def test_get_ready_batch_empty_when_nothing_ready(self, scheduler):
        """get_ready_batch should return empty list when nothing ready."""
        task = Task(id="t1", description="Task 1", status=TaskStatus.RUNNING)
        scheduler.tasks[task.id] = task

        batch = scheduler.get_ready_batch()
        assert len(batch) == 0

    def test_get_ready_batch_skips_non_pending(self, scheduler):
        """get_ready_batch should skip non-pending tasks."""
        task1 = Task(id="t1", description="Task 1", assigned_agent="huginn")
        task2 = Task(id="t2", description="Task 2", assigned_agent="skald",
                     status=TaskStatus.RUNNING)

        scheduler.add_task(task1)
        scheduler.tasks[task2.id] = task2  # Add without heap push

        batch = scheduler.get_ready_batch()
        assert len(batch) == 1
        assert batch[0].id == "t1"


class TestModelManagerThreadSafety:
    """Test ModelManager thread-safety for parallel execution."""

    @pytest.fixture
    def manager(self):
        """Create a model manager."""
        return ModelManager(total_vram_gb=16.0, reserve_gb=2.0)

    def test_manager_has_locks(self, manager):
        """ModelManager should have asyncio locks."""
        assert hasattr(manager, '_lock')
        assert hasattr(manager, '_model_locks')

    @pytest.mark.asyncio
    async def test_concurrent_ensure_loaded_same_model(self, manager):
        """Concurrent ensure_loaded for same model should work correctly."""
        model = "qwen2.5-coder:7b"

        # Simulate concurrent loads
        results = await asyncio.gather(
            manager.ensure_loaded(model, 5.0),
            manager.ensure_loaded(model, 5.0),
            manager.ensure_loaded(model, 5.0)
        )

        # All should succeed
        assert all(results)
        # Model should only be loaded once
        assert len(manager.loaded) == 1
        assert model in manager.loaded

    @pytest.mark.asyncio
    async def test_concurrent_ensure_loaded_different_models(self, manager):
        """Concurrent ensure_loaded for different models within VRAM limit."""
        results = await asyncio.gather(
            manager.ensure_loaded("model1", 5.0),
            manager.ensure_loaded("model2", 5.0)
        )

        assert all(results)
        assert len(manager.loaded) == 2

    @pytest.mark.asyncio
    async def test_ensure_loaded_eviction(self, manager):
        """ensure_loaded should evict LRU when VRAM is full."""
        # Load first model
        await manager.ensure_loaded("model1", 10.0)
        assert "model1" in manager.loaded

        # Load second model that requires eviction
        await manager.ensure_loaded("model2", 10.0)

        # model1 should be evicted, model2 loaded
        assert "model1" not in manager.loaded
        assert "model2" in manager.loaded

    def test_get_model_lock(self, manager):
        """_get_model_lock should create and return locks."""
        lock1 = manager._get_model_lock("model1")
        lock2 = manager._get_model_lock("model1")
        lock3 = manager._get_model_lock("model2")

        # Same model should return same lock
        assert lock1 is lock2
        # Different model should return different lock
        assert lock1 is not lock3


class TestEventTimestamps:
    """Test event timestamps for parallel execution ordering."""

    def test_event_has_timestamp(self):
        """Event should have timestamp field."""
        from sindri.core.events import Event, EventType

        event = Event(type=EventType.TASK_CREATED, data={})
        assert hasattr(event, 'timestamp')
        assert event.timestamp > 0

    def test_event_has_task_id(self):
        """Event should have task_id field."""
        from sindri.core.events import Event, EventType

        event = Event(type=EventType.TASK_CREATED, data={}, task_id="test-123")
        assert event.task_id == "test-123"

    def test_parallel_event_types_exist(self):
        """New parallel event types should exist."""
        from sindri.core.events import EventType

        assert hasattr(EventType, 'PARALLEL_BATCH_START')
        assert hasattr(EventType, 'PARALLEL_BATCH_END')


class TestOrchestratorParallel:
    """Test orchestrator parallel execution mode."""

    @pytest.mark.asyncio
    async def test_orchestrator_has_parallel_flag(self):
        """Orchestrator.run should accept parallel flag."""
        from sindri.core.orchestrator import Orchestrator
        from unittest.mock import AsyncMock, patch

        with patch.object(Orchestrator, '__init__', lambda self, **kwargs: None):
            orchestrator = Orchestrator()
            orchestrator.scheduler = Mock()
            orchestrator.scheduler.has_work.return_value = False
            orchestrator.scheduler.add_task = Mock()
            orchestrator.loop = Mock()

            # Should accept parallel parameter
            import inspect
            sig = inspect.signature(Orchestrator.run)
            assert 'parallel' in sig.parameters

    @pytest.mark.asyncio
    async def test_run_parallel_batch_method_exists(self):
        """Orchestrator should have _run_parallel_batch method."""
        from sindri.core.orchestrator import Orchestrator

        assert hasattr(Orchestrator, '_run_parallel_batch')

    @pytest.mark.asyncio
    async def test_run_sequential_method_exists(self):
        """Orchestrator should have _run_sequential method."""
        from sindri.core.orchestrator import Orchestrator

        assert hasattr(Orchestrator, '_run_sequential')
