"""IDE Protocol Definitions.

JSON-RPC 2.0 based protocol for IDE communication.

This follows LSP conventions for familiarity:
- All messages are JSON-RPC 2.0
- Requests expect responses
- Notifications are one-way
- Supports streaming via notification events
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Union


class RequestMethod(str, Enum):
    """Available request methods."""

    # Lifecycle
    INITIALIZE = "initialize"
    SHUTDOWN = "shutdown"

    # Task execution
    EXECUTE_TASK = "sindri/executeTask"
    CANCEL_TASK = "sindri/cancelTask"
    GET_TASK_STATUS = "sindri/getTaskStatus"

    # Code assistance
    EXPLAIN_CODE = "sindri/explainCode"
    SUGGEST_FIX = "sindri/suggestFix"
    GENERATE_TESTS = "sindri/generateTests"
    REFACTOR_CODE = "sindri/refactorCode"

    # File operations
    ANALYZE_FILE = "sindri/analyzeFile"
    GET_SYMBOLS = "sindri/getSymbols"
    FIND_REFERENCES = "sindri/findReferences"

    # Agent info
    LIST_AGENTS = "sindri/listAgents"
    GET_AGENT_INFO = "sindri/getAgentInfo"

    # Sessions
    LIST_SESSIONS = "sindri/listSessions"
    GET_SESSION = "sindri/getSession"


class NotificationMethod(str, Enum):
    """Available notification methods."""

    # Client -> Server
    DID_OPEN = "textDocument/didOpen"
    DID_CHANGE = "textDocument/didChange"
    DID_CLOSE = "textDocument/didClose"
    DID_SAVE = "textDocument/didSave"

    # Server -> Client
    LOG_MESSAGE = "sindri/logMessage"
    TASK_PROGRESS = "sindri/taskProgress"
    TASK_OUTPUT = "sindri/taskOutput"
    TASK_COMPLETE = "sindri/taskComplete"
    STREAMING_TOKEN = "sindri/streamingToken"


class LogLevel(str, Enum):
    """Log message severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Position:
    """Position in a text document (0-indexed)."""

    line: int
    character: int


@dataclass
class Range:
    """Range in a text document."""

    start: Position
    end: Position


@dataclass
class TextDocumentIdentifier:
    """Identifies a text document."""

    uri: str


@dataclass
class TextDocumentItem:
    """Full text document content."""

    uri: str
    language_id: str
    version: int
    text: str


@dataclass
class IDECapabilities:
    """Capabilities that the IDE client supports."""

    # Document sync
    text_document_sync: bool = True

    # Streaming
    streaming: bool = True

    # Window features
    show_message: bool = True
    log_message: bool = True

    # Workspace
    workspace_folders: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "textDocumentSync": self.text_document_sync,
            "streaming": self.streaming,
            "showMessage": self.show_message,
            "logMessage": self.log_message,
            "workspaceFolders": self.workspace_folders,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IDECapabilities":
        """Create from dictionary."""
        return cls(
            text_document_sync=data.get("textDocumentSync", True),
            streaming=data.get("streaming", True),
            show_message=data.get("showMessage", True),
            log_message=data.get("logMessage", True),
            workspace_folders=data.get("workspaceFolders", True),
        )


@dataclass
class ServerCapabilities:
    """Capabilities that the Sindri IDE server supports."""

    # Task execution
    task_execution: bool = True
    task_streaming: bool = True
    task_cancellation: bool = True

    # Code assistance
    code_explanation: bool = True
    fix_suggestions: bool = True
    test_generation: bool = True
    refactoring: bool = True

    # Analysis
    file_analysis: bool = True
    symbol_search: bool = True
    reference_search: bool = True

    # Agents
    multi_agent: bool = True
    agent_count: int = 11

    # Tools
    tool_count: int = 48

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "taskExecution": self.task_execution,
            "taskStreaming": self.task_streaming,
            "taskCancellation": self.task_cancellation,
            "codeExplanation": self.code_explanation,
            "fixSuggestions": self.fix_suggestions,
            "testGeneration": self.test_generation,
            "refactoring": self.refactoring,
            "fileAnalysis": self.file_analysis,
            "symbolSearch": self.symbol_search,
            "referenceSearch": self.reference_search,
            "multiAgent": self.multi_agent,
            "agentCount": self.agent_count,
            "toolCount": self.tool_count,
        }


@dataclass
class IDERequest:
    """JSON-RPC request message."""

    method: str
    params: Optional[dict[str, Any]] = None
    id: Union[str, int, None] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-RPC format."""
        result: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": self.method,
        }
        if self.params is not None:
            result["params"] = self.params
        if self.id is not None:
            result["id"] = self.id
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IDERequest":
        """Parse from JSON-RPC format."""
        return cls(
            method=data["method"],
            params=data.get("params"),
            id=data.get("id"),
        )


@dataclass
class IDEResponse:
    """JSON-RPC response message."""

    id: Union[str, int, None]
    result: Optional[Any] = None
    error_data: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-RPC format."""
        response: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self.id,
        }
        if self.error_data is not None:
            response["error"] = self.error_data
        else:
            response["result"] = self.result
        return response

    @classmethod
    def success(cls, id: Union[str, int, None], result: Any) -> "IDEResponse":
        """Create a success response."""
        return cls(id=id, result=result)

    @classmethod
    def error(
        cls,
        id: Union[str, int, None],
        code: int,
        message: str,
        data: Any = None,
    ) -> "IDEResponse":
        """Create an error response."""
        error_obj: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error_obj["data"] = data
        return cls(id=id, error_data=error_obj)


