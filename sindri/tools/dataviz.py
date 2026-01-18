"""Data visualization tools for Sindri (Phase 11).

Provides tools for analyzing data and generating visualizations using
D3.js, matplotlib, and Plotly.
"""

import csv
import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_data_file(file_path: Path) -> tuple[list[dict], list[str]]:
    """Parse CSV or JSON file and return list of records and column names."""
    suffix = file_path.suffix.lower()

    if suffix == ".csv":
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            records = list(reader)
            columns = reader.fieldnames or []
        return records, list(columns)

    elif suffix == ".json":
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        # Handle different JSON structures
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            # Look for array values
            for key, value in data.items():
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    records = value
                    break
            else:
                # Single object - wrap in list
                records = [data]
        else:
            records = []

        columns = list(records[0].keys()) if records else []
        return records, columns

    else:
        raise ValueError(f"Unsupported file format: {suffix}")


def _detect_column_type(values: list[Any]) -> str:
    """Detect the type of a column based on its values."""
    non_null = [v for v in values if v is not None and v != ""]

    if not non_null:
        return "empty"

    # Try numeric
    numeric_count = 0
    for v in non_null:
        try:
            float(v)
            numeric_count += 1
        except (ValueError, TypeError):
            pass

    if numeric_count == len(non_null):
        return "numeric"

    # Try datetime
    date_formats = ["%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"]
    for fmt in date_formats:
        date_count = 0
        for v in non_null:
            try:
                datetime.strptime(str(v), fmt)
                date_count += 1
            except ValueError:
                break
        if date_count == len(non_null):
            return "datetime"

    # Check if categorical (few unique values relative to total)
    unique_ratio = len(set(non_null)) / len(non_null)
    if unique_ratio < 0.5:
        return "categorical"

    return "text"


def _compute_numeric_stats(values: list[float]) -> dict:
    """Compute statistics for numeric values."""
    if not values:
        return {}

    return {
        "count": len(values),
        "mean": round(statistics.mean(values), 4),
        "median": round(statistics.median(values), 4),
        "std": round(statistics.stdev(values), 4) if len(values) > 1 else 0,
        "min": min(values),
        "max": max(values),
    }


def _compute_correlation(col1: list[float], col2: list[float]) -> float:
    """Compute Pearson correlation coefficient."""
    n = len(col1)
    if n < 2:
        return 0.0

    mean1 = statistics.mean(col1)
    mean2 = statistics.mean(col2)

    numerator = sum((x - mean1) * (y - mean2) for x, y in zip(col1, col2))
    denom1 = sum((x - mean1) ** 2 for x in col1) ** 0.5
    denom2 = sum((y - mean2) ** 2 for y in col2) ** 0.5

    if denom1 == 0 or denom2 == 0:
        return 0.0

    return round(numerator / (denom1 * denom2), 4)


# ═══════════════════════════════════════════════════════════════════════════════
# AnalyzeDataTool
# ═══════════════════════════════════════════════════════════════════════════════


