"""Tests for directory exploration tools."""

import pytest
from pathlib import Path
import tempfile
import shutil

from sindri.tools.filesystem import ListDirectoryTool, ReadTreeTool


@pytest.fixture
def temp_dir():
    """Create a temporary directory structure for testing."""
    temp = Path(tempfile.mkdtemp())

    # Create test directory structure
    # temp/
    #   ├── file1.txt
    #   ├── file2.py
    #   ├── .hidden
    #   ├── subdir1/
    #   │   ├── file3.txt
    #   │   └── file4.js
    #   └── subdir2/
    #       ├── deep/
    #       │   └── nested.txt
    #       └── file5.md

    (temp / "file1.txt").write_text("content1")
    (temp / "file2.py").write_text("print('hello')")
    (temp / ".hidden").write_text("hidden")

    (temp / "subdir1").mkdir()
    (temp / "subdir1" / "file3.txt").write_text("content3")
    (temp / "subdir1" / "file4.js").write_text("console.log('test');")

    (temp / "subdir2").mkdir()
    (temp / "subdir2" / "deep").mkdir(parents=True)
    (temp / "subdir2" / "deep" / "nested.txt").write_text("nested content")
    (temp / "subdir2" / "file5.md").write_text("# Markdown")

    yield temp

    # Cleanup
    shutil.rmtree(temp)


@pytest.mark.asyncio
async def test_list_directory_basic(temp_dir):
    """Test basic directory listing."""
    tool = ListDirectoryTool()
    result = await tool.execute(path=str(temp_dir))

    assert result.success is True
    assert "file1.txt" in result.output
    assert "file2.py" in result.output
    assert "subdir1" in result.output
    assert "subdir2" in result.output
    # Hidden files should be ignored by default
    assert ".hidden" not in result.output


@pytest.mark.asyncio
async def test_list_directory_show_hidden(temp_dir):
    """Test listing with hidden files shown."""
    tool = ListDirectoryTool()
    result = await tool.execute(path=str(temp_dir), ignore_hidden=False)

    assert result.success is True
    assert ".hidden" in result.output


@pytest.mark.asyncio
async def test_list_directory_with_pattern(temp_dir):
    """Test listing with glob pattern filter."""
    tool = ListDirectoryTool()
    result = await tool.execute(path=str(temp_dir), pattern="*.py")

    assert result.success is True
    assert "file2.py" in result.output
    # Should not show non-matching files
    assert "file1.txt" not in result.output


@pytest.mark.asyncio
async def test_list_directory_recursive(temp_dir):
    """Test recursive directory listing."""
    tool = ListDirectoryTool()
    result = await tool.execute(path=str(temp_dir), recursive=True)

    assert result.success is True
    assert "file1.txt" in result.output
    assert "subdir1" in result.output
    # Should show nested files
    assert "file3.txt" in result.output or "subdir1/file3.txt" in result.output
    assert "nested.txt" in result.output or "subdir2/deep/nested.txt" in result.output


@pytest.mark.asyncio
async def test_list_directory_recursive_with_pattern(temp_dir):
    """Test recursive listing with pattern."""
    tool = ListDirectoryTool()
    result = await tool.execute(path=str(temp_dir), recursive=True, pattern="*.txt")

    assert result.success is True
    assert "file1.txt" in result.output
    assert "file3.txt" in result.output or "subdir1/file3.txt" in result.output
    assert "nested.txt" in result.output or "subdir2/deep/nested.txt" in result.output
    # Should not show non-txt files
    assert "file2.py" not in result.output
    assert "file4.js" not in result.output


@pytest.mark.asyncio
async def test_list_directory_not_found():
    """Test listing non-existent directory."""
    tool = ListDirectoryTool()
    result = await tool.execute(path="/nonexistent/path")

    assert result.success is False
    assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_list_directory_file_instead_of_dir(temp_dir):
    """Test listing when path is a file, not directory."""
    tool = ListDirectoryTool()
    file_path = temp_dir / "file1.txt"
    result = await tool.execute(path=str(file_path))

    assert result.success is False
    assert "not a directory" in result.error.lower()


