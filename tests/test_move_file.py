"""Tests for MoveFileTool.

Comprehensive test coverage for the move_file tool including:
- Basic file moves
- Import updates (Python and JavaScript/TypeScript)
- Dry run mode
- Error handling
- Edge cases
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from sindri.tools.refactoring import MoveFileTool


@pytest.fixture
def temp_dir():
    """Create a temporary directory with test files for move operations."""
    temp = Path(tempfile.mkdtemp())

    # Create Python files
    (temp / "main.py").write_text("""#!/usr/bin/env python
\"\"\"Main application module.\"\"\"

from utils import helper_function
from models import User

def main():
    user = User("John")
    result = helper_function(user)
    return result
""")

    (temp / "utils.py").write_text("""\"\"\"Utility functions.\"\"\"

def helper_function(data):
    \"\"\"Process data.\"\"\"
    return str(data)
""")

    (temp / "models.py").write_text("""\"\"\"Data models.\"\"\"

class User:
    \"\"\"User model.\"\"\"
    def __init__(self, name: str):
        self.name = name

    def __str__(self):
        return f"User({self.name})"
""")

    # Create a file that imports from another file
    (temp / "app.py").write_text("""\"\"\"Application entry.\"\"\"

from utils import helper_function
import models

def run():
    user = models.User("Jane")
    return helper_function(user)
""")

    # Create subdirectories
    (temp / "src").mkdir()
    (temp / "src" / "helpers").mkdir()
    (temp / "lib").mkdir()

    # Python file in subdirectory
    (temp / "src" / "service.py").write_text("""\"\"\"Service module.\"\"\"

from utils import helper_function
from models import User

class UserService:
    def get_user(self, name: str) -> User:
        return User(name)
""")

    # TypeScript files
    (temp / "index.ts").write_text("""// Main entry point
import { helper } from './utils';
import { User } from './models';

export function main(): void {
    const user = new User('John');
    helper(user);
}
""")

    (temp / "utils.ts").write_text("""// Utility functions
export function helper(data: any): string {
    return String(data);
}

export function formatDate(date: Date): string {
    return date.toISOString();
}
""")

    (temp / "models.ts").write_text("""// Data models
export class User {
    constructor(public name: string) {}

    toString(): string {
        return `User(${this.name})`;
    }
}
""")

    # JavaScript file
    (temp / "app.js").write_text("""// Application
const { helper } = require('./utils');
import { User } from './models';

function run() {
    const user = new User('Jane');
    return helper(user);
}

module.exports = { run };
""")

    # TypeScript file in subdirectory
    (temp / "src" / "api.ts").write_text("""// API module
import { helper } from '../utils';
import { User } from '../models';

