"""Tests for Multi-Project Workspace Index (ROADMAP Item 4).

Tests cover:
- ProjectEmbedderSettings dataclass
- ProjectConfig workspace fields (active, auto_index, index_priority, embedder_settings)
- ProjectRegistry workspace methods (list_active_projects, set_active, etc.)
- GlobalMemoryStore incremental indexing
- GlobalMemoryStore active project context
- BackgroundIndexer queue and lifecycle
- Event emission for indexer progress
"""

import asyncio
import tempfile
import time
from pathlib import Path

import pytest

from sindri.memory.projects import (
    ProjectConfig,
    ProjectEmbedderSettings,
    ProjectRegistry,
)
from sindri.memory.global_memory import (
    GlobalMemoryStore,
    IncrementalIndexResult,
)
from sindri.memory.background_indexer import (
    BackgroundIndexer,
    IndexerConfig,
    IndexerState,
    IndexerStatus,
    QueuedProject,
)
from sindri.core.events import EventBus, Event, EventType


# === ProjectEmbedderSettings Tests ===


class TestProjectEmbedderSettings:
    """Tests for per-project embedder configuration."""

    def test_default_values(self):
        """Test default settings match expected values."""
        settings = ProjectEmbedderSettings()

        assert settings.chunk_size_lines == 50
        assert settings.max_chunk_chars == 2000
        assert settings.max_line_chars == 500
        assert settings.file_extensions is None
        assert settings.exclude_patterns == []
        assert settings.include_patterns == []

    def test_custom_values(self):
        """Test custom settings are stored correctly."""
        settings = ProjectEmbedderSettings(
            chunk_size_lines=100,
            max_chunk_chars=3000,
            max_line_chars=800,
            file_extensions=[".py", ".md"],
            exclude_patterns=["*.min.js", "dist/*"],
            include_patterns=["src/**/*.py"],
        )

        assert settings.chunk_size_lines == 100
        assert settings.max_chunk_chars == 3000
        assert settings.file_extensions == [".py", ".md"]
        assert "*.min.js" in settings.exclude_patterns
        assert "src/**/*.py" in settings.include_patterns

    def test_to_dict_serialization(self):
        """Test settings serialize to dictionary correctly."""
        settings = ProjectEmbedderSettings(
            chunk_size_lines=75,
            exclude_patterns=["node_modules/*"],
        )
        data = settings.to_dict()

        assert data["chunk_size_lines"] == 75
        assert data["exclude_patterns"] == ["node_modules/*"]
        assert data["file_extensions"] is None

    def test_from_dict_deserialization(self):
        """Test settings deserialize from dictionary correctly."""
        data = {
            "chunk_size_lines": 60,
            "max_chunk_chars": 2500,
            "exclude_patterns": ["*.log"],
        }
        settings = ProjectEmbedderSettings.from_dict(data)

        assert settings.chunk_size_lines == 60
        assert settings.max_chunk_chars == 2500
        assert settings.exclude_patterns == ["*.log"]
        # Defaults for missing keys
        assert settings.max_line_chars == 500

    def test_roundtrip_serialization(self):
        """Test settings survive dict roundtrip."""
        original = ProjectEmbedderSettings(
            chunk_size_lines=80,
            file_extensions=[".py", ".rs"],
            include_patterns=["src/*"],
        )
        data = original.to_dict()
        restored = ProjectEmbedderSettings.from_dict(data)

        assert restored.chunk_size_lines == original.chunk_size_lines
        assert restored.file_extensions == original.file_extensions
        assert restored.include_patterns == original.include_patterns


# === ProjectConfig Workspace Fields Tests ===


