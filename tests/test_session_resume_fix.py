"""Test session resume fix for hierarchical agent loop."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from sindri.core.hierarchical import HierarchicalAgentLoop
from sindri.core.tasks import Task, TaskStatus
from sindri.core.loop import LoopConfig
from sindri.persistence.state import Session, Turn
from sindri.agents.definitions import AgentDefinition


@pytest.fixture
def mock_brokkr_agent():
    """Fixture that provides a mock brokkr agent and restores original after test."""
    from sindri.agents.registry import AGENTS

    # Save original
    original_brokkr = AGENTS.get("brokkr")

    # Create mock agent
    agent = AgentDefinition(
        name="brokkr",
        role="orchestrator",
        model="test-model",
        system_prompt="Test prompt",
        tools=[],
        max_iterations=10,
        can_delegate=True,
        delegate_to=[]
    )
    AGENTS["brokkr"] = agent

    yield agent

    # Restore original
    if original_brokkr is not None:
        AGENTS["brokkr"] = original_brokkr


@pytest.mark.asyncio
async def test_new_task_creates_new_session(mock_brokkr_agent):
    """Test that a new task without session_id creates a new session."""

    # Setup mocks
    client = AsyncMock()
    tools = MagicMock()
    tools.get_schemas.return_value = []
    state = AsyncMock()
    scheduler = MagicMock()
    scheduler.model_manager.ensure_loaded = AsyncMock(return_value=True)
    delegation = AsyncMock()
    config = LoopConfig(max_iterations=1, completion_marker="<done/>")

    # Mock session creation
    new_session = Session(
        id="new-session-id",
        task="Test task",
        model="test-model",
        status="active"
    )
    state.create_session = AsyncMock(return_value=new_session)
    state.load_session = AsyncMock(return_value=None)
    state.complete_session = AsyncMock()

    # Mock LLM response with completion
    response = MagicMock()
    response.message.content = "Task done <done/>"
    response.message.tool_calls = None
    client.chat = AsyncMock(return_value=response)

    loop = HierarchicalAgentLoop(
        client=client,
        tools=tools,
        state=state,
        scheduler=scheduler,
        delegation=delegation,
        config=config
    )

    # Create task without session_id
    task = Task(
        description="Test task",
        assigned_agent="brokkr"
    )

    # Run the loop (mock_brokkr_agent fixture already set up the agent)
    await loop.run_task(task)

    # Verify new session was created (not loaded)
    state.create_session.assert_called_once()
    state.load_session.assert_not_called()

    # Verify task has session_id set
    assert task.session_id == "new-session-id"


@pytest.mark.asyncio
async def test_task_with_session_id_resumes_session(mock_brokkr_agent):
    """Test that a task with existing session_id loads that session."""

    # Setup mocks
    client = AsyncMock()
    tools = MagicMock()
    tools.get_schemas.return_value = []
    state = AsyncMock()
    scheduler = MagicMock()
    scheduler.model_manager.ensure_loaded = AsyncMock(return_value=True)
    delegation = AsyncMock()
    config = LoopConfig(max_iterations=1, completion_marker="<done/>")

    # Mock session loading
    existing_session = Session(
        id="existing-session-id",
        task="Test task",
        model="test-model",
        status="active"
    )
    # Add some conversation history
    existing_session.add_turn("user", "Original request")
    existing_session.add_turn("assistant", "I'll delegate this")
    existing_session.add_turn("tool", "Child completed successfully!")

    state.create_session = AsyncMock()
    state.load_session = AsyncMock(return_value=existing_session)
    state.complete_session = AsyncMock()

    # Mock LLM response with completion
    response = MagicMock()
    response.message.content = "Great! Task done <done/>"
    response.message.tool_calls = None
    client.chat = AsyncMock(return_value=response)

    loop = HierarchicalAgentLoop(
        client=client,
        tools=tools,
        state=state,
        scheduler=scheduler,
        delegation=delegation,
        config=config
    )

    # Create task WITH session_id (resuming)
    task = Task(
        description="Test task",
        assigned_agent="brokkr",
        session_id="existing-session-id"  # Key: task already has session_id
    )

    # Run the loop (mock_brokkr_agent fixture already set up the agent)
    await loop.run_task(task)

    # Verify session was LOADED (not created)
    state.load_session.assert_called_once_with("existing-session-id")
    state.create_session.assert_not_called()

    # Verify the session has the conversation history preserved
    # Should have: 3 original turns + 1 new assistant response = 4 total
    assert len(existing_session.turns) == 4

    # Verify original 3 turns are still there
    assert existing_session.turns[0].content == "Original request"
    assert existing_session.turns[1].content == "I'll delegate this"
    assert existing_session.turns[2].content == "Child completed successfully!"

    # Verify new turn was added from the loop
    assert existing_session.turns[3].content == "Great! Task done <done/>"
    assert existing_session.turns[3].role == "assistant"


@pytest.mark.asyncio
async def test_session_load_failure_falls_back_to_create(mock_brokkr_agent):
    """Test that if session load fails, we create a new session."""

    # Setup mocks
    client = AsyncMock()
    tools = MagicMock()
    tools.get_schemas.return_value = []
    state = AsyncMock()
    scheduler = MagicMock()
    scheduler.model_manager.ensure_loaded = AsyncMock(return_value=True)
    delegation = AsyncMock()
    config = LoopConfig(max_iterations=1, completion_marker="<done/>")

    # Mock session loading to return None (session not found)
    fallback_session = Session(
        id="fallback-session-id",
        task="Test task",
        model="test-model",
        status="active"
    )
    state.create_session = AsyncMock(return_value=fallback_session)
    state.load_session = AsyncMock(return_value=None)
    state.complete_session = AsyncMock()

    # Mock LLM response
    response = MagicMock()
    response.message.content = "Done <done/>"
    response.message.tool_calls = None
    client.chat = AsyncMock(return_value=response)

    loop = HierarchicalAgentLoop(
        client=client,
        tools=tools,
        state=state,
        scheduler=scheduler,
        delegation=delegation,
        config=config
    )

    # Create task with session_id that doesn't exist
    task = Task(
        description="Test task",
        assigned_agent="brokkr",
        session_id="nonexistent-session-id"
    )

    # Run the loop (mock_brokkr_agent fixture already set up the agent)
    await loop.run_task(task)

    # Verify load was attempted but create was used as fallback
    state.load_session.assert_called_once_with("nonexistent-session-id")
    state.create_session.assert_called_once()

    # Verify task got new session_id
    assert task.session_id == "fallback-session-id"
