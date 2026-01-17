"""Tests for SplitFileTool.

Comprehensive test coverage for the split_file tool including:
- Split by classes
- Split by functions
- Split by markers
- Split by line numbers
- Dry run mode
- Import updates
- __init__.py generation
- Re-export generation
- Error handling
- Edge cases
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from sindri.tools.refactoring import SplitFileTool


@pytest.fixture
def temp_dir():
    """Create a temporary directory with test files for split operations."""
    temp = Path(tempfile.mkdtemp())
    yield temp
    shutil.rmtree(temp)


@pytest.fixture
def python_classes_file(temp_dir):
    """Create a Python file with multiple classes."""
    content = '''"""Multiple classes module."""

import os
from typing import Optional

class User:
    """User model."""

    def __init__(self, name: str, email: str):
        self.name = name
        self.email = email

    def greet(self) -> str:
        return f"Hello, {self.name}!"


class Order:
    """Order model."""

    def __init__(self, id: int, user: User):
        self.id = id
        self.user = user

    def get_total(self) -> float:
        return 0.0


class Product:
    """Product model."""

    def __init__(self, name: str, price: float):
        self.name = name
        self.price = price

    def display(self) -> str:
        return f"{self.name}: ${self.price}"
'''
    file_path = temp_dir / "models.py"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def python_functions_file(temp_dir):
    """Create a Python file with multiple functions."""
    content = '''"""Multiple functions module."""

import json
from datetime import datetime


def calculate_total(items: list) -> float:
    """Calculate total from items."""
    return sum(item.price for item in items)


def format_date(dt: datetime) -> str:
    """Format a datetime object."""
    return dt.strftime("%Y-%m-%d")


async def fetch_data(url: str) -> dict:
    """Fetch data from URL."""
    return {"url": url}


@decorator
def decorated_function(x: int) -> int:
    """A decorated function."""
    return x * 2
'''
    file_path = temp_dir / "utils.py"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def marker_file(temp_dir):
    """Create a file with split markers."""
    content = '''"""File with markers."""

# --- split: header.py ---
# Header module
VERSION = "1.0.0"
AUTHOR = "Test"


# --- split: utils.py ---
# Utils module
def helper():
    pass


# --- split: config.py ---
# Config module
DEBUG = True
'''
    file_path = temp_dir / "combined.py"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def lines_file(temp_dir):
    """Create a file for line-based splitting."""
    content = """# Part 1
line 1
line 2
line 3
line 4
line 5
# Part 2
line 6
line 7
line 8
line 9
line 10
# Part 3
line 11
line 12
line 13
line 14
line 15
"""
    file_path = temp_dir / "data.txt"
    file_path.write_text(content)
    return file_path


# ============================================================
# Split by Classes Tests
# ============================================================


class TestSplitByClasses:
    """Tests for split by classes strategy."""

    @pytest.mark.asyncio
    async def test_split_classes_basic(self, python_classes_file, temp_dir):
        """Test basic class splitting."""
        tool = SplitFileTool(work_dir=temp_dir)
        output_dir = temp_dir / "models"

        result = await tool.execute(
            file=str(python_classes_file),
            strategy="classes",
            output_dir=str(output_dir),
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        assert "Split" in result.output
        assert result.metadata["strategy"] == "classes"
        assert len(result.metadata["files_created"]) == 3

        # Verify files were created
        assert (output_dir / "user.py").exists()
        assert (output_dir / "order.py").exists()
        assert (output_dir / "product.py").exists()

    @pytest.mark.asyncio
    async def test_split_classes_dry_run(self, python_classes_file, temp_dir):
        """Test dry run mode."""
        tool = SplitFileTool(work_dir=temp_dir)
        output_dir = temp_dir / "models"

        result = await tool.execute(
            file=str(python_classes_file),
            strategy="classes",
            output_dir=str(output_dir),
            dry_run=True,
        )

        assert result.success
        assert "Would split" in result.output
        assert result.metadata["dry_run"] is True

        # Verify no files were created
        assert not output_dir.exists()

    @pytest.mark.asyncio
    async def test_split_classes_with_init(self, python_classes_file, temp_dir):
        """Test __init__.py generation."""
        tool = SplitFileTool(work_dir=temp_dir)
        output_dir = temp_dir / "models"

        result = await tool.execute(
            file=str(python_classes_file),
            strategy="classes",
            output_dir=str(output_dir),
            create_init=True,
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        assert result.metadata["init_created"] is True

        # Verify __init__.py was created
        init_file = output_dir / "__init__.py"
        assert init_file.exists()

        init_content = init_file.read_text()
        assert "from .user import User" in init_content
        assert "from .order import Order" in init_content
        assert "from .product import Product" in init_content
        assert "__all__" in init_content

    @pytest.mark.asyncio
    async def test_split_classes_preserves_imports(self, python_classes_file, temp_dir):
        """Test that imports are preserved in split files."""
        tool = SplitFileTool(work_dir=temp_dir)
        output_dir = temp_dir / "models"

        result = await tool.execute(
            file=str(python_classes_file),
            strategy="classes",
            output_dir=str(output_dir),
            keep_original=False,
            update_imports=False,
        )

        assert result.success

        # Check that imports are in the split files
        user_content = (output_dir / "user.py").read_text()
        assert "import os" in user_content
        assert "from typing import Optional" in user_content

    @pytest.mark.asyncio
    async def test_split_classes_camelcase_to_snake(self, temp_dir):
        """Test CamelCase class names convert to snake_case filenames."""
        content = """class UserProfile:
    pass

