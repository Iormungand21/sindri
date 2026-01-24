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
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
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
from sindri.telemetry.collector import TelemetryCollector

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


# ===== Trigger Models =====


class TriggerCreateRequest(BaseModel):
    """Request to create a new trigger."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="")
    trigger_type: str = Field(..., description="Type: cron, webhook, or event")
    task_description: str = Field(..., min_length=1)
    agent: str = Field(default="brokkr")
    max_iterations: int = Field(default=30, ge=1, le=100)
    work_dir: Optional[str] = None

    # Cron-specific fields
    cron_expression: Optional[str] = None
    timezone: str = Field(default="UTC")

    # Webhook-specific fields
    webhook_secret: Optional[str] = None
    rate_limit_per_minute: int = Field(default=10, ge=1, le=100)

    # Event-specific fields
    event_types: list[str] = Field(default_factory=list)
    event_filters: dict[str, Any] = Field(default_factory=dict)

    # Notifications
    notifications: list[dict] = Field(default_factory=list)


class TriggerUpdateRequest(BaseModel):
    """Request to update a trigger (all fields optional for PATCH-style updates)."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    task_description: Optional[str] = None
    agent: Optional[str] = None
    max_iterations: Optional[int] = Field(None, ge=1, le=100)
    work_dir: Optional[str] = None
    cron_expression: Optional[str] = None
    timezone: Optional[str] = None
    webhook_secret: Optional[str] = None
    rate_limit_per_minute: Optional[int] = Field(None, ge=1, le=100)
    event_types: Optional[list[str]] = None
    event_filters: Optional[dict[str, Any]] = None
    notifications: Optional[list[dict]] = None


class TriggerRunRequest(BaseModel):
    """Request to manually run a trigger."""

    context: Optional[dict[str, Any]] = Field(
        default=None, description="Context data for execution"
    )


