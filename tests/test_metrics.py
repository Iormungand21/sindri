"""Tests for Phase 5.5 Performance Metrics system."""

import time
import pytest
import tempfile
from pathlib import Path

from sindri.persistence.metrics import (
    ToolExecutionMetrics,
    IterationMetrics,
    TaskMetrics,
    SessionMetrics,
    MetricsCollector,
    MetricsStore
)
from sindri.persistence.database import Database


# ============================================================================
# Tool Execution Metrics Tests
# ============================================================================

class TestToolExecutionMetrics:
    """Tests for ToolExecutionMetrics dataclass."""

    def test_duration_calculation(self):
        """Test that duration is calculated correctly."""
        metrics = ToolExecutionMetrics(
            tool_name="read_file",
            start_time=100.0,
            end_time=100.5,
            success=True
        )
        assert metrics.duration_seconds == 0.5
        assert metrics.duration_ms == 500.0

    def test_with_arguments(self):
        """Test that arguments are stored."""
        metrics = ToolExecutionMetrics(
            tool_name="write_file",
            start_time=0.0,
            end_time=1.0,
            success=True,
            arguments={"path": "/test.txt", "content": "hello"}
        )
        assert metrics.arguments == {"path": "/test.txt", "content": "hello"}

    def test_failed_execution(self):
        """Test failed tool execution."""
        metrics = ToolExecutionMetrics(
            tool_name="shell",
            start_time=0.0,
            end_time=2.0,
            success=False
        )
        assert metrics.success is False
        assert metrics.duration_seconds == 2.0


# ============================================================================
# Iteration Metrics Tests
# ============================================================================

class TestIterationMetrics:
    """Tests for IterationMetrics dataclass."""

    def test_basic_iteration(self):
        """Test basic iteration metrics."""
        metrics = IterationMetrics(
            iteration_number=1,
            start_time=0.0,
            end_time=10.0,
            agent_name="huginn",
            model_name="qwen2.5-coder:14b"
        )
        assert metrics.iteration_number == 1
        assert metrics.duration_seconds == 10.0
        assert metrics.tool_count == 0
        assert metrics.total_tool_time == 0.0

    def test_iteration_with_tools(self):
        """Test iteration with tool executions."""
        metrics = IterationMetrics(
            iteration_number=2,
            start_time=0.0,
            end_time=15.0,
            agent_name="huginn",
            model_name="qwen2.5-coder:14b",
            tool_executions=[
                ToolExecutionMetrics("read_file", 1.0, 1.5, True),
                ToolExecutionMetrics("write_file", 5.0, 6.0, True),
                ToolExecutionMetrics("shell", 10.0, 12.0, False),
            ]
        )
        assert metrics.tool_count == 3
        assert metrics.total_tool_time == pytest.approx(3.5)  # 0.5 + 1.0 + 2.0
        assert metrics.llm_time == pytest.approx(11.5)  # 15.0 - 3.5


# ============================================================================
# Task Metrics Tests
# ============================================================================

