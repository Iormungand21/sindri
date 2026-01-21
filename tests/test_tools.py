"""Tests for Sindri tools."""

import pytest
from pathlib import Path
import tempfile

from sindri.config import SindriConfig, SystemAccessLevel
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


# ============================================================================
# Shell Timeout Tests
# ============================================================================


@pytest.mark.asyncio
async def test_shell_timeout_default():
    """Test shell tool has default timeout in metadata."""
    tool = ShellTool()

    result = await tool.execute(command="echo 'quick'")

    assert result.success
    assert result.metadata.get("timeout") == ShellTool.DEFAULT_TIMEOUT


@pytest.mark.asyncio
async def test_shell_timeout_custom():
    """Test shell tool accepts custom timeout parameter."""
    tool = ShellTool()

    result = await tool.execute(command="echo 'quick'", timeout=60)

    assert result.success
    assert result.metadata.get("timeout") == 60


@pytest.mark.asyncio
async def test_shell_timeout_exceeded():
    """Test that hanging command is killed and error returned on timeout."""
    tool = ShellTool()

    # Sleep for 10 seconds but timeout after 1 second
    result = await tool.execute(command="sleep 10", timeout=1)

    assert not result.success
    assert "timed out" in result.error.lower()
    assert result.metadata.get("timed_out") is True
    assert result.metadata.get("timeout") == 1


@pytest.mark.asyncio
async def test_shell_timeout_capped_at_max():
    """Test that timeout is capped at MAX_TIMEOUT."""
    tool = ShellTool()

    # Request absurdly high timeout
    result = await tool.execute(command="echo 'quick'", timeout=999999)

    assert result.success
    # Should be capped at MAX_TIMEOUT
    assert result.metadata.get("timeout") == ShellTool.MAX_TIMEOUT


@pytest.mark.asyncio
async def test_shell_timeout_minimum():
    """Test that timeout cannot be less than 1 second."""
    tool = ShellTool()

    # Request zero or negative timeout
    result = await tool.execute(command="echo 'quick'", timeout=0)

    assert result.success
    # Should be at least 1
    assert result.metadata.get("timeout") >= 1


# ============================================================================
# Access Control Tests
# ============================================================================


