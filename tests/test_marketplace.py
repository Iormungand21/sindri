"""Tests for the plugin marketplace system."""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from sindri.marketplace.metadata import (
    PluginCategory,
    PluginMetadata,
    PluginSource,
    SourceType,
    parse_manifest,
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
    get_categories,
)


# ============================================
# PluginCategory Tests
# ============================================


class TestPluginCategory:
    """Tests for PluginCategory enum."""

    def test_all_categories_have_values(self):
        """All categories should have string values."""
        for cat in PluginCategory:
            assert isinstance(cat.value, str)
            assert len(cat.value) > 0

    def test_category_from_string(self):
        """Categories can be created from strings."""
        assert PluginCategory("filesystem") == PluginCategory.FILESYSTEM
        assert PluginCategory("git") == PluginCategory.GIT
        assert PluginCategory("coder") == PluginCategory.CODER

    def test_invalid_category_raises(self):
        """Invalid category string raises ValueError."""
        with pytest.raises(ValueError):
            PluginCategory("nonexistent")


# ============================================
# SourceType Tests
# ============================================


class TestSourceType:
    """Tests for SourceType enum."""

    def test_all_source_types(self):
        """All source types should exist."""
        assert SourceType.LOCAL.value == "local"
        assert SourceType.GIT.value == "git"
        assert SourceType.URL.value == "url"
        assert SourceType.MARKETPLACE.value == "marketplace"


# ============================================
# PluginSource Tests
# ============================================


class TestPluginSource:
    """Tests for PluginSource dataclass."""

    def test_create_local_source(self):
        """Create a local plugin source."""
        source = PluginSource(
            type=SourceType.LOCAL,
            location="/path/to/plugin.py",
        )
        assert source.type == SourceType.LOCAL
        assert source.location == "/path/to/plugin.py"
        assert source.ref is None

    def test_create_git_source(self):
        """Create a git plugin source."""
        source = PluginSource(
            type=SourceType.GIT,
            location="https://github.com/user/repo.git",
            ref="main",
            installed_at=datetime.now(),
        )
        assert source.type == SourceType.GIT
        assert source.ref == "main"
        assert source.installed_at is not None

    def test_to_dict(self):
        """PluginSource can be serialized to dict."""
        now = datetime.now()
        source = PluginSource(
            type=SourceType.GIT,
            location="https://github.com/user/repo.git",
            ref="v1.0.0",
            installed_at=now,
        )
        data = source.to_dict()
        assert data["type"] == "git"
        assert data["location"] == "https://github.com/user/repo.git"
        assert data["ref"] == "v1.0.0"
        assert data["installed_at"] == now.isoformat()

    def test_from_dict(self):
        """PluginSource can be deserialized from dict."""
        data = {
            "type": "local",
            "location": "/path/to/plugin.py",
            "ref": None,
            "installed_at": "2024-01-01T12:00:00",
            "updated_at": None,
        }
        source = PluginSource.from_dict(data)
        assert source.type == SourceType.LOCAL
        assert source.location == "/path/to/plugin.py"
        assert source.installed_at.year == 2024


# ============================================
# PluginMetadata Tests
# ============================================