class AnalyzeDataTool(Tool):
    """Analyze dataset structure and compute statistics."""

    name = "analyze_data"
    description = """Analyze a dataset to understand its structure and statistics.

Supports CSV and JSON files. Computes:
- Column names and detected types (numeric, categorical, datetime, text)
- Basic statistics for numeric columns (count, mean, median, std, min, max)
- Missing value counts per column
- Unique value counts per column
- Correlation matrix for numeric columns (optional)

Examples:
- analyze_data(file_path="data.csv")
- analyze_data(file_path="sales.json", columns=["revenue", "date"])
- analyze_data(data={"x": [1,2,3], "y": [4,5,6]}, include_correlation=True)"""

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to CSV or JSON file to analyze",
            },
            "data": {
                "type": "object",
                "description": "Inline data as dict of arrays (alternative to file_path)",
            },
            "columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific columns to analyze (optional, default: all)",
            },
            "include_correlation": {
                "type": "boolean",
                "description": "Include correlation matrix for numeric columns (default: true)",
            },
            "sample_size": {
                "type": "integer",
                "description": "Limit analysis to first N rows (default: all)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        file_path: Optional[str] = None,
        data: Optional[dict] = None,
        columns: Optional[list[str]] = None,
        include_correlation: bool = True,
        sample_size: Optional[int] = None,
        **kwargs,
    ) -> ToolResult:
        """Analyze dataset and return statistics."""
        try:
            # Load data
            if file_path:
                path = self._resolve_path(file_path)
                if not path.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"File not found: {file_path}",
                    )
                records, all_columns = _parse_data_file(path)
            elif data:
                # Convert dict of arrays to list of dicts
                if data and isinstance(next(iter(data.values())), list):
                    all_columns = list(data.keys())
                    n = len(next(iter(data.values())))
                    records = [{col: data[col][i] for col in all_columns} for i in range(n)]
                else:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Data must be a dict of arrays",
                    )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error="Either file_path or data must be provided",
                )

            if not records:
                return ToolResult(
                    success=False,
                    output="",
                    error="No data found in file",
                )

            # Apply sample size
            if sample_size and sample_size < len(records):
                records = records[:sample_size]

            # Filter columns if specified
            analyze_columns = columns if columns else all_columns

            # Analyze each column
            analysis = {
                "row_count": len(records),
                "column_count": len(analyze_columns),
                "columns": {},
            }

            numeric_columns = []

            for col in analyze_columns:
                if col not in all_columns:
                    continue

                values = [r.get(col) for r in records]
                col_type = _detect_column_type(values)

                col_info = {
                    "type": col_type,
                    "missing": sum(1 for v in values if v is None or v == ""),
                    "unique": len(set(v for v in values if v is not None and v != "")),
                }

                if col_type == "numeric":
                    numeric_values = []
                    for v in values:
                        try:
                            numeric_values.append(float(v))
                        except (ValueError, TypeError):
                            pass
                    col_info["statistics"] = _compute_numeric_stats(numeric_values)
                    numeric_columns.append((col, numeric_values))

                elif col_type == "categorical":
                    # Show top categories
                    from collections import Counter

                    counts = Counter(v for v in values if v is not None and v != "")
                    col_info["top_values"] = dict(counts.most_common(5))

                analysis["columns"][col] = col_info

            # Compute correlation matrix
            if include_correlation and len(numeric_columns) > 1:
                correlation = {}
                for i, (col1, vals1) in enumerate(numeric_columns):
                    correlation[col1] = {}
                    for col2, vals2 in numeric_columns:
                        # Align values (handle missing)
                        paired = [
                            (v1, v2)
                            for v1, v2 in zip(vals1, vals2)
                            if v1 is not None and v2 is not None
                        ]
                        if paired:
                            c1, c2 = zip(*paired)
                            correlation[col1][col2] = _compute_correlation(list(c1), list(c2))
                analysis["correlation"] = correlation

            # Format output
            output_lines = [
                "# Data Analysis Results",
                "",
                f"**Rows:** {analysis['row_count']}",
                f"**Columns:** {analysis['column_count']}",
                "",
                "## Column Details",
                "",
            ]

            for col, info in analysis["columns"].items():
                output_lines.append(f"### {col}")
                output_lines.append(f"- Type: {info['type']}")
                output_lines.append(f"- Missing: {info['missing']}")
                output_lines.append(f"- Unique: {info['unique']}")

                if "statistics" in info:
                    stats = info["statistics"]
                    output_lines.append(
                        f"- Statistics: mean={stats['mean']}, median={stats['median']}, "
                        f"std={stats['std']}, min={stats['min']}, max={stats['max']}"
                    )

                if "top_values" in info:
                    top = ", ".join(f"{k}({v})" for k, v in info["top_values"].items())
                    output_lines.append(f"- Top values: {top}")

                output_lines.append("")

            if "correlation" in analysis:
                output_lines.append("## Correlation Matrix")
                output_lines.append("")
                cols = list(analysis["correlation"].keys())
                output_lines.append("| | " + " | ".join(cols) + " |")
                output_lines.append("|" + "---|" * (len(cols) + 1))
                for col in cols:
                    row = [f"{analysis['correlation'][col].get(c, '')}" for c in cols]
                    output_lines.append(f"| {col} | " + " | ".join(row) + " |")

            log.info("data_analyzed", rows=analysis["row_count"], columns=analysis["column_count"])

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "row_count": analysis["row_count"],
                    "column_count": analysis["column_count"],
                    "columns": list(analysis["columns"].keys()),
                },
            )

        except Exception as e:
            log.error("data_analysis_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to analyze data: {str(e)}",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# SuggestVisualizationTool
# ═══════════════════════════════════════════════════════════════════════════════


class SuggestVisualizationTool(Tool):
    """Recommend appropriate chart types based on data characteristics."""

    name = "suggest_viz"
    description = """Suggest appropriate visualization types for a dataset.

Analyzes data structure and recommends:
- Chart type (bar, line, scatter, pie, heatmap, histogram, box, etc.)
- Suitable columns for each axis
- Grouping/coloring options
- Rationale for each suggestion

Examples:
- suggest_viz(file_path="sales.csv")
- suggest_viz(data={"date": [...], "revenue": [...]})
- suggest_viz(file_path="data.csv", goal="trend")"""

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to CSV or JSON file",
            },
            "data": {
                "type": "object",
                "description": "Inline data as dict of arrays",
            },
            "goal": {
                "type": "string",
                "enum": ["comparison", "distribution", "relationship", "trend", "composition"],
                "description": "Visualization goal to focus recommendations",
            },
            "max_suggestions": {
                "type": "integer",
                "description": "Maximum number of suggestions (default: 5)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        file_path: Optional[str] = None,
        data: Optional[dict] = None,
        goal: Optional[str] = None,
        max_suggestions: int = 5,
        **kwargs,
    ) -> ToolResult:
        """Suggest visualizations based on data analysis."""
        try:
            # Load and analyze data
            if file_path:
                path = self._resolve_path(file_path)
                if not path.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"File not found: {file_path}",
                    )
                records, columns = _parse_data_file(path)
            elif data:
                columns = list(data.keys())
                n = len(next(iter(data.values())))
                records = [{col: data[col][i] for col in columns} for i in range(n)]
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error="Either file_path or data must be provided",
                )

            if not records:
                return ToolResult(
                    success=False,
                    output="",
                    error="No data found",
                )

            # Classify columns by type
            numeric_cols = []
            categorical_cols = []
            datetime_cols = []

            for col in columns:
                values = [r.get(col) for r in records]
                col_type = _detect_column_type(values)

                if col_type == "numeric":
                    numeric_cols.append(col)
                elif col_type == "categorical":
                    categorical_cols.append(col)
                elif col_type == "datetime":
                    datetime_cols.append(col)

            # Generate suggestions
            suggestions = []

            # Distribution visualizations
            if not goal or goal == "distribution":
                for col in numeric_cols[:2]:
                    suggestions.append({
                        "chart": "histogram",
                        "x": col,
                        "rationale": f"Show distribution of {col}",
                        "goal": "distribution",
                    })

                if len(numeric_cols) >= 1 and categorical_cols:
                    suggestions.append({
                        "chart": "box",
                        "x": categorical_cols[0],
                        "y": numeric_cols[0],
                        "rationale": f"Compare {numeric_cols[0]} distribution across {categorical_cols[0]}",
                        "goal": "distribution",
                    })

            # Comparison visualizations
            if not goal or goal == "comparison":
                if categorical_cols and numeric_cols:
                    suggestions.append({
                        "chart": "bar",
                        "x": categorical_cols[0],
                        "y": numeric_cols[0],
                        "rationale": f"Compare {numeric_cols[0]} across {categorical_cols[0]} categories",
                        "goal": "comparison",
                    })

            # Trend visualizations
            if not goal or goal == "trend":
                if datetime_cols and numeric_cols:
                    suggestions.append({
                        "chart": "line",
                        "x": datetime_cols[0],
                        "y": numeric_cols[0],
                        "rationale": f"Show {numeric_cols[0]} trend over time",
                        "goal": "trend",
                    })

            # Relationship visualizations
            if not goal or goal == "relationship":
                if len(numeric_cols) >= 2:
                    suggestions.append({
                        "chart": "scatter",
                        "x": numeric_cols[0],
                        "y": numeric_cols[1],
                        "color": categorical_cols[0] if categorical_cols else None,
                        "rationale": f"Explore relationship between {numeric_cols[0]} and {numeric_cols[1]}",
                        "goal": "relationship",
                    })

                if len(numeric_cols) >= 3:
                    suggestions.append({
                        "chart": "heatmap",
                        "rationale": "Show correlation between numeric variables",
                        "goal": "relationship",
                    })

            # Composition visualizations
            if not goal or goal == "composition":
                if categorical_cols and numeric_cols:
                    unique_cats = len(set(r.get(categorical_cols[0]) for r in records))
                    if unique_cats <= 6:
                        suggestions.append({
                            "chart": "pie",
                            "labels": categorical_cols[0],
                            "values": numeric_cols[0],
                            "rationale": f"Show {numeric_cols[0]} composition by {categorical_cols[0]}",
                            "goal": "composition",
                        })

            # Limit suggestions
            suggestions = suggestions[:max_suggestions]

            # Format output
            output_lines = [
                "# Visualization Suggestions",
                "",
                f"**Data Summary:** {len(records)} rows, {len(columns)} columns",
                f"- Numeric: {', '.join(numeric_cols) if numeric_cols else 'none'}",
                f"- Categorical: {', '.join(categorical_cols) if categorical_cols else 'none'}",
                f"- Datetime: {', '.join(datetime_cols) if datetime_cols else 'none'}",
                "",
                "## Recommended Visualizations",
                "",
            ]

            for i, sug in enumerate(suggestions, 1):
                output_lines.append(f"### {i}. {sug['chart'].title()} Chart")
                output_lines.append(f"- **Goal:** {sug['goal']}")
                if "x" in sug:
                    output_lines.append(f"- **X-axis:** {sug['x']}")
                if "y" in sug:
                    output_lines.append(f"- **Y-axis:** {sug['y']}")
                if sug.get("color"):
                    output_lines.append(f"- **Color by:** {sug['color']}")
                if sug.get("labels"):
                    output_lines.append(f"- **Labels:** {sug['labels']}")
                if sug.get("values"):
                    output_lines.append(f"- **Values:** {sug['values']}")
                output_lines.append(f"- **Rationale:** {sug['rationale']}")
                output_lines.append("")

            log.info("viz_suggestions_generated", count=len(suggestions))

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "suggestions": suggestions,
                    "numeric_columns": numeric_cols,
                    "categorical_columns": categorical_cols,
                    "datetime_columns": datetime_cols,
                },
            )

        except Exception as e:
            log.error("viz_suggestion_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to suggest visualizations: {str(e)}",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# GenerateD3Tool
# ═══════════════════════════════════════════════════════════════════════════════


class GenerateD3Tool(Tool):
    """Generate D3.js interactive visualization code."""

    name = "generate_d3"
    description = """Generate D3.js code for interactive visualizations.

Supported chart types:
- bar: Vertical bar chart
- line: Line chart (for time series)
- scatter: Scatter plot
- pie: Pie/donut chart
- heatmap: Heat map
- histogram: Histogram
- area: Area chart

Features:
- Interactive tooltips on hover
- Smooth transitions/animations
- Responsive sizing option
- Customizable colors and dimensions

Examples:
- generate_d3(chart_type="bar", file_path="sales.csv", x="category", y="revenue")
- generate_d3(chart_type="line", data={"x": [...], "y": [...]}, title="Trends")
- generate_d3(chart_type="scatter", file_path="data.csv", x="x", y="y", color="category")"""

    parameters = {
        "type": "object",
        "properties": {
            "chart_type": {
                "type": "string",
                "enum": ["bar", "line", "scatter", "pie", "heatmap", "histogram", "area"],
                "description": "Type of chart to generate",
            },
            "file_path": {
                "type": "string",
                "description": "Path to data file (CSV or JSON)",
            },
            "data": {
                "type": "object",
                "description": "Inline data as dict of arrays",
            },
            "x": {
                "type": "string",
                "description": "Column for x-axis",
            },
            "y": {
                "type": "string",
                "description": "Column for y-axis",
            },
            "color": {
                "type": "string",
                "description": "Column for color grouping",
            },
            "title": {
                "type": "string",
                "description": "Chart title",
            },
            "width": {
                "type": "integer",
                "description": "Chart width in pixels (default: 800)",
            },
            "height": {
                "type": "integer",
                "description": "Chart height in pixels (default: 500)",
            },
            "interactive": {
                "type": "boolean",
                "description": "Include tooltips and hover effects (default: true)",
            },
            "output_file": {
                "type": "string",
                "description": "Save generated code to file",
            },
        },
        "required": ["chart_type"],
    }

    async def execute(
        self,
        chart_type: str,
        file_path: Optional[str] = None,
        data: Optional[dict] = None,
        x: Optional[str] = None,
        y: Optional[str] = None,
        color: Optional[str] = None,
        title: Optional[str] = None,
        width: int = 800,
        height: int = 500,
        interactive: bool = True,
        output_file: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Generate D3.js visualization code."""
        try:
            # Load data
            if file_path:
                path = self._resolve_path(file_path)
                if not path.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"File not found: {file_path}",
                    )
                records, columns = _parse_data_file(path)
            elif data:
                columns = list(data.keys())
                n = len(next(iter(data.values())))
                records = [{col: data[col][i] for col in columns} for i in range(n)]
            else:
                # Generate with placeholder data
                records = []
                columns = []

            # Generate chart code based on type
            if chart_type == "bar":
                code = self._generate_bar(records, x, y, title, width, height, interactive)
            elif chart_type == "line":
                code = self._generate_line(records, x, y, title, width, height, interactive)
            elif chart_type == "scatter":
                code = self._generate_scatter(records, x, y, color, title, width, height, interactive)
            elif chart_type == "pie":
                code = self._generate_pie(records, x, y, title, width, height, interactive)
            elif chart_type == "histogram":
                code = self._generate_histogram(records, x, title, width, height, interactive)
            elif chart_type == "heatmap":
                code = self._generate_heatmap(records, x, y, title, width, height)
            elif chart_type == "area":
                code = self._generate_area(records, x, y, title, width, height, interactive)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported chart type: {chart_type}",
                )

            # Save to file if requested
            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(code)

                log.info("d3_chart_saved", chart_type=chart_type, file=str(out_path))

                return ToolResult(
                    success=True,
                    output=f"D3.js {chart_type} chart saved to {out_path}\n\n```javascript\n{code}\n```",
                    metadata={
                        "chart_type": chart_type,
                        "output_file": str(out_path),
                        "library": "d3",
                    },
                )

            log.info("d3_chart_generated", chart_type=chart_type)

            return ToolResult(
                success=True,
                output=f"```javascript\n{code}\n```",
                metadata={
                    "chart_type": chart_type,
                    "library": "d3",
                },
            )

        except Exception as e:
            log.error("d3_generation_failed", error=str(e), chart_type=chart_type)
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate D3.js chart: {str(e)}",
            )

    def _generate_bar(
        self, records: list, x: str, y: str, title: str, width: int, height: int, interactive: bool
    ) -> str:
        """Generate D3.js bar chart code."""
        data_json = json.dumps(records, indent=2) if records else "[]"
        title_str = title or "Bar Chart"

        tooltip_code = ""
        if interactive:
            tooltip_code = f'''
// Tooltip
const tooltip = d3.select("body").append("div")
    .attr("class", "tooltip")
    .style("position", "absolute")
    .style("padding", "8px")
    .style("background", "rgba(0,0,0,0.7)")
    .style("color", "#fff")
    .style("border-radius", "4px")
    .style("font-size", "12px")
    .style("pointer-events", "none")
    .style("opacity", 0);

bars.on("mouseover", function(event, d) {{
        tooltip.transition().duration(200).style("opacity", 0.9);
        tooltip.html(`{x}: ${{d.{x}}}<br/>{y}: ${{d.{y}}}`)
            .style("left", (event.pageX + 10) + "px")
            .style("top", (event.pageY - 28) + "px");
        d3.select(this).style("opacity", 0.8);
    }})
    .on("mouseout", function() {{
        tooltip.transition().duration(500).style("opacity", 0);
        d3.select(this).style("opacity", 1);
    }});
'''

        return f'''// D3.js Bar Chart
const margin = {{top: 40, right: 30, bottom: 60, left: 60}};
const width = {width} - margin.left - margin.right;
const height = {height} - margin.top - margin.bottom;

const svg = d3.select("#chart")
    .append("svg")
    .attr("width", width + margin.left + margin.right)
    .attr("height", height + margin.top + margin.bottom)
    .append("g")
    .attr("transform", `translate(${{margin.left}},${{margin.top}})`);

const data = {data_json};

// Scales
const x = d3.scaleBand()
    .domain(data.map(d => d.{x}))
    .range([0, width])
    .padding(0.2);

const y = d3.scaleLinear()
    .domain([0, d3.max(data, d => +d.{y})])
    .nice()
    .range([height, 0]);

// Axes
svg.append("g")
    .attr("transform", `translate(0,${{height}})`)
    .call(d3.axisBottom(x))
    .selectAll("text")
    .attr("transform", "rotate(-45)")
    .style("text-anchor", "end");

svg.append("g")
    .call(d3.axisLeft(y));

// Bars
const bars = svg.selectAll(".bar")
    .data(data)
    .enter()
    .append("rect")
    .attr("class", "bar")
    .attr("x", d => x(d.{x}))
    .attr("width", x.bandwidth())
    .attr("y", height)
    .attr("height", 0)
    .attr("fill", "steelblue");

// Animation
bars.transition()
    .duration(750)
    .attr("y", d => y(+d.{y}))
    .attr("height", d => height - y(+d.{y}));

// Title
svg.append("text")
    .attr("x", width / 2)
    .attr("y", -10)
    .attr("text-anchor", "middle")
    .style("font-size", "16px")
    .style("font-weight", "bold")
    .text("{title_str}");
{tooltip_code}'''

    def _generate_line(
        self, records: list, x: str, y: str, title: str, width: int, height: int, interactive: bool
    ) -> str:
        """Generate D3.js line chart code."""
        data_json = json.dumps(records, indent=2) if records else "[]"
        title_str = title or "Line Chart"

        tooltip_code = ""
        if interactive:
            tooltip_code = f'''
// Tooltip and interaction
const tooltip = d3.select("body").append("div")
    .attr("class", "tooltip")
    .style("position", "absolute")
    .style("padding", "8px")
    .style("background", "rgba(0,0,0,0.7)")
    .style("color", "#fff")
    .style("border-radius", "4px")
    .style("pointer-events", "none")
    .style("opacity", 0);

// Add dots for interaction
svg.selectAll(".dot")
    .data(data)
    .enter()
    .append("circle")
    .attr("class", "dot")
    .attr("cx", d => xScale(d.{x}))
    .attr("cy", d => yScale(+d.{y}))
    .attr("r", 4)
    .attr("fill", "steelblue")
    .on("mouseover", function(event, d) {{
        tooltip.transition().duration(200).style("opacity", 0.9);
        tooltip.html(`{x}: ${{d.{x}}}<br/>{y}: ${{d.{y}}}`)
            .style("left", (event.pageX + 10) + "px")
            .style("top", (event.pageY - 28) + "px");
        d3.select(this).attr("r", 6);
    }})
    .on("mouseout", function() {{
        tooltip.transition().duration(500).style("opacity", 0);
        d3.select(this).attr("r", 4);
    }});
'''

        return f'''// D3.js Line Chart
const margin = {{top: 40, right: 30, bottom: 60, left: 60}};
const width = {width} - margin.left - margin.right;
const height = {height} - margin.top - margin.bottom;

const svg = d3.select("#chart")
    .append("svg")
    .attr("width", width + margin.left + margin.right)
    .attr("height", height + margin.top + margin.bottom)
    .append("g")
    .attr("transform", `translate(${{margin.left}},${{margin.top}})`);

const data = {data_json};

// Scales
const xScale = d3.scalePoint()
    .domain(data.map(d => d.{x}))
    .range([0, width]);

const yScale = d3.scaleLinear()
    .domain([0, d3.max(data, d => +d.{y})])
    .nice()
    .range([height, 0]);

// Axes
svg.append("g")
    .attr("transform", `translate(0,${{height}})`)
    .call(d3.axisBottom(xScale))
    .selectAll("text")
    .attr("transform", "rotate(-45)")
    .style("text-anchor", "end");

svg.append("g")
    .call(d3.axisLeft(yScale));

// Line
const line = d3.line()
    .x(d => xScale(d.{x}))
    .y(d => yScale(+d.{y}));

svg.append("path")
    .datum(data)
    .attr("fill", "none")
    .attr("stroke", "steelblue")
    .attr("stroke-width", 2)
    .attr("d", line);

// Title
svg.append("text")
    .attr("x", width / 2)
    .attr("y", -10)
    .attr("text-anchor", "middle")
    .style("font-size", "16px")
    .style("font-weight", "bold")
    .text("{title_str}");
{tooltip_code}'''

    def _generate_scatter(
        self, records: list, x: str, y: str, color: str, title: str, width: int, height: int, interactive: bool
    ) -> str:
        """Generate D3.js scatter plot code."""
        data_json = json.dumps(records, indent=2) if records else "[]"
        title_str = title or "Scatter Plot"

        color_code = 'const color = "steelblue";'
        fill_code = "color"
        if color:
            color_code = f'''const colorScale = d3.scaleOrdinal(d3.schemeCategory10)
    .domain([...new Set(data.map(d => d.{color}))]);'''
            fill_code = f"colorScale(d.{color})"

        tooltip_code = ""
        if interactive:
            tooltip_html = f'{x}: ${{d.{x}}}<br/>{y}: ${{d.{y}}}'
            if color:
                tooltip_html += f'<br/>{color}: ${{d.{color}}}'
            tooltip_code = f'''
// Tooltip
const tooltip = d3.select("body").append("div")
    .attr("class", "tooltip")
    .style("position", "absolute")
    .style("padding", "8px")
    .style("background", "rgba(0,0,0,0.7)")
    .style("color", "#fff")
    .style("border-radius", "4px")
    .style("pointer-events", "none")
    .style("opacity", 0);

circles.on("mouseover", function(event, d) {{
        tooltip.transition().duration(200).style("opacity", 0.9);
        tooltip.html(`{tooltip_html}`)
            .style("left", (event.pageX + 10) + "px")
            .style("top", (event.pageY - 28) + "px");
        d3.select(this).attr("r", 8).style("opacity", 1);
    }})
    .on("mouseout", function() {{
        tooltip.transition().duration(500).style("opacity", 0);
        d3.select(this).attr("r", 5).style("opacity", 0.7);
    }});
'''

        return f'''// D3.js Scatter Plot
const margin = {{top: 40, right: 30, bottom: 60, left: 60}};
const width = {width} - margin.left - margin.right;
const height = {height} - margin.top - margin.bottom;

const svg = d3.select("#chart")
    .append("svg")
    .attr("width", width + margin.left + margin.right)
    .attr("height", height + margin.top + margin.bottom)
    .append("g")
    .attr("transform", `translate(${{margin.left}},${{margin.top}})`);

const data = {data_json};

{color_code}

// Scales
const xScale = d3.scaleLinear()
    .domain(d3.extent(data, d => +d.{x}))
    .nice()
    .range([0, width]);

const yScale = d3.scaleLinear()
    .domain(d3.extent(data, d => +d.{y}))
    .nice()
    .range([height, 0]);

// Axes
svg.append("g")
    .attr("transform", `translate(0,${{height}})`)
    .call(d3.axisBottom(xScale));

svg.append("g")
    .call(d3.axisLeft(yScale));

// Points
const circles = svg.selectAll("circle")
    .data(data)
    .enter()
    .append("circle")
    .attr("cx", d => xScale(+d.{x}))
    .attr("cy", d => yScale(+d.{y}))
    .attr("r", 5)
    .attr("fill", d => {fill_code})
    .style("opacity", 0.7);

// Title
svg.append("text")
    .attr("x", width / 2)
    .attr("y", -10)
    .attr("text-anchor", "middle")
    .style("font-size", "16px")
    .style("font-weight", "bold")
    .text("{title_str}");
{tooltip_code}'''

    def _generate_pie(
        self, records: list, labels: str, values: str, title: str, width: int, height: int, interactive: bool
    ) -> str:
        """Generate D3.js pie chart code."""
        data_json = json.dumps(records, indent=2) if records else "[]"
        title_str = title or "Pie Chart"
        labels = labels or "label"
        values = values or "value"

        tooltip_code = ""
        if interactive:
            tooltip_code = f'''
// Tooltip
const tooltip = d3.select("body").append("div")
    .attr("class", "tooltip")
    .style("position", "absolute")
    .style("padding", "8px")
    .style("background", "rgba(0,0,0,0.7)")
    .style("color", "#fff")
    .style("border-radius", "4px")
    .style("pointer-events", "none")
    .style("opacity", 0);

arcs.on("mouseover", function(event, d) {{
        tooltip.transition().duration(200).style("opacity", 0.9);
        const percent = ((d.endAngle - d.startAngle) / (2 * Math.PI) * 100).toFixed(1);
        tooltip.html(`${{d.data.{labels}}}: ${{d.data.{values}}} (${{percent}}%)`)
            .style("left", (event.pageX + 10) + "px")
            .style("top", (event.pageY - 28) + "px");
        d3.select(this).style("opacity", 0.8);
    }})
    .on("mouseout", function() {{
        tooltip.transition().duration(500).style("opacity", 0);
        d3.select(this).style("opacity", 1);
    }});
'''

        return f'''// D3.js Pie Chart
const width = {width};
const height = {height};
const radius = Math.min(width, height) / 2 - 40;

const svg = d3.select("#chart")
    .append("svg")
    .attr("width", width)
    .attr("height", height)
    .append("g")
    .attr("transform", `translate(${{width / 2}},${{height / 2}})`);

const data = {data_json};

const color = d3.scaleOrdinal(d3.schemeCategory10);

const pie = d3.pie()
    .value(d => +d.{values})
    .sort(null);

const arc = d3.arc()
    .innerRadius(0)
    .outerRadius(radius);

const arcs = svg.selectAll("arc")
    .data(pie(data))
    .enter()
    .append("g");

arcs.append("path")
    .attr("d", arc)
    .attr("fill", (d, i) => color(i))
    .attr("stroke", "white")
    .style("stroke-width", "2px");

// Labels
arcs.append("text")
    .attr("transform", d => `translate(${{arc.centroid(d)}})`)
    .attr("text-anchor", "middle")
    .style("font-size", "12px")
    .text(d => d.data.{labels});

// Title
svg.append("text")
    .attr("y", -height/2 + 20)
    .attr("text-anchor", "middle")
    .style("font-size", "16px")
    .style("font-weight", "bold")
    .text("{title_str}");
{tooltip_code}'''

    def _generate_histogram(
        self, records: list, x: str, title: str, width: int, height: int, interactive: bool
    ) -> str:
        """Generate D3.js histogram code."""
        data_json = json.dumps(records, indent=2) if records else "[]"
        title_str = title or "Histogram"

        tooltip_code = ""
        if interactive:
            tooltip_code = '''
// Tooltip
const tooltip = d3.select("body").append("div")
    .attr("class", "tooltip")
    .style("position", "absolute")
    .style("padding", "8px")
    .style("background", "rgba(0,0,0,0.7)")
    .style("color", "#fff")
    .style("border-radius", "4px")
    .style("pointer-events", "none")
    .style("opacity", 0);

bars.on("mouseover", function(event, d) {
        tooltip.transition().duration(200).style("opacity", 0.9);
        tooltip.html(`Range: ${d.x0.toFixed(1)} - ${d.x1.toFixed(1)}<br/>Count: ${d.length}`)
            .style("left", (event.pageX + 10) + "px")
            .style("top", (event.pageY - 28) + "px");
        d3.select(this).style("opacity", 0.8);
    })
    .on("mouseout", function() {
        tooltip.transition().duration(500).style("opacity", 0);
        d3.select(this).style("opacity", 1);
    });
'''

        return f'''// D3.js Histogram
const margin = {{top: 40, right: 30, bottom: 60, left: 60}};
const width = {width} - margin.left - margin.right;
const height = {height} - margin.top - margin.bottom;

const svg = d3.select("#chart")
    .append("svg")
    .attr("width", width + margin.left + margin.right)
    .attr("height", height + margin.top + margin.bottom)
    .append("g")
    .attr("transform", `translate(${{margin.left}},${{margin.top}})`);

const data = {data_json};
const values = data.map(d => +d.{x});

// Scales
const x = d3.scaleLinear()
    .domain(d3.extent(values))
    .nice()
    .range([0, width]);

// Histogram bins
const histogram = d3.histogram()
    .domain(x.domain())
    .thresholds(x.ticks(20));

const bins = histogram(values);

const y = d3.scaleLinear()
    .domain([0, d3.max(bins, d => d.length)])
    .nice()
    .range([height, 0]);

// Axes
svg.append("g")
    .attr("transform", `translate(0,${{height}})`)
    .call(d3.axisBottom(x));

svg.append("g")
    .call(d3.axisLeft(y));

// Bars
const bars = svg.selectAll("rect")
    .data(bins)
    .enter()
    .append("rect")
    .attr("x", d => x(d.x0) + 1)
    .attr("width", d => Math.max(0, x(d.x1) - x(d.x0) - 1))
    .attr("y", height)
    .attr("height", 0)
    .attr("fill", "steelblue");

bars.transition()
    .duration(750)
    .attr("y", d => y(d.length))
    .attr("height", d => height - y(d.length));

// Title
svg.append("text")
    .attr("x", width / 2)
    .attr("y", -10)
    .attr("text-anchor", "middle")
    .style("font-size", "16px")
    .style("font-weight", "bold")
    .text("{title_str}");
{tooltip_code}'''

    def _generate_heatmap(
        self, records: list, x: str, y: str, title: str, width: int, height: int
    ) -> str:
        """Generate D3.js heatmap code."""
        data_json = json.dumps(records, indent=2) if records else "[]"
        title_str = title or "Heatmap"

        return f'''// D3.js Heatmap
const margin = {{top: 50, right: 30, bottom: 60, left: 60}};
const width = {width} - margin.left - margin.right;
const height = {height} - margin.top - margin.bottom;

const svg = d3.select("#chart")
    .append("svg")
    .attr("width", width + margin.left + margin.right)
    .attr("height", height + margin.top + margin.bottom)
    .append("g")
    .attr("transform", `translate(${{margin.left}},${{margin.top}})`);

const data = {data_json};

// Get unique values for axes
const xValues = [...new Set(data.map(d => d.{x or "x"}))];
const yValues = [...new Set(data.map(d => d.{y or "y"}))];

// Scales
const x = d3.scaleBand()
    .range([0, width])
    .domain(xValues)
    .padding(0.01);

const y = d3.scaleBand()
    .range([height, 0])
    .domain(yValues)
    .padding(0.01);

const colorScale = d3.scaleSequential(d3.interpolateBlues)
    .domain([0, d3.max(data, d => +d.value)]);

// Axes
svg.append("g")
    .attr("transform", `translate(0,${{height}})`)
    .call(d3.axisBottom(x))
    .selectAll("text")
    .attr("transform", "rotate(-45)")
    .style("text-anchor", "end");

svg.append("g")
    .call(d3.axisLeft(y));

// Cells
svg.selectAll()
    .data(data)
    .enter()
    .append("rect")
    .attr("x", d => x(d.{x or "x"}))
    .attr("y", d => y(d.{y or "y"}))
    .attr("width", x.bandwidth())
    .attr("height", y.bandwidth())
    .style("fill", d => colorScale(+d.value));

// Title
svg.append("text")
    .attr("x", width / 2)
    .attr("y", -20)
    .attr("text-anchor", "middle")
    .style("font-size", "16px")
    .style("font-weight", "bold")
    .text("{title_str}");
'''

    def _generate_area(
        self, records: list, x: str, y: str, title: str, width: int, height: int, interactive: bool
    ) -> str:
        """Generate D3.js area chart code."""
        data_json = json.dumps(records, indent=2) if records else "[]"
        title_str = title or "Area Chart"

        return f'''// D3.js Area Chart
const margin = {{top: 40, right: 30, bottom: 60, left: 60}};
const width = {width} - margin.left - margin.right;
const height = {height} - margin.top - margin.bottom;

const svg = d3.select("#chart")
    .append("svg")
    .attr("width", width + margin.left + margin.right)
    .attr("height", height + margin.top + margin.bottom)
    .append("g")
    .attr("transform", `translate(${{margin.left}},${{margin.top}})`);

const data = {data_json};

// Scales
const x = d3.scalePoint()
    .domain(data.map(d => d.{x}))
    .range([0, width]);

const y = d3.scaleLinear()
    .domain([0, d3.max(data, d => +d.{y})])
    .nice()
    .range([height, 0]);

// Axes
svg.append("g")
    .attr("transform", `translate(0,${{height}})`)
    .call(d3.axisBottom(x))
    .selectAll("text")
    .attr("transform", "rotate(-45)")
    .style("text-anchor", "end");

svg.append("g")
    .call(d3.axisLeft(y));

// Area
const area = d3.area()
    .x(d => x(d.{x}))
    .y0(height)
    .y1(d => y(+d.{y}));

svg.append("path")
    .datum(data)
    .attr("fill", "steelblue")
    .attr("fill-opacity", 0.3)
    .attr("stroke", "steelblue")
    .attr("stroke-width", 2)
    .attr("d", area);

// Title
svg.append("text")
    .attr("x", width / 2)
    .attr("y", -10)
    .attr("text-anchor", "middle")
    .style("font-size", "16px")
    .style("font-weight", "bold")
    .text("{title_str}");
'''


# ═══════════════════════════════════════════════════════════════════════════════
# GenerateMatplotlibTool
# ═══════════════════════════════════════════════════════════════════════════════


class GenerateMatplotlibTool(Tool):
    """Generate Python matplotlib visualization code."""

    name = "generate_matplotlib"
    description = """Generate Python matplotlib code for static visualizations.

Supported chart types:
- bar: Bar chart
- line: Line chart
- scatter: Scatter plot
- pie: Pie chart
- heatmap: Heat map
- histogram: Histogram
- box: Box plot
- violin: Violin plot

Examples:
- generate_matplotlib(chart_type="bar", file_path="data.csv", x="category", y="value")
- generate_matplotlib(chart_type="heatmap", data=correlation_matrix)"""

    parameters = {
        "type": "object",
        "properties": {
            "chart_type": {
                "type": "string",
                "enum": ["bar", "line", "scatter", "pie", "heatmap", "histogram", "box", "violin"],
                "description": "Type of chart to generate",
            },
            "file_path": {
                "type": "string",
                "description": "Path to data file",
            },
            "data": {
                "type": "object",
                "description": "Inline data as dict",
            },
            "x": {
                "type": "string",
                "description": "Column for x-axis",
            },
            "y": {
                "type": "string",
                "description": "Column for y-axis",
            },
            "hue": {
                "type": "string",
                "description": "Column for color grouping",
            },
            "title": {
                "type": "string",
                "description": "Chart title",
            },
            "xlabel": {
                "type": "string",
                "description": "X-axis label",
            },
            "ylabel": {
                "type": "string",
                "description": "Y-axis label",
            },
            "figsize": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Figure size [width, height] (default: [10, 6])",
            },
            "style": {
                "type": "string",
                "description": "Matplotlib style (seaborn, ggplot, dark_background)",
            },
            "output_file": {
                "type": "string",
                "description": "Save generated code to file",
            },
        },
        "required": ["chart_type"],
    }

    async def execute(
        self,
        chart_type: str,
        file_path: Optional[str] = None,
        data: Optional[dict] = None,
        x: Optional[str] = None,
        y: Optional[str] = None,
        hue: Optional[str] = None,
        title: Optional[str] = None,
        xlabel: Optional[str] = None,
        ylabel: Optional[str] = None,
        figsize: Optional[list] = None,
        style: Optional[str] = None,
        output_file: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Generate matplotlib visualization code."""
        try:
            figsize = figsize or [10, 6]
            title = title or f"{chart_type.title()} Chart"
            xlabel = xlabel or (x or "X")
            ylabel = ylabel or (y or "Y")
            style = style or "seaborn-v0_8-whitegrid"

            # Build code
            code_lines = [
                "import matplotlib.pyplot as plt",
                "import pandas as pd",
                "import numpy as np",
                "",
            ]

            # Data loading
            if file_path:
                code_lines.append(f'# Load data')
                code_lines.append(f'df = pd.read_csv("{file_path}")')
            elif data:
                code_lines.append("# Create dataframe from data")
                code_lines.append(f"df = pd.DataFrame({data})")
            else:
                code_lines.append("# Placeholder - replace with your data")
                code_lines.append("df = pd.DataFrame({'x': [1, 2, 3], 'y': [4, 5, 6]})")

            code_lines.append("")
            code_lines.append(f'# Set style')
            code_lines.append(f'plt.style.use("{style}")')
            code_lines.append("")
            code_lines.append(f"fig, ax = plt.subplots(figsize={figsize})")
            code_lines.append("")

            # Chart-specific code
            if chart_type == "bar":
                code_lines.append(f'ax.bar(df["{x}"], df["{y}"], color="steelblue")')

            elif chart_type == "line":
                code_lines.append(f'ax.plot(df["{x}"], df["{y}"], marker="o", color="steelblue")')

            elif chart_type == "scatter":
                if hue:
                    code_lines.append(f'for category in df["{hue}"].unique():')
                    code_lines.append(f'    subset = df[df["{hue}"] == category]')
                    code_lines.append(f'    ax.scatter(subset["{x}"], subset["{y}"], label=category, alpha=0.7)')
                    code_lines.append("ax.legend()")
                else:
                    code_lines.append(f'ax.scatter(df["{x}"], df["{y}"], color="steelblue", alpha=0.7)')

            elif chart_type == "pie":
                code_lines.append(f'ax.pie(df["{y}"], labels=df["{x}"], autopct="%1.1f%%")')

            elif chart_type == "histogram":
                code_lines.append(f'ax.hist(df["{x}"], bins=20, color="steelblue", edgecolor="black")')

            elif chart_type == "box":
                if hue:
                    code_lines.append(f'df.boxplot(column="{y}", by="{x}", ax=ax)')
                else:
                    code_lines.append(f'ax.boxplot(df["{x}"])')

            elif chart_type == "violin":
                code_lines.append("import seaborn as sns")
                if hue:
                    code_lines.append(f'sns.violinplot(data=df, x="{x}", y="{y}", ax=ax)')
                else:
                    code_lines.append(f'sns.violinplot(data=df["{x}"], ax=ax)')

            elif chart_type == "heatmap":
                code_lines.append("import seaborn as sns")
                code_lines.append("# Compute correlation matrix")
                code_lines.append("corr = df.select_dtypes(include=[np.number]).corr()")
                code_lines.append('sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax)')

            code_lines.append("")
            code_lines.append(f'ax.set_title("{title}", fontsize=14, fontweight="bold")')
            code_lines.append(f'ax.set_xlabel("{xlabel}", fontsize=12)')
            code_lines.append(f'ax.set_ylabel("{ylabel}", fontsize=12)')
            code_lines.append("")
            code_lines.append("plt.tight_layout()")
            code_lines.append("plt.show()")

            code = "\n".join(code_lines)

            # Save to file if requested
            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(code)

                log.info("matplotlib_chart_saved", chart_type=chart_type, file=str(out_path))

                return ToolResult(
                    success=True,
                    output=f"Matplotlib {chart_type} chart saved to {out_path}\n\n```python\n{code}\n```",
                    metadata={
                        "chart_type": chart_type,
                        "output_file": str(out_path),
                        "library": "matplotlib",
                    },
                )

            log.info("matplotlib_chart_generated", chart_type=chart_type)

            return ToolResult(
                success=True,
                output=f"```python\n{code}\n```",
                metadata={
                    "chart_type": chart_type,
                    "library": "matplotlib",
                },
            )

        except Exception as e:
            log.error("matplotlib_generation_failed", error=str(e), chart_type=chart_type)
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate matplotlib chart: {str(e)}",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# GeneratePlotlyTool
# ═══════════════════════════════════════════════════════════════════════════════


class GeneratePlotlyTool(Tool):
    """Generate Plotly interactive visualization code."""

    name = "generate_plotly"
    description = """Generate Plotly code for interactive visualizations.

Supports Python (plotly.express) and JavaScript (Plotly.js) output.

Chart types:
- bar, line, scatter, pie, heatmap, histogram
- box, violin (distribution)
- scatter_3d, surface (3D)
- sunburst, treemap (hierarchical)

Examples:
- generate_plotly(chart_type="scatter", file_path="data.csv", x="x", y="y", color="category")
- generate_plotly(chart_type="scatter_3d", data={...}, x="x", y="y", z="z")
- generate_plotly(chart_type="bar", language="javascript")"""

    parameters = {
        "type": "object",
        "properties": {
            "chart_type": {
                "type": "string",
                "enum": [
                    "bar", "line", "scatter", "pie", "heatmap", "histogram",
                    "box", "violin", "scatter_3d", "surface", "sunburst", "treemap",
                ],
                "description": "Type of chart to generate",
            },
            "language": {
                "type": "string",
                "enum": ["python", "javascript"],
                "description": "Output language (default: python)",
            },
            "file_path": {
                "type": "string",
                "description": "Path to data file",
            },
            "data": {
                "type": "object",
                "description": "Inline data",
            },
            "x": {
                "type": "string",
                "description": "Column for x-axis",
            },
            "y": {
                "type": "string",
                "description": "Column for y-axis",
            },
            "z": {
                "type": "string",
                "description": "Column for z-axis (3D charts)",
            },
            "color": {
                "type": "string",
                "description": "Column for color grouping",
            },
            "title": {
                "type": "string",
                "description": "Chart title",
            },
            "template": {
                "type": "string",
                "description": "Plotly template (plotly, plotly_white, plotly_dark, seaborn)",
            },
            "output_file": {
                "type": "string",
                "description": "Save generated code to file",
            },
        },
        "required": ["chart_type"],
    }

    async def execute(
        self,
        chart_type: str,
        language: str = "python",
        file_path: Optional[str] = None,
        data: Optional[dict] = None,
        x: Optional[str] = None,
        y: Optional[str] = None,
        z: Optional[str] = None,
        color: Optional[str] = None,
        title: Optional[str] = None,
        template: Optional[str] = None,
        output_file: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Generate Plotly visualization code."""
        try:
            title = title or f"{chart_type.replace('_', ' ').title()} Chart"
            template = template or "plotly_white"

            if language == "python":
                code = self._generate_python(chart_type, file_path, data, x, y, z, color, title, template)
            else:
                code = self._generate_javascript(chart_type, data, x, y, z, color, title)

            # Save to file if requested
            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(code)

                log.info("plotly_chart_saved", chart_type=chart_type, language=language, file=str(out_path))

                ext = "python" if language == "python" else "javascript"
                return ToolResult(
                    success=True,
                    output=f"Plotly {chart_type} chart saved to {out_path}\n\n```{ext}\n{code}\n```",
                    metadata={
                        "chart_type": chart_type,
                        "language": language,
                        "output_file": str(out_path),
                        "library": "plotly",
                    },
                )

            log.info("plotly_chart_generated", chart_type=chart_type, language=language)

            ext = "python" if language == "python" else "javascript"
            return ToolResult(
                success=True,
                output=f"```{ext}\n{code}\n```",
                metadata={
                    "chart_type": chart_type,
                    "language": language,
                    "library": "plotly",
                },
            )

        except Exception as e:
            log.error("plotly_generation_failed", error=str(e), chart_type=chart_type)
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate Plotly chart: {str(e)}",
            )

    def _generate_python(
        self, chart_type: str, file_path: str, data: dict, x: str, y: str, z: str, color: str, title: str, template: str
    ) -> str:
        """Generate Python Plotly code."""
        lines = [
            "import plotly.express as px",
            "import pandas as pd",
            "",
        ]

        # Data loading
        if file_path:
            lines.append(f'df = pd.read_csv("{file_path}")')
        elif data:
            lines.append(f"df = pd.DataFrame({data})")
        else:
            lines.append("# Replace with your data")
            lines.append("df = pd.DataFrame({'x': [1,2,3], 'y': [4,5,6]})")

        lines.append("")

        # Chart generation
        params = [f'df']
        if x:
            params.append(f'x="{x}"')
        if y:
            params.append(f'y="{y}"')
        if z:
            params.append(f'z="{z}"')
        if color:
            params.append(f'color="{color}"')
        params.append(f'title="{title}"')
        params.append(f'template="{template}"')

        if chart_type == "bar":
            lines.append(f"fig = px.bar({', '.join(params)})")
        elif chart_type == "line":
            lines.append(f"fig = px.line({', '.join(params)})")
        elif chart_type == "scatter":
            lines.append(f"fig = px.scatter({', '.join(params)})")
        elif chart_type == "pie":
            lines.append(f"fig = px.pie({', '.join(params)})")
        elif chart_type == "histogram":
            lines.append(f"fig = px.histogram({', '.join(params)})")
        elif chart_type == "box":
            lines.append(f"fig = px.box({', '.join(params)})")
        elif chart_type == "violin":
            lines.append(f"fig = px.violin({', '.join(params)})")
        elif chart_type == "heatmap":
            lines.append("# For heatmap, compute correlation or use matrix data")
            lines.append("corr = df.select_dtypes(include='number').corr()")
            lines.append(f'fig = px.imshow(corr, title="{title}", template="{template}")')
        elif chart_type == "scatter_3d":
            lines.append(f"fig = px.scatter_3d({', '.join(params)})")
        elif chart_type == "surface":
            lines.append("import plotly.graph_objects as go")
            lines.append("# Surface requires 2D array data")
            lines.append(f'fig = go.Figure(data=[go.Surface(z=df.values)])')
            lines.append(f'fig.update_layout(title="{title}", template="{template}")')
        elif chart_type == "sunburst":
            lines.append(f"fig = px.sunburst({', '.join(params)})")
        elif chart_type == "treemap":
            lines.append(f"fig = px.treemap({', '.join(params)})")

        lines.append("")
        lines.append("fig.show()")

        return "\n".join(lines)

    def _generate_javascript(
        self, chart_type: str, data: dict, x: str, y: str, z: str, color: str, title: str
    ) -> str:
        """Generate JavaScript Plotly code."""
        data_json = json.dumps(data or {"x": [], "y": []}, indent=2)

        # Map chart types to Plotly.js types
        type_map = {
            "bar": "bar",
            "line": "scatter",
            "scatter": "scatter",
            "pie": "pie",
            "histogram": "histogram",
            "box": "box",
            "heatmap": "heatmap",
            "scatter_3d": "scatter3d",
            "surface": "surface",
        }

        plotly_type = type_map.get(chart_type, "scatter")
        mode = "markers" if chart_type == "scatter" else ("lines" if chart_type == "line" else None)

        mode_str = f',\n    mode: "{mode}"' if mode else ""

        return f'''// Plotly.js {chart_type} Chart
const data = {data_json};

const trace = {{
    x: data.{x or "x"},
    y: data.{y or "y"},
    type: "{plotly_type}"{mode_str}
}};

const layout = {{
    title: "{title}",
    xaxis: {{ title: "{x or 'X'}" }},
    yaxis: {{ title: "{y or 'Y'}" }}
}};

Plotly.newPlot("chart", [trace], layout);
'''


# ═══════════════════════════════════════════════════════════════════════════════
# CreateDashboardTool
# ═══════════════════════════════════════════════════════════════════════════════


class CreateDashboardTool(Tool):
    """Create multi-chart dashboard layout."""

    name = "create_dashboard"
    description = """Create a dashboard with multiple charts.

Supports grid layouts with configurable chart types and data bindings.
Output formats: HTML (D3/Plotly), Python (matplotlib subplot)

Examples:
- create_dashboard(charts=[
    {"type": "line", "x": "date", "y": "revenue", "position": [0, 0]},
    {"type": "bar", "x": "category", "y": "count", "position": [0, 1]},
    {"type": "pie", "values": "share", "labels": "segment", "position": [1, 0]}
  ], file_path="data.csv")"""

    parameters = {
        "type": "object",
        "properties": {
            "charts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "position": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "[row, col] grid position",
                        },
                        "x": {"type": "string"},
                        "y": {"type": "string"},
                        "title": {"type": "string"},
                    },
                },
                "description": "List of chart configurations",
            },
            "file_path": {
                "type": "string",
                "description": "Path to data file",
            },
            "data": {
                "type": "object",
                "description": "Inline data",
            },
            "rows": {
                "type": "integer",
                "description": "Grid rows (default: 2)",
            },
            "cols": {
                "type": "integer",
                "description": "Grid columns (default: 2)",
            },
            "title": {
                "type": "string",
                "description": "Dashboard title",
            },
            "output_format": {
                "type": "string",
                "enum": ["html", "python"],
                "description": "Output format (default: html)",
            },
            "output_file": {
                "type": "string",
                "description": "Output file path",
            },
        },
        "required": ["charts"],
    }

    async def execute(
        self,
        charts: list[dict],
        file_path: Optional[str] = None,
        data: Optional[dict] = None,
        rows: int = 2,
        cols: int = 2,
        title: Optional[str] = None,
        output_format: str = "html",
        output_file: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Create dashboard layout."""
        try:
            title = title or "Dashboard"

            if output_format == "html":
                code = self._generate_html_dashboard(charts, file_path, data, rows, cols, title)
            else:
                code = self._generate_python_dashboard(charts, file_path, data, rows, cols, title)

            # Save to file if requested
            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(code)

                log.info("dashboard_saved", format=output_format, file=str(out_path))

                return ToolResult(
                    success=True,
                    output=f"Dashboard saved to {out_path}",
                    metadata={
                        "output_file": str(out_path),
                        "format": output_format,
                        "chart_count": len(charts),
                    },
                )

            ext = "html" if output_format == "html" else "python"
            log.info("dashboard_generated", format=output_format, charts=len(charts))

            return ToolResult(
                success=True,
                output=f"```{ext}\n{code}\n```",
                metadata={
                    "format": output_format,
                    "chart_count": len(charts),
                },
            )

        except Exception as e:
            log.error("dashboard_creation_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to create dashboard: {str(e)}",
            )

    def _generate_html_dashboard(
        self, charts: list, file_path: str, data: dict, rows: int, cols: int, title: str
    ) -> str:
        """Generate HTML dashboard with Plotly."""
        # Load data for embedding
        if file_path:
            try:
                path = Path(file_path)
                if path.exists():
                    records, _ = _parse_data_file(path)
                    data_json = json.dumps(records)
                else:
                    data_json = "[]"
            except Exception:
                data_json = "[]"
        elif data:
            # Convert dict of arrays to records
            columns = list(data.keys())
            n = len(next(iter(data.values()))) if data else 0
            records = [{col: data[col][i] for col in columns} for i in range(n)]
            data_json = json.dumps(records)
        else:
            data_json = "[]"

        # Generate chart divs and scripts
        chart_divs = []
        chart_scripts = []

        for i, chart in enumerate(charts):
            pos = chart.get("position", [i // cols, i % cols])
            chart_id = f"chart-{pos[0]}-{pos[1]}"
            chart_type = chart.get("type", "bar")
            x = chart.get("x", "x")
            y = chart.get("y", "y")
            chart_title = chart.get("title", f"{chart_type.title()} Chart")

            chart_divs.append(f'<div id="{chart_id}" class="chart"></div>')

            # Generate Plotly trace
            plotly_type = {
                "bar": "bar",
                "line": "scatter",
                "scatter": "scatter",
                "pie": "pie",
            }.get(chart_type, "scatter")

            mode = ""
            if chart_type == "line":
                mode = ', mode: "lines"'
            elif chart_type == "scatter":
                mode = ', mode: "markers"'

            if chart_type == "pie":
                chart_scripts.append(f'''
    Plotly.newPlot("{chart_id}", [{{
        values: data.map(d => d.{y}),
        labels: data.map(d => d.{x}),
        type: "pie"
    }}], {{title: "{chart_title}"}});
''')
            else:
                chart_scripts.append(f'''
    Plotly.newPlot("{chart_id}", [{{
        x: data.map(d => d.{x}),
        y: data.map(d => d.{y}),
        type: "{plotly_type}"{mode}
    }}], {{title: "{chart_title}"}});
''')

        grid_template = f"repeat({rows}, 1fr)"
        col_template = f"repeat({cols}, 1fr)"

        return f'''<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1 {{
            text-align: center;
            color: #333;
            margin-bottom: 20px;
        }}
        .dashboard {{
            display: grid;
            grid-template-rows: {grid_template};
            grid-template-columns: {col_template};
            gap: 20px;
            max-width: 1400px;
            margin: 0 auto;
        }}
        .chart {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 10px;
            min-height: 350px;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="dashboard">
        {chr(10).join("        " + d for d in chart_divs)}
    </div>
    <script>
const data = {data_json};
{"".join(chart_scripts)}
    </script>
</body>
</html>'''

    def _generate_python_dashboard(
        self, charts: list, file_path: str, data: dict, rows: int, cols: int, title: str
    ) -> str:
        """Generate Python matplotlib subplot dashboard."""
        lines = [
            "import matplotlib.pyplot as plt",
            "import pandas as pd",
            "",
        ]

        if file_path:
            lines.append(f'df = pd.read_csv("{file_path}")')
        elif data:
            lines.append(f"df = pd.DataFrame({data})")
        else:
            lines.append("# Load your data")
            lines.append("df = pd.DataFrame({'x': [1,2,3], 'y': [4,5,6]})")

        lines.append("")
        lines.append(f"fig, axes = plt.subplots({rows}, {cols}, figsize=(12, 8))")
        lines.append(f'fig.suptitle("{title}", fontsize=16, fontweight="bold")')
        lines.append("")

        for chart in charts:
            pos = chart.get("position", [0, 0])
            chart_type = chart.get("type", "bar")
            x = chart.get("x", "x")
            y = chart.get("y", "y")
            chart_title = chart.get("title", "")

            ax_ref = f"axes[{pos[0]}, {pos[1]}]" if rows > 1 and cols > 1 else f"axes[{pos[0] * cols + pos[1]}]"

            if chart_type == "bar":
                lines.append(f'{ax_ref}.bar(df["{x}"], df["{y}"])')
            elif chart_type == "line":
                lines.append(f'{ax_ref}.plot(df["{x}"], df["{y}"])')
            elif chart_type == "scatter":
                lines.append(f'{ax_ref}.scatter(df["{x}"], df["{y}"])')
            elif chart_type == "pie":
                lines.append(f'{ax_ref}.pie(df["{y}"], labels=df["{x}"], autopct="%1.1f%%")')

            if chart_title:
                lines.append(f'{ax_ref}.set_title("{chart_title}")')

            lines.append("")

        lines.append("plt.tight_layout()")
        lines.append("plt.show()")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# ExportInteractiveTool
# ═══════════════════════════════════════════════════════════════════════════════


class ExportInteractiveTool(Tool):
    """Export visualization as standalone HTML with embedded data."""

    name = "export_interactive"
    description = """Export visualization as standalone HTML file.

Creates a self-contained HTML file with:
- Embedded data (no external dependencies except CDN libraries)
- All JavaScript inline
- Interactive features (tooltips, zoom, filter)
- Optional export button for PNG/SVG

Examples:
- export_interactive(chart_code="...", output_file="viz.html")
- export_interactive(file_path="chart.js", library="d3", output_file="standalone.html")"""

    parameters = {
        "type": "object",
        "properties": {
            "chart_code": {
                "type": "string",
                "description": "D3.js or Plotly.js code to embed",
            },
            "file_path": {
                "type": "string",
                "description": "Path to existing chart JS file",
            },
            "data": {
                "type": "object",
                "description": "Data to embed in the HTML",
            },
            "library": {
                "type": "string",
                "enum": ["d3", "plotly"],
                "description": "JS library to include (default: d3)",
            },
            "title": {
                "type": "string",
                "description": "Page title",
            },
            "include_export_button": {
                "type": "boolean",
                "description": "Add PNG/SVG export button (default: true)",
            },
            "responsive": {
                "type": "boolean",
                "description": "Make chart responsive (default: true)",
            },
            "output_file": {
                "type": "string",
                "description": "Output HTML file path (required)",
            },
        },
        "required": ["output_file"],
    }

    async def execute(
        self,
        output_file: str,
        chart_code: Optional[str] = None,
        file_path: Optional[str] = None,
        data: Optional[dict] = None,
        library: str = "d3",
        title: Optional[str] = None,
        include_export_button: bool = True,
        responsive: bool = True,
        **kwargs,
    ) -> ToolResult:
        """Export visualization as standalone HTML."""
        try:
            # Get chart code
            if file_path:
                path = self._resolve_path(file_path)
                if not path.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"File not found: {file_path}",
                    )
                chart_code = path.read_text()
            elif not chart_code:
                chart_code = "// Add your chart code here"

            title = title or "Interactive Visualization"

            # Library CDN
            if library == "d3":
                lib_script = '<script src="https://d3js.org/d3.v7.min.js"></script>'
            else:
                lib_script = '<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>'

            # Data embedding
            data_script = ""
            if data:
                data_json = json.dumps(data, indent=2)
                data_script = f"const embeddedData = {data_json};"

            # Export button
            export_button = ""
            export_script = ""
            if include_export_button:
                export_button = '''
    <div style="text-align: center; margin-top: 10px;">
        <button onclick="exportSVG()" style="margin: 5px; padding: 8px 16px; cursor: pointer;">Export SVG</button>
        <button onclick="exportPNG()" style="margin: 5px; padding: 8px 16px; cursor: pointer;">Export PNG</button>
    </div>'''
                export_script = '''
function exportSVG() {
    const svg = document.querySelector("svg");
    if (!svg) { alert("No SVG found"); return; }
    const svgData = new XMLSerializer().serializeToString(svg);
    const blob = new Blob([svgData], {type: "image/svg+xml"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "chart.svg";
    a.click();
    URL.revokeObjectURL(url);
}

function exportPNG() {
    const svg = document.querySelector("svg");
    if (!svg) { alert("No SVG found"); return; }
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    const svgData = new XMLSerializer().serializeToString(svg);
    const img = new Image();
    img.onload = function() {
        canvas.width = img.width;
        canvas.height = img.height;
        ctx.drawImage(img, 0, 0);
        const a = document.createElement("a");
        a.href = canvas.toDataURL("image/png");
        a.download = "chart.png";
        a.click();
    };
    img.src = "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(svgData)));
}
'''

            # Responsive styles
            responsive_style = ""
            if responsive:
                responsive_style = '''
        #chart {
            width: 100%;
            max-width: 1200px;
            margin: 0 auto;
        }
        #chart svg {
            width: 100%;
            height: auto;
        }'''

            html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    {lib_script}
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #fafafa;
        }}
        h1 {{
            text-align: center;
            color: #333;
        }}
        .tooltip {{
            position: absolute;
            padding: 8px;
            background: rgba(0, 0, 0, 0.7);
            color: #fff;
            border-radius: 4px;
            font-size: 12px;
            pointer-events: none;
        }}{responsive_style}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div id="chart"></div>
{export_button}
    <script>
{data_script}

{chart_code}

{export_script}
    </script>
</body>
</html>'''

            # Save to file
            out_path = self._resolve_path(output_file)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(html)

            log.info("interactive_exported", file=str(out_path), library=library)

            return ToolResult(
                success=True,
                output=f"Interactive visualization exported to {out_path}",
                metadata={
                    "output_file": str(out_path),
                    "library": library,
                    "responsive": responsive,
                    "has_export_button": include_export_button,
                },
            )

        except Exception as e:
            log.error("export_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to export visualization: {str(e)}",
            )
