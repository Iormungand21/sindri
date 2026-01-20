"""Vision-based document processing tools using AI vision models.

This module provides tools that use vision language models (granite3.2-vision)
to understand and process documents visually, going beyond traditional text extraction.

Tools:
- document_describe: Describe document content using AI vision
- document_extract_structured: Extract structured data (forms, tables, key-values)
- document_summarize: AI-powered document summary
"""

from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from typing import Any, Optional

import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()

# Check for PyMuPDF availability (for PDF to image conversion)
try:
    import fitz  # PyMuPDF

    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    fitz = None  # type: ignore

# Check for Pillow availability
try:
    from PIL import Image

    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    Image = None  # type: ignore

# Check for ollama availability
try:
    import ollama

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    ollama = None  # type: ignore

# Default vision model
DEFAULT_VISION_MODEL = "granite3.2-vision:2b"


def _image_to_base64(image_path: Path) -> str:
    """Convert an image file to base64 string.

    Args:
        image_path: Path to the image file

    Returns:
        Base64 encoded string of the image
    """
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _pdf_page_to_base64(pdf_path: Path, page_num: int = 0, dpi: int = 150) -> str:
    """Convert a PDF page to base64 PNG image.

    Args:
        pdf_path: Path to PDF file
        page_num: Page number (0-indexed)
        dpi: Resolution for rendering (default 150)

    Returns:
        Base64 encoded PNG image
    """
    if not PYMUPDF_AVAILABLE:
        raise RuntimeError("PyMuPDF not available")

    doc = fitz.open(pdf_path)
    if page_num >= len(doc):
        raise ValueError(f"Page {page_num + 1} does not exist (PDF has {len(doc)} pages)")

    page = doc[page_num]
    # Scale factor for DPI (default PDF is 72 DPI)
    scale = dpi / 72
    matrix = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=matrix)

    # Convert to PNG bytes
    img_bytes = pix.tobytes("png")
    doc.close()

    return base64.b64encode(img_bytes).decode("utf-8")


async def _call_vision_model(
    prompt: str,
    image_base64: str,
    model: str = DEFAULT_VISION_MODEL,
) -> str:
    """Call a vision model with an image.

    Args:
        prompt: Text prompt for the model
        image_base64: Base64 encoded image data
        model: Vision model to use

    Returns:
        Model response text
    """
    if not OLLAMA_AVAILABLE:
        raise RuntimeError("ollama package not available")

    client = ollama.AsyncClient()

    response = await client.chat(
        model=model,
        messages=[
            {
                "role": "user",
                "content": prompt,
                "images": [image_base64],
            }
        ],
    )

    return response["message"]["content"]


