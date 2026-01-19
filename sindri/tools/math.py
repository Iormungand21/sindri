"""Math and scientific tools for Sindri.

Phase 12 - Math & Scientific Tools.

Provides tools for:
- Mathematical expression evaluation (SymPy)
- Equation solving (SymPy)
- Statistical analysis (SciPy, pandas)
- Plot generation (matplotlib)
- Unit conversion (pint)
- Matrix operations (NumPy)
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

import numpy as np
import pandas as pd
import structlog

from sindri.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    pass

# Use logger instead of log to avoid conflict with sympy.log
logger = structlog.get_logger()

# Check for optional dependencies
SYMPY_AVAILABLE = False
try:
    import sympy
    from sympy import (
        Abs,
        E,
        I,
        N,
        cos,
        diff,
        exp,
        factorial,
        integrate,
        limit,
        log,
        oo,
        pi,
        simplify,
        sin,
        solve,
        sqrt,
        symbols,
        tan,
    )
    from sympy.parsing.sympy_parser import (
        convert_xor,
        implicit_multiplication_application,
        parse_expr,
        standard_transformations,
    )

    SYMPY_AVAILABLE = True
except ImportError:
    pass

SCIPY_AVAILABLE = False
try:
    from scipy import stats as scipy_stats

    SCIPY_AVAILABLE = True
except ImportError:
    pass

MATPLOTLIB_AVAILABLE = False
try:
    import matplotlib

    matplotlib.use("Agg")  # Non-interactive backend
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    pass

PINT_AVAILABLE = False
try:
    import pint

    ureg = pint.UnitRegistry()
    PINT_AVAILABLE = True
except ImportError:
    ureg = None


def _format_number(value: float, precision: int = 6) -> str:
    """Format number with appropriate precision."""
    if abs(value) < 1e-10:
        return "0"
    elif abs(value) > 1e10 or abs(value) < 1e-4:
        return f"{value:.{precision}e}"
    else:
        result = f"{value:.{precision}f}".rstrip("0").rstrip(".")
        return result if result else "0"


class MathEvaluateTool(Tool):
    """Evaluate mathematical expressions symbolically or numerically."""

    name = "math_evaluate"
    description = """Evaluate mathematical expressions symbolically or numerically.

Supports:
- Arithmetic: 2+3*4, sqrt(16), 5**3
- Functions: sin, cos, tan, log, exp, sqrt, abs, factorial
- Constants: pi, e, oo (infinity)
- Symbolic: x**2 + 2*x + 1 (returns symbolic result)
- Numerical: evaluate x**2 + 1 at x=5

Examples:
- math_evaluate(expression="sqrt(2) + pi")
- math_evaluate(expression="factorial(10)")
- math_evaluate(expression="x**2 + 2*x + 1", values={"x": 3})
- math_evaluate(expression="sin(pi/4)", numeric=True)
- math_evaluate(expression="diff(x**3, x)") - derivative
- math_evaluate(expression="integrate(x**2, x)") - integral"""

    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression to evaluate",
            },
            "values": {
                "type": "object",
                "description": "Variable substitutions (e.g., {'x': 5, 'y': 3})",
            },
            "numeric": {
                "type": "boolean",
                "description": "Force numerical evaluation (default: false)",
            },
            "precision": {
                "type": "integer",
                "description": "Decimal precision for numeric results (default: 15)",
            },
        },
        "required": ["expression"],
    }

    async def execute(
        self,
        expression: str,
        values: Optional[dict] = None,
        numeric: bool = False,
        precision: int = 15,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute mathematical expression evaluation."""
        logger.info("math_evaluate_start", expression=expression[:100])

        if not SYMPY_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="SymPy not installed. Install with: pip install sympy",
            )

        try:
            # Parse the expression with extended transformations
            transformations = standard_transformations + (
                implicit_multiplication_application,
                convert_xor,
            )

            # Create local namespace with common functions and constants
            local_dict = {
                "pi": sympy.pi,
                "e": sympy.E,
                "E": sympy.E,
                "I": sympy.I,
                "i": sympy.I,
                "oo": sympy.oo,
                "inf": sympy.oo,
                "sin": sympy.sin,
                "cos": sympy.cos,
                "tan": sympy.tan,
                "asin": sympy.asin,
                "acos": sympy.acos,
                "atan": sympy.atan,
                "sinh": sympy.sinh,
                "cosh": sympy.cosh,
                "tanh": sympy.tanh,
                "log": sympy.log,
                "ln": sympy.ln,
                "exp": sympy.exp,
                "sqrt": sympy.sqrt,
                "abs": sympy.Abs,
                "Abs": sympy.Abs,
                "factorial": sympy.factorial,
                "gamma": sympy.gamma,
                "floor": sympy.floor,
                "ceiling": sympy.ceiling,
                "diff": sympy.diff,
                "integrate": sympy.integrate,
                "limit": sympy.limit,
                "simplify": sympy.simplify,
                "expand": sympy.expand,
                "factor": sympy.factor,
            }

            # Add common variable symbols
            for var in ["x", "y", "z", "t", "n", "a", "b", "c"]:
                local_dict[var] = sympy.Symbol(var)

            # Parse the expression
            expr = parse_expr(expression, local_dict=local_dict, transformations=transformations)

            # Apply substitutions if provided
            if values:
                subs_dict = {}
                for var, val in values.items():
                    if var in local_dict:
                        subs_dict[local_dict[var]] = val
                    else:
                        subs_dict[sympy.Symbol(var)] = val
                expr = expr.subs(subs_dict)

            # Simplify the result
            result = sympy.simplify(expr)

            # Force numeric evaluation if requested or if result is numeric
            if numeric or (not result.free_symbols and result.is_number):
                try:
                    numeric_result = sympy.N(result, precision)
                    if numeric_result.is_real:
                        result_str = str(float(numeric_result))
                    else:
                        result_str = str(numeric_result)
                except Exception:
                    result_str = str(result)
            else:
                result_str = str(result)

            # Build output
            output_lines = [
                "**Mathematical Evaluation**",
                "",
                f"**Expression:** `{expression}`",
            ]

            if values:
                values_str = ", ".join(f"{k}={v}" for k, v in values.items())
                output_lines.append(f"**Substitutions:** {values_str}")

            output_lines.extend(
                [
                    "",
                    f"**Result:** `{result_str}`",
                ]
            )

            # Add LaTeX representation if symbolic
            if result.free_symbols:
                latex_repr = sympy.latex(result)
                output_lines.extend(
                    [
                        "",
                        f"**LaTeX:** `{latex_repr}`",
                    ]
                )

            logger.info("math_evaluate_success", result=result_str[:50])

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "expression": expression,
                    "result": result_str,
                    "is_numeric": not bool(result.free_symbols),
                    "latex": sympy.latex(result) if result.free_symbols else None,
                },
            )

        except SyntaxError as e:
            logger.error("math_evaluate_syntax_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Syntax error in expression: {e}",
                suggestion="Check the expression for syntax errors. Use ** for exponents, not ^.",
            )
        except Exception as e:
            logger.error("math_evaluate_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Evaluation failed: {e}",
            )


