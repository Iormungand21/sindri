"""Tests for LaTeX generation tools (Phase 11)."""

import pytest
import tempfile
from pathlib import Path

from sindri.tools.latex import (
    GenerateLatexTool,
    FormatEquationsTool,
    GenerateTikzTool,
    ManageBibliographyTool,
    CreateBeamerTool,
    LatexToPdfTool,
)


# ═══════════════════════════════════════════════════════════════════════════════
# GenerateLatexTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateLatexTool:
    """Test suite for LaTeX document generation."""

    @pytest.fixture
    def tool(self):
        return GenerateLatexTool()

    @pytest.mark.asyncio
    async def test_basic_article(self, tool):
        """Test basic article generation."""
        result = await tool.execute(
            title="My Paper",
            author="John Smith",
        )

        assert result.success
        assert "\\documentclass" in result.output
        assert "article" in result.output
        assert "\\title{My Paper}" in result.output
        assert "\\author{John Smith}" in result.output
        assert "\\begin{document}" in result.output
        assert "\\end{document}" in result.output

    @pytest.mark.asyncio
    async def test_article_with_sections(self, tool):
        """Test article with sections."""
        result = await tool.execute(
            title="Research Paper",
            sections=["Introduction", "Methods", "Results", "Discussion"],
        )

        assert result.success
        assert "\\section{Introduction}" in result.output
        assert "\\section{Methods}" in result.output
        assert "\\section{Results}" in result.output
        assert "\\section{Discussion}" in result.output

    @pytest.mark.asyncio
    async def test_article_with_abstract(self, tool):
        """Test article with abstract."""
        result = await tool.execute(
            title="Research Paper",
            abstract="This paper explores important topics.",
        )

        assert result.success
        assert "\\begin{abstract}" in result.output
        assert "This paper explores important topics." in result.output
        assert "\\end{abstract}" in result.output

    @pytest.mark.asyncio
    async def test_report_with_chapters(self, tool):
        """Test report with chapters."""
        result = await tool.execute(
            title="My Thesis",
            document_class="report",
            chapters=["Introduction", "Background", "Methodology"],
        )

        assert result.success
        assert "\\documentclass" in result.output
        assert "report" in result.output
        assert "\\chapter{Introduction}" in result.output
        assert "\\chapter{Background}" in result.output
        assert "\\tableofcontents" in result.output

    @pytest.mark.asyncio
    async def test_ieee_style(self, tool):
        """Test IEEE paper style."""
        result = await tool.execute(
            title="IEEE Paper",
            style="ieee",
        )

        assert result.success
        assert "IEEEtran" in result.output
        assert "\\usepackage{cite}" in result.output

    @pytest.mark.asyncio
    async def test_two_column_layout(self, tool):
        """Test two-column layout."""
        result = await tool.execute(
            title="Two Column Paper",
            two_column=True,
        )

        assert result.success
        assert "twocolumn" in result.output

    @pytest.mark.asyncio
    async def test_custom_font_size(self, tool):
        """Test custom font size."""
        result = await tool.execute(
            title="Large Font Paper",
            font_size=12,
        )

        assert result.success
        assert "12pt" in result.output

    @pytest.mark.asyncio
    async def test_custom_packages(self, tool):
        """Test custom packages."""
        result = await tool.execute(
            title="Paper with Custom Packages",
            packages=["tikz", "pgfplots"],
        )

        assert result.success
        assert "\\usepackage{tikz}" in result.output
        assert "\\usepackage{pgfplots}" in result.output

    @pytest.mark.asyncio
    async def test_bibliography_reference(self, tool):
        """Test bibliography file reference."""
        result = await tool.execute(
            title="Paper with Refs",
            bibliography_file="refs.bib",
        )

        assert result.success
        assert "\\usepackage{natbib}" in result.output
        assert "\\bibliography{refs}" in result.output
        assert "\\bibliographystyle{plain}" in result.output

    @pytest.mark.asyncio
    async def test_standard_packages_included(self, tool):
        """Test that standard packages are included."""
        result = await tool.execute(title="Test Paper")

        assert result.success
        assert "\\usepackage[utf8]{inputenc}" in result.output
        assert "\\usepackage{amsmath}" in result.output
        assert "\\usepackage{graphicx}" in result.output
        assert "\\usepackage{hyperref}" in result.output

    @pytest.mark.asyncio
    async def test_output_to_file(self, tool):
        """Test saving document to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "paper.tex"

            result = await tool.execute(
                title="Saved Paper",
                output_file=str(output_file),
            )

            assert result.success
            assert output_file.exists()
            content = output_file.read_text()
            assert "\\title{Saved Paper}" in content

    @pytest.mark.asyncio
    async def test_metadata(self, tool):
        """Test that metadata is correctly set."""
        result = await tool.execute(
            title="Test Paper",
            style="ieee",
        )

        assert result.success
        assert result.metadata["document_class"] == "IEEEtran"
        assert result.metadata["style"] == "ieee"


# ═══════════════════════════════════════════════════════════════════════════════
# FormatEquationsTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestFormatEquationsTool:
    """Test suite for equation formatting."""

    @pytest.fixture
    def tool(self):
        return FormatEquationsTool()

    @pytest.mark.asyncio
    async def test_inline_equation(self, tool):
        """Test inline equation."""
        result = await tool.execute(
            expression="x^2 + 2x + 1",
        )

        assert result.success
        assert "$" in result.output
        assert "x^{2}" in result.output

    @pytest.mark.asyncio
    async def test_display_equation(self, tool):
        """Test display equation."""
        result = await tool.execute(
            expression="x^2 + 2x + 1",
            display=True,
        )

        assert result.success
        assert "\\[" in result.output
        assert "\\]" in result.output

    @pytest.mark.asyncio
    async def test_numbered_equation(self, tool):
        """Test numbered equation."""
        result = await tool.execute(
            expression="E = mc^2",
            display=True,
            numbered=True,
        )

        assert result.success
        assert "\\begin{equation}" in result.output
        assert "\\end{equation}" in result.output

    @pytest.mark.asyncio
    async def test_labeled_equation(self, tool):
        """Test equation with label."""
        result = await tool.execute(
            expression="E = mc^2",
            display=True,
            numbered=True,
            label="eq:energy",
        )

        assert result.success
        assert "\\label{eq:energy}" in result.output

    @pytest.mark.asyncio
    async def test_align_environment(self, tool):
        """Test align environment."""
        result = await tool.execute(
            expression="x = 1",
            align=True,
        )

        assert result.success
        assert "\\begin{align*}" in result.output
        assert "\\end{align*}" in result.output

    @pytest.mark.asyncio
    async def test_unicode_greek_letters(self, tool):
        """Test Unicode Greek letter conversion."""
        result = await tool.execute(
            expression="α + β = γ",
        )

        assert result.success
        assert "\\alpha" in result.output
        assert "\\beta" in result.output
        assert "\\gamma" in result.output

    @pytest.mark.asyncio
    async def test_unicode_operators(self, tool):
        """Test Unicode operator conversion."""
        result = await tool.execute(
            expression="∫ x dx = ∞",
        )

        assert result.success
        assert "\\int" in result.output
        assert "\\infty" in result.output

    @pytest.mark.asyncio
    async def test_natural_language_integral(self, tool):
        """Test natural language integral conversion."""
        result = await tool.execute(
            expression="integral from 0 to 1 of x^2 dx",
        )

        assert result.success
        assert "\\int" in result.output
        assert "_{0}" in result.output
        assert "^{1}" in result.output
        assert "d" in result.output

    @pytest.mark.asyncio
    async def test_function_names(self, tool):
        """Test function name formatting."""
        result = await tool.execute(
            expression="sin(x) + cos(x) + log(x)",
        )

        assert result.success
        assert "\\sin" in result.output
        assert "\\cos" in result.output
        assert "\\log" in result.output

    @pytest.mark.asyncio
    async def test_fraction(self, tool):
        """Test fraction conversion."""
        result = await tool.execute(
            expression="a/b",
        )

        assert result.success
        assert "\\frac{a}{b}" in result.output

    @pytest.mark.asyncio
    async def test_metadata_original_expression(self, tool):
        """Test that metadata includes original expression."""
        result = await tool.execute(
            expression="x^2",
            display=True,
        )

        assert result.success
        assert result.metadata["original"] == "x^2"
        assert result.metadata["display_mode"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# GenerateTikzTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateTikzTool:
    """Test suite for TikZ diagram generation."""

    @pytest.fixture
    def tool(self):
        return GenerateTikzTool()

    @pytest.mark.asyncio
    async def test_neural_network_default(self, tool):
        """Test default neural network diagram."""
        result = await tool.execute(
            diagram_type="neural_network",
        )

        assert result.success
        assert "\\begin{tikzpicture}" in result.output
        assert "\\end{tikzpicture}" in result.output
        assert "\\node" in result.output
        assert "\\draw" in result.output

    @pytest.mark.asyncio
    async def test_neural_network_custom_layers(self, tool):
        """Test neural network with custom layers."""
        result = await tool.execute(
            diagram_type="neural_network",
            layers=[3, 5, 5, 2],
            labels=["Input", "Hidden 1", "Hidden 2", "Output"],
        )

        assert result.success
        assert "Input" in result.output
        assert "Hidden 1" in result.output
        assert "Output" in result.output

    @pytest.mark.asyncio
    async def test_graph_basic(self, tool):
        """Test basic graph diagram."""
        result = await tool.execute(
            diagram_type="graph",
            nodes=["A", "B", "C"],
            edges=[["A", "B"], ["B", "C", "edge label"]],
        )

        assert result.success
        assert "\\node (A)" in result.output
        assert "\\draw" in result.output

    @pytest.mark.asyncio
    async def test_flowchart(self, tool):
        """Test flowchart diagram."""
        result = await tool.execute(
            diagram_type="flowchart",
            nodes=["Start", "Process", "End"],
        )

        assert result.success
        assert "startstop" in result.output
        assert "process" in result.output
        assert "\\draw[arrow]" in result.output

    @pytest.mark.asyncio
    async def test_flowchart_decision_detection(self, tool):
        """Test flowchart detects decision nodes."""
        result = await tool.execute(
            diagram_type="flowchart",
            nodes=["Start", "Is valid?", "End"],
        )

        assert result.success
        assert "decision" in result.output

    @pytest.mark.asyncio
    async def test_plot(self, tool):
        """Test function plot."""
        result = await tool.execute(
            diagram_type="plot",
            function="sin(deg(x))",
            x_range=[-3.14, 3.14],
            title="Sine Wave",
        )

        assert result.success
        assert "\\begin{axis}" in result.output
        assert "\\end{axis}" in result.output
        assert "\\addplot" in result.output
        assert "sin(deg(x))" in result.output

    @pytest.mark.asyncio
    async def test_timeline(self, tool):
        """Test timeline diagram."""
        result = await tool.execute(
            diagram_type="timeline",
            events=[
                {"date": "2020", "label": "Project Start"},
                {"date": "2022", "label": "First Release"},
                {"date": "2024", "label": "Major Update"},
            ],
        )

        assert result.success
        assert "2020" in result.output
        assert "Project Start" in result.output
        assert "\\draw[thick, ->]" in result.output

    @pytest.mark.asyncio
    async def test_venn_two_sets(self, tool):
        """Test two-set Venn diagram."""
        result = await tool.execute(
            diagram_type="venn",
            sets=["A", "B"],
        )

        assert result.success
        assert "circle" in result.output
        assert "A" in result.output
        assert "B" in result.output

    @pytest.mark.asyncio
    async def test_venn_three_sets(self, tool):
        """Test three-set Venn diagram."""
        result = await tool.execute(
            diagram_type="venn",
            sets=["X", "Y", "Z"],
        )

        assert result.success
        assert "X" in result.output
        assert "Y" in result.output
        assert "Z" in result.output

    @pytest.mark.asyncio
    async def test_with_title(self, tool):
        """Test diagram with title."""
        result = await tool.execute(
            diagram_type="graph",
            nodes=["A", "B"],
            title="My Graph",
        )

        assert result.success
        assert "\\begin{figure}" in result.output
        assert "\\caption{My Graph}" in result.output
        assert "\\end{figure}" in result.output

    @pytest.mark.asyncio
    async def test_custom_scale(self, tool):
        """Test diagram with custom scale."""
        result = await tool.execute(
            diagram_type="graph",
            scale=1.5,
        )

        assert result.success
        assert "scale=1.5" in result.output

    @pytest.mark.asyncio
    async def test_output_to_file(self, tool):
        """Test saving TikZ to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "diagram.tex"

            result = await tool.execute(
                diagram_type="neural_network",
                output_file=str(output_file),
            )

            assert result.success
            assert output_file.exists()
            content = output_file.read_text()
            assert "\\begin{tikzpicture}" in content

    @pytest.mark.asyncio
    async def test_unsupported_diagram_type(self, tool):
        """Test handling of unsupported diagram type."""
        result = await tool.execute(
            diagram_type="unsupported_type",
        )

        assert not result.success
        assert "Unsupported diagram type" in result.error


