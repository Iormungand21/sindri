"""Document processing tools for PDF, spreadsheet, and OCR operations.

This module provides tools for:
- PDF text extraction with optional OCR
- PDF to Markdown conversion
- PDF merge and split operations
- Image OCR using Tesseract
- Spreadsheet read/write (CSV and Excel)
"""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import structlog

from sindri.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    pass

log = structlog.get_logger()

# Check for PyMuPDF availability
try:
    import fitz  # PyMuPDF

    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    fitz = None  # type: ignore

# Check for pytesseract availability
try:
    import pytesseract

    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    pytesseract = None  # type: ignore

# Check for pandas and openpyxl availability
try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None  # type: ignore

try:
    import openpyxl  # noqa: F401

    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

# Check for Pillow (needed for OCR)
try:
    from PIL import Image

    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    Image = None  # type: ignore


class PdfExtractTextTool(Tool):
    """Extract text from PDF files."""

    name = "pdf_extract_text"
    description = """Extract text content from a PDF file.

Supports extracting text from all pages or a specific page range.
Can optionally use OCR for scanned documents (requires tesseract).

Examples:
- Extract all text: pdf_extract_text(input="document.pdf")
- Extract pages 1-5: pdf_extract_text(input="doc.pdf", start_page=1, end_page=5)
- Use OCR for scanned PDF: pdf_extract_text(input="scanned.pdf", use_ocr=true)
"""

    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to the PDF file",
            },
            "output": {
                "type": "string",
                "description": "Output file path for extracted text (optional, prints to stdout if not specified)",
            },
            "start_page": {
                "type": "integer",
                "description": "Starting page number (1-indexed, default: 1)",
            },
            "end_page": {
                "type": "integer",
                "description": "Ending page number (1-indexed, default: last page)",
            },
            "use_ocr": {
                "type": "boolean",
                "description": "Use OCR for scanned documents (requires tesseract)",
            },
            "ocr_language": {
                "type": "string",
                "description": "OCR language code (default: 'eng')",
            },
        },
        "required": ["input"],
    }

    async def execute(
        self,
        input: str,
        output: Optional[str] = None,
        start_page: int = 1,
        end_page: Optional[int] = None,
        use_ocr: bool = False,
        ocr_language: str = "eng",
        **kwargs: Any,
    ) -> ToolResult:
        """Extract text from a PDF file."""
        log.info(
            "pdf_extract_text_start",
            input=input,
            start_page=start_page,
            end_page=end_page,
            use_ocr=use_ocr,
        )

        if not PYMUPDF_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="PyMuPDF not installed. Install with: pip install PyMuPDF",
            )

        if use_ocr and not TESSERACT_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="pytesseract not installed. Install with: pip install pytesseract",
            )

        if use_ocr and not PILLOW_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Pillow not installed. Install with: pip install Pillow",
            )

        try:
            input_path = self._resolve_path(input)

            if not os.path.exists(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file does not exist: {input}",
                )

            doc = fitz.open(input_path)
            total_pages = len(doc)

            # Validate page range
            if start_page < 1:
                start_page = 1
            if end_page is None or end_page > total_pages:
                end_page = total_pages
            if start_page > end_page:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid page range: {start_page}-{end_page}",
                )

            extracted_text = []
            pages_processed = 0

            for page_num in range(start_page - 1, end_page):
                page = doc[page_num]

                if use_ocr:
                    # Render page to image and OCR
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img_data = pix.tobytes("png")
                    img = Image.open(io.BytesIO(img_data))
                    text = pytesseract.image_to_string(img, lang=ocr_language)
                else:
                    text = page.get_text()

                if text.strip():
                    extracted_text.append(f"--- Page {page_num + 1} ---\n{text}")
                    pages_processed += 1

            doc.close()

            full_text = "\n\n".join(extracted_text)

            if output:
                output_path = self._resolve_path(output)
                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(full_text)

                log.info(
                    "pdf_extract_text_success",
                    output=str(output_path),
                    pages=pages_processed,
                )

                return ToolResult(
                    success=True,
                    output=f"Extracted text from {pages_processed} pages. Saved to: {output_path}",
                    metadata={
                        "input": str(input_path),
                        "output": str(output_path),
                        "total_pages": total_pages,
                        "pages_processed": pages_processed,
                        "start_page": start_page,
                        "end_page": end_page,
                        "use_ocr": use_ocr,
                        "text_length": len(full_text),
                    },
                )
            else:
                log.info(
                    "pdf_extract_text_success",
                    pages=pages_processed,
                    text_length=len(full_text),
                )

                # Truncate for display if very long
                display_text = full_text
                if len(full_text) > 10000:
                    display_text = full_text[:10000] + f"\n\n... (truncated, {len(full_text)} total chars)"

                return ToolResult(
                    success=True,
                    output=f"**Extracted text from {pages_processed} pages:**\n\n{display_text}",
                    metadata={
                        "input": str(input_path),
                        "total_pages": total_pages,
                        "pages_processed": pages_processed,
                        "start_page": start_page,
                        "end_page": end_page,
                        "use_ocr": use_ocr,
                        "text_length": len(full_text),
                        "text": full_text,
                    },
                )

        except Exception as e:
            log.error("pdf_extract_text_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class PdfToMarkdownTool(Tool):
    """Convert PDF to Markdown format."""

    name = "pdf_to_markdown"
    description = """Convert a PDF file to Markdown format.

Attempts to preserve document structure including:
- Headers (detected by font size)
- Paragraphs
- Lists
- Basic formatting

Examples:
- Convert PDF: pdf_to_markdown(input="document.pdf", output="document.md")
- Convert specific pages: pdf_to_markdown(input="doc.pdf", start_page=1, end_page=10)
"""

    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to the PDF file",
            },
            "output": {
                "type": "string",
                "description": "Output Markdown file path (default: input with .md extension)",
            },
            "start_page": {
                "type": "integer",
                "description": "Starting page number (1-indexed, default: 1)",
            },
            "end_page": {
                "type": "integer",
                "description": "Ending page number (1-indexed, default: last page)",
            },
            "include_images": {
                "type": "boolean",
                "description": "Extract and include images (default: false)",
            },
        },
        "required": ["input"],
    }

    async def execute(
        self,
        input: str,
        output: Optional[str] = None,
        start_page: int = 1,
        end_page: Optional[int] = None,
        include_images: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Convert PDF to Markdown."""
        log.info(
            "pdf_to_markdown_start",
            input=input,
            start_page=start_page,
            end_page=end_page,
        )

        if not PYMUPDF_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="PyMuPDF not installed. Install with: pip install PyMuPDF",
            )

        try:
            input_path = self._resolve_path(input)

            if not os.path.exists(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file does not exist: {input}",
                )

            if output:
                output_path = self._resolve_path(output)
            else:
                base = os.path.splitext(input_path)[0]
                output_path = Path(f"{base}.md")

            doc = fitz.open(input_path)
            total_pages = len(doc)

            # Validate page range
            if start_page < 1:
                start_page = 1
            if end_page is None or end_page > total_pages:
                end_page = total_pages

            markdown_parts = []
            images_extracted = 0

            for page_num in range(start_page - 1, end_page):
                page = doc[page_num]

                # Get text blocks with position and font info
                blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

                page_md = []
                prev_size = 0

                for block in blocks:
                    if block["type"] == 0:  # Text block
                        for line in block.get("lines", []):
                            line_text = ""
                            line_size = 0

                            for span in line.get("spans", []):
                                text = span.get("text", "")
                                size = span.get("size", 12)
                                flags = span.get("flags", 0)
                                line_text += text
                                line_size = max(line_size, size)

                            if line_text.strip():
                                # Detect headers based on font size
                                if line_size >= 20:
                                    page_md.append(f"\n# {line_text.strip()}\n")
                                elif line_size >= 16:
                                    page_md.append(f"\n## {line_text.strip()}\n")
                                elif line_size >= 14:
                                    page_md.append(f"\n### {line_text.strip()}\n")
                                else:
                                    # Check for list patterns
                                    stripped = line_text.strip()
                                    if stripped.startswith(("- ", "* ", "• ")):
                                        page_md.append(f"- {stripped[2:].strip()}")
                                    elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in ".)" :
                                        page_md.append(f"1. {stripped[2:].strip()}")
                                    else:
                                        page_md.append(line_text.rstrip())

                                prev_size = line_size

                    elif block["type"] == 1 and include_images:  # Image block
                        # Extract image (simplified - just note it exists)
                        images_extracted += 1
                        page_md.append(f"\n![Image {images_extracted}](image_{page_num + 1}_{images_extracted}.png)\n")

                if page_md:
                    markdown_parts.append(f"\n<!-- Page {page_num + 1} -->\n")
                    markdown_parts.extend(page_md)

            doc.close()

            # Clean up markdown
            markdown_text = "\n".join(markdown_parts)
            # Remove excessive blank lines
            while "\n\n\n" in markdown_text:
                markdown_text = markdown_text.replace("\n\n\n", "\n\n")

            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(markdown_text)

            log.info(
                "pdf_to_markdown_success",
                output=str(output_path),
                pages=end_page - start_page + 1,
            )

            return ToolResult(
                success=True,
                output=f"Converted PDF to Markdown.\nInput: {input}\nOutput: {output_path}\nPages: {start_page}-{end_page} of {total_pages}",
                metadata={
                    "input": str(input_path),
                    "output": str(output_path),
                    "total_pages": total_pages,
                    "pages_converted": end_page - start_page + 1,
                    "images_extracted": images_extracted,
                    "markdown_length": len(markdown_text),
                },
            )

        except Exception as e:
            log.error("pdf_to_markdown_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class PdfMergeTool(Tool):
    """Merge multiple PDF files into one."""

    name = "pdf_merge"
    description = """Merge multiple PDF files into a single PDF.

Files are merged in the order provided.

Examples:
- Merge PDFs: pdf_merge(output="combined.pdf", inputs=["file1.pdf", "file2.pdf", "file3.pdf"])
"""

    parameters = {
        "type": "object",
        "properties": {
            "output": {
                "type": "string",
                "description": "Output PDF file path",
            },
            "inputs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of PDF files to merge (in order)",
            },
        },
        "required": ["output", "inputs"],
    }

    async def execute(
        self,
        output: str,
        inputs: list[str],
        **kwargs: Any,
    ) -> ToolResult:
        """Merge multiple PDFs."""
        log.info("pdf_merge_start", output=output, input_count=len(inputs))

        if not PYMUPDF_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="PyMuPDF not installed. Install with: pip install PyMuPDF",
            )

        if not inputs or len(inputs) < 2:
            return ToolResult(
                success=False,
                output="",
                error="At least 2 PDF files are required for merging",
            )

        try:
            output_path = self._resolve_path(output)

            # Validate all input files exist
            resolved_inputs = []
            for inp in inputs:
                inp_path = self._resolve_path(inp)
                if not os.path.exists(inp_path):
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Input file does not exist: {inp}",
                    )
                resolved_inputs.append(inp_path)

            # Create merged PDF
            merged_doc = fitz.open()
            total_pages = 0
            file_info = []

            for inp_path in resolved_inputs:
                doc = fitz.open(inp_path)
                pages = len(doc)
                merged_doc.insert_pdf(doc)
                total_pages += pages
                file_info.append({"file": str(inp_path), "pages": pages})
                doc.close()

            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            merged_doc.save(output_path)
            merged_doc.close()

            output_size = os.path.getsize(output_path)

            log.info(
                "pdf_merge_success",
                output=str(output_path),
                files=len(inputs),
                pages=total_pages,
            )

            return ToolResult(
                success=True,
                output=f"Merged {len(inputs)} PDFs into {output_path}\nTotal pages: {total_pages}\nOutput size: {output_size:,} bytes",
                metadata={
                    "output": str(output_path),
                    "input_count": len(inputs),
                    "total_pages": total_pages,
                    "output_size": output_size,
                    "files": file_info,
                },
            )

        except Exception as e:
            log.error("pdf_merge_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class PdfSplitTool(Tool):
    """Split a PDF file into multiple files."""

    name = "pdf_split"
    description = """Split a PDF file by page ranges or into individual pages.

Examples:
- Split into single pages: pdf_split(input="document.pdf", output_dir="./pages/")
- Extract pages 1-5: pdf_split(input="doc.pdf", output="pages_1-5.pdf", start_page=1, end_page=5)
- Split by ranges: pdf_split(input="doc.pdf", ranges="1-5,6-10,11-15")
"""

    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to the PDF file to split",
            },
            "output": {
                "type": "string",
                "description": "Output PDF file path (for single range extraction)",
            },
            "output_dir": {
                "type": "string",
                "description": "Output directory for split files (for multiple splits)",
            },
            "start_page": {
                "type": "integer",
                "description": "Starting page number (1-indexed)",
            },
            "end_page": {
                "type": "integer",
                "description": "Ending page number (1-indexed)",
            },
            "ranges": {
                "type": "string",
                "description": "Comma-separated page ranges (e.g., '1-5,6-10,11-15')",
            },
            "single_pages": {
                "type": "boolean",
                "description": "Split into individual single-page PDFs",
            },
        },
        "required": ["input"],
    }

    async def execute(
        self,
        input: str,
        output: Optional[str] = None,
        output_dir: Optional[str] = None,
        start_page: Optional[int] = None,
        end_page: Optional[int] = None,
        ranges: Optional[str] = None,
        single_pages: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Split a PDF file."""
        log.info("pdf_split_start", input=input, single_pages=single_pages)

        if not PYMUPDF_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="PyMuPDF not installed. Install with: pip install PyMuPDF",
            )

        try:
            input_path = self._resolve_path(input)

            if not os.path.exists(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file does not exist: {input}",
                )

            doc = fitz.open(input_path)
            total_pages = len(doc)
            base_name = os.path.splitext(os.path.basename(input_path))[0]

            files_created = []

            if single_pages:
                # Split into individual pages
                if output_dir:
                    out_dir = self._resolve_path(output_dir)
                else:
                    out_dir = Path(os.path.dirname(input_path)) / f"{base_name}_pages"

                os.makedirs(out_dir, exist_ok=True)

                for page_num in range(total_pages):
                    new_doc = fitz.open()
                    new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                    out_path = out_dir / f"{base_name}_page_{page_num + 1}.pdf"
                    new_doc.save(out_path)
                    new_doc.close()
                    files_created.append(str(out_path))

            elif ranges:
                # Split by specified ranges
                if output_dir:
                    out_dir = self._resolve_path(output_dir)
                else:
                    out_dir = Path(os.path.dirname(input_path))

                os.makedirs(out_dir, exist_ok=True)

                for range_str in ranges.split(","):
                    range_str = range_str.strip()
                    if "-" in range_str:
                        parts = range_str.split("-")
                        r_start = int(parts[0]) - 1
                        r_end = int(parts[1]) - 1
                    else:
                        r_start = r_end = int(range_str) - 1

                    if r_start < 0 or r_end >= total_pages or r_start > r_end:
                        continue

                    new_doc = fitz.open()
                    new_doc.insert_pdf(doc, from_page=r_start, to_page=r_end)
                    out_path = out_dir / f"{base_name}_pages_{r_start + 1}-{r_end + 1}.pdf"
                    new_doc.save(out_path)
                    new_doc.close()
                    files_created.append(str(out_path))

            elif start_page is not None:
                # Extract specific range
                s_page = start_page - 1
                e_page = (end_page - 1) if end_page else total_pages - 1

                if s_page < 0:
                    s_page = 0
                if e_page >= total_pages:
                    e_page = total_pages - 1

                if output:
                    out_path = self._resolve_path(output)
                else:
                    out_path = Path(os.path.dirname(input_path)) / f"{base_name}_pages_{s_page + 1}-{e_page + 1}.pdf"

                os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

                new_doc = fitz.open()
                new_doc.insert_pdf(doc, from_page=s_page, to_page=e_page)
                new_doc.save(out_path)
                new_doc.close()
                files_created.append(str(out_path))

            else:
                doc.close()
                return ToolResult(
                    success=False,
                    output="",
                    error="Must specify one of: single_pages=true, ranges, or start_page/end_page",
                )

            doc.close()

            log.info(
                "pdf_split_success",
                input=str(input_path),
                files_created=len(files_created),
            )

            return ToolResult(
                success=True,
                output=f"Split PDF into {len(files_created)} file(s):\n" + "\n".join(f"  - {f}" for f in files_created),
                metadata={
                    "input": str(input_path),
                    "total_pages": total_pages,
                    "files_created": files_created,
                    "file_count": len(files_created),
                },
            )

        except Exception as e:
            log.error("pdf_split_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class OcrImageTool(Tool):
    """Extract text from images using OCR."""

    name = "ocr_image"
    description = """Extract text from an image using Optical Character Recognition (OCR).

Requires tesseract-ocr to be installed on the system.

Examples:
- Basic OCR: ocr_image(input="scan.png")
- With language: ocr_image(input="document.jpg", language="deu")
- Save to file: ocr_image(input="image.png", output="extracted.txt")
"""

    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to the image file",
            },
            "output": {
                "type": "string",
                "description": "Output file path for extracted text (optional)",
            },
            "language": {
                "type": "string",
                "description": "OCR language code (default: 'eng'). Use 'eng+deu' for multiple languages.",
            },
            "config": {
                "type": "string",
                "description": "Additional tesseract config options",
            },
        },
        "required": ["input"],
    }

    async def execute(
        self,
        input: str,
        output: Optional[str] = None,
        language: str = "eng",
        config: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        """Extract text from image using OCR."""
        log.info("ocr_image_start", input=input, language=language)

        if not TESSERACT_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="pytesseract not installed. Install with: pip install pytesseract\nAlso ensure tesseract-ocr is installed on your system.",
            )

        if not PILLOW_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Pillow not installed. Install with: pip install Pillow",
            )

        try:
            input_path = self._resolve_path(input)

            if not os.path.exists(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file does not exist: {input}",
                )

            # Open and process image
            img = Image.open(input_path)

            # Get image info
            img_width, img_height = img.size
            img_format = img.format or "Unknown"

            # Perform OCR
            extracted_text = pytesseract.image_to_string(
                img,
                lang=language,
                config=config,
            )

            # Get detailed data for confidence
            try:
                data = pytesseract.image_to_data(img, lang=language, output_type=pytesseract.Output.DICT)
                confidences = [int(c) for c in data["conf"] if int(c) >= 0]
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            except Exception:
                avg_confidence = -1

            if output:
                output_path = self._resolve_path(output)
                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(extracted_text)

                log.info(
                    "ocr_image_success",
                    output=str(output_path),
                    text_length=len(extracted_text),
                )

                return ToolResult(
                    success=True,
                    output=f"OCR completed. Saved to: {output_path}\nCharacters extracted: {len(extracted_text)}\nAverage confidence: {avg_confidence:.1f}%",
                    metadata={
                        "input": str(input_path),
                        "output": str(output_path),
                        "language": language,
                        "text_length": len(extracted_text),
                        "avg_confidence": avg_confidence,
                        "image_width": img_width,
                        "image_height": img_height,
                        "image_format": img_format,
                    },
                )
            else:
                log.info(
                    "ocr_image_success",
                    text_length=len(extracted_text),
                )

                # Truncate for display if very long
                display_text = extracted_text
                if len(extracted_text) > 5000:
                    display_text = extracted_text[:5000] + f"\n\n... (truncated, {len(extracted_text)} total chars)"

                return ToolResult(
                    success=True,
                    output=f"**OCR Result** (Language: {language}, Confidence: {avg_confidence:.1f}%)\n\n{display_text}",
                    metadata={
                        "input": str(input_path),
                        "language": language,
                        "text_length": len(extracted_text),
                        "avg_confidence": avg_confidence,
                        "image_width": img_width,
                        "image_height": img_height,
                        "image_format": img_format,
                        "text": extracted_text,
                    },
                )

        except Exception as e:
            log.error("ocr_image_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class SpreadsheetReadTool(Tool):
    """Read data from spreadsheet files (CSV, Excel)."""

    name = "spreadsheet_read"
    description = """Read data from CSV or Excel spreadsheet files.

Returns structured data with column names and values.

Examples:
- Read CSV: spreadsheet_read(input="data.csv")
- Read Excel: spreadsheet_read(input="report.xlsx", sheet="Sales")
- Limit rows: spreadsheet_read(input="large.csv", limit=100)
- Select columns: spreadsheet_read(input="data.csv", columns=["name", "email"])
"""

    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to the spreadsheet file (CSV, XLS, XLSX)",
            },
            "sheet": {
                "type": "string",
                "description": "Sheet name for Excel files (default: first sheet)",
            },
            "columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of column names to include (default: all)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of rows to read (default: all)",
            },
            "skip_rows": {
                "type": "integer",
                "description": "Number of rows to skip from the beginning",
            },
            "output_format": {
                "type": "string",
                "enum": ["json", "csv", "table"],
                "description": "Output format (default: table)",
            },
        },
        "required": ["input"],
    }

    async def execute(
        self,
        input: str,
        sheet: Optional[str] = None,
        columns: Optional[list[str]] = None,
        limit: Optional[int] = None,
        skip_rows: int = 0,
        output_format: str = "table",
        **kwargs: Any,
    ) -> ToolResult:
        """Read spreadsheet data."""
        log.info("spreadsheet_read_start", input=input, sheet=sheet, limit=limit)

        if not PANDAS_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="pandas not installed. Install with: pip install pandas openpyxl",
            )

        try:
            input_path = self._resolve_path(input)

            if not os.path.exists(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file does not exist: {input}",
                )

            # Determine file type and read
            ext = os.path.splitext(input_path)[1].lower()

            if ext == ".csv":
                df = pd.read_csv(input_path, skiprows=skip_rows)
            elif ext in [".xls", ".xlsx", ".xlsm"]:
                if not OPENPYXL_AVAILABLE and ext == ".xlsx":
                    return ToolResult(
                        success=False,
                        output="",
                        error="openpyxl not installed. Install with: pip install openpyxl",
                    )
                # When sheet is None, read first sheet (index 0) to get a DataFrame, not dict
                sheet_to_read = sheet if sheet else 0
                df = pd.read_excel(input_path, sheet_name=sheet_to_read, skiprows=skip_rows)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported file format: {ext}. Supported: .csv, .xls, .xlsx",
                )

            total_rows = len(df)
            total_cols = len(df.columns)

            # Select columns
            if columns:
                missing = [c for c in columns if c not in df.columns]
                if missing:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Columns not found: {missing}. Available: {list(df.columns)}",
                    )
                df = df[columns]

            # Limit rows
            if limit:
                df = df.head(limit)

            rows_returned = len(df)

            # Format output
            if output_format == "json":
                output_data = df.to_json(orient="records", indent=2)
            elif output_format == "csv":
                output_data = df.to_csv(index=False)
            else:  # table
                output_data = df.to_string(index=False)

            # Truncate if too long
            if len(output_data) > 10000:
                output_data = output_data[:10000] + "\n\n... (truncated)"

            log.info(
                "spreadsheet_read_success",
                rows=rows_returned,
                cols=len(df.columns),
            )

            return ToolResult(
                success=True,
                output=f"**Spreadsheet Data** ({rows_returned} rows, {len(df.columns)} columns)\n\n{output_data}",
                metadata={
                    "input": str(input_path),
                    "total_rows": total_rows,
                    "total_cols": total_cols,
                    "rows_returned": rows_returned,
                    "columns": list(df.columns),
                    "dtypes": {str(k): str(v) for k, v in df.dtypes.items()},
                    "sheet": sheet,
                },
            )

        except Exception as e:
            log.error("spreadsheet_read_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class SpreadsheetWriteTool(Tool):
    """Write data to spreadsheet files (CSV, Excel)."""

    name = "spreadsheet_write"
    description = """Write structured data to CSV or Excel spreadsheet files.

Accepts data as JSON array of objects or list of lists.

Examples:
- Write JSON to CSV: spreadsheet_write(output="data.csv", data='[{"name": "John", "age": 30}]')
- Write to Excel: spreadsheet_write(output="report.xlsx", data='[{"col1": 1, "col2": 2}]', sheet="Data")
"""

    parameters = {
        "type": "object",
        "properties": {
            "output": {
                "type": "string",
                "description": "Output file path (.csv, .xlsx)",
            },
            "data": {
                "type": "string",
                "description": "JSON string of data (array of objects or array of arrays)",
            },
            "columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Column names (required if data is array of arrays)",
            },
            "sheet": {
                "type": "string",
                "description": "Sheet name for Excel files (default: 'Sheet1')",
            },
            "include_index": {
                "type": "boolean",
                "description": "Include row index in output (default: false)",
            },
        },
        "required": ["output", "data"],
    }

    async def execute(
        self,
        output: str,
        data: str,
        columns: Optional[list[str]] = None,
        sheet: str = "Sheet1",
        include_index: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Write data to spreadsheet."""
        log.info("spreadsheet_write_start", output=output)

        if not PANDAS_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="pandas not installed. Install with: pip install pandas openpyxl",
            )

        try:
            output_path = self._resolve_path(output)
            ext = os.path.splitext(output_path)[1].lower()

            if ext not in [".csv", ".xlsx", ".xls"]:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported output format: {ext}. Supported: .csv, .xlsx",
                )

            # Parse JSON data
            try:
                parsed_data = json.loads(data)
            except json.JSONDecodeError as e:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid JSON data: {e}",
                )

            # Create DataFrame
            if isinstance(parsed_data, list):
                if len(parsed_data) == 0:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Data is empty",
                    )

                if isinstance(parsed_data[0], dict):
                    df = pd.DataFrame(parsed_data)
                elif isinstance(parsed_data[0], list):
                    if columns:
                        df = pd.DataFrame(parsed_data, columns=columns)
                    else:
                        df = pd.DataFrame(parsed_data)
                else:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Data must be array of objects or array of arrays",
                    )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error="Data must be a JSON array",
                )

            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

            # Write to file
            if ext == ".csv":
                df.to_csv(output_path, index=include_index)
            else:  # Excel
                if not OPENPYXL_AVAILABLE:
                    return ToolResult(
                        success=False,
                        output="",
                        error="openpyxl not installed. Install with: pip install openpyxl",
                    )
                df.to_excel(output_path, sheet_name=sheet, index=include_index)

            output_size = os.path.getsize(output_path)

            log.info(
                "spreadsheet_write_success",
                output=str(output_path),
                rows=len(df),
                cols=len(df.columns),
            )

            return ToolResult(
                success=True,
                output=f"Wrote spreadsheet to: {output_path}\nRows: {len(df)}\nColumns: {len(df.columns)}\nSize: {output_size:,} bytes",
                metadata={
                    "output": str(output_path),
                    "rows": len(df),
                    "columns": list(df.columns),
                    "output_size": output_size,
                    "format": ext[1:],
                    "sheet": sheet if ext != ".csv" else None,
                },
            )

        except Exception as e:
            log.error("spreadsheet_write_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))
