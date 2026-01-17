"""Project registry for multi-project memory (Phase 8.4)."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import structlog

log = structlog.get_logger()


@dataclass
class ProjectConfig:
    """Configuration for a registered project."""

    path: str
    name: str = ""
    tags: List[str] = field(default_factory=list)
    enabled: bool = True
    indexed: bool = False
    last_indexed: Optional[datetime] = None
    file_count: int = 0
    created_at: Optional[datetime] = None

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
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectConfig":
        """Create from dictionary."""
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
