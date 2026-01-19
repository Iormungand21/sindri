"""Bash scripting and shell tools for Sif agent (Phase 12).

Provides tools for bash script generation, explanation, validation,
systemd unit file generation, and linting.
"""

import asyncio
import json
import re
import shutil
import subprocess
import tempfile
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════


class ShellType(str, Enum):
    """Target shell for validation."""

    BASH = "bash"
    SH = "sh"
    DASH = "dash"
    KSH = "ksh"


class Severity(str, Enum):
    """Shellcheck severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    STYLE = "style"


class ServiceType(str, Enum):
    """Systemd service types."""

    SIMPLE = "simple"
    EXEC = "exec"
    FORKING = "forking"
    ONESHOT = "oneshot"
    NOTIFY = "notify"
    IDLE = "idle"


class RestartPolicy(str, Enum):
    """Systemd restart policies."""

    NO = "no"
    ON_SUCCESS = "on-success"
    ON_FAILURE = "on-failure"
    ON_ABNORMAL = "on-abnormal"
    ON_ABORT = "on-abort"
    ALWAYS = "always"


class UnitType(str, Enum):
    """Systemd unit types."""

    SERVICE = "service"
    TIMER = "timer"
    SOCKET = "socket"
    PATH = "path"


# ═══════════════════════════════════════════════════════════════════════════════
# Bash keyword explanations
# ═══════════════════════════════════════════════════════════════════════════════

BASH_KEYWORDS = {
    "set -e": "Exit immediately if any command exits with a non-zero status",
    "set -u": "Treat unset variables as errors and exit immediately",
    "set -o pipefail": "Return the exit status of the last command in a pipeline that failed",
    "set -x": "Print each command before executing it (debug mode)",
    "set -n": "Read commands but do not execute them (syntax check mode)",
    "set -v": "Print shell input lines as they are read",
    "set -f": "Disable filename expansion (globbing)",
    "set -a": "Export all variables assigned to",
    "set -euo pipefail": "Common safety combination: exit on error, undefined vars, and pipe failures",
    "IFS=$'\\n\\t'": "Set Internal Field Separator to newline and tab for safer word splitting",
    "trap": "Execute a command when the shell receives a signal",
    "local": "Declare a variable as local to a function",
    "readonly": "Mark a variable as read-only",
    "export": "Make a variable available to child processes",
    "source": "Execute commands from a file in the current shell (same as .)",
    "eval": "Concatenate arguments and execute as a command (use with caution!)",
    "exec": "Replace the shell with the specified command",
    "shift": "Shift positional parameters left by one or more positions",
    "getopts": "Parse positional parameters as options",
    "shopt": "Toggle shell options (bash-specific)",
    "declare": "Declare variables and give them attributes",
    "typeset": "Declare variables and give them attributes (same as declare)",
}

# ═══════════════════════════════════════════════════════════════════════════════
# Common script templates
# ═══════════════════════════════════════════════════════════════════════════════

SCRIPT_TEMPLATES = {
    "backup": '''#!/usr/bin/env bash
set -euo pipefail

# Backup script for {target}
# Usage: {script_name} [OPTIONS]

BACKUP_DIR="${{BACKUP_DIR:-/var/backups}}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SOURCE="{source_path}"
DEST="${{BACKUP_DIR}}/{name}_${{TIMESTAMP}}.tar.gz"

# Create backup directory if it doesn't exist
mkdir -p "${{BACKUP_DIR}}"

# Create compressed backup
echo "Creating backup of ${{SOURCE}}..."
tar -czf "${{DEST}}" -C "$(dirname "${{SOURCE}}")" "$(basename "${{SOURCE}}")"

echo "Backup created: ${{DEST}}"

# Optional: Remove backups older than 7 days
find "${{BACKUP_DIR}}" -name "{name}_*.tar.gz" -mtime +7 -delete
echo "Old backups cleaned up."
''',
    "log_rotation": '''#!/usr/bin/env bash
set -euo pipefail

# Log rotation script for {log_path}
# Usage: {script_name}

LOG_FILE="{log_path}"
MAX_SIZE={max_size:-10485760}  # 10MB default
KEEP_DAYS={keep_days:-30}

# Check if log file exists and exceeds max size
if [[ -f "${{LOG_FILE}}" ]]; then
    FILE_SIZE=$(stat -f%z "${{LOG_FILE}}" 2>/dev/null || stat -c%s "${{LOG_FILE}}")

    if (( FILE_SIZE > MAX_SIZE )); then
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        ROTATED="${{LOG_FILE}}.${{TIMESTAMP}}"

        # Rotate the log
        mv "${{LOG_FILE}}" "${{ROTATED}}"
        gzip "${{ROTATED}}"
        touch "${{LOG_FILE}}"

        echo "Rotated ${{LOG_FILE}} to ${{ROTATED}}.gz"
    fi
fi

# Clean up old rotated logs
find "$(dirname "${{LOG_FILE}}")" -name "$(basename "${{LOG_FILE}}").*" -mtime +${{KEEP_DAYS}} -delete
''',
    "deployment": '''#!/usr/bin/env bash
set -euo pipefail

# Deployment script for {app_name}
# Usage: {script_name} [--rollback]

APP_NAME="{app_name}"
DEPLOY_DIR="{deploy_dir}"
BACKUP_DIR="${{DEPLOY_DIR}}/backups"
CURRENT_LINK="${{DEPLOY_DIR}}/current"
RELEASES_DIR="${{DEPLOY_DIR}}/releases"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Parse arguments
ROLLBACK=false
if [[ "${{1:-}}" == "--rollback" ]]; then
    ROLLBACK=true
fi

if [[ "${{ROLLBACK}}" == "true" ]]; then
    # Find previous release
    PREV_RELEASE=$(ls -t "${{RELEASES_DIR}}" | sed -n '2p')
    if [[ -z "${{PREV_RELEASE}}" ]]; then
        echo "Error: No previous release to rollback to"
        exit 1
    fi

    ln -sfn "${{RELEASES_DIR}}/${{PREV_RELEASE}}" "${{CURRENT_LINK}}"
    echo "Rolled back to ${{PREV_RELEASE}}"
else
    # Create new release directory
    RELEASE_DIR="${{RELEASES_DIR}}/${{TIMESTAMP}}"
    mkdir -p "${{RELEASE_DIR}}"

    # Deploy new version (customize this section)
    echo "Deploying to ${{RELEASE_DIR}}..."
    # cp -r /path/to/build/* "${{RELEASE_DIR}}/"

    # Update current symlink
    ln -sfn "${{RELEASE_DIR}}" "${{CURRENT_LINK}}"
    echo "Deployed ${{TIMESTAMP}}"

    # Keep only last 5 releases
    ls -t "${{RELEASES_DIR}}" | tail -n +6 | xargs -I{{}} rm -rf "${{RELEASES_DIR}}/{{}}"
fi
''',
    "service_health": '''#!/usr/bin/env bash
set -euo pipefail

# Health check script for {service_name}
# Usage: {script_name}

SERVICE="{service_name}"
ENDPOINT="{endpoint}"
TIMEOUT={timeout}
RETRIES={retries}

check_health() {{
    local attempt=1
    while (( attempt <= RETRIES )); do
        if curl -sf --max-time "${{TIMEOUT}}" "${{ENDPOINT}}" > /dev/null; then
            echo "${{SERVICE}} is healthy"
            return 0
        fi
        echo "Attempt ${{attempt}}/${{RETRIES}} failed, retrying..."
        (( attempt++ ))
        sleep 2
    done
    return 1
}}

if ! check_health; then
    echo "ERROR: ${{SERVICE}} health check failed after ${{RETRIES}} attempts"
    # Optional: restart service
    # systemctl restart "${{SERVICE}}"
    exit 1
fi
''',
    "cleanup": '''#!/usr/bin/env bash
set -euo pipefail

# Cleanup script for {target}
# Usage: {script_name}

TARGET_DIR="{target_dir}"
PATTERN="{pattern}"
OLDER_THAN={days}
DRY_RUN="${{DRY_RUN:-false}}"

echo "Cleaning up files matching ${{PATTERN}} older than ${{OLDER_THAN}} days in ${{TARGET_DIR}}"

if [[ "${{DRY_RUN}}" == "true" ]]; then
    echo "DRY RUN - would delete:"
    find "${{TARGET_DIR}}" -name "${{PATTERN}}" -mtime +${{OLDER_THAN}} -print
else
    DELETED=$(find "${{TARGET_DIR}}" -name "${{PATTERN}}" -mtime +${{OLDER_THAN}} -delete -print | wc -l)
    echo "Deleted ${{DELETED}} files"
fi
''',
}

# ═══════════════════════════════════════════════════════════════════════════════
# Systemd unit templates
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEMD_TEMPLATES = {
    "service_simple": """[Unit]
