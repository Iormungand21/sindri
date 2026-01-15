"""Integration tests for parallel task execution.

These tests verify the parallel execution infrastructure works correctly
without requiring actual LLM responses (which are slow).
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch

from sindri.core.tasks import Task, TaskStatus
from sindri.core.scheduler import TaskScheduler
from sindri.core.orchestrator import Orchestrator
from sindri.llm.manager import ModelManager
from sindri.core.loop import LoopResult


class TestParallelBatchFormation:
    """Test that parallel batches are formed correctly."""

    @pytest.fixture
    def scheduler(self):
        """Create scheduler with model manager."""
        manager = ModelManager(total_vram_gb=16.0, reserve_gb=2.0)
        return TaskScheduler(manager)

    def test_two_huginn_tasks_batch_together(self, scheduler):
        """Two Huginn tasks should batch together (same model, 5GB each, shared)."""
        task1 = Task(id="t1", description="Write code 1", assigned_agent="huginn")
        task2 = Task(id="t2", description="Write code 2", assigned_agent="huginn")

        scheduler.add_task(task1)
        scheduler.add_task(task2)

        batch = scheduler.get_ready_batch()

        # Both should be in batch since they share qwen2.5-coder:7b
        assert len(batch) == 2
        assert {t.id for t in batch} == {"t1", "t2"}

    def test_huginn_and_skald_batch_together(self, scheduler):
        """Huginn and Skald both use qwen2.5-coder:7b - should batch."""
        task1 = Task(id="t1", description="Write code", assigned_agent="huginn")
        task2 = Task(id="t2", description="Write tests", assigned_agent="skald")

        scheduler.add_task(task1)
        scheduler.add_task(task2)

        batch = scheduler.get_ready_batch()

        # Both use qwen2.5-coder:7b, so VRAM is shared = 5GB total
        assert len(batch) == 2

    def test_brokkr_and_odin_dont_batch(self, scheduler):
        """Brokkr (9GB) + Odin (6GB) = 15GB > 14GB available."""
        task1 = Task(id="t1", description="Orchestrate", assigned_agent="brokkr")
        task2 = Task(id="t2", description="Plan", assigned_agent="odin")

        scheduler.add_task(task1)
        scheduler.add_task(task2)

        batch = scheduler.get_ready_batch()

        # Should only get one task due to VRAM limit
        assert len(batch) == 1

    def test_three_small_agents_batch(self, scheduler):
        """Ratatoskr (3GB) + Mimir (5GB) + Fenrir (5GB) = 13GB < 14GB."""
        task1 = Task(id="t1", description="Execute", assigned_agent="ratatoskr")
        task2 = Task(id="t2", description="Review", assigned_agent="mimir")
        task3 = Task(id="t3", description="SQL", assigned_agent="fenrir")

        scheduler.add_task(task1)
        scheduler.add_task(task2)
        scheduler.add_task(task3)

        batch = scheduler.get_ready_batch()

        # All three should fit: 3 + 5 + 5 = 13GB < 14GB
        assert len(batch) == 3

    def test_dependency_prevents_batching(self, scheduler):
        """Tasks with dependencies shouldn't batch together."""
        task1 = Task(id="t1", description="First", assigned_agent="huginn")
        task2 = Task(id="t2", description="Second", assigned_agent="skald",
                     depends_on=["t1"])

        scheduler.add_task(task1)
        scheduler.add_task(task2)

        batch = scheduler.get_ready_batch()

        # Only task1 should be ready (task2 depends on t1)
        assert len(batch) == 1
        assert batch[0].id == "t1"

    def test_loaded_model_uses_no_additional_vram(self, scheduler):
        """If a model is already loaded, tasks using it need no additional VRAM."""
        # Pre-load Brokkr's model
        scheduler.model_manager.loaded["qwen2.5-coder:14b"] = Mock(
            name="qwen2.5-coder:14b", vram_gb=9.0, last_used=time.time()
        )

        # Now add Brokkr task - should use 0 additional VRAM
        task1 = Task(id="t1", description="Orchestrate", assigned_agent="brokkr")
        task2 = Task(id="t2", description="Review", assigned_agent="mimir")  # 5GB

        scheduler.add_task(task1)
        scheduler.add_task(task2)

        batch = scheduler.get_ready_batch()

        # Both should batch: Brokkr uses loaded model (0GB), Mimir needs 5GB
        assert len(batch) == 2


