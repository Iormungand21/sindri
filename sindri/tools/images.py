"""Image manipulation tools for Sindri.

Phase 12 Tier 2 - Universal Tool Expansion.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import structlog

from sindri.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    pass

# Check for Pillow support
try:
    from PIL import Image, ExifTags

    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    Image = None  # type: ignore
    ExifTags = None  # type: ignore

logger = structlog.get_logger()

# Supported image formats
SUPPORTED_FORMATS = {
    "jpeg": ["jpg", "jpeg"],
    "png": ["png"],
    "gif": ["gif"],
    "webp": ["webp"],
    "bmp": ["bmp"],
    "tiff": ["tiff", "tif"],
    "ico": ["ico"],
}

# Reverse mapping for format detection
EXTENSION_TO_FORMAT = {}
for fmt, exts in SUPPORTED_FORMATS.items():
    for ext in exts:
        EXTENSION_TO_FORMAT[ext] = fmt


def _get_format_from_path(path: str) -> str:
    """Get image format from file extension."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return EXTENSION_TO_FORMAT.get(ext, "")


def _human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


class ImageResizeTool(Tool):
    """Resize images to specified dimensions or scale."""

    name = "image_resize"
    description = """Resize an image to specified dimensions or scale percentage.

Examples:
- Resize to 800x600: image_resize(input="photo.jpg", width=800, height=600)
- Resize to width only: image_resize(input="photo.jpg", width=800)
- Scale by 50%: image_resize(input="image.png", scale=50)
- Maintain aspect ratio: image_resize(input="photo.jpg", width=800, maintain_aspect=true)
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to input image file",
            },
            "output": {
                "type": "string",
                "description": "Output file path (default: input with '_resized' suffix)",
            },
            "width": {
                "type": "integer",
                "description": "Target width in pixels",
            },
            "height": {
                "type": "integer",
                "description": "Target height in pixels",
            },
            "scale": {
                "type": "integer",
                "description": "Scale percentage (1-500, e.g., 50 for half size)",
            },
            "maintain_aspect": {
                "type": "boolean",
                "description": "Maintain aspect ratio when resizing (default: true)",
            },
            "quality": {
                "type": "integer",
                "description": "Output quality 1-100 for JPEG/WebP (default: 85)",
            },
            "resample": {
                "type": "string",
                "enum": ["nearest", "bilinear", "bicubic", "lanczos"],
                "description": "Resampling method (default: lanczos)",
            },
        },
        "required": ["input"],
    }

    async def execute(
        self,
        input: str,
        output: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        scale: Optional[int] = None,
        maintain_aspect: bool = True,
        quality: int = 85,
        resample: str = "lanczos",
        **kwargs: Any,
    ) -> ToolResult:
        """Resize an image to specified dimensions."""
        logger.info(
            "image_resize_start",
            input=input,
            width=width,
            height=height,
            scale=scale,
        )

        if not PILLOW_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Pillow library not installed. Install with: pip install Pillow",
            )

        try:
            input_path = self._resolve_path(input)

            if not os.path.exists(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file does not exist: {input}",
                )

            # Determine output path
            if output:
                output_path = self._resolve_path(output)
            else:
                base, ext = os.path.splitext(input_path)
                output_path = Path(f"{base}_resized{ext}")

            # Open image
            img = Image.open(input_path)
            original_size = img.size
            original_mode = img.mode

            # Calculate new dimensions
            if scale is not None:
                # Scale by percentage
                new_width = int(original_size[0] * scale / 100)
                new_height = int(original_size[1] * scale / 100)
            elif width is not None or height is not None:
                if maintain_aspect:
                    # Maintain aspect ratio
                    if width is not None and height is not None:
                        # Fit within bounds
                        img.thumbnail((width, height), getattr(Image.Resampling, resample.upper(), Image.Resampling.LANCZOS))
                        new_width, new_height = img.size
                    elif width is not None:
                        ratio = width / original_size[0]
                        new_width = width
                        new_height = int(original_size[1] * ratio)
                    else:
                        ratio = height / original_size[1]
                        new_height = height
                        new_width = int(original_size[0] * ratio)
                else:
                    # Exact dimensions
                    new_width = width if width is not None else original_size[0]
                    new_height = height if height is not None else original_size[1]
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error="Must specify width, height, or scale",
                )

            # Get resampling method
            resample_method = getattr(
                Image.Resampling, resample.upper(), Image.Resampling.LANCZOS
            )

            # Resize image (unless thumbnail was already used)
            if scale is not None or not (maintain_aspect and width is not None and height is not None):
                img = img.resize((new_width, new_height), resample_method)

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

            # Save with quality setting for supported formats
            save_kwargs: dict[str, Any] = {}
            fmt = _get_format_from_path(str(output_path))
            if fmt in ["jpeg", "webp"]:
                save_kwargs["quality"] = quality
            if fmt == "jpeg" and original_mode == "RGBA":
                img = img.convert("RGB")

            img.save(output_path, **save_kwargs)
            output_size = os.path.getsize(output_path)

            logger.info(
                "image_resize_success",
                output=str(output_path),
                new_size=(new_width, new_height),
            )

            return ToolResult(
                success=True,
                output=f"Image resized: {original_size[0]}x{original_size[1]} -> {new_width}x{new_height}\nSaved to: {output_path}",
                metadata={
                    "input": str(input_path),
                    "output": str(output_path),
                    "original_width": original_size[0],
                    "original_height": original_size[1],
                    "width": new_width,
                    "height": new_height,
                    "output_size": output_size,
                    "quality": quality,
                    "resample": resample,
                },
            )

        except Exception as e:
            logger.error("image_resize_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class ImageCropTool(Tool):
    """Crop images to a specified region."""

    name = "image_crop"
    description = """Crop an image to a specified rectangular region.

