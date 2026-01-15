"""Tests for Phase 6.2 model caching features."""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch

from sindri.llm.manager import ModelManager, LoadedModel, CacheMetrics
from sindri.core.delegation import DelegationManager
from sindri.core.tasks import Task, TaskStatus
from sindri.core.scheduler import TaskScheduler


class TestCacheMetrics:
    """Test CacheMetrics tracking."""

    def test_initial_metrics(self):
        """Metrics should start at zero."""
        metrics = CacheMetrics()
        assert metrics.hits == 0
        assert metrics.misses == 0
        assert metrics.evictions == 0
        assert metrics.hit_rate == 0.0
        assert metrics.avg_load_time == 0.0

    def test_hit_rate_calculation(self):
        """Hit rate should be calculated correctly."""
        metrics = CacheMetrics(hits=7, misses=3)
        assert metrics.hit_rate == 0.7

    def test_hit_rate_no_requests(self):
        """Hit rate should be 0 when no requests."""
        metrics = CacheMetrics()
        assert metrics.hit_rate == 0.0

    def test_avg_load_time(self):
        """Average load time calculation."""
        metrics = CacheMetrics(misses=4, total_load_time=8.0)
        assert metrics.avg_load_time == 2.0

    def test_avg_load_time_no_misses(self):
        """Average load time should be 0 when no misses."""
        metrics = CacheMetrics()
        assert metrics.avg_load_time == 0.0


class TestLoadedModel:
    """Test LoadedModel with enhanced tracking."""

    def test_loaded_model_defaults(self):
        """LoadedModel should have sensible defaults."""
        model = LoadedModel(name="test", vram_gb=5.0, last_used=time.time())
        assert model.use_count == 0
        assert model.load_time == 0.0
        assert model.loaded_at > 0

    def test_loaded_model_with_tracking(self):
        """LoadedModel should accept tracking values."""
        model = LoadedModel(
            name="test",
            vram_gb=5.0,
            last_used=time.time(),
            use_count=5,
            load_time=2.5
        )
        assert model.use_count == 5
        assert model.load_time == 2.5


class TestModelManagerCaching:
    """Test ModelManager caching features."""

    @pytest.fixture
    def manager(self):
        """Create a model manager."""
        return ModelManager(total_vram_gb=16.0, reserve_gb=2.0)

    @pytest.mark.asyncio
    async def test_cache_hit_increments_use_count(self, manager):
        """Loading same model should increment use_count."""
        await manager.ensure_loaded("model1", 5.0)
        assert manager.loaded["model1"].use_count == 1

        await manager.ensure_loaded("model1", 5.0)
        assert manager.loaded["model1"].use_count == 2

        await manager.ensure_loaded("model1", 5.0)
        assert manager.loaded["model1"].use_count == 3

    @pytest.mark.asyncio
    async def test_cache_hit_tracked_in_metrics(self, manager):
        """Cache hits should be tracked in metrics."""
        await manager.ensure_loaded("model1", 5.0)
        assert manager.metrics.misses == 1
        assert manager.metrics.hits == 0

        await manager.ensure_loaded("model1", 5.0)
        assert manager.metrics.hits == 1

        await manager.ensure_loaded("model1", 5.0)
        assert manager.metrics.hits == 2

    @pytest.mark.asyncio
    async def test_cache_miss_tracked(self, manager):
        """Cache misses should be tracked."""
        await manager.ensure_loaded("model1", 5.0)
        await manager.ensure_loaded("model2", 5.0)

        assert manager.metrics.misses == 2

    @pytest.mark.asyncio
    async def test_eviction_tracked(self, manager):
        """Evictions should be tracked in metrics."""
        await manager.ensure_loaded("model1", 10.0)
        await manager.ensure_loaded("model2", 10.0)  # Should evict model1

        assert manager.metrics.evictions == 1
        assert "model1" not in manager.loaded

    @pytest.mark.asyncio
    async def test_load_time_tracked(self, manager):
        """Load time should be tracked."""
        await manager.ensure_loaded("model1", 5.0)

        assert manager.loaded["model1"].load_time >= 0
        assert manager.metrics.total_load_time >= 0

    def test_get_cache_stats(self, manager):
        """get_cache_stats should return comprehensive stats."""
        stats = manager.get_cache_stats()

        assert "hits" in stats
        assert "misses" in stats
        assert "evictions" in stats
        assert "hit_rate" in stats
        assert "avg_load_time" in stats
        assert "models" in stats
        assert "keep_warm" in stats


class TestKeepWarm:
    """Test keep-warm functionality."""

    @pytest.fixture
    def manager(self):
        """Create a model manager with keep_warm."""
        return ModelManager(
            total_vram_gb=16.0,
            reserve_gb=2.0,
            keep_warm=["important_model"]
        )

    def test_keep_warm_initialized(self, manager):
        """Keep-warm list should be initialized."""
        assert "important_model" in manager.keep_warm

    @pytest.mark.asyncio
    async def test_keep_warm_not_evicted(self, manager):
        """Keep-warm models should not be evicted."""
        # Load the keep-warm model
        await manager.ensure_loaded("important_model", 8.0)

        # Try to load another model that would require eviction
        await manager.ensure_loaded("other_model", 8.0)

        # important_model should still be loaded (not evicted)
        # other_model should fail to load since important_model can't be evicted
        assert "important_model" in manager.loaded

    def test_add_keep_warm(self, manager):
        """Should be able to add models to keep-warm."""
        manager.add_keep_warm("another_model")
        assert "another_model" in manager.keep_warm

    def test_remove_keep_warm(self, manager):
        """Should be able to remove models from keep-warm."""
        manager.remove_keep_warm("important_model")
        assert "important_model" not in manager.keep_warm


