"""Tests for Sindri fine-tuning pipeline.

Tests for:
- Data curation (curator.py)
- Model registry (registry.py)
- Training orchestrator (trainer.py)
- Model evaluation (evaluator.py)
"""

import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from sindri.persistence.database import Database
from sindri.persistence.state import SessionState, Session
from sindri.persistence.feedback import SessionFeedback, FeedbackStore

from sindri.finetuning.curator import (
    DataCurator,
    CurationConfig,
    CuratedDataset,
    CuratedSession,
    TaskCategory,
)
from sindri.finetuning.registry import (
    ModelRegistry,
    FineTunedModel,
    ModelStatus,
    TrainingParams,
    TrainingMetrics,
)
from sindri.finetuning.trainer import (
    TrainingOrchestrator,
    TrainingConfig,
    TrainingJob,
    TrainingStatus,
)
from sindri.finetuning.evaluator import (
    ModelEvaluator,
    BenchmarkPrompt,
    BenchmarkSuite,
    EvaluationResult,
    ComparisonResult,
    EvalMetric,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path, auto_backup=False)
        yield db


@pytest.fixture
def feedback_store(temp_db):
    """Create a feedback store with temporary database."""
    return FeedbackStore(temp_db)


@pytest.fixture
def session_state(temp_db):
    """Create a session state with temporary database."""
    return SessionState(temp_db)


@pytest.fixture
def curator(temp_db):
    """Create a data curator with temporary database."""
    return DataCurator(temp_db)


@pytest.fixture
def registry(temp_db):
    """Create a model registry with temporary database."""
    return ModelRegistry(temp_db)


@pytest.fixture
def temp_output_dir():
    """Create a temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


async def create_rated_session(
    session_state, feedback_store, rating=5, task="Test task", unique_content=None
):
    """Create a session with feedback (helper function)."""
    session = await session_state.create_session(task, "qwen2.5-coder:7b")
    # Use unique content if provided to avoid deduplication
    content = unique_content or f"Write a function for {task}"
    session.add_turn("user", content)
    session.add_turn(
        "assistant",
        f"```python\ndef func_{hash(content) % 10000}(a, b):\n    return a + b\n```",
    )
    session.add_turn("user", "Thanks!")
    session.status = "completed"
    session.iterations = 2
    await session_state.save_session(session)

    feedback = SessionFeedback(
        session_id=session.id,
        rating=rating,
        quality_tags=["correct", "efficient"],
    )
    await feedback_store.add_feedback(feedback)

    return session


# ============================================================
# CurationConfig Tests
# ============================================================


class TestCurationConfig:
    """Tests for CurationConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = CurationConfig()
        assert config.min_rating == 4
        assert config.min_turns == 2
        assert config.max_turns == 100
        assert config.exclude_errors is True
        assert config.exclude_hallucinated is True
        assert config.deduplicate is True
        assert config.similarity_threshold == 0.85
        assert config.balance_categories is False
        assert config.max_per_category == 100

    def test_custom_config(self):
        """Test custom configuration."""
        config = CurationConfig(
            min_rating=5,
            min_turns=3,
            balance_categories=True,
            max_per_category=50,
        )
        assert config.min_rating == 5
        assert config.min_turns == 3
        assert config.balance_categories is True
        assert config.max_per_category == 50


# ============================================================
# TaskCategory Tests
# ============================================================


class TestTaskCategory:
    """Tests for TaskCategory enum."""

    def test_all_categories(self):
        """Test all task categories exist."""
        categories = [
            TaskCategory.CODE_GENERATION,
            TaskCategory.BUG_FIX,
            TaskCategory.REFACTORING,
            TaskCategory.TESTING,
            TaskCategory.DOCUMENTATION,
            TaskCategory.EXPLANATION,
            TaskCategory.DEBUGGING,
            TaskCategory.REVIEW,
            TaskCategory.OTHER,
        ]
        assert len(categories) == 9

    def test_category_values(self):
        """Test category string values."""
        assert TaskCategory.CODE_GENERATION.value == "code_generation"
        assert TaskCategory.BUG_FIX.value == "bug_fix"
        assert TaskCategory.OTHER.value == "other"