@dataclass
class IDENotification:
    """JSON-RPC notification message (no response expected)."""

    method: str
    params: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-RPC format."""
        result: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": self.method,
        }
        if self.params is not None:
            result["params"] = self.params
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IDENotification":
        """Parse from JSON-RPC format."""
        return cls(
            method=data["method"],
            params=data.get("params"),
        )


# Standard JSON-RPC error codes
class ErrorCode:
    """Standard JSON-RPC error codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # Custom Sindri error codes
    TASK_CANCELLED = -32000
    TASK_FAILED = -32001
    AGENT_NOT_FOUND = -32002
    SESSION_NOT_FOUND = -32003
    FILE_NOT_FOUND = -32004
    OLLAMA_ERROR = -32005


# Request/Response parameter types
@dataclass
class InitializeParams:
    """Parameters for initialize request."""

    process_id: Optional[int] = None
    client_info: Optional[dict[str, str]] = None
    capabilities: IDECapabilities = field(default_factory=IDECapabilities)
    workspace_folders: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InitializeParams":
        """Parse from dictionary."""
        caps = data.get("capabilities", {})
        return cls(
            process_id=data.get("processId"),
            client_info=data.get("clientInfo"),
            capabilities=IDECapabilities.from_dict(caps),
            workspace_folders=data.get("workspaceFolders", []),
        )


@dataclass
class InitializeResult:
    """Result for initialize request."""

    capabilities: ServerCapabilities = field(default_factory=ServerCapabilities)
    server_info: dict[str, str] = field(
        default_factory=lambda: {"name": "sindri", "version": "0.1.0"}
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "capabilities": self.capabilities.to_dict(),
            "serverInfo": self.server_info,
        }


@dataclass
class ExecuteTaskParams:
    """Parameters for task execution."""

    description: str
    agent: str = "brokkr"
    max_iterations: int = 30
    work_dir: Optional[str] = None
    enable_memory: bool = True
    # Context from editor
    current_file: Optional[str] = None
    current_selection: Optional[str] = None
    visible_range: Optional[Range] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecuteTaskParams":
        """Parse from dictionary."""
        visible = data.get("visibleRange")
        visible_range = None
        if visible:
            visible_range = Range(
                start=Position(
                    line=visible["start"]["line"],
                    character=visible["start"]["character"],
                ),
                end=Position(
                    line=visible["end"]["line"],
                    character=visible["end"]["character"],
                ),
            )
        return cls(
            description=data["description"],
            agent=data.get("agent", "brokkr"),
            max_iterations=data.get("maxIterations", 30),
            work_dir=data.get("workDir"),
            enable_memory=data.get("enableMemory", True),
            current_file=data.get("currentFile"),
            current_selection=data.get("currentSelection"),
            visible_range=visible_range,
        )


@dataclass
class ExplainCodeParams:
    """Parameters for code explanation."""

    code: str
    language: str = "auto"
    file_path: Optional[str] = None
    detail_level: str = "normal"  # brief, normal, detailed

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExplainCodeParams":
        """Parse from dictionary."""
        return cls(
            code=data["code"],
            language=data.get("language", "auto"),
            file_path=data.get("filePath"),
            detail_level=data.get("detailLevel", "normal"),
        )


@dataclass
class SuggestFixParams:
    """Parameters for fix suggestion."""

    code: str
    error_message: str
    language: str = "auto"
    file_path: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SuggestFixParams":
        """Parse from dictionary."""
        return cls(
            code=data["code"],
            error_message=data["errorMessage"],
            language=data.get("language", "auto"),
            file_path=data.get("filePath"),
        )


@dataclass
class GenerateTestsParams:
    """Parameters for test generation."""

    code: str
    language: str = "auto"
    file_path: Optional[str] = None
    test_framework: Optional[str] = None  # pytest, jest, etc.

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GenerateTestsParams":
        """Parse from dictionary."""
        return cls(
            code=data["code"],
            language=data.get("language", "auto"),
            file_path=data.get("filePath"),
            test_framework=data.get("testFramework"),
        )


@dataclass
class RefactorCodeParams:
    """Parameters for code refactoring."""

    code: str
    refactor_type: str  # extract_function, rename, inline, etc.
    language: str = "auto"
    file_path: Optional[str] = None
    options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RefactorCodeParams":
        """Parse from dictionary."""
        return cls(
            code=data["code"],
            refactor_type=data["refactorType"],
            language=data.get("language", "auto"),
            file_path=data.get("filePath"),
            options=data.get("options", {}),
        )


@dataclass
class TaskProgressParams:
    """Parameters for task progress notification."""

    task_id: str
    status: TaskStatus
    progress: float  # 0.0 to 1.0
    message: str = ""
    iteration: int = 0
    max_iterations: int = 30

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "taskId": self.task_id,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "iteration": self.iteration,
            "maxIterations": self.max_iterations,
        }


@dataclass
class StreamingTokenParams:
    """Parameters for streaming token notification."""

    task_id: str
    token: str
    is_complete: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "taskId": self.task_id,
            "token": self.token,
            "isComplete": self.is_complete,
        }
