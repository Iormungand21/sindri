"""Tests for system access configuration (Milestone 5).

Tests cover:
- SystemAccessLevel enum
- Config field defaults and validation
- Access check utility logic
- CLI command integration
"""

import pytest
from pathlib import Path
from click.testing import CliRunner

from sindri.config import SindriConfig, SystemAccessLevel
from sindri.core.access import (
    AccessCheckResult,
    check_system_access,
    can_modify_self,
)


class TestSystemAccessLevel:
    """Test SystemAccessLevel enum."""

    def test_enum_values(self):
        """Test that enum has expected values."""
        assert SystemAccessLevel.RESTRICTED.value == "restricted"
        assert SystemAccessLevel.SUPERVISED.value == "supervised"
        assert SystemAccessLevel.FULL.value == "full"

    def test_enum_from_string(self):
        """Test creating enum from string values."""
        assert SystemAccessLevel("restricted") == SystemAccessLevel.RESTRICTED
        assert SystemAccessLevel("supervised") == SystemAccessLevel.SUPERVISED
        assert SystemAccessLevel("full") == SystemAccessLevel.FULL

    def test_enum_invalid_value(self):
        """Test that invalid values raise ValueError."""
        with pytest.raises(ValueError):
            SystemAccessLevel("invalid")

    def test_enum_str_behavior(self):
        """Test that enum behaves like a string for serialization."""
        level = SystemAccessLevel.SUPERVISED
        # Should be usable as a string
        assert str(level) == "SystemAccessLevel.SUPERVISED"
        assert level.value == "supervised"


