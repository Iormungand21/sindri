"""Tests for Phase 13 Tier 2 Documentation Generation Tools.

Tests for:
- GenerateDocstringsTool
- GenerateReadmeTool
- GenerateApiDocsTool
- ExplainCodeTool
- GenerateChangelogTool
"""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from sindri.tools.documentation import (
    GenerateDocstringsTool,
    GenerateReadmeTool,
    GenerateApiDocsTool,
    ExplainCodeTool,
    GenerateChangelogTool,
    DocstringStyle,
    _detect_docstring_style,
    _parse_params_string,
    _detect_project_info,
    _generate_readme,
    _parse_conventional_commit,
    _generate_changelog,
    FunctionDocInfo,
    ClassDocInfo,
    ParameterInfo,
    ProjectInfo,
    CommitInfo,
)


# Sample Python code for testing
SAMPLE_PYTHON_CODE = '''"""Sample module for testing."""

def add_numbers(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


def process_data(data: list, options: dict = None) -> dict:
    result = {}
    for item in data:
        result[item] = item * 2
    return result


async def fetch_data(url: str, timeout: int = 30) -> bytes:
    # Placeholder for async function
    return b""


class DataProcessor:
    """A class for processing data."""

    def __init__(self, config: dict):
        self.config = config

    def process(self, data):
        return data

    async def async_process(self, data):
        return data
'''

SAMPLE_PYTHON_NO_DOCSTRINGS = '''def calculate_sum(numbers: list[int]) -> int:
    total = 0
    for num in numbers:
        total += num
    return total


def validate_input(data: str, max_length: int = 100) -> bool:
    if not data:
        return False
    return len(data) <= max_length


class Calculator:
    def __init__(self, precision: int = 2):
        self.precision = precision

    def add(self, a: float, b: float) -> float:
        return round(a + b, self.precision)

    def divide(self, a: float, b: float) -> float:
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return round(a / b, self.precision)
'''

SAMPLE_JS_CODE = '''/**
 * Sample JavaScript module
 */

function processItems(items, callback) {
    return items.map(callback);
}

async function fetchData(url, options = {}) {
    const response = await fetch(url, options);
    return response.json();
}

class DataHandler {
    constructor(config) {
        this.config = config;
    }

    process(data) {
        return data;
    }
}

export { processItems, fetchData, DataHandler };
'''

SAMPLE_TS_CODE = '''interface Config {
    debug: boolean;
    timeout: number;
}

function initialize(config: Config): void {
    console.log(config);
}

async function getData(id: number): Promise<string> {
    return `data-${id}`;
}

class Service {
    private config: Config;

    constructor(config: Config) {
        this.config = config;
    }

    public run(): void {
        console.log("running");
    }
}

export { initialize, getData, Service };
'''


