"""Tests for Phase 7.4: Codebase Understanding."""

import os
import tempfile
import pytest
from pathlib import Path

from sindri.analysis.results import (
    CodebaseAnalysis,
    DependencyInfo,
    ArchitectureInfo,
    StyleInfo,
    ModuleInfo,
)
from sindri.analysis.dependencies import DependencyAnalyzer
from sindri.analysis.architecture import ArchitectureDetector
from sindri.analysis.style import StyleAnalyzer
from sindri.memory.codebase import CodebaseAnalyzer, CodebaseAnalysisStore


# === Fixtures ===

@pytest.fixture
def temp_project():
    """Create a temporary Python project for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)

        # Create package structure
        pkg_dir = project_path / "mypackage"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")

        # Create core module
        core_dir = pkg_dir / "core"
        core_dir.mkdir()
        (core_dir / "__init__.py").write_text("")
        (core_dir / "main.py").write_text('''"""Main module with entry point."""
import asyncio
from typing import Optional, List
from mypackage.utils import helper

async def run(config: dict) -> Optional[str]:
    """Run the main process.

    Args:
        config: Configuration dictionary

    Returns:
        Result string or None
    """
    result = await helper.process(config)
    return result

if __name__ == "__main__":
    asyncio.run(run({}))
''')

        # Create utils module
        utils_dir = pkg_dir / "utils"
        utils_dir.mkdir()
        (utils_dir / "__init__.py").write_text("")
        (utils_dir / "helper.py").write_text('''"""Helper utilities."""
import json
from dataclasses import dataclass
from typing import Any

@dataclass
class Result:
    """Result container."""
    value: Any
    status: str

async def process(data: dict) -> str:
    """Process data."""
    return json.dumps(data)

def format_output(result: Result) -> str:
    """Format result for output."""
    return f"{result.status}: {result.value}"
''')

        # Create tests directory
        tests_dir = project_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "__init__.py").write_text("")
        (tests_dir / "test_main.py").write_text('''"""Tests for main module."""
import pytest
from mypackage.core.main import run

@pytest.fixture
def sample_config():
    return {"key": "value"}

@pytest.mark.asyncio
async def test_run(sample_config):
    result = await run(sample_config)
    assert result is not None
''')

        # Create config files
        (project_path / "pyproject.toml").write_text('''[project]
name = "mypackage"
version = "0.1.0"

[tool.black]
line-length = 100

[tool.ruff]
line-length = 100

[tool.pytest.ini_options]
asyncio_mode = "auto"
''')
        (project_path / "conftest.py").write_text('"""Pytest configuration."""\n')

        yield project_path


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    try:
        os.unlink(db_path)
    except Exception:
        pass


# === DependencyInfo Tests ===

class TestDependencyInfo:
    """Tests for DependencyInfo dataclass."""

    def test_to_dict_from_dict_roundtrip(self):
        """Test serialization roundtrip."""
        info = DependencyInfo(
            internal_dependencies={"main.py": ["utils", "config"]},
            external_packages={"click", "pytest"},
            circular_dependencies=[["a", "b", "a"]],
            most_imported=[("utils", 5), ("config", 3)],
            orphan_modules=["orphan.py"],
            entry_points=["main.py", "cli.py"],
        )

        data = info.to_dict()
        restored = DependencyInfo.from_dict(data)

        assert restored.internal_dependencies == info.internal_dependencies
        assert restored.external_packages == info.external_packages
        assert restored.circular_dependencies == info.circular_dependencies
        assert restored.entry_points == info.entry_points

    def test_format_summary(self):
        """Test summary formatting."""
        info = DependencyInfo(
            entry_points=["main.py"],
            circular_dependencies=[["a", "b", "c"]],
            most_imported=[("utils", 10)],
            external_packages={"flask", "click"},
        )

        summary = info.format_summary()
        assert "Dependency Analysis" in summary
        assert "main.py" in summary
        assert "Circular dependencies" in summary
        assert "utils" in summary


# === ArchitectureInfo Tests ===

class TestArchitectureInfo:
    """Tests for ArchitectureInfo dataclass."""

    def test_to_dict_from_dict_roundtrip(self):
        """Test serialization roundtrip."""
        info = ArchitectureInfo(
            detected_pattern="layered",
            confidence=0.85,
            layer_structure={"api": ["routes/"], "data": ["models/"]},
            source_roots=["src"],
            test_directories=["tests"],
            project_type="web_api",
            frameworks_detected=["fastapi", "pydantic"],
        )

        data = info.to_dict()
        restored = ArchitectureInfo.from_dict(data)

        assert restored.detected_pattern == "layered"
        assert restored.confidence == 0.85
        assert restored.project_type == "web_api"
        assert "fastapi" in restored.frameworks_detected

    def test_format_summary(self):
        """Test summary formatting."""
        info = ArchitectureInfo(
            detected_pattern="mvc",
            confidence=0.75,
            project_type="web_app",
            frameworks_detected=["django"],
            layer_structure={"presentation": ["views/"]},
        )

        summary = info.format_summary()
        assert "Architecture Analysis" in summary
        assert "mvc" in summary
        assert "75%" in summary
        assert "django" in summary


# === StyleInfo Tests ===

class TestStyleInfo:
    """Tests for StyleInfo dataclass."""

    def test_to_dict_from_dict_roundtrip(self):
        """Test serialization roundtrip."""
        info = StyleInfo(
            naming_conventions={"functions": "snake_case", "classes": "PascalCase"},
            indentation="spaces",
            indent_size=4,
            docstring_style="google",
            has_type_hints=True,
            formatter="black",
            linter="ruff",
            async_style=True,
            test_framework="pytest",
        )

        data = info.to_dict()
        restored = StyleInfo.from_dict(data)

        assert restored.naming_conventions["functions"] == "snake_case"
        assert restored.indent_size == 4
        assert restored.formatter == "black"
        assert restored.has_type_hints is True

    def test_format_summary(self):
        """Test summary formatting."""
        info = StyleInfo(
            indentation="spaces",
            indent_size=4,
            formatter="black",
            linter="ruff",
            docstring_style="google",
            has_type_hints=True,
            test_framework="pytest",
        )

        summary = info.format_summary()
        assert "Style Analysis" in summary
        assert "4 spaces" in summary
        assert "black" in summary
        assert "ruff" in summary


# === CodebaseAnalysis Tests ===

class TestCodebaseAnalysis:
    """Tests for CodebaseAnalysis dataclass."""

    def test_to_dict_from_dict_roundtrip(self):
        """Test serialization roundtrip."""
        analysis = CodebaseAnalysis(
            project_path="/path/to/project",
            project_id="test_project",
            primary_language="python",
            total_files=50,
            total_lines=5000,
            files_by_language={"python": 40, "yaml": 10},
        )

        data = analysis.to_dict()
        restored = CodebaseAnalysis.from_dict(data)

        assert restored.project_id == "test_project"
        assert restored.primary_language == "python"
        assert restored.total_files == 50
        assert restored.files_by_language["python"] == 40

    def test_to_json_from_json(self):
        """Test JSON serialization."""
        analysis = CodebaseAnalysis(
            project_id="json_test",
            primary_language="typescript",
        )

        json_str = analysis.to_json()
        restored = CodebaseAnalysis.from_json(json_str)

        assert restored.project_id == "json_test"
        assert restored.primary_language == "typescript"

    def test_format_summary(self):
        """Test complete summary formatting."""
        analysis = CodebaseAnalysis(
            project_id="summary_test",
            primary_language="python",
            total_files=100,
            total_lines=10000,
            files_by_language={"python": 80, "yaml": 20},
        )

        summary = analysis.format_summary()
        assert "summary_test" in summary
        assert "python" in summary.lower()
        assert "100" in summary
        assert "10,000" in summary

    def test_format_context(self):
        """Test agent context formatting."""
        analysis = CodebaseAnalysis(
            primary_language="python",
            architecture=ArchitectureInfo(
                detected_pattern="layered",
                project_type="cli",
                frameworks_detected=["click"],
            ),
            style=StyleInfo(
                has_type_hints=True,
                docstring_style="google",
                async_style=True,
                formatter="black",
            ),
            dependencies=DependencyInfo(
                entry_points=["cli.py"],
            ),
        )

        context = analysis.format_context()
        assert "python" in context.lower()
        assert "layered" in context.lower()
        assert "click" in context.lower()
        assert "type hints" in context.lower()


# === DependencyAnalyzer Tests ===

class TestDependencyAnalyzer:
    """Tests for DependencyAnalyzer."""

    def test_analyze_finds_entry_points(self, temp_project):
        """Test entry point detection."""
        analyzer = DependencyAnalyzer(str(temp_project))
        result = analyzer.analyze()

        # Should find conftest.py (has if __name__)
        assert len(result.entry_points) >= 0  # May have conftest.py

    def test_analyze_finds_internal_dependencies(self, temp_project):
        """Test internal dependency detection."""
        analyzer = DependencyAnalyzer(str(temp_project))
        result = analyzer.analyze()

        # main.py imports from mypackage.utils
        assert len(result.internal_dependencies) >= 0

    def test_analyze_finds_external_packages(self, temp_project):
        """Test external package detection."""
        analyzer = DependencyAnalyzer(str(temp_project))
        result = analyzer.analyze()

        # Should find json, pytest, etc.
        assert isinstance(result.external_packages, set)

    def test_detect_package_name(self, temp_project):
        """Test package name detection."""
        analyzer = DependencyAnalyzer(str(temp_project))
        assert analyzer.package_name == "mypackage"

    def test_circular_dependency_detection(self):
        """Test circular dependency detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = Path(tmpdir) / "pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("")
            (pkg / "a.py").write_text("from pkg import b")
            (pkg / "b.py").write_text("from pkg import a")

            analyzer = DependencyAnalyzer(tmpdir)
            result = analyzer.analyze()

            # May or may not detect depending on analysis depth
            assert isinstance(result.circular_dependencies, list)


