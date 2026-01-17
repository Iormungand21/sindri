"""Tests for delegation manager."""

import pytest

from sindri.core.tasks import Task, TaskStatus
from sindri.core.scheduler import TaskScheduler
from sindri.core.delegation import DelegationManager, DelegationRequest
from sindri.llm.manager import ModelManager


@pytest.fixture
def scheduler():
    """Create a scheduler for testing."""
    model_manager = ModelManager(total_vram_gb=16.0, reserve_gb=2.0)
    return TaskScheduler(model_manager)


@pytest.fixture
def delegation_manager(scheduler):
    """Create a delegation manager for testing."""
    return DelegationManager(scheduler)


@pytest.mark.asyncio
async def test_delegate_creates_child(scheduler, delegation_manager):
    """Test that delegation creates a child task."""
    parent = Task(description="Parent task", assigned_agent="brokkr")
    scheduler.add_task(parent)

    request = DelegationRequest(
        target_agent="huginn",
        task_description="Write some code",
        context={"language": "python"},
        constraints=["Use type hints"],
        success_criteria=["Code runs without errors"],
    )

    child = await delegation_manager.delegate(parent, request)

    assert child.parent_id == parent.id
    assert child.id in parent.subtask_ids
    assert child.assigned_agent == "huginn"
    assert parent.status == TaskStatus.WAITING
    assert child.id in scheduler.tasks


@pytest.mark.asyncio
async def test_child_completed_resumes_parent(scheduler, delegation_manager):
    """Test that completing all children resumes parent."""
    parent = Task(description="Parent task", assigned_agent="brokkr")
    scheduler.add_task(parent)

    request = DelegationRequest(
        target_agent="huginn",
        task_description="Write some code",
        context={},
        constraints=[],
        success_criteria=[],
    )

    child = await delegation_manager.delegate(parent, request)

    # Complete the child
    child.status = TaskStatus.COMPLETE

    await delegation_manager.child_completed(child)

    # Parent should be resumed
    assert parent.status == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_child_failed_fails_parent(scheduler, delegation_manager):
    """Test that child failure fails parent."""
    parent = Task(description="Parent task", assigned_agent="brokkr")
    scheduler.add_task(parent)

    request = DelegationRequest(
        target_agent="huginn",
        task_description="Write some code",
        context={},
        constraints=[],
        success_criteria=[],
    )

    child = await delegation_manager.delegate(parent, request)

    # Fail the child
    child.status = TaskStatus.FAILED
    child.error = "Compilation error"

    await delegation_manager.child_failed(child)

    # Parent should be failed
    assert parent.status == TaskStatus.FAILED
    assert "Compilation error" in parent.error


@pytest.mark.asyncio
async def test_invalid_delegation_target(scheduler, delegation_manager):
    """Test delegation to invalid agent."""
    parent = Task(description="Parent task", assigned_agent="brokkr")
    scheduler.add_task(parent)

    request = DelegationRequest(
        target_agent="nonexistent",
        task_description="Do something",
        context={},
        constraints=[],
        success_criteria=[],
    )

    with pytest.raises(ValueError, match="Unknown agent"):
        await delegation_manager.delegate(parent, request)