export class Api {
    getUser(name: string): User {
        return new User(name);
    }
}
""")

    yield temp
    shutil.rmtree(temp)


# ============================================================
# Basic Move Operations
# ============================================================

class TestMoveFileBasic:
    """Tests for basic file move operations."""

    @pytest.mark.asyncio
    async def test_move_file_simple(self, temp_dir):
        """Test simple file move without import updates."""
        tool = MoveFileTool(work_dir=temp_dir)

        # Create a simple file to move
        (temp_dir / "simple.txt").write_text("Hello World")

        result = await tool.execute(
            source="simple.txt",
            destination="moved.txt",
            update_imports=False
        )

        assert result.success
        assert not (temp_dir / "simple.txt").exists()
        assert (temp_dir / "moved.txt").exists()
        assert (temp_dir / "moved.txt").read_text() == "Hello World"

    @pytest.mark.asyncio
    async def test_move_file_to_subdirectory(self, temp_dir):
        """Test moving file to a subdirectory."""
        tool = MoveFileTool(work_dir=temp_dir)

        # Create a file
        (temp_dir / "file.py").write_text("# Test file\n")

        result = await tool.execute(
            source="file.py",
            destination="lib/file.py",
            update_imports=False
        )

        assert result.success
        assert not (temp_dir / "file.py").exists()
        assert (temp_dir / "lib" / "file.py").exists()

    @pytest.mark.asyncio
    async def test_move_file_creates_directory(self, temp_dir):
        """Test that move creates destination directory if needed."""
        tool = MoveFileTool(work_dir=temp_dir)

        # Create a file
        (temp_dir / "file.py").write_text("# Test\n")

        result = await tool.execute(
            source="file.py",
            destination="new_dir/subdir/file.py",
            update_imports=False,
            create_dirs=True
        )

        assert result.success
        assert (temp_dir / "new_dir" / "subdir" / "file.py").exists()

    @pytest.mark.asyncio
    async def test_move_file_rename(self, temp_dir):
        """Test file rename (move within same directory)."""
        tool = MoveFileTool(work_dir=temp_dir)

        result = await tool.execute(
            source="utils.py",
            destination="helpers.py",
            update_imports=False
        )

        assert result.success
        assert not (temp_dir / "utils.py").exists()
        assert (temp_dir / "helpers.py").exists()


# ============================================================
# Dry Run Tests
# ============================================================

class TestMoveFileDryRun:
    """Tests for dry run mode."""

    @pytest.mark.asyncio
    async def test_dry_run_does_not_move(self, temp_dir):
        """Test that dry run doesn't actually move the file."""
        tool = MoveFileTool(work_dir=temp_dir)

        result = await tool.execute(
            source="utils.py",
            destination="moved_utils.py",
            dry_run=True
        )

        assert result.success
        assert "Would move" in result.output
        # File should still be at original location
        assert (temp_dir / "utils.py").exists()
        assert not (temp_dir / "moved_utils.py").exists()

    @pytest.mark.asyncio
    async def test_dry_run_shows_import_updates(self, temp_dir):
        """Test that dry run shows what imports would be updated."""
        tool = MoveFileTool(work_dir=temp_dir)

        result = await tool.execute(
            source="utils.py",
            destination="helpers/utils.py",
            dry_run=True
        )

        assert result.success
        assert "Would" in result.output
        # Should show import update info
        assert result.metadata["dry_run"] is True


# ============================================================
# Python Import Update Tests
# ============================================================

class TestMoveFilePythonImports:
    """Tests for Python import updates."""

    @pytest.mark.asyncio
    async def test_update_python_import_statement(self, temp_dir):
        """Test updating 'import module' statements."""
        tool = MoveFileTool(work_dir=temp_dir)

        result = await tool.execute(
            source="models.py",
            destination="data/models.py",
            update_imports=True
        )

        assert result.success

        # Check that app.py import was updated
        app_content = (temp_dir / "app.py").read_text()
        assert "import data.models" in app_content or "from data.models import" in app_content

    @pytest.mark.asyncio
    async def test_update_python_from_import(self, temp_dir):
        """Test updating 'from module import x' statements."""
        tool = MoveFileTool(work_dir=temp_dir)

        result = await tool.execute(
            source="utils.py",
            destination="helpers/utils.py",
            update_imports=True
        )

        assert result.success

        # Check metadata for updated files
        assert result.metadata["imports_updated"] > 0
        assert len(result.metadata["files_updated"]) > 0

    @pytest.mark.asyncio
    async def test_python_import_multiple_files(self, temp_dir):
        """Test that multiple files are updated."""
        tool = MoveFileTool(work_dir=temp_dir)

        # utils.py is imported by multiple files
        result = await tool.execute(
            source="utils.py",
            destination="lib/utils.py",
            update_imports=True
        )

        assert result.success
        # Should update main.py, app.py, src/service.py
        assert result.metadata["imports_updated"] >= 1


# ============================================================
# JavaScript/TypeScript Import Update Tests
# ============================================================