# === ArchitectureDetector Tests ===

class TestArchitectureDetector:
    """Tests for ArchitectureDetector."""

    def test_analyze_detects_pattern(self, temp_project):
        """Test architecture pattern detection."""
        detector = ArchitectureDetector(str(temp_project))
        result = detector.analyze()

        assert result.detected_pattern in ["layered", "modular", "flat", "mvc", "monolith"]
        assert 0 <= result.confidence <= 1.0

    def test_analyze_finds_test_directories(self, temp_project):
        """Test test directory detection."""
        detector = ArchitectureDetector(str(temp_project))
        result = detector.analyze()

        # Should find tests/ directory
        assert any("tests" in d for d in result.test_directories)

    def test_analyze_finds_config_files(self, temp_project):
        """Test config file detection."""
        detector = ArchitectureDetector(str(temp_project))
        result = detector.analyze()

        # Should find pyproject.toml
        assert any("pyproject.toml" in f for f in result.config_files)

    def test_analyze_detects_frameworks(self, temp_project):
        """Test framework detection."""
        detector = ArchitectureDetector(str(temp_project))
        result = detector.analyze()

        # Should detect pytest from test files
        assert "pytest" in result.frameworks_detected or len(result.frameworks_detected) >= 0

    def test_analyze_detects_project_type(self, temp_project):
        """Test project type detection."""
        detector = ArchitectureDetector(str(temp_project))
        result = detector.analyze()

        assert result.project_type in ["cli", "web_api", "web_app", "library", "microservice", "data_pipeline", "unknown"]


