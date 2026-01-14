"""Semantic memory - codebase indexing."""

import os
from pathlib import Path
from typing import Optional
import hashlib
import structlog

log = structlog.get_logger()


class SemanticMemory:
    """Index and search codebase with embeddings."""

    SUPPORTED_EXTENSIONS = {
        '.py', '.js', '.ts', '.jsx', '.tsx',
        '.md', '.txt', '.yaml', '.yml', '.toml',
        '.json', '.sh', '.bash', '.sql'
    }

    def __init__(
        self,
        vector_store: 'VectorStore',
        embedder: 'LocalEmbedder'
    ):
        self.vectors = vector_store
        self.embedder = embedder
        self._file_hashes: dict[str, str] = {}
        log.info("semantic_memory_initialized")

    def index_directory(
        self,
        path: str,
        namespace: str,
        force: bool = False
    ) -> int:
        """Index all supported files in directory.

        Returns: Number of files indexed
        """
        indexed = 0
        root = Path(path)

        if not root.exists():
            log.warning("index_directory_not_found", path=path)
            return 0

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix not in self.SUPPORTED_EXTENSIONS:
                continue
            # Skip hidden files and directories
            if any(p.startswith('.') for p in file_path.parts):
                continue
            # Skip common directories
            if any(d in file_path.parts for d in ['node_modules', '__pycache__', 'dist', 'build']):
                continue

            try:
                # Check if changed
                content = file_path.read_text(errors='ignore')
                if not content.strip():
                    continue

                file_hash = hashlib.md5(content.encode()).hexdigest()
                rel_path = str(file_path.relative_to(root))

                if not force and self._file_hashes.get(rel_path) == file_hash:
                    continue

                # Index file chunks
                self._index_file(namespace, rel_path, content)
                self._file_hashes[rel_path] = file_hash
                indexed += 1

            except Exception as e:
                log.warning("index_file_failed", path=str(file_path), error=str(e))
                continue

        log.info("index_directory_complete", path=path, indexed=indexed)
        return indexed

    def _index_file(self, namespace: str, path: str, content: str):
        """Index a single file in chunks."""
        # Simple chunking by lines
        lines = content.split('\n')
        chunk_size = 50  # lines per chunk

        for i in range(0, len(lines), chunk_size):
            chunk = '\n'.join(lines[i:i + chunk_size])
            if not chunk.strip():
                continue

            try:
                embedding = self.embedder.embed(chunk)
                self.vectors.insert(
                    namespace=namespace,
                    content=chunk,
                    embedding=embedding,
                    metadata={
                        "path": path,
                        "start_line": i + 1,
                        "end_line": min(i + chunk_size, len(lines))
                    }
                )
            except Exception as e:
                log.warning(
                    "index_chunk_failed",
                    path=path,
                    start_line=i+1,
                    error=str(e)
                )
                continue

    def search(
        self,
        namespace: str,
        query: str,
        limit: int = 10
    ) -> list[tuple[str, dict, float]]:
        """Search for relevant code chunks.

        Returns: List of (content, metadata, similarity_score) tuples
        """
        try:
            query_emb = self.embedder.embed(query)
            results = self.vectors.search(namespace, query_emb, limit)
            # Reorder to (content, metadata, score)
            return [(content, meta, score) for content, score, meta in results]
        except Exception as e:
            log.error("semantic_search_failed", error=str(e))
            return []

    def clear_index(self, namespace: str):
        """Clear all indexed content for a namespace."""
        self.vectors.delete_namespace(namespace)
        self._file_hashes.clear()
        log.info("semantic_index_cleared", namespace=namespace)
