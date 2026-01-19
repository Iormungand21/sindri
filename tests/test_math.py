"""Tests for math and scientific tools (Phase 12).

Comprehensive test suite for the Nidhogg agent's math tools.
"""

import json
import math
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

from sindri.tools.math import (
    MathEvaluateTool,
    MathSolveTool,
    MatrixOperationsTool,
    PlotGenerateTool,
    StatsAnalyzeTool,
    UnitConvertTool,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_csv(tmp_path):
    """Create sample CSV for stats tests."""
    csv_content = """x,y,group
1,2.1,A
2,4.2,A
3,5.8,B
4,8.1,B
5,10.2,A
"""
    csv_file = tmp_path / "data.csv"
    csv_file.write_text(csv_content)
    return csv_file


# ═══════════════════════════════════════════════════════════════════════════════
# MathEvaluateTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMathEvaluateTool:
    """Test suite for MathEvaluateTool."""

    @pytest.fixture
    def tool(self):
        return MathEvaluateTool()

    @pytest.mark.asyncio
    async def test_basic_arithmetic(self, tool):
        """Test basic arithmetic evaluation."""
        result = await tool.execute(expression="2 + 3 * 4")
        assert result.success
        assert "14" in result.output

    @pytest.mark.asyncio
    async def test_sqrt_and_power(self, tool):
        """Test square root and powers."""
        result = await tool.execute(expression="sqrt(16) + 2**3")
        assert result.success
        assert "12" in result.output

    @pytest.mark.asyncio
    async def test_trigonometric(self, tool):
        """Test trigonometric functions."""
        result = await tool.execute(expression="sin(pi/2)", numeric=True)
        assert result.success
        assert "1" in result.output

    @pytest.mark.asyncio
    async def test_symbolic_expression(self, tool):
        """Test symbolic expression without evaluation."""
        result = await tool.execute(expression="x**2 + 2*x + 1")
        assert result.success
        # Should return symbolic form or simplified
        assert "x" in result.output or "+" in result.output

    @pytest.mark.asyncio
    async def test_substitution(self, tool):
        """Test variable substitution."""
        result = await tool.execute(expression="x**2 + y", values={"x": 3, "y": 5})
        assert result.success
        assert "14" in result.output

    @pytest.mark.asyncio
    async def test_constants(self, tool):
        """Test mathematical constants."""
        result = await tool.execute(expression="pi + e", numeric=True)
        assert result.success
        # pi + e ~ 5.86
        assert "5.8" in result.output or "5.9" in result.output

    @pytest.mark.asyncio
    async def test_factorial(self, tool):
        """Test factorial function."""
        result = await tool.execute(expression="factorial(5)")
        assert result.success
        assert "120" in result.output

    @pytest.mark.asyncio
    async def test_log_and_exp(self, tool):
        """Test logarithm and exponential."""
        result = await tool.execute(expression="log(e)", numeric=True)
        assert result.success
        assert "1" in result.output

    @pytest.mark.asyncio
    async def test_abs_function(self, tool):
        """Test absolute value."""
        result = await tool.execute(expression="abs(-5)")
        assert result.success
        assert "5" in result.output

    @pytest.mark.asyncio
    async def test_derivative(self, tool):
        """Test derivative computation."""
        result = await tool.execute(expression="diff(x**3, x)")
        assert result.success
        # derivative of x^3 is 3x^2
        assert "3" in result.output and "x" in result.output

    @pytest.mark.asyncio
    async def test_integral(self, tool):
        """Test integration computation."""
        result = await tool.execute(expression="integrate(x**2, x)")
        assert result.success
        # integral of x^2 is x^3/3
        assert "x" in result.output and "3" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# MathSolveTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMathSolveTool:
    """Test suite for MathSolveTool."""

    @pytest.fixture
    def tool(self):
        return MathSolveTool()

    @pytest.mark.asyncio
    async def test_linear_equation(self, tool):
        """Test solving linear equation."""
        result = await tool.execute(equation="2*x + 3 = 11", variable="x")
        assert result.success
        assert "4" in result.output

    @pytest.mark.asyncio
    async def test_quadratic_equation(self, tool):
        """Test solving quadratic equation."""
        result = await tool.execute(equation="x**2 - 4")
        assert result.success
        assert "2" in result.output
        assert "-2" in result.output

    @pytest.mark.asyncio
    async def test_system_of_equations(self, tool):
        """Test solving system of equations."""
        result = await tool.execute(
            equations=["x + y = 10", "x - y = 2"], variables=["x", "y"]
        )
        assert result.success
        assert "6" in result.output  # x = 6
        assert "4" in result.output  # y = 4

    @pytest.mark.asyncio
    async def test_complex_solutions(self, tool):
        """Test equations with complex solutions."""
        result = await tool.execute(equation="x**2 + 1", domain="complex")
        assert result.success
        assert "I" in result.output or "i" in result.output.lower()

    @pytest.mark.asyncio
    async def test_cubic_equation(self, tool):
        """Test solving cubic equation."""
        result = await tool.execute(equation="x**3 - 8")
        assert result.success
        assert "2" in result.output  # Real root

    @pytest.mark.asyncio
    async def test_equation_with_equals(self, tool):
        """Test equation with explicit equals sign."""
        result = await tool.execute(equation="x**2 = 9")
        assert result.success
        assert "3" in result.output
        assert "-3" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# StatsAnalyzeTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatsAnalyzeTool:
    """Test suite for StatsAnalyzeTool."""

    @pytest.fixture
    def tool(self):
        return StatsAnalyzeTool()

    @pytest.mark.asyncio
    async def test_descriptive_stats(self, tool):
        """Test descriptive statistics."""
        result = await tool.execute(data=[1, 2, 3, 4, 5], analysis="descriptive")
        assert result.success
        assert "mean" in result.output.lower()
        assert "3" in result.output  # mean = 3

    @pytest.mark.asyncio
    async def test_correlation(self, tool):
        """Test correlation analysis."""
        result = await tool.execute(
            x=[1, 2, 3, 4, 5], y=[2, 4, 6, 8, 10], analysis="correlation"
        )
        assert result.success
        assert "correlation" in result.output.lower() or "1" in result.output

    @pytest.mark.asyncio
    async def test_correlation_from_file(self, tool, sample_csv):
        """Test correlation analysis from CSV file."""
        result = await tool.execute(
            file_path=str(sample_csv), columns=["x", "y"], analysis="correlation"
        )
        assert result.success
        assert "correlation" in result.output.lower() or "pearson" in result.output.lower()

    @pytest.mark.asyncio
    async def test_ttest(self, tool):
        """Test t-test analysis."""
        result = await tool.execute(
            group1=[1, 2, 3, 4, 5], group2=[6, 7, 8, 9, 10], analysis="ttest"
        )
        assert result.success
        assert "p-value" in result.output.lower() or "statistic" in result.output.lower()

    @pytest.mark.asyncio
    async def test_regression(self, tool):
        """Test linear regression."""
        result = await tool.execute(
            x=[1, 2, 3, 4, 5], y=[2.1, 3.9, 6.1, 8.0, 9.9], analysis="regression"
        )
        assert result.success
        assert "slope" in result.output.lower() or "r-squared" in result.output.lower()

    @pytest.mark.asyncio
    async def test_normality(self, tool):
        """Test normality analysis."""
        # Normal-like distribution
        result = await tool.execute(
            data=[1, 2, 2, 3, 3, 3, 4, 4, 5], analysis="normality"
        )
        assert result.success
        assert "normality" in result.output.lower() or "shapiro" in result.output.lower()

    @pytest.mark.asyncio
    async def test_anova(self, tool):
        """Test ANOVA analysis."""
        result = await tool.execute(
            groups=[[1, 2, 3], [4, 5, 6], [7, 8, 9]], analysis="anova"
        )
        assert result.success
        assert "f-statistic" in result.output.lower() or "anova" in result.output.lower()

    @pytest.mark.asyncio
    async def test_distribution(self, tool):
        """Test distribution analysis."""
        result = await tool.execute(data=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10], analysis="distribution")
        assert result.success
        assert "distribution" in result.output.lower() or "skewness" in result.output.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# PlotGenerateTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlotGenerateTool:
    """Test suite for PlotGenerateTool."""

    @pytest.fixture
    def tool(self):
        return PlotGenerateTool()

    @pytest.mark.asyncio
    async def test_function_plot(self, tool, tmp_path):
        """Test function plot generation."""
        output_file = tmp_path / "plot.png"
        result = await tool.execute(
            plot_type="function",
            expression="sin(x)",
            x_range=[-3.14, 3.14],
            output_file=str(output_file),
        )
        assert result.success
        assert output_file.exists()

    @pytest.mark.asyncio
    async def test_scatter_plot(self, tool, tmp_path):
        """Test scatter plot generation."""
        output_file = tmp_path / "scatter.png"
        result = await tool.execute(
            plot_type="scatter",
            x=[1, 2, 3, 4, 5],
            y=[2, 4, 5, 4, 5],
            output_file=str(output_file),
        )
        assert result.success
        assert output_file.exists()

    @pytest.mark.asyncio
    async def test_histogram(self, tool, tmp_path):
        """Test histogram generation."""
        import random

        output_file = tmp_path / "hist.png"
        result = await tool.execute(
            plot_type="histogram",
            data=[random.gauss(0, 1) for _ in range(100)],
            output_file=str(output_file),
        )
        assert result.success
        assert output_file.exists()

    @pytest.mark.asyncio
    async def test_multiple_functions(self, tool, tmp_path):
        """Test multiple function plot."""
        output_file = tmp_path / "multi.png"
        result = await tool.execute(
            plot_type="function",
            expressions=["sin(x)", "cos(x)"],
            x_range=[-3.14, 3.14],
            legend=True,
            output_file=str(output_file),
        )
        assert result.success
        assert output_file.exists()

    @pytest.mark.asyncio
    async def test_scatter_with_fit(self, tool, tmp_path):
        """Test scatter plot with linear fit."""
        output_file = tmp_path / "scatter_fit.png"
        result = await tool.execute(
            plot_type="scatter",
            x=[1, 2, 3, 4, 5],
            y=[2.1, 4.0, 5.9, 8.1, 10.0],
            fit="linear",
            output_file=str(output_file),
        )
        assert result.success
        assert output_file.exists()

    @pytest.mark.asyncio
    async def test_line_plot(self, tool, tmp_path):
        """Test line plot generation."""
        output_file = tmp_path / "line.png"
        result = await tool.execute(
            plot_type="line",
            x=[1, 2, 3, 4, 5],
            y=[1, 4, 9, 16, 25],
            title="Square Numbers",
            output_file=str(output_file),
        )
        assert result.success
        assert output_file.exists()

    @pytest.mark.asyncio
    async def test_heatmap(self, tool, tmp_path):
        """Test heatmap generation."""
        output_file = tmp_path / "heatmap.png"
        result = await tool.execute(
            plot_type="heatmap",
            matrix=[[1, 2, 3], [4, 5, 6], [7, 8, 9]],
            output_file=str(output_file),
        )
        assert result.success
        assert output_file.exists()

    @pytest.mark.asyncio
    async def test_boxplot(self, tool, tmp_path):
        """Test boxplot generation."""
        output_file = tmp_path / "boxplot.png"
        result = await tool.execute(
            plot_type="boxplot",
            data=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            output_file=str(output_file),
        )
        assert result.success
        assert output_file.exists()

    @pytest.mark.asyncio
    async def test_base64_output(self, tool):
        """Test base64 output when no file specified."""
        result = await tool.execute(
            plot_type="function",
            expression="x**2",
            x_range=[-5, 5],
        )
        assert result.success
        assert "base64" in result.metadata


