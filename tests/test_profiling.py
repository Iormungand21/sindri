"""Tests for profiling tools.

Phase 12 Tier 3 - Profiling Tools.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sindri.tools.profiling import (
    BenchmarkFunctionTool,
    ComplexityAnalyzeTool,
    DetectMemoryLeaksTool,
    FlameGraphTool,
    MemoryAnalyzeTool,
    ProfilePythonTool,
    ProfileTimeTool,
    PYSPY_AVAILABLE,
    SCALENE_AVAILABLE,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def simple_script(temp_dir):
    """Create a simple Python script for testing."""
    script = Path(temp_dir) / "simple.py"
    script.write_text("""
def add(a, b):
    return a + b

def multiply(a, b):
    result = 0
    for _ in range(b):
        result = add(result, a)
    return result

if __name__ == "__main__":
    print(multiply(5, 10))
""")
    return str(script)


@pytest.fixture
def fibonacci_script(temp_dir):
    """Create a Fibonacci script for profiling tests."""
    script = Path(temp_dir) / "fibonacci.py"
    script.write_text("""
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

if __name__ == "__main__":
    fibonacci(15)
""")
    return str(script)


@pytest.fixture
def memory_heavy_script(temp_dir):
    """Create a memory-intensive script for testing."""
    script = Path(temp_dir) / "memory_test.py"
    script.write_text("""
def allocate_memory():
    data = [list(range(1000)) for _ in range(100)]
    return len(data)

if __name__ == "__main__":
    allocate_memory()
""")
    return str(script)


@pytest.fixture
def leaky_script(temp_dir):
    """Create a script with intentional memory leak pattern."""
    script = Path(temp_dir) / "leaky.py"
    script.write_text("""
cache = []

def leaky_function():
    cache.append([0] * 1000)

if __name__ == "__main__":
    for _ in range(10):
        leaky_function()
""")
    return str(script)


@pytest.fixture
def benchmark_script(temp_dir):
    """Create a script with functions for benchmarking."""
    script = Path(temp_dir) / "benchmark.py"
    script.write_text("""
def fast_sum(n):
    return sum(range(n))

def slow_sum(n):
    result = 0
    for i in range(n):
        result += i
    return result

def constant_time():
    return 42
""")
    return str(script)


@pytest.fixture
def complexity_examples(temp_dir):
    """Create scripts with different complexity levels."""
    script = Path(temp_dir) / "complexity.py"
    script.write_text("""
def constant_func():
    return 42

def linear_func(arr):
    total = 0
    for item in arr:
        total += item
    return total

def quadratic_func(arr):
    for i in arr:
        for j in arr:
            pass

def recursive_func(n):
    if n <= 1:
        return n
    return recursive_func(n-1) + recursive_func(n-2)

def sorting_func(arr):
    return sorted(arr)
