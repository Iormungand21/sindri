"""Tests for Granular Tool Permissions feature."""

import pytest
from pathlib import Path
import tempfile

from sindri.config import SindriConfig
from sindri.core.access import check_tool_permission, AccessCheckResult
from sindri.tools.shell import ShellTool
from sindri.tools.filesystem import WriteFileTool, EditFileTool


# ============================================================================
# Tool Permission Check Tests
# ============================================================================


class TestCheckToolPermission:
    """Test check_tool_permission function."""

    def test_all_tools_allowed_by_default(self):
        """Test that all tools are allowed when no restrictions set."""
        config = SindriConfig()  # Default config
        result = check_tool_permission(config, "shell")

        assert result.allowed
        assert not result.needs_confirmation

    def test_allowlist_allows_listed_tool(self):
        """Test that allowlist allows tools in the list."""
        config = SindriConfig(allowed_tools=["read_file", "write_file", "shell"])
        result = check_tool_permission(config, "shell")

        assert result.allowed

    def test_allowlist_blocks_unlisted_tool(self):
        """Test that allowlist blocks tools not in the list."""
        config = SindriConfig(allowed_tools=["read_file", "write_file"])
        result = check_tool_permission(config, "shell")

        assert not result.allowed
        assert "not in allowed_tools" in result.reason

    def test_blocklist_blocks_listed_tool(self):
        """Test that blocklist blocks tools in the list."""
        config = SindriConfig(blocked_tools=["shell", "delete_file"])
        result = check_tool_permission(config, "shell")

        assert not result.allowed
        assert "is blocked" in result.reason

    def test_blocklist_allows_unlisted_tool(self):
        """Test that blocklist allows tools not in the list."""
        config = SindriConfig(blocked_tools=["shell"])
        result = check_tool_permission(config, "read_file")

        assert result.allowed

    def test_approval_required_sets_confirmation_flag(self):
        """Test that tool_approval_required sets needs_confirmation."""
        config = SindriConfig(tool_approval_required=["write_file", "shell"])
        result = check_tool_permission(config, "shell")

        assert result.allowed
        assert result.needs_confirmation
        assert "requires approval" in result.reason

    def test_approval_not_required_for_unlisted_tool(self):
        """Test that tool_approval_required doesn't affect unlisted tools."""
        config = SindriConfig(tool_approval_required=["write_file"])
        result = check_tool_permission(config, "read_file")

        assert result.allowed
        assert not result.needs_confirmation

    def test_blocklist_takes_precedence_over_allowlist(self):
        """Test that blocklist takes precedence when tool is in both."""
        config = SindriConfig(
            allowed_tools=["shell", "read_file"],
            blocked_tools=["shell"],
        )
        result = check_tool_permission(config, "shell")

        assert not result.allowed
        assert "is blocked" in result.reason


# ============================================================================
# Dry-Run Mode Tests
# ============================================================================