# ═══════════════════════════════════════════════════════════════════════════════
# UnitConvertTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestUnitConvertTool:
    """Test suite for UnitConvertTool."""

    @pytest.fixture
    def tool(self):
        return UnitConvertTool()

    @pytest.mark.asyncio
    async def test_length_conversion(self, tool):
        """Test length unit conversion."""
        result = await tool.execute(value=1, from_unit="mile", to_unit="kilometer")
        assert result.success
        assert "1.6" in result.output  # 1 mile ~ 1.609 km

    @pytest.mark.asyncio
    async def test_temperature_celsius_to_fahrenheit(self, tool):
        """Test temperature conversion C to F."""
        result = await tool.execute(value=100, from_unit="celsius", to_unit="fahrenheit")
        assert result.success
        assert "212" in result.output  # 100C = 212F

    @pytest.mark.asyncio
    async def test_temperature_fahrenheit_to_celsius(self, tool):
        """Test temperature conversion F to C."""
        result = await tool.execute(value=32, from_unit="fahrenheit", to_unit="celsius")
        assert result.success
        assert "0" in result.output  # 32F = 0C

    @pytest.mark.asyncio
    async def test_mass_conversion(self, tool):
        """Test mass conversion."""
        result = await tool.execute(value=1, from_unit="kilogram", to_unit="pound")
        assert result.success
        assert "2.2" in result.output  # 1 kg ~ 2.2 lb

    @pytest.mark.asyncio
    async def test_time_conversion(self, tool):
        """Test time conversion."""
        result = await tool.execute(value=1, from_unit="hour", to_unit="second")
        assert result.success
        assert "3600" in result.output  # 1 hour = 3600 seconds

    @pytest.mark.asyncio
    async def test_speed_conversion(self, tool):
        """Test speed conversion."""
        result = await tool.execute(value=100, from_unit="km/hour", to_unit="mile/hour")
        assert result.success
        assert "62" in result.output  # 100 km/h ~ 62 mph

    @pytest.mark.asyncio
    async def test_expression_with_units(self, tool):
        """Test expression with units."""
        result = await tool.execute(expression="5 kg * 9.8 m/s**2")
        assert result.success
        # 5 * 9.8 = 49 N
        assert "49" in result.output

    @pytest.mark.asyncio
    async def test_celsius_to_kelvin(self, tool):
        """Test celsius to kelvin conversion."""
        result = await tool.execute(value=0, from_unit="celsius", to_unit="kelvin")
        assert result.success
        assert "273" in result.output  # 0C = 273.15K


