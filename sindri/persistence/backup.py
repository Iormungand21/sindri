"""Database backup and integrity management for Sindri."""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite
import structlog

log = structlog.get_logger()


class BackupError(Exception):
    """Error during backup operations."""
    pass


class DatabaseBackup:
    """Manages database backups and integrity checks.

    Provides functionality for:
    - Creating timestamped backups with reason tags
    - Checking database integrity
    - Restoring from backups
    - Listing available backups
    - Cleaning up old backups
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        backup_dir: Optional[Path] = None
    ):
        """Initialize backup manager.

        Args:
            db_path: Path to the database file. Defaults to ~/.sindri/sindri.db
            backup_dir: Directory for backups. Defaults to ~/.sindri/backups
        """
        if db_path is None:
            db_path = Path.home() / ".sindri" / "sindri.db"

        self.db_path = db_path

        if backup_dir is None:
            backup_dir = db_path.parent / "backups"

        self.backup_dir = backup_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    async def create_backup(self, reason: str = "manual") -> Path:
        """Create a backup of the database.

        Args:
            reason: Tag describing why backup was created
                   (e.g., "manual", "pre_migration", "auto")

        Returns:
            Path to the created backup file

        Raises:
            BackupError: If backup fails
            FileNotFoundError: If database doesn't exist
        """
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

        # Create timestamped backup filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize reason for filename
        safe_reason = "".join(c if c.isalnum() or c == "_" else "_" for c in reason)
        backup_name = f"sindri_{timestamp}_{safe_reason}.db"
        backup_path = self.backup_dir / backup_name

        try:
            # Use SQLite's backup API for safe backup while DB might be in use
            async with aiosqlite.connect(self.db_path) as source:
                # Create the backup using SQLite's built-in backup
                async with aiosqlite.connect(backup_path) as dest:
                    await source.backup(dest)

            log.info(
                "backup_created",
                backup_path=str(backup_path),
                reason=reason,
                size_bytes=backup_path.stat().st_size
            )

            return backup_path

        except Exception as e:
            # Clean up partial backup if it exists
            if backup_path.exists():
                backup_path.unlink()

            log.error("backup_failed", error=str(e), reason=reason)
            raise BackupError(f"Failed to create backup: {e}") from e

    async def check_integrity(self) -> tuple[bool, list[str]]:
        """Check database integrity using SQLite's integrity_check.

        Returns:
            Tuple of (is_healthy, list of issues found)
        """
        if not self.db_path.exists():
            return True, []  # No database = no integrity issues

        issues = []

        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Run SQLite integrity check
                async with db.execute("PRAGMA integrity_check") as cursor:
                    rows = await cursor.fetchall()

                for row in rows:
                    result = row[0]
                    if result != "ok":
                        issues.append(result)

                # Check foreign key constraints
                async with db.execute("PRAGMA foreign_key_check") as cursor:
                    fk_issues = await cursor.fetchall()

                for fk_issue in fk_issues:
                    table, rowid, parent, fkid = fk_issue
                    issues.append(
                        f"Foreign key violation in {table} row {rowid}: "
                        f"references {parent}"
                    )

            is_healthy = len(issues) == 0

            if is_healthy:
                log.debug("integrity_check_passed")
            else:
                log.warning("integrity_check_failed", issues=issues)

            return is_healthy, issues

        except sqlite3.DatabaseError as e:
            issues.append(f"Database error: {e}")
            log.error("integrity_check_error", error=str(e))
            return False, issues

    async def restore_from_backup(self, backup_path: Path) -> bool:
        """Restore database from a backup.

        Creates a backup of current database before restoring.

        Args:
            backup_path: Path to the backup file to restore from

        Returns:
            True if restore succeeded

        Raises:
            BackupError: If restore fails
            FileNotFoundError: If backup file doesn't exist
        """
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")

        # Verify backup integrity before restoring
        try:
            async with aiosqlite.connect(backup_path) as db:
                async with db.execute("PRAGMA integrity_check") as cursor:
                    result = await cursor.fetchone()
                    if result[0] != "ok":
                        raise BackupError(f"Backup file is corrupted: {result[0]}")
        except sqlite3.DatabaseError as e:
            raise BackupError(f"Backup file is not a valid database: {e}") from e

        # Create pre-restore backup of current database if it exists
        if self.db_path.exists():
            try:
                await self.create_backup(reason="pre_restore")
            except Exception as e:
                log.warning("pre_restore_backup_failed", error=str(e))

        try:
            # Copy backup to database location
            shutil.copy2(backup_path, self.db_path)

            log.info(
                "database_restored",
                backup_path=str(backup_path),
                db_path=str(self.db_path)
            )

            return True

        except Exception as e:
            log.error("restore_failed", error=str(e))
            raise BackupError(f"Failed to restore backup: {e}") from e

    def list_backups(self) -> list[dict]:
        """List available backups.

        Returns:
            List of dicts with backup info:
            - path: Path to backup file
            - timestamp: When backup was created
            - reason: Why backup was created
            - size_bytes: Backup file size
        """
        backups = []

        if not self.backup_dir.exists():
            return backups

        for backup_file in sorted(
            self.backup_dir.glob("sindri_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True  # Newest first
        ):
            # Parse filename: sindri_YYYYMMDD_HHMMSS_reason.db
            parts = backup_file.stem.split("_", 3)

            if len(parts) >= 3:
                try:
                    date_str = parts[1]
                    time_str = parts[2]
                    reason = parts[3] if len(parts) > 3 else "unknown"

                    timestamp = datetime.strptime(
                        f"{date_str}_{time_str}",
                        "%Y%m%d_%H%M%S"
                    )

                    backups.append({
                        "path": backup_file,
                        "timestamp": timestamp,
                        "reason": reason,
                        "size_bytes": backup_file.stat().st_size
                    })
                except (ValueError, IndexError):
                    # Can't parse filename, include with defaults
                    backups.append({
                        "path": backup_file,
                        "timestamp": datetime.fromtimestamp(
                            backup_file.stat().st_mtime
                        ),
                        "reason": "unknown",
                        "size_bytes": backup_file.stat().st_size
                    })

        return backups

    def cleanup_old_backups(self, keep: int = 10) -> int:
        """Remove old backups, keeping the most recent ones.

        Args:
            keep: Number of backups to keep (default 10)

        Returns:
            Number of backups deleted
        """
        backups = self.list_backups()

        if len(backups) <= keep:
            return 0

        # Backups are already sorted newest-first
        to_delete = backups[keep:]
        deleted = 0

        for backup in to_delete:
            try:
                backup["path"].unlink()
                deleted += 1
                log.debug("backup_deleted", path=str(backup["path"]))
            except Exception as e:
                log.warning(
                    "backup_delete_failed",
                    path=str(backup["path"]),
                    error=str(e)
                )

        if deleted > 0:
            log.info("backups_cleaned", deleted=deleted, kept=keep)

        return deleted

    def get_backup_stats(self) -> dict:
        """Get statistics about backups.

        Returns:
            Dict with:
            - count: Number of backups
            - total_size_bytes: Total size of all backups
            - oldest: Timestamp of oldest backup (or None)
            - newest: Timestamp of newest backup (or None)
        """
        backups = self.list_backups()

        if not backups:
            return {
                "count": 0,
                "total_size_bytes": 0,
                "oldest": None,
                "newest": None
            }

        return {
            "count": len(backups),
            "total_size_bytes": sum(b["size_bytes"] for b in backups),
            "oldest": backups[-1]["timestamp"],  # Last in list (sorted newest-first)
            "newest": backups[0]["timestamp"]     # First in list
        }
