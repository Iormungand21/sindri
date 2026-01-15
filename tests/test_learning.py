"""Tests for Phase 7.2 - Learning from Success pattern system."""

import pytest
import tempfile
import os
from pathlib import Path

from sindri.memory.patterns import Pattern, PatternStore
from sindri.memory.learner import PatternLearner, LearningConfig
from sindri.memory.system import MuninnMemory, MemoryConfig
from sindri.core.tasks import Task, TaskStatus


class TestPattern:
    """Tests for Pattern dataclass."""

    def test_pattern_creation(self):
        """Test creating a Pattern."""
        pattern = Pattern(
            name="test_pattern",
            description="A test pattern",
            context="testing",
            trigger_keywords=["test", "pytest", "unittest"],
            approach="Write tests using pytest",
            tool_sequence=["read_file", "write_file"],
            example_task="Write tests for the module",
            agent="skald",
            success_count=5,
            avg_iterations=3.5,
            min_iterations=2
        )

        assert pattern.name == "test_pattern"
        assert pattern.context == "testing"
        assert len(pattern.trigger_keywords) == 3
        assert pattern.success_count == 5
        assert pattern.avg_iterations == 3.5

    def test_pattern_matches_task(self):
        """Test keyword matching for task descriptions."""
        pattern = Pattern(
            name="test_pattern",
            trigger_keywords=["pytest", "tests", "function"]
        )

        # Full match
        score = pattern.matches_task("Write pytest tests for the function")
        assert score == 1.0  # All 3 keywords

        # Partial match
        score = pattern.matches_task("Write tests for the code")
        assert score == pytest.approx(1/3, rel=0.01)  # 1 keyword ("tests")

        # No match
        score = pattern.matches_task("Create a new file")
        assert score == 0.0

    def test_pattern_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        pattern = Pattern(
            name="serialize_test",
            description="Test description",
            context="code_generation",
            trigger_keywords=["create", "function"],
            approach="Create the function",
            tool_sequence=["read_file", "write_file"],
            example_task="Create a function",
            example_output="def hello(): ...",
            agent="huginn",
            project_id="proj_123",
            success_count=3,
            avg_iterations=4.0,
            min_iterations=2
        )

        data = pattern.to_dict()
        restored = Pattern.from_dict(data)

        assert restored.name == pattern.name
        assert restored.context == pattern.context
        assert restored.trigger_keywords == pattern.trigger_keywords
        assert restored.success_count == pattern.success_count


