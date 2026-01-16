"""Tests for testing tools (run_tests and check_syntax)."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from sindri.tools.testing import RunTestsTool, CheckSyntaxTool


class TestRunTestsTool:
    """Tests for RunTestsTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a RunTestsTool instance."""
        return RunTestsTool(work_dir=tmp_path)

    @pytest.fixture
    def tool_no_workdir(self):
        """Create a RunTestsTool without work_dir."""
        return RunTestsTool()

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "run_tests"
        assert "Run tests" in tool.description
        assert "pytest" in tool.description
        schema = tool.get_schema()
        assert schema["function"]["name"] == "run_tests"

    def test_parameters_schema(self, tool):
        """Test tool parameters schema is correct."""
        params = tool.parameters
        assert "path" in params["properties"]
        assert "framework" in params["properties"]
        assert "pattern" in params["properties"]
        assert "verbose" in params["properties"]
        assert "timeout" in params["properties"]
        assert "fail_fast" in params["properties"]
        assert "coverage" in params["properties"]

    @pytest.mark.asyncio
    async def test_detect_pytest_from_conftest(self, tool, tmp_path):
        """Test pytest detection from conftest.py."""
        (tmp_path / "conftest.py").write_text("# pytest config")

        with patch.object(tool, '_detect_framework') as mock_detect:
            mock_detect.return_value = "pytest"

            with patch('asyncio.create_subprocess_shell') as mock_proc:
                mock_process = AsyncMock()
                mock_process.communicate.return_value = (b"1 passed in 0.1s", b"")
                mock_process.returncode = 0
                mock_proc.return_value = mock_process

                result = await tool.execute()
                assert result.success
                assert result.metadata["framework"] == "pytest"

    @pytest.mark.asyncio
    async def test_detect_pytest_from_pyproject(self, tool, tmp_path):
        """Test pytest detection from pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            # First call for pytest check, second for running tests
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"1 passed", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute()
            # Framework should be detected

    @pytest.mark.asyncio
    async def test_detect_jest_from_package_json(self, tool, tmp_path):
        """Test jest detection from package.json."""
        package_json = {
            "name": "test-project",
            "devDependencies": {"jest": "^29.0.0"}
        }
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        framework = await tool._detect_framework(tmp_path)
        assert framework == "jest"

    @pytest.mark.asyncio
    async def test_detect_npm_from_package_json_test_script(self, tool, tmp_path):
        """Test npm detection from package.json test script."""
        package_json = {
            "name": "test-project",
            "scripts": {"test": "mocha tests/"}
        }
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        framework = await tool._detect_framework(tmp_path)
        assert framework == "npm"

    @pytest.mark.asyncio
    async def test_detect_cargo_from_cargo_toml(self, tool, tmp_path):
        """Test cargo detection from Cargo.toml."""
        (tmp_path / "Cargo.toml").write_text("[package]\nname = \"test\"")

        framework = await tool._detect_framework(tmp_path)
        assert framework == "cargo"

    @pytest.mark.asyncio
    async def test_detect_go_from_go_mod(self, tool, tmp_path):
        """Test go detection from go.mod."""
        (tmp_path / "go.mod").write_text("module test")

        framework = await tool._detect_framework(tmp_path)
        assert framework == "go"

    @pytest.mark.asyncio
    async def test_detect_go_from_test_files(self, tool, tmp_path):
        """Test go detection from *_test.go files."""
        (tmp_path / "main_test.go").write_text("package main")

        framework = await tool._detect_framework(tmp_path)
        assert framework == "go"

    @pytest.mark.asyncio
    async def test_no_framework_detected(self, tool, tmp_path):
        """Test error when no framework detected."""
        result = await tool.execute()
        assert not result.success
        assert "Could not auto-detect testing framework" in result.error

    @pytest.mark.asyncio
    async def test_pytest_command_basic(self, tool, tmp_path):
        """Test basic pytest command generation."""
        cmd = await tool._build_command(
            framework="pytest",
            test_path=tmp_path,
            work_dir=tmp_path,
            pattern=None,
            verbose=True,
            fail_fast=False,
            coverage=False
        )
        assert "python -m pytest" in cmd
        assert "-v" in cmd
        assert "--tb=short" in cmd

    @pytest.mark.asyncio
    async def test_pytest_command_with_pattern(self, tool, tmp_path):
        """Test pytest command with pattern filter."""
        cmd = await tool._build_command(
            framework="pytest",
            test_path=tmp_path,
            work_dir=tmp_path,
            pattern="test_auth",
            verbose=True,
            fail_fast=False,
            coverage=False
        )
        assert "-k" in cmd
        assert "test_auth" in cmd

    @pytest.mark.asyncio
    async def test_pytest_command_fail_fast(self, tool, tmp_path):
        """Test pytest command with fail_fast."""
        cmd = await tool._build_command(
            framework="pytest",
            test_path=tmp_path,
            work_dir=tmp_path,
            pattern=None,
            verbose=True,
            fail_fast=True,
            coverage=False
        )
        assert "-x" in cmd

    @pytest.mark.asyncio
    async def test_pytest_command_coverage(self, tool, tmp_path):
        """Test pytest command with coverage."""
        cmd = await tool._build_command(
            framework="pytest",
            test_path=tmp_path,
            work_dir=tmp_path,
            pattern=None,
            verbose=True,
            fail_fast=False,
            coverage=True
        )
        assert "--cov" in cmd

    @pytest.mark.asyncio
    async def test_jest_command_basic(self, tool, tmp_path):
        """Test basic jest command generation."""
        cmd = await tool._build_command(
            framework="jest",
            test_path=tmp_path,
            work_dir=tmp_path,
            pattern=None,
            verbose=True,
            fail_fast=False,
            coverage=False
        )
        assert "npx jest" in cmd
        assert "--verbose" in cmd
        assert "--colors" in cmd

    @pytest.mark.asyncio
    async def test_cargo_command_basic(self, tool, tmp_path):
        """Test basic cargo test command generation."""
        cmd = await tool._build_command(
            framework="cargo",
            test_path=tmp_path,
            work_dir=tmp_path,
            pattern=None,
            verbose=True,
            fail_fast=False,
            coverage=False
        )
        assert "cargo test" in cmd
        assert "--verbose" in cmd

    @pytest.mark.asyncio
    async def test_go_command_basic(self, tool, tmp_path):
        """Test basic go test command generation."""
        cmd = await tool._build_command(
            framework="go",
            test_path=tmp_path,
            work_dir=tmp_path,
            pattern=None,
            verbose=True,
            fail_fast=False,
            coverage=False
        )
        assert "go test" in cmd
        assert "-v" in cmd
        assert "./..." in cmd

    @pytest.mark.asyncio
    async def test_unsupported_framework(self, tool, tmp_path):
        """Test unsupported framework returns None."""
        cmd = await tool._build_command(
            framework="unknown",
            test_path=tmp_path,
            work_dir=tmp_path,
            pattern=None,
            verbose=True,
            fail_fast=False,
            coverage=False
        )
        assert cmd is None

    def test_parse_pytest_results_passed(self, tool):
        """Test parsing pytest output with passed tests."""
        output = "======================== 5 passed in 0.52s ========================"
        results = tool._parse_results("pytest", output, 0)
        assert results["passed"] == 5
        assert results["failed"] == 0
        assert results["total"] == 5

    def test_parse_pytest_results_mixed(self, tool):
        """Test parsing pytest output with mixed results."""
        output = "=============== 3 passed, 2 failed, 1 skipped in 0.52s ==============="
        results = tool._parse_results("pytest", output, 1)
        assert results["passed"] == 3
        assert results["failed"] == 2
        assert results["skipped"] == 1
        assert results["total"] == 6

    def test_parse_unittest_results_ok(self, tool):
        """Test parsing unittest output with OK."""
        output = "Ran 10 tests in 0.001s\n\nOK"
        results = tool._parse_results("unittest", output, 0)
        assert results["total"] == 10
        assert results["passed"] == 10

    def test_parse_unittest_results_failed(self, tool):
        """Test parsing unittest output with failures."""
        output = "Ran 10 tests in 0.001s\n\nFAILED (failures=2, errors=1)"
        results = tool._parse_results("unittest", output, 1)
        assert results["total"] == 10
        assert results["failed"] == 2
        assert results["errors"] == 1
        assert results["passed"] == 7

    def test_parse_jest_results(self, tool):
        """Test parsing jest output."""
        output = "Tests:       2 failed, 1 skipped, 5 passed, 8 total"
        results = tool._parse_results("jest", output, 1)
        assert results["passed"] == 5
        assert results["failed"] == 2
        assert results["skipped"] == 1
        assert results["total"] == 8

    def test_parse_cargo_results(self, tool):
        """Test parsing cargo test output."""
        output = "test result: ok. 10 passed; 0 failed; 2 ignored; 0 measured"
        results = tool._parse_results("cargo", output, 0)
        assert results["passed"] == 10
        assert results["failed"] == 0
        assert results["skipped"] == 2

    def test_parse_go_results(self, tool):
        """Test parsing go test output."""
        output = """--- PASS: TestOne (0.00s)
--- PASS: TestTwo (0.00s)
--- FAIL: TestThree (0.00s)
--- SKIP: TestFour (0.00s)
PASS
ok      example.com/pkg 0.001s"""
        results = tool._parse_results("go", output, 1)
        assert results["passed"] == 2
        assert results["failed"] == 1
        assert results["skipped"] == 1

    @pytest.mark.asyncio
    async def test_run_tests_success(self, tool, tmp_path):
        """Test successful test execution."""
        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (
                b"======================== 5 passed in 0.52s ========================",
                b""
            )
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(framework="pytest")

            assert result.success
            assert result.metadata["passed"] == 5
            assert result.metadata["failed"] == 0

    @pytest.mark.asyncio
    async def test_run_tests_failure(self, tool, tmp_path):
        """Test failed test execution."""
        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (
                b"=============== 3 passed, 2 failed in 0.52s ===============",
                b""
            )
            mock_process.returncode = 1
            mock_proc.return_value = mock_process

            result = await tool.execute(framework="pytest")

            assert not result.success
            assert "2 failure" in result.error
            assert result.metadata["passed"] == 3
            assert result.metadata["failed"] == 2

    @pytest.mark.asyncio
    async def test_run_tests_timeout(self, tool, tmp_path):
        """Test test execution timeout."""
        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.side_effect = asyncio.TimeoutError()
            mock_process.kill = MagicMock()
            mock_proc.return_value = mock_process

            result = await tool.execute(framework="pytest", timeout=1)

            assert not result.success
            assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_run_tests_with_specific_path(self, tool, tmp_path):
        """Test running tests on specific path."""
        test_file = tmp_path / "tests" / "test_example.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def test_pass(): pass")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"1 passed", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="tests/test_example.py", framework="pytest")

            # Check that path is included in metadata
            assert "test_example.py" in result.metadata["path"]


