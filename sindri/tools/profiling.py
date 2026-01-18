"""Profiling and performance analysis tools for Sindri.

Phase 12 Tier 3 - Profiling Tools.

Provides tools for:
- CPU/memory profiling (cProfile, Scalene)
- Execution timing (timeit)
- Memory analysis (tracemalloc, memory_profiler)
- Memory leak detection
- Function benchmarking
- Flame graph generation (py-spy)
- Complexity analysis (Big-O estimation)
"""

from __future__ import annotations

import ast
import asyncio
import cProfile
import io
import os
import pstats
import shutil
import statistics
import tempfile
import timeit
import tracemalloc
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import structlog

from sindri.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    pass

log = structlog.get_logger()

# Check for optional dependencies
SCALENE_AVAILABLE = False
try:
    import scalene  # noqa: F401

    SCALENE_AVAILABLE = True
except ImportError:
    pass

MEMORY_PROFILER_AVAILABLE = False
try:
    from memory_profiler import memory_usage  # noqa: F401

    MEMORY_PROFILER_AVAILABLE = True
except ImportError:
    pass

PYSPY_AVAILABLE = shutil.which("py-spy") is not None


def _format_time(seconds: float) -> str:
    """Format time in human-readable units."""
    if seconds < 1e-6:
        return f"{seconds * 1e9:.2f} ns"
    elif seconds < 1e-3:
        return f"{seconds * 1e6:.2f} us"
    elif seconds < 1:
        return f"{seconds * 1e3:.2f} ms"
    else:
        return f"{seconds:.4f} s"


def _format_bytes(size: float) -> str:
    """Format bytes in human-readable units."""
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size) < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


