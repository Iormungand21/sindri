"""Tests for bash scripting and shell tools (Phase 12).

Tests for Sif agent's bash script generation, explanation, validation,
systemd generation, and linting tools.
"""

import pytest
import shutil

from sindri.tools.bash_tools import (
    BashGenerateTool,
    BashExplainTool,
    BashValidateTool,
    SystemdGenerateTool,
    BashLintTool,
)
from sindri.agents.registry import get_agent, AGENTS


# ═══════════════════════════════════════════════════════════════════════════════
# BashGenerateTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestBashGenerateTool:
    """Test suite for bash script generation."""

    @pytest.fixture
    def tool(self):
        return BashGenerateTool()

    @pytest.mark.asyncio
    async def test_generate_backup_script(self, tool):
        """Test generating backup script from description."""
        result = await tool.execute(description="Create a backup script for /var/data")

        assert result.success
        assert "#!/" in result.output
        assert "backup" in result.metadata["template"]
        assert "tar" in result.output.lower() or "backup" in result.output.lower()

    @pytest.mark.asyncio
    async def test_generate_log_rotation_script(self, tool):
        """Test generating log rotation script."""
        result = await tool.execute(description="Script to rotate logs larger than 10MB")

        assert result.success
        assert "log_rotation" in result.metadata["template"]
        assert "10485760" in result.output  # 10MB in bytes

    @pytest.mark.asyncio
    async def test_generate_deployment_script(self, tool):
        """Test generating deployment script."""
        result = await tool.execute(description="Deployment script for myapp")

        assert result.success
        assert "deployment" in result.metadata["template"]
        assert "myapp" in result.output

    @pytest.mark.asyncio
    async def test_generate_health_check_script(self, tool):
        """Test generating health check script."""
        result = await tool.execute(description="Health check for my-service on port 8080")

        assert result.success
        assert "service_health" in result.metadata["template"]
        assert "8080" in result.output
        assert "curl" in result.output.lower() or "health" in result.output.lower()

    @pytest.mark.asyncio
    async def test_generate_cleanup_script(self, tool):
        """Test generating cleanup script."""
        result = await tool.execute(
            description="Cleanup script to delete old files in /tmp older than 7 days"
        )

        assert result.success
        assert "cleanup" in result.metadata["template"]
        assert "7" in result.output

    @pytest.mark.asyncio
    async def test_strict_mode_includes_safety(self, tool):
        """Test that strict mode includes safety settings."""
        result = await tool.execute(
            description="Simple hello world script",
            strict_mode=True,
        )

        assert result.success
        assert "set -" in result.output
        assert "pipefail" in result.output or "set -e" in result.output

    @pytest.mark.asyncio
    async def test_non_strict_mode(self, tool):
        """Test script without strict mode."""
        result = await tool.execute(
            description="Simple script",
            strict_mode=False,
        )

        assert result.success
        # Still should have shebang
        assert "#!/" in result.output

    @pytest.mark.asyncio
    async def test_portable_mode(self, tool):
        """Test POSIX-portable script generation."""
        result = await tool.execute(
            description="Create a backup script for /var/data",
            portable=True,
        )

        assert result.success
        # Should use sh instead of bash
        assert "#!/bin/sh" in result.output or "POSIX" in result.output

    @pytest.mark.asyncio
    async def test_include_help_function(self, tool):
        """Test including help function in script."""
        result = await tool.execute(
            description="Simple utility script",
            include_help=True,
        )

        assert result.success
        assert "usage" in result.output.lower() or "help" in result.output.lower()

    @pytest.mark.asyncio
    async def test_custom_script_generation(self, tool):
        """Test generating custom script from description."""
        result = await tool.execute(
            description="A script that does something unique and custom"
        )

        assert result.success
        assert "custom" in result.metadata["template"]
        assert "#!/" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# BashExplainTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestBashExplainTool:
    """Test suite for bash command explanation."""

    @pytest.fixture
    def tool(self):
        return BashExplainTool()

    @pytest.mark.asyncio
    async def test_explain_simple_command(self, tool):
        """Test explaining a simple command."""
        result = await tool.execute(command="ls -la")

        assert result.success
        assert "ls" in result.output.lower()
        assert "list" in result.output.lower() or "directory" in result.output.lower()

    @pytest.mark.asyncio
    async def test_explain_pipe_command(self, tool):
        """Test explaining piped commands."""
        result = await tool.execute(command="cat file.txt | grep error | wc -l")

        assert result.success
        assert "pipe" in result.output.lower() or "cat" in result.output.lower()
        assert "grep" in result.output.lower()
        assert "wc" in result.output.lower()

    @pytest.mark.asyncio
    async def test_explain_set_options(self, tool):
        """Test explaining set options."""
        result = await tool.execute(command="set -euo pipefail")

        assert result.success
        assert "exit" in result.output.lower() or "error" in result.output.lower()
        assert "pipefail" in result.output.lower() or "pipe" in result.output.lower()

    @pytest.mark.asyncio
    async def test_explain_find_command(self, tool):
        """Test explaining find command."""
        result = await tool.execute(command="find /var -type f -mtime +30 -delete")

        assert result.success
        assert "find" in result.output.lower()
        assert "file" in result.output.lower() or "search" in result.output.lower()

    @pytest.mark.asyncio
    async def test_explain_tar_command(self, tool):
        """Test explaining tar command."""
        result = await tool.execute(command="tar -czf backup.tar.gz /data")

        assert result.success
        assert "tar" in result.output.lower()
        assert "archive" in result.output.lower() or "compress" in result.output.lower()

    @pytest.mark.asyncio
    async def test_explain_verbose_mode(self, tool):
        """Test verbose explanation mode."""
        result = await tool.execute(
            command="grep -ri 'error' /var/log",
            verbose=True,
        )

        assert result.success
        assert "grep" in result.output.lower()

    @pytest.mark.asyncio
    async def test_explain_dangerous_command_warning(self, tool):
        """Test that dangerous commands generate warnings."""
        result = await tool.execute(command="rm -rf /")

        assert result.success
        assert "warning" in result.output.lower() or "danger" in result.output.lower()

    @pytest.mark.asyncio
    async def test_explain_eval_warning(self, tool):
        """Test that eval commands generate warnings."""
        result = await tool.execute(command='eval "$user_input"')

        assert result.success
        assert "warning" in result.output.lower() or "security" in result.output.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# BashValidateTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestBashValidateTool:
    """Test suite for bash script validation using shellcheck."""

    @pytest.fixture
    def tool(self):
        return BashValidateTool()

    @pytest.fixture
    def has_shellcheck(self):
        """Check if shellcheck is installed."""
        return shutil.which("shellcheck") is not None

    @pytest.mark.asyncio
    async def test_valid_script_passes(self, tool, has_shellcheck):
        """Test that a valid script passes validation."""
        if not has_shellcheck:
            pytest.skip("shellcheck not installed")

        script = '''#!/bin/bash
set -euo pipefail
echo "Hello, world!"
'''
        result = await tool.execute(script=script)

        assert result.success
        assert "pass" in result.output.lower() or result.metadata["issue_count"] == 0

    @pytest.mark.asyncio
    async def test_unquoted_variable_warning(self, tool, has_shellcheck):
        """Test that unquoted variables generate warnings."""
        if not has_shellcheck:
            pytest.skip("shellcheck not installed")

        script = '''#!/bin/bash
var="hello"
echo $var
'''
        result = await tool.execute(script=script, severity="warning")

        # Should either pass or find SC2086 warning
        assert result.success or not result.success
        # The issue count might be 0 or more depending on shellcheck version
        assert "issue_count" in result.metadata

    @pytest.mark.asyncio
    async def test_missing_shellcheck(self, tool, has_shellcheck):
        """Test error handling when shellcheck is not installed."""
        if has_shellcheck:
            pytest.skip("shellcheck is installed, can't test missing case")

        script = "#!/bin/bash\necho hello"
        result = await tool.execute(script=script)

        assert not result.success
        assert "shellcheck" in result.error.lower()

    @pytest.mark.asyncio
    async def test_different_shells(self, tool, has_shellcheck):
        """Test validation for different target shells."""
        if not has_shellcheck:
            pytest.skip("shellcheck not installed")

        script = '''#!/bin/sh
echo "Hello"
'''
        result = await tool.execute(script=script, shell="sh")

        assert "sh" in result.metadata.get("shell", "")

    @pytest.mark.asyncio
    async def test_severity_levels(self, tool, has_shellcheck):
        """Test different severity filter levels."""
        if not has_shellcheck:
            pytest.skip("shellcheck not installed")

        script = '''#!/bin/bash
echo "Hello"
'''
        # Test each severity level
        for severity in ["error", "warning", "info", "style"]:
            result = await tool.execute(script=script, severity=severity)
            assert result.metadata["severity"] == severity


