"""Tests for doctor health check functions."""

from sindri.core.doctor import (
    check_python_version,
    check_database,
    check_ollama,
    check_required_models,
    get_all_checks,
)


def test_check_python_version():
    """Test Python version check."""
    result = check_python_version()

    assert result.name == "Python Version"
    # Should pass on Python 3.11+
    assert result.passed is True
    assert "." in result.message  # Contains version number


def test_check_database():
    """Test database check."""
    result = check_database()

    assert result.name == "Database"
    # Should either exist or not be created yet (both are fine)
    # Don't assert passed value since it depends on system state
    assert result.message in [
        "Not created yet",
        "OK",
        "Database error",
    ] or result.message.startswith("OK (")


def test_check_ollama():
    """Test Ollama check."""
    result = check_ollama()

    assert result.name == "Ollama"
    # Result depends on whether Ollama is running
    # Just verify structure is correct
    assert isinstance(result.passed, bool)
    assert result.message is not None


def test_check_required_models():
    """Test required models check."""
    result, available, missing = check_required_models()

    assert result.name == "Required Models"
    assert isinstance(available, list)
    assert isinstance(missing, list)

    # Should check for at least a few models
    from sindri.agents.registry import AGENTS

    expected_count = (
        len({agent.model for agent in AGENTS.values()}) + 1
    )  # +1 for embedding model

    total_found = len(available) + len(missing)
    assert total_found == expected_count


def test_get_all_checks():
    """Test running all health checks."""
    results = get_all_checks()

    # Verify structure
    assert "checks" in results
    assert "models" in results
    assert "dependencies" in results
    assert "overall" in results

    # Verify all expected checks are present
    expected_checks = [
        "ollama",
        "python",
        "config",
        "database",
        "gpu",
        "models",
        "dependencies",
    ]
    for check_name in expected_checks:
        assert check_name in results["checks"]

    # Verify overall status fields
    assert "all_passed" in results["overall"]
    assert "critical_passed" in results["overall"]
    assert "ready" in results["overall"]

    # All should be boolean
    assert isinstance(results["overall"]["all_passed"], bool)
    assert isinstance(results["overall"]["critical_passed"], bool)
    assert isinstance(results["overall"]["ready"], bool)


def test_get_all_checks_with_config_path():
    """Test health checks with custom config path."""
    # Should not crash with non-existent config
    results = get_all_checks(config_path="/nonexistent/config.toml")

    assert "checks" in results
    # Config check should handle missing file gracefully
    assert results["checks"]["config"].name == "Configuration"