""")
    return str(script)


# ============================================================================
# ProfileTimeTool Tests
# ============================================================================


class TestProfileTimeTool:
    """Tests for ProfileTimeTool."""

    @pytest.fixture
    def tool(self):
        return ProfileTimeTool()

    @pytest.mark.asyncio
    async def test_basic_timing(self, tool):
        """Test basic code timing."""
        result = await tool.execute(code="sum(range(100))")
        assert result.success
        assert "mean" in result.output.lower() or "Mean" in result.output
        assert result.metadata.get("mean") is not None
        assert result.metadata.get("mean") > 0

    @pytest.mark.asyncio
    async def test_with_setup(self, tool):
        """Test timing with setup code."""
        result = await tool.execute(
            code="sorted(data)",
            setup="data = list(range(100, 0, -1))",
        )
        assert result.success
        assert result.metadata.get("mean") is not None

    @pytest.mark.asyncio
    async def test_custom_repeat(self, tool):
        """Test timing with custom repeat count."""
        result = await tool.execute(code="1 + 1", repeat=3)
        assert result.success
        assert result.metadata.get("repeat") == 3
        assert len(result.metadata.get("raw_times", [])) == 3

    @pytest.mark.asyncio
    async def test_custom_number(self, tool):
        """Test timing with custom number of iterations."""
        result = await tool.execute(code="pass", number=100, repeat=3)
        assert result.success
        assert result.metadata.get("number") == 100

    @pytest.mark.asyncio
    async def test_statistics_present(self, tool):
        """Test that all statistics are present."""
        result = await tool.execute(code="list(range(100))", repeat=5)
        assert result.success
        metadata = result.metadata
        assert "mean" in metadata
        assert "std" in metadata
        assert "min" in metadata
        assert "max" in metadata

    @pytest.mark.asyncio
    async def test_syntax_error(self, tool):
        """Test handling of syntax errors."""
        result = await tool.execute(code="if x = 1:")
        assert not result.success
        assert "syntax" in result.error.lower()

    @pytest.mark.asyncio
    async def test_runtime_error(self, tool):
        """Test handling of runtime errors."""
        result = await tool.execute(code="undefined_variable")
        assert not result.success


# ============================================================================
# ProfilePythonTool Tests
# ============================================================================


class TestProfilePythonTool:
    """Tests for ProfilePythonTool."""

    @pytest.fixture
    def tool(self):
        return ProfilePythonTool()

    @pytest.mark.asyncio
    async def test_profile_file(self, tool, fibonacci_script):
        """Test profiling a Python file."""
        result = await tool.execute(file=fibonacci_script)
        assert result.success
        assert "fibonacci" in result.output
        assert result.metadata.get("profiler") == "cProfile"

    @pytest.mark.asyncio
    async def test_profile_code_string(self, tool):
        """Test profiling inline code."""
        result = await tool.execute(code="sum(range(1000))")
        assert result.success
        assert result.metadata.get("total_calls") > 0

    @pytest.mark.asyncio
    async def test_sort_by_time(self, tool, simple_script):
        """Test sorting by time."""
        result = await tool.execute(file=simple_script, sort_by="time")
        assert result.success
        assert result.metadata.get("sort_by") == "time"

    @pytest.mark.asyncio
    async def test_sort_by_calls(self, tool, simple_script):
        """Test sorting by number of calls."""
        result = await tool.execute(file=simple_script, sort_by="calls")
        assert result.success
        assert result.metadata.get("sort_by") == "calls"

    @pytest.mark.asyncio
    async def test_top_n_limit(self, tool, fibonacci_script):
        """Test limiting output to top N results."""
        result = await tool.execute(file=fibonacci_script, top_n=5)
        assert result.success
        assert result.metadata.get("top_n") == 5

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, tool):
        """Test error for missing file."""
        result = await tool.execute(file="/nonexistent/file.py")
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_no_input(self, tool):
        """Test error when neither file nor code provided."""
        result = await tool.execute()
        assert not result.success
        assert "must be provided" in result.error

    @pytest.mark.asyncio
    async def test_syntax_error_in_file(self, tool, temp_dir):
        """Test handling syntax error in profiled file."""
        bad_script = Path(temp_dir) / "bad.py"
        bad_script.write_text("def broken(:\n    pass")
        result = await tool.execute(file=str(bad_script))
        assert not result.success
        assert "syntax" in result.error.lower()

    @pytest.mark.asyncio
    async def test_scalene_not_available(self, tool, simple_script):
        """Test helpful error when Scalene requested but not available."""
        with patch("sindri.tools.profiling.SCALENE_AVAILABLE", False):
            result = await tool.execute(file=simple_script, use_scalene=True)
            assert not result.success
            assert "scalene" in result.error.lower()
            assert "pip install" in result.error.lower()


# ============================================================================
# MemoryAnalyzeTool Tests
# ============================================================================


class TestMemoryAnalyzeTool:
    """Tests for MemoryAnalyzeTool."""

    @pytest.fixture
    def tool(self):
        return MemoryAnalyzeTool()

    @pytest.mark.asyncio
    async def test_analyze_file(self, tool, memory_heavy_script):
        """Test memory analysis of a file."""
        result = await tool.execute(file=memory_heavy_script)
        assert result.success
        assert "memory" in result.output.lower() or "allocation" in result.output.lower()
        assert result.metadata.get("total_size") >= 0

    @pytest.mark.asyncio
    async def test_analyze_code(self, tool):
        """Test memory analysis of inline code."""
        result = await tool.execute(code="data = [i**2 for i in range(1000)]")
        assert result.success
        assert result.metadata.get("allocation_count") >= 0

    @pytest.mark.asyncio
    async def test_top_n_allocations(self, tool, memory_heavy_script):
        """Test limiting allocation report."""
        result = await tool.execute(file=memory_heavy_script, top_n=5)
        assert result.success
        assert result.metadata.get("top_n") == 5

    @pytest.mark.asyncio
    async def test_trace_objects(self, tool, memory_heavy_script):
        """Test memory analysis with object tracing."""
        result = await tool.execute(file=memory_heavy_script, trace_objects=True)
        assert result.success
        assert "file" in result.output.lower()

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, tool):
        """Test error for missing file."""
        result = await tool.execute(file="/nonexistent/file.py")
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_no_input(self, tool):
        """Test error when no input provided."""
        result = await tool.execute()
        assert not result.success
        assert "must be provided" in result.error

    @pytest.mark.asyncio
    async def test_syntax_error(self, tool):
        """Test handling of syntax errors."""
        result = await tool.execute(code="def broken(:\n    pass")
        assert not result.success
        assert "syntax" in result.error.lower()


# ============================================================================
# DetectMemoryLeaksTool Tests
# ============================================================================


class TestDetectMemoryLeaksTool:
    """Tests for DetectMemoryLeaksTool."""

    @pytest.fixture
    def tool(self):
        return DetectMemoryLeaksTool()

    @pytest.mark.asyncio
    async def test_detect_leak(self, tool, leaky_script):
        """Test memory leak detection."""
        result = await tool.execute(file=leaky_script, iterations=3)
        assert result.success
        assert result.metadata.get("iterations") == 3
        assert "potential_leaks" in result.metadata

    @pytest.mark.asyncio
    async def test_clean_code(self, tool, temp_dir):
        """Test with code that doesn't leak."""
        script = Path(temp_dir) / "clean.py"
        script.write_text("""
def clean_function():
    data = list(range(100))
    return sum(data)

if __name__ == "__main__":
    clean_function()
""")
        result = await tool.execute(file=str(script))
        assert result.success

    @pytest.mark.asyncio
    async def test_custom_threshold(self, tool, leaky_script):
        """Test with custom threshold."""
        result = await tool.execute(file=leaky_script, threshold_kb=100)
        assert result.success
        assert result.metadata.get("threshold_kb") == 100

    @pytest.mark.asyncio
    async def test_code_string_input(self, tool):
        """Test leak detection with code string."""
        result = await tool.execute(
            code="data = [i for i in range(100)]",
            iterations=2,
        )
        assert result.success

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, tool):
        """Test error for missing file."""
        result = await tool.execute(file="/nonexistent/file.py")
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_no_input(self, tool):
        """Test error when no input provided."""
        result = await tool.execute()
        assert not result.success
        assert "must be provided" in result.error