# ============================================================
# CuratedSession Tests
# ============================================================


class TestCuratedSession:
    """Tests for CuratedSession dataclass."""

    def test_create_curated_session(self):
        """Test creating a curated session."""
        session = CuratedSession(
            session_id="test-123",
            task="Write a function",
            model="qwen2.5-coder:7b",
            turns=5,
            rating=4.5,
            quality_score=0.85,
            category=TaskCategory.CODE_GENERATION,
            content_hash="abc123",
            quality_tags=["correct"],
        )
        assert session.session_id == "test-123"
        assert session.turns == 5
        assert session.quality_score == 0.85
        assert session.category == TaskCategory.CODE_GENERATION


# ============================================================
# CuratedDataset Tests
# ============================================================


class TestCuratedDataset:
    """Tests for CuratedDataset dataclass."""

    def test_create_dataset(self):
        """Test creating a curated dataset."""
        sessions = [
            CuratedSession(
                session_id="1",
                task="Task 1",
                model="model",
                turns=3,
                rating=5,
                quality_score=0.9,
                category=TaskCategory.CODE_GENERATION,
                content_hash="hash1",
            ),
            CuratedSession(
                session_id="2",
                task="Task 2",
                model="model",
                turns=4,
                rating=4,
                quality_score=0.8,
                category=TaskCategory.BUG_FIX,
                content_hash="hash2",
            ),
        ]
        dataset = CuratedDataset(
            sessions=sessions,
            total_turns=7,
            category_distribution={"code_generation": 1, "bug_fix": 1},
            avg_quality_score=0.85,
        )
        assert len(dataset.sessions) == 2
        assert dataset.total_turns == 7
        assert dataset.avg_quality_score == 0.85

    def test_to_dict(self):
        """Test dictionary conversion."""
        dataset = CuratedDataset(
            sessions=[],
            total_turns=10,
            category_distribution={"code_generation": 5},
            avg_quality_score=0.75,
        )
        d = dataset.to_dict()
        assert d["session_count"] == 0
        assert d["total_turns"] == 10
        assert d["avg_quality_score"] == 0.75
        assert "created_at" in d


# ============================================================
# DataCurator Tests
# ============================================================