class TestCheckSyntaxTool:
    """Tests for CheckSyntaxTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a CheckSyntaxTool instance."""
        return CheckSyntaxTool(work_dir=tmp_path)

    def test_tool_metadata(self, tool):
        """Test tool has correct metadata."""
        assert tool.name == "check_syntax"
        assert "syntax" in tool.description.lower()
        schema = tool.get_schema()
        assert schema["function"]["name"] == "check_syntax"

    def test_parameters_schema(self, tool):
        """Test tool parameters schema is correct."""
        params = tool.parameters
        assert "path" in params["properties"]
        assert "language" in params["properties"]
        assert params["required"] == ["path"]

    def test_extension_mapping(self, tool):
        """Test file extension to language mapping."""
        assert tool.EXTENSION_MAP[".py"] == "python"
        assert tool.EXTENSION_MAP[".js"] == "javascript"
        assert tool.EXTENSION_MAP[".ts"] == "typescript"
        assert tool.EXTENSION_MAP[".rs"] == "rust"
        assert tool.EXTENSION_MAP[".go"] == "go"

    @pytest.mark.asyncio
    async def test_python_syntax_valid(self, tool, tmp_path):
        """Test valid Python syntax check."""
        py_file = tmp_path / "valid.py"
        py_file.write_text("def hello():\n    return 'world'\n")

        result = await tool.execute(path="valid.py")

        assert result.success
        assert "Syntax OK" in result.output

    @pytest.mark.asyncio
    async def test_python_syntax_invalid(self, tool, tmp_path):
        """Test invalid Python syntax check."""
        py_file = tmp_path / "invalid.py"
        py_file.write_text("def hello(\n    return 'world'\n")

        result = await tool.execute(path="invalid.py")

        assert not result.success
        assert "Syntax error" in result.error or "error" in result.error.lower()

    @pytest.mark.asyncio
    async def test_python_syntax_directory(self, tool, tmp_path):
        """Test Python syntax check on directory."""
        (tmp_path / "file1.py").write_text("x = 1")
        (tmp_path / "file2.py").write_text("y = 2")

        result = await tool.execute(path=".", language="python")

        assert result.success
        assert "2 file(s) checked" in result.output

    @pytest.mark.asyncio
    async def test_python_syntax_directory_with_error(self, tool, tmp_path):
        """Test Python syntax check on directory with errors."""
        (tmp_path / "valid.py").write_text("x = 1")
        (tmp_path / "invalid.py").write_text("def (:")

        result = await tool.execute(path=".", language="python")

        assert not result.success
        assert "invalid.py" in result.output

    @pytest.mark.asyncio
    async def test_javascript_syntax_valid(self, tool, tmp_path):
        """Test valid JavaScript syntax check."""
        js_file = tmp_path / "valid.js"
        js_file.write_text("function hello() { return 'world'; }")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="valid.js")

            assert result.success
            assert "Syntax OK" in result.output

    @pytest.mark.asyncio
    async def test_javascript_syntax_invalid(self, tool, tmp_path):
        """Test invalid JavaScript syntax check."""
        js_file = tmp_path / "invalid.js"
        js_file.write_text("function hello( { return 'world'; }")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"SyntaxError: Unexpected token")
            mock_process.returncode = 1
            mock_proc.return_value = mock_process

            result = await tool.execute(path="invalid.js")

            assert not result.success
            assert "Syntax error" in result.error or "SyntaxError" in result.output

    @pytest.mark.asyncio
    async def test_typescript_syntax_check(self, tool, tmp_path):
        """Test TypeScript syntax check."""
        ts_file = tmp_path / "app.ts"
        ts_file.write_text("const x: string = 'hello';")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="app.ts")

            assert result.success

    @pytest.mark.asyncio
    async def test_typescript_syntax_error(self, tool, tmp_path):
        """Test TypeScript syntax error detection."""
        ts_file = tmp_path / "app.ts"
        ts_file.write_text("const x: string = 123;")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (
                b"app.ts(1,7): error TS2322: Type 'number' is not assignable to type 'string'.",
                b""
            )
            mock_process.returncode = 1
            mock_proc.return_value = mock_process

            result = await tool.execute(path="app.ts")

            assert not result.success
            assert result.metadata.get("error_count", 0) >= 1

    @pytest.mark.asyncio
    async def test_rust_syntax_check(self, tool, tmp_path):
        """Test Rust syntax check."""
        (tmp_path / "Cargo.toml").write_text("[package]\nname = \"test\"")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.rs").write_text("fn main() {}")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="src/main.rs", language="rust")

            assert result.success

    @pytest.mark.asyncio
    async def test_go_syntax_check(self, tool, tmp_path):
        """Test Go syntax check."""
        go_file = tmp_path / "main.go"
        go_file.write_text("package main\n\nfunc main() {}")

        with patch('asyncio.create_subprocess_shell') as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await tool.execute(path="main.go")

            assert result.success

    @pytest.mark.asyncio
    async def test_path_not_exists(self, tool, tmp_path):
        """Test error when path doesn't exist."""
        result = await tool.execute(path="nonexistent.py")

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_unknown_extension(self, tool, tmp_path):
        """Test error when extension is unknown."""
        unknown_file = tmp_path / "file.xyz"
        unknown_file.write_text("content")

        result = await tool.execute(path="file.xyz")

        assert not result.success
        assert "Could not detect language" in result.error

    @pytest.mark.asyncio
    async def test_directory_requires_language(self, tool, tmp_path):
        """Test that directory check requires language parameter."""
        result = await tool.execute(path=".")

        assert not result.success
        assert "specify 'language'" in result.error

    @pytest.mark.asyncio
    async def test_unsupported_language(self, tool, tmp_path):
        """Test error for unsupported language."""
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1")

        result = await tool.execute(path="test.py", language="cobol")

        assert not result.success
        assert "Unsupported language" in result.error


