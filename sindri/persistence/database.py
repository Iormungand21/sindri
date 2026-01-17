"""SQLite database setup for Sindri."""

import aiosqlite
from pathlib import Path
from typing import Optional
import structlog

log = structlog.get_logger()

# Current schema version for migration tracking
# Version 2: Added session_metrics table for performance tracking
# Version 3: Added session_feedback table for feedback collection and fine-tuning
# Version 4: Added session_shares and session_comments for remote collaboration
SCHEMA_VERSION = 4


class Database:
    """Manages SQLite database connection and schema."""

    def __init__(self, db_path: Optional[Path] = None, auto_backup: bool = True):
        """Initialize database manager.

        Args:
            db_path: Path to the database file. Defaults to ~/.sindri/sindri.db
            auto_backup: Create backup before schema changes (default True)
        """
        if db_path is None:
            db_path = Path.home() / ".sindri" / "sindri.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.auto_backup = auto_backup
        self._backup_manager = None

    @property
    def backup_manager(self):
        """Lazy-load backup manager."""
        if self._backup_manager is None:
            from sindri.persistence.backup import DatabaseBackup

            self._backup_manager = DatabaseBackup(self.db_path)
        return self._backup_manager

    async def _get_schema_version(self, db: aiosqlite.Connection) -> int:
        """Get current schema version from database."""
        try:
            async with db.execute("PRAGMA user_version") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    async def _set_schema_version(self, db: aiosqlite.Connection, version: int):
        """Set schema version in database."""
        await db.execute(f"PRAGMA user_version = {version}")

    async def initialize(self):
        """Create database schema if it doesn't exist.

        Creates auto-backup before schema changes if database exists
        and auto_backup is enabled.
        """
        # Check if we need to create backup before schema changes
        needs_migration = False
        if self.db_path.exists() and self.auto_backup:
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    current_version = await self._get_schema_version(db)
                    needs_migration = current_version < SCHEMA_VERSION
            except Exception as e:
                log.warning("schema_version_check_failed", error=str(e))

        # Create backup before migration
        if needs_migration:
            try:
                await self.backup_manager.create_backup(reason="pre_migration")
                log.info("pre_migration_backup_created")
            except Exception as e:
                log.warning("pre_migration_backup_failed", error=str(e))
                # Continue with migration anyway

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    iterations INTEGER DEFAULT 0
                )
            """
            )

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_calls TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """
            )

            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_turns_session
                ON turns(session_id)
            """
            )

            # Phase 5.5: Performance metrics table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS session_metrics (
                    session_id TEXT PRIMARY KEY,
                    metrics_json TEXT NOT NULL,
                    duration_seconds REAL,
                    total_iterations INTEGER DEFAULT 0,
                    total_tool_executions INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """
            )

            # Phase 9.4: Session feedback for fine-tuning
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS session_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    turn_index INTEGER,
                    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                    quality_tags TEXT,
                    notes TEXT,
                    include_in_training INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """
            )

            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_feedback_session
                ON session_feedback(session_id)
            """
            )

            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_feedback_rating
                ON session_feedback(rating)
            """
            )

            # Phase 9.2: Remote collaboration - Session sharing
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS session_shares (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    share_token TEXT UNIQUE NOT NULL,
                    created_by TEXT,
                    permission TEXT NOT NULL DEFAULT 'read',
                    expires_at TIMESTAMP,
                    max_uses INTEGER,
                    use_count INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """
            )

            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_shares_token
                ON session_shares(share_token)
            """
            )

            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_shares_session
                ON session_shares(session_id)
            """
            )

            # Phase 9.2: Remote collaboration - Review comments
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS session_comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    turn_index INTEGER,
                    line_number INTEGER,
                    author TEXT NOT NULL,
                    content TEXT NOT NULL,
                    comment_type TEXT DEFAULT 'comment',
                    status TEXT DEFAULT 'open',
                    parent_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id),
                    FOREIGN KEY (parent_id) REFERENCES session_comments(id)
                )
            """
            )

            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_comments_session
                ON session_comments(session_id)
            """
            )

            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_comments_turn
                ON session_comments(session_id, turn_index)
            """
            )

            # Update schema version
            await self._set_schema_version(db, SCHEMA_VERSION)

            await db.commit()

        log.info("database_initialized", path=str(self.db_path))

    def get_connection(self):
        """Get an async database connection context manager."""
        return aiosqlite.connect(self.db_path)