class TestDataCurator:
    """Tests for DataCurator class."""

    def test_classify_code_generation(self, curator):
        """Test task classification for code generation."""
        assert curator._classify_task("Write a function") == TaskCategory.CODE_GENERATION
        assert curator._classify_task("Create a class for users") == TaskCategory.CODE_GENERATION
        assert curator._classify_task("Implement sorting algorithm") == TaskCategory.CODE_GENERATION

    def test_classify_bug_fix(self, curator):
        """Test task classification for bug fixes."""
        assert curator._classify_task("Fix this bug") == TaskCategory.BUG_FIX
        assert curator._classify_task("The code is not working") == TaskCategory.BUG_FIX
        assert curator._classify_task("There's an error in login") == TaskCategory.BUG_FIX

    def test_classify_refactoring(self, curator):
        """Test task classification for refactoring."""
        assert curator._classify_task("Refactor this code") == TaskCategory.REFACTORING
        assert curator._classify_task("Clean up the function") == TaskCategory.REFACTORING
        assert curator._classify_task("Optimize the algorithm") == TaskCategory.REFACTORING

    def test_classify_testing(self, curator):
        """Test task classification for testing."""
        assert curator._classify_task("Add tests for this function") == TaskCategory.TESTING
        assert curator._classify_task("Write pytest unit tests") == TaskCategory.TESTING

    def test_classify_documentation(self, curator):
        """Test task classification for documentation."""
        assert curator._classify_task("Document the API methods") == TaskCategory.DOCUMENTATION
        assert curator._classify_task("Update the readme file") == TaskCategory.DOCUMENTATION

    def test_classify_explanation(self, curator):
        """Test task classification for explanation."""
        assert curator._classify_task("Explain how this works") == TaskCategory.EXPLANATION
        assert curator._classify_task("What is a decorator?") == TaskCategory.EXPLANATION

    def test_classify_debugging(self, curator):
        """Test task classification for debugging."""
        assert curator._classify_task("Debug the login issue") == TaskCategory.DEBUGGING
        assert curator._classify_task("Investigate why this fails") == TaskCategory.DEBUGGING

    def test_classify_review(self, curator):
        """Test task classification for review."""
        assert curator._classify_task("Review this code") == TaskCategory.REVIEW
        assert curator._classify_task("Audit the security") == TaskCategory.REVIEW

    def test_classify_other(self, curator):
        """Test task classification for other."""
        assert curator._classify_task("Random task here") == TaskCategory.OTHER

    def test_compute_content_hash(self, curator):
        """Test content hash computation."""
        session = MagicMock()
        session.task = "Test task"
        session.turns = [
            MagicMock(role="assistant", content="Response 1"),
            MagicMock(role="assistant", content="Response 2"),
        ]

        hash1 = curator._compute_content_hash(session)
        hash2 = curator._compute_content_hash(session)
        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 hex length

    def test_deduplicate(self, curator):
        """Test deduplication of sessions."""
        sessions = [
            CuratedSession(
                session_id="1",
                task="Task",
                model="model",
                turns=3,
                rating=5,
                quality_score=0.9,
                category=TaskCategory.CODE_GENERATION,
                content_hash="same_hash",
            ),
            CuratedSession(
                session_id="2",
                task="Task",
                model="model",
                turns=3,
                rating=4,
                quality_score=0.7,
                category=TaskCategory.CODE_GENERATION,
                content_hash="same_hash",  # Duplicate
            ),
            CuratedSession(
                session_id="3",
                task="Other",
                model="model",
                turns=3,
                rating=4,
                quality_score=0.8,
                category=TaskCategory.BUG_FIX,
                content_hash="different_hash",
            ),
        ]

        deduplicated = curator._deduplicate(sessions, 0.85)
        assert len(deduplicated) == 2
        # Should keep the one with higher quality score
        assert any(s.session_id == "1" for s in deduplicated)
        assert any(s.session_id == "3" for s in deduplicated)

    def test_balance_categories(self, curator):
        """Test category balancing."""
        sessions = [
            CuratedSession(
                session_id=str(i),
                task=f"Task {i}",
                model="model",
                turns=3,
                rating=5,
                quality_score=0.9 - i * 0.01,
                category=TaskCategory.CODE_GENERATION,
                content_hash=f"hash{i}",
            )
            for i in range(10)
        ] + [
            CuratedSession(
                session_id="bug1",
                task="Bug fix",
                model="model",
                turns=3,
                rating=5,
                quality_score=0.8,
                category=TaskCategory.BUG_FIX,
                content_hash="bug_hash",
            )
        ]

        balanced = curator._balance_categories(sessions, max_per_category=3)
        # Should have at most 3 code_generation and 1 bug_fix
        code_gen_count = sum(
            1 for s in balanced if s.category == TaskCategory.CODE_GENERATION
        )
        assert code_gen_count <= 3

    @pytest.mark.asyncio
    async def test_curate_no_data(self, temp_db):
        """Test curation with no training data."""
        curator = DataCurator(temp_db)
        dataset = await curator.curate()
        assert len(dataset.sessions) == 0

    @pytest.mark.asyncio
    async def test_curate_with_data(self, temp_db, session_state, feedback_store):
        """Test curation with rated sessions."""
        # Create rated sessions with different content to avoid deduplication
        await create_rated_session(
            session_state, feedback_store, rating=5,
            task="Task 1", unique_content="First unique task"
        )
        await create_rated_session(
            session_state, feedback_store, rating=4,
            task="Task 2", unique_content="Second unique task"
        )

        curator = DataCurator(
            temp_db,
            session_state=session_state,
            feedback_store=feedback_store,
        )

        config = CurationConfig(min_rating=4)
        dataset = await curator.curate(config)

        assert len(dataset.sessions) == 2

    @pytest.mark.asyncio
    async def test_get_curation_stats(self, temp_db, session_state, feedback_store):
        """Test getting curation statistics."""
        await create_rated_session(session_state, feedback_store, rating=5, task="Write code")
        await create_rated_session(session_state, feedback_store, rating=3, task="Fix bug")

        curator = DataCurator(
            temp_db,
            session_state=session_state,
            feedback_store=feedback_store,
        )

        stats = await curator.get_curation_stats()
        assert stats["total_rated_sessions"] == 2
        assert stats["training_candidates"] == 1  # Only 5-star