class MathSolveTool(Tool):
    """Solve equations and systems of equations symbolically."""

    name = "math_solve"
    description = """Solve equations symbolically.

Supports:
- Single equations: x**2 - 4 = 0
- Systems of equations: x + y = 10, x - y = 2
- Polynomial equations
- Transcendental equations

Input formats:
- Single equation: "x**2 - 4" (assumed = 0)
- Explicit: "x**2 = 4" (converted to x**2 - 4 = 0)
- System: ["x + y = 10", "x - y = 2"]

Examples:
- math_solve(equation="x**2 - 4")                    -> x = -2, x = 2
- math_solve(equation="2*x + 3 = 11", variable="x") -> x = 4
- math_solve(equations=["x + y = 10", "x - y = 2"]) -> {x: 6, y: 4}
- math_solve(equation="x**2 + 1 = 0", domain="complex") -> x = -I, x = I"""

    parameters = {
        "type": "object",
        "properties": {
            "equation": {
                "type": "string",
                "description": "Single equation to solve (e.g., 'x**2 - 4' or 'x**2 = 4')",
            },
            "equations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "System of equations to solve simultaneously",
            },
            "variable": {
                "type": "string",
                "description": "Variable to solve for (default: auto-detect)",
            },
            "variables": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Variables for system of equations",
            },
            "domain": {
                "type": "string",
                "enum": ["real", "complex", "integer", "natural"],
                "description": "Domain for solutions (default: complex)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        equation: Optional[str] = None,
        equations: Optional[list] = None,
        variable: Optional[str] = None,
        variables: Optional[list] = None,
        domain: str = "complex",
        **kwargs: Any,
    ) -> ToolResult:
        """Execute equation solving."""
        logger.info("math_solve_start", equation=equation, equations=equations)

        if not SYMPY_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="SymPy not installed. Install with: pip install sympy",
            )

        if not equation and not equations:
            return ToolResult(
                success=False,
                output="",
                error="Either 'equation' or 'equations' must be provided",
            )

        try:
            # Standard transformations
            transformations = standard_transformations + (
                implicit_multiplication_application,
                convert_xor,
            )

            # Local namespace
            local_dict = {
                "pi": sympy.pi,
                "e": sympy.E,
                "E": sympy.E,
                "I": sympy.I,
                "sin": sympy.sin,
                "cos": sympy.cos,
                "tan": sympy.tan,
                "log": sympy.log,
                "exp": sympy.exp,
                "sqrt": sympy.sqrt,
            }

            # Add variable symbols
            for var in ["x", "y", "z", "t", "n", "a", "b", "c", "w"]:
                local_dict[var] = sympy.Symbol(var)

            def parse_equation(eq_str: str):
                """Parse equation string to SymPy expression."""
                if "=" in eq_str:
                    lhs, rhs = eq_str.split("=", 1)
                    lhs_expr = parse_expr(lhs.strip(), local_dict=local_dict, transformations=transformations)
                    rhs_expr = parse_expr(rhs.strip(), local_dict=local_dict, transformations=transformations)
                    return lhs_expr - rhs_expr
                else:
                    return parse_expr(eq_str.strip(), local_dict=local_dict, transformations=transformations)

            # Handle single equation
            if equation:
                expr = parse_equation(equation)

                # Detect variable if not specified
                free_vars = list(expr.free_symbols)
                if variable:
                    solve_var = local_dict.get(variable, sympy.Symbol(variable))
                elif len(free_vars) == 1:
                    solve_var = free_vars[0]
                else:
                    solve_var = local_dict["x"] if local_dict["x"] in free_vars else free_vars[0]

                # Solve based on domain
                if domain == "real":
                    solutions = sympy.solveset(expr, solve_var, domain=sympy.S.Reals)
                elif domain == "integer":
                    solutions = sympy.solveset(expr, solve_var, domain=sympy.S.Integers)
                elif domain == "natural":
                    solutions = sympy.solveset(expr, solve_var, domain=sympy.S.Naturals)
                else:
                    solutions = sympy.solve(expr, solve_var)

                # Format solutions
                if isinstance(solutions, (list, tuple)):
                    solutions_list = list(solutions)
                elif hasattr(solutions, "__iter__") and not isinstance(solutions, str):
                    try:
                        solutions_list = list(solutions)
                    except (TypeError, NotImplementedError):
                        solutions_list = [solutions]
                else:
                    solutions_list = [solutions]

                output_lines = [
                    "**Equation Solver**",
                    "",
                    f"**Equation:** `{equation}`",
                    f"**Variable:** `{solve_var}`",
                    f"**Domain:** {domain}",
                    "",
                    "**Solutions:**",
                ]

                if solutions_list:
                    for i, sol in enumerate(solutions_list, 1):
                        output_lines.append(f"  {i}. `{solve_var} = {sol}`")
                else:
                    output_lines.append("  No solutions found")

                logger.info("math_solve_success", num_solutions=len(solutions_list))

                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata={
                        "equation": equation,
                        "variable": str(solve_var),
                        "solutions": [str(s) for s in solutions_list],
                        "num_solutions": len(solutions_list),
                    },
                )

            # Handle system of equations
            else:
                exprs = [parse_equation(eq) for eq in equations]

                # Detect variables if not specified
                if variables:
                    solve_vars = [local_dict.get(v, sympy.Symbol(v)) for v in variables]
                else:
                    all_vars = set()
                    for expr in exprs:
                        all_vars.update(expr.free_symbols)
                    solve_vars = sorted(list(all_vars), key=str)

                # Solve system
                solutions = sympy.solve(exprs, solve_vars, dict=True)

                output_lines = [
                    "**System of Equations Solver**",
                    "",
                    "**Equations:**",
                ]
                for eq in equations:
                    output_lines.append(f"  - `{eq}`")

                output_lines.extend(
                    [
                        "",
                        f"**Variables:** {', '.join(str(v) for v in solve_vars)}",
                        "",
                        "**Solutions:**",
                    ]
                )

                if solutions:
                    for i, sol in enumerate(solutions, 1):
                        sol_str = ", ".join(f"{k} = {v}" for k, v in sol.items())
                        output_lines.append(f"  {i}. `{{{sol_str}}}`")
                else:
                    output_lines.append("  No solutions found")

                logger.info("math_solve_system_success", num_solutions=len(solutions))

                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata={
                        "equations": equations,
                        "variables": [str(v) for v in solve_vars],
                        "solutions": [{str(k): str(v) for k, v in sol.items()} for sol in solutions],
                        "num_solutions": len(solutions),
                    },
                )

        except SyntaxError as e:
            logger.error("math_solve_syntax_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Syntax error in equation: {e}",
            )
        except Exception as e:
            logger.error("math_solve_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Solving failed: {e}",
            )


