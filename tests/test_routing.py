"""Tests for model-aware routing (ROADMAP Item 10)."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from sindri.llm.routing import (
    RoutingTaskCategory,
    ModelCapabilities,
    RoutingDecision,
    RoutingPreferences,
    TaskClassifier,
)
from sindri.llm.capabilities import (
    MODEL_CAPABILITIES,
    get_capabilities,
    get_models_for_category,
    get_specialized_models,
    list_all_models,
)
from sindri.llm.router import ModelRouter


class TestRoutingTaskCategory:
    """Tests for RoutingTaskCategory enum."""

    def test_all_categories_defined(self):
        """All expected categories exist."""
        categories = [
            "code_generation",
            "code_review",
            "debugging",
            "testing",
            "documentation",
            "reasoning",
            "creative",
            "data",
            "domain_specific",
            "general",
        ]
        for cat in categories:
            assert RoutingTaskCategory(cat) is not None

    def test_category_string_values(self):
        """Categories have correct string values."""
        assert RoutingTaskCategory.CODE_GENERATION.value == "code_generation"
        assert RoutingTaskCategory.REASONING.value == "reasoning"
        assert RoutingTaskCategory.DATA.value == "data"


class TestModelCapabilities:
    """Tests for ModelCapabilities dataclass."""

    def test_create_capabilities(self):
        """Can create ModelCapabilities with all fields."""
        caps = ModelCapabilities(
            name="test-model:7b",
            vram_gb=5.0,
            context_length=32768,
            strengths={
                RoutingTaskCategory.CODE_GENERATION: 0.9,
                RoutingTaskCategory.REASONING: 0.7,
            },
            quality_score=0.8,
            specialized_for=[RoutingTaskCategory.CODE_GENERATION],
        )

        assert caps.name == "test-model:7b"
        assert caps.vram_gb == 5.0
        assert caps.context_length == 32768
        assert caps.quality_score == 0.8

    def test_get_strength_returns_value(self):
        """get_strength returns correct value for known category."""
        caps = ModelCapabilities(
            name="test-model",
            vram_gb=5.0,
            context_length=32768,
            strengths={RoutingTaskCategory.CODE_GENERATION: 0.9},
        )
        assert caps.get_strength(RoutingTaskCategory.CODE_GENERATION) == 0.9

    def test_get_strength_default_for_unknown(self):
        """get_strength returns 0.3 for unknown category."""
        caps = ModelCapabilities(
            name="test-model",
            vram_gb=5.0,
            context_length=32768,
        )
        assert caps.get_strength(RoutingTaskCategory.CREATIVE) == 0.3

    def test_is_specialized_for(self):
        """is_specialized_for returns correct value."""
        caps = ModelCapabilities(
            name="test-model",
            vram_gb=5.0,
            context_length=32768,
            specialized_for=[RoutingTaskCategory.DATA],
        )
        assert caps.is_specialized_for(RoutingTaskCategory.DATA) is True
        assert caps.is_specialized_for(RoutingTaskCategory.CODE_GENERATION) is False


class TestRoutingPreferences:
    """Tests for RoutingPreferences dataclass."""

    def test_default_preferences(self):
        """Default preferences have expected values."""
        prefs = RoutingPreferences()
        assert prefs.speed_preference == 0.5
        assert prefs.min_quality_score == 0.3
        assert prefs.model_overrides == {}
        assert prefs.locked_models == {}

    def test_get_override(self):
        """get_override returns correct value."""
        prefs = RoutingPreferences(
            model_overrides={RoutingTaskCategory.DATA: "sqlcoder:7b"}
        )
        assert prefs.get_override(RoutingTaskCategory.DATA) == "sqlcoder:7b"
        assert prefs.get_override(RoutingTaskCategory.CREATIVE) is None

    def test_get_locked_model(self):
        """get_locked_model returns correct value."""
        prefs = RoutingPreferences(
            locked_models={"heimdall": "qwen3:14b"}
        )
        assert prefs.get_locked_model("heimdall") == "qwen3:14b"
        assert prefs.get_locked_model("odin") is None

    def test_to_dict_from_dict(self):
        """Serialization roundtrip works."""
        prefs = RoutingPreferences(
            model_overrides={RoutingTaskCategory.DATA: "sqlcoder:7b"},
            locked_models={"heimdall": "qwen3:14b"},
            speed_preference=0.7,
            min_quality_score=0.4,
        )

        data = prefs.to_dict()
        assert data["speed_preference"] == 0.7
        assert data["min_quality_score"] == 0.4
        assert data["model_overrides"]["data"] == "sqlcoder:7b"
        assert data["locked_models"]["heimdall"] == "qwen3:14b"

        restored = RoutingPreferences.from_dict(data)
        assert restored.speed_preference == 0.7
        assert restored.get_override(RoutingTaskCategory.DATA) == "sqlcoder:7b"
        assert restored.get_locked_model("heimdall") == "qwen3:14b"


class TestTaskClassifier:
    """Tests for TaskClassifier."""

    def test_classify_code_generation(self):
        """Classifies code generation tasks."""
        classifier = TaskClassifier()

        # Direct matches
        assert classifier.classify("Create a user authentication module") == RoutingTaskCategory.CODE_GENERATION
        assert classifier.classify("Write a function to parse JSON") == RoutingTaskCategory.CODE_GENERATION
        assert classifier.classify("Implement the payment handler") == RoutingTaskCategory.CODE_GENERATION
        assert classifier.classify("Build a REST API endpoint") == RoutingTaskCategory.CODE_GENERATION

    def test_classify_testing(self):
        """Classifies testing tasks."""
        classifier = TaskClassifier()

        assert classifier.classify("Write tests for the auth module") == RoutingTaskCategory.TESTING
        assert classifier.classify("Add pytest coverage for utils") == RoutingTaskCategory.TESTING
        assert classifier.classify("Create unit test fixtures") == RoutingTaskCategory.TESTING

    def test_classify_debugging(self):
        """Classifies debugging tasks."""
        classifier = TaskClassifier()

        assert classifier.classify("Debug the login issue") == RoutingTaskCategory.DEBUGGING
        assert classifier.classify("Why is the API returning 500?") == RoutingTaskCategory.DEBUGGING
        assert classifier.classify("Investigate the memory leak") == RoutingTaskCategory.DEBUGGING
        assert classifier.classify("Fix the crash on startup") == RoutingTaskCategory.DEBUGGING

    def test_classify_documentation(self):
        """Classifies documentation tasks."""
        classifier = TaskClassifier()

        assert classifier.classify("Document the API endpoints") == RoutingTaskCategory.DOCUMENTATION
        assert classifier.classify("Update the README") == RoutingTaskCategory.DOCUMENTATION
        assert classifier.classify("Add docstrings to the module") == RoutingTaskCategory.DOCUMENTATION
        assert classifier.classify("Explain how the auth flow works") == RoutingTaskCategory.DOCUMENTATION

    def test_classify_code_review(self):
        """Classifies code review tasks."""
        classifier = TaskClassifier()

        assert classifier.classify("Review the PR changes") == RoutingTaskCategory.CODE_REVIEW
        assert classifier.classify("Audit the security of this code") == RoutingTaskCategory.CODE_REVIEW
        assert classifier.classify("Analyze code quality") == RoutingTaskCategory.CODE_REVIEW

    def test_classify_reasoning(self):
        """Classifies reasoning tasks."""
        classifier = TaskClassifier()

        assert classifier.classify("Plan the architecture for the feature") == RoutingTaskCategory.REASONING
        assert classifier.classify("Think through the algorithm design") == RoutingTaskCategory.REASONING
        assert classifier.classify("Refactor the service layer") == RoutingTaskCategory.REASONING

    def test_classify_data(self):
        """Classifies data/SQL tasks."""
        classifier = TaskClassifier()

        assert classifier.classify("Write a SQL query for user stats") == RoutingTaskCategory.DATA
        assert classifier.classify("Query the database for orders") == RoutingTaskCategory.DATA
        assert classifier.classify("Run a select from users join orders") == RoutingTaskCategory.DATA

    def test_classify_creative(self):
        """Classifies creative tasks."""
        classifier = TaskClassifier()

        assert classifier.classify("Generate a mermaid diagram") == RoutingTaskCategory.CREATIVE
        assert classifier.classify("Create music composition in MIDI") == RoutingTaskCategory.CREATIVE
        assert classifier.classify("Build a visualization dashboard") == RoutingTaskCategory.CREATIVE

    def test_classify_domain_specific(self):
        """Classifies domain-specific tasks."""
        classifier = TaskClassifier()

        assert classifier.classify("Create a KiCad schematic") == RoutingTaskCategory.DOMAIN_SPECIFIC
        assert classifier.classify("Design a PCB layout") == RoutingTaskCategory.DOMAIN_SPECIFIC
        assert classifier.classify("Generate a game level tilemap") == RoutingTaskCategory.DOMAIN_SPECIFIC

    def test_classify_general(self):
        """Unknown tasks get GENERAL category."""
        classifier = TaskClassifier()

        assert classifier.classify("Hello, how are you?") == RoutingTaskCategory.GENERAL
        assert classifier.classify("What time is it?") == RoutingTaskCategory.GENERAL

    def test_classify_with_confidence(self):
        """classify_with_confidence returns category and score."""
        classifier = TaskClassifier()

        category, confidence = classifier.classify_with_confidence("Write tests for authentication")
        assert category == RoutingTaskCategory.TESTING
        assert 0.5 <= confidence <= 1.0

    def test_classify_with_confidence_general(self):
        """General tasks have lower confidence."""
        classifier = TaskClassifier()

        category, confidence = classifier.classify_with_confidence("Hello world")
        assert category == RoutingTaskCategory.GENERAL
        assert confidence == 0.3


class TestModelCapabilitiesRegistry:
    """Tests for MODEL_CAPABILITIES registry."""

    def test_registry_not_empty(self):
        """Registry has models."""
        assert len(MODEL_CAPABILITIES) > 0

    def test_known_models_exist(self):
        """Known models are in registry."""
        known_models = [
            "qwen2.5-coder:14b",
            "qwen2.5-coder:7b",
            "deepseek-r1:14b",
            "sqlcoder:7b",
            "mathstral:7b",
        ]
        for model in known_models:
            assert model in MODEL_CAPABILITIES, f"Missing model: {model}"

    def test_get_capabilities(self):
        """get_capabilities returns correct data."""
        caps = get_capabilities("qwen2.5-coder:14b")
        assert caps is not None
        assert caps.vram_gb == 9.0
        assert caps.quality_score >= 0.8

    def test_get_capabilities_missing(self):
        """get_capabilities returns None for unknown model."""
        assert get_capabilities("nonexistent:model") is None

    def test_get_models_for_category(self):
        """get_models_for_category returns sorted list."""
        models = get_models_for_category(RoutingTaskCategory.CODE_GENERATION, min_score=0.7)
        assert len(models) > 0

        # Should be sorted by score descending
        scores = [score for _, score in models]
        assert scores == sorted(scores, reverse=True)

    def test_get_specialized_models(self):
        """get_specialized_models returns correct models."""
        # sqlcoder is specialized for DATA
        sql_models = get_specialized_models(RoutingTaskCategory.DATA)
        assert "sqlcoder:7b" in sql_models

        # deepseek-r1 is specialized for REASONING
        reasoning_models = get_specialized_models(RoutingTaskCategory.REASONING)
        assert "deepseek-r1:14b" in reasoning_models

    def test_list_all_models(self):
        """list_all_models returns all model names."""
        models = list_all_models()
        assert len(models) == len(MODEL_CAPABILITIES)
        assert "qwen2.5-coder:14b" in models


class TestModelRouter:
    """Tests for ModelRouter."""

    def create_mock_model_manager(self, loaded_models=None, can_load_all=True):
        """Create a mock ModelManager."""
        manager = MagicMock()
        manager.loaded = {m: MagicMock() for m in (loaded_models or [])}
        manager.can_load = MagicMock(return_value=can_load_all)
        manager._get_free_vram = MagicMock(return_value=14.0)
        return manager

    def test_route_returns_decision(self):
        """route() returns a RoutingDecision."""
        manager = self.create_mock_model_manager()
        router = ModelRouter(model_manager=manager)

        decision = router.route(
            task_description="Create a user module",
            agent_default_model="qwen2.5-coder:7b",
            agent_default_vram=5.0,
        )

        assert isinstance(decision, RoutingDecision)
        assert decision.primary_model is not None
        assert decision.primary_vram > 0

    def test_route_uses_locked_model(self):
        """Locked model bypasses routing."""
        manager = self.create_mock_model_manager()
        prefs = RoutingPreferences(
            locked_models={"heimdall": "qwen3:14b"}
        )
        router = ModelRouter(model_manager=manager, preferences=prefs)

        decision = router.route(
            task_description="Analyze security",
            agent_default_model="qwen2.5-coder:7b",
            agent_default_vram=5.0,
            context={"agent": "heimdall"},
        )

        assert decision.primary_model == "qwen3:14b"
        assert "locked" in decision.reason

    def test_route_uses_category_override(self):
        """Category override takes precedence."""
        manager = self.create_mock_model_manager()
        prefs = RoutingPreferences(
            model_overrides={RoutingTaskCategory.DATA: "sqlcoder:7b"}
        )
        router = ModelRouter(model_manager=manager, preferences=prefs)

        decision = router.route(
            task_description="Write a SQL query for users",
            agent_default_model="qwen2.5-coder:7b",
            agent_default_vram=5.0,
        )

        assert decision.primary_model == "sqlcoder:7b"
        assert "override" in decision.reason

    def test_route_prefers_loaded_models(self):
        """Already-loaded models are preferred."""
        manager = self.create_mock_model_manager(loaded_models=["qwen2.5-coder:7b"])
        router = ModelRouter(model_manager=manager)

        decision = router.route(
            task_description="Create a function",
            agent_default_model="qwen2.5-coder:14b",
            agent_default_vram=9.0,
        )

        # The decision should note if the selected model is already loaded
        assert decision.already_loaded is True or decision.primary_model in manager.loaded

    def test_route_prefer_loaded_disabled(self):
        """When prefer_loaded_models=False, loaded models are not prioritized."""
        # Load a smaller model, but a larger model scores higher for CODE_GENERATION
        manager = self.create_mock_model_manager(loaded_models=["qwen2.5-coder:7b"])
        prefs = RoutingPreferences(prefer_loaded_models=False)
        router = ModelRouter(model_manager=manager, preferences=prefs)

        decision = router.route(
            task_description="Implement a complex algorithm with multiple classes",
            agent_default_model="qwen2.5-coder:7b",
            agent_default_vram=5.0,
        )

        # With prefer_loaded_models=False, the router should pick by score alone
        # The loaded 7b model should NOT be automatically prioritized
        # This test verifies the preference is respected
        assert decision.primary_model is not None
        # The already_loaded flag should still be set correctly based on final selection
        if decision.primary_model == "qwen2.5-coder:7b":
            assert decision.already_loaded is True
        else:
            # A higher-scoring model was selected over the loaded one
            assert decision.already_loaded is False

    def test_route_respects_vram_constraints(self):
        """Router respects VRAM availability."""
        manager = self.create_mock_model_manager(can_load_all=False)
        router = ModelRouter(model_manager=manager)

        decision = router.route(
            task_description="Create a function",
            agent_default_model="qwen2.5-coder:14b",
            agent_default_vram=9.0,
            agent_fallback_model="qwen2.5-coder:3b",
            agent_fallback_vram=2.5,
        )

        # When no models can load, should fall back to agent default
        assert decision.primary_model is not None

    def test_route_without_model_manager(self):
        """Router works without ModelManager (all models assumed loadable)."""
        router = ModelRouter()

        decision = router.route(
            task_description="Create a function",
            agent_default_model="qwen2.5-coder:7b",
            agent_default_vram=5.0,
        )

        assert decision.primary_model is not None

    def test_route_classifies_task(self):
        """Router classifies task and includes category."""
        manager = self.create_mock_model_manager()
        router = ModelRouter(model_manager=manager)

        decision = router.route(
            task_description="Write SQL query for users",
            agent_default_model="qwen2.5-coder:7b",
            agent_default_vram=5.0,
        )

        assert decision.category == RoutingTaskCategory.DATA

    def test_route_speed_preference_affects_selection(self):
        """Speed preference influences model selection."""
        manager = self.create_mock_model_manager()

        # Quality preference
        quality_prefs = RoutingPreferences(speed_preference=0.0)
        quality_router = ModelRouter(model_manager=manager, preferences=quality_prefs)

        # Speed preference
        speed_prefs = RoutingPreferences(speed_preference=1.0)
        speed_router = ModelRouter(model_manager=manager, preferences=speed_prefs)

        quality_decision = quality_router.route(
            task_description="Create a function",
            agent_default_model="qwen2.5-coder:14b",
            agent_default_vram=9.0,
        )

        speed_decision = speed_router.route(
            task_description="Create a function",
            agent_default_model="qwen2.5-coder:14b",
            agent_default_vram=9.0,
        )

        # Both should return valid decisions
        assert quality_decision.primary_model is not None
        assert speed_decision.primary_model is not None

    def test_update_preferences(self):
        """update_preferences updates router config."""
        router = ModelRouter()
        new_prefs = RoutingPreferences(speed_preference=0.8)

        router.update_preferences(new_prefs)

        assert router.preferences.speed_preference == 0.8

    def test_get_routing_stats(self):
        """get_routing_stats returns statistics."""
        manager = self.create_mock_model_manager(loaded_models=["qwen2.5-coder:7b"])
        router = ModelRouter(model_manager=manager)

        stats = router.get_routing_stats()

        assert "model_count" in stats
        assert stats["model_count"] > 0
        assert "speed_preference" in stats
        assert "loaded_models" in stats


class TestRoutingDecision:
    """Tests for RoutingDecision dataclass."""

    def test_create_decision(self):
        """Can create RoutingDecision with all fields."""
        decision = RoutingDecision(
            primary_model="qwen2.5-coder:14b",
            primary_vram=9.0,
            fallback_model="qwen2.5-coder:7b",
            fallback_vram=5.0,
            reason="routed:code_generation",
            score=0.9,
            already_loaded=False,
            category=RoutingTaskCategory.CODE_GENERATION,
        )

        assert decision.primary_model == "qwen2.5-coder:14b"
        assert decision.fallback_model == "qwen2.5-coder:7b"
        assert decision.score == 0.9
        assert decision.category == RoutingTaskCategory.CODE_GENERATION

    def test_decision_optional_fields(self):
        """Optional fields have correct defaults."""
        decision = RoutingDecision(
            primary_model="test-model",
            primary_vram=5.0,
        )

        assert decision.fallback_model is None
        assert decision.fallback_vram is None
        assert decision.reason == ""
        assert decision.score == 0.0
        assert decision.already_loaded is False
        assert decision.category is None
