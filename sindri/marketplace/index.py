"""Local marketplace index for tracking installed plugins.

Maintains a registry of installed plugins, their sources, and metadata
to enable updates and management.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import json
import structlog

from sindri.marketplace.metadata import (
    PluginMetadata,
    PluginSource,
    SourceType,
    PluginCategory,
)

log = structlog.get_logger()


@dataclass
class InstalledPlugin:
    """Record of an installed plugin.

    Attributes:
        metadata: Plugin metadata
        source: Where the plugin was installed from
        installed_path: Local path where plugin is installed
        enabled: Whether the plugin is enabled
        pinned: If True, don't auto-update this plugin
    """

    metadata: PluginMetadata
    source: PluginSource
    installed_path: Path
    enabled: bool = True
    pinned: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "metadata": self.metadata.to_dict(),
            "source": self.source.to_dict(),
            "installed_path": str(self.installed_path),
            "enabled": self.enabled,
            "pinned": self.pinned,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InstalledPlugin":
        """Create from dictionary."""
        return cls(
            metadata=PluginMetadata.from_dict(data["metadata"]),
            source=PluginSource.from_dict(data["source"]),
            installed_path=Path(data["installed_path"]),
            enabled=data.get("enabled", True),
            pinned=data.get("pinned", False),
        )


class MarketplaceIndex:
    """Manages the local index of installed plugins.

    The index is stored as a JSON file at ~/.sindri/marketplace/index.json
    and tracks all plugins installed through the marketplace system.

    Example:
        index = MarketplaceIndex()
        index.load()

        # Add installed plugin
        index.add(InstalledPlugin(
            metadata=metadata,
            source=source,
            installed_path=path
        ))

        # Query plugins
        plugins = index.get_all()
        plugin = index.get("my_plugin")

        # Save changes
        index.save()
    """

    def __init__(self, index_dir: Optional[Path] = None):
        """Initialize the marketplace index.

        Args:
            index_dir: Directory for index file. Defaults to ~/.sindri/marketplace/
        """
        self.index_dir = index_dir or (Path.home() / ".sindri" / "marketplace")
        self.index_file = self.index_dir / "index.json"
        self._plugins: dict[str, InstalledPlugin] = {}
        self._loaded = False

    def load(self) -> None:
        """Load the index from disk."""
        if not self.index_file.exists():
            self._plugins = {}
            self._loaded = True
            return

        try:
            with open(self.index_file, "r") as f:
                data = json.load(f)

            self._plugins = {}
            for name, plugin_data in data.get("plugins", {}).items():
                try:
                    self._plugins[name] = InstalledPlugin.from_dict(plugin_data)
                except (KeyError, ValueError) as e:
                    log.warning("plugin_index_entry_invalid", name=name, error=str(e))

            self._loaded = True
            log.debug("marketplace_index_loaded", count=len(self._plugins))

        except (json.JSONDecodeError, OSError) as e:
            log.error("marketplace_index_load_failed", error=str(e))
            self._plugins = {}
            self._loaded = True

    def save(self) -> None:
        """Save the index to disk."""
        self.index_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "version": 1,
            "updated_at": datetime.now().isoformat(),
            "plugins": {
                name: plugin.to_dict() for name, plugin in self._plugins.items()
            },
        }

        try:
            with open(self.index_file, "w") as f:
                json.dump(data, f, indent=2)
            log.debug("marketplace_index_saved", count=len(self._plugins))
        except OSError as e:
            log.error("marketplace_index_save_failed", error=str(e))
            raise

    def _ensure_loaded(self) -> None:
        """Ensure index is loaded."""
        if not self._loaded:
            self.load()

    def add(self, plugin: InstalledPlugin) -> None:
        """Add or update a plugin in the index.

        Args:
            plugin: Plugin to add
        """
        self._ensure_loaded()
        self._plugins[plugin.metadata.name] = plugin
        log.info(
            "marketplace_plugin_added",
            name=plugin.metadata.name,
            version=plugin.metadata.version,
        )

    def remove(self, name: str) -> Optional[InstalledPlugin]:
        """Remove a plugin from the index.

        Args:
            name: Plugin name

        Returns:
            Removed plugin or None if not found
        """
        self._ensure_loaded()
        plugin = self._plugins.pop(name, None)
        if plugin:
            log.info("marketplace_plugin_removed", name=name)
        return plugin

    def get(self, name: str) -> Optional[InstalledPlugin]:
        """Get a plugin by name.

        Args:
            name: Plugin name

        Returns:
            InstalledPlugin or None if not found
        """
        self._ensure_loaded()
        return self._plugins.get(name)

    def get_all(self) -> list[InstalledPlugin]:
        """Get all installed plugins.

        Returns:
            List of all InstalledPlugin objects
        """
        self._ensure_loaded()
        return list(self._plugins.values())

    def get_by_category(self, category: PluginCategory) -> list[InstalledPlugin]:
        """Get plugins by category.

        Args:
            category: Plugin category

        Returns:
            List of plugins in that category
        """
        self._ensure_loaded()
        return [p for p in self._plugins.values() if p.metadata.category == category]

    def get_by_type(self, plugin_type: str) -> list[InstalledPlugin]:
        """Get plugins by type (tool or agent).

        Args:
            plugin_type: "tool" or "agent"

        Returns:
            List of plugins of that type
        """
        self._ensure_loaded()
        return [
            p for p in self._plugins.values() if p.metadata.plugin_type == plugin_type
        ]

    def exists(self, name: str) -> bool:
        """Check if a plugin is installed.

        Args:
            name: Plugin name

        Returns:
            True if installed
        """
        self._ensure_loaded()
        return name in self._plugins

    def get_outdated(self) -> list[tuple[InstalledPlugin, str]]:
        """Get plugins that may have updates available.

        Note: This only identifies plugins from git sources that
        might have updates. Actual version checking requires
        fetching from the source.

        Returns:
            List of (plugin, source_location) tuples
        """
        self._ensure_loaded()
        outdated = []
        for plugin in self._plugins.values():
            if plugin.pinned:
                continue
            if plugin.source.type in (SourceType.GIT, SourceType.URL):
                outdated.append((plugin, plugin.source.location))
        return outdated

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """Enable or disable a plugin.

        Args:
            name: Plugin name
            enabled: New enabled state

        Returns:
            True if plugin was found and updated
        """
        self._ensure_loaded()
        plugin = self._plugins.get(name)
        if plugin:
            plugin.enabled = enabled
            log.info("marketplace_plugin_enabled_changed", name=name, enabled=enabled)
            return True
        return False

    def set_pinned(self, name: str, pinned: bool) -> bool:
        """Pin or unpin a plugin (prevents auto-update).

        Args:
            name: Plugin name
            pinned: New pinned state

        Returns:
            True if plugin was found and updated
        """
        self._ensure_loaded()
        plugin = self._plugins.get(name)
        if plugin:
            plugin.pinned = pinned
            log.info("marketplace_plugin_pinned_changed", name=name, pinned=pinned)
            return True
        return False

    def get_stats(self) -> dict:
        """Get statistics about installed plugins.

        Returns:
            Dict with counts by type, category, source
        """
        self._ensure_loaded()

        by_type = {"tool": 0, "agent": 0}
        by_category: dict[str, int] = {}
        by_source: dict[str, int] = {}
        enabled_count = 0
        pinned_count = 0

        for plugin in self._plugins.values():
            # By type
            plugin_type = plugin.metadata.plugin_type
            by_type[plugin_type] = by_type.get(plugin_type, 0) + 1

            # By category
            cat = plugin.metadata.category.value
            by_category[cat] = by_category.get(cat, 0) + 1

            # By source
            src = plugin.source.type.value
            by_source[src] = by_source.get(src, 0) + 1

            if plugin.enabled:
                enabled_count += 1
            if plugin.pinned:
                pinned_count += 1

        return {
            "total": len(self._plugins),
            "enabled": enabled_count,
            "pinned": pinned_count,
            "by_type": by_type,
            "by_category": by_category,
            "by_source": by_source,
        }

    def clear(self) -> None:
        """Clear all plugins from the index."""
        self._plugins = {}
        log.info("marketplace_index_cleared")
