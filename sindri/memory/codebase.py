"""Codebase analysis storage - Phase 7.4: Codebase Understanding."""

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict
import structlog

from sindri.analysis.results import (
    CodebaseAnalysis,
    DependencyInfo,
    ArchitectureInfo,
    StyleInfo,
)
from sindri.analysis.dependencies import DependencyAnalyzer
from sindri.analysis.architecture import ArchitectureDetector
from sindri.analysis.style import StyleAnalyzer

log = structlog.get_logger()


class CodebaseAnalysisStore:
    """SQLite-backed storage for codebase analysis results."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = self._init_db()
        log.info("codebase_analysis_store_initialized", db_path=db_path)

    def _init_db(self) -> sqlite3.Connection:
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS codebase_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL UNIQUE,
                project_path TEXT,
                analysis_data TEXT NOT NULL,
                primary_language TEXT,
                detected_pattern TEXT,
                project_type TEXT,
                total_files INTEGER DEFAULT 0,
                total_lines INTEGER DEFAULT 0,
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                analysis_version TEXT DEFAULT '1.0'
            );

            CREATE INDEX IF NOT EXISTS idx_codebase_project ON codebase_analysis(project_id);
        """)
        conn.commit()
        return conn

    def store(self, analysis: CodebaseAnalysis) -> int:
        """Store or update analysis results for a project.

        Args:
            analysis: The analysis results to store

        Returns:
            Row ID of the stored analysis
        """
        # Check for existing analysis
        existing = self.get(analysis.project_id)

        analysis_json = analysis.to_json()

        if existing:
            # Update existing
            cursor = self.conn.execute(
                """
                UPDATE codebase_analysis SET
                    project_path = ?,
                    analysis_data = ?,
                    primary_language = ?,
                    detected_pattern = ?,
                    project_type = ?,
                    total_files = ?,
                    total_lines = ?,
                    analyzed_at = CURRENT_TIMESTAMP,
                    analysis_version = ?
                WHERE project_id = ?
                """,
                (
                    analysis.project_path,
                    analysis_json,
                    analysis.primary_language,
                    analysis.architecture.detected_pattern,
                    analysis.architecture.project_type,
                    analysis.total_files,
                    analysis.total_lines,
                    analysis.analysis_version,
                    analysis.project_id,
                )
            )
            self.conn.commit()
            log.info("codebase_analysis_updated", project_id=analysis.project_id)
            return cursor.lastrowid or 1
        else:
            # Insert new
            cursor = self.conn.execute(
                """
                INSERT INTO codebase_analysis (
                    project_id, project_path, analysis_data, primary_language,
                    detected_pattern, project_type, total_files, total_lines,
                    analysis_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis.project_id,
                    analysis.project_path,
                    analysis_json,
                    analysis.primary_language,
                    analysis.architecture.detected_pattern,
                    analysis.architecture.project_type,
                    analysis.total_files,
                    analysis.total_lines,
                    analysis.analysis_version,
                )
            )
            self.conn.commit()
            log.info("codebase_analysis_stored", project_id=analysis.project_id)
            return cursor.lastrowid or 1

    def get(self, project_id: str) -> Optional[CodebaseAnalysis]:
        """Get stored analysis for a project.

        Args:
            project_id: The project identifier

        Returns:
            CodebaseAnalysis if found, None otherwise
        """
        row = self.conn.execute(
            """
            SELECT analysis_data, analyzed_at
            FROM codebase_analysis
            WHERE project_id = ?
            """,
            (project_id,)
        ).fetchone()

        if not row:
            return None

        try:
            analysis = CodebaseAnalysis.from_json(row[0])
            if row[1]:
                analysis.analyzed_at = datetime.fromisoformat(row[1])
            return analysis
        except Exception as e:
            log.error("failed_to_parse_analysis", project_id=project_id, error=str(e))
            return None

    def delete(self, project_id: str) -> bool:
        """Delete analysis for a project.

        Args:
            project_id: The project identifier

        Returns:
            True if deleted, False if not found
        """
        cursor = self.conn.execute(
            "DELETE FROM codebase_analysis WHERE project_id = ?",
            (project_id,)
        )
        self.conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            log.info("codebase_analysis_deleted", project_id=project_id)
        return deleted

    def list_projects(self) -> List[Dict]:
        """List all analyzed projects.

        Returns:
            List of project summaries
        """
        rows = self.conn.execute(
            """
            SELECT project_id, project_path, primary_language, detected_pattern,
                   project_type, total_files, total_lines, analyzed_at
            FROM codebase_analysis
            ORDER BY analyzed_at DESC
            """
        ).fetchall()

        return [
            {
                "project_id": row[0],
                "project_path": row[1],
                "primary_language": row[2],
                "detected_pattern": row[3],
                "project_type": row[4],
                "total_files": row[5],
                "total_lines": row[6],
                "analyzed_at": row[7],
            }
            for row in rows
        ]

    def get_analysis_count(self) -> int:
        """Get the number of stored analyses."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM codebase_analysis")
        return cursor.fetchone()[0]

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


