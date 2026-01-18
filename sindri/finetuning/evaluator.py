"""Model evaluation for comparing fine-tuned models.

This module provides functionality for:
- Benchmarking models against test prompts
- Comparing before/after performance
- Measuring response quality metrics
- A/B testing between models
"""

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
import structlog

from sindri.llm.client import OllamaClient
from sindri.finetuning.registry import ModelRegistry, FineTunedModel

log = structlog.get_logger()


class EvalMetric(str, Enum):
    """Evaluation metrics."""

    RESPONSE_TIME = "response_time"  # Time to generate response
    TOKEN_COUNT = "token_count"  # Number of tokens generated
    CODE_QUALITY = "code_quality"  # Code structure/syntax score
    RELEVANCE = "relevance"  # How relevant is the response
    COMPLETENESS = "completeness"  # Does it fully answer the prompt
    CORRECTNESS = "correctness"  # Is the answer correct (if verifiable)


@dataclass
class BenchmarkPrompt:
    """A prompt for benchmarking models.

    Attributes:
        id: Unique identifier
        prompt: The test prompt
        category: Task category (code_generation, debugging, etc.)
        expected_patterns: Regex patterns expected in good responses
        forbidden_patterns: Patterns that indicate poor responses
        max_tokens: Maximum tokens for the response
        expected_answer: Optional expected answer for correctness checking
    """

    id: str
    prompt: str
    category: str = "general"
    expected_patterns: list[str] = field(default_factory=list)
    forbidden_patterns: list[str] = field(default_factory=list)
    max_tokens: int = 1024
    expected_answer: Optional[str] = None