# ═══════════════════════════════════════════════════════════════════════════════
# ManageBibliographyTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestManageBibliographyTool:
    """Test suite for bibliography management."""

    @pytest.fixture
    def tool(self):
        return ManageBibliographyTool()

    @pytest.fixture
    def sample_bib_file(self, tmp_path):
        """Create a sample .bib file for testing."""
        content = """@article{smith2023,
  author = {Smith, John and Doe, Jane},
  title = {A Great Paper},
  journal = {Journal of Research},
  year = {2023},
  volume = {42},
}

@book{johnson2022,
  author = {Johnson, Bob},
  title = {The Complete Guide},
  publisher = {Academic Press},
  year = {2022},
}
"""
        file_path = tmp_path / "refs.bib"
        file_path.write_text(content)
        return file_path

    @pytest.mark.asyncio
    async def test_create_bib_file(self, tool, tmp_path):
        """Test creating a new .bib file."""
        output_file = tmp_path / "new_refs.bib"

        result = await tool.execute(
            action="create",
            output_file=str(output_file),
        )

        assert result.success
        assert output_file.exists()
        content = output_file.read_text()
        assert "Bibliography file" in content

    @pytest.mark.asyncio
    async def test_add_article_entry(self, tool, tmp_path):
        """Test adding an article entry."""
        bib_file = tmp_path / "test.bib"
        bib_file.write_text("")

        result = await tool.execute(
            action="add",
            bib_file=str(bib_file),
            entry_type="article",
            author="Einstein, Albert",
            title="On the Electrodynamics of Moving Bodies",
            journal="Annalen der Physik",
            year="1905",
        )

        assert result.success
        content = bib_file.read_text()
        assert "@article{einstein1905" in content
        assert "author = {Einstein, Albert}" in content
        assert "title = {On the Electrodynamics of Moving Bodies}" in content

    @pytest.mark.asyncio
    async def test_add_book_entry(self, tool, tmp_path):
        """Test adding a book entry."""
        bib_file = tmp_path / "test.bib"
        bib_file.write_text("")

        result = await tool.execute(
            action="add",
            bib_file=str(bib_file),
            entry_type="book",
            author="Knuth, Donald",
            title="The Art of Computer Programming",
            publisher="Addison-Wesley",
            year="1968",
        )

        assert result.success
        content = bib_file.read_text()
        assert "@book{knuth1968" in content
        assert "publisher = {Addison-Wesley}" in content

    @pytest.mark.asyncio
    async def test_add_with_custom_key(self, tool, tmp_path):
        """Test adding entry with custom citation key."""
        bib_file = tmp_path / "test.bib"
        bib_file.write_text("")

        result = await tool.execute(
            action="add",
            bib_file=str(bib_file),
            entry_type="article",
            key="custom_key_2024",
            author="Test Author",
            title="Test Title",
            year="2024",
        )

        assert result.success
        content = bib_file.read_text()
        assert "@article{custom_key_2024" in content

    @pytest.mark.asyncio
    async def test_add_with_doi(self, tool, tmp_path):
        """Test adding entry with DOI."""
        bib_file = tmp_path / "test.bib"
        bib_file.write_text("")

        result = await tool.execute(
            action="add",
            bib_file=str(bib_file),
            entry_type="article",
            author="Author",
            title="Title",
            year="2024",
            doi="10.1234/example",
        )

        assert result.success
        content = bib_file.read_text()
        assert "doi = {10.1234/example}" in content

    @pytest.mark.asyncio
    async def test_list_entries(self, tool, sample_bib_file):
        """Test listing bibliography entries."""
        result = await tool.execute(
            action="list",
            bib_file=str(sample_bib_file),
        )

        assert result.success
        assert "smith2023" in result.output
        assert "johnson2022" in result.output
        assert "[article]" in result.output
        assert "[book]" in result.output

    @pytest.mark.asyncio
    async def test_validate_valid_bib(self, tool, sample_bib_file):
        """Test validating a valid .bib file."""
        result = await tool.execute(
            action="validate",
            bib_file=str(sample_bib_file),
        )

        assert result.success
        assert "2 entries" in result.output
        assert result.metadata["entries"] == 2

    @pytest.mark.asyncio
    async def test_validate_missing_fields(self, tool, tmp_path):
        """Test validation detects missing required fields."""
        bib_file = tmp_path / "incomplete.bib"
        bib_file.write_text("""@article{incomplete2024,
  author = {Test Author},
}
""")

        result = await tool.execute(
            action="validate",
            bib_file=str(bib_file),
        )

        assert result.success
        # Should report missing fields (title, journal, year for article)
        assert "missing" in result.output.lower()

    @pytest.mark.asyncio
    async def test_format_bib(self, tool, tmp_path):
        """Test formatting .bib file."""
        bib_file = tmp_path / "messy.bib"
        bib_file.write_text("""@article{test,
  AUTHOR={Test},
    title={Test},year={2024}}
""")

        result = await tool.execute(
            action="format",
            bib_file=str(bib_file),
        )

        assert result.success

    @pytest.mark.asyncio
    async def test_action_requires_bib_file(self, tool):
        """Test that add/list/validate require bib_file."""
        result = await tool.execute(
            action="list",
        )

        assert not result.success
        assert "bib_file is required" in result.error

    @pytest.mark.asyncio
    async def test_add_requires_entry_type(self, tool, tmp_path):
        """Test that add action requires entry_type."""
        bib_file = tmp_path / "test.bib"
        bib_file.write_text("")

        result = await tool.execute(
            action="add",
            bib_file=str(bib_file),
        )

        assert not result.success
        assert "entry_type is required" in result.error