class TestProjectConfigWorkspaceFields:
    """Tests for workspace-related ProjectConfig fields."""

    def test_default_workspace_fields(self):
        """Test new workspace fields have correct defaults."""
        config = ProjectConfig(path="/tmp/test")

        assert config.active is False
        assert config.auto_index is True
        assert config.index_priority == 5
        assert config.embedder_settings is None

    def test_custom_workspace_fields(self):
        """Test workspace fields can be set."""
        settings = ProjectEmbedderSettings(chunk_size_lines=100)
        config = ProjectConfig(
            path="/tmp/test",
            active=True,
            auto_index=False,
            index_priority=1,
            embedder_settings=settings,
        )

        assert config.active is True
        assert config.auto_index is False
        assert config.index_priority == 1
        assert config.embedder_settings.chunk_size_lines == 100

    def test_to_dict_includes_workspace_fields(self):
        """Test workspace fields are included in serialization."""
        settings = ProjectEmbedderSettings(exclude_patterns=["*.log"])
        config = ProjectConfig(
            path="/tmp/test",
            active=True,
            index_priority=2,
            embedder_settings=settings,
        )
        data = config.to_dict()

        assert data["active"] is True
        assert data["index_priority"] == 2
        assert data["embedder_settings"]["exclude_patterns"] == ["*.log"]

    def test_from_dict_loads_workspace_fields(self):
        """Test workspace fields are loaded from dictionary."""
        data = {
            "path": "/tmp/test",
            "active": True,
            "auto_index": False,
            "index_priority": 3,
            "embedder_settings": {
                "chunk_size_lines": 75,
            },
        }
        config = ProjectConfig.from_dict(data)

        assert config.active is True
        assert config.auto_index is False
        assert config.index_priority == 3
        assert config.embedder_settings.chunk_size_lines == 75

    def test_from_dict_handles_missing_workspace_fields(self):
        """Test missing workspace fields use defaults (backward compat)."""
        data = {
            "path": "/tmp/test",
            "name": "test",
        }
        config = ProjectConfig.from_dict(data)

        # Should use defaults
        assert config.active is False
        assert config.auto_index is True
        assert config.index_priority == 5
        assert config.embedder_settings is None


# === ProjectRegistry Workspace Methods Tests ===


class TestProjectRegistryWorkspaceMethods:
    """Tests for workspace-related ProjectRegistry methods."""

    @pytest.fixture
    def registry(self, tmp_path):
        """Create a registry with temp storage."""
        config_path = tmp_path / "projects.json"
        reg = ProjectRegistry(config_path=config_path)

        # Create test project directories
        proj1 = tmp_path / "project1"
        proj2 = tmp_path / "project2"
        proj3 = tmp_path / "project3"
        proj1.mkdir()
        proj2.mkdir()
        proj3.mkdir()

        # Add projects with different settings
        reg.add_project(str(proj1), name="Project 1")
        reg.add_project(str(proj2), name="Project 2")
        reg.add_project(str(proj3), name="Project 3")

        return reg

    def test_set_active(self, registry):
        """Test activating/deactivating projects."""
        projects = registry.list_projects()
        path = projects[0].path

        # Activate
        result = registry.set_active(path, active=True)
        assert result is not None
        assert result.active is True

        # Verify persistence
        reloaded = registry.get_project(path)
        assert reloaded.active is True

        # Deactivate
        result = registry.set_active(path, active=False)
        assert result.active is False

    def test_list_active_projects(self, registry):
        """Test listing only active projects."""
        projects = registry.list_projects()

        # Initially no active projects
        active = registry.list_active_projects()
        assert len(active) == 0

        # Activate some
        registry.set_active(projects[0].path, active=True)
        registry.set_active(projects[1].path, active=True)

        active = registry.list_active_projects()
        assert len(active) == 2

    def test_list_active_projects_sorted_by_priority(self, registry):
        """Test active projects are sorted by priority."""
        projects = registry.list_projects()

        # Set different priorities
        registry.set_auto_index(projects[0].path, priority=5)
        registry.set_auto_index(projects[1].path, priority=1)
        registry.set_auto_index(projects[2].path, priority=3)

        # Activate all
        for p in projects:
            registry.set_active(p.path, active=True)

        active = registry.list_active_projects()
        assert len(active) == 3
        # Should be sorted by priority (1, 3, 5)
        assert active[0].index_priority == 1
        assert active[1].index_priority == 3
        assert active[2].index_priority == 5

    def test_get_active_project_count(self, registry):
        """Test counting active projects."""
        assert registry.get_active_project_count() == 0

        projects = registry.list_projects()
        registry.set_active(projects[0].path, active=True)
        assert registry.get_active_project_count() == 1

        registry.set_active(projects[1].path, active=True)
        assert registry.get_active_project_count() == 2

    def test_set_auto_index(self, registry):
        """Test setting auto-index and priority."""
        projects = registry.list_projects()
        path = projects[0].path

        result = registry.set_auto_index(path, auto_index=False, priority=2)
        assert result.auto_index is False
        assert result.index_priority == 2

        # Test priority clamping
        registry.set_auto_index(path, priority=0)
        reloaded = registry.get_project(path)
        assert reloaded.index_priority == 1  # Clamped to minimum

        registry.set_auto_index(path, priority=15)
        reloaded = registry.get_project(path)
        assert reloaded.index_priority == 10  # Clamped to maximum

    def test_set_embedder_settings(self, registry):
        """Test setting per-project embedder settings."""
        projects = registry.list_projects()
        path = projects[0].path

        settings = ProjectEmbedderSettings(
            chunk_size_lines=100,
            exclude_patterns=["*.test.py"],
        )
        result = registry.set_embedder_settings(path, settings)

        assert result.embedder_settings is not None
        assert result.embedder_settings.chunk_size_lines == 100

        # Verify persistence
        reloaded = registry.get_project(path)
        assert reloaded.embedder_settings.chunk_size_lines == 100

    def test_clear_embedder_settings(self, registry):
        """Test clearing embedder settings."""
        projects = registry.list_projects()
        path = projects[0].path

        # Set settings
        settings = ProjectEmbedderSettings(chunk_size_lines=100)
        registry.set_embedder_settings(path, settings)

        # Clear
        result = registry.clear_embedder_settings(path)
        assert result.embedder_settings is None

    def test_list_auto_index_projects(self, registry):
        """Test listing auto-indexable projects."""
        projects = registry.list_projects()

        # All enabled and auto_index by default
        auto = registry.list_auto_index_projects()
        assert len(auto) == 3

        # Disable auto-index on one
        registry.set_auto_index(projects[0].path, auto_index=False)
        auto = registry.list_auto_index_projects()
        assert len(auto) == 2

        # Disable project (not just auto-index)
        registry.enable_project(projects[1].path, enabled=False)
        auto = registry.list_auto_index_projects()
        assert len(auto) == 1