class TestPluginMetadata:
    """Tests for PluginMetadata dataclass."""

    def test_create_basic_metadata(self):
        """Create basic plugin metadata."""
        meta = PluginMetadata(name="my_plugin")
        assert meta.name == "my_plugin"
        assert meta.version == "0.1.0"
        assert meta.plugin_type == "tool"
        assert meta.category == PluginCategory.OTHER

    def test_create_full_metadata(self):
        """Create plugin metadata with all fields."""
        meta = PluginMetadata(
            name="git_helper",
            version="1.2.3",
            description="Git integration tool",
            author="Test Author",
            category=PluginCategory.GIT,
            tags=["git", "vcs", "version-control"],
            homepage="https://example.com",
            repository="https://github.com/test/repo",
            license="MIT",
            dependencies=["base_tool"],
            sindri_version=">=0.1.0",
            plugin_type="tool",
        )
        assert meta.name == "git_helper"
        assert meta.version == "1.2.3"
        assert meta.category == PluginCategory.GIT
        assert "git" in meta.tags
        assert meta.license == "MIT"

    def test_to_dict(self):
        """PluginMetadata can be serialized to dict."""
        meta = PluginMetadata(
            name="test",
            category=PluginCategory.TESTING,
            tags=["unit", "test"],
        )
        data = meta.to_dict()
        assert data["name"] == "test"
        assert data["category"] == "testing"
        assert data["tags"] == ["unit", "test"]

    def test_from_dict(self):
        """PluginMetadata can be deserialized from dict."""
        data = {
            "name": "my_tool",
            "version": "2.0.0",
            "description": "A tool",
            "category": "security",
            "tags": ["security", "audit"],
            "plugin_type": "tool",
        }
        meta = PluginMetadata.from_dict(data)
        assert meta.name == "my_tool"
        assert meta.version == "2.0.0"
        assert meta.category == PluginCategory.SECURITY
        assert "audit" in meta.tags

    def test_from_dict_invalid_category(self):
        """Invalid category defaults to OTHER."""
        data = {
            "name": "test",
            "category": "invalid_category",
        }
        meta = PluginMetadata.from_dict(data)
        assert meta.category == PluginCategory.OTHER

    def test_from_python_file(self):
        """Extract metadata from Python plugin file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = Path(tmpdir) / "my_tool.py"
            plugin_path.write_text('''"""My amazing tool plugin.

Extended description goes here.
"""

__version__ = "1.0.0"
__author__ = "Test Author"

from sindri.tools.base import Tool, ToolResult

class MyTool(Tool):
    name = "my_tool"
    description = "Does something"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="done")
''')
            meta = PluginMetadata.from_plugin_file(plugin_path)
            assert meta is not None
            assert meta.name == "my_tool"
            assert meta.version == "1.0.0"
            assert meta.author == "Test Author"
            assert "My amazing tool plugin" in meta.description

    def test_from_toml_file(self):
        """Extract metadata from TOML agent config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent_path = Path(tmpdir) / "my_agent.toml"
            agent_path.write_text('''[agent]
name = "thor"
role = "Performance Optimizer"
description = "Optimizes code performance"
model = "qwen2.5-coder:14b"

[metadata]
version = "2.0.0"
author = "Test"
category = "specialist"
tags = ["performance", "optimization"]
''')
            meta = PluginMetadata.from_plugin_file(agent_path)
            assert meta is not None
            assert meta.name == "thor"
            assert meta.version == "2.0.0"
            assert meta.plugin_type == "agent"
            assert "performance" in meta.tags


class TestParseManifest:
    """Tests for parse_manifest function."""

    def test_parse_valid_manifest(self):
        """Parse a valid manifest file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "sindri-plugin.json"
            manifest_data = {
                "name": "awesome_plugin",
                "version": "3.0.0",
                "description": "An awesome plugin",
                "author": "Developer",
                "category": "utility",
                "tags": ["awesome", "plugin"],
                "plugin_type": "tool",
            }
            manifest_path.write_text(json.dumps(manifest_data))

            meta = parse_manifest(manifest_path)
            assert meta is not None
            assert meta.name == "awesome_plugin"
            assert meta.version == "3.0.0"

    def test_parse_invalid_json(self):
        """Return None for invalid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "sindri-plugin.json"
            manifest_path.write_text("not valid json")

            meta = parse_manifest(manifest_path)
            assert meta is None

    def test_parse_nonexistent_file(self):
        """Return None for nonexistent file."""
        meta = parse_manifest(Path("/nonexistent/manifest.json"))
        assert meta is None


# ============================================
# InstalledPlugin Tests
# ============================================


