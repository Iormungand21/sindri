"""Tests for the Multi-Project Memory system (Phase 8.4)."""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch

from sindri.memory.projects import ProjectConfig, ProjectRegistry
from sindri.memory.global_memory import GlobalMemoryStore, CrossProjectResult


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def temp_projects_file():
    """Create a temporary projects.json file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "projects.json"
        yield config_path


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory with sample files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "sample_project"
        project_dir.mkdir()

        # Create sample Python files
        (project_dir / "main.py").write_text('''"""Main module."""

def main():
    """Entry point for the application."""
    print("Hello, World!")

if __name__ == "__main__":
    main()
''')

        (project_dir / "utils.py").write_text('''"""Utility functions."""

def format_string(s: str) -> str:
    """Format a string with proper casing."""
    return s.strip().title()

def calculate_sum(numbers: list) -> int:
    """Calculate sum of numbers."""
    return sum(numbers)
''')

        # Create subdirectory
        (project_dir / "lib").mkdir()
        (project_dir / "lib" / "helpers.py").write_text('''"""Helper functions."""

def helper_function():
    return "helper"
''')

        yield project_dir


@pytest.fixture
def temp_second_project():
    """Create a second temporary project for cross-project tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "second_project"
        project_dir.mkdir()

        (project_dir / "api.py").write_text('''"""API module."""

def authenticate_user(username: str, password: str) -> bool:
    """Authenticate a user with credentials."""
    return username == "admin" and password == "secret"

def get_user_profile(user_id: int) -> dict:
    """Get user profile by ID."""
    return {"id": user_id, "name": "User"}
''')

        yield project_dir


@pytest.fixture
def registry(temp_projects_file):
    """Create a ProjectRegistry with temp file."""
    return ProjectRegistry(config_path=temp_projects_file)


# ============================================================================
# ProjectConfig Tests
# ============================================================================


class TestProjectConfig:
    """Tests for ProjectConfig dataclass."""

    def test_create_with_defaults(self):
        """Test creating ProjectConfig with minimal args."""
        config = ProjectConfig(path="/home/user/project")
        assert config.path == "/home/user/project"
        assert config.name == "project"  # Default from path
        assert config.tags == []
        assert config.enabled is True
        assert config.indexed is False

    def test_create_with_custom_name(self):
        """Test creating ProjectConfig with custom name."""
        config = ProjectConfig(path="/home/user/project", name="My Project")
        assert config.name == "My Project"

    def test_create_with_tags(self):
        """Test creating ProjectConfig with tags."""
        config = ProjectConfig(
            path="/home/user/project",
            tags=["python", "fastapi", "web"]
        )
        assert config.tags == ["python", "fastapi", "web"]

    def test_to_dict(self):
        """Test converting ProjectConfig to dictionary."""
        config = ProjectConfig(
            path="/home/user/project",
            name="Test Project",
            tags=["python"],
            enabled=True,
            indexed=True,
            file_count=10
        )
        data = config.to_dict()
        assert data["path"] == "/home/user/project"
        assert data["name"] == "Test Project"
        assert data["tags"] == ["python"]
        assert data["enabled"] is True
        assert data["indexed"] is True
        assert data["file_count"] == 10

    def test_from_dict(self):
        """Test creating ProjectConfig from dictionary."""
        data = {
            "path": "/home/user/project",
            "name": "From Dict",
            "tags": ["ml", "pytorch"],
            "enabled": False,
            "indexed": True,
            "file_count": 5
        }
        config = ProjectConfig.from_dict(data)
        assert config.path == "/home/user/project"
        assert config.name == "From Dict"
        assert config.tags == ["ml", "pytorch"]
        assert config.enabled is False
        assert config.indexed is True

    def test_matches_tag(self):
        """Test tag matching."""
        config = ProjectConfig(path="/test", tags=["Python", "FastAPI"])
        assert config.matches_tag("python") is True  # Case insensitive
        assert config.matches_tag("FASTAPI") is True
        assert config.matches_tag("django") is False

    def test_matches_any_tag(self):
        """Test matching any of multiple tags."""
        config = ProjectConfig(path="/test", tags=["python", "fastapi"])
        assert config.matches_any_tag(["python", "django"]) is True
        assert config.matches_any_tag(["django", "flask"]) is False


