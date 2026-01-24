"""Project registry for multi-project memory (Phase 8.4).

Extended with Multi-Project Workspace Index (ROADMAP Item 4):
- Per-project embedder settings (chunk size, exclusion patterns)
- Active/pinned projects for immediate context inclusion
- Auto-index and priority settings for background indexer
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import structlog

log = structlog.get_logger()


@dataclass
class ProjectEmbedderSettings:
    """Per-project embedder configuration for workspace indexing.

    Allows customization of how a project is indexed, including chunk sizes
    and file inclusion/exclusion patterns.
    """

    chunk_size_lines: int = 50  # Lines per chunk (default matches GlobalMemoryStore)
    max_chunk_chars: int = 2000  # Maximum characters per chunk
    max_line_chars: int = 500  # Truncate lines longer than this
    file_extensions: Optional[List[str]] = None  # Override default extensions (None = use defaults)
    exclude_patterns: List[str] = field(default_factory=list)  # Glob patterns to exclude
    include_patterns: List[str] = field(default_factory=list)  # Glob patterns to include (priority)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "chunk_size_lines": self.chunk_size_lines,
            "max_chunk_chars": self.max_chunk_chars,
            "max_line_chars": self.max_line_chars,
            "file_extensions": self.file_extensions,
            "exclude_patterns": self.exclude_patterns,
            "include_patterns": self.include_patterns,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectEmbedderSettings":
        """Create from dictionary."""
        return cls(
            chunk_size_lines=data.get("chunk_size_lines", 50),
            max_chunk_chars=data.get("max_chunk_chars", 2000),
            max_line_chars=data.get("max_line_chars", 500),
            file_extensions=data.get("file_extensions"),
            exclude_patterns=data.get("exclude_patterns", []),
            include_patterns=data.get("include_patterns", []),
        )


@dataclass
class ProjectRoutingPreferences:
    """Per-project model routing preferences (ROADMAP Item 10).

    Allows customization of how models are selected for tasks in a project,
    including category-based overrides and agent-specific locks.
    """

    # Override models for specific task categories (category name -> model name)
    model_overrides: Dict[str, str] = field(default_factory=dict)
    # Lock specific agents to specific models (agent name -> model name)
    locked_models: Dict[str, str] = field(default_factory=dict)
    # Speed vs quality preference (None = use global setting)
    speed_preference: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "model_overrides": self.model_overrides,
            "locked_models": self.locked_models,
            "speed_preference": self.speed_preference,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectRoutingPreferences":
        """Create from dictionary."""
        return cls(
            model_overrides=data.get("model_overrides", {}),
            locked_models=data.get("locked_models", {}),
            speed_preference=data.get("speed_preference"),
        )


@dataclass
class ProjectConfig:
    """Configuration for a registered project.

    Extended with workspace index fields:
    - active: Pin project for immediate context inclusion in agent prompts
    - auto_index: Include in background indexer queue
    - index_priority: Priority in indexer queue (1=highest, 10=lowest)
    - embedder_settings: Per-project indexing configuration
    - routing_preferences: Per-project model routing preferences
    """

    path: str
    name: str = ""
    tags: List[str] = field(default_factory=list)
    enabled: bool = True
    indexed: bool = False
    last_indexed: Optional[datetime] = None
    file_count: int = 0
    created_at: Optional[datetime] = None
    # Workspace Index fields (ROADMAP Item 4)
    active: bool = False  # Pinned for immediate context inclusion
    auto_index: bool = True  # Include in background indexer
    index_priority: int = 5  # Priority: 1=highest, 10=lowest
    embedder_settings: Optional[ProjectEmbedderSettings] = None  # Per-project config
    # Model Routing fields (ROADMAP Item 10)
    routing_preferences: Optional[ProjectRoutingPreferences] = None  # Per-project routing

    def __post_init__(self):
        if not self.name:
            # Default name from directory
            self.name = Path(self.path).name
        if not self.created_at:
            self.created_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "path": self.path,
            "name": self.name,
            "tags": self.tags,
            "enabled": self.enabled,
            "indexed": self.indexed,
            "last_indexed": (
                self.last_indexed.isoformat() if self.last_indexed else None
            ),
            "file_count": self.file_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            # Workspace Index fields
            "active": self.active,
            "auto_index": self.auto_index,
            "index_priority": self.index_priority,
            "embedder_settings": (
                self.embedder_settings.to_dict() if self.embedder_settings else None
            ),
            # Model Routing fields (ROADMAP Item 10)
            "routing_preferences": (
                self.routing_preferences.to_dict() if self.routing_preferences else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectConfig":
        """Create from dictionary."""
        # Parse embedder settings if present
        embedder_settings = None
        if data.get("embedder_settings"):
            embedder_settings = ProjectEmbedderSettings.from_dict(data["embedder_settings"])

        # Parse routing preferences if present (ROADMAP Item 10)
        routing_preferences = None
        if data.get("routing_preferences"):
            routing_preferences = ProjectRoutingPreferences.from_dict(data["routing_preferences"])

        return cls(
            path=data["path"],
            name=data.get("name", ""),
            tags=data.get("tags", []),
            enabled=data.get("enabled", True),
            indexed=data.get("indexed", False),
            last_indexed=(
                datetime.fromisoformat(data["last_indexed"])
                if data.get("last_indexed")
                else None
            ),
            file_count=data.get("file_count", 0),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else None
            ),
            # Workspace Index fields
            active=data.get("active", False),
            auto_index=data.get("auto_index", True),
            index_priority=data.get("index_priority", 5),
            embedder_settings=embedder_settings,
            # Model Routing fields (ROADMAP Item 10)
            routing_preferences=routing_preferences,
        )

    def matches_tag(self, tag: str) -> bool:
        """Check if project has a specific tag."""
        return tag.lower() in [t.lower() for t in self.tags]

    def matches_any_tag(self, tags: List[str]) -> bool:
        """Check if project has any of the specified tags."""
        lower_tags = [t.lower() for t in self.tags]
        return any(t.lower() in lower_tags for t in tags)


class ProjectRegistry:
    """Registry for managing multi-project memory configurations.

    Stores project configurations in ~/.sindri/projects.json
    """

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize project registry.

        Args:
            config_path: Path to projects.json. Defaults to ~/.sindri/projects.json
        """
        if config_path is None:
            config_path = Path.home() / ".sindri" / "projects.json"

        self.config_path = config_path
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._projects: Dict[str, ProjectConfig] = {}
        self._load()
        log.info("project_registry_initialized", path=str(config_path))

    def _load(self):
        """Load projects from config file."""
        if not self.config_path.exists():
            self._projects = {}
            return

        try:
            with open(self.config_path, "r") as f:
                data = json.load(f)

            self._projects = {}
            for path, proj_data in data.get("projects", {}).items():
                proj_data["path"] = path  # Ensure path is set
                self._projects[path] = ProjectConfig.from_dict(proj_data)

            log.info("projects_loaded", count=len(self._projects))
        except Exception as e:
            log.warning("projects_load_failed", error=str(e))
            self._projects = {}

    def _save(self):
        """Save projects to config file."""
        try:
            data = {
                "version": 1,
                "projects": {
                    path: proj.to_dict() for path, proj in self._projects.items()
                },
            }

            with open(self.config_path, "w") as f:
                json.dump(data, f, indent=2)

            log.debug("projects_saved", count=len(self._projects))
        except Exception as e:
            log.error("projects_save_failed", error=str(e))
            raise

    def add_project(
        self,
        path: str,
        name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        enabled: bool = True,
    ) -> ProjectConfig:
        """Add a project to the registry.

        Args:
            path: Path to the project directory
            name: Optional project name (defaults to directory name)
            tags: Optional list of tags for categorization
            enabled: Whether to include in cross-project search

        Returns:
            ProjectConfig for the added project
        """
        # Normalize path
        path_obj = Path(path).resolve()
        if not path_obj.exists():
            raise ValueError(f"Project path does not exist: {path}")
        if not path_obj.is_dir():
            raise ValueError(f"Project path is not a directory: {path}")

        normalized_path = str(path_obj)

        # Check if already exists
        if normalized_path in self._projects:
            log.info("project_already_exists", path=normalized_path)
            # Update existing project
            existing = self._projects[normalized_path]
            if name:
                existing.name = name
            if tags:
                existing.tags = list(set(existing.tags + tags))
            existing.enabled = enabled
            self._save()
            return existing

        # Create new project config
        project = ProjectConfig(
            path=normalized_path,
            name=name or path_obj.name,
            tags=tags or [],
            enabled=enabled,
        )

        self._projects[normalized_path] = project
        self._save()

        log.info("project_added", path=normalized_path, name=project.name)
        return project

    def remove_project(self, path: str) -> bool:
        """Remove a project from the registry.

        Args:
            path: Path to the project directory

        Returns:
            True if project was removed, False if not found
        """
        # Normalize path
        path_obj = Path(path).resolve()
        normalized_path = str(path_obj)

        # Also check if the original path matches (without normalization)
        if normalized_path not in self._projects and path not in self._projects:
            log.warning("project_not_found", path=path)
            return False

        # Try normalized first, then original
        actual_path = normalized_path if normalized_path in self._projects else path
        del self._projects[actual_path]
        self._save()

        log.info("project_removed", path=actual_path)
        return True

    def get_project(self, path: str) -> Optional[ProjectConfig]:
        """Get a project by path.

        Args:
            path: Path to the project directory

        Returns:
            ProjectConfig if found, None otherwise
        """
        # Normalize path
        path_obj = Path(path).resolve()
        normalized_path = str(path_obj)

        return self._projects.get(normalized_path) or self._projects.get(path)

    def list_projects(
        self, enabled_only: bool = False, tags: Optional[List[str]] = None
    ) -> List[ProjectConfig]:
        """List all registered projects.

        Args:
            enabled_only: If True, only return enabled projects
            tags: If specified, only return projects with matching tags

        Returns:
            List of ProjectConfig objects
        """
        projects = list(self._projects.values())

        if enabled_only:
            projects = [p for p in projects if p.enabled]

        if tags:
            projects = [p for p in projects if p.matches_any_tag(tags)]

        # Sort by name
        projects.sort(key=lambda p: p.name.lower())
        return projects

    def tag_project(self, path: str, tags: List[str]) -> Optional[ProjectConfig]:
        """Set tags for a project.

        Args:
            path: Path to the project directory
            tags: List of tags to set (replaces existing tags)

        Returns:
            Updated ProjectConfig, or None if project not found
        """
        project = self.get_project(path)
        if not project:
            log.warning("project_not_found_for_tagging", path=path)
            return None

        project.tags = tags
        self._save()

        log.info("project_tagged", path=path, tags=tags)
        return project

    def add_tags(self, path: str, tags: List[str]) -> Optional[ProjectConfig]:
        """Add tags to a project (without replacing existing).

        Args:
            path: Path to the project directory
            tags: List of tags to add

        Returns:
            Updated ProjectConfig, or None if project not found
        """
        project = self.get_project(path)
        if not project:
            log.warning("project_not_found_for_tagging", path=path)
            return None

        # Merge tags (case-insensitive dedup)
        existing_lower = {t.lower() for t in project.tags}
        for tag in tags:
            if tag.lower() not in existing_lower:
                project.tags.append(tag)
                existing_lower.add(tag.lower())

        self._save()

        log.info("project_tags_added", path=path, tags=project.tags)
        return project

    def set_indexed(
        self, path: str, indexed: bool, file_count: int = 0
    ) -> Optional[ProjectConfig]:
        """Mark a project as indexed/unindexed.

        Args:
            path: Path to the project directory
            indexed: Whether the project is indexed
            file_count: Number of files indexed

        Returns:
            Updated ProjectConfig, or None if project not found
        """
        project = self.get_project(path)
        if not project:
            return None

        project.indexed = indexed
        project.file_count = file_count
        if indexed:
            project.last_indexed = datetime.now()

        self._save()
        return project

    def enable_project(
        self, path: str, enabled: bool = True
    ) -> Optional[ProjectConfig]:
        """Enable or disable a project for cross-project search.

        Args:
            path: Path to the project directory
            enabled: Whether to enable (True) or disable (False)

        Returns:
            Updated ProjectConfig, or None if project not found
        """
        project = self.get_project(path)
        if not project:
            return None

        project.enabled = enabled
        self._save()

        log.info("project_enabled_changed", path=path, enabled=enabled)
        return project

    def find_by_name(self, name: str) -> Optional[ProjectConfig]:
        """Find a project by name (case-insensitive).

        Args:
            name: Project name to search for

        Returns:
            ProjectConfig if found, None otherwise
        """
        name_lower = name.lower()
        for project in self._projects.values():
            if project.name.lower() == name_lower:
                return project
        return None

    def get_project_count(self) -> int:
        """Get the total number of registered projects."""
        return len(self._projects)

    def get_enabled_project_count(self) -> int:
        """Get the number of enabled projects."""
        return sum(1 for p in self._projects.values() if p.enabled)

    def get_indexed_project_count(self) -> int:
        """Get the number of indexed projects."""
        return sum(1 for p in self._projects.values() if p.indexed)

    def get_all_tags(self) -> List[str]:
        """Get all unique tags across all projects."""
        tags_set = set()
        for project in self._projects.values():
            tags_set.update(project.tags)
        return sorted(tags_set, key=str.lower)

    # Workspace Index methods (ROADMAP Item 4)

    def list_active_projects(self) -> List[ProjectConfig]:
        """List all active (pinned) projects for context inclusion.

        Returns:
            List of ProjectConfig objects with active=True
        """
        projects = [p for p in self._projects.values() if p.active]
        # Sort by priority (lower = higher priority), then name
        projects.sort(key=lambda p: (p.index_priority, p.name.lower()))
        return projects

    def get_active_project_count(self) -> int:
        """Get the number of active (pinned) projects."""
        return sum(1 for p in self._projects.values() if p.active)

    def set_active(self, path: str, active: bool = True) -> Optional[ProjectConfig]:
        """Set a project as active/inactive for context inclusion.

        Args:
            path: Path to the project directory
            active: Whether to mark as active (True) or inactive (False)

        Returns:
            Updated ProjectConfig, or None if project not found
        """
        project = self.get_project(path)
        if not project:
            log.warning("project_not_found_for_activation", path=path)
            return None

        project.active = active
        self._save()

        log.info("project_active_changed", path=path, active=active)
        return project

    def set_auto_index(
        self, path: str, auto_index: bool = True, priority: Optional[int] = None
    ) -> Optional[ProjectConfig]:
        """Configure auto-indexing for a project.

        Args:
            path: Path to the project directory
            auto_index: Whether to include in background indexer
            priority: Optional priority (1=highest, 10=lowest)

        Returns:
            Updated ProjectConfig, or None if project not found
        """
        project = self.get_project(path)
        if not project:
            log.warning("project_not_found_for_auto_index", path=path)
            return None

        project.auto_index = auto_index
        if priority is not None:
            project.index_priority = max(1, min(10, priority))  # Clamp to 1-10

        self._save()

        log.info(
            "project_auto_index_changed",
            path=path,
            auto_index=auto_index,
            priority=project.index_priority,
        )
        return project

    def set_embedder_settings(
        self, path: str, settings: ProjectEmbedderSettings
    ) -> Optional[ProjectConfig]:
        """Set embedder settings for a project.

        Args:
            path: Path to the project directory
            settings: ProjectEmbedderSettings instance

        Returns:
            Updated ProjectConfig, or None if project not found
        """
        project = self.get_project(path)
        if not project:
            log.warning("project_not_found_for_settings", path=path)
            return None

        project.embedder_settings = settings
        self._save()

        log.info("project_embedder_settings_changed", path=path)
        return project

    def clear_embedder_settings(self, path: str) -> Optional[ProjectConfig]:
        """Clear embedder settings for a project (use defaults).

        Args:
            path: Path to the project directory

        Returns:
            Updated ProjectConfig, or None if project not found
        """
        project = self.get_project(path)
        if not project:
            return None

        project.embedder_settings = None
        self._save()

        log.info("project_embedder_settings_cleared", path=path)
        return project

    def list_auto_index_projects(self) -> List[ProjectConfig]:
        """List all projects enabled for auto-indexing.

        Returns:
            List of ProjectConfig objects with auto_index=True, sorted by priority
        """
        projects = [p for p in self._projects.values() if p.auto_index and p.enabled]
        # Sort by priority (lower = higher priority)
        projects.sort(key=lambda p: (p.index_priority, p.name.lower()))
        return projects
