"""Tests for formatting tools (format_code and lint_code)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from sindri.tools.formatting import FormatCodeTool, LintCodeTool


class TestFormatCodeTool:
    """Tests for FormatCodeTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a FormatCodeTool instance."""
        return FormatCodeTool(work_dir=tmp_path)

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "format_code"
        assert "Format code" in tool.description
        schema = tool.get_schema()
        assert schema["function"]["name"] == "format_code"

    def test_parameters_schema(self, tool):
        """Test tool parameters schema is correct."""
        params = tool.parameters
        assert "path" in params["properties"]
        assert "code" in params["properties"]
        assert "language" in params["properties"]
        assert "formatter" in params["properties"]
        assert "check_only" in params["properties"]
        assert "line_length" in params["properties"]
        assert "indent_size" in params["properties"]

    def test_extension_mapping(self, tool):
        """Test file extension to language mapping."""
        assert tool.EXTENSION_MAP[".py"] == "python"
        assert tool.EXTENSION_MAP[".js"] == "javascript"
        assert tool.EXTENSION_MAP[".ts"] == "typescript"
        assert tool.EXTENSION_MAP[".rs"] == "rust"
        assert tool.EXTENSION_MAP[".go"] == "go"
        assert tool.EXTENSION_MAP[".json"] == "json"
        assert tool.EXTENSION_MAP[".yaml"] == "yaml"
        assert tool.EXTENSION_MAP[".css"] == "css"
        assert tool.EXTENSION_MAP[".html"] == "html"
        assert tool.EXTENSION_MAP[".md"] == "markdown"

    def test_default_formatters(self, tool):
        """Test default formatter selection per language."""
        assert tool.DEFAULT_FORMATTERS["python"] == "black"
        assert tool.DEFAULT_FORMATTERS["javascript"] == "prettier"
        assert tool.DEFAULT_FORMATTERS["typescript"] == "prettier"
        assert tool.DEFAULT_FORMATTERS["rust"] == "rustfmt"
        assert tool.DEFAULT_FORMATTERS["go"] == "gofmt"
        assert tool.DEFAULT_FORMATTERS["json"] == "json"

    @pytest.mark.asyncio
    async def test_both_path_and_code_error(self, tool, tmp_path):
        """Test error when both path and code specified."""
        result = await tool.execute(path="file.py", code="x = 1")
        assert not result.success
        assert "Cannot specify both" in result.error

    @pytest.mark.asyncio
    async def test_neither_path_nor_code_error(self, tool):
        """Test error when neither path nor code specified."""
        result = await tool.execute()
        assert not result.success
        assert "Must specify either" in result.error

    @pytest.mark.asyncio
    async def test_inline_code_requires_language(self, tool):
        """Test that inline code requires language parameter."""
        result = await tool.execute(code="x = 1")
        assert not result.success
        assert "Must specify 'language'" in result.error

    @pytest.mark.asyncio
    async def test_path_not_exists(self, tool, tmp_path):
        """Test error when path doesn't exist."""
        result = await tool.execute(path="nonexistent.py")
        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_unknown_extension(self, tool, tmp_path):
        """Test error for unknown file extension."""
        unknown_file = tmp_path / "file.xyz"
        unknown_file.write_text("content")

        result = await tool.execute(path="file.xyz")
        assert not result.success
        assert "Could not detect language" in result.error

    @pytest.mark.asyncio
    async def test_directory_requires_language(self, tool, tmp_path):
        """Test that directory formatting requires language parameter."""
        result = await tool.execute(path=".")
        assert not result.success
        assert "specify 'language'" in result.error

    @pytest.mark.asyncio
    async def test_format_json_inline(self, tool):
        """Test inline JSON formatting."""
        code = '{"b":1,"a":2}'
        result = await tool.execute(code=code, language="json")

        assert result.success
        assert result.metadata["formatter"] == "json"
        # Check output is formatted
        formatted = json.loads(result.output)
        assert formatted == {"b": 1, "a": 2}

    @pytest.mark.asyncio
    async def test_format_json_file(self, tool, tmp_path):
        """Test JSON file formatting."""
        json_file = tmp_path / "data.json"
        json_file.write_text('{"b":1,"a":2}')

        result = await tool.execute(path="data.json")

        assert result.success
        # Check file was formatted
        content = json_file.read_text()
        assert "{\n" in content  # Indented

    @pytest.mark.asyncio
    async def test_format_json_check_only(self, tool, tmp_path):
        """Test JSON check-only mode."""
        json_file = tmp_path / "data.json"
        json_file.write_text('{"a":1}')  # Not formatted

        result = await tool.execute(path="data.json", check_only=True)

        # Should indicate needs formatting
        assert result.metadata.get("needs_formatting") is True or not result.success

    @pytest.mark.asyncio
    async def test_format_json_invalid(self, tool, tmp_path):
        """Test error for invalid JSON."""
        json_file = tmp_path / "invalid.json"
        json_file.write_text('{"a": }')

        result = await tool.execute(path="invalid.json")
        assert not result.success
        assert "Invalid JSON" in result.error

    @pytest.mark.asyncio
    async def test_format_python_black(self, tool, tmp_path):
        """Test Python formatting with black."""
        py_file = tmp_path / "code.py"
        py_file.write_text("x=1")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.py", formatter="black")

            assert result.success
            assert result.metadata["formatter"] == "black"

    @pytest.mark.asyncio
    async def test_format_python_ruff(self, tool, tmp_path):
        """Test Python formatting with ruff."""
        py_file = tmp_path / "code.py"
        py_file.write_text("x=1")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.py", formatter="ruff")

            assert result.success
            assert result.metadata["formatter"] == "ruff"

    @pytest.mark.asyncio
    async def test_format_javascript_prettier(self, tool, tmp_path):
        """Test JavaScript formatting with prettier."""
        js_file = tmp_path / "code.js"
        js_file.write_text("const x=1")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.js")

            assert result.success
            assert result.metadata["formatter"] == "prettier"

    @pytest.mark.asyncio
    async def test_format_typescript_prettier(self, tool, tmp_path):
        """Test TypeScript formatting with prettier."""
        ts_file = tmp_path / "code.ts"
        ts_file.write_text("const x: number=1")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.ts")

            assert result.success
            assert result.metadata["formatter"] == "prettier"

    @pytest.mark.asyncio
    async def test_format_rust_rustfmt(self, tool, tmp_path):
        """Test Rust formatting with rustfmt."""
        rs_file = tmp_path / "code.rs"
        rs_file.write_text("fn main(){}")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.rs")

            assert result.success
            assert result.metadata["formatter"] == "rustfmt"

    @pytest.mark.asyncio
    async def test_format_go_gofmt(self, tool, tmp_path):
        """Test Go formatting with gofmt."""
        go_file = tmp_path / "code.go"
        go_file.write_text("package main\nfunc main(){}")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.go")

            assert result.success
            assert result.metadata["formatter"] == "gofmt"

    @pytest.mark.asyncio
    async def test_format_with_line_length(self, tool, tmp_path):
        """Test formatting with custom line length."""
        py_file = tmp_path / "code.py"
        py_file.write_text("x = 1")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.py", line_length=120)

            # Check that line-length was passed
            call_args = mock_proc.call_args[0][0]
            assert "--line-length" in call_args or "120" in call_args

    @pytest.mark.asyncio
    async def test_format_check_only_success(self, tool, tmp_path):
        """Test check-only mode when file is formatted."""
        py_file = tmp_path / "code.py"
        py_file.write_text("x = 1\n")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0  # 0 = properly formatted
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.py", check_only=True)

            assert result.success
            assert result.metadata.get("needs_formatting") is False

    @pytest.mark.asyncio
    async def test_format_check_only_needs_formatting(self, tool, tmp_path):
        """Test check-only mode when file needs formatting."""
        py_file = tmp_path / "code.py"
        py_file.write_text("x=1")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"would reformat code.py", b"")
            mock_process.returncode = 1  # 1 = needs formatting
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.py", check_only=True)

            assert not result.success
            assert result.metadata.get("needs_formatting") is True

    @pytest.mark.asyncio
    async def test_unknown_formatter(self, tool, tmp_path):
        """Test error for unknown formatter."""
        py_file = tmp_path / "code.py"
        py_file.write_text("x = 1")

        result = await tool.execute(path="code.py", formatter="unknown_formatter")
        assert not result.success
        assert "Unknown formatter" in result.error


