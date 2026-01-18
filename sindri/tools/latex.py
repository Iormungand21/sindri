"""LaTeX generation tools for Sindri.

Provides tools for generating LaTeX documents, equations, TikZ diagrams,
Beamer presentations, and managing bibliographies.
"""

import re
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


class DocumentClass(str, Enum):
    """Standard LaTeX document classes."""

    ARTICLE = "article"
    REPORT = "report"
    BOOK = "book"
    LETTER = "letter"
    BEAMER = "beamer"


class PaperStyle(str, Enum):
    """Common academic paper styles."""

    IEEE = "ieee"
    ACM = "acm"
    APA = "apa"
    MLA = "mla"
    CHICAGO = "chicago"
    PLAIN = "plain"


class TikzDiagramType(str, Enum):
    """Types of TikZ diagrams."""

    GRAPH = "graph"
    NEURAL_NETWORK = "neural_network"
    FLOWCHART = "flowchart"
    TREE = "tree"
    CIRCUIT = "circuit"
    PLOT = "plot"
    TIMELINE = "timeline"
    VENN = "venn"


@dataclass
class BibEntry:
    """A bibliography entry."""

    key: str
    entry_type: str  # article, book, inproceedings, etc.
    author: Optional[str] = None
    title: Optional[str] = None
    year: Optional[str] = None
    journal: Optional[str] = None
    booktitle: Optional[str] = None
    publisher: Optional[str] = None
    volume: Optional[str] = None
    number: Optional[str] = None
    pages: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None


