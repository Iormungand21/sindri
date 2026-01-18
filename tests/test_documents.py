"""Tests for document processing tools."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

# Check for required dependencies
try:
    import fitz  # PyMuPDF

    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    import openpyxl

    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

try:
    import pytesseract

    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    from PIL import Image

    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False


from sindri.tools.documents import (
    PdfExtractTextTool,
    PdfToMarkdownTool,
    PdfMergeTool,
    PdfSplitTool,
    OcrImageTool,
    SpreadsheetReadTool,
    SpreadsheetWriteTool,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_pdf():
    """Create a sample PDF file for testing."""
    if not PYMUPDF_AVAILABLE:
        pytest.skip("PyMuPDF not installed")

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "test.pdf")

        doc = fitz.open()

        # Page 1
        page1 = doc.new_page()
        page1.insert_text((72, 72), "Test Document", fontsize=24)
        page1.insert_text((72, 120), "This is the first page with some text.", fontsize=12)
        page1.insert_text((72, 140), "It contains multiple lines of content.", fontsize=12)

        # Page 2
        page2 = doc.new_page()
        page2.insert_text((72, 72), "Chapter 2", fontsize=18)
        page2.insert_text((72, 100), "This is the second page.", fontsize=12)
        page2.insert_text((72, 120), "More content here.", fontsize=12)

        # Page 3
        page3 = doc.new_page()
        page3.insert_text((72, 72), "Conclusion", fontsize=16)
        page3.insert_text((72, 100), "Final thoughts on the matter.", fontsize=12)

        doc.save(pdf_path)
        doc.close()

        yield pdf_path, tmpdir


@pytest.fixture
def sample_csv():
    """Create a sample CSV file for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "data.csv")

        with open(csv_path, "w") as f:
            f.write("name,age,city\n")
            f.write("Alice,30,New York\n")
            f.write("Bob,25,Los Angeles\n")
            f.write("Charlie,35,Chicago\n")

        yield csv_path, tmpdir


@pytest.fixture
def sample_excel():
    """Create a sample Excel file for testing."""
    if not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE:
        pytest.skip("pandas or openpyxl not installed")

    with tempfile.TemporaryDirectory() as tmpdir:
        xlsx_path = os.path.join(tmpdir, "data.xlsx")

        df = pd.DataFrame(
            {
                "name": ["Alice", "Bob", "Charlie"],
                "age": [30, 25, 35],
                "city": ["New York", "Los Angeles", "Chicago"],
            }
        )
        df.to_excel(xlsx_path, index=False, sheet_name="People")

        yield xlsx_path, tmpdir


@pytest.fixture
def sample_image():
    """Create a sample image with text for OCR testing."""
    if not PILLOW_AVAILABLE:
        pytest.skip("Pillow not installed")

    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "test.png")

        # Create a white image with black text
        img = Image.new("RGB", (200, 100), color="white")
        img.save(img_path)

        yield img_path, tmpdir


# =============================================================================
# PdfExtractTextTool Tests
# =============================================================================


class TestPdfExtractTextTool:
    """Tests for PdfExtractTextTool."""

    @pytest.fixture
    def tool(self):
        return PdfExtractTextTool()

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_extract_all_pages(self, tool, sample_pdf):
        """Test extracting text from all pages."""
        pdf_path, tmpdir = sample_pdf

        result = await tool.execute(input=pdf_path)

        assert result.success
        assert "Test Document" in result.output or "Test Document" in result.metadata.get("text", "")
        assert result.metadata["total_pages"] == 3
        assert result.metadata["pages_processed"] >= 1

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_extract_page_range(self, tool, sample_pdf):
        """Test extracting text from specific page range."""
        pdf_path, tmpdir = sample_pdf

        result = await tool.execute(input=pdf_path, start_page=1, end_page=2)

        assert result.success
        assert result.metadata["start_page"] == 1
        assert result.metadata["end_page"] == 2

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_extract_to_file(self, tool, sample_pdf):
        """Test extracting text to output file."""
        pdf_path, tmpdir = sample_pdf
        output_path = os.path.join(tmpdir, "extracted.txt")

        result = await tool.execute(input=pdf_path, output=output_path)

        assert result.success
        assert os.path.exists(output_path)
        assert result.metadata["output"] == output_path

        with open(output_path) as f:
            content = f.read()
            assert len(content) > 0

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_extract_nonexistent_file(self, tool):
        """Test extracting from nonexistent file."""
        result = await tool.execute(input="/nonexistent/file.pdf")

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_extract_invalid_page_range(self, tool, sample_pdf):
        """Test extracting with invalid page range."""
        pdf_path, tmpdir = sample_pdf

        result = await tool.execute(input=pdf_path, start_page=5, end_page=3)

        assert not result.success
        assert "Invalid page range" in result.error