class TestLintCodeTool:
    """Tests for LintCodeTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a LintCodeTool instance."""
        return LintCodeTool(work_dir=tmp_path)

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "lint_code"
        assert "lint" in tool.description.lower()
        schema = tool.get_schema()
        assert schema["function"]["name"] == "lint_code"

    def test_parameters_schema(self, tool):
        """Test tool parameters schema is correct."""
        params = tool.parameters
        assert "path" in params["properties"]
        assert "language" in params["properties"]
        assert "linter" in params["properties"]
        assert "fix" in params["properties"]
        assert params["required"] == ["path"]

    def test_extension_mapping(self, tool):
        """Test file extension to language mapping."""
        assert tool.EXTENSION_MAP[".py"] == "python"
        assert tool.EXTENSION_MAP[".js"] == "javascript"
        assert tool.EXTENSION_MAP[".ts"] == "typescript"
        assert tool.EXTENSION_MAP[".rs"] == "rust"
        assert tool.EXTENSION_MAP[".go"] == "go"

    def test_default_linters(self, tool):
        """Test default linter selection per language."""
        assert tool.DEFAULT_LINTERS["python"] == "ruff"
        assert tool.DEFAULT_LINTERS["javascript"] == "eslint"
        assert tool.DEFAULT_LINTERS["typescript"] == "eslint"
        assert tool.DEFAULT_LINTERS["rust"] == "clippy"
        assert tool.DEFAULT_LINTERS["go"] == "staticcheck"

    @pytest.mark.asyncio
    async def test_path_not_exists(self, tool, tmp_path):
        """Test error when path doesn't exist."""
        result = await tool.execute(path="nonexistent.py")
        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_unknown_extension(self, tool, tmp_path):
        """Test error for unknown file extension."""
        unknown_file = tmp_path / "file.xyz"
        unknown_file.write_text("content")

        result = await tool.execute(path="file.xyz")
        assert not result.success
        assert "Could not detect language" in result.error

    @pytest.mark.asyncio
    async def test_directory_requires_language(self, tool, tmp_path):
        """Test that directory linting requires language parameter."""
        result = await tool.execute(path=".")
        assert not result.success
        assert "specify 'language'" in result.error

    @pytest.mark.asyncio
    async def test_lint_python_ruff(self, tool, tmp_path):
        """Test Python linting with ruff."""
        py_file = tmp_path / "code.py"
        py_file.write_text("import os\nx = 1")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.py")

            assert result.success
            assert result.metadata["linter"] == "ruff"

    @pytest.mark.asyncio
    async def test_lint_python_flake8(self, tool, tmp_path):
        """Test Python linting with flake8."""
        py_file = tmp_path / "code.py"
        py_file.write_text("import os\nx = 1")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.py", linter="flake8")

            assert result.success
            assert result.metadata["linter"] == "flake8"

    @pytest.mark.asyncio
    async def test_lint_python_pylint(self, tool, tmp_path):
        """Test Python linting with pylint."""
        py_file = tmp_path / "code.py"
        py_file.write_text("x = 1")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (
                b"Your code has been rated at 10.00/10",
                b""
            )
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.py", linter="pylint")

            assert result.success
            assert result.metadata["linter"] == "pylint"

    @pytest.mark.asyncio
    async def test_lint_python_mypy(self, tool, tmp_path):
        """Test Python type checking with mypy."""
        py_file = tmp_path / "code.py"
        py_file.write_text("x: int = 1")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"Success: no issues found", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.py", linter="mypy")

            assert result.success
            assert result.metadata["linter"] == "mypy"

    @pytest.mark.asyncio
    async def test_lint_javascript_eslint(self, tool, tmp_path):
        """Test JavaScript linting with eslint."""
        js_file = tmp_path / "code.js"
        js_file.write_text("const x = 1;")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.js")

            assert result.success
            assert result.metadata["linter"] == "eslint"

    @pytest.mark.asyncio
    async def test_lint_with_fix(self, tool, tmp_path):
        """Test linting with auto-fix enabled."""
        py_file = tmp_path / "code.py"
        py_file.write_text("import os\nx = 1")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.py", fix=True)

            # Check that --fix was passed
            call_args = mock_proc.call_args[0][0]
            assert "--fix" in call_args

    @pytest.mark.asyncio
    async def test_lint_issues_found(self, tool, tmp_path):
        """Test linting when issues are found."""
        py_file = tmp_path / "code.py"
        py_file.write_text("import os\nx = 1")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (
                b"code.py:1:1: F401 `os` imported but unused",
                b""
            )
            mock_process.returncode = 1
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.py")

            assert not result.success
            assert result.metadata["total"] > 0

    @pytest.mark.asyncio
    async def test_lint_rust_clippy(self, tool, tmp_path):
        """Test Rust linting with clippy."""
        rs_file = tmp_path / "code.rs"
        rs_file.write_text("fn main() {}")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.rs")

            assert result.success
            assert result.metadata["linter"] == "clippy"

    @pytest.mark.asyncio
    async def test_lint_go_staticcheck(self, tool, tmp_path):
        """Test Go linting with staticcheck."""
        go_file = tmp_path / "code.go"
        go_file.write_text("package main")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="code.go")

            assert result.success
            assert result.metadata["linter"] == "staticcheck"

    def test_parse_ruff_output(self, tool):
        """Test parsing ruff output."""
        output = """code.py:1:1: F401 [*] `os` imported but unused
code.py:2:5: E501 Line too long"""
        issues = tool._parse_lint_output(output, "ruff")
        assert issues["total"] == 2

    def test_parse_flake8_output(self, tool):
        """Test parsing flake8 output."""
        output = """code.py:1:1: F401 'os' imported but unused
code.py:2:80: E501 line too long (100 > 79 characters)"""
        issues = tool._parse_lint_output(output, "flake8")
        assert issues["total"] == 2

    def test_parse_pylint_output(self, tool):
        """Test parsing pylint output."""
        output = """C:  1, 0: Missing module docstring (missing-module-docstring)
W:  1, 0: Unused import os (unused-import)
Your code has been rated at 5.00/10"""
        issues = tool._parse_lint_output(output, "pylint")
        assert issues["total"] == 2
        assert issues.get("score") == 5.0

    def test_parse_eslint_output(self, tool):
        """Test parsing eslint output."""
        output = """
/path/code.js
  1:7  error  'x' is defined but never used  no-unused-vars

1 problem (1 error, 0 warnings)"""
        issues = tool._parse_lint_output(output, "eslint")
        assert issues["total"] == 1

    def test_parse_mypy_output(self, tool):
        """Test parsing mypy output."""
        output = """code.py:1: error: Incompatible types in assignment
code.py:2: error: Name 'x' is not defined
Found 2 errors in 1 file"""
        issues = tool._parse_lint_output(output, "mypy")
        assert issues["errors"] == 2
        assert issues["total"] == 2

    def test_parse_clippy_output(self, tool):
        """Test parsing clippy output."""
        output = """warning: unused variable: `x`
error[E0425]: cannot find value `y` in this scope
warning: 1 warning emitted"""
        issues = tool._parse_clippy_output(output)
        assert issues["warnings"] == 2  # "warning:" appears twice
        assert issues["errors"] == 1