# ============================================================
# TrainingParams Tests
# ============================================================


class TestTrainingParams:
    """Tests for TrainingParams dataclass."""

    def test_default_params(self):
        """Test default training parameters."""
        params = TrainingParams(base_model="qwen2.5-coder:7b")
        assert params.base_model == "qwen2.5-coder:7b"
        assert params.context_length == 4096
        assert params.temperature == 0.7
        assert params.quantization is None

    def test_to_dict(self):
        """Test dictionary conversion."""
        params = TrainingParams(
            base_model="llama3.1:8b",
            learning_rate=0.0001,
            epochs=3,
        )
        d = params.to_dict()
        assert d["base_model"] == "llama3.1:8b"
        assert d["learning_rate"] == 0.0001
        assert d["epochs"] == 3

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "base_model": "qwen2.5:7b",
            "context_length": 8192,
            "temperature": 0.8,
        }
        params = TrainingParams.from_dict(data)
        assert params.base_model == "qwen2.5:7b"
        assert params.context_length == 8192
        assert params.temperature == 0.8


# ============================================================
# TrainingMetrics Tests
# ============================================================


class TestTrainingMetrics:
    """Tests for TrainingMetrics dataclass."""

    def test_default_metrics(self):
        """Test default metrics."""
        metrics = TrainingMetrics()
        assert metrics.training_loss is None
        assert metrics.tokens_trained == 0
        assert metrics.sessions_used == 0

    def test_to_dict(self):
        """Test dictionary conversion."""
        metrics = TrainingMetrics(
            training_loss=0.5,
            sessions_used=100,
            tokens_trained=50000,
        )
        d = metrics.to_dict()
        assert d["training_loss"] == 0.5
        assert d["sessions_used"] == 100

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "training_time_seconds": 300.5,
            "tokens_trained": 100000,
        }
        metrics = TrainingMetrics.from_dict(data)
        assert metrics.training_time_seconds == 300.5
        assert metrics.tokens_trained == 100000


# ============================================================
# FineTunedModel Tests
# ============================================================


class TestFineTunedModel:
    """Tests for FineTunedModel dataclass."""

    def test_create_model(self):
        """Test creating a fine-tuned model."""
        model = FineTunedModel(
            name="sindri-coder-v1",
            description="Custom coding model",
            params=TrainingParams(base_model="qwen2.5-coder:7b"),
        )
        assert model.name == "sindri-coder-v1"
        assert model.status == ModelStatus.TRAINING
        assert model.version == 1

    def test_to_dict(self):
        """Test dictionary conversion."""
        model = FineTunedModel(
            name="test-model",
            status=ModelStatus.READY,
            tags=["coder", "custom"],
        )
        d = model.to_dict()
        assert d["name"] == "test-model"
        assert d["status"] == "ready"
        assert d["tags"] == ["coder", "custom"]

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "id": 1,
            "name": "my-model",
            "status": "active",
            "version": 2,
            "params": {"base_model": "llama3.1:8b"},
            "metrics": {"sessions_used": 50},
            "tags": ["test"],
        }
        model = FineTunedModel.from_dict(data)
        assert model.id == 1
        assert model.name == "my-model"
        assert model.status == ModelStatus.ACTIVE
        assert model.version == 2


# ============================================================
# ModelStatus Tests
# ============================================================


class TestModelStatus:
    """Tests for ModelStatus enum."""

    def test_all_statuses(self):
        """Test all model statuses exist."""
        statuses = [
            ModelStatus.TRAINING,
            ModelStatus.READY,
            ModelStatus.ACTIVE,
            ModelStatus.ARCHIVED,
            ModelStatus.FAILED,
        ]
        assert len(statuses) == 5

    def test_status_values(self):
        """Test status string values."""
        assert ModelStatus.TRAINING.value == "training"
        assert ModelStatus.READY.value == "ready"
        assert ModelStatus.ACTIVE.value == "active"


# ============================================================
# ModelRegistry Tests
# ============================================================