class TestMoveFileJsImports:
    """Tests for JavaScript/TypeScript import updates."""

    @pytest.mark.asyncio
    async def test_update_ts_import_statement(self, temp_dir):
        """Test updating TypeScript import statements."""
        tool = MoveFileTool(work_dir=temp_dir)

        result = await tool.execute(
            source="utils.ts",
            destination="lib/utils.ts",
            update_imports=True
        )

        assert result.success

    @pytest.mark.asyncio
    async def test_update_js_require_statement(self, temp_dir):
        """Test updating JavaScript require() statements."""
        tool = MoveFileTool(work_dir=temp_dir)

        # Move utils.ts which is required by app.js
        result = await tool.execute(
            source="utils.ts",
            destination="helpers/utils.ts",
            update_imports=True
        )

        assert result.success

    @pytest.mark.asyncio
    async def test_ts_relative_import_update(self, temp_dir):
        """Test updating relative imports in TypeScript."""
        tool = MoveFileTool(work_dir=temp_dir)

        result = await tool.execute(
            source="models.ts",
            destination="data/models.ts",
            update_imports=True
        )

        assert result.success


# ============================================================
# Error Handling Tests
# ============================================================

class TestMoveFileErrors:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_source_not_found(self, temp_dir):
        """Test error when source file doesn't exist."""
        tool = MoveFileTool(work_dir=temp_dir)

        result = await tool.execute(
            source="nonexistent.py",
            destination="moved.py"
        )

        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_destination_exists(self, temp_dir):
        """Test error when destination already exists."""
        tool = MoveFileTool(work_dir=temp_dir)

        result = await tool.execute(
            source="utils.py",
            destination="models.py"  # Already exists
        )

        assert not result.success
        assert "already exists" in result.error.lower()

    @pytest.mark.asyncio
    async def test_source_is_directory(self, temp_dir):
        """Test error when trying to move a directory."""
        tool = MoveFileTool(work_dir=temp_dir)

        result = await tool.execute(
            source="src",  # This is a directory
            destination="new_src"
        )

        assert not result.success
        assert "not a file" in result.error.lower()

    @pytest.mark.asyncio
    async def test_invalid_search_path(self, temp_dir):
        """Test error when search path doesn't exist."""
        tool = MoveFileTool(work_dir=temp_dir)

        result = await tool.execute(
            source="utils.py",
            destination="lib/utils.py",
            search_path="nonexistent_dir"
        )

        assert not result.success
        assert "does not exist" in result.error.lower()


# ============================================================
# Edge Cases
# ============================================================

class TestMoveFileEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_move_file_no_imports_to_update(self, temp_dir):
        """Test moving a file with no import references."""
        tool = MoveFileTool(work_dir=temp_dir)

        # Create an isolated file
        (temp_dir / "isolated.py").write_text("# No imports reference this\n")

        result = await tool.execute(
            source="isolated.py",
            destination="lib/isolated.py",
            update_imports=True
        )

        assert result.success
        assert result.metadata["imports_updated"] == 0

    @pytest.mark.asyncio
    async def test_move_within_same_directory(self, temp_dir):
        """Test moving file within the same directory (rename)."""
        tool = MoveFileTool(work_dir=temp_dir)

        result = await tool.execute(
            source="utils.py",
            destination="utility.py",
            update_imports=True
        )

        assert result.success
        assert not (temp_dir / "utils.py").exists()
        assert (temp_dir / "utility.py").exists()

    @pytest.mark.asyncio
    async def test_move_preserves_file_content(self, temp_dir):
        """Test that file content is preserved after move."""
        tool = MoveFileTool(work_dir=temp_dir)

        original_content = (temp_dir / "utils.py").read_text()

        result = await tool.execute(
            source="utils.py",
            destination="lib/utils.py",
            update_imports=False
        )

        assert result.success
        moved_content = (temp_dir / "lib" / "utils.py").read_text()
        assert moved_content == original_content

    @pytest.mark.asyncio
    async def test_move_with_special_characters_in_name(self, temp_dir):
        """Test moving files with special characters in name."""
        tool = MoveFileTool(work_dir=temp_dir)

        # Create file with underscores
        (temp_dir / "my_special_file.py").write_text("# Special\n")

        result = await tool.execute(
            source="my_special_file.py",
            destination="lib/my_special_file.py",
            update_imports=False
        )

        assert result.success
        assert (temp_dir / "lib" / "my_special_file.py").exists()

    @pytest.mark.asyncio
    async def test_disable_update_imports(self, temp_dir):
        """Test that update_imports=False skips import updates."""
        tool = MoveFileTool(work_dir=temp_dir)

        # Save original content
        original_main = (temp_dir / "main.py").read_text()

        result = await tool.execute(
            source="utils.py",
            destination="helpers/utils.py",
            update_imports=False
        )

        assert result.success
        # main.py should NOT be modified
        assert (temp_dir / "main.py").read_text() == original_main

    @pytest.mark.asyncio
    async def test_metadata_contains_expected_fields(self, temp_dir):
        """Test that result metadata has expected fields."""
        tool = MoveFileTool(work_dir=temp_dir)

        result = await tool.execute(
            source="utils.py",
            destination="lib/utils.py"
        )

        assert result.success
        assert "source" in result.metadata
        assert "destination" in result.metadata
        assert "files_updated" in result.metadata
        assert "imports_updated" in result.metadata
        assert "dry_run" in result.metadata


