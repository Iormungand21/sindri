"""Configuration for Sindri with validation."""

from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from sindri.core.policy import AgentPolicy
from pydantic import BaseModel, Field, field_validator, ConfigDict
import structlog


class SystemAccessLevel(str, Enum):
    """Control how much autonomous system access Sindri has.

    This is part of Milestone 5 of the architecture transformation,
    preparing Sindri for autonomous operation on a dedicated research machine.
    """

    RESTRICTED = "restricted"  # Read-only system info, no modifications
    SUPERVISED = "supervised"  # Can modify with confirmation prompts
    FULL = "full"  # Full autonomous access (for dedicated machine)

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

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Model name cannot be empty")
        return v.strip()


class IndexerConfig(BaseModel):
    """Background indexer configuration (ROADMAP Item 4).

    Controls the behavior of the multi-project workspace indexer.
    """

    enabled: bool = Field(
        default=True,
        description="Whether the background indexer is enabled",
    )
    auto_start: bool = Field(
        default=False,
        description="Start indexer automatically with TUI/Web",
    )
    schedule_interval_minutes: int = Field(
        default=60,
        ge=0,
        description="Re-index interval in minutes (0 = no automatic re-indexing)",
    )
    max_vram_percent: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Max VRAM fraction to use for embedding (0.0-1.0)",
    )
    cooldown_seconds: float = Field(
        default=1.0,
        ge=0.0,
        description="Pause between indexing projects (seconds)",
    )
    include_active_in_context: bool = Field(
        default=True,
        description="Include active project context in agent prompts",
    )
    active_project_budget_tokens: int = Field(
        default=2000,
        gt=0,
        description="Token budget for active project context",
    )


class MemoryConfig(BaseModel):
    """Memory system configuration."""

    enabled: bool = True
    episodic_limit: int = Field(gt=0, default=5)
    semantic_limit: int = Field(gt=0, default=10)
    max_context_tokens: int = Field(gt=0, default=16384)
    # Workspace indexer settings (ROADMAP Item 4)
    indexer: IndexerConfig = Field(default_factory=IndexerConfig)


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
    work_dir: Optional[Path] = (
        None  # Working directory for file operations (None = cwd)
    )

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

    # System Access Configuration (Milestone 5)
    system_access: SystemAccessLevel = Field(
        default=SystemAccessLevel.SUPERVISED,
        description="System access level: restricted, supervised, or full",
    )
    allowed_services: List[str] = Field(
        default_factory=lambda: ["ollama", "litellm", "sindri"],
        description="Services Sindri can manage (when supervised/full)",
    )
    allow_self_modification: bool = Field(
        default=False,
        description="Whether Sindri can modify its own config",
    )

    # Tool Permissions (Granular Tool Permissions feature)
    allowed_tools: Optional[List[str]] = Field(
        default=None,
        description="Allowlist of tool names (None = all tools allowed)",
    )
    blocked_tools: List[str] = Field(
        default_factory=list,
        description="Blocklist of tool names (applied after allowlist)",
    )
    tool_approval_required: List[str] = Field(
        default_factory=list,
        description="Tools requiring explicit approval before execution",
    )
    default_dry_run: bool = Field(
        default=False,
        description="Run dangerous tools in dry-run mode by default",
    )

    # Policy + Guardrails: Global defaults for agent policies
    default_max_tool_calls: Optional[int] = Field(
        default=None,
        description="Default max tool calls per task (None = unlimited)",
    )
    default_max_files_touched: Optional[int] = Field(
        default=None,
        description="Default max files an agent can touch per task",
    )
    default_max_runtime_seconds: Optional[float] = Field(
        default=None,
        description="Default max runtime in seconds per task",
    )
    default_file_scope: List[str] = Field(
        default_factory=list,
        description="Default allowed file patterns (glob)",
    )
    default_escalation_mode: str = Field(
        default="deny",
        description="Default escalation mode: deny, warn, or escalate",
    )
    policy_audit_enabled: bool = Field(
        default=True,
        description="Log policy violations to audit log",
    )

    @field_validator("allowed_services")
    @classmethod
    def validate_allowed_services(cls, v):
        """Ensure allowed_services contains only valid service names."""
        if not isinstance(v, list):
            raise ValueError("allowed_services must be a list")
        result = []
        for service in v:
            if not isinstance(service, str) or not service.strip():
                raise ValueError("Each service must be a non-empty string")
            result.append(service.strip())
        return result

    @field_validator("reserve_vram_gb")
    @classmethod
    def reserve_less_than_total(cls, v, info):
        if "total_vram_gb" in info.data and v >= info.data["total_vram_gb"]:
            raise ValueError("reserve_vram_gb must be less than total_vram_gb")
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
    def load(cls, path: Optional[str] = None) -> "SindriConfig":
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
                Path("~/.sindri/config.toml").expanduser(),
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
        with open(path, "w") as f:
            # Convert to dict, handling Path objects
            data = self.model_dump(mode="json")
            toml.dump(data, f)
        log.info("config_saved", path=path)

    def get_default_policy(self) -> "AgentPolicy":
        """Get the default agent policy from config.

        Returns:
            AgentPolicy with global defaults
        """
        from sindri.core.policy import AgentPolicy, EscalationMode

        return AgentPolicy(
            max_tool_calls=self.default_max_tool_calls,
            max_files_touched=self.default_max_files_touched,
            max_runtime_seconds=self.default_max_runtime_seconds,
            file_scope=self.default_file_scope,
            escalation_mode=EscalationMode(self.default_escalation_mode),
        )


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