class TestDryRunMode:
    """Test dry-run mode for dangerous tools."""

    @pytest.mark.asyncio
    async def test_shell_dry_run_explicit(self):
        """Test shell tool dry-run with explicit parameter."""
        tool = ShellTool()
        result = await tool.execute(command="echo test", dry_run=True)

        assert result.success
        assert "[DRY RUN]" in result.output
        assert result.metadata.get("dry_run") is True

    @pytest.mark.asyncio
    async def test_shell_dry_run_from_config(self, tmp_path, monkeypatch):
        """Test shell tool dry-run from config default."""
        monkeypatch.setattr(
            "sindri.tools.shell.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                default_dry_run=True,
            ),
        )
        tool = ShellTool()
        result = await tool.execute(command="echo test")

        assert result.success
        assert "[DRY RUN]" in result.output

    @pytest.mark.asyncio
    async def test_shell_dry_run_explicit_overrides_config(self, tmp_path, monkeypatch):
        """Test that explicit dry_run=False overrides config default."""
        monkeypatch.setattr(
            "sindri.tools.shell.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                default_dry_run=True,
                system_access="full",  # Allow execution
            ),
        )
        tool = ShellTool()
        result = await tool.execute(command="echo test", dry_run=False)

        assert result.success
        assert "[DRY RUN]" not in result.output
        assert "test" in result.output

    @pytest.mark.asyncio
    async def test_write_file_dry_run(self, tmp_path, monkeypatch):
        """Test write_file tool dry-run mode."""
        monkeypatch.setattr(
            "sindri.tools.filesystem.SindriConfig.load",
            lambda path=None: SindriConfig(data_dir=tmp_path),
        )
        tool = WriteFileTool()
        file_path = tmp_path / "test.txt"

        result = await tool.execute(
            path=str(file_path),
            content="Hello, world!",
            dry_run=True,
        )

        assert result.success
        assert "[DRY RUN]" in result.output
        assert result.metadata.get("dry_run") is True
        # File should NOT be created
        assert not file_path.exists()

    @pytest.mark.asyncio
    async def test_edit_file_dry_run(self, tmp_path, monkeypatch):
        """Test edit_file tool dry-run mode."""
        monkeypatch.setattr(
            "sindri.tools.filesystem.SindriConfig.load",
            lambda path=None: SindriConfig(data_dir=tmp_path),
        )
        tool = EditFileTool()
        file_path = tmp_path / "test.txt"
        file_path.write_text("Hello, world!")

        result = await tool.execute(
            path=str(file_path),
            old_text="world",
            new_text="Sindri",
            dry_run=True,
        )

        assert result.success
        assert "[DRY RUN]" in result.output
        assert result.metadata.get("dry_run") is True
        # File should NOT be modified
        assert file_path.read_text() == "Hello, world!"

    @pytest.mark.asyncio
    async def test_audit_records_dry_run_from_config_default(self, tmp_path, monkeypatch):
        """Test that audit log records dry_run=True when config.default_dry_run=True."""
        from sindri.tools.registry import ToolRegistry
        from sindri.persistence.audit import AuditStore
        from sindri.config import SystemAccessLevel
        import os

        os.environ["SINDRI_DB_PATH"] = str(tmp_path / "test.db")

        # Config has default_dry_run=True but caller doesn't pass dry_run
        monkeypatch.setattr(
            "sindri.tools.registry.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                default_dry_run=True,
                system_access=SystemAccessLevel.FULL,
            ),
        )
        monkeypatch.setattr(
            "sindri.tools.shell.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                default_dry_run=True,
                system_access=SystemAccessLevel.FULL,
            ),
        )

        registry = ToolRegistry.default()
        # Note: NOT passing dry_run argument - should use config default
        result = await registry.execute("shell", {"command": "echo test"})

        assert result.success
        assert "[DRY RUN]" in result.output

        # Audit should record dry_run=True from result.metadata
        store = AuditStore()
        entries = await store.list_entries(tool_name="shell")
        assert len(entries) == 1
        assert entries[0].dry_run is True

        del os.environ["SINDRI_DB_PATH"]


# ============================================================================
# Tool Registry Permission Enforcement Tests
# ============================================================================


class TestToolRegistryPermissions:
    """Test permission enforcement in ToolRegistry.execute()."""

    @pytest.mark.asyncio
    async def test_registry_blocks_disallowed_tool(self, tmp_path, monkeypatch):
        """Test that ToolRegistry blocks tools not in allowlist."""
        from sindri.tools.registry import ToolRegistry

        monkeypatch.setattr(
            "sindri.tools.registry.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                allowed_tools=["read_file"],  # shell not allowed
            ),
        )

        registry = ToolRegistry.default()
        result = await registry.execute("shell", {"command": "echo test"})

        assert not result.success
        assert "not in allowed_tools" in result.error

    @pytest.mark.asyncio
    async def test_registry_blocks_blocked_tool(self, tmp_path, monkeypatch):
        """Test that ToolRegistry blocks tools in blocklist."""
        from sindri.tools.registry import ToolRegistry

        monkeypatch.setattr(
            "sindri.tools.registry.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                blocked_tools=["shell"],
            ),
        )

        registry = ToolRegistry.default()
        result = await registry.execute("shell", {"command": "echo test"})

        assert not result.success
        assert "is blocked" in result.error

    @pytest.mark.asyncio
    async def test_registry_allows_permitted_tool(self, tmp_path, monkeypatch):
        """Test that ToolRegistry allows permitted tools."""
        from sindri.tools.registry import ToolRegistry
        from sindri.config import SystemAccessLevel

        monkeypatch.setattr(
            "sindri.tools.registry.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                allowed_tools=["shell"],
                system_access=SystemAccessLevel.FULL,
            ),
        )
        # Also patch for the shell tool's access check
        monkeypatch.setattr(
            "sindri.tools.shell.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                system_access=SystemAccessLevel.FULL,
            ),
        )

        registry = ToolRegistry.default()
        result = await registry.execute("shell", {"command": "echo permitted"})

        assert result.success
        assert "permitted" in result.output

    @pytest.mark.asyncio
    async def test_registry_blocks_approval_required_tool(self, tmp_path, monkeypatch):
        """Test that ToolRegistry blocks tools requiring approval."""
        from sindri.tools.registry import ToolRegistry
        from sindri.config import SystemAccessLevel

        monkeypatch.setattr(
            "sindri.tools.registry.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                tool_approval_required=["shell"],
                system_access=SystemAccessLevel.FULL,
            ),
        )

        registry = ToolRegistry.default()
        result = await registry.execute("shell", {"command": "echo test"})

        assert not result.success
        assert "requires approval" in result.error

    @pytest.mark.asyncio
    async def test_registry_logs_permission_denial(self, tmp_path, monkeypatch):
        """Test that permission denials are logged to audit."""
        from sindri.tools.registry import ToolRegistry
        from sindri.persistence.audit import AuditStore
        import os

        os.environ["SINDRI_DB_PATH"] = str(tmp_path / "test.db")

        monkeypatch.setattr(
            "sindri.tools.registry.SindriConfig.load",
            lambda path=None: SindriConfig(
                data_dir=tmp_path,
                blocked_tools=["shell"],
            ),
        )

        registry = ToolRegistry.default()
        await registry.execute("shell", {"command": "echo test"})

        # Check audit log has denial entry
        store = AuditStore()
        entries = await store.list_entries(tool_name="shell")
        assert len(entries) == 1
        assert entries[0].success is False
        assert "blocked" in entries[0].error

        del os.environ["SINDRI_DB_PATH"]


