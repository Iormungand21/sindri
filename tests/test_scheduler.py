"""Tests for task scheduler."""

import pytest

from sindri.core.tasks import Task, TaskStatus
from sindri.core.scheduler import TaskScheduler
from sindri.llm.manager import ModelManager


@pytest.fixture
def scheduler():
    """Create a scheduler for testing."""
    model_manager = ModelManager(total_vram_gb=16.0, reserve_gb=2.0)
    return TaskScheduler(model_manager)


def test_add_task(scheduler):
    """Test adding a task to scheduler."""
    task = Task(description="Test task", assigned_agent="brokkr")

    task_id = scheduler.add_task(task)

    assert task_id == task.id
    assert task.id in scheduler.tasks
    assert len(scheduler.pending) == 1


def test_get_next_task_priority(scheduler):
    """Test that scheduler returns highest priority task."""
    task1 = Task(description="Low priority", priority=5, assigned_agent="brokkr")
    task2 = Task(description="High priority", priority=1, assigned_agent="brokkr")
    task3 = Task(description="Medium priority", priority=3, assigned_agent="brokkr")

    scheduler.add_task(task1)
    scheduler.add_task(task2)
    scheduler.add_task(task3)

    next_task = scheduler.get_next_task()

    assert next_task.id == task2.id  # Highest priority (lowest number)


def test_dependencies_satisfied(scheduler):
    """Test dependency checking."""
    task1 = Task(description="First task", assigned_agent="brokkr")
    task2 = Task(description="Second task", assigned_agent="brokkr")
    task2.add_dependency(task1.id)

    scheduler.add_task(task1)
    scheduler.add_task(task2)

    # task2 should not be returned yet (dependency not complete)
    next_task = scheduler.get_next_task()
    assert next_task.id == task1.id

    # Complete task1 using scheduler's method
    scheduler.update_task_status(task1.id, TaskStatus.COMPLETE)

    # Now task2 should be available
    next_task = scheduler.get_next_task()
    assert next_task is not None
    assert next_task.id == task2.id


def test_get_pending_count(scheduler):
    """Test counting pending tasks."""
    task1 = Task(description="Task 1", assigned_agent="brokkr")
    task2 = Task(description="Task 2", assigned_agent="brokkr")
    task3 = Task(
        description="Task 3", assigned_agent="brokkr", status=TaskStatus.RUNNING
    )

    scheduler.add_task(task1)
    scheduler.add_task(task2)
    scheduler.add_task(task3)

    assert scheduler.get_pending_count() == 2  # Only pending tasks


def test_has_work(scheduler):
    """Test checking if scheduler has work."""
    assert not scheduler.has_work()

    task = Task(description="Test task", assigned_agent="brokkr")
    scheduler.add_task(task)

    assert scheduler.has_work()

    task.status = TaskStatus.COMPLETE

    assert not scheduler.has_work()
