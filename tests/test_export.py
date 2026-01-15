"""Tests for session export functionality."""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from sindri.persistence.state import Session, Turn
from sindri.persistence.export import MarkdownExporter, generate_export_filename


# Test fixtures

@pytest.fixture
def sample_session():
    """Create a sample session for testing."""
    session = Session(
        id="abc12345-6789-0123-4567-890abcdef123",
        task="Create a hello world function",
        model="qwen2.5-coder:14b",
        status="completed",
        iterations=5,
        created_at=datetime(2026, 1, 15, 10, 30, 0),
        completed_at=datetime(2026, 1, 15, 10, 35, 30)
    )
    return session


@pytest.fixture
def session_with_turns(sample_session):
    """Create a session with conversation turns."""
    sample_session.turns = [
        Turn(
            role="user",
            content="Create a function that says hello",
            created_at=datetime(2026, 1, 15, 10, 30, 0)
        ),
        Turn(
            role="assistant",
            content="I'll create a hello world function for you.",
            tool_calls=[{
                "function": {
                    "name": "write_file",
                    "arguments": {"path": "hello.py", "content": "def hello():\n    print('Hello, World!')"}
                }
            }],
            created_at=datetime(2026, 1, 15, 10, 31, 0)
        ),
        Turn(
            role="tool",
            content="File hello.py written successfully.",
            created_at=datetime(2026, 1, 15, 10, 31, 5)
        ),
        Turn(
            role="assistant",
            content="I've created the hello world function. <sindri:complete/>",
            created_at=datetime(2026, 1, 15, 10, 32, 0)
        ),
    ]
    return sample_session


@pytest.fixture
def empty_session(sample_session):
    """Create a session with no turns."""
    sample_session.turns = []
    return sample_session


@pytest.fixture
def active_session():
    """Create an active (incomplete) session."""
    return Session(
        id="def45678-abcd-efgh-ijkl-mnopqrstuvwx",
        task="A long running task",
        model="qwen2.5-coder:7b",
        status="active",
        iterations=3,
        created_at=datetime(2026, 1, 15, 11, 0, 0),
        completed_at=None
    )


# MarkdownExporter tests