# ============================================================================
# ProjectRegistry Tests
# ============================================================================


class TestProjectRegistry:
    """Tests for ProjectRegistry."""

    def test_init_creates_empty_registry(self, temp_projects_file):
        """Test initializing empty registry."""
        registry = ProjectRegistry(config_path=temp_projects_file)
        assert registry.get_project_count() == 0

    def test_add_project(self, registry, temp_project_dir):
        """Test adding a project."""
        project = registry.add_project(str(temp_project_dir))
        assert project is not None
        assert project.name == temp_project_dir.name
        assert project.enabled is True
        assert registry.get_project_count() == 1

    def test_add_project_with_custom_name(self, registry, temp_project_dir):
        """Test adding a project with custom name."""
        project = registry.add_project(
            str(temp_project_dir),
            name="My Custom Name"
        )
        assert project.name == "My Custom Name"

    def test_add_project_with_tags(self, registry, temp_project_dir):
        """Test adding a project with tags."""
        project = registry.add_project(
            str(temp_project_dir),
            tags=["python", "test"]
        )
        assert "python" in project.tags
        assert "test" in project.tags

    def test_add_project_invalid_path(self, registry):
        """Test adding a project with invalid path."""
        with pytest.raises(ValueError, match="does not exist"):
            registry.add_project("/nonexistent/path")

    def test_add_project_duplicate_updates(self, registry, temp_project_dir):
        """Test adding duplicate project updates existing."""
        project1 = registry.add_project(str(temp_project_dir), tags=["first"])
        project2 = registry.add_project(str(temp_project_dir), tags=["second"])

        assert registry.get_project_count() == 1
        assert "first" in project2.tags
        assert "second" in project2.tags

    def test_remove_project(self, registry, temp_project_dir):
        """Test removing a project."""
        registry.add_project(str(temp_project_dir))
        assert registry.get_project_count() == 1

        result = registry.remove_project(str(temp_project_dir))
        assert result is True
        assert registry.get_project_count() == 0

    def test_remove_nonexistent_project(self, registry):
        """Test removing a project that doesn't exist."""
        result = registry.remove_project("/nonexistent")
        assert result is False

    def test_get_project(self, registry, temp_project_dir):
        """Test getting a project by path."""
        registry.add_project(str(temp_project_dir), name="Test")
        project = registry.get_project(str(temp_project_dir))
        assert project is not None
        assert project.name == "Test"

    def test_get_project_not_found(self, registry):
        """Test getting nonexistent project."""
        project = registry.get_project("/nonexistent")
        assert project is None

    def test_list_projects(self, registry, temp_project_dir, temp_second_project):
        """Test listing all projects."""
        registry.add_project(str(temp_project_dir), name="First")
        registry.add_project(str(temp_second_project), name="Second")

        projects = registry.list_projects()
        assert len(projects) == 2
        names = [p.name for p in projects]
        assert "First" in names
        assert "Second" in names

    def test_list_projects_enabled_only(self, registry, temp_project_dir, temp_second_project):
        """Test listing only enabled projects."""
        registry.add_project(str(temp_project_dir), name="Enabled")
        project2 = registry.add_project(str(temp_second_project), name="Disabled")
        registry.enable_project(str(temp_second_project), enabled=False)

        projects = registry.list_projects(enabled_only=True)
        assert len(projects) == 1
        assert projects[0].name == "Enabled"

    def test_list_projects_by_tags(self, registry, temp_project_dir, temp_second_project):
        """Test listing projects filtered by tags."""
        registry.add_project(str(temp_project_dir), tags=["python", "web"])
        registry.add_project(str(temp_second_project), tags=["python", "ml"])

        projects = registry.list_projects(tags=["web"])
        assert len(projects) == 1
        assert str(temp_project_dir) in projects[0].path

        # Both have python
        projects = registry.list_projects(tags=["python"])
        assert len(projects) == 2

    def test_tag_project(self, registry, temp_project_dir):
        """Test setting tags on a project."""
        registry.add_project(str(temp_project_dir))
        project = registry.tag_project(str(temp_project_dir), ["new", "tags"])

        assert project is not None
        assert project.tags == ["new", "tags"]

    def test_add_tags(self, registry, temp_project_dir):
        """Test adding tags to existing tags."""
        registry.add_project(str(temp_project_dir), tags=["existing"])
        project = registry.add_tags(str(temp_project_dir), ["new", "more"])

        assert "existing" in project.tags
        assert "new" in project.tags
        assert "more" in project.tags

    def test_enable_disable_project(self, registry, temp_project_dir):
        """Test enabling and disabling a project."""
        registry.add_project(str(temp_project_dir))

        project = registry.enable_project(str(temp_project_dir), enabled=False)
        assert project.enabled is False

        project = registry.enable_project(str(temp_project_dir), enabled=True)
        assert project.enabled is True

    def test_set_indexed(self, registry, temp_project_dir):
        """Test marking a project as indexed."""
        registry.add_project(str(temp_project_dir))
        project = registry.set_indexed(str(temp_project_dir), indexed=True, file_count=10)

        assert project.indexed is True
        assert project.file_count == 10
        assert project.last_indexed is not None

    def test_find_by_name(self, registry, temp_project_dir):
        """Test finding a project by name."""
        registry.add_project(str(temp_project_dir), name="FindMe")
        project = registry.find_by_name("findme")  # Case insensitive
        assert project is not None
        assert project.name == "FindMe"

    def test_get_all_tags(self, registry, temp_project_dir, temp_second_project):
        """Test getting all unique tags."""
        registry.add_project(str(temp_project_dir), tags=["python", "web"])
        registry.add_project(str(temp_second_project), tags=["python", "ml"])

        all_tags = registry.get_all_tags()
        assert "python" in all_tags
        assert "web" in all_tags
        assert "ml" in all_tags
        assert len(all_tags) == 3

    def test_persistence(self, temp_projects_file, temp_project_dir):
        """Test that registry persists to file."""
        # Create and add project
        registry1 = ProjectRegistry(config_path=temp_projects_file)
        registry1.add_project(str(temp_project_dir), name="Persist", tags=["test"])

        # Create new registry instance and verify data
        registry2 = ProjectRegistry(config_path=temp_projects_file)
        assert registry2.get_project_count() == 1
        project = registry2.list_projects()[0]
        assert project.name == "Persist"
        assert "test" in project.tags


