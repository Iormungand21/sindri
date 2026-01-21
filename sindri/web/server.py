"""Sindri Web API Server.

Phase 8.3: FastAPI-based Web API for Sindri orchestration.

Features:
- REST API for agents, sessions, tasks, metrics
- WebSocket for real-time event streaming
- Integration with EventBus system
"""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional
from pathlib import Path

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    Query,
    Header,
    BackgroundTasks,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import structlog

from sindri.agents.registry import get_agent, list_agents
from sindri.persistence.state import SessionState
from sindri.core.events import EventBus, EventType, Event
from sindri.core.event_schemas import (
    API_VERSION,
    EVENT_PAYLOAD_MODELS,
    get_all_event_schemas,
)
from sindri.llm.manager import ModelManager

log = structlog.get_logger()


def _ws_debug(message: str):
    if os.getenv("SINDRI_WS_DEBUG"):
        print(f"[ws-debug] {message}", flush=True)


# Pydantic models for API
class AgentResponse(BaseModel):
    """Agent information response."""

    name: str
    role: str
    model: str
    tools: list[str]
    can_delegate: bool
    delegate_to: list[str] = []
    estimated_vram_gb: float
    max_iterations: int
    fallback_model: Optional[str] = None


class SessionResponse(BaseModel):
    """Session information response."""

    id: str
    task: str
    model: str
    status: str
    created_at: str
    completed_at: Optional[str] = None
    iterations: int


class SessionDetailResponse(SessionResponse):
    """Detailed session response with turns."""

    turns: list[dict[str, Any]] = []


class TaskCreateRequest(BaseModel):
    """Request to create a new task."""

    description: str = Field(..., min_length=1, description="Task description")
    agent: str = Field(default="brokkr", description="Starting agent")
    max_iterations: int = Field(default=30, ge=1, le=100)
    work_dir: Optional[str] = Field(default=None, description="Working directory")
    enable_memory: bool = Field(default=True, description="Enable memory system")


class TaskResponse(BaseModel):
    """Task execution response."""

    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """Task status response."""

    task_id: str
    status: str
    result: Optional[str] = None
    error: Optional[str] = None
    subtasks: int = 0


class MetricsResponse(BaseModel):
    """System metrics response."""

    total_sessions: int
    completed_sessions: int
    failed_sessions: int
    active_sessions: int
    total_iterations: int
    vram_used_gb: float
    vram_total_gb: float
    loaded_models: list[str]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    ollama_connected: bool
    database_ok: bool
    timestamp: str


class FileChangeResponse(BaseModel):
    """Individual file change from a session."""

    file_path: str
    operation: str  # 'read', 'write', 'edit'
    turn_index: int
    timestamp: str
    success: bool
    # For write operations
    new_content: Optional[str] = None
    content_size: Optional[int] = None
    # For edit operations
    old_text: Optional[str] = None
    new_text: Optional[str] = None
    # For read operations (used as "before" context)
    read_content: Optional[str] = None


class FileChangesResponse(BaseModel):
    """All file changes from a session."""

    session_id: str
    file_changes: list[FileChangeResponse]
    files_modified: list[str]
    total_changes: int


class WebSocketMessage(BaseModel):
    """WebSocket message format."""

    type: str
    data: dict[str, Any]
    timestamp: float


# Coverage models
class FileCoverageResponse(BaseModel):
    """Coverage data for a single file."""

    filename: str
    lines_valid: int
    lines_covered: int
    line_rate: float
    line_percentage: float
    branches_valid: int = 0
    branches_covered: int = 0
    branch_rate: float = 0.0
    covered_lines: list[int] = []
    uncovered_lines: list[int] = []


class PackageCoverageResponse(BaseModel):
    """Coverage data for a package/directory."""

    name: str
    line_rate: float
    branch_rate: float = 0.0
    lines_valid: int
    lines_covered: int
    files: list[FileCoverageResponse] = []


class CoverageSummaryResponse(BaseModel):
    """Summary of coverage data."""

    session_id: Optional[str] = None
    source: str = ""
    timestamp: str = ""
    line_rate: float
    line_percentage: float
    lines_valid: int
    lines_covered: int
    branch_rate: float = 0.0
    branch_percentage: float = 0.0
    branches_valid: int = 0
    branches_covered: int = 0
    files_count: int
    packages_count: int


class CoverageDetailResponse(CoverageSummaryResponse):
    """Detailed coverage response including package/file breakdown."""

    packages: list[PackageCoverageResponse] = []


class CoverageImportRequest(BaseModel):
    """Request to import coverage from a file."""

    coverage_path: str = Field(..., description="Path to coverage file (XML, JSON, or LCOV)")


class CoverageStatsResponse(BaseModel):
    """Aggregate coverage statistics."""

    total_reports: int
    avg_line_rate: float
    avg_line_percentage: float
    max_line_rate: float
    min_line_rate: float
    total_files: int
    total_lines: int
    total_covered: int