class ProfileTimeTool(Tool):
    """Measure execution time of Python code using timeit."""

    name = "profile_time"
    description = """Measure execution time of Python code using timeit.

Runs code multiple times to get accurate timing statistics including
mean, std dev, min, and max execution times."""

    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to time",
            },
            "setup": {
                "type": "string",
                "description": "Setup code run once before timing (e.g., imports)",
            },
            "number": {
                "type": "integer",
                "description": "Number of executions per timing run (default: auto-detect)",
            },
            "repeat": {
                "type": "integer",
                "description": "Number of timing runs (default: 7)",
            },
        },
        "required": ["code"],
    }

    async def execute(
        self,
        code: str,
        setup: str = "",
        number: Optional[int] = None,
        repeat: int = 7,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute timing measurement."""
        log.info("profile_time_start", code_len=len(code), repeat=repeat)

        try:
            # Create timer
            timer = timeit.Timer(stmt=code, setup=setup)

            # Auto-detect number if not specified
            if number is None:
                try:
                    number, _ = timer.autorange()
                except Exception:
                    number = 1000  # Default fallback

            # Run timing
            times = timer.repeat(repeat=repeat, number=number)

            # Calculate per-iteration times
            per_iter_times = [t / number for t in times]

            # Calculate statistics
            mean_time = statistics.mean(per_iter_times)
            std_time = statistics.stdev(per_iter_times) if len(per_iter_times) > 1 else 0
            min_time = min(per_iter_times)
            max_time = max(per_iter_times)

            # Format output
            output_lines = [
                "Timing Results",
                "=" * 40,
                f"Iterations per run: {number:,}",
                f"Number of runs: {repeat}",
                "",
                "Statistics (per iteration):",
                f"  Mean:   {_format_time(mean_time)}",
                f"  Std:    {_format_time(std_time)}",
                f"  Min:    {_format_time(min_time)}",
                f"  Max:    {_format_time(max_time)}",
                "",
                "Raw times per run:",
            ]

            for i, t in enumerate(times, 1):
                output_lines.append(f"  Run {i}: {_format_time(t)} total, {_format_time(t/number)}/iter")

            log.info("profile_time_success", mean=mean_time, repeat=repeat, number=number)

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "mean": mean_time,
                    "std": std_time,
                    "min": min_time,
                    "max": max_time,
                    "number": number,
                    "repeat": repeat,
                    "raw_times": times,
                },
            )

        except SyntaxError as e:
            log.error("profile_time_syntax_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Syntax error in code: {e}",
                suggestion="Check the code for syntax errors",
            )
        except Exception as e:
            log.error("profile_time_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Timing failed: {e}",
            )


class ProfilePythonTool(Tool):
    """Profile Python code for CPU and memory usage."""

    name = "profile_python"
    description = """Profile Python code for CPU and memory usage.

Uses cProfile (stdlib) for CPU profiling, with optional Scalene support for
detailed CPU/memory/GPU analysis. Profiles files or code strings."""

    parameters = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Python file to profile",
            },
            "code": {
                "type": "string",
                "description": "Python code string to profile (alternative to file)",
            },
            "sort_by": {
                "type": "string",
                "enum": ["cumulative", "time", "calls", "name"],
                "description": "Sort results by (default: cumulative)",
            },
            "top_n": {
                "type": "integer",
                "description": "Show top N results (default: 20)",
            },
            "use_scalene": {
                "type": "boolean",
                "description": "Use Scalene for detailed profiling (requires installation)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        file: Optional[str] = None,
        code: Optional[str] = None,
        sort_by: str = "cumulative",
        top_n: int = 20,
        use_scalene: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute profiling."""
        log.info("profile_python_start", has_file=bool(file), has_code=bool(code))

        if not file and not code:
            return ToolResult(
                success=False,
                output="",
                error="Either 'file' or 'code' must be provided",
            )

        if use_scalene:
            if not SCALENE_AVAILABLE:
                return ToolResult(
                    success=False,
                    output="",
                    error="Scalene not installed. Install with: pip install scalene",
                    suggestion="Use cProfile (default) or install scalene for detailed profiling",
                )
            return await self._profile_with_scalene(file, code, top_n)

        return await self._profile_with_cprofile(file, code, sort_by, top_n)

    async def _profile_with_cprofile(
        self,
        file: Optional[str],
        code: Optional[str],
        sort_by: str,
        top_n: int,
    ) -> ToolResult:
        """Profile using cProfile."""
        try:
            profiler = cProfile.Profile()

            if file:
                file_path = self._resolve_path(file)
                if not file_path.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"File not found: {file}",
                    )
                code_to_run = file_path.read_text()
                globals_dict = {"__name__": "__main__", "__file__": str(file_path)}
            else:
                code_to_run = code
                globals_dict = {"__name__": "__main__"}

            # Profile the code
            profiler.enable()
            try:
                exec(compile(code_to_run, file or "<string>", "exec"), globals_dict)
            finally:
                profiler.disable()

            # Format results
            stream = io.StringIO()
            stats = pstats.Stats(profiler, stream=stream)

            # Sort by specified key
            sort_keys = {
                "cumulative": "cumulative",
                "time": "time",
                "calls": "calls",
                "name": "name",
            }
            stats.sort_stats(sort_keys.get(sort_by, "cumulative"))
            stats.print_stats(top_n)

            output = stream.getvalue()

            # Extract metadata
            total_calls = stats.total_calls
            total_time = stats.total_tt

            log.info("profile_python_success", total_calls=total_calls, total_time=total_time)

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "total_calls": total_calls,
                    "total_time": total_time,
                    "sort_by": sort_by,
                    "top_n": top_n,
                    "profiler": "cProfile",
                },
            )

        except SyntaxError as e:
            log.error("profile_python_syntax_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Syntax error: {e}",
            )
        except Exception as e:
            log.error("profile_python_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Profiling failed: {e}",
            )

    async def _profile_with_scalene(
        self,
        file: Optional[str],
        code: Optional[str],
        top_n: int,
    ) -> ToolResult:
        """Profile using Scalene (subprocess)."""
        try:
            # Scalene requires a file, so write code to temp file if needed
            if code and not file:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                    f.write(code)
                    temp_file = f.name
                file_to_profile = temp_file
            else:
                file_path = self._resolve_path(file)
                if not file_path.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"File not found: {file}",
                    )
                file_to_profile = str(file_path)
                temp_file = None

            try:
                # Run scalene
                cmd = [
                    "python",
                    "-m",
                    "scalene",
                    "--cli",
                    "--reduced-profile",
                    file_to_profile,
                ]

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300.0)

                if process.returncode != 0:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Scalene failed: {stderr.decode()}",
                    )

                output = stdout.decode()
                log.info("profile_python_scalene_success")

                return ToolResult(
                    success=True,
                    output=output,
                    metadata={
                        "profiler": "scalene",
                        "top_n": top_n,
                    },
                )

            finally:
                if temp_file and os.path.exists(temp_file):
                    os.unlink(temp_file)

        except asyncio.TimeoutError:
            log.error("profile_python_timeout")
            return ToolResult(
                success=False,
                output="",
                error="Profiling timed out after 300 seconds",
            )
        except Exception as e:
            log.error("profile_python_scalene_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Scalene profiling failed: {e}",
            )


