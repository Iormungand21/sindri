"""Configuration for Sindri with validation."""

from pathlib import Path
from typing import Optional, Dict
from pydantic import BaseModel, Field, field_validator, ConfigDict
import structlog

try:
    import toml
    HAS_TOML = True
except ImportError:
    HAS_TOML = False

log = structlog.get_logger()


class ModelConfig(BaseModel):
    """Model configuration."""
    name: str
    vram_gb: float = Field(gt=0, le=24, default=8.0)

    @field_validator('name')
    @classmethod
    def name_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Model name cannot be empty')
        return v.strip()


class MemoryConfig(BaseModel):
    """Memory system configuration."""
    enabled: bool = True
    episodic_limit: int = Field(gt=0, default=5)
    semantic_limit: int = Field(gt=0, default=10)
    max_context_tokens: int = Field(gt=0, default=16384)


class TUIConfig(BaseModel):
    """TUI configuration."""
    theme: str = Field(default="dark", pattern="^(dark|light)$")
    refresh_rate_ms: int = Field(gt=0, default=100)


class SindriConfig(BaseModel):
    """Main configuration for Sindri with validation."""

    model_config = ConfigDict(validate_assignment=True)

    # Paths
    data_dir: Path = Field(default_factory=lambda: Path.home() / ".sindri")
    db_path: Optional[Path] = None  # Computed from data_dir if None
    work_dir: Optional[Path] = None  # Working directory for file operations (None = cwd)

    # Ollama
    ollama_host: str = "http://localhost:11434"
    default_model: str = "qwen2.5-coder:14b"

    # Hardware
    total_vram_gb: float = Field(gt=0, default=16.0)
    reserve_vram_gb: float = Field(ge=0, default=2.0)

    # Models (optional custom configs)
    models: Dict[str, ModelConfig] = Field(default_factory=dict)

    # Memory
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    # TUI
    tui: TUIConfig = Field(default_factory=TUIConfig)

    # Execution
    max_iterations: int = Field(gt=0, default=50)
    completion_marker: str = "<sindri:complete/>"
    stuck_threshold: int = Field(gt=0, default=3)
    checkpoint_interval: int = Field(gt=0, default=5)

    # Logging
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR)$")
    log_file: Optional[Path] = None

    @field_validator('reserve_vram_gb')
    @classmethod
    def reserve_less_than_total(cls, v, info):
        if 'total_vram_gb' in info.data and v >= info.data['total_vram_gb']:
            raise ValueError('reserve_vram_gb must be less than total_vram_gb')
        return v

    def model_post_init(self, __context):
        """Set computed values after initialization."""
        # Set db_path from data_dir if not provided
        if self.db_path is None:
            self.db_path = self.data_dir / "sindri.db"

        # Ensure data_dir exists
        self.data_dir = Path(self.data_dir).expanduser()
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Set work_dir to current directory if not provided
        if self.work_dir is not None:
            self.work_dir = Path(self.work_dir).expanduser().resolve()

    @classmethod
    def load(cls, path: Optional[str] = None) -> 'SindriConfig':
        """Load configuration from TOML file.

        Search order if path not provided:
        1. ./sindri.toml (project-specific)
        2. ~/.sindri/config.toml (user default)

        Args:
            path: Optional explicit config file path

        Returns:
            SindriConfig instance
        """
        if path is None:
            # Search for config
            candidates = [
                Path("sindri.toml"),
                Path("~/.sindri/config.toml").expanduser()
            ]
            for candidate in candidates:
                if candidate.exists():
                    path = str(candidate)
                    log.info("config_found", path=path)
                    break

        if path and Path(path).exists():
            if not HAS_TOML:
                log.warning("toml_not_installed", fallback="defaults")
                return cls()

            try:
                data = toml.load(path)
                log.info("config_loaded", path=path)
                return cls(**data)
            except Exception as e:
                log.error("config_load_failed", path=path, error=str(e))
                return cls()

        log.info("config_using_defaults")
        return cls()

    def save(self, path: str):
        """Save configuration to TOML file.

        Args:
            path: File path to save to
        """
        if not HAS_TOML:
            raise RuntimeError("toml package not installed")

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            # Convert to dict, handling Path objects
            data = self.model_dump(mode='json')
            toml.dump(data, f)
        log.info("config_saved", path=path)


def validate_config(config: SindriConfig) -> list[str]:
    """Validate configuration and return warnings.

    Args:
        config: Config to validate

    Returns:
        List of warning messages
    """
    warnings = []

    # Check available VRAM
    available = config.total_vram_gb - config.reserve_vram_gb
    if available <= 0:
        warnings.append(
            f"No VRAM available after reserve ({config.total_vram_gb}GB total, "
            f"{config.reserve_vram_gb}GB reserved)"
        )

    # Check if models fit in VRAM
    if config.models:
        total_model_vram = sum(m.vram_gb for m in config.models.values())
        if total_model_vram > available:
            warnings.append(
                f"Total model VRAM ({total_model_vram:.1f}GB) exceeds available "
                f"({available:.1f}GB)"
            )

    # Check data directory is writable
    try:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        test_file = config.data_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
    except Exception as e:
        warnings.append(f"Data directory not writable: {e}")

    return warnings
