"""Compression and archive tools for Sindri.

Phase 12 Tier 1 - Universal Tool Expansion.
"""

import bz2
import gzip
import lzma
import os
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import structlog

from sindri.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    pass

# Check for optional brotli support
try:
    import brotli

    BROTLI_AVAILABLE = True
except ImportError:
    BROTLI_AVAILABLE = False

logger = structlog.get_logger()


class ArchiveCreateTool(Tool):
    """Create archive files from files and directories."""

    name = "archive_create"
    description = """Create archive files (zip, tar, tar.gz, tar.bz2, tar.xz) from files and directories.

Examples:
- Create a zip archive: archive_create(output="backup.zip", paths=["file1.txt", "dir/"])
- Create a tar.gz archive: archive_create(output="backup.tar.gz", paths=["src/"])
- Exclude patterns: archive_create(output="code.zip", paths=["project/"], exclude=["*.pyc", "__pycache__"])
"""
    parameters = {
        "type": "object",
        "properties": {
            "output": {
                "type": "string",
                "description": "Output archive path. Format determined by extension (.zip, .tar, .tar.gz, .tar.bz2, .tar.xz, .tgz, .tbz2, .txz)",
            },
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of files and directories to include in the archive",
            },
            "exclude": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Glob patterns to exclude (e.g., '*.pyc', '__pycache__')",
            },
            "compression_level": {
                "type": "integer",
                "description": "Compression level (0-9, where 9 is highest). Default: 6",
            },
        },
        "required": ["output", "paths"],
    }

    def _should_exclude(self, path: str, exclude_patterns: list[str]) -> bool:
        """Check if a path matches any exclude pattern."""
        from fnmatch import fnmatch

        name = os.path.basename(path)
        for pattern in exclude_patterns:
            if fnmatch(name, pattern) or fnmatch(path, pattern):
                return True
        return False

    def _get_archive_format(self, output: str) -> tuple[str, str | None]:
        """Determine archive format from filename.

        Returns: (format, compression) where format is 'zip' or 'tar'
        and compression is None, 'gz', 'bz2', or 'xz'
        """
        output_lower = output.lower()
        if output_lower.endswith(".zip"):
            return ("zip", None)
        elif output_lower.endswith(".tar"):
            return ("tar", None)
        elif output_lower.endswith((".tar.gz", ".tgz")):
            return ("tar", "gz")
        elif output_lower.endswith((".tar.bz2", ".tbz2")):
            return ("tar", "bz2")
        elif output_lower.endswith((".tar.xz", ".txz")):
            return ("tar", "xz")
        else:
            # Default to zip
            return ("zip", None)

    async def execute(
        self,
        output: str,
        paths: list[str],
        exclude: Optional[list[str]] = None,
        compression_level: int = 6,
    ) -> ToolResult:
        """Create an archive from the specified paths."""
        logger.info(
            "archive_create_start", output=output, paths=paths, exclude=exclude
        )

        try:
            output_path = self._resolve_path(output)
            exclude_patterns = exclude or []

            # Validate paths exist
            resolved_paths = []
            for p in paths:
                resolved = self._resolve_path(p)
                if not os.path.exists(resolved):
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Path does not exist: {p}",
                    )
                resolved_paths.append((p, resolved))

            # Get format
            fmt, compression = self._get_archive_format(output)
            files_added = 0
            total_size = 0

            if fmt == "zip":
                # Create ZIP archive
                comp_type = (
                    zipfile.ZIP_DEFLATED
                    if compression_level > 0
                    else zipfile.ZIP_STORED
                )
                with zipfile.ZipFile(
                    output_path, "w", comp_type, compresslevel=compression_level
                ) as zf:
                    for orig_path, resolved in resolved_paths:
                        if os.path.isfile(resolved):
                            if not self._should_exclude(orig_path, exclude_patterns):
                                zf.write(resolved, orig_path)
                                files_added += 1
                                total_size += os.path.getsize(resolved)
                        elif os.path.isdir(resolved):
                            for root, dirs, files in os.walk(resolved):
                                # Filter excluded directories
                                dirs[:] = [
                                    d
                                    for d in dirs
                                    if not self._should_exclude(d, exclude_patterns)
                                ]
                                for file in files:
                                    file_path = os.path.join(root, file)
                                    arcname = os.path.relpath(file_path, resolved)
                                    arcname = os.path.join(orig_path, arcname)
                                    if not self._should_exclude(
                                        file_path, exclude_patterns
                                    ):
                                        zf.write(file_path, arcname)
                                        files_added += 1
                                        total_size += os.path.getsize(file_path)
            else:
                # Create TAR archive
                mode = "w"
                if compression == "gz":
                    mode = "w:gz"
                elif compression == "bz2":
                    mode = "w:bz2"
                elif compression == "xz":
                    mode = "w:xz"

                with tarfile.open(output_path, mode) as tf:
                    for orig_path, resolved in resolved_paths:
                        if os.path.isfile(resolved):
                            if not self._should_exclude(orig_path, exclude_patterns):
                                tf.add(resolved, arcname=orig_path)
                                files_added += 1
                                total_size += os.path.getsize(resolved)
                        elif os.path.isdir(resolved):

                            def filter_func(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
                                if self._should_exclude(
                                    tarinfo.name, exclude_patterns
                                ):
                                    return None
                                return tarinfo

                            for root, dirs, files in os.walk(resolved):
                                dirs[:] = [
                                    d
                                    for d in dirs
                                    if not self._should_exclude(d, exclude_patterns)
                                ]
                                for file in files:
                                    file_path = os.path.join(root, file)
                                    arcname = os.path.relpath(file_path, resolved)
                                    arcname = os.path.join(orig_path, arcname)
                                    if not self._should_exclude(
                                        file_path, exclude_patterns
                                    ):
                                        tf.add(file_path, arcname=arcname)
                                        files_added += 1
                                        total_size += os.path.getsize(file_path)

            archive_size = os.path.getsize(output_path)
            ratio = (
                ((total_size - archive_size) / total_size * 100)
                if total_size > 0
                else 0
            )

            result_output = f"""Archive created: {output}
Format: {fmt}{f' ({compression})' if compression else ''}
Files added: {files_added}
Original size: {total_size:,} bytes
Archive size: {archive_size:,} bytes
Compression ratio: {ratio:.1f}%"""

            logger.info(
                "archive_create_success",
                output=output,
                files=files_added,
                original_size=total_size,
                archive_size=archive_size,
            )

            return ToolResult(
                success=True,
                output=result_output,
                metadata={
                    "output": str(output_path),
                    "format": fmt,
                    "compression": compression,
                    "files_added": files_added,
                    "original_size": total_size,
                    "archive_size": archive_size,
                    "compression_ratio": ratio,
                },
            )

        except Exception as e:
            logger.error("archive_create_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class ArchiveExtractTool(Tool):
    """Extract archive files to a directory."""

    name = "archive_extract"
    description = """Extract archive files (zip, tar, tar.gz, tar.bz2, tar.xz) to a directory.

Examples:
- Extract to current directory: archive_extract(archive="backup.zip")
- Extract to specific directory: archive_extract(archive="backup.tar.gz", output_dir="./extracted/")
- Extract specific files: archive_extract(archive="data.zip", files=["config.json", "data/"])
"""
    parameters = {
        "type": "object",
        "properties": {
            "archive": {
                "type": "string",
                "description": "Path to the archive file to extract",
            },
            "output_dir": {
                "type": "string",
                "description": "Directory to extract to. Default: current directory",
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific files/directories to extract. Default: extract all",
            },
            "overwrite": {
                "type": "boolean",
                "description": "Overwrite existing files. Default: true",
            },
        },
        "required": ["archive"],
    }

    def _detect_format(self, archive_path: str | Path) -> tuple[str, str | None]:
        """Detect archive format from extension or magic bytes."""
        path_str = str(archive_path)
        path_lower = path_str.lower()

        # Try by extension first
        if path_lower.endswith(".zip"):
            return ("zip", None)
        elif path_lower.endswith(".tar"):
            return ("tar", None)
        elif path_lower.endswith((".tar.gz", ".tgz")):
            return ("tar", "gz")
        elif path_lower.endswith((".tar.bz2", ".tbz2")):
            return ("tar", "bz2")
        elif path_lower.endswith((".tar.xz", ".txz")):
            return ("tar", "xz")

        # Try magic bytes
        with open(archive_path, "rb") as f:
            header = f.read(6)

        if header[:4] == b"PK\x03\x04":
            return ("zip", None)
        elif header[:2] == b"\x1f\x8b":
            return ("tar", "gz")
        elif header[:3] == b"BZh":
            return ("tar", "bz2")
        elif header[:6] == b"\xfd7zXZ\x00":
            return ("tar", "xz")

        # Default to tar
        return ("tar", None)

    async def execute(
        self,
        archive: str,
        output_dir: Optional[str] = None,
        files: Optional[list[str]] = None,
        overwrite: bool = True,
    ) -> ToolResult:
        """Extract an archive to the specified directory."""
        logger.info(
            "archive_extract_start",
            archive=archive,
            output_dir=output_dir,
            files=files,
        )

        try:
            archive_path = self._resolve_path(archive)
            if not os.path.exists(archive_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Archive does not exist: {archive}",
                )

            # Resolve output directory
            if output_dir:
                out_path = self._resolve_path(output_dir)
            else:
                out_path = self.work_dir or os.getcwd()

            os.makedirs(out_path, exist_ok=True)

            fmt, compression = self._detect_format(archive_path)
            files_extracted = 0
            total_size = 0
            extracted_files: list[str] = []

            if fmt == "zip":
                with zipfile.ZipFile(archive_path, "r") as zf:
                    members = files if files else zf.namelist()
                    for member in members:
                        if member in zf.namelist():
                            dest = os.path.join(out_path, member)
                            if not overwrite and os.path.exists(dest):
                                continue
                            zf.extract(member, out_path)
                            info = zf.getinfo(member)
                            if not info.is_dir():
                                files_extracted += 1
                                total_size += info.file_size
                                extracted_files.append(member)
            else:
                # TAR format
                mode = "r"
                if compression == "gz":
                    mode = "r:gz"
                elif compression == "bz2":
                    mode = "r:bz2"
                elif compression == "xz":
                    mode = "r:xz"

                with tarfile.open(archive_path, mode) as tf:
                    members = files if files else [m.name for m in tf.getmembers()]
                    for member_name in members:
                        try:
                            member = tf.getmember(member_name)
                            dest = os.path.join(out_path, member.name)
                            if not overwrite and os.path.exists(dest):
                                continue
                            tf.extract(member, out_path)
                            if member.isfile():
                                files_extracted += 1
                                total_size += member.size
                                extracted_files.append(member.name)
                        except KeyError:
                            continue

            result_output = f"""Archive extracted: {archive}
Output directory: {out_path}
Files extracted: {files_extracted}
Total size: {total_size:,} bytes"""

            logger.info(
                "archive_extract_success",
                archive=archive,
                files=files_extracted,
                total_size=total_size,
            )

            return ToolResult(
                success=True,
                output=result_output,
                metadata={
                    "archive": str(archive_path),
                    "output_dir": str(out_path),
                    "format": fmt,
                    "compression": compression,
                    "files_extracted": files_extracted,
                    "total_size": total_size,
                    "extracted_files": extracted_files[:100],  # Limit for metadata
                },
            )

        except Exception as e:
            logger.error("archive_extract_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class ArchiveListTool(Tool):
    """List contents of an archive file."""

    name = "archive_list"
    description = """List contents of archive files (zip, tar, tar.gz, tar.bz2, tar.xz).

Examples:
- List contents: archive_list(archive="backup.zip")
- Show detailed info: archive_list(archive="data.tar.gz", detailed=true)
"""
    parameters = {
        "type": "object",
        "properties": {
            "archive": {
                "type": "string",
                "description": "Path to the archive file",
            },
            "detailed": {
                "type": "boolean",
                "description": "Show detailed information (size, date). Default: false",
            },
        },
        "required": ["archive"],
    }

    def _detect_format(self, archive_path: str | Path) -> tuple[str, str | None]:
        """Detect archive format from extension or magic bytes."""
        path_str = str(archive_path)
        path_lower = path_str.lower()

        if path_lower.endswith(".zip"):
            return ("zip", None)
        elif path_lower.endswith(".tar"):
            return ("tar", None)
        elif path_lower.endswith((".tar.gz", ".tgz")):
            return ("tar", "gz")
        elif path_lower.endswith((".tar.bz2", ".tbz2")):
            return ("tar", "bz2")
        elif path_lower.endswith((".tar.xz", ".txz")):
            return ("tar", "xz")

        # Try magic bytes
        with open(archive_path, "rb") as f:
            header = f.read(6)

        if header[:4] == b"PK\x03\x04":
            return ("zip", None)
        elif header[:2] == b"\x1f\x8b":
            return ("tar", "gz")
        elif header[:3] == b"BZh":
            return ("tar", "bz2")
        elif header[:6] == b"\xfd7zXZ\x00":
            return ("tar", "xz")

        return ("tar", None)

    async def execute(
        self,
        archive: str,
        detailed: bool = False,
    ) -> ToolResult:
        """List contents of an archive."""
        logger.info("archive_list_start", archive=archive, detailed=detailed)

        try:
            archive_path = self._resolve_path(archive)
            if not os.path.exists(archive_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Archive does not exist: {archive}",
                )

            fmt, compression = self._detect_format(archive_path)
            entries: list[dict] = []
            total_size = 0
            file_count = 0
            dir_count = 0

            if fmt == "zip":
                with zipfile.ZipFile(archive_path, "r") as zf:
                    for info in zf.infolist():
                        is_dir = info.is_dir()
                        entry = {
                            "name": info.filename,
                            "size": info.file_size,
                            "compressed_size": info.compress_size,
                            "is_dir": is_dir,
                            "modified": datetime(*info.date_time).isoformat(),
                        }
                        entries.append(entry)
                        if is_dir:
                            dir_count += 1
                        else:
                            file_count += 1
                            total_size += info.file_size
            else:
                mode = "r"
                if compression == "gz":
                    mode = "r:gz"
                elif compression == "bz2":
                    mode = "r:bz2"
                elif compression == "xz":
                    mode = "r:xz"

                with tarfile.open(archive_path, mode) as tf:
                    for member in tf.getmembers():
                        is_dir = member.isdir()
                        entry = {
                            "name": member.name,
                            "size": member.size,
                            "compressed_size": member.size,  # TAR doesn't track per-file
                            "is_dir": is_dir,
                            "modified": datetime.fromtimestamp(
                                member.mtime
                            ).isoformat(),
                            "mode": oct(member.mode),
                        }
                        entries.append(entry)
                        if is_dir:
                            dir_count += 1
                        else:
                            file_count += 1
                            total_size += member.size

            # Format output
            lines = [f"Archive: {archive}", f"Format: {fmt}{f' ({compression})' if compression else ''}", ""]

            if detailed:
                lines.append(f"{'Size':>12}  {'Modified':<20}  Name")
                lines.append("-" * 60)
                for entry in entries:
                    size_str = f"{entry['size']:,}" if not entry["is_dir"] else "<DIR>"
                    mod_str = entry["modified"][:19]
                    lines.append(f"{size_str:>12}  {mod_str:<20}  {entry['name']}")
            else:
                for entry in entries:
                    prefix = "[D] " if entry["is_dir"] else "    "
                    lines.append(f"{prefix}{entry['name']}")

            lines.extend(
                [
                    "",
                    f"Total: {file_count} files, {dir_count} directories, {total_size:,} bytes",
                ]
            )

            logger.info(
                "archive_list_success",
                archive=archive,
                files=file_count,
                dirs=dir_count,
            )

            return ToolResult(
                success=True,
                output="\n".join(lines),
                metadata={
                    "archive": str(archive_path),
                    "format": fmt,
                    "compression": compression,
                    "file_count": file_count,
                    "dir_count": dir_count,
                    "total_size": total_size,
                    "entries": entries[:100],  # Limit for metadata
                },
            )

        except Exception as e:
            logger.error("archive_list_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class CompressFileTool(Tool):
    """Compress a single file using various algorithms."""

    name = "compress_file"
    description = """Compress a single file using gzip, bz2, xz, or brotli.

Examples:
- Compress with gzip: compress_file(input="data.json", format="gzip")
- Compress with max level: compress_file(input="large.txt", format="xz", level=9)
- Custom output: compress_file(input="file.txt", format="bz2", output="file.txt.bz2")
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to the file to compress",
            },
            "format": {
                "type": "string",
                "enum": ["gzip", "bz2", "xz", "brotli"],
                "description": "Compression format to use",
            },
            "output": {
                "type": "string",
                "description": "Output path. Default: input + extension (.gz, .bz2, .xz, .br)",
            },
            "level": {
                "type": "integer",
                "description": "Compression level (1-9, 9 is highest). Default: 6",
            },
        },
        "required": ["input", "format"],
    }

    async def execute(
        self,
        input: str,
        format: str,
        output: Optional[str] = None,
        level: int = 6,
    ) -> ToolResult:
        """Compress a file."""
        logger.info(
            "compress_file_start", input=input, format=format, output=output, level=level
        )

        try:
            input_path = self._resolve_path(input)
            if not os.path.exists(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File does not exist: {input}",
                )

            if not os.path.isfile(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path is not a file: {input}",
                )

            # Determine output path
            extensions = {"gzip": ".gz", "bz2": ".bz2", "xz": ".xz", "brotli": ".br"}
            if output:
                output_path = self._resolve_path(output)
            else:
                output_path = str(input_path) + extensions.get(format, ".compressed")

            # Validate level
            level = max(1, min(9, level))

            original_size = os.path.getsize(input_path)

            # Read input file
            with open(input_path, "rb") as f:
                data = f.read()

            # Compress based on format
            if format == "gzip":
                compressed = gzip.compress(data, compresslevel=level)
            elif format == "bz2":
                compressed = bz2.compress(data, compresslevel=level)
            elif format == "xz":
                compressed = lzma.compress(
                    data, preset=level, format=lzma.FORMAT_XZ
                )
            elif format == "brotli":
                if not BROTLI_AVAILABLE:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Brotli support not available. Install with: pip install brotli",
                    )
                compressed = brotli.compress(data, quality=level)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown format: {format}",
                )

            # Write compressed file
            with open(output_path, "wb") as f:
                f.write(compressed)

            compressed_size = len(compressed)
            ratio = (
                ((original_size - compressed_size) / original_size * 100)
                if original_size > 0
                else 0
            )

            result_output = f"""File compressed: {input} -> {output_path}
Format: {format}
Compression level: {level}
Original size: {original_size:,} bytes
Compressed size: {compressed_size:,} bytes
Compression ratio: {ratio:.1f}%"""

            logger.info(
                "compress_file_success",
                input=input,
                output=str(output_path),
                format=format,
                ratio=ratio,
            )

            return ToolResult(
                success=True,
                output=result_output,
                metadata={
                    "input": str(input_path),
                    "output": str(output_path),
                    "format": format,
                    "level": level,
                    "original_size": original_size,
                    "compressed_size": compressed_size,
                    "compression_ratio": ratio,
                },
            )

        except Exception as e:
            logger.error("compress_file_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class DecompressFileTool(Tool):
    """Decompress a single compressed file."""

    name = "decompress_file"
    description = """Decompress a file compressed with gzip, bz2, xz, or brotli.

Examples:
- Decompress gzip: decompress_file(input="data.json.gz")
- Custom output: decompress_file(input="file.txt.xz", output="restored.txt")
- Specify format: decompress_file(input="data.compressed", format="bz2")
"""
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Path to the compressed file",
            },
            "output": {
                "type": "string",
                "description": "Output path. Default: input without compression extension",
            },
            "format": {
                "type": "string",
                "enum": ["gzip", "bz2", "xz", "brotli", "auto"],
                "description": "Compression format. Default: auto-detect from extension/magic bytes",
            },
        },
        "required": ["input"],
    }

    def _detect_format(self, path: str | Path) -> str | None:
        """Detect compression format from extension or magic bytes."""
        path_str = str(path)
        path_lower = path_str.lower()

        # Try extension
        if path_lower.endswith(".gz"):
            return "gzip"
        elif path_lower.endswith(".bz2"):
            return "bz2"
        elif path_lower.endswith(".xz"):
            return "xz"
        elif path_lower.endswith(".br"):
            return "brotli"

        # Try magic bytes
        try:
            with open(path, "rb") as f:
                header = f.read(6)

            if header[:2] == b"\x1f\x8b":
                return "gzip"
            elif header[:3] == b"BZh":
                return "bz2"
            elif header[:6] == b"\xfd7zXZ\x00":
                return "xz"
            # Brotli doesn't have a magic number, so we can't auto-detect it
        except Exception:
            pass

        return None

    async def execute(
        self,
        input: str,
        output: Optional[str] = None,
        format: str = "auto",
    ) -> ToolResult:
        """Decompress a file."""
        logger.info(
            "decompress_file_start", input=input, output=output, format=format
        )

        try:
            input_path = self._resolve_path(input)
            if not os.path.exists(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File does not exist: {input}",
                )

            if not os.path.isfile(input_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path is not a file: {input}",
                )

            # Detect or validate format
            detected_format = format
            if format == "auto":
                detected_format = self._detect_format(input_path)
                if not detected_format:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Could not auto-detect compression format. Please specify format explicitly.",
                    )

            # Determine output path
            if output:
                output_path = self._resolve_path(output)
            else:
                # Remove compression extension
                extensions = {".gz": "gzip", ".bz2": "bz2", ".xz": "xz", ".br": "brotli"}
                input_path_str = str(input_path)
                output_path = input_path_str
                for ext, fmt in extensions.items():
                    if input_path_str.lower().endswith(ext):
                        output_path = input_path_str[: -len(ext)]
                        break
                else:
                    output_path = input_path_str + ".decompressed"

            compressed_size = os.path.getsize(input_path)

            # Read and decompress
            with open(input_path, "rb") as f:
                compressed_data = f.read()

            if detected_format == "gzip":
                data = gzip.decompress(compressed_data)
            elif detected_format == "bz2":
                data = bz2.decompress(compressed_data)
            elif detected_format == "xz":
                data = lzma.decompress(compressed_data)
            elif detected_format == "brotli":
                if not BROTLI_AVAILABLE:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Brotli support not available. Install with: pip install brotli",
                    )
                data = brotli.decompress(compressed_data)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown format: {detected_format}",
                )

            # Write decompressed file
            with open(output_path, "wb") as f:
                f.write(data)

            decompressed_size = len(data)

            result_output = f"""File decompressed: {input} -> {output_path}
Format: {detected_format}
Compressed size: {compressed_size:,} bytes
Decompressed size: {decompressed_size:,} bytes"""

            logger.info(
                "decompress_file_success",
                input=input,
                output=str(output_path),
                format=detected_format,
            )

            return ToolResult(
                success=True,
                output=result_output,
                metadata={
                    "input": str(input_path),
                    "output": str(output_path),
                    "format": detected_format,
                    "compressed_size": compressed_size,
                    "decompressed_size": decompressed_size,
                },
            )

        except Exception as e:
            logger.error("decompress_file_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))
