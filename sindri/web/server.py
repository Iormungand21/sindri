"""Sindri Web API Server.

Phase 8.3: FastAPI-based Web API for Sindri orchestration.

Features:
- REST API for agents, sessions, tasks, metrics
- WebSocket for real-time event streaming
- Integration with EventBus system
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import structlog

from sindri.agents.registry import AGENTS, get_agent, list_agents
from sindri.persistence.state import SessionState
from sindri.persistence.database import Database
from sindri.core.events import EventBus, EventType, Event
from sindri.llm.manager import ModelManager

log = structlog.get_logger()


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


# Collaboration models
class ShareCreateRequest(BaseModel):
    """Request to create a session share."""
    permission: str = Field(default="read", description="Permission level: read, comment, write")
    expires_in_hours: Optional[float] = Field(default=None, description="Hours until expiration")
    max_uses: Optional[int] = Field(default=None, description="Maximum number of uses")
    created_by: Optional[str] = Field(default=None, description="Creator identifier")


class ShareResponse(BaseModel):
    """Session share response."""
    id: int
    session_id: str
    share_token: str
    share_url: str
    permission: str
    expires_at: Optional[str] = None
    max_uses: Optional[int] = None
    use_count: int
    is_active: bool
    is_valid: bool
    created_at: str


class CommentCreateRequest(BaseModel):
    """Request to create a comment."""
    author: str = Field(..., min_length=1, description="Comment author")
    content: str = Field(..., min_length=1, description="Comment text (markdown supported)")
    turn_index: Optional[int] = Field(default=None, description="Turn to attach comment to")
    line_number: Optional[int] = Field(default=None, description="Line within turn")
    comment_type: str = Field(default="comment", description="Type: comment, suggestion, question, issue, praise, note")
    parent_id: Optional[int] = Field(default=None, description="Parent comment ID for replies")


class CommentResponse(BaseModel):
    """Comment response."""
    id: int
    session_id: str
    author: str
    content: str
    turn_index: Optional[int] = None
    line_number: Optional[int] = None
    comment_type: str
    status: str
    parent_id: Optional[int] = None
    is_reply: bool
    is_resolved: bool
    created_at: str
    updated_at: str


class CommentUpdateRequest(BaseModel):
    """Request to update a comment."""
    content: Optional[str] = Field(default=None, description="New content")
    status: Optional[str] = Field(default=None, description="New status: open, resolved, wontfix, outdated")


class ParticipantResponse(BaseModel):
    """Participant in a collaborative session."""
    user_id: str
    display_name: str
    session_id: str
    status: str
    cursor_turn: Optional[int] = None
    cursor_line: Optional[int] = None
    color: Optional[str] = None
    joined_at: str
    is_idle: bool


class JoinSessionRequest(BaseModel):
    """Request to join a session for collaboration."""
    user_id: str = Field(..., min_length=1, description="Unique user identifier")
    display_name: str = Field(..., min_length=1, description="Display name")


class CursorUpdateRequest(BaseModel):
    """Request to update cursor position."""
    turn_index: Optional[int] = Field(default=None, description="Turn being viewed")
    line_number: Optional[int] = Field(default=None, description="Line within turn")


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

        # Collaboration components
        self.share_store: Optional["ShareStore"] = None
        self.comment_store: Optional["CommentStore"] = None
        self.presence_manager: Optional["PresenceManager"] = None

    async def initialize(self):
        """Initialize API components."""
        await self.state.db.initialize()
        self.model_manager = ModelManager(total_vram_gb=self.vram_gb)

        # Initialize collaboration components
        from sindri.collaboration.sharing import ShareStore
        from sindri.collaboration.comments import CommentStore
        from sindri.collaboration.presence import PresenceManager

        self.share_store = ShareStore(self.state.db)
        self.comment_store = CommentStore(self.state.db)
        self.presence_manager = PresenceManager()

        # Start presence cleanup task
        self.presence_manager.start_cleanup_task()

        # Register presence callbacks for WebSocket broadcast
        self.presence_manager.on_join(self._broadcast_presence_join)
        self.presence_manager.on_leave(self._broadcast_presence_leave)
        self.presence_manager.on_update(self._broadcast_presence_update)

        # Clean up stale sessions on startup
        # Any "active" sessions from before server start are clearly not running
        cleaned = await self.state.cleanup_stale_sessions(max_age_hours=0.0)
        if cleaned > 0:
            log.info("startup_cleanup", stale_sessions_marked_failed=cleaned)

        # Subscribe to events for WebSocket broadcast
        for event_type in EventType:
            self.event_bus.subscribe(event_type, self._broadcast_event_sync)

        log.info("sindri_api_initialized", vram_gb=self.vram_gb, collaboration_enabled=True)

    def _broadcast_event_sync(self, data: Any):
        """Synchronous wrapper for event broadcast (called from EventBus)."""
        # Queue for async broadcast
        asyncio.create_task(self._broadcast_event(data))

    async def _broadcast_event(self, data: Any):
        """Broadcast an event to all connected WebSocket clients."""
        if not self.websocket_connections:
            return

        message = {
            "type": "event",
            "data": data if isinstance(data, dict) else str(data),
            "timestamp": time.time()
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

    async def _broadcast_presence_join(self, participant: Any):
        """Broadcast participant join event."""
        await self._broadcast_event({
            "event_type": "presence_join",
            "participant": participant.to_dict(),
        })

    async def _broadcast_presence_leave(self, participant: Any):
        """Broadcast participant leave event."""
        await self._broadcast_event({
            "event_type": "presence_leave",
            "participant": participant.to_dict(),
        })

    async def _broadcast_presence_update(self, participant: Any):
        """Broadcast participant update event."""
        await self._broadcast_event({
            "event_type": "presence_update",
            "participant": participant.to_dict(),
        })

    async def shutdown(self):
        """Clean shutdown of API components."""
        # Stop presence manager cleanup task
        if self.presence_manager:
            self.presence_manager.stop_cleanup_task()

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
        await api.initialize()
        yield
        await api.shutdown()

    app = FastAPI(
        title="Sindri API",
        description="Local LLM Orchestration API - forge code with Ollama",
        version="0.1.0",
        lifespan=lifespan
    )

    # Add CORS middleware for frontend access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store api instance on app for access in routes
    app.state.api = api

    # ===== Health & Info Endpoints =====

    async def _health_check_impl():
        """Health check implementation."""
        from ollama import Client

        # Check Ollama
        ollama_ok = False
        try:
            client = Client()
            client.list()
            ollama_ok = True
        except Exception:
            pass

        # Check database
        db_ok = False
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
            timestamp=datetime.now().isoformat()
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
            agents.append(AgentResponse(
                name=agent.name,
                role=agent.role,
                model=agent.model,
                tools=agent.tools,
                can_delegate=agent.can_delegate,
                delegate_to=agent.delegate_to,
                estimated_vram_gb=agent.estimated_vram_gb,
                max_iterations=agent.max_iterations,
                fallback_model=agent.fallback_model
            ))
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
                fallback_model=agent.fallback_model
            )
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    # ===== Session Endpoints =====

    @app.get("/api/sessions", response_model=list[SessionResponse], tags=["Sessions"])
    async def list_sessions(
        limit: int = Query(default=20, ge=1, le=100, description="Maximum sessions to return"),
        status: Optional[str] = Query(default=None, description="Filter by status (active, completed, failed, cancelled)")
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
                iterations=s["iterations"]
            )
            for s in sessions
        ]

    @app.get("/api/sessions/{session_id}", response_model=SessionDetailResponse, tags=["Sessions"])
    async def get_session_detail(session_id: str):
        """Get detailed session information including turns."""
        # Handle short session IDs
        full_id = session_id
        if len(session_id) < 36:
            sessions = await api.state.list_sessions(limit=100)
            matching = [s for s in sessions if s["id"].startswith(session_id)]
            if not matching:
                raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
            if len(matching) > 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ambiguous session ID '{session_id}', matches: {[m['id'][:8] for m in matching]}"
                )
            full_id = matching[0]["id"]

        session = await api.state.load_session(full_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

        return SessionDetailResponse(
            id=session.id,
            task=session.task,
            model=session.model,
            status=session.status,
            created_at=session.created_at.isoformat(),
            completed_at=session.completed_at.isoformat() if session.completed_at else None,
            iterations=session.iterations,
            turns=[
                {
                    "role": turn.role,
                    "content": turn.content,
                    "tool_calls": turn.tool_calls,
                    "created_at": turn.created_at.isoformat()
                }
                for turn in session.turns
            ]
        )

    @app.get("/api/sessions/{session_id}/file-changes", response_model=FileChangesResponse, tags=["Sessions"])
    async def get_session_file_changes(
        session_id: str,
        include_content: bool = Query(default=True, description="Include file content in response")
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
                raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
            if len(matching) > 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ambiguous session ID '{session_id}', matches: {[m['id'][:8] for m in matching]}"
                )
            full_id = matching[0]["id"]

        session = await api.state.load_session(full_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

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
                        file_changes.append(FileChangeResponse(
                            file_path=file_path,
                            operation="read",
                            turn_index=turn_index,
                            timestamp=turn.created_at.isoformat(),
                            success=True,  # Assume success if in tool_calls
                            read_content=None  # Would need tool result parsing
                        ))

                elif tool_name == "write_file":
                    file_path = args.get("path", "")
                    content = args.get("content", "") if include_content else None
                    if file_path:
                        files_modified.add(file_path)
                        file_changes.append(FileChangeResponse(
                            file_path=file_path,
                            operation="write",
                            turn_index=turn_index,
                            timestamp=turn.created_at.isoformat(),
                            success=True,
                            new_content=content,
                            content_size=len(args.get("content", ""))
                        ))

                elif tool_name == "edit_file":
                    file_path = args.get("path", "")
                    old_text = args.get("old_text", "") if include_content else None
                    new_text = args.get("new_text", "") if include_content else None
                    if file_path:
                        files_modified.add(file_path)
                        file_changes.append(FileChangeResponse(
                            file_path=file_path,
                            operation="edit",
                            turn_index=turn_index,
                            timestamp=turn.created_at.isoformat(),
                            success=True,
                            old_text=old_text,
                            new_text=new_text
                        ))

        return FileChangesResponse(
            session_id=full_id,
            file_changes=file_changes,
            files_modified=sorted(files_modified),
            total_changes=len(file_changes)
        )

    # ===== Task Endpoints =====

    @app.post("/api/tasks", response_model=TaskResponse, tags=["Tasks"])
    async def create_task(request: TaskCreateRequest, background_tasks: BackgroundTasks):
        """Create and start a new task."""
        from sindri.core.orchestrator import Orchestrator
        from sindri.core.loop import LoopConfig

        # Validate agent
        try:
            get_agent(request.agent)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown agent: {request.agent}")

        # Create orchestrator
        config = LoopConfig(max_iterations=request.max_iterations)
        work_path = Path(request.work_dir).resolve() if request.work_dir else api.work_dir

        orchestrator = Orchestrator(
            config=config,
            total_vram_gb=api.vram_gb,
            enable_memory=request.enable_memory,
            work_dir=work_path,
            event_bus=api.event_bus
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
            "error": None
        }

        # Run task in background
        async def run_task():
            try:
                result = await orchestrator.run(request.description)
                api.active_tasks[task_id]["status"] = "completed" if result.get("success") else "failed"
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
            message=f"Task started with agent '{request.agent}'"
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
            subtasks=task.get("subtasks", 0)
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
            tasks.append(TaskStatusResponse(
                task_id=task_id,
                status=task["status"],
                result=task.get("result"),
                error=task.get("error"),
                subtasks=task.get("subtasks", 0)
            ))
        return tasks

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
            loaded_models = list(api.model_manager._loaded_models.keys()) if hasattr(api.model_manager, '_loaded_models') else []

        return MetricsResponse(
            total_sessions=len(sessions),
            completed_sessions=completed,
            failed_sessions=failed,
            active_sessions=active,
            total_iterations=total_iterations,
            vram_used_gb=vram_used,
            vram_total_gb=api.vram_gb,
            loaded_models=loaded_models
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
                raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
            if len(matching) > 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ambiguous session ID '{session_id}'"
                )
            full_id = matching[0]["id"]

        metrics = await store.get_metrics(full_id)
        if not metrics:
            raise HTTPException(status_code=404, detail=f"Metrics not found for session '{session_id}'")

        return metrics.to_dict()

    # ===== Collaboration Endpoints =====

    @app.post("/api/sessions/{session_id}/share", response_model=ShareResponse, tags=["Collaboration"])
    async def create_share(session_id: str, request: ShareCreateRequest):
        """Create a share link for a session.

        Allows sharing a session with others via a unique link.
        Permissions: read (view only), comment (view + add comments), write (full access).
        """
        from sindri.collaboration.sharing import SharePermission

        # Verify session exists
        full_id = await _resolve_session_id(api, session_id)

        # Create share
        try:
            permission = SharePermission(request.permission)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid permission: {request.permission}")

        share = await api.share_store.create_share(
            session_id=full_id,
            permission=permission,
            created_by=request.created_by,
            expires_in_hours=request.expires_in_hours,
            max_uses=request.max_uses,
        )

        return ShareResponse(
            id=share.id,
            session_id=share.session_id,
            share_token=share.share_token,
            share_url=share.get_share_url(),
            permission=share.permission.value,
            expires_at=share.expires_at.isoformat() if share.expires_at else None,
            max_uses=share.max_uses,
            use_count=share.use_count,
            is_active=share.is_active,
            is_valid=share.is_valid,
            created_at=share.created_at.isoformat(),
        )

    @app.get("/api/sessions/{session_id}/shares", response_model=list[ShareResponse], tags=["Collaboration"])
    async def list_shares(session_id: str):
        """List all share links for a session."""
        full_id = await _resolve_session_id(api, session_id)

        shares = await api.share_store.get_shares_for_session(full_id)

        return [
            ShareResponse(
                id=s.id,
                session_id=s.session_id,
                share_token=s.share_token,
                share_url=s.get_share_url(),
                permission=s.permission.value,
                expires_at=s.expires_at.isoformat() if s.expires_at else None,
                max_uses=s.max_uses,
                use_count=s.use_count,
                is_active=s.is_active,
                is_valid=s.is_valid,
                created_at=s.created_at.isoformat(),
            )
            for s in shares
        ]

    @app.get("/api/share/{share_token}", tags=["Collaboration"])
    async def get_shared_session(share_token: str):
        """Access a shared session via share token.

        Returns session details if the share is valid.
        """
        share = await api.share_store.validate_and_use_share(share_token)
        if not share:
            raise HTTPException(status_code=404, detail="Share link not found or expired")

        # Load the session
        session = await api.state.load_session(share.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Shared session not found")

        return {
            "share": share.to_dict(),
            "session": {
                "id": session.id,
                "task": session.task,
                "model": session.model,
                "status": session.status,
                "created_at": session.created_at.isoformat(),
                "completed_at": session.completed_at.isoformat() if session.completed_at else None,
                "iterations": session.iterations,
                "turns": [
                    {
                        "role": t.role,
                        "content": t.content,
                        "tool_calls": t.tool_calls,
                        "created_at": t.created_at.isoformat(),
                    }
                    for t in session.turns
                ],
            },
        }

    @app.delete("/api/shares/{share_id}", tags=["Collaboration"])
    async def revoke_share(share_id: int):
        """Revoke a share link."""
        success = await api.share_store.revoke_share(share_id)
        if not success:
            raise HTTPException(status_code=404, detail="Share not found")
        return {"message": "Share revoked", "share_id": share_id}

    # ===== Comments Endpoints =====

    @app.post("/api/sessions/{session_id}/comments", response_model=CommentResponse, tags=["Collaboration"])
    async def create_comment(session_id: str, request: CommentCreateRequest):
        """Add a review comment to a session."""
        from sindri.collaboration.comments import SessionComment, CommentType

        full_id = await _resolve_session_id(api, session_id)

        try:
            comment_type = CommentType(request.comment_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid comment type: {request.comment_type}")

        comment = SessionComment(
            session_id=full_id,
            author=request.author,
            content=request.content,
            turn_index=request.turn_index,
            line_number=request.line_number,
            comment_type=comment_type,
            parent_id=request.parent_id,
        )

        comment = await api.comment_store.add_comment(comment)

        # Broadcast comment event
        await api._broadcast_event({
            "event_type": "comment_added",
            "comment": comment.to_dict(),
        })

        return CommentResponse(
            id=comment.id,
            session_id=comment.session_id,
            author=comment.author,
            content=comment.content,
            turn_index=comment.turn_index,
            line_number=comment.line_number,
            comment_type=comment.comment_type.value,
            status=comment.status.value,
            parent_id=comment.parent_id,
            is_reply=comment.is_reply,
            is_resolved=comment.is_resolved,
            created_at=comment.created_at.isoformat(),
            updated_at=comment.updated_at.isoformat(),
        )

    @app.get("/api/sessions/{session_id}/comments", response_model=list[CommentResponse], tags=["Collaboration"])
    async def list_comments(
        session_id: str,
        include_resolved: bool = Query(default=True, description="Include resolved comments"),
    ):
        """List all comments for a session."""
        full_id = await _resolve_session_id(api, session_id)

        comments = await api.comment_store.get_comments_for_session(full_id, include_resolved)

        return [
            CommentResponse(
                id=c.id,
                session_id=c.session_id,
                author=c.author,
                content=c.content,
                turn_index=c.turn_index,
                line_number=c.line_number,
                comment_type=c.comment_type.value,
                status=c.status.value,
                parent_id=c.parent_id,
                is_reply=c.is_reply,
                is_resolved=c.is_resolved,
                created_at=c.created_at.isoformat(),
                updated_at=c.updated_at.isoformat(),
            )
            for c in comments
        ]

    @app.put("/api/comments/{comment_id}", response_model=CommentResponse, tags=["Collaboration"])
    async def update_comment(comment_id: int, request: CommentUpdateRequest):
        """Update a comment's content or status."""
        from sindri.collaboration.comments import CommentStatus

        status = None
        if request.status:
            try:
                status = CommentStatus(request.status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {request.status}")

        success = await api.comment_store.update_comment(
            comment_id, content=request.content, status=status
        )

        if not success:
            raise HTTPException(status_code=404, detail="Comment not found")

        comment = await api.comment_store.get_comment(comment_id)

        # Broadcast update
        await api._broadcast_event({
            "event_type": "comment_updated",
            "comment": comment.to_dict(),
        })

        return CommentResponse(
            id=comment.id,
            session_id=comment.session_id,
            author=comment.author,
            content=comment.content,
            turn_index=comment.turn_index,
            line_number=comment.line_number,
            comment_type=comment.comment_type.value,
            status=comment.status.value,
            parent_id=comment.parent_id,
            is_reply=comment.is_reply,
            is_resolved=comment.is_resolved,
            created_at=comment.created_at.isoformat(),
            updated_at=comment.updated_at.isoformat(),
        )

    @app.delete("/api/comments/{comment_id}", tags=["Collaboration"])
    async def delete_comment(comment_id: int):
        """Delete a comment and its replies."""
        success = await api.comment_store.delete_comment(comment_id)
        if not success:
            raise HTTPException(status_code=404, detail="Comment not found")

        # Broadcast deletion
        await api._broadcast_event({
            "event_type": "comment_deleted",
            "comment_id": comment_id,
        })

        return {"message": "Comment deleted", "comment_id": comment_id}

    # ===== Presence Endpoints =====

    @app.post("/api/sessions/{session_id}/join", response_model=ParticipantResponse, tags=["Collaboration"])
    async def join_session(session_id: str, request: JoinSessionRequest):
        """Join a session for real-time collaboration."""
        full_id = await _resolve_session_id(api, session_id)

        participant = await api.presence_manager.join_session(
            session_id=full_id,
            user_id=request.user_id,
            display_name=request.display_name,
        )

        return ParticipantResponse(
            user_id=participant.user_id,
            display_name=participant.display_name,
            session_id=participant.session_id,
            status=participant.status.value,
            cursor_turn=participant.cursor_turn,
            cursor_line=participant.cursor_line,
            color=participant.color,
            joined_at=participant.joined_at.isoformat(),
            is_idle=participant.is_idle,
        )

    @app.post("/api/sessions/{session_id}/leave", tags=["Collaboration"])
    async def leave_session(session_id: str, user_id: str = Query(..., description="User ID")):
        """Leave a collaborative session."""
        participant = await api.presence_manager.leave_session(user_id)
        if not participant:
            raise HTTPException(status_code=404, detail="User not in session")

        return {"message": "Left session", "session_id": session_id}

    @app.get("/api/sessions/{session_id}/participants", response_model=list[ParticipantResponse], tags=["Collaboration"])
    async def list_participants(session_id: str):
        """List all participants in a session."""
        full_id = await _resolve_session_id(api, session_id)

        participants = api.presence_manager.get_session_participants(full_id)

        return [
            ParticipantResponse(
                user_id=p.user_id,
                display_name=p.display_name,
                session_id=p.session_id,
                status=p.status.value,
                cursor_turn=p.cursor_turn,
                cursor_line=p.cursor_line,
                color=p.color,
                joined_at=p.joined_at.isoformat(),
                is_idle=p.is_idle,
            )
            for p in participants
        ]

    @app.put("/api/users/{user_id}/cursor", tags=["Collaboration"])
    async def update_cursor(user_id: str, request: CursorUpdateRequest):
        """Update a participant's cursor position."""
        participant = await api.presence_manager.update_cursor(
            user_id=user_id,
            turn_index=request.turn_index,
            line_number=request.line_number,
        )

        if not participant:
            raise HTTPException(status_code=404, detail="User not in any session")

        return {"message": "Cursor updated"}

    @app.get("/api/collaboration/stats", tags=["Collaboration"])
    async def get_collaboration_stats():
        """Get collaboration statistics."""
        share_stats = await api.share_store.get_share_stats()
        comment_stats = await api.comment_store.get_comment_stats()
        presence_stats = api.presence_manager.get_stats()

        return {
            "shares": share_stats,
            "comments": comment_stats,
            "presence": presence_stats,
        }

    # Helper function for session ID resolution
    async def _resolve_session_id(api_instance: SindriAPI, session_id: str) -> str:
        """Resolve a potentially short session ID to full ID."""
        if len(session_id) >= 36:
            return session_id

        sessions = await api_instance.state.list_sessions(limit=100)
        matching = [s for s in sessions if s["id"].startswith(session_id)]

        if not matching:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
        if len(matching) > 1:
            raise HTTPException(status_code=400, detail=f"Ambiguous session ID '{session_id}'")

        return matching[0]["id"]

    # ===== WebSocket Endpoint =====

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for real-time event streaming."""
        await websocket.accept()
        api.websocket_connections.append(websocket)
        log.info("websocket_connected", total_connections=len(api.websocket_connections))

        try:
            # Send initial state
            await websocket.send_json({
                "type": "connected",
                "data": {
                    "message": "Connected to Sindri API",
                    "version": "0.1.0",
                    "active_connections": len(api.websocket_connections)
                },
                "timestamp": time.time()
            })

            # Keep connection alive and handle incoming messages
            while True:
                try:
                    # Wait for messages (with timeout for heartbeat)
                    data = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=30.0
                    )

                    # Handle ping/pong
                    message = json.loads(data)
                    if message.get("type") == "ping":
                        await websocket.send_json({
                            "type": "pong",
                            "timestamp": time.time()
                        })

                except asyncio.TimeoutError:
                    # Send heartbeat
                    await websocket.send_json({
                        "type": "heartbeat",
                        "timestamp": time.time()
                    })

        except WebSocketDisconnect:
            log.info("websocket_disconnected")
        except Exception as e:
            log.error("websocket_error", error=str(e))
        finally:
            if websocket in api.websocket_connections:
                api.websocket_connections.remove(websocket)
            log.info("websocket_cleanup", remaining_connections=len(api.websocket_connections))

    # ===== Static Files & SPA Support =====

    # Path to static files (React build output)
    static_dir = Path(__file__).parent / "static" / "dist"

    if static_dir.exists():
        # Mount static assets (JS, CSS, images)
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        # Serve index.html for SPA routing (catch-all for non-API routes)
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            """Serve the SPA for all non-API routes."""
            # Don't catch API or WebSocket routes
            if full_path.startswith("api/") or full_path == "ws" or full_path == "health":
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


def run_server(host: str = "0.0.0.0", port: int = 8000, vram_gb: float = 16.0, work_dir: Optional[Path] = None):
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
