"""Tests for MergeFilesTool.

Comprehensive test coverage for the merge_files tool including:
- Basic file merging
- Python file merging with import deduplication
- JavaScript/TypeScript merging
- Glob pattern matching
- Sort orders (preserve, alpha, dependency)
- Dry run mode
- Delete sources option
- Import updates
- Error handling
- Edge cases
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from sindri.tools.refactoring import MergeFilesTool


@pytest.fixture
def temp_dir():
    """Create a temporary directory with test files for merge operations."""
    temp = Path(tempfile.mkdtemp())
    yield temp
    shutil.rmtree(temp)


@pytest.fixture
def python_files(temp_dir):
    """Create multiple Python files for merging."""
    # user.py
    (temp_dir / "user.py").write_text('''"""User module."""

import json
from typing import Optional

class User:
    """User model."""

    def __init__(self, name: str, email: str):
        self.name = name
        self.email = email

    def greet(self) -> str:
        return f"Hello, {self.name}!"
''')

    # order.py
    (temp_dir / "order.py").write_text('''"""Order module."""

import json
from datetime import datetime

class Order:
    """Order model."""

    def __init__(self, id: int, user_id: int):
        self.id = id
        self.user_id = user_id

    def get_total(self) -> float:
        return 0.0
''')

    # product.py
    (temp_dir / "product.py").write_text('''"""Product module."""

from typing import Optional
from decimal import Decimal

class Product:
    """Product model."""

    def __init__(self, name: str, price: Decimal):
        self.name = name
        self.price = price

    def display(self) -> str:
        return f"{self.name}: ${self.price}"
''')

    return temp_dir


@pytest.fixture
def js_files(temp_dir):
    """Create multiple JavaScript files for merging."""
    # header.js
    (temp_dir / "header.js").write_text('''import React from 'react';
import { useEffect } from 'react';

export function Header() {
    return <div>Header</div>;
}
''')

    # footer.js
    (temp_dir / "footer.js").write_text('''import React from 'react';

export function Footer() {
    return <div>Footer</div>;
}
''')

    return temp_dir


# ============================================================
# Basic Merge Tests
# ============================================================

class TestBasicMerge:
    """Tests for basic file merging."""

    @pytest.mark.asyncio
    async def test_merge_basic_files(self, python_files):
        """Test basic merging of Python files."""
        tool = MergeFilesTool(work_dir=python_files)

        result = await tool.execute(
            files=["user.py", "order.py", "product.py"],
            destination="models.py",
            update_imports=False
        )

        assert result.success
        assert "Merged" in result.output
        assert result.metadata["files_merged"] == 3

        # Verify merged file exists
        merged_file = python_files / "models.py"
        assert merged_file.exists()

        content = merged_file.read_text()
        assert "class User" in content
        assert "class Order" in content
        assert "class Product" in content

    @pytest.mark.asyncio
    async def test_merge_with_pattern(self, python_files):
        """Test merging with glob pattern."""
        tool = MergeFilesTool(work_dir=python_files)

        # Create a subdirectory with files to merge
        subdir = python_files / "models"
        subdir.mkdir()
        (subdir / "a.py").write_text("class A: pass")
        (subdir / "b.py").write_text("class B: pass")

        result = await tool.execute(
            pattern="models/*.py",
            destination="models/combined.py",
            update_imports=False
        )

        assert result.success
        assert result.metadata["files_merged"] == 2

    @pytest.mark.asyncio
    async def test_merge_dry_run(self, python_files):
        """Test dry run mode."""
        tool = MergeFilesTool(work_dir=python_files)

        result = await tool.execute(
            files=["user.py", "order.py"],
            destination="models.py",
            dry_run=True
        )

        assert result.success
        assert "Would merge" in result.output
        assert result.metadata["dry_run"] is True

        # Verify merged file was NOT created
        merged_file = python_files / "models.py"
        assert not merged_file.exists()


# ============================================================
# Python Merge Tests
# ============================================================

class TestPythonMerge:
    """Tests for Python-specific merge functionality."""

    @pytest.mark.asyncio
    async def test_import_deduplication(self, python_files):
        """Test that imports are deduplicated."""
        tool = MergeFilesTool(work_dir=python_files)

        result = await tool.execute(
            files=["user.py", "order.py", "product.py"],
            destination="models.py",
            update_imports=False
        )

        assert result.success

        content = (python_files / "models.py").read_text()

        # Should only have one 'import json' (deduplicated)
        assert content.count("import json") == 1

        # Should have from typing import Optional (merged)
        assert "from typing import Optional" in content

    @pytest.mark.asyncio
    async def test_section_comments(self, python_files):
        """Test section comments are added."""
        tool = MergeFilesTool(work_dir=python_files)

        result = await tool.execute(
            files=["user.py", "order.py"],
            destination="models.py",
            add_section_comments=True,
            update_imports=False
        )

        assert result.success

        content = (python_files / "models.py").read_text()
        assert "# From: user" in content
        assert "# From: order" in content

    @pytest.mark.asyncio
    async def test_no_section_comments(self, python_files):
        """Test section comments can be disabled."""
        tool = MergeFilesTool(work_dir=python_files)

        result = await tool.execute(
            files=["user.py", "order.py"],
            destination="models.py",
            add_section_comments=False,
            update_imports=False
        )

        assert result.success

        content = (python_files / "models.py").read_text()
        assert "# From:" not in content

    @pytest.mark.asyncio
    async def test_all_export(self, python_files):
        """Test __all__ is generated."""
        tool = MergeFilesTool(work_dir=python_files)

        result = await tool.execute(
            files=["user.py", "order.py", "product.py"],
            destination="models.py",
            update_imports=False
        )

        assert result.success

        content = (python_files / "models.py").read_text()
        assert "__all__" in content


# ============================================================
# JavaScript Merge Tests
# ============================================================

class TestJavaScriptMerge:
    """Tests for JavaScript-specific merge functionality."""

    @pytest.mark.asyncio
    async def test_merge_js_files(self, js_files):
        """Test merging JavaScript files."""
        tool = MergeFilesTool(work_dir=js_files)

        result = await tool.execute(
            files=["header.js", "footer.js"],
            destination="components.js",
            update_imports=False
        )

        assert result.success

        content = (js_files / "components.js").read_text()
        assert "Header" in content
        assert "Footer" in content

    @pytest.mark.asyncio
    async def test_js_import_deduplication(self, js_files):
        """Test JavaScript import deduplication."""
        tool = MergeFilesTool(work_dir=js_files)

        result = await tool.execute(
            files=["header.js", "footer.js"],
            destination="components.js",
            update_imports=False
        )

        assert result.success

        content = (js_files / "components.js").read_text()
        # Should only have one import React from 'react';
        assert content.count("import React from 'react';") == 1


# ============================================================
# Sort Order Tests
# ============================================================

class TestSortOrder:
    """Tests for sort order options."""

    @pytest.mark.asyncio
    async def test_sort_preserve(self, temp_dir):
        """Test preserve order (default)."""
        (temp_dir / "z_file.py").write_text("class Z: pass")
        (temp_dir / "a_file.py").write_text("class A: pass")

        tool = MergeFilesTool(work_dir=temp_dir)

        result = await tool.execute(
            files=["z_file.py", "a_file.py"],
            destination="combined.py",
            sort_order="preserve",
            update_imports=False
        )

        assert result.success

        content = (temp_dir / "combined.py").read_text()
        # Z should come before A (preserve input order)
        z_pos = content.find("class Z")
        a_pos = content.find("class A")
        assert z_pos < a_pos

    @pytest.mark.asyncio
    async def test_sort_alpha(self, temp_dir):
        """Test alphabetical sorting."""
        (temp_dir / "z_file.py").write_text("class Z: pass")
        (temp_dir / "a_file.py").write_text("class A: pass")

        tool = MergeFilesTool(work_dir=temp_dir)

        result = await tool.execute(
            files=["z_file.py", "a_file.py"],
            destination="combined.py",
            sort_order="alpha",
            update_imports=False
        )

        assert result.success

        content = (temp_dir / "combined.py").read_text()
        # A should come before Z (alphabetical)
        a_pos = content.find("class A")
        z_pos = content.find("class Z")
        assert a_pos < z_pos

    @pytest.mark.asyncio
    async def test_sort_dependency(self, temp_dir):
        """Test dependency sorting."""
        # base.py has no dependencies
        (temp_dir / "base.py").write_text('''"""Base module."""
class Base:
    pass
''')

        # child.py depends on base
        (temp_dir / "child.py").write_text('''"""Child module."""
from base import Base

class Child(Base):
    pass
''')

        tool = MergeFilesTool(work_dir=temp_dir)

        result = await tool.execute(
            files=["child.py", "base.py"],
            destination="combined.py",
            sort_order="dependency",
            update_imports=False
        )

        assert result.success

        content = (temp_dir / "combined.py").read_text()
        # Base should come before Child (dependency order)
        base_pos = content.find("class Base")
        child_pos = content.find("class Child")
        assert base_pos < child_pos


# ============================================================
# Delete Sources Tests
# ============================================================

class TestDeleteSources:
    """Tests for delete_sources option."""

    @pytest.mark.asyncio
    async def test_keep_sources_default(self, temp_dir):
        """Test sources are kept by default."""
        (temp_dir / "a.py").write_text("class A: pass")
        (temp_dir / "b.py").write_text("class B: pass")

        tool = MergeFilesTool(work_dir=temp_dir)

        result = await tool.execute(
            files=["a.py", "b.py"],
            destination="combined.py",
            update_imports=False
        )

        assert result.success
        assert result.metadata["sources_deleted"] is False

        # Source files should still exist
        assert (temp_dir / "a.py").exists()
        assert (temp_dir / "b.py").exists()

    @pytest.mark.asyncio
    async def test_delete_sources(self, temp_dir):
        """Test sources are deleted when requested."""
        (temp_dir / "a.py").write_text("class A: pass")
        (temp_dir / "b.py").write_text("class B: pass")

        tool = MergeFilesTool(work_dir=temp_dir)

        result = await tool.execute(
            files=["a.py", "b.py"],
            destination="combined.py",
            delete_sources=True,
            update_imports=False
        )

        assert result.success
        assert result.metadata["sources_deleted"] is True
        assert "Deleted" in result.output

        # Source files should be deleted
        assert not (temp_dir / "a.py").exists()
        assert not (temp_dir / "b.py").exists()

        # Merged file should exist
        assert (temp_dir / "combined.py").exists()


# ============================================================
# Error Handling Tests
# ============================================================

class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_no_files_or_pattern(self, temp_dir):
        """Test error when neither files nor pattern is specified."""
        tool = MergeFilesTool(work_dir=temp_dir)

        result = await tool.execute(
            destination="output.py"
        )

        assert not result.success
        assert "Either 'files' or 'pattern' must be specified" in result.error

    @pytest.mark.asyncio
    async def test_both_files_and_pattern(self, temp_dir):
        """Test error when both files and pattern are specified."""
        tool = MergeFilesTool(work_dir=temp_dir)

        result = await tool.execute(
            files=["a.py", "b.py"],
            pattern="*.py",
            destination="output.py"
        )

        assert not result.success
        assert "Cannot specify both" in result.error

    @pytest.mark.asyncio
    async def test_invalid_sort_order(self, temp_dir):
        """Test error for invalid sort order."""
        (temp_dir / "a.py").write_text("pass")

        tool = MergeFilesTool(work_dir=temp_dir)

        result = await tool.execute(
            files=["a.py"],
            destination="output.py",
            sort_order="invalid"
        )

        assert not result.success
        assert "Invalid sort_order" in result.error

    @pytest.mark.asyncio
    async def test_missing_source_file(self, temp_dir):
        """Test error when source file doesn't exist."""
        tool = MergeFilesTool(work_dir=temp_dir)

        result = await tool.execute(
            files=["nonexistent.py"],
            destination="output.py"
        )

        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_destination_in_sources(self, temp_dir):
        """Test error when destination would overwrite a source."""
        (temp_dir / "a.py").write_text("class A: pass")
        (temp_dir / "b.py").write_text("class B: pass")

        tool = MergeFilesTool(work_dir=temp_dir)

        result = await tool.execute(
            files=["a.py", "b.py"],
            destination="a.py",  # Overwriting source
            delete_sources=False
        )

        assert not result.success
        assert "is in the source list" in result.error

    @pytest.mark.asyncio
    async def test_destination_in_sources_with_delete(self, temp_dir):
        """Test that destination can be a source when delete_sources is true."""
        (temp_dir / "main.py").write_text("class Main: pass")
        (temp_dir / "helper.py").write_text("class Helper: pass")

        tool = MergeFilesTool(work_dir=temp_dir)

        result = await tool.execute(
            files=["main.py", "helper.py"],
            destination="main.py",
            delete_sources=True,
            update_imports=False
        )

        assert result.success