class StatsAnalyzeTool(Tool):
    """Perform statistical analysis on datasets."""

    name = "stats_analyze"
    description = """Perform statistical analysis on data.

Computes:
- Descriptive: mean, median, mode, std, var, min, max, quartiles
- Distribution: skewness, kurtosis, normality test
- Correlation: Pearson, Spearman, Kendall
- Hypothesis tests: t-test, chi-square, ANOVA
- Regression: linear, polynomial fitting

Examples:
- stats_analyze(data=[1,2,3,4,5], analysis="descriptive")
- stats_analyze(file_path="data.csv", columns=["x", "y"], analysis="correlation")
- stats_analyze(data=[...], analysis="normality")
- stats_analyze(group1=[...], group2=[...], analysis="ttest")
- stats_analyze(x=[1,2,3], y=[2,4,6], analysis="regression")"""

    parameters = {
        "type": "object",
        "properties": {
            "data": {
                "type": "array",
                "description": "Data array for analysis",
            },
            "file_path": {
                "type": "string",
                "description": "Path to CSV/JSON file",
            },
            "columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Columns to analyze from file",
            },
            "analysis": {
                "type": "string",
                "enum": ["descriptive", "correlation", "normality", "ttest", "anova", "regression", "distribution"],
                "description": "Type of analysis to perform",
            },
            "x": {
                "type": "array",
                "description": "X data for regression/correlation",
            },
            "y": {
                "type": "array",
                "description": "Y data for regression/correlation",
            },
            "group1": {
                "type": "array",
                "description": "First group for comparison tests",
            },
            "group2": {
                "type": "array",
                "description": "Second group for comparison tests",
            },
            "groups": {
                "type": "array",
                "description": "Multiple groups for ANOVA (array of arrays)",
            },
            "regression_degree": {
                "type": "integer",
                "description": "Polynomial degree for regression (default: 1)",
            },
        },
        "required": ["analysis"],
    }

    async def execute(
        self,
        analysis: str,
        data: Optional[list] = None,
        file_path: Optional[str] = None,
        columns: Optional[list] = None,
        x: Optional[list] = None,
        y: Optional[list] = None,
        group1: Optional[list] = None,
        group2: Optional[list] = None,
        groups: Optional[list] = None,
        regression_degree: int = 1,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute statistical analysis."""
        logger.info("stats_analyze_start", analysis=analysis)

        if not SCIPY_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="SciPy not installed. Install with: pip install scipy",
            )

        try:
            # Load data from file if specified
            if file_path:
                resolved_path = self._resolve_path(file_path)
                if not os.path.exists(resolved_path):
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"File not found: {file_path}",
                    )

                if str(resolved_path).endswith(".csv"):
                    df = pd.read_csv(resolved_path)
                elif str(resolved_path).endswith(".json"):
                    df = pd.read_json(resolved_path)
                else:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Unsupported file format. Use CSV or JSON.",
                    )

                if columns:
                    if len(columns) == 1:
                        data = df[columns[0]].dropna().tolist()
                    elif len(columns) >= 2:
                        x = df[columns[0]].dropna().tolist()
                        y = df[columns[1]].dropna().tolist()
                        # Ensure equal length
                        min_len = min(len(x), len(y))
                        x = x[:min_len]
                        y = y[:min_len]

            # Descriptive statistics
            if analysis == "descriptive":
                if data is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Data required for descriptive analysis",
                    )

                arr = np.array(data, dtype=float)
                stats_dict = {
                    "count": len(arr),
                    "mean": float(np.mean(arr)),
                    "median": float(np.median(arr)),
                    "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0,
                    "variance": float(np.var(arr, ddof=1)) if len(arr) > 1 else 0,
                    "min": float(np.min(arr)),
                    "max": float(np.max(arr)),
                    "range": float(np.max(arr) - np.min(arr)),
                    "q1": float(np.percentile(arr, 25)),
                    "q3": float(np.percentile(arr, 75)),
                    "iqr": float(np.percentile(arr, 75) - np.percentile(arr, 25)),
                }

                # Mode (most frequent value)
                try:
                    mode_result = scipy_stats.mode(arr, keepdims=True)
                    stats_dict["mode"] = float(mode_result.mode[0])
                except Exception:
                    stats_dict["mode"] = "N/A"

                output_lines = [
                    "**Descriptive Statistics**",
                    "",
                    f"**Count:** {stats_dict['count']}",
                    f"**Mean:** {_format_number(stats_dict['mean'])}",
                    f"**Median:** {_format_number(stats_dict['median'])}",
                    f"**Mode:** {stats_dict['mode']}",
                    f"**Std Dev:** {_format_number(stats_dict['std'])}",
                    f"**Variance:** {_format_number(stats_dict['variance'])}",
                    f"**Min:** {_format_number(stats_dict['min'])}",
                    f"**Max:** {_format_number(stats_dict['max'])}",
                    f"**Range:** {_format_number(stats_dict['range'])}",
                    f"**Q1 (25%):** {_format_number(stats_dict['q1'])}",
                    f"**Q3 (75%):** {_format_number(stats_dict['q3'])}",
                    f"**IQR:** {_format_number(stats_dict['iqr'])}",
                ]

                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata=stats_dict,
                )

            # Correlation analysis
            elif analysis == "correlation":
                if x is None or y is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Both x and y data required for correlation analysis",
                    )

                x_arr = np.array(x, dtype=float)
                y_arr = np.array(y, dtype=float)

                pearson_r, pearson_p = scipy_stats.pearsonr(x_arr, y_arr)
                spearman_r, spearman_p = scipy_stats.spearmanr(x_arr, y_arr)
                kendall_tau, kendall_p = scipy_stats.kendalltau(x_arr, y_arr)

                output_lines = [
                    "**Correlation Analysis**",
                    "",
                    f"**Sample Size:** {len(x_arr)}",
                    "",
                    "**Pearson Correlation:**",
                    f"  r = {_format_number(pearson_r)}",
                    f"  p-value = {_format_number(pearson_p)}",
                    "",
                    "**Spearman Correlation:**",
                    f"  rho = {_format_number(spearman_r)}",
                    f"  p-value = {_format_number(spearman_p)}",
                    "",
                    "**Kendall Tau:**",
                    f"  tau = {_format_number(kendall_tau)}",
                    f"  p-value = {_format_number(kendall_p)}",
                ]

                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata={
                        "pearson_r": float(pearson_r),
                        "pearson_p": float(pearson_p),
                        "spearman_r": float(spearman_r),
                        "spearman_p": float(spearman_p),
                        "kendall_tau": float(kendall_tau),
                        "kendall_p": float(kendall_p),
                    },
                )

            # Normality test
            elif analysis == "normality":
                if data is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Data required for normality test",
                    )

                arr = np.array(data, dtype=float)

                # Shapiro-Wilk test (best for n < 5000)
                if len(arr) < 5000:
                    shapiro_stat, shapiro_p = scipy_stats.shapiro(arr)
                else:
                    shapiro_stat, shapiro_p = None, None

                # D'Agostino-Pearson test (requires n >= 8)
                if len(arr) >= 8:
                    dagostino_stat, dagostino_p = scipy_stats.normaltest(arr)
                else:
                    dagostino_stat, dagostino_p = None, None

                # Skewness and kurtosis
                skewness = float(scipy_stats.skew(arr))
                kurtosis = float(scipy_stats.kurtosis(arr))

                output_lines = [
                    "**Normality Analysis**",
                    "",
                    f"**Sample Size:** {len(arr)}",
                    f"**Skewness:** {_format_number(skewness)} (0 = symmetric)",
                    f"**Kurtosis:** {_format_number(kurtosis)} (0 = normal)",
                    "",
                ]

                if shapiro_stat is not None:
                    output_lines.extend(
                        [
                            "**Shapiro-Wilk Test:**",
                            f"  W = {_format_number(shapiro_stat)}",
                            f"  p-value = {_format_number(shapiro_p)}",
                            f"  Conclusion: {'Normal' if shapiro_p > 0.05 else 'Non-normal'} (alpha=0.05)",
                            "",
                        ]
                    )

                if dagostino_stat is not None:
                    output_lines.extend(
                        [
                            "**D'Agostino-Pearson Test:**",
                            f"  K2 = {_format_number(dagostino_stat)}",
                            f"  p-value = {_format_number(dagostino_p)}",
                            f"  Conclusion: {'Normal' if dagostino_p > 0.05 else 'Non-normal'} (alpha=0.05)",
                        ]
                    )

                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata={
                        "skewness": skewness,
                        "kurtosis": kurtosis,
                        "shapiro_w": float(shapiro_stat) if shapiro_stat else None,
                        "shapiro_p": float(shapiro_p) if shapiro_p else None,
                        "dagostino_k2": float(dagostino_stat) if dagostino_stat else None,
                        "dagostino_p": float(dagostino_p) if dagostino_p else None,
                    },
                )

            # T-test
            elif analysis == "ttest":
                if group1 is None or group2 is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Both group1 and group2 required for t-test",
                    )

                g1 = np.array(group1, dtype=float)
                g2 = np.array(group2, dtype=float)

                # Independent samples t-test
                t_stat, t_p = scipy_stats.ttest_ind(g1, g2)

                # Welch's t-test (unequal variances)
                welch_t, welch_p = scipy_stats.ttest_ind(g1, g2, equal_var=False)

                # Effect size (Cohen's d)
                pooled_std = np.sqrt(((len(g1) - 1) * np.var(g1, ddof=1) + (len(g2) - 1) * np.var(g2, ddof=1)) / (len(g1) + len(g2) - 2))
                cohens_d = (np.mean(g1) - np.mean(g2)) / pooled_std if pooled_std != 0 else 0

                output_lines = [
                    "**Independent Samples T-Test**",
                    "",
                    f"**Group 1:** n={len(g1)}, mean={_format_number(np.mean(g1))}, std={_format_number(np.std(g1, ddof=1))}",
                    f"**Group 2:** n={len(g2)}, mean={_format_number(np.mean(g2))}, std={_format_number(np.std(g2, ddof=1))}",
                    "",
                    "**Student's t-test (equal variances):**",
                    f"  t = {_format_number(t_stat)}",
                    f"  p-value = {_format_number(t_p)}",
                    "",
                    "**Welch's t-test (unequal variances):**",
                    f"  t = {_format_number(welch_t)}",
                    f"  p-value = {_format_number(welch_p)}",
                    "",
                    f"**Cohen's d (effect size):** {_format_number(cohens_d)}",
                    f"**Interpretation:** {'Small' if abs(cohens_d) < 0.5 else 'Medium' if abs(cohens_d) < 0.8 else 'Large'} effect",
                ]

                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata={
                        "t_statistic": float(t_stat),
                        "t_pvalue": float(t_p),
                        "welch_t": float(welch_t),
                        "welch_p": float(welch_p),
                        "cohens_d": float(cohens_d),
                    },
                )

            # ANOVA
            elif analysis == "anova":
                if groups is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error="'groups' parameter required for ANOVA (array of arrays)",
                    )

                groups_arr = [np.array(g, dtype=float) for g in groups]
                f_stat, f_p = scipy_stats.f_oneway(*groups_arr)

                output_lines = [
                    "**One-Way ANOVA**",
                    "",
                    f"**Number of Groups:** {len(groups_arr)}",
                ]

                for i, g in enumerate(groups_arr, 1):
                    output_lines.append(f"**Group {i}:** n={len(g)}, mean={_format_number(np.mean(g))}")

                output_lines.extend(
                    [
                        "",
                        f"**F-statistic:** {_format_number(f_stat)}",
                        f"**p-value:** {_format_number(f_p)}",
                        f"**Conclusion:** {'Significant difference' if f_p < 0.05 else 'No significant difference'} (alpha=0.05)",
                    ]
                )

                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata={
                        "f_statistic": float(f_stat),
                        "p_value": float(f_p),
                        "num_groups": len(groups_arr),
                    },
                )

            # Regression
            elif analysis == "regression":
                if x is None or y is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Both x and y data required for regression",
                    )

                x_arr = np.array(x, dtype=float)
                y_arr = np.array(y, dtype=float)

                # Polynomial fit
                coeffs = np.polyfit(x_arr, y_arr, regression_degree)
                poly = np.poly1d(coeffs)

                # R-squared
                y_pred = poly(x_arr)
                ss_res = np.sum((y_arr - y_pred) ** 2)
                ss_tot = np.sum((y_arr - np.mean(y_arr)) ** 2)
                r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

                # Linear regression details (if degree=1)
                if regression_degree == 1:
                    slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(x_arr, y_arr)

                output_lines = [
                    f"**{'Linear' if regression_degree == 1 else f'Polynomial (degree {regression_degree})'} Regression**",
                    "",
                    f"**Sample Size:** {len(x_arr)}",
                    "",
                ]

                if regression_degree == 1:
                    output_lines.extend(
                        [
                            f"**Slope:** {_format_number(slope)}",
                            f"**Intercept:** {_format_number(intercept)}",
                            f"**Equation:** y = {_format_number(slope)}x + {_format_number(intercept)}",
                            "",
                            f"**R:** {_format_number(r_value)}",
                            f"**R-squared:** {_format_number(r_squared)}",
                            f"**p-value:** {_format_number(p_value)}",
                            f"**Std Error:** {_format_number(std_err)}",
                        ]
                    )

                    return ToolResult(
                        success=True,
                        output="\n".join(output_lines),
                        metadata={
                            "slope": float(slope),
                            "intercept": float(intercept),
                            "r_value": float(r_value),
                            "r_squared": float(r_squared),
                            "p_value": float(p_value),
                            "std_error": float(std_err),
                        },
                    )
                else:
                    # Format polynomial equation
                    terms = []
                    for i, c in enumerate(coeffs):
                        power = regression_degree - i
                        if power == 0:
                            terms.append(f"{_format_number(c)}")
                        elif power == 1:
                            terms.append(f"{_format_number(c)}x")
                        else:
                            terms.append(f"{_format_number(c)}x^{power}")

                    equation = " + ".join(terms)

                    output_lines.extend(
                        [
                            f"**Coefficients:** {[float(c) for c in coeffs]}",
                            f"**Equation:** y = {equation}",
                            "",
                            f"**R-squared:** {_format_number(r_squared)}",
                        ]
                    )

                    return ToolResult(
                        success=True,
                        output="\n".join(output_lines),
                        metadata={
                            "coefficients": [float(c) for c in coeffs],
                            "r_squared": float(r_squared),
                            "degree": regression_degree,
                        },
                    )

            # Distribution analysis
            elif analysis == "distribution":
                if data is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Data required for distribution analysis",
                    )

                arr = np.array(data, dtype=float)

                skewness = float(scipy_stats.skew(arr))
                kurtosis = float(scipy_stats.kurtosis(arr))

                # Fit common distributions
                # Normal
                norm_params = scipy_stats.norm.fit(arr)
                _, norm_p = scipy_stats.kstest(arr, "norm", args=norm_params)

                output_lines = [
                    "**Distribution Analysis**",
                    "",
                    f"**Sample Size:** {len(arr)}",
                    f"**Skewness:** {_format_number(skewness)}",
                    f"**Kurtosis:** {_format_number(kurtosis)}",
                    "",
                    "**Distribution Fit (KS test):**",
                    f"  Normal: mu={_format_number(norm_params[0])}, sigma={_format_number(norm_params[1])}, p={_format_number(norm_p)}",
                ]

                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata={
                        "skewness": skewness,
                        "kurtosis": kurtosis,
                        "normal_mu": float(norm_params[0]),
                        "normal_sigma": float(norm_params[1]),
                        "normal_ks_pvalue": float(norm_p),
                    },
                )

            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown analysis type: {analysis}",
                )

        except Exception as e:
            logger.error("stats_analyze_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Analysis failed: {e}",
            )


class PlotGenerateTool(Tool):
    """Generate scientific plots and charts."""

    name = "plot_generate"
    description = """Generate scientific plots using matplotlib.

Plot types:
- function: Plot mathematical functions (y = f(x))
- scatter: Scatter plot with optional fit line
- histogram: Distribution histogram
- boxplot: Box and whisker plot
- heatmap: 2D heatmap from matrix
- line: Line plot from data points

Examples:
- plot_generate(plot_type="function", expression="sin(x)", x_range=[-3.14, 3.14])
- plot_generate(plot_type="scatter", x=[1,2,3], y=[4,5,6], fit="linear")
- plot_generate(plot_type="histogram", data=[...], bins=20)
- plot_generate(plot_type="function", expressions=["sin(x)", "cos(x)"], legend=True)
- plot_generate(plot_type="line", x=[1,2,3,4], y=[2,4,3,5], title="My Data")"""

    parameters = {
        "type": "object",
        "properties": {
            "plot_type": {
                "type": "string",
                "enum": ["function", "scatter", "histogram", "boxplot", "heatmap", "line"],
                "description": "Type of plot to generate",
            },
            "expression": {
                "type": "string",
                "description": "Mathematical expression for function plots",
            },
            "expressions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Multiple expressions for multi-function plots",
            },
            "x_range": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[min, max] range for x-axis (default: [-10, 10])",
            },
            "x": {
                "type": "array",
                "description": "X data points",
            },
            "y": {
                "type": "array",
                "description": "Y data points",
            },
            "data": {
                "type": "array",
                "description": "Data for histogram/boxplot",
            },
            "matrix": {
                "type": "array",
                "description": "2D array for heatmap",
            },
            "title": {
                "type": "string",
                "description": "Plot title",
            },
            "xlabel": {
                "type": "string",
                "description": "X-axis label",
            },
            "ylabel": {
                "type": "string",
                "description": "Y-axis label",
            },
            "output_file": {
                "type": "string",
                "description": "Save plot to file (PNG, SVG, PDF)",
            },
            "fit": {
                "type": "string",
                "enum": ["linear", "polynomial"],
                "description": "Fit line for scatter plots",
            },
            "fit_degree": {
                "type": "integer",
                "description": "Polynomial degree for fit (default: 2)",
            },
            "bins": {
                "type": "integer",
                "description": "Number of bins for histogram (default: auto)",
            },
            "figsize": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[width, height] in inches (default: [8, 6])",
            },
            "grid": {
                "type": "boolean",
                "description": "Show grid lines (default: true)",
            },
            "legend": {
                "type": "boolean",
                "description": "Show legend (default: auto)",
            },
        },
        "required": ["plot_type"],
    }

    async def execute(
        self,
        plot_type: str,
        expression: Optional[str] = None,
        expressions: Optional[list] = None,
        x_range: Optional[list] = None,
        x: Optional[list] = None,
        y: Optional[list] = None,
        data: Optional[list] = None,
        matrix: Optional[list] = None,
        title: Optional[str] = None,
        xlabel: Optional[str] = None,
        ylabel: Optional[str] = None,
        output_file: Optional[str] = None,
        fit: Optional[str] = None,
        fit_degree: int = 2,
        bins: Optional[int] = None,
        figsize: Optional[list] = None,
        grid: bool = True,
        legend: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute plot generation."""
        logger.info("plot_generate_start", plot_type=plot_type)

        if not MATPLOTLIB_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="matplotlib not installed. Install with: pip install matplotlib",
            )

        try:
            # Set figure size
            fig_width, fig_height = figsize if figsize else [8, 6]
            fig, ax = plt.subplots(figsize=(fig_width, fig_height))

            # Function plot
            if plot_type == "function":
                if not expression and not expressions:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Expression required for function plot",
                    )

                # Set x range
                x_min, x_max = x_range if x_range else [-10, 10]
                x_vals = np.linspace(x_min, x_max, 500)

                # Parse and evaluate expressions
                expr_list = expressions if expressions else [expression]

                for expr_str in expr_list:
                    # Simple evaluation using numpy functions
                    eval_namespace = {
                        "x": x_vals,
                        "sin": np.sin,
                        "cos": np.cos,
                        "tan": np.tan,
                        "exp": np.exp,
                        "log": np.log,
                        "sqrt": np.sqrt,
                        "abs": np.abs,
                        "pi": np.pi,
                        "e": np.e,
                    }

                    try:
                        y_vals = eval(expr_str.replace("^", "**"), {"__builtins__": {}}, eval_namespace)
                        ax.plot(x_vals, y_vals, label=expr_str)
                    except Exception as eval_err:
                        logger.warning("plot_eval_warning", expr=expr_str, error=str(eval_err))
                        continue

                if len(expr_list) > 1 or legend:
                    ax.legend()

                xlabel = xlabel or "x"
                ylabel = ylabel or "y"

            # Scatter plot
            elif plot_type == "scatter":
                if x is None or y is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Both x and y required for scatter plot",
                    )

                x_arr = np.array(x, dtype=float)
                y_arr = np.array(y, dtype=float)

                ax.scatter(x_arr, y_arr, alpha=0.7)

                # Add fit line
                if fit:
                    if fit == "linear":
                        coeffs = np.polyfit(x_arr, y_arr, 1)
                        poly = np.poly1d(coeffs)
                        x_fit = np.linspace(min(x_arr), max(x_arr), 100)
                        ax.plot(x_fit, poly(x_fit), "r-", label=f"Linear fit (y={coeffs[0]:.2f}x+{coeffs[1]:.2f})")
                        ax.legend()
                    elif fit == "polynomial":
                        coeffs = np.polyfit(x_arr, y_arr, fit_degree)
                        poly = np.poly1d(coeffs)
                        x_fit = np.linspace(min(x_arr), max(x_arr), 100)
                        ax.plot(x_fit, poly(x_fit), "r-", label=f"Polynomial fit (degree {fit_degree})")
                        ax.legend()

            # Histogram
            elif plot_type == "histogram":
                if data is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Data required for histogram",
                    )

                arr = np.array(data, dtype=float)
                ax.hist(arr, bins=bins if bins else "auto", edgecolor="black", alpha=0.7)
                xlabel = xlabel or "Value"
                ylabel = ylabel or "Frequency"

            # Boxplot
            elif plot_type == "boxplot":
                if data is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Data required for boxplot",
                    )

                # Handle multiple groups or single group
                if isinstance(data[0], list):
                    ax.boxplot(data)
                else:
                    ax.boxplot([data])

                ylabel = ylabel or "Value"

            # Heatmap
            elif plot_type == "heatmap":
                if matrix is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Matrix required for heatmap",
                    )

                arr = np.array(matrix, dtype=float)
                im = ax.imshow(arr, cmap="viridis", aspect="auto")
                plt.colorbar(im, ax=ax)

            # Line plot
            elif plot_type == "line":
                if y is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error="y data required for line plot",
                    )

                y_arr = np.array(y, dtype=float)
                x_arr = np.array(x, dtype=float) if x else np.arange(len(y_arr))

                ax.plot(x_arr, y_arr, marker="o")

            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown plot type: {plot_type}",
                )

            # Set labels and title
            if title:
                ax.set_title(title)
            if xlabel:
                ax.set_xlabel(xlabel)
            if ylabel:
                ax.set_ylabel(ylabel)
            if grid:
                ax.grid(True, alpha=0.3)

            plt.tight_layout()

            # Save or encode
            if output_file:
                resolved_path = self._resolve_path(output_file)
                plt.savefig(resolved_path, dpi=150, bbox_inches="tight")
                plt.close(fig)

                output_text = f"**Plot Generated**\n\nSaved to: `{output_file}`"
                metadata = {"output_file": str(resolved_path), "plot_type": plot_type}
            else:
                # Encode to base64
                buf = io.BytesIO()
                plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
                buf.seek(0)
                img_base64 = base64.b64encode(buf.read()).decode("utf-8")
                plt.close(fig)

                output_text = f"**Plot Generated**\n\nPlot type: {plot_type}\n(Base64 encoded PNG in metadata)"
                metadata = {"base64": img_base64, "plot_type": plot_type}

            logger.info("plot_generate_success", plot_type=plot_type)

            return ToolResult(
                success=True,
                output=output_text,
                metadata=metadata,
            )

        except Exception as e:
            logger.error("plot_generate_error", error=str(e))
            plt.close("all")
            return ToolResult(
                success=False,
                output="",
                error=f"Plot generation failed: {e}",
            )


