"""Tests for compression and archive tools.

Phase 12 Tier 1 - Universal Tool Expansion.
"""

import bz2
import gzip
import lzma
import os
import tarfile
import tempfile
import zipfile
from pathlib import Path

import pytest

from sindri.tools.compression import (
    ArchiveCreateTool,
    ArchiveExtractTool,
    ArchiveListTool,
    CompressFileTool,
    DecompressFileTool,
    BROTLI_AVAILABLE,
)


class TestArchiveCreateTool:
    """Tests for ArchiveCreateTool."""

    @pytest.fixture
    def tool(self):
        return ArchiveCreateTool()

    @pytest.fixture
    def temp_files(self):
        """Create temporary test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            file1 = Path(tmpdir) / "file1.txt"
            file1.write_text("Hello, World!")

            file2 = Path(tmpdir) / "file2.txt"
            file2.write_text("Test content")

            # Create a subdirectory with files
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            (subdir / "nested.txt").write_text("Nested content")
            (subdir / "data.json").write_text('{"key": "value"}')

            # Create some files to exclude
            (Path(tmpdir) / "temp.pyc").write_bytes(b"bytecode")
            cache_dir = Path(tmpdir) / "__pycache__"
            cache_dir.mkdir()
            (cache_dir / "cached.pyc").write_bytes(b"cached")

            yield tmpdir

    @pytest.mark.asyncio
    async def test_create_zip_single_file(self, tool, temp_files):
        """Test creating a zip archive from a single file."""
        output = os.path.join(temp_files, "output.zip")
        file1 = os.path.join(temp_files, "file1.txt")

        result = await tool.execute(output=output, paths=[file1])

        assert result.success
        assert os.path.exists(output)
        assert "Archive created" in result.output
        assert result.metadata["format"] == "zip"
        assert result.metadata["files_added"] == 1

        # Verify contents (path may include temp directory prefix)
        with zipfile.ZipFile(output, "r") as zf:
            names = zf.namelist()
            assert any("file1.txt" in name for name in names)

    @pytest.mark.asyncio
    async def test_create_zip_multiple_files(self, tool, temp_files):
        """Test creating a zip archive from multiple files."""
        output = os.path.join(temp_files, "output.zip")
        file1 = os.path.join(temp_files, "file1.txt")
        file2 = os.path.join(temp_files, "file2.txt")

        result = await tool.execute(output=output, paths=[file1, file2])

        assert result.success
        assert result.metadata["files_added"] == 2

    @pytest.mark.asyncio
    async def test_create_zip_directory(self, tool, temp_files):
        """Test creating a zip archive from a directory."""
        output = os.path.join(temp_files, "output.zip")
        subdir = os.path.join(temp_files, "subdir")

        result = await tool.execute(output=output, paths=[subdir])

        assert result.success
        assert result.metadata["files_added"] == 2  # nested.txt and data.json

    @pytest.mark.asyncio
    async def test_create_tar_gz(self, tool, temp_files):
        """Test creating a tar.gz archive."""
        output = os.path.join(temp_files, "output.tar.gz")
        file1 = os.path.join(temp_files, "file1.txt")

        result = await tool.execute(output=output, paths=[file1])

        assert result.success
        assert result.metadata["format"] == "tar"
        assert result.metadata["compression"] == "gz"

        # Verify contents
        with tarfile.open(output, "r:gz") as tf:
            names = tf.getnames()
            assert any("file1.txt" in n for n in names)

    @pytest.mark.asyncio
    async def test_create_tar_bz2(self, tool, temp_files):
        """Test creating a tar.bz2 archive."""
        output = os.path.join(temp_files, "output.tar.bz2")
        file1 = os.path.join(temp_files, "file1.txt")

        result = await tool.execute(output=output, paths=[file1])

        assert result.success
        assert result.metadata["format"] == "tar"
        assert result.metadata["compression"] == "bz2"

    @pytest.mark.asyncio
    async def test_create_tar_xz(self, tool, temp_files):
        """Test creating a tar.xz archive."""
        output = os.path.join(temp_files, "output.tar.xz")
        file1 = os.path.join(temp_files, "file1.txt")

        result = await tool.execute(output=output, paths=[file1])

        assert result.success
        assert result.metadata["format"] == "tar"
        assert result.metadata["compression"] == "xz"

    @pytest.mark.asyncio
    async def test_create_plain_tar(self, tool, temp_files):
        """Test creating a plain tar archive (no compression)."""
        output = os.path.join(temp_files, "output.tar")
        file1 = os.path.join(temp_files, "file1.txt")

        result = await tool.execute(output=output, paths=[file1])

        assert result.success
        assert result.metadata["format"] == "tar"
        assert result.metadata["compression"] is None

    @pytest.mark.asyncio
    async def test_create_with_exclude_patterns(self, tool, temp_files):
        """Test creating archive with exclude patterns."""
        output = os.path.join(temp_files, "output.zip")

        result = await tool.execute(
            output=output,
            paths=[temp_files],
            exclude=["*.pyc", "__pycache__"],
        )

        assert result.success
        # Should not include .pyc files or __pycache__ directory
        with zipfile.ZipFile(output, "r") as zf:
            names = zf.namelist()
            assert not any(".pyc" in n for n in names)
            assert not any("__pycache__" in n for n in names)

    @pytest.mark.asyncio
    async def test_create_with_compression_level(self, tool, temp_files):
        """Test creating archive with custom compression level."""
        output = os.path.join(temp_files, "output.zip")
        file1 = os.path.join(temp_files, "file1.txt")

        result = await tool.execute(
            output=output,
            paths=[file1],
            compression_level=9,
        )

        assert result.success
        assert "compression_ratio" in result.metadata

    @pytest.mark.asyncio
    async def test_create_nonexistent_path(self, tool, temp_files):
        """Test creating archive with nonexistent path fails."""
        output = os.path.join(temp_files, "output.zip")

        result = await tool.execute(
            output=output,
            paths=["/nonexistent/path/file.txt"],
        )

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_tgz_extension(self, tool, temp_files):
        """Test .tgz extension is recognized."""
        output = os.path.join(temp_files, "output.tgz")
        file1 = os.path.join(temp_files, "file1.txt")

        result = await tool.execute(output=output, paths=[file1])

        assert result.success
        assert result.metadata["format"] == "tar"
        assert result.metadata["compression"] == "gz"


class TestArchiveExtractTool:
    """Tests for ArchiveExtractTool."""

    @pytest.fixture
    def tool(self):
        return ArchiveExtractTool()

    @pytest.fixture
    def zip_archive(self):
        """Create a temporary zip archive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = os.path.join(tmpdir, "test.zip")
            with zipfile.ZipFile(archive_path, "w") as zf:
                zf.writestr("file1.txt", "Content 1")
                zf.writestr("file2.txt", "Content 2")
                zf.writestr("subdir/nested.txt", "Nested content")
            yield archive_path, tmpdir

    @pytest.fixture
    def tar_gz_archive(self):
        """Create a temporary tar.gz archive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = os.path.join(tmpdir, "test.tar.gz")
            with tarfile.open(archive_path, "w:gz") as tf:
                # Add files using TarInfo
                data1 = b"Content 1"
                info1 = tarfile.TarInfo(name="file1.txt")
                info1.size = len(data1)
                tf.addfile(info1, fileobj=__import__("io").BytesIO(data1))

                data2 = b"Content 2"
                info2 = tarfile.TarInfo(name="file2.txt")
                info2.size = len(data2)
                tf.addfile(info2, fileobj=__import__("io").BytesIO(data2))
            yield archive_path, tmpdir

    @pytest.mark.asyncio
    async def test_extract_zip(self, tool, zip_archive):
        """Test extracting a zip archive."""
        archive_path, tmpdir = zip_archive
        output_dir = os.path.join(tmpdir, "extracted")

        result = await tool.execute(archive=archive_path, output_dir=output_dir)

        assert result.success
        assert os.path.exists(os.path.join(output_dir, "file1.txt"))
        assert os.path.exists(os.path.join(output_dir, "file2.txt"))
        assert result.metadata["files_extracted"] >= 2

    @pytest.mark.asyncio
    async def test_extract_tar_gz(self, tool, tar_gz_archive):
        """Test extracting a tar.gz archive."""
        archive_path, tmpdir = tar_gz_archive
        output_dir = os.path.join(tmpdir, "extracted")

        result = await tool.execute(archive=archive_path, output_dir=output_dir)

        assert result.success
        assert result.metadata["format"] == "tar"
        assert result.metadata["compression"] == "gz"

    @pytest.mark.asyncio
    async def test_extract_specific_files(self, tool, zip_archive):
        """Test extracting specific files from archive."""
        archive_path, tmpdir = zip_archive
        output_dir = os.path.join(tmpdir, "extracted")

        result = await tool.execute(
            archive=archive_path,
            output_dir=output_dir,
            files=["file1.txt"],
        )

        assert result.success
        assert os.path.exists(os.path.join(output_dir, "file1.txt"))
        # file2.txt should not be extracted
        assert result.metadata["files_extracted"] == 1

    @pytest.mark.asyncio
    async def test_extract_to_current_dir(self, tool, zip_archive):
        """Test extracting to current directory."""
        archive_path, tmpdir = zip_archive

        # Use tool with work_dir set
        tool_with_dir = ArchiveExtractTool(work_dir=Path(tmpdir))
        result = await tool_with_dir.execute(archive=archive_path)

        assert result.success
        assert os.path.exists(os.path.join(tmpdir, "file1.txt"))

    @pytest.mark.asyncio
    async def test_extract_nonexistent_archive(self, tool):
        """Test extracting nonexistent archive fails."""
        result = await tool.execute(archive="/nonexistent/archive.zip")

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_extract_no_overwrite(self, tool, zip_archive):
        """Test extract with no-overwrite flag."""
        archive_path, tmpdir = zip_archive
        output_dir = os.path.join(tmpdir, "extracted")
        os.makedirs(output_dir)

        # Create existing file
        existing = os.path.join(output_dir, "file1.txt")
        with open(existing, "w") as f:
            f.write("Original")

        result = await tool.execute(
            archive=archive_path,
            output_dir=output_dir,
            overwrite=False,
        )

        assert result.success
        # Original file should not be overwritten
        with open(existing) as f:
            assert f.read() == "Original"


class TestArchiveListTool:
    """Tests for ArchiveListTool."""

    @pytest.fixture
    def tool(self):
        return ArchiveListTool()

    @pytest.fixture
    def zip_archive(self):
        """Create a temporary zip archive for listing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = os.path.join(tmpdir, "test.zip")
            with zipfile.ZipFile(archive_path, "w") as zf:
                zf.writestr("file1.txt", "Content 1")
                zf.writestr("file2.txt", "Content 2 with more data")
                zf.writestr("subdir/", "")  # Directory entry
                zf.writestr("subdir/nested.txt", "Nested")
            yield archive_path

    @pytest.fixture
    def tar_archive(self):
        """Create a temporary tar archive for listing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = os.path.join(tmpdir, "test.tar")
            with tarfile.open(archive_path, "w") as tf:
                data = b"Content"
                info = tarfile.TarInfo(name="file.txt")
                info.size = len(data)
                tf.addfile(info, fileobj=__import__("io").BytesIO(data))
            yield archive_path

    @pytest.mark.asyncio
    async def test_list_zip(self, tool, zip_archive):
        """Test listing zip archive contents."""
        result = await tool.execute(archive=zip_archive)

        assert result.success
        assert "file1.txt" in result.output
        assert "file2.txt" in result.output
        assert result.metadata["file_count"] >= 3

    @pytest.mark.asyncio
    async def test_list_tar(self, tool, tar_archive):
        """Test listing tar archive contents."""
        result = await tool.execute(archive=tar_archive)

        assert result.success
        assert "file.txt" in result.output

    @pytest.mark.asyncio
    async def test_list_detailed(self, tool, zip_archive):
        """Test detailed listing with sizes and dates."""
        result = await tool.execute(archive=zip_archive, detailed=True)

        assert result.success
        # Detailed output includes size column
        assert "Size" in result.output or any(
            entry.get("size", 0) > 0 for entry in result.metadata.get("entries", [])
        )

    @pytest.mark.asyncio
    async def test_list_nonexistent_archive(self, tool):
        """Test listing nonexistent archive fails."""
        result = await tool.execute(archive="/nonexistent/archive.zip")

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_list_metadata_entries(self, tool, zip_archive):
        """Test that metadata contains entry details."""
        result = await tool.execute(archive=zip_archive)

        assert result.success
        assert "entries" in result.metadata
        assert len(result.metadata["entries"]) > 0
        assert "name" in result.metadata["entries"][0]
        assert "size" in result.metadata["entries"][0]


class TestCompressFileTool:
    """Tests for CompressFileTool."""

    @pytest.fixture
    def tool(self):
        return CompressFileTool()

    @pytest.fixture
    def temp_file(self):
        """Create a temporary file to compress."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.txt")
            # Create a file with some content
            content = "Hello, World! " * 100  # Repeating content compresses well
            with open(file_path, "w") as f:
                f.write(content)
            yield file_path, tmpdir

    @pytest.mark.asyncio
    async def test_compress_gzip(self, tool, temp_file):
        """Test gzip compression."""
        file_path, tmpdir = temp_file

        result = await tool.execute(input=file_path, format="gzip")

        assert result.success
        assert os.path.exists(file_path + ".gz")
        assert result.metadata["format"] == "gzip"
        assert result.metadata["compression_ratio"] > 0

        # Verify decompression
        with gzip.open(file_path + ".gz", "rt") as f:
            content = f.read()
        assert "Hello, World!" in content

    @pytest.mark.asyncio
    async def test_compress_bz2(self, tool, temp_file):
        """Test bz2 compression."""
        file_path, tmpdir = temp_file

        result = await tool.execute(input=file_path, format="bz2")

        assert result.success
        assert os.path.exists(file_path + ".bz2")
        assert result.metadata["format"] == "bz2"

        # Verify decompression
        with bz2.open(file_path + ".bz2", "rt") as f:
            content = f.read()
        assert "Hello, World!" in content

    @pytest.mark.asyncio
    async def test_compress_xz(self, tool, temp_file):
        """Test xz/lzma compression."""
        file_path, tmpdir = temp_file

        result = await tool.execute(input=file_path, format="xz")

        assert result.success
        assert os.path.exists(file_path + ".xz")
        assert result.metadata["format"] == "xz"

        # Verify decompression
        with lzma.open(file_path + ".xz", "rt") as f:
            content = f.read()
        assert "Hello, World!" in content

    @pytest.mark.asyncio
    @pytest.mark.skipif(not BROTLI_AVAILABLE, reason="Brotli not installed")
    async def test_compress_brotli(self, tool, temp_file):
        """Test brotli compression."""
        file_path, tmpdir = temp_file

        result = await tool.execute(input=file_path, format="brotli")

        assert result.success
        assert os.path.exists(file_path + ".br")
        assert result.metadata["format"] == "brotli"

    @pytest.mark.asyncio
    async def test_compress_custom_output(self, tool, temp_file):
        """Test compression with custom output path."""
        file_path, tmpdir = temp_file
        output_path = os.path.join(tmpdir, "custom.gz")

        result = await tool.execute(
            input=file_path,
            format="gzip",
            output=output_path,
        )

        assert result.success
        assert os.path.exists(output_path)
        assert result.metadata["output"] == output_path

    @pytest.mark.asyncio
    async def test_compress_with_level(self, tool, temp_file):
        """Test compression with different levels."""
        file_path, tmpdir = temp_file

        # High compression
        result_high = await tool.execute(
            input=file_path,
            format="gzip",
            level=9,
            output=os.path.join(tmpdir, "high.gz"),
        )

        # Low compression
        result_low = await tool.execute(
            input=file_path,
            format="gzip",
            level=1,
            output=os.path.join(tmpdir, "low.gz"),
        )

        assert result_high.success
        assert result_low.success
        # Higher compression should produce smaller file (usually)
        high_size = result_high.metadata["compressed_size"]
        low_size = result_low.metadata["compressed_size"]
        # Just verify both work, size relationship may vary
        assert high_size > 0
        assert low_size > 0

    @pytest.mark.asyncio
    async def test_compress_nonexistent_file(self, tool):
        """Test compressing nonexistent file fails."""
        result = await tool.execute(
            input="/nonexistent/file.txt",
            format="gzip",
        )

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_compress_directory(self, tool):
        """Test compressing a directory fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await tool.execute(input=tmpdir, format="gzip")

            assert not result.success
            assert "not a file" in result.error

    @pytest.mark.asyncio
    @pytest.mark.skipif(BROTLI_AVAILABLE, reason="Brotli is installed")
    async def test_brotli_not_available(self, tool, temp_file):
        """Test brotli error when not installed."""
        file_path, tmpdir = temp_file

        result = await tool.execute(input=file_path, format="brotli")

        assert not result.success
        assert "not available" in result.error


class TestDecompressFileTool:
    """Tests for DecompressFileTool."""

    @pytest.fixture
    def tool(self):
        return DecompressFileTool()

    @pytest.fixture
    def gzip_file(self):
        """Create a gzip compressed file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.txt.gz")
            content = b"Hello, World! Compressed content."
            with gzip.open(file_path, "wb") as f:
                f.write(content)
            yield file_path, tmpdir, content

    @pytest.fixture
    def bz2_file(self):
        """Create a bz2 compressed file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.txt.bz2")
            content = b"Hello, World! BZ2 compressed."
            with bz2.open(file_path, "wb") as f:
                f.write(content)
            yield file_path, tmpdir, content

    @pytest.fixture
    def xz_file(self):
        """Create an xz compressed file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.txt.xz")
            content = b"Hello, World! XZ compressed."
            with lzma.open(file_path, "wb") as f:
                f.write(content)
            yield file_path, tmpdir, content

    @pytest.mark.asyncio
    async def test_decompress_gzip(self, tool, gzip_file):
        """Test gzip decompression."""
        file_path, tmpdir, original_content = gzip_file

        result = await tool.execute(input=file_path)

        assert result.success
        output_path = result.metadata["output"]
        assert os.path.exists(output_path)
        with open(output_path, "rb") as f:
            assert f.read() == original_content

    @pytest.mark.asyncio
    async def test_decompress_bz2(self, tool, bz2_file):
        """Test bz2 decompression."""
        file_path, tmpdir, original_content = bz2_file

        result = await tool.execute(input=file_path)

        assert result.success
        output_path = result.metadata["output"]
        with open(output_path, "rb") as f:
            assert f.read() == original_content

    @pytest.mark.asyncio
    async def test_decompress_xz(self, tool, xz_file):
        """Test xz decompression."""
        file_path, tmpdir, original_content = xz_file

        result = await tool.execute(input=file_path)

        assert result.success
        output_path = result.metadata["output"]
        with open(output_path, "rb") as f:
            assert f.read() == original_content

    @pytest.mark.asyncio
    async def test_decompress_custom_output(self, tool, gzip_file):
        """Test decompression with custom output path."""
        file_path, tmpdir, original_content = gzip_file
        output_path = os.path.join(tmpdir, "custom_output.txt")

        result = await tool.execute(input=file_path, output=output_path)

        assert result.success
        assert os.path.exists(output_path)
        with open(output_path, "rb") as f:
            assert f.read() == original_content

    @pytest.mark.asyncio
    async def test_decompress_explicit_format(self, tool, gzip_file):
        """Test decompression with explicit format."""
        file_path, tmpdir, original_content = gzip_file

        result = await tool.execute(input=file_path, format="gzip")

        assert result.success
        assert result.metadata["format"] == "gzip"

    @pytest.mark.asyncio
    async def test_decompress_auto_detect_by_extension(self, tool, gzip_file):
        """Test auto-detection by file extension."""
        file_path, tmpdir, _ = gzip_file

        result = await tool.execute(input=file_path, format="auto")

        assert result.success
        assert result.metadata["format"] == "gzip"

    @pytest.mark.asyncio
    async def test_decompress_nonexistent_file(self, tool):
        """Test decompressing nonexistent file fails."""
        result = await tool.execute(input="/nonexistent/file.gz")

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_decompress_unknown_format(self, tool):
        """Test decompression fails for unknown format."""
        with tempfile.NamedTemporaryFile(suffix=".unknown", delete=False) as f:
            f.write(b"random data")
            file_path = f.name

        try:
            result = await tool.execute(input=file_path, format="auto")

            assert not result.success
            assert "Could not auto-detect" in result.error
        finally:
            os.unlink(file_path)

    @pytest.mark.asyncio
    @pytest.mark.skipif(not BROTLI_AVAILABLE, reason="Brotli not installed")
    async def test_decompress_brotli(self, tool):
        """Test brotli decompression."""
        import brotli as br

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.txt.br")
            content = b"Hello, brotli compressed!"
            with open(file_path, "wb") as f:
                f.write(br.compress(content))

            result = await tool.execute(input=file_path)

            assert result.success
            output_path = result.metadata["output"]
            with open(output_path, "rb") as f:
                assert f.read() == content