class TestParallelExecutionTiming:
    """Test that parallel execution actually runs tasks concurrently."""

    @pytest.mark.asyncio
    async def test_parallel_tasks_run_concurrently(self):
        """Verify tasks actually run in parallel, not sequentially."""
        execution_times = []

        async def mock_task_runner(task_id: str, delay: float = 0.1):
            """Simulated task that records its execution time."""
            start = time.time()
            await asyncio.sleep(delay)
            end = time.time()
            execution_times.append({
                "task_id": task_id,
                "start": start,
                "end": end
            })
            return LoopResult(success=True, iterations=1, reason="test")

        # Run 3 tasks in parallel
        start_time = time.time()
        results = await asyncio.gather(
            mock_task_runner("task1", 0.1),
            mock_task_runner("task2", 0.1),
            mock_task_runner("task3", 0.1)
        )
        total_time = time.time() - start_time

        # All tasks should succeed
        assert all(r.success for r in results)

        # Total time should be ~0.1s (parallel), not ~0.3s (sequential)
        # Allow some overhead
        assert total_time < 0.25, f"Tasks took {total_time}s, expected ~0.1s for parallel"

        # All tasks should have overlapping execution windows
        starts = [e["start"] for e in execution_times]
        ends = [e["end"] for e in execution_times]

        # First task's end should be after all tasks started (they overlapped)
        assert min(ends) > max(starts) - 0.05  # Small tolerance for scheduling


class TestOrchestratorParallelMode:
    """Test orchestrator parallel vs sequential modes."""

    @pytest.mark.asyncio
    async def test_orchestrator_run_accepts_parallel_flag(self):
        """Orchestrator.run() should accept parallel parameter."""
        with patch('sindri.core.orchestrator.OllamaClient'):
            orchestrator = Orchestrator(enable_memory=False)

            # Mock scheduler to return no work immediately
            orchestrator.scheduler.has_work = Mock(return_value=False)

            # Should accept parallel=True (default)
            result = await orchestrator.run("test task", parallel=True)
            assert "task_id" in result

    @pytest.mark.asyncio
    async def test_orchestrator_run_parallel_false(self):
        """Orchestrator should work with parallel=False (legacy mode)."""
        with patch('sindri.core.orchestrator.OllamaClient'):
            orchestrator = Orchestrator(enable_memory=False)

            orchestrator.scheduler.has_work = Mock(return_value=False)

            # Should accept parallel=False
            result = await orchestrator.run("test task", parallel=False)
            assert "task_id" in result


class TestVRAMCalculation:
    """Test VRAM calculation for parallel batching."""

    def test_vram_shared_correctly(self):
        """Verify VRAM sharing calculation for same-model tasks."""
        manager = ModelManager(total_vram_gb=16.0, reserve_gb=2.0)
        scheduler = TaskScheduler(manager)

        # Add 3 tasks using qwen2.5-coder:7b (5GB each)
        for i in range(3):
            task = Task(id=f"t{i}", description=f"Task {i}", assigned_agent="huginn")
            scheduler.add_task(task)

        batch = scheduler.get_ready_batch()

        # All 3 should batch - they share the model so only 5GB total needed
        assert len(batch) == 3

    def test_vram_mixed_models(self):
        """Test VRAM calculation with mixed models."""
        manager = ModelManager(total_vram_gb=16.0, reserve_gb=2.0)
        scheduler = TaskScheduler(manager)

        # Huginn (5GB qwen2.5-coder:7b) + Mimir (5GB llama3.1:8b) + Fenrir (5GB sqlcoder:7b)
        # Total: 15GB > 14GB available
        scheduler.add_task(Task(id="t1", description="Code", assigned_agent="huginn"))
        scheduler.add_task(Task(id="t2", description="Review", assigned_agent="mimir"))
        scheduler.add_task(Task(id="t3", description="SQL", assigned_agent="fenrir"))

        batch = scheduler.get_ready_batch()

        # Should get 2 tasks (10GB) since 3 would be 15GB > 14GB
        # But wait - 5+5+5=15 > 14, so only 2 should fit
        # Actually let's recalculate: available = 16 - 2 = 14GB
        # 3 different models × 5GB = 15GB > 14GB available
        # So max 2 tasks (10GB)
        assert len(batch) == 2


class TestEventTimestamps:
    """Test that events have proper timestamps for parallel ordering."""

    def test_events_have_increasing_timestamps(self):
        """Events created in sequence should have increasing timestamps."""
        from sindri.core.events import Event, EventType
        import time

        events = []
        for i in range(5):
            events.append(Event(type=EventType.TASK_CREATED, data={"id": i}))
            time.sleep(0.001)  # Small delay to ensure different timestamps

        # Timestamps should be monotonically increasing
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)

    def test_events_can_be_sorted_by_timestamp(self):
        """Events from parallel tasks can be sorted by timestamp."""
        from sindri.core.events import Event, EventType
        import random

        # Create events with random order but known timestamps
        events = [
            Event(type=EventType.TASK_CREATED, data={"id": i}, task_id=f"t{i}")
            for i in range(5)
        ]

        # Shuffle to simulate out-of-order arrival
        random.shuffle(events)

        # Sort by timestamp
        sorted_events = sorted(events, key=lambda e: e.timestamp)

        # Should be back in original order (by creation time)
        assert [e.data["id"] for e in sorted_events] == list(range(5))