def _get_supported_image_extensions() -> set[str]:
    """Get supported image file extensions."""
    return {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"}


def _is_pdf(path: Path) -> bool:
    """Check if file is a PDF."""
    return path.suffix.lower() == ".pdf"


def _is_image(path: Path) -> bool:
    """Check if file is a supported image."""
    return path.suffix.lower() in _get_supported_image_extensions()


class DocumentDescribeTool(Tool):
    """Describe document content using AI vision model."""

    name = "document_describe"
    description = """Describe the content of a document or image using AI vision.

Uses a vision language model to understand and describe:
- Document layout and structure
- Text content and formatting
- Charts, graphs, and diagrams
- Tables and their data
- Images and illustrations

Unlike traditional OCR, this tool understands context and meaning.

Examples:
- document_describe(input="report.pdf", page=1)
- document_describe(input="screenshot.png")
- document_describe(input="form.pdf", prompt="What fields are on this form?")
- document_describe(input="chart.png", detail_level="comprehensive")
"""

    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to document (PDF, PNG, JPG, etc.)",
            },
            "page": {
                "type": "integer",
                "description": "Page number for PDFs (1-indexed, default: 1)",
            },
            "prompt": {
                "type": "string",
                "description": "Custom prompt for specific analysis (default: general description)",
            },
            "detail_level": {
                "type": "string",
                "enum": ["brief", "detailed", "comprehensive"],
                "description": "Level of detail in description (default: detailed)",
            },
        },
        "required": ["input"],
    }

    async def execute(
        self,
        input: str,
        page: int = 1,
        prompt: Optional[str] = None,
        detail_level: str = "detailed",
        **kwargs: Any,
    ) -> ToolResult:
        """Describe document content using AI vision."""
        log.info(
            "document_describe_start",
            input=input,
            page=page,
            detail_level=detail_level,
        )

        # Check dependencies
        if not OLLAMA_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="ollama package not installed. Install with: pip install ollama",
            )

        try:
            input_path = self._resolve_path(input)

            if not os.path.exists(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file does not exist: {input}",
                )

            # Convert to image
            if _is_pdf(input_path):
                if not PYMUPDF_AVAILABLE:
                    return ToolResult(
                        success=False,
                        output="",
                        error="PyMuPDF not installed. Install with: pip install PyMuPDF",
                    )
                image_base64 = _pdf_page_to_base64(input_path, page - 1)
                source_desc = f"page {page} of {input_path.name}"
            elif _is_image(input_path):
                image_base64 = _image_to_base64(input_path)
                source_desc = input_path.name
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported file type: {input_path.suffix}. Supported: PDF, PNG, JPG, etc.",
                )

            # Build prompt based on detail level
            if prompt:
                full_prompt = prompt
            else:
                detail_instructions = {
                    "brief": "Provide a brief, 2-3 sentence description of this document/image.",
                    "detailed": "Describe this document/image in detail, including layout, content, and any notable elements.",
                    "comprehensive": "Provide a comprehensive analysis of this document/image. Include: overall structure, all text content visible, any charts/tables/diagrams and their meaning, images present, and the apparent purpose of the document.",
                }
                full_prompt = detail_instructions.get(detail_level, detail_instructions["detailed"])

            # Call vision model
            description = await _call_vision_model(full_prompt, image_base64)

            log.info(
                "document_describe_success",
                input=str(input_path),
                description_length=len(description),
            )

            return ToolResult(
                success=True,
                output=f"**Description of {source_desc}:**\n\n{description}",
                metadata={
                    "input": str(input_path),
                    "page": page if _is_pdf(input_path) else None,
                    "detail_level": detail_level,
                    "model": DEFAULT_VISION_MODEL,
                    "description_length": len(description),
                },
            )

        except ValueError as e:
            log.error("document_describe_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))
        except Exception as e:
            log.error("document_describe_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to describe document: {str(e)}",
            )


class DocumentExtractStructuredTool(Tool):
    """Extract structured data from documents using AI vision."""

    name = "document_extract_structured"
    description = """Extract structured data from forms, tables, and documents using AI vision.

Uses a vision model to intelligently extract:
- Form fields and their values
- Table data as structured JSON
- Key-value pairs from invoices/receipts
- Data from charts and graphs

Returns data in structured format (JSON, CSV, or markdown).

Examples:
- document_extract_structured(input="invoice.pdf", extract_type="key_value")
- document_extract_structured(input="spreadsheet.png", extract_type="table")
- document_extract_structured(input="form.pdf", extract_type="form_fields")
- document_extract_structured(input="receipt.jpg", output_format="json")
"""

    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to document (PDF, PNG, JPG, etc.)",
            },
            "page": {
                "type": "integer",
                "description": "Page number for PDFs (1-indexed, default: 1)",
            },
            "extract_type": {
                "type": "string",
                "enum": ["table", "form_fields", "key_value", "auto"],
                "description": "Type of data to extract (default: auto)",
            },
            "output_format": {
                "type": "string",
                "enum": ["json", "csv", "markdown"],
                "description": "Output format (default: json)",
            },
        },
        "required": ["input"],
    }

    async def execute(
        self,
        input: str,
        page: int = 1,
        extract_type: str = "auto",
        output_format: str = "json",
        **kwargs: Any,
    ) -> ToolResult:
        """Extract structured data from document using AI vision."""
        log.info(
            "document_extract_structured_start",
            input=input,
            page=page,
            extract_type=extract_type,
            output_format=output_format,
        )

        # Check dependencies
        if not OLLAMA_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="ollama package not installed. Install with: pip install ollama",
            )

        try:
            input_path = self._resolve_path(input)

            if not os.path.exists(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file does not exist: {input}",
                )

            # Convert to image
            if _is_pdf(input_path):
                if not PYMUPDF_AVAILABLE:
                    return ToolResult(
                        success=False,
                        output="",
                        error="PyMuPDF not installed. Install with: pip install PyMuPDF",
                    )
                image_base64 = _pdf_page_to_base64(input_path, page - 1)
            elif _is_image(input_path):
                image_base64 = _image_to_base64(input_path)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported file type: {input_path.suffix}",
                )

            # Build extraction prompt based on type
            extraction_prompts = {
                "table": """Extract all tables from this document image.
Return the data as a JSON array where each table is an object with:
- "headers": array of column headers
- "rows": array of row arrays containing cell values
Only output valid JSON, no explanations.""",
                "form_fields": """Extract all form fields from this document image.
Return as a JSON object where keys are field labels/names and values are the field values (or null if empty).
Only output valid JSON, no explanations.""",
                "key_value": """Extract all key-value pairs from this document (like an invoice, receipt, or form).
Return as a JSON object mapping each key to its value.
Include things like dates, amounts, names, addresses, IDs, etc.
Only output valid JSON, no explanations.""",
                "auto": """Analyze this document and extract all structured data you can find.
This may include: tables, form fields, key-value pairs, lists.
Return as a JSON object with keys for each type of data found (e.g., "tables", "fields", "metadata").
Only output valid JSON, no explanations.""",
            }

            prompt = extraction_prompts.get(extract_type, extraction_prompts["auto"])

            # Call vision model
            raw_result = await _call_vision_model(prompt, image_base64)

            # Try to parse as JSON
            try:
                # Clean up common issues
                cleaned = raw_result.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

                parsed_data = json.loads(cleaned)
            except json.JSONDecodeError:
                # Return raw result if JSON parsing fails
                log.warning(
                    "document_extract_json_parse_failed",
                    raw_result_preview=raw_result[:200],
                )
                return ToolResult(
                    success=True,
                    output=f"**Extracted data (raw text - JSON parsing failed):**\n\n{raw_result}",
                    metadata={
                        "input": str(input_path),
                        "extract_type": extract_type,
                        "output_format": "text",
                        "json_parse_failed": True,
                    },
                )

            # Format output based on requested format
            if output_format == "json":
                formatted_output = json.dumps(parsed_data, indent=2)
            elif output_format == "csv":
                # Convert to CSV if it's a table-like structure
                formatted_output = self._to_csv(parsed_data)
            elif output_format == "markdown":
                formatted_output = self._to_markdown(parsed_data)
            else:
                formatted_output = json.dumps(parsed_data, indent=2)

            log.info(
                "document_extract_structured_success",
                input=str(input_path),
                extract_type=extract_type,
                output_format=output_format,
            )

            return ToolResult(
                success=True,
                output=f"**Extracted {extract_type} data from {input_path.name}:**\n\n```{output_format}\n{formatted_output}\n```",
                metadata={
                    "input": str(input_path),
                    "page": page if _is_pdf(input_path) else None,
                    "extract_type": extract_type,
                    "output_format": output_format,
                    "model": DEFAULT_VISION_MODEL,
                    "data": parsed_data,
                },
            )

        except ValueError as e:
            log.error("document_extract_structured_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))
        except Exception as e:
            log.error("document_extract_structured_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to extract data: {str(e)}",
            )

    def _to_csv(self, data: Any) -> str:
        """Convert parsed data to CSV format."""
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        if isinstance(data, dict):
            # If it has a tables key with headers/rows
            if "tables" in data and isinstance(data["tables"], list):
                for table in data["tables"]:
                    if "headers" in table:
                        writer.writerow(table["headers"])
                    if "rows" in table:
                        writer.writerows(table["rows"])
                    writer.writerow([])  # Blank line between tables
            elif "headers" in data and "rows" in data:
                # Single table format
                writer.writerow(data["headers"])
                writer.writerows(data["rows"])
            else:
                # Key-value pairs
                writer.writerow(["Key", "Value"])
                for k, v in data.items():
                    writer.writerow([k, v])
        elif isinstance(data, list):
            # List of rows
            for row in data:
                if isinstance(row, list):
                    writer.writerow(row)
                elif isinstance(row, dict):
                    if not output.tell():  # First row, write headers
                        writer.writerow(row.keys())
                    writer.writerow(row.values())

        return output.getvalue()

    def _to_markdown(self, data: Any) -> str:
        """Convert parsed data to markdown format."""
        lines = []

        if isinstance(data, dict):
            if "tables" in data and isinstance(data["tables"], list):
                for i, table in enumerate(data["tables"]):
                    if i > 0:
                        lines.append("")
                    lines.append(f"### Table {i + 1}")
                    lines.append(self._table_to_markdown(table))
            elif "headers" in data and "rows" in data:
                lines.append(self._table_to_markdown(data))
            else:
                # Key-value pairs as table
                lines.append("| Key | Value |")
                lines.append("|-----|-------|")
                for k, v in data.items():
                    lines.append(f"| {k} | {v} |")
        elif isinstance(data, list):
            # Assume list of dicts
            if data and isinstance(data[0], dict):
                headers = list(data[0].keys())
                lines.append("| " + " | ".join(headers) + " |")
                lines.append("|" + "|".join(["---"] * len(headers)) + "|")
                for row in data:
                    lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")

        return "\n".join(lines)

    def _table_to_markdown(self, table: dict) -> str:
        """Convert a single table to markdown."""
        lines = []
        headers = table.get("headers", [])
        rows = table.get("rows", [])

        if headers:
            lines.append("| " + " | ".join(str(h) for h in headers) + " |")
            lines.append("|" + "|".join(["---"] * len(headers)) + "|")

        for row in rows:
            lines.append("| " + " | ".join(str(c) for c in row) + " |")

        return "\n".join(lines)


class DocumentSummarizeTool(Tool):
    """Create AI-powered document summaries using vision model."""

    name = "document_summarize"
    description = """Create an AI-powered summary of document content.

Uses vision to understand both text and visual elements:
- Executive summary of reports
- Key points from presentations
- Main findings from research papers
- Action items from meeting notes

Can process multiple pages and focus on specific aspects.

Examples:
- document_summarize(input="report.pdf")
- document_summarize(input="presentation.pdf", length="brief")
- document_summarize(input="contract.pdf", focus="obligations")
- document_summarize(input="meeting_notes.pdf", start_page=1, end_page=5)
"""

    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to document (PDF or image)",
            },
            "start_page": {
                "type": "integer",
                "description": "Starting page (1-indexed, default: 1)",
            },
            "end_page": {
                "type": "integer",
                "description": "Ending page (default: min(start+5, total_pages) to limit processing)",
            },
            "length": {
                "type": "string",
                "enum": ["brief", "standard", "detailed"],
                "description": "Summary length (default: standard)",
            },
            "focus": {
                "type": "string",
                "description": "Specific aspect to focus on (e.g., 'financials', 'action items', 'key findings')",
            },
        },
        "required": ["input"],
    }

    async def execute(
        self,
        input: str,
        start_page: int = 1,
        end_page: Optional[int] = None,
        length: str = "standard",
        focus: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Summarize document content using AI vision."""
        log.info(
            "document_summarize_start",
            input=input,
            start_page=start_page,
            end_page=end_page,
            length=length,
            focus=focus,
        )

        # Check dependencies
        if not OLLAMA_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="ollama package not installed. Install with: pip install ollama",
            )

        try:
            input_path = self._resolve_path(input)

            if not os.path.exists(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file does not exist: {input}",
                )

            # Handle single images
            if _is_image(input_path):
                image_base64 = _image_to_base64(input_path)
                page_summaries = [await self._summarize_page(image_base64, length, focus)]
                total_pages = 1
                pages_processed = 1
            elif _is_pdf(input_path):
                if not PYMUPDF_AVAILABLE:
                    return ToolResult(
                        success=False,
                        output="",
                        error="PyMuPDF not installed. Install with: pip install PyMuPDF",
                    )

                doc = fitz.open(input_path)
                total_pages = len(doc)
                doc.close()

                # Limit pages to process (vision models are slower)
                if end_page is None:
                    end_page = min(start_page + 4, total_pages)  # Max 5 pages by default
                else:
                    end_page = min(end_page, total_pages)

                if start_page < 1:
                    start_page = 1
                if start_page > total_pages:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Start page {start_page} exceeds total pages {total_pages}",
                    )

                # Summarize each page
                page_summaries = []
                for page_num in range(start_page, end_page + 1):
                    image_base64 = _pdf_page_to_base64(input_path, page_num - 1)
                    summary = await self._summarize_page(image_base64, length, focus, page_num)
                    page_summaries.append(summary)

                pages_processed = len(page_summaries)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported file type: {input_path.suffix}",
                )

            # Combine summaries
            if len(page_summaries) == 1:
                final_summary = page_summaries[0]
            else:
                # Create a meta-summary for multiple pages
                combined = "\n\n".join(page_summaries)
                if len(combined) > 4000:
                    # If combined summaries are too long, create a meta-summary
                    final_summary = await self._create_meta_summary(combined, length, focus)
                else:
                    final_summary = combined

            log.info(
                "document_summarize_success",
                input=str(input_path),
                pages_processed=pages_processed,
                summary_length=len(final_summary),
            )

            return ToolResult(
                success=True,
                output=f"**Summary of {input_path.name}:**\n\n{final_summary}",
                metadata={
                    "input": str(input_path),
                    "total_pages": total_pages if _is_pdf(input_path) else 1,
                    "pages_processed": pages_processed,
                    "start_page": start_page,
                    "end_page": end_page,
                    "length": length,
                    "focus": focus,
                    "model": DEFAULT_VISION_MODEL,
                    "summary_length": len(final_summary),
                },
            )

        except ValueError as e:
            log.error("document_summarize_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))
        except Exception as e:
            log.error("document_summarize_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to summarize document: {str(e)}",
            )

    async def _summarize_page(
        self,
        image_base64: str,
        length: str,
        focus: Optional[str],
        page_num: Optional[int] = None,
    ) -> str:
        """Summarize a single page/image."""
        length_instructions = {
            "brief": "Provide a 2-3 sentence summary.",
            "standard": "Provide a clear, concise summary in 1-2 paragraphs.",
            "detailed": "Provide a comprehensive summary covering all key points, findings, and details.",
        }

        prompt_parts = [
            "Analyze this document page and summarize its content.",
            length_instructions.get(length, length_instructions["standard"]),
        ]

        if focus:
            prompt_parts.append(f"Focus specifically on: {focus}")

        prompt = " ".join(prompt_parts)
        summary = await _call_vision_model(prompt, image_base64)

        if page_num:
            return f"**Page {page_num}:**\n{summary}"
        return summary

    async def _create_meta_summary(
        self,
        combined_summaries: str,
        length: str,
        focus: Optional[str],
    ) -> str:
        """Create a meta-summary from multiple page summaries.

        Note: This uses a text-only call since we already have text summaries.
        """
        if not OLLAMA_AVAILABLE:
            return combined_summaries

        length_instructions = {
            "brief": "Create a very brief 2-3 sentence summary.",
            "standard": "Create a concise summary in 2-3 paragraphs.",
            "detailed": "Create a comprehensive summary covering all key points.",
        }

        prompt = f"""The following are summaries of individual pages from a document.
Create a cohesive overall summary that captures the main points.

{length_instructions.get(length, length_instructions["standard"])}

Page summaries:
{combined_summaries}

Overall summary:"""

        client = ollama.AsyncClient()
        response = await client.chat(
            model="qwen2.5:3b-instruct",  # Use small text model for meta-summary
            messages=[{"role": "user", "content": prompt}],
        )

        return response["message"]["content"]
