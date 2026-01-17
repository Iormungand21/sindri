"""Sindri IDE Integration.

Provides JSON-RPC server and protocol for IDE plugins (Neovim, VS Code, etc.).

Features:
- LSP-style JSON-RPC communication over stdio
- Task execution from editor context
- Code completion and suggestions
- File context integration
- Real-time streaming responses

Usage:
    sindri ide --mode stdio  # Start IDE server in stdio mode
    sindri ide --mode http   # Start IDE server in HTTP mode
"""

from sindri.ide.protocol import (
    IDERequest,
    IDEResponse,
    IDENotification,
    IDECapabilities,
)
from sindri.ide.server import IDEServer

__all__ = [
    "IDERequest",
    "IDEResponse",
    "IDENotification",
    "IDECapabilities",
    "IDEServer",
]