class TestModelRegistry:
    """Tests for ModelRegistry class."""

    @pytest.mark.asyncio
    async def test_register_model(self, registry):
        """Test registering a new model."""
        model = FineTunedModel(
            name="test-model",
            description="Test description",
            params=TrainingParams(base_model="qwen2.5-coder:7b"),
        )
        registered = await registry.register(model)
        assert registered.id is not None
        assert registered.version == 1

    @pytest.mark.asyncio
    async def test_register_increments_version(self, registry):
        """Test that registering same name increments version."""
        model1 = FineTunedModel(name="my-model")
        model2 = FineTunedModel(name="my-model")

        registered1 = await registry.register(model1)
        registered2 = await registry.register(model2)

        assert registered1.version == 1
        assert registered2.version == 2

    @pytest.mark.asyncio
    async def test_get_by_id(self, registry):
        """Test getting model by ID."""
        model = FineTunedModel(name="test")
        registered = await registry.register(model)

        found = await registry.get_by_id(registered.id)
        assert found is not None
        assert found.name == "test"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, registry):
        """Test getting non-existent model."""
        found = await registry.get_by_id(9999)
        assert found is None

    @pytest.mark.asyncio
    async def test_get_by_name(self, registry):
        """Test getting models by name."""
        model1 = FineTunedModel(name="test-model")
        model2 = FineTunedModel(name="test-model")
        model3 = FineTunedModel(name="other-model")

        await registry.register(model1)
        await registry.register(model2)
        await registry.register(model3)

        models = await registry.get_by_name("test-model")
        assert len(models) == 2

    @pytest.mark.asyncio
    async def test_get_latest(self, registry):
        """Test getting latest version of a model."""
        model1 = FineTunedModel(name="test")
        model2 = FineTunedModel(name="test")

        await registry.register(model1)
        await registry.register(model2)

        latest = await registry.get_latest("test")
        assert latest is not None
        assert latest.version == 2

    @pytest.mark.asyncio
    async def test_update_model(self, registry):
        """Test updating a model."""
        model = FineTunedModel(name="test", status=ModelStatus.TRAINING)
        registered = await registry.register(model)

        registered.status = ModelStatus.READY
        registered.description = "Updated"
        success = await registry.update(registered)

        assert success is True
        updated = await registry.get_by_id(registered.id)
        assert updated.status == ModelStatus.READY
        assert updated.description == "Updated"

    @pytest.mark.asyncio
    async def test_set_active(self, registry):
        """Test setting a model as active."""
        model1 = FineTunedModel(name="model1", status=ModelStatus.READY)
        model2 = FineTunedModel(name="model2", status=ModelStatus.READY)

        reg1 = await registry.register(model1)
        reg2 = await registry.register(model2)

        # Set first as active
        await registry.set_active(reg1.id)
        active = await registry.get_active()
        assert active.id == reg1.id

        # Set second as active (first should become ready)
        await registry.set_active(reg2.id)
        active = await registry.get_active()
        assert active.id == reg2.id

        old_model = await registry.get_by_id(reg1.id)
        assert old_model.status == ModelStatus.READY

    @pytest.mark.asyncio
    async def test_list_models(self, registry):
        """Test listing models."""
        await registry.register(FineTunedModel(name="m1", status=ModelStatus.READY))
        await registry.register(FineTunedModel(name="m2", status=ModelStatus.TRAINING))
        await registry.register(FineTunedModel(name="m3", status=ModelStatus.READY))

        all_models = await registry.list_models()
        assert len(all_models) == 3

        ready_models = await registry.list_models(status=ModelStatus.READY)
        assert len(ready_models) == 2

    @pytest.mark.asyncio
    async def test_archive_model(self, registry):
        """Test archiving a model."""
        model = FineTunedModel(name="test")
        registered = await registry.register(model)

        success = await registry.archive(registered.id)
        assert success is True

        archived = await registry.get_by_id(registered.id)
        assert archived.status == ModelStatus.ARCHIVED

    @pytest.mark.asyncio
    async def test_delete_model(self, registry):
        """Test deleting a model."""
        model = FineTunedModel(name="test")
        registered = await registry.register(model)

        success = await registry.delete(registered.id)
        assert success is True

        found = await registry.get_by_id(registered.id)
        assert found is None

    @pytest.mark.asyncio
    async def test_get_stats(self, registry):
        """Test getting registry statistics."""
        await registry.register(FineTunedModel(name="m1", status=ModelStatus.READY))
        await registry.register(FineTunedModel(name="m2", status=ModelStatus.TRAINING))

        stats = await registry.get_stats()
        assert stats["total_models"] == 2
        assert "status_distribution" in stats