class TestTaskMetrics:
    """Tests for TaskMetrics dataclass."""

    def test_basic_task(self):
        """Test basic task metrics."""
        metrics = TaskMetrics(
            task_id="task-001",
            task_description="Write hello.py",
            agent_name="huginn",
            model_name="qwen2.5-coder:14b",
            start_time=0.0,
            end_time=30.0,
            status="completed"
        )
        assert metrics.duration_seconds == 30.0
        assert metrics.iteration_count == 0
        assert metrics.total_tool_executions == 0

    def test_task_with_iterations(self):
        """Test task with multiple iterations."""
        iterations = [
            IterationMetrics(1, 0.0, 10.0, "huginn", "model"),
            IterationMetrics(2, 10.0, 25.0, "huginn", "model"),
        ]
        iterations[0].tool_executions.append(
            ToolExecutionMetrics("read_file", 1.0, 2.0, True)
        )
        iterations[1].tool_executions.append(
            ToolExecutionMetrics("write_file", 12.0, 13.0, True)
        )

        metrics = TaskMetrics(
            task_id="task-002",
            task_description="Edit code",
            agent_name="huginn",
            model_name="model",
            start_time=0.0,
            end_time=25.0,
            iterations=iterations
        )

        assert metrics.iteration_count == 2
        assert metrics.total_tool_executions == 2
        assert metrics.total_tool_time == pytest.approx(2.0)  # 1.0 + 1.0
        assert metrics.avg_iteration_time == pytest.approx(12.5)  # (10 + 15) / 2

    def test_tool_breakdown(self):
        """Test tool usage breakdown."""
        iterations = [
            IterationMetrics(1, 0.0, 10.0, "huginn", "model"),
            IterationMetrics(2, 10.0, 20.0, "huginn", "model"),
        ]
        iterations[0].tool_executions.extend([
            ToolExecutionMetrics("read_file", 1.0, 1.5, True),
            ToolExecutionMetrics("read_file", 2.0, 2.3, True),
        ])
        iterations[1].tool_executions.extend([
            ToolExecutionMetrics("read_file", 11.0, 11.2, True),
            ToolExecutionMetrics("write_file", 12.0, 13.0, True),
            ToolExecutionMetrics("write_file", 14.0, 14.5, False),
        ])

        metrics = TaskMetrics(
            task_id="task-003",
            task_description="Refactor",
            agent_name="huginn",
            model_name="model",
            start_time=0.0,
            end_time=20.0,
            iterations=iterations
        )

        breakdown = metrics.get_tool_breakdown()
        assert "read_file" in breakdown
        assert breakdown["read_file"]["count"] == 3
        assert breakdown["read_file"]["successes"] == 3
        assert breakdown["read_file"]["failures"] == 0

        assert "write_file" in breakdown
        assert breakdown["write_file"]["count"] == 2
        assert breakdown["write_file"]["successes"] == 1
        assert breakdown["write_file"]["failures"] == 1


# ============================================================================
# Session Metrics Tests
# ============================================================================

class TestSessionMetrics:
    """Tests for SessionMetrics dataclass."""

    def test_empty_session(self):
        """Test empty session metrics."""
        metrics = SessionMetrics(
            session_id="session-001",
            task_description="Hello world",
            model_name="model",
            start_time=0.0,
            end_time=5.0
        )
        assert metrics.duration_seconds == 5.0
        assert metrics.total_iterations == 0
        assert metrics.total_tool_executions == 0

    def test_session_with_tasks(self):
        """Test session with multiple tasks."""
        task1 = TaskMetrics(
            task_id="task-001",
            task_description="Task 1",
            agent_name="brokkr",
            model_name="model",
            start_time=0.0,
            end_time=20.0,
            model_load_time=2.0
        )
        task1.iterations.append(
            IterationMetrics(1, 0.0, 20.0, "brokkr", "model")
        )

        task2 = TaskMetrics(
            task_id="task-002",
            task_description="Task 2",
            agent_name="huginn",
            model_name="model2",
            start_time=20.0,
            end_time=40.0,
            model_load_time=3.0
        )
        task2.iterations.extend([
            IterationMetrics(1, 20.0, 28.0, "huginn", "model2"),
            IterationMetrics(2, 28.0, 40.0, "huginn", "model2"),
        ])

        metrics = SessionMetrics(
            session_id="session-002",
            task_description="Main task",
            model_name="model",
            start_time=0.0,
            end_time=40.0,
            tasks=[task1, task2]
        )

        assert metrics.duration_seconds == 40.0
        assert metrics.total_iterations == 3  # 1 + 2
        assert metrics.total_model_load_time == 5.0  # 2 + 3

    def test_session_summary(self):
        """Test session summary generation."""
        task = TaskMetrics(
            task_id="task-001",
            task_description="Test task",
            agent_name="huginn",
            model_name="model",
            start_time=0.0,
            end_time=60.0,
            model_load_time=5.0
        )
        iteration = IterationMetrics(1, 0.0, 60.0, "huginn", "model")
        iteration.tool_executions.extend([
            ToolExecutionMetrics("read_file", 10.0, 11.0, True),
            ToolExecutionMetrics("write_file", 30.0, 32.0, True),
        ])
        task.iterations.append(iteration)

        metrics = SessionMetrics(
            session_id="session-003",
            task_description="Main task",
            model_name="model",
            start_time=0.0,
            end_time=60.0,
            status="completed",
            tasks=[task]
        )

        summary = metrics.get_summary()
        assert summary["session_id"] == "session-003"
        assert summary["status"] == "completed"
        assert summary["duration_seconds"] == 60.0
        assert summary["total_tasks"] == 1
        assert summary["total_iterations"] == 1
        assert summary["total_tool_executions"] == 2
        assert summary["time_breakdown"]["tool_execution"] == pytest.approx(3.0)

    def test_serialization_roundtrip(self):
        """Test that metrics serialize and deserialize correctly."""
        task = TaskMetrics(
            task_id="task-001",
            task_description="Test",
            agent_name="huginn",
            model_name="model",
            start_time=0.0,
            end_time=30.0,
            status="completed",
            model_load_time=2.5
        )
        iteration = IterationMetrics(1, 0.0, 30.0, "huginn", "model", tokens_generated=100)
        iteration.tool_executions.append(
            ToolExecutionMetrics("read_file", 5.0, 6.0, True, {"path": "/test.txt"})
        )
        task.iterations.append(iteration)

        original = SessionMetrics(
            session_id="session-roundtrip",
            task_description="Roundtrip test",
            model_name="model",
            start_time=0.0,
            end_time=30.0,
            status="completed",
            tasks=[task]
        )

        # Serialize and deserialize
        data = original.to_dict()
        restored = SessionMetrics.from_dict(data)

        # Verify
        assert restored.session_id == original.session_id
        assert restored.task_description == original.task_description
        assert restored.duration_seconds == original.duration_seconds
        assert len(restored.tasks) == 1
        assert restored.tasks[0].task_id == "task-001"
        assert restored.tasks[0].model_load_time == 2.5
        assert len(restored.tasks[0].iterations) == 1
        assert restored.tasks[0].iterations[0].tokens_generated == 100
        assert len(restored.tasks[0].iterations[0].tool_executions) == 1


