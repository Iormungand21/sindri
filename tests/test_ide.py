"""Tests for IDE integration module.

Tests JSON-RPC protocol, server functionality, and request handlers.
"""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from sindri.ide.protocol import (
    ErrorCode,
    ExecuteTaskParams,
    ExplainCodeParams,
    GenerateTestsParams,
    IDECapabilities,
    IDENotification,
    IDERequest,
    IDEResponse,
    InitializeParams,
    InitializeResult,
    NotificationMethod,
    Position,
    Range,
    RefactorCodeParams,
    RequestMethod,
    ServerCapabilities,
    StreamingTokenParams,
    SuggestFixParams,
    TaskProgressParams,
    TaskStatus,
    TextDocumentIdentifier,
    TextDocumentItem,
)
from sindri.ide.server import IDEServer


# ============================================
# Protocol Tests
# ============================================


class TestIDERequest:
    """Tests for IDERequest class."""

    def test_to_dict(self):
        """Test conversion to JSON-RPC format."""
        request = IDERequest(
            method="initialize",
            params={"processId": 1234},
            id=1,
        )
        result = request.to_dict()

        assert result["jsonrpc"] == "2.0"
        assert result["method"] == "initialize"
        assert result["params"] == {"processId": 1234}
        assert result["id"] == 1

    def test_to_dict_no_params(self):
        """Test conversion without params."""
        request = IDERequest(method="shutdown", id=2)
        result = request.to_dict()

        assert "params" not in result
        assert result["id"] == 2

    def test_from_dict(self):
        """Test parsing from JSON-RPC format."""
        data = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {"processId": 1234},
            "id": 1,
        }
        request = IDERequest.from_dict(data)

        assert request.method == "initialize"
        assert request.params == {"processId": 1234}
        assert request.id == 1

    def test_from_dict_minimal(self):
        """Test parsing minimal request."""
        data = {"jsonrpc": "2.0", "method": "shutdown"}
        request = IDERequest.from_dict(data)

        assert request.method == "shutdown"
        assert request.params is None
        assert request.id is None


class TestIDEResponse:
    """Tests for IDEResponse class."""

    def test_success_response(self):
        """Test creating success response."""
        response = IDEResponse.success(1, {"initialized": True})
        result = response.to_dict()

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        # Result is set when no error
        assert "result" in result
        assert result["result"] == {"initialized": True}
        assert "error" not in result

    def test_error_response(self):
        """Test creating error response."""
        response = IDEResponse.error(1, ErrorCode.METHOD_NOT_FOUND, "Unknown method")
        result = response.to_dict()

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert result["error"]["code"] == ErrorCode.METHOD_NOT_FOUND
        assert result["error"]["message"] == "Unknown method"
        assert "result" not in result
        # Check instance attribute
        assert response.error_data is not None

    def test_error_response_with_data(self):
        """Test error response with additional data."""
        response = IDEResponse.error(
            1,
            ErrorCode.INTERNAL_ERROR,
            "Something went wrong",
            data={"traceback": "..."},
        )
        result = response.to_dict()

        assert result["error"]["data"] == {"traceback": "..."}


class TestIDENotification:
    """Tests for IDENotification class."""

    def test_to_dict(self):
        """Test conversion to JSON-RPC format."""
        notification = IDENotification(
            method="sindri/taskProgress",
            params={"taskId": "abc123", "progress": 0.5},
        )
        result = notification.to_dict()

        assert result["jsonrpc"] == "2.0"
        assert result["method"] == "sindri/taskProgress"
        assert result["params"]["taskId"] == "abc123"
        assert "id" not in result

    def test_from_dict(self):
        """Test parsing notification."""
        data = {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {"uri": "file:///test.py"},
        }
        notification = IDENotification.from_dict(data)

        assert notification.method == "textDocument/didOpen"
        assert notification.params["uri"] == "file:///test.py"