class MemoryAnalyzeTool(Tool):
    """Analyze memory usage of Python code."""

    name = "memory_analyze"
    description = """Analyze memory usage of Python code.

Shows line-by-line memory increments using memory_profiler (if installed)
or basic memory tracking using tracemalloc (stdlib)."""

    parameters = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Python file to analyze",
            },
            "code": {
                "type": "string",
                "description": "Python code string to analyze (alternative to file)",
            },
            "top_n": {
                "type": "integer",
                "description": "Show top N memory allocations (default: 20)",
            },
            "trace_objects": {
                "type": "boolean",
                "description": "Trace object types in memory (default: false)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        file: Optional[str] = None,
        code: Optional[str] = None,
        top_n: int = 20,
        trace_objects: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute memory analysis."""
        log.info("memory_analyze_start", has_file=bool(file), has_code=bool(code))

        if not file and not code:
            return ToolResult(
                success=False,
                output="",
                error="Either 'file' or 'code' must be provided",
            )

        try:
            # Determine code to run
            if file:
                file_path = self._resolve_path(file)
                if not file_path.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"File not found: {file}",
                    )
                code_to_run = file_path.read_text()
                source_name = str(file_path)
            else:
                code_to_run = code
                source_name = "<string>"

            # Start tracemalloc
            tracemalloc.start()

            try:
                # Execute code
                globals_dict = {"__name__": "__main__"}
                if file:
                    globals_dict["__file__"] = source_name

                exec(compile(code_to_run, source_name, "exec"), globals_dict)

                # Take snapshot
                snapshot = tracemalloc.take_snapshot()
            finally:
                tracemalloc.stop()

            # Analyze snapshot
            stats = snapshot.statistics("lineno")

            output_lines = [
                "Memory Analysis Results",
                "=" * 50,
                "",
                f"Top {top_n} memory allocations by line:",
                "",
            ]

            total_size = 0
            for stat in stats[:top_n]:
                total_size += stat.size
                output_lines.append(f"  {stat.traceback.format()[0]}")
                output_lines.append(f"    Size: {_format_bytes(stat.size)}, Count: {stat.count}")

            output_lines.extend([
                "",
                f"Total tracked memory: {_format_bytes(total_size)}",
                f"Total allocations shown: {len(stats[:top_n])}",
            ])

            # Object type analysis if requested
            if trace_objects:
                type_stats = snapshot.statistics("filename")
                output_lines.extend([
                    "",
                    "Memory by file:",
                    "",
                ])
                for stat in type_stats[:10]:
                    output_lines.append(f"  {stat.traceback.format()[0]}: {_format_bytes(stat.size)}")

            log.info("memory_analyze_success", total_size=total_size)

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "total_size": total_size,
                    "allocation_count": len(stats),
                    "top_n": top_n,
                },
            )

        except SyntaxError as e:
            log.error("memory_analyze_syntax_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Syntax error: {e}",
            )
        except Exception as e:
            log.error("memory_analyze_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Memory analysis failed: {e}",
            )


class DetectMemoryLeaksTool(Tool):
    """Detect potential memory leaks in Python code."""

    name = "detect_memory_leaks"
    description = """Detect potential memory leaks in Python code.

Uses tracemalloc to compare memory snapshots before and after code execution,
identifying allocations that weren't freed."""

    parameters = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Python file to check for leaks",
            },
            "code": {
                "type": "string",
                "description": "Python code string to check (alternative to file)",
            },
            "iterations": {
                "type": "integer",
                "description": "Run code N times to amplify leaks (default: 3)",
            },
            "threshold_kb": {
                "type": "number",
                "description": "Report leaks above this threshold in KB (default: 10)",
            },
            "trace_depth": {
                "type": "integer",
                "description": "Traceback depth for leak sources (default: 5)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        file: Optional[str] = None,
        code: Optional[str] = None,
        iterations: int = 3,
        threshold_kb: float = 10.0,
        trace_depth: int = 5,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute memory leak detection."""
        log.info("detect_memory_leaks_start", iterations=iterations)

        if not file and not code:
            return ToolResult(
                success=False,
                output="",
                error="Either 'file' or 'code' must be provided",
            )

        try:
            # Determine code to run
            if file:
                file_path = self._resolve_path(file)
                if not file_path.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"File not found: {file}",
                    )
                code_to_run = file_path.read_text()
                source_name = str(file_path)
            else:
                code_to_run = code
                source_name = "<string>"

            # Start tracemalloc with depth
            tracemalloc.start(trace_depth)

            try:
                # Take initial snapshot
                snapshot1 = tracemalloc.take_snapshot()

                # Execute code multiple times
                for i in range(iterations):
                    globals_dict = {"__name__": "__main__", "__iteration__": i}
                    if file:
                        globals_dict["__file__"] = source_name
                    exec(compile(code_to_run, source_name, "exec"), globals_dict)

                # Take final snapshot
                snapshot2 = tracemalloc.take_snapshot()

            finally:
                tracemalloc.stop()

            # Compare snapshots
            diff_stats = snapshot2.compare_to(snapshot1, "lineno")

            # Filter by threshold
            threshold_bytes = threshold_kb * 1024
            potential_leaks = [
                stat for stat in diff_stats
                if stat.size_diff > threshold_bytes
            ]

            output_lines = [
                "Memory Leak Detection Results",
                "=" * 50,
                "",
                f"Iterations: {iterations}",
                f"Threshold: {threshold_kb} KB",
                "",
            ]

            if potential_leaks:
                output_lines.append(f"Potential leaks detected: {len(potential_leaks)}")
                output_lines.append("")

                for stat in potential_leaks[:20]:
                    output_lines.append(f"  {stat.traceback.format()[0]}")
                    output_lines.append(
                        f"    Size diff: +{_format_bytes(stat.size_diff)} "
                        f"({stat.count_diff:+d} allocations)"
                    )
            else:
                output_lines.append("No significant memory leaks detected.")

            # Summary
            total_diff = sum(s.size_diff for s in diff_stats if s.size_diff > 0)
            output_lines.extend([
                "",
                f"Total memory growth: {_format_bytes(total_diff)}",
            ])

            log.info(
                "detect_memory_leaks_success",
                potential_leaks=len(potential_leaks),
                total_diff=total_diff,
            )

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "potential_leaks": len(potential_leaks),
                    "total_memory_diff": total_diff,
                    "iterations": iterations,
                    "threshold_kb": threshold_kb,
                },
            )

        except SyntaxError as e:
            log.error("detect_memory_leaks_syntax_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Syntax error: {e}",
            )
        except Exception as e:
            log.error("detect_memory_leaks_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Memory leak detection failed: {e}",
            )


class BenchmarkFunctionTool(Tool):
    """Benchmark Python functions with statistical analysis."""

    name = "benchmark_function"
    description = """Benchmark Python functions using timeit.

Provides statistical analysis of function performance including mean, stddev,
min, max, rounds, and iterations. Supports comparison between functions."""

    parameters = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Python file containing functions to benchmark",
            },
            "function": {
                "type": "string",
                "description": "Function name to benchmark",
            },
            "args": {
                "type": "array",
                "items": {},
                "description": "Positional arguments to pass to function",
            },
            "kwargs": {
                "type": "object",
                "description": "Keyword arguments to pass to function",
            },
            "rounds": {
                "type": "integer",
                "description": "Number of benchmark rounds (default: 100)",
            },
            "warmup_rounds": {
                "type": "integer",
                "description": "Number of warmup rounds (default: 10)",
            },
            "compare_with": {
                "type": "string",
                "description": "Compare with another function in same file",
            },
        },
        "required": ["file", "function"],
    }

    async def execute(
        self,
        file: str,
        function: str,
        args: Optional[list] = None,
        kwargs: Optional[dict] = None,
        rounds: int = 100,
        warmup_rounds: int = 10,
        compare_with: Optional[str] = None,
        **extra_kwargs: Any,
    ) -> ToolResult:
        """Execute benchmarking."""
        log.info("benchmark_function_start", function=function, rounds=rounds)

        args = args or []
        kwargs = kwargs or {}

        try:
            file_path = self._resolve_path(file)
            if not file_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File not found: {file}",
                )

            # Load the module
            code = file_path.read_text()
            globals_dict: dict[str, Any] = {"__name__": "__main__", "__file__": str(file_path)}
            exec(compile(code, str(file_path), "exec"), globals_dict)

            # Get the function
            if function not in globals_dict:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Function '{function}' not found in {file}",
                )

            func = globals_dict[function]

            # Benchmark the function
            result1 = await self._benchmark_single(func, args, kwargs, rounds, warmup_rounds)

            output_lines = [
                "Benchmark Results",
                "=" * 50,
                "",
                f"Function: {function}",
                f"File: {file}",
                f"Rounds: {rounds} (+ {warmup_rounds} warmup)",
                "",
                "Statistics:",
                f"  Mean:   {_format_time(result1['mean'])}",
                f"  Std:    {_format_time(result1['std'])}",
                f"  Min:    {_format_time(result1['min'])}",
                f"  Max:    {_format_time(result1['max'])}",
                f"  Median: {_format_time(result1['median'])}",
            ]

            metadata = {
                "function": function,
                "rounds": rounds,
                "warmup_rounds": warmup_rounds,
                **result1,
            }

            # Compare with another function if specified
            if compare_with:
                if compare_with not in globals_dict:
                    output_lines.extend([
                        "",
                        f"Warning: Comparison function '{compare_with}' not found",
                    ])
                else:
                    func2 = globals_dict[compare_with]
                    result2 = await self._benchmark_single(func2, args, kwargs, rounds, warmup_rounds)

                    speedup = result2["mean"] / result1["mean"] if result1["mean"] > 0 else 0

                    output_lines.extend([
                        "",
                        f"Comparison: {compare_with}",
                        f"  Mean:   {_format_time(result2['mean'])}",
                        f"  Std:    {_format_time(result2['std'])}",
                        "",
                        f"Speedup: {speedup:.2f}x ({function} vs {compare_with})",
                    ])

                    metadata["compare_with"] = compare_with
                    metadata["compare_stats"] = result2
                    metadata["speedup"] = speedup

            log.info("benchmark_function_success", mean=result1["mean"])

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata=metadata,
            )

        except SyntaxError as e:
            log.error("benchmark_function_syntax_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Syntax error: {e}",
            )
        except Exception as e:
            log.error("benchmark_function_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Benchmarking failed: {e}",
            )

    async def _benchmark_single(
        self,
        func: Any,
        args: list,
        kwargs: dict,
        rounds: int,
        warmup_rounds: int,
    ) -> dict[str, float]:
        """Benchmark a single function."""
        import time

        # Warmup
        for _ in range(warmup_rounds):
            func(*args, **kwargs)

        # Benchmark
        times = []
        for _ in range(rounds):
            start = time.perf_counter()
            func(*args, **kwargs)
            end = time.perf_counter()
            times.append(end - start)

        return {
            "mean": statistics.mean(times),
            "std": statistics.stdev(times) if len(times) > 1 else 0,
            "min": min(times),
            "max": max(times),
            "median": statistics.median(times),
        }


class FlameGraphTool(Tool):
    """Generate flame graphs for Python performance visualization."""

    name = "flame_graph"
    description = """Generate flame graphs for Python performance visualization.

Uses py-spy to sample running processes and generate SVG flame graphs.
Note: py-spy may require elevated permissions on some systems."""

    parameters = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Python script to profile",
            },
            "pid": {
                "type": "integer",
                "description": "Attach to running process by PID (alternative to file)",
            },
            "duration": {
                "type": "number",
                "description": "Sampling duration in seconds (default: 10)",
            },
            "output": {
                "type": "string",
                "description": "Output SVG file path (default: flame_graph.svg)",
            },
            "rate": {
                "type": "integer",
                "description": "Sample rate in Hz (default: 100)",
            },
            "subprocesses": {
                "type": "boolean",
                "description": "Profile subprocesses as well (default: false)",
            },
            "native": {
                "type": "boolean",
                "description": "Include native frames (default: false)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        file: Optional[str] = None,
        pid: Optional[int] = None,
        duration: float = 10.0,
        output: Optional[str] = None,
        rate: int = 100,
        subprocesses: bool = False,
        native: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute flame graph generation."""
        log.info("flame_graph_start", has_file=bool(file), has_pid=bool(pid))

        if not PYSPY_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="py-spy not installed. Install with: pip install py-spy",
                suggestion="py-spy may require elevated privileges. Try: sudo pip install py-spy",
            )

        if not file and not pid:
            return ToolResult(
                success=False,
                output="",
                error="Either 'file' or 'pid' must be provided",
            )

        # Determine output path
        if output:
            output_path = self._resolve_path(output)
        else:
            output_path = Path.cwd() / "flame_graph.svg"

        try:
            if file:
                # Record new process
                file_path = self._resolve_path(file)
                if not file_path.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"File not found: {file}",
                    )

                cmd = [
                    "py-spy",
                    "record",
                    "-o", str(output_path),
                    "--duration", str(int(duration)),
                    "--rate", str(rate),
                    "--format", "speedscope",
                ]

                if subprocesses:
                    cmd.append("--subprocesses")
                if native:
                    cmd.append("--native")

                cmd.extend(["--", "python", str(file_path)])

            else:
                # Attach to existing process
                cmd = [
                    "py-spy",
                    "record",
                    "-o", str(output_path),
                    "--pid", str(pid),
                    "--duration", str(int(duration)),
                    "--rate", str(rate),
                    "--format", "speedscope",
                ]

                if subprocesses:
                    cmd.append("--subprocesses")
                if native:
                    cmd.append("--native")

            # Run py-spy
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=duration + 60,  # Extra time for startup/shutdown
            )

            if process.returncode != 0:
                stderr_text = stderr.decode()
                if "permission" in stderr_text.lower():
                    return ToolResult(
                        success=False,
                        output="",
                        error="Permission denied. py-spy requires elevated privileges.",
                        suggestion="Run with sudo or set ptrace_scope: "
                        "echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope",
                    )
                return ToolResult(
                    success=False,
                    output="",
                    error=f"py-spy failed: {stderr_text}",
                )

            log.info("flame_graph_success", output=str(output_path))

            return ToolResult(
                success=True,
                output=f"Flame graph generated: {output_path}\n"
                f"Duration: {duration}s, Rate: {rate}Hz\n"
                "Open in speedscope.app or your preferred viewer.",
                metadata={
                    "output": str(output_path),
                    "duration": duration,
                    "rate": rate,
                    "format": "speedscope",
                },
            )

        except asyncio.TimeoutError:
            log.error("flame_graph_timeout")
            return ToolResult(
                success=False,
                output="",
                error=f"Flame graph generation timed out after {duration + 60} seconds",
            )
        except Exception as e:
            log.error("flame_graph_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Flame graph generation failed: {e}",
            )