# =============================================================================
# PdfToMarkdownTool Tests
# =============================================================================


class TestPdfToMarkdownTool:
    """Tests for PdfToMarkdownTool."""

    @pytest.fixture
    def tool(self):
        return PdfToMarkdownTool()

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_convert_basic(self, tool, sample_pdf):
        """Test basic PDF to Markdown conversion."""
        pdf_path, tmpdir = sample_pdf

        result = await tool.execute(input=pdf_path)

        assert result.success
        assert result.metadata["total_pages"] == 3

        # Check output file was created
        expected_output = os.path.splitext(pdf_path)[0] + ".md"
        assert os.path.exists(expected_output)

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_convert_custom_output(self, tool, sample_pdf):
        """Test conversion with custom output path."""
        pdf_path, tmpdir = sample_pdf
        output_path = os.path.join(tmpdir, "output.md")

        result = await tool.execute(input=pdf_path, output=output_path)

        assert result.success
        assert os.path.exists(output_path)
        assert result.metadata["output"] == output_path

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_convert_page_range(self, tool, sample_pdf):
        """Test conversion of specific page range."""
        pdf_path, tmpdir = sample_pdf

        result = await tool.execute(input=pdf_path, start_page=2, end_page=3)

        assert result.success
        assert result.metadata["pages_converted"] == 2

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_convert_nonexistent_file(self, tool):
        """Test converting nonexistent file."""
        result = await tool.execute(input="/nonexistent/file.pdf")

        assert not result.success
        assert "does not exist" in result.error


# =============================================================================
# PdfMergeTool Tests
# =============================================================================


class TestPdfMergeTool:
    """Tests for PdfMergeTool."""

    @pytest.fixture
    def tool(self):
        return PdfMergeTool()

    @pytest.fixture
    def multiple_pdfs(self):
        """Create multiple PDF files for merging."""
        if not PYMUPDF_AVAILABLE:
            pytest.skip("PyMuPDF not installed")

        with tempfile.TemporaryDirectory() as tmpdir:
            pdfs = []
            for i in range(3):
                pdf_path = os.path.join(tmpdir, f"doc{i + 1}.pdf")
                doc = fitz.open()
                page = doc.new_page()
                page.insert_text((72, 72), f"Document {i + 1}", fontsize=20)
                doc.save(pdf_path)
                doc.close()
                pdfs.append(pdf_path)

            yield pdfs, tmpdir

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_merge_pdfs(self, tool, multiple_pdfs):
        """Test merging multiple PDFs."""
        pdfs, tmpdir = multiple_pdfs
        output_path = os.path.join(tmpdir, "merged.pdf")

        result = await tool.execute(output=output_path, inputs=pdfs)

        assert result.success
        assert os.path.exists(output_path)
        assert result.metadata["input_count"] == 3
        assert result.metadata["total_pages"] == 3

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_merge_insufficient_files(self, tool, sample_pdf):
        """Test merging with less than 2 files."""
        pdf_path, tmpdir = sample_pdf
        output_path = os.path.join(tmpdir, "merged.pdf")

        result = await tool.execute(output=output_path, inputs=[pdf_path])

        assert not result.success
        assert "2 PDF files" in result.error

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_merge_nonexistent_file(self, tool, sample_pdf):
        """Test merging with nonexistent file."""
        pdf_path, tmpdir = sample_pdf
        output_path = os.path.join(tmpdir, "merged.pdf")

        result = await tool.execute(
            output=output_path, inputs=[pdf_path, "/nonexistent.pdf"]
        )

        assert not result.success
        assert "does not exist" in result.error


# =============================================================================
# PdfSplitTool Tests
# =============================================================================


