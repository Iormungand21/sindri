"""Filesystem tools for Sindri."""

import aiofiles
from pathlib import Path
import structlog
from typing import List
import fnmatch

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


class ReadFileTool(Tool):
    """Read contents of a file."""

    name = "read_file"
    description = "Read the contents of a file at the given path"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read"}
        },
        "required": ["path"],
    }

    async def execute(self, path: str) -> ToolResult:
        """Read file contents."""
        try:
            file_path = self._resolve_path(path)

            if not file_path.exists():
                return ToolResult(
                    success=False, output="", error=f"File not found: {path}"
                )

            async with aiofiles.open(file_path, "r") as f:
                content = await f.read()

            log.info(
                "file_read",
                path=str(file_path),
                size=len(content),
                work_dir=str(self.work_dir) if self.work_dir else None,
            )

            return ToolResult(
                success=True,
                output=content,
                metadata={"path": str(file_path), "size": len(content)},
            )

        except Exception as e:
            log.error("file_read_error", path=path, error=str(e))
            return ToolResult(
                success=False, output="", error=f"Failed to read file: {str(e)}"
            )


class WriteFileTool(Tool):
    """Write content to a file."""

    name = "write_file"
    description = (
        "Write content to a file at the given path, creating it if it doesn't exist"
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to write"},
            "content": {
                "type": "string",
                "description": "Content to write to the file",
            },
        },
        "required": ["path", "content"],
    }

    async def execute(self, path: str, content: str) -> ToolResult:
        """Write content to file."""
        try:
            file_path = self._resolve_path(path)

            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(file_path, "w") as f:
                await f.write(content)

            log.info(
                "file_written",
                path=str(file_path),
                size=len(content),
                work_dir=str(self.work_dir) if self.work_dir else None,
            )

            return ToolResult(
                success=True,
                output=f"Successfully wrote {len(content)} bytes to {path}",
                metadata={"path": str(file_path), "size": len(content)},
            )

        except Exception as e:
            log.error("file_write_error", path=path, error=str(e))
            return ToolResult(
                success=False, output="", error=f"Failed to write file: {str(e)}"
            )


class EditFileTool(Tool):
    """Edit a file by replacing old content with new content."""

    name = "edit_file"
    description = "Edit a file by replacing old_text with new_text"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to edit"},
            "old_text": {
                "type": "string",
                "description": "Text to search for and replace",
            },
            "new_text": {"type": "string", "description": "Text to replace with"},
        },
        "required": ["path", "old_text", "new_text"],
    }

    async def execute(self, path: str, old_text: str, new_text: str) -> ToolResult:
        """Edit file by replacing text."""
        try:
            file_path = self._resolve_path(path)

            if not file_path.exists():
                return ToolResult(
                    success=False, output="", error=f"File not found: {path}"
                )

            # Read current content
            async with aiofiles.open(file_path, "r") as f:
                content = await f.read()

            if old_text not in content:
                return ToolResult(
                    success=False, output="", error="Text to replace not found in file"
                )

            # Replace and write back
            new_content = content.replace(old_text, new_text)

            async with aiofiles.open(file_path, "w") as f:
                await f.write(new_content)

            log.info(
                "file_edited",
                path=str(file_path),
                work_dir=str(self.work_dir) if self.work_dir else None,
            )

            return ToolResult(
                success=True,
                output=f"Successfully edited {path}",
                metadata={"path": str(file_path)},
            )

        except Exception as e:
            log.error("file_edit_error", path=path, error=str(e))
            return ToolResult(
                success=False, output="", error=f"Failed to edit file: {str(e)}"
            )