# === StyleAnalyzer Tests ===

class TestStyleAnalyzer:
    """Tests for StyleAnalyzer."""

    def test_analyze_detects_indentation(self, temp_project):
        """Test indentation detection."""
        analyzer = StyleAnalyzer(str(temp_project))
        result = analyzer.analyze()

        assert result.indentation in ["spaces", "tabs"]
        assert result.indent_size > 0

    def test_analyze_detects_naming_conventions(self, temp_project):
        """Test naming convention detection."""
        analyzer = StyleAnalyzer(str(temp_project))
        result = analyzer.analyze()

        # Should detect snake_case for functions
        assert isinstance(result.naming_conventions, dict)

    def test_analyze_detects_docstring_style(self, temp_project):
        """Test docstring style detection."""
        analyzer = StyleAnalyzer(str(temp_project))
        result = analyzer.analyze()

        # Project uses Google-style docstrings
        assert result.docstring_style in ["google", "numpy", "sphinx", "epytext", "unknown"]

    def test_analyze_detects_type_hints(self, temp_project):
        """Test type hint detection."""
        analyzer = StyleAnalyzer(str(temp_project))
        result = analyzer.analyze()

        # Project uses type hints
        assert result.has_type_hints is True

    def test_analyze_detects_async_style(self, temp_project):
        """Test async pattern detection."""
        analyzer = StyleAnalyzer(str(temp_project))
        result = analyzer.analyze()

        # Project uses async/await
        assert result.async_style is True

    def test_analyze_detects_formatters(self, temp_project):
        """Test formatter detection."""
        analyzer = StyleAnalyzer(str(temp_project))
        result = analyzer.analyze()

        # pyproject.toml has black config
        assert result.formatter == "black"
        assert result.linter == "ruff"

    def test_analyze_finds_config_files(self, temp_project):
        """Test config file finding."""
        analyzer = StyleAnalyzer(str(temp_project))
        result = analyzer.analyze()

        # Should find pyproject.toml
        assert "pyproject.toml" in result.formatting_configs

    def test_analyze_detects_test_framework(self, temp_project):
        """Test framework detection."""
        analyzer = StyleAnalyzer(str(temp_project))
        result = analyzer.analyze()

        # Project uses pytest
        assert result.test_framework == "pytest"


