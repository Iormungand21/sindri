"""Tests for CLI commands."""

import pytest
from click.testing import CliRunner
from unittest.mock import AsyncMock, MagicMock, patch

from sindri.cli import cli, agents, sessions, recover, resume


def test_agents_command():
    """Test the agents command displays agent information."""
    runner = CliRunner()
    result = runner.invoke(agents)

    assert result.exit_code == 0
    assert "Sindri Agents" in result.output
    assert "brokkr" in result.output
    assert "huginn" in result.output
    assert "mimir" in result.output
    assert "Total agents" in result.output


def test_sessions_command_no_sessions():
    """Test sessions command with no sessions."""
    from sindri.persistence.state import SessionState

    with patch.object(SessionState, 'list_sessions', new_callable=AsyncMock) as mock_list:
        mock_list.return_value = []

        runner = CliRunner()
        result = runner.invoke(sessions)

        assert result.exit_code == 0
        assert "No sessions found" in result.output


def test_sessions_command_with_sessions():
    """Test sessions command with existing sessions."""
    from sindri.persistence.state import SessionState

    mock_sessions = [
        {
            "id": "test-session-1",
            "task": "Test task 1",
            "model": "test-model",
            "iterations": 5,
            "status": "completed",
            "created_at": "2026-01-15 12:00:00"
        },
        {
            "id": "test-session-2",
            "task": "Test task 2",
            "model": "test-model-2",
            "iterations": 3,
            "status": "active",
            "created_at": "2026-01-15 13:00:00"
        }
    ]

    with patch.object(SessionState, 'list_sessions', new_callable=AsyncMock) as mock_list:
        mock_list.return_value = mock_sessions

        runner = CliRunner()
        result = runner.invoke(sessions)

        assert result.exit_code == 0
        assert "Recent sessions" in result.output
        assert "test-session-1" in result.output or "test-ses" in result.output
        assert "Test task 1" in result.output
        assert "test-model" in result.output


def test_recover_command_no_sessions():
    """Test recover command with no recoverable sessions."""
    from sindri.core.recovery import RecoveryManager

    with patch.object(RecoveryManager, 'list_recoverable_sessions') as mock_list:
        mock_list.return_value = []

        runner = CliRunner()
        result = runner.invoke(recover)

        assert result.exit_code == 0
        assert "No recoverable sessions found" in result.output


def test_recover_command_with_sessions():
    """Test recover command with recoverable sessions."""
    from sindri.core.recovery import RecoveryManager

    mock_sessions = [
        {
            "session_id": "test-session-1",
            "task": "Test interrupted task",
            "timestamp": "2026-01-15 12:00:00"
        }
    ]

    with patch.object(RecoveryManager, 'list_recoverable_sessions') as mock_list:
        mock_list.return_value = mock_sessions

        runner = CliRunner()
        result = runner.invoke(recover)

        assert result.exit_code == 0
        assert "Recoverable Sessions" in result.output
        assert "test-ses" in result.output


def test_resume_command_not_found():
    """Test resume command with non-existent full-length session ID."""
    runner = CliRunner()
    result = runner.invoke(resume, ['aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'])

    # Should complete without error but report not found
    assert result.exit_code == 0
    assert "not found" in result.output.lower()


def test_resume_command_short_id_not_found():
    """Test resume command with short session ID that doesn't exist."""
    runner = CliRunner()
    result = runner.invoke(resume, ['xxxxxxxx'])

    # Should complete without error but report not found
    assert result.exit_code == 0
    assert "not found" in result.output.lower() or "no session" in result.output.lower()
