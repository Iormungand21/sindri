"""Scheduling tools for Sindri.

These tools enable task scheduling via cron, systemd timers, and at commands.
All modification operations are gated by the system access level configuration.
"""

import asyncio
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from sindri.config import SindriConfig
from sindri.core.access import check_system_access
from sindri.tools.base import Tool, ToolResult


class CronListTool(Tool):
    """List current user's cron jobs."""

    name = "cron_list"
    description = "List the current user's cron jobs"
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """List cron jobs for the current user."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "crontab",
                "-l",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                stderr_text = stderr.decode().strip()
                if "no crontab" in stderr_text.lower():
                    return ToolResult(
                        success=True,
                        output="No cron jobs configured for current user.",
                        error=None,
                    )
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to list cron jobs: {stderr_text}",
                )

            output = stdout.decode()
            if not output.strip():
                return ToolResult(
                    success=True,
                    output="No cron jobs configured for current user.",
                    error=None,
                )

            return ToolResult(success=True, output=output, error=None)

        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error="crontab command not found",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class CronAddTool(Tool):
    """Add a cron job for the current user."""

    name = "cron_add"
    description = "Add a cron job with the specified schedule and command"
    parameters = {
        "type": "object",
        "properties": {
            "schedule": {
                "type": "string",
                "description": "Cron schedule (e.g., '0 * * * *' for hourly, '0 0 * * *' for daily)",
            },
            "command": {
                "type": "string",
                "description": "Command to execute",
            },
            "comment": {
                "type": "string",
                "description": "Optional comment to identify this job",
            },
        },
        "required": ["schedule", "command"],
    }

    async def execute(
        self,
        schedule: str,
        command: str,
        comment: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Add a cron job."""
        config = SindriConfig.load()
        access_result = check_system_access(
            config,
            f"add cron job: {schedule} {command}",
            is_modification=True,
        )

        if not access_result.allowed:
            return ToolResult(success=False, output="", error=access_result.reason)

        try:
            # Get existing crontab
            proc = await asyncio.create_subprocess_exec(
                "crontab",
                "-l",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            existing = ""
            if proc.returncode == 0:
                existing = stdout.decode()
            elif "no crontab" not in stderr.decode().lower():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to read crontab: {stderr.decode()}",
                )

            # Build new cron entry
            new_entry = ""
            if comment:
                new_entry += f"# {comment}\n"
            new_entry += f"{schedule} {command}\n"

            # Combine existing + new
            new_crontab = existing.rstrip("\n") + "\n" + new_entry if existing.strip() else new_entry

            # Write new crontab via temp file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".cron", delete=False) as f:
                f.write(new_crontab)
                temp_path = f.name

            try:
                proc = await asyncio.create_subprocess_exec(
                    "crontab",
                    temp_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()

                if proc.returncode != 0:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Failed to install crontab: {stderr.decode()}",
                    )
            finally:
                os.unlink(temp_path)

            return ToolResult(
                success=True,
                output=f"Cron job added: {schedule} {command}",
                error=None,
            )

        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error="crontab command not found",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class CronRemoveTool(Tool):
    """Remove a cron job by line number or pattern."""

    name = "cron_remove"
    description = "Remove a cron job by line number or matching pattern"
    parameters = {
        "type": "object",
        "properties": {
            "line_number": {
                "type": "integer",
                "description": "Line number to remove (1-indexed)",
            },
            "pattern": {
                "type": "string",
                "description": "Pattern to match and remove (removes all matching lines)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        line_number: int | None = None,
        pattern: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Remove a cron job."""
        if line_number is None and pattern is None:
            return ToolResult(
                success=False,
                output="",
                error="Must specify either line_number or pattern",
            )

        config = SindriConfig.load()
        access_result = check_system_access(
            config,
            f"remove cron job (line={line_number}, pattern={pattern})",
            is_modification=True,
        )

        if not access_result.allowed:
            return ToolResult(success=False, output="", error=access_result.reason)

        try:
            # Get existing crontab
            proc = await asyncio.create_subprocess_exec(
                "crontab",
                "-l",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to read crontab: {stderr.decode()}",
                )

            lines = stdout.decode().split("\n")
            removed_count = 0

            if line_number is not None:
                if line_number < 1 or line_number > len(lines):
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Line number {line_number} out of range (1-{len(lines)})",
                    )
                removed_line = lines.pop(line_number - 1)
                removed_count = 1
            else:
                # Remove by pattern
                new_lines = []
                for line in lines:
                    if pattern and pattern in line:
                        removed_count += 1
                    else:
                        new_lines.append(line)
                lines = new_lines

            if removed_count == 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"No matching cron jobs found for pattern: {pattern}",
                )

            # Write updated crontab
            new_crontab = "\n".join(lines)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".cron", delete=False) as f:
                f.write(new_crontab)
                temp_path = f.name

            try:
                proc = await asyncio.create_subprocess_exec(
                    "crontab",
                    temp_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()

                if proc.returncode != 0:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Failed to update crontab: {stderr.decode()}",
                    )
            finally:
                os.unlink(temp_path)

            return ToolResult(
                success=True,
                output=f"Removed {removed_count} cron job(s)",
                error=None,
            )

        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error="crontab command not found",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class TimerListTool(Tool):
    """List systemd user timers."""

    name = "timer_list"
    description = "List systemd user timers"
    parameters = {
        "type": "object",
        "properties": {
            "all": {
                "type": "boolean",
                "description": "Show all timers including inactive",
            },
        },
        "required": [],
    }

    async def execute(self, all: bool = False, **kwargs: Any) -> ToolResult:
        """List systemd user timers."""
        try:
            cmd = ["systemctl", "--user", "list-timers"]
            if all:
                cmd.append("--all")

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to list timers: {stderr.decode()}",
                )

            return ToolResult(success=True, output=stdout.decode(), error=None)

        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error="systemctl command not found",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class TimerCreateTool(Tool):
    """Create a systemd user timer."""

    name = "timer_create"
    description = "Create a systemd user timer with associated service"
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Timer name (without .timer extension)",
            },
            "description": {
                "type": "string",
                "description": "Description of the timer",
            },
            "on_calendar": {
                "type": "string",
                "description": "Calendar schedule (e.g., 'hourly', 'daily', '*:0/15' for every 15 min)",
            },
            "on_boot_sec": {
                "type": "string",
                "description": "Time after boot to trigger (e.g., '5min')",
            },
            "command": {
                "type": "string",
                "description": "Command to execute",
            },
            "persistent": {
                "type": "boolean",
                "description": "Run immediately if last run was missed",
            },
        },
        "required": ["name", "command"],
    }

    async def execute(
        self,
        name: str,
        command: str,
        description: str = "",
        on_calendar: str | None = None,
        on_boot_sec: str | None = None,
        persistent: bool = True,
        **kwargs: Any,
    ) -> ToolResult:
        """Create a systemd user timer."""
        config = SindriConfig.load()
        access_result = check_system_access(
            config,
            f"create systemd timer '{name}'",
            is_modification=True,
        )

        if not access_result.allowed:
            return ToolResult(success=False, output="", error=access_result.reason)

        if not on_calendar and not on_boot_sec:
            return ToolResult(
                success=False,
                output="",
                error="Must specify either on_calendar or on_boot_sec",
            )

        # Sanitize name
        name = re.sub(r"[^a-zA-Z0-9_-]", "", name)
        if not name:
            return ToolResult(
                success=False,
                output="",
                error="Invalid timer name",
            )

        try:
            # Create user systemd directory
            user_systemd = Path.home() / ".config" / "systemd" / "user"
            user_systemd.mkdir(parents=True, exist_ok=True)

            # Create service unit
            service_content = f"""[Unit]
Description={description or f"Service for {name}"}

[Service]
Type=oneshot
ExecStart={command}
"""
            service_path = user_systemd / f"{name}.service"
            service_path.write_text(service_content)

            # Create timer unit
            timer_lines = [
                "[Unit]",
                f"Description={description or f'Timer for {name}'}",
                "",
                "[Timer]",
            ]
            if on_calendar:
                timer_lines.append(f"OnCalendar={on_calendar}")
            if on_boot_sec:
                timer_lines.append(f"OnBootSec={on_boot_sec}")
            if persistent:
                timer_lines.append("Persistent=true")
            timer_lines.extend(["", "[Install]", "WantedBy=timers.target"])

            timer_path = user_systemd / f"{name}.timer"
            timer_path.write_text("\n".join(timer_lines) + "\n")

            # Reload daemon
            proc = await asyncio.create_subprocess_exec(
                "systemctl",
                "--user",
                "daemon-reload",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            # Enable and start timer
            proc = await asyncio.create_subprocess_exec(
                "systemctl",
                "--user",
                "enable",
                "--now",
                f"{name}.timer",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Timer created but failed to enable: {stderr.decode()}",
                )

            return ToolResult(
                success=True,
                output=f"Created and enabled timer '{name}.timer'\nService: {service_path}\nTimer: {timer_path}",
                error=None,
            )

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class TimerRemoveTool(Tool):
    """Remove a systemd user timer."""

    name = "timer_remove"
    description = "Remove a systemd user timer and its associated service"
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Timer name (without .timer extension)",
            },
        },
        "required": ["name"],
    }

    async def execute(self, name: str, **kwargs: Any) -> ToolResult:
        """Remove a systemd user timer."""
        config = SindriConfig.load()
        access_result = check_system_access(
            config,
            f"remove systemd timer '{name}'",
            is_modification=True,
        )

        if not access_result.allowed:
            return ToolResult(success=False, output="", error=access_result.reason)

        # Sanitize name
        name = re.sub(r"[^a-zA-Z0-9_-]", "", name)
        if not name:
            return ToolResult(
                success=False,
                output="",
                error="Invalid timer name",
            )

        try:
            user_systemd = Path.home() / ".config" / "systemd" / "user"
            timer_path = user_systemd / f"{name}.timer"
            service_path = user_systemd / f"{name}.service"

            # Stop and disable timer
            proc = await asyncio.create_subprocess_exec(
                "systemctl",
                "--user",
                "disable",
                "--now",
                f"{name}.timer",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            # Remove files
            removed = []
            if timer_path.exists():
                timer_path.unlink()
                removed.append(str(timer_path))
            if service_path.exists():
                service_path.unlink()
                removed.append(str(service_path))

            if not removed:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Timer '{name}' not found",
                )

            # Reload daemon
            proc = await asyncio.create_subprocess_exec(
                "systemctl",
                "--user",
                "daemon-reload",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            return ToolResult(
                success=True,
                output=f"Removed timer '{name}'\nDeleted: {', '.join(removed)}",
                error=None,
            )

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class AtScheduleTool(Tool):
    """Schedule a one-time task using 'at'."""

    name = "at_schedule"
    description = "Schedule a one-time task to run at a specific time"
    parameters = {
        "type": "object",
        "properties": {
            "time": {
                "type": "string",
                "description": "When to run (e.g., 'now + 1 hour', '10:30', 'tomorrow', '2pm + 3 days')",
            },
            "command": {
                "type": "string",
                "description": "Command to execute",
            },
        },
        "required": ["time", "command"],
    }

    async def execute(self, time: str, command: str, **kwargs: Any) -> ToolResult:
        """Schedule a one-time task."""
        config = SindriConfig.load()
        access_result = check_system_access(
            config,
            f"schedule task at '{time}': {command}",
            is_modification=True,
        )

        if not access_result.allowed:
            return ToolResult(success=False, output="", error=access_result.reason)

        try:
            # 'at' reads command from stdin
            proc = await asyncio.create_subprocess_exec(
                "at",
                time,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate(input=command.encode())

            # 'at' outputs job info to stderr (not an error)
            output = stderr.decode() if stderr else stdout.decode()

            if proc.returncode != 0 and "job" not in output.lower():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to schedule task: {output}",
                )

            return ToolResult(
                success=True,
                output=f"Scheduled task:\n{output.strip()}",
                error=None,
            )

        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error="'at' command not found. Install with: pacman -S at",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class AtListTool(Tool):
    """List scheduled 'at' jobs."""

    name = "at_list"
    description = "List all scheduled 'at' jobs for the current user"
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """List scheduled at jobs."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "atq",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to list jobs: {stderr.decode()}",
                )

            output = stdout.decode()
            if not output.strip():
                return ToolResult(
                    success=True,
                    output="No scheduled 'at' jobs.",
                    error=None,
                )

            return ToolResult(success=True, output=output, error=None)

        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error="'atq' command not found. Install with: pacman -S at",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class AtRemoveTool(Tool):
    """Remove a scheduled 'at' job."""

    name = "at_remove"
    description = "Remove a scheduled 'at' job by job number"
    parameters = {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "integer",
                "description": "Job number to remove (from 'at_list')",
            },
        },
        "required": ["job_id"],
    }

    async def execute(self, job_id: int, **kwargs: Any) -> ToolResult:
        """Remove a scheduled at job."""
        config = SindriConfig.load()
        access_result = check_system_access(
            config,
            f"remove scheduled job {job_id}",
            is_modification=True,
        )

        if not access_result.allowed:
            return ToolResult(success=False, output="", error=access_result.reason)

        try:
            proc = await asyncio.create_subprocess_exec(
                "atrm",
                str(job_id),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to remove job: {stderr.decode()}",
                )

            return ToolResult(
                success=True,
                output=f"Removed job {job_id}",
                error=None,
            )

        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error="'atrm' command not found. Install with: pacman -S at",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


# Export all scheduling tools
SCHEDULING_TOOLS = [
    CronListTool,
    CronAddTool,
    CronRemoveTool,
    TimerListTool,
    TimerCreateTool,
    TimerRemoveTool,
    AtScheduleTool,
    AtListTool,
    AtRemoveTool,
]