# ═══════════════════════════════════════════════════════════════════════════════
# MatrixOperationsTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMatrixOperationsTool:
    """Test suite for MatrixOperationsTool."""

    @pytest.fixture
    def tool(self):
        return MatrixOperationsTool()

    @pytest.mark.asyncio
    async def test_matrix_multiply(self, tool):
        """Test matrix multiplication."""
        result = await tool.execute(
            operation="multiply", a=[[1, 2], [3, 4]], b=[[5, 6], [7, 8]]
        )
        assert result.success
        assert "19" in result.output  # result[0][0]
        assert "22" in result.output  # result[0][1]

    @pytest.mark.asyncio
    async def test_matrix_add(self, tool):
        """Test matrix addition."""
        result = await tool.execute(
            operation="add", a=[[1, 2], [3, 4]], b=[[5, 6], [7, 8]]
        )
        assert result.success
        assert "6" in result.output  # 1+5
        assert "8" in result.output  # 2+6

    @pytest.mark.asyncio
    async def test_matrix_inverse(self, tool):
        """Test matrix inverse."""
        result = await tool.execute(operation="inverse", matrix=[[4, 7], [2, 6]])
        assert result.success
        assert result.metadata.get("result") is not None

    @pytest.mark.asyncio
    async def test_determinant(self, tool):
        """Test determinant calculation."""
        result = await tool.execute(operation="determinant", matrix=[[1, 2], [3, 4]])
        assert result.success
        assert "-2" in result.output  # det = 1*4 - 2*3 = -2

    @pytest.mark.asyncio
    async def test_eigenvalues(self, tool):
        """Test eigenvalue computation."""
        result = await tool.execute(operation="eigenvalues", matrix=[[4, -2], [1, 1]])
        assert result.success
        assert "2" in result.output or "3" in result.output  # eigenvalues

    @pytest.mark.asyncio
    async def test_solve_linear_system(self, tool):
        """Test solving linear system Ax = b."""
        result = await tool.execute(
            operation="solve", a=[[2, 1], [1, 3]], b=[4, 5]
        )
        assert result.success
        # Solution exists
        assert result.metadata.get("solution") is not None

    @pytest.mark.asyncio
    async def test_transpose(self, tool):
        """Test matrix transpose."""
        result = await tool.execute(
            operation="transpose", matrix=[[1, 2, 3], [4, 5, 6]]
        )
        assert result.success
        # Transposed should be 3x2
        assert result.metadata.get("result") is not None

    @pytest.mark.asyncio
    async def test_identity_matrix(self, tool):
        """Test identity matrix creation."""
        result = await tool.execute(operation="identity", size=[3, 3])
        assert result.success
        assert "1" in result.output
        assert "0" in result.output

    @pytest.mark.asyncio
    async def test_svd(self, tool):
        """Test SVD decomposition."""
        result = await tool.execute(operation="svd", matrix=[[1, 2], [3, 4], [5, 6]])
        assert result.success
        assert "U" in result.output
        assert "V" in result.output

    @pytest.mark.asyncio
    async def test_qr(self, tool):
        """Test QR decomposition."""
        result = await tool.execute(operation="qr", matrix=[[1, 2], [3, 4], [5, 6]])
        assert result.success
        assert "Q" in result.output
        assert "R" in result.output

    @pytest.mark.asyncio
    async def test_rank(self, tool):
        """Test matrix rank."""
        result = await tool.execute(operation="rank", matrix=[[1, 2, 3], [4, 5, 6], [7, 8, 9]])
        assert result.success
        assert "Rank" in result.output

    @pytest.mark.asyncio
    async def test_trace(self, tool):
        """Test matrix trace."""
        result = await tool.execute(operation="trace", matrix=[[1, 2], [3, 4]])
        assert result.success
        assert "5" in result.output  # trace = 1 + 4 = 5

    @pytest.mark.asyncio
    async def test_norm(self, tool):
        """Test matrix norm."""
        result = await tool.execute(operation="norm", matrix=[[1, 2], [3, 4]])
        assert result.success
        assert "Frobenius" in result.output

    @pytest.mark.asyncio
    async def test_zeros_matrix(self, tool):
        """Test zeros matrix creation."""
        result = await tool.execute(operation="zeros", size=[2, 3])
        assert result.success
        assert "0" in result.output

    @pytest.mark.asyncio
    async def test_ones_matrix(self, tool):
        """Test ones matrix creation."""
        result = await tool.execute(operation="ones", size=[2, 2])
        assert result.success
        assert "1" in result.output

    @pytest.mark.asyncio
    async def test_diagonal_matrix(self, tool):
        """Test diagonal matrix creation."""
        result = await tool.execute(operation="diagonal", diagonal_values=[1, 2, 3])
        assert result.success
        assert "1" in result.output
        assert "2" in result.output
        assert "3" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMathIntegration:
    """Integration tests for math tools and agent."""

    @pytest.mark.asyncio
    async def test_agent_registration(self):
        """Test Nidhogg agent is properly registered."""
        from sindri.agents.registry import AGENTS, get_agent

        assert "nidhogg" in AGENTS

        nidhogg = get_agent("nidhogg")
        assert nidhogg.name == "nidhogg"
        assert "math_evaluate" in nidhogg.tools
        assert "math_solve" in nidhogg.tools
        assert "stats_analyze" in nidhogg.tools
        assert "plot_generate" in nidhogg.tools
        assert "unit_convert" in nidhogg.tools
        assert "matrix_operations" in nidhogg.tools

    @pytest.mark.asyncio
    async def test_tools_registered(self):
        """Test all math tools are registered."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()

        expected_tools = [
            "math_evaluate",
            "math_solve",
            "stats_analyze",
            "plot_generate",
            "unit_convert",
            "matrix_operations",
        ]

        for tool_name in expected_tools:
            tool = registry.get_tool(tool_name)
            assert tool is not None, f"Tool {tool_name} not registered"

    @pytest.mark.asyncio
    async def test_brokkr_can_delegate_to_nidhogg(self):
        """Test Brokkr can delegate to Nidhogg."""
        from sindri.agents.registry import get_agent

        brokkr = get_agent("brokkr")
        assert "nidhogg" in brokkr.delegate_to

    @pytest.mark.asyncio
    async def test_physics_workflow(self):
        """Test a physics calculation workflow."""
        # Solve kinematic equation: v^2 = u^2 + 2as
        # Given u=0, a=9.8, s=100, find v

        eval_tool = MathEvaluateTool()
        result = await eval_tool.execute(expression="sqrt(2*9.8*100)", numeric=True)
        assert result.success
        # v ~ 44.27 m/s
        assert "44" in result.output

    @pytest.mark.asyncio
    async def test_stats_and_plot_workflow(self):
        """Test statistics + plotting workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Analyze data
            stats_tool = StatsAnalyzeTool()
            stats_result = await stats_tool.execute(
                data=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10], analysis="descriptive"
            )
            assert stats_result.success

            # Plot histogram
            plot_tool = PlotGenerateTool()
            output_file = Path(tmpdir) / "hist.png"
            plot_result = await plot_tool.execute(
                plot_type="histogram",
                data=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                output_file=str(output_file),
            )
            assert plot_result.success
            assert output_file.exists()

    @pytest.mark.asyncio
    async def test_matrix_linear_system_workflow(self):
        """Test solving linear system with verification."""
        matrix_tool = MatrixOperationsTool()

        # Solve Ax = b
        # A = [[2, 1], [1, 3]], b = [4, 5]
        solve_result = await matrix_tool.execute(
            operation="solve", a=[[2, 1], [1, 3]], b=[4, 5]
        )
        assert solve_result.success
        solution = solve_result.metadata.get("solution")
        assert solution is not None

        # Verify by multiplication: Ax should equal b
        # x ~ [1.4, 1.2]
        verify_result = await matrix_tool.execute(
            operation="multiply", a=[[2, 1], [1, 3]], b=[[solution[0]], [solution[1]]]
        )
        assert verify_result.success