class TestSindriConfigAccessFields:
    """Test access-related config fields."""

    def test_default_access_level(self, tmp_path):
        """Test default access level is SUPERVISED."""
        config = SindriConfig(data_dir=tmp_path)
        assert config.system_access == SystemAccessLevel.SUPERVISED

    def test_default_allowed_services(self, tmp_path):
        """Test default allowed services list."""
        config = SindriConfig(data_dir=tmp_path)
        assert "ollama" in config.allowed_services
        assert "litellm" in config.allowed_services
        assert "sindri" in config.allowed_services
        assert len(config.allowed_services) == 3

    def test_default_self_modification(self, tmp_path):
        """Test default self-modification is disabled."""
        config = SindriConfig(data_dir=tmp_path)
        assert config.allow_self_modification is False

    def test_custom_access_level_restricted(self, tmp_path):
        """Test setting RESTRICTED access level."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.RESTRICTED,
        )
        assert config.system_access == SystemAccessLevel.RESTRICTED

    def test_custom_access_level_full(self, tmp_path):
        """Test setting FULL access level."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.FULL,
        )
        assert config.system_access == SystemAccessLevel.FULL

    def test_custom_allowed_services(self, tmp_path):
        """Test setting custom allowed services."""
        config = SindriConfig(
            data_dir=tmp_path,
            allowed_services=["docker", "nginx", "postgresql"],
        )
        assert config.allowed_services == ["docker", "nginx", "postgresql"]

    def test_empty_allowed_services(self, tmp_path):
        """Test that empty allowed services list is valid."""
        config = SindriConfig(
            data_dir=tmp_path,
            allowed_services=[],
        )
        assert config.allowed_services == []

    def test_allowed_services_strips_whitespace(self, tmp_path):
        """Test that service names are stripped of whitespace."""
        config = SindriConfig(
            data_dir=tmp_path,
            allowed_services=["  docker  ", "nginx ", " redis"],
        )
        assert config.allowed_services == ["docker", "nginx", "redis"]

    def test_allowed_services_validates_strings(self, tmp_path):
        """Test that allowed_services rejects non-strings."""
        with pytest.raises(ValueError, match="non-empty string"):
            SindriConfig(
                data_dir=tmp_path,
                allowed_services=["valid", ""],
            )

    def test_allow_self_modification_true(self, tmp_path):
        """Test enabling self-modification."""
        config = SindriConfig(
            data_dir=tmp_path,
            allow_self_modification=True,
        )
        assert config.allow_self_modification is True

    def test_config_serialization_roundtrip(self, tmp_path):
        """Test that config saves and loads correctly with new fields."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.FULL,
            allowed_services=["test_service_a", "test_service_b"],
            allow_self_modification=True,
        )

        config_path = tmp_path / "config.toml"
        config.save(str(config_path))

        loaded = SindriConfig.load(str(config_path))
        assert loaded.system_access == SystemAccessLevel.FULL
        assert loaded.allowed_services == ["test_service_a", "test_service_b"]
        assert loaded.allow_self_modification is True

    def test_config_serialization_defaults(self, tmp_path):
        """Test that defaults are preserved through serialization."""
        config = SindriConfig(data_dir=tmp_path)

        config_path = tmp_path / "config.toml"
        config.save(str(config_path))

        loaded = SindriConfig.load(str(config_path))
        assert loaded.system_access == SystemAccessLevel.SUPERVISED
        assert "ollama" in loaded.allowed_services
        assert loaded.allow_self_modification is False


class TestAccessCheckResult:
    """Test AccessCheckResult dataclass."""

    def test_basic_creation(self):
        """Test creating AccessCheckResult."""
        result = AccessCheckResult(allowed=True, reason="Test reason")
        assert result.allowed is True
        assert result.reason == "Test reason"
        assert result.needs_confirmation is False

    def test_with_confirmation(self):
        """Test AccessCheckResult with confirmation flag."""
        result = AccessCheckResult(
            allowed=True,
            reason="Needs confirmation",
            needs_confirmation=True,
        )
        assert result.needs_confirmation is True


class TestCheckSystemAccess:
    """Test check_system_access function."""

    def test_restricted_blocks_modifications(self, tmp_path):
        """Test that RESTRICTED mode blocks all modifications."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.RESTRICTED,
        )
        result = check_system_access(
            config, "restart service", is_modification=True
        )
        assert not result.allowed
        assert "RESTRICTED" in result.reason

    def test_restricted_allows_reads(self, tmp_path):
        """Test that RESTRICTED mode allows read operations."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.RESTRICTED,
        )
        result = check_system_access(
            config, "check service status", is_modification=False
        )
        assert result.allowed
        assert "Read operation allowed" in result.reason

    def test_supervised_requires_confirmation_for_modifications(self, tmp_path):
        """Test that SUPERVISED mode requires confirmation for modifications."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.SUPERVISED,
        )
        result = check_system_access(
            config, "restart ollama", service="ollama", is_modification=True
        )
        assert result.allowed
        assert result.needs_confirmation
        assert "confirmation required" in result.reason

    def test_supervised_no_confirmation_for_reads(self, tmp_path):
        """Test that SUPERVISED mode doesn't require confirmation for reads."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.SUPERVISED,
        )
        result = check_system_access(
            config, "check status", is_modification=False
        )
        assert result.allowed
        assert not result.needs_confirmation

    def test_full_access_no_confirmation(self, tmp_path):
        """Test that FULL mode allows modifications without confirmation."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.FULL,
        )
        result = check_system_access(
            config, "restart ollama", service="ollama", is_modification=True
        )
        assert result.allowed
        assert not result.needs_confirmation
        assert "Full access granted" in result.reason

    def test_service_not_in_whitelist_supervised(self, tmp_path):
        """Test that service not in whitelist is blocked (SUPERVISED)."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.SUPERVISED,
            allowed_services=["ollama"],
        )
        result = check_system_access(
            config, "restart nginx", service="nginx", is_modification=True
        )
        assert not result.allowed
        assert "not in allowed_services" in result.reason
        assert "nginx" in result.reason

    def test_service_not_in_whitelist_full(self, tmp_path):
        """Test that service not in whitelist is blocked even in FULL mode."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.FULL,
            allowed_services=["ollama"],
        )
        result = check_system_access(
            config, "restart nginx", service="nginx", is_modification=True
        )
        assert not result.allowed
        assert "not in allowed_services" in result.reason

    def test_service_in_whitelist_full(self, tmp_path):
        """Test that service in whitelist is allowed in FULL mode."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.FULL,
            allowed_services=["ollama", "docker"],
        )
        result = check_system_access(
            config, "restart docker", service="docker", is_modification=True
        )
        assert result.allowed

    def test_no_service_check_when_service_none(self, tmp_path):
        """Test that service whitelist isn't checked when service is None."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.FULL,
            allowed_services=[],  # Empty whitelist
        )
        # No service specified, so whitelist shouldn't be checked
        result = check_system_access(
            config, "some operation", is_modification=True
        )
        assert result.allowed