# ═══════════════════════════════════════════════════════════════════════════════
# CreateBeamerTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateBeamerTool:
    """Test suite for Beamer presentation generation."""

    @pytest.fixture
    def tool(self):
        return CreateBeamerTool()

    @pytest.mark.asyncio
    async def test_basic_presentation(self, tool):
        """Test basic presentation generation."""
        result = await tool.execute(
            title="My Talk",
            author="John Smith",
        )

        assert result.success
        assert "\\documentclass{beamer}" in result.output
        assert "\\usetheme{Madrid}" in result.output
        assert "\\title{My Talk}" in result.output
        assert "\\author{John Smith}" in result.output
        assert "\\titlepage" in result.output

    @pytest.mark.asyncio
    async def test_custom_theme(self, tool):
        """Test presentation with custom theme."""
        result = await tool.execute(
            title="Talk",
            theme="Berlin",
        )

        assert result.success
        assert "\\usetheme{Berlin}" in result.output

    @pytest.mark.asyncio
    async def test_color_theme(self, tool):
        """Test presentation with color theme."""
        result = await tool.execute(
            title="Talk",
            color_theme="crane",
        )

        assert result.success
        assert "\\usecolortheme{crane}" in result.output

    @pytest.mark.asyncio
    async def test_with_slides(self, tool):
        """Test presentation with slides."""
        result = await tool.execute(
            title="Workshop",
            slides=["Introduction", "Demo", "Questions"],
        )

        assert result.success
        assert "\\begin{frame}{Introduction}" in result.output
        assert "\\begin{frame}{Demo}" in result.output
        assert "\\begin{frame}{Questions}" in result.output
        assert "\\begin{itemize}" in result.output

    @pytest.mark.asyncio
    async def test_with_sections(self, tool):
        """Test presentation with sections."""
        result = await tool.execute(
            title="Conference Talk",
            sections=[
                {"title": "Part 1", "slides": ["Overview", "Details"]},
                {"title": "Part 2", "slides": ["More Info"]},
            ],
        )

        assert result.success
        assert "\\section{Part 1}" in result.output
        assert "\\section{Part 2}" in result.output
        assert "\\begin{frame}{Overview}" in result.output

    @pytest.mark.asyncio
    async def test_with_subtitle_and_institute(self, tool):
        """Test presentation with subtitle and institute."""
        result = await tool.execute(
            title="Research Presentation",
            subtitle="A Deep Dive",
            institute="University of Testing",
        )

        assert result.success
        assert "\\subtitle{A Deep Dive}" in result.output
        assert "\\institute{University of Testing}" in result.output

    @pytest.mark.asyncio
    async def test_table_of_contents(self, tool):
        """Test presentation with table of contents."""
        result = await tool.execute(
            title="Talk",
            toc=True,
        )

        assert result.success
        assert "\\tableofcontents" in result.output

    @pytest.mark.asyncio
    async def test_no_table_of_contents(self, tool):
        """Test presentation without table of contents."""
        result = await tool.execute(
            title="Talk",
            toc=False,
        )

        assert result.success
        assert "\\tableofcontents" not in result.output

    @pytest.mark.asyncio
    async def test_includes_packages(self, tool):
        """Test that standard packages are included."""
        result = await tool.execute(title="Talk")

        assert result.success
        assert "\\usepackage{amsmath}" in result.output
        assert "\\usepackage{graphicx}" in result.output
        assert "\\usepackage{listings}" in result.output

    @pytest.mark.asyncio
    async def test_output_to_file(self, tool):
        """Test saving presentation to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "slides.tex"

            result = await tool.execute(
                title="Saved Presentation",
                output_file=str(output_file),
            )

            assert result.success
            assert output_file.exists()
            content = output_file.read_text()
            assert "\\documentclass{beamer}" in content

    @pytest.mark.asyncio
    async def test_metadata(self, tool):
        """Test that metadata includes theme."""
        result = await tool.execute(
            title="Talk",
            theme="Warsaw",
        )

        assert result.success
        assert result.metadata["theme"] == "Warsaw"


# ═══════════════════════════════════════════════════════════════════════════════
# LatexToPdfTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestLatexToPdfTool:
    """Test suite for LaTeX compilation."""

    @pytest.fixture
    def tool(self):
        return LatexToPdfTool()

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test handling of non-existent file."""
        result = await tool.execute(
            input_file="/nonexistent/file.tex",
        )

        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_latex_not_installed(self, tool, tmp_path):
        """Test handling when LaTeX is not installed."""
        # Create a minimal .tex file
        tex_file = tmp_path / "test.tex"
        tex_file.write_text("\\documentclass{article}\\begin{document}Test\\end{document}")

        result = await tool.execute(
            input_file=str(tex_file),
            engine="nonexistent_engine",
        )

        # Should fail because the engine doesn't exist
        assert not result.success

    # Note: Full compilation tests would require LaTeX to be installed
    # These tests focus on error handling and basic validation


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestLatexToolsIntegration:
    """Integration tests for LaTeX tools."""

    @pytest.mark.asyncio
    async def test_tools_registered(self):
        """Test that all LaTeX tools are registered in the registry."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()

        assert registry.get_tool("generate_latex") is not None
        assert registry.get_tool("format_equations") is not None
        assert registry.get_tool("generate_tikz") is not None
        assert registry.get_tool("manage_bibliography") is not None
        assert registry.get_tool("create_beamer") is not None
        assert registry.get_tool("latex_to_pdf") is not None

    @pytest.mark.asyncio
    async def test_kvasir_agent_exists(self):
        """Test that Kvasir agent is defined in the registry."""
        from sindri.agents.registry import AGENTS, get_agent

        assert "kvasir" in AGENTS

        kvasir = get_agent("kvasir")
        assert kvasir.name == "kvasir"
        assert "latex" in kvasir.role.lower()
        assert "generate_latex" in kvasir.tools
        assert "format_equations" in kvasir.tools
        assert "generate_tikz" in kvasir.tools
        assert "manage_bibliography" in kvasir.tools
        assert "create_beamer" in kvasir.tools

    @pytest.mark.asyncio
    async def test_brokkr_can_delegate_to_kvasir(self):
        """Test that Brokkr can delegate to Kvasir."""
        from sindri.agents.registry import get_agent

        brokkr = get_agent("brokkr")
        assert "kvasir" in brokkr.delegate_to

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test a complete workflow: document, equations, and bibliography."""
        from sindri.tools.latex import (
            GenerateLatexTool,
            FormatEquationsTool,
            ManageBibliographyTool,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create bibliography
            bib_tool = ManageBibliographyTool(work_dir=tmpdir)
            bib_result = await bib_tool.execute(
                action="create",
                output_file="refs.bib",
            )
            assert bib_result.success

            # Add an entry
            add_result = await bib_tool.execute(
                action="add",
                bib_file="refs.bib",
                entry_type="article",
                author="Test Author",
                title="Test Paper",
                journal="Test Journal",
                year="2024",
            )
            assert add_result.success

            # Format an equation
            eq_tool = FormatEquationsTool()
            eq_result = await eq_tool.execute(
                expression="E = mc^2",
                display=True,
            )
            assert eq_result.success

            # Generate document
            doc_tool = GenerateLatexTool(work_dir=tmpdir)
            doc_result = await doc_tool.execute(
                title="Complete Document",
                author="Test Author",
                sections=["Introduction", "Theory", "Conclusion"],
                bibliography_file="refs.bib",
                output_file="paper.tex",
            )
            assert doc_result.success

            # Verify files exist
            assert (tmpdir / "refs.bib").exists()
            assert (tmpdir / "paper.tex").exists()