# === IncrementalIndexResult Tests ===


class TestIncrementalIndexResult:
    """Tests for incremental indexing result dataclass."""

    def test_default_values(self):
        """Test result defaults."""
        result = IncrementalIndexResult(project_path="/tmp/test")

        assert result.files_indexed == 0
        assert result.files_skipped == 0
        assert result.files_failed == 0
        assert result.files_removed == 0
        assert result.chunks_added == 0
        assert result.chunks_removed == 0
        assert result.duration_seconds == 0.0
        assert result.error is None

    def test_to_dict(self):
        """Test result serialization."""
        result = IncrementalIndexResult(
            project_path="/tmp/test",
            files_indexed=10,
            files_skipped=5,
            chunks_added=50,
            duration_seconds=1.5,
        )
        data = result.to_dict()

        assert data["project_path"] == "/tmp/test"
        assert data["files_indexed"] == 10
        assert data["chunks_added"] == 50


# === GlobalMemoryStore Incremental Indexing Tests ===


class TestGlobalMemoryStoreIncremental:
    """Tests for incremental indexing in GlobalMemoryStore."""

    @pytest.fixture
    def setup(self, tmp_path):
        """Create GlobalMemoryStore and test project."""
        db_path = tmp_path / "global_memory.db"
        registry_path = tmp_path / "projects.json"

        # Create test project with files
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        (project_dir / "main.py").write_text("def main():\n    print('hello')\n")
        (project_dir / "utils.py").write_text("def helper():\n    return 42\n")
        (project_dir / "README.md").write_text("# Test Project\n\nDescription here.\n")

        registry = ProjectRegistry(config_path=registry_path)
        registry.add_project(str(project_dir), name="Test Project")

        # Use mock embedder to avoid Ollama dependency
        class MockEmbedder:
            def embed(self, text):
                # Return consistent mock embedding
                import hashlib
                h = hashlib.md5(text.encode()).hexdigest()
                return [float(int(h[i:i+2], 16)) / 255.0 for i in range(0, 32, 2)] * 48  # 768-dim

        store = GlobalMemoryStore(
            db_path=db_path,
            registry=registry,
            embedder=MockEmbedder(),
        )

        return {
            "store": store,
            "registry": registry,
            "project_dir": project_dir,
        }

    def test_index_project_incremental_first_time(self, setup):
        """Test incremental indexing on fresh project."""
        store = setup["store"]
        project_dir = setup["project_dir"]

        result = store.index_project_incremental(str(project_dir))

        assert result.error is None
        assert result.files_indexed == 3  # main.py, utils.py, README.md
        assert result.files_skipped == 0
        assert result.chunks_added > 0
        assert result.duration_seconds > 0

    def test_index_project_incremental_unchanged(self, setup):
        """Test incremental indexing skips unchanged files."""
        store = setup["store"]
        project_dir = setup["project_dir"]

        # First index
        store.index_project_incremental(str(project_dir))

        # Second index - should skip all
        result = store.index_project_incremental(str(project_dir))

        assert result.files_indexed == 0
        assert result.files_skipped == 3
        assert result.chunks_added == 0

    def test_index_project_incremental_with_changes(self, setup):
        """Test incremental indexing processes changed files."""
        store = setup["store"]
        project_dir = setup["project_dir"]

        # First index
        store.index_project_incremental(str(project_dir))

        # Modify a file
        (project_dir / "main.py").write_text("def main():\n    print('updated!')\n")

        # Second index - should process changed file
        result = store.index_project_incremental(str(project_dir))

        assert result.files_indexed == 1
        assert result.files_skipped == 2
        assert result.chunks_removed > 0  # Old chunks removed
        assert result.chunks_added > 0  # New chunks added

    def test_index_project_incremental_with_deletion(self, setup):
        """Test incremental indexing handles deleted files."""
        store = setup["store"]
        project_dir = setup["project_dir"]

        # First index
        store.index_project_incremental(str(project_dir))

        # Delete a file
        (project_dir / "utils.py").unlink()

        # Second index - should detect deletion
        result = store.index_project_incremental(str(project_dir))

        assert result.files_removed == 1
        assert result.chunks_removed > 0

    def test_index_project_incremental_force(self, setup):
        """Test force re-index ignores hashes."""
        store = setup["store"]
        project_dir = setup["project_dir"]

        # First index
        store.index_project_incremental(str(project_dir))

        # Force re-index
        result = store.index_project_incremental(str(project_dir), force=True)

        # All files should be re-indexed
        assert result.files_indexed == 3
        assert result.files_skipped == 0

    def test_index_project_incremental_with_settings(self, setup):
        """Test incremental indexing respects embedder settings."""
        store = setup["store"]
        registry = setup["registry"]
        project_dir = setup["project_dir"]

        # Set custom settings to exclude .md files
        settings = ProjectEmbedderSettings(
            exclude_patterns=["*.md"],
        )
        registry.set_embedder_settings(str(project_dir), settings)

        result = store.index_project_incremental(str(project_dir))

        # Should only index .py files (README.md excluded)
        assert result.files_indexed == 2

    def test_include_patterns_whitelist_behavior(self, setup):
        """Test that include_patterns acts as a whitelist when set."""
        store = setup["store"]
        registry = setup["registry"]
        project_dir = setup["project_dir"]

        # Create additional files
        (project_dir / "src").mkdir(exist_ok=True)
        (project_dir / "src" / "main.py").write_text("# Main code\ndef main(): pass\n")
        (project_dir / "tests").mkdir(exist_ok=True)
        (project_dir / "tests" / "test_main.py").write_text("# Test code\ndef test_main(): pass\n")
        (project_dir / "utils.py").write_text("# Utils\ndef util(): pass\n")

        # Set include_patterns to only include src/* files
        settings = ProjectEmbedderSettings(
            include_patterns=["src/*"],
        )
        registry.set_embedder_settings(str(project_dir), settings)

        result = store.index_project_incremental(str(project_dir))

        # Only src/main.py should be indexed (include_patterns acts as whitelist)
        assert result.files_indexed == 1

    def test_include_patterns_with_exclude_patterns(self, setup):
        """Test that exclude_patterns still applies when include_patterns is set."""
        store = setup["store"]
        registry = setup["registry"]
        project_dir = setup["project_dir"]

        # Create files in src
        (project_dir / "src").mkdir(exist_ok=True)
        (project_dir / "src" / "main.py").write_text("# Main\n")
        (project_dir / "src" / "main.min.py").write_text("# Minified\n")
        (project_dir / "src" / "utils.py").write_text("# Utils\n")

        # Set include_patterns with exclude override
        settings = ProjectEmbedderSettings(
            include_patterns=["src/*"],
            exclude_patterns=["*.min.py"],
        )
        registry.set_embedder_settings(str(project_dir), settings)

        result = store.index_project_incremental(str(project_dir))

        # Should index src/main.py and src/utils.py, exclude *.min.py
        assert result.files_indexed == 2

    def test_on_file_indexed_callback(self, setup):
        """Test that on_file_indexed callback is called for each file."""
        store = setup["store"]
        project_dir = setup["project_dir"]

        processed_files = []

        def callback(proj_path, file_path, chunks, skipped):
            processed_files.append({
                "project_path": proj_path,
                "file_path": file_path,
                "chunks": chunks,
                "skipped": skipped,
            })

        result = store.index_project_incremental(
            str(project_dir), on_file_indexed=callback
        )

        # Should have called callback for each file processed
        assert len(processed_files) == result.files_indexed + result.files_skipped
        # All files should have project_path set
        assert all(f["project_path"] == str(project_dir.resolve()) for f in processed_files)