# ============================================================================
# Metrics Collector Tests
# ============================================================================

class TestMetricsCollector:
    """Tests for MetricsCollector class."""

    def test_basic_collection(self):
        """Test basic metrics collection workflow."""
        collector = MetricsCollector(
            session_id="session-001",
            task_description="Test task",
            model_name="model"
        )

        # Start and end a task
        collector.start_task("task-001", "Subtask", "huginn", "model")
        collector.start_iteration(1, "huginn", "model")
        collector.record_tool_execution("read_file", 0.0, 0.5, True)
        collector.end_iteration()
        collector.end_task()
        collector.end_session()

        metrics = collector.get_metrics()
        assert metrics.status == "completed"
        assert len(metrics.tasks) == 1
        assert metrics.tasks[0].iteration_count == 1
        assert metrics.tasks[0].total_tool_executions == 1

    def test_multiple_iterations(self):
        """Test collecting multiple iterations."""
        collector = MetricsCollector(
            session_id="session-002",
            task_description="Multi-iteration",
            model_name="model"
        )

        collector.start_task("task-001", "Task", "huginn", "model")

        for i in range(3):
            collector.start_iteration(i + 1, "huginn", "model")
            collector.record_tool_execution("read_file", 0.0, 0.1, True)
            collector.end_iteration()

        collector.end_task()
        collector.end_session()

        metrics = collector.get_metrics()
        assert metrics.tasks[0].iteration_count == 3
        assert metrics.tasks[0].total_tool_executions == 3

    def test_incomplete_task_handling(self):
        """Test that incomplete tasks/iterations are handled."""
        collector = MetricsCollector(
            session_id="session-003",
            task_description="Incomplete",
            model_name="model"
        )

        collector.start_task("task-001", "Task", "huginn", "model")
        collector.start_iteration(1, "huginn", "model")
        # Don't end iteration or task

        collector.end_session(status="failed")

        metrics = collector.get_metrics()
        assert metrics.status == "failed"
        assert len(metrics.tasks) == 1
        assert metrics.tasks[0].status == "incomplete"

    def test_real_time_duration(self):
        """Test real-time duration calculation."""
        collector = MetricsCollector(
            session_id="session-004",
            task_description="Duration test",
            model_name="model"
        )

        collector.start_task("task-001", "Task", "huginn", "model")

        # Should have some duration even without ending
        time.sleep(0.01)  # Small delay
        duration = collector.get_session_duration()
        assert duration > 0

        task_duration = collector.get_current_task_duration()
        assert task_duration > 0


# ============================================================================
# Metrics Store Tests
# ============================================================================