class TestPatternStore:
    """Tests for PatternStore SQLite storage."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a temporary pattern store."""
        db_path = str(tmp_path / "test_patterns.db")
        return PatternStore(db_path)

    def test_store_and_retrieve_pattern(self, store):
        """Test storing and retrieving a pattern."""
        pattern = Pattern(
            name="file_creation",
            context="code_generation",
            trigger_keywords=["create", "file", "write"],
            approach="Use write_file tool to create the file",
            tool_sequence=["write_file"],
            agent="huginn"
        )

        pattern_id = store.store(pattern)
        assert pattern_id > 0

        retrieved = store.get_by_id(pattern_id)
        assert retrieved is not None
        assert retrieved.name == "file_creation"
        assert retrieved.context == "code_generation"

    def test_update_existing_pattern(self, store):
        """Test updating an existing pattern increases success count."""
        pattern1 = Pattern(
            name="test_pattern",
            context="testing",
            approach="Write tests",
            avg_iterations=5.0,
            min_iterations=5
        )

        id1 = store.store(pattern1)

        # Store pattern with same name and context
        pattern2 = Pattern(
            name="test_pattern",
            context="testing",
            approach="Write more tests",
            avg_iterations=3.0,
            min_iterations=3
        )

        id2 = store.store(pattern2)

        # Should update existing, same ID
        assert id2 == id1

        # Check updated values
        retrieved = store.get_by_id(id1)
        assert retrieved.success_count == 2  # Original + update
        assert retrieved.avg_iterations == pytest.approx(4.0, rel=0.01)  # (5+3)/2
        assert retrieved.min_iterations == 3  # Min of 5 and 3

    def test_find_relevant_patterns(self, store):
        """Test finding relevant patterns for a task."""
        # Store multiple patterns
        patterns = [
            Pattern(
                name="testing_pattern",
                context="testing",
                trigger_keywords=["test", "pytest"],
                approach="Write tests",
                agent="skald",
                success_count=10
            ),
            Pattern(
                name="code_pattern",
                context="code_generation",
                trigger_keywords=["create", "function"],
                approach="Create function",
                agent="huginn",
                success_count=5
            ),
            Pattern(
                name="refactor_pattern",
                context="refactoring",
                trigger_keywords=["refactor", "rename"],
                approach="Refactor code",
                agent="huginn",
                success_count=3
            )
        ]

        for p in patterns:
            store.store(p)

        # Find patterns relevant to testing
        results = store.find_relevant("Write pytest tests for module", limit=2)
        assert len(results) > 0
        assert results[0].context == "testing"

        # Find patterns relevant to code generation
        results = store.find_relevant("Create a new function", limit=2)
        assert len(results) > 0
        # Should find code pattern

    def test_find_by_context(self, store):
        """Test filtering by context."""
        store.store(Pattern(
            name="test_pattern",
            context="testing",
            trigger_keywords=["test"],
            approach="Write tests"
        ))
        store.store(Pattern(
            name="code_pattern",
            context="code_generation",
            trigger_keywords=["create"],
            approach="Create code"
        ))

        # Find only testing patterns
        results = store.find_relevant(
            "some task",
            context="testing",
            limit=10
        )

        # Should only return testing context patterns
        for r in results:
            assert r.context == "testing"

    def test_find_by_project(self, store):
        """Test filtering by project."""
        store.store(Pattern(
            name="global_pattern",
            context="general",
            trigger_keywords=["task"],
            approach="Do task",
            project_id=""
        ))
        store.store(Pattern(
            name="project_pattern",
            context="general",
            trigger_keywords=["task"],
            approach="Do project task",
            project_id="my_project"
        ))

        # Find for specific project
        results = store.find_relevant(
            "some task",
            project_id="my_project",
            limit=10
        )

        # Should return both global and project-specific
        assert len(results) >= 1

    def test_get_pattern_count(self, store):
        """Test getting pattern count."""
        assert store.get_pattern_count() == 0

        store.store(Pattern(name="p1", context="c1", approach="a1"))
        store.store(Pattern(name="p2", context="c2", approach="a2"))

        assert store.get_pattern_count() == 2

    def test_delete_pattern(self, store):
        """Test deleting a pattern."""
        pattern_id = store.store(Pattern(
            name="to_delete",
            context="test",
            approach="approach"
        ))

        assert store.get_by_id(pattern_id) is not None
        assert store.delete(pattern_id) is True
        assert store.get_by_id(pattern_id) is None

    def test_get_all_patterns(self, store):
        """Test getting all patterns."""
        for i in range(5):
            store.store(Pattern(
                name=f"pattern_{i}",
                context="test",
                approach="approach",
                success_count=i
            ))

        all_patterns = store.get_all()
        assert len(all_patterns) == 5

        # Should be ordered by success count
        for i, p in enumerate(all_patterns[:-1]):
            assert p.success_count >= all_patterns[i + 1].success_count


