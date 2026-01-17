"""Plugin metadata definitions for the marketplace.

Extends the core PluginInfo with additional fields for marketplace features
like categories, tags, dependencies, and source information.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Optional
import json


class PluginCategory(str, Enum):
    """Categories for organizing plugins."""

    # Tool categories
    FILESYSTEM = "filesystem"      # File operations
    GIT = "git"                    # Git/VCS tools
    HTTP = "http"                  # HTTP/API tools
    DATABASE = "database"          # Database tools
    TESTING = "testing"            # Test runners, assertions
    FORMATTING = "formatting"      # Code formatting/linting
    REFACTORING = "refactoring"    # Code refactoring
    ANALYSIS = "analysis"          # Code analysis
    SECURITY = "security"          # Security scanning
    DEVOPS = "devops"              # CI/CD, deployment
    DOCUMENTATION = "documentation" # Doc generation

    # Agent categories
    CODER = "coder"                # Code generation agents
    REVIEWER = "reviewer"          # Code review agents
    PLANNER = "planner"            # Planning/architecture agents
    SPECIALIST = "specialist"      # Domain-specific agents

    # General
    UTILITY = "utility"            # General utilities
    OTHER = "other"                # Uncategorized


class SourceType(str, Enum):
    """Types of plugin sources for installation."""

    LOCAL = "local"          # Local file path
    GIT = "git"              # Git repository URL
    URL = "url"              # Direct download URL
    MARKETPLACE = "marketplace"  # Community marketplace (future)


@dataclass
class PluginSource:
    """Information about where a plugin was installed from.

    Attributes:
        type: Type of source (local, git, url)
        location: Source location (path, URL, git repo)
        ref: Git ref (branch, tag, commit) if applicable
        installed_at: When the plugin was installed
        updated_at: When the plugin was last updated
    """
    type: SourceType
    location: str
    ref: Optional[str] = None
    installed_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type.value,
            "location": self.location,
            "ref": self.ref,
            "installed_at": self.installed_at.isoformat() if self.installed_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PluginSource":
        """Create from dictionary."""
        return cls(
            type=SourceType(data["type"]),
            location=data["location"],
            ref=data.get("ref"),
            installed_at=datetime.fromisoformat(data["installed_at"]) if data.get("installed_at") else None,
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
        )


@dataclass
class PluginMetadata:
    """Extended metadata for marketplace plugins.

    Attributes:
        name: Unique plugin name
        version: Semantic version string
        description: Brief description
        author: Author name or handle
        category: Primary category
        tags: List of searchable tags
        homepage: Project homepage URL
        repository: Source code repository URL
        license: License identifier (MIT, Apache-2.0, etc.)
        dependencies: List of plugin names this depends on
        sindri_version: Compatible Sindri version range
        plugin_type: "tool" or "agent"
        readme: Full readme content (if available)
        changelog: Version history (if available)
    """
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    category: PluginCategory = PluginCategory.OTHER
    tags: list[str] = field(default_factory=list)
    homepage: str = ""
    repository: str = ""
    license: str = ""
    dependencies: list[str] = field(default_factory=list)
    sindri_version: str = ">=0.1.0"
    plugin_type: str = "tool"  # "tool" or "agent"
    readme: str = ""
    changelog: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "category": self.category.value if isinstance(self.category, PluginCategory) else self.category,
            "tags": self.tags,
            "homepage": self.homepage,
            "repository": self.repository,
            "license": self.license,
            "dependencies": self.dependencies,
            "sindri_version": self.sindri_version,
            "plugin_type": self.plugin_type,
            "readme": self.readme,
            "changelog": self.changelog,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PluginMetadata":
        """Create from dictionary."""
        category = data.get("category", "other")
        if isinstance(category, str):
            try:
                category = PluginCategory(category)
            except ValueError:
                category = PluginCategory.OTHER

        return cls(
            name=data["name"],
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            category=category,
            tags=data.get("tags", []),
            homepage=data.get("homepage", ""),
            repository=data.get("repository", ""),
            license=data.get("license", ""),
            dependencies=data.get("dependencies", []),
            sindri_version=data.get("sindri_version", ">=0.1.0"),
            plugin_type=data.get("plugin_type", "tool"),
            readme=data.get("readme", ""),
            changelog=data.get("changelog", ""),
        )

    @classmethod
    def from_plugin_file(cls, path: Path) -> Optional["PluginMetadata"]:
        """Extract metadata from a plugin file.

        For Python plugins, extracts from docstrings and __metadata__.
        For TOML plugins, extracts from [metadata] section.

        Args:
            path: Path to plugin file

        Returns:
            PluginMetadata or None if extraction fails
        """
        if path.suffix == ".py":
            return cls._from_python_file(path)
        elif path.suffix == ".toml":
            return cls._from_toml_file(path)
        return None

    @classmethod
    def _from_python_file(cls, path: Path) -> Optional["PluginMetadata"]:
        """Extract metadata from Python plugin file."""
        import ast

        try:
            source = path.read_text()
            tree = ast.parse(source)
        except (SyntaxError, OSError):
            return None

        metadata = {
            "name": path.stem,
            "plugin_type": "tool",
        }

        # Get docstring as description
        if tree.body and isinstance(tree.body[0], ast.Expr):
            if isinstance(tree.body[0].value, ast.Constant):
                docstring = tree.body[0].value.value
                if isinstance(docstring, str):
                    lines = docstring.strip().split("\n")
                    if lines:
                        metadata["description"] = lines[0].strip()

        # Look for __metadata__ dict or individual dunders
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        name = target.id
                        if name == "__metadata__" and isinstance(node.value, ast.Dict):
                            # Parse dict literal
                            for key, value in zip(node.value.keys, node.value.values):
                                if isinstance(key, ast.Constant) and isinstance(value, ast.Constant):
                                    metadata[key.value] = value.value
                        elif name == "__version__" and isinstance(node.value, ast.Constant):
                            metadata["version"] = str(node.value.value)
                        elif name == "__author__" and isinstance(node.value, ast.Constant):
                            metadata["author"] = str(node.value.value)

        return cls.from_dict(metadata)

    @classmethod
    def _from_toml_file(cls, path: Path) -> Optional["PluginMetadata"]:
        """Extract metadata from TOML agent config file."""
        try:
            import toml
            config = toml.load(path)
        except Exception:
            return None

        metadata = {
            "name": path.stem,
            "plugin_type": "agent",
        }

        # Get agent section
        if "agent" in config:
            agent = config["agent"]
            metadata["name"] = agent.get("name", path.stem)
            metadata["description"] = agent.get("description", agent.get("role", ""))

        # Get metadata section
        if "metadata" in config:
            meta = config["metadata"]
            metadata.update({
                "version": meta.get("version", "0.1.0"),
                "author": meta.get("author", ""),
                "category": meta.get("category", "specialist"),
                "tags": meta.get("tags", []),
                "homepage": meta.get("homepage", ""),
                "repository": meta.get("repository", ""),
                "license": meta.get("license", ""),
                "dependencies": meta.get("dependencies", []),
                "sindri_version": meta.get("sindri_version", ">=0.1.0"),
            })

        return cls.from_dict(metadata)


def parse_manifest(manifest_path: Path) -> Optional[PluginMetadata]:
    """Parse a sindri-plugin.json manifest file.

    The manifest file contains full metadata for a plugin package:

    {
        "name": "my_plugin",
        "version": "1.0.0",
        "description": "A useful plugin",
        "author": "author",
        "category": "utility",
        "tags": ["tag1", "tag2"],
        "plugin_type": "tool",
        "entry_point": "my_plugin.py",
        ...
    }

    Args:
        manifest_path: Path to sindri-plugin.json

    Returns:
        PluginMetadata or None if parsing fails
    """
    try:
        with open(manifest_path, "r") as f:
            data = json.load(f)
        return PluginMetadata.from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError):
        return None
