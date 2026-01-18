"""Tests for system and process monitoring tools."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sindri.tools.system import (
    ProcessListTool,
    ProcessKillTool,
    SystemInfoTool,
    DiskUsageTool,
    MemoryUsageTool,
    EnvGetTool,
    _format_bytes,
    _format_duration,
)


class TestFormatHelpers:
    """Tests for formatting helper functions."""

    def test_format_bytes_small(self):
        """Test formatting small byte values."""
        assert _format_bytes(100) == "100.0 B"
        assert _format_bytes(1023) == "1023.0 B"

    def test_format_bytes_kilobytes(self):
        """Test formatting kilobyte values."""
        assert _format_bytes(1024) == "1.0 KB"
        assert _format_bytes(1536) == "1.5 KB"

    def test_format_bytes_megabytes(self):
        """Test formatting megabyte values."""
        assert _format_bytes(1024 * 1024) == "1.0 MB"
        assert _format_bytes(1024 * 1024 * 512) == "512.0 MB"

    def test_format_bytes_gigabytes(self):
        """Test formatting gigabyte values."""
        assert _format_bytes(1024 * 1024 * 1024) == "1.0 GB"

    def test_format_duration_seconds(self):
        """Test formatting short durations."""
        assert _format_duration(45) == "45s"
        assert _format_duration(0) == "0s"

    def test_format_duration_minutes(self):
        """Test formatting minute durations."""
        assert _format_duration(90) == "1m 30s"
        assert _format_duration(120) == "2m"

    def test_format_duration_hours(self):
        """Test formatting hour durations."""
        assert _format_duration(3661) == "1h 1m 1s"

    def test_format_duration_days(self):
        """Test formatting day durations."""
        assert "d" in _format_duration(86400)
        assert "1d" in _format_duration(86400)


class TestProcessListTool:
    """Tests for ProcessListTool."""

    @pytest.fixture
    def tool(self):
        """Create a ProcessListTool instance."""
        return ProcessListTool()

    @pytest.mark.asyncio
    async def test_basic_listing(self, tool):
        """Test basic process listing."""
        result = await tool.execute()
        assert result.success
        assert "PID" in result.output
        assert "NAME" in result.output
        assert result.metadata["process_count"] > 0

    @pytest.mark.asyncio
    async def test_limit_parameter(self, tool):
        """Test limiting number of results."""
        result = await tool.execute(limit=5)
        assert result.success
        assert result.metadata["process_count"] <= 5
        assert result.metadata["limit"] == 5

    @pytest.mark.asyncio
    async def test_filter_by_name(self, tool):
        """Test filtering by process name."""
        # Filter for python processes (we know at least one is running)
        result = await tool.execute(name="python", limit=10)
        assert result.success
        assert result.metadata["filters"]["name"] == "python"

    @pytest.mark.asyncio
    async def test_sort_by_cpu(self, tool):
        """Test sorting by CPU usage."""
        result = await tool.execute(sort_by="cpu", limit=5)
        assert result.success
        assert result.metadata["sort_by"] == "cpu"

    @pytest.mark.asyncio
    async def test_sort_by_memory(self, tool):
        """Test sorting by memory usage."""
        result = await tool.execute(sort_by="memory", limit=5)
        assert result.success
        assert result.metadata["sort_by"] == "memory"

    @pytest.mark.asyncio
    async def test_sort_by_pid(self, tool):
        """Test sorting by PID."""
        result = await tool.execute(sort_by="pid", limit=5)
        assert result.success
        assert result.metadata["sort_by"] == "pid"

    @pytest.mark.asyncio
    async def test_sort_by_name(self, tool):
        """Test sorting by name."""
        result = await tool.execute(sort_by="name", limit=5)
        assert result.success
        assert result.metadata["sort_by"] == "name"

    @pytest.mark.asyncio
    async def test_no_matching_processes(self, tool):
        """Test filtering with no matches."""
        result = await tool.execute(name="nonexistent_process_xyz123")
        assert result.success
        assert result.metadata["process_count"] == 0


class TestProcessKillTool:
    """Tests for ProcessKillTool."""

    @pytest.fixture
    def tool(self):
        """Create a ProcessKillTool instance."""
        return ProcessKillTool()

    @pytest.mark.asyncio
    async def test_no_pid_or_name(self, tool):
        """Test error when neither pid nor name specified."""
        result = await tool.execute()
        assert not result.success
        assert "Must specify either pid or name" in result.error

    @pytest.mark.asyncio
    async def test_nonexistent_pid(self, tool):
        """Test killing nonexistent PID."""
        result = await tool.execute(pid=999999999)
        assert not result.success
        assert "No process found" in result.error

    @pytest.mark.asyncio
    async def test_nonexistent_name(self, tool):
        """Test killing nonexistent process name."""
        result = await tool.execute(name="nonexistent_process_xyz123")
        assert not result.success
        assert "No process found" in result.error

    @pytest.mark.asyncio
    async def test_kill_by_pid_mocked(self, tool):
        """Test killing by PID with mocked process."""
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.name.return_value = "test_process"
        mock_proc.status.return_value = "running"
        mock_proc.username.return_value = "testuser"

        with patch("sindri.tools.system.psutil.Process", return_value=mock_proc):
            result = await tool.execute(pid=12345, signal="TERM")
            assert result.success
            assert "12345" in result.output
            assert result.metadata["pid"] == 12345
            mock_proc.send_signal.assert_called_once()

    @pytest.mark.asyncio
    async def test_kill_by_name_mocked(self, tool):
        """Test killing by name with mocked process."""
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.name.return_value = "test_process"
        mock_proc.status.return_value = "running"
        mock_proc.username.return_value = "testuser"
        mock_proc.info = {"pid": 12345, "name": "test_process"}

        with patch(
            "sindri.tools.system.psutil.process_iter", return_value=[mock_proc]
        ):
            result = await tool.execute(name="test_process", signal="KILL")
            assert result.success
            assert result.metadata["signal"] == "KILL"


class TestSystemInfoTool:
    """Tests for SystemInfoTool."""

    @pytest.fixture
    def tool(self):
        """Create a SystemInfoTool instance."""
        return SystemInfoTool()

    @pytest.mark.asyncio
    async def test_basic_info(self, tool):
        """Test basic system info retrieval."""
        result = await tool.execute()
        assert result.success
        assert "System Information" in result.output
        assert "Platform:" in result.output

    @pytest.mark.asyncio
    async def test_platform_metadata(self, tool):
        """Test platform metadata is present."""
        result = await tool.execute()
        assert result.success
        assert "platform" in result.metadata
        assert "system" in result.metadata["platform"]
        assert "python_version" in result.metadata["platform"]

    @pytest.mark.asyncio
    async def test_cpu_metadata(self, tool):
        """Test CPU metadata is present."""
        result = await tool.execute()
        assert result.success
        assert "cpu" in result.metadata
        assert "logical_cores" in result.metadata["cpu"]

    @pytest.mark.asyncio
    async def test_memory_metadata(self, tool):
        """Test memory metadata is present."""
        result = await tool.execute()
        assert result.success
        assert "memory" in result.metadata
        assert "total" in result.metadata["memory"]
        assert "available" in result.metadata["memory"]

    @pytest.mark.asyncio
    async def test_uptime_metadata(self, tool):
        """Test uptime metadata is present."""
        result = await tool.execute()
        assert result.success
        assert "uptime" in result.metadata
        assert "boot_time" in result.metadata["uptime"]
        assert "uptime_human" in result.metadata["uptime"]


class TestDiskUsageTool:
    """Tests for DiskUsageTool."""

    @pytest.fixture
    def tool(self):
        """Create a DiskUsageTool instance."""
        return DiskUsageTool()

    @pytest.mark.asyncio
    async def test_root_path(self, tool):
        """Test disk usage for root path."""
        result = await tool.execute(path="/")
        assert result.success
        assert "Disk Usage" in result.output
        assert result.metadata["partitions"]
        assert result.metadata["partitions"][0]["total"] > 0

    @pytest.mark.asyncio
    async def test_current_dir(self, tool):
        """Test disk usage for current directory."""
        result = await tool.execute(path=".")
        assert result.success
        assert result.metadata["partitions"]

    @pytest.mark.asyncio
    async def test_temp_dir(self, tool):
        """Test disk usage for temp directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await tool.execute(path=tmpdir)
            assert result.success
            assert result.metadata["partitions"]

    @pytest.mark.asyncio
    async def test_nonexistent_path(self, tool):
        """Test error for nonexistent path."""
        result = await tool.execute(path="/nonexistent/path/xyz123")
        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_all_partitions(self, tool):
        """Test listing all partitions."""
        result = await tool.execute(all_partitions=True)
        assert result.success
        assert result.metadata["all_partitions"] is True
        # Should have at least one partition
        assert len(result.metadata["partitions"]) >= 1

    @pytest.mark.asyncio
    async def test_partition_fields(self, tool):
        """Test partition metadata fields."""
        result = await tool.execute(path="/")
        assert result.success
        partition = result.metadata["partitions"][0]
        assert "total" in partition
        assert "used" in partition
        assert "free" in partition
        assert "percent" in partition

    @pytest.mark.asyncio
    async def test_human_readable_output(self, tool):
        """Test output contains human-readable sizes."""
        result = await tool.execute(path="/")
        assert result.success
        # Output should contain size units
        assert any(unit in result.output for unit in ["GB", "TB", "MB"])


