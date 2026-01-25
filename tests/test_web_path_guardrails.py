"""Tests for Sindri Web API Path Guardrails.

Web/API Hardening PRD - Epic C: API Work Dir and Path Guardrails tests.
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient

from sindri.web.server import create_app
from sindri.config import ApiConfig
from sindri.tools.registry import ToolRegistry
from sindri.tools.base import ToolResult


# ===== Fixtures =====


@pytest.fixture
def temp_base_dir():
    """Create a temporary base directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def app_no_guardrails():
    """Create test application without path guardrails."""
    return create_app(vram_gb=16.0, base_work_dir=None)


@pytest.fixture
def app_with_guardrails(temp_base_dir):
    """Create test application with path guardrails enabled."""
    return create_app(vram_gb=16.0, base_work_dir=temp_base_dir)


@pytest.fixture
def client_no_guardrails(app_no_guardrails):
    """Create test client without path guardrails."""
    return TestClient(app_no_guardrails)


@pytest.fixture
def client_with_guardrails(app_with_guardrails):
    """Create test client with path guardrails enabled."""
    return TestClient(app_with_guardrails)


# ===== ApiConfig Path Guardrails Tests =====


class TestApiConfigPathGuardrails:
    """Tests for ApiConfig path guardrails fields."""

    def test_api_config_defaults(self):
        """Test default base_work_dir is None (no restriction)."""
        config = ApiConfig()
        assert config.base_work_dir is None

    def test_api_config_base_work_dir_set(self, temp_base_dir):
        """Test base_work_dir can be set."""
        config = ApiConfig(base_work_dir=temp_base_dir)
        assert config.base_work_dir == temp_base_dir

    def test_validate_path_within_base_allowed(self, temp_base_dir):
        """Test path within base returns allowed."""
        config = ApiConfig(base_work_dir=temp_base_dir)
        subdir = temp_base_dir / "subdir"
        allowed, reason = config.validate_path_within_base(subdir)
        assert allowed is True
        assert reason == ""

    def test_validate_path_within_base_denied(self, temp_base_dir):
        """Test path outside base returns denied."""
        config = ApiConfig(base_work_dir=temp_base_dir)
        outside_path = Path("/etc/passwd")
        allowed, reason = config.validate_path_within_base(outside_path)
        assert allowed is False
        assert "outside allowed base directory" in reason

    def test_validate_path_traversal_denied(self, temp_base_dir):
        """Test path traversal attack is caught."""
        config = ApiConfig(base_work_dir=temp_base_dir)
        # Try to escape using ..
        traversal_path = temp_base_dir / ".." / ".." / "etc" / "passwd"
        allowed, reason = config.validate_path_within_base(traversal_path)
        assert allowed is False
        assert "outside allowed base directory" in reason

    def test_validate_path_no_restriction(self):
        """Test no restriction when base_work_dir is None."""
        config = ApiConfig(base_work_dir=None)
        # Any path should be allowed
        allowed, reason = config.validate_path_within_base(Path("/etc/passwd"))
        assert allowed is True
        assert reason == ""

    def test_get_resolved_base_work_dir(self, temp_base_dir):
        """Test get_resolved_base_work_dir returns resolved path."""
        config = ApiConfig(base_work_dir=temp_base_dir)
        resolved = config.get_resolved_base_work_dir()
        assert resolved == temp_base_dir.resolve()

    def test_get_resolved_base_work_dir_none(self):
        """Test get_resolved_base_work_dir returns None when not set."""
        config = ApiConfig(base_work_dir=None)
        assert config.get_resolved_base_work_dir() is None


# ===== ToolRegistry Path Guardrails Tests =====