@pytest.fixture
def work_dir():
    """Create a temporary working directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_python_file(work_dir):
    """Create a sample Python file."""
    path = work_dir / "sample.py"
    path.write_text(SAMPLE_PYTHON_CODE)
    return path


@pytest.fixture
def sample_python_no_docs(work_dir):
    """Create a Python file without docstrings."""
    path = work_dir / "no_docs.py"
    path.write_text(SAMPLE_PYTHON_NO_DOCSTRINGS)
    return path


@pytest.fixture
def sample_js_file(work_dir):
    """Create a sample JavaScript file."""
    path = work_dir / "sample.js"
    path.write_text(SAMPLE_JS_CODE)
    return path


@pytest.fixture
def sample_ts_file(work_dir):
    """Create a sample TypeScript file."""
    path = work_dir / "sample.ts"
    path.write_text(SAMPLE_TS_CODE)
    return path


@pytest.fixture
def python_project(work_dir):
    """Create a sample Python project structure."""
    # Create pyproject.toml
    pyproject = work_dir / "pyproject.toml"
    pyproject.write_text('''[project]
name = "test-project"
version = "1.0.0"
description = "A test project for documentation"
requires-python = ">=3.9"
dependencies = [
    "requests>=2.28.0",
    "pydantic>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "ruff>=0.1.0",
]
''')

    # Create source directory
    src_dir = work_dir / "src"
    src_dir.mkdir()

    # Create sample module
    module = src_dir / "main.py"
    module.write_text(SAMPLE_PYTHON_CODE)

    # Create tests directory
    tests_dir = work_dir / "tests"
    tests_dir.mkdir()

    # Create LICENSE
    license_file = work_dir / "LICENSE"
    license_file.write_text("MIT License\n\nCopyright (c) 2024")

    return work_dir


@pytest.fixture
def node_project(work_dir):
    """Create a sample Node.js project structure."""
    package_json = work_dir / "package.json"
    package_json.write_text(json.dumps({
        "name": "test-node-project",
        "version": "2.0.0",
        "description": "A test Node.js project",
        "author": "Test Author",
        "license": "MIT",
        "dependencies": {
            "express": "^4.18.0",
            "lodash": "^4.17.0"
        },
        "devDependencies": {
            "jest": "^29.0.0",
            "typescript": "^5.0.0"
        }
    }, indent=2))

    src_dir = work_dir / "src"
    src_dir.mkdir()

    module = src_dir / "index.js"
    module.write_text(SAMPLE_JS_CODE)

    return work_dir


@pytest.fixture
def git_project(work_dir):
    """Create a sample git project with commits."""
    import subprocess

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=work_dir, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=work_dir,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=work_dir,
        capture_output=True,
    )

    # Create and commit files
    (work_dir / "file1.py").write_text("# Initial file")
    subprocess.run(["git", "add", "."], cwd=work_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: initial commit"],
        cwd=work_dir,
        capture_output=True,
    )

    (work_dir / "file2.py").write_text("# Second file")
    subprocess.run(["git", "add", "."], cwd=work_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fix(api): fix bug in API"],
        cwd=work_dir,
        capture_output=True,
    )

    (work_dir / "file3.py").write_text("# Third file")
    subprocess.run(["git", "add", "."], cwd=work_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "docs: update documentation"],
        cwd=work_dir,
        capture_output=True,
    )

    return work_dir


# Fixtures for tools
@pytest.fixture
def docstrings_tool(work_dir):
    return GenerateDocstringsTool(work_dir=work_dir)


@pytest.fixture
def readme_tool(work_dir):
    return GenerateReadmeTool(work_dir=work_dir)


@pytest.fixture
def api_docs_tool(work_dir):
    return GenerateApiDocsTool(work_dir=work_dir)


@pytest.fixture
def explain_tool(work_dir):
    return ExplainCodeTool(work_dir=work_dir)


@pytest.fixture
def changelog_tool(work_dir):
    return GenerateChangelogTool(work_dir=work_dir)


# ============================================================================
# GenerateDocstringsTool Tests
# ============================================================================


class TestGenerateDocstringsTool:
    """Tests for GenerateDocstringsTool."""

    def test_tool_metadata(self, docstrings_tool):
        """Test tool has correct metadata."""
        assert docstrings_tool.name == "generate_docstrings"
        assert "docstrings" in docstrings_tool.description.lower()
        assert "source_file" in docstrings_tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_file_not_found(self, docstrings_tool):
        """Test error when file doesn't exist."""
        result = await docstrings_tool.execute(source_file="nonexistent.py")
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_unsupported_file_type(self, docstrings_tool, work_dir):
        """Test error for unsupported file types."""
        txt_file = work_dir / "test.txt"
        txt_file.write_text("Some text")

        result = await docstrings_tool.execute(source_file=str(txt_file))
        assert not result.success
        assert "unsupported" in result.error.lower()

    @pytest.mark.asyncio
    async def test_generate_docstrings_dry_run(
        self, docstrings_tool, sample_python_no_docs
    ):
        """Test dry run mode doesn't write file."""
        original_content = sample_python_no_docs.read_text()

        result = await docstrings_tool.execute(
            source_file=str(sample_python_no_docs), dry_run=True
        )

        assert result.success
        assert "Preview" in result.output
        assert result.metadata["dry_run"] is True
        # File should be unchanged
        assert sample_python_no_docs.read_text() == original_content

    @pytest.mark.asyncio
    async def test_generate_docstrings_google_style(
        self, docstrings_tool, sample_python_no_docs
    ):
        """Test generating Google-style docstrings."""
        result = await docstrings_tool.execute(
            source_file=str(sample_python_no_docs), style="google", dry_run=True
        )

        assert result.success
        assert result.metadata["style"] == "google"
        assert "Args:" in result.output or result.metadata["changes"] >= 0

    @pytest.mark.asyncio
    async def test_generate_docstrings_numpy_style(
        self, docstrings_tool, sample_python_no_docs
    ):
        """Test generating NumPy-style docstrings."""
        result = await docstrings_tool.execute(
            source_file=str(sample_python_no_docs), style="numpy", dry_run=True
        )

        assert result.success
        assert result.metadata["style"] == "numpy"

    @pytest.mark.asyncio
    async def test_generate_docstrings_sphinx_style(
        self, docstrings_tool, sample_python_no_docs
    ):
        """Test generating Sphinx-style docstrings."""
        result = await docstrings_tool.execute(
            source_file=str(sample_python_no_docs), style="sphinx", dry_run=True
        )

        assert result.success
        assert result.metadata["style"] == "sphinx"

    @pytest.mark.asyncio
    async def test_generate_docstrings_specific_target(
        self, docstrings_tool, sample_python_no_docs
    ):
        """Test generating docstring for specific function."""
        result = await docstrings_tool.execute(
            source_file=str(sample_python_no_docs),
            target="calculate_sum",
            dry_run=True,
        )

        assert result.success
        assert result.metadata["changes"] >= 0

    @pytest.mark.asyncio
    async def test_generate_docstrings_target_not_found(
        self, docstrings_tool, sample_python_no_docs
    ):
        """Test error when target doesn't exist."""
        result = await docstrings_tool.execute(
            source_file=str(sample_python_no_docs), target="nonexistent_function"
        )

        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_skip_existing_docstrings(self, docstrings_tool, sample_python_file):
        """Test that existing docstrings are skipped by default."""
        result = await docstrings_tool.execute(
            source_file=str(sample_python_file), dry_run=True
        )

        assert result.success
        # add_numbers has a docstring, should be skipped
        # process_data doesn't, should be added


