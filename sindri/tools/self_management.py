"""Self-management tools for Sindri.

This module provides tools for Sindri to manage itself, including:
- Version and status information
- Self-update capability
- Configuration management
- Ollama model management
- GPU VRAM status

These tools integrate with the system access configuration from Milestone 5.
"""

import asyncio
import shutil
from pathlib import Path
from typing import Any, Optional

import structlog

from sindri.config import SindriConfig, SystemAccessLevel
from sindri.core.access import check_system_access, can_modify_self
from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


def _check_ollama() -> bool:
    """Check if ollama CLI is available."""
    return shutil.which("ollama") is not None


def _check_rocm_smi() -> bool:
    """Check if rocm-smi (AMD GPU) is available."""
    return shutil.which("rocm-smi") is not None


def _check_nvidia_smi() -> bool:
    """Check if nvidia-smi (NVIDIA GPU) is available."""
    return shutil.which("nvidia-smi") is not None


class SindriVersionTool(Tool):
    """Show Sindri version and status information."""

    name = "sindri_version"
    description = (
        "Show Sindri version, installation path, and current configuration status. "
        "This is a read-only operation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "verbose": {
                "type": "boolean",
                "description": "Show detailed configuration information (default: false)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        verbose: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Get Sindri version and status."""
        log.info("sindri_version_request", verbose=verbose)

        try:
            from sindri import __version__

            config = SindriConfig.load()

            lines = [
                f"Sindri Version: {__version__}",
                f"Data Directory: {config.data_dir}",
                f"Database: {config.db_path}",
                f"Ollama Host: {config.ollama_host}",
                f"Default Model: {config.default_model}",
                f"System Access: {config.system_access.value.upper()}",
            ]

            if verbose:
                lines.extend([
                    "",
                    "Configuration Details:",
                    f"  Total VRAM: {config.total_vram_gb} GB",
                    f"  Reserved VRAM: {config.reserve_vram_gb} GB",
                    f"  Max Iterations: {config.max_iterations}",
                    f"  Memory Enabled: {config.memory.enabled}",
                    f"  Log Level: {config.log_level}",
                    "",
                    "Access Configuration:",
                    f"  Access Level: {config.system_access.value}",
                    f"  Allowed Services: {', '.join(config.allowed_services)}",
                    f"  Self-Modification: {'enabled' if config.allow_self_modification else 'disabled'}",
                ])

            output = "\n".join(lines)

            log.info("sindri_version_success", version=__version__)
            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "version": __version__,
                    "data_dir": str(config.data_dir),
                    "ollama_host": config.ollama_host,
                    "system_access": config.system_access.value,
                },
            )

        except Exception as e:
            log.error("sindri_version_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to get version info: {str(e)}",
            )