# ============================================================
# TrainingConfig Tests
# ============================================================


class TestTrainingConfig:
    """Tests for TrainingConfig dataclass."""

    def test_default_config(self):
        """Test default training configuration."""
        config = TrainingConfig()
        assert config.base_model == "qwen2.5-coder:7b"
        assert config.model_name == "sindri-custom"
        assert config.min_rating == 4
        assert config.max_sessions == 500

    def test_custom_config(self):
        """Test custom training configuration."""
        config = TrainingConfig(
            base_model="llama3.1:8b",
            model_name="my-model",
            min_rating=5,
            max_sessions=100,
            tags=["custom", "test"],
        )
        assert config.base_model == "llama3.1:8b"
        assert config.model_name == "my-model"
        assert config.tags == ["custom", "test"]


# ============================================================
# TrainingJob Tests
# ============================================================


class TestTrainingJob:
    """Tests for TrainingJob dataclass."""

    def test_create_job(self):
        """Test creating a training job."""
        config = TrainingConfig(model_name="test")
        job = TrainingJob(id="train-123", config=config)
        assert job.id == "train-123"
        assert job.status == TrainingStatus.PENDING
        assert job.progress == 0.0

    def test_to_dict(self):
        """Test dictionary conversion."""
        config = TrainingConfig(model_name="test", base_model="qwen2.5:7b")
        job = TrainingJob(
            id="train-123",
            config=config,
            status=TrainingStatus.TRAINING,
            progress=50.0,
        )
        d = job.to_dict()
        assert d["id"] == "train-123"
        assert d["status"] == "training"
        assert d["progress"] == 50.0


# ============================================================
# TrainingStatus Tests
# ============================================================


class TestTrainingStatus:
    """Tests for TrainingStatus enum."""

    def test_all_statuses(self):
        """Test all training statuses exist."""
        statuses = [
            TrainingStatus.PENDING,
            TrainingStatus.PREPARING,
            TrainingStatus.EXPORTING,
            TrainingStatus.TRAINING,
            TrainingStatus.COMPLETED,
            TrainingStatus.FAILED,
            TrainingStatus.CANCELLED,
        ]
        assert len(statuses) == 7


# ============================================================
# TrainingOrchestrator Tests
# ============================================================


class TestTrainingOrchestrator:
    """Tests for TrainingOrchestrator class."""

    @pytest.mark.asyncio
    async def test_prepare_training_no_data(self, temp_db, temp_output_dir):
        """Test preparing training with no data."""
        orchestrator = TrainingOrchestrator(database=temp_db)
        config = TrainingConfig(output_dir=temp_output_dir)

        job = await orchestrator.prepare_training(config)
        assert job.status == TrainingStatus.PREPARING
        assert job.dataset is not None
        assert len(job.dataset.sessions) == 0

    @pytest.mark.asyncio
    async def test_get_job(self, temp_db, temp_output_dir):
        """Test getting a job by ID."""
        orchestrator = TrainingOrchestrator(database=temp_db)
        config = TrainingConfig(output_dir=temp_output_dir)

        job = await orchestrator.prepare_training(config)
        found = orchestrator.get_job(job.id)
        assert found is not None
        assert found.id == job.id

    @pytest.mark.asyncio
    async def test_list_jobs(self, temp_db, temp_output_dir):
        """Test listing jobs."""
        orchestrator = TrainingOrchestrator(database=temp_db)
        config = TrainingConfig(output_dir=temp_output_dir)

        await orchestrator.prepare_training(config)
        jobs = orchestrator.list_jobs()
        assert len(jobs) == 1

    @pytest.mark.asyncio
    async def test_progress_callback(self, temp_db, temp_output_dir):
        """Test progress callbacks."""
        orchestrator = TrainingOrchestrator(database=temp_db)
        config = TrainingConfig(output_dir=temp_output_dir)

        progress_updates = []

        def on_progress(job):
            progress_updates.append(job.progress)

        orchestrator.on_progress(on_progress)
        await orchestrator.prepare_training(config)

        assert len(progress_updates) > 0

    @pytest.mark.asyncio
    async def test_get_training_stats(self, temp_db):
        """Test getting training statistics."""
        orchestrator = TrainingOrchestrator(database=temp_db)
        stats = await orchestrator.get_training_stats()

        assert "curation" in stats
        assert "registry" in stats
        assert "jobs" in stats


