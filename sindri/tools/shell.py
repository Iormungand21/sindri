"""Shell execution tool for Sindri."""

import asyncio
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


class ShellTool(Tool):
    """Execute shell commands."""

    name = "shell"
    description = "Execute a shell command and return the output"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"}
        },
        "required": ["command"],
    }

    async def execute(self, command: str) -> ToolResult:
        """Execute shell command."""
        try:
            log.info(
                "shell_execute",
                command=command,
                work_dir=str(self.work_dir) if self.work_dir else None,
            )

            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.work_dir) if self.work_dir else None,
            )

            stdout, stderr = await process.communicate()

            stdout_text = stdout.decode() if stdout else ""
            stderr_text = stderr.decode() if stderr else ""

            if process.returncode == 0:
                log.info(
                    "shell_success", command=command, returncode=process.returncode
                )
                return ToolResult(
                    success=True,
                    output=stdout_text,
                    metadata={"returncode": process.returncode, "stderr": stderr_text},
                )
            else:
                log.warning(
                    "shell_failed", command=command, returncode=process.returncode
                )
                return ToolResult(
                    success=False,
                    output=stdout_text,
                    error=f"Command failed with exit code {process.returncode}: {stderr_text}",
                    metadata={"returncode": process.returncode},
                )

        except Exception as e:
            log.error("shell_error", command=command, error=str(e))
            return ToolResult(
                success=False, output="", error=f"Failed to execute command: {str(e)}"
            )