class SindriUpdateTool(Tool):
    """Update Sindri from local repository."""

    name = "sindri_update"
    description = (
        "Update Sindri by reinstalling from the local repository. "
        "Requires SUPERVISED or FULL access level and allow_self_modification enabled."
    )
    parameters = {
        "type": "object",
        "properties": {
            "check_only": {
                "type": "boolean",
                "description": "Only check if update is available, don't apply (default: false)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        check_only: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Update Sindri."""
        log.info("sindri_update_request", check_only=check_only)

        # Check if self-modification is allowed
        config = SindriConfig.load()
        access_result = can_modify_self(config)

        if not access_result.allowed:
            log.warning("sindri_update_denied", reason=access_result.reason)
            return ToolResult(
                success=False,
                output="",
                error=access_result.reason,
            )

        try:
            # Find sindri installation directory
            import sindri
            sindri_dir = Path(sindri.__file__).parent.parent

            if not (sindri_dir / "pyproject.toml").exists():
                return ToolResult(
                    success=False,
                    output="",
                    error="Cannot find Sindri source directory. Is it installed in editable mode?",
                )

            if check_only:
                # Check git status for changes
                proc = await asyncio.create_subprocess_exec(
                    "git", "-C", str(sindri_dir), "fetch", "--dry-run",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()

                if proc.returncode != 0:
                    return ToolResult(
                        success=True,
                        output="Unable to check for updates (git fetch failed). Repository may be up to date.",
                        metadata={"check_only": True, "update_available": None},
                    )

                return ToolResult(
                    success=True,
                    output=f"Sindri installation at: {sindri_dir}\nRun without check_only to apply updates.",
                    metadata={"check_only": True, "install_path": str(sindri_dir)},
                )

            # Actually update
            log.info("sindri_update_installing", path=str(sindri_dir))

            proc = await asyncio.create_subprocess_exec(
                "pip", "install", "-e", str(sindri_dir), "--upgrade",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            if proc.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                log.error("sindri_update_failed", error=error_msg)
                return ToolResult(
                    success=False,
                    output=stdout.decode("utf-8", errors="replace"),
                    error=f"Update failed: {error_msg}",
                )

            log.info("sindri_update_success")
            return ToolResult(
                success=True,
                output="Sindri updated successfully. Restart may be required for changes to take effect.",
                metadata={"updated": True, "install_path": str(sindri_dir)},
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error="Update timed out after 120 seconds",
            )
        except Exception as e:
            log.error("sindri_update_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Update failed: {str(e)}",
            )


class SindriConfigGetTool(Tool):
    """Get a Sindri configuration value."""

    name = "sindri_config_get"
    description = (
        "Get a specific configuration value or all configuration. "
        "This is a read-only operation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Configuration key to get (e.g., 'system_access', 'ollama_host'). If not specified, returns all config.",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        key: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Get configuration value."""
        log.info("sindri_config_get_request", key=key)

        try:
            config = SindriConfig.load()
            config_dict = config.model_dump(mode="json")

            if key:
                if key not in config_dict:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Unknown configuration key: {key}. Valid keys: {', '.join(config_dict.keys())}",
                    )

                value = config_dict[key]
                log.info("sindri_config_get_success", key=key, value=value)
                return ToolResult(
                    success=True,
                    output=f"{key} = {value}",
                    metadata={"key": key, "value": value},
                )

            # Return all config
            import json
            output = json.dumps(config_dict, indent=2, default=str)

            log.info("sindri_config_get_success", key="*")
            return ToolResult(
                success=True,
                output=output,
                metadata={"keys": list(config_dict.keys())},
            )

        except Exception as e:
            log.error("sindri_config_get_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to get config: {str(e)}",
            )


class SindriConfigSetTool(Tool):
    """Set a Sindri configuration value."""

    name = "sindri_config_set"
    description = (
        "Set a configuration value. Requires allow_self_modification to be enabled. "
        "Supports setting: system_access, ollama_host, default_model, log_level."
    )
    parameters = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Configuration key to set",
            },
            "value": {
                "type": "string",
                "description": "Value to set",
            },
        },
        "required": ["key", "value"],
    }

    # Keys that can be modified via this tool
    ALLOWED_KEYS = {
        "system_access",
        "ollama_host",
        "default_model",
        "log_level",
        "max_iterations",
        "total_vram_gb",
        "reserve_vram_gb",
    }

    async def execute(
        self,
        key: str,
        value: str,
        **kwargs: Any,
    ) -> ToolResult:
        """Set configuration value."""
        log.info("sindri_config_set_request", key=key, value=value)

        # Check if self-modification is allowed
        config = SindriConfig.load()
        access_result = can_modify_self(config)

        if not access_result.allowed:
            log.warning("sindri_config_set_denied", reason=access_result.reason)
            return ToolResult(
                success=False,
                output="",
                error=access_result.reason,
            )

        if key not in self.ALLOWED_KEYS:
            return ToolResult(
                success=False,
                output="",
                error=f"Cannot modify '{key}'. Allowed keys: {', '.join(sorted(self.ALLOWED_KEYS))}",
            )

        try:
            # Convert value to appropriate type
            if key == "system_access":
                if value not in ("restricted", "supervised", "full"):
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Invalid system_access value. Must be: restricted, supervised, or full",
                    )
                config.system_access = SystemAccessLevel(value)

            elif key in ("max_iterations",):
                config.__dict__[key] = int(value)

            elif key in ("total_vram_gb", "reserve_vram_gb"):
                config.__dict__[key] = float(value)

            else:
                setattr(config, key, value)

            # Save config
            config_path = Path.home() / ".sindri" / "config.toml"
            config.save(str(config_path))

            log.info("sindri_config_set_success", key=key, value=value)
            return ToolResult(
                success=True,
                output=f"Configuration updated: {key} = {value}\nSaved to: {config_path}",
                metadata={"key": key, "value": value, "config_path": str(config_path)},
            )

        except Exception as e:
            log.error("sindri_config_set_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to set config: {str(e)}",
            )


class OllamaListTool(Tool):
    """List installed Ollama models."""

    name = "ollama_list"
    description = (
        "List all installed Ollama models with their sizes and modification dates. "
        "This is a read-only operation."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """List Ollama models."""
        log.info("ollama_list_request")

        if not _check_ollama():
            return ToolResult(
                success=False,
                output="",
                error="Ollama is not installed or not in PATH",
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                "ollama", "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            if proc.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to list models: {error_msg}",
                )

            output = stdout.decode("utf-8", errors="replace").strip()

            # Count models (skip header line)
            lines = output.split("\n")
            model_count = len(lines) - 1 if lines else 0

            log.info("ollama_list_success", count=model_count)
            return ToolResult(
                success=True,
                output=output,
                metadata={"model_count": model_count},
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error="Timed out connecting to Ollama",
            )
        except Exception as e:
            log.error("ollama_list_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to list models: {str(e)}",
            )


class OllamaPullTool(Tool):
    """Pull (download) an Ollama model."""

    name = "ollama_pull"
    description = (
        "Download an Ollama model. This may take a while for large models. "
        "Requires SUPERVISED or FULL access level."
    )
    parameters = {
        "type": "object",
        "properties": {
            "model": {
                "type": "string",
                "description": "Model name to pull (e.g., 'llama3.1:8b', 'qwen2.5-coder:7b')",
            },
        },
        "required": ["model"],
    }

    async def execute(
        self,
        model: str,
        **kwargs: Any,
    ) -> ToolResult:
        """Pull an Ollama model."""
        log.info("ollama_pull_request", model=model)

        if not _check_ollama():
            return ToolResult(
                success=False,
                output="",
                error="Ollama is not installed or not in PATH",
            )

        # Check access control (pulling models is a modification)
        config = SindriConfig.load()
        access_result = check_system_access(
            config,
            f"pull Ollama model '{model}'",
            service="ollama",
            is_modification=True,
        )

        if not access_result.allowed:
            log.warning("ollama_pull_denied", model=model, reason=access_result.reason)
            return ToolResult(
                success=False,
                output="",
                error=access_result.reason,
            )

        try:
            log.info("ollama_pull_starting", model=model)

            proc = await asyncio.create_subprocess_exec(
                "ollama", "pull", model,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # Long timeout for model downloads
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=3600)

            if proc.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                log.error("ollama_pull_failed", model=model, error=error_msg)
                return ToolResult(
                    success=False,
                    output=stdout.decode("utf-8", errors="replace"),
                    error=f"Failed to pull model: {error_msg}",
                )

            output = stdout.decode("utf-8", errors="replace").strip()
            log.info("ollama_pull_success", model=model)
            return ToolResult(
                success=True,
                output=f"Successfully pulled model: {model}\n{output}",
                metadata={"model": model, "action": "pull"},
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error="Model pull timed out after 1 hour",
            )
        except Exception as e:
            log.error("ollama_pull_error", model=model, error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to pull model: {str(e)}",
            )


class OllamaRemoveTool(Tool):
    """Remove an Ollama model."""

    name = "ollama_remove"
    description = (
        "Remove (delete) an installed Ollama model to free up disk space. "
        "Requires SUPERVISED or FULL access level."
    )
    parameters = {
        "type": "object",
        "properties": {
            "model": {
                "type": "string",
                "description": "Model name to remove (e.g., 'llama3.1:8b')",
            },
        },
        "required": ["model"],
    }

    async def execute(
        self,
        model: str,
        **kwargs: Any,
    ) -> ToolResult:
        """Remove an Ollama model."""
        log.info("ollama_remove_request", model=model)

        if not _check_ollama():
            return ToolResult(
                success=False,
                output="",
                error="Ollama is not installed or not in PATH",
            )

        # Check access control
        config = SindriConfig.load()
        access_result = check_system_access(
            config,
            f"remove Ollama model '{model}'",
            service="ollama",
            is_modification=True,
        )

        if not access_result.allowed:
            log.warning("ollama_remove_denied", model=model, reason=access_result.reason)
            return ToolResult(
                success=False,
                output="",
                error=access_result.reason,
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                "ollama", "rm", model,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            if proc.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                log.error("ollama_remove_failed", model=model, error=error_msg)
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to remove model: {error_msg}",
                )

            log.info("ollama_remove_success", model=model)
            return ToolResult(
                success=True,
                output=f"Successfully removed model: {model}",
                metadata={"model": model, "action": "remove"},
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error="Model removal timed out",
            )
        except Exception as e:
            log.error("ollama_remove_error", model=model, error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to remove model: {str(e)}",
            )


class OllamaStatusTool(Tool):
    """Check Ollama server status."""

    name = "ollama_status"
    description = (
        "Check if Ollama server is running and responding. "
        "This is a read-only operation."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Check Ollama status."""
        log.info("ollama_status_request")

        config = SindriConfig.load()
        ollama_host = config.ollama_host

        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{ollama_host}/api/tags")

                if response.status_code == 200:
                    data = response.json()
                    model_count = len(data.get("models", []))

                    log.info("ollama_status_running", host=ollama_host, models=model_count)
                    return ToolResult(
                        success=True,
                        output=f"Ollama is running at {ollama_host}\nLoaded models: {model_count}",
                        metadata={
                            "status": "running",
                            "host": ollama_host,
                            "model_count": model_count,
                        },
                    )
                else:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Ollama returned status {response.status_code}",
                        metadata={"status": "error", "host": ollama_host},
                    )

        except ImportError:
            # Fall back to ollama CLI
            if not _check_ollama():
                return ToolResult(
                    success=False,
                    output="",
                    error="Neither httpx nor ollama CLI available to check status",
                )

            proc = await asyncio.create_subprocess_exec(
                "ollama", "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

            if proc.returncode == 0:
                return ToolResult(
                    success=True,
                    output=f"Ollama is running at {ollama_host}",
                    metadata={"status": "running", "host": ollama_host},
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Ollama is not responding: {stderr.decode()}",
                    metadata={"status": "stopped", "host": ollama_host},
                )

        except Exception as e:
            log.error("ollama_status_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Cannot connect to Ollama at {ollama_host}: {str(e)}",
                metadata={"status": "unreachable", "host": ollama_host},
            )


class VramStatusTool(Tool):
    """Check GPU VRAM usage."""

    name = "vram_status"
    description = (
        "Check GPU VRAM usage. Supports AMD GPUs (rocm-smi) and NVIDIA GPUs (nvidia-smi). "
        "This is a read-only operation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "detailed": {
                "type": "boolean",
                "description": "Show detailed GPU information (default: false)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        detailed: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Check VRAM status."""
        log.info("vram_status_request", detailed=detailed)

        # Try AMD first (since the target machine has AMD GPU)
        if _check_rocm_smi():
            return await self._check_amd_vram(detailed)
        elif _check_nvidia_smi():
            return await self._check_nvidia_vram(detailed)
        else:
            return ToolResult(
                success=False,
                output="",
                error="No GPU monitoring tool found. Install rocm-smi (AMD) or nvidia-smi (NVIDIA).",
            )

    async def _check_amd_vram(self, detailed: bool) -> ToolResult:
        """Check AMD GPU VRAM using rocm-smi."""
        try:
            cmd = ["rocm-smi"]
            if detailed:
                cmd.append("--showmeminfo")

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

            if proc.returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"rocm-smi failed: {stderr.decode()}",
                )

            output = stdout.decode("utf-8", errors="replace")

            # Try to parse VRAM usage
            used_vram = None
            total_vram = None

            # Parse memory info from rocm-smi output
            for line in output.split("\n"):
                if "VRAM" in line or "Memory" in line:
                    # Try to extract used/total
                    pass  # Format varies by version

            log.info("vram_status_amd_success")
            return ToolResult(
                success=True,
                output=output.strip(),
                metadata={
                    "gpu_type": "AMD",
                    "tool": "rocm-smi",
                    "used_vram_gb": used_vram,
                    "total_vram_gb": total_vram,
                },
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error="rocm-smi timed out",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to check AMD VRAM: {str(e)}",
            )

    async def _check_nvidia_vram(self, detailed: bool) -> ToolResult:
        """Check NVIDIA GPU VRAM using nvidia-smi."""
        try:
            if detailed:
                cmd = ["nvidia-smi"]
            else:
                cmd = [
                    "nvidia-smi",
                    "--query-gpu=name,memory.used,memory.total,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

            if proc.returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"nvidia-smi failed: {stderr.decode()}",
                )

            output = stdout.decode("utf-8", errors="replace").strip()

            # Parse VRAM from CSV output
            used_vram = None
            total_vram = None

            if not detailed:
                try:
                    parts = output.split(",")
                    if len(parts) >= 3:
                        used_vram = float(parts[1].strip()) / 1024  # MB to GB
                        total_vram = float(parts[2].strip()) / 1024  # MB to GB
                except (ValueError, IndexError):
                    pass

            log.info("vram_status_nvidia_success", used=used_vram, total=total_vram)
            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "gpu_type": "NVIDIA",
                    "tool": "nvidia-smi",
                    "used_vram_gb": used_vram,
                    "total_vram_gb": total_vram,
                },
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error="nvidia-smi timed out",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to check NVIDIA VRAM: {str(e)}",
            )


# Export all self-management tools
SELF_MANAGEMENT_TOOLS = [
    SindriVersionTool,
    SindriUpdateTool,
    SindriConfigGetTool,
    SindriConfigSetTool,
    OllamaListTool,
    OllamaPullTool,
    OllamaRemoveTool,
    OllamaStatusTool,
    VramStatusTool,
]
