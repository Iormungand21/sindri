"""Session export functionality for Sindri.

This module provides utilities for exporting Sindri sessions to various
formats, primarily Markdown for documentation, debugging, and sharing.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import structlog

from sindri.persistence.state import Session, Turn

log = structlog.get_logger()


class MarkdownExporter:
    """Exports Sindri sessions to Markdown format.

    Generates well-formatted Markdown documents that include:
    - Session metadata (task, model, duration, status)
    - Full conversation history with agent/user/tool turns
    - Tool calls formatted as JSON code blocks
    - Timestamps for each turn

    Example usage:
        exporter = MarkdownExporter()
        markdown = exporter.format_session(session)
        exporter.export_to_file(session, Path("output.md"))
    """

    def __init__(self, include_timestamps: bool = True, include_metadata: bool = True):
        """Initialize the exporter.

        Args:
            include_timestamps: Include timestamps for each turn
            include_metadata: Include session metadata section
        """
        self.include_timestamps = include_timestamps
        self.include_metadata = include_metadata

    def format_session(self, session: Session) -> str:
        """Format a session as Markdown.

        Args:
            session: The session to format

        Returns:
            Formatted Markdown string
        """
        lines = []

        # Title
        lines.append("# Sindri Session Export")
        lines.append("")

        # Metadata section
        if self.include_metadata:
            lines.extend(self._format_metadata(session))

        # Conversation section
        lines.append("## Conversation")
        lines.append("")

        for i, turn in enumerate(session.turns, 1):
            lines.extend(self._format_turn(turn, i))

        # Footer
        lines.append("---")
        lines.append("")
        lines.append(f"*Exported from Sindri on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("")

        return "\n".join(lines)

    def _format_metadata(self, session: Session) -> list[str]:
        """Format the metadata section."""
        lines = []
        lines.append("## Metadata")
        lines.append("")

        # Task description (truncate if very long)
        task = session.task
        if len(task) > 200:
            task = task[:200] + "..."
        lines.append(f"- **Task**: {task}")
        lines.append(f"- **Model**: {session.model}")
        lines.append(f"- **Status**: {session.status}")
        lines.append(f"- **Iterations**: {session.iterations}")

        # Duration
        duration = self._calculate_duration(session)
        if duration:
            lines.append(f"- **Duration**: {duration}")

        # Timestamps
        lines.append(f"- **Created**: {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if session.completed_at:
            lines.append(f"- **Completed**: {session.completed_at.strftime('%Y-%m-%d %H:%M:%S')}")

        # Session ID (useful for debugging/resuming)
        lines.append(f"- **Session ID**: `{session.id}`")
        lines.append("")

        return lines

    def _format_turn(self, turn: Turn, turn_number: int) -> list[str]:
        """Format a single conversation turn."""
        lines = []

        # Turn header with role
        role_display = self._get_role_display(turn.role)
        lines.append(f"### Turn {turn_number}: {role_display}")

        # Timestamp
        if self.include_timestamps:
            lines.append(f"*{turn.created_at.strftime('%H:%M:%S')}*")

        lines.append("")

        # Content
        if turn.content:
            # Handle multi-line content properly
            content = turn.content.strip()
            if content:
                lines.append(content)
                lines.append("")

        # Tool calls
        if turn.tool_calls:
            lines.extend(self._format_tool_calls(turn.tool_calls))

        return lines

    def _format_tool_calls(self, tool_calls: list) -> list[str]:
        """Format tool calls as a subsection with JSON code blocks."""
        lines = []
        lines.append("#### Tool Calls")
        lines.append("")

        for i, call in enumerate(tool_calls, 1):
            if isinstance(call, dict):
                # Extract function info
                func = call.get('function', call)
                name = func.get('name', 'unknown')
                args = func.get('arguments', {})

                lines.append(f"**{i}. `{name}`**")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(args, indent=2, default=str))
                lines.append("```")
                lines.append("")
            else:
                # Fallback for unexpected format
                lines.append(f"**{i}.**")
                lines.append("")
                lines.append("```")
                lines.append(str(call))
                lines.append("```")
                lines.append("")

        return lines

    def _get_role_display(self, role: str) -> str:
        """Get a human-readable display name for a role."""
        role_map = {
            "user": "User",
            "assistant": "Assistant",
            "tool": "Tool Result",
            "system": "System",
        }
        return role_map.get(role.lower(), role.capitalize())

    def _calculate_duration(self, session: Session) -> Optional[str]:
        """Calculate and format the session duration."""
        if not session.completed_at:
            # For active sessions, calculate from now
            if session.status == "active":
                delta = datetime.now() - session.created_at
            else:
                return None
        else:
            delta = session.completed_at - session.created_at

        total_seconds = int(delta.total_seconds())

        if total_seconds < 60:
            return f"{total_seconds}s"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            return f"{minutes}m {seconds}s"
        else:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}h {minutes}m"

    def export_to_file(self, session: Session, path: Path) -> Path:
        """Export a session to a Markdown file.

        Args:
            session: The session to export
            path: Output file path

        Returns:
            The path to the exported file
        """
        content = self.format_session(session)

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        path.write_text(content, encoding="utf-8")

        log.info(
            "session_exported",
            session_id=session.id,
            path=str(path),
            turns=len(session.turns)
        )

        return path


def generate_export_filename(session: Session, format: str = "md") -> str:
    """Generate a filename for an exported session.

    Args:
        session: The session to generate a filename for
        format: File extension (default: md)

    Returns:
        A filename like "sindri_2026-01-15_abc12345.md"
    """
    date_str = session.created_at.strftime("%Y-%m-%d")
    short_id = session.id[:8]
    return f"sindri_{date_str}_{short_id}.{format}"