class TestIDECapabilities:
    """Tests for IDECapabilities class."""

    def test_defaults(self):
        """Test default capabilities."""
        caps = IDECapabilities()

        assert caps.text_document_sync is True
        assert caps.streaming is True
        assert caps.show_message is True

    def test_to_dict(self):
        """Test conversion to dictionary."""
        caps = IDECapabilities(streaming=False)
        result = caps.to_dict()

        assert result["textDocumentSync"] is True
        assert result["streaming"] is False

    def test_from_dict(self):
        """Test parsing from dictionary."""
        data = {"textDocumentSync": False, "streaming": True}
        caps = IDECapabilities.from_dict(data)

        assert caps.text_document_sync is False
        assert caps.streaming is True


class TestServerCapabilities:
    """Tests for ServerCapabilities class."""

    def test_defaults(self):
        """Test default server capabilities."""
        caps = ServerCapabilities()

        assert caps.task_execution is True
        assert caps.code_explanation is True
        assert caps.multi_agent is True
        assert caps.agent_count == 11
        assert caps.tool_count == 48

    def test_to_dict(self):
        """Test conversion to dictionary."""
        caps = ServerCapabilities()
        result = caps.to_dict()

        assert result["taskExecution"] is True
        assert result["agentCount"] == 11


class TestInitializeParams:
    """Tests for InitializeParams class."""

    def test_from_dict(self):
        """Test parsing initialize params."""
        data = {
            "processId": 1234,
            "clientInfo": {"name": "neovim", "version": "0.9.0"},
            "capabilities": {"streaming": True},
            "workspaceFolders": ["/home/user/project"],
        }
        params = InitializeParams.from_dict(data)

        assert params.process_id == 1234
        assert params.client_info["name"] == "neovim"
        assert params.capabilities.streaming is True
        assert params.workspace_folders == ["/home/user/project"]


class TestExecuteTaskParams:
    """Tests for ExecuteTaskParams class."""

    def test_from_dict_minimal(self):
        """Test parsing minimal params."""
        data = {"description": "Create hello.py"}
        params = ExecuteTaskParams.from_dict(data)

        assert params.description == "Create hello.py"
        assert params.agent == "brokkr"
        assert params.max_iterations == 30
        assert params.enable_memory is True

    def test_from_dict_full(self):
        """Test parsing full params."""
        data = {
            "description": "Fix bug",
            "agent": "huginn",
            "maxIterations": 50,
            "enableMemory": False,
            "currentFile": "/test.py",
            "currentSelection": "def foo():\n    pass",
            "workDir": "/home/user/project",
        }
        params = ExecuteTaskParams.from_dict(data)

        assert params.agent == "huginn"
        assert params.max_iterations == 50
        assert params.enable_memory is False
        assert params.current_file == "/test.py"
        assert params.current_selection == "def foo():\n    pass"
        assert params.work_dir == "/home/user/project"


class TestTaskProgressParams:
    """Tests for TaskProgressParams class."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        params = TaskProgressParams(
            task_id="abc123",
            status=TaskStatus.RUNNING,
            progress=0.75,
            message="Processing...",
            iteration=3,
            max_iterations=10,
        )
        result = params.to_dict()

        assert result["taskId"] == "abc123"
        assert result["status"] == "running"
        assert result["progress"] == 0.75
        assert result["message"] == "Processing..."
        assert result["iteration"] == 3


class TestStreamingTokenParams:
    """Tests for StreamingTokenParams class."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        params = StreamingTokenParams(
            task_id="abc123",
            token="Hello",
            is_complete=False,
        )
        result = params.to_dict()

        assert result["taskId"] == "abc123"
        assert result["token"] == "Hello"
        assert result["isComplete"] is False


# ============================================
# Server Tests
# ============================================


class TestIDEServer:
    """Tests for IDEServer class."""

    def test_init_default(self):
        """Test server initialization with defaults."""
        server = IDEServer()

        assert server.work_dir == Path.cwd()
        assert server.initialized is False
        assert server.shutdown_requested is False

    def test_init_with_work_dir(self, tmp_path):
        """Test server initialization with work directory."""
        server = IDEServer(work_dir=tmp_path)

        assert server.work_dir == tmp_path

    def test_handlers_registered(self):
        """Test that all handlers are registered."""
        server = IDEServer()

        # Check lifecycle handlers
        assert RequestMethod.INITIALIZE.value in server._handlers
        assert RequestMethod.SHUTDOWN.value in server._handlers

        # Check task handlers
        assert RequestMethod.EXECUTE_TASK.value in server._handlers
        assert RequestMethod.CANCEL_TASK.value in server._handlers
        assert RequestMethod.GET_TASK_STATUS.value in server._handlers

        # Check code assistance handlers
        assert RequestMethod.EXPLAIN_CODE.value in server._handlers
        assert RequestMethod.SUGGEST_FIX.value in server._handlers
        assert RequestMethod.GENERATE_TESTS.value in server._handlers
        assert RequestMethod.REFACTOR_CODE.value in server._handlers

        # Check agent handlers
        assert RequestMethod.LIST_AGENTS.value in server._handlers
        assert RequestMethod.GET_AGENT_INFO.value in server._handlers


