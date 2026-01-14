# Phase 3: Hierarchical Memory System (Muninn)

Named after Odin's raven of memory, this phase implements the three-tier memory system.

## Phase 3 Objectives

1. Working memory (immediate context assembly)
2. Episodic memory (project session history)
3. Semantic memory (codebase indexing with embeddings)
4. Local embeddings with nomic-embed-text
5. sqlite-vec integration for vector search
6. Summarization pipeline

## New Components

```
sindri/
├── memory/
│   ├── __init__.py
│   ├── system.py           # MemorySystem orchestrator
│   ├── working.py          # Working memory (context window)
│   ├── episodic.py         # Session history storage
│   ├── semantic.py         # Codebase embeddings
│   ├── embedder.py         # Local embedding client
│   └── summarizer.py       # Conversation summarization
└── persistence/
    └── vectors.py          # sqlite-vec setup
```

## Memory Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    WORKING MEMORY                           │
│  • Current task + constraints                               │
│  • Last N tool results                                      │
│  • Active conversation                                      │
│  Lifetime: Single agent invocation                          │
│  Storage: In-memory                                         │
└─────────────────────────────────────────────────────────────┘
                              │
                    retrieval queries
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   EPISODIC MEMORY                           │
│  • Completed task summaries                                 │
│  • Key decisions and rationale                              │
│  • Error patterns and resolutions                           │
│  Lifetime: Project duration                                 │
│  Storage: SQLite + JSON                                     │
└─────────────────────────────────────────────────────────────┘
                              │
                    semantic search
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   SEMANTIC MEMORY                           │
│  • Codebase index (files, functions, classes)               │
│  • Documentation embeddings                                 │
│  • Cross-project patterns                                   │
│  Lifetime: Persistent                                       │
│  Storage: sqlite-vec embeddings                             │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Details

### Dependencies Update (pyproject.toml)

```toml
dependencies = [
    # ... existing
    "sqlite-vec>=0.1.0",
    "tiktoken>=0.5.0",      # Token counting
]
```

### Embedder (memory/embedder.py)

```python
"""Local embeddings using Ollama's nomic-embed-text."""

import ollama
from typing import Optional
import numpy as np

class LocalEmbedder:
    """Generate embeddings locally via Ollama."""
    
    def __init__(
        self,
        model: str = "nomic-embed-text",
        host: str = "http://localhost:11434"
    ):
        self.model = model
        self.client = ollama.Client(host=host)
        self._dimension: Optional[int] = None
    
    @property
    def dimension(self) -> int:
        """Get embedding dimension (768 for nomic-embed-text)."""
        if self._dimension is None:
            # Get dimension from a test embedding
            test = self.embed("test")
            self._dimension = len(test)
        return self._dimension
    
    def embed(self, text: str) -> list[float]:
        """Embed a single text."""
        response = self.client.embeddings(
            model=self.model,
            prompt=text
        )
        return response["embedding"]
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts."""
        # Ollama doesn't support batching yet, so sequential
        return [self.embed(t) for t in texts]
    
    def similarity(self, a: list[float], b: list[float]) -> float:
        """Cosine similarity between two embeddings."""
        a_arr = np.array(a)
        b_arr = np.array(b)
        return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))
```

### Vector Storage (persistence/vectors.py)

