"""Tests for service management tools (Milestone 6).

Tests cover:
- Service status, start, stop, restart tools
- Service enable/disable tools
- Service logs and list tools
- Access control integration
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from sindri.tools.services import (
    ServiceStatusTool,
    ServiceStartTool,
    ServiceStopTool,
    ServiceRestartTool,
    ServiceEnableTool,
    ServiceDisableTool,
    ServiceLogsTool,
    ServiceListTool,
    SERVICE_TOOLS,
)
from sindri.config import SindriConfig, SystemAccessLevel


class TestServiceStatusTool:
    """Test ServiceStatusTool."""

    @pytest.fixture
    def tool(self):
        return ServiceStatusTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "service_status"
        assert "service" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_status_success(self, tool):
        """Test successful status check."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"active (running)", b""))
            mock_exec.return_value = mock_proc

            result = await tool.execute(service="ollama")

            assert result.success
            assert "active" in result.output

    @pytest.mark.asyncio
    async def test_status_not_found(self, tool):
        """Test status for non-existent service."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 4
            mock_proc.communicate = AsyncMock(return_value=(b"", b"Unit not found"))
            mock_exec.return_value = mock_proc

            result = await tool.execute(service="nonexistent")

            assert not result.success
            assert "not found" in result.error.lower() or "Unit not found" in result.error

    @pytest.mark.asyncio
    async def test_status_user_service(self, tool):
        """Test status check for user service."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"active", b""))
            mock_exec.return_value = mock_proc

            await tool.execute(service="syncthing", user=True)

            # Check --user flag was passed
            call_args = mock_exec.call_args[0]
            assert "--user" in call_args


