"""Shared test fixtures."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock


@pytest.fixture
def temp_dir():
    """Temporary directory for tests."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def mock_ollama(mocker):
    """Mock Ollama client."""
    mock_async_client = mocker.patch("sindri.llm.client.ollama.AsyncClient")
    mock_sync_client = mocker.patch("sindri.llm.client.ollama.Client")

    # Configure default mock responses
    mock_async_client.return_value.chat = AsyncMock(
        return_value={
            "message": {
                "role": "assistant",
                "content": "Test response",
                "tool_calls": None,
            },
            "model": "test-model",
            "done": True,
        }
    )

    mock_sync_client.return_value.list = Mock(
        return_value={"models": [{"name": "test-model"}]}
    )

    return {"async_client": mock_async_client, "sync_client": mock_sync_client}


@pytest.fixture
def db(temp_dir):
    """Test database."""
    from sindri.persistence.database import Database

    db_path = temp_dir / "test.db"
    return Database(db_path)


@pytest.fixture
def session_state(db):
    """Test session state manager."""
    from sindri.persistence.state import SessionState

    return SessionState(db)


@pytest.fixture
def ollama_client():
    """Mock OllamaClient instance."""
    from sindri.llm.client import OllamaClient, Response, Message

    client = Mock(spec=OllamaClient)

    # Default chat response
    client.chat = AsyncMock(
        return_value=Response(
            message=Message(role="assistant", content="Test response", tool_calls=None),
            model="test-model",
            done=True,
        )
    )

    return client


@pytest.fixture
def tool_registry():
    """Test tool registry with minimal tools."""
    from sindri.tools.registry import ToolRegistry

    return ToolRegistry.default()


@pytest.fixture
def recovery_manager(temp_dir):
    """Test recovery manager."""
    from sindri.core.recovery import RecoveryManager

    return RecoveryManager(str(temp_dir / "state"))


@pytest.fixture
def config(temp_dir):
    """Test configuration."""
    from sindri.config import SindriConfig

    return SindriConfig(
        data_dir=temp_dir, project_dir=temp_dir, total_vram_gb=16.0, reserve_vram_gb=2.0
    )


@pytest.fixture
def event_bus():
    """Test event bus."""
    from sindri.core.events import EventBus

    return EventBus()


@pytest.fixture
async def agent_loop(ollama_client, tool_registry, session_state, config):
    """Test agent loop instance."""
    from sindri.core.loop import AgentLoop, LoopConfig

    loop_config = LoopConfig(
        max_iterations=10,
        completion_marker="<sindri:complete/>",
        stuck_threshold=3,
        checkpoint_interval=5,
    )

    return AgentLoop(
        client=ollama_client,
        tools=tool_registry,
        state=session_state,
        config=loop_config,
    )


@pytest.fixture
def mock_embedder(mocker):
    """Mock embedding client."""
    mock = mocker.patch("sindri.memory.embedder.LocalEmbedder")

    # Return fixed 768-dim embedding
    mock.return_value.embed = Mock(return_value=[0.1] * 768)
    mock.return_value.embed_batch = Mock(return_value=[[0.1] * 768])
    mock.return_value.similarity = Mock(return_value=0.95)

    return mock