@dataclass
class EvaluationResult:
    """Result of evaluating a model on a single prompt.

    Attributes:
        prompt_id: ID of the benchmark prompt
        model_name: Name of the model evaluated
        response: The model's response
        metrics: Dictionary of metric scores
        response_time_ms: Time to generate response in milliseconds
        token_count: Number of tokens in response
        passed_patterns: Number of expected patterns matched
        failed_patterns: Number of forbidden patterns found
        score: Overall score (0-1)
        timestamp: When the evaluation was run
    """

    prompt_id: str
    model_name: str
    response: str
    metrics: dict[str, float] = field(default_factory=dict)
    response_time_ms: float = 0.0
    token_count: int = 0
    passed_patterns: int = 0
    failed_patterns: int = 0
    score: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "prompt_id": self.prompt_id,
            "model_name": self.model_name,
            "response_preview": self.response[:200] if self.response else "",
            "metrics": self.metrics,
            "response_time_ms": round(self.response_time_ms, 2),
            "token_count": self.token_count,
            "passed_patterns": self.passed_patterns,
            "failed_patterns": self.failed_patterns,
            "score": round(self.score, 3),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class BenchmarkSuite:
    """A collection of benchmark prompts for evaluation.

    Attributes:
        name: Suite name
        description: Suite description
        prompts: List of benchmark prompts
        created_at: When the suite was created
    """

    name: str
    description: str = ""
    prompts: list[BenchmarkPrompt] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def default_coding_suite(cls) -> "BenchmarkSuite":
        """Create a default suite for evaluating coding models."""
        prompts = [
            BenchmarkPrompt(
                id="code_gen_1",
                prompt="Write a Python function that checks if a number is prime. Include type hints and a docstring.",
                category="code_generation",
                expected_patterns=[
                    r"def\s+\w+\s*\(",  # Function definition
                    r":\s*bool",  # Return type hint
                    r'""".*"""',  # Docstring
                    r"return\s+(True|False)",  # Return statement
                ],
                forbidden_patterns=[
                    r"import\s+sympy",  # Shouldn't use external libs
                ],
            ),
            BenchmarkPrompt(
                id="code_gen_2",
                prompt="Write a Python class for a binary search tree with insert and search methods.",
                category="code_generation",
                expected_patterns=[
                    r"class\s+\w+",  # Class definition
                    r"def\s+insert",  # Insert method
                    r"def\s+search",  # Search method
                    r"self\.left|self\.right",  # Tree structure
                ],
            ),
            BenchmarkPrompt(
                id="debug_1",
                prompt="""Fix this Python code that should reverse a string but has a bug:
```python
def reverse_string(s):
    result = ""
    for i in range(len(s), 0, -1):
        result += s[i]
    return result
```""",
                category="debugging",
                expected_patterns=[
                    r"range\(len\(s\)\s*-\s*1",  # Fixed range
                    r"s\[i\]|s\[-1\]",  # Correct indexing
                ],
                forbidden_patterns=[
                    r"range\(len\(s\),\s*0",  # Bug pattern
                ],
            ),
            BenchmarkPrompt(
                id="refactor_1",
                prompt="""Refactor this code to be more Pythonic:
```python
result = []
for i in range(len(numbers)):
    if numbers[i] > 0:
        result.append(numbers[i] * 2)
```""",
                category="refactoring",
                expected_patterns=[
                    r"\[.*for.*in.*\]",  # List comprehension
                    r"if.*>.*0",  # Condition preserved
                ],
                forbidden_patterns=[
                    r"range\(len\(",  # Anti-pattern should be removed
                ],
            ),
            BenchmarkPrompt(
                id="explain_1",
                prompt="Explain what a Python decorator is and give a simple example.",
                category="explanation",
                expected_patterns=[
                    r"@\w+",  # Decorator syntax
                    r"def\s+\w+\s*\(",  # Function example
                    r"wrapper|inner|decorated",  # Common decorator terms
                ],
            ),
            BenchmarkPrompt(
                id="test_gen_1",
                prompt="Write pytest tests for a function `add(a, b)` that adds two numbers.",
                category="testing",
                expected_patterns=[
                    r"def\s+test_",  # Test function
                    r"assert\s+add\(",  # Assert statement
                    r"import\s+pytest|from\s+pytest",  # Pytest import or usage
                ],
            ),
        ]

        return cls(
            name="default_coding",
            description="Default benchmark suite for evaluating coding capabilities",
            prompts=prompts,
        )

    @classmethod
    def quick_suite(cls) -> "BenchmarkSuite":
        """Create a minimal suite for quick evaluation."""
        prompts = [
            BenchmarkPrompt(
                id="quick_1",
                prompt="Write a Python function that returns the factorial of a number.",
                category="code_generation",
                expected_patterns=[r"def\s+\w+", r"return"],
            ),
            BenchmarkPrompt(
                id="quick_2",
                prompt="Explain what recursion is in one paragraph.",
                category="explanation",
                expected_patterns=[r"function|call|itself|base\s*case"],
            ),
        ]

        return cls(
            name="quick",
            description="Quick evaluation suite",
            prompts=prompts,
        )


@dataclass
class ComparisonResult:
    """Result of comparing two models.

    Attributes:
        model_a: First model name
        model_b: Second model name
        results_a: Results for model A
        results_b: Results for model B
        winner: Which model performed better overall
        summary: Summary statistics
    """

    model_a: str
    model_b: str
    results_a: list[EvaluationResult]
    results_b: list[EvaluationResult]
    winner: Optional[str] = None
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model_a": self.model_a,
            "model_b": self.model_b,
            "winner": self.winner,
            "summary": self.summary,
            "prompt_count": len(self.results_a),
        }