# ============================================================
# Edge Cases Tests
# ============================================================

class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_single_file(self, temp_dir):
        """Test merging a single file does nothing."""
        (temp_dir / "only.py").write_text("pass")

        tool = MergeFilesTool(work_dir=temp_dir)

        result = await tool.execute(
            files=["only.py"],
            destination="output.py"
        )

        assert result.success
        assert "Only one file" in result.output

    @pytest.mark.asyncio
    async def test_empty_pattern_match(self, temp_dir):
        """Test pattern that matches no files."""
        tool = MergeFilesTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="nonexistent/*.py",
            destination="output.py"
        )

        assert result.success
        assert "No files found" in result.output

    @pytest.mark.asyncio
    async def test_generic_file_merge(self, temp_dir):
        """Test merging non-Python, non-JS files."""
        (temp_dir / "a.txt").write_text("Content A")
        (temp_dir / "b.txt").write_text("Content B")

        tool = MergeFilesTool(work_dir=temp_dir)

        result = await tool.execute(
            files=["a.txt", "b.txt"],
            destination="combined.txt",
            update_imports=False
        )

        assert result.success

        content = (temp_dir / "combined.txt").read_text()
        assert "Content A" in content
        assert "Content B" in content


# ============================================================
# Metadata Tests
# ============================================================