class TestToolRegistryPathGuardrails:
    """Tests for ToolRegistry path validation."""

    def test_registry_default_no_guardrails(self):
        """Test ToolRegistry defaults to no path guardrails."""
        registry = ToolRegistry.default()
        assert registry.api_base_work_dir is None

    def test_registry_with_guardrails(self, temp_base_dir):
        """Test ToolRegistry can be created with path guardrails."""
        registry = ToolRegistry.default(api_base_work_dir=temp_base_dir)
        assert registry.api_base_work_dir == temp_base_dir

    def test_extract_path_arguments(self, temp_base_dir):
        """Test _extract_path_arguments finds path args."""
        registry = ToolRegistry.default(api_base_work_dir=temp_base_dir)

        arguments = {
            "path": "/some/file.txt",
            "content": "hello world",
            "other": 123,
        }
        path_args = registry._extract_path_arguments("write_file", arguments)
        assert "path" in path_args
        assert path_args["path"] == ["/some/file.txt"]  # Now returns list
        assert "content" not in path_args

    def test_extract_path_arguments_multiple(self, temp_base_dir):
        """Test _extract_path_arguments finds multiple path args."""
        registry = ToolRegistry.default(api_base_work_dir=temp_base_dir)

        arguments = {
            "source": "/src/file.txt",
            "destination": "/dst/file.txt",
            "mode": "copy",
        }
        path_args = registry._extract_path_arguments("move_file", arguments)
        assert "source" in path_args
        assert "destination" in path_args
        assert path_args["source"] == ["/src/file.txt"]
        assert path_args["destination"] == ["/dst/file.txt"]
        assert "mode" not in path_args

    def test_extract_path_arguments_list_based(self, temp_base_dir):
        """Test _extract_path_arguments handles list-based path arguments."""
        registry = ToolRegistry.default(api_base_work_dir=temp_base_dir)

        arguments = {
            "output": "/backup.zip",
            "paths": ["/file1.txt", "/dir/", "/file2.txt"],
            "compression_level": 6,
        }
        path_args = registry._extract_path_arguments("archive_create", arguments)
        assert "output" in path_args
        assert "paths" in path_args
        assert path_args["output"] == ["/backup.zip"]
        assert path_args["paths"] == ["/file1.txt", "/dir/", "/file2.txt"]
        assert "compression_level" not in path_args

    def test_resolve_path_for_validation_absolute(self, temp_base_dir):
        """Test _resolve_path_for_validation handles absolute paths."""
        registry = ToolRegistry.default(
            work_dir=temp_base_dir,
            api_base_work_dir=temp_base_dir,
        )

        resolved = registry._resolve_path_for_validation("/etc/passwd")
        assert resolved == Path("/etc/passwd").resolve()

    def test_resolve_path_for_validation_relative(self, temp_base_dir):
        """Test _resolve_path_for_validation handles relative paths."""
        registry = ToolRegistry.default(
            work_dir=temp_base_dir,
            api_base_work_dir=temp_base_dir,
        )

        resolved = registry._resolve_path_for_validation("subdir/file.txt")
        assert resolved == (temp_base_dir / "subdir" / "file.txt").resolve()

    def test_is_path_within_base_allowed(self, temp_base_dir):
        """Test _is_path_within_base returns True for paths inside base."""
        registry = ToolRegistry.default(api_base_work_dir=temp_base_dir)

        resolved_base = temp_base_dir.resolve()
        path_inside = (temp_base_dir / "subdir" / "file.txt").resolve()

        assert registry._is_path_within_base(path_inside, resolved_base) is True

    def test_is_path_within_base_denied(self, temp_base_dir):
        """Test _is_path_within_base returns False for paths outside base."""
        registry = ToolRegistry.default(api_base_work_dir=temp_base_dir)

        resolved_base = temp_base_dir.resolve()
        path_outside = Path("/etc/passwd").resolve()

        assert registry._is_path_within_base(path_outside, resolved_base) is False

    @pytest.mark.asyncio
    async def test_execute_tool_path_denied(self, temp_base_dir):
        """Test tool execution is blocked for paths outside base."""
        registry = ToolRegistry.default(
            work_dir=temp_base_dir,
            api_base_work_dir=temp_base_dir,
        )

        # Try to read a file outside the base directory
        result = await registry.execute("read_file", {"path": "/etc/passwd"})

        assert result.success is False
        assert "outside allowed base directory" in result.error

    @pytest.mark.asyncio
    async def test_execute_tool_path_allowed(self, temp_base_dir):
        """Test tool execution is allowed for paths inside base."""
        # Create a test file inside base
        test_file = temp_base_dir / "test.txt"
        test_file.write_text("hello")

        registry = ToolRegistry.default(
            work_dir=temp_base_dir,
            api_base_work_dir=temp_base_dir,
        )

        # Read a file inside the base directory
        result = await registry.execute("read_file", {"path": str(test_file)})

        assert result.success is True
        assert result.output == "hello"

    @pytest.mark.asyncio
    async def test_execute_tool_no_guardrails_allows_all(self, temp_base_dir):
        """Test tool execution allows any path when guardrails disabled."""
        registry = ToolRegistry.default(
            work_dir=temp_base_dir,
            api_base_work_dir=None,  # No guardrails
        )

        # Path validation is skipped, tool will fail for different reason
        # (file may not exist, permission denied, etc. - but not path guardrails)
        result = await registry.execute("read_file", {"path": "/etc/hostname"})

        # Should either succeed or fail for a non-guardrails reason
        if not result.success:
            assert "outside allowed base directory" not in result.error

    @pytest.mark.asyncio
    async def test_execute_tool_list_paths_denied(self, temp_base_dir):
        """Test tool execution blocks list-based paths outside base."""
        registry = ToolRegistry.default(
            work_dir=temp_base_dir,
            api_base_work_dir=temp_base_dir,
        )

        # Try to use list-based paths with one path outside base
        # Using 'paths' argument which is in PATH_ARG_NAMES
        result = await registry.execute("archive_create", {
            "output": str(temp_base_dir / "backup.zip"),
            "paths": [str(temp_base_dir / "file.txt"), "/etc/passwd"],
        })

        assert result.success is False
        assert "outside allowed base directory" in result.error

    @pytest.mark.asyncio
    async def test_execute_tool_list_paths_all_allowed(self, temp_base_dir):
        """Test tool execution allows list-based paths all within base."""
        # Create test files
        file1 = temp_base_dir / "file1.txt"
        file2 = temp_base_dir / "file2.txt"
        file1.write_text("hello")
        file2.write_text("world")

        registry = ToolRegistry.default(
            work_dir=temp_base_dir,
            api_base_work_dir=temp_base_dir,
        )

        # All paths within base - should pass path validation
        # (tool may still fail for other reasons, but not path guardrails)
        result = await registry.execute("archive_create", {
            "output": str(temp_base_dir / "backup.zip"),
            "paths": [str(file1), str(file2)],
        })

        # If failed, should not be due to path guardrails
        if not result.success:
            assert "outside allowed base directory" not in (result.error or "")