class TestGenerateReadmeTool:
    """Tests for GenerateReadmeTool."""

    def test_tool_metadata(self, readme_tool):
        """Test tool has correct metadata."""
        assert readme_tool.name == "generate_readme"
        assert "readme" in readme_tool.description.lower()
        assert "project_path" in readme_tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_project_not_found(self, readme_tool):
        """Test error when project doesn't exist."""
        result = await readme_tool.execute(project_path="/nonexistent/path")
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_not_a_directory(self, readme_tool, work_dir):
        """Test error when path is not a directory."""
        file_path = work_dir / "file.txt"
        file_path.write_text("content")

        result = await readme_tool.execute(project_path=str(file_path))
        assert not result.success
        assert "not a directory" in result.error.lower()

    @pytest.mark.asyncio
    async def test_generate_readme_python_project(self, readme_tool, python_project):
        """Test README generation for Python project."""
        result = await readme_tool.execute(
            project_path=str(python_project), dry_run=True
        )

        assert result.success
        assert result.metadata["project_type"] == "python"
        assert result.metadata["project_name"] == "test-project"
        assert "pip install" in result.output
        assert result.metadata["dry_run"] is True

    @pytest.mark.asyncio
    async def test_generate_readme_node_project(self, readme_tool, node_project):
        """Test README generation for Node.js project."""
        result = await readme_tool.execute(
            project_path=str(node_project), dry_run=True
        )

        assert result.success
        assert result.metadata["project_type"] == "node"
        assert result.metadata["project_name"] == "test-node-project"
        assert "npm install" in result.output

    @pytest.mark.asyncio
    async def test_generate_readme_writes_file(self, readme_tool, python_project):
        """Test README generation writes to file."""
        result = await readme_tool.execute(
            project_path=str(python_project), dry_run=False
        )

        assert result.success
        readme_path = python_project / "README.md"
        assert readme_path.exists()
        content = readme_path.read_text()
        assert "test-project" in content

    @pytest.mark.asyncio
    async def test_generate_readme_custom_output(self, readme_tool, python_project):
        """Test README generation with custom output path."""
        custom_path = python_project / "docs" / "README.md"

        result = await readme_tool.execute(
            project_path=str(python_project),
            output=str(custom_path),
            dry_run=False,
        )

        assert result.success
        assert custom_path.exists()