class SindriAPI:
    """Sindri API application state."""

    def __init__(self, vram_gb: float = 16.0, work_dir: Optional[Path] = None):
        self.vram_gb = vram_gb
        self.work_dir = work_dir
        self.state = SessionState()
        self.event_bus = EventBus()
        self.model_manager: Optional[ModelManager] = None
        self.active_tasks: dict[str, dict] = {}
        self.websocket_connections: list[WebSocket] = []
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

    async def initialize(self):
        """Initialize API components."""
        _ws_debug("api.initialize: start")

        # Store reference to the event loop for thread-safe event broadcasting
        self._event_loop = asyncio.get_running_loop()

        if os.getenv("SINDRI_SKIP_DB_INIT"):
            _ws_debug("api.initialize: skipping db.initialize")
        else:
            _ws_debug("api.initialize: db.initialize start")
            await self.state.db.initialize()
            _ws_debug("api.initialize: db.initialize complete")
        self.model_manager = ModelManager(total_vram_gb=self.vram_gb)

        # Clean up stale sessions on startup
        # Any "active" sessions from before server start are clearly not running
        if os.getenv("SINDRI_SKIP_DB_INIT"):
            _ws_debug("api.initialize: skipping cleanup_stale_sessions")
        else:
            _ws_debug("api.initialize: cleanup_stale_sessions start")
            cleaned = await self.state.cleanup_stale_sessions(max_age_hours=0.0)
            _ws_debug("api.initialize: cleanup_stale_sessions complete")
            if cleaned > 0:
                log.info("startup_cleanup", stale_sessions_marked_failed=cleaned)

        # Subscribe to events for WebSocket broadcast
        self.event_bus.subscribe_event(self._broadcast_event_sync)

        log.info("sindri_api_initialized", vram_gb=self.vram_gb)
        _ws_debug("api.initialize: complete")

    def _broadcast_event_sync(self, event: Event):
        """Synchronous wrapper for event broadcast (called from EventBus).

        This method can be called from any thread. It schedules the async
        broadcast on the server's event loop using thread-safe scheduling.
        """
        if self._event_loop is None:
            log.debug("event_broadcast_skipped_no_loop", event_type=event.type.name)
            return

        # Use call_soon_threadsafe to schedule on the server's event loop
        # This works whether called from the main thread or a worker thread
        try:
            self._event_loop.call_soon_threadsafe(
                lambda: self._event_loop.create_task(self._broadcast_event(event))
            )
        except RuntimeError:
            # Event loop is closed or not running
            log.debug("event_broadcast_skipped_loop_closed", event_type=event.type.name)

    async def _broadcast_event(self, event: Event):
        """Broadcast an event to all connected WebSocket clients."""
        if not self.websocket_connections:
            return

        message = {
            "type": event.type.name,
            "data": event.data if isinstance(event.data, dict) else str(event.data),
            "timestamp": event.timestamp,
            "task_id": event.task_id,
        }
        message_json = json.dumps(message, default=str)

        # Broadcast to all connections
        disconnected = []
        for ws in self.websocket_connections:
            try:
                await ws.send_text(message_json)
            except Exception:
                disconnected.append(ws)

        # Remove disconnected clients
        for ws in disconnected:
            self.websocket_connections.remove(ws)

    async def shutdown(self):
        """Clean shutdown of API components."""
        # Close WebSocket connections
        for ws in self.websocket_connections:
            try:
                await ws.close()
            except Exception:
                pass
        self.websocket_connections.clear()
        log.info("sindri_api_shutdown")