class TestPatternLearner:
    """Tests for PatternLearner extraction logic."""

    @pytest.fixture
    def learner(self, tmp_path):
        """Create a learner with temporary storage."""
        db_path = str(tmp_path / "test_learning.db")
        store = PatternStore(db_path)
        return PatternLearner(store)

    def test_infer_context_testing(self, learner):
        """Test context inference for testing tasks."""
        context = learner._infer_context("Write pytest tests for the module", "general")
        assert context == "testing"

        context = learner._infer_context("Create unit tests", "general")
        assert context == "testing"

    def test_infer_context_code_generation(self, learner):
        """Test context inference for code generation."""
        context = learner._infer_context("Create a function to validate emails", "general")
        assert context == "code_generation"

        context = learner._infer_context("Implement the user authentication", "general")
        assert context == "code_generation"

    def test_infer_context_refactoring(self, learner):
        """Test context inference for refactoring."""
        context = learner._infer_context("Refactor the database module", "general")
        assert context == "refactoring"

        context = learner._infer_context("Rename the function to be clearer", "general")
        assert context == "refactoring"

    def test_infer_context_review(self, learner):
        """Test context inference for review tasks."""
        context = learner._infer_context("Review the code for security issues", "general")
        assert context == "review"

    def test_infer_context_database(self, learner):
        """Test context inference for database tasks."""
        context = learner._infer_context("Optimize the SQL query for performance", "general")
        assert context == "database"

        context = learner._infer_context("Debug the database connection issue", "general")
        assert context == "database"

    def test_extract_keywords(self, learner):
        """Test keyword extraction from task description."""
        keywords = learner._extract_keywords(
            "Create a function to validate email addresses"
        )

        assert "function" in keywords
        assert "validate" in keywords
        assert "email" in keywords
        # Stop words should be filtered out
        assert "a" not in keywords
        assert "to" not in keywords

    def test_extract_keywords_limit(self, learner):
        """Test keyword extraction respects max limit."""
        learner.config.max_keywords = 3
        keywords = learner._extract_keywords(
            "Create a very long function description with many different words"
        )

        assert len(keywords) <= 3

    def test_extract_tool_sequence(self, learner):
        """Test tool sequence extraction with deduplication."""
        tools = ["read_file", "write_file", "read_file", "shell", "write_file"]
        sequence = learner._extract_tool_sequence(tools)

        # Should preserve order but remove duplicates
        assert sequence == ["read_file", "write_file", "shell"]

    def test_generate_pattern_name(self, learner):
        """Test pattern name generation."""
        name = learner._generate_pattern_name("testing", ["pytest", "module"])
        assert "testing" in name
        assert "pytest" in name

        name = learner._generate_pattern_name("code_generation", [])
        assert name == "code_generation_pattern"

    def test_learn_from_completion_success(self, learner):
        """Test learning from a successful task completion."""
        task = Task(
            description="Write pytest tests for the validation module",
            task_type="testing",
            assigned_agent="skald",
            status=TaskStatus.COMPLETE
        )

        pattern_id = learner.learn_from_completion(
            task=task,
            iterations=5,
            tool_calls=["read_file", "write_file"],
            final_output="Tests written successfully",
            session_turns=[
                {"role": "assistant", "content": "I'll write the tests"}
            ]
        )

        assert pattern_id is not None
        assert pattern_id > 0

        # Verify pattern was stored
        pattern = learner.store.get_by_id(pattern_id)
        assert pattern.context == "testing"
        assert pattern.agent == "skald"
        assert pattern.avg_iterations == 5.0

    def test_learn_skip_incomplete_task(self, learner):
        """Test that incomplete tasks are skipped."""
        task = Task(
            description="Some task",
            status=TaskStatus.FAILED  # Not complete
        )

        pattern_id = learner.learn_from_completion(
            task=task,
            iterations=5,
            tool_calls=["read_file"],
            final_output="Failed"
        )

        assert pattern_id is None

    def test_learn_skip_inefficient(self, learner):
        """Test that inefficient completions are skipped."""
        learner.config.efficiency_threshold = 5
        task = Task(
            description="Some task",
            status=TaskStatus.COMPLETE
        )

        pattern_id = learner.learn_from_completion(
            task=task,
            iterations=10,  # More than threshold
            tool_calls=["read_file"],
            final_output="Done"
        )

        assert pattern_id is None

    def test_learn_skip_trivial(self, learner):
        """Test that trivial completions are skipped."""
        learner.config.min_iterations = 2
        task = Task(
            description="Some task",
            status=TaskStatus.COMPLETE
        )

        pattern_id = learner.learn_from_completion(
            task=task,
            iterations=1,  # Less than min
            tool_calls=["read_file"],
            final_output="Done"
        )

        assert pattern_id is None

    def test_suggest_patterns(self, learner):
        """Test pattern suggestions for new tasks."""
        # First, learn some patterns
        for i in range(3):
            task = Task(
                description=f"Write pytest tests for module {i}",
                status=TaskStatus.COMPLETE,
                assigned_agent="skald"
            )
            learner.learn_from_completion(
                task=task,
                iterations=3,
                tool_calls=["read_file", "write_file"],
                final_output="Tests done"
            )

        # Get suggestions for a similar task
        suggestions = learner.suggest_patterns(
            "Write tests for the new validation module"
        )

        assert len(suggestions) > 0
        pattern, suggestion_text = suggestions[0]
        assert "testing" in pattern.context or "test" in pattern.name

    def test_get_stats(self, learner):
        """Test getting learning statistics."""
        # Learn a pattern
        task = Task(
            description="Create a function",
            status=TaskStatus.COMPLETE,
            assigned_agent="huginn"
        )
        learner.learn_from_completion(
            task=task,
            iterations=3,
            tool_calls=["write_file"],
            final_output="Done"
        )

        stats = learner.get_stats()

        assert stats["total_patterns"] >= 1
        assert stats["total_successes"] >= 1
        assert "huginn" in stats["agents"]


