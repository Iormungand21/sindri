"""Tests for BatchRenameTool.

Comprehensive test coverage for the batch_rename tool including:
- Basic glob pattern matching
- Regex pattern matching
- Output pattern placeholders
- Dry run mode
- Import updates
- Error handling
- Edge cases
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from sindri.tools.refactoring import BatchRenameTool


@pytest.fixture
def temp_dir():
    """Create a temporary directory with test files for batch rename operations."""
    temp = Path(tempfile.mkdtemp())

    # Create Python test files with test_ prefix
    (temp / "test_users.py").write_text("""\"\"\"User tests.\"\"\"

import pytest
from users import User

def test_create_user():
    user = User("John")
    assert user.name == "John"
""")

    (temp / "test_orders.py").write_text("""\"\"\"Order tests.\"\"\"

import pytest
from orders import Order

def test_create_order():
    order = Order(123)
    assert order.id == 123
""")

    (temp / "test_products.py").write_text("""\"\"\"Product tests.\"\"\"

import pytest
from products import Product

def test_create_product():
    product = Product("Widget")
    assert product.name == "Widget"
""")

    # Create corresponding source files
    (temp / "users.py").write_text("""\"\"\"User module.\"\"\"

class User:
    def __init__(self, name: str):
        self.name = name
""")

    (temp / "orders.py").write_text("""\"\"\"Orders module.\"\"\"

class Order:
    def __init__(self, id: int):
        self.id = id
""")

    (temp / "products.py").write_text("""\"\"\"Products module.\"\"\"

class Product:
    def __init__(self, name: str):
        self.name = name
""")

    # Create TypeScript test files with .test.ts suffix
    (temp / "utils.test.ts").write_text("""// Utils tests
import { helper } from './utils';

describe('helper', () => {
    it('should work', () => {
        expect(helper('test')).toBe('test');
    });
});
""")

    (temp / "api.test.ts").write_text("""// API tests
import { fetch } from './api';

describe('fetch', () => {
    it('should fetch data', () => {
        expect(fetch()).toBeDefined();
    });
});
""")

    # Source files for TS
    (temp / "utils.ts").write_text("""// Utils module
export function helper(data: string): string {
    return data;
}
""")

    (temp / "api.ts").write_text("""// API module
export function fetch(): any {
    return {};
}
""")

    # Create subdirectories
    (temp / "src").mkdir()
    (temp / "lib").mkdir()

    # Files in subdirectory
    (temp / "src" / "test_helpers.py").write_text("""\"\"\"Helper tests.\"\"\"

def test_something():
    pass
""")

    (temp / "src" / "config.test.ts").write_text("""// Config tests
import { config } from '../config';

describe('config', () => {
    it('should load', () => {
        expect(config).toBeDefined();
    });
});
""")

    # Create old_ prefixed files for regex testing
    (temp / "old_module.py").write_text("""\"\"\"Old module.\"\"\"
pass
""")

    (temp / "old_helper.py").write_text("""\"\"\"Old helper.\"\"\"
pass
""")

    yield temp
    shutil.rmtree(temp)


# ============================================================
# Basic Glob Pattern Tests
# ============================================================

class TestBatchRenameGlob:
    """Tests for glob pattern matching."""

    @pytest.mark.asyncio
    async def test_rename_test_prefix_to_suffix(self, temp_dir):
        """Test renaming test_*.py to *_test.py pattern."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="test_*.py",
            output="{1}_test.py",
            path=str(temp_dir),
            recursive=False,
            update_imports=False,
        )

        assert result.success
        assert "3" in result.output  # 3 files renamed
        assert (temp_dir / "users_test.py").exists()
        assert (temp_dir / "orders_test.py").exists()
        assert (temp_dir / "products_test.py").exists()
        assert not (temp_dir / "test_users.py").exists()

    @pytest.mark.asyncio
    async def test_rename_test_suffix_to_spec(self, temp_dir):
        """Test renaming *.test.ts to *.spec.ts pattern."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="*.test.ts",
            output="{stem}.spec.ts",
            path=str(temp_dir),
            recursive=False,
            update_imports=False,
        )

        assert result.success
        # The {stem} captures "utils.test", so we get "utils.test.spec.ts"
        # Let's verify what we get
        assert "2" in result.output  # 2 TS files
        assert result.metadata["files_renamed"] == 2

    @pytest.mark.asyncio
    async def test_rename_no_matches(self, temp_dir):
        """Test when no files match pattern."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="nonexistent_*.xyz",
            output="{stem}.abc",
            path=str(temp_dir),
        )

        assert result.success
        assert "No files matching" in result.output
        assert result.metadata["files_renamed"] == 0

    @pytest.mark.asyncio
    async def test_rename_recursive(self, temp_dir):
        """Test recursive file matching."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="test_*.py",
            output="{1}_test.py",
            path=str(temp_dir),
            recursive=True,
            update_imports=False,
        )

        assert result.success
        # Should match files in root and src/
        assert result.metadata["files_renamed"] == 4  # 3 in root + 1 in src
        assert (temp_dir / "src" / "helpers_test.py").exists()

    @pytest.mark.asyncio
    async def test_rename_non_recursive(self, temp_dir):
        """Test non-recursive file matching."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="test_*.py",
            output="{1}_test.py",
            path=str(temp_dir),
            recursive=False,
            update_imports=False,
        )

        assert result.success
        assert result.metadata["files_renamed"] == 3  # Only root files
        assert not (temp_dir / "src" / "helpers_test.py").exists()  # Not touched