class TestMarkdownExporter:
    """Tests for MarkdownExporter class."""

    def test_init_defaults(self):
        """Test exporter initialization with defaults."""
        exporter = MarkdownExporter()
        assert exporter.include_timestamps is True
        assert exporter.include_metadata is True

    def test_init_custom_options(self):
        """Test exporter initialization with custom options."""
        exporter = MarkdownExporter(include_timestamps=False, include_metadata=False)
        assert exporter.include_timestamps is False
        assert exporter.include_metadata is False

    def test_format_session_with_metadata(self, session_with_turns):
        """Test formatting a session with metadata included."""
        exporter = MarkdownExporter()
        markdown = exporter.format_session(session_with_turns)

        # Check header
        assert "# Sindri Session Export" in markdown

        # Check metadata section
        assert "## Metadata" in markdown
        assert "**Task**: Create a hello world function" in markdown
        assert "**Model**: qwen2.5-coder:14b" in markdown
        assert "**Status**: completed" in markdown
        assert "**Iterations**: 5" in markdown
        assert "**Duration**:" in markdown
        assert "**Session ID**: `abc12345-6789-0123-4567-890abcdef123`" in markdown

    def test_format_session_without_metadata(self, session_with_turns):
        """Test formatting a session without metadata."""
        exporter = MarkdownExporter(include_metadata=False)
        markdown = exporter.format_session(session_with_turns)

        assert "# Sindri Session Export" in markdown
        assert "## Metadata" not in markdown
        assert "**Task**:" not in markdown

    def test_format_session_conversation(self, session_with_turns):
        """Test that conversation turns are included."""
        exporter = MarkdownExporter()
        markdown = exporter.format_session(session_with_turns)

        # Check conversation section
        assert "## Conversation" in markdown
        assert "### Turn 1: User" in markdown
        assert "### Turn 2: Assistant" in markdown
        assert "### Turn 3: Tool Result" in markdown
        assert "### Turn 4: Assistant" in markdown

        # Check content
        assert "Create a function that says hello" in markdown
        assert "I'll create a hello world function for you." in markdown
        assert "File hello.py written successfully." in markdown

    def test_format_session_with_timestamps(self, session_with_turns):
        """Test that timestamps are included when enabled."""
        exporter = MarkdownExporter(include_timestamps=True)
        markdown = exporter.format_session(session_with_turns)

        # Check for timestamps (format: *HH:MM:SS*)
        assert "*10:30:00*" in markdown
        assert "*10:31:00*" in markdown

    def test_format_session_without_timestamps(self, session_with_turns):
        """Test that timestamps are excluded when disabled."""
        exporter = MarkdownExporter(include_timestamps=False)
        markdown = exporter.format_session(session_with_turns)

        # Timestamps should not be present
        assert "*10:30:00*" not in markdown
        assert "*10:31:00*" not in markdown

    def test_format_tool_calls(self, session_with_turns):
        """Test that tool calls are formatted as JSON code blocks."""
        exporter = MarkdownExporter()
        markdown = exporter.format_session(session_with_turns)

        # Check tool calls section
        assert "#### Tool Calls" in markdown
        assert "**1. `write_file`**" in markdown
        assert "```json" in markdown
        assert '"path": "hello.py"' in markdown

    def test_format_empty_session(self, empty_session):
        """Test formatting a session with no turns."""
        exporter = MarkdownExporter()
        markdown = exporter.format_session(empty_session)

        assert "# Sindri Session Export" in markdown
        assert "## Metadata" in markdown
        assert "## Conversation" in markdown
        # No turns should be present
        assert "### Turn 1:" not in markdown

    def test_format_active_session(self, active_session):
        """Test formatting an active session (no completed_at)."""
        exporter = MarkdownExporter()
        markdown = exporter.format_session(active_session)

        assert "**Status**: active" in markdown
        assert "**Completed**:" not in markdown

    def test_calculate_duration_completed(self, sample_session):
        """Test duration calculation for completed session."""
        sample_session.completed_at = sample_session.created_at + timedelta(minutes=5, seconds=30)
        exporter = MarkdownExporter()

        duration = exporter._calculate_duration(sample_session)
        assert duration == "5m 30s"

    def test_calculate_duration_short(self):
        """Test duration calculation for short session (<1 minute)."""
        session = Session(
            id="test",
            task="Test",
            model="test",
            status="completed",
            created_at=datetime(2026, 1, 15, 10, 0, 0),
            completed_at=datetime(2026, 1, 15, 10, 0, 45)
        )
        exporter = MarkdownExporter()
        duration = exporter._calculate_duration(session)
        assert duration == "45s"

    def test_calculate_duration_long(self):
        """Test duration calculation for long session (>1 hour)."""
        session = Session(
            id="test",
            task="Test",
            model="test",
            status="completed",
            created_at=datetime(2026, 1, 15, 10, 0, 0),
            completed_at=datetime(2026, 1, 15, 11, 30, 0)
        )
        exporter = MarkdownExporter()
        duration = exporter._calculate_duration(session)
        assert duration == "1h 30m"

    def test_role_display_names(self):
        """Test that roles get proper display names."""
        exporter = MarkdownExporter()

        assert exporter._get_role_display("user") == "User"
        assert exporter._get_role_display("assistant") == "Assistant"
        assert exporter._get_role_display("tool") == "Tool Result"
        assert exporter._get_role_display("system") == "System"
        assert exporter._get_role_display("unknown") == "Unknown"

    def test_export_to_file(self, session_with_turns, tmp_path):
        """Test exporting to a file."""
        exporter = MarkdownExporter()
        output_path = tmp_path / "export.md"

        result_path = exporter.export_to_file(session_with_turns, output_path)

        assert result_path == output_path
        assert output_path.exists()

        content = output_path.read_text()
        assert "# Sindri Session Export" in content
        assert "Create a hello world function" in content

    def test_export_creates_parent_directories(self, session_with_turns, tmp_path):
        """Test that export creates parent directories if needed."""
        exporter = MarkdownExporter()
        output_path = tmp_path / "subdir" / "nested" / "export.md"

        exporter.export_to_file(session_with_turns, output_path)

        assert output_path.exists()
        assert output_path.parent.exists()

    def test_long_task_truncated(self):
        """Test that very long tasks are truncated in metadata."""
        long_task = "A" * 300  # 300 character task
        session = Session(
            id="test",
            task=long_task,
            model="test",
            status="completed",
            created_at=datetime.now()
        )
        exporter = MarkdownExporter()
        markdown = exporter.format_session(session)

        # Task should be truncated to 200 chars + "..."
        assert long_task not in markdown
        assert "A" * 200 + "..." in markdown

    def test_multiline_content(self):
        """Test that multiline content is handled correctly."""
        session = Session(
            id="test",
            task="Test",
            model="test",
            status="completed",
            created_at=datetime.now(),
            turns=[
                Turn(
                    role="assistant",
                    content="Line 1\nLine 2\nLine 3",
                    created_at=datetime.now()
                )
            ]
        )
        exporter = MarkdownExporter()
        markdown = exporter.format_session(session)

        assert "Line 1\nLine 2\nLine 3" in markdown

    def test_empty_content_turn(self):
        """Test handling turns with empty content."""
        session = Session(
            id="test",
            task="Test",
            model="test",
            status="completed",
            created_at=datetime.now(),
            turns=[
                Turn(
                    role="assistant",
                    content="",
                    tool_calls=[{"function": {"name": "test", "arguments": {}}}],
                    created_at=datetime.now()
                )
            ]
        )
        exporter = MarkdownExporter()
        markdown = exporter.format_session(session)

        # Should still include the turn with tool calls
        assert "#### Tool Calls" in markdown
        assert "`test`" in markdown

    def test_footer_included(self, session_with_turns):
        """Test that export footer is included."""
        exporter = MarkdownExporter()
        markdown = exporter.format_session(session_with_turns)

        assert "---" in markdown
        assert "*Exported from Sindri on" in markdown