Examples:
- Crop from top-left: image_crop(input="photo.jpg", x=0, y=0, width=640, height=480)
- Crop center region: image_crop(input="photo.jpg", x=100, y=100, width=200, height=200)
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to input image file",
            },
            "output": {
                "type": "string",
                "description": "Output file path (default: input with '_cropped' suffix)",
            },
            "x": {
                "type": "integer",
                "description": "X coordinate of top-left corner (0-based)",
            },
            "y": {
                "type": "integer",
                "description": "Y coordinate of top-left corner (0-based)",
            },
            "width": {
                "type": "integer",
                "description": "Width of crop region in pixels",
            },
            "height": {
                "type": "integer",
                "description": "Height of crop region in pixels",
            },
            "quality": {
                "type": "integer",
                "description": "Output quality 1-100 for JPEG/WebP (default: 85)",
            },
        },
        "required": ["input", "x", "y", "width", "height"],
    }

    async def execute(
        self,
        input: str,
        x: int,
        y: int,
        width: int,
        height: int,
        output: Optional[str] = None,
        quality: int = 85,
        **kwargs: Any,
    ) -> ToolResult:
        """Crop an image to specified region."""
        logger.info(
            "image_crop_start",
            input=input,
            x=x,
            y=y,
            width=width,
            height=height,
        )

        if not PILLOW_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Pillow library not installed. Install with: pip install Pillow",
            )

        try:
            input_path = self._resolve_path(input)

            if not os.path.exists(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file does not exist: {input}",
                )

            # Determine output path
            if output:
                output_path = self._resolve_path(output)
            else:
                base, ext = os.path.splitext(input_path)
                output_path = Path(f"{base}_cropped{ext}")

            # Open image
            img = Image.open(input_path)
            original_size = img.size
            original_mode = img.mode

            # Validate crop region
            if x < 0 or y < 0:
                return ToolResult(
                    success=False,
                    output="",
                    error="Crop coordinates (x, y) must be non-negative",
                )

            if x + width > original_size[0] or y + height > original_size[1]:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Crop region exceeds image bounds. Image size: {original_size[0]}x{original_size[1]}",
                )

            # Crop image (box is left, upper, right, lower)
            box = (x, y, x + width, y + height)
            cropped = img.crop(box)

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

            # Save with quality setting
            save_kwargs: dict[str, Any] = {}
            fmt = _get_format_from_path(str(output_path))
            if fmt in ["jpeg", "webp"]:
                save_kwargs["quality"] = quality
            if fmt == "jpeg" and original_mode == "RGBA":
                cropped = cropped.convert("RGB")

            cropped.save(output_path, **save_kwargs)
            output_size = os.path.getsize(output_path)

            logger.info(
                "image_crop_success",
                output=str(output_path),
                crop_size=(width, height),
            )

            return ToolResult(
                success=True,
                output=f"Image cropped: {width}x{height} from ({x}, {y})\nSaved to: {output_path}",
                metadata={
                    "input": str(input_path),
                    "output": str(output_path),
                    "original_width": original_size[0],
                    "original_height": original_size[1],
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "output_size": output_size,
                },
            )

        except Exception as e:
            logger.error("image_crop_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class ImageConvertTool(Tool):
    """Convert images between formats."""

    name = "image_convert"
    description = """Convert an image to a different format.

Supported formats: JPEG, PNG, GIF, WebP, BMP, TIFF

Examples:
- Convert to PNG: image_convert(input="photo.jpg", format="png")
- Convert to WebP with quality: image_convert(input="photo.png", format="webp", quality=90)
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to input image file",
            },
            "output": {
                "type": "string",
                "description": "Output file path (default: input with new extension)",
            },
            "format": {
                "type": "string",
                "enum": ["jpeg", "png", "gif", "webp", "bmp", "tiff"],
                "description": "Target format",
            },
            "quality": {
                "type": "integer",
                "description": "Output quality 1-100 for JPEG/WebP (default: 85)",
            },
        },
        "required": ["input", "format"],
    }

    async def execute(
        self,
        input: str,
        format: str,
        output: Optional[str] = None,
        quality: int = 85,
        **kwargs: Any,
    ) -> ToolResult:
        """Convert an image to a different format."""
        logger.info("image_convert_start", input=input, format=format)

        if not PILLOW_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Pillow library not installed. Install with: pip install Pillow",
            )

        try:
            input_path = self._resolve_path(input)

            if not os.path.exists(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file does not exist: {input}",
                )

            # Validate format
            format_lower = format.lower()
            if format_lower not in SUPPORTED_FORMATS:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported format: {format}. Supported: {', '.join(SUPPORTED_FORMATS.keys())}",
                )

            # Determine output path
            new_ext = SUPPORTED_FORMATS[format_lower][0]
            if output:
                output_path = self._resolve_path(output)
            else:
                base = os.path.splitext(input_path)[0]
                output_path = Path(f"{base}.{new_ext}")

            # Open image
            img = Image.open(input_path)
            original_format = img.format or "unknown"
            original_mode = img.mode
            original_size = os.path.getsize(input_path)

            # Handle mode conversion for JPEG (no alpha channel)
            if format_lower == "jpeg" and original_mode in ["RGBA", "P"]:
                if original_mode == "P":
                    img = img.convert("RGBA")
                # Create white background for transparency
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

            # Save with appropriate settings
            save_kwargs: dict[str, Any] = {}
            if format_lower in ["jpeg", "webp"]:
                save_kwargs["quality"] = quality
            if format_lower == "png":
                save_kwargs["optimize"] = True
            if format_lower == "gif" and original_mode not in ["P", "L"]:
                img = img.convert("P", palette=Image.Palette.ADAPTIVE)

            img.save(output_path, format=format_lower.upper(), **save_kwargs)
            output_size = os.path.getsize(output_path)

            # Calculate size change
            size_change = output_size - original_size
            size_change_str = (
                f"+{_human_readable_size(size_change)}"
                if size_change >= 0
                else f"-{_human_readable_size(abs(size_change))}"
            )

            logger.info(
                "image_convert_success",
                output=str(output_path),
                original_format=original_format,
                new_format=format_lower,
            )

            return ToolResult(
                success=True,
                output=f"Image converted: {original_format} -> {format_lower.upper()}\nSize: {_human_readable_size(original_size)} -> {_human_readable_size(output_size)} ({size_change_str})\nSaved to: {output_path}",
                metadata={
                    "input": str(input_path),
                    "output": str(output_path),
                    "original_format": original_format,
                    "new_format": format_lower,
                    "original_size": original_size,
                    "output_size": output_size,
                    "quality": quality,
                },
            )

        except Exception as e:
            logger.error("image_convert_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class ImageRotateTool(Tool):
    """Rotate images by specified degrees."""

    name = "image_rotate"
    description = """Rotate an image by specified degrees.

Examples:
- Rotate 90 degrees clockwise: image_rotate(input="photo.jpg", angle=90)
- Rotate 45 degrees with expansion: image_rotate(input="photo.jpg", angle=45, expand=true)
- Rotate with custom fill: image_rotate(input="photo.png", angle=30, fill_color="white")
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to input image file",
            },
            "output": {
                "type": "string",
                "description": "Output file path (default: input with '_rotated' suffix)",
            },
            "angle": {
                "type": "number",
                "description": "Rotation angle in degrees (positive = counter-clockwise)",
            },
            "expand": {
                "type": "boolean",
                "description": "Expand image to fit rotated content (default: false)",
            },
            "fill_color": {
                "type": "string",
                "description": "Fill color for areas outside rotated image (default: transparent/black)",
            },
            "quality": {
                "type": "integer",
                "description": "Output quality 1-100 for JPEG/WebP (default: 85)",
            },
        },
        "required": ["input", "angle"],
    }

    async def execute(
        self,
        input: str,
        angle: float,
        output: Optional[str] = None,
        expand: bool = False,
        fill_color: Optional[str] = None,
        quality: int = 85,
        **kwargs: Any,
    ) -> ToolResult:
        """Rotate an image by specified degrees."""
        logger.info("image_rotate_start", input=input, angle=angle, expand=expand)

        if not PILLOW_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Pillow library not installed. Install with: pip install Pillow",
            )

        try:
            input_path = self._resolve_path(input)

            if not os.path.exists(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file does not exist: {input}",
                )

            # Determine output path
            if output:
                output_path = self._resolve_path(output)
            else:
                base, ext = os.path.splitext(input_path)
                output_path = Path(f"{base}_rotated{ext}")

            # Open image
            img = Image.open(input_path)
            original_size = img.size
            original_mode = img.mode

            # Parse fill color
            fill = None
            if fill_color:
                try:
                    from PIL import ImageColor

                    fill = ImageColor.getrgb(fill_color)
                    if original_mode == "RGBA" and len(fill) == 3:
                        fill = fill + (255,)
                except ValueError:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Invalid fill color: {fill_color}",
                    )

            # Rotate image
            rotated = img.rotate(angle, expand=expand, fillcolor=fill, resample=Image.Resampling.BICUBIC)
            new_size = rotated.size

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

            # Save with quality setting
            save_kwargs: dict[str, Any] = {}
            fmt = _get_format_from_path(str(output_path))
            if fmt in ["jpeg", "webp"]:
                save_kwargs["quality"] = quality
            if fmt == "jpeg" and rotated.mode == "RGBA":
                # Create white background
                background = Image.new("RGB", rotated.size, (255, 255, 255))
                background.paste(rotated, mask=rotated.split()[3])
                rotated = background

            rotated.save(output_path, **save_kwargs)
            output_size = os.path.getsize(output_path)

            logger.info(
                "image_rotate_success",
                output=str(output_path),
                angle=angle,
                new_size=new_size,
            )

            return ToolResult(
                success=True,
                output=f"Image rotated by {angle} degrees\nSize: {original_size[0]}x{original_size[1]} -> {new_size[0]}x{new_size[1]}\nSaved to: {output_path}",
                metadata={
                    "input": str(input_path),
                    "output": str(output_path),
                    "angle": angle,
                    "expand": expand,
                    "original_width": original_size[0],
                    "original_height": original_size[1],
                    "width": new_size[0],
                    "height": new_size[1],
                    "output_size": output_size,
                },
            )

        except Exception as e:
            logger.error("image_rotate_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class ImageThumbnailTool(Tool):
    """Generate thumbnails from images."""

    name = "image_thumbnail"
    description = """Generate a thumbnail from an image while preserving aspect ratio.

Examples:
- 128x128 thumbnail: image_thumbnail(input="photo.jpg", max_size=128)
- Custom max dimensions: image_thumbnail(input="photo.jpg", max_width=200, max_height=150)
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to input image file",
            },
            "output": {
                "type": "string",
                "description": "Output file path (default: input with '_thumb' suffix)",
            },
            "max_size": {
                "type": "integer",
                "description": "Maximum size for both width and height",
            },
            "max_width": {
                "type": "integer",
                "description": "Maximum width (use with max_height for different aspect)",
            },
            "max_height": {
                "type": "integer",
                "description": "Maximum height (use with max_width for different aspect)",
            },
            "quality": {
                "type": "integer",
                "description": "Output quality 1-100 for JPEG/WebP (default: 85)",
            },
        },
        "required": ["input"],
    }

    async def execute(
        self,
        input: str,
        output: Optional[str] = None,
        max_size: Optional[int] = None,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
        quality: int = 85,
        **kwargs: Any,
    ) -> ToolResult:
        """Generate a thumbnail from an image."""
        logger.info(
            "image_thumbnail_start",
            input=input,
            max_size=max_size,
            max_width=max_width,
            max_height=max_height,
        )

        if not PILLOW_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Pillow library not installed. Install with: pip install Pillow",
            )

        try:
            input_path = self._resolve_path(input)

            if not os.path.exists(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file does not exist: {input}",
                )

            # Determine thumbnail size
            if max_size is not None:
                thumb_size = (max_size, max_size)
            elif max_width is not None and max_height is not None:
                thumb_size = (max_width, max_height)
            elif max_width is not None:
                thumb_size = (max_width, max_width * 10)  # Very tall to only constrain width
            elif max_height is not None:
                thumb_size = (max_height * 10, max_height)  # Very wide to only constrain height
            else:
                thumb_size = (128, 128)  # Default thumbnail size

            # Determine output path
            if output:
                output_path = self._resolve_path(output)
            else:
                base, ext = os.path.splitext(input_path)
                output_path = Path(f"{base}_thumb{ext}")

            # Open image
            img = Image.open(input_path)
            original_size = img.size
            original_mode = img.mode

            # Create thumbnail (modifies in place, preserves aspect ratio)
            img.thumbnail(thumb_size, Image.Resampling.LANCZOS)
            thumb_size_actual = img.size

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

            # Save with quality setting
            save_kwargs: dict[str, Any] = {}
            fmt = _get_format_from_path(str(output_path))
            if fmt in ["jpeg", "webp"]:
                save_kwargs["quality"] = quality
            if fmt == "jpeg" and original_mode == "RGBA":
                img = img.convert("RGB")

            img.save(output_path, **save_kwargs)
            output_size = os.path.getsize(output_path)

            logger.info(
                "image_thumbnail_success",
                output=str(output_path),
                thumb_size=thumb_size_actual,
            )

            return ToolResult(
                success=True,
                output=f"Thumbnail created: {original_size[0]}x{original_size[1]} -> {thumb_size_actual[0]}x{thumb_size_actual[1]}\nSaved to: {output_path}",
                metadata={
                    "input": str(input_path),
                    "output": str(output_path),
                    "original_width": original_size[0],
                    "original_height": original_size[1],
                    "width": thumb_size_actual[0],
                    "height": thumb_size_actual[1],
                    "output_size": output_size,
                    "quality": quality,
                },
            )

        except Exception as e:
            logger.error("image_thumbnail_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class ImageInfoTool(Tool):
    """Get information and metadata from images."""

    name = "image_info"
    description = """Get information and metadata from an image file.

Returns dimensions, format, mode, file size, and EXIF data if available.

Examples:
- Get image info: image_info(input="photo.jpg")
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to input image file",
            },
        },
        "required": ["input"],
    }

    async def execute(
        self,
        input: str,
        **kwargs: Any,
    ) -> ToolResult:
        """Get information from an image file."""
        logger.info("image_info_start", input=input)

        if not PILLOW_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Pillow library not installed. Install with: pip install Pillow",
            )

        try:
            input_path = self._resolve_path(input)

            if not os.path.exists(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Input file does not exist: {input}",
                )

            # Get file stats
            file_size = os.path.getsize(input_path)
            file_modified = datetime.fromtimestamp(os.path.getmtime(input_path))

            # Open image
            img = Image.open(input_path)

            # Basic info
            info: dict[str, Any] = {
                "path": str(input_path),
                "format": img.format or "unknown",
                "mode": img.mode,
                "width": img.size[0],
                "height": img.size[1],
                "file_size": file_size,
                "file_size_human": _human_readable_size(file_size),
                "modified": file_modified.isoformat(),
            }

            # Try to get EXIF data
            exif_data: dict[str, Any] = {}
            try:
                exif = img._getexif()
                if exif and ExifTags:
                    for tag_id, value in exif.items():
                        tag = ExifTags.TAGS.get(tag_id, tag_id)
                        # Skip binary/complex data
                        if isinstance(value, (str, int, float)):
                            exif_data[str(tag)] = value
                        elif isinstance(value, bytes) and len(value) < 100:
                            try:
                                exif_data[str(tag)] = value.decode("utf-8", errors="replace")
                            except Exception:
                                pass
            except Exception:
                pass  # EXIF not available for all formats

            info["exif"] = exif_data if exif_data else None

            # Check for animation (GIF)
            is_animated = False
            n_frames = 1
            try:
                n_frames = getattr(img, "n_frames", 1)
                is_animated = n_frames > 1
            except Exception:
                pass

            info["animated"] = is_animated
            info["frames"] = n_frames

            # Build output string
            output_lines = [
                f"Image: {os.path.basename(input_path)}",
                f"Format: {info['format']}",
                f"Dimensions: {info['width']}x{info['height']}",
                f"Mode: {info['mode']}",
                f"File size: {info['file_size_human']}",
                f"Modified: {info['modified']}",
            ]

            if is_animated:
                output_lines.append(f"Animated: Yes ({n_frames} frames)")

            if exif_data:
                output_lines.append(f"EXIF tags: {len(exif_data)}")
                # Show a few common EXIF fields
                for key in ["Make", "Model", "DateTime", "ExposureTime", "FNumber"]:
                    if key in exif_data:
                        output_lines.append(f"  {key}: {exif_data[key]}")

            logger.info("image_info_success", input=input, format=info["format"])

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata=info,
            )

        except Exception as e:
            logger.error("image_info_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))