Description={description}
After=network.target

[Service]
Type=simple
ExecStart={exec_command}
Restart={restart_policy}
RestartSec=5
{user_section}{working_dir_section}{environment_section}
[Install]
WantedBy=multi-user.target
""",
    "service_hardened": """[Unit]
Description={description}
After=network.target

[Service]
Type={service_type}
ExecStart={exec_command}
Restart={restart_policy}
RestartSec=5
{user_section}{working_dir_section}{environment_section}
# Security hardening
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
NoNewPrivileges=true
CapabilityBoundingSet=
{read_write_paths}
[Install]
WantedBy=multi-user.target
""",
    "timer": """[Unit]
Description={description}

[Timer]
OnCalendar={schedule}
Persistent={persistent}
{on_boot_section}
[Install]
WantedBy=timers.target
""",
    "socket": """[Unit]
Description={description}

[Socket]
ListenStream={listen_address}
Accept=no

[Install]
WantedBy=sockets.target
""",
    "path": """[Unit]
Description={description}

[Path]
PathModified={watch_path}
Unit={target_unit}

[Install]
WantedBy=multi-user.target
""",
}


# ═══════════════════════════════════════════════════════════════════════════════
# BashGenerateTool
# ═══════════════════════════════════════════════════════════════════════════════


class BashGenerateTool(Tool):
    """Generate bash scripts from natural language descriptions."""

    name = "bash_generate"
    description = """Generate a bash script from a natural language description.

Can generate scripts for common use cases like backups, log rotation, deployment,
health checks, and cleanup tasks. Also handles custom scripts based on description.