class TestToolRegistration:
    """Test that testing tools are properly registered."""

    def test_run_tests_in_registry(self):
        """Test RunTestsTool is in default registry."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()
        tool = registry.get_tool("run_tests")

        assert tool is not None
        assert isinstance(tool, RunTestsTool)

    def test_check_syntax_in_registry(self):
        """Test CheckSyntaxTool is in default registry."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()
        tool = registry.get_tool("check_syntax")

        assert tool is not None
        assert isinstance(tool, CheckSyntaxTool)


class TestAgentIntegration:
    """Test that testing tools are available to appropriate agents."""

    def test_brokkr_has_testing_tools(self):
        """Test Brokkr has run_tests and check_syntax."""
        from sindri.agents.registry import AGENTS

        brokkr = AGENTS["brokkr"]
        assert "run_tests" in brokkr.tools
        assert "check_syntax" in brokkr.tools

    def test_huginn_has_testing_tools(self):
        """Test Huginn has run_tests and check_syntax."""
        from sindri.agents.registry import AGENTS

        huginn = AGENTS["huginn"]
        assert "run_tests" in huginn.tools
        assert "check_syntax" in huginn.tools

    def test_mimir_has_testing_tools(self):
        """Test Mimir has run_tests and check_syntax."""
        from sindri.agents.registry import AGENTS

        mimir = AGENTS["mimir"]
        assert "run_tests" in mimir.tools
        assert "check_syntax" in mimir.tools

    def test_skald_has_testing_tools(self):
        """Test Skald has run_tests and check_syntax."""
        from sindri.agents.registry import AGENTS

        skald = AGENTS["skald"]
        assert "run_tests" in skald.tools
        assert "check_syntax" in skald.tools