# ============================================================
# BenchmarkPrompt Tests
# ============================================================


class TestBenchmarkPrompt:
    """Tests for BenchmarkPrompt dataclass."""

    def test_create_prompt(self):
        """Test creating a benchmark prompt."""
        prompt = BenchmarkPrompt(
            id="test-1",
            prompt="Write a hello world function",
            category="code_generation",
            expected_patterns=[r"def \w+", r"print"],
        )
        assert prompt.id == "test-1"
        assert prompt.max_tokens == 1024
        assert len(prompt.expected_patterns) == 2

    def test_default_values(self):
        """Test default prompt values."""
        prompt = BenchmarkPrompt(id="test", prompt="Test prompt")
        assert prompt.category == "general"
        assert prompt.expected_patterns == []
        assert prompt.forbidden_patterns == []


# ============================================================
# BenchmarkSuite Tests
# ============================================================


class TestBenchmarkSuite:
    """Tests for BenchmarkSuite class."""

    def test_create_suite(self):
        """Test creating a benchmark suite."""
        prompts = [
            BenchmarkPrompt(id="1", prompt="P1"),
            BenchmarkPrompt(id="2", prompt="P2"),
        ]
        suite = BenchmarkSuite(
            name="test-suite",
            description="Test suite",
            prompts=prompts,
        )
        assert suite.name == "test-suite"
        assert len(suite.prompts) == 2

    def test_default_coding_suite(self):
        """Test default coding suite."""
        suite = BenchmarkSuite.default_coding_suite()
        assert suite.name == "default_coding"
        assert len(suite.prompts) > 0

        # Check for various categories
        categories = {p.category for p in suite.prompts}
        assert "code_generation" in categories
        assert "debugging" in categories

    def test_quick_suite(self):
        """Test quick suite."""
        suite = BenchmarkSuite.quick_suite()
        assert suite.name == "quick"
        assert len(suite.prompts) == 2


# ============================================================
# EvaluationResult Tests
# ============================================================


class TestEvaluationResult:
    """Tests for EvaluationResult dataclass."""

    def test_create_result(self):
        """Test creating an evaluation result."""
        result = EvaluationResult(
            prompt_id="test-1",
            model_name="qwen2.5:7b",
            response="def hello(): print('hi')",
            score=0.85,
            response_time_ms=500.0,
        )
        assert result.prompt_id == "test-1"
        assert result.score == 0.85

    def test_to_dict(self):
        """Test dictionary conversion."""
        result = EvaluationResult(
            prompt_id="test",
            model_name="model",
            response="response text here",
            score=0.75,
            passed_patterns=3,
            failed_patterns=1,
        )
        d = result.to_dict()
        assert d["prompt_id"] == "test"
        assert d["score"] == 0.75
        assert "response_preview" in d


# ============================================================
# EvalMetric Tests
# ============================================================


class TestEvalMetric:
    """Tests for EvalMetric enum."""

    def test_all_metrics(self):
        """Test all evaluation metrics exist."""
        metrics = [
            EvalMetric.RESPONSE_TIME,
            EvalMetric.TOKEN_COUNT,
            EvalMetric.CODE_QUALITY,
            EvalMetric.RELEVANCE,
            EvalMetric.COMPLETENESS,
            EvalMetric.CORRECTNESS,
        ]
        assert len(metrics) == 6


# ============================================================
# ComparisonResult Tests
# ============================================================