class TestGenerateApiDocsTool:
    """Tests for GenerateApiDocsTool."""

    def test_tool_metadata(self, api_docs_tool):
        """Test tool has correct metadata."""
        assert api_docs_tool.name == "generate_api_docs"
        assert "api" in api_docs_tool.description.lower()
        assert "source_path" in api_docs_tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_source_not_found(self, api_docs_tool):
        """Test error when source doesn't exist."""
        result = await api_docs_tool.execute(source_path="/nonexistent/path")
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_generate_api_docs_single_file(
        self, api_docs_tool, sample_python_file
    ):
        """Test API docs generation for single file."""
        result = await api_docs_tool.execute(
            source_path=str(sample_python_file), dry_run=True
        )

        assert result.success
        assert result.metadata["modules"] >= 1
        assert "Preview" in result.output

    @pytest.mark.asyncio
    async def test_generate_api_docs_directory(self, api_docs_tool, python_project):
        """Test API docs generation for directory."""
        src_dir = python_project / "src"

        result = await api_docs_tool.execute(
            source_path=str(src_dir), recursive=True, dry_run=True
        )

        assert result.success
        assert result.metadata["modules"] >= 1

    @pytest.mark.asyncio
    async def test_generate_api_docs_markdown_format(
        self, api_docs_tool, sample_python_file
    ):
        """Test Markdown output format."""
        result = await api_docs_tool.execute(
            source_path=str(sample_python_file), format="markdown", dry_run=True
        )

        assert result.success
        assert result.metadata["format"] == "markdown"
        assert "#" in result.output  # Markdown headers

    @pytest.mark.asyncio
    async def test_generate_api_docs_rst_format(
        self, api_docs_tool, sample_python_file
    ):
        """Test reStructuredText output format."""
        result = await api_docs_tool.execute(
            source_path=str(sample_python_file), format="rst", dry_run=True
        )

        assert result.success
        assert result.metadata["format"] == "rst"

    @pytest.mark.asyncio
    async def test_generate_api_docs_html_format(
        self, api_docs_tool, sample_python_file
    ):
        """Test HTML output format."""
        result = await api_docs_tool.execute(
            source_path=str(sample_python_file), format="html", dry_run=True
        )

        assert result.success
        assert result.metadata["format"] == "html"
        assert "<html>" in result.output

    @pytest.mark.asyncio
    async def test_generate_api_docs_exclude_private(
        self, api_docs_tool, work_dir
    ):
        """Test excluding private members."""
        code = '''def public_func():
    pass

def _private_func():
    pass

class PublicClass:
    pass

class _PrivateClass:
    pass
'''
        path = work_dir / "module.py"
        path.write_text(code)

        result = await api_docs_tool.execute(
            source_path=str(path), include_private=False, dry_run=True
        )

        assert result.success
        # Should only include public members


