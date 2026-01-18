"""Tests for data visualization tools (Phase 11).

Comprehensive test suite for the Saga agent's data visualization tools.
"""

import json
import pytest
import tempfile
from pathlib import Path

from sindri.tools.dataviz import (
    AnalyzeDataTool,
    SuggestVisualizationTool,
    GenerateD3Tool,
    GenerateMatplotlibTool,
    GeneratePlotlyTool,
    CreateDashboardTool,
    ExportInteractiveTool,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test Data Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_csv(tmp_path):
    """Create sample CSV file."""
    csv_content = """category,value,date,region
Electronics,1200,2024-01-01,North
Clothing,800,2024-01-02,South
Electronics,1500,2024-01-03,North
Food,400,2024-01-04,East
Clothing,950,2024-01-05,West
Food,350,2024-01-06,South
Electronics,1800,2024-01-07,East
"""
    csv_file = tmp_path / "data.csv"
    csv_file.write_text(csv_content)
    return csv_file


@pytest.fixture
def sample_json(tmp_path):
    """Create sample JSON file."""
    data = {
        "sales": [
            {"product": "A", "revenue": 1000, "units": 50},
            {"product": "B", "revenue": 1500, "units": 75},
            {"product": "C", "revenue": 800, "units": 40},
        ]
    }
    json_file = tmp_path / "data.json"
    json_file.write_text(json.dumps(data))
    return json_file


@pytest.fixture
def numeric_csv(tmp_path):
    """Create CSV with numeric data for scatter plots."""
    csv_content = """x,y,category
1,10,A
2,20,A
3,15,B
4,25,B
5,30,A
6,35,B
"""
    csv_file = tmp_path / "numeric.csv"
    csv_file.write_text(csv_content)
    return csv_file


@pytest.fixture
def time_series_csv(tmp_path):
    """Create time series CSV."""
    csv_content = """date,value
2024-01-01,100
2024-01-02,120
2024-01-03,115
2024-01-04,130
2024-01-05,125
"""
    csv_file = tmp_path / "timeseries.csv"
    csv_file.write_text(csv_content)
    return csv_file


# ═══════════════════════════════════════════════════════════════════════════════
# AnalyzeDataTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalyzeDataTool:
    """Test suite for AnalyzeDataTool."""

    @pytest.fixture
    def tool(self):
        return AnalyzeDataTool()

    @pytest.mark.asyncio
    async def test_analyze_csv(self, tool, sample_csv):
        """Test analyzing CSV file."""
        result = await tool.execute(file_path=str(sample_csv))

        assert result.success
        assert "category" in result.output
        assert "value" in result.output
        # Should include row count
        assert "7" in result.output or "Rows" in result.output

    @pytest.mark.asyncio
    async def test_analyze_json(self, tool, sample_json):
        """Test analyzing JSON file."""
        result = await tool.execute(file_path=str(sample_json))

        assert result.success
        assert "product" in result.output or "revenue" in result.output

    @pytest.mark.asyncio
    async def test_analyze_specific_columns(self, tool, sample_csv):
        """Test analyzing specific columns."""
        result = await tool.execute(
            file_path=str(sample_csv), columns=["value", "category"]
        )

        assert result.success
        assert "value" in result.output
        assert "category" in result.output

    @pytest.mark.asyncio
    async def test_analyze_inline_data(self, tool):
        """Test analyzing inline data."""
        result = await tool.execute(
            data={"x": [1, 2, 3, 4, 5], "y": [10, 20, 30, 40, 50]}
        )

        assert result.success
        assert result.metadata.get("row_count") == 5
        assert result.metadata.get("column_count") == 2

    @pytest.mark.asyncio
    async def test_analyze_with_correlation(self, tool, numeric_csv):
        """Test correlation matrix generation."""
        result = await tool.execute(
            file_path=str(numeric_csv), include_correlation=True
        )

        assert result.success
        # Should have correlation section
        assert "correlation" in result.output.lower() or "Correlation" in result.output

    @pytest.mark.asyncio
    async def test_analyze_nonexistent_file(self, tool):
        """Test error handling for nonexistent file."""
        result = await tool.execute(file_path="/nonexistent/path.csv")

        assert not result.success
        assert "not found" in result.error.lower() or "error" in result.error.lower()

    @pytest.mark.asyncio
    async def test_analyze_with_sample_size(self, tool, sample_csv):
        """Test sample size limiting."""
        result = await tool.execute(file_path=str(sample_csv), sample_size=3)

        assert result.success
        # Metadata should reflect sample
        assert result.metadata.get("row_count") == 3

    @pytest.mark.asyncio
    async def test_analyze_detects_column_types(self, tool, sample_csv):
        """Test column type detection."""
        result = await tool.execute(file_path=str(sample_csv))

        assert result.success
        # Should identify numeric type for value column
        assert "numeric" in result.output.lower()
        # Should identify categorical for category/region
        assert "categorical" in result.output.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# SuggestVisualizationTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSuggestVisualizationTool:
    """Test suite for SuggestVisualizationTool."""

    @pytest.fixture
    def tool(self):
        return SuggestVisualizationTool()

    @pytest.mark.asyncio
    async def test_suggest_for_csv(self, tool, sample_csv):
        """Test visualization suggestions for CSV."""
        result = await tool.execute(file_path=str(sample_csv))

        assert result.success
        # Should suggest chart types
        output_lower = result.output.lower()
        assert any(
            chart in output_lower
            for chart in ["bar", "line", "scatter", "pie", "histogram"]
        )

    @pytest.mark.asyncio
    async def test_suggest_with_comparison_goal(self, tool, sample_csv):
        """Test suggestions with comparison goal."""
        result = await tool.execute(file_path=str(sample_csv), goal="comparison")

        assert result.success
        assert "bar" in result.output.lower()

    @pytest.mark.asyncio
    async def test_suggest_with_trend_goal(self, tool, time_series_csv):
        """Test suggestions for time series data."""
        result = await tool.execute(file_path=str(time_series_csv), goal="trend")

        assert result.success
        assert "line" in result.output.lower()

    @pytest.mark.asyncio
    async def test_suggest_with_distribution_goal(self, tool, numeric_csv):
        """Test suggestions for distribution goal."""
        result = await tool.execute(file_path=str(numeric_csv), goal="distribution")

        assert result.success
        output_lower = result.output.lower()
        assert "histogram" in output_lower or "box" in output_lower

    @pytest.mark.asyncio
    async def test_suggest_max_suggestions(self, tool, sample_csv):
        """Test limiting number of suggestions."""
        result = await tool.execute(file_path=str(sample_csv), max_suggestions=2)

        assert result.success
        # Should have at most 2 suggestions in metadata
        assert len(result.metadata.get("suggestions", [])) <= 2

    @pytest.mark.asyncio
    async def test_suggest_inline_data(self, tool):
        """Test suggestions for inline data."""
        result = await tool.execute(data={"x": [1, 2, 3], "y": [4, 5, 6]})

        assert result.success
        # Should suggest scatter for two numeric columns
        assert "scatter" in result.output.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# GenerateD3Tool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateD3Tool:
    """Test suite for D3.js visualization generation."""

    @pytest.fixture
    def tool(self):
        return GenerateD3Tool()

    @pytest.mark.asyncio
    async def test_bar_chart(self, tool, sample_csv):
        """Test bar chart generation."""
        result = await tool.execute(
            chart_type="bar",
            file_path=str(sample_csv),
            x="category",
            y="value",
            title="Sales by Category",
        )

        assert result.success
        assert "d3" in result.output.lower()
        assert "svg" in result.output.lower()
        assert "scaleBand" in result.output or "scale" in result.output

    @pytest.mark.asyncio
    async def test_line_chart(self, tool, sample_csv):
        """Test line chart generation."""
        result = await tool.execute(
            chart_type="line", file_path=str(sample_csv), x="date", y="value"
        )

        assert result.success
        assert "line" in result.output.lower()

    @pytest.mark.asyncio
    async def test_scatter_plot(self, tool, numeric_csv):
        """Test scatter plot generation."""
        result = await tool.execute(
            chart_type="scatter", file_path=str(numeric_csv), x="x", y="y"
        )

        assert result.success
        assert "circle" in result.output.lower() or "scatter" in result.output.lower()

    @pytest.mark.asyncio
    async def test_scatter_with_color(self, tool, numeric_csv):
        """Test scatter plot with color grouping."""
        result = await tool.execute(
            chart_type="scatter",
            file_path=str(numeric_csv),
            x="x",
            y="y",
            color="category",
        )

        assert result.success
        assert "colorScale" in result.output or "color" in result.output.lower()

    @pytest.mark.asyncio
    async def test_pie_chart(self, tool, sample_csv):
        """Test pie chart generation."""
        result = await tool.execute(
            chart_type="pie", file_path=str(sample_csv), x="category", y="value"
        )

        assert result.success
        assert "arc" in result.output.lower() or "pie" in result.output.lower()

    @pytest.mark.asyncio
    async def test_histogram(self, tool, numeric_csv):
        """Test histogram generation."""
        result = await tool.execute(
            chart_type="histogram", file_path=str(numeric_csv), x="x"
        )

        assert result.success
        assert "histogram" in result.output.lower()

    @pytest.mark.asyncio
    async def test_heatmap(self, tool):
        """Test heatmap generation."""
        result = await tool.execute(
            chart_type="heatmap",
            data={
                "x": ["A", "B", "A", "B"],
                "y": ["X", "X", "Y", "Y"],
                "value": [1, 2, 3, 4],
            },
        )

        assert result.success
        assert "rect" in result.output.lower() or "heatmap" in result.output.lower()

    @pytest.mark.asyncio
    async def test_area_chart(self, tool, time_series_csv):
        """Test area chart generation."""
        result = await tool.execute(
            chart_type="area", file_path=str(time_series_csv), x="date", y="value"
        )

        assert result.success
        assert "area" in result.output.lower()

    @pytest.mark.asyncio
    async def test_output_to_file(self, tool, sample_csv):
        """Test saving D3 code to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "chart.js"

            result = await tool.execute(
                chart_type="bar",
                file_path=str(sample_csv),
                x="category",
                y="value",
                output_file=str(output_file),
            )

            assert result.success
            assert output_file.exists()
            content = output_file.read_text()
            assert "d3" in content.lower()

    @pytest.mark.asyncio
    async def test_interactive_tooltips(self, tool, sample_csv):
        """Test interactive features are included."""
        result = await tool.execute(
            chart_type="bar",
            file_path=str(sample_csv),
            x="category",
            y="value",
            interactive=True,
        )

        assert result.success
        output_lower = result.output.lower()
        assert "tooltip" in output_lower or "mouseover" in output_lower

    @pytest.mark.asyncio
    async def test_custom_dimensions(self, tool, sample_csv):
        """Test custom width and height."""
        result = await tool.execute(
            chart_type="bar",
            file_path=str(sample_csv),
            x="category",
            y="value",
            width=1000,
            height=600,
        )

        assert result.success
        assert "1000" in result.output
        assert "600" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# GenerateMatplotlibTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateMatplotlibTool:
    """Test suite for matplotlib visualization generation."""

    @pytest.fixture
    def tool(self):
        return GenerateMatplotlibTool()

    @pytest.mark.asyncio
    async def test_bar_chart(self, tool, sample_csv):
        """Test matplotlib bar chart."""
        result = await tool.execute(
            chart_type="bar", file_path=str(sample_csv), x="category", y="value"
        )

        assert result.success
        assert "matplotlib" in result.output.lower() or "plt" in result.output

    @pytest.mark.asyncio
    async def test_line_chart(self, tool, time_series_csv):
        """Test matplotlib line chart."""
        result = await tool.execute(
            chart_type="line", file_path=str(time_series_csv), x="date", y="value"
        )

        assert result.success
        assert "plot" in result.output.lower()

    @pytest.mark.asyncio
    async def test_scatter_plot(self, tool, numeric_csv):
        """Test matplotlib scatter plot."""
        result = await tool.execute(
            chart_type="scatter", file_path=str(numeric_csv), x="x", y="y"
        )

        assert result.success
        assert "scatter" in result.output.lower()

    @pytest.mark.asyncio
    async def test_histogram(self, tool, numeric_csv):
        """Test histogram generation."""
        result = await tool.execute(
            chart_type="histogram", file_path=str(numeric_csv), x="x"
        )

        assert result.success
        assert "hist" in result.output.lower()

    @pytest.mark.asyncio
    async def test_box_plot(self, tool, sample_csv):
        """Test box plot generation."""
        result = await tool.execute(
            chart_type="box", file_path=str(sample_csv), x="category", y="value"
        )

        assert result.success
        assert "boxplot" in result.output.lower() or "box" in result.output.lower()

    @pytest.mark.asyncio
    async def test_pie_chart(self, tool, sample_csv):
        """Test pie chart generation."""
        result = await tool.execute(
            chart_type="pie", file_path=str(sample_csv), x="category", y="value"
        )

        assert result.success
        assert "pie" in result.output.lower()

    @pytest.mark.asyncio
    async def test_heatmap(self, tool, numeric_csv):
        """Test heatmap generation."""
        result = await tool.execute(
            chart_type="heatmap", file_path=str(numeric_csv), x="x", y="y"
        )

        assert result.success
        assert "heatmap" in result.output.lower() or "seaborn" in result.output.lower()

    @pytest.mark.asyncio
    async def test_style_option(self, tool, sample_csv):
        """Test matplotlib style option."""
        result = await tool.execute(
            chart_type="bar",
            file_path=str(sample_csv),
            x="category",
            y="value",
            style="ggplot",
        )

        assert result.success
        assert "ggplot" in result.output

    @pytest.mark.asyncio
    async def test_with_hue(self, tool, sample_csv):
        """Test scatter plot with hue."""
        result = await tool.execute(
            chart_type="scatter",
            file_path=str(sample_csv),
            x="value",
            y="value",
            hue="category",
        )

        assert result.success
        assert "category" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# GeneratePlotlyTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGeneratePlotlyTool:
    """Test suite for Plotly visualization generation."""

    @pytest.fixture
    def tool(self):
        return GeneratePlotlyTool()

    @pytest.mark.asyncio
    async def test_scatter_python(self, tool, numeric_csv):
        """Test Plotly scatter plot (Python)."""
        result = await tool.execute(
            chart_type="scatter",
            file_path=str(numeric_csv),
            x="x",
            y="y",
            language="python",
        )

        assert result.success
        assert "plotly" in result.output.lower()
        assert "px.scatter" in result.output or "scatter" in result.output.lower()

    @pytest.mark.asyncio
    async def test_scatter_javascript(self, tool, numeric_csv):
        """Test Plotly scatter plot (JavaScript)."""
        result = await tool.execute(
            chart_type="scatter",
            file_path=str(numeric_csv),
            x="x",
            y="y",
            language="javascript",
        )

        assert result.success
        assert "Plotly" in result.output

    @pytest.mark.asyncio
    async def test_bar_chart(self, tool, sample_csv):
        """Test Plotly bar chart."""
        result = await tool.execute(
            chart_type="bar", file_path=str(sample_csv), x="category", y="value"
        )

        assert result.success
        assert "bar" in result.output.lower()

    @pytest.mark.asyncio
    async def test_line_chart(self, tool, time_series_csv):
        """Test Plotly line chart."""
        result = await tool.execute(
            chart_type="line", file_path=str(time_series_csv), x="date", y="value"
        )

        assert result.success
        assert "line" in result.output.lower()

    @pytest.mark.asyncio
    async def test_histogram(self, tool, numeric_csv):
        """Test Plotly histogram."""
        result = await tool.execute(
            chart_type="histogram", file_path=str(numeric_csv), x="x"
        )

        assert result.success
        assert "histogram" in result.output.lower()

    @pytest.mark.asyncio
    async def test_box_plot(self, tool, sample_csv):
        """Test Plotly box plot."""
        result = await tool.execute(
            chart_type="box", file_path=str(sample_csv), x="category", y="value"
        )

        assert result.success
        assert "box" in result.output.lower()

    @pytest.mark.asyncio
    async def test_3d_scatter(self, tool):
        """Test 3D scatter plot."""
        result = await tool.execute(
            chart_type="scatter_3d",
            data={"x": [1, 2, 3], "y": [4, 5, 6], "z": [7, 8, 9]},
            x="x",
            y="y",
            z="z",
        )

        assert result.success
        assert "3d" in result.output.lower() or "scatter_3d" in result.output.lower()

    @pytest.mark.asyncio
    async def test_pie_chart(self, tool, sample_csv):
        """Test Plotly pie chart."""
        result = await tool.execute(
            chart_type="pie", file_path=str(sample_csv), x="category", y="value"
        )

        assert result.success
        assert "pie" in result.output.lower()

    @pytest.mark.asyncio
    async def test_heatmap(self, tool, numeric_csv):
        """Test Plotly heatmap."""
        result = await tool.execute(
            chart_type="heatmap", file_path=str(numeric_csv), x="x", y="y"
        )

        assert result.success
        assert "heatmap" in result.output.lower() or "imshow" in result.output.lower()

    @pytest.mark.asyncio
    async def test_with_color(self, tool, numeric_csv):
        """Test chart with color parameter."""
        result = await tool.execute(
            chart_type="scatter",
            file_path=str(numeric_csv),
            x="x",
            y="y",
            color="category",
        )

        assert result.success
        assert "color" in result.output.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# CreateDashboardTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateDashboardTool:
    """Test suite for dashboard creation."""

    @pytest.fixture
    def tool(self):
        return CreateDashboardTool()

    @pytest.mark.asyncio
    async def test_basic_dashboard(self, tool, sample_csv):
        """Test basic dashboard creation."""
        result = await tool.execute(
            charts=[
                {"type": "bar", "x": "category", "y": "value", "position": [0, 0]},
                {"type": "line", "x": "date", "y": "value", "position": [0, 1]},
            ],
            file_path=str(sample_csv),
            title="Sales Dashboard",
        )

        assert result.success
        assert (
            "dashboard" in result.output.lower()
            or "grid" in result.output.lower()
            or "Plotly" in result.output
        )

    @pytest.mark.asyncio
    async def test_dashboard_html_output(self, tool, sample_csv):
        """Test dashboard HTML output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "dashboard.html"

            result = await tool.execute(
                charts=[
                    {"type": "bar", "x": "category", "y": "value", "position": [0, 0]}
                ],
                file_path=str(sample_csv),
                output_file=str(output_file),
                output_format="html",
            )

            assert result.success
            assert output_file.exists()
            content = output_file.read_text()
            assert "<html" in content.lower()

    @pytest.mark.asyncio
    async def test_dashboard_python_output(self, tool, sample_csv):
        """Test dashboard Python output."""
        result = await tool.execute(
            charts=[
                {"type": "bar", "x": "category", "y": "value", "position": [0, 0]}
            ],
            file_path=str(sample_csv),
            output_format="python",
        )

        assert result.success
        assert "matplotlib" in result.output.lower() or "plt" in result.output

    @pytest.mark.asyncio
    async def test_dashboard_with_title(self, tool, sample_csv):
        """Test dashboard with custom title."""
        result = await tool.execute(
            charts=[
                {"type": "bar", "x": "category", "y": "value", "position": [0, 0]}
            ],
            file_path=str(sample_csv),
            title="Custom Dashboard Title",
            output_format="html",
        )

        assert result.success
        assert (
            "Custom Dashboard Title" in result.output
            or "custom dashboard title" in result.output.lower()
        )

    @pytest.mark.asyncio
    async def test_dashboard_grid_size(self, tool, sample_csv):
        """Test dashboard with custom grid size."""
        result = await tool.execute(
            charts=[
                {"type": "bar", "x": "category", "y": "value", "position": [0, 0]}
            ],
            file_path=str(sample_csv),
            rows=3,
            cols=3,
            output_format="html",
        )

        assert result.success


# ═══════════════════════════════════════════════════════════════════════════════
# ExportInteractiveTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestExportInteractiveTool:
    """Test suite for standalone HTML export."""

    @pytest.fixture
    def tool(self):
        return ExportInteractiveTool()

    @pytest.mark.asyncio
    async def test_export_d3_chart(self, tool):
        """Test exporting D3 chart as HTML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "viz.html"

            chart_code = """
            const data = [1, 2, 3, 4, 5];
            d3.select("#chart").selectAll("div")
                .data(data).enter().append("div")
                .style("width", d => d * 20 + "px");
            """

            result = await tool.execute(
                chart_code=chart_code,
                library="d3",
                title="Test Chart",
                output_file=str(output_file),
            )

            assert result.success
            assert output_file.exists()
            content = output_file.read_text()
            assert "d3" in content.lower()
            assert "<html" in content.lower()

    @pytest.mark.asyncio
    async def test_export_plotly_chart(self, tool):
        """Test exporting Plotly chart as HTML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "viz.html"

            chart_code = """
            Plotly.newPlot('chart', [{x: [1,2,3], y: [4,5,6], type: 'scatter'}]);
            """

            result = await tool.execute(
                chart_code=chart_code,
                library="plotly",
                title="Plotly Test",
                output_file=str(output_file),
            )

            assert result.success
            assert output_file.exists()
            content = output_file.read_text()
            assert "plotly" in content.lower()

    @pytest.mark.asyncio
    async def test_export_with_embedded_data(self, tool):
        """Test export with embedded data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "viz.html"

            result = await tool.execute(
                chart_code="console.log(embeddedData);",
                data={"values": [1, 2, 3]},
                library="d3",
                output_file=str(output_file),
            )

            assert result.success
            content = output_file.read_text()
            assert "embeddedData" in content
            assert "values" in content

    @pytest.mark.asyncio
    async def test_responsive_export(self, tool):
        """Test responsive chart export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "viz.html"

            result = await tool.execute(
                chart_code="// chart code",
                library="d3",
                responsive=True,
                output_file=str(output_file),
            )

            assert result.success
            content = output_file.read_text()
            assert "width" in content.lower()

    @pytest.mark.asyncio
    async def test_export_button(self, tool):
        """Test export button inclusion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "viz.html"

            result = await tool.execute(
                chart_code="// chart",
                library="d3",
                include_export_button=True,
                output_file=str(output_file),
            )

            assert result.success
            content = output_file.read_text()
            assert "export" in content.lower()

    @pytest.mark.asyncio
    async def test_export_from_file(self, tool, tmp_path):
        """Test export from existing JS file."""
        # Create a JS file
        js_file = tmp_path / "chart.js"
        js_file.write_text("const chart = d3.select('#chart');")

        output_file = tmp_path / "viz.html"

        result = await tool.execute(
            file_path=str(js_file), library="d3", output_file=str(output_file)
        )

        assert result.success
        assert output_file.exists()


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDataVizIntegration:
    """Integration tests for data visualization workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, sample_csv):
        """Test complete visualization workflow."""
        # 1. Analyze data
        analyze = AnalyzeDataTool()
        analysis = await analyze.execute(file_path=str(sample_csv))
        assert analysis.success

        # 2. Get suggestions
        suggest = SuggestVisualizationTool()
        suggestions = await suggest.execute(file_path=str(sample_csv))
        assert suggestions.success

        # 3. Generate visualization
        d3_tool = GenerateD3Tool()
        viz = await d3_tool.execute(
            chart_type="bar", file_path=str(sample_csv), x="category", y="value"
        )
        assert viz.success

    @pytest.mark.asyncio
    async def test_agent_registration(self):
        """Test Saga agent is properly registered."""
        from sindri.agents.registry import AGENTS, get_agent

        assert "saga" in AGENTS

        saga = get_agent("saga")
        assert saga.name == "saga"
        assert "analyze_data" in saga.tools
        assert "generate_d3" in saga.tools
        assert "generate_matplotlib" in saga.tools
        assert "generate_plotly" in saga.tools

    @pytest.mark.asyncio
    async def test_tools_registered(self):
        """Test all dataviz tools are registered."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()

        expected_tools = [
            "analyze_data",
            "suggest_viz",
            "generate_d3",
            "generate_matplotlib",
            "generate_plotly",
            "create_dashboard",
            "export_interactive",
        ]

        for tool_name in expected_tools:
            tool = registry.get_tool(tool_name)
            assert tool is not None, f"Tool {tool_name} not registered"

    @pytest.mark.asyncio
    async def test_brokkr_can_delegate_to_saga(self):
        """Test Brokkr can delegate to Saga."""
        from sindri.agents.registry import get_agent

        brokkr = get_agent("brokkr")
        assert brokkr.can_delegate_to("saga")

    @pytest.mark.asyncio
    async def test_generate_and_export_workflow(self, sample_csv):
        """Test generating and exporting a visualization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Generate D3 chart
            d3_tool = GenerateD3Tool()
            d3_result = await d3_tool.execute(
                chart_type="bar",
                file_path=str(sample_csv),
                x="category",
                y="value",
            )
            assert d3_result.success

            # Export as HTML
            export_tool = ExportInteractiveTool()
            output_file = Path(tmpdir) / "final.html"

            # Extract just the JS code from the output
            chart_code = d3_result.output.replace("```javascript", "").replace(
                "```", ""
            )

            export_result = await export_tool.execute(
                chart_code=chart_code,
                library="d3",
                title="Final Chart",
                output_file=str(output_file),
            )

            assert export_result.success
            assert output_file.exists()
