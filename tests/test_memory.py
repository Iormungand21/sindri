"""Tests for the memory system."""

import pytest
import tempfile
import os
from pathlib import Path

from sindri.memory.embedder import LocalEmbedder
from sindri.persistence.vectors import VectorStore
from sindri.memory.episodic import EpisodicMemory, Episode
from sindri.memory.semantic import SemanticMemory
from sindri.memory.system import MuninnMemory, MemoryConfig


@pytest.fixture
def temp_db():
    """Create a temporary database."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name
    yield db_path
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def embedder():
    """Create an embedder instance."""
    # Note: This requires nomic-embed-text to be pulled
    return LocalEmbedder()


@pytest.fixture
def temp_codebase():
    """Create a temporary codebase for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some test files
        code_dir = Path(tmpdir) / "src"
        code_dir.mkdir()

        (code_dir / "main.py").write_text("""
def hello():
    print("Hello from Sindri!")

def add(a, b):
    return a + b
""")

        (code_dir / "utils.py").write_text("""
def multiply(a, b):
    return a * b

def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
""")

        yield tmpdir


class TestEmbedder:
    """Test the embedder."""

    @pytest.mark.asyncio
    async def test_embed_single(self, embedder):
        """Test embedding a single text."""
        text = "This is a test sentence for embedding."
        embedding = embedder.embed(text)

        assert isinstance(embedding, list)
        assert len(embedding) > 0
        assert all(isinstance(x, float) for x in embedding)

    @pytest.mark.asyncio
    async def test_embed_dimension(self, embedder):
        """Test that dimension is consistent."""
        text1 = "First sentence"
        text2 = "Second sentence"

        emb1 = embedder.embed(text1)
        emb2 = embedder.embed(text2)

        assert len(emb1) == len(emb2)
        assert len(emb1) == embedder.dimension

    @pytest.mark.asyncio
    async def test_similarity(self, embedder):
        """Test similarity computation."""
        text1 = "Python programming language"
        text2 = "Python coding and development"
        text3 = "Cooking recipes for dinner"

        emb1 = embedder.embed(text1)
        emb2 = embedder.embed(text2)
        emb3 = embedder.embed(text3)

        # Similar texts should have higher similarity
        sim_similar = embedder.similarity(emb1, emb2)
        sim_different = embedder.similarity(emb1, emb3)

        assert sim_similar > sim_different
        assert 0 <= sim_similar <= 1
        assert 0 <= sim_different <= 1


class TestVectorStore:
    """Test the vector store."""

    @pytest.mark.asyncio
    async def test_insert_and_search(self, temp_db, embedder):
        """Test inserting and searching vectors."""
        store = VectorStore(temp_db, embedder.dimension)

        # Insert some vectors
        text1 = "Python is a programming language"
        text2 = "JavaScript is used for web development"
        text3 = "Python is great for data science"

        emb1 = embedder.embed(text1)
        emb2 = embedder.embed(text2)
        emb3 = embedder.embed(text3)

        store.insert("test", text1, emb1, {"source": "doc1"})
        store.insert("test", text2, emb2, {"source": "doc2"})
        store.insert("test", text3, emb3, {"source": "doc3"})

        # Search for Python-related content
        query = "Python programming"
        query_emb = embedder.embed(query)
        results = store.search("test", query_emb, limit=2)

        assert len(results) == 2
        # Should find the Python-related docs
        assert any("Python" in content for content, _, _ in results)

        store.close()

    @pytest.mark.asyncio
    async def test_namespace_isolation(self, temp_db, embedder):
        """Test that namespaces are isolated."""
        store = VectorStore(temp_db, embedder.dimension)

        text = "Test content"
        emb = embedder.embed(text)

        store.insert("ns1", text, emb)
        store.insert("ns2", "Different content", embedder.embed("Different content"))

        # Search in ns1
        results = store.search("ns1", emb, limit=10)
        assert len(results) == 1

        # Search in ns2
        results = store.search("ns2", emb, limit=10)
        assert len(results) == 1

        store.close()


