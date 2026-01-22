"""Global memory store for cross-project embeddings (Phase 8.4).

Provides cross-project semantic search by storing embeddings from all
registered projects in a unified database.

Extended with Multi-Project Workspace Index (ROADMAP Item 4):
- Incremental indexing with MD5-based change detection
- Active project context for agent prompts
- Per-project embedder settings support
"""

import fnmatch
import hashlib
import sqlite3
import sqlite_vec
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
import structlog

from sindri.memory.embedder import LocalEmbedder
from sindri.memory.projects import ProjectRegistry, ProjectEmbedderSettings

log = structlog.get_logger()


def serialize_f32(vector: list[float]) -> bytes:
    """Serialize float vector for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)


@dataclass
class CrossProjectResult:
    """Result from cross-project search."""

    content: str
    project_path: str
    project_name: str
    file_path: str
    start_line: int
    end_line: int
    similarity: float
    tags: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "project_path": self.project_path,
            "project_name": self.project_name,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "similarity": self.similarity,
            "tags": self.tags,
        }


@dataclass
class IncrementalIndexResult:
    """Result of incremental project indexing (ROADMAP Item 4)."""

    project_path: str
    files_indexed: int = 0
    files_skipped: int = 0  # Unchanged files
    files_failed: int = 0
    files_removed: int = 0  # Deleted files
    chunks_added: int = 0
    chunks_removed: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "project_path": self.project_path,
            "files_indexed": self.files_indexed,
            "files_skipped": self.files_skipped,
            "files_failed": self.files_failed,
            "files_removed": self.files_removed,
            "chunks_added": self.chunks_added,
            "chunks_removed": self.chunks_removed,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
        }


class GlobalMemoryStore:
    """Cross-project semantic memory storage.

    Stores embeddings from all registered projects in a unified database,
    enabling cross-project search and pattern discovery.

    Database: ~/.sindri/global_memory.db
    """

    SUPPORTED_EXTENSIONS = {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".md",
        ".txt",
        ".yaml",
        ".yml",
        ".toml",
        ".json",
        ".sh",
        ".bash",
        ".sql",
    }

    def __init__(
        self,
        db_path: Optional[Path] = None,
        embedder: Optional[LocalEmbedder] = None,
        registry: Optional[ProjectRegistry] = None,
        dimension: int = 768,
    ):
        """Initialize global memory store.

        Args:
            db_path: Path to database. Defaults to ~/.sindri/global_memory.db
            embedder: LocalEmbedder instance. Created if not provided.
            registry: ProjectRegistry instance. Created if not provided.
            dimension: Embedding dimension (default 768 for nomic-embed-text)
        """
        if db_path is None:
            db_path = Path.home() / ".sindri" / "global_memory.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.dimension = dimension
        self.embedder = embedder or LocalEmbedder()
        self.registry = registry or ProjectRegistry()
        self.conn = self._init_db()
        log.info("global_memory_initialized", db_path=str(db_path))

    def _init_db(self) -> sqlite3.Connection:
        """Initialize database schema."""
        conn = sqlite3.connect(str(self.db_path))
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS global_embeddings (
                id INTEGER PRIMARY KEY,
                project_path TEXT NOT NULL,
                file_path TEXT NOT NULL,
                content TEXT NOT NULL,
                start_line INTEGER,
                end_line INTEGER,
                embedding F32_BLOB({self.dimension}),
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_global_project
            ON global_embeddings(project_path);

            CREATE INDEX IF NOT EXISTS idx_global_file
            ON global_embeddings(project_path, file_path);

            -- Project metadata table
            CREATE TABLE IF NOT EXISTS project_index_meta (
                project_path TEXT PRIMARY KEY,
                file_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- File index state for incremental indexing (ROADMAP Item 4)
            CREATE TABLE IF NOT EXISTS file_index_state (
                id INTEGER PRIMARY KEY,
                project_path TEXT NOT NULL,
                file_path TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                chunk_count INTEGER DEFAULT 0,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_path, file_path)
            );

            CREATE INDEX IF NOT EXISTS idx_file_state_project
            ON file_index_state(project_path);

            -- Indexer state for background indexer progress tracking
            CREATE TABLE IF NOT EXISTS indexer_state (
                id INTEGER PRIMARY KEY,
                project_path TEXT NOT NULL UNIQUE,
                status TEXT DEFAULT 'idle',
                progress_files INTEGER DEFAULT 0,
                progress_chunks INTEGER DEFAULT 0,
                total_files INTEGER DEFAULT 0,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT
            );
        """
        )
        conn.commit()
        return conn

    def index_project(self, project_path: str, force: bool = False) -> int:
        """Index a project into global memory.

        Args:
            project_path: Path to project directory
            force: Force re-index even if already indexed

        Returns:
            Number of chunks indexed
        """
        path_obj = Path(project_path).resolve()
        if not path_obj.exists():
            log.warning("project_not_found", path=project_path)
            return 0

        normalized_path = str(path_obj)

        # Check if already indexed (unless force)
        if not force:
            existing = self.conn.execute(
                "SELECT chunk_count FROM project_index_meta WHERE project_path = ?",
                (normalized_path,),
            ).fetchone()
            if existing and existing[0] > 0:
                log.info(
                    "project_already_indexed", path=normalized_path, chunks=existing[0]
                )
                return existing[0]

        # Clear existing embeddings for this project
        self._clear_project(normalized_path)

        # Index files
        chunk_count = 0
        file_count = 0

        for file_path in path_obj.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix not in self.SUPPORTED_EXTENSIONS:
                continue
            # Skip hidden files and directories
            if any(p.startswith(".") for p in file_path.parts):
                continue
            # Skip common directories
            if any(
                d in file_path.parts
                for d in [
                    "node_modules",
                    "__pycache__",
                    "dist",
                    "build",
                    "venv",
                    ".venv",
                ]
            ):
                continue

            try:
                content = file_path.read_text(errors="ignore")
                if not content.strip():
                    continue

                rel_path = str(file_path.relative_to(path_obj))
                chunks = self._index_file(normalized_path, rel_path, content)
                chunk_count += chunks
                file_count += 1

            except Exception as e:
                log.warning(
                    "global_index_file_failed", path=str(file_path), error=str(e)
                )
                continue

        # Update metadata
        self.conn.execute(
            """
            INSERT OR REPLACE INTO project_index_meta
            (project_path, file_count, chunk_count, indexed_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (normalized_path, file_count, chunk_count),
        )
        self.conn.commit()

        # Update registry
        self.registry.set_indexed(normalized_path, True, file_count)

        log.info(
            "global_project_indexed",
            path=normalized_path,
            files=file_count,
            chunks=chunk_count,
        )

        return chunk_count

    def _index_file(self, project_path: str, file_path: str, content: str) -> int:
        """Index a single file in chunks.

        Returns: Number of chunks indexed
        """
        lines = content.split("\n")
        chunk_size = 50  # lines per chunk
        chunks_indexed = 0

        for i in range(0, len(lines), chunk_size):
            chunk = "\n".join(lines[i : i + chunk_size])
            if not chunk.strip():
                continue

            try:
                embedding = self.embedder.embed(chunk)
                self.conn.execute(
                    """
                    INSERT INTO global_embeddings
                    (project_path, file_path, content, start_line, end_line, embedding)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_path,
                        file_path,
                        chunk,
                        i + 1,
                        min(i + chunk_size, len(lines)),
                        serialize_f32(embedding),
                    ),
                )
                chunks_indexed += 1
            except Exception as e:
                log.warning(
                    "global_chunk_failed", file=file_path, start=i + 1, error=str(e)
                )
                continue

        self.conn.commit()
        return chunks_indexed

    def _clear_project(self, project_path: str):
        """Clear all embeddings for a project."""
        self.conn.execute(
            "DELETE FROM global_embeddings WHERE project_path = ?", (project_path,)
        )
        self.conn.commit()
        log.debug("global_project_cleared", path=project_path)

    def search(
        self,
        query: str,
        limit: int = 10,
        project_paths: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        exclude_current: Optional[str] = None,
    ) -> List[CrossProjectResult]:
        """Search across all indexed projects.

        Args:
            query: Search query text
            limit: Maximum results to return
            project_paths: Optional list of project paths to search (default: all enabled)
            tags: Optional tags to filter projects by
            exclude_current: Optional project path to exclude (e.g., current project)

        Returns:
            List of CrossProjectResult objects
        """
        try:
            query_embedding = self.embedder.embed(query)
        except Exception as e:
            log.error("global_search_embed_failed", error=str(e))
            return []

        # Determine which projects to search
        if project_paths is None:
            projects = self.registry.list_projects(enabled_only=True, tags=tags)
            project_paths = [p.path for p in projects]

        if exclude_current and exclude_current in project_paths:
            project_paths = [p for p in project_paths if p != exclude_current]

        if not project_paths:
            log.debug("global_search_no_projects")
            return []

        # Build query with project filter
        placeholders = ",".join("?" for _ in project_paths)
        query_sql = f"""
            SELECT
                ge.content,
                ge.project_path,
                ge.file_path,
                ge.start_line,
                ge.end_line,
                vec_distance_cosine(ge.embedding, ?) as distance
            FROM global_embeddings ge
            WHERE ge.project_path IN ({placeholders})
            ORDER BY distance
            LIMIT ?
        """

        params = [serialize_f32(query_embedding)] + project_paths + [limit]

        try:
            rows = self.conn.execute(query_sql, params).fetchall()
        except Exception as e:
            log.error("global_search_failed", error=str(e))
            return []

        # Build results with project info
        results = []
        for row in rows:
            content, project_path, file_path, start_line, end_line, distance = row
            similarity = 1 - distance

            # Get project info from registry
            project = self.registry.get_project(project_path)
            project_name = project.name if project else Path(project_path).name
            project_tags = project.tags if project else []

            results.append(
                CrossProjectResult(
                    content=content,
                    project_path=project_path,
                    project_name=project_name,
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    similarity=similarity,
                    tags=project_tags,
                )
            )

        log.debug("global_search_complete", query=query[:50], results=len(results))

        return results

    def search_by_tags(
        self, query: str, tags: List[str], limit: int = 10
    ) -> List[CrossProjectResult]:
        """Search only in projects with specific tags.

        Args:
            query: Search query text
            tags: Tags to filter projects by
            limit: Maximum results

        Returns:
            List of CrossProjectResult objects
        """
        return self.search(query, limit=limit, tags=tags)

    def index_all_projects(self, force: bool = False) -> Dict[str, int]:
        """Index all registered and enabled projects.

        Args:
            force: Force re-index all projects

        Returns:
            Dict mapping project path to chunk count indexed
        """
        projects = self.registry.list_projects(enabled_only=True)
        results = {}

        for project in projects:
            try:
                chunks = self.index_project(project.path, force=force)
                results[project.path] = chunks
            except Exception as e:
                log.error("index_all_project_failed", path=project.path, error=str(e))
                results[project.path] = 0

        log.info(
            "index_all_complete",
            projects=len(projects),
            total_chunks=sum(results.values()),
        )

        return results

    def remove_project(self, project_path: str) -> bool:
        """Remove a project from global memory.

        Args:
            project_path: Path to project

        Returns:
            True if project was removed
        """
        normalized = str(Path(project_path).resolve())

        self.conn.execute(
            "DELETE FROM global_embeddings WHERE project_path = ?", (normalized,)
        )
        self.conn.execute(
            "DELETE FROM project_index_meta WHERE project_path = ?", (normalized,)
        )
        self.conn.commit()

        log.info("global_project_removed", path=normalized)
        return True

    def get_stats(self) -> Dict[str, Any]:
        """Get global memory statistics.

        Returns:
            Dict with project count, chunk count, etc.
        """
        project_count = self.conn.execute(
            "SELECT COUNT(*) FROM project_index_meta"
        ).fetchone()[0]

        total_chunks = (
            self.conn.execute(
                "SELECT SUM(chunk_count) FROM project_index_meta"
            ).fetchone()[0]
            or 0
        )

        total_files = (
            self.conn.execute(
                "SELECT SUM(file_count) FROM project_index_meta"
            ).fetchone()[0]
            or 0
        )

        return {
            "indexed_projects": project_count,
            "total_chunks": total_chunks,
            "total_files": total_files,
            "registered_projects": self.registry.get_project_count(),
            "enabled_projects": self.registry.get_enabled_project_count(),
        }

    def get_project_stats(self, project_path: str) -> Optional[Dict[str, Any]]:
        """Get stats for a specific project.

        Args:
            project_path: Path to project

        Returns:
            Dict with file count, chunk count, indexed_at, or None if not found
        """
        normalized = str(Path(project_path).resolve())

        row = self.conn.execute(
            """
            SELECT file_count, chunk_count, indexed_at
            FROM project_index_meta
            WHERE project_path = ?
            """,
            (normalized,),
        ).fetchone()

        if not row:
            return None

        return {
            "file_count": row[0],
            "chunk_count": row[1],
            "indexed_at": row[2],
        }

    def format_search_context(
        self, results: List[CrossProjectResult], max_tokens: int = 2000
    ) -> str:
        """Format search results for agent context injection.

        Args:
            results: List of search results
            max_tokens: Approximate token limit

        Returns:
            Formatted string for context injection
        """
        if not results:
            return ""

        parts = []
        estimated_tokens = 0

        for result in results:
            header = (
                f"# [{result.project_name}] {result.file_path} "
                f"(lines {result.start_line}-{result.end_line}, "
                f"similarity: {result.similarity:.2f})"
            )
            chunk_text = f"{header}\n{result.content}\n"

            # Rough token estimate (4 chars per token)
            chunk_tokens = len(chunk_text) // 4

            if estimated_tokens + chunk_tokens > max_tokens:
                break

            parts.append(chunk_text)
            estimated_tokens += chunk_tokens

        return "\n".join(parts)

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    # === Incremental Indexing Methods (ROADMAP Item 4) ===

    def _compute_file_hash(self, content: str) -> str:
        """Compute MD5 hash of file content for change detection."""
        return hashlib.md5(content.encode("utf-8", errors="ignore")).hexdigest()

    def _get_file_hash(self, project_path: str, file_path: str) -> Optional[str]:
        """Get stored hash for a file, if any."""
        row = self.conn.execute(
            "SELECT content_hash FROM file_index_state WHERE project_path = ? AND file_path = ?",
            (project_path, file_path),
        ).fetchone()
        return row[0] if row else None

    def _set_file_hash(
        self, project_path: str, file_path: str, content_hash: str, chunk_count: int
    ):
        """Store or update hash for a file."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO file_index_state
            (project_path, file_path, content_hash, chunk_count, indexed_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (project_path, file_path, content_hash, chunk_count),
        )

    def _get_indexed_files(self, project_path: str) -> Dict[str, str]:
        """Get all indexed files and their hashes for a project."""
        rows = self.conn.execute(
            "SELECT file_path, content_hash FROM file_index_state WHERE project_path = ?",
            (project_path,),
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def _remove_file_index(self, project_path: str, file_path: str) -> int:
        """Remove index data for a deleted file. Returns chunks removed."""
        # Count chunks to be removed
        row = self.conn.execute(
            "SELECT COUNT(*) FROM global_embeddings WHERE project_path = ? AND file_path = ?",
            (project_path, file_path),
        ).fetchone()
        chunks_removed = row[0] if row else 0

        # Remove embeddings
        self.conn.execute(
            "DELETE FROM global_embeddings WHERE project_path = ? AND file_path = ?",
            (project_path, file_path),
        )
        # Remove file state
        self.conn.execute(
            "DELETE FROM file_index_state WHERE project_path = ? AND file_path = ?",
            (project_path, file_path),
        )
        return chunks_removed

    def _should_include_file(
        self, file_path: Path, rel_path: str, settings: Optional[ProjectEmbedderSettings]
    ) -> bool:
        """Check if a file should be included based on settings.

        Args:
            file_path: Absolute path to the file
            rel_path: Path relative to project root (for pattern matching)
            settings: Per-project embedder settings

        Pattern behavior:
            - If include_patterns is set, it acts as a whitelist - only matching
              files are included (exclude_patterns and extensions are still checked)
            - If include_patterns is not set, fall through to exclude/extension checks
        """
        # Patterns are matched against project-relative paths (e.g., "src/*", "*.py")

        # Check include patterns first - they act as a whitelist when set
        if settings and settings.include_patterns:
            include_matched = False
            for pattern in settings.include_patterns:
                if fnmatch.fnmatch(rel_path, pattern):
                    include_matched = True
                    break
            # If include_patterns is configured but nothing matched, exclude the file
            if not include_matched:
                return False

        # Check exclude patterns
        if settings and settings.exclude_patterns:
            for pattern in settings.exclude_patterns:
                if fnmatch.fnmatch(rel_path, pattern):
                    return False

        # Check extension
        extensions = self.SUPPORTED_EXTENSIONS
        if settings and settings.file_extensions:
            extensions = set(settings.file_extensions)

        return file_path.suffix in extensions

    def _index_file_with_settings(
        self,
        project_path: str,
        file_path: str,
        content: str,
        settings: Optional[ProjectEmbedderSettings],
    ) -> int:
        """Index a file using per-project settings.

        Returns: Number of chunks indexed
        """
        lines = content.split("\n")

        # Use settings or defaults
        chunk_size = settings.chunk_size_lines if settings else 50
        max_chunk_chars = settings.max_chunk_chars if settings else 2000
        max_line_chars = settings.max_line_chars if settings else 500

        chunks_indexed = 0

        for i in range(0, len(lines), chunk_size):
            chunk_lines = lines[i : i + chunk_size]

            # Truncate long lines
            truncated_lines = []
            for line in chunk_lines:
                if len(line) > max_line_chars:
                    truncated_lines.append(line[:max_line_chars] + " [truncated]")
                else:
                    truncated_lines.append(line)

            chunk = "\n".join(truncated_lines)

            # Skip empty chunks
            if not chunk.strip():
                continue

            # Truncate chunk if too long
            if len(chunk) > max_chunk_chars:
                chunk = chunk[:max_chunk_chars] + "\n[chunk truncated]"

            try:
                embedding = self.embedder.embed(chunk)
                self.conn.execute(
                    """
                    INSERT INTO global_embeddings
                    (project_path, file_path, content, start_line, end_line, embedding)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_path,
                        file_path,
                        chunk,
                        i + 1,
                        min(i + chunk_size, len(lines)),
                        serialize_f32(embedding),
                    ),
                )
                chunks_indexed += 1
            except Exception as e:
                log.warning(
                    "global_chunk_failed", file=file_path, start=i + 1, error=str(e)
                )
                continue

        return chunks_indexed

    def index_project_incremental(
        self,
        project_path: str,
        force: bool = False,
        on_file_indexed: Optional[Callable[[str, str, int, bool], None]] = None,
    ) -> IncrementalIndexResult:
        """Incrementally index a project, only processing changed files.

        Uses MD5 hashing to detect file changes and only re-indexes modified files.
        Removes index data for deleted files.

        Args:
            project_path: Path to project directory
            force: Force re-index all files (ignores hashes)
            on_file_indexed: Optional callback called after each file is processed.
                Signature: (project_path, file_path, chunks_created, skipped) -> None

        Returns:
            IncrementalIndexResult with detailed statistics
        """
        import time

        start_time = time.time()
        path_obj = Path(project_path).resolve()

        if not path_obj.exists():
            return IncrementalIndexResult(
                project_path=str(path_obj),
                error=f"Project path does not exist: {project_path}",
            )

        normalized_path = str(path_obj)

        # Get project settings
        project = self.registry.get_project(normalized_path)
        settings = project.embedder_settings if project else None

        # Get currently indexed files
        indexed_files = self._get_indexed_files(normalized_path)

        result = IncrementalIndexResult(project_path=normalized_path)

        # Track files we've seen (for detecting deletions)
        seen_files: set[str] = set()

        # Scan project files
        for file_path in path_obj.rglob("*"):
            if not file_path.is_file():
                continue

            # Skip hidden files and directories
            if any(p.startswith(".") for p in file_path.parts):
                continue

            # Skip common directories
            if any(
                d in file_path.parts
                for d in [
                    "node_modules",
                    "__pycache__",
                    "dist",
                    "build",
                    "venv",
                    ".venv",
                ]
            ):
                continue

            rel_path = str(file_path.relative_to(path_obj))

            # Check if file should be included (pass rel_path for pattern matching)
            if not self._should_include_file(file_path, rel_path, settings):
                continue

            seen_files.add(rel_path)

            try:
                content = file_path.read_text(errors="ignore")
                if not content.strip():
                    continue

                current_hash = self._compute_file_hash(content)
                stored_hash = indexed_files.get(rel_path)

                # Skip if unchanged (unless force)
                if not force and stored_hash == current_hash:
                    result.files_skipped += 1
                    # Notify callback for skipped file
                    if on_file_indexed:
                        on_file_indexed(normalized_path, rel_path, 0, True)
                    continue

                # Remove old chunks if file exists and changed
                if rel_path in indexed_files:
                    chunks_removed = self._remove_file_index(normalized_path, rel_path)
                    result.chunks_removed += chunks_removed

                # Index file
                chunks = self._index_file_with_settings(
                    normalized_path, rel_path, content, settings
                )
                self._set_file_hash(normalized_path, rel_path, current_hash, chunks)

                result.files_indexed += 1
                result.chunks_added += chunks

                # Notify callback for indexed file
                if on_file_indexed:
                    on_file_indexed(normalized_path, rel_path, chunks, False)

            except Exception as e:
                log.warning(
                    "incremental_index_file_failed", path=str(file_path), error=str(e)
                )
                result.files_failed += 1
                continue

        # Remove deleted files
        for rel_path in indexed_files.keys():
            if rel_path not in seen_files:
                chunks_removed = self._remove_file_index(normalized_path, rel_path)
                result.chunks_removed += chunks_removed
                result.files_removed += 1

        # Update metadata
        total_files = result.files_indexed + result.files_skipped
        total_chunks = self.conn.execute(
            "SELECT COUNT(*) FROM global_embeddings WHERE project_path = ?",
            (normalized_path,),
        ).fetchone()[0]

        self.conn.execute(
            """
            INSERT OR REPLACE INTO project_index_meta
            (project_path, file_count, chunk_count, indexed_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (normalized_path, total_files, total_chunks),
        )
        self.conn.commit()

        # Update registry
        if project:
            self.registry.set_indexed(normalized_path, True, total_files)

        result.duration_seconds = time.time() - start_time

        log.info(
            "incremental_index_complete",
            path=normalized_path,
            files_indexed=result.files_indexed,
            files_skipped=result.files_skipped,
            files_removed=result.files_removed,
            chunks_added=result.chunks_added,
            chunks_removed=result.chunks_removed,
            duration=f"{result.duration_seconds:.2f}s",
        )

        return result

    # === Active Project Context Methods (ROADMAP Item 4) ===

    def search_active_projects(
        self,
        query: str,
        limit: int = 10,
        exclude_current: Optional[str] = None,
    ) -> List[CrossProjectResult]:
        """Search only in active (pinned) projects.

        Active projects are those marked with active=True in the registry,
        intended for immediate context inclusion in agent prompts.

        Args:
            query: Search query text
            limit: Maximum results to return
            exclude_current: Optional project path to exclude

        Returns:
            List of CrossProjectResult objects from active projects
        """
        active_projects = self.registry.list_active_projects()

        if not active_projects:
            log.debug("no_active_projects_for_search")
            return []

        project_paths = [p.path for p in active_projects]

        if exclude_current:
            # Normalize and exclude
            normalized_current = str(Path(exclude_current).resolve())
            project_paths = [p for p in project_paths if p != normalized_current]

        if not project_paths:
            return []

        return self.search(query, limit=limit, project_paths=project_paths)

    def get_active_project_context(
        self,
        query: str,
        max_tokens: int = 2000,
        exclude_current: Optional[str] = None,
    ) -> str:
        """Get formatted context from active projects for agent injection.

        Searches active projects and formats results for inclusion in agent prompts.

        Args:
            query: Search query (usually the current task description)
            max_tokens: Approximate token limit for the context
            exclude_current: Optional project path to exclude

        Returns:
            Formatted string suitable for agent context injection
        """
        # Calculate limit based on token budget (roughly 100 tokens per result)
        estimated_results_per_token = max_tokens // 100
        limit = max(5, min(20, estimated_results_per_token))

        results = self.search_active_projects(
            query, limit=limit, exclude_current=exclude_current
        )

        if not results:
            return ""

        # Format with header
        header = "## Cross-Project Context (from active projects)\n\n"
        content = self.format_search_context(results, max_tokens=max_tokens - 50)

        if not content:
            return ""

        return header + content

    def get_active_project_stats(self) -> Dict[str, Any]:
        """Get statistics about active projects.

        Returns:
            Dict with active project counts and details
        """
        active_projects = self.registry.list_active_projects()

        stats = {
            "active_count": len(active_projects),
            "active_indexed_count": sum(1 for p in active_projects if p.indexed),
            "active_total_files": sum(p.file_count for p in active_projects),
            "projects": [
                {
                    "name": p.name,
                    "path": p.path,
                    "indexed": p.indexed,
                    "file_count": p.file_count,
                    "priority": p.index_priority,
                }
                for p in active_projects
            ],
        }

        return stats
