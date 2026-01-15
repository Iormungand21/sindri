"""Tool registry for Sindri."""

import json
from pathlib import Path
from typing import Optional
import structlog

from sindri.tools.base import Tool, ToolResult
from sindri.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool
from sindri.tools.shell import ShellTool

log = structlog.get_logger()


class ToolRegistry:
    """Manages available tools."""

    def __init__(self, work_dir: Optional[Path] = None):
        """Initialize registry with optional working directory.

        Args:
            work_dir: Working directory for file operations. None = current directory.
        """
        self._tools: dict[str, Tool] = {}
        self.work_dir = work_dir

    def register(self, tool: Tool):
        """Register a tool."""
        self._tools[tool.name] = tool
        log.info("tool_registered", name=tool.name, work_dir=str(self.work_dir) if self.work_dir else None)

    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_schemas(self) -> list[dict]:
        """Get all tool schemas for Ollama."""
        return [tool.get_schema() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict | str) -> ToolResult:
        """Execute a tool by name."""

        tool = self.get_tool(name)
        if not tool:
            log.error("tool_not_found", name=name)
            return ToolResult(
                success=False,
                output="",
                error=f"Tool not found: {name}"
            )

        # Parse arguments if they're a JSON string
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as e:
                log.error("tool_args_parse_error", name=name, error=str(e))
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to parse tool arguments: {str(e)}"
                )

        log.info("tool_execute", name=name, args=arguments)

        try:
            result = await tool.execute(**arguments)
            return result
        except Exception as e:
            log.error("tool_execution_error", name=name, error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Tool execution failed: {str(e)}"
            )

    @classmethod
    def default(cls, work_dir: Optional[Path] = None) -> "ToolRegistry":
        """Create a registry with default tools.

        Args:
            work_dir: Working directory for file operations. None = current directory.

        Returns:
            ToolRegistry with default filesystem and shell tools registered.
        """
        registry = cls(work_dir=work_dir)
        registry.register(ReadFileTool(work_dir=work_dir))
        registry.register(WriteFileTool(work_dir=work_dir))
        registry.register(EditFileTool(work_dir=work_dir))
        registry.register(ShellTool(work_dir=work_dir))
        return registry
