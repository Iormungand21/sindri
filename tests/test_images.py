"""Tests for image manipulation tools."""

import os
import tempfile
from pathlib import Path

import pytest

# Skip all tests if Pillow is not available
PIL = pytest.importorskip("PIL")
from PIL import Image

from sindri.tools.images import (
    ImageResizeTool,
    ImageCropTool,
    ImageConvertTool,
    ImageRotateTool,
    ImageThumbnailTool,
    ImageInfoTool,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_image():
    """Create a temporary test image."""
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "test.png")

        # Create a 100x100 red image
        img = Image.new("RGB", (100, 100), color="red")
        img.save(img_path)

        yield img_path, tmpdir


@pytest.fixture
def sample_rgba_image():
    """Create a temporary RGBA test image with transparency."""
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "test_rgba.png")

        # Create a 100x100 RGBA image with semi-transparent green
        img = Image.new("RGBA", (100, 100), color=(0, 255, 0, 128))
        img.save(img_path)

        yield img_path, tmpdir


@pytest.fixture
def sample_large_image():
    """Create a larger test image for resize/thumbnail tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "large.jpg")

        # Create a 800x600 image with gradient
        img = Image.new("RGB", (800, 600), color="blue")
        img.save(img_path, quality=95)

        yield img_path, tmpdir


@pytest.fixture
def sample_jpeg_image():
    """Create a temporary JPEG test image."""
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "test.jpg")

        img = Image.new("RGB", (200, 150), color="yellow")
        img.save(img_path, quality=90)

        yield img_path, tmpdir


# =============================================================================
# ImageResizeTool Tests
# =============================================================================


class TestImageResizeTool:
    """Tests for ImageResizeTool."""

    @pytest.fixture
    def tool(self):
        return ImageResizeTool()

    @pytest.mark.asyncio
    async def test_resize_to_width(self, tool, sample_image):
        """Test resizing to specific width."""
        img_path, tmpdir = sample_image
        output = os.path.join(tmpdir, "resized.png")

        result = await tool.execute(
            input=img_path,
            output=output,
            width=50,
        )

        assert result.success
        assert os.path.exists(output)
        assert "resized" in result.output.lower()
        assert result.metadata["width"] == 50

        # Verify actual image
        resized = Image.open(output)
        assert resized.size[0] == 50

    @pytest.mark.asyncio
    async def test_resize_to_height(self, tool, sample_image):
        """Test resizing to specific height."""
        img_path, tmpdir = sample_image
        output = os.path.join(tmpdir, "resized.png")

        result = await tool.execute(
            input=img_path,
            output=output,
            height=50,
        )

        assert result.success
        assert result.metadata["height"] == 50

        resized = Image.open(output)
        assert resized.size[1] == 50

    @pytest.mark.asyncio
    async def test_resize_to_width_and_height(self, tool, sample_image):
        """Test resizing to specific width and height."""
        img_path, tmpdir = sample_image
        output = os.path.join(tmpdir, "resized.png")

        result = await tool.execute(
            input=img_path,
            output=output,
            width=50,
            height=30,
            maintain_aspect=False,
        )

        assert result.success

        resized = Image.open(output)
        assert resized.size == (50, 30)

    @pytest.mark.asyncio
    async def test_resize_maintain_aspect(self, tool, sample_large_image):
        """Test resizing while maintaining aspect ratio."""
        img_path, tmpdir = sample_large_image
        output = os.path.join(tmpdir, "resized.jpg")

        result = await tool.execute(
            input=img_path,
            output=output,
            width=400,
            maintain_aspect=True,
        )

        assert result.success

        resized = Image.open(output)
        # Original is 800x600 (4:3), resized width is 400, so height should be 300
        assert resized.size[0] == 400
        assert resized.size[1] == 300

    @pytest.mark.asyncio
    async def test_resize_by_scale(self, tool, sample_image):
        """Test resizing by scale percentage."""
        img_path, tmpdir = sample_image
        output = os.path.join(tmpdir, "resized.png")

        result = await tool.execute(
            input=img_path,
            output=output,
            scale=50,
        )

        assert result.success

        resized = Image.open(output)
        assert resized.size == (50, 50)

    @pytest.mark.asyncio
    async def test_resize_default_output(self, tool, sample_image):
        """Test resizing with default output path."""
        img_path, tmpdir = sample_image

        result = await tool.execute(
            input=img_path,
            width=50,
        )

        assert result.success
        # Default output should be input_resized.ext
        expected_output = os.path.join(tmpdir, "test_resized.png")
        assert result.metadata["output"] == expected_output
        assert os.path.exists(expected_output)

    @pytest.mark.asyncio
    async def test_resize_with_quality(self, tool, sample_jpeg_image):
        """Test resizing with quality setting."""
        img_path, tmpdir = sample_jpeg_image
        output = os.path.join(tmpdir, "resized.jpg")

        result = await tool.execute(
            input=img_path,
            output=output,
            width=100,
            quality=50,
        )

        assert result.success
        assert result.metadata["quality"] == 50

    @pytest.mark.asyncio
    async def test_resize_nonexistent_file(self, tool):
        """Test resizing nonexistent file."""
        result = await tool.execute(
            input="/nonexistent/image.png",
            width=50,
        )

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_resize_no_dimensions(self, tool, sample_image):
        """Test resizing without specifying dimensions."""
        img_path, tmpdir = sample_image

        result = await tool.execute(input=img_path)

        assert not result.success
        assert "must specify" in result.error.lower()

    @pytest.mark.asyncio
    async def test_resize_different_resample_methods(self, tool, sample_image):
        """Test different resampling methods."""
        img_path, tmpdir = sample_image

        for method in ["nearest", "bilinear", "bicubic", "lanczos"]:
            output = os.path.join(tmpdir, f"resized_{method}.png")
            result = await tool.execute(
                input=img_path,
                output=output,
                width=50,
                resample=method,
            )

            assert result.success
            assert result.metadata["resample"] == method


# =============================================================================
# ImageCropTool Tests
# =============================================================================


class TestImageCropTool:
    """Tests for ImageCropTool."""

    @pytest.fixture
    def tool(self):
        return ImageCropTool()

    @pytest.mark.asyncio
    async def test_crop_basic(self, tool, sample_image):
        """Test basic cropping."""
        img_path, tmpdir = sample_image
        output = os.path.join(tmpdir, "cropped.png")

        result = await tool.execute(
            input=img_path,
            output=output,
            x=10,
            y=10,
            width=50,
            height=50,
        )

        assert result.success
        assert os.path.exists(output)
        assert result.metadata["width"] == 50
        assert result.metadata["height"] == 50

        cropped = Image.open(output)
        assert cropped.size == (50, 50)

    @pytest.mark.asyncio
    async def test_crop_from_origin(self, tool, sample_image):
        """Test cropping from origin."""
        img_path, tmpdir = sample_image
        output = os.path.join(tmpdir, "cropped.png")

        result = await tool.execute(
            input=img_path,
            output=output,
            x=0,
            y=0,
            width=30,
            height=30,
        )

        assert result.success
        cropped = Image.open(output)
        assert cropped.size == (30, 30)

    @pytest.mark.asyncio
    async def test_crop_exceeds_bounds(self, tool, sample_image):
        """Test cropping with region exceeding image bounds."""
        img_path, tmpdir = sample_image

        result = await tool.execute(
            input=img_path,
            x=50,
            y=50,
            width=100,
            height=100,
        )

        assert not result.success
        assert "exceeds" in result.error.lower()

    @pytest.mark.asyncio
    async def test_crop_negative_coords(self, tool, sample_image):
        """Test cropping with negative coordinates."""
        img_path, tmpdir = sample_image

        result = await tool.execute(
            input=img_path,
            x=-10,
            y=0,
            width=50,
            height=50,
        )

        assert not result.success
        assert "non-negative" in result.error.lower()

    @pytest.mark.asyncio
    async def test_crop_default_output(self, tool, sample_image):
        """Test cropping with default output path."""
        img_path, tmpdir = sample_image

        result = await tool.execute(
            input=img_path,
            x=0,
            y=0,
            width=50,
            height=50,
        )

        assert result.success
        expected_output = os.path.join(tmpdir, "test_cropped.png")
        assert result.metadata["output"] == expected_output

    @pytest.mark.asyncio
    async def test_crop_nonexistent_file(self, tool):
        """Test cropping nonexistent file."""
        result = await tool.execute(
            input="/nonexistent/image.png",
            x=0,
            y=0,
            width=50,
            height=50,
        )

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_crop_full_image(self, tool, sample_image):
        """Test cropping entire image."""
        img_path, tmpdir = sample_image
        output = os.path.join(tmpdir, "cropped.png")

        result = await tool.execute(
            input=img_path,
            output=output,
            x=0,
            y=0,
            width=100,
            height=100,
        )

        assert result.success
        cropped = Image.open(output)
        assert cropped.size == (100, 100)


# =============================================================================
# ImageConvertTool Tests
# =============================================================================


class TestImageConvertTool:
    """Tests for ImageConvertTool."""

    @pytest.fixture
    def tool(self):
        return ImageConvertTool()

    @pytest.mark.asyncio
    async def test_convert_png_to_jpeg(self, tool, sample_image):
        """Test converting PNG to JPEG."""
        img_path, tmpdir = sample_image
        output = os.path.join(tmpdir, "converted.jpg")

        result = await tool.execute(
            input=img_path,
            format="jpeg",
            output=output,
        )

        assert result.success
        assert os.path.exists(output)
        assert result.metadata["new_format"] == "jpeg"

        converted = Image.open(output)
        assert converted.format == "JPEG"

    @pytest.mark.asyncio
    async def test_convert_jpeg_to_png(self, tool, sample_jpeg_image):
        """Test converting JPEG to PNG."""
        img_path, tmpdir = sample_jpeg_image
        output = os.path.join(tmpdir, "converted.png")

        result = await tool.execute(
            input=img_path,
            format="png",
            output=output,
        )

        assert result.success
        converted = Image.open(output)
        assert converted.format == "PNG"

    @pytest.mark.asyncio
    async def test_convert_to_webp(self, tool, sample_image):
        """Test converting to WebP."""
        img_path, tmpdir = sample_image
        output = os.path.join(tmpdir, "converted.webp")

        result = await tool.execute(
            input=img_path,
            format="webp",
            output=output,
            quality=80,
        )

        assert result.success
        converted = Image.open(output)
        assert converted.format == "WEBP"

    @pytest.mark.asyncio
    async def test_convert_to_gif(self, tool, sample_image):
        """Test converting to GIF."""
        img_path, tmpdir = sample_image
        output = os.path.join(tmpdir, "converted.gif")

        result = await tool.execute(
            input=img_path,
            format="gif",
            output=output,
        )

        assert result.success
        converted = Image.open(output)
        assert converted.format == "GIF"

    @pytest.mark.asyncio
    async def test_convert_to_bmp(self, tool, sample_image):
        """Test converting to BMP."""
        img_path, tmpdir = sample_image
        output = os.path.join(tmpdir, "converted.bmp")

        result = await tool.execute(
            input=img_path,
            format="bmp",
            output=output,
        )

        assert result.success
        converted = Image.open(output)
        assert converted.format == "BMP"

    @pytest.mark.asyncio
    async def test_convert_rgba_to_jpeg(self, tool, sample_rgba_image):
        """Test converting RGBA to JPEG (handles transparency)."""
        img_path, tmpdir = sample_rgba_image
        output = os.path.join(tmpdir, "converted.jpg")

        result = await tool.execute(
            input=img_path,
            format="jpeg",
            output=output,
        )

        assert result.success
        converted = Image.open(output)
        assert converted.format == "JPEG"
        assert converted.mode == "RGB"

    @pytest.mark.asyncio
    async def test_convert_default_output(self, tool, sample_image):
        """Test conversion with default output path."""
        img_path, tmpdir = sample_image

        result = await tool.execute(
            input=img_path,
            format="jpeg",
        )

        assert result.success
        expected_output = os.path.join(tmpdir, "test.jpg")
        assert result.metadata["output"] == expected_output

    @pytest.mark.asyncio
    async def test_convert_nonexistent_file(self, tool):
        """Test converting nonexistent file."""
        result = await tool.execute(
            input="/nonexistent/image.png",
            format="jpeg",
        )

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_convert_with_quality(self, tool, sample_image):
        """Test conversion with quality setting."""
        img_path, tmpdir = sample_image
        output_low = os.path.join(tmpdir, "low.jpg")
        output_high = os.path.join(tmpdir, "high.jpg")

        await tool.execute(input=img_path, format="jpeg", output=output_low, quality=20)
        await tool.execute(input=img_path, format="jpeg", output=output_high, quality=95)

        # Higher quality should result in larger file
        assert os.path.getsize(output_low) < os.path.getsize(output_high)


# =============================================================================
# ImageRotateTool Tests
# =============================================================================


class TestImageRotateTool:
    """Tests for ImageRotateTool."""

    @pytest.fixture
    def tool(self):
        return ImageRotateTool()

    @pytest.mark.asyncio
    async def test_rotate_90_degrees(self, tool, sample_large_image):
        """Test rotating 90 degrees."""
        img_path, tmpdir = sample_large_image
        output = os.path.join(tmpdir, "rotated.jpg")

        result = await tool.execute(
            input=img_path,
            output=output,
            angle=90,
            expand=True,
        )

        assert result.success
        rotated = Image.open(output)
        # 800x600 rotated 90 degrees with expand should be 600x800
        assert rotated.size == (600, 800)

    @pytest.mark.asyncio
    async def test_rotate_180_degrees(self, tool, sample_image):
        """Test rotating 180 degrees."""
        img_path, tmpdir = sample_image
        output = os.path.join(tmpdir, "rotated.png")

        result = await tool.execute(
            input=img_path,
            output=output,
            angle=180,
        )

        assert result.success
        rotated = Image.open(output)
        # 180 degree rotation keeps same size
        assert rotated.size == (100, 100)

    @pytest.mark.asyncio
    async def test_rotate_45_degrees_no_expand(self, tool, sample_image):
        """Test rotating 45 degrees without expanding."""
        img_path, tmpdir = sample_image
        output = os.path.join(tmpdir, "rotated.png")

        result = await tool.execute(
            input=img_path,
            output=output,
            angle=45,
            expand=False,
        )

        assert result.success
        rotated = Image.open(output)
        # Without expand, size stays the same
        assert rotated.size == (100, 100)

    @pytest.mark.asyncio
    async def test_rotate_45_degrees_with_expand(self, tool, sample_image):
        """Test rotating 45 degrees with expanding."""
        img_path, tmpdir = sample_image
        output = os.path.join(tmpdir, "rotated.png")

        result = await tool.execute(
            input=img_path,
            output=output,
            angle=45,
            expand=True,
        )

        assert result.success
        rotated = Image.open(output)
        # With expand, size should be larger
        assert rotated.size[0] > 100
        assert rotated.size[1] > 100

    @pytest.mark.asyncio
    async def test_rotate_with_fill_color(self, tool, sample_image):
        """Test rotating with fill color."""
        img_path, tmpdir = sample_image
        output = os.path.join(tmpdir, "rotated.png")

        result = await tool.execute(
            input=img_path,
            output=output,
            angle=45,
            expand=True,
            fill_color="white",
        )

        assert result.success
        assert os.path.exists(output)

    @pytest.mark.asyncio
    async def test_rotate_default_output(self, tool, sample_image):
        """Test rotation with default output path."""
        img_path, tmpdir = sample_image

        result = await tool.execute(
            input=img_path,
            angle=90,
        )

        assert result.success
        expected_output = os.path.join(tmpdir, "test_rotated.png")
        assert result.metadata["output"] == expected_output

    @pytest.mark.asyncio
    async def test_rotate_nonexistent_file(self, tool):
        """Test rotating nonexistent file."""
        result = await tool.execute(
            input="/nonexistent/image.png",
            angle=90,
        )

        assert not result.success
        assert "does not exist" in result.error


# =============================================================================
# ImageThumbnailTool Tests
# =============================================================================


class TestImageThumbnailTool:
    """Tests for ImageThumbnailTool."""

    @pytest.fixture
    def tool(self):
        return ImageThumbnailTool()

    @pytest.mark.asyncio
    async def test_thumbnail_default_size(self, tool, sample_large_image):
        """Test thumbnail with default size."""
        img_path, tmpdir = sample_large_image
        output = os.path.join(tmpdir, "thumb.jpg")

        result = await tool.execute(
            input=img_path,
            output=output,
        )

        assert result.success
        thumb = Image.open(output)
        # Default is 128, aspect preserved
        assert max(thumb.size) <= 128

    @pytest.mark.asyncio
    async def test_thumbnail_custom_size(self, tool, sample_large_image):
        """Test thumbnail with custom size."""
        img_path, tmpdir = sample_large_image
        output = os.path.join(tmpdir, "thumb.jpg")

        result = await tool.execute(
            input=img_path,
            output=output,
            max_size=64,
        )

        assert result.success
        thumb = Image.open(output)
        assert max(thumb.size) <= 64

    @pytest.mark.asyncio
    async def test_thumbnail_max_width_height(self, tool, sample_large_image):
        """Test thumbnail with separate max width and height."""
        img_path, tmpdir = sample_large_image
        output = os.path.join(tmpdir, "thumb.jpg")

        result = await tool.execute(
            input=img_path,
            output=output,
            max_width=200,
            max_height=100,
        )

        assert result.success
        thumb = Image.open(output)
        assert thumb.size[0] <= 200
        assert thumb.size[1] <= 100

    @pytest.mark.asyncio
    async def test_thumbnail_preserves_aspect(self, tool, sample_large_image):
        """Test that thumbnail preserves aspect ratio."""
        img_path, tmpdir = sample_large_image
        output = os.path.join(tmpdir, "thumb.jpg")

        result = await tool.execute(
            input=img_path,
            output=output,
            max_size=100,
        )

        assert result.success
        thumb = Image.open(output)
        original = Image.open(img_path)

        # Calculate aspect ratios
        orig_aspect = original.size[0] / original.size[1]
        thumb_aspect = thumb.size[0] / thumb.size[1]

        # Should be approximately equal
        assert abs(orig_aspect - thumb_aspect) < 0.01

    @pytest.mark.asyncio
    async def test_thumbnail_default_output(self, tool, sample_image):
        """Test thumbnail with default output path."""
        img_path, tmpdir = sample_image

        result = await tool.execute(input=img_path)

        assert result.success
        expected_output = os.path.join(tmpdir, "test_thumb.png")
        assert result.metadata["output"] == expected_output

    @pytest.mark.asyncio
    async def test_thumbnail_nonexistent_file(self, tool):
        """Test thumbnail of nonexistent file."""
        result = await tool.execute(input="/nonexistent/image.png")

        assert not result.success
        assert "does not exist" in result.error


# =============================================================================
# ImageInfoTool Tests
# =============================================================================


class TestImageInfoTool:
    """Tests for ImageInfoTool."""

    @pytest.fixture
    def tool(self):
        return ImageInfoTool()

    @pytest.mark.asyncio
    async def test_info_basic(self, tool, sample_image):
        """Test getting basic image info."""
        img_path, tmpdir = sample_image

        result = await tool.execute(input=img_path)

        assert result.success
        assert "PNG" in result.output.upper()
        assert "100" in result.output  # dimensions
        assert result.metadata["width"] == 100
        assert result.metadata["height"] == 100
        assert result.metadata["format"] == "PNG"

    @pytest.mark.asyncio
    async def test_info_jpeg(self, tool, sample_jpeg_image):
        """Test getting JPEG image info."""
        img_path, tmpdir = sample_jpeg_image

        result = await tool.execute(input=img_path)

        assert result.success
        assert result.metadata["format"] == "JPEG"
        assert result.metadata["width"] == 200
        assert result.metadata["height"] == 150

    @pytest.mark.asyncio
    async def test_info_rgba(self, tool, sample_rgba_image):
        """Test getting RGBA image info."""
        img_path, tmpdir = sample_rgba_image

        result = await tool.execute(input=img_path)

        assert result.success
        assert result.metadata["mode"] == "RGBA"

    @pytest.mark.asyncio
    async def test_info_file_size(self, tool, sample_image):
        """Test that file size is reported."""
        img_path, tmpdir = sample_image

        result = await tool.execute(input=img_path)

        assert result.success
        assert result.metadata["file_size"] > 0
        assert "file_size_human" in result.metadata

    @pytest.mark.asyncio
    async def test_info_nonexistent_file(self, tool):
        """Test info on nonexistent file."""
        result = await tool.execute(input="/nonexistent/image.png")

        assert not result.success
        assert "does not exist" in result.error


# =============================================================================
# Integration Tests
# =============================================================================


class TestImageRoundTrip:
    """Integration tests for image operations."""

    @pytest.mark.asyncio
    async def test_resize_then_crop(self, sample_large_image):
        """Test resizing then cropping."""
        img_path, tmpdir = sample_large_image

        resize_tool = ImageResizeTool()
        crop_tool = ImageCropTool()

        # First resize
        resized = os.path.join(tmpdir, "resized.jpg")
        result1 = await resize_tool.execute(
            input=img_path,
            output=resized,
            width=400,
        )
        assert result1.success

        # Then crop
        cropped = os.path.join(tmpdir, "cropped.jpg")
        result2 = await crop_tool.execute(
            input=resized,
            output=cropped,
            x=50,
            y=50,
            width=100,
            height=100,
        )
        assert result2.success

        final = Image.open(cropped)
        assert final.size == (100, 100)

    @pytest.mark.asyncio
    async def test_convert_then_resize(self, sample_image):
        """Test converting then resizing."""
        img_path, tmpdir = sample_image

        convert_tool = ImageConvertTool()
        resize_tool = ImageResizeTool()

        # Convert to JPEG
        converted = os.path.join(tmpdir, "converted.jpg")
        result1 = await convert_tool.execute(
            input=img_path,
            format="jpeg",
            output=converted,
        )
        assert result1.success

        # Resize
        resized = os.path.join(tmpdir, "resized.jpg")
        result2 = await resize_tool.execute(
            input=converted,
            output=resized,
            width=50,
        )
        assert result2.success

        final = Image.open(resized)
        assert final.format == "JPEG"
        assert final.size[0] == 50

    @pytest.mark.asyncio
    async def test_rotate_then_thumbnail(self, sample_large_image):
        """Test rotating then creating thumbnail."""
        img_path, tmpdir = sample_large_image

        rotate_tool = ImageRotateTool()
        thumb_tool = ImageThumbnailTool()

        # Rotate
        rotated = os.path.join(tmpdir, "rotated.jpg")
        result1 = await rotate_tool.execute(
            input=img_path,
            output=rotated,
            angle=90,
            expand=True,
        )
        assert result1.success

        # Thumbnail
        thumb = os.path.join(tmpdir, "thumb.jpg")
        result2 = await thumb_tool.execute(
            input=rotated,
            output=thumb,
            max_size=64,
        )
        assert result2.success

        final = Image.open(thumb)
        assert max(final.size) <= 64

    @pytest.mark.asyncio
    async def test_multiple_format_conversions(self, sample_image):
        """Test converting through multiple formats."""
        img_path, tmpdir = sample_image

        tool = ImageConvertTool()

        # PNG -> JPEG
        jpeg = os.path.join(tmpdir, "step1.jpg")
        await tool.execute(input=img_path, format="jpeg", output=jpeg)

        # JPEG -> WebP
        webp = os.path.join(tmpdir, "step2.webp")
        await tool.execute(input=jpeg, format="webp", output=webp)

        # WebP -> PNG
        png = os.path.join(tmpdir, "step3.png")
        result = await tool.execute(input=webp, format="png", output=png)

        assert result.success
        final = Image.open(png)
        assert final.format == "PNG"