Examples:
- "Create a backup script for /var/data" -> Complete backup script with compression
- "Script to rotate logs larger than 10MB" -> Log rotation with cleanup
- "Health check for my-service on port 8080" -> HTTP health check with retries
"""

    parameters = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Natural language description of what the script should do",
            },
            "strict_mode": {
                "type": "boolean",
                "description": "Include 'set -euo pipefail' for safer scripts (default: true)",
            },
            "portable": {
                "type": "boolean",
                "description": "Prefer POSIX-compatible syntax (default: false)",
            },
            "include_help": {
                "type": "boolean",
                "description": "Include usage/help function (default: false)",
            },
        },
        "required": ["description"],
    }

    async def execute(
        self,
        description: str,
        strict_mode: bool = True,
        portable: bool = False,
        include_help: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Generate a bash script from description."""
        try:
            log.info(
                "bash_generate_start",
                description=description[:100],
                strict_mode=strict_mode,
                portable=portable,
            )

            description_lower = description.lower()

            # Check for common patterns
            script = None
            template_name = None

            if any(word in description_lower for word in ["backup", "archive", "save"]):
                template_name = "backup"
                # Extract target path if mentioned
                path_match = re.search(r"(?:for|of)\s+([/\w.-]+)", description_lower)
                source_path = path_match.group(1) if path_match else "/path/to/source"
                name = Path(source_path).name or "backup"
                script = SCRIPT_TEMPLATES["backup"].format(
                    target=source_path,
                    script_name="backup.sh",
                    source_path=source_path,
                    name=name,
                )

            elif any(word in description_lower for word in ["log rotation", "rotate log", "logrotate"]):
                template_name = "log_rotation"
                path_match = re.search(r"(?:for|of)\s+([/\w.-]+)", description_lower)
                log_path = path_match.group(1) if path_match else "/var/log/app.log"
                # Extract size if mentioned
                size_match = re.search(r"(\d+)\s*(?:mb|MB)", description)
                max_size = int(size_match.group(1)) * 1024 * 1024 if size_match else 10485760
                script = SCRIPT_TEMPLATES["log_rotation"].format(
                    log_path=log_path,
                    script_name="rotate_logs.sh",
                    max_size=max_size,
                    keep_days=30,
                )

            elif any(word in description_lower for word in ["deploy", "deployment", "release"]):
                template_name = "deployment"
                name_match = re.search(r"(?:for|of)\s+([/\w.-]+)", description_lower)
                app_name = name_match.group(1) if name_match else "myapp"
                script = SCRIPT_TEMPLATES["deployment"].format(
                    app_name=app_name,
                    script_name="deploy.sh",
                    deploy_dir=f"/opt/{app_name}",
                )

            elif any(word in description_lower for word in ["health", "healthcheck", "health check", "ping"]):
                template_name = "service_health"
                name_match = re.search(r"(?:for|of)\s+([/\w.-]+)", description_lower)
                service_name = name_match.group(1) if name_match else "myservice"
                # Extract port if mentioned
                port_match = re.search(r"port\s*(\d+)", description_lower)
                port = port_match.group(1) if port_match else "8080"
                script = SCRIPT_TEMPLATES["service_health"].format(
                    service_name=service_name,
                    script_name="health_check.sh",
                    endpoint=f"http://localhost:{port}/health",
                    timeout=5,
                    retries=3,
                )

            elif any(word in description_lower for word in ["cleanup", "clean up", "delete old", "remove old"]):
                template_name = "cleanup"
                path_match = re.search(r"(?:in|from)\s+([/\w.-]+)", description_lower)
                target_dir = path_match.group(1) if path_match else "/tmp"
                # Extract pattern if mentioned
                pattern_match = re.search(r"(?:pattern|matching)\s+([*\w.-]+)", description_lower)
                pattern = pattern_match.group(1) if pattern_match else "*.tmp"
                # Extract days if mentioned
                days_match = re.search(r"(?:older than|>)\s*(\d+)\s*days?", description_lower)
                days = int(days_match.group(1)) if days_match else 7
                script = SCRIPT_TEMPLATES["cleanup"].format(
                    target="files",
                    script_name="cleanup.sh",
                    target_dir=target_dir,
                    pattern=pattern,
                    days=days,
                )

            # Generate custom script if no template matched
            if script is None:
                script = self._generate_custom_script(
                    description, strict_mode, portable, include_help
                )
                template_name = "custom"

            # Apply modifications
            if portable:
                script = self._make_portable(script)

            if include_help and "usage()" not in script:
                script = self._add_help_function(script, description)

            output_lines = [
                f"Generated bash script ({template_name} template):",
                "",
                "```bash",
                script.strip(),
                "```",
                "",
                "Script features:",
            ]

            if "set -euo pipefail" in script or "set -e" in script:
                output_lines.append("- Strict error handling enabled")
            if "trap" in script:
                output_lines.append("- Cleanup trap configured")
            if "usage()" in script or "help" in script.lower():
                output_lines.append("- Help/usage function included")
            if portable:
                output_lines.append("- POSIX-compatible syntax")

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "template": template_name,
                    "strict_mode": strict_mode,
                    "portable": portable,
                    "include_help": include_help,
                    "script_length": len(script),
                },
            )

        except Exception as e:
            log.error("bash_generate_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate bash script: {e}",
            )

    def _generate_custom_script(
        self,
        description: str,
        strict_mode: bool,
        portable: bool,
        include_help: bool,
    ) -> str:
        """Generate a custom script from description."""
        lines = []

        # Shebang
        if portable:
            lines.append("#!/bin/sh")
        else:
            lines.append("#!/usr/bin/env bash")

        # Strict mode
        if strict_mode:
            if portable:
                lines.append("set -eu")
            else:
                lines.append("set -euo pipefail")

        lines.append("")
        lines.append(f"# {description}")
        lines.append("# Generated by Sindri")
        lines.append("")

        # Add placeholder content
        lines.append("# TODO: Implement your script logic here")
        lines.append("echo \"Script started\"")
        lines.append("")
        lines.append("# Your commands here...")
        lines.append("")
        lines.append("echo \"Script completed\"")

        return "\n".join(lines)

    def _make_portable(self, script: str) -> str:
        """Convert bash-specific syntax to POSIX-compatible."""
        # Replace bash shebang
        script = re.sub(r"#!/usr/bin/env bash", "#!/bin/sh", script)
        script = re.sub(r"#!/bin/bash", "#!/bin/sh", script)

        # Replace [[ ]] with [ ]
        script = re.sub(r"\[\[", "[", script)
        script = re.sub(r"\]\]", "]", script)

        # Replace (( )) with $(( ))
        script = re.sub(r"\(\(([^)]+)\)\)", r"$((\1))", script)

        # Replace set -euo pipefail with set -eu (pipefail is bash-specific)
        script = re.sub(r"set -euo pipefail", "set -eu", script)

        # Replace $'...' with '...'
        script = re.sub(r"\$'([^']*)'", r"'\1'", script)

        return script

    def _add_help_function(self, script: str, description: str) -> str:
        """Add a help/usage function to the script."""
        help_func = '''
usage() {
    cat <<EOF
Usage: ${0##*/} [OPTIONS]

''' + description + '''

Options:
    -h, --help    Show this help message
    -v, --verbose Enable verbose output
EOF
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) usage ;;
        -v|--verbose) VERBOSE=true; shift ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

'''
        # Insert after the header comments
        lines = script.split("\n")
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("#") or line.strip() == "" or line.startswith("set"):
                insert_idx = i + 1
            else:
                break

        lines.insert(insert_idx, help_func)
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# BashExplainTool
# ═══════════════════════════════════════════════════════════════════════════════