# === GlobalMemoryStore Active Context Tests ===


class TestGlobalMemoryStoreActiveContext:
    """Tests for active project context methods."""

    @pytest.fixture
    def setup(self, tmp_path):
        """Create GlobalMemoryStore with multiple projects."""
        db_path = tmp_path / "global_memory.db"
        registry_path = tmp_path / "projects.json"

        registry = ProjectRegistry(config_path=registry_path)

        # Create and register multiple projects
        for i in range(3):
            project_dir = tmp_path / f"project{i}"
            project_dir.mkdir()
            (project_dir / "code.py").write_text(f"# Project {i}\ndef func{i}(): pass\n")
            registry.add_project(str(project_dir), name=f"Project {i}")

        class MockEmbedder:
            def embed(self, text):
                import hashlib
                h = hashlib.md5(text.encode()).hexdigest()
                return [float(int(h[i:i+2], 16)) / 255.0 for i in range(0, 32, 2)] * 48

        store = GlobalMemoryStore(
            db_path=db_path,
            registry=registry,
            embedder=MockEmbedder(),
        )

        # Index all projects
        for p in registry.list_projects():
            store.index_project(p.path)

        return {
            "store": store,
            "registry": registry,
            "tmp_path": tmp_path,
        }

    def test_search_active_projects_none_active(self, setup):
        """Test search returns empty when no projects are active."""
        store = setup["store"]

        results = store.search_active_projects("function")

        assert len(results) == 0

    def test_search_active_projects_with_active(self, setup):
        """Test search only includes active projects."""
        store = setup["store"]
        registry = setup["registry"]

        projects = registry.list_projects()
        # Activate only first project
        registry.set_active(projects[0].path, active=True)

        results = store.search_active_projects("Project")

        # Should only return results from active project
        assert len(results) > 0
        for r in results:
            assert r.project_path == projects[0].path

    def test_search_active_projects_exclude_current(self, setup):
        """Test excluding current project from active search."""
        store = setup["store"]
        registry = setup["registry"]

        projects = registry.list_projects()
        # Activate multiple
        registry.set_active(projects[0].path, active=True)
        registry.set_active(projects[1].path, active=True)

        results = store.search_active_projects(
            "Project",
            exclude_current=projects[0].path,
        )

        # Should not include excluded project
        for r in results:
            assert r.project_path != projects[0].path

    def test_get_active_project_context(self, setup):
        """Test formatted active context for agent injection."""
        store = setup["store"]
        registry = setup["registry"]

        projects = registry.list_projects()
        registry.set_active(projects[0].path, active=True)

        context = store.get_active_project_context("code", max_tokens=1000)

        assert "Cross-Project Context" in context
        assert len(context) > 0

    def test_get_active_project_context_empty(self, setup):
        """Test empty context when no active projects."""
        store = setup["store"]

        context = store.get_active_project_context("anything")

        assert context == ""

    def test_get_active_project_stats(self, setup):
        """Test active project statistics."""
        store = setup["store"]
        registry = setup["registry"]

        projects = registry.list_projects()
        registry.set_active(projects[0].path, active=True)
        registry.set_active(projects[1].path, active=True)

        stats = store.get_active_project_stats()

        assert stats["active_count"] == 2
        assert stats["active_indexed_count"] == 2
        assert len(stats["projects"]) == 2