class TestCompressionRoundTrip:
    """End-to-end tests for compression/decompression round trips."""

    @pytest.mark.asyncio
    async def test_gzip_roundtrip(self):
        """Test compressing and decompressing with gzip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            original = os.path.join(tmpdir, "original.txt")
            content = "Test content for round trip!"
            with open(original, "w") as f:
                f.write(content)

            # Compress
            compress_tool = CompressFileTool()
            compressed_path = os.path.join(tmpdir, "compressed.gz")
            result = await compress_tool.execute(
                input=original,
                format="gzip",
                output=compressed_path,
            )
            assert result.success

            # Decompress
            decompress_tool = DecompressFileTool()
            restored_path = os.path.join(tmpdir, "restored.txt")
            result = await decompress_tool.execute(
                input=compressed_path,
                output=restored_path,
            )
            assert result.success

            # Verify
            with open(restored_path) as f:
                assert f.read() == content

    @pytest.mark.asyncio
    async def test_archive_roundtrip(self):
        """Test creating and extracting an archive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            src_dir = os.path.join(tmpdir, "source")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "file1.txt"), "w") as f:
                f.write("Content 1")
            with open(os.path.join(src_dir, "file2.txt"), "w") as f:
                f.write("Content 2")

            # Create archive
            create_tool = ArchiveCreateTool()
            archive_path = os.path.join(tmpdir, "archive.zip")
            result = await create_tool.execute(
                output=archive_path,
                paths=[src_dir],
            )
            assert result.success
            assert result.metadata["files_added"] == 2

            # Extract archive
            extract_tool = ArchiveExtractTool()
            extract_dir = os.path.join(tmpdir, "extracted")
            result = await extract_tool.execute(
                archive=archive_path,
                output_dir=extract_dir,
            )
            assert result.success
            assert result.metadata["files_extracted"] == 2

            # Verify - files are extracted (paths may include temp dir prefix)
            # Check by counting files
            extracted_files = []
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    extracted_files.append(f)
            assert "file1.txt" in extracted_files
            assert "file2.txt" in extracted_files