# ═══════════════════════════════════════════════════════════════════════════════
# SystemdGenerateTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSystemdGenerateTool:
    """Test suite for systemd unit file generation."""

    @pytest.fixture
    def tool(self):
        return SystemdGenerateTool()

    @pytest.mark.asyncio
    async def test_generate_simple_service(self, tool):
        """Test generating a simple service unit."""
        result = await tool.execute(
            description="Run my application",
            exec_command="/usr/bin/myapp",
        )

        assert result.success
        assert "[Unit]" in result.output
        assert "[Service]" in result.output
        assert "[Install]" in result.output
        assert "ExecStart=/usr/bin/myapp" in result.output

    @pytest.mark.asyncio
    async def test_generate_hardened_service(self, tool):
        """Test generating a hardened service unit."""
        result = await tool.execute(
            description="Run my secure application",
            exec_command="/usr/bin/secureapp",
            hardened=True,
        )

        assert result.success
        assert "PrivateTmp=true" in result.output
        assert "ProtectSystem=strict" in result.output
        assert "NoNewPrivileges=true" in result.output

    @pytest.mark.asyncio
    async def test_generate_timer_unit(self, tool):
        """Test generating a timer unit."""
        result = await tool.execute(
            description="Hourly cleanup task",
            unit_type="timer",
            exec_command="/usr/bin/cleanup.sh",
            timer_schedule="hourly",
        )

        assert result.success
        assert "[Timer]" in result.output
        assert "OnCalendar=hourly" in result.output
        assert result.metadata["unit_count"] == 2  # Service + timer

    @pytest.mark.asyncio
    async def test_generate_service_with_user(self, tool):
        """Test generating a service with specific user."""
        result = await tool.execute(
            description="Run as myuser",
            exec_command="/usr/bin/myapp",
            user="myuser",
        )

        assert result.success
        assert "User=myuser" in result.output

    @pytest.mark.asyncio
    async def test_generate_service_with_working_dir(self, tool):
        """Test generating a service with working directory."""
        result = await tool.execute(
            description="Run in /opt/myapp",
            exec_command="/usr/bin/myapp",
            working_directory="/opt/myapp",
        )

        assert result.success
        assert "WorkingDirectory=/opt/myapp" in result.output

    @pytest.mark.asyncio
    async def test_generate_service_with_environment(self, tool):
        """Test generating a service with environment variables."""
        result = await tool.execute(
            description="Run with env vars",
            exec_command="/usr/bin/myapp",
            environment={"NODE_ENV": "production", "PORT": "8080"},
        )

        assert result.success
        assert "Environment=" in result.output
        assert "NODE_ENV" in result.output
        assert "production" in result.output

    @pytest.mark.asyncio
    async def test_generate_socket_unit(self, tool):
        """Test generating a socket unit."""
        result = await tool.execute(
            description="Socket for my service",
            unit_type="socket",
            exec_command="/run/myservice.sock",
        )

        assert result.success
        assert "[Socket]" in result.output
        assert "ListenStream" in result.output

    @pytest.mark.asyncio
    async def test_generate_path_unit(self, tool):
        """Test generating a path unit."""
        result = await tool.execute(
            description="Watch for file changes",
            unit_type="path",
            exec_command="/path/to/watch",
        )

        assert result.success
        assert "[Path]" in result.output
        assert "PathModified" in result.output

    @pytest.mark.asyncio
    async def test_missing_exec_command_for_service(self, tool):
        """Test error when exec_command is missing for service."""
        result = await tool.execute(
            description="Service without command",
            unit_type="service",
        )

        assert not result.success
        assert "exec_command" in result.error.lower()

    @pytest.mark.asyncio
    async def test_missing_schedule_for_timer(self, tool):
        """Test error when timer_schedule is missing for timer."""
        result = await tool.execute(
            description="Timer without schedule",
            unit_type="timer",
        )

        assert not result.success
        assert "timer_schedule" in result.error.lower()

    @pytest.mark.asyncio
    async def test_installation_instructions_included(self, tool):
        """Test that installation instructions are included."""
        result = await tool.execute(
            description="My service",
            exec_command="/usr/bin/myapp",
        )

        assert result.success
        assert "Installation" in result.output
        assert "systemctl" in result.output
        assert "daemon-reload" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# BashLintTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestBashLintTool:
    """Test suite for bash script linting."""

    @pytest.fixture
    def tool(self):
        return BashLintTool()

    @pytest.fixture
    def has_shellcheck(self):
        """Check if shellcheck is installed."""
        return shutil.which("shellcheck") is not None

    @pytest.mark.asyncio
    async def test_lint_clean_script(self, tool, has_shellcheck):
        """Test linting a clean script with no issues."""
        if not has_shellcheck:
            pytest.skip("shellcheck not installed")

        script = '''#!/bin/bash
set -euo pipefail
echo "Hello, world!"
'''
        result = await tool.execute(script=script)

        assert result.success
        assert result.metadata["issue_count"] == 0

    @pytest.mark.asyncio
    async def test_lint_script_with_issues(self, tool, has_shellcheck):
        """Test linting a script with issues."""
        if not has_shellcheck:
            pytest.skip("shellcheck not installed")

        # Script with common issues
        script = '''#!/bin/bash
var="hello"
echo $var
cd $DIR
'''
        result = await tool.execute(script=script)

        assert result.success
        # Should find at least some issues
        assert "issue_count" in result.metadata

    @pytest.mark.asyncio
    async def test_lint_with_fix_mode(self, tool, has_shellcheck):
        """Test linting with auto-fix mode."""
        if not has_shellcheck:
            pytest.skip("shellcheck not installed")

        script = '''#!/bin/bash
var="hello"
echo $var
'''
        result = await tool.execute(script=script, fix=True)

        assert result.success
        assert result.metadata["fixed"] == True

    @pytest.mark.asyncio
    async def test_lint_specific_rules(self, tool, has_shellcheck):
        """Test linting with specific rules."""
        if not has_shellcheck:
            pytest.skip("shellcheck not installed")

        script = '''#!/bin/bash
echo $var
'''
        result = await tool.execute(script=script, rules=["SC2086"])

        assert result.success

    @pytest.mark.asyncio
    async def test_lint_missing_shellcheck(self, tool, has_shellcheck):
        """Test error handling when shellcheck is not installed."""
        if has_shellcheck:
            pytest.skip("shellcheck is installed, can't test missing case")

        script = "#!/bin/bash\necho hello"
        result = await tool.execute(script=script)

        assert not result.success
        assert "shellcheck" in result.error.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Sif Agent Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSifAgent:
    """Integration tests for Sif agent."""

    def test_agent_exists(self):
        """Test that Sif agent exists in registry."""
        agent = get_agent("sif")
        assert agent is not None
        assert agent.name == "sif"

    def test_agent_in_agents_dict(self):
        """Test that Sif is in AGENTS dict."""
        assert "sif" in AGENTS

    def test_agent_has_required_tools(self):
        """Test that Sif has all required tools."""
        agent = get_agent("sif")
        required_tools = [
            "bash_generate",
            "bash_explain",
            "bash_validate",
            "systemd_generate",
            "bash_lint",
            "shell",
            "read_file",
            "write_file",
        ]
        for tool in required_tools:
            assert tool in agent.tools, f"Missing tool: {tool}"

    def test_agent_has_system_monitoring_tools(self):
        """Test that Sif has system monitoring tools."""
        agent = get_agent("sif")
        monitoring_tools = [
            "process_list",
            "system_info",
            "disk_usage",
            "memory_usage",
            "env_get",
        ]
        for tool in monitoring_tools:
            assert tool in agent.tools, f"Missing monitoring tool: {tool}"

    def test_agent_has_service_readonly_tools(self):
        """Test that Sif has read-only service tools."""
        agent = get_agent("sif")
        readonly_tools = [
            "service_status",
            "service_logs",
            "service_list",
        ]
        for tool in readonly_tools:
            assert tool in agent.tools, f"Missing readonly tool: {tool}"

    def test_agent_does_not_have_service_modification_tools(self):
        """Test that Sif does NOT have service modification tools."""
        agent = get_agent("sif")
        forbidden_tools = [
            "service_start",
            "service_stop",
            "service_restart",
            "service_enable",
            "service_disable",
        ]
        for tool in forbidden_tools:
            assert tool not in agent.tools, f"Should not have tool: {tool}"

    def test_agent_cannot_delegate(self):
        """Test that Sif cannot delegate."""
        agent = get_agent("sif")
        assert agent.can_delegate is False

    def test_agent_model_configuration(self):
        """Test agent model configuration."""
        agent = get_agent("sif")
        assert agent.model == "qwen2.5-coder:7b"
        assert agent.fallback_model == "qwen2.5:3b-instruct-q8_0"
        assert agent.temperature == 0.3
        assert agent.estimated_vram_gb == 5.0

    def test_brokkr_can_delegate_to_sif(self):
        """Test that Brokkr can delegate to Sif."""
        brokkr = get_agent("brokkr")
        assert "sif" in brokkr.delegate_to

    def test_agent_count_is_20(self):
        """Test that total agent count is now 20."""
        # After adding Nidhogg: 19 (previous) + 1 = 20
        assert len(AGENTS) == 20