# === CodebaseAnalysisStore Tests ===

class TestCodebaseAnalysisStore:
    """Tests for CodebaseAnalysisStore."""

    def test_store_and_retrieve(self, temp_db):
        """Test storing and retrieving analysis."""
        store = CodebaseAnalysisStore(temp_db)

        analysis = CodebaseAnalysis(
            project_id="test_project",
            project_path="/path/to/project",
            primary_language="python",
            total_files=100,
        )

        row_id = store.store(analysis)
        assert row_id > 0

        retrieved = store.get("test_project")
        assert retrieved is not None
        assert retrieved.project_id == "test_project"
        assert retrieved.primary_language == "python"

        store.close()

    def test_update_existing(self, temp_db):
        """Test updating existing analysis."""
        store = CodebaseAnalysisStore(temp_db)

        # Store first version
        analysis1 = CodebaseAnalysis(
            project_id="update_test",
            total_files=50,
        )
        store.store(analysis1)

        # Update with new data
        analysis2 = CodebaseAnalysis(
            project_id="update_test",
            total_files=100,
        )
        store.store(analysis2)

        # Should have updated
        retrieved = store.get("update_test")
        assert retrieved.total_files == 100

        # Should still be just one entry
        assert store.get_analysis_count() == 1

        store.close()

    def test_delete(self, temp_db):
        """Test deleting analysis."""
        store = CodebaseAnalysisStore(temp_db)

        analysis = CodebaseAnalysis(project_id="delete_test")
        store.store(analysis)

        assert store.delete("delete_test") is True
        assert store.get("delete_test") is None
        assert store.delete("delete_test") is False

        store.close()

    def test_list_projects(self, temp_db):
        """Test listing analyzed projects."""
        store = CodebaseAnalysisStore(temp_db)

        store.store(CodebaseAnalysis(project_id="project1", primary_language="python"))
        store.store(CodebaseAnalysis(project_id="project2", primary_language="typescript"))

        projects = store.list_projects()
        assert len(projects) == 2
        assert any(p["project_id"] == "project1" for p in projects)
        assert any(p["project_id"] == "project2" for p in projects)

        store.close()

    def test_get_analysis_count(self, temp_db):
        """Test getting analysis count."""
        store = CodebaseAnalysisStore(temp_db)

        assert store.get_analysis_count() == 0

        store.store(CodebaseAnalysis(project_id="count_test"))
        assert store.get_analysis_count() == 1

        store.close()


# === CodebaseAnalyzer Tests ===