class TestMemoryUsageTool:
    """Tests for MemoryUsageTool."""

    @pytest.fixture
    def tool(self):
        """Create a MemoryUsageTool instance."""
        return MemoryUsageTool()

    @pytest.mark.asyncio
    async def test_basic_memory(self, tool):
        """Test basic memory info retrieval."""
        result = await tool.execute()
        assert result.success
        assert "Memory Usage" in result.output
        assert "RAM:" in result.output

    @pytest.mark.asyncio
    async def test_memory_fields(self, tool):
        """Test memory metadata fields."""
        result = await tool.execute()
        assert result.success
        assert "total" in result.metadata
        assert "available" in result.metadata
        assert "used" in result.metadata
        assert "percent" in result.metadata

    @pytest.mark.asyncio
    async def test_human_readable_fields(self, tool):
        """Test human-readable memory fields."""
        result = await tool.execute()
        assert result.success
        assert "total_human" in result.metadata
        assert "available_human" in result.metadata

    @pytest.mark.asyncio
    async def test_with_swap(self, tool):
        """Test memory with swap info."""
        result = await tool.execute(include_swap=True)
        assert result.success
        assert "Swap:" in result.output
        assert "swap" in result.metadata

    @pytest.mark.asyncio
    async def test_without_swap(self, tool):
        """Test memory without swap info."""
        result = await tool.execute(include_swap=False)
        assert result.success
        assert "swap" not in result.metadata

    @pytest.mark.asyncio
    async def test_percent_range(self, tool):
        """Test memory percent is in valid range."""
        result = await tool.execute()
        assert result.success
        percent = result.metadata["percent"]
        assert 0 <= percent <= 100


