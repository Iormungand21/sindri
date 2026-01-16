"""Tests for refactoring tools."""

import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import Mock, AsyncMock, patch

from sindri.tools.refactoring import (
    RenameSymbolTool,
    ExtractFunctionTool,
    InlineVariableTool,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory with test files for refactoring."""
    temp = Path(tempfile.mkdtemp())

    # Create Python files
    (temp / "main.py").write_text("""#!/usr/bin/env python
\"\"\"Main application module.\"\"\"

def get_user(user_id: int) -> dict:
    \"\"\"Get a user by ID.\"\"\"
    user = fetch_from_db(user_id)
    return user


def fetch_from_db(id: int) -> dict:
    \"\"\"Fetch data from database.\"\"\"
    return {"id": id, "name": "John"}


class UserModel:
    \"\"\"User data model.\"\"\"
    def __init__(self, name: str):
        self.name = name

    def get_user_name(self) -> str:
        return self.name


MAX_RETRIES = 3
config = {
    "debug": True,
    "port": 8080
}
""")

    (temp / "utils.py").write_text("""\"\"\"Utility functions.\"\"\"

from main import get_user, UserModel

def process_user(user_id: int) -> str:
    \"\"\"Process a user.\"\"\"
    user = get_user(user_id)
    model = UserModel(user["name"])
    return model.get_user_name()


def calculate_total(items: list) -> float:
    total = 0
    for item in items:
        total = total + item["price"]
    return total


DEBUG = True
MAX_RETRIES = 5  # Different value in this file
""")

    # Create TypeScript file
    (temp / "app.ts").write_text("""// Application entry point

export interface User {
    id: number;
    name: string;
}

export class UserHandler {
    private users: User[] = [];

    async fetchUser(userId: number): Promise<User | null> {
        return this.users.find(u => u.id === userId) || null;
    }

    getUserName(user: User): string {
        return user.name;
    }
}

export const MAX_RETRIES = 3;

export function processUser(userId: number): void {
    console.log("Processing user", userId);
}
""")

    # Create JavaScript file
    (temp / "helpers.js").write_text("""// Helper functions

const API_URL = "http://api.example.com";

function fetchUser(id) {
    return null;
}

function processData(data) {
    const result = data.value * 2;
    console.log(result);
    return result;
}

class DataManager {
    constructor() {
        this.data = [];
    }

    addItem(item) {
        this.data.push(item);
    }
}
""")

    # Create a subdirectory with more files
    sub = temp / "src"
    sub.mkdir()

    (sub / "module.py").write_text("""\"\"\"Module file.\"\"\"

from main import get_user

def get_user_info(user_id: int) -> str:
    user = get_user(user_id)
    return f"User: {user['name']}"
""")

    yield temp
    shutil.rmtree(temp)


# ============================================================
# RenameSymbolTool Tests
# ============================================================

class TestRenameSymbolTool:
    """Tests for RenameSymbolTool."""

    @pytest.fixture
    def tool(self, temp_dir):
        """Create tool with temp directory as work_dir."""
        return RenameSymbolTool(work_dir=temp_dir)

    @pytest.mark.asyncio
    async def test_rename_function_in_single_file(self, tool, temp_dir):
        """Test renaming a function in a single file."""
        result = await tool.execute(
            old_name="fetch_from_db",
            new_name="retrieve_from_database",
            path=str(temp_dir / "main.py")
        )
        assert result.success
        assert "occurrence(s)" in result.output
        assert "1 file(s)" in result.output

        # Verify the change was made
        content = (temp_dir / "main.py").read_text()
        assert "def retrieve_from_database" in content
        assert "def fetch_from_db" not in content

    @pytest.mark.asyncio
    async def test_rename_function_across_files(self, tool, temp_dir):
        """Test renaming a function used across multiple files."""
        result = await tool.execute(
            old_name="get_user",
            new_name="fetch_user_by_id",
            path=str(temp_dir)
        )
        assert result.success
        assert "file(s)" in result.output

        # Verify changes in multiple files
        main_content = (temp_dir / "main.py").read_text()
        utils_content = (temp_dir / "utils.py").read_text()
        module_content = (temp_dir / "src" / "module.py").read_text()

        assert "def fetch_user_by_id" in main_content
        assert "fetch_user_by_id" in utils_content
        assert "fetch_user_by_id" in module_content
        # get_user_name should NOT be renamed (respects word boundaries)
        assert "get_user_name" in main_content

    @pytest.mark.asyncio
    async def test_rename_class(self, tool, temp_dir):
        """Test renaming a class."""
        result = await tool.execute(
            old_name="UserModel",
            new_name="UserEntity",
            path=str(temp_dir)
        )
        assert result.success

        # Verify the class was renamed
        main_content = (temp_dir / "main.py").read_text()
        utils_content = (temp_dir / "utils.py").read_text()

        assert "class UserEntity" in main_content
        assert "UserEntity(user" in utils_content

    @pytest.mark.asyncio
    async def test_rename_constant(self, tool, temp_dir):
        """Test renaming a constant."""
        result = await tool.execute(
            old_name="MAX_RETRIES",
            new_name="MAX_ATTEMPTS",
            path=str(temp_dir),
            file_types=["py"]
        )
        assert result.success

        # Verify the constant was renamed in both files
        main_content = (temp_dir / "main.py").read_text()
        utils_content = (temp_dir / "utils.py").read_text()

        assert "MAX_ATTEMPTS" in main_content
        assert "MAX_ATTEMPTS" in utils_content
        assert "MAX_RETRIES" not in main_content
        assert "MAX_RETRIES" not in utils_content

    @pytest.mark.asyncio
    async def test_rename_dry_run(self, tool, temp_dir):
        """Test dry run mode - should not modify files."""
        original_content = (temp_dir / "main.py").read_text()

        result = await tool.execute(
            old_name="get_user",
            new_name="fetch_user",
            path=str(temp_dir),
            dry_run=True
        )
        assert result.success
        assert "Would modify" in result.output

        # Verify file was NOT modified
        new_content = (temp_dir / "main.py").read_text()
        assert new_content == original_content

    @pytest.mark.asyncio
    async def test_rename_typescript_class(self, tool, temp_dir):
        """Test renaming in TypeScript files."""
        result = await tool.execute(
            old_name="UserHandler",
            new_name="UserService",
            path=str(temp_dir),
            file_types=["ts"]
        )
        assert result.success

        content = (temp_dir / "app.ts").read_text()
        assert "class UserService" in content
        assert "UserHandler" not in content

    @pytest.mark.asyncio
    async def test_rename_respects_word_boundaries(self, tool, temp_dir):
        """Test that rename respects word boundaries (no partial matches)."""
        # Create a file with similar names
        (temp_dir / "boundary.py").write_text("""
user = "test"
user_id = 1
user_name = "John"
current_user = None
""")

        result = await tool.execute(
            old_name="user",
            new_name="person",
            path=str(temp_dir / "boundary.py")
        )
        assert result.success

        content = (temp_dir / "boundary.py").read_text()
        assert "person = " in content
        assert "user_id" in content  # Should NOT be changed
        assert "user_name" in content  # Should NOT be changed
        assert "current_user" in content  # Should NOT be changed

    @pytest.mark.asyncio
    async def test_rename_no_occurrences(self, tool, temp_dir):
        """Test renaming when symbol doesn't exist."""
        result = await tool.execute(
            old_name="nonexistent_function",
            new_name="new_name",
            path=str(temp_dir)
        )
        assert result.success
        assert "No occurrences" in result.output

    @pytest.mark.asyncio
    async def test_rename_empty_old_name_error(self, tool):
        """Test error when old_name is empty."""
        result = await tool.execute(old_name="", new_name="new_name")
        assert not result.success
        assert "cannot be empty" in result.error

    @pytest.mark.asyncio
    async def test_rename_same_name_error(self, tool):
        """Test error when old_name equals new_name."""
        result = await tool.execute(old_name="test", new_name="test")
        assert not result.success
        assert "same" in result.error

    @pytest.mark.asyncio
    async def test_rename_invalid_identifier_error(self, tool):
        """Test error for invalid identifier names."""
        result = await tool.execute(old_name="123invalid", new_name="valid")
        assert not result.success
        assert "Invalid identifier" in result.error

    @pytest.mark.asyncio
    async def test_rename_path_not_found(self, tool):
        """Test error when path doesn't exist."""
        result = await tool.execute(
            old_name="test",
            new_name="new_test",
            path="/nonexistent/path"
        )
        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_rename_metadata(self, tool, temp_dir):
        """Test that result includes proper metadata."""
        result = await tool.execute(
            old_name="get_user",
            new_name="fetch_user",
            path=str(temp_dir)
        )
        assert result.success
        assert "files_modified" in result.metadata
        assert "occurrences" in result.metadata
        assert result.metadata["occurrences"] > 0


# ============================================================
# ExtractFunctionTool Tests
# ============================================================

class TestExtractFunctionTool:
    """Tests for ExtractFunctionTool."""

    @pytest.fixture
    def tool(self, temp_dir):
        """Create tool with temp directory as work_dir."""
        return ExtractFunctionTool(work_dir=temp_dir)

    @pytest.fixture
    def extract_test_file(self, temp_dir):
        """Create a test file for extraction."""
        content = """def process_items(items):
    # Calculate total price
    total = 0
    for item in items:
        price = item["price"]
        quantity = item["quantity"]
        total = total + (price * quantity)
    return total
"""
        (temp_dir / "extract_test.py").write_text(content)
        return temp_dir / "extract_test.py"

    @pytest.mark.asyncio
    async def test_extract_python_function(self, tool, extract_test_file):
        """Test extracting a Python function."""
        result = await tool.execute(
            file=str(extract_test_file),
            start_line=3,
            end_line=7,
            function_name="calculate_item_total"
        )
        assert result.success
        assert "Extracted function" in result.output
        assert "calculate_item_total" in result.output

        content = extract_test_file.read_text()
        assert "def calculate_item_total" in content

    @pytest.mark.asyncio
    async def test_extract_with_params(self, tool, extract_test_file):
        """Test extracting with explicit parameters."""
        result = await tool.execute(
            file=str(extract_test_file),
            start_line=3,
            end_line=7,
            function_name="calculate_total",
            params=["items"],
            return_value="total"
        )
        assert result.success

        content = extract_test_file.read_text()
        assert "def calculate_total(items)" in content
        assert "return total" in content

    @pytest.mark.asyncio
    async def test_extract_with_docstring(self, tool, extract_test_file):
        """Test extracting with docstring."""
        result = await tool.execute(
            file=str(extract_test_file),
            start_line=3,
            end_line=7,
            function_name="calculate_total",
            docstring="Calculate the total price of items."
        )
        assert result.success

        content = extract_test_file.read_text()
        assert "Calculate the total price" in content

    @pytest.mark.asyncio
    async def test_extract_dry_run(self, tool, extract_test_file):
        """Test dry run mode."""
        original_content = extract_test_file.read_text()

        result = await tool.execute(
            file=str(extract_test_file),
            start_line=3,
            end_line=7,
            function_name="calculate_total",
            dry_run=True
        )
        assert result.success
        assert "Would extract" in result.output

        # File should not be modified
        assert extract_test_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_extract_javascript_function(self, tool, temp_dir):
        """Test extracting a JavaScript function."""
        js_file = temp_dir / "extract_test.js"
        js_file.write_text("""function processData(data) {
    // Transform the data
    const result = [];
    for (const item of data) {
        result.push(item.value * 2);
    }
    return result;
}
""")
        result = await tool.execute(
            file=str(js_file),
            start_line=3,
            end_line=6,
            function_name="transformData",
            params=["data"],
            return_value="result"
        )
        assert result.success

        content = js_file.read_text()
        assert "function transformData" in content

    @pytest.mark.asyncio
    async def test_extract_invalid_line_numbers(self, tool, extract_test_file):
        """Test error for invalid line numbers."""
        result = await tool.execute(
            file=str(extract_test_file),
            start_line=0,
            end_line=5,
            function_name="test"
        )
        assert not result.success
        assert "must be >= 1" in result.error

    @pytest.mark.asyncio
    async def test_extract_end_before_start(self, tool, extract_test_file):
        """Test error when end_line is before start_line."""
        result = await tool.execute(
            file=str(extract_test_file),
            start_line=5,
            end_line=3,
            function_name="test"
        )
        assert not result.success
        assert "must be >= start_line" in result.error

    @pytest.mark.asyncio
    async def test_extract_invalid_function_name(self, tool, extract_test_file):
        """Test error for invalid function name."""
        result = await tool.execute(
            file=str(extract_test_file),
            start_line=3,
            end_line=7,
            function_name="123invalid"
        )
        assert not result.success
        assert "Invalid function name" in result.error

    @pytest.mark.asyncio
    async def test_extract_file_not_found(self, tool):
        """Test error when file doesn't exist."""
        result = await tool.execute(
            file="/nonexistent/file.py",
            start_line=1,
            end_line=5,
            function_name="test"
        )
        assert not result.success
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_extract_start_line_exceeds_file(self, tool, extract_test_file):
        """Test error when start_line exceeds file length."""
        result = await tool.execute(
            file=str(extract_test_file),
            start_line=1000,
            end_line=1005,
            function_name="test"
        )
        assert not result.success
        assert "exceeds file length" in result.error

    @pytest.mark.asyncio
    async def test_extract_metadata(self, tool, extract_test_file):
        """Test that result includes proper metadata."""
        result = await tool.execute(
            file=str(extract_test_file),
            start_line=3,
            end_line=7,
            function_name="calculate_total"
        )
        assert result.success
        assert "function_name" in result.metadata
        assert "start_line" in result.metadata
        assert "end_line" in result.metadata
        assert "lines_extracted" in result.metadata


# ============================================================
# InlineVariableTool Tests
# ============================================================

class TestInlineVariableTool:
    """Tests for InlineVariableTool."""

    @pytest.fixture
    def tool(self, temp_dir):
        """Create tool with temp directory as work_dir."""
        return InlineVariableTool(work_dir=temp_dir)

    @pytest.fixture
    def inline_test_file(self, temp_dir):
        """Create a test file for inlining."""
        content = """def calculate_discount(price, rate):
    discount = price * rate
    final_price = price - discount
    savings = discount
    print(f"You save: {savings}")
    return final_price
"""
        (temp_dir / "inline_test.py").write_text(content)
        return temp_dir / "inline_test.py"

    @pytest.mark.asyncio
    async def test_inline_simple_variable(self, tool, inline_test_file):
        """Test inlining a simple variable."""
        result = await tool.execute(
            file=str(inline_test_file),
            variable="discount"
        )
        assert result.success
        assert "Inlined" in result.output

        content = inline_test_file.read_text()
        # discount should be inlined, but price * rate might have parens
        assert "discount" not in content or "(price * rate)" in content

    @pytest.mark.asyncio
    async def test_inline_keeps_assignment_when_requested(self, tool, inline_test_file):
        """Test keeping the assignment line when remove_assignment is False."""
        result = await tool.execute(
            file=str(inline_test_file),
            variable="discount",
            remove_assignment=False
        )
        assert result.success

        content = inline_test_file.read_text()
        # Assignment should still exist
        assert "discount = price * rate" in content

    @pytest.mark.asyncio
    async def test_inline_dry_run(self, tool, inline_test_file):
        """Test dry run mode."""
        original_content = inline_test_file.read_text()

        result = await tool.execute(
            file=str(inline_test_file),
            variable="discount",
            dry_run=True
        )
        assert result.success
        assert "Would inline" in result.output

        # File should not be modified
        assert inline_test_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_inline_javascript_const(self, tool, temp_dir):
        """Test inlining a JavaScript const."""
        js_file = temp_dir / "inline_test.js"
        js_file.write_text("""function calculate(x) {
    const multiplier = 2;
    const result = x * multiplier;
    return result + multiplier;
}
""")
        result = await tool.execute(
            file=str(js_file),
            variable="multiplier"
        )
        assert result.success

        content = js_file.read_text()
        # multiplier should be inlined with value 2
        assert "* 2" in content or "* (2)" in content

    @pytest.mark.asyncio
    async def test_inline_variable_not_found(self, tool, inline_test_file):
        """Test error when variable is not found."""
        result = await tool.execute(
            file=str(inline_test_file),
            variable="nonexistent_variable"
        )
        assert not result.success
        assert "Could not find assignment" in result.error

    @pytest.mark.asyncio
    async def test_inline_no_usages(self, tool, temp_dir):
        """Test when variable has no usages to inline."""
        test_file = temp_dir / "no_usage.py"
        test_file.write_text("""def func():
    unused_var = 42
    return "nothing"
""")
        result = await tool.execute(
            file=str(test_file),
            variable="unused_var"
        )
        assert result.success
        assert "No usages" in result.output

    @pytest.mark.asyncio
    async def test_inline_invalid_variable_name(self, tool):
        """Test error for invalid variable name."""
        result = await tool.execute(
            file="/some/file.py",
            variable="123invalid"
        )
        assert not result.success
        assert "Invalid variable name" in result.error

    @pytest.mark.asyncio
    async def test_inline_file_not_found(self, tool):
        """Test error when file doesn't exist."""
        result = await tool.execute(
            file="/nonexistent/file.py",
            variable="test"
        )
        assert not result.success
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_inline_wraps_complex_expressions(self, tool, temp_dir):
        """Test that complex expressions are wrapped in parentheses."""
        test_file = temp_dir / "wrap_test.py"
        test_file.write_text("""def func():
    value = a + b
    result = value * 2
    return result
""")
        result = await tool.execute(
            file=str(test_file),
            variable="value"
        )
        assert result.success

        content = test_file.read_text()
        # Expression should be wrapped
        assert "(a + b)" in content

    @pytest.mark.asyncio
    async def test_inline_metadata(self, tool, inline_test_file):
        """Test that result includes proper metadata."""
        result = await tool.execute(
            file=str(inline_test_file),
            variable="discount"
        )
        assert result.success
        assert "variable" in result.metadata
        assert "value" in result.metadata
        assert "usages_replaced" in result.metadata

    @pytest.mark.asyncio
    async def test_inline_specific_line(self, tool, temp_dir):
        """Test inlining variable from specific line."""
        test_file = temp_dir / "specific_line.py"
        test_file.write_text("""def func():
    multiplier = 2
    result = value * multiplier
    return result + multiplier
""")
        # Inline the multiplier assignment (line 2)
        result = await tool.execute(
            file=str(test_file),
            variable="multiplier",
            line=2
        )
        assert result.success

        content = test_file.read_text()
        # multiplier should be inlined with value 2
        assert "* 2" in content or "* (2)" in content
        assert "+ 2" in content or "+ (2)" in content


# ============================================================
# Integration Tests
# ============================================================

class TestRefactoringToolsIntegration:
    """Integration tests for refactoring tools."""

    @pytest.mark.asyncio
    async def test_rename_and_extract_workflow(self, temp_dir):
        """Test combined rename and extract workflow."""
        # Create initial file
        test_file = temp_dir / "workflow.py"
        test_file.write_text("""def process_data(data):
    # Calculate sum
    total = 0
    for item in data:
        total = total + item
    # Calculate average
    avg = total / len(data)
    return avg
""")

        # First, extract the sum calculation
        extract_tool = ExtractFunctionTool(work_dir=temp_dir)
        result = await extract_tool.execute(
            file=str(test_file),
            start_line=3,
            end_line=5,
            function_name="calculate_sum",
            params=["data"],
            return_value="total"
        )
        assert result.success

        # Then rename it to something better
        rename_tool = RenameSymbolTool(work_dir=temp_dir)
        result = await rename_tool.execute(
            old_name="calculate_sum",
            new_name="sum_items",
            path=str(test_file)
        )
        assert result.success

        content = test_file.read_text()
        assert "def sum_items" in content

    @pytest.mark.asyncio
    async def test_tools_with_work_dir(self, temp_dir):
        """Test that tools work correctly with work_dir."""
        # Create file in subdirectory
        sub = temp_dir / "sub"
        sub.mkdir()
        (sub / "test.py").write_text("x = 1\nprint(x)")

        # Tool with work_dir set
        tool = RenameSymbolTool(work_dir=temp_dir)

        result = await tool.execute(
            old_name="x",
            new_name="value",
            path="sub/test.py"  # Relative path
        )
        assert result.success

        content = (sub / "test.py").read_text()
        assert "value = 1" in content


# ============================================================
# Registry Integration Tests
# ============================================================

class TestRefactoringToolsRegistry:
    """Test that refactoring tools are properly registered."""

    def test_tools_registered_in_default_registry(self):
        """Test that refactoring tools are in the default registry."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()

        assert registry.get_tool("rename_symbol") is not None
        assert registry.get_tool("extract_function") is not None
        assert registry.get_tool("inline_variable") is not None

    def test_tool_schemas_valid(self):
        """Test that tool schemas are valid."""
        rename_tool = RenameSymbolTool()
        extract_tool = ExtractFunctionTool()
        inline_tool = InlineVariableTool()

        for tool in [rename_tool, extract_tool, inline_tool]:
            schema = tool.get_schema()
            assert "type" in schema
            assert schema["type"] == "function"
            assert "function" in schema
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]
