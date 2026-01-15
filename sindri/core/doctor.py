"""Health check functions for Sindri doctor command."""

import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import sqlite3

import structlog

log = structlog.get_logger()


class HealthCheck:
    """Result of a health check."""

    def __init__(self, name: str, passed: bool, message: str, details: Optional[str] = None):
        self.name = name
        self.passed = passed
        self.message = message
        self.details = details


def check_ollama() -> HealthCheck:
    """Check if Ollama is running and responsive."""
    try:
        import ollama
        client = ollama.Client()
        models = client.list()
        model_count = len(models.get("models", []))

        return HealthCheck(
            name="Ollama",
            passed=True,
            message=f"Running ({model_count} models available)",
            details=None
        )
    except ConnectionError:
        return HealthCheck(
            name="Ollama",
            passed=False,
            message="Not running or unreachable",
            details="Start Ollama with: systemctl start ollama"
        )
    except Exception as e:
        return HealthCheck(
            name="Ollama",
            passed=False,
            message=f"Error: {str(e)}",
            details=None
        )


def check_required_models() -> Tuple[HealthCheck, List[str], List[str]]:
    """Check if required models are available.

    Returns:
        Tuple of (HealthCheck, available_models, missing_models)
    """
    from sindri.agents.registry import AGENTS

    # Get unique models from agents
    required_models = set()
    for agent in AGENTS.values():
        required_models.add(agent.model)

    # Add embedding model
    required_models.add("nomic-embed-text")

    try:
        import ollama
        client = ollama.Client()
        models_response = client.list()

        # Get available model names, handling both "model:tag" and "model" formats
        available_raw = {m.model for m in models_response.get("models", [])}

        # Create a normalized set (without tags) for matching
        available_normalized = set()
        for model in available_raw:
            # Add both the full name and the base name (without tag)
            available_normalized.add(model)
            if ':' in model:
                available_normalized.add(model.split(':')[0])

        missing = required_models - available_normalized
        available_required = required_models & available_normalized

        if not missing:
            return (
                HealthCheck(
                    name="Required Models",
                    passed=True,
                    message=f"All {len(required_models)} required models available",
                    details=None
                ),
                list(available_required),
                []
            )
        else:
            return (
                HealthCheck(
                    name="Required Models",
                    passed=False,
                    message=f"{len(missing)} models missing",
                    details=f"Missing: {', '.join(sorted(missing))}"
                ),
                list(available_required),
                list(missing)
            )
    except Exception as e:
        return (
            HealthCheck(
                name="Required Models",
                passed=False,
                message=f"Error: {str(e)}",
                details=None
            ),
            [],
            list(required_models)
        )


def check_gpu_vram() -> HealthCheck:
    """Check GPU availability and VRAM."""
    try:
        # Try rocm-smi for AMD GPUs
        result = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            # Parse rocm-smi output to get total VRAM
            # This is a simple approach - rocm-smi output varies
            lines = result.stdout.split('\n')
            for line in lines:
                if 'Total VRAM' in line or 'VRAM Total' in line:
                    # Try to extract number
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part.isdigit() or (part.replace('.', '').isdigit()):
                            vram_mb = int(float(part))
                            vram_gb = vram_mb / 1024 if vram_mb > 1000 else vram_mb
                            return HealthCheck(
                                name="GPU/VRAM",
                                passed=True,
                                message=f"AMD GPU detected (~{vram_gb:.1f} GB VRAM)",
                                details="Using ROCm"
                            )

            # If we got here, rocm-smi ran but we couldn't parse
            return HealthCheck(
                name="GPU/VRAM",
                passed=True,
                message="AMD GPU detected (VRAM unknown)",
                details="rocm-smi available"
            )
    except FileNotFoundError:
        pass  # rocm-smi not found, try other methods
    except Exception as e:
        log.debug("rocm_smi_error", error=str(e))

    # Try nvidia-smi for NVIDIA GPUs
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            vram_mb = int(result.stdout.strip())
            vram_gb = vram_mb / 1024
            return HealthCheck(
                name="GPU/VRAM",
                passed=True,
                message=f"NVIDIA GPU detected ({vram_gb:.1f} GB VRAM)",
                details="Using CUDA"
            )
    except FileNotFoundError:
        pass  # nvidia-smi not found
    except Exception as e:
        log.debug("nvidia_smi_error", error=str(e))

    # No GPU detection tools found
    return HealthCheck(
        name="GPU/VRAM",
        passed=False,
        message="GPU not detected",
        details="Install rocm-smi (AMD) or nvidia-smi (NVIDIA) for GPU detection"
    )


def check_backup() -> HealthCheck:
    """Check backup status and health."""
    try:
        from sindri.persistence.backup import DatabaseBackup

        backup_mgr = DatabaseBackup()
        stats = backup_mgr.get_backup_stats()

        if stats["count"] == 0:
            return HealthCheck(
                name="Backups",
                passed=True,
                message="No backups yet",
                details="Backups will be created automatically before migrations"
            )

        # Format size
        total_mb = stats["total_size_bytes"] / (1024 * 1024)
        if total_mb < 1:
            size_str = f"{stats['total_size_bytes'] / 1024:.1f} KB"
        else:
            size_str = f"{total_mb:.1f} MB"

        # Format age of newest backup
        if stats["newest"]:
            from datetime import datetime
            age = datetime.now() - stats["newest"]
            if age.days > 0:
                age_str = f"{age.days}d ago"
            elif age.seconds > 3600:
                age_str = f"{age.seconds // 3600}h ago"
            else:
                age_str = f"{age.seconds // 60}m ago"
        else:
            age_str = "unknown"

        return HealthCheck(
            name="Backups",
            passed=True,
            message=f"{stats['count']} backups ({size_str})",
            details=f"Latest: {age_str}"
        )

    except Exception as e:
        return HealthCheck(
            name="Backups",
            passed=True,  # Non-critical check
            message=f"Could not check: {str(e)}",
            details=None
        )


