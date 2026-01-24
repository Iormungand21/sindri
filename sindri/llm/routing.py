"""Model routing data models and task classification.

This module provides the core data structures for model-aware routing:
- RoutingTaskCategory: Task categories for routing decisions
- ModelCapabilities: Model traits and performance metrics
- RoutingDecision: Result of a routing decision
- RoutingPreferences: Per-project routing preferences
- TaskClassifier: Classifies tasks into routing categories
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import structlog

log = structlog.get_logger()


class RoutingTaskCategory(str, Enum):
    """Categories for model routing decisions.

    Extends the existing TaskCategory from curator.py with additional
    categories for specialized routing decisions.
    """

    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    DEBUGGING = "debugging"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    REASONING = "reasoning"
    CREATIVE = "creative"
    DATA = "data"
    DOMAIN_SPECIFIC = "domain_specific"
    GENERAL = "general"


@dataclass
class ModelCapabilities:
    """Model traits for routing decisions.

    Attributes:
        name: Model identifier (e.g., 'qwen2.5-coder:14b')
        vram_gb: VRAM requirement in GB
        context_length: Maximum context window size
        strengths: Capability scores (0.0-1.0) per task category
        avg_latency_ms: Average response latency in milliseconds
        avg_tokens_per_sec: Average token generation rate
        quality_score: Baseline quality score (0.0-1.0)
        specialized_for: List of categories this model is specialized for
    """

    name: str
    vram_gb: float
    context_length: int
    strengths: dict[RoutingTaskCategory, float] = field(default_factory=dict)
    avg_latency_ms: float = 0.0
    avg_tokens_per_sec: float = 0.0
    quality_score: float = 0.5
    specialized_for: list[RoutingTaskCategory] = field(default_factory=list)

    def get_strength(self, category: RoutingTaskCategory) -> float:
        """Get strength score for a category, defaulting to 0.3."""
        return self.strengths.get(category, 0.3)

    def is_specialized_for(self, category: RoutingTaskCategory) -> bool:
        """Check if model is specialized for a category."""
        return category in self.specialized_for


@dataclass
class RoutingDecision:
    """Result of a routing decision.

    Attributes:
        primary_model: Selected primary model
        primary_vram: VRAM requirement for primary model
        fallback_model: Fallback model if primary fails
        fallback_vram: VRAM requirement for fallback model
        reason: Explanation for the routing decision
        score: Confidence score for the decision
        already_loaded: Whether primary model is already loaded
        category: The classified task category
    """

    primary_model: str
    primary_vram: float
    fallback_model: Optional[str] = None
    fallback_vram: Optional[float] = None
    reason: str = ""
    score: float = 0.0
    already_loaded: bool = False
    category: Optional[RoutingTaskCategory] = None


@dataclass
class RoutingPreferences:
    """Per-project routing preferences.

    Attributes:
        model_overrides: Override models for specific task categories
        speed_preference: Speed vs quality tradeoff (0.0=quality, 1.0=speed)
        locked_models: Lock specific agents to specific models
        min_quality_score: Minimum acceptable model quality score
        prefer_loaded_models: Whether to prefer already-loaded models for latency
    """

    model_overrides: dict[RoutingTaskCategory, str] = field(default_factory=dict)
    speed_preference: float = 0.5
    locked_models: dict[str, str] = field(default_factory=dict)
    min_quality_score: float = 0.3
    prefer_loaded_models: bool = True

    def get_override(self, category: RoutingTaskCategory) -> Optional[str]:
        """Get model override for a category if set."""
        return self.model_overrides.get(category)

    def get_locked_model(self, agent_name: str) -> Optional[str]:
        """Get locked model for an agent if set."""
        return self.locked_models.get(agent_name)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "model_overrides": {k.value: v for k, v in self.model_overrides.items()},
            "speed_preference": self.speed_preference,
            "locked_models": self.locked_models,
            "min_quality_score": self.min_quality_score,
            "prefer_loaded_models": self.prefer_loaded_models,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RoutingPreferences":
        """Create from dictionary."""
        model_overrides = {}
        for k, v in data.get("model_overrides", {}).items():
            try:
                model_overrides[RoutingTaskCategory(k)] = v
            except ValueError:
                log.warning("unknown_routing_category", category=k)

        return cls(
            model_overrides=model_overrides,
            speed_preference=data.get("speed_preference", 0.5),
            locked_models=data.get("locked_models", {}),
            min_quality_score=data.get("min_quality_score", 0.3),
            prefer_loaded_models=data.get("prefer_loaded_models", True),
        )


class TaskClassifier:
    """Classifies tasks into routing categories.

    Uses regex patterns to classify task descriptions into categories
    for model routing decisions. Extended from DataCurator patterns.
    """

    # Patterns ordered from most specific to least specific
    CATEGORY_PATTERNS: dict[RoutingTaskCategory, list[str]] = {
        # Domain-specific (most specific)
        RoutingTaskCategory.DOMAIN_SPECIFIC: [
            r"\bkicad\b|\bpcb\b|electronics|schematic|circuit",
            r"\bgame\s+level\b|tilemap|dungeon|procedural\s+generation",
            r"\bblender\b|3d\s+model|mesh|render\s+scene",
            r"\bopenscad\b|parametric|stl|3d\s+print",
        ],
        # Creative tasks
        RoutingTaskCategory.CREATIVE: [
            r"\bmusic\b|midi|abc\s+notation|compose|arrangement",
            r"\bdiagram\b|mermaid|plantuml|d2\s+diagram",
            r"\blatex\b|tikz|beamer|document\s+format",
            r"\bvisualization\b|chart|dashboard|d3\.js|plotly",
        ],
        # Data and SQL tasks
        RoutingTaskCategory.DATA: [
            r"\bsql\b|\bquery\b|database|select\s+from|join\s+on",
            r"\bdata\s+analysis\b|statistics|dataframe|pandas",
            r"\bmath\b|equation|calculate|formula|matrix",
        ],
        # Testing tasks (specific)
        RoutingTaskCategory.TESTING: [
            r"\btest\b|\btests\b|pytest|unittest|spec\b|coverage",
            r"write\s+tests|add\s+tests|test\s+file|unit\s+test",
            r"test\s+case|mock|fixture|assertion",
        ],
        # Debugging tasks
        RoutingTaskCategory.DEBUGGING: [
            r"\bdebug\b|trace\b|investigate|figure\s+out|find.*cause",
            r"why\s+is|what'?s\s+causing|troubleshoot|root\s+cause",
            r"\bbug\b|\berror\b|broken|not\s+working|crash",
            r"doesn'?t\s+work|failing|\bproblem\b",
        ],
        # Documentation tasks
        RoutingTaskCategory.DOCUMENTATION: [
            r"\bdocument\b|readme|docstring|add\s+docs",
            r"write\s+documentation|update\s+docs|api\s+docs",
            r"\bexplain\b|how\s+does|what\s+is|describe\b",
            r"help\s+me\s+understand|walk\s+through",
        ],
        # Code review tasks
        RoutingTaskCategory.CODE_REVIEW: [
            r"\breview\b|\baudit\b|\binspect\b|check\s+code",
            r"look\s+at|evaluate|assess|analyze\s+code",
            r"code\s+quality|code\s+smell|security\s+audit",
        ],
        # Reasoning/planning tasks
        RoutingTaskCategory.REASONING: [
            r"\bplan\b|design|architecture|algorithm",
            r"think\s+through|reason\s+about|strategy",
            r"\brefactor\b|restructure|reorganize",
            r"optimize|improve\s+performance",
        ],
        # Code generation (most general coding task)
        RoutingTaskCategory.CODE_GENERATION: [
            r"\bcreate\b|\bwrite\b|\bimplement\b|\bbuild\b|\bgenerate\b",
            r"add\s+.*function|make\s+.*class|new\s+feature",
            r"\bcode\b|\bscript\b|\bprogram\b",
        ],
    }

    def classify(self, task: str) -> RoutingTaskCategory:
        """Classify task into a routing category.

        Args:
            task: Task description to classify

        Returns:
            RoutingTaskCategory for the task
        """
        task_lower = task.lower()

        for category, patterns in self.CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, task_lower):
                    log.debug(
                        "task_classified",
                        task=task[:50],
                        category=category.value,
                        pattern=pattern,
                    )
                    return category

        return RoutingTaskCategory.GENERAL

    def classify_with_confidence(
        self, task: str
    ) -> tuple[RoutingTaskCategory, float]:
        """Classify task with a confidence score.

        Args:
            task: Task description to classify

        Returns:
            Tuple of (category, confidence) where confidence is 0.0-1.0
        """
        task_lower = task.lower()
        matches: dict[RoutingTaskCategory, int] = {}

        for category, patterns in self.CATEGORY_PATTERNS.items():
            match_count = 0
            for pattern in patterns:
                if re.search(pattern, task_lower):
                    match_count += 1
            if match_count > 0:
                matches[category] = match_count

        if not matches:
            return RoutingTaskCategory.GENERAL, 0.3

        # Return category with most pattern matches
        best_category = max(matches.keys(), key=lambda k: matches[k])
        # Confidence based on number of matching patterns
        confidence = min(1.0, 0.5 + (matches[best_category] * 0.15))

        return best_category, confidence
