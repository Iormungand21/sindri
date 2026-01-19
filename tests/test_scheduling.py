"""Tests for scheduling tools (Milestone 6).

Tests cover:
- Cron job management tools
- Systemd timer management tools
- At job management tools
- Access control integration
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from sindri.tools.scheduling import (
    CronListTool,
    CronAddTool,
    CronRemoveTool,
    TimerListTool,
    TimerCreateTool,
    TimerRemoveTool,
    AtScheduleTool,
    AtListTool,
    AtRemoveTool,
    SCHEDULING_TOOLS,
)
from sindri.config import SindriConfig, SystemAccessLevel


class TestCronListTool:
    """Test CronListTool."""

    @pytest.fixture
    def tool(self):
        return CronListTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "cron_list"

    @pytest.mark.asyncio
    async def test_list_success(self, tool):
        """Test successful cron listing."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(
                b"0 * * * * /usr/bin/backup.sh\n",
                b""
            ))
            mock_exec.return_value = mock_proc

            result = await tool.execute()

            assert result.success
            assert "backup" in result.output

    @pytest.mark.asyncio
    async def test_list_empty(self, tool):
        """Test listing when no crontab exists."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.communicate = AsyncMock(return_value=(b"", b"no crontab for user"))
            mock_exec.return_value = mock_proc

            result = await tool.execute()

            assert result.success
            assert "no cron" in result.output.lower()


class TestCronAddTool:
    """Test CronAddTool."""

    @pytest.fixture
    def tool(self):
        return CronAddTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "cron_add"
        assert "schedule" in tool.parameters["properties"]
        assert "command" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_add_requires_access(self, tool):
        """Test add requires appropriate access level."""
        with patch("sindri.tools.scheduling.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.RESTRICTED
            mock_load.return_value = mock_config

            result = await tool.execute(schedule="0 * * * *", command="/usr/bin/test.sh")

            assert not result.success

    @pytest.mark.asyncio
    async def test_add_success(self, tool):
        """Test successful cron job addition."""
        with patch("sindri.tools.scheduling.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_load.return_value = mock_config

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                # First call: get existing crontab
                mock_proc_list = AsyncMock()
                mock_proc_list.returncode = 0
                mock_proc_list.communicate = AsyncMock(return_value=(b"", b""))

                # Second call: install new crontab
                mock_proc_install = AsyncMock()
                mock_proc_install.returncode = 0
                mock_proc_install.communicate = AsyncMock(return_value=(b"", b""))

                mock_exec.side_effect = [mock_proc_list, mock_proc_install]

                with patch("tempfile.NamedTemporaryFile"):
                    with patch("os.unlink"):
                        result = await tool.execute(
                            schedule="0 * * * *",
                            command="/usr/bin/test.sh"
                        )

                        assert result.success

    @pytest.mark.asyncio
    async def test_add_with_comment(self, tool):
        """Test adding cron job with comment."""
        with patch("sindri.tools.scheduling.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_load.return_value = mock_config

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                mock_exec.return_value = mock_proc

                with patch("tempfile.NamedTemporaryFile"):
                    with patch("os.unlink"):
                        result = await tool.execute(
                            schedule="0 2 * * *",
                            command="sindri doctor",
                            comment="Daily health check"
                        )


class TestCronRemoveTool:
    """Test CronRemoveTool."""

    @pytest.fixture
    def tool(self):
        return CronRemoveTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "cron_remove"

    @pytest.mark.asyncio
    async def test_remove_requires_line_or_pattern(self, tool):
        """Test remove requires either line number or pattern."""
        with patch("sindri.tools.scheduling.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_load.return_value = mock_config

            result = await tool.execute()  # No line or pattern

            assert not result.success
            assert "line_number or pattern" in result.error.lower()

    @pytest.mark.asyncio
    async def test_remove_by_line(self, tool):
        """Test removing cron job by line number."""
        with patch("sindri.tools.scheduling.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_load.return_value = mock_config

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                # First call: get existing crontab
                mock_proc_list = AsyncMock()
                mock_proc_list.returncode = 0
                mock_proc_list.communicate = AsyncMock(return_value=(
                    b"0 * * * * /first\n0 2 * * * /second\n",
                    b""
                ))

                # Second call: install updated crontab
                mock_proc_install = AsyncMock()
                mock_proc_install.returncode = 0
                mock_proc_install.communicate = AsyncMock(return_value=(b"", b""))

                mock_exec.side_effect = [mock_proc_list, mock_proc_install]

                with patch("tempfile.NamedTemporaryFile"):
                    with patch("os.unlink"):
                        result = await tool.execute(line_number=1)

                        assert result.success


class TestTimerListTool:
    """Test TimerListTool."""

    @pytest.fixture
    def tool(self):
        return TimerListTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "timer_list"

    @pytest.mark.asyncio
    async def test_list_success(self, tool):
        """Test successful timer listing."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(
                b"NEXT                         LEFT          LAST                         PASSED       UNIT                         ACTIVATES\n"
                b"Sun 2026-01-19 00:00:00 PST  5h left       Sat 2026-01-18 00:00:00 PST  19h ago      logrotate.timer             logrotate.service\n",
                b""
            ))
            mock_exec.return_value = mock_proc

            result = await tool.execute()

            assert result.success
            assert "logrotate" in result.output or "NEXT" in result.output