def check_database() -> HealthCheck:
    """Check database integrity."""
    try:
        data_dir = Path.home() / ".sindri"
        db_path = data_dir / "sindri.db"

        if not db_path.exists():
            return HealthCheck(
                name="Database",
                passed=True,
                message="Not created yet",
                details="Will be created on first run"
            )

        # Test database connection and basic query
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check if sessions table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
        )

        if not cursor.fetchone():
            conn.close()
            return HealthCheck(
                name="Database",
                passed=False,
                message="Schema not initialized",
                details="Database exists but tables are missing"
            )

        # Count sessions
        cursor.execute("SELECT COUNT(*) FROM sessions")
        session_count = cursor.fetchone()[0]

        # Get DB size
        db_size_mb = db_path.stat().st_size / (1024 * 1024)

        conn.close()

        return HealthCheck(
            name="Database",
            passed=True,
            message=f"OK ({session_count} sessions, {db_size_mb:.2f} MB)",
            details=str(db_path)
        )

    except sqlite3.Error as e:
        return HealthCheck(
            name="Database",
            passed=False,
            message=f"Database error: {str(e)}",
            details="Database may be corrupted"
        )
    except Exception as e:
        return HealthCheck(
            name="Database",
            passed=False,
            message=f"Error: {str(e)}",
            details=None
        )


def check_python_version() -> HealthCheck:
    """Check Python version."""
    major, minor, micro = sys.version_info[:3]
    version_str = f"{major}.{minor}.{micro}"

    if (major, minor) >= (3, 11):
        return HealthCheck(
            name="Python Version",
            passed=True,
            message=f"{version_str}",
            details=None
        )
    else:
        return HealthCheck(
            name="Python Version",
            passed=False,
            message=f"{version_str} (requires >= 3.11)",
            details="Upgrade Python to 3.11 or higher"
        )


def check_dependencies() -> Tuple[HealthCheck, List[Tuple[str, str, bool]]]:
    """Check required dependencies.

    Returns:
        Tuple of (HealthCheck, list of (module, description, is_optional, installed))
    """
    deps = [
        ("ollama", "Ollama client", False),
        ("click", "CLI framework", False),
        ("rich", "Terminal formatting", False),
        ("pydantic", "Data validation", False),
        ("structlog", "Logging", False),
        ("textual", "TUI framework", True),
    ]

    results = []
    missing_required = []

    for module, description, is_optional in deps:
        try:
            __import__(module)
            results.append((module, description, is_optional, True))
        except ImportError:
            results.append((module, description, is_optional, False))
            if not is_optional:
                missing_required.append(module)

    if not missing_required:
        installed_count = sum(1 for _, _, _, installed in results if installed)
        return (
            HealthCheck(
                name="Dependencies",
                passed=True,
                message=f"{installed_count}/{len(deps)} packages available",
                details=None
            ),
            results
        )
    else:
        return (
            HealthCheck(
                name="Dependencies",
                passed=False,
                message=f"{len(missing_required)} required packages missing",
                details=f"Missing: {', '.join(missing_required)}"
            ),
            results
        )


def check_config(config_path: Optional[str] = None) -> HealthCheck:
    """Check configuration file."""
    try:
        from sindri.config import SindriConfig

        config = SindriConfig.load(config_path)

        # Basic validation
        warnings = []
        if config.total_vram_gb < 8:
            warnings.append("Low VRAM configuration (<8GB)")

        if warnings:
            return HealthCheck(
                name="Configuration",
                passed=True,
                message="Loaded with warnings",
                details="; ".join(warnings)
            )
        else:
            return HealthCheck(
                name="Configuration",
                passed=True,
                message="OK",
                details=f"Data dir: {config.data_dir}"
            )

    except FileNotFoundError:
        return HealthCheck(
            name="Configuration",
            passed=True,
            message="Using defaults",
            details="No config file found, using built-in defaults"
        )
    except Exception as e:
        return HealthCheck(
            name="Configuration",
            passed=False,
            message=f"Error: {str(e)}",
            details=None
        )


def get_all_checks(config_path: Optional[str] = None) -> Dict:
    """Run all health checks and return results.

    Returns:
        Dictionary with check results and metadata
    """
    results = {
        "ollama": check_ollama(),
        "python": check_python_version(),
        "config": check_config(config_path),
        "database": check_database(),
        "backups": check_backup(),
        "gpu": check_gpu_vram(),
    }

    # Models check returns tuple
    models_check, available_models, missing_models = check_required_models()
    results["models"] = models_check

    # Dependencies check returns tuple
    deps_check, dep_details = check_dependencies()
    results["dependencies"] = deps_check

    # Calculate overall status
    all_passed = all(check.passed for check in results.values())
    critical_passed = all(
        check.passed for name, check in results.items()
        if name in ["ollama", "python", "dependencies"]
    )

    return {
        "checks": results,
        "models": {
            "available": available_models,
            "missing": missing_models
        },
        "dependencies": dep_details,
        "overall": {
            "all_passed": all_passed,
            "critical_passed": critical_passed,
            "ready": critical_passed  # Can use Sindri if critical checks pass
        }
    }