class TestInstalledPlugin:
    """Tests for InstalledPlugin dataclass."""

    def test_create_installed_plugin(self):
        """Create an installed plugin record."""
        meta = PluginMetadata(name="test_plugin", version="1.0.0")
        source = PluginSource(
            type=SourceType.LOCAL,
            location="/path/to/plugin.py",
        )
        plugin = InstalledPlugin(
            metadata=meta,
            source=source,
            installed_path=Path("/home/user/.sindri/plugins/test_plugin.py"),
        )
        assert plugin.metadata.name == "test_plugin"
        assert plugin.enabled is True
        assert plugin.pinned is False

    def test_to_dict(self):
        """InstalledPlugin can be serialized to dict."""
        meta = PluginMetadata(name="test", version="1.0.0")
        source = PluginSource(type=SourceType.GIT, location="https://github.com/test")
        plugin = InstalledPlugin(
            metadata=meta,
            source=source,
            installed_path=Path("/path/to/plugin.py"),
            enabled=True,
            pinned=True,
        )
        data = plugin.to_dict()
        assert data["metadata"]["name"] == "test"
        assert data["source"]["type"] == "git"
        assert data["enabled"] is True
        assert data["pinned"] is True

    def test_from_dict(self):
        """InstalledPlugin can be deserialized from dict."""
        data = {
            "metadata": {
                "name": "my_plugin",
                "version": "1.0.0",
            },
            "source": {
                "type": "local",
                "location": "/path/to/source",
            },
            "installed_path": "/path/to/installed",
            "enabled": False,
            "pinned": True,
        }
        plugin = InstalledPlugin.from_dict(data)
        assert plugin.metadata.name == "my_plugin"
        assert plugin.enabled is False
        assert plugin.pinned is True


# ============================================
# MarketplaceIndex Tests
# ============================================


