"""VRAM-aware model management for AMD 6950XT (16GB)."""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional
import ollama
import structlog

log = structlog.get_logger()


@dataclass
class LoadedModel:
    """Represents a loaded model in VRAM."""
    name: str
    vram_gb: float
    last_used: float  # timestamp


class ModelManager:
    """Manages model loading with VRAM constraints.

    Thread-safe for parallel task execution via asyncio locks.
    """

    def __init__(self, total_vram_gb: float = 16.0, reserve_gb: float = 2.0):
        self.total_vram = total_vram_gb
        self.reserve = reserve_gb
        self.available = total_vram_gb - reserve_gb
        self.loaded: dict[str, LoadedModel] = {}
        self._client = ollama.Client()

        # Phase 6.1: Thread-safety for parallel execution
        self._lock = asyncio.Lock()  # Main lock for VRAM operations
        self._model_locks: dict[str, asyncio.Lock] = {}  # Per-model locks

        log.info("model_manager_initialized",
                 total_vram=total_vram_gb,
                 available=self.available)

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
        """
        # Quick check without lock
        if model in self.loaded:
            # Update last used time (atomic for simple assignment)
            self.loaded[model].last_used = time.time()
            log.debug("model_already_loaded", model=model)
            return True

        # Need to load - acquire per-model lock to prevent double-loading
        model_lock = self._get_model_lock(model)
        async with model_lock:
            # Double-check after acquiring lock
            if model in self.loaded:
                self.loaded[model].last_used = time.time()
                log.debug("model_loaded_by_another_task", model=model)
                return True

            log.info("loading_model", model=model, required_vram=required_vram)

            # Acquire main lock for VRAM operations
            async with self._lock:
                # Need to free up space?
                while self._get_free_vram() < required_vram and self.loaded:
                    # Evict least recently used (but not models with active locks)
                    evictable = [
                        m for m in self.loaded.values()
                        if m.name not in self._model_locks
                        or not self._model_locks[m.name].locked()
                    ]
                    if not evictable:
                        log.warning("no_evictable_models", model=model)
                        break

                    lru = min(evictable, key=lambda m: m.last_used)
                    log.info("evicting_model", model=lru.name, reason="LRU")
                    await self._unload(lru.name)

                free_vram = self._get_free_vram()
                if free_vram < required_vram:
                    log.error("insufficient_vram",
                              model=model,
                              required=required_vram,
                              free=free_vram)
                    return False  # Can't fit

                # Track as loaded (Ollama loads on first use)
                self.loaded[model] = LoadedModel(
                    name=model,
                    vram_gb=required_vram,
                    last_used=time.time()
                )

                log.info("model_loaded",
                         model=model,
                         vram_used=required_vram,
                         free_vram=self._get_free_vram())

        return True

    async def _unload(self, model: str):
        """Unload a model from VRAM."""
        # Ollama doesn't have explicit unload API, but we track it
        if model in self.loaded:
            del self.loaded[model]
            log.info("model_unloaded", model=model)

    def get_vram_stats(self) -> dict:
        """Get VRAM usage statistics."""
        used = sum(m.vram_gb for m in self.loaded.values())
        return {
            "total": self.total_vram,
            "available": self.available,
            "used": used,
            "free": self.available - used,
            "loaded_models": list(self.loaded.keys())
        }
