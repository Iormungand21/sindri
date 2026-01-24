"""Model-aware routing for task-based model selection.

This module provides the ModelRouter class which selects optimal models
based on task type, VRAM availability, and per-project preferences.

ROADMAP Item 10: Model-Aware Routing
- Lightweight router for model selection by task type
- VRAM-aware fallback + cost/latency heuristics
- Per-project model preferences
"""

from typing import TYPE_CHECKING, Optional

import structlog

from sindri.llm.capabilities import MODEL_CAPABILITIES, get_capabilities
from sindri.llm.routing import (
    ModelCapabilities,
    RoutingDecision,
    RoutingPreferences,
    RoutingTaskCategory,
    TaskClassifier,
)

if TYPE_CHECKING:
    from sindri.llm.manager import ModelManager

log = structlog.get_logger()


class ModelRouter:
    """Lightweight model router for task-based model selection.

    Selects optimal model based on:
    1. Task category classification
    2. Current VRAM availability
    3. Model capability scores
    4. Per-project preferences
    5. Already-loaded models (latency optimization)

    Attributes:
        model_manager: Reference to ModelManager for VRAM checks
        capabilities: Model capabilities registry
        preferences: Per-project routing preferences
    """

    def __init__(
        self,
        model_manager: Optional["ModelManager"] = None,
        capabilities: Optional[dict[str, ModelCapabilities]] = None,
        preferences: Optional[RoutingPreferences] = None,
    ):
        """Initialize the model router.

        Args:
            model_manager: ModelManager for VRAM availability checks
            capabilities: Model capabilities registry (uses default if None)
            preferences: Routing preferences (uses defaults if None)
        """
        self.model_manager = model_manager
        self.capabilities = capabilities or MODEL_CAPABILITIES
        self.preferences = preferences or RoutingPreferences()
        self._classifier = TaskClassifier()

        log.info(
            "model_router_initialized",
            model_count=len(self.capabilities),
            speed_preference=self.preferences.speed_preference,
        )

    def route(
        self,
        task_description: str,
        agent_default_model: str,
        agent_default_vram: float,
        agent_fallback_model: Optional[str] = None,
        agent_fallback_vram: Optional[float] = None,
        context: Optional[dict] = None,
    ) -> RoutingDecision:
        """Select optimal model for a task.

        The routing logic:
        1. Check for locked model (agent-specific override)
        2. Classify the task into a category
        3. Check for category override in preferences
        4. Score candidate models by capability
        5. Filter by VRAM availability
        6. Prefer already-loaded models for latency
        7. Select best match with fallback chain

        Args:
            task_description: Description of the task
            agent_default_model: Agent's configured primary model
            agent_default_vram: Agent's primary model VRAM requirement
            agent_fallback_model: Agent's fallback model
            agent_fallback_vram: Agent's fallback VRAM requirement
            context: Additional context (agent name, task_type, etc.)

        Returns:
            RoutingDecision with selected model(s) and reasoning
        """
        context = context or {}
        agent_name = context.get("agent")

        # 1. Check for locked model (highest priority)
        if agent_name and self.preferences.get_locked_model(agent_name):
            locked_model = self.preferences.locked_models[agent_name]
            locked_caps = get_capabilities(locked_model)
            locked_vram = locked_caps.vram_gb if locked_caps else agent_default_vram

            log.debug(
                "routing_locked_model",
                agent=agent_name,
                locked_model=locked_model,
            )

            return RoutingDecision(
                primary_model=locked_model,
                primary_vram=locked_vram,
                fallback_model=agent_fallback_model,
                fallback_vram=agent_fallback_vram,
                reason=f"locked:{agent_name}",
                score=1.0,
                already_loaded=self._is_loaded(locked_model),
                category=None,
            )

        # 2. Classify the task
        category, confidence = self._classifier.classify_with_confidence(
            task_description
        )

        log.debug(
            "task_classified_for_routing",
            task=task_description[:50],
            category=category.value,
            confidence=confidence,
        )

        # 3. Check for category override in preferences
        override_model = self.preferences.get_override(category)
        if override_model:
            override_caps = get_capabilities(override_model)
            if override_caps and self._can_load(override_model, override_caps.vram_gb):
                log.debug(
                    "routing_category_override",
                    category=category.value,
                    override_model=override_model,
                )

                return RoutingDecision(
                    primary_model=override_model,
                    primary_vram=override_caps.vram_gb,
                    fallback_model=agent_fallback_model,
                    fallback_vram=agent_fallback_vram,
                    reason=f"override:{category.value}",
                    score=override_caps.get_strength(category),
                    already_loaded=self._is_loaded(override_model),
                    category=category,
                )

        # 4. Score candidate models
        candidates = self._score_candidates(category, agent_default_vram)

        # 5. Filter by VRAM availability
        viable = self._filter_by_vram(candidates)

        # 6. Rank by latency (prefer loaded models)
        ranked = self._rank_by_latency(viable)

        # 7. Select best or fall back to agent default
        if not ranked:
            log.debug(
                "routing_no_viable_candidates",
                category=category.value,
                using_default=agent_default_model,
            )

            return RoutingDecision(
                primary_model=agent_default_model,
                primary_vram=agent_default_vram,
                fallback_model=agent_fallback_model,
                fallback_vram=agent_fallback_vram,
                reason="no_viable_candidates",
                score=0.5,
                already_loaded=self._is_loaded(agent_default_model),
                category=category,
            )

        best = ranked[0]
        best_score = best.get_strength(category)

        # Find fallback from remaining viable candidates
        fallback = None
        fallback_vram = agent_fallback_vram
        for candidate in ranked[1:]:
            if candidate.vram_gb < best.vram_gb:
                fallback = candidate.name
                fallback_vram = candidate.vram_gb
                break

        # If no smaller candidate found, use agent's fallback
        if not fallback:
            fallback = agent_fallback_model
            fallback_vram = agent_fallback_vram

        decision = RoutingDecision(
            primary_model=best.name,
            primary_vram=best.vram_gb,
            fallback_model=fallback,
            fallback_vram=fallback_vram,
            reason=f"routed:{category.value}",
            score=best_score,
            already_loaded=self._is_loaded(best.name),
            category=category,
        )

        log.info(
            "model_routed",
            task=task_description[:50],
            category=category.value,
            primary_model=decision.primary_model,
            agent_default=agent_default_model,
            score=decision.score,
            already_loaded=decision.already_loaded,
            reason=decision.reason,
        )

        return decision

    def _score_candidates(
        self,
        category: RoutingTaskCategory,
        max_vram: float,
    ) -> list[tuple[ModelCapabilities, float]]:
        """Score models for a task category.

        Args:
            category: Task category to score for
            max_vram: Maximum VRAM to consider (with some flexibility)

        Returns:
            List of (ModelCapabilities, score) sorted by score descending
        """
        scored = []

        for name, caps in self.capabilities.items():
            # Allow some VRAM flexibility (1.5x the agent's allocation)
            if caps.vram_gb > max_vram * 1.5:
                continue

            # Skip models below minimum quality threshold
            if caps.quality_score < self.preferences.min_quality_score:
                continue

            # Base score from category strength
            score = caps.get_strength(category)

            # Boost for specialization (20% bonus)
            if caps.is_specialized_for(category):
                score *= 1.2

            # Factor in overall quality score
            score *= 0.5 + caps.quality_score * 0.5

            # Apply speed preference (0=quality, 1=speed)
            if self.preferences.speed_preference > 0.5:
                # Prefer smaller/faster models when speed is prioritized
                speed_factor = self.preferences.speed_preference
                # Smaller models get bonus, larger models get penalty
                vram_penalty = (caps.vram_gb / 14.0) * 0.3 * speed_factor
                score -= vram_penalty

            scored.append((caps, score))

        # Sort by score descending
        return sorted(scored, key=lambda x: x[1], reverse=True)

    def _filter_by_vram(
        self,
        candidates: list[tuple[ModelCapabilities, float]],
    ) -> list[ModelCapabilities]:
        """Filter candidates to models that can actually load.

        Args:
            candidates: List of (ModelCapabilities, score) tuples

        Returns:
            List of ModelCapabilities that can load
        """
        viable = []
        for caps, score in candidates:
            if self._can_load(caps.name, caps.vram_gb):
                viable.append(caps)
        return viable

    def _rank_by_latency(
        self,
        candidates: list[ModelCapabilities],
    ) -> list[ModelCapabilities]:
        """Rank candidates preferring already-loaded models.

        Args:
            candidates: List of viable ModelCapabilities

        Returns:
            Reordered list with loaded models first (if prefer_loaded_models is True)
        """
        # If prefer_loaded_models is disabled, return candidates as-is (by score)
        if not self.preferences.prefer_loaded_models:
            return candidates

        loaded = []
        not_loaded = []

        for caps in candidates:
            if self._is_loaded(caps.name):
                loaded.append(caps)
            else:
                not_loaded.append(caps)

        # Loaded models come first for latency optimization
        return loaded + not_loaded

    def _is_loaded(self, model: str) -> bool:
        """Check if model is currently loaded."""
        if not self.model_manager:
            return False
        return model in self.model_manager.loaded

    def _can_load(self, model: str, vram_gb: float) -> bool:
        """Check if model can be loaded (with eviction if needed)."""
        if not self.model_manager:
            # Without model manager, assume all models can load
            return True
        return self.model_manager.can_load(model, vram_gb)

    def update_preferences(self, preferences: RoutingPreferences) -> None:
        """Update routing preferences.

        Args:
            preferences: New routing preferences
        """
        self.preferences = preferences
        log.info(
            "routing_preferences_updated",
            speed_preference=preferences.speed_preference,
            override_count=len(preferences.model_overrides),
            locked_count=len(preferences.locked_models),
        )

    def get_routing_stats(self) -> dict:
        """Get routing statistics.

        Returns:
            Dictionary with routing statistics
        """
        stats = {
            "model_count": len(self.capabilities),
            "speed_preference": self.preferences.speed_preference,
            "min_quality_score": self.preferences.min_quality_score,
            "override_count": len(self.preferences.model_overrides),
            "locked_count": len(self.preferences.locked_models),
        }

        if self.model_manager:
            stats["loaded_models"] = list(self.model_manager.loaded.keys())
            stats["available_vram"] = self.model_manager._get_free_vram()

        return stats