class TestMarketplaceIndex:
    """Tests for MarketplaceIndex."""

    @pytest.fixture
    def temp_index_dir(self):
        """Create a temporary directory for index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sample_plugin(self) -> InstalledPlugin:
        """Create a sample installed plugin."""
        meta = PluginMetadata(
            name="sample_tool",
            version="1.0.0",
            description="A sample tool",
            category=PluginCategory.UTILITY,
            plugin_type="tool",
        )
        source = PluginSource(
            type=SourceType.LOCAL,
            location="/path/to/source.py",
            installed_at=datetime.now(),
        )
        return InstalledPlugin(
            metadata=meta,
            source=source,
            installed_path=Path("/path/to/installed.py"),
        )

    def test_empty_index(self, temp_index_dir):
        """New index starts empty."""
        index = MarketplaceIndex(index_dir=temp_index_dir)
        index.load()
        assert len(index.get_all()) == 0

    def test_add_plugin(self, temp_index_dir, sample_plugin):
        """Can add a plugin to the index."""
        index = MarketplaceIndex(index_dir=temp_index_dir)
        index.load()
        index.add(sample_plugin)

        assert index.exists("sample_tool")
        assert index.get("sample_tool").metadata.version == "1.0.0"

    def test_remove_plugin(self, temp_index_dir, sample_plugin):
        """Can remove a plugin from the index."""
        index = MarketplaceIndex(index_dir=temp_index_dir)
        index.load()
        index.add(sample_plugin)

        removed = index.remove("sample_tool")
        assert removed is not None
        assert not index.exists("sample_tool")

    def test_save_and_load(self, temp_index_dir, sample_plugin):
        """Index can be saved and loaded."""
        # Save
        index1 = MarketplaceIndex(index_dir=temp_index_dir)
        index1.load()
        index1.add(sample_plugin)
        index1.save()

        # Load in new instance
        index2 = MarketplaceIndex(index_dir=temp_index_dir)
        index2.load()

        assert index2.exists("sample_tool")
        assert index2.get("sample_tool").metadata.version == "1.0.0"

    def test_get_by_category(self, temp_index_dir):
        """Can filter plugins by category."""
        index = MarketplaceIndex(index_dir=temp_index_dir)
        index.load()

        # Add plugins with different categories
        for name, category in [("git_tool", PluginCategory.GIT), ("test_tool", PluginCategory.TESTING), ("git_tool2", PluginCategory.GIT)]:
            meta = PluginMetadata(name=name, category=category)
            source = PluginSource(type=SourceType.LOCAL, location="/path")
            plugin = InstalledPlugin(metadata=meta, source=source, installed_path=Path("/path"))
            index.add(plugin)

        git_plugins = index.get_by_category(PluginCategory.GIT)
        assert len(git_plugins) == 2

    def test_get_by_type(self, temp_index_dir):
        """Can filter plugins by type."""
        index = MarketplaceIndex(index_dir=temp_index_dir)
        index.load()

        for name, ptype in [("tool1", "tool"), ("tool2", "tool"), ("agent1", "agent")]:
            meta = PluginMetadata(name=name, plugin_type=ptype)
            source = PluginSource(type=SourceType.LOCAL, location="/path")
            plugin = InstalledPlugin(metadata=meta, source=source, installed_path=Path("/path"))
            index.add(plugin)

        tools = index.get_by_type("tool")
        assert len(tools) == 2

        agents = index.get_by_type("agent")
        assert len(agents) == 1

    def test_set_enabled(self, temp_index_dir, sample_plugin):
        """Can enable/disable plugins."""
        index = MarketplaceIndex(index_dir=temp_index_dir)
        index.load()
        index.add(sample_plugin)

        index.set_enabled("sample_tool", False)
        assert index.get("sample_tool").enabled is False

        index.set_enabled("sample_tool", True)
        assert index.get("sample_tool").enabled is True

    def test_set_pinned(self, temp_index_dir, sample_plugin):
        """Can pin/unpin plugins."""
        index = MarketplaceIndex(index_dir=temp_index_dir)
        index.load()
        index.add(sample_plugin)

        index.set_pinned("sample_tool", True)
        assert index.get("sample_tool").pinned is True

        index.set_pinned("sample_tool", False)
        assert index.get("sample_tool").pinned is False

    def test_get_stats(self, temp_index_dir):
        """Get index statistics."""
        index = MarketplaceIndex(index_dir=temp_index_dir)
        index.load()

        # Add some plugins
        for i, (ptype, cat, src_type) in enumerate([
            ("tool", PluginCategory.GIT, SourceType.GIT),
            ("tool", PluginCategory.TESTING, SourceType.LOCAL),
            ("agent", PluginCategory.CODER, SourceType.URL),
        ]):
            meta = PluginMetadata(name=f"plugin{i}", category=cat, plugin_type=ptype)
            source = PluginSource(type=src_type, location="/path")
            plugin = InstalledPlugin(metadata=meta, source=source, installed_path=Path("/path"))
            index.add(plugin)

        stats = index.get_stats()
        assert stats["total"] == 3
        assert stats["by_type"]["tool"] == 2
        assert stats["by_type"]["agent"] == 1


# ============================================
# PluginInstaller Tests
# ============================================


class TestPluginInstaller:
    """Tests for PluginInstaller."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            agent_dir = Path(tmpdir) / "agents"
            index_dir = Path(tmpdir) / "marketplace"
            plugin_dir.mkdir()
            agent_dir.mkdir()
            index_dir.mkdir()
            yield plugin_dir, agent_dir, index_dir

    @pytest.fixture
    def sample_plugin_file(self, temp_dirs):
        """Create a sample plugin file."""
        plugin_dir, _, _ = temp_dirs
        source_dir = Path(temp_dirs[0]).parent / "source"
        source_dir.mkdir()

        plugin_path = source_dir / "sample_tool.py"
        plugin_path.write_text('''"""Sample tool plugin."""

__version__ = "1.0.0"
__author__ = "Test"

from sindri.tools.base import Tool, ToolResult

class SampleTool(Tool):
    name = "sample_tool"
    description = "A sample tool"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="done")
''')
        return plugin_path

    def test_detect_source_type_local(self, temp_dirs, sample_plugin_file):
        """Detect local file path source."""
        plugin_dir, agent_dir, index_dir = temp_dirs
        installer = PluginInstaller(plugin_dir=plugin_dir, agent_dir=agent_dir)

        source_type, location = installer._detect_source_type(str(sample_plugin_file))
        assert source_type == SourceType.LOCAL

    def test_detect_source_type_git_url(self, temp_dirs):
        """Detect git URL source."""
        plugin_dir, agent_dir, _ = temp_dirs
        installer = PluginInstaller(plugin_dir=plugin_dir, agent_dir=agent_dir)

        source_type, _ = installer._detect_source_type("https://github.com/user/repo.git")
        assert source_type == SourceType.GIT

    def test_detect_source_type_github_shorthand(self, temp_dirs):
        """Detect GitHub shorthand source."""
        plugin_dir, agent_dir, _ = temp_dirs
        installer = PluginInstaller(plugin_dir=plugin_dir, agent_dir=agent_dir)

        source_type, location = installer._detect_source_type("user/repo")
        assert source_type == SourceType.GIT
        assert "github.com" in location

    def test_detect_source_type_url(self, temp_dirs):
        """Detect direct URL source."""
        plugin_dir, agent_dir, _ = temp_dirs
        installer = PluginInstaller(plugin_dir=plugin_dir, agent_dir=agent_dir)

        source_type, _ = installer._detect_source_type("https://example.com/plugin.py")
        assert source_type == SourceType.URL

    @pytest.mark.asyncio
    async def test_install_from_path(self, temp_dirs, sample_plugin_file):
        """Install a plugin from local path."""
        plugin_dir, agent_dir, index_dir = temp_dirs
        index = MarketplaceIndex(index_dir=index_dir)

        installer = PluginInstaller(
            plugin_dir=plugin_dir,
            agent_dir=agent_dir,
            index=index,
            validate=False,  # Skip validation for test
        )

        result = await installer.install_from_path(sample_plugin_file)

        assert result.success
        assert result.plugin is not None
        assert result.plugin.metadata.name == "sample_tool"
        assert (plugin_dir / "sample_tool.py").exists()

    @pytest.mark.asyncio
    async def test_install_from_path_not_found(self, temp_dirs):
        """Install from nonexistent path fails."""
        plugin_dir, agent_dir, index_dir = temp_dirs
        installer = PluginInstaller(plugin_dir=plugin_dir, agent_dir=agent_dir)

        result = await installer.install_from_path(Path("/nonexistent/plugin.py"))

        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_install_duplicate_fails(self, temp_dirs, sample_plugin_file):
        """Installing duplicate plugin fails."""
        plugin_dir, agent_dir, index_dir = temp_dirs
        index = MarketplaceIndex(index_dir=index_dir)

        installer = PluginInstaller(
            plugin_dir=plugin_dir,
            agent_dir=agent_dir,
            index=index,
            validate=False,
        )

        # Install first time
        result1 = await installer.install_from_path(sample_plugin_file)
        assert result1.success

        # Try to install again
        result2 = await installer.install_from_path(sample_plugin_file)
        assert not result2.success
        assert "already installed" in result2.error.lower()

    @pytest.mark.asyncio
    async def test_uninstall(self, temp_dirs, sample_plugin_file):
        """Uninstall an installed plugin."""
        plugin_dir, agent_dir, index_dir = temp_dirs
        index = MarketplaceIndex(index_dir=index_dir)

        installer = PluginInstaller(
            plugin_dir=plugin_dir,
            agent_dir=agent_dir,
            index=index,
            validate=False,
        )

        # Install
        await installer.install_from_path(sample_plugin_file)
        assert index.exists("sample_tool")

        # Uninstall
        result = await installer.uninstall("sample_tool")

        assert result.success
        assert not index.exists("sample_tool")
        assert not (plugin_dir / "sample_tool.py").exists()

    @pytest.mark.asyncio
    async def test_uninstall_not_installed(self, temp_dirs):
        """Uninstall nonexistent plugin fails."""
        plugin_dir, agent_dir, index_dir = temp_dirs
        installer = PluginInstaller(plugin_dir=plugin_dir, agent_dir=agent_dir)

        result = await installer.uninstall("nonexistent")

        assert not result.success
        assert "not installed" in result.error.lower()


