"""Tests for vision-based document processing tools (Phase 12).

Tests for Groa agent's vision document tools: document_describe,
document_extract_structured, document_summarize.
"""

import base64
import json
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from sindri.tools.vision_documents import (
    DocumentDescribeTool,
    DocumentExtractStructuredTool,
    DocumentSummarizeTool,
    _image_to_base64,
    _is_pdf,
    _is_image,
    _get_supported_image_extensions,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper Function Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestHelperFunctions:
    """Test helper functions for vision document tools."""

    def test_is_pdf_true(self):
        """Test _is_pdf returns True for PDF files."""
        assert _is_pdf(Path("document.pdf")) is True
        assert _is_pdf(Path("DOCUMENT.PDF")) is True
        assert _is_pdf(Path("/path/to/file.pdf")) is True

    def test_is_pdf_false(self):
        """Test _is_pdf returns False for non-PDF files."""
        assert _is_pdf(Path("document.png")) is False
        assert _is_pdf(Path("document.jpg")) is False
        assert _is_pdf(Path("document.txt")) is False

    def test_is_image_true(self):
        """Test _is_image returns True for image files."""
        assert _is_image(Path("image.png")) is True
        assert _is_image(Path("image.jpg")) is True
        assert _is_image(Path("image.jpeg")) is True
        assert _is_image(Path("image.gif")) is True
        assert _is_image(Path("image.webp")) is True
        assert _is_image(Path("IMAGE.PNG")) is True

    def test_is_image_false(self):
        """Test _is_image returns False for non-image files."""
        assert _is_image(Path("document.pdf")) is False
        assert _is_image(Path("document.txt")) is False
        assert _is_image(Path("document.doc")) is False

    def test_get_supported_image_extensions(self):
        """Test that all common image extensions are supported."""
        extensions = _get_supported_image_extensions()
        assert ".png" in extensions
        assert ".jpg" in extensions
        assert ".jpeg" in extensions
        assert ".gif" in extensions
        assert ".webp" in extensions
        assert ".bmp" in extensions

    def test_image_to_base64(self, tmp_path):
        """Test _image_to_base64 encodes files correctly."""
        # Create a simple test file
        test_file = tmp_path / "test.txt"
        test_content = b"Hello, World!"
        test_file.write_bytes(test_content)

        result = _image_to_base64(test_file)

        # Verify it's valid base64 that decodes to original content
        decoded = base64.b64decode(result)
        assert decoded == test_content


# ═══════════════════════════════════════════════════════════════════════════════
# DocumentDescribeTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDocumentDescribeTool:
    """Test suite for document description using vision model."""

    @pytest.fixture
    def tool(self, tmp_path):
        return DocumentDescribeTool(work_dir=tmp_path)

    @pytest.fixture
    def sample_image(self, tmp_path):
        """Create a simple test image file."""
        # Create a minimal valid PNG file (1x1 pixel)
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        img_path = tmp_path / "test_image.png"
        img_path.write_bytes(png_data)
        return img_path

    @pytest.mark.asyncio
    async def test_describe_missing_file(self, tool):
        """Test describing a file that doesn't exist."""
        result = await tool.execute(input="nonexistent.pdf")

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_describe_unsupported_format(self, tool, tmp_path):
        """Test describing a file with unsupported format."""
        unsupported = tmp_path / "test.xyz"
        unsupported.write_text("test content")

        result = await tool.execute(input=str(unsupported))

        assert not result.success
        assert "Unsupported file type" in result.error

    @pytest.mark.asyncio
    async def test_describe_image_success(self, tool, sample_image):
        """Test successful image description with mocked vision model."""
        mock_description = "This is a simple 1x1 pixel image."

        with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
            with patch("sindri.tools.vision_documents._call_vision_model", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = mock_description

                result = await tool.execute(input=str(sample_image))

                assert result.success
                assert mock_description in result.output
                assert result.metadata["input"] == str(sample_image)
                assert result.metadata["detail_level"] == "detailed"

    @pytest.mark.asyncio
    async def test_describe_with_custom_prompt(self, tool, sample_image):
        """Test description with custom prompt."""
        custom_prompt = "What colors are in this image?"
        mock_description = "The image contains a single white pixel."

        with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
            with patch("sindri.tools.vision_documents._call_vision_model", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = mock_description

                result = await tool.execute(input=str(sample_image), prompt=custom_prompt)

                assert result.success
                # Verify custom prompt was passed
                mock_call.assert_called_once()
                assert mock_call.call_args[0][0] == custom_prompt

    @pytest.mark.asyncio
    async def test_describe_detail_levels(self, tool, sample_image):
        """Test different detail levels."""
        for detail_level in ["brief", "detailed", "comprehensive"]:
            with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
                with patch("sindri.tools.vision_documents._call_vision_model", new_callable=AsyncMock) as mock_call:
                    mock_call.return_value = f"Description with {detail_level} detail"

                    result = await tool.execute(input=str(sample_image), detail_level=detail_level)

                    assert result.success
                    assert result.metadata["detail_level"] == detail_level

    @pytest.mark.asyncio
    async def test_describe_ollama_unavailable(self, tool, sample_image):
        """Test behavior when ollama is not available."""
        with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", False):
            result = await tool.execute(input=str(sample_image))

            assert not result.success
            assert "ollama package not installed" in result.error


# ═══════════════════════════════════════════════════════════════════════════════
# DocumentExtractStructuredTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDocumentExtractStructuredTool:
    """Test suite for structured data extraction."""

    @pytest.fixture
    def tool(self, tmp_path):
        return DocumentExtractStructuredTool(work_dir=tmp_path)

    @pytest.fixture
    def sample_image(self, tmp_path):
        """Create a simple test image file."""
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        img_path = tmp_path / "test_form.png"
        img_path.write_bytes(png_data)
        return img_path

    @pytest.mark.asyncio
    async def test_extract_missing_file(self, tool):
        """Test extracting from a file that doesn't exist."""
        result = await tool.execute(input="nonexistent.pdf")

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_extract_table_json(self, tool, sample_image):
        """Test table extraction with JSON output."""
        mock_json = json.dumps({
            "headers": ["Name", "Age", "City"],
            "rows": [
                ["Alice", "30", "NYC"],
                ["Bob", "25", "LA"]
            ]
        })

        with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
            with patch("sindri.tools.vision_documents._call_vision_model", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = mock_json

                result = await tool.execute(
                    input=str(sample_image),
                    extract_type="table",
                    output_format="json"
                )

                assert result.success
                assert "Alice" in result.output
                assert result.metadata["extract_type"] == "table"
                assert result.metadata["output_format"] == "json"

    @pytest.mark.asyncio
    async def test_extract_key_value(self, tool, sample_image):
        """Test key-value extraction from invoice-like document."""
        mock_json = json.dumps({
            "Invoice Number": "INV-001",
            "Date": "2024-01-15",
            "Total": "$150.00"
        })

        with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
            with patch("sindri.tools.vision_documents._call_vision_model", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = mock_json

                result = await tool.execute(
                    input=str(sample_image),
                    extract_type="key_value"
                )

                assert result.success
                assert "INV-001" in result.output
                assert result.metadata["data"]["Invoice Number"] == "INV-001"

    @pytest.mark.asyncio
    async def test_extract_form_fields(self, tool, sample_image):
        """Test form field extraction."""
        mock_json = json.dumps({
            "First Name": "John",
            "Last Name": "Doe",
            "Email": "john@example.com",
            "Phone": None
        })

        with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
            with patch("sindri.tools.vision_documents._call_vision_model", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = mock_json

                result = await tool.execute(
                    input=str(sample_image),
                    extract_type="form_fields"
                )

                assert result.success
                assert "John" in result.output
                assert result.metadata["extract_type"] == "form_fields"

    @pytest.mark.asyncio
    async def test_extract_csv_output(self, tool, sample_image):
        """Test extraction with CSV output format."""
        mock_json = json.dumps({
            "headers": ["Product", "Price"],
            "rows": [["Apple", "1.00"], ["Banana", "0.50"]]
        })

        with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
            with patch("sindri.tools.vision_documents._call_vision_model", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = mock_json

                result = await tool.execute(
                    input=str(sample_image),
                    extract_type="table",
                    output_format="csv"
                )

                assert result.success
                assert "Product" in result.output
                assert "Apple" in result.output
                assert result.metadata["output_format"] == "csv"

    @pytest.mark.asyncio
    async def test_extract_markdown_output(self, tool, sample_image):
        """Test extraction with markdown output format."""
        mock_json = json.dumps({
            "headers": ["Name", "Value"],
            "rows": [["foo", "bar"]]
        })

        with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
            with patch("sindri.tools.vision_documents._call_vision_model", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = mock_json

                result = await tool.execute(
                    input=str(sample_image),
                    extract_type="table",
                    output_format="markdown"
                )

                assert result.success
                assert "|" in result.output  # Markdown table syntax
                assert result.metadata["output_format"] == "markdown"

    @pytest.mark.asyncio
    async def test_extract_auto_detection(self, tool, sample_image):
        """Test auto-detection of data type."""
        mock_json = json.dumps({
            "tables": [{"headers": ["A"], "rows": [["1"]]}],
            "metadata": {"document_type": "report"}
        })

        with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
            with patch("sindri.tools.vision_documents._call_vision_model", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = mock_json

                result = await tool.execute(
                    input=str(sample_image),
                    extract_type="auto"
                )

                assert result.success
                assert result.metadata["extract_type"] == "auto"

    @pytest.mark.asyncio
    async def test_extract_json_parse_failure(self, tool, sample_image):
        """Test handling of invalid JSON from vision model."""
        with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
            with patch("sindri.tools.vision_documents._call_vision_model", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = "This is not valid JSON, just text description"

                result = await tool.execute(input=str(sample_image))

                # Should still succeed but note JSON parse failure
                assert result.success
                assert result.metadata.get("json_parse_failed") is True


# ═══════════════════════════════════════════════════════════════════════════════
# DocumentSummarizeTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDocumentSummarizeTool:
    """Test suite for document summarization."""

    @pytest.fixture
    def tool(self, tmp_path):
        return DocumentSummarizeTool(work_dir=tmp_path)

    @pytest.fixture
    def sample_image(self, tmp_path):
        """Create a simple test image file."""
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        img_path = tmp_path / "test_doc.png"
        img_path.write_bytes(png_data)
        return img_path

    @pytest.mark.asyncio
    async def test_summarize_missing_file(self, tool):
        """Test summarizing a file that doesn't exist."""
        result = await tool.execute(input="nonexistent.pdf")

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_summarize_image_success(self, tool, sample_image):
        """Test successful image summarization."""
        mock_summary = "This document contains a simple image with minimal content."

        with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
            with patch("sindri.tools.vision_documents._call_vision_model", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = mock_summary

                result = await tool.execute(input=str(sample_image))

                assert result.success
                assert mock_summary in result.output
                assert result.metadata["pages_processed"] == 1

    @pytest.mark.asyncio
    async def test_summarize_length_brief(self, tool, sample_image):
        """Test brief summary length."""
        mock_summary = "Simple image."

        with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
            with patch("sindri.tools.vision_documents._call_vision_model", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = mock_summary

                result = await tool.execute(input=str(sample_image), length="brief")

                assert result.success
                assert result.metadata["length"] == "brief"

    @pytest.mark.asyncio
    async def test_summarize_length_detailed(self, tool, sample_image):
        """Test detailed summary length."""
        mock_summary = "This is a comprehensive analysis of the document..."

        with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
            with patch("sindri.tools.vision_documents._call_vision_model", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = mock_summary

                result = await tool.execute(input=str(sample_image), length="detailed")

                assert result.success
                assert result.metadata["length"] == "detailed"

    @pytest.mark.asyncio
    async def test_summarize_with_focus(self, tool, sample_image):
        """Test summarization with specific focus area."""
        mock_summary = "The financial section shows revenue of $1M."

        with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
            with patch("sindri.tools.vision_documents._call_vision_model", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = mock_summary

                result = await tool.execute(
                    input=str(sample_image),
                    focus="financials"
                )

                assert result.success
                assert result.metadata["focus"] == "financials"

    @pytest.mark.asyncio
    async def test_summarize_ollama_unavailable(self, tool, sample_image):
        """Test behavior when ollama is not available."""
        with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", False):
            result = await tool.execute(input=str(sample_image))

            assert not result.success
            assert "ollama package not installed" in result.error


# ═══════════════════════════════════════════════════════════════════════════════
# PDF Handling Tests (with mocked PyMuPDF)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPdfHandling:
    """Test PDF-specific handling in vision document tools."""

    @pytest.fixture
    def describe_tool(self, tmp_path):
        return DocumentDescribeTool(work_dir=tmp_path)

    @pytest.fixture
    def extract_tool(self, tmp_path):
        return DocumentExtractStructuredTool(work_dir=tmp_path)

    @pytest.fixture
    def summarize_tool(self, tmp_path):
        return DocumentSummarizeTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_describe_pdf_page(self, describe_tool, tmp_path):
        """Test describing a specific PDF page."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 mock content")

        mock_base64 = "mock_base64_image_data"
        mock_description = "This PDF page contains text and tables."

        with patch("sindri.tools.vision_documents.PYMUPDF_AVAILABLE", True):
            with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
                with patch("sindri.tools.vision_documents._pdf_page_to_base64") as mock_pdf:
                    mock_pdf.return_value = mock_base64
                    with patch("sindri.tools.vision_documents._call_vision_model", new_callable=AsyncMock) as mock_call:
                        mock_call.return_value = mock_description

                        result = await describe_tool.execute(input=str(pdf_path), page=2)

                        assert result.success
                        mock_pdf.assert_called_once()
                        # Page should be 0-indexed internally
                        assert mock_pdf.call_args[0][1] == 1

    @pytest.mark.asyncio
    async def test_describe_pdf_without_pymupdf(self, describe_tool, tmp_path):
        """Test PDF handling when PyMuPDF is not available."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 mock content")

        with patch("sindri.tools.vision_documents.PYMUPDF_AVAILABLE", False):
            with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
                result = await describe_tool.execute(input=str(pdf_path))

                assert not result.success
                assert "PyMuPDF not installed" in result.error

    @pytest.mark.asyncio
    async def test_summarize_pdf_multiple_pages(self, summarize_tool, tmp_path):
        """Test summarizing multiple PDF pages."""
        pdf_path = tmp_path / "multipage.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 mock content")

        mock_base64 = "mock_base64_image_data"

        with patch("sindri.tools.vision_documents.PYMUPDF_AVAILABLE", True):
            with patch("sindri.tools.vision_documents.OLLAMA_AVAILABLE", True):
                with patch("sindri.tools.vision_documents._pdf_page_to_base64") as mock_pdf:
                    mock_pdf.return_value = mock_base64

                    # Mock fitz.open to return a document with 3 pages
                    mock_doc = MagicMock()
                    mock_doc.__len__ = MagicMock(return_value=3)

                    with patch("sindri.tools.vision_documents.fitz") as mock_fitz:
                        mock_fitz.open.return_value = mock_doc

                        with patch("sindri.tools.vision_documents._call_vision_model", new_callable=AsyncMock) as mock_call:
                            mock_call.return_value = "Page summary"

                            result = await summarize_tool.execute(
                                input=str(pdf_path),
                                start_page=1,
                                end_page=3
                            )

                            assert result.success
                            assert result.metadata["pages_processed"] == 3


# ═══════════════════════════════════════════════════════════════════════════════
# Tool Registry Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestVisionDocumentToolRegistry:
    """Test that vision document tools are properly registered."""

    def test_tools_registered(self):
        """Test that all vision document tools are registered."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()
        tool_names = list(registry._tools.keys())

        assert "document_describe" in tool_names
        assert "document_extract_structured" in tool_names
        assert "document_summarize" in tool_names

    def test_tool_schemas_valid(self):
        """Test that tool schemas are valid."""
        describe = DocumentDescribeTool()
        extract = DocumentExtractStructuredTool()
        summarize = DocumentSummarizeTool()

        for tool in [describe, extract, summarize]:
            schema = tool.get_schema()
            assert schema["type"] == "function"
            assert "function" in schema
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]
            assert schema["function"]["parameters"]["type"] == "object"
            assert "required" in schema["function"]["parameters"]
            assert "input" in schema["function"]["parameters"]["required"]