class TestIDEServerHandlers:
    """Tests for IDEServer request handlers."""

    @pytest.fixture
    def server(self, tmp_path):
        """Create a server instance for testing."""
        return IDEServer(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_handle_initialize(self, server):
        """Test initialize handler."""
        params = {
            "processId": 1234,
            "clientInfo": {"name": "test", "version": "1.0"},
            "capabilities": {"streaming": True},
            "workspaceFolders": [str(server.work_dir)],
        }

        result = await server._handle_initialize(params)

        assert "capabilities" in result
        assert "serverInfo" in result
        assert result["serverInfo"]["name"] == "sindri"
        assert server.initialized is True

    @pytest.mark.asyncio
    async def test_handle_shutdown(self, server):
        """Test shutdown handler."""
        result = await server._handle_shutdown({})

        assert result is None
        assert server.shutdown_requested is True

    @pytest.mark.asyncio
    async def test_handle_list_agents(self, server):
        """Test list agents handler."""
        result = await server._handle_list_agents({})

        assert "agents" in result
        assert len(result["agents"]) > 0

        # Check agent structure
        agent = result["agents"][0]
        assert "name" in agent
        assert "role" in agent
        assert "model" in agent
        assert "tools" in agent

    @pytest.mark.asyncio
    async def test_handle_get_agent_info(self, server):
        """Test get agent info handler."""
        result = await server._handle_get_agent_info({"name": "brokkr"})

        assert result["name"] == "brokkr"
        assert "role" in result
        assert "model" in result
        assert "tools" in result

    @pytest.mark.asyncio
    async def test_handle_get_agent_info_not_found(self, server):
        """Test get agent info with unknown agent."""
        with pytest.raises(ValueError, match="Unknown agent"):
            await server._handle_get_agent_info({"name": "unknown"})

    @pytest.mark.asyncio
    async def test_handle_execute_task(self, server):
        """Test execute task handler starts a task."""
        with patch("sindri.ide.server.asyncio.create_task") as mock_create:
            mock_task = MagicMock()
            mock_create.return_value = mock_task

            params = {
                "description": "Test task",
                "agent": "brokkr",
            }
            result = await server._handle_execute_task(params)

            assert "taskId" in result
            assert result["status"] == "running"
            assert result["taskId"] in server.active_tasks

    @pytest.mark.asyncio
    async def test_handle_cancel_task_not_found(self, server):
        """Test cancel task with unknown task."""
        result = await server._handle_cancel_task({"taskId": "unknown"})

        assert result["success"] is False
        assert "not found" in result["message"]

    @pytest.mark.asyncio
    async def test_handle_cancel_task_no_id(self, server):
        """Test cancel task without task ID."""
        with pytest.raises(ValueError, match="taskId is required"):
            await server._handle_cancel_task({})

    @pytest.mark.asyncio
    async def test_handle_get_task_status_not_found(self, server):
        """Test get task status with unknown task."""
        result = await server._handle_get_task_status({"taskId": "unknown"})

        assert result["status"] == "failed"
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_analyze_file(self, server, tmp_path):
        """Test analyze file handler."""
        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n")

        result = await server._handle_analyze_file({"filePath": str(test_file)})

        assert result["filePath"] == str(test_file)
        assert result["language"] == "python"
        assert result["lineCount"] == 2

    @pytest.mark.asyncio
    async def test_handle_analyze_file_not_found(self, server):
        """Test analyze file with non-existent file."""
        with pytest.raises(FileNotFoundError):
            await server._handle_analyze_file({"filePath": "/nonexistent.py"})

    @pytest.mark.asyncio
    async def test_handle_list_sessions(self, server):
        """Test list sessions handler."""
        with patch("sindri.persistence.state.SessionState") as mock_state_class:
            mock_state = MagicMock()
            mock_state.list_sessions = AsyncMock(return_value=[])
            mock_state_class.return_value = mock_state

            result = await server._handle_list_sessions({"limit": 10})

            assert "sessions" in result
            mock_state.list_sessions.assert_called_once_with(limit=10)


class TestIDEServerRequest:
    """Tests for IDEServer request handling."""

    @pytest.fixture
    def server(self, tmp_path):
        """Create a server instance for testing."""
        return IDEServer(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_handle_request_success(self, server):
        """Test successful request handling."""
        request = IDERequest(method="sindri/listAgents", id=1)

        response = await server._handle_request(request)

        assert response.id == 1
        assert response.result is not None
        assert response.error_data is None

    @pytest.mark.asyncio
    async def test_handle_request_method_not_found(self, server):
        """Test request with unknown method."""
        request = IDERequest(method="unknown/method", id=1)

        response = await server._handle_request(request)

        assert response.id == 1
        assert response.error_data is not None
        assert response.error_data["code"] == ErrorCode.METHOD_NOT_FOUND

    @pytest.mark.asyncio
    async def test_handle_request_handler_error(self, server):
        """Test request when handler raises exception."""
        request = IDERequest(
            method="sindri/getAgentInfo",
            params={"name": "nonexistent"},
            id=1,
        )

        response = await server._handle_request(request)

        assert response.error_data is not None
        assert response.error_data["code"] == ErrorCode.INTERNAL_ERROR


class TestIDEServerMessage:
    """Tests for IDEServer message handling."""

    @pytest.fixture
    def server(self, tmp_path):
        """Create a server instance for testing."""
        return IDEServer(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_handle_message_request(self, server):
        """Test handling request message."""
        message = {
            "jsonrpc": "2.0",
            "method": "sindri/listAgents",
            "id": 1,
        }

        response = await server._handle_message(message)

        assert response is not None
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1

    @pytest.mark.asyncio
    async def test_handle_message_notification(self, server):
        """Test handling notification message."""
        message = {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {"uri": "file:///test.py"},
        }

        response = await server._handle_message(message)

        # Notifications don't return a response
        assert response is None


class TestIDEServerLanguageDetection:
    """Tests for language detection."""

    @pytest.fixture
    def server(self):
        """Create a server instance."""
        return IDEServer()

    def test_detect_python(self, server):
        """Test Python detection."""
        assert server._detect_language(Path("test.py")) == "python"
        assert server._detect_language(Path("test.pyi")) == "python"

    def test_detect_javascript(self, server):
        """Test JavaScript detection."""
        assert server._detect_language(Path("test.js")) == "javascript"
        assert server._detect_language(Path("test.jsx")) == "javascript"

    def test_detect_typescript(self, server):
        """Test TypeScript detection."""
        assert server._detect_language(Path("test.ts")) == "typescript"
        assert server._detect_language(Path("test.tsx")) == "typescript"

    def test_detect_rust(self, server):
        """Test Rust detection."""
        assert server._detect_language(Path("test.rs")) == "rust"

    def test_detect_go(self, server):
        """Test Go detection."""
        assert server._detect_language(Path("test.go")) == "go"

    def test_detect_unknown(self, server):
        """Test unknown file type."""
        assert server._detect_language(Path("test.unknown")) == "text"


# ============================================
# Code Assistance Handler Tests
# ============================================


class TestCodeAssistanceHandlers:
    """Tests for code assistance handlers."""

    @pytest.fixture
    def server(self, tmp_path):
        """Create a server instance for testing."""
        return IDEServer(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_handle_explain_code(self, server):
        """Test explain code handler."""
        with patch("sindri.llm.client.OllamaClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(
                return_value={
                    "message": {"content": "This function does X."}
                }
            )
            mock_client_class.return_value = mock_client

            params = {
                "code": "def foo(): pass",
                "language": "python",
            }
            result = await server._handle_explain_code(params)

            assert "explanation" in result
            assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_handle_suggest_fix(self, server):
        """Test suggest fix handler."""
        with patch("sindri.llm.client.OllamaClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(
                return_value={
                    "message": {"content": "Fix: Change X to Y."}
                }
            )
            mock_client_class.return_value = mock_client

            params = {
                "code": "def foo(): pass",
                "errorMessage": "IndentationError",
                "language": "python",
            }
            result = await server._handle_suggest_fix(params)

            assert "suggestion" in result
            assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_handle_generate_tests(self, server):
        """Test generate tests handler."""
        with patch("sindri.llm.client.OllamaClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(
                return_value={
                    "message": {"content": "def test_foo(): assert True"}
                }
            )
            mock_client_class.return_value = mock_client

            params = {
                "code": "def foo(): return 42",
                "language": "python",
            }
            result = await server._handle_generate_tests(params)

            assert "tests" in result
            assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_handle_refactor_code(self, server):
        """Test refactor code handler."""
        with patch("sindri.llm.client.OllamaClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(
                return_value={
                    "message": {"content": "Refactored: def bar(): pass"}
                }
            )
            mock_client_class.return_value = mock_client

            params = {
                "code": "def foo(): pass",
                "refactorType": "rename",
                "language": "python",
            }
            result = await server._handle_refactor_code(params)

            assert "refactored" in result
            assert result["refactorType"] == "rename"


# ============================================
# Integration Tests
# ============================================


class TestIDEIntegration:
    """Integration tests for IDE functionality."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, tmp_path):
        """Test full server lifecycle: initialize, request, shutdown."""
        server = IDEServer(work_dir=tmp_path)

        # Initialize
        init_params = {
            "processId": 1234,
            "clientInfo": {"name": "test"},
            "capabilities": {},
            "workspaceFolders": [str(tmp_path)],
        }
        init_result = await server._handle_initialize(init_params)
        assert server.initialized is True
        assert "capabilities" in init_result

        # Make a request
        agents_result = await server._handle_list_agents({})
        assert len(agents_result["agents"]) > 0

        # Shutdown
        await server._handle_shutdown({})
        assert server.shutdown_requested is True

    @pytest.mark.asyncio
    async def test_file_operations(self, tmp_path):
        """Test file-related operations."""
        server = IDEServer(work_dir=tmp_path)

        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text(
            "def greet(name):\n"
            "    return f'Hello, {name}!'\n"
        )

        # Analyze file
        result = await server._handle_analyze_file({"filePath": str(test_file)})
        assert result["language"] == "python"
        assert result["lineCount"] == 2

    @pytest.mark.asyncio
    async def test_session_operations(self, tmp_path):
        """Test session-related operations."""
        server = IDEServer(work_dir=tmp_path)

        with patch("sindri.persistence.state.SessionState") as mock_state_class:
            mock_state = MagicMock()
            mock_state.list_sessions = AsyncMock(
                return_value=[
                    {"id": "abc123", "task": "Test task", "status": "completed"}
                ]
            )
            mock_state_class.return_value = mock_state

            result = await server._handle_list_sessions({"limit": 5})

            assert len(result["sessions"]) == 1
            assert result["sessions"][0]["id"] == "abc123"


# ============================================
# Position and Range Tests
# ============================================


class TestPositionAndRange:
    """Tests for Position and Range classes."""

    def test_position(self):
        """Test Position creation."""
        pos = Position(line=10, character=5)
        assert pos.line == 10
        assert pos.character == 5

    def test_range(self):
        """Test Range creation."""
        start = Position(line=0, character=0)
        end = Position(line=5, character=10)
        range_ = Range(start=start, end=end)

        assert range_.start.line == 0
        assert range_.end.line == 5


class TestTextDocument:
    """Tests for text document classes."""

    def test_text_document_identifier(self):
        """Test TextDocumentIdentifier."""
        doc = TextDocumentIdentifier(uri="file:///test.py")
        assert doc.uri == "file:///test.py"

    def test_text_document_item(self):
        """Test TextDocumentItem."""
        doc = TextDocumentItem(
            uri="file:///test.py",
            language_id="python",
            version=1,
            text="print('hello')",
        )
        assert doc.uri == "file:///test.py"
        assert doc.language_id == "python"
        assert doc.version == 1
        assert "hello" in doc.text
