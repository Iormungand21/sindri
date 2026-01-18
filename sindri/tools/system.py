"""System and process monitoring tools using psutil."""

import os
import platform
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()

# Check if psutil is available
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


def _format_bytes(size: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def _format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


class ProcessListTool(Tool):
    """Tool for listing running processes with filtering and sorting."""

    name = "process_list"
    description = (
        "List running processes with optional filtering by name/user and sorting. "
        "Returns process ID, name, username, CPU%, memory%, and status."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Filter processes by name (case-insensitive substring match)",
            },
            "user": {
                "type": "string",
                "description": "Filter processes by username",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of processes to return (default: 50)",
            },
            "sort_by": {
                "type": "string",
                "enum": ["cpu", "memory", "pid", "name"],
                "description": "Sort processes by: cpu, memory, pid, or name (default: cpu)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        name: Optional[str] = None,
        user: Optional[str] = None,
        limit: int = 50,
        sort_by: str = "cpu",
        **kwargs: Any,
    ) -> ToolResult:
        """List running processes with filtering."""
        log.info("process_list_start", name_filter=name, user_filter=user, limit=limit)

        if not PSUTIL_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="psutil not installed. Install with: pip install psutil",
            )

        try:
            processes = []
            for proc in psutil.process_iter(
                ["pid", "name", "username", "cpu_percent", "memory_percent", "status"]
            ):
                try:
                    info = proc.info
                    # Apply filters
                    if name and name.lower() not in (info["name"] or "").lower():
                        continue
                    if user and user.lower() != (info["username"] or "").lower():
                        continue

                    processes.append(
                        {
                            "pid": info["pid"],
                            "name": info["name"] or "unknown",
                            "username": info["username"] or "unknown",
                            "cpu_percent": info["cpu_percent"] or 0.0,
                            "memory_percent": info["memory_percent"] or 0.0,
                            "status": info["status"] or "unknown",
                        }
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Sort processes
            sort_keys = {
                "cpu": lambda x: x["cpu_percent"],
                "memory": lambda x: x["memory_percent"],
                "pid": lambda x: x["pid"],
                "name": lambda x: x["name"].lower(),
            }
            sort_key = sort_keys.get(sort_by, sort_keys["cpu"])
            reverse = sort_by in ["cpu", "memory"]
            processes.sort(key=sort_key, reverse=reverse)

            # Apply limit
            processes = processes[:limit]

            # Format output
            lines = [
                f"{'PID':>8}  {'NAME':<25}  {'USER':<15}  {'CPU%':>6}  {'MEM%':>6}  STATUS"
            ]
            lines.append("-" * 80)
            for p in processes:
                lines.append(
                    f"{p['pid']:>8}  {p['name']:<25}  {p['username']:<15}  "
                    f"{p['cpu_percent']:>5.1f}%  {p['memory_percent']:>5.1f}%  {p['status']}"
                )

            output = "\n".join(lines)
            log.info("process_list_success", count=len(processes))

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "process_count": len(processes),
                    "filters": {"name": name, "user": user},
                    "sort_by": sort_by,
                    "limit": limit,
                },
            )
        except Exception as e:
            log.error("process_list_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class ProcessKillTool(Tool):
    """Tool for killing processes by PID or name."""

    name = "process_kill"
    description = (
        "Kill a process by PID or name. "
        "Use with caution - killing system processes may cause instability."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pid": {
                "type": "integer",
                "description": "Process ID to kill",
            },
            "name": {
                "type": "string",
                "description": "Process name to kill (first match)",
            },
            "signal": {
                "type": "string",
                "enum": ["TERM", "KILL", "HUP"],
                "description": "Signal to send: TERM (graceful), KILL (force), HUP (reload). Default: TERM",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        pid: Optional[int] = None,
        name: Optional[str] = None,
        signal: str = "TERM",
        **kwargs: Any,
    ) -> ToolResult:
        """Kill a process by PID or name."""
        log.info("process_kill_start", pid=pid, name=name, signal=signal)

        if not PSUTIL_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="psutil not installed. Install with: pip install psutil",
            )

        if not pid and not name:
            return ToolResult(
                success=False,
                output="",
                error="Must specify either pid or name to kill a process",
            )

        try:
            import signal as sig_module

            signal_map = {
                "TERM": sig_module.SIGTERM,
                "KILL": sig_module.SIGKILL,
                "HUP": sig_module.SIGHUP,
            }
            sig = signal_map.get(signal.upper(), sig_module.SIGTERM)

            proc = None
            if pid:
                try:
                    proc = psutil.Process(pid)
                except psutil.NoSuchProcess:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"No process found with PID {pid}",
                    )
            elif name:
                # Find first matching process
                for p in psutil.process_iter(["pid", "name"]):
                    try:
                        if name.lower() in (p.info["name"] or "").lower():
                            proc = p
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                if not proc:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"No process found matching name '{name}'",
                    )

            # Get process info before killing
            proc_info = {
                "pid": proc.pid,
                "name": proc.name(),
                "status": proc.status(),
            }
            try:
                proc_info["username"] = proc.username()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                proc_info["username"] = "unknown"

            # Kill the process
            proc.send_signal(sig)

            output = (
                f"Sent {signal} signal to process:\n"
                f"  PID: {proc_info['pid']}\n"
                f"  Name: {proc_info['name']}\n"
                f"  User: {proc_info['username']}\n"
                f"  Status: {proc_info['status']}"
            )
            log.info("process_kill_success", **proc_info)

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "pid": proc_info["pid"],
                    "name": proc_info["name"],
                    "signal": signal,
                },
            )
        except psutil.AccessDenied:
            log.warning("process_kill_access_denied", pid=pid, name=name)
            return ToolResult(
                success=False,
                output="",
                error="Permission denied. May need elevated privileges to kill this process.",
            )
        except Exception as e:
            log.error("process_kill_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class SystemInfoTool(Tool):
    """Tool for getting system information."""

    name = "system_info"
    description = (
        "Get comprehensive system information including OS, CPU, memory, and uptime."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Get system information."""
        log.info("system_info_start")

        try:
            # Platform info (always available)
            info = {
                "platform": {
                    "system": platform.system(),
                    "release": platform.release(),
                    "version": platform.version(),
                    "machine": platform.machine(),
                    "processor": platform.processor(),
                    "python_version": platform.python_version(),
                },
            }

            # CPU info (requires psutil)
            if PSUTIL_AVAILABLE:
                cpu_freq = psutil.cpu_freq()
                info["cpu"] = {
                    "physical_cores": psutil.cpu_count(logical=False),
                    "logical_cores": psutil.cpu_count(logical=True),
                    "current_freq_mhz": cpu_freq.current if cpu_freq else None,
                    "usage_percent": psutil.cpu_percent(interval=0.1),
                }

                # Memory info
                mem = psutil.virtual_memory()
                info["memory"] = {
                    "total": mem.total,
                    "available": mem.available,
                    "used": mem.used,
                    "percent": mem.percent,
                    "total_human": _format_bytes(mem.total),
                    "available_human": _format_bytes(mem.available),
                }

                # Boot time
                boot_time = datetime.fromtimestamp(psutil.boot_time())
                uptime = datetime.now() - boot_time
                info["uptime"] = {
                    "boot_time": boot_time.isoformat(),
                    "uptime_seconds": uptime.total_seconds(),
                    "uptime_human": _format_duration(uptime.total_seconds()),
                }
            else:
                info["note"] = (
                    "psutil not installed - CPU, memory, and uptime info unavailable"
                )

            # Format output
            lines = ["System Information", "=" * 50]

            # Platform section
            lines.append("\nPlatform:")
            p = info["platform"]
            lines.append(f"  OS: {p['system']} {p['release']}")
            lines.append(f"  Version: {p['version']}")
            lines.append(f"  Architecture: {p['machine']}")
            lines.append(f"  Python: {p['python_version']}")

            if PSUTIL_AVAILABLE:
                # CPU section
                lines.append("\nCPU:")
                c = info["cpu"]
                lines.append(f"  Cores: {c['physical_cores']} physical, {c['logical_cores']} logical")
                if c["current_freq_mhz"]:
                    lines.append(f"  Frequency: {c['current_freq_mhz']:.0f} MHz")
                lines.append(f"  Usage: {c['usage_percent']:.1f}%")

                # Memory section
                lines.append("\nMemory:")
                m = info["memory"]
                lines.append(f"  Total: {m['total_human']}")
                lines.append(f"  Available: {m['available_human']}")
                lines.append(f"  Usage: {m['percent']:.1f}%")

                # Uptime section
                lines.append("\nUptime:")
                u = info["uptime"]
                lines.append(f"  Boot Time: {u['boot_time']}")
                lines.append(f"  Uptime: {u['uptime_human']}")

            output = "\n".join(lines)
            log.info("system_info_success")

            return ToolResult(
                success=True,
                output=output,
                metadata=info,
            )
        except Exception as e:
            log.error("system_info_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class DiskUsageTool(Tool):
    """Tool for checking disk usage."""

    name = "disk_usage"
    description = (
        "Check disk space usage for a path or all mounted partitions. "
        "Shows total, used, free space and usage percentage."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to check disk usage for (default: /)",
            },
            "all_partitions": {
                "type": "boolean",
                "description": "Show usage for all mounted partitions (default: false)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: str = "/",
        all_partitions: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Check disk usage."""
        log.info("disk_usage_start", path=path, all_partitions=all_partitions)

        if not PSUTIL_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="psutil not installed. Install with: pip install psutil",
            )

        try:
            partitions_info = []

            if all_partitions:
                # Get all partitions
                for partition in psutil.disk_partitions(all=False):
                    try:
                        usage = psutil.disk_usage(partition.mountpoint)
                        partitions_info.append(
                            {
                                "device": partition.device,
                                "mountpoint": partition.mountpoint,
                                "fstype": partition.fstype,
                                "total": usage.total,
                                "used": usage.used,
                                "free": usage.free,
                                "percent": usage.percent,
                            }
                        )
                    except (PermissionError, OSError):
                        continue
            else:
                # Single path
                resolved_path = self._resolve_path(path)
                if not resolved_path.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Path does not exist: {path}",
                    )

                usage = psutil.disk_usage(str(resolved_path))
                partitions_info.append(
                    {
                        "device": "N/A",
                        "mountpoint": str(resolved_path),
                        "fstype": "N/A",
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": usage.percent,
                    }
                )

            # Format output
            lines = ["Disk Usage", "=" * 70]
            lines.append(
                f"{'MOUNT':<25}  {'TOTAL':>10}  {'USED':>10}  {'FREE':>10}  {'USE%':>6}"
            )
            lines.append("-" * 70)

            for p in partitions_info:
                lines.append(
                    f"{p['mountpoint']:<25}  "
                    f"{_format_bytes(p['total']):>10}  "
                    f"{_format_bytes(p['used']):>10}  "
                    f"{_format_bytes(p['free']):>10}  "
                    f"{p['percent']:>5.1f}%"
                )

            output = "\n".join(lines)
            log.info("disk_usage_success", partitions=len(partitions_info))

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "partitions": partitions_info,
                    "path": path,
                    "all_partitions": all_partitions,
                },
            )
        except Exception as e:
            log.error("disk_usage_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class MemoryUsageTool(Tool):
    """Tool for checking memory usage."""

    name = "memory_usage"
    description = (
        "Check system memory usage including RAM and optionally swap. "
        "Shows total, available, used, free, and cache information."
    )
    parameters = {
        "type": "object",
        "properties": {
            "include_swap": {
                "type": "boolean",
                "description": "Include swap memory information (default: true)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        include_swap: bool = True,
        **kwargs: Any,
    ) -> ToolResult:
        """Check memory usage."""
        log.info("memory_usage_start", include_swap=include_swap)

        if not PSUTIL_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="psutil not installed. Install with: pip install psutil",
            )

        try:
            mem = psutil.virtual_memory()
            memory_info = {
                "total": mem.total,
                "available": mem.available,
                "used": mem.used,
                "free": mem.free,
                "percent": mem.percent,
                "total_human": _format_bytes(mem.total),
                "available_human": _format_bytes(mem.available),
                "used_human": _format_bytes(mem.used),
                "free_human": _format_bytes(mem.free),
            }

            # Add buffers and cached if available (Linux)
            if hasattr(mem, "buffers"):
                memory_info["buffers"] = mem.buffers
                memory_info["buffers_human"] = _format_bytes(mem.buffers)
            if hasattr(mem, "cached"):
                memory_info["cached"] = mem.cached
                memory_info["cached_human"] = _format_bytes(mem.cached)

            # Format output
            lines = ["Memory Usage", "=" * 50]
            lines.append("\nRAM:")
            lines.append(f"  Total:     {memory_info['total_human']}")
            lines.append(f"  Available: {memory_info['available_human']}")
            lines.append(f"  Used:      {memory_info['used_human']}")
            lines.append(f"  Free:      {memory_info['free_human']}")
            lines.append(f"  Usage:     {memory_info['percent']:.1f}%")

            if "buffers" in memory_info:
                lines.append(f"  Buffers:   {memory_info['buffers_human']}")
            if "cached" in memory_info:
                lines.append(f"  Cached:    {memory_info['cached_human']}")

            swap_info = None
            if include_swap:
                swap = psutil.swap_memory()
                swap_info = {
                    "total": swap.total,
                    "used": swap.used,
                    "free": swap.free,
                    "percent": swap.percent,
                    "total_human": _format_bytes(swap.total),
                    "used_human": _format_bytes(swap.used),
                    "free_human": _format_bytes(swap.free),
                }
                memory_info["swap"] = swap_info

                lines.append("\nSwap:")
                lines.append(f"  Total:     {swap_info['total_human']}")
                lines.append(f"  Used:      {swap_info['used_human']}")
                lines.append(f"  Free:      {swap_info['free_human']}")
                lines.append(f"  Usage:     {swap_info['percent']:.1f}%")

            output = "\n".join(lines)
            log.info("memory_usage_success", percent=mem.percent)

            return ToolResult(
                success=True,
                output=output,
                metadata=memory_info,
            )
        except Exception as e:
            log.error("memory_usage_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class EnvGetTool(Tool):
    """Tool for getting environment variables."""

    name = "env_get"
    description = (
        "Get environment variables. Can filter by exact name or regex pattern. "
        "Option to hide values for security-sensitive operations."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Exact environment variable name to get",
            },
            "pattern": {
                "type": "string",
                "description": "Regex pattern to filter variable names (e.g., '^PATH$', 'HOME')",
            },
            "show_values": {
                "type": "boolean",
                "description": "Show variable values (default: true). Set false to only list names.",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        name: Optional[str] = None,
        pattern: Optional[str] = None,
        show_values: bool = True,
        **kwargs: Any,
    ) -> ToolResult:
        """Get environment variables."""
        log.info("env_get_start", name=name, pattern=pattern, show_values=show_values)

        try:
            env_vars = {}

            if name:
                # Get specific variable
                value = os.environ.get(name)
                if value is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Environment variable '{name}' not found",
                    )
                env_vars[name] = value
            elif pattern:
                # Filter by regex pattern
                try:
                    regex = re.compile(pattern, re.IGNORECASE)
                except re.error as e:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Invalid regex pattern: {e}",
                    )

                for key, value in sorted(os.environ.items()):
                    if regex.search(key):
                        env_vars[key] = value
            else:
                # Get all variables
                env_vars = dict(sorted(os.environ.items()))

            # Format output
            if not env_vars:
                return ToolResult(
                    success=True,
                    output="No environment variables match the criteria",
                    metadata={"count": 0},
                )

            lines = [f"Environment Variables ({len(env_vars)} found)", "=" * 60]

            if show_values:
                for key, value in env_vars.items():
                    # Truncate long values
                    display_value = value if len(value) <= 100 else value[:97] + "..."
                    lines.append(f"{key}={display_value}")
            else:
                for key in env_vars.keys():
                    lines.append(key)

            output = "\n".join(lines)
            log.info("env_get_success", count=len(env_vars))

            metadata: dict[str, Any] = {"count": len(env_vars)}
            if show_values:
                metadata["variables"] = env_vars

            return ToolResult(
                success=True,
                output=output,
                metadata=metadata,
            )
        except Exception as e:
            log.error("env_get_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))