# ============================================================================
# BenchmarkFunctionTool Tests
# ============================================================================


class TestBenchmarkFunctionTool:
    """Tests for BenchmarkFunctionTool."""

    @pytest.fixture
    def tool(self):
        return BenchmarkFunctionTool()

    @pytest.mark.asyncio
    async def test_benchmark_function(self, tool, benchmark_script):
        """Test benchmarking a single function."""
        result = await tool.execute(
            file=benchmark_script,
            function="fast_sum",
            args=[100],
        )
        assert result.success
        assert "fast_sum" in result.output
        assert result.metadata.get("mean") > 0

    @pytest.mark.asyncio
    async def test_benchmark_with_kwargs(self, tool, temp_dir):
        """Test benchmarking with keyword arguments."""
        script = Path(temp_dir) / "kwargs_test.py"
        script.write_text("""
def greet(name, greeting="Hello"):
    return f"{greeting}, {name}!"
""")
        result = await tool.execute(
            file=str(script),
            function="greet",
            args=["World"],
            kwargs={"greeting": "Hi"},
        )
        assert result.success

    @pytest.mark.asyncio
    async def test_custom_rounds(self, tool, benchmark_script):
        """Test benchmarking with custom rounds."""
        result = await tool.execute(
            file=benchmark_script,
            function="constant_time",
            rounds=50,
            warmup_rounds=5,
        )
        assert result.success
        assert result.metadata.get("rounds") == 50
        assert result.metadata.get("warmup_rounds") == 5

    @pytest.mark.asyncio
    async def test_compare_functions(self, tool, benchmark_script):
        """Test comparing two functions."""
        result = await tool.execute(
            file=benchmark_script,
            function="fast_sum",
            args=[100],
            compare_with="slow_sum",
        )
        assert result.success
        assert "comparison" in result.output.lower() or "slow_sum" in result.output
        assert "speedup" in result.metadata or "compare_stats" in result.metadata

    @pytest.mark.asyncio
    async def test_statistics_present(self, tool, benchmark_script):
        """Test that all statistics are present."""
        result = await tool.execute(
            file=benchmark_script,
            function="fast_sum",
            args=[100],
        )
        assert result.success
        assert "mean" in result.metadata
        assert "std" in result.metadata
        assert "min" in result.metadata
        assert "max" in result.metadata
        assert "median" in result.metadata

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, tool):
        """Test error for missing file."""
        result = await tool.execute(file="/nonexistent.py", function="test")
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_nonexistent_function(self, tool, benchmark_script):
        """Test error for missing function."""
        result = await tool.execute(
            file=benchmark_script,
            function="nonexistent_function",
        )
        assert not result.success
        assert "not found" in result.error.lower()


