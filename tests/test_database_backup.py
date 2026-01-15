"""Tests for database backup functionality."""

import asyncio
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sindri.persistence.backup import BackupError, DatabaseBackup


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary test database."""
    db_path = tmp_path / "test.db"

    # Create a simple database with some data
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO test (value) VALUES ('hello')")
    conn.execute("INSERT INTO test (value) VALUES ('world')")
    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def backup_dir(tmp_path):
    """Create a temporary backup directory."""
    backup_path = tmp_path / "backups"
    backup_path.mkdir()
    return backup_path


@pytest.fixture
def backup_manager(temp_db, backup_dir):
    """Create a DatabaseBackup manager with temp paths."""
    return DatabaseBackup(db_path=temp_db, backup_dir=backup_dir)


class TestDatabaseBackupInit:
    """Test DatabaseBackup initialization."""

    def test_default_paths(self, tmp_path, monkeypatch):
        """Should use default paths when none provided."""
        # Mock Path.home() to use tmp_path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        mgr = DatabaseBackup()

        assert mgr.db_path == tmp_path / ".sindri" / "sindri.db"
        assert mgr.backup_dir == tmp_path / ".sindri" / "backups"

    def test_custom_paths(self, temp_db, backup_dir):
        """Should use custom paths when provided."""
        mgr = DatabaseBackup(db_path=temp_db, backup_dir=backup_dir)

        assert mgr.db_path == temp_db
        assert mgr.backup_dir == backup_dir

    def test_creates_backup_dir(self, temp_db, tmp_path):
        """Should create backup directory if it doesn't exist."""
        backup_dir = tmp_path / "new_backups"
        assert not backup_dir.exists()

        DatabaseBackup(db_path=temp_db, backup_dir=backup_dir)

        assert backup_dir.exists()


class TestCreateBackup:
    """Test backup creation."""

    @pytest.mark.asyncio
    async def test_creates_backup_file(self, backup_manager, backup_dir):
        """Should create a backup file."""
        backup_path = await backup_manager.create_backup(reason="test")

        assert backup_path.exists()
        assert backup_path.parent == backup_dir
        assert "test" in backup_path.name

    @pytest.mark.asyncio
    async def test_backup_contains_data(self, backup_manager, temp_db):
        """Backup should contain original database data."""
        backup_path = await backup_manager.create_backup()

        # Verify backup has the same data
        conn = sqlite3.connect(str(backup_path))
        cursor = conn.execute("SELECT value FROM test ORDER BY id")
        values = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert values == ["hello", "world"]

    @pytest.mark.asyncio
    async def test_backup_filename_format(self, backup_manager):
        """Backup filename should include timestamp and reason."""
        backup_path = await backup_manager.create_backup(reason="manual")

        # Format: sindri_YYYYMMDD_HHMMSS_reason.db
        assert backup_path.name.startswith("sindri_")
        assert backup_path.name.endswith("_manual.db")

    @pytest.mark.asyncio
    async def test_sanitizes_reason(self, backup_manager):
        """Should sanitize special characters in reason."""
        backup_path = await backup_manager.create_backup(reason="pre/migration!")

        assert "pre_migration_" in backup_path.name

    @pytest.mark.asyncio
    async def test_raises_on_missing_database(self, backup_dir):
        """Should raise FileNotFoundError if database doesn't exist."""
        mgr = DatabaseBackup(
            db_path=Path("/nonexistent/db.sqlite"),
            backup_dir=backup_dir
        )

        with pytest.raises(FileNotFoundError):
            await mgr.create_backup()

    @pytest.mark.asyncio
    async def test_multiple_backups(self, backup_manager):
        """Should create multiple unique backups."""
        backup1 = await backup_manager.create_backup(reason="first")
        # Small delay to ensure different timestamp
        await asyncio.sleep(0.01)
        backup2 = await backup_manager.create_backup(reason="second")

        assert backup1 != backup2
        assert backup1.exists()
        assert backup2.exists()