```python
"""sqlite-vec integration for vector search."""

import sqlite3
import sqlite_vec
import struct
from typing import Optional

def serialize_f32(vector: list[float]) -> bytes:
    """Serialize float vector for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)

class VectorStore:
    """SQLite-based vector storage with sqlite-vec."""
    
    def __init__(self, db_path: str, dimension: int = 768):
        self.db_path = db_path
        self.dimension = dimension
        self.conn = self._init_db()
    
    def _init_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        
        conn.executescript(f"""
            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY,
                namespace TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,  -- JSON
                embedding F32_BLOB({self.dimension})
            );
            
            CREATE INDEX IF NOT EXISTS idx_namespace ON embeddings(namespace);
        """)
        
        return conn
    
    def insert(
        self,
        namespace: str,
        content: str,
        embedding: list[float],
        metadata: Optional[dict] = None
    ) -> int:
        """Insert a vector with content."""
        cursor = self.conn.execute(
            """
            INSERT INTO embeddings (namespace, content, metadata, embedding)
            VALUES (?, ?, ?, ?)
            """,
            (
                namespace,
                content,
                json.dumps(metadata) if metadata else None,
                serialize_f32(embedding)
            )
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def search(
        self,
        namespace: str,
        query_embedding: list[float],
        limit: int = 10
    ) -> list[tuple[str, float, dict]]:
        """Search for similar vectors."""
        results = self.conn.execute(
            """
            SELECT content, metadata,
                   vec_distance_cosine(embedding, ?) as distance
            FROM embeddings
            WHERE namespace = ?
            ORDER BY distance
            LIMIT ?
            """,
            (serialize_f32(query_embedding), namespace, limit)
        ).fetchall()
        
        return [
            (row[0], 1 - row[2], json.loads(row[1]) if row[1] else {})  # Convert distance to similarity
            for row in results
        ]
    
    def delete_namespace(self, namespace: str):
        """Delete all vectors in a namespace."""
        self.conn.execute("DELETE FROM embeddings WHERE namespace = ?", (namespace,))
        self.conn.commit()
```

### Episodic Memory (memory/episodic.py)

```python
"""Episodic memory - project session history."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import json

@dataclass
class Episode:
    id: int
    project_id: str
    event_type: str      # task_complete, decision, error, milestone
    content: str
    metadata: dict
    timestamp: datetime
    embedding: Optional[list[float]] = None

class EpisodicMemory:
    """Stores and retrieves project history."""
    
    def __init__(self, db_path: str, embedder: 'LocalEmbedder'):
        self.db_path = db_path
        self.embedder = embedder
        self.conn = self._init_db()
    
    def _init_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY,
                project_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_project ON episodes(project_id);
        """)
        return conn
    
    def store(
        self,
        project_id: str,
        event_type: str,
        content: str,
        metadata: Optional[dict] = None
    ) -> int:
        """Store an episode."""
        cursor = self.conn.execute(
            """
            INSERT INTO episodes (project_id, event_type, content, metadata)
            VALUES (?, ?, ?, ?)
            """,
            (project_id, event_type, content, json.dumps(metadata) if metadata else None)
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def retrieve_recent(
        self,
        project_id: str,
        limit: int = 10
    ) -> list[Episode]:
        """Get recent episodes for a project."""
        rows = self.conn.execute(
            """
            SELECT id, project_id, event_type, content, metadata, timestamp
            FROM episodes
            WHERE project_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (project_id, limit)
        ).fetchall()
        
        return [
            Episode(
                id=r[0],
                project_id=r[1],
                event_type=r[2],
                content=r[3],
                metadata=json.loads(r[4]) if r[4] else {},
                timestamp=datetime.fromisoformat(r[5])
            )
            for r in rows
        ]
    
    def retrieve_relevant(
        self,
        project_id: str,
        query: str,
        limit: int = 5
    ) -> list[Episode]:
        """Retrieve episodes semantically similar to query."""
        # Get all episodes for project
        episodes = self.retrieve_recent(project_id, limit=100)
        
        if not episodes:
            return []
        
        # Embed query
        query_emb = self.embedder.embed(query)
        
        # Score episodes
        scored = []
        for ep in episodes:
            ep_emb = self.embedder.embed(ep.content)
            score = self.embedder.similarity(query_emb, ep_emb)
            scored.append((ep, score))
        
        # Return top matches
        scored.sort(key=lambda x: x[1], reverse=True)
        return [ep for ep, _ in scored[:limit]]
```

### Semantic Memory (memory/semantic.py)