class TestEnvGetTool:
    """Tests for EnvGetTool."""

    @pytest.fixture
    def tool(self):
        """Create an EnvGetTool instance."""
        return EnvGetTool()

    @pytest.mark.asyncio
    async def test_get_path(self, tool):
        """Test getting PATH variable."""
        result = await tool.execute(name="PATH")
        assert result.success
        assert "PATH=" in result.output
        assert result.metadata["count"] == 1

    @pytest.mark.asyncio
    async def test_get_home(self, tool):
        """Test getting HOME variable."""
        result = await tool.execute(name="HOME")
        assert result.success
        assert "HOME=" in result.output

    @pytest.mark.asyncio
    async def test_nonexistent_var(self, tool):
        """Test getting nonexistent variable."""
        result = await tool.execute(name="NONEXISTENT_VAR_XYZ123")
        assert not result.success
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_list_all(self, tool):
        """Test listing all variables."""
        result = await tool.execute()
        assert result.success
        assert result.metadata["count"] > 0
        assert "PATH" in result.output

    @pytest.mark.asyncio
    async def test_pattern_match(self, tool):
        """Test filtering by regex pattern."""
        result = await tool.execute(pattern="^PATH$")
        assert result.success
        assert result.metadata["count"] >= 1

    @pytest.mark.asyncio
    async def test_pattern_partial(self, tool):
        """Test filtering by partial pattern."""
        result = await tool.execute(pattern="HOME")
        assert result.success
        # Should match HOME and possibly other vars containing HOME
        assert result.metadata["count"] >= 1

    @pytest.mark.asyncio
    async def test_invalid_pattern(self, tool):
        """Test error for invalid regex pattern."""
        result = await tool.execute(pattern="[invalid")
        assert not result.success
        assert "Invalid regex" in result.error

    @pytest.mark.asyncio
    async def test_hide_values(self, tool):
        """Test hiding variable values."""
        result = await tool.execute(name="PATH", show_values=False)
        assert result.success
        assert "PATH" in result.output
        # Should only show name, not value (skip header lines)
        lines = result.output.split("\n")
        var_lines = [line for line in lines if line and not line.startswith("=") and not line.startswith("Environment")]
        # Variable lines should not contain '=' (no values)
        for line in var_lines:
            assert "=" not in line

    @pytest.mark.asyncio
    async def test_show_values_default(self, tool):
        """Test that values are shown by default."""
        result = await tool.execute(name="PATH")
        assert result.success
        assert "=" in result.output
        assert "variables" in result.metadata


class TestSystemToolsIntegration:
    """Integration tests for system tools."""

    @pytest.mark.asyncio
    async def test_system_overview(self):
        """Test getting a complete system overview."""
        system_tool = SystemInfoTool()
        disk_tool = DiskUsageTool()
        memory_tool = MemoryUsageTool()

        system_result = await system_tool.execute()
        disk_result = await disk_tool.execute()
        memory_result = await memory_tool.execute()

        assert system_result.success
        assert disk_result.success
        assert memory_result.success

    @pytest.mark.asyncio
    async def test_process_list_and_info(self):
        """Test process list followed by system info."""
        process_tool = ProcessListTool()
        system_tool = SystemInfoTool()

        proc_result = await process_tool.execute(limit=10)
        sys_result = await system_tool.execute()

        assert proc_result.success
        assert sys_result.success
        assert proc_result.metadata["process_count"] <= 10

    @pytest.mark.asyncio
    async def test_env_and_system(self):
        """Test env variables and system info together."""
        env_tool = EnvGetTool()
        system_tool = SystemInfoTool()

        env_result = await env_tool.execute(name="PATH")
        sys_result = await system_tool.execute()

        assert env_result.success
        assert sys_result.success

    @pytest.mark.asyncio
    async def test_disk_and_memory(self):
        """Test disk and memory usage together."""
        disk_tool = DiskUsageTool()
        memory_tool = MemoryUsageTool()

        disk_result = await disk_tool.execute(all_partitions=True)
        memory_result = await memory_tool.execute(include_swap=True)

        assert disk_result.success
        assert memory_result.success
        assert disk_result.metadata["partitions"]
        assert memory_result.metadata["total"] > 0