class TestGenerateExportFilename:
    """Tests for generate_export_filename function."""

    def test_default_format(self, sample_session):
        """Test default filename generation."""
        filename = generate_export_filename(sample_session)

        assert filename == "sindri_2026-01-15_abc12345.md"

    def test_custom_format(self, sample_session):
        """Test filename generation with custom format."""
        filename = generate_export_filename(sample_session, format="txt")

        assert filename == "sindri_2026-01-15_abc12345.txt"

    def test_different_sessions_different_filenames(self):
        """Test that different sessions generate different filenames."""
        session1 = Session(
            id="aaa11111-0000-0000-0000-000000000000",
            task="Task 1",
            model="test",
            status="completed",
            created_at=datetime(2026, 1, 15, 10, 0, 0)
        )
        session2 = Session(
            id="bbb22222-0000-0000-0000-000000000000",
            task="Task 2",
            model="test",
            status="completed",
            created_at=datetime(2026, 1, 16, 10, 0, 0)
        )

        filename1 = generate_export_filename(session1)
        filename2 = generate_export_filename(session2)

        assert filename1 != filename2
        assert "aaa11111" in filename1
        assert "bbb22222" in filename2


class TestExportCLI:
    """Tests for CLI export command.

    Note: These tests use synchronous mocking because the CLI command
    uses asyncio.run() internally, which conflicts with pytest-asyncio.
    """

    def test_export_help(self):
        """Test export command help."""
        from click.testing import CliRunner
        from sindri.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ['export', '--help'])

        assert result.exit_code == 0
        assert "Export a session to Markdown" in result.output
        assert "SESSION_ID" in result.output

    def test_export_requires_session_id(self):
        """Test that export command requires session ID."""
        from click.testing import CliRunner
        from sindri.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ['export'])

        assert result.exit_code != 0
        assert "Missing argument" in result.output

    def test_export_options(self):
        """Test that export command has correct options."""
        from click.testing import CliRunner
        from sindri.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ['export', '--help'])

        assert "--no-metadata" in result.output
        assert "--no-timestamps" in result.output


class TestExportIntegration:
    """Integration tests for export functionality."""

    def test_full_export_workflow(self, session_with_turns, tmp_path):
        """Test complete export workflow."""
        exporter = MarkdownExporter()
        output_path = tmp_path / "full_export.md"

        # Export
        exporter.export_to_file(session_with_turns, output_path)

        # Read and verify
        content = output_path.read_text()

        # Verify structure
        assert content.startswith("# Sindri Session Export")
        assert "## Metadata" in content
        assert "## Conversation" in content

        # Verify metadata
        assert "abc12345-6789-0123-4567-890abcdef123" in content
        assert "qwen2.5-coder:14b" in content

        # Verify turns
        assert "User" in content
        assert "Assistant" in content
        assert "Tool Result" in content

        # Verify tool calls
        assert "write_file" in content
        assert "hello.py" in content

        # Verify footer
        assert "Exported from Sindri" in content

    def test_export_preserves_special_characters(self, tmp_path):
        """Test that special characters in content are preserved."""
        session = Session(
            id="test",
            task="Test with `code` and *emphasis*",
            model="test",
            status="completed",
            created_at=datetime.now(),
            turns=[
                Turn(
                    role="assistant",
                    content="Here's code:\n```python\ndef foo():\n    pass\n```",
                    created_at=datetime.now()
                )
            ]
        )

        exporter = MarkdownExporter()
        output_path = tmp_path / "special_chars.md"
        exporter.export_to_file(session, output_path)

        content = output_path.read_text()

        # Special characters should be preserved
        assert "`code`" in content
        assert "*emphasis*" in content
        assert "```python" in content
        assert "def foo():" in content