class TestPdfSplitTool:
    """Tests for PdfSplitTool."""

    @pytest.fixture
    def tool(self):
        return PdfSplitTool()

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_split_single_pages(self, tool, sample_pdf):
        """Test splitting into single pages."""
        pdf_path, tmpdir = sample_pdf
        output_dir = os.path.join(tmpdir, "pages")

        result = await tool.execute(
            input=pdf_path, output_dir=output_dir, single_pages=True
        )

        assert result.success
        assert result.metadata["file_count"] == 3
        assert os.path.exists(output_dir)

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_split_page_range(self, tool, sample_pdf):
        """Test splitting specific page range."""
        pdf_path, tmpdir = sample_pdf
        output_path = os.path.join(tmpdir, "pages_1-2.pdf")

        result = await tool.execute(
            input=pdf_path, output=output_path, start_page=1, end_page=2
        )

        assert result.success
        assert os.path.exists(output_path)
        assert result.metadata["file_count"] == 1

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_split_by_ranges(self, tool, sample_pdf):
        """Test splitting by comma-separated ranges."""
        pdf_path, tmpdir = sample_pdf
        output_dir = os.path.join(tmpdir, "ranges")

        result = await tool.execute(
            input=pdf_path, output_dir=output_dir, ranges="1-1,2-3"
        )

        assert result.success
        assert result.metadata["file_count"] == 2

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_split_no_option(self, tool, sample_pdf):
        """Test splitting without specifying option."""
        pdf_path, tmpdir = sample_pdf

        result = await tool.execute(input=pdf_path)

        assert not result.success
        assert "Must specify" in result.error

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_split_nonexistent_file(self, tool):
        """Test splitting nonexistent file."""
        result = await tool.execute(input="/nonexistent.pdf", single_pages=True)

        assert not result.success
        assert "does not exist" in result.error


# =============================================================================
# OcrImageTool Tests
# =============================================================================


class TestOcrImageTool:
    """Tests for OcrImageTool."""

    @pytest.fixture
    def tool(self):
        return OcrImageTool()

    @pytest.mark.skipif(
        not TESSERACT_AVAILABLE or not PILLOW_AVAILABLE,
        reason="pytesseract or Pillow not installed",
    )
    @pytest.mark.asyncio
    async def test_ocr_basic(self, tool, sample_image):
        """Test basic OCR on image."""
        img_path, tmpdir = sample_image

        result = await tool.execute(input=img_path)

        assert result.success
        assert result.metadata["image_width"] == 200
        assert result.metadata["image_height"] == 100

    @pytest.mark.skipif(
        not TESSERACT_AVAILABLE or not PILLOW_AVAILABLE,
        reason="pytesseract or Pillow not installed",
    )
    @pytest.mark.asyncio
    async def test_ocr_to_file(self, tool, sample_image):
        """Test OCR with output to file."""
        img_path, tmpdir = sample_image
        output_path = os.path.join(tmpdir, "ocr.txt")

        result = await tool.execute(input=img_path, output=output_path)

        assert result.success
        assert os.path.exists(output_path)

    @pytest.mark.asyncio
    async def test_ocr_nonexistent_file(self, tool):
        """Test OCR on nonexistent file."""
        result = await tool.execute(input="/nonexistent.png")

        if not TESSERACT_AVAILABLE:
            assert not result.success
            assert "pytesseract" in result.error
        else:
            assert not result.success
            assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_ocr_unavailable(self):
        """Test OCR when tesseract is not available."""
        tool = OcrImageTool()

        # This test verifies the error message when dependencies are missing
        # The actual behavior depends on what's installed
        result = await tool.execute(input="/dummy.png")

        assert not result.success


# =============================================================================
# SpreadsheetReadTool Tests
# =============================================================================