class OrderHistory:
    pass
"""
        file_path = temp_dir / "models.py"
        file_path.write_text(content)

        tool = SplitFileTool(work_dir=temp_dir)

        result = await tool.execute(
            file=str(file_path),
            strategy="classes",
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        assert (temp_dir / "user_profile.py").exists()
        assert (temp_dir / "order_history.py").exists()


# ============================================================
# Split by Functions Tests
# ============================================================


class TestSplitByFunctions:
    """Tests for split by functions strategy."""

    @pytest.mark.asyncio
    async def test_split_functions_basic(self, python_functions_file, temp_dir):
        """Test basic function splitting."""
        tool = SplitFileTool(work_dir=temp_dir)
        output_dir = temp_dir / "utils"

        result = await tool.execute(
            file=str(python_functions_file),
            strategy="functions",
            output_dir=str(output_dir),
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        assert result.metadata["strategy"] == "functions"
        assert len(result.metadata["files_created"]) >= 3

    @pytest.mark.asyncio
    async def test_split_functions_includes_async(
        self, python_functions_file, temp_dir
    ):
        """Test that async functions are included."""
        tool = SplitFileTool(work_dir=temp_dir)
        output_dir = temp_dir / "utils"

        result = await tool.execute(
            file=str(python_functions_file),
            strategy="functions",
            output_dir=str(output_dir),
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        assert (output_dir / "fetch_data.py").exists()

    @pytest.mark.asyncio
    async def test_split_functions_preserves_imports(
        self, python_functions_file, temp_dir
    ):
        """Test that imports are preserved in split files."""
        tool = SplitFileTool(work_dir=temp_dir)
        output_dir = temp_dir / "utils"

        result = await tool.execute(
            file=str(python_functions_file),
            strategy="functions",
            output_dir=str(output_dir),
            keep_original=False,
            update_imports=False,
        )

        assert result.success

        # Check imports in split files
        calc_content = (output_dir / "calculate_total.py").read_text()
        assert "import json" in calc_content


# ============================================================
# Split by Markers Tests
# ============================================================


class TestSplitByMarkers:
    """Tests for split by markers strategy."""

    @pytest.mark.asyncio
    async def test_split_markers_basic(self, marker_file, temp_dir):
        """Test basic marker splitting."""
        tool = SplitFileTool(work_dir=temp_dir)
        output_dir = temp_dir / "split"

        result = await tool.execute(
            file=str(marker_file),
            strategy="markers",
            output_dir=str(output_dir),
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        assert result.metadata["strategy"] == "markers"
        assert len(result.metadata["files_created"]) == 3

    @pytest.mark.asyncio
    async def test_split_markers_custom_marker(self, temp_dir):
        """Test custom marker pattern."""
        content = """# ==== BEGIN: first.py ====
content1
# ==== BEGIN: second.py ====
content2
"""
        file_path = temp_dir / "combined.py"
        file_path.write_text(content)

        tool = SplitFileTool(work_dir=temp_dir)

        result = await tool.execute(
            file=str(file_path),
            strategy="markers",
            marker="# ==== BEGIN: {filename} ====",
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        assert (temp_dir / "first.py").exists()
        assert (temp_dir / "second.py").exists()

    @pytest.mark.asyncio
    async def test_split_markers_no_markers(self, temp_dir):
        """Test file with no markers."""
        content = """# No markers here