@pytest.mark.asyncio
async def test_list_directory_empty(temp_dir):
    """Test listing empty directory."""
    empty_dir = temp_dir / "empty"
    empty_dir.mkdir()

    tool = ListDirectoryTool()
    result = await tool.execute(path=str(empty_dir))

    assert result.success is True
    assert result.output == "(empty directory)"


@pytest.mark.asyncio
async def test_read_tree_basic(temp_dir):
    """Test basic tree reading."""
    tool = ReadTreeTool()
    result = await tool.execute(path=str(temp_dir), max_depth=3)

    assert result.success is True
    # Should show directory name
    assert temp_dir.name in result.output
    # Should show files
    assert "file1.txt" in result.output
    assert "file2.py" in result.output
    # Should show subdirectories
    assert "subdir1" in result.output
    assert "subdir2" in result.output
    # Should show nested files (within depth 3)
    assert "file3.txt" in result.output
    assert "nested.txt" in result.output
    # Should show summary
    assert "directories" in result.output
    assert "files" in result.output


@pytest.mark.asyncio
async def test_read_tree_limited_depth(temp_dir):
    """Test tree with depth limit."""
    tool = ReadTreeTool()
    # Depth 1 should only show immediate children
    result = await tool.execute(path=str(temp_dir), max_depth=1)

    assert result.success is True
    # Should show immediate files
    assert "file1.txt" in result.output
    # Should show immediate subdirectories
    assert "subdir1" in result.output
    # Should NOT show nested files (they're at depth 2)
    assert "file3.txt" not in result.output
    assert "nested.txt" not in result.output


@pytest.mark.asyncio
async def test_read_tree_ignore_hidden(temp_dir):
    """Test tree with hidden files ignored."""
    tool = ReadTreeTool()
    result = await tool.execute(path=str(temp_dir), ignore_hidden=True)

    assert result.success is True
    assert ".hidden" not in result.output


@pytest.mark.asyncio
async def test_read_tree_show_hidden(temp_dir):
    """Test tree with hidden files shown."""
    tool = ReadTreeTool()
    result = await tool.execute(path=str(temp_dir), ignore_hidden=False)

    assert result.success is True
    assert ".hidden" in result.output


@pytest.mark.asyncio
async def test_read_tree_not_found():
    """Test tree for non-existent directory."""
    tool = ReadTreeTool()
    result = await tool.execute(path="/nonexistent/path")

    assert result.success is False
    assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_read_tree_file_instead_of_dir(temp_dir):
    """Test tree when path is a file, not directory."""
    tool = ReadTreeTool()
    file_path = temp_dir / "file1.txt"
    result = await tool.execute(path=str(file_path))

    assert result.success is False
    assert "not a directory" in result.error.lower()


@pytest.mark.asyncio
async def test_read_tree_metadata(temp_dir):
    """Test tree result metadata."""
    tool = ReadTreeTool()
    result = await tool.execute(path=str(temp_dir), max_depth=3)

    assert result.success is True
    assert "directories" in result.metadata
    assert "files" in result.metadata
    assert result.metadata["directories"] >= 3  # temp, subdir1, subdir2, deep
    assert result.metadata["files"] >= 5  # At least 5 files


@pytest.mark.asyncio
async def test_list_directory_with_work_dir(temp_dir):
    """Test list_directory with work_dir set."""
    # Create tool with work_dir
    tool = ListDirectoryTool(work_dir=temp_dir)

    # Use relative path
    result = await tool.execute(path="subdir1")

    assert result.success is True
    assert "file3.txt" in result.output
    assert "file4.js" in result.output


@pytest.mark.asyncio
async def test_read_tree_with_work_dir(temp_dir):
    """Test read_tree with work_dir set."""
    # Create tool with work_dir
    tool = ReadTreeTool(work_dir=temp_dir)

    # Use relative path
    result = await tool.execute(path="subdir2")

    assert result.success is True
    assert "deep" in result.output
    assert "file5.md" in result.output
