"""Tests for Sindri tools."""

import pytest
from pathlib import Path
import tempfile

from sindri.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool
from sindri.tools.shell import ShellTool


@pytest.mark.asyncio
async def test_write_file():
    """Test writing a file."""
    tool = WriteFileTool()

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.txt"

        result = await tool.execute(path=str(file_path), content="Hello, world!")

        assert result.success
        assert file_path.exists()
        assert file_path.read_text() == "Hello, world!"


@pytest.mark.asyncio
async def test_read_file():
    """Test reading a file."""
    tool = ReadFileTool()

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.txt"
        file_path.write_text("Hello from test")

        result = await tool.execute(path=str(file_path))

        assert result.success
        assert result.output == "Hello from test"


@pytest.mark.asyncio
async def test_edit_file():
    """Test editing a file."""
    tool = EditFileTool()

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.txt"
        file_path.write_text("Hello, world!")

        result = await tool.execute(
            path=str(file_path), old_text="world", new_text="Sindri"
        )

        assert result.success
        assert file_path.read_text() == "Hello, Sindri!"


@pytest.mark.asyncio
async def test_shell():
    """Test shell execution."""
    tool = ShellTool()

    result = await tool.execute(command="echo 'test output'")

    assert result.success
    assert "test output" in result.output


@pytest.mark.asyncio
async def test_shell_failure():
    """Test shell execution with failing command."""
    tool = ShellTool()

    result = await tool.execute(command="exit 1")

    assert not result.success
    assert result.metadata["returncode"] == 1