class TestCheckIntegrity:
    """Test database integrity checking."""

    @pytest.mark.asyncio
    async def test_healthy_database(self, backup_manager):
        """Should return healthy for valid database."""
        is_healthy, issues = await backup_manager.check_integrity()

        assert is_healthy is True
        assert issues == []

    @pytest.mark.asyncio
    async def test_nonexistent_database(self, backup_dir):
        """Should return healthy for nonexistent database."""
        mgr = DatabaseBackup(
            db_path=Path("/nonexistent/db.sqlite"),
            backup_dir=backup_dir
        )

        is_healthy, issues = await mgr.check_integrity()

        assert is_healthy is True
        assert issues == []

    @pytest.mark.asyncio
    async def test_corrupted_database(self, tmp_path, backup_dir):
        """Should detect corrupted database."""
        # Create a corrupted database file
        corrupt_db = tmp_path / "corrupt.db"
        corrupt_db.write_bytes(b"not a valid sqlite database")

        mgr = DatabaseBackup(db_path=corrupt_db, backup_dir=backup_dir)

        is_healthy, issues = await mgr.check_integrity()

        assert is_healthy is False
        assert len(issues) > 0


class TestRestoreFromBackup:
    """Test backup restoration."""

    @pytest.mark.asyncio
    async def test_restores_data(self, backup_manager, temp_db):
        """Should restore database from backup."""
        # Create backup
        backup_path = await backup_manager.create_backup(reason="original")

        # Modify original database
        conn = sqlite3.connect(str(temp_db))
        conn.execute("DELETE FROM test")
        conn.execute("INSERT INTO test (value) VALUES ('modified')")
        conn.commit()
        conn.close()

        # Restore from backup
        result = await backup_manager.restore_from_backup(backup_path)

        assert result is True

        # Verify original data restored
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.execute("SELECT value FROM test ORDER BY id")
        values = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert values == ["hello", "world"]

    @pytest.mark.asyncio
    async def test_creates_pre_restore_backup(self, backup_manager, backup_dir):
        """Should create pre-restore backup before restoring."""
        backup_path = await backup_manager.create_backup(reason="original")

        await backup_manager.restore_from_backup(backup_path)

        # Check for pre_restore backup
        backups = backup_manager.list_backups()
        reasons = [b["reason"] for b in backups]

        assert "pre_restore" in reasons

    @pytest.mark.asyncio
    async def test_raises_on_missing_backup(self, backup_manager):
        """Should raise FileNotFoundError if backup doesn't exist."""
        with pytest.raises(FileNotFoundError):
            await backup_manager.restore_from_backup(Path("/nonexistent/backup.db"))

    @pytest.mark.asyncio
    async def test_raises_on_corrupted_backup(self, backup_manager, tmp_path):
        """Should raise BackupError if backup is corrupted."""
        # Create a corrupted backup file
        corrupt_backup = tmp_path / "corrupt_backup.db"
        corrupt_backup.write_bytes(b"not a valid sqlite database")

        with pytest.raises(BackupError, match="not a valid database"):
            await backup_manager.restore_from_backup(corrupt_backup)


class TestListBackups:
    """Test backup listing."""

    @pytest.mark.asyncio
    async def test_lists_backups(self, backup_manager):
        """Should list created backups."""
        await backup_manager.create_backup(reason="first")
        await asyncio.sleep(0.01)
        await backup_manager.create_backup(reason="second")

        backups = backup_manager.list_backups()

        assert len(backups) == 2
        # Should be sorted newest first
        assert backups[0]["reason"] == "second"
        assert backups[1]["reason"] == "first"

    def test_empty_when_no_backups(self, backup_manager):
        """Should return empty list when no backups exist."""
        backups = backup_manager.list_backups()

        assert backups == []

    @pytest.mark.asyncio
    async def test_backup_metadata(self, backup_manager):
        """Should include correct metadata in backup info."""
        await backup_manager.create_backup(reason="test")

        backups = backup_manager.list_backups()

        assert len(backups) == 1
        backup = backups[0]

        assert "path" in backup
        assert "timestamp" in backup
        assert "reason" in backup
        assert "size_bytes" in backup
        assert backup["reason"] == "test"
        assert isinstance(backup["timestamp"], datetime)
        assert backup["size_bytes"] > 0