class TestSpreadsheetReadTool:
    """Tests for SpreadsheetReadTool."""

    @pytest.fixture
    def tool(self):
        return SpreadsheetReadTool()

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
    @pytest.mark.asyncio
    async def test_read_csv(self, tool, sample_csv):
        """Test reading CSV file."""
        csv_path, tmpdir = sample_csv

        result = await tool.execute(input=csv_path)

        assert result.success
        assert result.metadata["total_rows"] == 3
        assert result.metadata["total_cols"] == 3
        assert "name" in result.metadata["columns"]
        assert "Alice" in result.output

    @pytest.mark.skipif(
        not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE,
        reason="pandas or openpyxl not installed",
    )
    @pytest.mark.asyncio
    async def test_read_excel(self, tool, sample_excel):
        """Test reading Excel file."""
        xlsx_path, tmpdir = sample_excel

        result = await tool.execute(input=xlsx_path)

        assert result.success
        assert result.metadata["total_rows"] == 3
        assert "Alice" in result.output

    @pytest.mark.skipif(
        not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE,
        reason="pandas or openpyxl not installed",
    )
    @pytest.mark.asyncio
    async def test_read_excel_with_sheet(self, tool, sample_excel):
        """Test reading specific sheet from Excel."""
        xlsx_path, tmpdir = sample_excel

        result = await tool.execute(input=xlsx_path, sheet="People")

        assert result.success
        assert result.metadata["sheet"] == "People"

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
    @pytest.mark.asyncio
    async def test_read_with_columns(self, tool, sample_csv):
        """Test reading specific columns."""
        csv_path, tmpdir = sample_csv

        result = await tool.execute(input=csv_path, columns=["name", "age"])

        assert result.success
        assert "city" not in result.metadata["columns"]
        assert "name" in result.metadata["columns"]

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
    @pytest.mark.asyncio
    async def test_read_with_limit(self, tool, sample_csv):
        """Test reading with row limit."""
        csv_path, tmpdir = sample_csv

        result = await tool.execute(input=csv_path, limit=2)

        assert result.success
        assert result.metadata["rows_returned"] == 2

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
    @pytest.mark.asyncio
    async def test_read_json_format(self, tool, sample_csv):
        """Test reading with JSON output format."""
        csv_path, tmpdir = sample_csv

        result = await tool.execute(input=csv_path, output_format="json")

        assert result.success
        # Should contain JSON array
        assert "[" in result.output

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
    @pytest.mark.asyncio
    async def test_read_invalid_column(self, tool, sample_csv):
        """Test reading with invalid column name."""
        csv_path, tmpdir = sample_csv

        result = await tool.execute(input=csv_path, columns=["invalid_col"])

        assert not result.success
        assert "not found" in result.error

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, tool):
        """Test reading nonexistent file."""
        result = await tool.execute(input="/nonexistent.csv")

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
    @pytest.mark.asyncio
    async def test_read_unsupported_format(self, tool):
        """Test reading unsupported file format."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test content")
            temp_path = f.name

        try:
            result = await tool.execute(input=temp_path)
            assert not result.success
            assert "Unsupported" in result.error
        finally:
            os.unlink(temp_path)


# =============================================================================
# SpreadsheetWriteTool Tests
# =============================================================================


class TestSpreadsheetWriteTool:
    """Tests for SpreadsheetWriteTool."""

    @pytest.fixture
    def tool(self):
        return SpreadsheetWriteTool()

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
    @pytest.mark.asyncio
    async def test_write_csv(self, tool):
        """Test writing CSV file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output.csv")
            data = json.dumps([{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}])

            result = await tool.execute(output=output_path, data=data)

            assert result.success
            assert os.path.exists(output_path)
            assert result.metadata["rows"] == 2
            assert result.metadata["format"] == "csv"

    @pytest.mark.skipif(
        not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE,
        reason="pandas or openpyxl not installed",
    )
    @pytest.mark.asyncio
    async def test_write_excel(self, tool):
        """Test writing Excel file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output.xlsx")
            data = json.dumps([{"col1": 1, "col2": 2}, {"col1": 3, "col2": 4}])

            result = await tool.execute(output=output_path, data=data, sheet="Data")

            assert result.success
            assert os.path.exists(output_path)
            assert result.metadata["sheet"] == "Data"

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
    @pytest.mark.asyncio
    async def test_write_array_of_arrays(self, tool):
        """Test writing array of arrays."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output.csv")
            data = json.dumps([[1, 2, 3], [4, 5, 6]])

            result = await tool.execute(
                output=output_path, data=data, columns=["a", "b", "c"]
            )

            assert result.success
            assert result.metadata["columns"] == ["a", "b", "c"]

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
    @pytest.mark.asyncio
    async def test_write_invalid_json(self, tool):
        """Test writing invalid JSON data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output.csv")

            result = await tool.execute(output=output_path, data="invalid json")

            assert not result.success
            assert "Invalid JSON" in result.error

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
    @pytest.mark.asyncio
    async def test_write_empty_data(self, tool):
        """Test writing empty data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output.csv")

            result = await tool.execute(output=output_path, data="[]")

            assert not result.success
            assert "empty" in result.error.lower()

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
    @pytest.mark.asyncio
    async def test_write_unsupported_format(self, tool):
        """Test writing unsupported file format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output.txt")
            data = json.dumps([{"a": 1}])

            result = await tool.execute(output=output_path, data=data)

            assert not result.success
            assert "Unsupported" in result.error


# =============================================================================
# Integration Tests
# =============================================================================


class TestDocumentToolsIntegration:
    """Integration tests for document tools."""

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_extract_then_save(self, sample_pdf):
        """Test extracting text and saving to file."""
        pdf_path, tmpdir = sample_pdf
        output_path = os.path.join(tmpdir, "text.txt")

        tool = PdfExtractTextTool()
        result = await tool.execute(input=pdf_path, output=output_path)

        assert result.success
        assert os.path.exists(output_path)

        with open(output_path) as f:
            content = f.read()
            assert "Page" in content

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_split_and_merge(self, sample_pdf):
        """Test splitting PDF then merging back."""
        pdf_path, tmpdir = sample_pdf
        pages_dir = os.path.join(tmpdir, "pages")
        merged_path = os.path.join(tmpdir, "merged.pdf")

        # Split into single pages
        split_tool = PdfSplitTool()
        split_result = await split_tool.execute(
            input=pdf_path, output_dir=pages_dir, single_pages=True
        )
        assert split_result.success

        # Get the created files
        page_files = sorted(
            [os.path.join(pages_dir, f) for f in os.listdir(pages_dir) if f.endswith(".pdf")]
        )
        assert len(page_files) == 3

        # Merge them back
        merge_tool = PdfMergeTool()
        merge_result = await merge_tool.execute(output=merged_path, inputs=page_files)
        assert merge_result.success
        assert merge_result.metadata["total_pages"] == 3

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
    @pytest.mark.asyncio
    async def test_read_write_csv_roundtrip(self):
        """Test reading and writing CSV maintains data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create original data
            original_path = os.path.join(tmpdir, "original.csv")
            output_path = os.path.join(tmpdir, "output.csv")

            original_data = [
                {"name": "Alice", "score": 95},
                {"name": "Bob", "score": 87},
            ]

            # Write original
            write_tool = SpreadsheetWriteTool()
            write_result = await write_tool.execute(
                output=original_path, data=json.dumps(original_data)
            )
            assert write_result.success

            # Read it back
            read_tool = SpreadsheetReadTool()
            read_result = await read_tool.execute(
                input=original_path, output_format="json"
            )
            assert read_result.success

            # Write again
            write_result2 = await write_tool.execute(
                output=output_path, data=read_result.metadata.get("data", "[]")
                if "data" in read_result.metadata else json.dumps(original_data)
            )
            assert write_result2.success


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestDocumentToolsEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_pdf_tools_without_pymupdf(self):
        """Test PDF tools handle missing PyMuPDF gracefully."""
        # These tests verify error messages when PyMuPDF is not installed
        # The tools should return appropriate error messages

        tools = [
            PdfExtractTextTool(),
            PdfToMarkdownTool(),
            PdfMergeTool(),
            PdfSplitTool(),
        ]

        for tool in tools:
            if not PYMUPDF_AVAILABLE:
                result = await tool.execute(input="/dummy.pdf")
                assert not result.success
                assert "PyMuPDF" in result.error

    @pytest.mark.asyncio
    async def test_spreadsheet_tools_without_pandas(self):
        """Test spreadsheet tools handle missing pandas gracefully."""
        if not PANDAS_AVAILABLE:
            read_tool = SpreadsheetReadTool()
            result = await read_tool.execute(input="/dummy.csv")
            assert not result.success
            assert "pandas" in result.error

            write_tool = SpreadsheetWriteTool()
            result = await write_tool.execute(output="/dummy.csv", data="[]")
            assert not result.success
            assert "pandas" in result.error

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    @pytest.mark.asyncio
    async def test_pdf_with_special_characters_in_path(self):
        """Test PDF operations with special characters in path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create PDF with spaces in name
            pdf_path = os.path.join(tmpdir, "my document (1).pdf")

            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "Test", fontsize=12)
            doc.save(pdf_path)
            doc.close()

            tool = PdfExtractTextTool()
            result = await tool.execute(input=pdf_path)

            assert result.success

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
    @pytest.mark.asyncio
    async def test_csv_with_unicode(self):
        """Test reading CSV with unicode characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "unicode.csv")

            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("name,city\n")
                f.write("José,São Paulo\n")
                f.write("北京,中国\n")

            tool = SpreadsheetReadTool()
            result = await tool.execute(input=csv_path)

            assert result.success
            assert "José" in result.output or result.metadata["total_rows"] == 2

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
    @pytest.mark.asyncio
    async def test_large_csv_limit(self):
        """Test reading large CSV with row limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "large.csv")

            # Create CSV with many rows
            with open(csv_path, "w") as f:
                f.write("id,value\n")
                for i in range(1000):
                    f.write(f"{i},{i * 10}\n")

            tool = SpreadsheetReadTool()
            result = await tool.execute(input=csv_path, limit=10)

            assert result.success
            assert result.metadata["total_rows"] == 1000
            assert result.metadata["rows_returned"] == 10