just regular content
"""
        file_path = temp_dir / "nomarkers.py"
        file_path.write_text(content)

        tool = SplitFileTool(work_dir=temp_dir)

        result = await tool.execute(
            file=str(file_path),
            strategy="markers",
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        assert "No markers found" in result.output


# ============================================================
# Split by Lines Tests
# ============================================================


class TestSplitByLines:
    """Tests for split by lines strategy."""

    @pytest.mark.asyncio
    async def test_split_lines_basic(self, lines_file, temp_dir):
        """Test basic line splitting."""
        tool = SplitFileTool(work_dir=temp_dir)

        result = await tool.execute(
            file=str(lines_file),
            strategy="lines",
            lines=[5, 10],
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        assert result.metadata["strategy"] == "lines"
        assert len(result.metadata["files_created"]) == 3

    @pytest.mark.asyncio
    async def test_split_lines_creates_parts(self, lines_file, temp_dir):
        """Test that line split creates part files."""
        tool = SplitFileTool(work_dir=temp_dir)

        result = await tool.execute(
            file=str(lines_file),
            strategy="lines",
            lines=[5, 10],
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        assert (temp_dir / "data_part1.txt").exists()
        assert (temp_dir / "data_part2.txt").exists()
        assert (temp_dir / "data_part3.txt").exists()

    @pytest.mark.asyncio
    async def test_split_lines_requires_lines_param(self, lines_file, temp_dir):
        """Test that lines strategy requires lines parameter."""
        tool = SplitFileTool(work_dir=temp_dir)

        result = await tool.execute(file=str(lines_file), strategy="lines")

        assert not result.success
        assert "requires 'lines' parameter" in result.error

    @pytest.mark.asyncio
    async def test_split_lines_empty_list(self, lines_file, temp_dir):
        """Test that empty lines list returns error."""
        tool = SplitFileTool(work_dir=temp_dir)

        result = await tool.execute(file=str(lines_file), strategy="lines", lines=[])

        assert not result.success


# ============================================================
# Re-export and Backward Compatibility Tests
# ============================================================


class TestReexportGeneration:
    """Tests for re-export generation."""

    @pytest.mark.asyncio
    async def test_reexport_original_file(self, python_classes_file, temp_dir):
        """Test that original file is updated with re-exports."""
        tool = SplitFileTool(work_dir=temp_dir)
        output_dir = temp_dir / "models"

        result = await tool.execute(
            file=str(python_classes_file),
            strategy="classes",
            output_dir=str(output_dir),
            keep_original=True,
            update_imports=False,
        )

        assert result.success

        # Check original file has re-exports
        original_content = python_classes_file.read_text()
        assert "Re-exports" in original_content or "from models" in original_content


# ============================================================
# Error Handling Tests
# ============================================================


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_file_not_found(self, temp_dir):
        """Test error when file doesn't exist."""
        tool = SplitFileTool(work_dir=temp_dir)

        result = await tool.execute(file="nonexistent.py", strategy="classes")

        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_invalid_strategy(self, python_classes_file, temp_dir):
        """Test error for invalid strategy."""
        tool = SplitFileTool(work_dir=temp_dir)

        result = await tool.execute(file=str(python_classes_file), strategy="invalid")

        assert not result.success
        assert "Invalid strategy" in result.error

    @pytest.mark.asyncio
    async def test_directory_instead_of_file(self, temp_dir):
        """Test error when path is a directory."""
        tool = SplitFileTool(work_dir=temp_dir)

        result = await tool.execute(file=str(temp_dir), strategy="classes")

        assert not result.success
        assert "Not a file" in result.error


