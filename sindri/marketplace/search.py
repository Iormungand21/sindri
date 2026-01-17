"""Plugin search and discovery for the marketplace.

Provides search functionality across installed plugins and
local plugin directories.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import structlog

from sindri.marketplace.metadata import PluginMetadata, PluginCategory
from sindri.marketplace.index import MarketplaceIndex, InstalledPlugin
from sindri.plugins.loader import PluginLoader, PluginType

log = structlog.get_logger()


@dataclass
class SearchResult:
    """Result from a plugin search.

    Attributes:
        name: Plugin name
        version: Plugin version
        description: Plugin description
        category: Plugin category
        tags: Plugin tags
        plugin_type: "tool" or "agent"
        installed: Whether plugin is installed
        installed_path: Path if installed
        source: Source location if installed
        score: Search relevance score (0-100)
    """
    name: str
    version: str
    description: str
    category: str
    tags: list[str]
    plugin_type: str
    installed: bool = False
    installed_path: Optional[Path] = None
    source: Optional[str] = None
    score: int = 0

    @classmethod
    def from_installed_plugin(cls, plugin: InstalledPlugin) -> "SearchResult":
        """Create from an InstalledPlugin."""
        return cls(
            name=plugin.metadata.name,
            version=plugin.metadata.version,
            description=plugin.metadata.description,
            category=plugin.metadata.category.value if isinstance(plugin.metadata.category, PluginCategory) else plugin.metadata.category,
            tags=plugin.metadata.tags,
            plugin_type=plugin.metadata.plugin_type,
            installed=True,
            installed_path=plugin.installed_path,
            source=plugin.source.location,
        )

    @classmethod
    def from_metadata(cls, metadata: PluginMetadata, path: Optional[Path] = None) -> "SearchResult":
        """Create from PluginMetadata."""
        return cls(
            name=metadata.name,
            version=metadata.version,
            description=metadata.description,
            category=metadata.category.value if isinstance(metadata.category, PluginCategory) else metadata.category,
            tags=metadata.tags,
            plugin_type=metadata.plugin_type,
            installed_path=path,
        )


class PluginSearcher:
    """Searches for plugins in installed index and local directories.

    Example:
        searcher = PluginSearcher()

        # Search by query
        results = searcher.search("git")

        # Search by category
        results = searcher.search_by_category(PluginCategory.GIT)

        # Search by type
        results = searcher.search_by_type("tool")

        # List all
        results = searcher.list_all()
    """

    def __init__(
        self,
        index: Optional[MarketplaceIndex] = None,
        plugin_dir: Optional[Path] = None,
        agent_dir: Optional[Path] = None,
    ):
        """Initialize the searcher.

        Args:
            index: Marketplace index (created if not provided)
            plugin_dir: Directory for tool plugins
            agent_dir: Directory for agent configs
        """
        self.index = index or MarketplaceIndex()
        self.plugin_dir = plugin_dir or (Path.home() / ".sindri" / "plugins")
        self.agent_dir = agent_dir or (Path.home() / ".sindri" / "agents")

    def search(
        self,
        query: str,
        plugin_type: Optional[str] = None,
        category: Optional[PluginCategory] = None,
        installed_only: bool = False,
    ) -> list[SearchResult]:
        """Search plugins by query string.

        Searches name, description, and tags.

        Args:
            query: Search query
            plugin_type: Filter by "tool" or "agent"
            category: Filter by category
            installed_only: Only search installed plugins

        Returns:
            List of SearchResults sorted by relevance
        """
        query = query.lower()
        results = []

        # Search installed plugins
        self.index.load()
        for plugin in self.index.get_all():
            # Apply filters
            if plugin_type and plugin.metadata.plugin_type != plugin_type:
                continue
            if category and plugin.metadata.category != category:
                continue

            # Calculate relevance score
            score = self._calculate_score(query, plugin.metadata)
            if score > 0:
                result = SearchResult.from_installed_plugin(plugin)
                result.score = score
                results.append(result)

        # Search local plugin directories (not yet indexed)
        if not installed_only:
            local_results = self._search_local(query, plugin_type, category)
            for result in local_results:
                # Don't duplicate installed plugins
                if not any(r.name == result.name for r in results):
                    results.append(result)

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)

        return results

    def search_by_category(
        self,
        category: PluginCategory,
        installed_only: bool = False,
    ) -> list[SearchResult]:
        """Search plugins by category.

        Args:
            category: Plugin category
            installed_only: Only search installed plugins

        Returns:
            List of SearchResults
        """
        results = []

        self.index.load()
        for plugin in self.index.get_by_category(category):
            results.append(SearchResult.from_installed_plugin(plugin))

        if not installed_only:
            local_results = self._search_local("", None, category)
            for result in local_results:
                if not any(r.name == result.name for r in results):
                    results.append(result)

        return results

    def search_by_type(
        self,
        plugin_type: str,
        installed_only: bool = False,
    ) -> list[SearchResult]:
        """Search plugins by type.

        Args:
            plugin_type: "tool" or "agent"
            installed_only: Only search installed plugins

        Returns:
            List of SearchResults
        """
        results = []

        self.index.load()
        for plugin in self.index.get_by_type(plugin_type):
            results.append(SearchResult.from_installed_plugin(plugin))

        if not installed_only:
            local_results = self._search_local("", plugin_type, None)
            for result in local_results:
                if not any(r.name == result.name for r in results):
                    results.append(result)

        return results

    def search_by_tags(
        self,
        tags: list[str],
        installed_only: bool = False,
    ) -> list[SearchResult]:
        """Search plugins by tags.

        Args:
            tags: Tags to search for (any match)
            installed_only: Only search installed plugins

        Returns:
            List of SearchResults
        """
        tags = [t.lower() for t in tags]
        results = []

        self.index.load()
        for plugin in self.index.get_all():
            plugin_tags = [t.lower() for t in plugin.metadata.tags]
            if any(tag in plugin_tags for tag in tags):
                results.append(SearchResult.from_installed_plugin(plugin))

        if not installed_only:
            local_results = self._search_local_by_tags(tags)
            for result in local_results:
                if not any(r.name == result.name for r in results):
                    results.append(result)

        return results

    def list_all(self, installed_only: bool = False) -> list[SearchResult]:
        """List all available plugins.

        Args:
            installed_only: Only list installed plugins

        Returns:
            List of SearchResults
        """
        results = []

        # Installed plugins
        self.index.load()
        for plugin in self.index.get_all():
            results.append(SearchResult.from_installed_plugin(plugin))

        # Local plugins not yet indexed
        if not installed_only:
            local_results = self._get_all_local()
            for result in local_results:
                if not any(r.name == result.name for r in results):
                    results.append(result)

        return results

    def get_info(self, name: str) -> Optional[SearchResult]:
        """Get detailed info about a specific plugin.

        Args:
            name: Plugin name

        Returns:
            SearchResult or None if not found
        """
        self.index.load()
        plugin = self.index.get(name)
        if plugin:
            return SearchResult.from_installed_plugin(plugin)

        # Check local directories
        for result in self._get_all_local():
            if result.name == name:
                return result

        return None

    def _calculate_score(self, query: str, metadata: PluginMetadata) -> int:
        """Calculate search relevance score.

        Args:
            query: Search query
            metadata: Plugin metadata

        Returns:
            Score from 0-100
        """
        if not query:
            return 50  # Default score for empty query

        score = 0

        # Exact name match
        if query == metadata.name.lower():
            return 100

        # Name contains query
        if query in metadata.name.lower():
            score += 60

        # Description contains query
        if query in metadata.description.lower():
            score += 30

        # Tag match
        for tag in metadata.tags:
            if query == tag.lower():
                score += 40
            elif query in tag.lower():
                score += 20

        # Category match
        category = metadata.category
        if isinstance(category, PluginCategory):
            category = category.value
        if query in category.lower():
            score += 25

        return min(score, 100)

    def _search_local(
        self,
        query: str,
        plugin_type: Optional[str],
        category: Optional[PluginCategory],
    ) -> list[SearchResult]:
        """Search local plugin directories."""
        results = []

        loader = PluginLoader(
            plugin_dir=self.plugin_dir,
            agent_dir=self.agent_dir,
        )
        discovered = loader.discover()

        for info in discovered:
            # Skip if not enabled or has error
            if not info.enabled or info.error:
                continue

            # Apply type filter
            if plugin_type:
                if plugin_type == "tool" and info.type != PluginType.TOOL:
                    continue
                if plugin_type == "agent" and info.type != PluginType.AGENT:
                    continue

            # Extract metadata
            metadata = PluginMetadata.from_plugin_file(info.path)
            if not metadata:
                metadata = PluginMetadata(
                    name=info.name,
                    version=info.version,
                    description=info.description,
                    author=info.author,
                    plugin_type="tool" if info.type == PluginType.TOOL else "agent",
                )

            # Apply category filter
            if category and metadata.category != category:
                continue

            # Calculate score
            score = self._calculate_score(query, metadata) if query else 50

            if score > 0 or not query:
                result = SearchResult.from_metadata(metadata, info.path)
                result.score = score
                results.append(result)

        return results

    def _search_local_by_tags(self, tags: list[str]) -> list[SearchResult]:
        """Search local plugins by tags."""
        results = []

        for plugin in self._get_all_local():
            plugin_tags = [t.lower() for t in plugin.tags]
            if any(tag in plugin_tags for tag in tags):
                results.append(plugin)

        return results

    def _get_all_local(self) -> list[SearchResult]:
        """Get all local plugins."""
        results = []

        loader = PluginLoader(
            plugin_dir=self.plugin_dir,
            agent_dir=self.agent_dir,
        )
        discovered = loader.discover()

        for info in discovered:
            if not info.enabled or info.error:
                continue

            metadata = PluginMetadata.from_plugin_file(info.path)
            if not metadata:
                metadata = PluginMetadata(
                    name=info.name,
                    version=info.version,
                    description=info.description,
                    author=info.author,
                    plugin_type="tool" if info.type == PluginType.TOOL else "agent",
                )

            result = SearchResult.from_metadata(metadata, info.path)
            result.score = 50  # Default score
            results.append(result)

        return results


def get_categories() -> list[tuple[str, str]]:
    """Get all available categories with descriptions.

    Returns:
        List of (value, description) tuples
    """
    return [
        (PluginCategory.FILESYSTEM.value, "File and directory operations"),
        (PluginCategory.GIT.value, "Git and version control"),
        (PluginCategory.HTTP.value, "HTTP requests and API tools"),
        (PluginCategory.DATABASE.value, "Database queries and management"),
        (PluginCategory.TESTING.value, "Test runners and assertions"),
        (PluginCategory.FORMATTING.value, "Code formatting and linting"),
        (PluginCategory.REFACTORING.value, "Code refactoring operations"),
        (PluginCategory.ANALYSIS.value, "Code analysis and metrics"),
        (PluginCategory.SECURITY.value, "Security scanning and auditing"),
        (PluginCategory.DEVOPS.value, "CI/CD and deployment tools"),
        (PluginCategory.DOCUMENTATION.value, "Documentation generation"),
        (PluginCategory.CODER.value, "Code generation agents"),
        (PluginCategory.REVIEWER.value, "Code review agents"),
        (PluginCategory.PLANNER.value, "Planning and architecture agents"),
        (PluginCategory.SPECIALIST.value, "Domain-specific agents"),
        (PluginCategory.UTILITY.value, "General utility tools"),
        (PluginCategory.OTHER.value, "Uncategorized plugins"),
    ]