class TriggerResponse(BaseModel):
    """Trigger information response.

    Note: webhook_secret is intentionally excluded to prevent leaking secrets.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    description: str
    trigger_type: str
    status: str
    task_description: str
    agent: str
    max_iterations: int
    work_dir: Optional[str]
    cron_expression: Optional[str]
    timezone: str
    # webhook_secret intentionally excluded - sensitive data
    rate_limit_per_minute: int
    event_types: list[str]
    event_filters: dict[str, Any]
    notifications: list[dict]
    created_at: str
    updated_at: str
    last_run_at: Optional[str]
    next_run_at: Optional[str]
    run_count: int
    failure_count: int
    consecutive_failures: int


class TriggerRunResponse(BaseModel):
    """Trigger run record response."""

    id: str
    trigger_id: str
    trigger_name: str
    task_id: Optional[str]
    session_id: Optional[str]
    started_at: str
    completed_at: Optional[str]
    duration_ms: Optional[float]
    success: bool
    error: Optional[str]
    result_summary: Optional[str]
    webhook_payload: Optional[dict]
    webhook_headers: Optional[dict]
    event_type: Optional[str]
    event_data: Optional[dict]


class TriggerStatsResponse(BaseModel):
    """Aggregate trigger statistics response."""

    total_triggers: int
    enabled_triggers: int
    disabled_triggers: int
    paused_triggers: int
    total_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float
    by_type: dict[str, int]


class SindriAPI:
    """Sindri API application state."""

    def __init__(self, vram_gb: float = 16.0, work_dir: Optional[Path] = None):
        self.vram_gb = vram_gb
        self.work_dir = work_dir
        self.state = SessionState()
        self.event_bus = EventBus()
        self.model_manager: Optional[ModelManager] = None
        self.telemetry_collector: Optional[TelemetryCollector] = None
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

        # Start TelemetryCollector for real-time metrics
        self.telemetry_collector = TelemetryCollector(
            event_bus=self.event_bus,
            model_manager=self.model_manager,
        )
        await self.telemetry_collector.start()
        _ws_debug("api.initialize: telemetry collector started")

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
        # Stop TelemetryCollector
        if self.telemetry_collector:
            await self.telemetry_collector.stop()
            _ws_debug("api.shutdown: telemetry collector stopped")

        # Close WebSocket connections
        for ws in self.websocket_connections:
            try:
                await ws.close()
            except Exception:
                pass
        self.websocket_connections.clear()
        log.info("sindri_api_shutdown")


def create_app(
    vram_gb: float = 16.0,
    work_dir: Optional[Path] = None,
    allowed_origins: Optional[list[str]] = None,
    allow_credentials: bool = False,
    port: int = 8000,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        vram_gb: Total VRAM available in GB
        work_dir: Working directory for file operations
        allowed_origins: CORS allowed origins (default: localhost + 127.0.0.1 on given port)
        allow_credentials: Allow credentials in CORS requests
        port: Server port for generating default origins

    Returns:
        Configured FastAPI application

    Raises:
        ValueError: If CORS configuration is insecure (wildcard + credentials)

    Environment Variables (for reload mode):
        SINDRI_CORS_ORIGINS: Comma-separated list of allowed origins (triggers env var mode)
        SINDRI_CORS_CREDENTIALS: "1" to enable credentials, "0" to disable
        SINDRI_SERVER_PORT: Port for generating default origins
    """
    # Check for environment variables (used in reload mode)
    # Env vars are a complete package - only used when SINDRI_CORS_ORIGINS is set
    # AND no explicit allowed_origins were passed. This prevents partial overrides.
    env_origins = os.getenv("SINDRI_CORS_ORIGINS")

    if env_origins is not None and allowed_origins is None:
        # Reload mode: CLI set env vars, use them as a complete package
        allowed_origins = [o.strip() for o in env_origins.split(",") if o.strip()]
        env_credentials = os.getenv("SINDRI_CORS_CREDENTIALS")
        if env_credentials is not None:
            allow_credentials = env_credentials == "1"
        env_port = os.getenv("SINDRI_SERVER_PORT")
        if env_port is not None:
            try:
                port = int(env_port)
            except ValueError:
                pass

    # Default CORS origins - both localhost and 127.0.0.1 for the actual port
    if allowed_origins is None:
        allowed_origins = [
            f"http://localhost:{port}",
            f"http://127.0.0.1:{port}",
        ]

    # Validate CORS security: reject wildcard with credentials
    if allow_credentials and "*" in allowed_origins:
        raise ValueError(
            "CORS security error: allow_credentials=True cannot be used with "
            "wildcard origin '*'. This combination is rejected by browsers and "
            "indicates a misconfiguration. Use specific origins instead."
        )

    api = SindriAPI(vram_gb=vram_gb, work_dir=work_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan handler."""
        _ws_debug("lifespan: start")
        await api.initialize()
        _ws_debug("lifespan: initialized")

        # Log startup configuration
        log.info(
            "sindri_api_cors_config",
            allowed_origins=allowed_origins,
            allow_credentials=allow_credentials,
        )

        yield
        _ws_debug("lifespan: shutdown")
        await api.shutdown()

    app = FastAPI(
        title="Sindri API",
        description="Local LLM Orchestration API - forge code with Ollama",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Add CORS middleware with secure defaults (Web/API Hardening PRD - Epic A)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,
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
            telemetry_collector=api.telemetry_collector,
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
            finally:
                # Unregister from telemetry on task completion
                await orchestrator.cleanup()

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

    # ===== Telemetry Endpoints (ROADMAP Item 7: Performance Telemetry Stream) =====

    @app.get("/api/metrics/live", tags=["Telemetry"])
    async def stream_live_telemetry():
        """Stream live telemetry metrics via Server-Sent Events.

        This endpoint provides real-time telemetry data including:
        - VRAM usage and loaded models
        - Task concurrency (running/pending/waiting)
        - Session progress (current agent, iteration)

        Connect with EventSource in browsers or curl:
            curl -N http://localhost:8000/api/metrics/live

        Events:
        - connected: Initial connection confirmation
        - telemetry_tick: Periodic snapshot (every 2 seconds)
        - heartbeat: Keep-alive (every 30 seconds if no data)
        """
        from sindri.core.event_schemas import TelemetryTickData, VRAMSnapshot, ConcurrencySnapshot

        async def event_generator():
            # Send initial connection event
            yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'timestamp': time.time()})}\n\n"

            # Create a queue for this connection
            queue: asyncio.Queue = asyncio.Queue(maxsize=10)

            def on_telemetry_event(event: Event):
                """Handle TELEMETRY_TICK events from EventBus."""
                if event.type == EventType.TELEMETRY_TICK:
                    try:
                        queue.put_nowait(event.data)
                    except asyncio.QueueFull:
                        pass  # Drop if queue is full

            # Subscribe to telemetry events
            api.event_bus.subscribe_event(on_telemetry_event)

            try:
                last_heartbeat = time.time()
                while True:
                    try:
                        # Wait for telemetry data with timeout
                        data = await asyncio.wait_for(queue.get(), timeout=5.0)
                        yield f"event: telemetry_tick\ndata: {json.dumps(data)}\n\n"
                        last_heartbeat = time.time()
                    except asyncio.TimeoutError:
                        # Send heartbeat if no data for 30 seconds
                        if time.time() - last_heartbeat > 30:
                            yield f"event: heartbeat\ndata: {json.dumps({'timestamp': time.time()})}\n\n"
                            last_heartbeat = time.time()

                        # If no active telemetry collector, generate synthetic tick
                        if not hasattr(api, "telemetry_collector") or not api.telemetry_collector:
                            # Generate basic tick from available stats
                            vram_stats = {}
                            cache_stats = {}
                            loaded_models = []
                            if api.model_manager:
                                vram_stats = api.model_manager.get_vram_stats()
                                cache_stats = api.model_manager.get_cache_stats()
                                loaded_models = vram_stats.get("loaded_models", [])

                            tick_data = {
                                "timestamp": time.time(),
                                "session_id": None,
                                "vram": {
                                    "total_gb": vram_stats.get("total", api.vram_gb),
                                    "used_gb": vram_stats.get("used", 0.0),
                                    "free_gb": vram_stats.get("free", api.vram_gb),
                                    "loaded_models": loaded_models,
                                    "cache_hit_rate": cache_stats.get("hit_rate", 0.0),
                                },
                                "concurrency": {
                                    "running_tasks": len(api.active_tasks),
                                    "pending_tasks": 0,
                                    "waiting_tasks": 0,
                                    "batch_size": 0,
                                },
                                "session_duration_seconds": 0.0,
                                "current_agent": None,
                                "current_iteration": 0,
                            }
                            yield f"event: telemetry_tick\ndata: {json.dumps(tick_data)}\n\n"
                            last_heartbeat = time.time()
            except asyncio.CancelledError:
                pass
            finally:
                api.event_bus.unsubscribe_event(on_telemetry_event)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    @app.get("/api/metrics/telemetry/snapshot", tags=["Telemetry"])
    async def get_telemetry_snapshot():
        """Get current telemetry snapshot (on-demand).

        Returns full telemetry data including agent and tool statistics
        if a telemetry collector is active.
        """
        from sindri.core.event_schemas import (
            TelemetrySnapshotData,
            VRAMSnapshot,
            ConcurrencySnapshot,
        )

        # Check for active telemetry collector
        if hasattr(api, "telemetry_collector") and api.telemetry_collector:
            return api.telemetry_collector.get_snapshot().model_dump()

        # Generate basic snapshot from available stats
        vram_stats = {}
        cache_stats = {}
        loaded_models = []
        if api.model_manager:
            vram_stats = api.model_manager.get_vram_stats()
            cache_stats = api.model_manager.get_cache_stats()
            loaded_models = vram_stats.get("loaded_models", [])

        return {
            "timestamp": time.time(),
            "session_id": "",
            "session_duration_seconds": 0.0,
            "vram": {
                "total_gb": vram_stats.get("total", api.vram_gb),
                "used_gb": vram_stats.get("used", 0.0),
                "free_gb": vram_stats.get("free", api.vram_gb),
                "loaded_models": loaded_models,
                "cache_hit_rate": cache_stats.get("hit_rate", 0.0),
            },
            "concurrency": {
                "running_tasks": len(api.active_tasks),
                "pending_tasks": 0,
                "waiting_tasks": 0,
                "batch_size": 0,
            },
            "agent_stats": [],
            "tool_stats": [],
            "total_iterations": 0,
            "total_tool_calls": 0,
            "llm_time_seconds": 0.0,
            "tool_time_seconds": 0.0,
        }

    @app.get("/api/metrics/vram/history", tags=["Telemetry"])
    async def get_vram_history():
        """Get VRAM usage time-series for charting.

        Returns up to 5 minutes of VRAM history at 2-second intervals
        if a telemetry collector is active.
        """
        if hasattr(api, "telemetry_collector") and api.telemetry_collector:
            history = api.telemetry_collector.get_vram_history()
            return {
                "history": [
                    {"timestamp": ts, "vram": vram.model_dump()} for ts, vram in history
                ]
            }
        return {"history": [], "message": "No active telemetry collection"}

    @app.get("/api/metrics/concurrency/history", tags=["Telemetry"])
    async def get_concurrency_history():
        """Get task concurrency time-series for charting.

        Returns up to 5 minutes of concurrency history at 2-second intervals
        if a telemetry collector is active.
        """
        if hasattr(api, "telemetry_collector") and api.telemetry_collector:
            history = api.telemetry_collector.get_concurrency_history()
            return {
                "history": [
                    {"timestamp": ts, "concurrency": conc.model_dump()}
                    for ts, conc in history
                ]
            }
        return {"history": [], "message": "No active telemetry collection"}

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

    # ===== Trigger Endpoints =====

    @app.get("/api/triggers", response_model=list[TriggerResponse], tags=["Triggers"])
    async def list_triggers(
        trigger_type: Optional[str] = Query(
            default=None,
            description="Filter by type (cron, webhook, event)",
        ),
        status: Optional[str] = Query(
            default=None,
            description="Filter by status (enabled, disabled, paused)",
        ),
        limit: int = Query(
            default=50,
            ge=1,
            le=200,
            description="Maximum triggers to return",
        ),
    ):
        """List all triggers with optional filtering."""
        from sindri.triggers.store import TriggerStore
        from sindri.triggers.models import TriggerType, TriggerStatus

        store = TriggerStore(database=api.state.db)

        type_filter = None
        if trigger_type:
            try:
                type_filter = TriggerType(trigger_type)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid trigger_type: {trigger_type}. Must be cron, webhook, or event",
                )

        status_filter = None
        if status:
            try:
                status_filter = TriggerStatus(status)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {status}. Must be enabled, disabled, or paused",
                )

        triggers = await store.list_triggers(
            trigger_type=type_filter,
            status=status_filter,
            limit=limit,
        )

        return [TriggerResponse(**t.to_dict()) for t in triggers]

    @app.get(
        "/api/triggers/stats", response_model=TriggerStatsResponse, tags=["Triggers"]
    )
    async def get_trigger_stats():
        """Get aggregate trigger statistics."""
        from sindri.triggers.store import TriggerStore
        from sindri.triggers.models import TriggerStatus

        store = TriggerStore(database=api.state.db)
        triggers = await store.list_triggers(limit=1000)

        # Aggregate counts
        enabled = sum(1 for t in triggers if t.status == TriggerStatus.ENABLED)
        disabled = sum(1 for t in triggers if t.status == TriggerStatus.DISABLED)
        paused = sum(1 for t in triggers if t.status == TriggerStatus.PAUSED)

        total_runs = sum(t.run_count for t in triggers)
        total_failures = sum(t.failure_count for t in triggers)
        successful_runs = total_runs - total_failures

        by_type: dict[str, int] = {}
        for t in triggers:
            by_type[t.trigger_type.value] = by_type.get(t.trigger_type.value, 0) + 1

        return TriggerStatsResponse(
            total_triggers=len(triggers),
            enabled_triggers=enabled,
            disabled_triggers=disabled,
            paused_triggers=paused,
            total_runs=total_runs,
            successful_runs=successful_runs,
            failed_runs=total_failures,
            success_rate=successful_runs / total_runs if total_runs > 0 else 0.0,
            by_type=by_type,
        )

    @app.get(
        "/api/triggers/{trigger_id}",
        response_model=TriggerResponse,
        tags=["Triggers"],
    )
    async def get_trigger(trigger_id: str):
        """Get details for a specific trigger."""
        from sindri.triggers.store import TriggerStore

        store = TriggerStore(database=api.state.db)
        trigger = await store.load_trigger(trigger_id)

        if not trigger:
            raise HTTPException(
                status_code=404, detail=f"Trigger '{trigger_id}' not found"
            )

        return TriggerResponse(**trigger.to_dict())

    @app.get(
        "/api/triggers/{trigger_id}/runs",
        response_model=list[TriggerRunResponse],
        tags=["Triggers"],
    )
    async def get_trigger_runs(
        trigger_id: str,
        limit: int = Query(default=50, ge=1, le=200),
    ):
        """Get run history for a trigger."""
        from sindri.triggers.store import TriggerStore

        store = TriggerStore(database=api.state.db)

        # Verify trigger exists
        trigger = await store.load_trigger(trigger_id)
        if not trigger:
            raise HTTPException(
                status_code=404, detail=f"Trigger '{trigger_id}' not found"
            )

        runs = await store.list_runs(trigger_id, limit=limit)
        return [TriggerRunResponse(**r.to_dict()) for r in runs]

    @app.get(
        "/api/triggers/{trigger_id}/runs/{run_id}",
        response_model=TriggerRunResponse,
        tags=["Triggers"],
    )
    async def get_trigger_run(trigger_id: str, run_id: str):
        """Get a specific trigger run."""
        from sindri.triggers.store import TriggerStore

        store = TriggerStore(database=api.state.db)

        # Verify trigger exists
        trigger = await store.load_trigger(trigger_id)
        if not trigger:
            raise HTTPException(
                status_code=404, detail=f"Trigger '{trigger_id}' not found"
            )

        run = await store.load_run(run_id)
        if not run or run.trigger_id != trigger_id:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

        return TriggerRunResponse(**run.to_dict())

    @app.post("/api/triggers", response_model=TriggerResponse, tags=["Triggers"])
    async def create_trigger(request: TriggerCreateRequest):
        """Create a new trigger."""
        from sindri.triggers.store import TriggerStore
        from sindri.triggers.models import (
            TriggerDefinition,
            TriggerType,
            NotificationHook,
        )
        from sindri.triggers.scheduler import TriggerScheduler

        store = TriggerStore(database=api.state.db)

        # Validate trigger type
        try:
            trigger_type = TriggerType(request.trigger_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid trigger type: {request.trigger_type}. Must be cron, webhook, or event",
            )

        # Validate cron expression if cron type
        if trigger_type == TriggerType.CRON:
            if not request.cron_expression:
                raise HTTPException(
                    status_code=400,
                    detail="cron_expression is required for cron triggers",
                )
            scheduler = TriggerScheduler(store, None)
            valid, error = scheduler.validate_cron_expression(request.cron_expression)
            if not valid:
                raise HTTPException(
                    status_code=400, detail=f"Invalid cron expression: {error}"
                )

        # Build notification hooks
        notifications = []
        for n in request.notifications:
            try:
                notifications.append(NotificationHook(**n))
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid notification config: {e}"
                )

        # Create trigger
        trigger = TriggerDefinition(
            name=request.name,
            description=request.description,
            trigger_type=trigger_type,
            task_description=request.task_description,
            agent=request.agent,
            max_iterations=request.max_iterations,
            work_dir=request.work_dir,
            cron_expression=request.cron_expression,
            timezone=request.timezone,
            webhook_secret=request.webhook_secret,
            rate_limit_per_minute=request.rate_limit_per_minute,
            event_types=request.event_types,
            event_filters=request.event_filters,
            notifications=notifications,
        )

        # Calculate next_run for cron triggers
        if trigger_type == TriggerType.CRON:
            scheduler = TriggerScheduler(store, None)
            trigger.next_run_at = scheduler._calculate_next_run(trigger)

        # Save trigger
        await store.save_trigger(trigger)

        # Emit event
        api.event_bus.emit(
            Event(
                type=EventType.TRIGGER_CREATED,
                data={
                    "trigger_id": trigger.id,
                    "name": trigger.name,
                    "trigger_type": trigger_type.value,
                },
                timestamp=time.time(),
            )
        )

        return TriggerResponse(**trigger.to_dict())

    @app.put(
        "/api/triggers/{trigger_id}",
        response_model=TriggerResponse,
        tags=["Triggers"],
    )
    async def update_trigger(trigger_id: str, request: TriggerUpdateRequest):
        """Update a trigger."""
        from sindri.triggers.store import TriggerStore
        from sindri.triggers.models import TriggerType
        from sindri.triggers.scheduler import TriggerScheduler

        store = TriggerStore(database=api.state.db)

        # Verify trigger exists
        existing = await store.load_trigger(trigger_id)
        if not existing:
            raise HTTPException(
                status_code=404, detail=f"Trigger '{trigger_id}' not found"
            )

        # Build updates dict, excluding None values
        updates = {k: v for k, v in request.model_dump().items() if v is not None}

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Validate new cron expression if provided
        if "cron_expression" in updates:
            scheduler = TriggerScheduler(store, None)
            valid, error = scheduler.validate_cron_expression(
                updates["cron_expression"]
            )
            if not valid:
                raise HTTPException(
                    status_code=400, detail=f"Invalid cron expression: {error}"
                )

        # Validate notifications if provided
        if "notifications" in updates:
            from sindri.triggers.models import NotificationHook

            validated_notifications = []
            for n in updates["notifications"]:
                try:
                    validated_notifications.append(NotificationHook(**n))
                except Exception as e:
                    raise HTTPException(
                        status_code=400, detail=f"Invalid notification config: {e}"
                    )
            updates["notifications"] = validated_notifications

        # Apply updates
        await store.update_trigger(trigger_id, updates)

        # Recalculate next_run if cron expression or timezone changed
        if "cron_expression" in updates or "timezone" in updates:
            updated_trigger = await store.load_trigger(trigger_id)
            if updated_trigger and updated_trigger.trigger_type == TriggerType.CRON:
                scheduler = TriggerScheduler(store, None)
                next_run = scheduler._calculate_next_run(updated_trigger)
                if next_run:
                    await store.update_next_run(trigger_id, next_run)

        # Load updated trigger
        trigger = await store.load_trigger(trigger_id)

        # Emit event
        api.event_bus.emit(
            Event(
                type=EventType.TRIGGER_UPDATED,
                data={
                    "trigger_id": trigger_id,
                    "name": trigger.name if trigger else existing.name,
                    "fields_updated": list(updates.keys()),
                },
                timestamp=time.time(),
            )
        )

        return TriggerResponse(**trigger.to_dict())

    @app.delete("/api/triggers/{trigger_id}", tags=["Triggers"])
    async def delete_trigger(trigger_id: str):
        """Delete a trigger and its run history."""
        from sindri.triggers.store import TriggerStore

        store = TriggerStore(database=api.state.db)

        # Load trigger for event data before deleting
        trigger = await store.load_trigger(trigger_id)
        if not trigger:
            raise HTTPException(
                status_code=404, detail=f"Trigger '{trigger_id}' not found"
            )

        trigger_name = trigger.name
        deleted = await store.delete_trigger(trigger_id)

        if not deleted:
            raise HTTPException(status_code=500, detail="Failed to delete trigger")

        # Emit event
        api.event_bus.emit(
            Event(
                type=EventType.TRIGGER_DELETED,
                data={"trigger_id": trigger_id, "name": trigger_name},
                timestamp=time.time(),
            )
        )

        return {"message": "Trigger deleted", "trigger_id": trigger_id}

    @app.post(
        "/api/triggers/{trigger_id}/enable",
        response_model=TriggerResponse,
        tags=["Triggers"],
    )
    async def enable_trigger(trigger_id: str):
        """Enable a trigger."""
        from sindri.triggers.store import TriggerStore
        from sindri.triggers.models import TriggerStatus

        store = TriggerStore(database=api.state.db)

        trigger = await store.load_trigger(trigger_id)
        if not trigger:
            raise HTTPException(
                status_code=404, detail=f"Trigger '{trigger_id}' not found"
            )

        await store.update_trigger(
            trigger_id, {"status": TriggerStatus.ENABLED, "consecutive_failures": 0}
        )

        # Emit event
        api.event_bus.emit(
            Event(
                type=EventType.TRIGGER_ENABLED,
                data={"trigger_id": trigger_id, "name": trigger.name},
                timestamp=time.time(),
            )
        )

        trigger = await store.load_trigger(trigger_id)
        return TriggerResponse(**trigger.to_dict())

    @app.post(
        "/api/triggers/{trigger_id}/disable",
        response_model=TriggerResponse,
        tags=["Triggers"],
    )
    async def disable_trigger(trigger_id: str):
        """Disable a trigger."""
        from sindri.triggers.store import TriggerStore
        from sindri.triggers.models import TriggerStatus

        store = TriggerStore(database=api.state.db)

        trigger = await store.load_trigger(trigger_id)
        if not trigger:
            raise HTTPException(
                status_code=404, detail=f"Trigger '{trigger_id}' not found"
            )

        await store.update_trigger(trigger_id, {"status": TriggerStatus.DISABLED})

        # Emit event
        api.event_bus.emit(
            Event(
                type=EventType.TRIGGER_DISABLED,
                data={"trigger_id": trigger_id, "name": trigger.name},
                timestamp=time.time(),
            )
        )

        trigger = await store.load_trigger(trigger_id)
        return TriggerResponse(**trigger.to_dict())

    @app.post(
        "/api/triggers/{trigger_id}/run",
        response_model=TriggerRunResponse,
        tags=["Triggers"],
    )
    async def run_trigger(
        trigger_id: str,
        request: Optional[TriggerRunRequest] = None,
    ):
        """Manually execute a trigger."""
        from sindri.triggers.store import TriggerStore
        from sindri.triggers.executor import TriggerExecutor

        store = TriggerStore(database=api.state.db)

        trigger = await store.load_trigger(trigger_id)
        if not trigger:
            raise HTTPException(
                status_code=404, detail=f"Trigger '{trigger_id}' not found"
            )

        executor = TriggerExecutor(
            store=store,
            event_bus=api.event_bus,
            vram_gb=api.vram_gb,
        )

        context = request.context if request else None
        run = await executor.execute_trigger(trigger, context=context)

        return TriggerRunResponse(**run.to_dict())

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
    host: Optional[str] = None,
    port: Optional[int] = None,
    vram_gb: float = 16.0,
    work_dir: Optional[Path] = None,
    allowed_origins: Optional[list[str]] = None,
    allow_credentials: Optional[bool] = None,
):
    """Run the Sindri API server.

    Args:
        host: Host to bind to (default: from config or 127.0.0.1)
        port: Port to listen on (default: from config or 8000)
        vram_gb: Total VRAM available
        work_dir: Working directory for file operations
        allowed_origins: CORS allowed origins (default: from config or localhost + 127.0.0.1)
        allow_credentials: Allow credentials in CORS requests (default: from config or False)

    Configuration is loaded from sindri.toml if available. Explicit arguments override config.
    """
    import uvicorn
    from sindri.config import SindriConfig

    # Load config for defaults
    config = SindriConfig.load()
    api_config = config.api

    # Apply config defaults where args are None
    effective_host = host if host is not None else api_config.bind_host
    effective_port = port if port is not None else api_config.bind_port
    effective_credentials = (
        allow_credentials if allow_credentials is not None else api_config.allow_credentials
    )

    # Build CORS origins - use provided, config, or generate defaults
    if allowed_origins is None:
        allowed_origins = api_config.get_allowed_origins(effective_port)

    app = create_app(
        vram_gb=vram_gb,
        work_dir=work_dir,
        allowed_origins=allowed_origins,
        allow_credentials=effective_credentials,
        port=effective_port,
    )
    uvicorn.run(app, host=effective_host, port=effective_port, log_level="info")