class UnitConvertTool(Tool):
    """Convert between physical units."""

    name = "unit_convert"
    description = """Convert values between physical units.

Supports:
- Length: meter, foot, inch, mile, kilometer, light_year
- Mass: kilogram, pound, ounce, gram, tonne
- Time: second, minute, hour, day, year
- Temperature: celsius, fahrenheit, kelvin
- Speed: m/s, km/h, mph, knot
- Energy: joule, calorie, eV, kWh, BTU
- Pressure: pascal, bar, atm, psi
- Volume: liter, gallon, cubic_meter
- Area: square_meter, acre, hectare
- Force: newton, pound_force
- Power: watt, horsepower
- And many more (pint's full unit registry)

Examples:
- unit_convert(value=100, from_unit="celsius", to_unit="fahrenheit") -> 212 F
- unit_convert(value=1, from_unit="mile", to_unit="kilometer") -> 1.609 km
- unit_convert(value=9.8, from_unit="m/s**2", to_unit="ft/s**2")
- unit_convert(expression="5 kg * 9.8 m/s**2") -> 49 N"""

    parameters = {
        "type": "object",
        "properties": {
            "value": {
                "type": "number",
                "description": "Numeric value to convert",
            },
            "from_unit": {
                "type": "string",
                "description": "Source unit (e.g., 'meter', 'kg', 'celsius')",
            },
            "to_unit": {
                "type": "string",
                "description": "Target unit",
            },
            "expression": {
                "type": "string",
                "description": "Expression with units (e.g., '5 kg * 9.8 m/s**2')",
            },
            "precision": {
                "type": "integer",
                "description": "Decimal precision (default: 6)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        value: Optional[float] = None,
        from_unit: Optional[str] = None,
        to_unit: Optional[str] = None,
        expression: Optional[str] = None,
        precision: int = 6,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute unit conversion."""
        logger.info("unit_convert_start", value=value, from_unit=from_unit, to_unit=to_unit)

        if not PINT_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="pint not installed. Install with: pip install pint",
            )

        try:
            # Handle temperature separately for celsius/fahrenheit
            if from_unit and to_unit:
                from_lower = from_unit.lower()
                to_lower = to_unit.lower()

                # Temperature conversion
                if from_lower in ["celsius", "degc", "c"] and to_lower in ["fahrenheit", "degf", "f"]:
                    result_val = value * 9 / 5 + 32
                    output_text = f"**Unit Conversion**\n\n{value} {from_unit} = **{_format_number(result_val, precision)} {to_unit}**"
                    return ToolResult(
                        success=True,
                        output=output_text,
                        metadata={"value": value, "from_unit": from_unit, "to_unit": to_unit, "result": result_val},
                    )

                elif from_lower in ["fahrenheit", "degf", "f"] and to_lower in ["celsius", "degc", "c"]:
                    result_val = (value - 32) * 5 / 9
                    output_text = f"**Unit Conversion**\n\n{value} {from_unit} = **{_format_number(result_val, precision)} {to_unit}**"
                    return ToolResult(
                        success=True,
                        output=output_text,
                        metadata={"value": value, "from_unit": from_unit, "to_unit": to_unit, "result": result_val},
                    )

                elif from_lower in ["celsius", "degc", "c"] and to_lower in ["kelvin", "k"]:
                    result_val = value + 273.15
                    output_text = f"**Unit Conversion**\n\n{value} {from_unit} = **{_format_number(result_val, precision)} {to_unit}**"
                    return ToolResult(
                        success=True,
                        output=output_text,
                        metadata={"value": value, "from_unit": from_unit, "to_unit": to_unit, "result": result_val},
                    )

                elif from_lower in ["kelvin", "k"] and to_lower in ["celsius", "degc", "c"]:
                    result_val = value - 273.15
                    output_text = f"**Unit Conversion**\n\n{value} {from_unit} = **{_format_number(result_val, precision)} {to_unit}**"
                    return ToolResult(
                        success=True,
                        output=output_text,
                        metadata={"value": value, "from_unit": from_unit, "to_unit": to_unit, "result": result_val},
                    )

            # Expression evaluation
            if expression:
                quantity = ureg.parse_expression(expression)
                result = quantity.to_base_units()

                output_text = f"**Unit Calculation**\n\n`{expression}` = **{result:.{precision}g}**"

                return ToolResult(
                    success=True,
                    output=output_text,
                    metadata={
                        "expression": expression,
                        "result": str(result),
                        "magnitude": float(result.magnitude),
                        "units": str(result.units),
                    },
                )

            # Standard conversion
            if value is None or from_unit is None or to_unit is None:
                return ToolResult(
                    success=False,
                    output="",
                    error="Either provide (value, from_unit, to_unit) or (expression)",
                )

            # Create quantity and convert
            quantity = value * ureg(from_unit)
            result = quantity.to(to_unit)

            result_val = result.magnitude
            output_text = f"**Unit Conversion**\n\n{value} {from_unit} = **{_format_number(result_val, precision)} {to_unit}**"

            logger.info("unit_convert_success", result=result_val)

            return ToolResult(
                success=True,
                output=output_text,
                metadata={
                    "value": value,
                    "from_unit": from_unit,
                    "to_unit": to_unit,
                    "result": float(result_val),
                },
            )

        except pint.errors.DimensionalityError as e:
            logger.error("unit_convert_dimension_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Incompatible units: {e}",
                suggestion="Ensure units have compatible dimensions (e.g., length to length, not length to mass)",
            )
        except pint.errors.UndefinedUnitError as e:
            logger.error("unit_convert_undefined_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown unit: {e}",
                suggestion="Check unit spelling. Common units: meter, kilogram, second, kelvin, ampere, mole, candela",
            )
        except Exception as e:
            logger.error("unit_convert_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Conversion failed: {e}",
            )


class MatrixOperationsTool(Tool):
    """Perform matrix and linear algebra operations."""

    name = "matrix_operations"
    description = """Perform matrix and linear algebra operations.

Operations:
- Basic: add, subtract, multiply, transpose, inverse
- Decomposition: eigenvalues, eigenvectors, svd, lu, qr, cholesky
- Properties: determinant, rank, trace, norm
- Solve: linear system Ax = b
- Create: identity, zeros, ones, diagonal, random

Examples:
- matrix_operations(operation="multiply", a=[[1,2],[3,4]], b=[[5,6],[7,8]])
- matrix_operations(operation="inverse", matrix=[[1,2],[3,4]])
- matrix_operations(operation="eigenvalues", matrix=[[4,-2],[1,1]])
- matrix_operations(operation="solve", a=[[2,1],[1,3]], b=[4,5])
- matrix_operations(operation="svd", matrix=[[1,2,3],[4,5,6]])
- matrix_operations(operation="identity", size=[3,3])"""

    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "add",
                    "subtract",
                    "multiply",
                    "transpose",
                    "inverse",
                    "determinant",
                    "eigenvalues",
                    "eigenvectors",
                    "svd",
                    "lu",
                    "qr",
                    "cholesky",
                    "rank",
                    "trace",
                    "norm",
                    "solve",
                    "identity",
                    "zeros",
                    "ones",
                    "diagonal",
                    "random",
                ],
                "description": "Matrix operation to perform",
            },
            "matrix": {
                "type": "array",
                "description": "Input matrix (2D array)",
            },
            "a": {
                "type": "array",
                "description": "First matrix for binary operations",
            },
            "b": {
                "type": "array",
                "description": "Second matrix/vector for binary operations or Ax=b",
            },
            "size": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "[rows, cols] for creation operations",
            },
            "diagonal_values": {
                "type": "array",
                "description": "Values for diagonal matrix",
            },
            "precision": {
                "type": "integer",
                "description": "Decimal precision for output (default: 6)",
            },
        },
        "required": ["operation"],
    }

    async def execute(
        self,
        operation: str,
        matrix: Optional[list] = None,
        a: Optional[list] = None,
        b: Optional[list] = None,
        size: Optional[list] = None,
        diagonal_values: Optional[list] = None,
        precision: int = 6,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute matrix operation."""
        logger.info("matrix_operations_start", operation=operation)

        try:

            def format_matrix(mat: np.ndarray) -> str:
                """Format matrix for display."""
                rows = []
                for row in mat:
                    if mat.ndim == 1:
                        row_str = " ".join(_format_number(float(x), precision) for x in mat)
                        return f"[{row_str}]"
                    row_str = " ".join(_format_number(float(x), precision) for x in row)
                    rows.append(f"  [{row_str}]")
                return "[\n" + "\n".join(rows) + "\n]"

            # Binary operations
            if operation in ["add", "subtract", "multiply"]:
                if a is None or b is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Both 'a' and 'b' matrices required for {operation}",
                    )

                a_arr = np.array(a, dtype=float)
                b_arr = np.array(b, dtype=float)

                if operation == "add":
                    result = a_arr + b_arr
                elif operation == "subtract":
                    result = a_arr - b_arr
                else:  # multiply
                    result = np.matmul(a_arr, b_arr)

                output_lines = [
                    f"**Matrix {operation.capitalize()}**",
                    "",
                    "**A:**",
                    format_matrix(a_arr),
                    "",
                    "**B:**",
                    format_matrix(b_arr),
                    "",
                    "**Result:**",
                    format_matrix(result),
                ]

                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata={"result": result.tolist(), "shape": list(result.shape)},
                )

            # Unary operations
            if operation in ["transpose", "inverse", "determinant", "eigenvalues", "eigenvectors", "svd", "lu", "qr", "cholesky", "rank", "trace", "norm"]:
                if matrix is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Matrix required for {operation}",
                    )

                mat = np.array(matrix, dtype=float)

                if operation == "transpose":
                    result = mat.T
                    output_lines = [
                        "**Matrix Transpose**",
                        "",
                        "**Input:**",
                        format_matrix(mat),
                        "",
                        "**Result:**",
                        format_matrix(result),
                    ]
                    return ToolResult(
                        success=True,
                        output="\n".join(output_lines),
                        metadata={"result": result.tolist()},
                    )

                elif operation == "inverse":
                    result = np.linalg.inv(mat)
                    output_lines = [
                        "**Matrix Inverse**",
                        "",
                        "**Input:**",
                        format_matrix(mat),
                        "",
                        "**Inverse:**",
                        format_matrix(result),
                    ]
                    return ToolResult(
                        success=True,
                        output="\n".join(output_lines),
                        metadata={"result": result.tolist()},
                    )

                elif operation == "determinant":
                    det = np.linalg.det(mat)
                    output_lines = [
                        "**Matrix Determinant**",
                        "",
                        "**Input:**",
                        format_matrix(mat),
                        "",
                        f"**Determinant:** {_format_number(det, precision)}",
                    ]
                    return ToolResult(
                        success=True,
                        output="\n".join(output_lines),
                        metadata={"determinant": float(det)},
                    )

                elif operation == "eigenvalues":
                    eigenvalues = np.linalg.eigvals(mat)
                    output_lines = [
                        "**Eigenvalues**",
                        "",
                        "**Input:**",
                        format_matrix(mat),
                        "",
                        "**Eigenvalues:**",
                    ]
                    for i, ev in enumerate(eigenvalues, 1):
                        if np.iscomplex(ev):
                            output_lines.append(f"  {i}. {ev.real:.{precision}f} + {ev.imag:.{precision}f}i")
                        else:
                            output_lines.append(f"  {i}. {_format_number(float(ev.real), precision)}")

                    return ToolResult(
                        success=True,
                        output="\n".join(output_lines),
                        metadata={"eigenvalues": [complex(x) for x in eigenvalues]},
                    )

                elif operation == "eigenvectors":
                    eigenvalues, eigenvectors = np.linalg.eig(mat)
                    output_lines = [
                        "**Eigenvalues and Eigenvectors**",
                        "",
                        "**Input:**",
                        format_matrix(mat),
                        "",
                    ]
                    for i, (ev, vec) in enumerate(zip(eigenvalues, eigenvectors.T), 1):
                        if np.iscomplex(ev):
                            ev_str = f"{ev.real:.{precision}f} + {ev.imag:.{precision}f}i"
                        else:
                            ev_str = _format_number(float(ev.real), precision)
                        vec_str = "[" + ", ".join(_format_number(float(v.real), precision) for v in vec) + "]"
                        output_lines.append(f"**Eigenvalue {i}:** {ev_str}")
                        output_lines.append(f"**Eigenvector {i}:** {vec_str}")
                        output_lines.append("")

                    return ToolResult(
                        success=True,
                        output="\n".join(output_lines),
                        metadata={
                            "eigenvalues": [complex(x) for x in eigenvalues],
                            "eigenvectors": eigenvectors.tolist(),
                        },
                    )

                elif operation == "svd":
                    U, S, Vt = np.linalg.svd(mat)
                    output_lines = [
                        "**Singular Value Decomposition (SVD)**",
                        "",
                        "**Input:**",
                        format_matrix(mat),
                        "",
                        "**U:**",
                        format_matrix(U),
                        "",
                        "**Singular Values (S):**",
                        "[" + ", ".join(_format_number(float(s), precision) for s in S) + "]",
                        "",
                        "**V^T:**",
                        format_matrix(Vt),
                    ]
                    return ToolResult(
                        success=True,
                        output="\n".join(output_lines),
                        metadata={"U": U.tolist(), "S": S.tolist(), "Vt": Vt.tolist()},
                    )

                elif operation == "lu":
                    from scipy.linalg import lu

                    P, L, U = lu(mat)
                    output_lines = [
                        "**LU Decomposition**",
                        "",
                        "**Input:**",
                        format_matrix(mat),
                        "",
                        "**P (Permutation):**",
                        format_matrix(P),
                        "",
                        "**L (Lower):**",
                        format_matrix(L),
                        "",
                        "**U (Upper):**",
                        format_matrix(U),
                    ]
                    return ToolResult(
                        success=True,
                        output="\n".join(output_lines),
                        metadata={"P": P.tolist(), "L": L.tolist(), "U": U.tolist()},
                    )

                elif operation == "qr":
                    Q, R = np.linalg.qr(mat)
                    output_lines = [
                        "**QR Decomposition**",
                        "",
                        "**Input:**",
                        format_matrix(mat),
                        "",
                        "**Q (Orthogonal):**",
                        format_matrix(Q),
                        "",
                        "**R (Upper Triangular):**",
                        format_matrix(R),
                    ]
                    return ToolResult(
                        success=True,
                        output="\n".join(output_lines),
                        metadata={"Q": Q.tolist(), "R": R.tolist()},
                    )

                elif operation == "cholesky":
                    L = np.linalg.cholesky(mat)
                    output_lines = [
                        "**Cholesky Decomposition**",
                        "",
                        "**Input:**",
                        format_matrix(mat),
                        "",
                        "**L (Lower Triangular):**",
                        format_matrix(L),
                        "",
                        "Note: A = L @ L.T",
                    ]
                    return ToolResult(
                        success=True,
                        output="\n".join(output_lines),
                        metadata={"L": L.tolist()},
                    )

                elif operation == "rank":
                    r = np.linalg.matrix_rank(mat)
                    output_lines = [
                        "**Matrix Rank**",
                        "",
                        "**Input:**",
                        format_matrix(mat),
                        "",
                        f"**Rank:** {r}",
                    ]
                    return ToolResult(
                        success=True,
                        output="\n".join(output_lines),
                        metadata={"rank": int(r)},
                    )

                elif operation == "trace":
                    tr = np.trace(mat)
                    output_lines = [
                        "**Matrix Trace**",
                        "",
                        "**Input:**",
                        format_matrix(mat),
                        "",
                        f"**Trace:** {_format_number(tr, precision)}",
                    ]
                    return ToolResult(
                        success=True,
                        output="\n".join(output_lines),
                        metadata={"trace": float(tr)},
                    )

                elif operation == "norm":
                    frobenius = np.linalg.norm(mat, "fro")
                    spectral = np.linalg.norm(mat, 2)
                    output_lines = [
                        "**Matrix Norms**",
                        "",
                        "**Input:**",
                        format_matrix(mat),
                        "",
                        f"**Frobenius Norm:** {_format_number(frobenius, precision)}",
                        f"**Spectral Norm (2-norm):** {_format_number(spectral, precision)}",
                    ]
                    return ToolResult(
                        success=True,
                        output="\n".join(output_lines),
                        metadata={"frobenius_norm": float(frobenius), "spectral_norm": float(spectral)},
                    )

            # Solve linear system
            if operation == "solve":
                if a is None or b is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Both 'a' (matrix) and 'b' (vector) required for solve",
                    )

                a_arr = np.array(a, dtype=float)
                b_arr = np.array(b, dtype=float)
                x = np.linalg.solve(a_arr, b_arr)

                output_lines = [
                    "**Solve Linear System (Ax = b)**",
                    "",
                    "**A:**",
                    format_matrix(a_arr),
                    "",
                    "**b:**",
                    format_matrix(b_arr),
                    "",
                    "**Solution x:**",
                    format_matrix(x),
                ]
                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata={"solution": x.tolist()},
                )

            # Creation operations
            if operation in ["identity", "zeros", "ones", "diagonal", "random"]:
                if operation == "identity":
                    if size is None:
                        return ToolResult(
                            success=False,
                            output="",
                            error="Size required for identity matrix (e.g., size=[3,3])",
                        )
                    n = size[0]
                    result = np.eye(n)

                elif operation == "zeros":
                    if size is None:
                        return ToolResult(
                            success=False,
                            output="",
                            error="Size required (e.g., size=[3,4])",
                        )
                    result = np.zeros(tuple(size))

                elif operation == "ones":
                    if size is None:
                        return ToolResult(
                            success=False,
                            output="",
                            error="Size required (e.g., size=[3,4])",
                        )
                    result = np.ones(tuple(size))

                elif operation == "diagonal":
                    if diagonal_values is None:
                        return ToolResult(
                            success=False,
                            output="",
                            error="diagonal_values required for diagonal matrix",
                        )
                    result = np.diag(diagonal_values)

                elif operation == "random":
                    if size is None:
                        return ToolResult(
                            success=False,
                            output="",
                            error="Size required (e.g., size=[3,4])",
                        )
                    result = np.random.rand(*size)

                output_lines = [
                    f"**{operation.capitalize()} Matrix**",
                    "",
                    f"**Shape:** {result.shape}",
                    "",
                    "**Result:**",
                    format_matrix(result),
                ]
                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata={"result": result.tolist(), "shape": list(result.shape)},
                )

            return ToolResult(
                success=False,
                output="",
                error=f"Unknown operation: {operation}",
            )

        except np.linalg.LinAlgError as e:
            logger.error("matrix_operations_linalg_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Linear algebra error: {e}",
                suggestion="Check if matrix is singular, non-square, or not positive definite",
            )
        except Exception as e:
            logger.error("matrix_operations_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Operation failed: {e}",
            )