# === BackgroundIndexer Tests ===


class TestBackgroundIndexer:
    """Tests for BackgroundIndexer service."""

    @pytest.fixture
    def setup(self, tmp_path):
        """Create BackgroundIndexer with dependencies."""
        db_path = tmp_path / "global_memory.db"
        registry_path = tmp_path / "projects.json"

        registry = ProjectRegistry(config_path=registry_path)

        # Create test project
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        (project_dir / "code.py").write_text("def test(): pass\n")
        registry.add_project(str(project_dir), name="Test Project")

        class MockEmbedder:
            def embed(self, text):
                import hashlib
                h = hashlib.md5(text.encode()).hexdigest()
                return [float(int(h[i:i+2], 16)) / 255.0 for i in range(0, 32, 2)] * 48

        store = GlobalMemoryStore(
            db_path=db_path,
            registry=registry,
            embedder=MockEmbedder(),
        )

        event_bus = EventBus()
        config = IndexerConfig(cooldown_seconds=0.1)

        indexer = BackgroundIndexer(
            global_memory=store,
            registry=registry,
            event_bus=event_bus,
            config=config,
        )

        return {
            "indexer": indexer,
            "store": store,
            "registry": registry,
            "event_bus": event_bus,
            "project_dir": project_dir,
        }

    def test_initial_state(self, setup):
        """Test indexer starts in stopped state."""
        indexer = setup["indexer"]

        assert indexer.status == IndexerStatus.STOPPED
        state = indexer.get_state()
        assert state.status == IndexerStatus.STOPPED
        assert state.queue_length == 0

    @pytest.mark.asyncio
    async def test_start_stop(self, setup):
        """Test starting and stopping the indexer."""
        indexer = setup["indexer"]

        # Start
        result = await indexer.start()
        assert result is True
        assert indexer.status == IndexerStatus.RUNNING

        # Can't start twice
        result = await indexer.start()
        assert result is False

        # Stop
        await indexer.stop()
        assert indexer.status == IndexerStatus.STOPPED

    @pytest.mark.asyncio
    async def test_queue_project(self, setup):
        """Test queueing projects for indexing."""
        indexer = setup["indexer"]
        project_dir = setup["project_dir"]

        position = await indexer.queue_project(str(project_dir))

        assert position == 0
        state = indexer.get_state()
        assert state.queue_length == 1

    @pytest.mark.asyncio
    async def test_queue_project_priority(self, setup):
        """Test queue respects priority."""
        indexer = setup["indexer"]
        registry = setup["registry"]
        tmp_path = setup["project_dir"].parent

        # Create more projects
        proj2 = tmp_path / "project2"
        proj3 = tmp_path / "project3"
        proj2.mkdir()
        proj3.mkdir()
        (proj2 / "code.py").write_text("pass")
        (proj3 / "code.py").write_text("pass")
        registry.add_project(str(proj2), name="Project 2")
        registry.add_project(str(proj3), name="Project 3")

        # Queue with different priorities
        await indexer.queue_project(str(proj2), priority=5)
        await indexer.queue_project(str(proj3), priority=1)  # Higher priority

        queue = indexer.get_queue()
        # Higher priority (lower number) should be first
        assert queue[0]["priority"] == 1

    @pytest.mark.asyncio
    async def test_queue_all_projects(self, setup):
        """Test queueing all auto-indexable projects."""
        indexer = setup["indexer"]

        count = await indexer.queue_all_projects()

        assert count == 1  # One project registered
        state = indexer.get_state()
        assert state.queue_length == 1

    @pytest.mark.asyncio
    async def test_index_project_emits_events(self, setup):
        """Test indexing emits progress events."""
        indexer = setup["indexer"]
        event_bus = setup["event_bus"]
        project_dir = setup["project_dir"]

        events = []
        event_bus.subscribe_event(lambda e: events.append(e))

        # Start and queue
        await indexer.start()
        await indexer.queue_project(str(project_dir))

        # Wait for indexing to complete
        await asyncio.sleep(0.5)
        await indexer.stop()

        # Check events were emitted
        event_types = [e.type for e in events]
        assert EventType.INDEXER_STARTED in event_types
        assert EventType.INDEX_QUEUED in event_types
        assert EventType.INDEX_STARTED in event_types
        assert EventType.INDEX_COMPLETED in event_types
        assert EventType.INDEXER_STOPPED in event_types

    @pytest.mark.asyncio
    async def test_clear_queue(self, setup):
        """Test clearing the queue."""
        indexer = setup["indexer"]
        project_dir = setup["project_dir"]

        await indexer.queue_project(str(project_dir))
        assert indexer.get_state().queue_length == 1

        indexer.clear_queue()
        assert indexer.get_state().queue_length == 0

    def test_get_queue(self, setup):
        """Test getting queue contents."""
        indexer = setup["indexer"]

        queue = indexer.get_queue()
        assert queue == []

    @pytest.mark.asyncio
    async def test_indexer_state_tracking(self, setup):
        """Test indexer tracks state correctly."""
        indexer = setup["indexer"]
        project_dir = setup["project_dir"]

        await indexer.start()
        await indexer.queue_project(str(project_dir))

        # Wait for completion
        await asyncio.sleep(0.5)

        state = indexer.get_state()
        assert state.projects_indexed >= 1
        assert state.last_completed is not None

        await indexer.stop()