# ============================================
# SearchResult Tests
# ============================================


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_from_installed_plugin(self):
        """Create SearchResult from InstalledPlugin."""
        meta = PluginMetadata(
            name="test_tool",
            version="1.0.0",
            description="Test tool",
            category=PluginCategory.TESTING,
            tags=["test", "unit"],
        )
        source = PluginSource(type=SourceType.GIT, location="https://github.com/test")
        plugin = InstalledPlugin(
            metadata=meta,
            source=source,
            installed_path=Path("/path/to/plugin"),
        )

        result = SearchResult.from_installed_plugin(plugin)

        assert result.name == "test_tool"
        assert result.installed is True
        assert result.source == "https://github.com/test"
        assert "test" in result.tags

    def test_from_metadata(self):
        """Create SearchResult from PluginMetadata."""
        meta = PluginMetadata(
            name="my_plugin",
            version="2.0.0",
            description="My plugin",
        )

        result = SearchResult.from_metadata(meta, Path("/path"))

        assert result.name == "my_plugin"
        assert result.version == "2.0.0"
        assert result.installed is False


# ============================================
# PluginSearcher Tests
# ============================================


class TestPluginSearcher:
    """Tests for PluginSearcher."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            agent_dir = Path(tmpdir) / "agents"
            index_dir = Path(tmpdir) / "marketplace"
            plugin_dir.mkdir()
            agent_dir.mkdir()
            index_dir.mkdir()
            yield plugin_dir, agent_dir, index_dir

    @pytest.fixture
    def populated_index(self, temp_dirs):
        """Create index with sample plugins."""
        _, _, index_dir = temp_dirs
        index = MarketplaceIndex(index_dir=index_dir)
        index.load()

        plugins = [
            ("git_helper", "1.0.0", "Git operations helper", PluginCategory.GIT, ["git", "vcs"]),
            ("test_runner", "2.0.0", "Test runner tool", PluginCategory.TESTING, ["test", "runner"]),
            ("security_audit", "1.5.0", "Security auditing", PluginCategory.SECURITY, ["security", "audit"]),
        ]

        for name, version, desc, cat, tags in plugins:
            meta = PluginMetadata(
                name=name,
                version=version,
                description=desc,
                category=cat,
                tags=tags,
            )
            source = PluginSource(type=SourceType.LOCAL, location="/path")
            plugin = InstalledPlugin(
                metadata=meta,
                source=source,
                installed_path=Path("/path"),
            )
            index.add(plugin)

        index.save()
        return index

    def test_search_by_name(self, temp_dirs, populated_index):
        """Search plugins by name."""
        plugin_dir, agent_dir, _ = temp_dirs
        searcher = PluginSearcher(
            index=populated_index,
            plugin_dir=plugin_dir,
            agent_dir=agent_dir,
        )

        results = searcher.search("git", installed_only=True)

        assert len(results) >= 1
        assert any(r.name == "git_helper" for r in results)

    def test_search_by_description(self, temp_dirs, populated_index):
        """Search finds plugins by description."""
        plugin_dir, agent_dir, _ = temp_dirs
        searcher = PluginSearcher(
            index=populated_index,
            plugin_dir=plugin_dir,
            agent_dir=agent_dir,
        )

        results = searcher.search("auditing", installed_only=True)

        assert len(results) >= 1
        assert any(r.name == "security_audit" for r in results)

    def test_search_by_category(self, temp_dirs, populated_index):
        """Search plugins by category."""
        plugin_dir, agent_dir, _ = temp_dirs
        searcher = PluginSearcher(
            index=populated_index,
            plugin_dir=plugin_dir,
            agent_dir=agent_dir,
        )

        results = searcher.search_by_category(PluginCategory.TESTING, installed_only=True)

        assert len(results) >= 1
        assert any(r.name == "test_runner" for r in results)

    def test_search_by_tags(self, temp_dirs, populated_index):
        """Search plugins by tags."""
        plugin_dir, agent_dir, _ = temp_dirs
        searcher = PluginSearcher(
            index=populated_index,
            plugin_dir=plugin_dir,
            agent_dir=agent_dir,
        )

        results = searcher.search_by_tags(["security"], installed_only=True)

        assert len(results) >= 1
        assert any(r.name == "security_audit" for r in results)

    def test_list_all(self, temp_dirs, populated_index):
        """List all plugins."""
        plugin_dir, agent_dir, _ = temp_dirs
        searcher = PluginSearcher(
            index=populated_index,
            plugin_dir=plugin_dir,
            agent_dir=agent_dir,
        )

        results = searcher.list_all(installed_only=True)

        assert len(results) == 3

    def test_get_info(self, temp_dirs, populated_index):
        """Get detailed plugin info."""
        plugin_dir, agent_dir, _ = temp_dirs
        searcher = PluginSearcher(
            index=populated_index,
            plugin_dir=plugin_dir,
            agent_dir=agent_dir,
        )

        result = searcher.get_info("git_helper")

        assert result is not None
        assert result.name == "git_helper"
        assert result.version == "1.0.0"
        assert "vcs" in result.tags

    def test_get_info_not_found(self, temp_dirs, populated_index):
        """Get info for nonexistent plugin returns None."""
        plugin_dir, agent_dir, _ = temp_dirs
        searcher = PluginSearcher(
            index=populated_index,
            plugin_dir=plugin_dir,
            agent_dir=agent_dir,
        )

        result = searcher.get_info("nonexistent")

        assert result is None


class TestGetCategories:
    """Tests for get_categories function."""

    def test_returns_all_categories(self):
        """Returns all available categories."""
        categories = get_categories()

        assert len(categories) > 0
        assert all(isinstance(c, tuple) and len(c) == 2 for c in categories)

    def test_categories_have_descriptions(self):
        """All categories have descriptions."""
        categories = get_categories()

        for value, description in categories:
            assert len(value) > 0
            assert len(description) > 0


# ============================================
# Integration Tests
# ============================================


class TestMarketplaceIntegration:
    """Integration tests for the marketplace system."""

    @pytest.fixture
    def temp_environment(self):
        """Create a full test environment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            plugin_dir = base_dir / "plugins"
            agent_dir = base_dir / "agents"
            index_dir = base_dir / "marketplace"
            source_dir = base_dir / "source"

            plugin_dir.mkdir()
            agent_dir.mkdir()
            index_dir.mkdir()
            source_dir.mkdir()

            # Create a sample plugin in source
            plugin_file = source_dir / "my_tool.py"
            plugin_file.write_text('''"""My tool plugin.

A useful tool for testing.
"""

__version__ = "1.0.0"
__author__ = "Test Author"

__metadata__ = {
    "category": "utility",
    "tags": ["test", "example"],
}

from sindri.tools.base import Tool, ToolResult

class MyTool(Tool):
    name = "my_tool"
    description = "A useful tool"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="Hello")
''')

            yield {
                "base_dir": base_dir,
                "plugin_dir": plugin_dir,
                "agent_dir": agent_dir,
                "index_dir": index_dir,
                "source_dir": source_dir,
                "plugin_file": plugin_file,
            }

    @pytest.mark.asyncio
    async def test_full_install_search_uninstall_flow(self, temp_environment):
        """Test complete install -> search -> uninstall workflow."""
        env = temp_environment

        # Create index and installer
        index = MarketplaceIndex(index_dir=env["index_dir"])
        installer = PluginInstaller(
            plugin_dir=env["plugin_dir"],
            agent_dir=env["agent_dir"],
            index=index,
            validate=False,
        )
        searcher = PluginSearcher(
            index=index,
            plugin_dir=env["plugin_dir"],
            agent_dir=env["agent_dir"],
        )

        # Install plugin
        install_result = await installer.install_from_path(env["plugin_file"])
        assert install_result.success
        assert install_result.plugin.metadata.name == "my_tool"

        # Search for it
        search_results = searcher.search("my_tool", installed_only=True)
        assert len(search_results) >= 1
        assert any(r.name == "my_tool" for r in search_results)

        # Get info
        info = searcher.get_info("my_tool")
        assert info is not None
        assert info.installed is True

        # Pin it
        index.set_pinned("my_tool", True)
        assert index.get("my_tool").pinned is True

        # Uninstall
        uninstall_result = await installer.uninstall("my_tool")
        assert uninstall_result.success

        # Verify it's gone
        assert not index.exists("my_tool")
        assert searcher.get_info("my_tool") is None