class TestPreWarming:
    """Test model pre-warming functionality."""

    @pytest.fixture
    def manager(self):
        """Create a model manager."""
        return ModelManager(total_vram_gb=16.0, reserve_gb=2.0)

    @pytest.mark.asyncio
    async def test_prewarm_loads_model(self, manager):
        """pre_warm should load model in background."""
        await manager.pre_warm("model1", 5.0)

        # Wait for pre-warm to complete
        await asyncio.sleep(0.1)

        assert "model1" in manager.loaded
        assert manager.metrics.prewarm_count == 1

    @pytest.mark.asyncio
    async def test_prewarm_skips_loaded(self, manager):
        """pre_warm should skip already loaded models."""
        await manager.ensure_loaded("model1", 5.0)
        initial_prewarm_count = manager.metrics.prewarm_count

        await manager.pre_warm("model1", 5.0)

        # Should not increment prewarm count
        assert manager.metrics.prewarm_count == initial_prewarm_count

    @pytest.mark.asyncio
    async def test_wait_for_prewarm(self, manager):
        """wait_for_prewarm should block until model is loaded."""
        # Start pre-warming
        await manager.pre_warm("model1", 5.0)

        # Wait for it
        result = await manager.wait_for_prewarm("model1")

        assert result is True
        assert "model1" in manager.loaded

    @pytest.mark.asyncio
    async def test_prewarm_doesnt_duplicate(self, manager):
        """Multiple pre_warm calls shouldn't duplicate work."""
        # Start multiple pre-warms
        await manager.pre_warm("model1", 5.0)
        await manager.pre_warm("model1", 5.0)
        await manager.pre_warm("model1", 5.0)

        await asyncio.sleep(0.1)

        # Should only have one prewarm
        assert manager.metrics.prewarm_count == 1


class TestDelegationPreWarm:
    """Test pre-warming integration with delegation."""

    @pytest.fixture
    def setup(self):
        """Create delegation manager with model manager."""
        model_manager = ModelManager(total_vram_gb=16.0, reserve_gb=2.0)
        scheduler = TaskScheduler(model_manager)
        delegation = DelegationManager(
            scheduler,
            state=None,
            model_manager=model_manager
        )
        return {
            "model_manager": model_manager,
            "scheduler": scheduler,
            "delegation": delegation
        }

    @pytest.mark.asyncio
    async def test_delegation_triggers_prewarm(self, setup):
        """Delegation should trigger pre-warming."""
        from sindri.core.delegation import DelegationRequest

        parent = Task(id="parent", description="Parent task", assigned_agent="brokkr")
        setup["scheduler"].add_task(parent)

        request = DelegationRequest(
            target_agent="huginn",
            task_description="Child task",
            context={},
            constraints=[],
            success_criteria=[]
        )

        await setup["delegation"].delegate(parent, request)

        # Wait for pre-warm
        await asyncio.sleep(0.1)

        # Huginn's model should be pre-warmed
        assert setup["model_manager"].metrics.prewarm_count == 1

    @pytest.mark.asyncio
    async def test_delegation_without_model_manager(self):
        """Delegation should work without model_manager."""
        model_manager = ModelManager(total_vram_gb=16.0, reserve_gb=2.0)
        scheduler = TaskScheduler(model_manager)
        delegation = DelegationManager(scheduler, state=None, model_manager=None)

        from sindri.core.delegation import DelegationRequest

        parent = Task(id="parent", description="Parent task", assigned_agent="brokkr")
        scheduler.add_task(parent)

        request = DelegationRequest(
            target_agent="huginn",
            task_description="Child task",
            context={},
            constraints=[],
            success_criteria=[]
        )

        # Should not raise even without model_manager
        child = await delegation.delegate(parent, request)
        assert child is not None


class TestCacheEvictionStrategy:
    """Test cache eviction strategies."""

    @pytest.fixture
    def manager(self):
        """Create a model manager."""
        return ModelManager(total_vram_gb=16.0, reserve_gb=2.0)

    @pytest.mark.asyncio
    async def test_lru_eviction(self, manager):
        """Least recently used model should be evicted."""
        # Load model1, then model2
        await manager.ensure_loaded("model1", 7.0)
        await asyncio.sleep(0.01)  # Ensure different timestamps
        await manager.ensure_loaded("model2", 7.0)

        # Access model1 to make it more recently used
        await manager.ensure_loaded("model1", 7.0)

        # Load model3 - should evict model2 (LRU)
        await manager.ensure_loaded("model3", 7.0)

        assert "model1" in manager.loaded
        assert "model2" not in manager.loaded
        assert "model3" in manager.loaded

    @pytest.mark.asyncio
    async def test_eviction_logs_use_count(self, manager):
        """Eviction should log the use count of evicted model."""
        await manager.ensure_loaded("model1", 10.0)
        # Use it multiple times
        await manager.ensure_loaded("model1", 10.0)
        await manager.ensure_loaded("model1", 10.0)

        # Evict by loading larger model
        await manager.ensure_loaded("model2", 10.0)

        # model1 was used 3 times before eviction
        assert manager.metrics.evictions == 1