```python
"""Semantic memory - codebase indexing."""

import os
from pathlib import Path
from typing import Optional
import hashlib

class SemanticMemory:
    """Index and search codebase with embeddings."""
    
    SUPPORTED_EXTENSIONS = {'.py', '.js', '.ts', '.md', '.txt', '.yaml', '.toml', '.json'}
    
    def __init__(
        self,
        vector_store: 'VectorStore',
        embedder: 'LocalEmbedder'
    ):
        self.vectors = vector_store
        self.embedder = embedder
        self._file_hashes: dict[str, str] = {}
    
    def index_directory(
        self,
        path: str,
        namespace: str,
        force: bool = False
    ) -> int:
        """Index all supported files in directory."""
        indexed = 0
        root = Path(path)
        
        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix not in self.SUPPORTED_EXTENSIONS:
                continue
            if any(p.startswith('.') for p in file_path.parts):
                continue  # Skip hidden
            if 'node_modules' in file_path.parts:
                continue
            
            # Check if changed
            content = file_path.read_text(errors='ignore')
            file_hash = hashlib.md5(content.encode()).hexdigest()
            
            rel_path = str(file_path.relative_to(root))
            if not force and self._file_hashes.get(rel_path) == file_hash:
                continue
            
            # Index file chunks
            self._index_file(namespace, rel_path, content)
            self._file_hashes[rel_path] = file_hash
            indexed += 1
        
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
    
    def search(
        self,
        namespace: str,
        query: str,
        limit: int = 10
    ) -> list[tuple[str, dict, float]]:
        """Search for relevant code chunks."""
        query_emb = self.embedder.embed(query)
        results = self.vectors.search(namespace, query_emb, limit)
        return [(content, meta, score) for content, score, meta in results]
```

### Memory System Orchestrator (memory/system.py)

```python
"""Unified memory system - Muninn."""

from dataclasses import dataclass
from typing import Optional
import tiktoken

from sindri.memory.episodic import EpisodicMemory
from sindri.memory.semantic import SemanticMemory
from sindri.memory.embedder import LocalEmbedder
from sindri.persistence.vectors import VectorStore

@dataclass
class MemoryConfig:
    episodic_limit: int = 5
    semantic_limit: int = 10
    max_context_tokens: int = 16384
    working_memory_ratio: float = 0.6  # 60% for conversation

class MuninnMemory:
    """The complete memory system - Odin's raven of memory."""
    
    def __init__(
        self,
        db_path: str,
        config: MemoryConfig = None
    ):
        self.config = config or MemoryConfig()
        self.embedder = LocalEmbedder()
        self.vectors = VectorStore(db_path, self.embedder.dimension)
        self.episodic = EpisodicMemory(db_path, self.embedder)
        self.semantic = SemanticMemory(self.vectors, self.embedder)
        self._tokenizer = tiktoken.get_encoding("cl100k_base")
    
    def build_context(
        self,
        project_id: str,
        current_task: str,
        conversation: list[dict],
        max_tokens: Optional[int] = None
    ) -> list[dict]:
        """Build complete context for an agent invocation."""
        
        max_tokens = max_tokens or self.config.max_context_tokens
        
        # Budget allocation
        working_budget = int(max_tokens * self.config.working_memory_ratio)
        episodic_budget = int(max_tokens * 0.2)
        semantic_budget = int(max_tokens * 0.2)
        
        context_parts = []
        
        # 1. Semantic memory (codebase context)
        semantic_results = self.semantic.search(
            namespace=project_id,
            query=current_task,
            limit=self.config.semantic_limit
        )
        if semantic_results:
            semantic_text = self._format_semantic(semantic_results)
            semantic_text = self._truncate_to_tokens(semantic_text, semantic_budget)
            context_parts.append({
                "role": "user",
                "content": f"[Relevant code from codebase]\n{semantic_text}"
            })
        
        # 2. Episodic memory (past decisions)
        episodes = self.episodic.retrieve_relevant(
            project_id=project_id,
            query=current_task,
            limit=self.config.episodic_limit
        )
        if episodes:
            episodic_text = self._format_episodic(episodes)
            episodic_text = self._truncate_to_tokens(episodic_text, episodic_budget)
            context_parts.append({
                "role": "user",
                "content": f"[Relevant past context]\n{episodic_text}"
            })
        
        # 3. Working memory (recent conversation)
        working_conv = self._fit_conversation(conversation, working_budget)
        
        return context_parts + working_conv
    
    def _format_semantic(self, results: list) -> str:
        parts = []
        for content, meta, score in results:
            parts.append(f"# {meta.get('path', 'unknown')} (lines {meta.get('start_line')}-{meta.get('end_line')})\n{content}")
        return "\n\n".join(parts)
    
    def _format_episodic(self, episodes: list) -> str:
        parts = []
        for ep in episodes:
            parts.append(f"[{ep.event_type}] {ep.content}")
        return "\n".join(parts)
    
    def _count_tokens(self, text: str) -> int:
        return len(self._tokenizer.encode(text))
    
    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        tokens = self._tokenizer.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self._tokenizer.decode(tokens[:max_tokens])
    
    def _fit_conversation(self, conv: list[dict], max_tokens: int) -> list[dict]:
        """Fit conversation into token budget, keeping most recent."""
        result = []
        used = 0
        
        for msg in reversed(conv):
            msg_tokens = self._count_tokens(msg.get("content", ""))
            if used + msg_tokens > max_tokens:
                break
            result.insert(0, msg)
            used += msg_tokens
        
        return result
    
    # Storage operations
    
    def store_episode(self, project_id: str, event_type: str, content: str, metadata: dict = None):
        """Store a new episode."""
        self.episodic.store(project_id, event_type, content, metadata)
    
    def index_project(self, project_path: str, project_id: str):
        """Index a project's codebase."""
        return self.semantic.index_directory(project_path, project_id)
```