class GenerateLatexTool(Tool):
    """Generate LaTeX documents from descriptions or outlines.

    Creates well-structured LaTeX documents with proper formatting,
    packages, and document structure.
    """

    name = "generate_latex"
    description = """Generate a LaTeX document from an outline or description.

Creates complete LaTeX documents with proper structure, packages, and formatting.

Features:
- Multiple document classes (article, report, book, beamer)
- Academic paper styles (IEEE, ACM, APA, etc.)
- Automatic package inclusion based on content
- Section and subsection structure
- Bibliography support

Examples:
- generate_latex(title="My Paper", document_class="article", sections=["Introduction", "Methods"])
- generate_latex(title="Research", style="ieee", abstract="This paper...")
- generate_latex(title="Thesis", document_class="report", chapters=["Introduction", "Background"])"""

    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Document title",
            },
            "author": {
                "type": "string",
                "description": "Author name(s)",
            },
            "document_class": {
                "type": "string",
                "description": "LaTeX document class",
                "enum": ["article", "report", "book", "letter", "beamer"],
            },
            "style": {
                "type": "string",
                "description": "Academic paper style (for articles)",
                "enum": ["ieee", "acm", "apa", "mla", "chicago", "plain"],
            },
            "abstract": {
                "type": "string",
                "description": "Document abstract",
            },
            "sections": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of section titles",
            },
            "chapters": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of chapter titles (for report/book)",
            },
            "packages": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Additional LaTeX packages to include",
            },
            "bibliography_file": {
                "type": "string",
                "description": "Path to .bib file for references",
            },
            "two_column": {
                "type": "boolean",
                "description": "Use two-column layout (default: false)",
            },
            "font_size": {
                "type": "integer",
                "description": "Base font size in pt (10, 11, or 12)",
                "enum": [10, 11, 12],
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the document",
            },
        },
        "required": ["title"],
    }

    # Standard packages for different use cases
    STANDARD_PACKAGES = [
        "inputenc",
        "fontenc",
        "amsmath",
        "amssymb",
        "graphicx",
        "hyperref",
    ]

    MATH_PACKAGES = ["amsmath", "amssymb", "amsthm", "mathtools"]
    CODE_PACKAGES = ["listings", "xcolor"]
    FIGURE_PACKAGES = ["graphicx", "float", "subcaption"]
    TABLE_PACKAGES = ["booktabs", "tabularx", "multirow"]

    # Style-specific document classes and packages
    STYLE_CONFIGS = {
        "ieee": {
            "documentclass": "IEEEtran",
            "packages": ["cite", "amsmath", "graphicx", "algorithm2e"],
            "options": [],
        },
        "acm": {
            "documentclass": "acmart",
            "packages": ["booktabs", "subcaption"],
            "options": ["sigconf"],
        },
        "apa": {
            "documentclass": "apa7",
            "packages": ["apacite"],
            "options": ["man"],
        },
        "plain": {
            "documentclass": "article",
            "packages": [],
            "options": [],
        },
    }

    async def execute(
        self,
        title: str,
        author: Optional[str] = None,
        document_class: str = "article",
        style: Optional[str] = None,
        abstract: Optional[str] = None,
        sections: Optional[list[str]] = None,
        chapters: Optional[list[str]] = None,
        packages: Optional[list[str]] = None,
        bibliography_file: Optional[str] = None,
        two_column: bool = False,
        font_size: int = 11,
        output_file: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Generate a LaTeX document."""
        try:
            lines = []

            # Determine document class and options
            if style and style in self.STYLE_CONFIGS:
                config = self.STYLE_CONFIGS[style]
                doc_class = config["documentclass"]
                style_packages = config["packages"]
                class_options = config["options"]
            else:
                doc_class = document_class
                style_packages = []
                class_options = []

            # Build class options
            options = class_options.copy()
            if font_size != 11:
                options.append(f"{font_size}pt")
            if two_column and doc_class not in ["IEEEtran"]:
                options.append("twocolumn")

            # Document class declaration
            if options:
                lines.append(f"\\documentclass[{','.join(options)}]{{{doc_class}}}")
            else:
                lines.append(f"\\documentclass{{{doc_class}}}")

            lines.append("")

            # Packages
            all_packages = set(self.STANDARD_PACKAGES)
            all_packages.update(style_packages)
            if packages:
                all_packages.update(packages)
            if bibliography_file:
                all_packages.add("natbib")

            lines.append("% Packages")
            for pkg in sorted(all_packages):
                if pkg == "inputenc":
                    lines.append(f"\\usepackage[utf8]{{{pkg}}}")
                elif pkg == "fontenc":
                    lines.append(f"\\usepackage[T1]{{{pkg}}}")
                elif pkg == "hyperref":
                    lines.append(f"\\usepackage{{{pkg}}}")
                    lines.append("\\hypersetup{colorlinks=true,linkcolor=blue,citecolor=blue,urlcolor=blue}")
                else:
                    lines.append(f"\\usepackage{{{pkg}}}")

            lines.append("")

            # Title and author
            lines.append("% Document metadata")
            lines.append(f"\\title{{{title}}}")
            if author:
                lines.append(f"\\author{{{author}}}")
            lines.append("\\date{\\today}")

            lines.append("")

            # Begin document
            lines.append("\\begin{document}")
            lines.append("")

            # Title page
            if doc_class == "beamer":
                lines.append("\\begin{frame}")
                lines.append("\\titlepage")
                lines.append("\\end{frame}")
            else:
                lines.append("\\maketitle")

            lines.append("")

            # Abstract
            if abstract and doc_class not in ["beamer", "letter"]:
                lines.append("\\begin{abstract}")
                lines.append(abstract)
                lines.append("\\end{abstract}")
                lines.append("")

            # Table of contents for longer documents
            if doc_class in ["report", "book"] or chapters:
                lines.append("\\tableofcontents")
                lines.append("\\newpage")
                lines.append("")

            # Chapters (for report/book)
            if chapters and doc_class in ["report", "book"]:
                for chapter in chapters:
                    lines.append(f"\\chapter{{{chapter}}}")
                    lines.append("")
                    lines.append("% TODO: Add chapter content")
                    lines.append("")

            # Sections
            if sections:
                for section in sections:
                    if doc_class == "beamer":
                        lines.append(f"\\begin{{frame}}{{{section}}}")
                        lines.append("")
                        lines.append("% TODO: Add slide content")
                        lines.append("")
                        lines.append("\\end{frame}")
                    else:
                        lines.append(f"\\section{{{section}}}")
                        lines.append("")
                        lines.append("% TODO: Add section content")
                        lines.append("")

            # Bibliography
            if bibliography_file:
                lines.append("")
                lines.append("% Bibliography")
                lines.append("\\bibliographystyle{plain}")
                bib_name = Path(bibliography_file).stem
                lines.append(f"\\bibliography{{{bib_name}}}")

            lines.append("")
            lines.append("\\end{document}")

            document = "\n".join(lines)

            if output_file:
                output_path = self._resolve_path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(document)
                return ToolResult(
                    success=True,
                    output=f"LaTeX document saved to {output_path}\n\n```latex\n{document}\n```",
                    metadata={
                        "document_class": doc_class,
                        "style": style,
                        "output_file": str(output_path),
                    },
                )

            return ToolResult(
                success=True,
                output=f"```latex\n{document}\n```",
                metadata={"document_class": doc_class, "style": style},
            )

        except Exception as e:
            log.error("latex_generation_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate LaTeX document: {str(e)}",
            )


class FormatEquationsTool(Tool):
    """Convert mathematical notation to LaTeX equations.

    Supports various input formats and produces properly formatted
    LaTeX math expressions.
    """

    name = "format_equations"
    description = """Convert mathematical notation to LaTeX format.

Supports:
- Plain text math notation (e.g., "x^2 + 2x + 1")
- Unicode math symbols (e.g., "∫ x² dx")
- Named functions (e.g., "sin(x) + cos(x)")
- Matrices and vectors
- Fractions and roots

Examples:
- format_equations(expression="x^2 + 2x + 1")
- format_equations(expression="integral from 0 to infinity of e^(-x) dx")
- format_equations(expression="matrix [[1,2],[3,4]]", display=True)"""

    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression to convert",
            },
            "display": {
                "type": "boolean",
                "description": "Use display math mode (centered, larger) vs inline",
            },
            "numbered": {
                "type": "boolean",
                "description": "Add equation number (for display mode)",
            },
            "label": {
                "type": "string",
                "description": "LaTeX label for cross-referencing",
            },
            "align": {
                "type": "boolean",
                "description": "Use align environment for multi-line equations",
            },
        },
        "required": ["expression"],
    }

    # Unicode to LaTeX mappings
    UNICODE_MAP = {
        "α": "\\alpha",
        "β": "\\beta",
        "γ": "\\gamma",
        "δ": "\\delta",
        "ε": "\\epsilon",
        "ζ": "\\zeta",
        "η": "\\eta",
        "θ": "\\theta",
        "ι": "\\iota",
        "κ": "\\kappa",
        "λ": "\\lambda",
        "μ": "\\mu",
        "ν": "\\nu",
        "ξ": "\\xi",
        "π": "\\pi",
        "ρ": "\\rho",
        "σ": "\\sigma",
        "τ": "\\tau",
        "υ": "\\upsilon",
        "φ": "\\phi",
        "χ": "\\chi",
        "ψ": "\\psi",
        "ω": "\\omega",
        "Γ": "\\Gamma",
        "Δ": "\\Delta",
        "Θ": "\\Theta",
        "Λ": "\\Lambda",
        "Ξ": "\\Xi",
        "Π": "\\Pi",
        "Σ": "\\Sigma",
        "Φ": "\\Phi",
        "Ψ": "\\Psi",
        "Ω": "\\Omega",
        "∞": "\\infty",
        "∂": "\\partial",
        "∇": "\\nabla",
        "∫": "\\int",
        "∑": "\\sum",
        "∏": "\\prod",
        "√": "\\sqrt",
        "±": "\\pm",
        "∓": "\\mp",
        "×": "\\times",
        "÷": "\\div",
        "≤": "\\leq",
        "≥": "\\geq",
        "≠": "\\neq",
        "≈": "\\approx",
        "∈": "\\in",
        "∉": "\\notin",
        "⊂": "\\subset",
        "⊃": "\\supset",
        "∪": "\\cup",
        "∩": "\\cap",
        "→": "\\rightarrow",
        "←": "\\leftarrow",
        "⇒": "\\Rightarrow",
        "⇐": "\\Leftarrow",
        "↔": "\\leftrightarrow",
        "⇔": "\\Leftrightarrow",
        "²": "^{2}",
        "³": "^{3}",
        "⁴": "^{4}",
        "₀": "_{0}",
        "₁": "_{1}",
        "₂": "_{2}",
    }

    async def execute(
        self,
        expression: str,
        display: bool = False,
        numbered: bool = False,
        label: Optional[str] = None,
        align: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Convert expression to LaTeX."""
        try:
            latex = self._convert_to_latex(expression)

            # Wrap in appropriate environment
            if align:
                if numbered:
                    env = "align"
                else:
                    env = "align*"
                result = f"\\begin{{{env}}}\n{latex}\n\\end{{{env}}}"
            elif display:
                if numbered:
                    result = f"\\begin{{equation}}\n{latex}"
                    if label:
                        result += f"\n\\label{{{label}}}"
                    result += "\n\\end{equation}"
                else:
                    result = f"\\[\n{latex}\n\\]"
            else:
                result = f"${latex}$"

            return ToolResult(
                success=True,
                output=f"```latex\n{result}\n```",
                metadata={
                    "display_mode": display,
                    "numbered": numbered,
                    "original": expression,
                },
            )

        except Exception as e:
            log.error("equation_formatting_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to format equation: {str(e)}",
            )

    def _convert_to_latex(self, expression: str) -> str:
        """Convert expression to LaTeX syntax."""
        result = expression

        # Natural language to LaTeX patterns
        natural_patterns = [
            (r"integral\s+from\s+(\S+)\s+to\s+(\S+)\s+of\s+(.+?)\s+d(\w+)", r"\\int_{\1}^{\2} \3 \\, d\4"),
            (r"integral\s+of\s+(.+?)\s+d(\w+)", r"\\int \1 \\, d\2"),
            (r"sum\s+from\s+(\S+)\s*=\s*(\S+)\s+to\s+(\S+)\s+of\s+(.+)", r"\\sum_{\1=\2}^{\3} \4"),
            (r"product\s+from\s+(\S+)\s*=\s*(\S+)\s+to\s+(\S+)\s+of\s+(.+)", r"\\prod_{\1=\2}^{\3} \4"),
            (r"limit\s+as\s+(\w+)\s+approaches\s+(\S+)\s+of\s+(.+)", r"\\lim_{\1 \\to \2} \3"),
            (r"(\w+)\s+over\s+(\w+)", r"\\frac{\1}{\2}"),
            (r"sqrt\s*\((.+?)\)", r"\\sqrt{\1}"),
            (r"(\d+)th\s+root\s+of\s+(.+)", r"\\sqrt[\1]{\2}"),
            (r"matrix\s*\[\[(.+?)\]\]", r"\\begin{pmatrix} \1 \\end{pmatrix}"),
        ]

        # Apply natural language patterns
        for pattern, replacement in natural_patterns:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        # Replace Unicode symbols
        for unicode_char, latex in self.UNICODE_MAP.items():
            result = result.replace(unicode_char, latex)

        # Handle common function names
        functions = ["sin", "cos", "tan", "cot", "sec", "csc",
                     "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh",
                     "log", "ln", "exp", "max", "min", "lim", "det"]
        for func in functions:
            result = re.sub(rf"\b{func}\b", rf"\\{func}", result)

        # Handle fractions written as a/b
        result = re.sub(r"\(([^)]+)\)/\(([^)]+)\)", r"\\frac{\1}{\2}", result)
        result = re.sub(r"(\w+)/(\w+)", r"\\frac{\1}{\2}", result)

        # Handle exponents and subscripts
        result = re.sub(r"\^(\w)", r"^{\1}", result)
        result = re.sub(r"_(\w)", r"_{\1}", result)

        # Handle matrix notation [[a,b],[c,d]]
        matrix_match = re.search(r"\[\[(.+?)\]\]", result)
        if matrix_match:
            matrix_content = matrix_match.group(1)
            # Parse rows
            rows = re.split(r"\],\s*\[", matrix_content)
            latex_rows = []
            for row in rows:
                row = row.strip("[]")
                elements = [e.strip() for e in row.split(",")]
                latex_rows.append(" & ".join(elements))
            matrix_latex = " \\\\\n".join(latex_rows)
            result = result.replace(matrix_match.group(0), f"\\begin{{pmatrix}}\n{matrix_latex}\n\\end{{pmatrix}}")

        return result


class GenerateTikzTool(Tool):
    """Generate TikZ diagrams for LaTeX documents.

    Creates various types of diagrams including graphs, neural networks,
    flowcharts, trees, and more.
    """

    name = "generate_tikz"
    description = """Generate TikZ diagram code for LaTeX documents.

Supported diagram types:
- graph: Node-edge graphs
- neural_network: Neural network architectures
- flowchart: Process flows
- tree: Hierarchical trees
- circuit: Simple circuits (resistors, capacitors)
- plot: Function plots
- timeline: Event timelines
- venn: Venn diagrams

Examples:
- generate_tikz(diagram_type="neural_network", layers=[3, 4, 2], labels=["Input", "Hidden", "Output"])
- generate_tikz(diagram_type="tree", nodes={"root": ["child1", "child2"]})
- generate_tikz(diagram_type="graph", nodes=["A", "B", "C"], edges=[("A", "B"), ("B", "C")])"""

    parameters = {
        "type": "object",
        "properties": {
            "diagram_type": {
                "type": "string",
                "description": "Type of diagram to generate",
                "enum": ["graph", "neural_network", "flowchart", "tree", "circuit", "plot", "timeline", "venn"],
            },
            "nodes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of node labels (for graph/flowchart)",
            },
            "edges": {
                "type": "array",
                "items": {"type": "array"},
                "description": "List of edges as [from, to] or [from, to, label]",
            },
            "layers": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "For neural networks: neurons per layer [input, hidden..., output]",
            },
            "labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Labels for layers or nodes",
            },
            "tree_data": {
                "type": "object",
                "description": "Tree structure as nested dict {parent: [children]}",
            },
            "function": {
                "type": "string",
                "description": "For plots: mathematical function (e.g., 'sin(x)', 'x^2')",
            },
            "x_range": {
                "type": "array",
                "items": {"type": "number"},
                "description": "For plots: [min, max] for x-axis",
            },
            "events": {
                "type": "array",
                "items": {"type": "object"},
                "description": "For timeline: list of {date: str, label: str}",
            },
            "sets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "For Venn: list of set labels",
            },
            "title": {
                "type": "string",
                "description": "Optional diagram title",
            },
            "scale": {
                "type": "number",
                "description": "Scale factor (default: 1.0)",
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the TikZ code",
            },
        },
        "required": ["diagram_type"],
    }

    async def execute(
        self,
        diagram_type: str,
        nodes: Optional[list[str]] = None,
        edges: Optional[list[list]] = None,
        layers: Optional[list[int]] = None,
        labels: Optional[list[str]] = None,
        tree_data: Optional[dict] = None,
        function: Optional[str] = None,
        x_range: Optional[list[float]] = None,
        events: Optional[list[dict]] = None,
        sets: Optional[list[str]] = None,
        title: Optional[str] = None,
        scale: float = 1.0,
        output_file: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Generate TikZ diagram code."""
        try:
            if diagram_type == "neural_network":
                tikz = self._generate_neural_network(layers, labels, scale)
            elif diagram_type == "graph":
                tikz = self._generate_graph(nodes, edges, scale)
            elif diagram_type == "flowchart":
                tikz = self._generate_flowchart(nodes, edges, scale)
            elif diagram_type == "tree":
                tikz = self._generate_tree(tree_data, scale)
            elif diagram_type == "plot":
                tikz = self._generate_plot(function, x_range, title, scale)
            elif diagram_type == "timeline":
                tikz = self._generate_timeline(events, scale)
            elif diagram_type == "venn":
                tikz = self._generate_venn(sets, scale)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported diagram type: {diagram_type}",
                )

            # Wrap in figure environment if title provided
            if title:
                tikz = f"""\\begin{{figure}}[h]
\\centering
{tikz}
\\caption{{{title}}}
\\end{{figure}}"""

            if output_file:
                output_path = self._resolve_path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(tikz)
                return ToolResult(
                    success=True,
                    output=f"TikZ diagram saved to {output_path}\n\n```latex\n{tikz}\n```",
                    metadata={"diagram_type": diagram_type, "output_file": str(output_path)},
                )

            return ToolResult(
                success=True,
                output=f"```latex\n{tikz}\n```",
                metadata={"diagram_type": diagram_type},
            )

        except Exception as e:
            log.error("tikz_generation_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate TikZ diagram: {str(e)}",
            )

    def _generate_neural_network(
        self,
        layers: Optional[list[int]],
        labels: Optional[list[str]],
        scale: float,
    ) -> str:
        """Generate neural network diagram."""
        if not layers:
            layers = [3, 4, 2]  # Default: 3 input, 4 hidden, 2 output

        lines = [
            "\\begin{tikzpicture}[",
            f"    scale={scale},",
            "    shorten >=1pt,",
            "    node distance=1.5cm,",
            "    on grid,",
            "    >=stealth,",
            "    every node/.style={circle, draw, minimum size=8mm}",
            "]",
            "",
        ]

        # Define layer colors
        colors = ["red!30", "blue!30", "green!30", "orange!30", "purple!30"]

        # Draw nodes
        max_neurons = max(layers)
        for layer_idx, num_neurons in enumerate(layers):
            x = layer_idx * 2.5
            color = colors[layer_idx % len(colors)]
            offset = (max_neurons - num_neurons) / 2

            for neuron_idx in range(num_neurons):
                y = neuron_idx + offset
                node_name = f"n{layer_idx}_{neuron_idx}"
                lines.append(f"    \\node[fill={color}] ({node_name}) at ({x}, {-y}) {{}};")

        lines.append("")

        # Draw connections
        lines.append("    % Connections")
        for layer_idx in range(len(layers) - 1):
            for from_neuron in range(layers[layer_idx]):
                for to_neuron in range(layers[layer_idx + 1]):
                    from_node = f"n{layer_idx}_{from_neuron}"
                    to_node = f"n{layer_idx + 1}_{to_neuron}"
                    lines.append(f"    \\draw[->] ({from_node}) -- ({to_node});")

        lines.append("")

        # Add labels if provided
        if labels:
            lines.append("    % Layer labels")
            for layer_idx, label in enumerate(labels):
                x = layer_idx * 2.5
                lines.append(f"    \\node[draw=none, above] at ({x}, 0.5) {{{label}}};")

        lines.append("\\end{tikzpicture}")
        return "\n".join(lines)

    def _generate_graph(
        self,
        nodes: Optional[list[str]],
        edges: Optional[list[list]],
        scale: float,
    ) -> str:
        """Generate graph diagram."""
        if not nodes:
            nodes = ["A", "B", "C"]

        lines = [
            "\\begin{tikzpicture}[",
            f"    scale={scale},",
            "    auto,",
            "    node distance=2.5cm,",
            "    every node/.style={circle, draw, minimum size=1cm}",
            "]",
            "",
        ]

        # Position nodes in a circle
        n = len(nodes)
        for i, node in enumerate(nodes):
            angle = 90 + i * 360 / n
            lines.append(f"    \\node ({node}) at ({angle}:{2*scale}cm) {{{node}}};")

        lines.append("")

        # Draw edges
        if edges:
            for edge in edges:
                from_node = edge[0]
                to_node = edge[1]
                label = edge[2] if len(edge) > 2 else ""
                if label:
                    lines.append(f"    \\draw[->] ({from_node}) -- node {{{label}}} ({to_node});")
                else:
                    lines.append(f"    \\draw[->] ({from_node}) -- ({to_node});")

        lines.append("\\end{tikzpicture}")
        return "\n".join(lines)

    def _generate_flowchart(
        self,
        nodes: Optional[list[str]],
        edges: Optional[list[list]],
        scale: float,
    ) -> str:
        """Generate flowchart diagram."""
        if not nodes:
            nodes = ["Start", "Process", "End"]

        lines = [
            "\\begin{tikzpicture}[",
            f"    scale={scale},",
            "    node distance=1.5cm,",
            "    startstop/.style={rectangle, rounded corners, minimum width=2cm, minimum height=1cm, draw, fill=red!30},",
            "    process/.style={rectangle, minimum width=2cm, minimum height=1cm, draw, fill=orange!30},",
            "    decision/.style={diamond, minimum width=2cm, minimum height=1cm, draw, fill=green!30},",
            "    arrow/.style={thick, ->, >=stealth}",
            "]",
            "",
        ]

        # Position nodes vertically
        for i, node in enumerate(nodes):
            y = -i * 2
            # Determine style based on position/name
            if i == 0 or "start" in node.lower():
                style = "startstop"
            elif i == len(nodes) - 1 or "end" in node.lower():
                style = "startstop"
            elif "?" in node or "decision" in node.lower():
                style = "decision"
            else:
                style = "process"

            node_id = f"node{i}"
            lines.append(f"    \\node[{style}] ({node_id}) at (0, {y}) {{{node}}};")

        lines.append("")

        # Draw edges
        if edges:
            for edge in edges:
                from_idx = edge[0] if isinstance(edge[0], int) else nodes.index(edge[0]) if edge[0] in nodes else 0
                to_idx = edge[1] if isinstance(edge[1], int) else nodes.index(edge[1]) if edge[1] in nodes else 1
                label = edge[2] if len(edge) > 2 else ""
                if label:
                    lines.append(f"    \\draw[arrow] (node{from_idx}) -- node[right] {{{label}}} (node{to_idx});")
                else:
                    lines.append(f"    \\draw[arrow] (node{from_idx}) -- (node{to_idx});")
        else:
            # Default: connect sequentially
            for i in range(len(nodes) - 1):
                lines.append(f"    \\draw[arrow] (node{i}) -- (node{i+1});")

        lines.append("\\end{tikzpicture}")
        return "\n".join(lines)

    def _generate_tree(self, tree_data: Optional[dict], scale: float) -> str:
        """Generate tree diagram."""
        if not tree_data:
            tree_data = {"Root": ["Child 1", "Child 2"]}

        lines = [
            "\\begin{tikzpicture}[",
            f"    scale={scale},",
            "    level 1/.style={sibling distance=4cm},",
            "    level 2/.style={sibling distance=2cm},",
            "    every node/.style={circle, draw, minimum size=8mm}",
            "]",
            "",
        ]

        def build_tree(data: dict, parent: Optional[str] = None) -> list[str]:
            result = []
            for node, children in data.items():
                if parent is None:
                    result.append(f"    \\node {{{node}}}")
                if children:
                    if isinstance(children, list):
                        child_strs = []
                        for child in children:
                            if isinstance(child, dict):
                                child_strs.extend(build_tree(child))
                            else:
                                child_strs.append(f"child {{node {{{child}}}}}")
                        result.append("        " + "\n        ".join(child_strs))
            return result

        tree_content = build_tree(tree_data)
        lines.extend(tree_content)
        lines.append("    ;")
        lines.append("\\end{tikzpicture}")
        return "\n".join(lines)

    def _generate_plot(
        self,
        function: Optional[str],
        x_range: Optional[list[float]],
        title: Optional[str],
        scale: float,
    ) -> str:
        """Generate function plot."""
        if not function:
            function = "sin(deg(x))"
        if not x_range:
            x_range = [-3.14, 3.14]

        # Convert common notation
        func = function.replace("^", "**")
        if "sin" in func and "deg" not in func:
            func = func.replace("sin(x)", "sin(deg(x))")
        if "cos" in func and "deg" not in func:
            func = func.replace("cos(x)", "cos(deg(x))")

        lines = [
            "\\begin{tikzpicture}",
            "    \\begin{axis}[",
            f"        scale={scale},",
            "        axis lines=middle,",
            "        xlabel={$x$},",
            "        ylabel={$y$},",
            f"        xmin={x_range[0]}, xmax={x_range[1]},",
            "        samples=100,",
            "        smooth,",
            "        grid=both,",
        ]

        if title:
            lines.append(f"        title={{{title}}},")

        lines.append("    ]")
        lines.append(f"    \\addplot[blue, thick, domain={x_range[0]}:{x_range[1]}] {{{func}}};")
        lines.append("    \\end{axis}")
        lines.append("\\end{tikzpicture}")
        return "\n".join(lines)

    def _generate_timeline(self, events: Optional[list[dict]], scale: float) -> str:
        """Generate timeline diagram."""
        if not events:
            events = [
                {"date": "2020", "label": "Event 1"},
                {"date": "2022", "label": "Event 2"},
                {"date": "2024", "label": "Event 3"},
            ]

        lines = [
            "\\begin{tikzpicture}[",
            f"    scale={scale},",
            "]",
            "",
            "    % Draw timeline",
            f"    \\draw[thick, ->] (0, 0) -- ({len(events) * 2.5 + 1}, 0);",
            "",
        ]

        for i, event in enumerate(events):
            x = i * 2.5 + 1
            date = event.get("date", f"Event {i+1}")
            label = event.get("label", "")

            lines.append(f"    % Event {i+1}")
            lines.append(f"    \\draw ({x}, 0.1) -- ({x}, -0.1);")
            lines.append(f"    \\node[below] at ({x}, -0.2) {{{date}}};")
            lines.append(f"    \\node[above, align=center] at ({x}, 0.3) {{{label}}};")

        lines.append("\\end{tikzpicture}")
        return "\n".join(lines)

    def _generate_venn(self, sets: Optional[list[str]], scale: float) -> str:
        """Generate Venn diagram."""
        if not sets:
            sets = ["A", "B"]

        lines = [
            "\\begin{tikzpicture}[",
            f"    scale={scale},",
            "]",
            "",
        ]

        if len(sets) == 2:
            lines.extend([
                "    \\draw[fill=red!30, opacity=0.5] (-0.5, 0) circle (1.5);",
                "    \\draw[fill=blue!30, opacity=0.5] (0.5, 0) circle (1.5);",
                f"    \\node at (-1.5, 0) {{{sets[0]}}};",
                f"    \\node at (1.5, 0) {{{sets[1]}}};",
            ])
        elif len(sets) == 3:
            lines.extend([
                "    \\draw[fill=red!30, opacity=0.5] (0, 0.5) circle (1.5);",
                "    \\draw[fill=blue!30, opacity=0.5] (-0.75, -0.75) circle (1.5);",
                "    \\draw[fill=green!30, opacity=0.5] (0.75, -0.75) circle (1.5);",
                f"    \\node at (0, 2) {{{sets[0]}}};",
                f"    \\node at (-2, -1.5) {{{sets[1]}}};",
                f"    \\node at (2, -1.5) {{{sets[2]}}};",
            ])
        else:
            # Simple circle for single set or more complex
            for i, s in enumerate(sets):
                x = i * 2 - (len(sets) - 1)
                color = ["red", "blue", "green", "orange", "purple"][i % 5]
                lines.append(f"    \\draw[fill={color}!30, opacity=0.5] ({x}, 0) circle (1);")
                lines.append(f"    \\node at ({x}, 0) {{{s}}};")

        lines.append("\\end{tikzpicture}")
        return "\n".join(lines)


class ManageBibliographyTool(Tool):
    """Manage BibTeX bibliographies for LaTeX documents.

    Create, format, and organize bibliography entries.
    """

    name = "manage_bibliography"
    description = """Manage BibTeX bibliography entries.

Features:
- Create new .bib files
- Add entries (article, book, inproceedings, etc.)
- Format entries consistently
- Validate entry fields
- Generate citation keys

Examples:
- manage_bibliography(action="create", output_file="refs.bib")
- manage_bibliography(action="add", bib_file="refs.bib", entry_type="article", author="Smith, J.", title="...")
- manage_bibliography(action="format", bib_file="refs.bib")"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action to perform",
                "enum": ["create", "add", "format", "validate", "list"],
            },
            "bib_file": {
                "type": "string",
                "description": "Path to .bib file",
            },
            "output_file": {
                "type": "string",
                "description": "Output path for new .bib file",
            },
            "entry_type": {
                "type": "string",
                "description": "Type of bibliography entry",
                "enum": ["article", "book", "inproceedings", "incollection", "phdthesis", "mastersthesis", "misc", "techreport", "unpublished"],
            },
            "key": {
                "type": "string",
                "description": "Citation key (auto-generated if not provided)",
            },
            "author": {
                "type": "string",
                "description": "Author(s)",
            },
            "title": {
                "type": "string",
                "description": "Title",
            },
            "year": {
                "type": "string",
                "description": "Publication year",
            },
            "journal": {
                "type": "string",
                "description": "Journal name (for articles)",
            },
            "booktitle": {
                "type": "string",
                "description": "Book title (for inproceedings/incollection)",
            },
            "publisher": {
                "type": "string",
                "description": "Publisher",
            },
            "volume": {
                "type": "string",
                "description": "Volume number",
            },
            "number": {
                "type": "string",
                "description": "Issue number",
            },
            "pages": {
                "type": "string",
                "description": "Page numbers (e.g., '1--10')",
            },
            "doi": {
                "type": "string",
                "description": "DOI",
            },
            "url": {
                "type": "string",
                "description": "URL",
            },
        },
        "required": ["action"],
    }

    # Required fields per entry type
    REQUIRED_FIELDS = {
        "article": ["author", "title", "journal", "year"],
        "book": ["author", "title", "publisher", "year"],
        "inproceedings": ["author", "title", "booktitle", "year"],
        "incollection": ["author", "title", "booktitle", "publisher", "year"],
        "phdthesis": ["author", "title", "school", "year"],
        "mastersthesis": ["author", "title", "school", "year"],
        "misc": [],
        "techreport": ["author", "title", "institution", "year"],
        "unpublished": ["author", "title", "note"],
    }

    async def execute(
        self,
        action: str,
        bib_file: Optional[str] = None,
        output_file: Optional[str] = None,
        entry_type: Optional[str] = None,
        key: Optional[str] = None,
        author: Optional[str] = None,
        title: Optional[str] = None,
        year: Optional[str] = None,
        journal: Optional[str] = None,
        booktitle: Optional[str] = None,
        publisher: Optional[str] = None,
        volume: Optional[str] = None,
        number: Optional[str] = None,
        pages: Optional[str] = None,
        doi: Optional[str] = None,
        url: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Manage bibliography."""
        try:
            if action == "create":
                return await self._create_bib(output_file)
            elif action == "add":
                return await self._add_entry(
                    bib_file, entry_type, key, author, title, year,
                    journal, booktitle, publisher, volume, number,
                    pages, doi, url
                )
            elif action == "format":
                return await self._format_bib(bib_file)
            elif action == "validate":
                return await self._validate_bib(bib_file)
            elif action == "list":
                return await self._list_entries(bib_file)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown action: {action}",
                )
        except Exception as e:
            log.error("bibliography_operation_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Bibliography operation failed: {str(e)}",
            )

    async def _create_bib(self, output_file: Optional[str]) -> ToolResult:
        """Create a new .bib file."""
        if not output_file:
            output_file = "references.bib"

        output_path = self._resolve_path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        content = """% Bibliography file
% Generated by Sindri LaTeX Tools

"""
        output_path.write_text(content)

        return ToolResult(
            success=True,
            output=f"Created bibliography file: {output_path}",
            metadata={"output_file": str(output_path)},
        )

    async def _add_entry(
        self,
        bib_file: Optional[str],
        entry_type: Optional[str],
        key: Optional[str],
        author: Optional[str],
        title: Optional[str],
        year: Optional[str],
        journal: Optional[str],
        booktitle: Optional[str],
        publisher: Optional[str],
        volume: Optional[str],
        number: Optional[str],
        pages: Optional[str],
        doi: Optional[str],
        url: Optional[str],
    ) -> ToolResult:
        """Add entry to .bib file."""
        if not bib_file:
            return ToolResult(success=False, output="", error="bib_file is required")
        if not entry_type:
            return ToolResult(success=False, output="", error="entry_type is required")

        # Generate key if not provided
        if not key:
            author_key = author.split(",")[0].strip().lower() if author else "unknown"
            year_key = year or "0000"
            key = f"{author_key}{year_key}"

        # Build entry
        lines = [f"@{entry_type}{{{key},"]

        fields = [
            ("author", author),
            ("title", title),
            ("year", year),
            ("journal", journal),
            ("booktitle", booktitle),
            ("publisher", publisher),
            ("volume", volume),
            ("number", number),
            ("pages", pages),
            ("doi", doi),
            ("url", url),
        ]

        for field_name, field_value in fields:
            if field_value:
                lines.append(f"  {field_name} = {{{field_value}}},")

        lines.append("}")
        entry = "\n".join(lines)

        # Append to file
        bib_path = self._resolve_path(bib_file)
        if bib_path.exists():
            existing = bib_path.read_text()
            bib_path.write_text(existing + "\n" + entry + "\n")
        else:
            bib_path.write_text(entry + "\n")

        return ToolResult(
            success=True,
            output=f"Added entry '{key}' to {bib_path}\n\n```bibtex\n{entry}\n```",
            metadata={"key": key, "entry_type": entry_type, "bib_file": str(bib_path)},
        )

    async def _format_bib(self, bib_file: Optional[str]) -> ToolResult:
        """Format .bib file consistently."""
        if not bib_file:
            return ToolResult(success=False, output="", error="bib_file is required")

        bib_path = self._resolve_path(bib_file)
        if not bib_path.exists():
            return ToolResult(success=False, output="", error=f"File not found: {bib_path}")

        content = bib_path.read_text()

        # Simple formatting: normalize whitespace, align fields
        # More sophisticated formatting would require a proper BibTeX parser
        lines = content.split("\n")
        formatted_lines = []
        in_entry = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("@"):
                in_entry = True
                formatted_lines.append(stripped)
            elif stripped == "}":
                in_entry = False
                formatted_lines.append(stripped)
                formatted_lines.append("")  # Add blank line between entries
            elif in_entry and "=" in stripped:
                # Format field
                parts = stripped.split("=", 1)
                field_name = parts[0].strip().lower()
                field_value = parts[1].strip()
                formatted_lines.append(f"  {field_name:12} = {field_value}")
            else:
                formatted_lines.append(stripped)

        formatted = "\n".join(formatted_lines)
        bib_path.write_text(formatted)

        return ToolResult(
            success=True,
            output=f"Formatted {bib_path}",
            metadata={"bib_file": str(bib_path)},
        )

    async def _validate_bib(self, bib_file: Optional[str]) -> ToolResult:
        """Validate .bib file entries."""
        if not bib_file:
            return ToolResult(success=False, output="", error="bib_file is required")

        bib_path = self._resolve_path(bib_file)
        if not bib_path.exists():
            return ToolResult(success=False, output="", error=f"File not found: {bib_path}")

        content = bib_path.read_text()

        # Parse entries
        entry_pattern = re.compile(r"@(\w+)\{([^,]+),([^@]*)\}", re.DOTALL)
        issues = []
        entries = []

        for match in entry_pattern.finditer(content):
            entry_type = match.group(1).lower()
            key = match.group(2).strip()
            fields_str = match.group(3)

            entries.append(key)

            # Check required fields
            required = self.REQUIRED_FIELDS.get(entry_type, [])
            found_fields = set()

            for field_match in re.finditer(r"(\w+)\s*=", fields_str):
                found_fields.add(field_match.group(1).lower())

            missing = set(required) - found_fields
            if missing:
                issues.append(f"{key} ({entry_type}): missing {', '.join(missing)}")

        result_lines = [f"Found {len(entries)} entries"]
        if issues:
            result_lines.append("\nIssues:")
            result_lines.extend(f"  - {issue}" for issue in issues)
        else:
            result_lines.append("All entries valid!")

        return ToolResult(
            success=True,
            output="\n".join(result_lines),
            metadata={"entries": len(entries), "issues": len(issues)},
        )

    async def _list_entries(self, bib_file: Optional[str]) -> ToolResult:
        """List entries in .bib file."""
        if not bib_file:
            return ToolResult(success=False, output="", error="bib_file is required")

        bib_path = self._resolve_path(bib_file)
        if not bib_path.exists():
            return ToolResult(success=False, output="", error=f"File not found: {bib_path}")

        content = bib_path.read_text()

        # Parse entries
        entry_pattern = re.compile(r"@(\w+)\{([^,]+),", re.MULTILINE)
        entries = []

        for match in entry_pattern.finditer(content):
            entry_type = match.group(1).lower()
            key = match.group(2).strip()
            entries.append(f"  [{entry_type}] {key}")

        if not entries:
            return ToolResult(
                success=True,
                output="No entries found in bibliography file",
                metadata={"entries": 0},
            )

        return ToolResult(
            success=True,
            output=f"Entries in {bib_path}:\n" + "\n".join(entries),
            metadata={"entries": len(entries)},
        )


class CreateBeamerTool(Tool):
    """Generate Beamer presentation slides.

    Creates LaTeX Beamer presentations with various themes and layouts.
    """

    name = "create_beamer"
    description = """Generate a Beamer (LaTeX) presentation.

Creates slide decks with:
- Multiple theme options
- Title and section slides
- Bullet points and content frames
- Code listings support
- Math support

Examples:
- create_beamer(title="My Talk", author="J. Smith", slides=["Introduction", "Methods", "Results"])
- create_beamer(title="Workshop", theme="Madrid", slides=["Setup", "Demo", "Q&A"])"""

    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Presentation title",
            },
            "subtitle": {
                "type": "string",
                "description": "Presentation subtitle",
            },
            "author": {
                "type": "string",
                "description": "Author name(s)",
            },
            "institute": {
                "type": "string",
                "description": "Institution/organization",
            },
            "date": {
                "type": "string",
                "description": "Presentation date (default: \\today)",
            },
            "theme": {
                "type": "string",
                "description": "Beamer theme",
                "enum": ["default", "Madrid", "Berlin", "Copenhagen", "Warsaw", "Singapore", "Boadilla", "Malmoe", "Pittsburgh", "Rochester"],
            },
            "color_theme": {
                "type": "string",
                "description": "Color theme",
                "enum": ["default", "albatross", "beaver", "beetle", "crane", "dolphin", "dove", "lily", "orchid", "rose", "seahorse", "whale"],
            },
            "slides": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of slide titles",
            },
            "sections": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Sections with slides: [{title: str, slides: [str]}]",
            },
            "toc": {
                "type": "boolean",
                "description": "Include table of contents slide",
            },
            "slide_numbers": {
                "type": "boolean",
                "description": "Show slide numbers (default: true)",
            },
            "output_file": {
                "type": "string",
                "description": "Output file path",
            },
        },
        "required": ["title"],
    }

    async def execute(
        self,
        title: str,
        subtitle: Optional[str] = None,
        author: Optional[str] = None,
        institute: Optional[str] = None,
        date: Optional[str] = None,
        theme: str = "Madrid",
        color_theme: Optional[str] = None,
        slides: Optional[list[str]] = None,
        sections: Optional[list[dict]] = None,
        toc: bool = True,
        slide_numbers: bool = True,
        output_file: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Generate Beamer presentation."""
        try:
            lines = []

            # Document class and theme
            lines.append("\\documentclass{beamer}")
            lines.append(f"\\usetheme{{{theme}}}")
            if color_theme:
                lines.append(f"\\usecolortheme{{{color_theme}}}")
            lines.append("")

            # Packages
            lines.append("% Packages")
            lines.append("\\usepackage[utf8]{inputenc}")
            lines.append("\\usepackage{amsmath}")
            lines.append("\\usepackage{graphicx}")
            lines.append("\\usepackage{listings}")
            lines.append("")

            # Remove navigation symbols optionally
            if not slide_numbers:
                lines.append("\\setbeamertemplate{navigation symbols}{}")
            lines.append("")

            # Title info
            lines.append("% Title page info")
            lines.append(f"\\title{{{title}}}")
            if subtitle:
                lines.append(f"\\subtitle{{{subtitle}}}")
            if author:
                lines.append(f"\\author{{{author}}}")
            if institute:
                lines.append(f"\\institute{{{institute}}}")
            lines.append(f"\\date{{{date or '\\\\today'}}}")
            lines.append("")

            # Begin document
            lines.append("\\begin{document}")
            lines.append("")

            # Title frame
            lines.append("% Title slide")
            lines.append("\\begin{frame}")
            lines.append("\\titlepage")
            lines.append("\\end{frame}")
            lines.append("")

            # Table of contents
            if toc:
                lines.append("% Table of contents")
                lines.append("\\begin{frame}{Outline}")
                lines.append("\\tableofcontents")
                lines.append("\\end{frame}")
                lines.append("")

            # Content slides
            if sections:
                for section in sections:
                    section_title = section.get("title", "Section")
                    section_slides = section.get("slides", [])

                    lines.append(f"\\section{{{section_title}}}")
                    lines.append("")

                    for slide in section_slides:
                        lines.append(f"\\begin{{frame}}{{{slide}}}")
                        lines.append("")
                        lines.append("% TODO: Add slide content")
                        lines.append("\\begin{itemize}")
                        lines.append("    \\item Point 1")
                        lines.append("    \\item Point 2")
                        lines.append("    \\item Point 3")
                        lines.append("\\end{itemize}")
                        lines.append("")
                        lines.append("\\end{frame}")
                        lines.append("")

            elif slides:
                for slide in slides:
                    lines.append(f"\\begin{{frame}}{{{slide}}}")
                    lines.append("")
                    lines.append("% TODO: Add slide content")
                    lines.append("\\begin{itemize}")
                    lines.append("    \\item Point 1")
                    lines.append("    \\item Point 2")
                    lines.append("    \\item Point 3")
                    lines.append("\\end{itemize}")
                    lines.append("")
                    lines.append("\\end{frame}")
                    lines.append("")

            lines.append("\\end{document}")

            document = "\n".join(lines)

            if output_file:
                output_path = self._resolve_path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(document)
                return ToolResult(
                    success=True,
                    output=f"Beamer presentation saved to {output_path}\n\n```latex\n{document}\n```",
                    metadata={"theme": theme, "output_file": str(output_path)},
                )

            return ToolResult(
                success=True,
                output=f"```latex\n{document}\n```",
                metadata={"theme": theme},
            )

        except Exception as e:
            log.error("beamer_generation_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate Beamer presentation: {str(e)}",
            )


class LatexToPdfTool(Tool):
    """Compile LaTeX documents to PDF.

    Requires a LaTeX distribution (texlive, miktex) to be installed.
    """

    name = "latex_to_pdf"
    description = """Compile a LaTeX document to PDF.

Requires a LaTeX distribution (texlive, miktex) to be installed on the system.

Features:
- Multiple compilation passes for references
- BibTeX processing
- Error reporting

Examples:
- latex_to_pdf(input_file="document.tex")
- latex_to_pdf(input_file="paper.tex", output_dir="build/", bibtex=True)"""

    parameters = {
        "type": "object",
        "properties": {
            "input_file": {
                "type": "string",
                "description": "Path to .tex file",
            },
            "output_dir": {
                "type": "string",
                "description": "Output directory for PDF (default: same as input)",
            },
            "bibtex": {
                "type": "boolean",
                "description": "Run BibTeX for bibliography (default: false)",
            },
            "engine": {
                "type": "string",
                "description": "LaTeX engine to use",
                "enum": ["pdflatex", "xelatex", "lualatex"],
            },
            "passes": {
                "type": "integer",
                "description": "Number of compilation passes (default: 2)",
            },
        },
        "required": ["input_file"],
    }

    async def execute(
        self,
        input_file: str,
        output_dir: Optional[str] = None,
        bibtex: bool = False,
        engine: str = "pdflatex",
        passes: int = 2,
        **kwargs,
    ) -> ToolResult:
        """Compile LaTeX to PDF."""
        try:
            input_path = self._resolve_path(input_file)
            if not input_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file not found: {input_path}",
                )

            if output_dir:
                out_path = self._resolve_path(output_dir)
                out_path.mkdir(parents=True, exist_ok=True)
            else:
                out_path = input_path.parent

            # Check if LaTeX is installed
            try:
                result = subprocess.run(
                    [engine, "--version"],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"LaTeX engine '{engine}' not found. Please install a LaTeX distribution.",
                    )
            except FileNotFoundError:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"LaTeX engine '{engine}' not found. Please install a LaTeX distribution (e.g., texlive).",
                )

            # Compilation commands
            base_cmd = [
                engine,
                "-interaction=nonstopmode",
                f"-output-directory={out_path}",
                str(input_path),
            ]

            errors = []
            outputs = []

            # First pass
            for i in range(passes):
                result = subprocess.run(
                    base_cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                outputs.append(f"Pass {i+1}: {'OK' if result.returncode == 0 else 'Error'}")

                if result.returncode != 0:
                    # Extract error from log
                    log_lines = result.stdout.split("\n")
                    for line in log_lines:
                        if "!" in line or "Error" in line:
                            errors.append(line)

                # Run BibTeX after first pass if requested
                if i == 0 and bibtex:
                    aux_file = out_path / f"{input_path.stem}.aux"
                    if aux_file.exists():
                        bib_result = subprocess.run(
                            ["bibtex", str(aux_file)],
                            capture_output=True,
                            text=True,
                            timeout=60,
                        )
                        outputs.append(f"BibTeX: {'OK' if bib_result.returncode == 0 else 'Error'}")

            pdf_path = out_path / f"{input_path.stem}.pdf"

            if pdf_path.exists():
                return ToolResult(
                    success=True,
                    output=f"PDF generated: {pdf_path}\n\n" + "\n".join(outputs),
                    metadata={"pdf_file": str(pdf_path), "engine": engine},
                )
            else:
                return ToolResult(
                    success=False,
                    output="\n".join(outputs),
                    error="PDF not generated. Errors:\n" + "\n".join(errors[:10]),
                )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error="LaTeX compilation timed out",
            )
        except Exception as e:
            log.error("latex_compilation_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"LaTeX compilation failed: {str(e)}",
            )