class TestExplainCodeTool:
    """Tests for ExplainCodeTool."""

    def test_tool_metadata(self, explain_tool):
        """Test tool has correct metadata."""
        assert explain_tool.name == "explain_code"
        assert "explain" in explain_tool.description.lower()
        assert "source_file" in explain_tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_file_not_found(self, explain_tool):
        """Test error when file doesn't exist."""
        result = await explain_tool.execute(source_file="nonexistent.py")
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_unsupported_file_type(self, explain_tool, work_dir):
        """Test error for unsupported file types."""
        txt_file = work_dir / "test.txt"
        txt_file.write_text("Some text")

        result = await explain_tool.execute(source_file=str(txt_file))
        assert not result.success
        assert "unsupported" in result.error.lower()

    @pytest.mark.asyncio
    async def test_explain_code_basic(self, explain_tool, sample_python_file):
        """Test basic code explanation."""
        result = await explain_tool.execute(source_file=str(sample_python_file))

        assert result.success
        assert result.metadata["functions"] >= 1
        assert result.metadata["classes"] >= 1

    @pytest.mark.asyncio
    async def test_explain_specific_function(self, explain_tool, sample_python_file):
        """Test explaining specific function."""
        result = await explain_tool.execute(
            source_file=str(sample_python_file), target="add_numbers"
        )

        assert result.success
        assert "add_numbers" in result.output

    @pytest.mark.asyncio
    async def test_explain_specific_class(self, explain_tool, sample_python_file):
        """Test explaining specific class."""
        result = await explain_tool.execute(
            source_file=str(sample_python_file), target="DataProcessor"
        )

        assert result.success
        assert "DataProcessor" in result.output

    @pytest.mark.asyncio
    async def test_explain_target_not_found(self, explain_tool, sample_python_file):
        """Test error when target doesn't exist."""
        result = await explain_tool.execute(
            source_file=str(sample_python_file), target="nonexistent"
        )

        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_explain_detail_levels(self, explain_tool, sample_python_file):
        """Test different detail levels."""
        for level in ["brief", "standard", "detailed"]:
            result = await explain_tool.execute(
                source_file=str(sample_python_file), detail_level=level
            )
            assert result.success
            assert result.metadata["detail_level"] == level

    @pytest.mark.asyncio
    async def test_explain_markdown_format(self, explain_tool, sample_python_file):
        """Test Markdown output format."""
        result = await explain_tool.execute(
            source_file=str(sample_python_file), format="markdown"
        )

        assert result.success
        assert "#" in result.output  # Markdown headers

    @pytest.mark.asyncio
    async def test_explain_text_format(self, explain_tool, sample_python_file):
        """Test plain text output format."""
        result = await explain_tool.execute(
            source_file=str(sample_python_file), format="text"
        )

        assert result.success
        assert "=" in result.output  # Text separators


