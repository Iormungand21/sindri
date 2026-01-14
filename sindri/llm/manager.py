"""VRAM-aware model management for AMD 6950XT (16GB)."""

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
    """Manages model loading with VRAM constraints."""

    def __init__(self, total_vram_gb: float = 16.0, reserve_gb: float = 2.0):
        self.total_vram = total_vram_gb
        self.reserve = reserve_gb
        self.available = total_vram_gb - reserve_gb
        self.loaded: dict[str, LoadedModel] = {}
        self._client = ollama.Client()

        log.info("model_manager_initialized",
                 total_vram=total_vram_gb,
                 available=self.available)

    def can_load(self, model: str, required_vram: float) -> bool:
        """Check if model can be loaded without eviction."""
        if model in self.loaded:
            return True

        free_vram = self._get_free_vram()
        can = free_vram >= required_vram

        log.debug("can_load_check",
                  model=model,
                  required=required_vram,
                  free=free_vram,
                  can_load=can)

        return can

    def _get_free_vram(self) -> float:
        """Calculate free VRAM."""
        used = sum(m.vram_gb for m in self.loaded.values())
        return self.available - used

    async def ensure_loaded(self, model: str, required_vram: float) -> bool:
        """Ensure model is loaded, evicting others if needed."""

        if model in self.loaded:
            # Update last used time
            self.loaded[model].last_used = time.time()
            log.debug("model_already_loaded", model=model)
            return True

        log.info("loading_model", model=model, required_vram=required_vram)

        # Need to free up space?
        while self._get_free_vram() < required_vram and self.loaded:
            # Evict least recently used
            lru = min(self.loaded.values(), key=lambda m: m.last_used)
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