# ============================================================================
# Audit Store Tests
# ============================================================================


class TestAuditStore:
    """Test AuditStore functionality."""

    @pytest.mark.asyncio
    async def test_log_and_list_entries(self, tmp_path):
        """Test logging and listing audit entries."""
        from sindri.persistence.audit import AuditStore, AuditEntry
        from sindri.persistence.database import Database
        import os

        os.environ["SINDRI_DB_PATH"] = str(tmp_path / "test.db")

        store = AuditStore()
        entry = AuditEntry(
            tool_name="shell",
            success=True,
            arguments='{"command": "echo test"}',
            duration_ms=100,
        )

        # Log entry
        logged = await store.log_tool_execution(entry)
        assert logged.id is not None

        # List entries
        entries = await store.list_entries(limit=10)
        assert len(entries) == 1
        assert entries[0].tool_name == "shell"
        assert entries[0].success is True

        del os.environ["SINDRI_DB_PATH"]

    @pytest.mark.asyncio
    async def test_list_entries_with_filters(self, tmp_path):
        """Test listing audit entries with filters."""
        from sindri.persistence.audit import AuditStore, AuditEntry
        import os

        os.environ["SINDRI_DB_PATH"] = str(tmp_path / "test.db")

        store = AuditStore()

        # Log multiple entries
        await store.log_tool_execution(AuditEntry(tool_name="shell", success=True))
        await store.log_tool_execution(AuditEntry(tool_name="read_file", success=True))
        await store.log_tool_execution(AuditEntry(tool_name="shell", success=False, error="failed"))

        # Filter by tool name
        shell_entries = await store.list_entries(tool_name="shell")
        assert len(shell_entries) == 2

        # Filter by success
        success_entries = await store.list_entries(success_only=True)
        assert len(success_entries) == 2

        failed_entries = await store.list_entries(failed_only=True)
        assert len(failed_entries) == 1

        del os.environ["SINDRI_DB_PATH"]

    @pytest.mark.asyncio
    async def test_get_tool_stats(self, tmp_path):
        """Test getting tool usage statistics."""
        from sindri.persistence.audit import AuditStore, AuditEntry
        import os

        os.environ["SINDRI_DB_PATH"] = str(tmp_path / "test.db")

        store = AuditStore()

        # Log entries with various outcomes
        await store.log_tool_execution(AuditEntry(tool_name="shell", success=True, duration_ms=100))
        await store.log_tool_execution(AuditEntry(tool_name="shell", success=True, duration_ms=200))
        await store.log_tool_execution(AuditEntry(tool_name="shell", success=False, duration_ms=50))

        stats = await store.get_tool_stats()

        assert "shell" in stats
        assert stats["shell"]["total"] == 3
        assert stats["shell"]["successes"] == 2
        assert stats["shell"]["failures"] == 1
        assert stats["shell"]["success_rate"] == pytest.approx(66.67, rel=0.1)

        del os.environ["SINDRI_DB_PATH"]

    @pytest.mark.asyncio
    async def test_export_json(self, tmp_path):
        """Test exporting audit entries to JSON."""
        from sindri.persistence.audit import AuditStore, AuditEntry
        import json
        import os

        os.environ["SINDRI_DB_PATH"] = str(tmp_path / "test.db")

        store = AuditStore()
        await store.log_tool_execution(AuditEntry(tool_name="shell", success=True))

        export_data = await store.export_entries(format="json")
        parsed = json.loads(export_data)

        assert len(parsed) == 1
        assert parsed[0]["tool_name"] == "shell"

        del os.environ["SINDRI_DB_PATH"]

    @pytest.mark.asyncio
    async def test_export_csv(self, tmp_path):
        """Test exporting audit entries to CSV."""
        from sindri.persistence.audit import AuditStore, AuditEntry
        import os

        os.environ["SINDRI_DB_PATH"] = str(tmp_path / "test.db")

        store = AuditStore()
        await store.log_tool_execution(AuditEntry(tool_name="shell", success=True))

        export_data = await store.export_entries(format="csv")

        assert "tool_name" in export_data  # Header
        assert "shell" in export_data

        del os.environ["SINDRI_DB_PATH"]
