"""SQLite database setup for Sindri."""

import sqlite3
import aiosqlite
from pathlib import Path
from typing import Optional
import structlog

log = structlog.get_logger()


class Database:
    """Manages SQLite database connection and schema."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path.home() / ".sindri" / "sindri.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self):
        """Create database schema if it doesn't exist."""

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    iterations INTEGER DEFAULT 0
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_calls TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_turns_session
                ON turns(session_id)
            """)

            await db.commit()

        log.info("database_initialized", path=str(self.db_path))

    def get_connection(self):
        """Get an async database connection context manager."""
        return aiosqlite.connect(self.db_path)