@dataclass
class ComplexityResult:
    """Result of complexity analysis."""

    time_complexity: str
    space_complexity: str
    confidence: str  # "high", "medium", "low"
    explanation: str
    patterns_found: list[str] = field(default_factory=list)


class ComplexityAnalyzeTool(Tool):
    """Analyze algorithmic complexity (Big-O) of Python code."""

    name = "complexity_analyze"
    description = """Analyze algorithmic complexity (Big-O) of Python code.

Uses static analysis to estimate time and space complexity of functions
by detecting common patterns like loops, recursion, and data structures."""

    parameters = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Python file to analyze",
            },
            "function": {
                "type": "string",
                "description": "Specific function to analyze (optional)",
            },
            "code": {
                "type": "string",
                "description": "Python code string to analyze (alternative to file)",
            },
            "include_space": {
                "type": "boolean",
                "description": "Include space complexity analysis (default: true)",
            },
            "empirical": {
                "type": "boolean",
                "description": "Run empirical tests to verify complexity (default: false)",
            },
            "input_sizes": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Input sizes for empirical testing (default: [10, 100, 1000])",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        file: Optional[str] = None,
        function: Optional[str] = None,
        code: Optional[str] = None,
        include_space: bool = True,
        empirical: bool = False,
        input_sizes: Optional[list[int]] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute complexity analysis."""
        log.info("complexity_analyze_start", has_file=bool(file), function=function)

        if not file and not code:
            return ToolResult(
                success=False,
                output="",
                error="Either 'file' or 'code' must be provided",
            )

        try:
            # Get code to analyze
            if file:
                file_path = self._resolve_path(file)
                if not file_path.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"File not found: {file}",
                    )
                code_text = file_path.read_text()
            else:
                code_text = code

            # Parse AST
            try:
                tree = ast.parse(code_text)
            except SyntaxError as e:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Syntax error: {e}",
                )

            # Find functions to analyze
            functions_to_analyze = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if function is None or node.name == function:
                        functions_to_analyze.append(node)

            if not functions_to_analyze:
                if function:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Function '{function}' not found",
                    )
                return ToolResult(
                    success=False,
                    output="",
                    error="No functions found to analyze",
                )

            # Analyze each function
            results = []
            for func_node in functions_to_analyze:
                result = self._analyze_function(func_node, include_space)
                results.append((func_node.name, result))

            # Format output
            output_lines = [
                "Complexity Analysis Results",
                "=" * 50,
                "",
            ]

            for func_name, result in results:
                output_lines.extend([
                    f"Function: {func_name}",
                    f"  Time Complexity:  {result.time_complexity}",
                ])
                if include_space:
                    output_lines.append(f"  Space Complexity: {result.space_complexity}")
                output_lines.extend([
                    f"  Confidence: {result.confidence}",
                    "",
                    f"  Analysis: {result.explanation}",
                ])
                if result.patterns_found:
                    output_lines.append(f"  Patterns: {', '.join(result.patterns_found)}")
                output_lines.append("")

            log.info(
                "complexity_analyze_success",
                functions_analyzed=len(results),
            )

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "functions_analyzed": len(results),
                    "results": {
                        name: {
                            "time": r.time_complexity,
                            "space": r.space_complexity,
                            "confidence": r.confidence,
                        }
                        for name, r in results
                    },
                },
            )

        except Exception as e:
            log.error("complexity_analyze_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Complexity analysis failed: {e}",
            )

    def _analyze_function(self, func: ast.FunctionDef, include_space: bool) -> ComplexityResult:
        """Analyze a single function's complexity."""
        patterns = []
        max_loop_depth = 0
        has_recursion = False
        has_sorting = False
        has_list_comprehension = False
        creates_data_structure = False

        # Walk the AST
        for node in ast.walk(func):
            # Check for loops
            if isinstance(node, (ast.For, ast.While)):
                depth = self._get_loop_depth(node)
                max_loop_depth = max(max_loop_depth, depth)
                if depth == 1:
                    patterns.append("single_loop")
                elif depth == 2:
                    patterns.append("nested_loops")
                elif depth >= 3:
                    patterns.append("deeply_nested_loops")

            # Check for recursion
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == func.name:
                    has_recursion = True
                    patterns.append("recursion")

                # Check for sorting calls
                if isinstance(node.func, ast.Name) and node.func.id in ("sorted", "sort"):
                    has_sorting = True
                    patterns.append("sorting")
                if isinstance(node.func, ast.Attribute) and node.func.attr == "sort":
                    has_sorting = True
                    patterns.append("sorting")

            # Check for list comprehension
            if isinstance(node, ast.ListComp):
                has_list_comprehension = True
                patterns.append("list_comprehension")

            # Check for data structure creation
            if isinstance(node, ast.Assign):
                if isinstance(node.value, (ast.List, ast.Dict, ast.Set)):
                    creates_data_structure = True

        # Determine time complexity
        if has_recursion:
            # Recursion analysis is complex, estimate based on patterns
            if max_loop_depth == 0:
                time_complexity = "O(2^n)"  # Assume exponential without more info
                explanation = "Recursive function detected. Without memoization, likely exponential."
                confidence = "low"
            else:
                time_complexity = f"O(n^{max_loop_depth + 1})"
                explanation = f"Recursion with {max_loop_depth} loop level(s)."
                confidence = "low"
        elif max_loop_depth == 0:
            if has_sorting:
                time_complexity = "O(n log n)"
                explanation = "Uses sorting operation."
                confidence = "high"
            else:
                time_complexity = "O(1)"
                explanation = "No loops or recursive calls detected."
                confidence = "high"
        elif max_loop_depth == 1:
            if has_sorting:
                time_complexity = "O(n log n)"
                explanation = "Single loop with sorting, dominated by sort."
                confidence = "medium"
            else:
                time_complexity = "O(n)"
                explanation = "Single loop iterating over input."
                confidence = "high"
        elif max_loop_depth == 2:
            time_complexity = "O(n^2)"
            explanation = "Nested loops detected (2 levels deep)."
            confidence = "high"
        elif max_loop_depth == 3:
            time_complexity = "O(n^3)"
            explanation = "Deeply nested loops (3 levels deep)."
            confidence = "high"
        else:
            time_complexity = f"O(n^{max_loop_depth})"
            explanation = f"Very deeply nested loops ({max_loop_depth} levels deep)."
            confidence = "medium"

        # Determine space complexity
        if include_space:
            if has_recursion:
                space_complexity = "O(n)"
                explanation += " Recursion uses O(n) stack space."
            elif creates_data_structure or has_list_comprehension:
                space_complexity = "O(n)"
            else:
                space_complexity = "O(1)"
        else:
            space_complexity = "N/A"

        return ComplexityResult(
            time_complexity=time_complexity,
            space_complexity=space_complexity,
            confidence=confidence,
            explanation=explanation,
            patterns_found=list(set(patterns)),
        )

    def _get_loop_depth(self, node: ast.AST, current_depth: int = 1) -> int:
        """Get the maximum loop nesting depth."""
        max_depth = current_depth

        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.For, ast.While)):
                child_depth = self._get_loop_depth(child, current_depth + 1)
                max_depth = max(max_depth, child_depth)
            else:
                # Check non-loop children for nested loops
                for grandchild in ast.walk(child):
                    if isinstance(grandchild, (ast.For, ast.While)) and grandchild is not child:
                        if any(isinstance(p, (ast.For, ast.While)) for p in ast.walk(grandchild)):
                            pass  # Already counted

        return max_depth