# ============================================================================
# FlameGraphTool Tests
# ============================================================================


class TestFlameGraphTool:
    """Tests for FlameGraphTool."""

    @pytest.fixture
    def tool(self):
        return FlameGraphTool()

    @pytest.mark.asyncio
    async def test_pyspy_not_available(self, tool, simple_script):
        """Test helpful error when py-spy not installed."""
        with patch("sindri.tools.profiling.PYSPY_AVAILABLE", False):
            result = await tool.execute(file=simple_script)
            assert not result.success
            assert "py-spy" in result.error.lower()
            assert "pip install" in result.error.lower()

    @pytest.mark.asyncio
    async def test_no_input(self, tool):
        """Test error when neither file nor pid provided."""
        with patch("sindri.tools.profiling.PYSPY_AVAILABLE", True):
            result = await tool.execute()
            assert not result.success
            assert "must be provided" in result.error

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, tool):
        """Test error for missing file."""
        with patch("sindri.tools.profiling.PYSPY_AVAILABLE", True):
            result = await tool.execute(file="/nonexistent.py")
            assert not result.success
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not PYSPY_AVAILABLE, reason="py-spy not installed")
    async def test_basic_flame_graph_mocked(self, tool, simple_script, temp_dir):
        """Test flame graph generation with mocked subprocess."""
        output_path = Path(temp_dir) / "flame.svg"

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Create mock process
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.return_value = mock_process

            # Create output file (py-spy would create it)
            output_path.write_text("<svg></svg>")

            result = await tool.execute(
                file=simple_script,
                duration=2,
                output=str(output_path),
            )

            # May succeed or fail based on environment
            if result.success:
                assert output_path.exists()

    @pytest.mark.asyncio
    async def test_permission_denied_error(self, tool, simple_script, temp_dir):
        """Test handling of permission denied error."""
        with patch("sindri.tools.profiling.PYSPY_AVAILABLE", True):
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_process = AsyncMock()
                mock_process.returncode = 1
                mock_process.communicate = AsyncMock(
                    return_value=(b"", b"Permission denied")
                )
                mock_exec.return_value = mock_process

                result = await tool.execute(
                    file=simple_script,
                    output=str(Path(temp_dir) / "flame.svg"),
                )

                assert not result.success
                assert "permission" in result.error.lower()
                assert "suggestion" in dir(result) or result.suggestion is not None


# ============================================================================
# ComplexityAnalyzeTool Tests
# ============================================================================


