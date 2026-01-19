"""Service management tools for systemd services.

This module provides tools for managing systemd services, integrating with the
system access configuration from Milestone 5 to ensure proper permission checks.

Tools:
- service_status: Check service status
- service_start: Start a service
- service_stop: Stop a service
- service_restart: Restart a service
- service_enable: Enable service on boot
- service_disable: Disable service on boot
- service_logs: View service logs
- service_list: List services
"""

import asyncio
import shutil
from pathlib import Path
from typing import Any, Optional

import structlog

from sindri.config import SindriConfig
from sindri.core.access import check_system_access
from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


def _check_systemctl() -> bool:
    """Check if systemctl is available."""
    return shutil.which("systemctl") is not None


def _check_journalctl() -> bool:
    """Check if journalctl is available."""
    return shutil.which("journalctl") is not None


async def _run_systemctl(
    *args: str, user: bool = False, timeout: int = 30
) -> tuple[int, str, str]:
    """Run systemctl command and return (returncode, stdout, stderr).

    Args:
        *args: Arguments to pass to systemctl
        user: If True, run as user service (--user flag)
        timeout: Command timeout in seconds

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    cmd = ["systemctl"]
    if user:
        cmd.append("--user")
    cmd.extend(args)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return (
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )
    except asyncio.TimeoutError:
        return (-1, "", f"Command timed out after {timeout} seconds")
    except Exception as e:
        return (-1, "", str(e))


class ServiceStatusTool(Tool):
    """Check the status of a systemd service."""

    name = "service_status"
    description = (
        "Check the status of a systemd service. "
        "Returns whether the service is running, its PID, memory usage, and recent logs."
    )
    parameters = {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "Name of the service (e.g., 'ollama', 'nginx')",
            },
            "user": {
                "type": "boolean",
                "description": "Check user service instead of system service (default: false)",
            },
        },
        "required": ["service"],
    }

    async def execute(
        self,
        service: str,
        user: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Check service status."""
        log.info("service_status_start", service=service, user=user)

        if not _check_systemctl():
            return ToolResult(
                success=False,
                output="",
                error="systemctl not found. This tool requires systemd.",
            )

        # Status is a read operation - allowed in all access levels
        # But we still validate the service name
        config = SindriConfig.load()
        if service not in config.allowed_services:
            log.warning("service_status_not_allowed", service=service)
            # Still allow status checks for non-whitelisted services
            # but log a warning

        returncode, stdout, stderr = await _run_systemctl(
            "status", service, user=user
        )

        # systemctl status returns non-zero if service is stopped
        # but that's not an error for us
        if returncode not in (0, 3):  # 3 = service not running
            if "could not be found" in stderr.lower():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Service '{service}' not found",
                )
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to get service status: {stderr}",
            )

        # Parse status for metadata
        is_active = "Active: active" in stdout
        is_enabled = "enabled;" in stdout.lower()

        log.info(
            "service_status_success",
            service=service,
            active=is_active,
            enabled=is_enabled,
        )

        return ToolResult(
            success=True,
            output=stdout.strip(),
            metadata={
                "service": service,
                "active": is_active,
                "enabled": is_enabled,
                "user_service": user,
            },
        )