class TestTimerCreateTool:
    """Test TimerCreateTool."""

    @pytest.fixture
    def tool(self):
        return TimerCreateTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "timer_create"
        assert "name" in tool.parameters["properties"]
        assert "command" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_create_requires_schedule(self, tool):
        """Test create requires either on_calendar or on_boot_sec."""
        with patch("sindri.tools.scheduling.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_load.return_value = mock_config

            result = await tool.execute(name="test", command="echo test")

            assert not result.success
            assert "on_calendar or on_boot_sec" in result.error.lower()

    @pytest.mark.asyncio
    async def test_create_success(self, tool, tmp_path):
        """Test successful timer creation."""
        with patch("sindri.tools.scheduling.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_load.return_value = mock_config

            with patch("pathlib.Path.home") as mock_home:
                mock_home.return_value = tmp_path

                with patch("asyncio.create_subprocess_exec") as mock_exec:
                    mock_proc = AsyncMock()
                    mock_proc.returncode = 0
                    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                    mock_exec.return_value = mock_proc

                    result = await tool.execute(
                        name="test-timer",
                        command="echo hello",
                        on_calendar="daily",
                    )

                    assert result.success
                    assert "test-timer" in result.output


class TestTimerRemoveTool:
    """Test TimerRemoveTool."""

    @pytest.fixture
    def tool(self):
        return TimerRemoveTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "timer_remove"
        assert "name" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_remove_success(self, tool, tmp_path):
        """Test successful timer removal."""
        with patch("sindri.tools.scheduling.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_load.return_value = mock_config

            # Create mock timer files
            user_systemd = tmp_path / ".config" / "systemd" / "user"
            user_systemd.mkdir(parents=True)
            (user_systemd / "test.timer").write_text("[Timer]")
            (user_systemd / "test.service").write_text("[Service]")

            with patch("pathlib.Path.home") as mock_home:
                mock_home.return_value = tmp_path

                with patch("asyncio.create_subprocess_exec") as mock_exec:
                    mock_proc = AsyncMock()
                    mock_proc.returncode = 0
                    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                    mock_exec.return_value = mock_proc

                    result = await tool.execute(name="test")

                    assert result.success

    @pytest.mark.asyncio
    async def test_remove_not_found(self, tool, tmp_path):
        """Test removing nonexistent timer."""
        with patch("sindri.tools.scheduling.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_load.return_value = mock_config

            with patch("pathlib.Path.home") as mock_home:
                mock_home.return_value = tmp_path

                with patch("asyncio.create_subprocess_exec") as mock_exec:
                    mock_proc = AsyncMock()
                    mock_proc.returncode = 0
                    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                    mock_exec.return_value = mock_proc

                    result = await tool.execute(name="nonexistent")

                    assert not result.success


class TestAtScheduleTool:
    """Test AtScheduleTool."""

    @pytest.fixture
    def tool(self):
        return AtScheduleTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "at_schedule"
        assert "time" in tool.parameters["properties"]
        assert "command" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_schedule_success(self, tool):
        """Test successful at job scheduling."""
        with patch("sindri.tools.scheduling.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_load.return_value = mock_config

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(
                    b"",
                    b"job 42 at Sun Jan 19 10:00:00 2026\n"
                ))
                mock_exec.return_value = mock_proc

                result = await tool.execute(time="now + 1 hour", command="echo hello")

                assert result.success
                assert "job" in result.output.lower()


class TestAtListTool:
    """Test AtListTool."""

    @pytest.fixture
    def tool(self):
        return AtListTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "at_list"

    @pytest.mark.asyncio
    async def test_list_success(self, tool):
        """Test successful at job listing."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(
                b"42\tSun Jan 19 10:00:00 2026 a ryan\n",
                b""
            ))
            mock_exec.return_value = mock_proc

            result = await tool.execute()

            assert result.success

    @pytest.mark.asyncio
    async def test_list_empty(self, tool):
        """Test listing when no at jobs exist."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.return_value = mock_proc

            result = await tool.execute()

            assert result.success
            assert "no scheduled" in result.output.lower()


class TestAtRemoveTool:
    """Test AtRemoveTool."""

    @pytest.fixture
    def tool(self):
        return AtRemoveTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "at_remove"
        assert "job_id" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_remove_success(self, tool):
        """Test successful at job removal."""
        with patch("sindri.tools.scheduling.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_load.return_value = mock_config

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                mock_exec.return_value = mock_proc

                result = await tool.execute(job_id=42)

                assert result.success
                assert "42" in result.output


class TestSchedulingToolsCollection:
    """Test the SCHEDULING_TOOLS collection."""

    def test_all_tools_in_collection(self):
        """Test all scheduling tools are in the collection."""
        assert len(SCHEDULING_TOOLS) == 9
        tool_classes = [t.__name__ for t in SCHEDULING_TOOLS]
        assert "CronListTool" in tool_classes
        assert "CronAddTool" in tool_classes
        assert "CronRemoveTool" in tool_classes
        assert "TimerListTool" in tool_classes
        assert "TimerCreateTool" in tool_classes
        assert "TimerRemoveTool" in tool_classes
        assert "AtScheduleTool" in tool_classes
        assert "AtListTool" in tool_classes
        assert "AtRemoveTool" in tool_classes


class TestAccessControlIntegration:
    """Test access control integration with scheduling tools."""

    @pytest.mark.asyncio
    async def test_cron_add_blocked_in_restricted(self):
        """Test cron add blocked in RESTRICTED mode."""
        with patch("sindri.tools.scheduling.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.RESTRICTED
            mock_load.return_value = mock_config

            tool = CronAddTool()
            result = await tool.execute(schedule="0 * * * *", command="test")

            assert not result.success

    @pytest.mark.asyncio
    async def test_timer_create_blocked_in_restricted(self):
        """Test timer create blocked in RESTRICTED mode."""
        with patch("sindri.tools.scheduling.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.RESTRICTED
            mock_load.return_value = mock_config

            tool = TimerCreateTool()
            result = await tool.execute(name="test", command="echo", on_calendar="daily")

            assert not result.success

    @pytest.mark.asyncio
    async def test_at_schedule_blocked_in_restricted(self):
        """Test at schedule blocked in RESTRICTED mode."""
        with patch("sindri.tools.scheduling.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.RESTRICTED
            mock_load.return_value = mock_config

            tool = AtScheduleTool()
            result = await tool.execute(time="now + 1 hour", command="echo")

            assert not result.success

    @pytest.mark.asyncio
    async def test_list_tools_allowed_in_restricted(self):
        """Test list tools work in RESTRICTED mode (read-only)."""
        list_tools = [
            (CronListTool(), {}),
            (TimerListTool(), {}),
            (AtListTool(), {}),
        ]

        for tool, kwargs in list_tools:
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(b"output", b""))
                mock_exec.return_value = mock_proc

                result = await tool.execute(**kwargs)

                # List tools should work regardless of access level
                assert result.success, f"{tool.name} should work in any access mode"