class TestToolRegistration:
    """Test that formatting tools are properly registered."""

    def test_format_code_in_registry(self):
        """Test FormatCodeTool is in default registry."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()
        tool = registry.get_tool("format_code")

        assert tool is not None
        assert isinstance(tool, FormatCodeTool)

    def test_lint_code_in_registry(self):
        """Test LintCodeTool is in default registry."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()
        tool = registry.get_tool("lint_code")

        assert tool is not None
        assert isinstance(tool, LintCodeTool)


class TestAgentIntegration:
    """Test that formatting tools are available to appropriate agents."""

    def test_brokkr_has_formatting_tools(self):
        """Test Brokkr has format_code and lint_code."""
        from sindri.agents.registry import AGENTS

        brokkr = AGENTS["brokkr"]
        assert "format_code" in brokkr.tools
        assert "lint_code" in brokkr.tools

    def test_huginn_has_formatting_tools(self):
        """Test Huginn has format_code and lint_code."""
        from sindri.agents.registry import AGENTS

        huginn = AGENTS["huginn"]
        assert "format_code" in huginn.tools
        assert "lint_code" in huginn.tools

    def test_mimir_has_lint_code(self):
        """Test Mimir has lint_code for code review."""
        from sindri.agents.registry import AGENTS

        mimir = AGENTS["mimir"]
        assert "lint_code" in mimir.tools