class TestCleanupOldBackups:
    """Test backup cleanup."""

    @pytest.mark.asyncio
    async def test_keeps_recent_backups(self, backup_manager):
        """Should keep the specified number of recent backups."""
        for i in range(5):
            await backup_manager.create_backup(reason=f"backup_{i}")
            await asyncio.sleep(0.01)

        deleted = backup_manager.cleanup_old_backups(keep=3)

        assert deleted == 2
        assert len(backup_manager.list_backups()) == 3

    @pytest.mark.asyncio
    async def test_no_deletion_when_under_limit(self, backup_manager):
        """Should not delete any backups when under the limit."""
        await backup_manager.create_backup(reason="only_one")

        deleted = backup_manager.cleanup_old_backups(keep=10)

        assert deleted == 0
        assert len(backup_manager.list_backups()) == 1

    def test_no_deletion_when_empty(self, backup_manager):
        """Should handle empty backup directory."""
        deleted = backup_manager.cleanup_old_backups(keep=10)

        assert deleted == 0


class TestGetBackupStats:
    """Test backup statistics."""

    @pytest.mark.asyncio
    async def test_stats_with_backups(self, backup_manager):
        """Should return correct statistics."""
        await backup_manager.create_backup(reason="first")
        await asyncio.sleep(1.1)  # Ensure different second for timestamp
        await backup_manager.create_backup(reason="second")

        stats = backup_manager.get_backup_stats()

        assert stats["count"] == 2
        assert stats["total_size_bytes"] > 0
        assert stats["oldest"] is not None
        assert stats["newest"] is not None
        assert stats["newest"] >= stats["oldest"]

    def test_stats_when_empty(self, backup_manager):
        """Should return zero stats when no backups."""
        stats = backup_manager.get_backup_stats()

        assert stats["count"] == 0
        assert stats["total_size_bytes"] == 0
        assert stats["oldest"] is None
        assert stats["newest"] is None


class TestDatabaseIntegration:
    """Test integration with Database class."""

    @pytest.mark.asyncio
    async def test_auto_backup_property(self, tmp_path):
        """Database should have backup_manager property."""
        from sindri.persistence.database import Database

        db = Database(db_path=tmp_path / "test.db")

        assert hasattr(db, "backup_manager")
        assert isinstance(db.backup_manager, DatabaseBackup)

    @pytest.mark.asyncio
    async def test_database_init_with_auto_backup_disabled(self, tmp_path):
        """Database should respect auto_backup setting."""
        from sindri.persistence.database import Database

        db = Database(db_path=tmp_path / "test.db", auto_backup=False)

        assert db.auto_backup is False


class TestDoctorBackupCheck:
    """Test doctor's backup health check."""

    def test_check_backup_no_backups(self, tmp_path, monkeypatch):
        """Should handle case with no backups."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        from sindri.core.doctor import check_backup

        result = check_backup()

        assert result.passed is True
        assert "No backups" in result.message

    def test_check_backup_with_backups(self, tmp_path, monkeypatch):
        """Should report backup count and size."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Create a fake backup file
        backup_dir = tmp_path / ".sindri" / "backups"
        backup_dir.mkdir(parents=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"sindri_{timestamp}_test.db"
        backup_file.write_bytes(b"fake backup content " * 100)

        from sindri.core.doctor import check_backup

        result = check_backup()

        assert result.passed is True
        assert "1 backup" in result.message