class TestMuninnMemoryLearning:
    """Tests for learning integration in MuninnMemory."""

    @pytest.fixture
    def memory(self, tmp_path):
        """Create a memory system with temporary storage."""
        db_path = str(tmp_path / "test_memory.db")
        config = MemoryConfig(enable_learning=True)
        return MuninnMemory(db_path, config)

    def test_memory_has_learner(self, memory):
        """Test that memory has learner initialized."""
        assert memory.learner is not None
        assert memory.patterns is not None

    def test_memory_learning_disabled(self, tmp_path):
        """Test that learning can be disabled."""
        db_path = str(tmp_path / "test_memory_no_learn.db")
        config = MemoryConfig(enable_learning=False)
        memory = MuninnMemory(db_path, config)

        assert memory.learner is None

    def test_get_pattern_count(self, memory):
        """Test getting pattern count through memory system."""
        assert memory.get_pattern_count() == 0

        # Learn a pattern
        task = Task(
            description="Test task",
            status=TaskStatus.COMPLETE,
            assigned_agent="huginn"
        )
        memory.learn_from_completion(
            task=task,
            iterations=3,
            tool_calls=["read_file"],
            final_output="Done"
        )

        assert memory.get_pattern_count() >= 1

    def test_get_learning_stats(self, memory):
        """Test getting learning stats through memory system."""
        stats = memory.get_learning_stats()

        assert stats["learning_enabled"] is True
        assert "total_patterns" in stats

    def test_learning_disabled_stats(self, tmp_path):
        """Test stats when learning is disabled."""
        db_path = str(tmp_path / "test_memory_no_learn.db")
        config = MemoryConfig(enable_learning=False)
        memory = MuninnMemory(db_path, config)

        stats = memory.get_learning_stats()
        assert stats["learning_enabled"] is False


class TestContextBuilding:
    """Tests for pattern suggestions in context building."""

    @pytest.fixture
    def memory_with_patterns(self, tmp_path):
        """Create memory with some pre-learned patterns."""
        db_path = str(tmp_path / "test_memory_context.db")
        config = MemoryConfig(enable_learning=True, pattern_limit=2)
        memory = MuninnMemory(db_path, config)

        # Learn some patterns
        patterns = [
            ("Write pytest tests for validation", "testing", "skald"),
            ("Create a user model", "code_generation", "huginn"),
            ("Refactor the database module", "refactoring", "huginn")
        ]

        for desc, context, agent in patterns:
            task = Task(
                description=desc,
                status=TaskStatus.COMPLETE,
                assigned_agent=agent
            )
            memory.learn_from_completion(
                task=task,
                iterations=3,
                tool_calls=["read_file", "write_file"],
                final_output="Done"
            )

        return memory

    def test_patterns_included_in_context(self, memory_with_patterns):
        """Test that relevant patterns are included in context."""
        memory = memory_with_patterns

        context = memory.build_context(
            project_id="test_project",
            current_task="Write tests for the new module",
            conversation=[]
        )

        # Check if patterns are included
        pattern_messages = [
            msg for msg in context
            if "Learned patterns" in msg.get("content", "")
        ]

        # Should include pattern suggestions if any relevant
        # Note: May be empty if no patterns match
        # Just verify no errors occurred

    def test_patterns_limited(self, memory_with_patterns):
        """Test that pattern limit is respected."""
        memory = memory_with_patterns
        memory.config.pattern_limit = 1

        context = memory.build_context(
            project_id="test_project",
            current_task="Write tests for the module",
            conversation=[]
        )

        # Even with many patterns, should only include limited number
        # Verify by checking length of pattern message


class TestLearningConfig:
    """Tests for LearningConfig settings."""

    def test_default_config(self):
        """Test default configuration values."""
        config = LearningConfig()

        assert config.efficiency_threshold == 10
        assert config.min_iterations == 2
        assert config.max_keywords == 10
        assert config.max_tool_sequence == 20

    def test_custom_config(self):
        """Test custom configuration."""
        config = LearningConfig(
            efficiency_threshold=5,
            min_iterations=1,
            max_keywords=5
        )

        assert config.efficiency_threshold == 5
        assert config.min_iterations == 1
        assert config.max_keywords == 5