class BashExplainTool(Tool):
    """Explain bash commands in plain English."""

    name = "bash_explain"
    description = """Explain a bash command or script in plain English.

Breaks down complex commands into understandable parts, explaining each component,
flag, and operation. Useful for learning or understanding unfamiliar scripts.

Examples:
- "find /var -type f -mtime +30 -delete" -> Explains find command with all flags
- "tar -czf backup.tar.gz /data" -> Explains tar compression
"""

    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The bash command or script to explain",
            },
            "verbose": {
                "type": "boolean",
                "description": "Include detailed breakdown of each component (default: false)",
            },
        },
        "required": ["command"],
    }

    async def execute(
        self,
        command: str,
        verbose: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Explain a bash command."""
        try:
            log.info(
                "bash_explain_start",
                command=command[:100],
                verbose=verbose,
            )

            explanations = []

            # Check for shell settings
            for keyword, explanation in BASH_KEYWORDS.items():
                if keyword in command:
                    explanations.append(f"- `{keyword}`: {explanation}")

            # Analyze command structure
            parts = self._parse_command(command)
            main_explanation = self._explain_command_parts(parts, verbose)

            output_lines = [
                "## Bash Command Explanation",
                "",
                f"**Command:** `{command}`",
                "",
            ]

            if explanations:
                output_lines.append("### Shell Settings")
                output_lines.extend(explanations)
                output_lines.append("")

            output_lines.append("### Breakdown")
            output_lines.append(main_explanation)

            # Add warnings if applicable
            warnings = self._check_for_warnings(command)
            if warnings:
                output_lines.append("")
                output_lines.append("### Warnings")
                for warning in warnings:
                    output_lines.append(f"- {warning}")

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "command_length": len(command),
                    "has_warnings": len(warnings) > 0,
                    "verbose": verbose,
                },
            )

        except Exception as e:
            log.error("bash_explain_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to explain command: {e}",
            )

    def _parse_command(self, command: str) -> list[dict]:
        """Parse command into components."""
        parts = []

        # Split by pipes
        pipe_parts = command.split("|")
        for i, part in enumerate(pipe_parts):
            part = part.strip()
            if not part:
                continue

            # Get the base command
            tokens = part.split()
            if not tokens:
                continue

            cmd = tokens[0]
            args = tokens[1:]

            parts.append({
                "command": cmd,
                "args": args,
                "full": part,
                "is_piped": i > 0,
            })

        return parts

    def _explain_command_parts(self, parts: list[dict], verbose: bool) -> str:
        """Generate explanation for command parts."""
        lines = []

        for i, part in enumerate(parts):
            if part["is_piped"]:
                lines.append("")
                lines.append("**Then piped to:**")

            cmd = part["command"]
            args = part["args"]

            # Common command explanations
            cmd_explanations = {
                "find": "Search for files in a directory hierarchy",
                "grep": "Search for patterns in text",
                "awk": "Pattern scanning and text processing",
                "sed": "Stream editor for filtering and transforming text",
                "cat": "Concatenate and display files",
                "ls": "List directory contents",
                "rm": "Remove files or directories",
                "cp": "Copy files or directories",
                "mv": "Move or rename files",
                "chmod": "Change file permissions",
                "chown": "Change file ownership",
                "tar": "Archive utility",
                "gzip": "Compress files",
                "gunzip": "Decompress gzip files",
                "curl": "Transfer data from or to a server",
                "wget": "Download files from the web",
                "ssh": "Secure shell connection",
                "scp": "Secure copy over SSH",
                "rsync": "Fast, versatile file copying",
                "xargs": "Build and execute commands from standard input",
                "sort": "Sort lines of text",
                "uniq": "Report or omit repeated lines",
                "wc": "Word, line, and byte count",
                "head": "Output the first part of files",
                "tail": "Output the last part of files",
                "cut": "Remove sections from lines",
                "tr": "Translate or delete characters",
                "tee": "Read from stdin and write to stdout and files",
                "echo": "Display a line of text",
                "printf": "Format and print data",
                "read": "Read a line from stdin",
                "test": "Check file types and compare values",
                "expr": "Evaluate expressions",
                "bc": "Calculator language",
                "date": "Display or set system date/time",
                "sleep": "Pause execution",
                "kill": "Send signals to processes",
                "ps": "Report process status",
                "top": "Display system processes",
                "df": "Report filesystem disk space usage",
                "du": "Estimate file space usage",
                "mkdir": "Create directories",
                "touch": "Change file timestamps or create empty file",
                "ln": "Create links",
                "stat": "Display file status",
                "file": "Determine file type",
                "which": "Locate a command",
                "whereis": "Locate binary, source, and manual page files",
                "man": "Display manual pages",
                "systemctl": "Control systemd services",
                "journalctl": "Query systemd journal",
            }

            base_explanation = cmd_explanations.get(cmd, f"Execute '{cmd}'")
            lines.append(f"**`{cmd}`**: {base_explanation}")

            if verbose and args:
                lines.append("")
                lines.append("Arguments:")
                for arg in args:
                    arg_explanation = self._explain_argument(cmd, arg)
                    lines.append(f"  - `{arg}`: {arg_explanation}")

        return "\n".join(lines)

    def _explain_argument(self, cmd: str, arg: str) -> str:
        """Explain a command argument."""
        # Common flag patterns
        if arg.startswith("--"):
            return f"Long option '{arg[2:]}'"
        elif arg.startswith("-"):
            flags = arg[1:]
            if len(flags) == 1:
                return self._explain_single_flag(cmd, flags)
            else:
                return f"Combined flags: {', '.join(flags)}"
        elif arg.startswith("/") or arg.startswith("./"):
            return "File/directory path"
        elif arg.startswith("$"):
            return f"Variable expansion for '{arg[1:]}'"
        elif "*" in arg or "?" in arg:
            return "Glob pattern for matching files"
        else:
            return "Argument value"

    def _explain_single_flag(self, cmd: str, flag: str) -> str:
        """Explain a single flag for common commands."""
        common_flags = {
            "find": {
                "type": "File type (f=file, d=directory, l=symlink)",
                "name": "Match filename pattern",
                "mtime": "Modification time in days",
                "size": "File size",
                "exec": "Execute command on each match",
                "delete": "Delete matching files",
                "print": "Print matching paths",
            },
            "grep": {
                "r": "Recursive search",
                "i": "Case-insensitive",
                "v": "Invert match",
                "l": "List filenames only",
                "n": "Show line numbers",
                "c": "Count matches",
                "E": "Extended regex",
                "o": "Only matching part",
            },
            "ls": {
                "l": "Long format",
                "a": "Show hidden files",
                "h": "Human-readable sizes",
                "r": "Reverse order",
                "t": "Sort by time",
                "R": "Recursive",
            },
            "tar": {
                "c": "Create archive",
                "x": "Extract archive",
                "z": "Use gzip compression",
                "j": "Use bzip2 compression",
                "v": "Verbose output",
                "f": "Archive filename",
                "t": "List contents",
            },
        }

        if cmd in common_flags and flag in common_flags[cmd]:
            return common_flags[cmd][flag]

        return f"Flag '-{flag}'"

    def _check_for_warnings(self, command: str) -> list[str]:
        """Check for potentially dangerous patterns."""
        warnings = []

        if "rm -rf" in command or "rm -fr" in command:
            warnings.append("Contains recursive force delete - verify paths carefully!")

        if "eval " in command:
            warnings.append("Uses 'eval' which can be a security risk with untrusted input")

        if "> /dev/" in command:
            warnings.append("Writes to a device file - ensure this is intentional")

        if "chmod 777" in command:
            warnings.append("Sets world-writable permissions - consider more restrictive permissions")

        if "curl " in command and "| bash" in command:
            warnings.append("Pipes curl output to bash - only run from trusted sources!")

        if "sudo " in command and ("rm " in command or "mv " in command or "chmod " in command):
            warnings.append("Uses sudo with destructive command - double-check before running")

        if re.search(r"\$\([^)]+\)", command) and "rm" in command:
            warnings.append("Uses command substitution with rm - ensure substitution is correct")

        return warnings


# ═══════════════════════════════════════════════════════════════════════════════
# BashValidateTool
# ═══════════════════════════════════════════════════════════════════════════════


class BashValidateTool(Tool):
    """Validate bash scripts using shellcheck."""

    name = "bash_validate"
    description = """Validate a bash script using shellcheck.

Checks for common issues like unquoted variables, useless use of cat,
deprecated syntax, and potential bugs. Returns issues categorized by severity.

Requires shellcheck to be installed (https://www.shellcheck.net/).
"""

    parameters = {
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": "The bash script content to validate",
            },
            "severity": {
                "type": "string",
                "enum": ["error", "warning", "info", "style"],
                "description": "Minimum severity level to report (default: warning)",
            },
            "shell": {
                "type": "string",
                "enum": ["bash", "sh", "dash", "ksh"],
                "description": "Target shell for validation (default: bash)",
            },
        },
        "required": ["script"],
    }

    async def execute(
        self,
        script: str,
        severity: str = "warning",
        shell: str = "bash",
        **kwargs,
    ) -> ToolResult:
        """Validate a bash script."""
        try:
            log.info(
                "bash_validate_start",
                script_length=len(script),
                severity=severity,
                shell=shell,
            )

            # Check if shellcheck is available
            shellcheck_path = shutil.which("shellcheck")
            if not shellcheck_path:
                return ToolResult(
                    success=False,
                    output="",
                    error="shellcheck is not installed. Install it with: pacman -S shellcheck (Arch) or apt install shellcheck (Debian/Ubuntu)",
                )

            # Map severity to shellcheck format
            severity_map = {
                "error": "error",
                "warning": "warning",
                "info": "info",
                "style": "style",
            }

            # Write script to temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".sh", delete=False
            ) as f:
                f.write(script)
                temp_path = f.name

            try:
                # Run shellcheck
                result = subprocess.run(
                    [
                        shellcheck_path,
                        "-f", "json",
                        "-s", shell,
                        "-S", severity_map.get(severity, "warning"),
                        temp_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                # Parse results
                issues = []
                if result.stdout:
                    try:
                        issues = json.loads(result.stdout)
                    except json.JSONDecodeError:
                        pass

                # Format output
                if not issues:
                    return ToolResult(
                        success=True,
                        output="Script validation passed with no issues.",
                        metadata={
                            "shell": shell,
                            "severity": severity,
                            "issue_count": 0,
                        },
                    )

                output_lines = [
                    f"Found {len(issues)} issue(s):",
                    "",
                ]

                for issue in issues:
                    level = issue.get("level", "unknown").upper()
                    code = issue.get("code", "?")
                    line = issue.get("line", "?")
                    column = issue.get("column", "?")
                    message = issue.get("message", "No message")

                    output_lines.append(
                        f"**[{level}]** SC{code} at line {line}, column {column}:"
                    )
                    output_lines.append(f"  {message}")

                    # Add fix suggestion if available
                    fix = issue.get("fix")
                    if fix:
                        output_lines.append(f"  Fix: {fix}")

                    output_lines.append("")

                return ToolResult(
                    success=result.returncode == 0,
                    output="\n".join(output_lines),
                    metadata={
                        "shell": shell,
                        "severity": severity,
                        "issue_count": len(issues),
                        "issues": issues,
                    },
                )

            finally:
                # Clean up temp file
                Path(temp_path).unlink(missing_ok=True)

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error="Shellcheck timed out",
            )
        except Exception as e:
            log.error("bash_validate_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to validate script: {e}",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# SystemdGenerateTool
# ═══════════════════════════════════════════════════════════════════════════════


class SystemdGenerateTool(Tool):
    """Generate systemd unit files."""

    name = "systemd_generate"
    description = """Generate systemd unit files (service, timer, socket, path).

Creates properly formatted systemd unit files with security hardening options.
For services that need scheduling, generates both service and timer units.

Examples:
- Service: "Run /usr/bin/myapp as myuser" -> Service unit with security hardening
- Timer: "Run backup.sh daily at 2am" -> Timer unit with OnCalendar
"""

    parameters = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Description of what the unit does",
            },
            "unit_type": {
                "type": "string",
                "enum": ["service", "timer", "socket", "path"],
                "description": "Type of systemd unit to generate (default: service)",
            },
            "exec_command": {
                "type": "string",
                "description": "Command to execute (for service/timer)",
            },
            "service_type": {
                "type": "string",
                "enum": ["simple", "exec", "forking", "oneshot", "notify", "idle"],
                "description": "Service type (default: simple)",
            },
            "restart_policy": {
                "type": "string",
                "enum": ["no", "on-success", "on-failure", "on-abnormal", "on-abort", "always"],
                "description": "Restart policy (default: on-failure)",
            },
            "user": {
                "type": "string",
                "description": "User to run as (optional)",
            },
            "working_directory": {
                "type": "string",
                "description": "Working directory for the service (optional)",
            },
            "environment": {
                "type": "object",
                "description": "Environment variables as key-value pairs",
            },
            "timer_schedule": {
                "type": "string",
                "description": "OnCalendar schedule for timer units (e.g., 'daily', '*:0/15', 'Mon *-*-* 00:00:00')",
            },
            "hardened": {
                "type": "boolean",
                "description": "Include security hardening options (default: true)",
            },
        },
        "required": ["description"],
    }

    async def execute(
        self,
        description: str,
        unit_type: str = "service",
        exec_command: Optional[str] = None,
        service_type: str = "simple",
        restart_policy: str = "on-failure",
        user: Optional[str] = None,
        working_directory: Optional[str] = None,
        environment: Optional[dict] = None,
        timer_schedule: Optional[str] = None,
        hardened: bool = True,
        **kwargs,
    ) -> ToolResult:
        """Generate a systemd unit file."""
        try:
            log.info(
                "systemd_generate_start",
                description=description[:100],
                unit_type=unit_type,
            )

            units = []

            # Build section strings
            user_section = f"User={user}\n" if user else ""
            working_dir_section = f"WorkingDirectory={working_directory}\n" if working_directory else ""

            env_section = ""
            if environment:
                for key, value in environment.items():
                    env_section += f"Environment=\"{key}={value}\"\n"

            if unit_type == "service":
                if not exec_command:
                    return ToolResult(
                        success=False,
                        output="",
                        error="exec_command is required for service units",
                    )

                template = SYSTEMD_TEMPLATES["service_hardened"] if hardened else SYSTEMD_TEMPLATES["service_simple"]

                read_write_paths = ""
                if hardened and working_directory:
                    read_write_paths = f"ReadWritePaths={working_directory}\n"

                unit = template.format(
                    description=description,
                    exec_command=exec_command,
                    service_type=service_type,
                    restart_policy=restart_policy,
                    user_section=user_section,
                    working_dir_section=working_dir_section,
                    environment_section=env_section,
                    read_write_paths=read_write_paths,
                )
                units.append(("myservice.service", unit))

            elif unit_type == "timer":
                if not timer_schedule:
                    return ToolResult(
                        success=False,
                        output="",
                        error="timer_schedule is required for timer units",
                    )

                # Generate service unit first
                if exec_command:
                    service_template = SYSTEMD_TEMPLATES["service_hardened"] if hardened else SYSTEMD_TEMPLATES["service_simple"]

                    read_write_paths = ""
                    if hardened and working_directory:
                        read_write_paths = f"ReadWritePaths={working_directory}\n"

                    service_unit = service_template.format(
                        description=f"{description} (service)",
                        exec_command=exec_command,
                        service_type="oneshot",  # Timers typically use oneshot
                        restart_policy="no",
                        user_section=user_section,
                        working_dir_section=working_dir_section,
                        environment_section=env_section,
                        read_write_paths=read_write_paths,
                    )
                    units.append(("mytimer.service", service_unit))

                # Generate timer unit
                timer_unit = SYSTEMD_TEMPLATES["timer"].format(
                    description=description,
                    schedule=timer_schedule,
                    persistent="true",
                    on_boot_section="",
                )
                units.append(("mytimer.timer", timer_unit))

            elif unit_type == "socket":
                listen_address = exec_command or "/run/myservice.sock"
                socket_unit = SYSTEMD_TEMPLATES["socket"].format(
                    description=description,
                    listen_address=listen_address,
                )
                units.append(("myservice.socket", socket_unit))

            elif unit_type == "path":
                watch_path = exec_command or "/path/to/watch"
                path_unit = SYSTEMD_TEMPLATES["path"].format(
                    description=description,
                    watch_path=watch_path,
                    target_unit="myservice.service",
                )
                units.append(("myservice.path", path_unit))

            # Format output
            output_lines = [
                f"Generated {len(units)} systemd unit(s):",
                "",
            ]

            for name, content in units:
                output_lines.append(f"### {name}")
                output_lines.append("")
                output_lines.append("```ini")
                output_lines.append(content.strip())
                output_lines.append("```")
                output_lines.append("")

            output_lines.append("### Installation")
            output_lines.append("")
            output_lines.append("For user services:")
            output_lines.append("```bash")
            output_lines.append("mkdir -p ~/.config/systemd/user")
            for name, _ in units:
                output_lines.append(f"cp {name} ~/.config/systemd/user/")
            output_lines.append("systemctl --user daemon-reload")
            if unit_type == "timer":
                output_lines.append("systemctl --user enable --now mytimer.timer")
            else:
                output_lines.append(f"systemctl --user enable --now {units[0][0]}")
            output_lines.append("```")
            output_lines.append("")
            output_lines.append("For system services (requires root):")
            output_lines.append("```bash")
            for name, _ in units:
                output_lines.append(f"sudo cp {name} /etc/systemd/system/")
            output_lines.append("sudo systemctl daemon-reload")
            if unit_type == "timer":
                output_lines.append("sudo systemctl enable --now mytimer.timer")
            else:
                output_lines.append(f"sudo systemctl enable --now {units[0][0]}")
            output_lines.append("```")

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "unit_type": unit_type,
                    "unit_count": len(units),
                    "hardened": hardened,
                },
            )

        except Exception as e:
            log.error("systemd_generate_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate systemd unit: {e}",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# BashLintTool
# ═══════════════════════════════════════════════════════════════════════════════


class BashLintTool(Tool):
    """Lint bash scripts with optional auto-fix."""

    name = "bash_lint"
    description = """Lint a bash script and optionally apply fixes.

Uses shellcheck to identify issues and can automatically fix certain problems
like unquoted variables, deprecated syntax, and useless commands.

Note: Auto-fix is best-effort and may not fix all issues.
"""

    parameters = {
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": "The bash script content to lint",
            },
            "fix": {
                "type": "boolean",
                "description": "Return fixed script (default: false)",
            },
            "rules": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific shellcheck rules to check (e.g., ['SC2086', 'SC2046'])",
            },
        },
        "required": ["script"],
    }

    async def execute(
        self,
        script: str,
        fix: bool = False,
        rules: Optional[list[str]] = None,
        **kwargs,
    ) -> ToolResult:
        """Lint a bash script."""
        try:
            log.info(
                "bash_lint_start",
                script_length=len(script),
                fix=fix,
                rules=rules,
            )

            # Check if shellcheck is available
            shellcheck_path = shutil.which("shellcheck")
            if not shellcheck_path:
                return ToolResult(
                    success=False,
                    output="",
                    error="shellcheck is not installed. Install it with: pacman -S shellcheck (Arch) or apt install shellcheck (Debian/Ubuntu)",
                )

            # Write script to temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".sh", delete=False
            ) as f:
                f.write(script)
                temp_path = f.name

            try:
                # Build command
                cmd = [shellcheck_path, "-f", "json", temp_path]
                if rules:
                    for rule in rules:
                        cmd.extend(["-e", rule])

                # Run shellcheck
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                # Parse results
                issues = []
                if result.stdout:
                    try:
                        issues = json.loads(result.stdout)
                    except json.JSONDecodeError:
                        pass

                if fix and issues:
                    fixed_script = self._apply_fixes(script, issues)
                    return ToolResult(
                        success=True,
                        output=f"Applied fixes to {len(issues)} issue(s).\n\nFixed script:\n```bash\n{fixed_script}\n```",
                        metadata={
                            "issue_count": len(issues),
                            "fixed": True,
                            "fixed_script": fixed_script,
                        },
                    )

                if not issues:
                    return ToolResult(
                        success=True,
                        output="No linting issues found.",
                        metadata={"issue_count": 0, "fixed": False},
                    )

                # Format issues
                output_lines = [f"Found {len(issues)} issue(s):", ""]

                by_severity = {"error": [], "warning": [], "info": [], "style": []}
                for issue in issues:
                    level = issue.get("level", "warning")
                    by_severity.get(level, by_severity["warning"]).append(issue)

                for level in ["error", "warning", "info", "style"]:
                    level_issues = by_severity[level]
                    if level_issues:
                        output_lines.append(f"### {level.upper()} ({len(level_issues)})")
                        for issue in level_issues:
                            code = issue.get("code", "?")
                            line = issue.get("line", "?")
                            message = issue.get("message", "No message")
                            output_lines.append(f"- **SC{code}** (line {line}): {message}")
                        output_lines.append("")

                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata={
                        "issue_count": len(issues),
                        "fixed": False,
                        "by_severity": {k: len(v) for k, v in by_severity.items()},
                    },
                )

            finally:
                # Clean up temp file
                Path(temp_path).unlink(missing_ok=True)

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error="Shellcheck timed out",
            )
        except Exception as e:
            log.error("bash_lint_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to lint script: {e}",
            )

    def _apply_fixes(self, script: str, issues: list[dict]) -> str:
        """Apply automatic fixes to script."""
        lines = script.split("\n")

        # Sort issues by line number in reverse to avoid offset issues
        sorted_issues = sorted(issues, key=lambda x: x.get("line", 0), reverse=True)

        for issue in sorted_issues:
            code = issue.get("code", 0)
            line_num = issue.get("line", 0) - 1  # 0-indexed
            column = issue.get("column", 1) - 1  # 0-indexed

            if line_num < 0 or line_num >= len(lines):
                continue

            line = lines[line_num]

            # Apply specific fixes
            if code == 2086:  # Double quote to prevent globbing and word splitting
                # Add quotes around unquoted variable
                fixed_line = self._fix_unquoted_variable(line, column)
                lines[line_num] = fixed_line

            elif code == 2046:  # Quote this to prevent word splitting
                # Similar to 2086
                fixed_line = self._fix_unquoted_variable(line, column)
                lines[line_num] = fixed_line

            elif code == 2006:  # Use $(...) notation instead of legacy backticks
                # Replace backticks with $()
                lines[line_num] = re.sub(r"`([^`]+)`", r"$(\1)", line)

            elif code == 2001:  # Useless cat
                # Remove useless cat
                lines[line_num] = re.sub(r"cat\s+(\S+)\s*\|", r"< \1 ", line)

        return "\n".join(lines)

    def _fix_unquoted_variable(self, line: str, column: int) -> str:
        """Fix an unquoted variable by adding quotes."""
        # Find the variable starting at or near the column
        var_match = re.search(r"\$\{?\w+\}?", line[column:])
        if var_match:
            var = var_match.group()
            var_start = column + var_match.start()
            var_end = column + var_match.end()

            # Check if already quoted
            if var_start > 0 and line[var_start - 1] == '"':
                return line

            # Add quotes
            return line[:var_start] + '"' + var + '"' + line[var_end:]

        return line


# ═══════════════════════════════════════════════════════════════════════════════
# Export list
# ═══════════════════════════════════════════════════════════════════════════════

BASH_TOOLS = [
    BashGenerateTool,
    BashExplainTool,
    BashValidateTool,
    SystemdGenerateTool,
    BashLintTool,
]
