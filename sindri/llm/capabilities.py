"""Model capabilities registry for routing decisions.

This module contains the MODEL_CAPABILITIES registry which maps model
names to their capabilities, strengths, and performance characteristics.

The capabilities are used by the ModelRouter to select optimal models
for different task types.
"""

from sindri.llm.routing import ModelCapabilities, RoutingTaskCategory


# Model capabilities registry
# Maps model names to their capabilities for routing decisions
MODEL_CAPABILITIES: dict[str, ModelCapabilities] = {
    # ═══════════════════════════════════════════════════════════════════════════════
    # Qwen Coder Models - Primary coding models
    # ═══════════════════════════════════════════════════════════════════════════════
    "qwen2.5-coder:14b": ModelCapabilities(
        name="qwen2.5-coder:14b",
        vram_gb=9.0,
        context_length=32768,
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.95,
            RoutingTaskCategory.CODE_REVIEW: 0.80,
            RoutingTaskCategory.DEBUGGING: 0.85,
            RoutingTaskCategory.TESTING: 0.80,
            RoutingTaskCategory.DOCUMENTATION: 0.70,
            RoutingTaskCategory.REASONING: 0.70,
            RoutingTaskCategory.CREATIVE: 0.60,
            RoutingTaskCategory.DATA: 0.70,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.65,
            RoutingTaskCategory.GENERAL: 0.80,
        },
        quality_score=0.9,
        specialized_for=[
            RoutingTaskCategory.CODE_GENERATION,
            RoutingTaskCategory.DEBUGGING,
        ],
    ),
    "qwen2.5-coder:7b": ModelCapabilities(
        name="qwen2.5-coder:7b",
        vram_gb=5.0,
        context_length=32768,
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.85,
            RoutingTaskCategory.CODE_REVIEW: 0.70,
            RoutingTaskCategory.DEBUGGING: 0.75,
            RoutingTaskCategory.TESTING: 0.75,
            RoutingTaskCategory.DOCUMENTATION: 0.65,
            RoutingTaskCategory.REASONING: 0.60,
            RoutingTaskCategory.CREATIVE: 0.55,
            RoutingTaskCategory.DATA: 0.60,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.60,
            RoutingTaskCategory.GENERAL: 0.70,
        },
        quality_score=0.75,
        specialized_for=[RoutingTaskCategory.CODE_GENERATION],
    ),
    "qwen2.5-coder:3b": ModelCapabilities(
        name="qwen2.5-coder:3b",
        vram_gb=2.5,
        context_length=32768,
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.70,
            RoutingTaskCategory.CODE_REVIEW: 0.55,
            RoutingTaskCategory.DEBUGGING: 0.60,
            RoutingTaskCategory.TESTING: 0.60,
            RoutingTaskCategory.DOCUMENTATION: 0.55,
            RoutingTaskCategory.REASONING: 0.45,
            RoutingTaskCategory.CREATIVE: 0.40,
            RoutingTaskCategory.DATA: 0.50,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.45,
            RoutingTaskCategory.GENERAL: 0.55,
        },
        quality_score=0.55,
        specialized_for=[],
    ),
    "qwen2.5-coder:1.5b": ModelCapabilities(
        name="qwen2.5-coder:1.5b",
        vram_gb=1.0,
        context_length=32768,
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.55,
            RoutingTaskCategory.CODE_REVIEW: 0.40,
            RoutingTaskCategory.DEBUGGING: 0.45,
            RoutingTaskCategory.TESTING: 0.45,
            RoutingTaskCategory.DOCUMENTATION: 0.45,
            RoutingTaskCategory.REASONING: 0.35,
            RoutingTaskCategory.CREATIVE: 0.30,
            RoutingTaskCategory.DATA: 0.40,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.35,
            RoutingTaskCategory.GENERAL: 0.45,
        },
        quality_score=0.40,
        specialized_for=[],
    ),
    # ═══════════════════════════════════════════════════════════════════════════════
    # Qwen Instruct Models - General purpose
    # ═══════════════════════════════════════════════════════════════════════════════
    "qwen2.5:3b-instruct-q8_0": ModelCapabilities(
        name="qwen2.5:3b-instruct-q8_0",
        vram_gb=3.0,
        context_length=32768,
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.60,
            RoutingTaskCategory.CODE_REVIEW: 0.50,
            RoutingTaskCategory.DEBUGGING: 0.55,
            RoutingTaskCategory.TESTING: 0.55,
            RoutingTaskCategory.DOCUMENTATION: 0.60,
            RoutingTaskCategory.REASONING: 0.50,
            RoutingTaskCategory.CREATIVE: 0.50,
            RoutingTaskCategory.DATA: 0.50,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.45,
            RoutingTaskCategory.GENERAL: 0.60,
        },
        quality_score=0.50,
        specialized_for=[],
    ),
    "qwen3:14b": ModelCapabilities(
        name="qwen3:14b",
        vram_gb=10.0,
        context_length=32768,
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.85,
            RoutingTaskCategory.CODE_REVIEW: 0.85,
            RoutingTaskCategory.DEBUGGING: 0.80,
            RoutingTaskCategory.TESTING: 0.75,
            RoutingTaskCategory.DOCUMENTATION: 0.80,
            RoutingTaskCategory.REASONING: 0.90,
            RoutingTaskCategory.CREATIVE: 0.70,
            RoutingTaskCategory.DATA: 0.75,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.70,
            RoutingTaskCategory.GENERAL: 0.85,
        },
        quality_score=0.85,
        specialized_for=[RoutingTaskCategory.REASONING, RoutingTaskCategory.CODE_REVIEW],
    ),
    # ═══════════════════════════════════════════════════════════════════════════════
    # DeepSeek Reasoning Models - Deep reasoning and planning
    # ═══════════════════════════════════════════════════════════════════════════════
    "deepseek-r1:14b": ModelCapabilities(
        name="deepseek-r1:14b",
        vram_gb=9.0,
        context_length=65536,
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.75,
            RoutingTaskCategory.CODE_REVIEW: 0.85,
            RoutingTaskCategory.DEBUGGING: 0.90,
            RoutingTaskCategory.TESTING: 0.70,
            RoutingTaskCategory.DOCUMENTATION: 0.70,
            RoutingTaskCategory.REASONING: 0.95,
            RoutingTaskCategory.CREATIVE: 0.60,
            RoutingTaskCategory.DATA: 0.80,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.70,
            RoutingTaskCategory.GENERAL: 0.80,
        },
        quality_score=0.90,
        specialized_for=[RoutingTaskCategory.REASONING, RoutingTaskCategory.DEBUGGING],
    ),
    "deepseek-r1:8b": ModelCapabilities(
        name="deepseek-r1:8b",
        vram_gb=5.0,
        context_length=65536,
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.65,
            RoutingTaskCategory.CODE_REVIEW: 0.75,
            RoutingTaskCategory.DEBUGGING: 0.80,
            RoutingTaskCategory.TESTING: 0.60,
            RoutingTaskCategory.DOCUMENTATION: 0.60,
            RoutingTaskCategory.REASONING: 0.85,
            RoutingTaskCategory.CREATIVE: 0.50,
            RoutingTaskCategory.DATA: 0.70,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.60,
            RoutingTaskCategory.GENERAL: 0.70,
        },
        quality_score=0.75,
        specialized_for=[RoutingTaskCategory.REASONING],
    ),
    # ═══════════════════════════════════════════════════════════════════════════════
    # Llama Models - Balanced general purpose
    # ═══════════════════════════════════════════════════════════════════════════════
    "llama3.1:8b": ModelCapabilities(
        name="llama3.1:8b",
        vram_gb=5.0,
        context_length=131072,
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.70,
            RoutingTaskCategory.CODE_REVIEW: 0.75,
            RoutingTaskCategory.DEBUGGING: 0.70,
            RoutingTaskCategory.TESTING: 0.65,
            RoutingTaskCategory.DOCUMENTATION: 0.80,
            RoutingTaskCategory.REASONING: 0.70,
            RoutingTaskCategory.CREATIVE: 0.65,
            RoutingTaskCategory.DATA: 0.65,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.60,
            RoutingTaskCategory.GENERAL: 0.75,
        },
        quality_score=0.70,
        specialized_for=[RoutingTaskCategory.DOCUMENTATION],
    ),
    # ═══════════════════════════════════════════════════════════════════════════════
    # Codestral - Mistral's dedicated code model
    # ═══════════════════════════════════════════════════════════════════════════════
    "codestral:22b-v0.1-q4_K_M": ModelCapabilities(
        name="codestral:22b-v0.1-q4_K_M",
        vram_gb=14.0,
        context_length=32768,
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.95,
            RoutingTaskCategory.CODE_REVIEW: 0.85,
            RoutingTaskCategory.DEBUGGING: 0.85,
            RoutingTaskCategory.TESTING: 0.85,
            RoutingTaskCategory.DOCUMENTATION: 0.75,
            RoutingTaskCategory.REASONING: 0.75,
            RoutingTaskCategory.CREATIVE: 0.60,
            RoutingTaskCategory.DATA: 0.75,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.70,
            RoutingTaskCategory.GENERAL: 0.80,
        },
        quality_score=0.90,
        specialized_for=[
            RoutingTaskCategory.CODE_GENERATION,
            RoutingTaskCategory.CODE_REVIEW,
        ],
    ),
    # codestral:22b - default quantization variant (same capabilities as q4_K_M)
    "codestral:22b": ModelCapabilities(
        name="codestral:22b",
        vram_gb=14.0,
        context_length=32768,  # Verified via ollama show
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.95,
            RoutingTaskCategory.CODE_REVIEW: 0.85,
            RoutingTaskCategory.DEBUGGING: 0.85,
            RoutingTaskCategory.TESTING: 0.85,
            RoutingTaskCategory.DOCUMENTATION: 0.75,
            RoutingTaskCategory.REASONING: 0.75,
            RoutingTaskCategory.CREATIVE: 0.60,
            RoutingTaskCategory.DATA: 0.75,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.70,
            RoutingTaskCategory.GENERAL: 0.80,
        },
        quality_score=0.90,
        specialized_for=[
            RoutingTaskCategory.CODE_GENERATION,
            RoutingTaskCategory.CODE_REVIEW,
        ],
    ),
    # ═══════════════════════════════════════════════════════════════════════════════
    # Mistral Nemo - General purpose mid-size model
    # ═══════════════════════════════════════════════════════════════════════════════
    "mistral-nemo:12b": ModelCapabilities(
        name="mistral-nemo:12b",
        vram_gb=8.0,
        context_length=1024000,  # Verified via ollama show
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.80,
            RoutingTaskCategory.CODE_REVIEW: 0.80,
            RoutingTaskCategory.DEBUGGING: 0.75,
            RoutingTaskCategory.TESTING: 0.70,
            RoutingTaskCategory.DOCUMENTATION: 0.85,
            RoutingTaskCategory.REASONING: 0.80,
            RoutingTaskCategory.CREATIVE: 0.75,
            RoutingTaskCategory.DATA: 0.70,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.70,
            RoutingTaskCategory.GENERAL: 0.85,
        },
        quality_score=0.82,
        specialized_for=[RoutingTaskCategory.DOCUMENTATION, RoutingTaskCategory.GENERAL],
    ),
    # ═══════════════════════════════════════════════════════════════════════════════
    # Gemma 2 - Google's efficient large model
    # ═══════════════════════════════════════════════════════════════════════════════
    "gemma2:27b": ModelCapabilities(
        name="gemma2:27b",
        vram_gb=18.0,
        context_length=8192,  # Verified via ollama show
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.85,
            RoutingTaskCategory.CODE_REVIEW: 0.85,
            RoutingTaskCategory.DEBUGGING: 0.80,
            RoutingTaskCategory.TESTING: 0.75,
            RoutingTaskCategory.DOCUMENTATION: 0.85,
            RoutingTaskCategory.REASONING: 0.90,
            RoutingTaskCategory.CREATIVE: 0.80,
            RoutingTaskCategory.DATA: 0.80,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.75,
            RoutingTaskCategory.GENERAL: 0.90,
        },
        quality_score=0.88,
        specialized_for=[RoutingTaskCategory.REASONING, RoutingTaskCategory.GENERAL],
    ),
    # ═══════════════════════════════════════════════════════════════════════════════
    # Qwen 2.5 Large - High-capability general purpose
    # ═══════════════════════════════════════════════════════════════════════════════
    "qwen2.5:32b": ModelCapabilities(
        name="qwen2.5:32b",
        vram_gb=20.0,
        context_length=32768,  # Verified via ollama show
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.90,
            RoutingTaskCategory.CODE_REVIEW: 0.90,
            RoutingTaskCategory.DEBUGGING: 0.85,
            RoutingTaskCategory.TESTING: 0.80,
            RoutingTaskCategory.DOCUMENTATION: 0.90,
            RoutingTaskCategory.REASONING: 0.95,
            RoutingTaskCategory.CREATIVE: 0.80,
            RoutingTaskCategory.DATA: 0.85,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.80,
            RoutingTaskCategory.GENERAL: 0.92,
        },
        quality_score=0.92,
        specialized_for=[RoutingTaskCategory.REASONING, RoutingTaskCategory.GENERAL],
    ),
    # ═══════════════════════════════════════════════════════════════════════════════
    # Specialized Models
    # ═══════════════════════════════════════════════════════════════════════════════
    "sqlcoder:7b": ModelCapabilities(
        name="sqlcoder:7b",
        vram_gb=5.0,
        context_length=8192,
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.50,
            RoutingTaskCategory.CODE_REVIEW: 0.40,
            RoutingTaskCategory.DEBUGGING: 0.50,
            RoutingTaskCategory.TESTING: 0.40,
            RoutingTaskCategory.DOCUMENTATION: 0.40,
            RoutingTaskCategory.REASONING: 0.50,
            RoutingTaskCategory.CREATIVE: 0.30,
            RoutingTaskCategory.DATA: 0.95,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.40,
            RoutingTaskCategory.GENERAL: 0.45,
        },
        quality_score=0.85,
        specialized_for=[RoutingTaskCategory.DATA],
    ),
    "mathstral:7b": ModelCapabilities(
        name="mathstral:7b",
        vram_gb=5.0,
        context_length=32768,
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.55,
            RoutingTaskCategory.CODE_REVIEW: 0.45,
            RoutingTaskCategory.DEBUGGING: 0.55,
            RoutingTaskCategory.TESTING: 0.45,
            RoutingTaskCategory.DOCUMENTATION: 0.50,
            RoutingTaskCategory.REASONING: 0.90,
            RoutingTaskCategory.CREATIVE: 0.40,
            RoutingTaskCategory.DATA: 0.85,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.50,
            RoutingTaskCategory.GENERAL: 0.55,
        },
        quality_score=0.80,
        specialized_for=[RoutingTaskCategory.REASONING, RoutingTaskCategory.DATA],
    ),
    "granite3.2-vision:2b": ModelCapabilities(
        name="granite3.2-vision:2b",
        vram_gb=2.0,
        context_length=8192,
        strengths={
            RoutingTaskCategory.CODE_GENERATION: 0.40,
            RoutingTaskCategory.CODE_REVIEW: 0.35,
            RoutingTaskCategory.DEBUGGING: 0.40,
            RoutingTaskCategory.TESTING: 0.35,
            RoutingTaskCategory.DOCUMENTATION: 0.70,
            RoutingTaskCategory.REASONING: 0.45,
            RoutingTaskCategory.CREATIVE: 0.60,
            RoutingTaskCategory.DATA: 0.50,
            RoutingTaskCategory.DOMAIN_SPECIFIC: 0.75,
            RoutingTaskCategory.GENERAL: 0.50,
        },
        quality_score=0.60,
        specialized_for=[RoutingTaskCategory.DOMAIN_SPECIFIC],
    ),
}


def get_capabilities(model_name: str) -> ModelCapabilities | None:
    """Get capabilities for a model.

    Args:
        model_name: Model identifier

    Returns:
        ModelCapabilities or None if not found
    """
    return MODEL_CAPABILITIES.get(model_name)


def get_models_for_category(
    category: RoutingTaskCategory,
    min_score: float = 0.5,
) -> list[tuple[str, float]]:
    """Get models suitable for a task category.

    Args:
        category: Task category to find models for
        min_score: Minimum strength score required

    Returns:
        List of (model_name, score) tuples sorted by score descending
    """
    results = []
    for name, caps in MODEL_CAPABILITIES.items():
        score = caps.get_strength(category)
        if score >= min_score:
            results.append((name, score))

    return sorted(results, key=lambda x: x[1], reverse=True)


def get_specialized_models(
    category: RoutingTaskCategory,
) -> list[str]:
    """Get models specialized for a category.

    Args:
        category: Task category

    Returns:
        List of model names specialized for the category
    """
    return [
        name
        for name, caps in MODEL_CAPABILITIES.items()
        if caps.is_specialized_for(category)
    ]


def list_all_models() -> list[str]:
    """List all known models."""
    return list(MODEL_CAPABILITIES.keys())
