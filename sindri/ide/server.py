"""IDE Server Implementation.

JSON-RPC server for IDE integration supporting stdio and HTTP modes.
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

import structlog

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
    RefactorCodeParams,
    RequestMethod,
    ServerCapabilities,
    StreamingTokenParams,
    SuggestFixParams,
    TaskProgressParams,
    TaskStatus,
)

if TYPE_CHECKING:
    from sindri.core.events import EventBus

log = structlog.get_logger()


class IDEServer:
    """JSON-RPC server for IDE integration.

    Supports two modes:
    - stdio: Communication over stdin/stdout (for Neovim, etc.)
    - http: HTTP/WebSocket server (for VS Code, etc.)
    """

    def __init__(
        self,
        work_dir: Optional[Path] = None,
        event_bus: Optional["EventBus"] = None,
    ):
        """Initialize IDE server.

        Args:
            work_dir: Default working directory for file operations
            event_bus: Optional event bus for integration with orchestrator
        """
        self.work_dir = work_dir or Path.cwd()
        self.event_bus = event_bus
        self.initialized = False
        self.client_capabilities = IDECapabilities()
        self.shutdown_requested = False
        self.active_tasks: dict[str, asyncio.Task] = {}
        self._handlers: dict[str, Callable] = {}
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Register request handlers."""
        self._handlers = {
            # Lifecycle
            RequestMethod.INITIALIZE.value: self._handle_initialize,
            RequestMethod.SHUTDOWN.value: self._handle_shutdown,
            # Task execution
            RequestMethod.EXECUTE_TASK.value: self._handle_execute_task,
            RequestMethod.CANCEL_TASK.value: self._handle_cancel_task,
            RequestMethod.GET_TASK_STATUS.value: self._handle_get_task_status,
            # Code assistance
            RequestMethod.EXPLAIN_CODE.value: self._handle_explain_code,
            RequestMethod.SUGGEST_FIX.value: self._handle_suggest_fix,
            RequestMethod.GENERATE_TESTS.value: self._handle_generate_tests,
            RequestMethod.REFACTOR_CODE.value: self._handle_refactor_code,
            # File operations
            RequestMethod.ANALYZE_FILE.value: self._handle_analyze_file,
            RequestMethod.GET_SYMBOLS.value: self._handle_get_symbols,
            RequestMethod.FIND_REFERENCES.value: self._handle_find_references,
            # Agent info
            RequestMethod.LIST_AGENTS.value: self._handle_list_agents,
            RequestMethod.GET_AGENT_INFO.value: self._handle_get_agent_info,
            # Sessions
            RequestMethod.LIST_SESSIONS.value: self._handle_list_sessions,
            RequestMethod.GET_SESSION.value: self._handle_get_session,
        }

    async def run_stdio(self) -> None:
        """Run server in stdio mode (for Neovim, etc.).

        Reads JSON-RPC messages from stdin and writes responses to stdout.
        Uses Content-Length headers like LSP.
        """
        log.info("ide_server_starting", mode="stdio")

        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(
            lambda: protocol, sys.stdin
        )

        writer_transport, writer_protocol = (
            await asyncio.get_event_loop().connect_write_pipe(
                asyncio.streams.FlowControlMixin, sys.stdout
            )
        )
        writer = asyncio.StreamWriter(
            writer_transport, writer_protocol, reader, asyncio.get_event_loop()
        )

        try:
            while not self.shutdown_requested:
                message = await self._read_message(reader)
                if message is None:
                    break

                response = await self._handle_message(message)
                if response:
                    await self._write_message(writer, response)
        except asyncio.CancelledError:
            log.info("ide_server_cancelled")
        except Exception as e:
            log.error("ide_server_error", error=str(e))
        finally:
            log.info("ide_server_stopped")

    async def _read_message(
        self, reader: asyncio.StreamReader
    ) -> Optional[dict[str, Any]]:
        """Read a JSON-RPC message from the reader.

        Uses Content-Length headers like LSP.
        """
        headers: dict[str, str] = {}

        # Read headers
        while True:
            line = await reader.readline()
            if not line:
                return None
            line_str = line.decode("utf-8").strip()
            if not line_str:
                break
            if ":" in line_str:
                key, value = line_str.split(":", 1)
                headers[key.strip().lower()] = value.strip()

        # Get content length
        content_length = int(headers.get("content-length", 0))
        if content_length == 0:
            return None

        # Read content
        content = await reader.read(content_length)
        if not content:
            return None

        try:
            return json.loads(content.decode("utf-8"))
        except json.JSONDecodeError as e:
            log.error("json_parse_error", error=str(e))
            return None

    async def _write_message(
        self, writer: asyncio.StreamWriter, message: dict[str, Any]
    ) -> None:
        """Write a JSON-RPC message to the writer.

        Uses Content-Length headers like LSP.
        """
        content = json.dumps(message)
        content_bytes = content.encode("utf-8")

        header = f"Content-Length: {len(content_bytes)}\r\n\r\n"
        writer.write(header.encode("utf-8"))
        writer.write(content_bytes)
        await writer.drain()

    async def _handle_message(
        self, message: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Handle an incoming JSON-RPC message."""
        # Check if it's a notification (no id)
        if "id" not in message:
            notification = IDENotification.from_dict(message)
            await self._handle_notification(notification)
            return None

        # It's a request
        request = IDERequest.from_dict(message)
        response = await self._handle_request(request)
        return response.to_dict()

    async def _handle_notification(self, notification: IDENotification) -> None:
        """Handle a notification (no response needed)."""
        log.debug("notification_received", method=notification.method)

        # Handle document sync notifications
        if notification.method == NotificationMethod.DID_OPEN.value:
            # Track open documents
            pass
        elif notification.method == NotificationMethod.DID_CHANGE.value:
            # Track document changes
            pass
        elif notification.method == NotificationMethod.DID_CLOSE.value:
            # Clean up closed documents
            pass

    async def _handle_request(self, request: IDERequest) -> IDEResponse:
        """Handle a request and return a response."""
        log.debug("request_received", method=request.method, id=request.id)

        handler = self._handlers.get(request.method)
        if not handler:
            return IDEResponse.error(
                request.id,
                ErrorCode.METHOD_NOT_FOUND,
                f"Method not found: {request.method}",
            )

        try:
            result = await handler(request.params or {})
            return IDEResponse.success(request.id, result)
        except Exception as e:
            log.error("request_handler_error", method=request.method, error=str(e))
            return IDEResponse.error(
                request.id, ErrorCode.INTERNAL_ERROR, str(e)
            )

    # Lifecycle handlers
    async def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle initialize request."""
        init_params = InitializeParams.from_dict(params)
        self.client_capabilities = init_params.capabilities

        if init_params.workspace_folders:
            self.work_dir = Path(init_params.workspace_folders[0])

        self.initialized = True
        log.info(
            "ide_server_initialized",
            client=init_params.client_info,
            workspace=str(self.work_dir),
        )

        result = InitializeResult()
        return result.to_dict()

    async def _handle_shutdown(self, params: dict[str, Any]) -> None:
        """Handle shutdown request."""
        log.info("ide_server_shutdown_requested")
        self.shutdown_requested = True

        # Cancel all active tasks
        for task_id, task in self.active_tasks.items():
            if not task.done():
                task.cancel()
                log.info("cancelled_active_task", task_id=task_id)

        return None

    # Task execution handlers
    async def _handle_execute_task(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle task execution request."""
        task_params = ExecuteTaskParams.from_dict(params)

        # Generate task ID
        task_id = str(uuid.uuid4())[:8]

        # Build context-aware task description
        description = task_params.description
        if task_params.current_file:
            description = f"[File: {task_params.current_file}] {description}"
        if task_params.current_selection:
            description = f"{description}\n\nSelected code:\n```\n{task_params.current_selection}\n```"

        # Start task execution in background
        async def run_task():
            try:
                from sindri.core.orchestrator import Orchestrator
                from sindri.core.loop import LoopConfig

                config = LoopConfig(max_iterations=task_params.max_iterations)
                work_path = (
                    Path(task_params.work_dir)
                    if task_params.work_dir
                    else self.work_dir
                )

                orchestrator = Orchestrator(
                    config=config,
                    total_vram_gb=16.0,
                    enable_memory=task_params.enable_memory,
                    work_dir=work_path,
                )

                result = await orchestrator.run(description)
                return result
            except Exception as e:
                log.error("task_execution_error", task_id=task_id, error=str(e))
                return {"success": False, "error": str(e)}

        # Create async task
        task = asyncio.create_task(run_task())
        self.active_tasks[task_id] = task

        return {
            "taskId": task_id,
            "status": TaskStatus.RUNNING.value,
            "message": f"Task started with agent: {task_params.agent}",
        }

    async def _handle_cancel_task(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle task cancellation request."""
        task_id = params.get("taskId")
        if not task_id:
            raise ValueError("taskId is required")

        task = self.active_tasks.get(task_id)
        if not task:
            return {
                "taskId": task_id,
                "success": False,
                "message": "Task not found",
            }

        if task.done():
            return {
                "taskId": task_id,
                "success": False,
                "message": "Task already completed",
            }

        task.cancel()
        return {
            "taskId": task_id,
            "success": True,
            "message": "Task cancelled",
        }

    async def _handle_get_task_status(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle task status request."""
        task_id = params.get("taskId")
        if not task_id:
            raise ValueError("taskId is required")

        task = self.active_tasks.get(task_id)
        if not task:
            return {
                "taskId": task_id,
                "status": TaskStatus.FAILED.value,
                "error": "Task not found",
            }

        if task.done():
            try:
                result = task.result()
                if result.get("success"):
                    return {
                        "taskId": task_id,
                        "status": TaskStatus.COMPLETED.value,
                        "result": result.get("result"),
                    }
                else:
                    return {
                        "taskId": task_id,
                        "status": TaskStatus.FAILED.value,
                        "error": result.get("error", "Unknown error"),
                    }
            except asyncio.CancelledError:
                return {
                    "taskId": task_id,
                    "status": TaskStatus.CANCELLED.value,
                }
            except Exception as e:
                return {
                    "taskId": task_id,
                    "status": TaskStatus.FAILED.value,
                    "error": str(e),
                }
        else:
            return {
                "taskId": task_id,
                "status": TaskStatus.RUNNING.value,
            }

    # Code assistance handlers
    async def _handle_explain_code(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle code explanation request."""
        explain_params = ExplainCodeParams.from_dict(params)

        # Build prompt for code explanation
        prompt = f"Explain the following {explain_params.language} code"
        if explain_params.detail_level == "brief":
            prompt += " briefly (1-2 sentences)"
        elif explain_params.detail_level == "detailed":
            prompt += " in detail with examples"

        prompt += f":\n\n```{explain_params.language}\n{explain_params.code}\n```"

        # Use local LLM for quick explanation
        from sindri.llm.client import OllamaClient

        client = OllamaClient()
        response = await client.chat(
            model="qwen2.5-coder:7b",
            messages=[{"role": "user", "content": prompt}],
        )

        return {
            "explanation": response.get("message", {}).get("content", ""),
            "language": explain_params.language,
        }

    async def _handle_suggest_fix(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle fix suggestion request."""
        fix_params = SuggestFixParams.from_dict(params)

        prompt = f"""Fix the following error in this {fix_params.language} code:

Error: {fix_params.error_message}

Code:
```{fix_params.language}
{fix_params.code}
```

Provide the corrected code and explain the fix."""

        from sindri.llm.client import OllamaClient

        client = OllamaClient()
        response = await client.chat(
            model="qwen2.5-coder:7b",
            messages=[{"role": "user", "content": prompt}],
        )

        content = response.get("message", {}).get("content", "")

        return {
            "suggestion": content,
            "language": fix_params.language,
        }

    async def _handle_generate_tests(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle test generation request."""
        test_params = GenerateTestsParams.from_dict(params)

        framework_hint = ""
        if test_params.test_framework:
            framework_hint = f" using {test_params.test_framework}"

        prompt = f"""Generate unit tests{framework_hint} for this {test_params.language} code:

```{test_params.language}
{test_params.code}
```

Include tests for:
- Normal cases
- Edge cases
- Error cases (if applicable)"""

        from sindri.llm.client import OllamaClient

        client = OllamaClient()
        response = await client.chat(
            model="qwen2.5-coder:7b",
            messages=[{"role": "user", "content": prompt}],
        )

        return {
            "tests": response.get("message", {}).get("content", ""),
            "framework": test_params.test_framework,
            "language": test_params.language,
        }

    async def _handle_refactor_code(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle code refactoring request."""
        refactor_params = RefactorCodeParams.from_dict(params)

        prompt = f"""Refactor this {refactor_params.language} code using {refactor_params.refactor_type}:

```{refactor_params.language}
{refactor_params.code}
```

Options: {json.dumps(refactor_params.options)}

Provide the refactored code and explain the changes."""

        from sindri.llm.client import OllamaClient

        client = OllamaClient()
        response = await client.chat(
            model="qwen2.5-coder:7b",
            messages=[{"role": "user", "content": prompt}],
        )

        return {
            "refactored": response.get("message", {}).get("content", ""),
            "refactorType": refactor_params.refactor_type,
            "language": refactor_params.language,
        }

    # File operations handlers
    async def _handle_analyze_file(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle file analysis request."""
        file_path = params.get("filePath")
        if not file_path:
            raise ValueError("filePath is required")

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        content = path.read_text()
        language = self._detect_language(path)

        # Use AST tools if available
        try:
            from sindri.tools.ast_refactoring import ParseASTTool

            ast_tool = ParseASTTool()
            result = await ast_tool.execute(file_path=file_path)
            if result.success:
                return {
                    "filePath": file_path,
                    "language": language,
                    "lineCount": len(content.splitlines()),
                    "ast": result.output,
                }
        except ImportError:
            pass

        return {
            "filePath": file_path,
            "language": language,
            "lineCount": len(content.splitlines()),
        }

    async def _handle_get_symbols(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle symbol search request."""
        file_path = params.get("filePath")
        if not file_path:
            raise ValueError("filePath is required")

        try:
            from sindri.tools.ast_refactoring import ParseASTTool

            ast_tool = ParseASTTool()
            result = await ast_tool.execute(file_path=file_path)
            if result.success:
                # Parse AST output to extract symbols
                return {
                    "filePath": file_path,
                    "symbols": result.output,
                }
        except ImportError:
            pass

        return {"filePath": file_path, "symbols": []}

    async def _handle_find_references(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle reference search request."""
        symbol_name = params.get("symbolName")
        search_path = params.get("path", str(self.work_dir))

        if not symbol_name:
            raise ValueError("symbolName is required")

        try:
            from sindri.tools.ast_refactoring import FindReferencesTool

            ref_tool = FindReferencesTool()
            result = await ref_tool.execute(
                symbol_name=symbol_name, path=search_path
            )
            if result.success:
                return {
                    "symbolName": symbol_name,
                    "references": result.output,
                }
        except ImportError:
            pass

        return {"symbolName": symbol_name, "references": []}

    # Agent info handlers
    async def _handle_list_agents(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle list agents request."""
        from sindri.agents.registry import AGENTS

        return {
            "agents": [
                {
                    "name": agent.name,
                    "role": agent.role,
                    "model": agent.model,
                    "tools": agent.tools,
                }
                for agent in AGENTS.values()
            ]
        }

    async def _handle_get_agent_info(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle get agent info request."""
        agent_name = params.get("name")
        if not agent_name:
            raise ValueError("name is required")

        from sindri.agents.registry import get_agent

        agent = get_agent(agent_name)
        if not agent:
            raise ValueError(f"Agent not found: {agent_name}")

        return {
            "name": agent.name,
            "role": agent.role,
            "model": agent.model,
            "tools": agent.tools,
            "delegateTo": agent.delegate_to,
            "maxIterations": agent.max_iterations,
            "estimatedVramGb": agent.estimated_vram_gb,
        }

    # Session handlers
    async def _handle_list_sessions(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle list sessions request."""
        limit = params.get("limit", 20)

        from sindri.persistence.state import SessionState

        state = SessionState()
        sessions = await state.list_sessions(limit=limit)

        return {"sessions": sessions}

    async def _handle_get_session(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle get session request."""
        session_id = params.get("sessionId")
        if not session_id:
            raise ValueError("sessionId is required")

        from sindri.persistence.state import SessionState

        state = SessionState()
        session = await state.load_session(session_id)

        if not session:
            raise ValueError(f"Session not found: {session_id}")

        return {
            "id": session.id,
            "task": session.task,
            "model": session.model,
            "status": session.status,
            "iterations": session.iterations,
            "turns": [
                {
                    "role": turn.role,
                    "content": turn.content[:500] if turn.content else None,
                }
                for turn in session.turns
            ],
        }

    def _detect_language(self, path: Path) -> str:
        """Detect language from file extension."""
        ext_map = {
            ".py": "python",
            ".pyi": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".sh": "bash",
            ".sql": "sql",
            ".html": "html",
            ".css": "css",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".md": "markdown",
        }
        return ext_map.get(path.suffix.lower(), "text")

    # Helper methods for sending notifications
    async def send_notification(
        self, writer: asyncio.StreamWriter, notification: IDENotification
    ) -> None:
        """Send a notification to the client."""
        await self._write_message(writer, notification.to_dict())

    async def send_log_message(
        self, writer: asyncio.StreamWriter, level: str, message: str
    ) -> None:
        """Send a log message notification."""
        notification = IDENotification(
            method=NotificationMethod.LOG_MESSAGE.value,
            params={"level": level, "message": message},
        )
        await self.send_notification(writer, notification)

    async def send_task_progress(
        self, writer: asyncio.StreamWriter, progress: TaskProgressParams
    ) -> None:
        """Send a task progress notification."""
        notification = IDENotification(
            method=NotificationMethod.TASK_PROGRESS.value,
            params=progress.to_dict(),
        )
        await self.send_notification(writer, notification)

    async def send_streaming_token(
        self, writer: asyncio.StreamWriter, token_params: StreamingTokenParams
    ) -> None:
        """Send a streaming token notification."""
        notification = IDENotification(
            method=NotificationMethod.STREAMING_TOKEN.value,
            params=token_params.to_dict(),
        )
        await self.send_notification(writer, notification)