### Summarizer (memory/summarizer.py)

```python
"""Summarize conversations for episodic memory."""

from sindri.llm.client import OllamaClient

SUMMARIZE_PROMPT = """Summarize this completed task conversation into a brief episodic memory.

Task: {task}

Conversation:
{conversation}

Provide a concise summary (2-3 sentences) capturing:
1. What was accomplished
2. Key decisions made
3. Any important lessons/errors

Summary:"""

class ConversationSummarizer:
    """Compress conversations into episodic memories."""
    
    def __init__(
        self,
        client: OllamaClient,
        model: str = "phi4:3.8b"  # Small, fast model for summarization
    ):
        self.client = client
        self.model = model
    
    async def summarize(
        self,
        task: str,
        conversation: list[dict]
    ) -> str:
        """Summarize a completed task conversation."""
        
        # Format conversation
        conv_text = "\n".join(
            f"{msg['role']}: {msg['content'][:500]}"
            for msg in conversation
        )
        
        prompt = SUMMARIZE_PROMPT.format(
            task=task,
            conversation=conv_text
        )
        
        response = await self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return response.message.content.strip()
```

## Integration with Core Loop

Update `core/loop.py` to use memory:

```python
class AgentLoop:
    def __init__(self, ..., memory: MuninnMemory):
        self.memory = memory
    
    async def run(self, task: str, model: str) -> LoopResult:
        # Before starting, index project
        await self.memory.index_project(os.getcwd(), session.project_id)
        
        for iteration in range(...):
            # Build context with memory
            messages = self.memory.build_context(
                project_id=session.project_id,
                current_task=task,
                conversation=session.turns,
                max_tokens=agent.max_context_tokens
            )
            
            # ... rest of loop
        
        # After completion, store episode
        summary = await self.summarizer.summarize(task, session.turns)
        self.memory.store_episode(
            project_id=session.project_id,
            event_type="task_complete",
            content=summary,
            metadata={"task": task, "iterations": iteration}
        )
```

## Testing

1. Test embedder generates correct dimensions
2. Test vector search returns similar content
3. Test episodic storage and retrieval
4. Test context building fits token budget
5. Test codebase indexing

```bash
# Ensure nomic-embed-text is pulled
ollama pull nomic-embed-text

# Run tests
pytest tests/test_memory.py -v
```

## Completion Criteria

Phase 3 is complete when:

1. ✅ LocalEmbedder works with nomic-embed-text
2. ✅ VectorStore stores and searches embeddings
3. ✅ EpisodicMemory stores/retrieves episodes
4. ✅ SemanticMemory indexes codebase
5. ✅ MuninnMemory builds context within token budget
6. ✅ Summarizer compresses conversations
7. ✅ Core loop uses memory for context
8. ✅ Tests pass

When complete: `<promise>PHASE3_COMPLETE</promise>`
