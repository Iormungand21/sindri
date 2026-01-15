"""Sindri Web API module.

Phase 8.3: FastAPI-based Web API server for Sindri.

Provides:
- REST API endpoints for agents, sessions, tasks, metrics
- WebSocket support for real-time event streaming
- Integration with existing EventBus system

Usage:
    from sindri.web import create_app
    app = create_app()

    # Or run via CLI:
    sindri web --port 8000
"""

from sindri.web.server import create_app, SindriAPI

__all__ = ["create_app", "SindriAPI"]