def create_app(vram_gb: float = 16.0, work_dir: Optional[Path] = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        vram_gb: Total VRAM available in GB
        work_dir: Working directory for file operations

    Returns:
        Configured FastAPI application
    """

    api = SindriAPI(vram_gb=vram_gb, work_dir=work_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan handler."""
        _ws_debug("lifespan: start")
        await api.initialize()
        _ws_debug("lifespan: initialized")
        yield
        _ws_debug("lifespan: shutdown")
        await api.shutdown()

    app = FastAPI(
        title="Sindri API",
        description="Local LLM Orchestration API - forge code with Ollama",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Add CORS middleware for frontend access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add API version header to all responses
    @app.middleware("http")
    async def add_api_version_header(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Sindri-API-Version"] = API_VERSION
        return response

    # Store api instance on app for access in routes
    app.state.api = api

    # ===== Schema & Version Endpoints =====

    @app.get("/api/version", tags=["Schema"])
    async def get_api_version():
        """Get the current API version and compatibility information."""
        return {
            "version": API_VERSION,
            "compatible_versions": [API_VERSION],
            "deprecated_versions": [],
        }

    @app.get("/api/schema", tags=["Schema"])
    async def get_api_schema():
        """Get JSON Schema for all WebSocket event types.

        Use this endpoint to auto-generate client types or validate event messages.
        The OpenAPI schema for REST endpoints is available at /openapi.json.
        """
        return {
            "version": API_VERSION,
            "openapi_url": "/openapi.json",
            "event_types": get_all_event_schemas(),
            "event_type_list": list(EVENT_PAYLOAD_MODELS.keys()),
        }

    @app.get("/api/schema/events/{event_type}", tags=["Schema"])
    async def get_event_schema(event_type: str):
        """Get JSON Schema for a specific event type.

        Args:
            event_type: Event type name (e.g., TASK_CREATED, AGENT_OUTPUT)
        """
        if event_type not in EVENT_PAYLOAD_MODELS:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown event type: {event_type}. Available: {list(EVENT_PAYLOAD_MODELS.keys())}",
            )
        model = EVENT_PAYLOAD_MODELS[event_type]
        return {
            "event_type": event_type,
            "schema": model.model_json_schema(),
        }

    # ===== Health & Info Endpoints =====

    async def _health_check_impl():
        """Health check implementation."""
        from ollama import Client

        # Check Ollama
        ollama_ok = False
        if os.getenv("SINDRI_SKIP_DB_INIT"):
            _ws_debug("health_check: skipping ollama check")
        else:
            try:
                client = Client()
                client.list()
                ollama_ok = True
            except Exception:
                pass

        # Check database
        db_ok = False
        if os.getenv("SINDRI_SKIP_DB_INIT"):
            _ws_debug("health_check: skipping db check")
        else:
            try:
                async with api.state.db.get_connection() as conn:
                    await conn.execute("SELECT 1")
                db_ok = True
            except Exception:
                pass

        return HealthResponse(
            status="healthy" if (ollama_ok and db_ok) else "degraded",
            version="0.1.0",
            ollama_connected=ollama_ok,
            database_ok=db_ok,
            timestamp=datetime.now().isoformat(),
        )

    @app.get("/health", response_model=HealthResponse, tags=["System"])
    async def health_check():
        """Check API health status."""
        return await _health_check_impl()

    @app.get("/api/health", response_model=HealthResponse, tags=["System"])
    async def health_check_api():
        """Check API health status (alias for /health)."""
        return await _health_check_impl()

    # ===== Agent Endpoints =====

    @app.get("/api/agents", response_model=list[AgentResponse], tags=["Agents"])
    async def list_all_agents():
        """List all available agents."""
        agents = []
        for name in list_agents():
            agent = get_agent(name)
            agents.append(
                AgentResponse(
                    name=agent.name,
                    role=agent.role,
                    model=agent.model,
                    tools=agent.tools,
                    can_delegate=agent.can_delegate,
                    delegate_to=agent.delegate_to,
                    estimated_vram_gb=agent.estimated_vram_gb,
                    max_iterations=agent.max_iterations,
                    fallback_model=agent.fallback_model,
                )
            )
        return agents

    @app.get("/api/agents/{agent_name}", response_model=AgentResponse, tags=["Agents"])
    async def get_agent_detail(agent_name: str):
        """Get details for a specific agent."""
        try:
            agent = get_agent(agent_name)
            return AgentResponse(
                name=agent.name,
                role=agent.role,
                model=agent.model,
                tools=agent.tools,
                can_delegate=agent.can_delegate,
                delegate_to=agent.delegate_to,
                estimated_vram_gb=agent.estimated_vram_gb,
                max_iterations=agent.max_iterations,
                fallback_model=agent.fallback_model,
            )
        except ValueError:
            raise HTTPException(
                status_code=404, detail=f"Agent '{agent_name}' not found"
            )

    # ===== Session Endpoints =====

    @app.get("/api/sessions", response_model=list[SessionResponse], tags=["Sessions"])
    async def list_sessions(
        limit: int = Query(
            default=20, ge=1, le=100, description="Maximum sessions to return"
        ),
        status: Optional[str] = Query(
            default=None,
            description="Filter by status (active, completed, failed, cancelled)",
        ),
    ):
        """List recent sessions."""
        sessions = await api.state.list_sessions(limit=limit)

        if status:
            sessions = [s for s in sessions if s["status"] == status]

        return [
            SessionResponse(
                id=s["id"],
                task=s["task"],
                model=s["model"],
                status=s["status"],
                created_at=s["created_at"],
                iterations=s["iterations"],
            )
            for s in sessions
        ]

    @app.get(
        "/api/sessions/{session_id}",
        response_model=SessionDetailResponse,
        tags=["Sessions"],
    )
    async def get_session_detail(session_id: str):
        """Get detailed session information including turns."""
        # Handle short session IDs
        full_id = session_id
        if len(session_id) < 36:
            sessions = await api.state.list_sessions(limit=100)
            matching = [s for s in sessions if s["id"].startswith(session_id)]
            if not matching:
                raise HTTPException(
                    status_code=404, detail=f"Session '{session_id}' not found"
                )
            if len(matching) > 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ambiguous session ID '{session_id}', matches: {[m['id'][:8] for m in matching]}",
                )
            full_id = matching[0]["id"]

        session = await api.state.load_session(full_id)
        if not session:
            raise HTTPException(
                status_code=404, detail=f"Session '{session_id}' not found"
            )

        return SessionDetailResponse(
            id=session.id,
            task=session.task,
            model=session.model,
            status=session.status,
            created_at=session.created_at.isoformat(),
            completed_at=(
                session.completed_at.isoformat() if session.completed_at else None
            ),
            iterations=session.iterations,
            turns=[
                {
                    "role": turn.role,
                    "content": turn.content,
                    "tool_calls": turn.tool_calls,
                    "created_at": turn.created_at.isoformat(),
                }
                for turn in session.turns
            ],
        )

    @app.get(
        "/api/sessions/{session_id}/file-changes",
        response_model=FileChangesResponse,
        tags=["Sessions"],
    )
    async def get_session_file_changes(
        session_id: str,
        include_content: bool = Query(
            default=True, description="Include file content in response"
        ),
    ):
        """Get all file changes from a session for diff visualization.

        Extracts file operations (read, write, edit) from session turns and
        returns structured data for rendering diffs.
        """
        # Handle short session IDs
        full_id = session_id
        if len(session_id) < 36:
            sessions = await api.state.list_sessions(limit=100)
            matching = [s for s in sessions if s["id"].startswith(session_id)]
            if not matching:
                raise HTTPException(
                    status_code=404, detail=f"Session '{session_id}' not found"
                )
            if len(matching) > 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ambiguous session ID '{session_id}', matches: {[m['id'][:8] for m in matching]}",
                )
            full_id = matching[0]["id"]

        session = await api.state.load_session(full_id)
        if not session:
            raise HTTPException(
                status_code=404, detail=f"Session '{session_id}' not found"
            )

        # Extract file changes from turns
        file_changes: list[FileChangeResponse] = []
        files_modified: set[str] = set()

        for turn_index, turn in enumerate(session.turns):
            if not turn.tool_calls:
                continue

            for tool_call in turn.tool_calls:
                # Handle both dict and object formats
                if isinstance(tool_call, dict):
                    func = tool_call.get("function", {})
                    tool_name = func.get("name", "")
                    args = func.get("arguments", {})
                else:
                    # Object format
                    func = getattr(tool_call, "function", None)
                    tool_name = getattr(func, "name", "") if func else ""
                    args = getattr(func, "arguments", {}) if func else {}

                # Parse arguments if string (JSON)
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}

                # Process file operations
                if tool_name == "read_file":
                    file_path = args.get("path", "")
                    if file_path:
                        # For reads, we store content for context (before state)
                        # Content will be in tool result, but we capture the path
                        file_changes.append(
                            FileChangeResponse(
                                file_path=file_path,
                                operation="read",
                                turn_index=turn_index,
                                timestamp=turn.created_at.isoformat(),
                                success=True,  # Assume success if in tool_calls
                                read_content=None,  # Would need tool result parsing
                            )
                        )

                elif tool_name == "write_file":
                    file_path = args.get("path", "")
                    content = args.get("content", "") if include_content else None
                    if file_path:
                        files_modified.add(file_path)
                        file_changes.append(
                            FileChangeResponse(
                                file_path=file_path,
                                operation="write",
                                turn_index=turn_index,
                                timestamp=turn.created_at.isoformat(),
                                success=True,
                                new_content=content,
                                content_size=len(args.get("content", "")),
                            )
                        )

                elif tool_name == "edit_file":
                    file_path = args.get("path", "")
                    old_text = args.get("old_text", "") if include_content else None
                    new_text = args.get("new_text", "") if include_content else None
                    if file_path:
                        files_modified.add(file_path)
                        file_changes.append(
                            FileChangeResponse(
                                file_path=file_path,
                                operation="edit",
                                turn_index=turn_index,
                                timestamp=turn.created_at.isoformat(),
                                success=True,
                                old_text=old_text,
                                new_text=new_text,
                            )
                        )

        return FileChangesResponse(
            session_id=full_id,
            file_changes=file_changes,
            files_modified=sorted(files_modified),
            total_changes=len(file_changes),
        )

    # ===== Task Endpoints =====

    @app.post("/api/tasks", response_model=TaskResponse, tags=["Tasks"])
    async def create_task(
        request: TaskCreateRequest, background_tasks: BackgroundTasks
    ):
        """Create and start a new task."""
        from sindri.core.orchestrator import Orchestrator
        from sindri.core.loop import LoopConfig

        # Validate agent
        try:
            get_agent(request.agent)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Unknown agent: {request.agent}"
            )

        # Create orchestrator
        config = LoopConfig(max_iterations=request.max_iterations)
        work_path = (
            Path(request.work_dir).resolve() if request.work_dir else api.work_dir
        )

        orchestrator = Orchestrator(
            config=config,
            total_vram_gb=api.vram_gb,
            enable_memory=request.enable_memory,
            work_dir=work_path,
            event_bus=api.event_bus,
        )

        # Generate task ID
        import uuid

        task_id = str(uuid.uuid4())

        # Track task
        api.active_tasks[task_id] = {
            "status": "running",
            "description": request.description,
            "agent": request.agent,
            "started_at": time.time(),
            "result": None,
            "error": None,
        }

        # Run task in background
        async def run_task():
            try:
                result = await orchestrator.run(request.description)
                api.active_tasks[task_id]["status"] = (
                    "completed" if result.get("success") else "failed"
                )
                api.active_tasks[task_id]["result"] = result.get("result")
                api.active_tasks[task_id]["error"] = result.get("error")
                api.active_tasks[task_id]["subtasks"] = result.get("subtasks", 0)
            except Exception as e:
                api.active_tasks[task_id]["status"] = "failed"
                api.active_tasks[task_id]["error"] = str(e)
                log.error("task_execution_failed", task_id=task_id, error=str(e))

        background_tasks.add_task(run_task)

        return TaskResponse(
            task_id=task_id,
            status="running",
            message=f"Task started with agent '{request.agent}'",
        )

    @app.get("/api/tasks/{task_id}", response_model=TaskStatusResponse, tags=["Tasks"])
    async def get_task_status(task_id: str):
        """Get task execution status."""
        if task_id not in api.active_tasks:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

        task = api.active_tasks[task_id]
        return TaskStatusResponse(
            task_id=task_id,
            status=task["status"],
            result=task.get("result"),
            error=task.get("error"),
            subtasks=task.get("subtasks", 0),
        )

    @app.get("/api/tasks", response_model=list[TaskStatusResponse], tags=["Tasks"])
    async def list_tasks(
        status: Optional[str] = Query(default=None, description="Filter by status")
    ):
        """List all tracked tasks."""
        tasks = []
        for task_id, task in api.active_tasks.items():
            if status and task["status"] != status:
                continue
            tasks.append(
                TaskStatusResponse(
                    task_id=task_id,
                    status=task["status"],
                    result=task.get("result"),
                    error=task.get("error"),
                    subtasks=task.get("subtasks", 0),
                )
            )
        return tasks

    # ===== Plan-First Execution Endpoints (ROADMAP.md Item 2) =====

    @app.get("/api/plans", tags=["Plans"])
    async def list_plans(
        status: Optional[str] = None,
        task_id: Optional[str] = None,
        limit: int = 50,
    ):
        """List execution plans with optional filtering."""
        from sindri.persistence.plans import PlanStore
        from sindri.core.plan_execution import PlanStatus

        store = PlanStore(database=api.state.db)
        plan_status = PlanStatus(status) if status else None
        plans = await store.list_plans(status=plan_status, task_id=task_id, limit=limit)
        return [p.to_dict() for p in plans]

    @app.get("/api/plans/{plan_id}", tags=["Plans"])
    async def get_plan(plan_id: str):
        """Get a specific execution plan with all steps."""
        from sindri.persistence.plans import PlanStore

        store = PlanStore(database=api.state.db)
        plan = await store.load_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        return plan.to_dict()

    @app.post("/api/plans/{plan_id}/approve", tags=["Plans"])
    async def approve_plan(plan_id: str):
        """Approve a plan for execution.

        This updates the plan status and emits a PLAN_APPROVED event.
        If an Orchestrator is running, it should listen for this event
        and resume the waiting task.
        """
        from sindri.persistence.plans import PlanStore
        from sindri.core.plan_executor import PlanExecutor

        store = PlanStore(database=api.state.db)
        executor = PlanExecutor(store, event_bus=api.event_bus)

        # Load plan to get task_id before approving
        plan = await store.load_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        task_id = plan.task_id

        success = await executor.approve_plan(plan_id)
        if not success:
            raise HTTPException(
                status_code=400, detail="Plan not found or not in proposed status"
            )

        return {"status": "approved", "plan_id": plan_id, "task_id": task_id}

    @app.post("/api/plans/{plan_id}/reject", tags=["Plans"])
    async def reject_plan(plan_id: str, reason: Optional[str] = None):
        """Reject a plan.

        This updates the plan status and emits a PLAN_REJECTED event.
        If an Orchestrator is running, it should listen for this event
        and fail the waiting task.
        """
        from sindri.persistence.plans import PlanStore
        from sindri.core.plan_executor import PlanExecutor

        store = PlanStore(database=api.state.db)
        executor = PlanExecutor(store, event_bus=api.event_bus)

        # Load plan to get task_id before rejecting
        plan = await store.load_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        task_id = plan.task_id

        success = await executor.reject_plan(plan_id, reason=reason)
        if not success:
            raise HTTPException(status_code=404, detail="Plan not found")

        return {"status": "rejected", "plan_id": plan_id, "task_id": task_id}

    @app.get("/api/plans/{plan_id}/steps", tags=["Plans"])
    async def get_plan_steps(plan_id: str):
        """Get all steps for a plan."""
        from sindri.persistence.plans import PlanStore

        store = PlanStore(database=api.state.db)
        steps = await store.get_steps_for_plan(plan_id)
        return [s.to_dict() for s in steps]

    @app.get("/api/plans/{plan_id}/steps/{step_number}", tags=["Plans"])
    async def get_plan_step(plan_id: str, step_number: int):
        """Get a specific step from a plan."""
        from sindri.persistence.plans import PlanStore

        store = PlanStore(database=api.state.db)
        plan = await store.load_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        step = plan.get_step(step_number)
        if not step:
            raise HTTPException(status_code=404, detail="Step not found")
        return step.to_dict()

    @app.post("/api/plans/{plan_id}/steps/{step_number}/approve", tags=["Plans"])
    async def approve_step(plan_id: str, step_number: int):
        """Approve a step to start execution."""
        from sindri.persistence.plans import PlanStore
        from sindri.core.plan_execution import StepStatus, ApprovalStatus
        from datetime import datetime

        store = PlanStore(database=api.state.db)
        plan = await store.load_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        step = plan.get_step(step_number)
        if not step:
            raise HTTPException(status_code=404, detail="Step not found")

        await store.update_step_approval(
            step.id, ApprovalStatus.APPROVED, approved_at=datetime.now()
        )
        await store.update_step_status(step.id, StepStatus.APPROVED)
        return {"status": "approved", "step_number": step_number}

    @app.post("/api/plans/{plan_id}/steps/{step_number}/reject", tags=["Plans"])
    async def reject_step(plan_id: str, step_number: int, reason: Optional[str] = None):
        """Reject a step (skip it)."""
        from sindri.persistence.plans import PlanStore
        from sindri.core.plan_execution import StepStatus, ApprovalStatus

        store = PlanStore(database=api.state.db)
        plan = await store.load_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        step = plan.get_step(step_number)
        if not step:
            raise HTTPException(status_code=404, detail="Step not found")

        await store.update_step_approval(
            step.id, ApprovalStatus.REJECTED, rejection_reason=reason
        )
        await store.update_step_status(step.id, StepStatus.SKIPPED)
        return {"status": "rejected", "step_number": step_number}

    @app.post("/api/plans/{plan_id}/steps/{step_number}/accept", tags=["Plans"])
    async def accept_step_result(plan_id: str, step_number: int):
        """Accept a step's result and proceed."""
        from sindri.persistence.plans import PlanStore
        from sindri.core.plan_executor import PlanExecutor
        from sindri.core.plan_execution import ApprovalStatus

        store = PlanStore(database=api.state.db)
        executor = PlanExecutor(store, event_bus=api.event_bus)
        plan = await store.load_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        step = plan.get_step(step_number)
        if not step:
            raise HTTPException(status_code=404, detail="Step not found")

        # Signal approval through executor
        executor.approve_pending(ApprovalStatus.APPROVED)
        return {"status": "accepted", "step_number": step_number}

    @app.post("/api/plans/{plan_id}/steps/{step_number}/rerun", tags=["Plans"])
    async def rerun_step(plan_id: str, step_number: int):
        """Request re-run of a step."""
        from sindri.persistence.plans import PlanStore
        from sindri.core.plan_executor import PlanExecutor

        store = PlanStore(database=api.state.db)
        executor = PlanExecutor(store, event_bus=api.event_bus)
        plan = await store.load_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        step = plan.get_step(step_number)
        if not step:
            raise HTTPException(status_code=404, detail="Step not found")

        result = await executor.rerun_step(step.id)
        return {
            "status": "rerun_completed" if result else "rerun_failed",
            "step_number": step_number,
            "result": result.to_dict() if result else None,
        }

    # ===== Metrics Endpoints =====

    @app.get("/api/metrics", response_model=MetricsResponse, tags=["Metrics"])
    async def get_system_metrics():
        """Get system-wide metrics."""
        # Get session counts
        sessions = await api.state.list_sessions(limit=1000)
        completed = sum(1 for s in sessions if s["status"] == "completed")
        failed = sum(1 for s in sessions if s["status"] == "failed")
        active = sum(1 for s in sessions if s["status"] == "active")
        total_iterations = sum(s["iterations"] for s in sessions)

        # Get VRAM stats
        vram_used = 0.0
        loaded_models = []
        if api.model_manager:
            vram_stats = api.model_manager.get_vram_stats()
            vram_used = vram_stats.get("used_gb", 0.0)
            loaded_models = (
                list(api.model_manager._loaded_models.keys())
                if hasattr(api.model_manager, "_loaded_models")
                else []
            )

        return MetricsResponse(
            total_sessions=len(sessions),
            completed_sessions=completed,
            failed_sessions=failed,
            active_sessions=active,
            total_iterations=total_iterations,
            vram_used_gb=vram_used,
            vram_total_gb=api.vram_gb,
            loaded_models=loaded_models,
        )

    @app.get("/api/metrics/sessions/{session_id}", tags=["Metrics"])
    async def get_session_metrics(session_id: str):
        """Get detailed metrics for a specific session."""
        from sindri.persistence.metrics import MetricsStore

        store = MetricsStore(api.state.db)

        # Handle short session IDs
        full_id = session_id
        if len(session_id) < 36:
            sessions = await api.state.list_sessions(limit=100)
            matching = [s for s in sessions if s["id"].startswith(session_id)]
            if not matching:
                raise HTTPException(
                    status_code=404, detail=f"Session '{session_id}' not found"
                )
            if len(matching) > 1:
                raise HTTPException(
                    status_code=400, detail=f"Ambiguous session ID '{session_id}'"
                )
            full_id = matching[0]["id"]

        metrics = await store.get_metrics(full_id)
        if not metrics:
            raise HTTPException(
                status_code=404, detail=f"Metrics not found for session '{session_id}'"
            )

        return metrics.to_dict()

    # ===== Coverage Endpoints =====

    async def _resolve_session_id(session_id: str) -> str:
        """Resolve short session ID to full UUID."""
        if len(session_id) >= 36:
            return session_id

        sessions = await api.state.list_sessions(limit=100)
        matching = [s for s in sessions if s["id"].startswith(session_id)]
        if not matching:
            raise HTTPException(
                status_code=404, detail=f"Session '{session_id}' not found"
            )
        if len(matching) > 1:
            raise HTTPException(
                status_code=400,
                detail=f"Ambiguous session ID '{session_id}', matches: {[m['id'][:8] for m in matching]}",
            )
        return matching[0]["id"]

    @app.get(
        "/api/sessions/{session_id}/coverage",
        response_model=CoverageSummaryResponse,
        tags=["Coverage"],
    )
    async def get_session_coverage_summary(session_id: str):
        """Get coverage summary for a session.

        Returns high-level coverage metrics without detailed file breakdown.
        """
        from sindri.persistence.coverage import CoverageStore

        full_id = await _resolve_session_id(session_id)
        store = CoverageStore(api.state.db)

        coverage = await store.load_coverage(full_id)
        if not coverage:
            raise HTTPException(
                status_code=404, detail=f"Coverage not found for session '{session_id}'"
            )

        summary = coverage.get_summary()
        return CoverageSummaryResponse(**summary)

    @app.get(
        "/api/sessions/{session_id}/coverage/detail",
        response_model=CoverageDetailResponse,
        tags=["Coverage"],
    )
    async def get_session_coverage_detail(session_id: str):
        """Get detailed coverage for a session including file breakdown.

        Returns complete coverage data with package and file-level details.
        """
        from sindri.persistence.coverage import CoverageStore

        full_id = await _resolve_session_id(session_id)
        store = CoverageStore(api.state.db)

        coverage = await store.load_coverage(full_id)
        if not coverage:
            raise HTTPException(
                status_code=404, detail=f"Coverage not found for session '{session_id}'"
            )

        # Build response with packages and files
        packages = []
        for pkg in coverage.packages:
            files = []
            for f in pkg.files:
                files.append(
                    FileCoverageResponse(
                        filename=f.filename,
                        lines_valid=f.lines_valid,
                        lines_covered=f.lines_covered,
                        line_rate=f.line_rate,
                        line_percentage=f.line_percentage,
                        branches_valid=f.branches_valid,
                        branches_covered=f.branches_covered,
                        branch_rate=f.branch_rate,
                        covered_lines=f.covered_lines,
                        uncovered_lines=f.uncovered_lines,
                    )
                )
            packages.append(
                PackageCoverageResponse(
                    name=pkg.name,
                    line_rate=pkg.line_rate,
                    branch_rate=pkg.branch_rate,
                    lines_valid=pkg.lines_valid,
                    lines_covered=pkg.lines_covered,
                    files=files,
                )
            )

        summary = coverage.get_summary()
        return CoverageDetailResponse(
            **summary,
            packages=packages,
        )

    @app.post(
        "/api/sessions/{session_id}/coverage",
        response_model=CoverageSummaryResponse,
        tags=["Coverage"],
    )
    async def import_session_coverage(session_id: str, request: CoverageImportRequest):
        """Import coverage data from a file for a session.

        Supports Cobertura XML (coverage.xml), LCOV (lcov.info), and JSON formats.
        """
        from sindri.persistence.coverage import CoverageStore

        full_id = await _resolve_session_id(session_id)
        store = CoverageStore(api.state.db)

        coverage_path = Path(request.coverage_path)
        if not coverage_path.exists():
            raise HTTPException(
                status_code=400, detail=f"Coverage file not found: {request.coverage_path}"
            )

        try:
            coverage = await store.import_from_file(full_id, coverage_path)
            summary = coverage.get_summary()
            return CoverageSummaryResponse(**summary)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            log.error("coverage_import_failed", error=str(e))
            raise HTTPException(
                status_code=500, detail=f"Failed to import coverage: {str(e)}"
            )

    @app.delete("/api/sessions/{session_id}/coverage", tags=["Coverage"])
    async def delete_session_coverage(session_id: str):
        """Delete coverage data for a session."""
        from sindri.persistence.coverage import CoverageStore

        full_id = await _resolve_session_id(session_id)
        store = CoverageStore(api.state.db)

        deleted = await store.delete_coverage(full_id)
        if not deleted:
            raise HTTPException(
                status_code=404, detail=f"Coverage not found for session '{session_id}'"
            )

        return {"message": "Coverage deleted", "session_id": full_id}

    @app.get("/api/coverage", response_model=list[dict], tags=["Coverage"])
    async def list_coverage_reports(
        limit: int = Query(default=20, ge=1, le=100, description="Maximum reports to return"),
    ):
        """List recent coverage reports across all sessions."""
        from sindri.persistence.coverage import CoverageStore

        store = CoverageStore(api.state.db)
        return await store.list_coverage(limit=limit)

    @app.get("/api/coverage/stats", response_model=CoverageStatsResponse, tags=["Coverage"])
    async def get_coverage_stats():
        """Get aggregate coverage statistics across all sessions."""
        from sindri.persistence.coverage import CoverageStore

        store = CoverageStore(api.state.db)
        stats = await store.get_aggregate_stats()
        return CoverageStatsResponse(**stats)

    # ===== WebSocket Endpoint =====

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for real-time event streaming."""
        _ws_debug("websocket_endpoint: start")
        await websocket.accept()
        api.websocket_connections.append(websocket)
        _ws_debug(
            f"websocket_endpoint: accepted (connections={len(api.websocket_connections)})"
        )
        log.info(
            "websocket_connected", total_connections=len(api.websocket_connections)
        )

        try:
            # Send initial state
            _ws_debug("websocket_endpoint: sending connected message")
            await websocket.send_json(
                {
                    "type": "connected",
                    "data": {
                        "message": "Connected to Sindri API",
                        "version": "0.1.0",
                        "active_connections": len(api.websocket_connections),
                    },
                    "timestamp": time.time(),
                }
            )
            _ws_debug("websocket_endpoint: connected message sent")

            # Keep connection alive and handle incoming messages
            while True:
                try:
                    # Wait for messages (with timeout for heartbeat)
                    _ws_debug("websocket_endpoint: waiting for message")
                    data = await asyncio.wait_for(
                        websocket.receive_text(), timeout=30.0
                    )
                    _ws_debug("websocket_endpoint: received message")

                    # Handle ping/pong
                    message = json.loads(data)
                    if message.get("type") == "ping":
                        _ws_debug("websocket_endpoint: responding to ping")
                        await websocket.send_json(
                            {"type": "pong", "timestamp": time.time()}
                        )

                except asyncio.TimeoutError:
                    # Send heartbeat
                    _ws_debug("websocket_endpoint: sending heartbeat")
                    await websocket.send_json(
                        {"type": "heartbeat", "timestamp": time.time()}
                    )

        except WebSocketDisconnect:
            _ws_debug("websocket_endpoint: disconnect")
            log.info("websocket_disconnected")
        except Exception as e:
            _ws_debug(f"websocket_endpoint: error {e}")
            log.error("websocket_error", error=str(e))
        finally:
            if websocket in api.websocket_connections:
                api.websocket_connections.remove(websocket)
            _ws_debug(
                f"websocket_endpoint: cleanup (connections={len(api.websocket_connections)})"
            )
            log.info(
                "websocket_cleanup",
                remaining_connections=len(api.websocket_connections),
            )

    # ===== Static Files & SPA Support =====

    # Path to static files (React build output)
    static_dir = Path(__file__).parent / "static" / "dist"

    if static_dir.exists():
        # Mount static assets (JS, CSS, images)
        app.mount(
            "/assets", StaticFiles(directory=static_dir / "assets"), name="assets"
        )

        # Serve index.html for SPA routing (catch-all for non-API routes)
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            """Serve the SPA for all non-API routes."""
            # Don't catch API or WebSocket routes
            if (
                full_path.startswith("api/")
                or full_path == "ws"
                or full_path == "health"
            ):
                raise HTTPException(status_code=404, detail="Not found")

            # Try to serve static file first
            file_path = static_dir / full_path
            if file_path.is_file():
                return FileResponse(file_path)

            # Fall back to index.html for SPA client-side routing
            index_path = static_dir / "index.html"
            if index_path.exists():
                return FileResponse(index_path)

            raise HTTPException(status_code=404, detail="Not found")

        log.info("static_files_mounted", path=str(static_dir))
    else:
        log.warning("static_files_not_found", expected_path=str(static_dir))

    return app


def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    vram_gb: float = 16.0,
    work_dir: Optional[Path] = None,
):
    """Run the Sindri API server.

    Args:
        host: Host to bind to
        port: Port to listen on
        vram_gb: Total VRAM available
        work_dir: Working directory for file operations
    """
    import uvicorn

    app = create_app(vram_gb=vram_gb, work_dir=work_dir)
    uvicorn.run(app, host=host, port=port, log_level="info")