class TestGenerateChangelogTool:
    """Tests for GenerateChangelogTool."""

    def test_tool_metadata(self, changelog_tool):
        """Test tool has correct metadata."""
        assert changelog_tool.name == "generate_changelog"
        assert "changelog" in changelog_tool.description.lower()
        assert "project_path" in changelog_tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_project_not_found(self, changelog_tool):
        """Test error when project doesn't exist."""
        result = await changelog_tool.execute(project_path="/nonexistent/path")
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_not_git_repo(self, changelog_tool, work_dir):
        """Test error when not a git repository."""
        result = await changelog_tool.execute(project_path=str(work_dir))
        assert not result.success
        assert "git" in result.error.lower()

    @pytest.mark.asyncio
    async def test_generate_changelog_basic(self, changelog_tool, git_project):
        """Test basic changelog generation."""
        result = await changelog_tool.execute(
            project_path=str(git_project), dry_run=True
        )

        assert result.success
        assert result.metadata["commits"] >= 1
        assert "Changelog" in result.output

    @pytest.mark.asyncio
    async def test_generate_changelog_with_version(self, changelog_tool, git_project):
        """Test changelog with custom version."""
        result = await changelog_tool.execute(
            project_path=str(git_project), version="1.0.0", dry_run=True
        )

        assert result.success
        assert "1.0.0" in result.output

    @pytest.mark.asyncio
    async def test_generate_changelog_writes_file(self, changelog_tool, git_project):
        """Test changelog generation writes to file."""
        result = await changelog_tool.execute(
            project_path=str(git_project), dry_run=False
        )

        assert result.success
        changelog_path = git_project / "CHANGELOG.md"
        assert changelog_path.exists()


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_detect_docstring_style_google(self):
        """Test detecting Google-style docstrings."""
        code = '''def func():
    """Summary.

    Args:
        x: Description.

    Returns:
        Result.
    """
    pass
'''
        assert _detect_docstring_style(code) == DocstringStyle.GOOGLE

    def test_detect_docstring_style_numpy(self):
        """Test detecting NumPy-style docstrings."""
        code = '''def func():
    """Summary.

    Parameters
    ----------
    x : int
        Description.

    Returns
    -------
    int
        Result.
    """
    pass
'''
        assert _detect_docstring_style(code) == DocstringStyle.NUMPY

    def test_detect_docstring_style_sphinx(self):
        """Test detecting Sphinx-style docstrings."""
        code = '''def func():
    """Summary.

    :param x: Description.
    :type x: int
    :returns: Result.
    :rtype: int
    """
    pass
'''
        assert _detect_docstring_style(code) == DocstringStyle.SPHINX

    def test_detect_docstring_style_default(self):
        """Test default style when no docstrings."""
        code = "def func(): pass"
        assert _detect_docstring_style(code) == DocstringStyle.GOOGLE

    def test_parse_params_string_simple(self):
        """Test parsing simple parameter string."""
        params = _parse_params_string("a, b, c")
        assert len(params) == 3
        assert params[0].name == "a"
        assert params[1].name == "b"
        assert params[2].name == "c"

    def test_parse_params_string_with_types(self):
        """Test parsing parameters with type hints."""
        params = _parse_params_string("a: int, b: str, c: list")
        assert len(params) == 3
        assert params[0].type_hint == "int"
        assert params[1].type_hint == "str"
        assert params[2].type_hint == "list"

    def test_parse_params_string_with_defaults(self):
        """Test parsing parameters with defaults."""
        params = _parse_params_string("a=1, b='test', c=None")
        assert len(params) == 3
        assert params[0].default == "1"
        assert params[1].default == "'test'"
        assert params[2].default == "None"

    def test_parse_params_string_skip_self_cls(self):
        """Test skipping self and cls parameters."""
        params = _parse_params_string("self, a, b")
        assert len(params) == 2
        assert params[0].name == "a"

        params = _parse_params_string("cls, a")
        assert len(params) == 1
        assert params[0].name == "a"

    def test_parse_params_string_empty(self):
        """Test parsing empty parameter string."""
        params = _parse_params_string("")
        assert len(params) == 0

    def test_parse_conventional_commit_feat(self):
        """Test parsing feat commit."""
        commit_type, scope, breaking = _parse_conventional_commit(
            "feat: add new feature"
        )
        assert commit_type == "feat"
        assert scope == ""
        assert not breaking

    def test_parse_conventional_commit_with_scope(self):
        """Test parsing commit with scope."""
        commit_type, scope, breaking = _parse_conventional_commit(
            "fix(api): fix bug"
        )
        assert commit_type == "fix"
        assert scope == "api"
        assert not breaking

    def test_parse_conventional_commit_breaking(self):
        """Test parsing breaking change commit."""
        commit_type, scope, breaking = _parse_conventional_commit(
            "feat!: breaking change"
        )
        assert commit_type == "feat"
        assert breaking

    def test_parse_conventional_commit_breaking_with_scope(self):
        """Test parsing breaking change with scope."""
        commit_type, scope, breaking = _parse_conventional_commit(
            "refactor(core)!: major refactor"
        )
        assert commit_type == "refactor"
        assert scope == "core"
        assert breaking

    def test_parse_conventional_commit_non_conventional(self):
        """Test parsing non-conventional commit."""
        commit_type, scope, breaking = _parse_conventional_commit(
            "Just a regular commit message"
        )
        assert commit_type == ""
        assert scope == ""
        assert not breaking


class TestProjectInfoDetection:
    """Tests for project info detection."""

    @pytest.mark.asyncio
    async def test_detect_python_project(self, python_project):
        """Test detecting Python project info."""
        info = await _detect_project_info(python_project)

        assert info.project_type == "python"
        assert info.name == "test-project"
        assert info.version == "1.0.0"
        assert info.description == "A test project for documentation"
        assert "requests" in str(info.dependencies)
        assert info.has_tests

    @pytest.mark.asyncio
    async def test_detect_node_project(self, node_project):
        """Test detecting Node.js project info."""
        info = await _detect_project_info(node_project)

        assert info.project_type == "node"
        assert info.name == "test-node-project"
        assert info.version == "2.0.0"
        assert info.license == "MIT"

    @pytest.mark.asyncio
    async def test_detect_license(self, python_project):
        """Test detecting license from LICENSE file."""
        info = await _detect_project_info(python_project)
        assert info.license == "MIT"

    @pytest.mark.asyncio
    async def test_fallback_to_directory_name(self, work_dir):
        """Test fallback to directory name when no config."""
        info = await _detect_project_info(work_dir)
        # Should use directory name as project name
        assert info.name == work_dir.name