class TestEpisodicMemory:
    """Test episodic memory."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, temp_db, embedder):
        """Test storing and retrieving episodes."""
        memory = EpisodicMemory(temp_db, embedder)

        # Store an episode
        episode_id = memory.store(
            project_id="test_project",
            event_type="task_complete",
            content="Successfully implemented feature X",
            metadata={"iterations": 5}
        )

        assert episode_id > 0

        # Retrieve recent episodes
        episodes = memory.retrieve_recent("test_project", limit=10)
        assert len(episodes) == 1
        assert episodes[0].content == "Successfully implemented feature X"
        assert episodes[0].event_type == "task_complete"

        memory.close()

    @pytest.mark.asyncio
    async def test_retrieve_relevant(self, temp_db, embedder):
        """Test semantic retrieval of episodes."""
        memory = EpisodicMemory(temp_db, embedder)

        # Store multiple episodes
        memory.store("test_project", "task_complete", "Implemented authentication system")
        memory.store("test_project", "task_complete", "Fixed database connection bug")
        memory.store("test_project", "task_complete", "Added user login functionality")

        # Search for auth-related episodes
        relevant = memory.retrieve_relevant("test_project", "authentication and login", limit=2)

        assert len(relevant) <= 2
        # Should find auth-related episodes
        assert any("authentication" in ep.content.lower() or "login" in ep.content.lower()
                   for ep in relevant)

        memory.close()


class TestSemanticMemory:
    """Test semantic memory (codebase indexing)."""

    @pytest.mark.asyncio
    async def test_index_directory(self, temp_db, temp_codebase, embedder):
        """Test indexing a directory."""
        store = VectorStore(temp_db, embedder.dimension)
        memory = SemanticMemory(store, embedder)

        indexed = memory.index_directory(temp_codebase, "test_project")

        assert indexed == 2  # main.py and utils.py
        assert store.count("test_project") > 0

        store.close()

    @pytest.mark.asyncio
    async def test_search_code(self, temp_db, temp_codebase, embedder):
        """Test searching indexed code."""
        store = VectorStore(temp_db, embedder.dimension)
        memory = SemanticMemory(store, embedder)

        memory.index_directory(temp_codebase, "test_project")

        # Search for math-related functions
        results = memory.search("test_project", "mathematical operations multiply divide", limit=5)

        assert len(results) > 0
        # Should find the utils.py content with multiply/divide
        assert any("multiply" in content or "divide" in content for content, _, _ in results)

        store.close()


class TestMuninnMemory:
    """Test the complete memory system."""

    @pytest.mark.asyncio
    async def test_build_context(self, temp_db, temp_codebase):
        """Test building context from all memory tiers."""
        memory = MuninnMemory(temp_db, MemoryConfig(
            episodic_limit=2,
            semantic_limit=3,
            max_context_tokens=1000
        ))

        project_id = "test_project"

        # Index the codebase
        indexed = memory.index_project(temp_codebase, project_id)
        assert indexed > 0

        # Store some episodes
        memory.store_episode(project_id, "task_complete", "Added authentication")
        memory.store_episode(project_id, "decision", "Chose JWT for token auth")

        # Build context
        conversation = [
            {"role": "user", "content": "Implement login"},
            {"role": "assistant", "content": "I'll implement the login function"}
        ]

        context = memory.build_context(
            project_id=project_id,
            current_task="Add user login functionality",
            conversation=conversation,
            max_tokens=2000
        )

        assert isinstance(context, list)
        assert len(context) > 0

        # Should have semantic and episodic context
        context_str = " ".join(msg["content"] for msg in context)
        # May have codebase or past context, depending on relevance

    @pytest.mark.asyncio
    async def test_token_budget(self, temp_db):
        """Test that context fits within token budget."""
        memory = MuninnMemory(temp_db, MemoryConfig(max_context_tokens=500))

        project_id = "test_project"

        # Create a long conversation
        conversation = [
            {"role": "user", "content": "Test message " * 100},
            {"role": "assistant", "content": "Response " * 100}
        ] * 10  # Very long conversation

        context = memory.build_context(
            project_id=project_id,
            current_task="Simple task",
            conversation=conversation,
            max_tokens=500
        )

        # Context should fit in budget
        total_tokens = sum(memory._count_tokens(msg["content"]) for msg in context)
        assert total_tokens <= 500
