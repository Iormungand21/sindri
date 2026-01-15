"""VRAM-aware model management for AMD 6950XT (16GB).

Phase 6.2: Model caching with pre-warming and usage metrics.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional
import ollama
import structlog

log = structlog.get_logger()


@dataclass
class LoadedModel:
    """Represents a loaded model in VRAM with usage tracking."""
    name: str
    vram_gb: float
    last_used: float  # timestamp
    # Phase 6.2: Enhanced tracking
    use_count: int = 0  # Times this model has been used
    load_time: float = 0.0  # Seconds taken to load
    loaded_at: float = field(default_factory=time.time)  # When loaded


@dataclass
class CacheMetrics:
    """Cache performance metrics for monitoring."""
    hits: int = 0  # Model already loaded
    misses: int = 0  # Model needed loading
    evictions: int = 0  # Models evicted to make room
    total_load_time: float = 0.0  # Cumulative load time
    prewarm_count: int = 0  # Pre-warming operations

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate (0.0 to 1.0)."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def avg_load_time(self) -> float:
        """Average model load time in seconds."""
        return self.total_load_time / self.misses if self.misses > 0 else 0.0


class ModelManager:
    """Manages model loading with VRAM constraints.

    Thread-safe for parallel task execution via asyncio locks.

    Phase 6.2 Features:
    - Usage tracking (use_count, load_time)
    - Cache metrics (hit rate, evictions)
    - Pre-warming for anticipated model needs
    - Keep-warm list for frequently used models
    """

    def __init__(
        self,
        total_vram_gb: float = 16.0,
        reserve_gb: float = 2.0,
        keep_warm: Optional[list[str]] = None
    ):
        self.total_vram = total_vram_gb
        self.reserve = reserve_gb
        self.available = total_vram_gb - reserve_gb
        self.loaded: dict[str, LoadedModel] = {}
        self._client = ollama.Client()

        # Phase 6.1: Thread-safety for parallel execution
        self._lock = asyncio.Lock()  # Main lock for VRAM operations
        self._model_locks: dict[str, asyncio.Lock] = {}  # Per-model locks

        # Phase 6.2: Caching features
        self.metrics = CacheMetrics()
        self.keep_warm: set[str] = set(keep_warm or [])  # Models to never evict
        self._prewarm_tasks: dict[str, asyncio.Task] = {}  # Background pre-warming

        log.info("model_manager_initialized",
                 total_vram=total_vram_gb,
                 available=self.available,
                 keep_warm=list(self.keep_warm))

    def can_load(self, model: str, required_vram: float) -> bool:
        """Check if model can be loaded (may require eviction).

        Note: This is a non-locking check. For actual loading, use ensure_loaded().
        """
        if model in self.loaded:
            return True

        free_vram = self._get_free_vram()
        # Can load if we have space OR can make space by evicting
        can = free_vram >= required_vram or len(self.loaded) > 0

        log.debug("can_load_check",
                  model=model,
                  required=required_vram,
                  free=free_vram,
                  can_load=can)

        return can

    def _get_model_lock(self, model: str) -> asyncio.Lock:
        """Get or create a lock for a specific model."""
        if model not in self._model_locks:
            self._model_locks[model] = asyncio.Lock()
        return self._model_locks[model]

    def _get_free_vram(self) -> float:
        """Calculate free VRAM."""
        used = sum(m.vram_gb for m in self.loaded.values())
        return self.available - used

    async def ensure_loaded(self, model: str, required_vram: float) -> bool:
        """Ensure model is loaded, evicting others if needed.

        Thread-safe for parallel execution via asyncio locks.
        Tracks cache metrics for monitoring.
        """
        # Quick check without lock - cache hit
        if model in self.loaded:
            # Update usage tracking
            self.loaded[model].last_used = time.time()
            self.loaded[model].use_count += 1
            self.metrics.hits += 1
            log.debug("model_cache_hit", model=model,
                      use_count=self.loaded[model].use_count,
                      hit_rate=f"{self.metrics.hit_rate:.1%}")
            return True

        # Cache miss - need to load
        self.metrics.misses += 1

        # Need to load - acquire per-model lock to prevent double-loading
        model_lock = self._get_model_lock(model)
        async with model_lock:
            # Double-check after acquiring lock (another task may have loaded it)
            if model in self.loaded:
                self.loaded[model].last_used = time.time()
                self.loaded[model].use_count += 1
                # This is still a "hit" from user perspective
                self.metrics.hits += 1
                self.metrics.misses -= 1  # Correct the earlier miss
                log.debug("model_loaded_by_another_task", model=model)
                return True

            load_start = time.time()
            log.info("loading_model", model=model, required_vram=required_vram)

            # Acquire main lock for VRAM operations
            async with self._lock:
                # Need to free up space?
                while self._get_free_vram() < required_vram and self.loaded:
                    # Evict least recently used (but not locked or keep_warm models)
                    evictable = [
                        m for m in self.loaded.values()
                        if m.name not in self.keep_warm
                        and (m.name not in self._model_locks
                             or not self._model_locks[m.name].locked())
                    ]
                    if not evictable:
                        log.warning("no_evictable_models", model=model,
                                    keep_warm=list(self.keep_warm))
                        break

                    # Evict LRU (could also consider use_count for smarter eviction)
                    lru = min(evictable, key=lambda m: m.last_used)
                    log.info("evicting_model", model=lru.name, reason="LRU",
                             use_count=lru.use_count)
                    await self._unload(lru.name)
                    self.metrics.evictions += 1

                free_vram = self._get_free_vram()
                if free_vram < required_vram:
                    log.error("insufficient_vram",
                              model=model,
                              required=required_vram,
                              free=free_vram)
                    return False  # Can't fit

                load_time = time.time() - load_start

                # Track as loaded (Ollama loads on first use)
                self.loaded[model] = LoadedModel(
                    name=model,
                    vram_gb=required_vram,
                    last_used=time.time(),
                    use_count=1,
                    load_time=load_time,
                    loaded_at=time.time()
                )

                self.metrics.total_load_time += load_time

                log.info("model_loaded",
                         model=model,
                         vram_used=required_vram,
                         load_time=f"{load_time:.2f}s",
                         free_vram=self._get_free_vram(),
                         cache_hit_rate=f"{self.metrics.hit_rate:.1%}")

        return True

    async def _unload(self, model: str):
        """Unload a model from VRAM."""
        # Ollama doesn't have explicit unload API, but we track it
        if model in self.loaded:
            unloaded = self.loaded.pop(model)
            log.info("model_unloaded", model=model,
                     was_used=unloaded.use_count,
                     lifetime=f"{time.time() - unloaded.loaded_at:.1f}s")

    async def pre_warm(self, model: str, required_vram: float) -> None:
        """Pre-load a model in the background for anticipated use.

        This is called during delegation to reduce latency when the
        child task actually needs the model.
        """
        # Don't pre-warm if already loaded or warming
        if model in self.loaded:
            log.debug("prewarm_skipped_already_loaded", model=model)
            return

        if model in self._prewarm_tasks:
            task = self._prewarm_tasks[model]
            if not task.done():
                log.debug("prewarm_skipped_in_progress", model=model)
                return

        async def _do_prewarm():
            try:
                log.info("prewarm_starting", model=model, vram=required_vram)
                self.metrics.prewarm_count += 1
                await self.ensure_loaded(model, required_vram)
                log.info("prewarm_completed", model=model)
            except Exception as e:
                log.warning("prewarm_failed", model=model, error=str(e))

        # Start pre-warming in background
        self._prewarm_tasks[model] = asyncio.create_task(_do_prewarm())

    async def wait_for_prewarm(self, model: str) -> bool:
        """Wait for a pre-warming task to complete.

        Returns True if model is loaded, False otherwise.
        """
        if model in self._prewarm_tasks:
            task = self._prewarm_tasks[model]
            if not task.done():
                try:
                    await task
                except Exception:
                    pass  # Error already logged in _do_prewarm

        return model in self.loaded

    def get_vram_stats(self) -> dict:
        """Get VRAM usage statistics including cache metrics."""
        used = sum(m.vram_gb for m in self.loaded.values())
        return {
            "total": self.total_vram,
            "available": self.available,
            "used": used,
            "free": self.available - used,
            "loaded_models": list(self.loaded.keys())
        }

    def get_cache_stats(self) -> dict:
        """Get cache performance statistics."""
        return {
            "hits": self.metrics.hits,
            "misses": self.metrics.misses,
            "evictions": self.metrics.evictions,
            "hit_rate": self.metrics.hit_rate,
            "avg_load_time": self.metrics.avg_load_time,
            "total_load_time": self.metrics.total_load_time,
            "prewarm_count": self.metrics.prewarm_count,
            "keep_warm": list(self.keep_warm),
            "models": {
                name: {
                    "use_count": m.use_count,
                    "vram_gb": m.vram_gb,
                    "load_time": m.load_time,
                    "lifetime": time.time() - m.loaded_at
                }
                for name, m in self.loaded.items()
            }
        }

    def add_keep_warm(self, model: str) -> None:
        """Add a model to the keep-warm list (won't be evicted)."""
        self.keep_warm.add(model)
        log.info("model_added_to_keep_warm", model=model)

    def remove_keep_warm(self, model: str) -> None:
        """Remove a model from the keep-warm list."""
        self.keep_warm.discard(model)
        log.info("model_removed_from_keep_warm", model=model)
