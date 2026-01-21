"""Shell execution tool for Sindri."""

import asyncio
import structlog

from sindri.config import SindriConfig
from sindri.core.access import check_system_access
from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


class ShellTool(Tool):
    """Execute shell commands."""

    name = "shell"
    description = "Execute a shell command and return the output"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {
                "type": "integer",
                "description": "Command timeout in seconds (default: 300, max: 3600)",
            },
        },
        "required": ["command"],
    }

    # Default timeout in seconds (5 minutes)
    DEFAULT_TIMEOUT = 300
    # Maximum allowed timeout (1 hour)
    MAX_TIMEOUT = 3600

    async def execute(self, command: str, timeout: int | None = None) -> ToolResult:
        """Execute shell command with timeout support.

        Args:
            command: Shell command to execute
            timeout: Command timeout in seconds (default: 300, max: 3600)

        Returns:
            ToolResult with command output or error
        """
        # Check access control - all shell commands are modifications
        config = SindriConfig.load()
        access_result = check_system_access(
            config,
            f"execute shell command: {command[:50]}{'...' if len(command) > 50 else ''}",
            is_modification=True,
        )

        if not access_result.allowed:
            log.warning(
                "shell_access_denied",
                command=command,
                reason=access_result.reason,
            )
            return ToolResult(
                success=False,
                output="",
                error=access_result.reason,
            )

        # Validate and cap timeout
        if timeout is None:
            timeout = self.DEFAULT_TIMEOUT
        timeout = max(1, min(timeout, self.MAX_TIMEOUT))

        try:
            log.info(
                "shell_execute",
                command=command,
                timeout=timeout,
                work_dir=str(self.work_dir) if self.work_dir else None,
            )

            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.work_dir) if self.work_dir else None,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                # Kill the process on timeout
                process.kill()
                await process.wait()  # Ensure process is cleaned up
                log.warning(
                    "shell_timeout",
                    command=command,
                    timeout=timeout,
                )
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Command timed out after {timeout} seconds",
                    metadata={"timeout": timeout, "timed_out": True},
                )

            stdout_text = stdout.decode() if stdout else ""
            stderr_text = stderr.decode() if stderr else ""

            if process.returncode == 0:
                log.info(
                    "shell_success", command=command, returncode=process.returncode
                )
                return ToolResult(
                    success=True,
                    output=stdout_text,
                    metadata={
                        "returncode": process.returncode,
                        "stderr": stderr_text,
                        "timeout": timeout,
                    },
                )
            else:
                log.warning(
                    "shell_failed", command=command, returncode=process.returncode
                )
                return ToolResult(
                    success=False,
                    output=stdout_text,
                    error=f"Command failed with exit code {process.returncode}: {stderr_text}",
                    metadata={"returncode": process.returncode, "timeout": timeout},
                )

        except Exception as e:
            log.error("shell_error", command=command, error=str(e))
            return ToolResult(
                success=False, output="", error=f"Failed to execute command: {str(e)}"
            )