# ===== Environment Variable Tests =====


class TestPathGuardrailsEnvironmentVariables:
    """Tests for path guardrails configuration via environment variables."""

    def test_create_app_reads_base_work_dir_from_env(self, temp_base_dir, monkeypatch):
        """Test that create_app reads SINDRI_API_BASE_WORK_DIR env var."""
        monkeypatch.setenv("SINDRI_API_BASE_WORK_DIR", str(temp_base_dir))

        app = create_app(vram_gb=16.0)

        # Get the API config from the module
        from sindri.web import server
        assert server._api_config is not None
        assert server._api_config.base_work_dir == temp_base_dir

    def test_explicit_arg_overrides_env_var(self, temp_base_dir, monkeypatch):
        """Test that explicit base_work_dir arg overrides env var."""
        other_dir = temp_base_dir / "other"
        other_dir.mkdir()

        monkeypatch.setenv("SINDRI_API_BASE_WORK_DIR", str(temp_base_dir))

        app = create_app(vram_gb=16.0, base_work_dir=other_dir)

        from sindri.web import server
        assert server._api_config.base_work_dir == other_dir


# ===== Task Creation Path Validation Tests =====


class TestTaskCreationPathValidation:
    """Tests for work_dir validation during task creation."""

    def test_task_create_work_dir_allowed(self, temp_base_dir):
        """Test task creation succeeds when work_dir is within base."""
        app = create_app(vram_gb=16.0, base_work_dir=temp_base_dir)
        client = TestClient(app)

        with patch("sindri.core.orchestrator.Orchestrator") as mock_orch:
            mock_instance = AsyncMock()
            mock_orch.return_value = mock_instance
            mock_instance.run = AsyncMock(return_value={"success": True, "result": "done"})
            mock_instance.cleanup = AsyncMock()

            response = client.post("/api/tasks", json={
                "description": "test task",
                "work_dir": str(temp_base_dir / "subdir"),
            })

        # Should succeed (not be blocked by path validation)
        assert response.status_code == 200

    def test_task_create_work_dir_denied(self, temp_base_dir):
        """Test task creation fails when work_dir is outside base."""
        app = create_app(vram_gb=16.0, base_work_dir=temp_base_dir)
        client = TestClient(app)

        response = client.post("/api/tasks", json={
            "description": "test task",
            "work_dir": "/etc",
        })

        assert response.status_code == 400
        assert "outside allowed base directory" in response.json()["detail"]

    def test_task_create_work_dir_no_restriction(self):
        """Test task creation allows any work_dir when guardrails disabled."""
        app = create_app(vram_gb=16.0, base_work_dir=None)
        client = TestClient(app)

        with patch("sindri.core.orchestrator.Orchestrator") as mock_orch:
            mock_instance = AsyncMock()
            mock_orch.return_value = mock_instance
            mock_instance.run = AsyncMock(return_value={"success": True, "result": "done"})
            mock_instance.cleanup = AsyncMock()

            response = client.post("/api/tasks", json={
                "description": "test task",
                "work_dir": "/tmp",
            })

        # Should succeed when no guardrails
        assert response.status_code == 200

    def test_task_create_work_dir_omitted_defaults_to_base(self, temp_base_dir):
        """Test work_dir defaults to base_work_dir when omitted (not cwd)."""
        app = create_app(vram_gb=16.0, base_work_dir=temp_base_dir)
        client = TestClient(app)

        with patch("sindri.core.orchestrator.Orchestrator") as mock_orch:
            mock_instance = AsyncMock()
            mock_orch.return_value = mock_instance
            mock_instance.run = AsyncMock(return_value={"success": True, "result": "done"})
            mock_instance.cleanup = AsyncMock()

            # Don't provide work_dir - should default to base_work_dir
            response = client.post("/api/tasks", json={
                "description": "test task",
            })

        # Should succeed - work_dir defaults to base_work_dir
        assert response.status_code == 200

        # Verify Orchestrator was called with work_dir=base_work_dir
        mock_orch.assert_called_once()
        call_kwargs = mock_orch.call_args.kwargs
        assert call_kwargs["work_dir"] == temp_base_dir.resolve()