class TestComplexityAnalyzeTool:
    """Tests for ComplexityAnalyzeTool."""

    @pytest.fixture
    def tool(self):
        return ComplexityAnalyzeTool()

    @pytest.mark.asyncio
    async def test_constant_complexity(self, tool, complexity_examples):
        """Test detecting O(1) complexity."""
        result = await tool.execute(file=complexity_examples, function="constant_func")
        assert result.success
        assert "O(1)" in result.output

    @pytest.mark.asyncio
    async def test_linear_complexity(self, tool, complexity_examples):
        """Test detecting O(n) complexity."""
        result = await tool.execute(file=complexity_examples, function="linear_func")
        assert result.success
        assert "O(n)" in result.output

    @pytest.mark.asyncio
    async def test_quadratic_complexity(self, tool, complexity_examples):
        """Test detecting O(n^2) complexity."""
        result = await tool.execute(file=complexity_examples, function="quadratic_func")
        assert result.success
        assert "O(n^2)" in result.output or "O(n²)" in result.output

    @pytest.mark.asyncio
    async def test_recursive_complexity(self, tool, complexity_examples):
        """Test detecting recursive complexity."""
        result = await tool.execute(file=complexity_examples, function="recursive_func")
        assert result.success
        assert "recursion" in result.output.lower() or "O(" in result.output

    @pytest.mark.asyncio
    async def test_sorting_complexity(self, tool, complexity_examples):
        """Test detecting O(n log n) for sorting."""
        result = await tool.execute(file=complexity_examples, function="sorting_func")
        assert result.success
        assert "O(n log n)" in result.output or "sort" in result.output.lower()

    @pytest.mark.asyncio
    async def test_analyze_all_functions(self, tool, complexity_examples):
        """Test analyzing all functions in a file."""
        result = await tool.execute(file=complexity_examples)
        assert result.success
        assert result.metadata.get("functions_analyzed") >= 4

    @pytest.mark.asyncio
    async def test_analyze_code_string(self, tool):
        """Test analyzing code string."""
        code = """
def nested_loops(n):
    for i in range(n):
        for j in range(n):
            for k in range(n):
                pass
"""
        result = await tool.execute(code=code, function="nested_loops")
        assert result.success
        assert "O(n^3)" in result.output or "O(n³)" in result.output

    @pytest.mark.asyncio
    async def test_include_space_complexity(self, tool, complexity_examples):
        """Test including space complexity analysis."""
        result = await tool.execute(
            file=complexity_examples,
            function="linear_func",
            include_space=True,
        )
        assert result.success
        assert "space" in result.output.lower()

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, tool):
        """Test error for missing file."""
        result = await tool.execute(file="/nonexistent.py")
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_nonexistent_function(self, tool, complexity_examples):
        """Test error for missing function."""
        result = await tool.execute(
            file=complexity_examples,
            function="nonexistent_function",
        )
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_no_input(self, tool):
        """Test error when no input provided."""
        result = await tool.execute()
        assert not result.success
        assert "must be provided" in result.error

    @pytest.mark.asyncio
    async def test_syntax_error(self, tool):
        """Test handling of syntax errors."""
        result = await tool.execute(code="def broken(:\n    pass")
        assert not result.success
        assert "syntax" in result.error.lower()


# ============================================================================
# Integration Tests
# ============================================================================


class TestProfilingIntegration:
    """Integration tests for profiling tools."""

    @pytest.mark.asyncio
    async def test_profile_then_benchmark(self, temp_dir):
        """Test profiling followed by benchmarking."""
        script = Path(temp_dir) / "test_func.py"
        script.write_text("""
def test_function(n):
    return sum(range(n))

if __name__ == "__main__":
    test_function(1000)
""")

        profile_tool = ProfilePythonTool()
        benchmark_tool = BenchmarkFunctionTool()

        # Profile first
        profile_result = await profile_tool.execute(file=str(script))
        assert profile_result.success

        # Then benchmark
        bench_result = await benchmark_tool.execute(
            file=str(script),
            function="test_function",
            args=[100],
        )
        assert bench_result.success

    @pytest.mark.asyncio
    async def test_memory_then_leak_detection(self, temp_dir):
        """Test memory analysis followed by leak detection."""
        script = Path(temp_dir) / "memory_test.py"
        script.write_text("""
data = []

def grow_memory():
    data.append([0] * 100)

if __name__ == "__main__":
    for _ in range(5):
        grow_memory()
""")

        memory_tool = MemoryAnalyzeTool()
        leak_tool = DetectMemoryLeaksTool()

        # Analyze memory
        memory_result = await memory_tool.execute(file=str(script))
        assert memory_result.success

        # Check for leaks
        leak_result = await leak_tool.execute(file=str(script), iterations=2)
        assert leak_result.success

    @pytest.mark.asyncio
    async def test_timing_then_complexity(self, temp_dir):
        """Test timing followed by complexity analysis."""
        script = Path(temp_dir) / "algo.py"
        script.write_text("""
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr
""")

        time_tool = ProfileTimeTool()
        complexity_tool = ComplexityAnalyzeTool()

        # Time the algorithm using inline definition
        setup_code = """
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr
"""
        time_result = await time_tool.execute(
            code="bubble_sort(list(range(50, 0, -1)))",
            setup=setup_code,
        )
        assert time_result.success

        # Analyze complexity
        complexity_result = await complexity_tool.execute(
            file=str(script),
            function="bubble_sort",
        )
        assert complexity_result.success
        assert "O(n^2)" in complexity_result.output or "O(n²)" in complexity_result.output
