"""Filesystem tools for Sindri."""

import aiofiles
from pathlib import Path
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


class ReadFileTool(Tool):
    """Read contents of a file."""

    name = "read_file"
    description = "Read the contents of a file at the given path"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to read"
            }
        },
        "required": ["path"]
    }

    async def execute(self, path: str) -> ToolResult:
        """Read file contents."""
        try:
            file_path = self._resolve_path(path)

            if not file_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File not found: {path}"
                )

            async with aiofiles.open(file_path, "r") as f:
                content = await f.read()

            log.info("file_read", path=str(file_path), size=len(content), work_dir=str(self.work_dir) if self.work_dir else None)

            return ToolResult(
                success=True,
                output=content,
                metadata={"path": str(file_path), "size": len(content)}
            )

        except Exception as e:
            log.error("file_read_error", path=path, error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to read file: {str(e)}"
            )


class WriteFileTool(Tool):
    """Write content to a file."""

    name = "write_file"
    description = "Write content to a file at the given path, creating it if it doesn't exist"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to write"
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file"
            }
        },
        "required": ["path", "content"]
    }

    async def execute(self, path: str, content: str) -> ToolResult:
        """Write content to file."""
        try:
            file_path = self._resolve_path(path)

            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(file_path, "w") as f:
                await f.write(content)

            log.info("file_written", path=str(file_path), size=len(content), work_dir=str(self.work_dir) if self.work_dir else None)

            return ToolResult(
                success=True,
                output=f"Successfully wrote {len(content)} bytes to {path}",
                metadata={"path": str(file_path), "size": len(content)}
            )

        except Exception as e:
            log.error("file_write_error", path=path, error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to write file: {str(e)}"
            )


class EditFileTool(Tool):
    """Edit a file by replacing old content with new content."""

    name = "edit_file"
    description = "Edit a file by replacing old_text with new_text"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to edit"
            },
            "old_text": {
                "type": "string",
                "description": "Text to search for and replace"
            },
            "new_text": {
                "type": "string",
                "description": "Text to replace with"
            }
        },
        "required": ["path", "old_text", "new_text"]
    }

    async def execute(self, path: str, old_text: str, new_text: str) -> ToolResult:
        """Edit file by replacing text."""
        try:
            file_path = self._resolve_path(path)

            if not file_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File not found: {path}"
                )

            # Read current content
            async with aiofiles.open(file_path, "r") as f:
                content = await f.read()

            if old_text not in content:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Text to replace not found in file"
                )

            # Replace and write back
            new_content = content.replace(old_text, new_text)

            async with aiofiles.open(file_path, "w") as f:
                await f.write(new_content)

            log.info("file_edited", path=str(file_path), work_dir=str(self.work_dir) if self.work_dir else None)

            return ToolResult(
                success=True,
                output=f"Successfully edited {path}",
                metadata={"path": str(file_path)}
            )

        except Exception as e:
            log.error("file_edit_error", path=path, error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to edit file: {str(e)}"
            )
