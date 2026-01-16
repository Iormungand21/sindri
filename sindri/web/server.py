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


class WebSocketMessage(BaseModel):
    """WebSocket message format."""
    type: str
    data: dict[str, Any]
    timestamp: float


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

    async def initialize(self):
        """Initialize API components."""
        await self.state.db.initialize()
        self.model_manager = ModelManager(total_vram_gb=self.vram_gb)

        # Clean up stale sessions on startup
        # Any "active" sessions from before server start are clearly not running
        cleaned = await self.state.cleanup_stale_sessions(max_age_hours=0.0)
        if cleaned > 0:
            log.info("startup_cleanup", stale_sessions_marked_failed=cleaned)

        # Subscribe to events for WebSocket broadcast
        for event_type in EventType:
            self.event_bus.subscribe(event_type, self._broadcast_event_sync)

        log.info("sindri_api_initialized", vram_gb=self.vram_gb)

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