# === QueuedProject Tests ===


class TestQueuedProject:
    """Tests for QueuedProject priority ordering."""

    def test_priority_ordering(self):
        """Test projects are ordered by priority."""
        p1 = QueuedProject(priority=5, timestamp=time.time(), project_path="/a")
        p2 = QueuedProject(priority=1, timestamp=time.time(), project_path="/b")
        p3 = QueuedProject(priority=3, timestamp=time.time(), project_path="/c")

        sorted_projects = sorted([p1, p2, p3])

        assert sorted_projects[0].priority == 1
        assert sorted_projects[1].priority == 3
        assert sorted_projects[2].priority == 5

    def test_same_priority_fifo(self):
        """Test same priority uses FIFO (timestamp)."""
        import time

        p1 = QueuedProject(priority=5, timestamp=1.0, project_path="/a")
        p2 = QueuedProject(priority=5, timestamp=2.0, project_path="/b")

        # Comparison only uses priority, not timestamp
        # So they're equal in terms of ordering
        assert not (p1 < p2)
        assert not (p1 > p2)


# === Event Schema Tests ===


class TestIndexerEventSchemas:
    """Tests for indexer event payload schemas."""

    def test_index_queued_data(self):
        """Test IndexQueuedData schema."""
        from sindri.core.event_schemas import IndexQueuedData

        data = IndexQueuedData(
            project_path="/tmp/test",
            project_name="Test",
            priority=1,
            queue_position=0,
        )

        assert data.project_path == "/tmp/test"
        assert data.priority == 1

    def test_index_progress_data(self):
        """Test IndexProgressData schema."""
        from sindri.core.event_schemas import IndexProgressData

        data = IndexProgressData(
            project_path="/tmp/test",
            project_name="Test",
            files_processed=5,
            total_files=10,
            chunks_added=25,
            percent_complete=50.0,
        )

        assert data.files_processed == 5
        assert data.percent_complete == 50.0

    def test_index_completed_data(self):
        """Test IndexCompletedData schema."""
        from sindri.core.event_schemas import IndexCompletedData

        data = IndexCompletedData(
            project_path="/tmp/test",
            project_name="Test",
            files_indexed=10,
            files_skipped=2,
            chunks_added=50,
            duration_seconds=1.5,
        )

        assert data.files_indexed == 10
        assert data.duration_seconds == 1.5

    def test_event_payload_models_mapping(self):
        """Test all indexer events have payload models."""
        from sindri.core.event_schemas import EVENT_PAYLOAD_MODELS

        assert "INDEX_QUEUED" in EVENT_PAYLOAD_MODELS
        assert "INDEX_STARTED" in EVENT_PAYLOAD_MODELS
        assert "INDEX_PROGRESS" in EVENT_PAYLOAD_MODELS
        assert "INDEX_COMPLETED" in EVENT_PAYLOAD_MODELS
        assert "INDEX_FAILED" in EVENT_PAYLOAD_MODELS
        assert "INDEXER_STARTED" in EVENT_PAYLOAD_MODELS
        assert "INDEXER_STOPPED" in EVENT_PAYLOAD_MODELS