# ============================================================
# Integration Tests
# ============================================================

class TestMoveFileIntegration:
    """Integration tests for MoveFileTool."""

    @pytest.mark.asyncio
    async def test_move_and_verify_imports_valid(self, temp_dir):
        """Test that moved file and updated imports are syntactically valid."""
        tool = MoveFileTool(work_dir=temp_dir)

        result = await tool.execute(
            source="models.py",
            destination="data/models.py",
            update_imports=True
        )

        assert result.success

        # Verify the moved file exists
        assert (temp_dir / "data" / "models.py").exists()

        # Verify we can still import (syntax check)
        import ast
        moved_content = (temp_dir / "data" / "models.py").read_text()
        ast.parse(moved_content)  # Should not raise

    @pytest.mark.asyncio
    async def test_multiple_moves_sequential(self, temp_dir):
        """Test multiple sequential move operations."""
        tool = MoveFileTool(work_dir=temp_dir)

        # First move
        result1 = await tool.execute(
            source="utils.py",
            destination="lib/utils.py",
            update_imports=False
        )
        assert result1.success

        # Second move
        result2 = await tool.execute(
            source="lib/utils.py",
            destination="helpers/utils.py",
            update_imports=False
        )
        assert result2.success

        # Verify final location
        assert not (temp_dir / "utils.py").exists()
        assert not (temp_dir / "lib" / "utils.py").exists()
        assert (temp_dir / "helpers" / "utils.py").exists()


# ============================================================
# Tool Schema Tests
# ============================================================

class TestMoveFileSchema:
    """Tests for tool schema and registration."""

    def test_tool_name(self):
        """Test tool has correct name."""
        tool = MoveFileTool()
        assert tool.name == "move_file"

    def test_tool_description(self):
        """Test tool has description."""
        tool = MoveFileTool()
        assert tool.description
        assert "move" in tool.description.lower()
        assert "import" in tool.description.lower()

    def test_tool_parameters(self):
        """Test tool has required parameters."""
        tool = MoveFileTool()
        params = tool.parameters

        assert params["type"] == "object"
        assert "source" in params["properties"]
        assert "destination" in params["properties"]
        assert "update_imports" in params["properties"]
        assert "dry_run" in params["properties"]
        assert "source" in params["required"]
        assert "destination" in params["required"]

    def test_tool_schema(self):
        """Test tool generates valid schema."""
        tool = MoveFileTool()
        schema = tool.get_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "move_file"
        assert "parameters" in schema["function"]