class ServiceStartTool(Tool):
    """Start a systemd service."""

    name = "service_start"
    description = (
        "Start a systemd service. Requires appropriate system access level. "
        "The service must be in the allowed_services list."
    )
    parameters = {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "Name of the service to start",
            },
            "user": {
                "type": "boolean",
                "description": "Start user service instead of system service (default: false)",
            },
        },
        "required": ["service"],
    }

    async def execute(
        self,
        service: str,
        user: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Start a service."""
        log.info("service_start_request", service=service, user=user)

        if not _check_systemctl():
            return ToolResult(
                success=False,
                output="",
                error="systemctl not found. This tool requires systemd.",
            )

        # Check access control
        config = SindriConfig.load()
        access_result = check_system_access(
            config,
            f"start service '{service}'",
            service=service,
            is_modification=True,
        )

        if not access_result.allowed:
            log.warning("service_start_denied", service=service, reason=access_result.reason)
            return ToolResult(
                success=False,
                output="",
                error=access_result.reason,
            )

        if access_result.needs_confirmation:
            log.info("service_start_needs_confirmation", service=service)
            # In tool context, we proceed but log that confirmation was needed
            # The caller (CLI/TUI) should handle confirmation prompts

        returncode, stdout, stderr = await _run_systemctl(
            "start", service, user=user
        )

        if returncode != 0:
            log.error("service_start_failed", service=service, error=stderr)
            return ToolResult(
                success=False,
                output=stdout,
                error=f"Failed to start service: {stderr}",
            )

        log.info("service_start_success", service=service)
        return ToolResult(
            success=True,
            output=f"Service '{service}' started successfully",
            metadata={"service": service, "action": "start", "user_service": user},
        )


class ServiceStopTool(Tool):
    """Stop a systemd service."""

    name = "service_stop"
    description = (
        "Stop a systemd service. Requires appropriate system access level. "
        "The service must be in the allowed_services list."
    )
    parameters = {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "Name of the service to stop",
            },
            "user": {
                "type": "boolean",
                "description": "Stop user service instead of system service (default: false)",
            },
        },
        "required": ["service"],
    }

    async def execute(
        self,
        service: str,
        user: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Stop a service."""
        log.info("service_stop_request", service=service, user=user)

        if not _check_systemctl():
            return ToolResult(
                success=False,
                output="",
                error="systemctl not found. This tool requires systemd.",
            )

        # Check access control
        config = SindriConfig.load()
        access_result = check_system_access(
            config,
            f"stop service '{service}'",
            service=service,
            is_modification=True,
        )

        if not access_result.allowed:
            log.warning("service_stop_denied", service=service, reason=access_result.reason)
            return ToolResult(
                success=False,
                output="",
                error=access_result.reason,
            )

        returncode, stdout, stderr = await _run_systemctl(
            "stop", service, user=user
        )

        if returncode != 0:
            log.error("service_stop_failed", service=service, error=stderr)
            return ToolResult(
                success=False,
                output=stdout,
                error=f"Failed to stop service: {stderr}",
            )

        log.info("service_stop_success", service=service)
        return ToolResult(
            success=True,
            output=f"Service '{service}' stopped successfully",
            metadata={"service": service, "action": "stop", "user_service": user},
        )


class ServiceRestartTool(Tool):
    """Restart a systemd service."""

    name = "service_restart"
    description = (
        "Restart a systemd service. Requires appropriate system access level. "
        "The service must be in the allowed_services list."
    )
    parameters = {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "Name of the service to restart",
            },
            "user": {
                "type": "boolean",
                "description": "Restart user service instead of system service (default: false)",
            },
        },
        "required": ["service"],
    }

    async def execute(
        self,
        service: str,
        user: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Restart a service."""
        log.info("service_restart_request", service=service, user=user)

        if not _check_systemctl():
            return ToolResult(
                success=False,
                output="",
                error="systemctl not found. This tool requires systemd.",
            )

        # Check access control
        config = SindriConfig.load()
        access_result = check_system_access(
            config,
            f"restart service '{service}'",
            service=service,
            is_modification=True,
        )

        if not access_result.allowed:
            log.warning("service_restart_denied", service=service, reason=access_result.reason)
            return ToolResult(
                success=False,
                output="",
                error=access_result.reason,
            )

        returncode, stdout, stderr = await _run_systemctl(
            "restart", service, user=user
        )

        if returncode != 0:
            log.error("service_restart_failed", service=service, error=stderr)
            return ToolResult(
                success=False,
                output=stdout,
                error=f"Failed to restart service: {stderr}",
            )

        log.info("service_restart_success", service=service)
        return ToolResult(
            success=True,
            output=f"Service '{service}' restarted successfully",
            metadata={"service": service, "action": "restart", "user_service": user},
        )


class ServiceEnableTool(Tool):
    """Enable a systemd service to start on boot."""

    name = "service_enable"
    description = (
        "Enable a systemd service to start automatically on boot. "
        "Requires appropriate system access level. "
        "The service must be in the allowed_services list."
    )
    parameters = {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "Name of the service to enable",
            },
            "user": {
                "type": "boolean",
                "description": "Enable user service instead of system service (default: false)",
            },
            "now": {
                "type": "boolean",
                "description": "Also start the service immediately (default: false)",
            },
        },
        "required": ["service"],
    }

    async def execute(
        self,
        service: str,
        user: bool = False,
        now: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Enable a service."""
        log.info("service_enable_request", service=service, user=user, now=now)

        if not _check_systemctl():
            return ToolResult(
                success=False,
                output="",
                error="systemctl not found. This tool requires systemd.",
            )

        # Check access control
        config = SindriConfig.load()
        access_result = check_system_access(
            config,
            f"enable service '{service}'",
            service=service,
            is_modification=True,
        )

        if not access_result.allowed:
            log.warning("service_enable_denied", service=service, reason=access_result.reason)
            return ToolResult(
                success=False,
                output="",
                error=access_result.reason,
            )

        args = ["enable", service]
        if now:
            args.append("--now")

        returncode, stdout, stderr = await _run_systemctl(*args, user=user)

        if returncode != 0:
            log.error("service_enable_failed", service=service, error=stderr)
            return ToolResult(
                success=False,
                output=stdout,
                error=f"Failed to enable service: {stderr}",
            )

        msg = f"Service '{service}' enabled"
        if now:
            msg += " and started"

        log.info("service_enable_success", service=service, now=now)
        return ToolResult(
            success=True,
            output=msg,
            metadata={"service": service, "action": "enable", "now": now, "user_service": user},
        )


class ServiceDisableTool(Tool):
    """Disable a systemd service from starting on boot."""

    name = "service_disable"
    description = (
        "Disable a systemd service from starting automatically on boot. "
        "Requires appropriate system access level. "
        "The service must be in the allowed_services list."
    )
    parameters = {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "Name of the service to disable",
            },
            "user": {
                "type": "boolean",
                "description": "Disable user service instead of system service (default: false)",
            },
            "now": {
                "type": "boolean",
                "description": "Also stop the service immediately (default: false)",
            },
        },
        "required": ["service"],
    }

    async def execute(
        self,
        service: str,
        user: bool = False,
        now: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Disable a service."""
        log.info("service_disable_request", service=service, user=user, now=now)

        if not _check_systemctl():
            return ToolResult(
                success=False,
                output="",
                error="systemctl not found. This tool requires systemd.",
            )

        # Check access control
        config = SindriConfig.load()
        access_result = check_system_access(
            config,
            f"disable service '{service}'",
            service=service,
            is_modification=True,
        )

        if not access_result.allowed:
            log.warning("service_disable_denied", service=service, reason=access_result.reason)
            return ToolResult(
                success=False,
                output="",
                error=access_result.reason,
            )

        args = ["disable", service]
        if now:
            args.append("--now")

        returncode, stdout, stderr = await _run_systemctl(*args, user=user)

        if returncode != 0:
            log.error("service_disable_failed", service=service, error=stderr)
            return ToolResult(
                success=False,
                output=stdout,
                error=f"Failed to disable service: {stderr}",
            )

        msg = f"Service '{service}' disabled"
        if now:
            msg += " and stopped"

        log.info("service_disable_success", service=service, now=now)
        return ToolResult(
            success=True,
            output=msg,
            metadata={"service": service, "action": "disable", "now": now, "user_service": user},
        )


class ServiceLogsTool(Tool):
    """View logs for a systemd service."""

    name = "service_logs"
    description = (
        "View logs for a systemd service using journalctl. "
        "Can filter by number of lines, time range, and priority."
    )
    parameters = {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "Name of the service to view logs for",
            },
            "lines": {
                "type": "integer",
                "description": "Number of lines to show (default: 50)",
            },
            "since": {
                "type": "string",
                "description": "Show logs since this time (e.g., '1 hour ago', '2024-01-01')",
            },
            "priority": {
                "type": "string",
                "enum": ["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"],
                "description": "Filter by priority level",
            },
            "follow": {
                "type": "boolean",
                "description": "Follow log output (not recommended for tool use)",
            },
            "user": {
                "type": "boolean",
                "description": "View user service logs instead of system service (default: false)",
            },
        },
        "required": ["service"],
    }

    async def execute(
        self,
        service: str,
        lines: int = 50,
        since: Optional[str] = None,
        priority: Optional[str] = None,
        follow: bool = False,
        user: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """View service logs."""
        log.info(
            "service_logs_request",
            service=service,
            lines=lines,
            since=since,
            priority=priority,
        )

        if not _check_journalctl():
            return ToolResult(
                success=False,
                output="",
                error="journalctl not found. This tool requires systemd.",
            )

        # Logs are read-only - no access control needed beyond basic validation
        cmd = ["journalctl", "-u", service, "-n", str(lines)]

        if user:
            cmd.append("--user")
        if since:
            cmd.extend(["--since", since])
        if priority:
            cmd.extend(["-p", priority])
        if follow:
            # Don't actually follow - just get recent logs
            log.warning("service_logs_follow_ignored", service=service)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            if proc.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                if "No entries" in error_msg:
                    return ToolResult(
                        success=True,
                        output=f"No log entries found for service '{service}'",
                        metadata={"service": service, "lines": 0},
                    )
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to get logs: {error_msg}",
                )

            output = stdout.decode("utf-8", errors="replace")
            line_count = len(output.strip().split("\n")) if output.strip() else 0

            log.info("service_logs_success", service=service, lines=line_count)
            return ToolResult(
                success=True,
                output=output.strip(),
                metadata={"service": service, "lines": line_count, "user_service": user},
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error="Timed out getting logs",
            )
        except Exception as e:
            log.error("service_logs_error", service=service, error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to get logs: {str(e)}",
            )


class ServiceListTool(Tool):
    """List systemd services."""

    name = "service_list"
    description = (
        "List systemd services. Can filter by state (active, running, failed, etc.) "
        "and show all or just loaded services."
    )
    parameters = {
        "type": "object",
        "properties": {
            "state": {
                "type": "string",
                "enum": ["active", "inactive", "running", "failed", "enabled", "disabled"],
                "description": "Filter by service state",
            },
            "all": {
                "type": "boolean",
                "description": "Show all services including inactive (default: false)",
            },
            "user": {
                "type": "boolean",
                "description": "List user services instead of system services (default: false)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        state: Optional[str] = None,
        all: bool = False,
        user: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """List services."""
        log.info("service_list_request", state=state, all=all, user=user)

        if not _check_systemctl():
            return ToolResult(
                success=False,
                output="",
                error="systemctl not found. This tool requires systemd.",
            )

        # List is read-only - no access control needed
        args = ["list-units", "--type=service", "--no-pager"]

        if all:
            args.append("--all")
        if state:
            if state in ("enabled", "disabled"):
                # Use list-unit-files for enabled/disabled state
                args = ["list-unit-files", "--type=service", "--no-pager"]
                args.append(f"--state={state}")
            else:
                args.append(f"--state={state}")

        returncode, stdout, stderr = await _run_systemctl(*args, user=user)

        if returncode != 0:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to list services: {stderr}",
            )

        # Count services
        lines = [l for l in stdout.strip().split("\n") if l and not l.startswith("UNIT") and not l.startswith("LEGEND")]
        service_count = len([l for l in lines if ".service" in l])

        log.info("service_list_success", count=service_count)
        return ToolResult(
            success=True,
            output=stdout.strip(),
            metadata={
                "count": service_count,
                "state_filter": state,
                "show_all": all,
                "user_service": user,
            },
        )


# Export all service tools
SERVICE_TOOLS = [
    ServiceStatusTool,
    ServiceStartTool,
    ServiceStopTool,
    ServiceRestartTool,
    ServiceEnableTool,
    ServiceDisableTool,
    ServiceLogsTool,
    ServiceListTool,
]