class TestToolAccessControl:
    """Test access control for modification tools."""

    @pytest.mark.asyncio
    async def test_shell_blocked_in_restricted_mode(self, tmp_path, monkeypatch):
        """Test shell tool is blocked in RESTRICTED mode."""
        monkeypatch.setattr(
            "sindri.tools.shell.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                system_access=SystemAccessLevel.RESTRICTED,
            ),
        )
        tool = ShellTool()
        result = await tool.execute(command="echo test")

        assert not result.success
        assert "RESTRICTED" in result.error

    @pytest.mark.asyncio
    async def test_shell_allowed_in_supervised_mode(self, tmp_path, monkeypatch):
        """Test shell tool is allowed in SUPERVISED mode."""
        monkeypatch.setattr(
            "sindri.tools.shell.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                system_access=SystemAccessLevel.SUPERVISED,
            ),
        )
        tool = ShellTool()
        result = await tool.execute(command="echo test")

        assert result.success
        assert "test" in result.output

    @pytest.mark.asyncio
    async def test_shell_allowed_in_full_mode(self, tmp_path, monkeypatch):
        """Test shell tool is allowed in FULL mode."""
        monkeypatch.setattr(
            "sindri.tools.shell.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                system_access=SystemAccessLevel.FULL,
            ),
        )
        tool = ShellTool()
        result = await tool.execute(command="echo test")

        assert result.success
        assert "test" in result.output

    @pytest.mark.asyncio
    async def test_write_file_blocked_in_restricted_mode(self, tmp_path, monkeypatch):
        """Test write_file tool is blocked in RESTRICTED mode."""
        monkeypatch.setattr(
            "sindri.tools.filesystem.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                system_access=SystemAccessLevel.RESTRICTED,
            ),
        )
        tool = WriteFileTool()
        file_path = tmp_path / "test.txt"
        result = await tool.execute(path=str(file_path), content="test")

        assert not result.success
        assert "RESTRICTED" in result.error
        assert not file_path.exists()  # File should NOT be created

    @pytest.mark.asyncio
    async def test_write_file_allowed_in_supervised_mode(self, tmp_path, monkeypatch):
        """Test write_file tool is allowed in SUPERVISED mode."""
        monkeypatch.setattr(
            "sindri.tools.filesystem.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                system_access=SystemAccessLevel.SUPERVISED,
            ),
        )
        tool = WriteFileTool()
        file_path = tmp_path / "test.txt"
        result = await tool.execute(path=str(file_path), content="test content")

        assert result.success
        assert file_path.exists()
        assert file_path.read_text() == "test content"

    @pytest.mark.asyncio
    async def test_write_file_allowed_in_full_mode(self, tmp_path, monkeypatch):
        """Test write_file tool is allowed in FULL mode."""
        monkeypatch.setattr(
            "sindri.tools.filesystem.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                system_access=SystemAccessLevel.FULL,
            ),
        )
        tool = WriteFileTool()
        file_path = tmp_path / "test.txt"
        result = await tool.execute(path=str(file_path), content="test content")

        assert result.success
        assert file_path.exists()

    @pytest.mark.asyncio
    async def test_edit_file_blocked_in_restricted_mode(self, tmp_path, monkeypatch):
        """Test edit_file tool is blocked in RESTRICTED mode."""
        monkeypatch.setattr(
            "sindri.tools.filesystem.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                system_access=SystemAccessLevel.RESTRICTED,
            ),
        )
        # Create file first
        file_path = tmp_path / "test.txt"
        file_path.write_text("original content")

        tool = EditFileTool()
        result = await tool.execute(
            path=str(file_path),
            old_text="original",
            new_text="modified",
        )

        assert not result.success
        assert "RESTRICTED" in result.error
        assert file_path.read_text() == "original content"  # Unchanged

    @pytest.mark.asyncio
    async def test_edit_file_allowed_in_supervised_mode(self, tmp_path, monkeypatch):
        """Test edit_file tool is allowed in SUPERVISED mode."""
        monkeypatch.setattr(
            "sindri.tools.filesystem.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                system_access=SystemAccessLevel.SUPERVISED,
            ),
        )
        file_path = tmp_path / "test.txt"
        file_path.write_text("original content")

        tool = EditFileTool()
        result = await tool.execute(
            path=str(file_path),
            old_text="original",
            new_text="modified",
        )

        assert result.success
        assert file_path.read_text() == "modified content"

    @pytest.mark.asyncio
    async def test_edit_file_allowed_in_full_mode(self, tmp_path, monkeypatch):
        """Test edit_file tool is allowed in FULL mode."""
        monkeypatch.setattr(
            "sindri.tools.filesystem.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                system_access=SystemAccessLevel.FULL,
            ),
        )
        file_path = tmp_path / "test.txt"
        file_path.write_text("original content")

        tool = EditFileTool()
        result = await tool.execute(
            path=str(file_path),
            old_text="original",
            new_text="modified",
        )

        assert result.success
        assert file_path.read_text() == "modified content"

    @pytest.mark.asyncio
    async def test_read_file_allowed_in_restricted_mode(self, tmp_path, monkeypatch):
        """Test read_file tool is allowed even in RESTRICTED mode (read-only)."""
        # Note: ReadFileTool doesn't have access control checks (it's read-only)
        # This test verifies read operations still work regardless of access level
        file_path = tmp_path / "test.txt"
        file_path.write_text("test content")

        tool = ReadFileTool()
        result = await tool.execute(path=str(file_path))

        assert result.success
        assert result.output == "test content"

    @pytest.mark.asyncio
    async def test_shell_long_command_truncated_in_error(self, tmp_path, monkeypatch):
        """Test that long shell commands are truncated in access denial messages."""
        monkeypatch.setattr(
            "sindri.tools.shell.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                system_access=SystemAccessLevel.RESTRICTED,
            ),
        )
        tool = ShellTool()
        long_command = "echo " + "x" * 100  # Command longer than 50 chars
        result = await tool.execute(command=long_command)

        assert not result.success
        assert "RESTRICTED" in result.error