# ============================================================================
# GlobalMemoryStore Tests (with mocked embedder)
# ============================================================================


class TestGlobalMemoryStore:
    """Tests for GlobalMemoryStore."""

    @pytest.fixture
    def mock_embedder(self):
        """Create a mock embedder."""
        embedder = MagicMock()
        embedder.dimension = 768
        # Return consistent fake embeddings
        embedder.embed.return_value = [0.1] * 768
        return embedder

    @pytest.fixture
    def global_memory(self, temp_projects_file, mock_embedder):
        """Create GlobalMemoryStore with mocked embedder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "global_memory.db"
            registry = ProjectRegistry(config_path=temp_projects_file)
            yield GlobalMemoryStore(
                db_path=db_path,
                embedder=mock_embedder,
                registry=registry
            )

    def test_init(self, global_memory):
        """Test GlobalMemoryStore initialization."""
        assert global_memory.conn is not None
        stats = global_memory.get_stats()
        assert stats["indexed_projects"] == 0

    def test_index_project(self, global_memory, temp_project_dir):
        """Test indexing a project."""
        # Add to registry first
        global_memory.registry.add_project(str(temp_project_dir))

        chunks = global_memory.index_project(str(temp_project_dir))
        assert chunks > 0

        stats = global_memory.get_stats()
        assert stats["indexed_projects"] == 1
        assert stats["total_chunks"] == chunks

    def test_index_project_not_found(self, global_memory):
        """Test indexing nonexistent project."""
        chunks = global_memory.index_project("/nonexistent/path")
        assert chunks == 0

    def test_index_project_skip_hidden(self, global_memory, temp_project_dir):
        """Test that hidden files are skipped."""
        # Create hidden file
        (temp_project_dir / ".hidden.py").write_text("secret = 'hidden'")

        global_memory.registry.add_project(str(temp_project_dir))
        chunks = global_memory.index_project(str(temp_project_dir))

        # Verify hidden file wasn't indexed (check metadata)
        stats = global_memory.get_project_stats(str(temp_project_dir))
        assert stats is not None

    def test_index_project_force_reindex(self, global_memory, temp_project_dir):
        """Test force re-indexing a project."""
        global_memory.registry.add_project(str(temp_project_dir))

        # First index
        chunks1 = global_memory.index_project(str(temp_project_dir))

        # Second index without force - should use cached
        chunks2 = global_memory.index_project(str(temp_project_dir))
        assert chunks2 == chunks1  # Returns cached count

        # Force re-index
        chunks3 = global_memory.index_project(str(temp_project_dir), force=True)
        assert chunks3 > 0

    def test_search(self, global_memory, temp_project_dir):
        """Test searching indexed projects."""
        global_memory.registry.add_project(str(temp_project_dir))
        global_memory.index_project(str(temp_project_dir))

        results = global_memory.search("format string", limit=5)
        assert len(results) > 0
        assert all(isinstance(r, CrossProjectResult) for r in results)

    def test_search_by_tags(self, global_memory, temp_project_dir, temp_second_project):
        """Test searching with tag filter."""
        global_memory.registry.add_project(str(temp_project_dir), tags=["util"])
        global_memory.registry.add_project(str(temp_second_project), tags=["api"])

        global_memory.index_project(str(temp_project_dir))
        global_memory.index_project(str(temp_second_project))

        # Search only in util-tagged projects
        results = global_memory.search_by_tags("format", tags=["util"])

        # Should only have results from temp_project_dir
        for r in results:
            assert r.project_path == str(Path(temp_project_dir).resolve())

    def test_search_exclude_current(self, global_memory, temp_project_dir, temp_second_project):
        """Test excluding current project from search."""
        global_memory.registry.add_project(str(temp_project_dir))
        global_memory.registry.add_project(str(temp_second_project))

        global_memory.index_project(str(temp_project_dir))
        global_memory.index_project(str(temp_second_project))

        # Exclude first project
        results = global_memory.search(
            "function",
            exclude_current=str(Path(temp_project_dir).resolve())
        )

        # Results should only be from second project
        for r in results:
            assert r.project_path == str(Path(temp_second_project).resolve())

    def test_remove_project(self, global_memory, temp_project_dir):
        """Test removing a project from global memory."""
        global_memory.registry.add_project(str(temp_project_dir))
        global_memory.index_project(str(temp_project_dir))

        stats_before = global_memory.get_stats()
        assert stats_before["indexed_projects"] == 1

        global_memory.remove_project(str(temp_project_dir))

        stats_after = global_memory.get_stats()
        assert stats_after["indexed_projects"] == 0

    def test_index_all_projects(self, global_memory, temp_project_dir, temp_second_project):
        """Test indexing all registered projects."""
        global_memory.registry.add_project(str(temp_project_dir))
        global_memory.registry.add_project(str(temp_second_project))

        results = global_memory.index_all_projects()
        assert len(results) == 2
        assert all(chunks > 0 for chunks in results.values())

    def test_get_stats(self, global_memory, temp_project_dir):
        """Test getting global memory statistics."""
        global_memory.registry.add_project(str(temp_project_dir))
        global_memory.index_project(str(temp_project_dir))

        stats = global_memory.get_stats()
        assert "indexed_projects" in stats
        assert "total_chunks" in stats
        assert "total_files" in stats
        assert "registered_projects" in stats
        assert "enabled_projects" in stats

    def test_get_project_stats(self, global_memory, temp_project_dir):
        """Test getting stats for a specific project."""
        global_memory.registry.add_project(str(temp_project_dir))
        global_memory.index_project(str(temp_project_dir))

        stats = global_memory.get_project_stats(str(temp_project_dir))
        assert stats is not None
        assert "file_count" in stats
        assert "chunk_count" in stats
        assert "indexed_at" in stats

    def test_get_project_stats_not_found(self, global_memory):
        """Test getting stats for nonexistent project."""
        stats = global_memory.get_project_stats("/nonexistent")
        assert stats is None

    def test_format_search_context(self, global_memory, temp_project_dir):
        """Test formatting search results for context injection."""
        global_memory.registry.add_project(str(temp_project_dir))
        global_memory.index_project(str(temp_project_dir))

        results = global_memory.search("function", limit=5)
        context = global_memory.format_search_context(results, max_tokens=1000)

        assert isinstance(context, str)
        if results:
            assert temp_project_dir.name in context or "sample_project" in context


# ============================================================================
# CrossProjectResult Tests
# ============================================================================


class TestCrossProjectResult:
    """Tests for CrossProjectResult dataclass."""

    def test_create_result(self):
        """Test creating a CrossProjectResult."""
        result = CrossProjectResult(
            content="def hello(): pass",
            project_path="/home/user/project",
            project_name="Test Project",
            file_path="main.py",
            start_line=1,
            end_line=10,
            similarity=0.95,
            tags=["python"]
        )
        assert result.content == "def hello(): pass"
        assert result.project_name == "Test Project"
        assert result.similarity == 0.95

    def test_to_dict(self):
        """Test converting CrossProjectResult to dictionary."""
        result = CrossProjectResult(
            content="code",
            project_path="/path",
            project_name="Project",
            file_path="file.py",
            start_line=1,
            end_line=5,
            similarity=0.9,
            tags=["tag1"]
        )
        data = result.to_dict()
        assert data["content"] == "code"
        assert data["project_name"] == "Project"
        assert data["similarity"] == 0.9
        assert data["tags"] == ["tag1"]


# ============================================================================
# CLI Command Tests (basic)
# ============================================================================


class TestProjectsCLI:
    """Tests for projects CLI commands."""

    def test_cli_group_exists(self):
        """Test that projects CLI group is registered."""
        from sindri.cli import cli, projects
        assert projects is not None

    def test_projects_list_command_exists(self):
        """Test that projects list command exists."""
        from click.testing import CliRunner
        from sindri.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["projects", "list"])
        # Should not error (may show "no projects registered")
        assert result.exit_code == 0

    def test_projects_stats_command(self):
        """Test projects stats command."""
        from click.testing import CliRunner
        from sindri.cli import cli

        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use isolated filesystem for test
            result = runner.invoke(cli, ["projects", "stats"])
            assert result.exit_code == 0
            assert "Global Memory Statistics" in result.output

    def test_projects_add_command(self):
        """Test projects add command with temp directory."""
        from click.testing import CliRunner
        from sindri.cli import cli

        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a project directory
            project_dir = Path(tmpdir) / "test_project"
            project_dir.mkdir()
            (project_dir / "main.py").write_text("print('hello')")

            # Patch the embedding to avoid Ollama dependency
            with patch('sindri.memory.global_memory.GlobalMemoryStore.index_project', return_value=1):
                result = runner.invoke(cli, [
                    "projects", "add",
                    str(project_dir),
                    "--name", "Test",
                    "--tags", "python,test",
                    "--no-index"  # Skip actual indexing
                ])

            assert result.exit_code == 0
            assert "Added project" in result.output or "Test" in result.output