# ===== Trigger work_dir Validation Tests =====


class TestTriggerPathValidation:
    """Tests for work_dir in trigger creation."""

    def test_trigger_create_respects_path_guardrails(self, temp_base_dir):
        """Test that triggers also respect path guardrails on execution."""
        # This is a placeholder - the actual trigger execution
        # will use the same Orchestrator with api_base_work_dir
        app = create_app(vram_gb=16.0, base_work_dir=temp_base_dir)
        client = TestClient(app)

        # Triggers can be created with any work_dir (validation happens at execution)
        response = client.post("/api/triggers", json={
            "name": "test-trigger",
            "trigger_type": "cron",
            "task_description": "test task",
            "cron_expression": "0 * * * *",
            "work_dir": str(temp_base_dir / "allowed"),
        })

        # Trigger creation should succeed
        assert response.status_code == 200


# ===== CLI Unaffected Tests =====


class TestCLIUnaffected:
    """Tests to verify CLI/TUI tools are not affected by API guardrails."""

    def test_tool_registry_without_api_context_has_no_guardrails(self):
        """Test ToolRegistry created without api_base_work_dir has no restrictions."""
        # This simulates CLI/TUI usage
        registry = ToolRegistry.default(work_dir=Path.cwd())

        # Should have no API base work dir restriction
        assert registry.api_base_work_dir is None

    @pytest.mark.asyncio
    async def test_cli_tool_execution_allows_any_path(self, temp_base_dir):
        """Test that CLI-mode tools can access any path."""
        # Create a test file
        test_file = Path("/etc/hostname")

        # CLI mode: no api_base_work_dir
        registry = ToolRegistry.default(
            work_dir=Path.cwd(),
            api_base_work_dir=None,
        )

        # Should be able to read system files (if permissions allow)
        result = await registry.execute("read_file", {"path": str(test_file)})

        # The test passes if there's no "outside allowed base directory" error
        if not result.success:
            assert "outside allowed base directory" not in (result.error or "")
