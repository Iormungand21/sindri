"""Tests for Sindri Web API.

Phase 8.3: Tests for FastAPI-based Web API server.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from sindri.web.server import create_app, SindriAPI
from sindri.agents.registry import AGENTS
from sindri.persistence.state import Session, Turn


# ===== Fixtures =====

@pytest.fixture
def app():
    """Create test application."""
    return create_app(vram_gb=16.0)


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
async def async_client(app):
    """Create async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


# ===== Health Endpoint Tests =====

class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_check_basic(self, client):
        """Test basic health check response."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert "version" in data
        assert data["version"] == "0.1.0"
        assert "ollama_connected" in data
        assert "database_ok" in data
        assert "timestamp" in data

    def test_health_check_has_timestamp(self, client):
        """Test that health check includes timestamp."""
        response = client.get("/health")
        data = response.json()

        # Should be an ISO format timestamp
        assert "timestamp" in data
        assert "T" in data["timestamp"]  # ISO format has T separator


# ===== Agent Endpoints Tests =====

class TestAgentEndpoints:
    """Tests for agent-related endpoints."""

    def test_list_agents(self, client):
        """Test listing all agents."""
        response = client.get("/api/agents")
        assert response.status_code == 200
        agents = response.json()

        # Should return all registered agents
        assert len(agents) == len(AGENTS)

        # Check agent structure
        agent_names = {a["name"] for a in agents}
        assert "brokkr" in agent_names
        assert "huginn" in agent_names
        assert "mimir" in agent_names

    def test_list_agents_structure(self, client):
        """Test agent response structure."""
        response = client.get("/api/agents")
        agents = response.json()

        for agent in agents:
            assert "name" in agent
            assert "role" in agent
            assert "model" in agent
            assert "tools" in agent
            assert "can_delegate" in agent
            assert "estimated_vram_gb" in agent
            assert "max_iterations" in agent

    def test_get_agent_brokkr(self, client):
        """Test getting specific agent (brokkr)."""
        # Re-import to ensure fresh registry (in case other tests modified it)
        from sindri.agents.registry import AGENTS, get_agent

        response = client.get("/api/agents/brokkr")
        assert response.status_code == 200
        agent = response.json()

        assert agent["name"] == "brokkr"
        assert agent["can_delegate"] == True
        assert isinstance(agent["tools"], list)
        assert agent["estimated_vram_gb"] > 0

    def test_get_agent_huginn(self, client):
        """Test getting specific agent (huginn)."""
        response = client.get("/api/agents/huginn")
        assert response.status_code == 200
        agent = response.json()

        assert agent["name"] == "huginn"
        assert "write_file" in agent["tools"]

    def test_get_agent_not_found(self, client):
        """Test getting non-existent agent."""
        response = client.get("/api/agents/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_agent_has_fallback_model(self, client):
        """Test that agents can have fallback models."""
        response = client.get("/api/agents/brokkr")
        agent = response.json()

        # Brokkr has a fallback model defined
        assert "fallback_model" in agent


# ===== Session Endpoints Tests =====

class TestSessionEndpoints:
    """Tests for session-related endpoints."""

    def test_list_sessions_empty(self, client):
        """Test listing sessions when empty."""
        with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock:
            mock.return_value = []
            response = client.get("/api/sessions")
            assert response.status_code == 200
            assert response.json() == []

    def test_list_sessions_with_limit(self, client):
        """Test listing sessions with limit parameter."""
        mock_sessions = [
            {"id": f"session-{i}", "task": f"Task {i}", "model": "qwen2.5:7b",
             "status": "completed", "created_at": "2026-01-15T10:00:00", "iterations": 5}
            for i in range(30)
        ]

        with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock:
            mock.return_value = mock_sessions[:10]
            response = client.get("/api/sessions?limit=10")
            assert response.status_code == 200
            sessions = response.json()
            assert len(sessions) <= 10

    def test_list_sessions_with_status_filter(self, client):
        """Test listing sessions with status filter."""
        mock_sessions = [
            {"id": "s1", "task": "Task 1", "model": "qwen2.5:7b",
             "status": "completed", "created_at": "2026-01-15T10:00:00", "iterations": 5},
            {"id": "s2", "task": "Task 2", "model": "qwen2.5:7b",
             "status": "failed", "created_at": "2026-01-15T11:00:00", "iterations": 10},
        ]

        with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock:
            mock.return_value = mock_sessions
            response = client.get("/api/sessions?status=completed")
            assert response.status_code == 200
            sessions = response.json()
            assert all(s["status"] == "completed" for s in sessions)

    def test_get_session_detail(self, client):
        """Test getting session details."""
        from datetime import datetime

        mock_session = Session(
            id="test-session-1234567890123456789012345678",
            task="Test task",
            model="qwen2.5:7b",
            status="completed",
            iterations=5,
            created_at=datetime(2026, 1, 15, 10, 0, 0),
            completed_at=datetime(2026, 1, 15, 10, 5, 0)
        )
        mock_session.turns = [
            Turn(role="user", content="Do something", created_at=datetime(2026, 1, 15, 10, 0, 0)),
            Turn(role="assistant", content="Done!", created_at=datetime(2026, 1, 15, 10, 5, 0))
        ]

        with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock_list:
            with patch.object(client.app.state.api.state, 'load_session', new_callable=AsyncMock) as mock_load:
                # For short ID lookup
                mock_list.return_value = [
                    {"id": "test-session-1234567890123456789012345678", "task": "Test task"}
                ]
                mock_load.return_value = mock_session

                # Use full ID to avoid short ID lookup
                response = client.get("/api/sessions/test-session-1234567890123456789012345678")
                assert response.status_code == 200
                data = response.json()

                assert data["id"] == "test-session-1234567890123456789012345678"
                assert data["task"] == "Test task"
                assert data["status"] == "completed"
                assert len(data["turns"]) == 2

    def test_get_session_not_found(self, client):
        """Test getting non-existent session."""
        with patch.object(client.app.state.api.state, 'load_session', new_callable=AsyncMock) as mock_load:
            with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock_list:
                mock_load.return_value = None
                mock_list.return_value = []

                response = client.get("/api/sessions/nonexistent-session")
                assert response.status_code == 404

    def test_get_session_short_id(self, client):
        """Test getting session with short ID."""
        from datetime import datetime

        mock_session = Session(
            id="abcd1234-5678-9012-3456-789012345678",
            task="Test task",
            model="qwen2.5:7b",
            status="completed",
            iterations=5,
            created_at=datetime(2026, 1, 15, 10, 0, 0)
        )

        with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock_list:
            with patch.object(client.app.state.api.state, 'load_session', new_callable=AsyncMock) as mock_load:
                mock_list.return_value = [
                    {"id": "abcd1234-5678-9012-3456-789012345678", "task": "Test"}
                ]
                mock_load.return_value = mock_session

                response = client.get("/api/sessions/abcd1234")
                assert response.status_code == 200
                assert response.json()["id"] == "abcd1234-5678-9012-3456-789012345678"


# ===== File Changes Endpoint Tests =====

class TestFileChangesEndpoint:
    """Tests for the /api/sessions/{id}/file-changes endpoint."""

    def test_get_file_changes_empty_session(self, client):
        """Test file changes for session with no file operations."""
        from datetime import datetime

        mock_session = Session(
            id="test-session-1234567890123456789012345678",
            task="Test task with no files",
            model="qwen2.5:7b",
            status="completed",
            iterations=5,
            created_at=datetime(2026, 1, 15, 10, 0, 0)
        )
        mock_session.turns = [
            Turn(role="user", content="Hello", created_at=datetime(2026, 1, 15, 10, 0, 0)),
            Turn(role="assistant", content="Hi!", created_at=datetime(2026, 1, 15, 10, 1, 0))
        ]

        with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock_list:
            with patch.object(client.app.state.api.state, 'load_session', new_callable=AsyncMock) as mock_load:
                mock_list.return_value = [
                    {"id": "test-session-1234567890123456789012345678", "task": "Test task"}
                ]
                mock_load.return_value = mock_session

                response = client.get("/api/sessions/test-session-1234567890123456789012345678/file-changes")
                assert response.status_code == 200
                data = response.json()

                assert data["session_id"] == "test-session-1234567890123456789012345678"
                assert data["total_changes"] == 0
                assert data["file_changes"] == []
                assert data["files_modified"] == []

    def test_get_file_changes_with_write(self, client):
        """Test file changes for session with write_file operation."""
        from datetime import datetime

        mock_session = Session(
            id="test-session-write-12345678901234567890",
            task="Create a file",
            model="qwen2.5:7b",
            status="completed",
            iterations=3,
            created_at=datetime(2026, 1, 15, 10, 0, 0)
        )
        mock_session.turns = [
            Turn(
                role="user",
                content="Create hello.py",
                created_at=datetime(2026, 1, 15, 10, 0, 0)
            ),
            Turn(
                role="assistant",
                content="I'll create the file",
                tool_calls=[{
                    "function": {
                        "name": "write_file",
                        "arguments": {
                            "path": "/tmp/hello.py",
                            "content": 'print("Hello, World!")'
                        }
                    }
                }],
                created_at=datetime(2026, 1, 15, 10, 1, 0)
            )
        ]

        with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock_list:
            with patch.object(client.app.state.api.state, 'load_session', new_callable=AsyncMock) as mock_load:
                mock_list.return_value = [
                    {"id": "test-session-write-12345678901234567890", "task": "Create a file"}
                ]
                mock_load.return_value = mock_session

                response = client.get("/api/sessions/test-session-write-12345678901234567890/file-changes")
                assert response.status_code == 200
                data = response.json()

                assert data["total_changes"] == 1
                assert len(data["file_changes"]) == 1
                assert data["files_modified"] == ["/tmp/hello.py"]

                change = data["file_changes"][0]
                assert change["file_path"] == "/tmp/hello.py"
                assert change["operation"] == "write"
                assert change["new_content"] == 'print("Hello, World!")'
                assert change["content_size"] == 22

    def test_get_file_changes_with_edit(self, client):
        """Test file changes for session with edit_file operation."""
        from datetime import datetime

        mock_session = Session(
            id="test-session-edit-123456789012345678901",
            task="Edit a file",
            model="qwen2.5:7b",
            status="completed",
            iterations=3,
            created_at=datetime(2026, 1, 15, 10, 0, 0)
        )
        mock_session.turns = [
            Turn(
                role="assistant",
                content="I'll edit the file",
                tool_calls=[{
                    "function": {
                        "name": "edit_file",
                        "arguments": {
                            "path": "/tmp/hello.py",
                            "old_text": 'print("Hello")',
                            "new_text": 'print("Hello, World!")'
                        }
                    }
                }],
                created_at=datetime(2026, 1, 15, 10, 1, 0)
            )
        ]

        with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock_list:
            with patch.object(client.app.state.api.state, 'load_session', new_callable=AsyncMock) as mock_load:
                mock_list.return_value = [
                    {"id": "test-session-edit-123456789012345678901", "task": "Edit a file"}
                ]
                mock_load.return_value = mock_session

                response = client.get("/api/sessions/test-session-edit-123456789012345678901/file-changes")
                assert response.status_code == 200
                data = response.json()

                assert data["total_changes"] == 1
                change = data["file_changes"][0]
                assert change["file_path"] == "/tmp/hello.py"
                assert change["operation"] == "edit"
                assert change["old_text"] == 'print("Hello")'
                assert change["new_text"] == 'print("Hello, World!")'

    def test_get_file_changes_with_read(self, client):
        """Test file changes includes read operations."""
        from datetime import datetime

        mock_session = Session(
            id="test-session-read-123456789012345678901",
            task="Read a file",
            model="qwen2.5:7b",
            status="completed",
            iterations=3,
            created_at=datetime(2026, 1, 15, 10, 0, 0)
        )
        mock_session.turns = [
            Turn(
                role="assistant",
                content="I'll read the file",
                tool_calls=[{
                    "function": {
                        "name": "read_file",
                        "arguments": {"path": "/tmp/hello.py"}
                    }
                }],
                created_at=datetime(2026, 1, 15, 10, 1, 0)
            )
        ]

        with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock_list:
            with patch.object(client.app.state.api.state, 'load_session', new_callable=AsyncMock) as mock_load:
                mock_list.return_value = [
                    {"id": "test-session-read-123456789012345678901", "task": "Read a file"}
                ]
                mock_load.return_value = mock_session

                response = client.get("/api/sessions/test-session-read-123456789012345678901/file-changes")
                assert response.status_code == 200
                data = response.json()

                assert data["total_changes"] == 1
                change = data["file_changes"][0]
                assert change["file_path"] == "/tmp/hello.py"
                assert change["operation"] == "read"
                # Read operations don't modify files
                assert "/tmp/hello.py" not in data["files_modified"]

    def test_get_file_changes_multiple_operations(self, client):
        """Test file changes with multiple file operations."""
        from datetime import datetime

        mock_session = Session(
            id="test-session-multi-12345678901234567890",
            task="Multiple file ops",
            model="qwen2.5:7b",
            status="completed",
            iterations=5,
            created_at=datetime(2026, 1, 15, 10, 0, 0)
        )
        mock_session.turns = [
            Turn(
                role="assistant",
                content="Working...",
                tool_calls=[
                    {
                        "function": {
                            "name": "write_file",
                            "arguments": {"path": "/tmp/file1.py", "content": "# File 1"}
                        }
                    },
                    {
                        "function": {
                            "name": "write_file",
                            "arguments": {"path": "/tmp/file2.py", "content": "# File 2"}
                        }
                    }
                ],
                created_at=datetime(2026, 1, 15, 10, 1, 0)
            ),
            Turn(
                role="assistant",
                content="Editing...",
                tool_calls=[{
                    "function": {
                        "name": "edit_file",
                        "arguments": {
                            "path": "/tmp/file1.py",
                            "old_text": "# File 1",
                            "new_text": "# Modified File 1"
                        }
                    }
                }],
                created_at=datetime(2026, 1, 15, 10, 2, 0)
            )
        ]

        with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock_list:
            with patch.object(client.app.state.api.state, 'load_session', new_callable=AsyncMock) as mock_load:
                mock_list.return_value = [
                    {"id": "test-session-multi-12345678901234567890", "task": "Multiple"}
                ]
                mock_load.return_value = mock_session

                response = client.get("/api/sessions/test-session-multi-12345678901234567890/file-changes")
                assert response.status_code == 200
                data = response.json()

                assert data["total_changes"] == 3
                assert len(data["files_modified"]) == 2
                assert "/tmp/file1.py" in data["files_modified"]
                assert "/tmp/file2.py" in data["files_modified"]

    def test_get_file_changes_exclude_content(self, client):
        """Test file changes with include_content=false."""
        from datetime import datetime

        mock_session = Session(
            id="test-session-nocontent-123456789012345",
            task="Test no content",
            model="qwen2.5:7b",
            status="completed",
            iterations=3,
            created_at=datetime(2026, 1, 15, 10, 0, 0)
        )
        mock_session.turns = [
            Turn(
                role="assistant",
                content="Writing...",
                tool_calls=[{
                    "function": {
                        "name": "write_file",
                        "arguments": {"path": "/tmp/test.py", "content": "big content"}
                    }
                }],
                created_at=datetime(2026, 1, 15, 10, 1, 0)
            )
        ]

        with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock_list:
            with patch.object(client.app.state.api.state, 'load_session', new_callable=AsyncMock) as mock_load:
                mock_list.return_value = [
                    {"id": "test-session-nocontent-123456789012345", "task": "Test"}
                ]
                mock_load.return_value = mock_session

                response = client.get(
                    "/api/sessions/test-session-nocontent-123456789012345/file-changes?include_content=false"
                )
                assert response.status_code == 200
                data = response.json()

                change = data["file_changes"][0]
                assert change["new_content"] is None  # Content excluded
                assert change["content_size"] == 11  # Size still tracked

    def test_get_file_changes_short_id(self, client):
        """Test file changes with short session ID."""
        from datetime import datetime

        mock_session = Session(
            id="abcd1234-5678-9012-3456-789012345678",
            task="Test short ID",
            model="qwen2.5:7b",
            status="completed",
            iterations=2,
            created_at=datetime(2026, 1, 15, 10, 0, 0)
        )
        mock_session.turns = []

        with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock_list:
            with patch.object(client.app.state.api.state, 'load_session', new_callable=AsyncMock) as mock_load:
                mock_list.return_value = [
                    {"id": "abcd1234-5678-9012-3456-789012345678", "task": "Test"}
                ]
                mock_load.return_value = mock_session

                response = client.get("/api/sessions/abcd1234/file-changes")
                assert response.status_code == 200
                assert response.json()["session_id"] == "abcd1234-5678-9012-3456-789012345678"

    def test_get_file_changes_not_found(self, client):
        """Test file changes for non-existent session."""
        with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock_list:
            with patch.object(client.app.state.api.state, 'load_session', new_callable=AsyncMock) as mock_load:
                mock_list.return_value = []
                mock_load.return_value = None

                response = client.get("/api/sessions/nonexistent/file-changes")
                assert response.status_code == 404

    def test_get_file_changes_json_string_arguments(self, client):
        """Test file changes when tool_call arguments are JSON strings."""
        from datetime import datetime

        mock_session = Session(
            id="test-session-jsonargs-1234567890123456",
            task="JSON args test",
            model="qwen2.5:7b",
            status="completed",
            iterations=2,
            created_at=datetime(2026, 1, 15, 10, 0, 0)
        )
        mock_session.turns = [
            Turn(
                role="assistant",
                content="Writing...",
                tool_calls=[{
                    "function": {
                        "name": "write_file",
                        # Arguments as JSON string (some backends do this)
                        "arguments": '{"path": "/tmp/test.py", "content": "hello"}'
                    }
                }],
                created_at=datetime(2026, 1, 15, 10, 1, 0)
            )
        ]

        with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock_list:
            with patch.object(client.app.state.api.state, 'load_session', new_callable=AsyncMock) as mock_load:
                mock_list.return_value = [
                    {"id": "test-session-jsonargs-1234567890123456", "task": "Test"}
                ]
                mock_load.return_value = mock_session

                response = client.get("/api/sessions/test-session-jsonargs-1234567890123456/file-changes")
                assert response.status_code == 200
                data = response.json()

                assert data["total_changes"] == 1
                change = data["file_changes"][0]
                assert change["file_path"] == "/tmp/test.py"
                assert change["new_content"] == "hello"


# ===== Task Endpoints Tests =====

class TestTaskEndpoints:
    """Tests for task-related endpoints."""

    def test_create_task_invalid_agent(self, client):
        """Test creating task with invalid agent."""
        response = client.post("/api/tasks", json={
            "description": "Do something",
            "agent": "nonexistent_agent"
        })
        assert response.status_code == 400
        assert "Unknown agent" in response.json()["detail"]

    def test_create_task_valid(self, client):
        """Test creating a valid task."""
        with patch('sindri.core.orchestrator.Orchestrator') as mock_orchestrator:
            mock_instance = MagicMock()
            mock_instance.run = AsyncMock(return_value={"success": True, "result": "Done"})
            mock_orchestrator.return_value = mock_instance

            response = client.post("/api/tasks", json={
                "description": "Create a hello world program",
                "agent": "brokkr",
                "max_iterations": 10
            })

            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data
            assert data["status"] == "running"

    def test_create_task_default_agent(self, client):
        """Test that default agent is brokkr."""
        with patch('sindri.core.orchestrator.Orchestrator') as mock_orchestrator:
            mock_instance = MagicMock()
            mock_instance.run = AsyncMock(return_value={"success": True})
            mock_orchestrator.return_value = mock_instance

            response = client.post("/api/tasks", json={
                "description": "Do something"
            })

            assert response.status_code == 200
            # Default agent should be brokkr (no error)

    def test_list_tasks_empty(self, client):
        """Test listing tasks when empty."""
        response = client.get("/api/tasks")
        assert response.status_code == 200
        # Should return empty or only tracked tasks

    def test_get_task_not_found(self, client):
        """Test getting non-existent task."""
        response = client.get("/api/tasks/nonexistent-task-id")
        assert response.status_code == 404


# ===== Metrics Endpoints Tests =====

class TestMetricsEndpoints:
    """Tests for metrics-related endpoints."""

    def test_get_system_metrics(self, client):
        """Test getting system metrics."""
        mock_sessions = [
            {"id": "s1", "status": "completed", "iterations": 5},
            {"id": "s2", "status": "failed", "iterations": 10},
            {"id": "s3", "status": "active", "iterations": 3},
        ]

        with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock:
            mock.return_value = mock_sessions

            response = client.get("/api/metrics")
            assert response.status_code == 200
            data = response.json()

            assert "total_sessions" in data
            assert "completed_sessions" in data
            assert "failed_sessions" in data
            assert "active_sessions" in data
            assert "total_iterations" in data
            assert "vram_used_gb" in data
            assert "vram_total_gb" in data
            assert "loaded_models" in data

    def test_metrics_counts_correct(self, client):
        """Test that metrics counts are correct."""
        mock_sessions = [
            {"id": "s1", "status": "completed", "iterations": 5},
            {"id": "s2", "status": "completed", "iterations": 10},
            {"id": "s3", "status": "failed", "iterations": 3},
        ]

        with patch.object(client.app.state.api.state, 'list_sessions', new_callable=AsyncMock) as mock:
            mock.return_value = mock_sessions

            response = client.get("/api/metrics")
            data = response.json()

            assert data["total_sessions"] == 3
            assert data["completed_sessions"] == 2
            assert data["failed_sessions"] == 1
            assert data["total_iterations"] == 18


# ===== API Model Tests =====

class TestAPIModels:
    """Tests for Pydantic API models."""

    def test_task_create_request_validation(self):
        """Test TaskCreateRequest validation."""
        from sindri.web.server import TaskCreateRequest

        # Valid request
        req = TaskCreateRequest(description="Test task")
        assert req.description == "Test task"
        assert req.agent == "brokkr"  # Default
        assert req.max_iterations == 30  # Default

        # With options
        req = TaskCreateRequest(
            description="Custom task",
            agent="huginn",
            max_iterations=50,
            enable_memory=False
        )
        assert req.agent == "huginn"
        assert req.max_iterations == 50
        assert req.enable_memory == False

    def test_task_create_request_empty_description(self):
        """Test that empty description is rejected."""
        from sindri.web.server import TaskCreateRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TaskCreateRequest(description="")

    def test_agent_response_model(self):
        """Test AgentResponse model."""
        from sindri.web.server import AgentResponse

        agent = AgentResponse(
            name="test",
            role="Test agent",
            model="qwen2.5:7b",
            tools=["read_file"],
            can_delegate=False,
            estimated_vram_gb=5.0,
            max_iterations=30
        )
        assert agent.name == "test"
        assert agent.delegate_to == []  # Default


# ===== SindriAPI Class Tests =====

class TestSindriAPI:
    """Tests for SindriAPI class."""

    @pytest.mark.asyncio
    async def test_api_initialization(self):
        """Test SindriAPI initialization."""
        api = SindriAPI(vram_gb=16.0)
        assert api.vram_gb == 16.0
        assert api.active_tasks == {}
        assert api.websocket_connections == []

    @pytest.mark.asyncio
    async def test_api_with_work_dir(self):
        """Test SindriAPI with work directory."""
        from pathlib import Path

        api = SindriAPI(vram_gb=16.0, work_dir=Path("/tmp/test"))
        assert api.work_dir == Path("/tmp/test")


# ===== WebSocket Tests =====

class TestWebSocket:
    """Tests for WebSocket functionality."""

    def test_websocket_connection(self, client):
        """Test WebSocket connection."""
        with client.websocket_connect("/ws") as websocket:
            # Should receive initial connection message
            data = websocket.receive_json()
            assert data["type"] == "connected"
            assert "message" in data["data"]

    def test_websocket_heartbeat(self, client):
        """Test WebSocket heartbeat/ping-pong."""
        with client.websocket_connect("/ws") as websocket:
            # Receive connection message
            websocket.receive_json()

            # Send ping
            websocket.send_json({"type": "ping"})

            # Should receive pong
            data = websocket.receive_json()
            assert data["type"] == "pong"
            assert "timestamp" in data


# ===== Integration Tests =====

class TestIntegration:
    """Integration tests for the Web API."""

    def test_app_creation(self):
        """Test application creation."""
        app = create_app(vram_gb=16.0)
        assert app is not None
        assert app.title == "Sindri API"

    def test_app_has_routes(self):
        """Test that app has expected routes."""
        app = create_app()

        route_paths = [route.path for route in app.routes]

        assert "/health" in route_paths
        assert "/api/agents" in route_paths
        assert "/api/sessions" in route_paths
        assert "/api/tasks" in route_paths
        assert "/api/metrics" in route_paths
        assert "/ws" in route_paths

    def test_cors_middleware(self):
        """Test CORS middleware is configured."""
        app = create_app()

        # Check that CORS middleware is present in user_middleware
        # FastAPI stores middleware differently, check user_middleware list
        middleware_found = False
        for middleware in app.user_middleware:
            middleware_str = str(middleware)
            if "CORS" in middleware_str or "cors" in middleware_str.lower():
                middleware_found = True
                break

        assert middleware_found, "CORS middleware should be configured"

    def test_openapi_docs_available(self, client):
        """Test that OpenAPI docs are available."""
        response = client.get("/docs")
        # Should redirect or return docs HTML
        assert response.status_code in [200, 307]

        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert data["info"]["title"] == "Sindri API"


# ===== Error Handling Tests =====

class TestErrorHandling:
    """Tests for API error handling."""

    def test_invalid_session_limit(self, client):
        """Test invalid limit parameter."""
        response = client.get("/api/sessions?limit=0")
        assert response.status_code == 422  # Validation error

        response = client.get("/api/sessions?limit=1000")
        assert response.status_code == 422  # Over limit

    def test_invalid_task_iterations(self, client):
        """Test invalid max_iterations."""
        response = client.post("/api/tasks", json={
            "description": "Test",
            "max_iterations": 0
        })
        assert response.status_code == 422

        response = client.post("/api/tasks", json={
            "description": "Test",
            "max_iterations": 200
        })
        assert response.status_code == 422