class CodebaseAnalyzer:
    """High-level analyzer that coordinates all analysis types."""

    def __init__(self, db_path: str):
        self.store = CodebaseAnalysisStore(db_path)

    def analyze_project(
        self,
        project_path: str,
        project_id: Optional[str] = None,
        force: bool = False
    ) -> CodebaseAnalysis:
        """Perform full codebase analysis.

        Args:
            project_path: Path to the project directory
            project_id: Optional project identifier (defaults to directory name)
            force: Force re-analysis even if recent analysis exists

        Returns:
            CodebaseAnalysis with all results
        """
        project_path = str(Path(project_path).resolve())
        project_id = project_id or Path(project_path).name

        # Check for existing analysis
        if not force:
            existing = self.store.get(project_id)
            if existing and existing.analyzed_at:
                # Ensure both datetimes are UTC-aware for comparison
                now_utc = datetime.now(timezone.utc)
                analyzed_at = existing.analyzed_at
                if analyzed_at.tzinfo is None:
                    analyzed_at = analyzed_at.replace(tzinfo=timezone.utc)
                age_hours = (now_utc - analyzed_at).total_seconds() / 3600
                if age_hours < 24:  # Use cached if less than 24 hours old
                    log.info("using_cached_analysis",
                            project_id=project_id,
                            age_hours=round(age_hours, 1))
                    return existing

        log.info("starting_codebase_analysis", project_path=project_path, project_id=project_id)

        # Run all analyzers
        dep_analyzer = DependencyAnalyzer(project_path)
        arch_analyzer = ArchitectureDetector(project_path)
        style_analyzer = StyleAnalyzer(project_path)

        dependencies = dep_analyzer.analyze()
        architecture = arch_analyzer.analyze()
        style = style_analyzer.analyze()

        # Count files and lines
        total_files, total_lines, files_by_lang = self._count_files(project_path)

        # Determine primary language
        primary_language = "python"  # Default
        if files_by_lang:
            primary_language = max(files_by_lang.keys(), key=lambda k: files_by_lang[k])

        # Build result
        analysis = CodebaseAnalysis(
            dependencies=dependencies,
            architecture=architecture,
            style=style,
            project_path=project_path,
            project_id=project_id,
            primary_language=primary_language,
            total_files=total_files,
            total_lines=total_lines,
            files_by_language=files_by_lang,
            analyzed_at=datetime.now(timezone.utc),
        )

        # Store result
        self.store.store(analysis)

        log.info(
            "codebase_analysis_complete",
            project_id=project_id,
            total_files=total_files,
            total_lines=total_lines,
            pattern=architecture.detected_pattern,
        )

        return analysis

    def _count_files(self, project_path: str) -> tuple:
        """Count files and lines in project."""
        path = Path(project_path)
        total_files = 0
        total_lines = 0
        files_by_lang = {}

        extensions = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".php": "php",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".md": "markdown",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".sql": "sql",
            ".sh": "shell",
        }

        for file_path in path.rglob("*"):
            if not file_path.is_file():
                continue

            # Skip hidden and build directories
            parts = file_path.relative_to(path).parts
            if any(p.startswith(".") or p in {"__pycache__", "node_modules", "venv", ".venv", "build", "dist"} for p in parts):
                continue

            ext = file_path.suffix.lower()
            if ext in extensions:
                lang = extensions[ext]
                files_by_lang[lang] = files_by_lang.get(lang, 0) + 1
                total_files += 1

                # Count lines
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    total_lines += len(content.splitlines())
                except Exception:
                    pass

        return total_files, total_lines, files_by_lang

    def get_context_for_agent(self, project_id: str) -> Optional[str]:
        """Get formatted analysis context for agent injection.

        Args:
            project_id: The project identifier

        Returns:
            Formatted context string or None if no analysis exists
        """
        analysis = self.store.get(project_id)
        if analysis:
            return analysis.format_context()
        return None

    def close(self):
        """Close resources."""
        self.store.close()
