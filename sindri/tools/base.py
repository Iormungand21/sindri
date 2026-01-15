"""Tool base class and result types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class ToolResult:
    success: bool
    output: str
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class Tool(ABC):
    """Base class for all tools."""

    name: str
    description: str
    parameters: dict  # JSON Schema

    def __init__(self, work_dir: Optional[Path] = None):
        """Initialize tool with optional working directory.

        Args:
            work_dir: Working directory for file operations. None = current directory.
        """
        self.work_dir = work_dir

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool."""
        pass

    def get_schema(self) -> dict:
        """Get Ollama-compatible tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }

    def _resolve_path(self, path: str) -> Path:
        """Resolve a path relative to work_dir if set and path is relative.

        Args:
            path: Path string to resolve

        Returns:
            Resolved Path object
        """
        file_path = Path(path).expanduser()

        # If path is absolute, use it as-is
        if file_path.is_absolute():
            return file_path.resolve()

        # If work_dir is set, resolve relative to it
        if self.work_dir:
            return (self.work_dir / file_path).resolve()

        # Otherwise, resolve relative to current directory
        return file_path.resolve()
