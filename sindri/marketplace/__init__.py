"""Plugin marketplace for Sindri.

Enables discovering, installing, and sharing plugins from various sources
including git repositories, URLs, and local paths.

Features:
- Search for plugins by name, category, or tags
- Install plugins from git repos, URLs, or local paths
- Track installed plugins and their sources
- Package plugins for sharing
- Update plugins to latest versions

CLI Commands:
    sindri marketplace search <query>     # Search available plugins
    sindri marketplace install <source>   # Install from URL/path/git
    sindri marketplace uninstall <name>   # Remove installed plugin
    sindri marketplace update [name]      # Update plugins
    sindri marketplace info <name>        # Show plugin details
    sindri marketplace publish <path>     # Package for sharing
"""

from sindri.marketplace.metadata import (
    PluginCategory,
    PluginMetadata,
    PluginSource,
    SourceType,
)
from sindri.marketplace.index import (
    MarketplaceIndex,
    InstalledPlugin,
)
from sindri.marketplace.installer import (
    PluginInstaller,
    InstallResult,
    UninstallResult,
)
from sindri.marketplace.search import (
    PluginSearcher,
    SearchResult,
)

__all__ = [
    # Metadata
    "PluginCategory",
    "PluginMetadata",
    "PluginSource",
    "SourceType",
    # Index
    "MarketplaceIndex",
    "InstalledPlugin",
    # Installer
    "PluginInstaller",
    "InstallResult",
    "UninstallResult",
    # Search
    "PluginSearcher",
    "SearchResult",
]