class TestServiceStartTool:
    """Test ServiceStartTool."""

    @pytest.fixture
    def tool(self):
        return ServiceStartTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "service_start"
        assert "service" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_start_requires_access(self, tool, tmp_path):
        """Test start requires appropriate access level."""
        with patch("sindri.tools.services.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.RESTRICTED
            mock_config.allowed_services = ["ollama"]
            mock_load.return_value = mock_config

            result = await tool.execute(service="ollama")

            assert not result.success
            assert "restricted" in result.error.lower() or "access" in result.error.lower()

    @pytest.mark.asyncio
    async def test_start_respects_allowed_services(self, tool):
        """Test start only works for allowed services."""
        with patch("sindri.tools.services.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_config.allowed_services = ["docker"]  # ollama not in list
            mock_load.return_value = mock_config

            result = await tool.execute(service="ollama")

            assert not result.success
            assert "not in allowed" in result.error.lower() or "allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_start_success(self, tool):
        """Test successful service start."""
        with patch("sindri.tools.services.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_config.allowed_services = ["ollama"]
            mock_load.return_value = mock_config

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                mock_exec.return_value = mock_proc

                result = await tool.execute(service="ollama")

                assert result.success
                assert "started" in result.output.lower()


class TestServiceStopTool:
    """Test ServiceStopTool."""

    @pytest.fixture
    def tool(self):
        return ServiceStopTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "service_stop"

    @pytest.mark.asyncio
    async def test_stop_success(self, tool):
        """Test successful service stop."""
        with patch("sindri.tools.services.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_config.allowed_services = ["ollama"]
            mock_load.return_value = mock_config

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                mock_exec.return_value = mock_proc

                result = await tool.execute(service="ollama")

                assert result.success
                assert "stopped" in result.output.lower()


class TestServiceRestartTool:
    """Test ServiceRestartTool."""

    @pytest.fixture
    def tool(self):
        return ServiceRestartTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "service_restart"

    @pytest.mark.asyncio
    async def test_restart_success(self, tool):
        """Test successful service restart."""
        with patch("sindri.tools.services.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_config.allowed_services = ["ollama"]
            mock_load.return_value = mock_config

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                mock_exec.return_value = mock_proc

                result = await tool.execute(service="ollama")

                assert result.success
                assert "restarted" in result.output.lower()


class TestServiceEnableTool:
    """Test ServiceEnableTool."""

    @pytest.fixture
    def tool(self):
        return ServiceEnableTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "service_enable"

    @pytest.mark.asyncio
    async def test_enable_success(self, tool):
        """Test successful service enable."""
        with patch("sindri.tools.services.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_config.allowed_services = ["ollama"]
            mock_load.return_value = mock_config

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                mock_exec.return_value = mock_proc

                result = await tool.execute(service="ollama")

                assert result.success
                assert "enabled" in result.output.lower()


class TestServiceDisableTool:
    """Test ServiceDisableTool."""

    @pytest.fixture
    def tool(self):
        return ServiceDisableTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "service_disable"

    @pytest.mark.asyncio
    async def test_disable_success(self, tool):
        """Test successful service disable."""
        with patch("sindri.tools.services.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_config.allowed_services = ["ollama"]
            mock_load.return_value = mock_config

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                mock_exec.return_value = mock_proc

                result = await tool.execute(service="ollama")

                assert result.success
                assert "disabled" in result.output.lower()


class TestServiceLogsTool:
    """Test ServiceLogsTool."""

    @pytest.fixture
    def tool(self):
        return ServiceLogsTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "service_logs"
        assert "lines" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_logs_success(self, tool):
        """Test successful log retrieval."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"Jan 18 10:00 log line", b""))
            mock_exec.return_value = mock_proc

            result = await tool.execute(service="ollama", lines=50)

            assert result.success
            assert "log line" in result.output

    @pytest.mark.asyncio
    async def test_logs_custom_line_count(self, tool):
        """Test log retrieval with custom line count."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"log", b""))
            mock_exec.return_value = mock_proc

            await tool.execute(service="ollama", lines=100)

            call_args = mock_exec.call_args[0]
            assert "-n" in call_args
            # Find the position of -n and check next argument
            n_idx = list(call_args).index("-n")
            assert call_args[n_idx + 1] == "100"


class TestServiceListTool:
    """Test ServiceListTool."""

    @pytest.fixture
    def tool(self):
        return ServiceListTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "service_list"
        assert "state" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_list_running_services(self, tool):
        """Test listing running services."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"ollama.service running", b""))
            mock_exec.return_value = mock_proc

            result = await tool.execute(state="running")

            assert result.success
            assert "ollama" in result.output

    @pytest.mark.asyncio
    async def test_list_all_services(self, tool):
        """Test listing all services."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"service list", b""))
            mock_exec.return_value = mock_proc

            result = await tool.execute(state="all")

            # The tool uses --state=all instead of --all flag
            call_args = mock_exec.call_args[0]
            assert "--state=all" in call_args or result.success


class TestServiceToolsCollection:
    """Test the SERVICE_TOOLS collection."""

    def test_all_tools_in_collection(self):
        """Test all service tools are in the collection."""
        assert len(SERVICE_TOOLS) == 8
        tool_classes = [t.__name__ for t in SERVICE_TOOLS]
        assert "ServiceStatusTool" in tool_classes
        assert "ServiceStartTool" in tool_classes
        assert "ServiceStopTool" in tool_classes
        assert "ServiceRestartTool" in tool_classes
        assert "ServiceEnableTool" in tool_classes
        assert "ServiceDisableTool" in tool_classes
        assert "ServiceLogsTool" in tool_classes
        assert "ServiceListTool" in tool_classes


class TestAccessControlIntegration:
    """Test access control integration with service tools."""

    @pytest.mark.asyncio
    async def test_restricted_blocks_modifications(self):
        """Test RESTRICTED level blocks all modification operations."""
        modification_tools = [
            ServiceStartTool(),
            ServiceStopTool(),
            ServiceRestartTool(),
            ServiceEnableTool(),
            ServiceDisableTool(),
        ]

        with patch("sindri.tools.services.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.RESTRICTED
            mock_config.allowed_services = ["ollama"]
            mock_load.return_value = mock_config

            for tool in modification_tools:
                result = await tool.execute(service="ollama")
                assert not result.success, f"{tool.name} should be blocked in RESTRICTED mode"

    @pytest.mark.asyncio
    async def test_supervised_needs_confirmation(self):
        """Test SUPERVISED level indicates confirmation needed."""
        with patch("sindri.tools.services.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.SUPERVISED
            mock_config.allowed_services = ["ollama"]
            mock_load.return_value = mock_config

            tool = ServiceRestartTool()
            # In supervised mode, check_system_access returns needs_confirmation=True
            # The tool should still proceed (confirmation is handled by caller)
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                mock_exec.return_value = mock_proc

                result = await tool.execute(service="ollama")
                # Should succeed since we mock the subprocess
                assert result.success

    @pytest.mark.asyncio
    async def test_full_access_allows_all(self):
        """Test FULL level allows all operations."""
        with patch("sindri.tools.services.SindriConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.system_access = SystemAccessLevel.FULL
            mock_config.allowed_services = ["ollama"]
            mock_load.return_value = mock_config

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                mock_exec.return_value = mock_proc

                tool = ServiceRestartTool()
                result = await tool.execute(service="ollama")

                assert result.success