class TestMetadata:
    """Tests for result metadata."""

    @pytest.mark.asyncio
    async def test_metadata_contains_all_fields(self, python_files):
        """Test that metadata contains all expected fields."""
        tool = MergeFilesTool(work_dir=python_files)

        result = await tool.execute(
            files=["user.py", "order.py"],
            destination="models.py",
            update_imports=False
        )

        assert result.success
        assert "destination" in result.metadata
        assert "files_merged" in result.metadata
        assert "source_files" in result.metadata
        assert "items_exported" in result.metadata
        assert "imports_updated" in result.metadata
        assert "sources_deleted" in result.metadata
        assert "dry_run" in result.metadata

    @pytest.mark.asyncio
    async def test_items_exported_contains_classes(self, python_files):
        """Test that items_exported contains class names."""
        tool = MergeFilesTool(work_dir=python_files)

        result = await tool.execute(
            files=["user.py", "order.py", "product.py"],
            destination="models.py",
            update_imports=False
        )

        assert result.success
        assert "User" in result.metadata["items_exported"]
        assert "Order" in result.metadata["items_exported"]
        assert "Product" in result.metadata["items_exported"]


# ============================================================
# Integration Tests
# ============================================================

class TestIntegration:
    """Integration tests for merge_files."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, temp_dir):
        """Test full merge workflow with import updates."""
        # Create source files
        (temp_dir / "user.py").write_text('''"""User module."""
class User:
    def __init__(self, name: str):
        self.name = name
''')

        (temp_dir / "order.py").write_text('''"""Order module."""
from user import User

class Order:
    def __init__(self, id: int, user: User):
        self.id = id
        self.user = user
''')

        # Create a file that imports from user
        (temp_dir / "app.py").write_text('''"""App module."""
from user import User

def create_user():
    return User("Test")
''')

        # Merge user and order into models
        tool = MergeFilesTool(work_dir=temp_dir)

        result = await tool.execute(
            files=["user.py", "order.py"],
            destination="models.py",
            update_imports=True
        )

        assert result.success
        assert result.metadata["files_merged"] == 2

        # Verify merged file
        models_content = (temp_dir / "models.py").read_text()
        assert "class User" in models_content
        assert "class Order" in models_content

    @pytest.mark.asyncio
    async def test_split_and_merge_roundtrip(self, temp_dir):
        """Test that split and merge are inverse operations."""
        from sindri.tools.refactoring import SplitFileTool

        # Create a combined file
        combined_content = '''"""Combined module."""

import json
from typing import Optional

class User:
    def __init__(self, name: str):
        self.name = name


class Order:
    def __init__(self, id: int):
        self.id = id
'''
        (temp_dir / "combined.py").write_text(combined_content)

        # Split the file
        split_tool = SplitFileTool(work_dir=temp_dir)
        split_result = await split_tool.execute(
            file="combined.py",
            strategy="classes",
            output_dir=str(temp_dir / "split"),
            keep_original=False,
            update_imports=False
        )

        assert split_result.success
        assert len(split_result.metadata["files_created"]) == 2

        # Merge back
        merge_tool = MergeFilesTool(work_dir=temp_dir)
        merge_result = await merge_tool.execute(
            pattern="split/*.py",
            destination="merged.py",
            update_imports=False
        )

        assert merge_result.success

        # Verify merged content has both classes
        merged_content = (temp_dir / "merged.py").read_text()
        assert "class User" in merged_content
        assert "class Order" in merged_content


# ============================================================
# Work Directory Tests
# ============================================================

class TestWorkDirectory:
    """Tests for work directory handling."""

    @pytest.mark.asyncio
    async def test_relative_paths(self, temp_dir):
        """Test that relative paths work correctly."""
        subdir = temp_dir / "src"
        subdir.mkdir()

        (subdir / "a.py").write_text("class A: pass")
        (subdir / "b.py").write_text("class B: pass")

        tool = MergeFilesTool(work_dir=temp_dir)

        result = await tool.execute(
            files=["src/a.py", "src/b.py"],
            destination="src/combined.py",
            update_imports=False
        )

        assert result.success
        assert (subdir / "combined.py").exists()