class ListDirectoryTool(Tool):
    """List files and directories in a path."""

    name = "list_directory"
    description = "List files and directories in a path with optional filtering"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to list (default: current directory)",
            },
            "recursive": {
                "type": "boolean",
                "description": "List recursively (default: false)",
            },
            "pattern": {
                "type": "string",
                "description": "Glob pattern filter (e.g., '*.py', '*.{js,ts}')",
            },
            "ignore_hidden": {
                "type": "boolean",
                "description": "Skip hidden files/directories (default: true)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: str = ".",
        recursive: bool = False,
        pattern: str = None,
        ignore_hidden: bool = True,
    ) -> ToolResult:
        """List directory contents."""
        try:
            dir_path = self._resolve_path(path)

            if not dir_path.exists():
                return ToolResult(
                    success=False, output="", error=f"Directory not found: {path}"
                )

            if not dir_path.is_dir():
                return ToolResult(
                    success=False, output="", error=f"Path is not a directory: {path}"
                )

            # Collect entries
            entries: List[Path] = []

            if recursive:
                # Recursively walk the directory
                for item in dir_path.rglob("*"):
                    if ignore_hidden and any(
                        part.startswith(".")
                        for part in item.relative_to(dir_path).parts
                    ):
                        continue
                    if pattern and not fnmatch.fnmatch(item.name, pattern):
                        continue
                    entries.append(item)
            else:
                # Just list immediate children
                for item in dir_path.iterdir():
                    if ignore_hidden and item.name.startswith("."):
                        continue
                    if pattern and not fnmatch.fnmatch(item.name, pattern):
                        continue
                    entries.append(item)

            # Sort entries: directories first, then files
            entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))

            # Format output
            lines = []
            for entry in entries:
                if recursive:
                    rel_path = entry.relative_to(dir_path)
                    prefix = "📁 " if entry.is_dir() else "📄 "
                    lines.append(f"{prefix}{rel_path}")
                else:
                    prefix = "📁 " if entry.is_dir() else "📄 "
                    size_info = ""
                    if entry.is_file():
                        size = entry.stat().st_size
                        if size < 1024:
                            size_info = f" ({size}B)"
                        elif size < 1024 * 1024:
                            size_info = f" ({size / 1024:.1f}KB)"
                        else:
                            size_info = f" ({size / (1024 * 1024):.1f}MB)"
                    lines.append(f"{prefix}{entry.name}{size_info}")

            output = "\n".join(lines) if lines else "(empty directory)"

            log.info(
                "directory_listed",
                path=str(dir_path),
                count=len(entries),
                recursive=recursive,
                work_dir=str(self.work_dir) if self.work_dir else None,
            )

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "path": str(dir_path),
                    "count": len(entries),
                    "recursive": recursive,
                },
            )

        except Exception as e:
            log.error("directory_list_error", path=path, error=str(e))
            return ToolResult(
                success=False, output="", error=f"Failed to list directory: {str(e)}"
            )


class ReadTreeTool(Tool):
    """Show directory tree structure."""

    name = "read_tree"
    description = "Show directory tree structure with optional depth limit"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Root directory path (default: current directory)",
            },
            "max_depth": {
                "type": "integer",
                "description": "Maximum depth to traverse (default: 3)",
            },
            "ignore_hidden": {
                "type": "boolean",
                "description": "Skip hidden files/directories (default: true)",
            },
        },
        "required": [],
    }

    async def execute(
        self, path: str = ".", max_depth: int = 3, ignore_hidden: bool = True
    ) -> ToolResult:
        """Show directory tree."""
        try:
            root_path = self._resolve_path(path)

            if not root_path.exists():
                return ToolResult(
                    success=False, output="", error=f"Directory not found: {path}"
                )

            if not root_path.is_dir():
                return ToolResult(
                    success=False, output="", error=f"Path is not a directory: {path}"
                )

            # Build tree structure
            lines = [f"📁 {root_path.name}/"]
            total_files = 0
            total_dirs = 1  # Count root

            def _build_tree(dir_path: Path, prefix: str = "", depth: int = 0):
                nonlocal total_files, total_dirs

                if depth >= max_depth:
                    return

                try:
                    # Get and sort entries
                    entries = list(dir_path.iterdir())
                    if ignore_hidden:
                        entries = [e for e in entries if not e.name.startswith(".")]

                    # Sort: directories first, then files, alphabetically
                    entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))

                    for i, entry in enumerate(entries):
                        is_last = i == len(entries) - 1
                        connector = "└── " if is_last else "├── "
                        extension = "    " if is_last else "│   "

                        if entry.is_dir():
                            total_dirs += 1
                            lines.append(f"{prefix}{connector}📁 {entry.name}/")
                            _build_tree(entry, prefix + extension, depth + 1)
                        else:
                            total_files += 1
                            size = entry.stat().st_size
                            if size < 1024:
                                size_str = f"{size}B"
                            elif size < 1024 * 1024:
                                size_str = f"{size / 1024:.1f}KB"
                            else:
                                size_str = f"{size / (1024 * 1024):.1f}MB"
                            lines.append(
                                f"{prefix}{connector}📄 {entry.name} ({size_str})"
                            )

                except PermissionError:
                    lines.append(f"{prefix}└── [Permission Denied]")

            _build_tree(root_path)

            # Add summary
            lines.append("")
            lines.append(f"{total_dirs} directories, {total_files} files")
            if max_depth < 10:  # Only show depth hint if not very deep
                lines.append(f"(max depth: {max_depth})")

            output = "\n".join(lines)

            log.info(
                "tree_generated",
                path=str(root_path),
                dirs=total_dirs,
                files=total_files,
                depth=max_depth,
                work_dir=str(self.work_dir) if self.work_dir else None,
            )

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "path": str(root_path),
                    "directories": total_dirs,
                    "files": total_files,
                    "max_depth": max_depth,
                },
            )

        except Exception as e:
            log.error("tree_read_error", path=path, error=str(e))
            return ToolResult(
                success=False, output="", error=f"Failed to read tree: {str(e)}"
            )