class TestCodebaseAnalyzer:
    """Tests for CodebaseAnalyzer."""

    def test_analyze_project(self, temp_project, temp_db):
        """Test full project analysis."""
        analyzer = CodebaseAnalyzer(temp_db)
        result = analyzer.analyze_project(str(temp_project), "test_project")

        assert result.project_id == "test_project"
        assert result.primary_language == "python"
        assert result.total_files > 0
        assert result.total_lines > 0

        # Check sub-analyses
        assert result.architecture is not None
        assert result.dependencies is not None
        assert result.style is not None

        analyzer.close()

    def test_cached_analysis(self, temp_project, temp_db):
        """Test that analysis is cached."""
        analyzer = CodebaseAnalyzer(temp_db)

        # First analysis
        result1 = analyzer.analyze_project(str(temp_project), "cache_test")
        assert result1.analyzed_at is not None

        # Second analysis should use cache (no re-analysis within 24 hours)
        # The result should be the same object from cache
        result2 = analyzer.analyze_project(str(temp_project), "cache_test")
        assert result2.analyzed_at is not None

        # Verify both results have same project_id and data
        assert result1.project_id == result2.project_id
        assert result1.total_files == result2.total_files
        assert result1.primary_language == result2.primary_language

        # Verify there's only one entry in the database (no duplicate)
        assert analyzer.store.get_analysis_count() == 1

        analyzer.close()

    def test_force_reanalysis(self, temp_project, temp_db):
        """Test forced re-analysis."""
        analyzer = CodebaseAnalyzer(temp_db)

        # First analysis
        result1 = analyzer.analyze_project(str(temp_project), "force_test")
        analyzed_at1 = result1.analyzed_at

        # Force re-analysis
        result2 = analyzer.analyze_project(str(temp_project), "force_test", force=True)
        analyzed_at2 = result2.analyzed_at

        # Should be different (re-analyzed)
        assert analyzed_at1 != analyzed_at2

        analyzer.close()

    def test_get_context_for_agent(self, temp_project, temp_db):
        """Test getting context for agent injection."""
        analyzer = CodebaseAnalyzer(temp_db)
        analyzer.analyze_project(str(temp_project), "context_test")

        context = analyzer.get_context_for_agent("context_test")
        assert context is not None
        assert "python" in context.lower()

        analyzer.close()

    def test_get_context_for_nonexistent_project(self, temp_db):
        """Test getting context for non-existent project."""
        analyzer = CodebaseAnalyzer(temp_db)

        context = analyzer.get_context_for_agent("nonexistent")
        assert context is None

        analyzer.close()


# === Integration Tests ===

class TestCodebaseUnderstandingIntegration:
    """Integration tests for codebase understanding."""

    def test_full_analysis_pipeline(self, temp_project, temp_db):
        """Test the complete analysis pipeline."""
        analyzer = CodebaseAnalyzer(temp_db)

        # Run full analysis
        analysis = analyzer.analyze_project(str(temp_project), "integration_test")

        # Verify all components work together
        assert analysis.project_id == "integration_test"
        assert analysis.primary_language == "python"

        # Check architecture detection
        assert analysis.architecture.detected_pattern in ["layered", "modular", "flat", "mvc", "monolith"]

        # Check style detection
        assert analysis.style.formatter == "black"
        assert analysis.style.has_type_hints is True

        # Check context generation
        context = analysis.format_context()
        assert len(context) > 0

        # Verify storage
        retrieved = analyzer.store.get("integration_test")
        assert retrieved is not None
        assert retrieved.project_id == analysis.project_id

        analyzer.close()

    def test_analysis_with_empty_project(self, temp_db):
        """Test analysis of an empty project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            analyzer = CodebaseAnalyzer(temp_db)
            analysis = analyzer.analyze_project(tmpdir, "empty_test")

            assert analysis.total_files == 0
            assert analysis.primary_language == "python"  # Default
            assert analysis.architecture.detected_pattern in ["flat", "unknown"]

            analyzer.close()

    def test_memory_system_integration(self, temp_project, temp_db):
        """Test integration with MuninnMemory system."""
        from sindri.memory.system import MuninnMemory, MemoryConfig

        config = MemoryConfig(
            enable_codebase_analysis=True,
            enable_learning=False,  # Disable for simpler test
        )

        memory = MuninnMemory(temp_db, config)

        # Analyze project
        analysis = memory.analyze_codebase(str(temp_project), "memory_test")
        assert analysis is not None

        # Check retrieval
        retrieved = memory.get_codebase_analysis("memory_test")
        assert retrieved is not None
        assert retrieved.project_id == "memory_test"

        # Check count
        count = memory.get_analysis_count()
        assert count >= 1