class TestCanModifySelf:
    """Test can_modify_self function."""

    def test_disabled_returns_not_allowed(self, tmp_path):
        """Test that disabled self-modification returns not allowed."""
        config = SindriConfig(
            data_dir=tmp_path,
            allow_self_modification=False,
        )
        result = can_modify_self(config)
        assert not result.allowed
        assert "disabled" in result.reason.lower()

    def test_restricted_mode_blocks_even_if_enabled(self, tmp_path):
        """Test that RESTRICTED mode blocks self-modification even if enabled."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.RESTRICTED,
            allow_self_modification=True,
        )
        result = can_modify_self(config)
        assert not result.allowed
        assert "RESTRICTED" in result.reason

    def test_supervised_mode_requires_confirmation(self, tmp_path):
        """Test that SUPERVISED mode requires confirmation for self-modification."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.SUPERVISED,
            allow_self_modification=True,
        )
        result = can_modify_self(config)
        assert result.allowed
        assert result.needs_confirmation

    def test_full_mode_allows_without_confirmation(self, tmp_path):
        """Test that FULL mode allows self-modification without confirmation."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.FULL,
            allow_self_modification=True,
        )
        result = can_modify_self(config)
        assert result.allowed
        assert not result.needs_confirmation


class TestAccessCLI:
    """Test access CLI commands."""

    def test_access_show_command(self, tmp_path, monkeypatch):
        """Test 'sindri access show' command."""
        from sindri.cli import cli

        # Monkeypatch SindriConfig.load to use tmp_path
        monkeypatch.setattr(
            "sindri.config.SindriConfig.load",
            lambda path=None: SindriConfig(data_dir=tmp_path),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["access", "show"])

        assert result.exit_code == 0
        assert "SUPERVISED" in result.output
        assert "ollama" in result.output
        assert "Self-Modification" in result.output

    def test_access_services_list(self, tmp_path, monkeypatch):
        """Test 'sindri access services --list' command."""
        from sindri.cli import cli

        monkeypatch.setattr(
            "sindri.config.SindriConfig.load",
            lambda path=None: SindriConfig(data_dir=tmp_path),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["access", "services", "--list"])

        assert result.exit_code == 0
        assert "ollama" in result.output
        assert "litellm" in result.output
        assert "sindri" in result.output

    def test_access_self_modify_status(self, tmp_path, monkeypatch):
        """Test 'sindri access self-modify' (status only) command."""
        from sindri.cli import cli

        monkeypatch.setattr(
            "sindri.config.SindriConfig.load",
            lambda path=None: SindriConfig(data_dir=tmp_path),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["access", "self-modify"])

        assert result.exit_code == 0
        assert "Disabled" in result.output or "disabled" in result.output.lower()


class TestAccessCheckEdgeCases:
    """Test edge cases for access checking."""

    def test_case_sensitivity_in_service_names(self, tmp_path):
        """Test that service names are case-sensitive."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.FULL,
            allowed_services=["Ollama"],  # Capitalized
        )
        # Lowercase should not match
        result = check_system_access(
            config, "restart ollama", service="ollama", is_modification=True
        )
        assert not result.allowed  # Should be blocked due to case mismatch

    def test_empty_operation_string(self, tmp_path):
        """Test that empty operation string is handled."""
        config = SindriConfig(
            data_dir=tmp_path,
            system_access=SystemAccessLevel.RESTRICTED,
        )
        result = check_system_access(config, "", is_modification=True)
        assert not result.allowed

    def test_all_config_combinations(self, tmp_path):
        """Test various config combinations work correctly."""
        # Test matrix of access levels and modification flags
        for level in SystemAccessLevel:
            for is_mod in [True, False]:
                config = SindriConfig(
                    data_dir=tmp_path,
                    system_access=level,
                )
                result = check_system_access(
                    config, "test operation", is_modification=is_mod
                )
                # Should not raise any exceptions
                assert isinstance(result, AccessCheckResult)
                assert isinstance(result.allowed, bool)
                assert isinstance(result.reason, str)