class TestMetricsStore:
    """Tests for MetricsStore database operations."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path, auto_backup=False)
            yield db

    @pytest.fixture
    def store(self, temp_db):
        """Create a metrics store with temp database."""
        return MetricsStore(temp_db)

    @pytest.mark.asyncio
    async def test_save_and_load_metrics(self, store):
        """Test saving and loading session metrics."""
        # Create sample metrics
        task = TaskMetrics(
            task_id="task-001",
            task_description="Test task",
            agent_name="huginn",
            model_name="model",
            start_time=0.0,
            end_time=30.0,
            status="completed"
        )
        task.iterations.append(
            IterationMetrics(1, 0.0, 30.0, "huginn", "model")
        )

        original = SessionMetrics(
            session_id="test-session-001",
            task_description="Main task",
            model_name="model",
            start_time=0.0,
            end_time=30.0,
            status="completed",
            tasks=[task]
        )

        # Save
        await store.save_metrics(original)

        # Load
        loaded = await store.load_metrics("test-session-001")

        assert loaded is not None
        assert loaded.session_id == original.session_id
        assert loaded.duration_seconds == original.duration_seconds
        assert len(loaded.tasks) == 1

    @pytest.mark.asyncio
    async def test_list_metrics(self, store):
        """Test listing recent metrics."""
        # Save multiple sessions
        for i in range(5):
            metrics = SessionMetrics(
                session_id=f"session-{i:03d}",
                task_description=f"Task {i}",
                model_name="model",
                start_time=0.0,
                end_time=float(10 + i),
                status="completed"
            )
            await store.save_metrics(metrics)

        # List with limit
        sessions = await store.list_metrics(limit=3)
        assert len(sessions) == 3

    @pytest.mark.asyncio
    async def test_aggregate_stats(self, store):
        """Test aggregate statistics calculation."""
        # Save some sessions with different metrics
        for i in range(3):
            task = TaskMetrics(
                task_id=f"task-{i}",
                task_description=f"Task {i}",
                agent_name="huginn",
                model_name="model",
                start_time=0.0,
                end_time=float(10 * (i + 1))
            )
            task.iterations.append(
                IterationMetrics(1, 0.0, float(10 * (i + 1)), "huginn", "model")
            )
            task.iterations[0].tool_executions.extend([
                ToolExecutionMetrics("tool", 0.0, 1.0, True)
                for _ in range(i + 1)
            ])

            metrics = SessionMetrics(
                session_id=f"session-{i:03d}",
                task_description=f"Task {i}",
                model_name="model",
                start_time=0.0,
                end_time=float(10 * (i + 1)),
                status="completed",
                tasks=[task]
            )
            await store.save_metrics(metrics)

        stats = await store.get_aggregate_stats()
        assert stats["total_sessions"] == 3
        assert stats["total_iterations"] == 3
        # 1 + 2 + 3 = 6 tool executions total
        assert stats["total_tool_executions"] == 6

    @pytest.mark.asyncio
    async def test_delete_metrics(self, store):
        """Test deleting metrics."""
        metrics = SessionMetrics(
            session_id="to-delete",
            task_description="Delete me",
            model_name="model",
            start_time=0.0,
            end_time=10.0
        )
        await store.save_metrics(metrics)

        # Verify saved
        loaded = await store.load_metrics("to-delete")
        assert loaded is not None

        # Delete
        deleted = await store.delete_metrics("to-delete")
        assert deleted is True

        # Verify deleted
        loaded = await store.load_metrics("to-delete")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_load_nonexistent(self, store):
        """Test loading non-existent metrics returns None."""
        loaded = await store.load_metrics("nonexistent-session")
        assert loaded is None


# ============================================================================
# Header Widget Tests
# ============================================================================

class TestHeaderMetricsDisplay:
    """Tests for header widget metrics display."""

    def test_task_duration_formatting(self):
        """Test that task duration formats correctly."""
        from sindri.tui.widgets.header import SindriHeader

        header = SindriHeader()

        # Test seconds
        header.update_task_metrics(45.5, 3)
        assert header.task_duration == 45.5
        assert header.current_iteration == 3

        # Test minutes
        header.update_task_metrics(125.0, 5)
        assert header.task_duration == 125.0

    def test_reset_metrics(self):
        """Test resetting metrics."""
        from sindri.tui.widgets.header import SindriHeader

        header = SindriHeader()
        header.update_task_metrics(100.0, 10)

        assert header.task_duration == 100.0
        assert header.current_iteration == 10

        header.reset_task_metrics()

        assert header.task_duration == 0.0
        assert header.current_iteration == 0