class ModelEvaluator:
    """Evaluates and compares fine-tuned models.

    Runs benchmark prompts against models and measures
    performance metrics for comparison.
    """

    def __init__(
        self,
        client: Optional[OllamaClient] = None,
        registry: Optional[ModelRegistry] = None,
    ):
        """Initialize the evaluator.

        Args:
            client: Ollama client for running models
            registry: Model registry for looking up models
        """
        self.client = client or OllamaClient()
        self.registry = registry or ModelRegistry()
        self._results_cache: dict[str, list[EvaluationResult]] = {}

    async def evaluate_model(
        self,
        model_name: str,
        suite: Optional[BenchmarkSuite] = None,
        timeout: float = 60.0,
    ) -> list[EvaluationResult]:
        """Evaluate a model against a benchmark suite.

        Args:
            model_name: Name of the model to evaluate
            suite: Benchmark suite to use (defaults to coding suite)
            timeout: Timeout per prompt in seconds

        Returns:
            List of evaluation results
        """
        suite = suite or BenchmarkSuite.default_coding_suite()
        results = []

        log.info(
            "starting_evaluation",
            model=model_name,
            suite=suite.name,
            prompts=len(suite.prompts),
        )

        for prompt in suite.prompts:
            result = await self._evaluate_prompt(model_name, prompt, timeout)
            results.append(result)

        # Cache results
        cache_key = f"{model_name}:{suite.name}"
        self._results_cache[cache_key] = results

        # Log summary
        avg_score = sum(r.score for r in results) / len(results) if results else 0
        avg_time = (
            sum(r.response_time_ms for r in results) / len(results) if results else 0
        )

        log.info(
            "evaluation_complete",
            model=model_name,
            avg_score=round(avg_score, 3),
            avg_response_time_ms=round(avg_time, 2),
        )

        return results

    async def _evaluate_prompt(
        self,
        model_name: str,
        prompt: BenchmarkPrompt,
        timeout: float,
    ) -> EvaluationResult:
        """Evaluate a model on a single prompt."""
        start_time = time.time()

        try:
            # Generate response
            response = await asyncio.wait_for(
                self.client.generate(
                    model=model_name,
                    prompt=prompt.prompt,
                    options={"num_predict": prompt.max_tokens},
                ),
                timeout=timeout,
            )

            response_time = (time.time() - start_time) * 1000
            response_text = response.get("response", "")

            # Count patterns
            passed = 0
            for pattern in prompt.expected_patterns:
                if re.search(pattern, response_text, re.IGNORECASE | re.DOTALL):
                    passed += 1

            failed = 0
            for pattern in prompt.forbidden_patterns:
                if re.search(pattern, response_text, re.IGNORECASE | re.DOTALL):
                    failed += 1

            # Calculate score
            total_expected = len(prompt.expected_patterns)
            pattern_score = passed / total_expected if total_expected > 0 else 1.0

            # Penalize for forbidden patterns
            penalty = failed * 0.2
            score = max(0.0, pattern_score - penalty)

            # Estimate token count (rough approximation)
            token_count = len(response_text.split())

            # Build metrics
            metrics = {
                EvalMetric.RESPONSE_TIME.value: response_time,
                EvalMetric.TOKEN_COUNT.value: token_count,
                EvalMetric.RELEVANCE.value: pattern_score,
            }

            return EvaluationResult(
                prompt_id=prompt.id,
                model_name=model_name,
                response=response_text,
                metrics=metrics,
                response_time_ms=response_time,
                token_count=token_count,
                passed_patterns=passed,
                failed_patterns=failed,
                score=score,
            )

        except asyncio.TimeoutError:
            return EvaluationResult(
                prompt_id=prompt.id,
                model_name=model_name,
                response="[TIMEOUT]",
                response_time_ms=timeout * 1000,
                score=0.0,
            )
        except Exception as e:
            log.error(
                "evaluation_error",
                model=model_name,
                prompt_id=prompt.id,
                error=str(e),
            )
            return EvaluationResult(
                prompt_id=prompt.id,
                model_name=model_name,
                response=f"[ERROR: {str(e)}]",
                score=0.0,
            )

    async def compare_models(
        self,
        model_a: str,
        model_b: str,
        suite: Optional[BenchmarkSuite] = None,
    ) -> ComparisonResult:
        """Compare two models on a benchmark suite.

        Args:
            model_a: First model name
            model_b: Second model name
            suite: Benchmark suite to use

        Returns:
            ComparisonResult with detailed comparison
        """
        suite = suite or BenchmarkSuite.default_coding_suite()

        log.info(
            "comparing_models",
            model_a=model_a,
            model_b=model_b,
            suite=suite.name,
        )

        # Run evaluations
        results_a = await self.evaluate_model(model_a, suite)
        results_b = await self.evaluate_model(model_b, suite)

        # Calculate summary statistics
        avg_score_a = sum(r.score for r in results_a) / len(results_a) if results_a else 0
        avg_score_b = sum(r.score for r in results_b) / len(results_b) if results_b else 0

        avg_time_a = (
            sum(r.response_time_ms for r in results_a) / len(results_a)
            if results_a
            else 0
        )
        avg_time_b = (
            sum(r.response_time_ms for r in results_b) / len(results_b)
            if results_b
            else 0
        )

        # Count wins per prompt
        wins_a = 0
        wins_b = 0
        for ra, rb in zip(results_a, results_b):
            if ra.score > rb.score:
                wins_a += 1
            elif rb.score > ra.score:
                wins_b += 1

        # Determine winner
        if avg_score_a > avg_score_b + 0.05:  # 5% threshold
            winner = model_a
        elif avg_score_b > avg_score_a + 0.05:
            winner = model_b
        else:
            winner = None  # Tie or too close to call

        summary = {
            "model_a": {
                "avg_score": round(avg_score_a, 3),
                "avg_response_time_ms": round(avg_time_a, 2),
                "prompt_wins": wins_a,
            },
            "model_b": {
                "avg_score": round(avg_score_b, 3),
                "avg_response_time_ms": round(avg_time_b, 2),
                "prompt_wins": wins_b,
            },
            "ties": len(results_a) - wins_a - wins_b,
            "score_diff": round(avg_score_a - avg_score_b, 3),
            "speed_diff_ms": round(avg_time_a - avg_time_b, 2),
        }

        log.info(
            "comparison_complete",
            winner=winner or "tie",
            score_a=round(avg_score_a, 3),
            score_b=round(avg_score_b, 3),
        )

        return ComparisonResult(
            model_a=model_a,
            model_b=model_b,
            results_a=results_a,
            results_b=results_b,
            winner=winner,
            summary=summary,
        )

    async def evaluate_improvement(
        self,
        base_model: str,
        finetuned_model: str,
        suite: Optional[BenchmarkSuite] = None,
    ) -> dict[str, Any]:
        """Evaluate improvement from fine-tuning.

        Compares a base model against its fine-tuned version
        and reports the improvement.

        Args:
            base_model: Original base model
            finetuned_model: Fine-tuned version

        Returns:
            Dictionary with improvement metrics
        """
        comparison = await self.compare_models(base_model, finetuned_model, suite)

        base_score = comparison.summary["model_a"]["avg_score"]
        tuned_score = comparison.summary["model_b"]["avg_score"]

        improvement = tuned_score - base_score
        improvement_pct = (improvement / base_score * 100) if base_score > 0 else 0

        return {
            "base_model": base_model,
            "finetuned_model": finetuned_model,
            "base_score": base_score,
            "finetuned_score": tuned_score,
            "improvement": round(improvement, 3),
            "improvement_pct": round(improvement_pct, 1),
            "is_improved": improvement > 0.05,  # 5% threshold
            "winner": comparison.winner,
            "comparison": comparison.summary,
        }

    async def quick_evaluate(
        self,
        model_name: str,
    ) -> dict[str, Any]:
        """Quick evaluation with minimal prompts.

        Useful for fast sanity checks during development.

        Args:
            model_name: Model to evaluate

        Returns:
            Quick evaluation summary
        """
        suite = BenchmarkSuite.quick_suite()
        results = await self.evaluate_model(model_name, suite)

        avg_score = sum(r.score for r in results) / len(results) if results else 0
        avg_time = (
            sum(r.response_time_ms for r in results) / len(results) if results else 0
        )

        return {
            "model": model_name,
            "prompts_tested": len(results),
            "avg_score": round(avg_score, 3),
            "avg_response_time_ms": round(avg_time, 2),
            "all_passed": all(r.score >= 0.5 for r in results),
        }

    def get_cached_results(
        self,
        model_name: str,
        suite_name: str = "default_coding",
    ) -> Optional[list[EvaluationResult]]:
        """Get cached evaluation results.

        Args:
            model_name: Model name
            suite_name: Suite name

        Returns:
            Cached results or None
        """
        cache_key = f"{model_name}:{suite_name}"
        return self._results_cache.get(cache_key)

    def clear_cache(self) -> None:
        """Clear the results cache."""
        self._results_cache.clear()