class TestReadmeGeneration:
    """Tests for README generation."""

    def test_generate_readme_basic(self):
        """Test basic README generation."""
        info = ProjectInfo(
            name="test-project",
            description="A test project",
            version="1.0.0",
            project_type="python",
        )

        readme = _generate_readme(info)

        assert "# test-project" in readme
        assert "A test project" in readme
        assert "pip install" in readme

    def test_generate_readme_with_dependencies(self):
        """Test README with dependencies."""
        info = ProjectInfo(
            name="test-project",
            project_type="python",
            dependencies=["requests", "pydantic", "click"],
        )

        readme = _generate_readme(info)

        assert "Dependencies" in readme
        assert "requests" in readme

    def test_generate_readme_node_project(self):
        """Test README for Node.js project."""
        info = ProjectInfo(
            name="test-node",
            project_type="node",
            version="2.0.0",
        )

        readme = _generate_readme(info)

        assert "npm install" in readme


class TestChangelogGeneration:
    """Tests for changelog generation."""

    def test_generate_changelog_basic(self):
        """Test basic changelog generation."""
        from datetime import datetime

        commits = [
            CommitInfo(
                hash="abc123",
                short_hash="abc",
                message="feat: add feature",
                body="",
                author="Test",
                date=datetime.now(),
                commit_type="feat",
            ),
            CommitInfo(
                hash="def456",
                short_hash="def",
                message="fix: fix bug",
                body="",
                author="Test",
                date=datetime.now(),
                commit_type="fix",
            ),
        ]

        changelog = _generate_changelog(commits)

        assert "# Changelog" in changelog
        assert "### Added" in changelog
        assert "### Fixed" in changelog

    def test_generate_changelog_with_version(self):
        """Test changelog with version."""
        from datetime import datetime as dt

        commits = [
            CommitInfo(
                hash="abc123",
                short_hash="abc",
                message="feat: feature",
                body="",
                author="Test",
                date=dt.now(),
                commit_type="feat",
            ),
        ]

        changelog = _generate_changelog(commits, version="1.0.0")

        assert "[1.0.0]" in changelog

    def test_generate_changelog_grouping(self):
        """Test changelog groups commits by type."""
        from datetime import datetime

        commits = [
            CommitInfo(
                hash="1", short_hash="1", message="feat: f1", body="",
                author="Test", date=datetime.now(), commit_type="feat"
            ),
            CommitInfo(
                hash="2", short_hash="2", message="feat: f2", body="",
                author="Test", date=datetime.now(), commit_type="feat"
            ),
            CommitInfo(
                hash="3", short_hash="3", message="fix: b1", body="",
                author="Test", date=datetime.now(), commit_type="fix"
            ),
        ]

        changelog = _generate_changelog(commits)

        # Features should be grouped together
        added_section = changelog.split("### Added")[1].split("###")[0]
        assert "f1" in added_section
        assert "f2" in added_section


# ============================================================================
# Agent Integration Tests
# ============================================================================


class TestAgentIntegration:
    """Tests for agent integration."""

    def test_tools_registered_in_registry(self):
        """Test that documentation tools are registered."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()

        # Check all documentation tools are registered
        assert registry.get_tool("generate_docstrings") is not None
        assert registry.get_tool("generate_readme") is not None
        assert registry.get_tool("generate_api_docs") is not None
        assert registry.get_tool("explain_code") is not None
        assert registry.get_tool("generate_changelog") is not None

    def test_idunn_agent_has_documentation_tools(self):
        """Test that Idunn agent has documentation tools."""
        from sindri.agents.registry import AGENTS

        idunn = AGENTS.get("idunn")
        assert idunn is not None

        # Check all documentation tools are assigned
        assert "generate_docstrings" in idunn.tools
        assert "generate_readme" in idunn.tools
        assert "generate_api_docs" in idunn.tools
        assert "explain_code" in idunn.tools
        assert "generate_changelog" in idunn.tools

    def test_idunn_has_original_tools(self):
        """Test that Idunn still has original tools."""
        from sindri.agents.registry import AGENTS

        idunn = AGENTS.get("idunn")

        # Original tools should still be present
        assert "read_file" in idunn.tools
        assert "write_file" in idunn.tools
        assert "edit_file" in idunn.tools
        assert "search_code" in idunn.tools
        assert "list_directory" in idunn.tools
        assert "read_tree" in idunn.tools