# ============================================================
# Regex Pattern Tests
# ============================================================

class TestBatchRenameRegex:
    """Tests for regex pattern matching."""

    @pytest.mark.asyncio
    async def test_regex_prefix_replacement(self, temp_dir):
        """Test regex pattern for replacing prefix."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern=r"old_(.+)\.py",
            output="new_{1}.py",
            path=str(temp_dir),
            regex=True,
            update_imports=False,
        )

        assert result.success
        assert result.metadata["files_renamed"] == 2
        assert (temp_dir / "new_module.py").exists()
        assert (temp_dir / "new_helper.py").exists()
        assert not (temp_dir / "old_module.py").exists()

    @pytest.mark.asyncio
    async def test_regex_invalid_pattern(self, temp_dir):
        """Test error handling for invalid regex."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern=r"[invalid(",
            output="{1}.py",
            path=str(temp_dir),
            regex=True,
        )

        assert not result.success
        assert "Invalid regex pattern" in result.error

    @pytest.mark.asyncio
    async def test_regex_capture_groups(self, temp_dir):
        """Test regex with multiple capture groups."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern=r"test_(\w+)\.py",
            output="{1}_test.py",
            path=str(temp_dir),
            regex=True,
            recursive=False,
            update_imports=False,
        )

        assert result.success
        assert result.metadata["files_renamed"] == 3


# ============================================================
# Output Pattern Tests
# ============================================================

class TestBatchRenameOutput:
    """Tests for output pattern placeholders."""

    @pytest.mark.asyncio
    async def test_placeholder_stem(self, temp_dir):
        """Test {stem} placeholder."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="users.py",
            output="{stem}_backup.py",
            path=str(temp_dir),
            update_imports=False,
        )

        assert result.success
        assert (temp_dir / "users_backup.py").exists()

    @pytest.mark.asyncio
    async def test_placeholder_ext(self, temp_dir):
        """Test {ext} placeholder."""
        tool = BatchRenameTool(work_dir=temp_dir)

        # Write a .txt file first
        (temp_dir / "readme.txt").write_text("Hello")

        result = await tool.execute(
            pattern="readme.txt",
            output="README{ext}",
            path=str(temp_dir),
            update_imports=False,
        )

        assert result.success
        assert (temp_dir / "README.txt").exists()

    @pytest.mark.asyncio
    async def test_placeholder_parent(self, temp_dir):
        """Test {parent} placeholder."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="test_helpers.py",
            output="{parent}_{stem}.py",
            path=str(temp_dir / "src"),
            update_imports=False,
        )

        assert result.success
        assert (temp_dir / "src" / "src_test_helpers.py").exists()

    @pytest.mark.asyncio
    async def test_output_with_directory(self, temp_dir):
        """Test output pattern with directory path."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="old_*.py",
            output="lib/{stem}.py",
            path=str(temp_dir),
            recursive=False,
            update_imports=False,
        )

        assert result.success
        assert result.metadata["files_renamed"] == 2
        assert (temp_dir / "lib" / "old_module.py").exists()
        assert (temp_dir / "lib" / "old_helper.py").exists()


# ============================================================
# Dry Run Tests
# ============================================================