# ═══════════════════════════════════════════════════════════════════════════════
# Error Handling Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestErrorHandling:
    """Test error handling for math tools."""

    @pytest.mark.asyncio
    async def test_invalid_expression(self):
        """Test error handling for invalid expression."""
        tool = MathEvaluateTool()
        result = await tool.execute(expression="2 +* 3")
        # Should either fail or handle gracefully
        assert not result.success or "error" in str(result.error or "").lower()

    @pytest.mark.asyncio
    async def test_division_by_zero(self):
        """Test division by zero handling."""
        tool = MathEvaluateTool()
        result = await tool.execute(expression="1/0")
        # Should handle gracefully (may return zoo/oo in SymPy)
        assert result.success or "error" in str(result.error).lower()

    @pytest.mark.asyncio
    async def test_singular_matrix_inverse(self):
        """Test error handling for singular matrix inverse."""
        tool = MatrixOperationsTool()
        result = await tool.execute(operation="inverse", matrix=[[1, 2], [2, 4]])
        # Singular matrix - should fail
        assert not result.success

    @pytest.mark.asyncio
    async def test_incompatible_unit_conversion(self):
        """Test error on incompatible unit conversion."""
        tool = UnitConvertTool()
        result = await tool.execute(value=100, from_unit="meter", to_unit="kilogram")
        assert not result.success or "error" in result.output.lower()

    @pytest.mark.asyncio
    async def test_missing_data_for_stats(self):
        """Test error when data is missing for stats."""
        tool = StatsAnalyzeTool()
        result = await tool.execute(analysis="descriptive")
        assert not result.success

    @pytest.mark.asyncio
    async def test_missing_matrix_for_operation(self):
        """Test error when matrix is missing."""
        tool = MatrixOperationsTool()
        result = await tool.execute(operation="inverse")
        assert not result.success