class TestComparisonResult:
    """Tests for ComparisonResult dataclass."""

    def test_create_comparison(self):
        """Test creating a comparison result."""
        comparison = ComparisonResult(
            model_a="model-a",
            model_b="model-b",
            results_a=[],
            results_b=[],
            winner="model-b",
            summary={"score_diff": 0.1},
        )
        assert comparison.model_a == "model-a"
        assert comparison.winner == "model-b"

    def test_to_dict(self):
        """Test dictionary conversion."""
        comparison = ComparisonResult(
            model_a="a",
            model_b="b",
            results_a=[],
            results_b=[],
            summary={"test": 1},
        )
        d = comparison.to_dict()
        assert d["model_a"] == "a"
        assert d["prompt_count"] == 0


# ============================================================
# ModelEvaluator Tests
# ============================================================


class TestModelEvaluator:
    """Tests for ModelEvaluator class."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock Ollama client."""
        client = AsyncMock()
        client.generate = AsyncMock(
            return_value={
                "response": """def is_prime(n: int) -> bool:
    '''Check if a number is prime.'''
    if n <= 1:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True"""
            }
        )
        return client

    def test_cache_operations(self):
        """Test cache operations."""
        evaluator = ModelEvaluator()
        evaluator._results_cache["test:suite"] = []
        assert evaluator.get_cached_results("test", "suite") == []

        evaluator.clear_cache()
        assert evaluator.get_cached_results("test", "suite") is None

    @pytest.mark.asyncio
    async def test_evaluate_prompt(self, mock_client):
        """Test evaluating a single prompt."""
        evaluator = ModelEvaluator(client=mock_client)

        prompt = BenchmarkPrompt(
            id="prime-test",
            prompt="Write a prime checker",
            expected_patterns=[r"def\s+\w+", r"return\s+(True|False)"],
        )

        result = await evaluator._evaluate_prompt("test-model", prompt, timeout=30)

        assert result.prompt_id == "prime-test"
        assert result.model_name == "test-model"
        assert result.score > 0
        assert result.passed_patterns > 0

    @pytest.mark.asyncio
    async def test_evaluate_model(self, mock_client):
        """Test evaluating a model on a suite."""
        evaluator = ModelEvaluator(client=mock_client)
        suite = BenchmarkSuite.quick_suite()

        results = await evaluator.evaluate_model("test-model", suite)

        assert len(results) == len(suite.prompts)
        assert all(r.model_name == "test-model" for r in results)

    @pytest.mark.asyncio
    async def test_quick_evaluate(self, mock_client):
        """Test quick evaluation."""
        evaluator = ModelEvaluator(client=mock_client)

        result = await evaluator.quick_evaluate("test-model")

        assert "model" in result
        assert "avg_score" in result
        assert "all_passed" in result

    @pytest.mark.asyncio
    async def test_compare_models(self, mock_client):
        """Test comparing two models."""
        evaluator = ModelEvaluator(client=mock_client)
        suite = BenchmarkSuite.quick_suite()

        comparison = await evaluator.compare_models("model-a", "model-b", suite)

        assert comparison.model_a == "model-a"
        assert comparison.model_b == "model-b"
        assert len(comparison.results_a) == len(suite.prompts)
        assert len(comparison.results_b) == len(suite.prompts)
        assert "model_a" in comparison.summary
        assert "model_b" in comparison.summary

    @pytest.mark.asyncio
    async def test_evaluate_improvement(self, mock_client):
        """Test evaluating improvement from fine-tuning."""
        evaluator = ModelEvaluator(client=mock_client)

        result = await evaluator.evaluate_improvement(
            "base-model",
            "finetuned-model",
            BenchmarkSuite.quick_suite(),
        )

        assert "base_model" in result
        assert "finetuned_model" in result
        assert "improvement" in result
        assert "improvement_pct" in result
        assert "is_improved" in result

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test timeout handling during evaluation."""
        slow_client = AsyncMock()

        async def slow_response(*args, **kwargs):
            import asyncio

            await asyncio.sleep(10)
            return {"response": "too late"}

        slow_client.generate = slow_response

        evaluator = ModelEvaluator(client=slow_client)
        prompt = BenchmarkPrompt(id="test", prompt="Quick test")

        result = await evaluator._evaluate_prompt("model", prompt, timeout=0.1)

        assert result.response == "[TIMEOUT]"
        assert result.score == 0.0