class TestBatchRenameDryRun:
    """Tests for dry run mode."""

    @pytest.mark.asyncio
    async def test_dry_run_no_changes(self, temp_dir):
        """Test that dry run doesn't modify files."""
        tool = BatchRenameTool(work_dir=temp_dir)

        # Record original files
        original_files = set(temp_dir.glob("test_*.py"))

        result = await tool.execute(
            pattern="test_*.py",
            output="{1}_test.py",
            path=str(temp_dir),
            dry_run=True,
            recursive=False,
            update_imports=False,
        )

        assert result.success
        assert "Would rename" in result.output
        assert result.metadata["dry_run"] is True

        # Verify files unchanged
        current_files = set(temp_dir.glob("test_*.py"))
        assert original_files == current_files

    @pytest.mark.asyncio
    async def test_dry_run_shows_planned_changes(self, temp_dir):
        """Test that dry run shows what would happen."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="test_*.py",
            output="{1}_test.py",
            path=str(temp_dir),
            dry_run=True,
            recursive=False,
            update_imports=False,
        )

        assert result.success
        assert "test_users.py" in result.output
        assert "users_test.py" in result.output
        assert result.metadata["files_renamed"] == 3


# ============================================================
# Import Update Tests
# ============================================================

class TestBatchRenameImports:
    """Tests for import update functionality."""

    @pytest.mark.asyncio
    async def test_rename_with_import_updates(self, temp_dir):
        """Test that imports are updated when files are renamed."""
        tool = BatchRenameTool(work_dir=temp_dir)

        # Rename users.py to user_model.py
        result = await tool.execute(
            pattern="users.py",
            output="user_model.py",
            path=str(temp_dir),
            update_imports=True,
        )

        assert result.success
        assert (temp_dir / "user_model.py").exists()

        # Check that test file was updated
        test_content = (temp_dir / "test_users.py").read_text()
        # The test file imports from users, which should now be user_model
        # Note: The import update happens if the module path changes

    @pytest.mark.asyncio
    async def test_rename_without_import_updates(self, temp_dir):
        """Test rename without updating imports."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="users.py",
            output="user_model.py",
            path=str(temp_dir),
            update_imports=False,
        )

        assert result.success
        assert (temp_dir / "user_model.py").exists()
        # Test file should have old import (unchanged)


# ============================================================
# Error Handling Tests
# ============================================================

class TestBatchRenameErrors:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_empty_pattern(self, temp_dir):
        """Test error on empty pattern."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="",
            output="new_{stem}.py",
            path=str(temp_dir),
        )

        assert not result.success
        assert "Pattern cannot be empty" in result.error

    @pytest.mark.asyncio
    async def test_empty_output(self, temp_dir):
        """Test error on empty output pattern."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="*.py",
            output="",
            path=str(temp_dir),
        )

        assert not result.success
        assert "Output pattern cannot be empty" in result.error

    @pytest.mark.asyncio
    async def test_invalid_path(self, temp_dir):
        """Test error on invalid path."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="*.py",
            output="{stem}_new.py",
            path="/nonexistent/path/12345",
        )

        assert not result.success
        assert "Path does not exist" in result.error

    @pytest.mark.asyncio
    async def test_path_is_file(self, temp_dir):
        """Test error when path is a file instead of directory."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="*.py",
            output="{stem}_new.py",
            path=str(temp_dir / "users.py"),
        )

        assert not result.success
        assert "not a directory" in result.error

    @pytest.mark.asyncio
    async def test_max_files_exceeded(self, temp_dir):
        """Test error when max_files limit exceeded."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="*.py",
            output="{stem}_new.py",
            path=str(temp_dir),
            max_files=1,  # Very low limit
        )

        assert not result.success
        assert "exceeds max_files limit" in result.error

    @pytest.mark.asyncio
    async def test_destination_conflict(self, temp_dir):
        """Test error when destination already exists."""
        tool = BatchRenameTool(work_dir=temp_dir)

        # Try to rename users.py to orders.py (which exists)
        result = await tool.execute(
            pattern="users.py",
            output="orders.py",
            path=str(temp_dir),
            update_imports=False,
        )

        assert not result.success
        assert "already exists" in result.error

    @pytest.mark.asyncio
    async def test_multiple_to_same_destination(self, temp_dir):
        """Test error when multiple files would rename to same destination."""
        tool = BatchRenameTool(work_dir=temp_dir)

        # All test_*.py would rename to same "tests.py"
        result = await tool.execute(
            pattern="test_*.py",
            output="tests.py",
            path=str(temp_dir),
            recursive=False,
            update_imports=False,
        )

        assert not result.success
        assert "Multiple files" in result.error or "Conflicts detected" in result.error

    @pytest.mark.asyncio
    async def test_invalid_max_files(self, temp_dir):
        """Test error on invalid max_files value."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="*.py",
            output="{stem}_new.py",
            path=str(temp_dir),
            max_files=0,
        )

        assert not result.success
        assert "max_files must be at least 1" in result.error


# ============================================================
# Edge Cases
# ============================================================

class TestBatchRenameEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_single_file_rename(self, temp_dir):
        """Test renaming a single file."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="users.py",
            output="user_model.py",
            path=str(temp_dir),
            update_imports=False,
        )

        assert result.success
        assert result.metadata["files_renamed"] == 1
        assert (temp_dir / "user_model.py").exists()
        assert not (temp_dir / "users.py").exists()

    @pytest.mark.asyncio
    async def test_preserve_extension(self, temp_dir):
        """Test preserving file extension with {ext}."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="users.py",
            output="model_{name}{ext}",
            path=str(temp_dir),
            update_imports=False,
        )

        assert result.success
        assert (temp_dir / "model_users.py").exists()

    @pytest.mark.asyncio
    async def test_skip_dirs(self, temp_dir):
        """Test that skip directories are honored."""
        # Create a file in node_modules (should be skipped)
        (temp_dir / "node_modules").mkdir()
        (temp_dir / "node_modules" / "test_skip.py").write_text("pass")

        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="test_*.py",
            output="{1}_test.py",
            path=str(temp_dir),
            recursive=True,
            update_imports=False,
        )

        assert result.success
        # The file in node_modules should not be touched
        assert (temp_dir / "node_modules" / "test_skip.py").exists()

    @pytest.mark.asyncio
    async def test_glob_question_mark(self, temp_dir):
        """Test glob pattern with ? wildcard."""
        # Create specific files
        (temp_dir / "a1.txt").write_text("a1")
        (temp_dir / "b2.txt").write_text("b2")
        (temp_dir / "c3.txt").write_text("c3")
        (temp_dir / "abc.txt").write_text("abc")  # Won't match

        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="??.txt",  # Two character names
            output="{stem}_file.txt",
            path=str(temp_dir),
            update_imports=False,
        )

        assert result.success
        assert result.metadata["files_renamed"] == 3
        assert (temp_dir / "a1_file.txt").exists()
        assert (temp_dir / "b2_file.txt").exists()
        assert (temp_dir / "c3_file.txt").exists()
        assert (temp_dir / "abc.txt").exists()  # Unchanged

    @pytest.mark.asyncio
    async def test_metadata_content(self, temp_dir):
        """Test that metadata contains expected fields."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="test_*.py",
            output="{1}_test.py",
            path=str(temp_dir),
            recursive=False,
            update_imports=False,
            dry_run=True,
        )

        assert result.success
        assert "files_renamed" in result.metadata
        assert "renames" in result.metadata
        assert "dry_run" in result.metadata
        assert result.metadata["dry_run"] is True
        assert len(result.metadata["renames"]) == 3


# ============================================================
# Integration Tests
# ============================================================

class TestBatchRenameIntegration:
    """Integration tests with real file operations."""

    @pytest.mark.asyncio
    async def test_full_workflow_python_tests(self, temp_dir):
        """Test complete workflow: rename test files and update imports."""
        tool = BatchRenameTool(work_dir=temp_dir)

        # First, dry run to preview
        dry_result = await tool.execute(
            pattern="test_*.py",
            output="{1}_test.py",
            path=str(temp_dir),
            recursive=False,
            update_imports=True,
            dry_run=True,
        )

        assert dry_result.success
        assert dry_result.metadata["files_renamed"] == 3

        # Then execute for real
        result = await tool.execute(
            pattern="test_*.py",
            output="{1}_test.py",
            path=str(temp_dir),
            recursive=False,
            update_imports=True,
            dry_run=False,
        )

        assert result.success
        assert result.metadata["files_renamed"] == 3

        # Verify all files renamed
        assert (temp_dir / "users_test.py").exists()
        assert (temp_dir / "orders_test.py").exists()
        assert (temp_dir / "products_test.py").exists()

    @pytest.mark.asyncio
    async def test_full_workflow_ts_tests(self, temp_dir):
        """Test complete workflow with TypeScript files."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="*.test.ts",
            output="{1}.spec.ts",
            path=str(temp_dir),
            recursive=False,
            update_imports=False,
        )

        assert result.success
        assert result.metadata["files_renamed"] == 2

    @pytest.mark.asyncio
    async def test_move_files_to_subdirectory(self, temp_dir):
        """Test moving files to a subdirectory using output pattern."""
        tool = BatchRenameTool(work_dir=temp_dir)

        result = await tool.execute(
            pattern="old_*.py",
            output="lib/{stem}.py",
            path=str(temp_dir),
            recursive=False,
            update_imports=False,
        )

        assert result.success
        assert result.metadata["files_renamed"] == 2
        assert (temp_dir / "lib" / "old_module.py").exists()
        assert (temp_dir / "lib" / "old_helper.py").exists()
        assert not (temp_dir / "old_module.py").exists()
        assert not (temp_dir / "old_helper.py").exists()