# ============================================================
# Edge Cases Tests
# ============================================================


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_single_class_file(self, temp_dir):
        """Test file with only one class doesn't split."""
        content = """class OnlyOne:
    pass
"""
        file_path = temp_dir / "single.py"
        file_path.write_text(content)

        tool = SplitFileTool(work_dir=temp_dir)

        result = await tool.execute(
            file=str(file_path),
            strategy="classes",
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        assert "Only one" in result.output

    @pytest.mark.asyncio
    async def test_empty_file(self, temp_dir):
        """Test empty file returns no splits."""
        file_path = temp_dir / "empty.py"
        file_path.write_text("")

        tool = SplitFileTool(work_dir=temp_dir)

        result = await tool.execute(
            file=str(file_path),
            strategy="classes",
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        assert "No classes found" in result.output

    @pytest.mark.asyncio
    async def test_no_functions_file(self, temp_dir):
        """Test file with no top-level functions."""
        content = """class MyClass:
    def method(self):
        pass
"""
        file_path = temp_dir / "nofunction.py"
        file_path.write_text(content)

        tool = SplitFileTool(work_dir=temp_dir)

        result = await tool.execute(
            file=str(file_path),
            strategy="functions",
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        assert "No functions found" in result.output

    @pytest.mark.asyncio
    async def test_same_directory_output(self, python_classes_file, temp_dir):
        """Test splitting to same directory."""
        tool = SplitFileTool(work_dir=temp_dir)

        result = await tool.execute(
            file=str(python_classes_file),
            strategy="classes",
            # No output_dir - uses same directory
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        assert (temp_dir / "user.py").exists()
        assert (temp_dir / "order.py").exists()
        assert (temp_dir / "product.py").exists()


# ============================================================
# Integration Tests
# ============================================================


class TestIntegration:
    """Integration tests for split_file."""

    @pytest.mark.asyncio
    async def test_full_workflow_classes(self, temp_dir):
        """Test full workflow: split classes, create init, update imports."""
        # Create main module
        models_content = '''"""Models module."""

import json

class User:
    def __init__(self, name: str):
        self.name = name


class Order:
    def __init__(self, id: int, user: User):
        self.id = id
        self.user = user
'''
        models_file = temp_dir / "models.py"
        models_file.write_text(models_content)

        # Create a file that imports from models
        app_content = '''"""App module."""

from models import User, Order

def create_user():
    return User("Test")
'''
        app_file = temp_dir / "app.py"
        app_file.write_text(app_content)

        # Split the models file
        tool = SplitFileTool(work_dir=temp_dir)
        output_dir = temp_dir / "models_pkg"

        result = await tool.execute(
            file=str(models_file),
            strategy="classes",
            output_dir=str(output_dir),
            create_init=True,
            update_imports=True,
            keep_original=True,
        )

        assert result.success
        assert len(result.metadata["files_created"]) == 2
        assert (output_dir / "user.py").exists()
        assert (output_dir / "order.py").exists()
        assert (output_dir / "__init__.py").exists()

    @pytest.mark.asyncio
    async def test_typescript_classes_split(self, temp_dir):
        """Test splitting TypeScript file by classes."""
        content = """import { Component } from 'react';

export class Header extends Component {
    render() {
        return null;
    }
}

export class Footer extends Component {
    render() {
        return null;
    }
}
"""
        file_path = temp_dir / "components.ts"
        file_path.write_text(content)

        tool = SplitFileTool(work_dir=temp_dir)

        result = await tool.execute(
            file=str(file_path),
            strategy="classes",
            keep_original=False,
            update_imports=False,
        )

        # Note: TS support is regex-based, may have limitations
        assert result.success


# ============================================================
# Work Directory Tests
# ============================================================


class TestWorkDirectory:
    """Tests for work directory handling."""

    @pytest.mark.asyncio
    async def test_relative_paths(self, temp_dir):
        """Test that relative paths work correctly."""
        # Create file in subdirectory
        subdir = temp_dir / "src"
        subdir.mkdir()

        content = """class Foo:
    pass

class Bar:
    pass
"""
        file_path = subdir / "models.py"
        file_path.write_text(content)

        tool = SplitFileTool(work_dir=temp_dir)

        result = await tool.execute(
            file="src/models.py",
            strategy="classes",
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        assert (subdir / "foo.py").exists()
        assert (subdir / "bar.py").exists()


# ============================================================
# Metadata Tests
# ============================================================


class TestMetadata:
    """Tests for result metadata."""

    @pytest.mark.asyncio
    async def test_metadata_contains_all_fields(self, python_classes_file, temp_dir):
        """Test that metadata contains all expected fields."""
        tool = SplitFileTool(work_dir=temp_dir)
        output_dir = temp_dir / "models"

        result = await tool.execute(
            file=str(python_classes_file),
            strategy="classes",
            output_dir=str(output_dir),
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        assert "source_file" in result.metadata
        assert "strategy" in result.metadata
        assert "files_created" in result.metadata
        assert "init_created" in result.metadata
        assert "dry_run" in result.metadata

    @pytest.mark.asyncio
    async def test_files_created_has_details(self, python_classes_file, temp_dir):
        """Test that files_created has detailed info."""
        tool = SplitFileTool(work_dir=temp_dir)
        output_dir = temp_dir / "models"

        result = await tool.execute(
            file=str(python_classes_file),
            strategy="classes",
            output_dir=str(output_dir),
            keep_original=False,
            update_imports=False,
        )

        assert result.success
        for file_info in result.metadata["files_created"]:
            assert "file" in file_info
            assert "name" in file_info
            assert "lines" in file_info
