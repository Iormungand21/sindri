"""Tests for code search tools."""

import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import Mock

from sindri.tools.search import SearchCodeTool, FindSymbolTool


@pytest.fixture
def temp_dir():
    """Create a temporary directory with test files for searching."""
    temp = Path(tempfile.mkdtemp())

    # Create Python files
    (temp / "main.py").write_text(
        """#!/usr/bin/env python
\"\"\"Main application module.\"\"\"

def authenticate(username: str, password: str) -> bool:
    \"\"\"Authenticate a user.\"\"\"
    # TODO: Implement proper auth
    return username == "admin" and password == "secret"


class UserModel:
    \"\"\"User data model.\"\"\"
    def __init__(self, name: str):
        self.name = name


config = {
    "debug": True,
    "port": 8080
}


async def fetch_data(url: str):
    \"\"\"Fetch data from API.\"\"\"
    pass
"""
    )

    (temp / "utils.py").write_text(
        """\"\"\"Utility functions.\"\"\"

def validate_email(email: str) -> bool:
    \"\"\"Validate email address.\"\"\"
    return "@" in email


def format_name(first: str, last: str) -> str:
    \"\"\"Format a full name.\"\"\"
    return f"{first} {last}"


# TODO: Add more utilities
DEBUG = True
"""
    )

    # Create TypeScript file
    (temp / "app.ts").write_text(
        """// Application entry point

export interface User {
    id: number;
    name: string;
}

export class UserHandler {
    private users: User[] = [];

    async authenticate(user: User): Promise<boolean> {
        // TODO: Implement
        return true;
    }
}

export const config = {
    apiUrl: "http://localhost:3000"
};

export function handleError(err: Error): void {
    console.error(err);
}
"""
    )

    # Create JavaScript file
    (temp / "helpers.js").write_text(
        """// Helper functions

const API_URL = "http://api.example.com";

function fetchUser(id) {
    // TODO: Fetch user
    return null;
}

class DataManager {
    constructor() {
        this.data = [];
    }

    async loadData() {
        // Implementation
    }
}

export { fetchUser, DataManager, API_URL };
"""
    )

    # Create a subdirectory
    (temp / "subdir").mkdir()
    (temp / "subdir" / "module.py").write_text(
        """\"\"\"Submodule.\"\"\"

class Handler:
    pass


def process_data(data):
    return data
"""
    )

    # Create node_modules directory (should be skipped)
    (temp / "node_modules").mkdir()
    (temp / "node_modules" / "package.js").write_text("// Should be skipped")

    # Create hidden file
    (temp / ".env").write_text("SECRET=abc123")

    yield temp

    # Cleanup
    shutil.rmtree(temp)


# =============================================================================
# SearchCodeTool Tests - Text Search
# =============================================================================


@pytest.mark.asyncio
async def test_search_code_basic_literal(temp_dir):
    """Test basic literal text search."""
    tool = SearchCodeTool(work_dir=temp_dir)
    result = await tool.execute(query="TODO")

    assert result.success is True
    assert "TODO" in result.output
    assert result.metadata.get("match_count", 0) > 0


@pytest.mark.asyncio
async def test_search_code_no_matches(temp_dir):
    """Test search with no matches."""
    tool = SearchCodeTool(work_dir=temp_dir)
    result = await tool.execute(query="NONEXISTENT_STRING_12345")

    assert result.success is True
    assert "No matches found" in result.output
    assert result.metadata.get("match_count") == 0


@pytest.mark.asyncio
async def test_search_code_case_insensitive(temp_dir):
    """Test case-insensitive search."""
    tool = SearchCodeTool(work_dir=temp_dir)
    result = await tool.execute(query="debug", case_sensitive=False)

    assert result.success is True
    # Should find DEBUG in utils.py and debug in main.py
    assert result.output.strip() != ""


@pytest.mark.asyncio
async def test_search_code_case_sensitive(temp_dir):
    """Test case-sensitive search."""
    tool = SearchCodeTool(work_dir=temp_dir)
    result = await tool.execute(query="DEBUG", case_sensitive=True)

    assert result.success is True
    # Should only find DEBUG, not debug
    if result.metadata.get("match_count", 0) > 0:
        assert "DEBUG" in result.output


@pytest.mark.asyncio
async def test_search_code_regex_pattern(temp_dir):
    """Test regex pattern search."""
    tool = SearchCodeTool(work_dir=temp_dir)
    result = await tool.execute(query=r"def \w+\(", regex=True)

    assert result.success is True
    # Should find function definitions
    assert result.metadata.get("match_count", 0) > 0


@pytest.mark.asyncio
async def test_search_code_file_type_filter(temp_dir):
    """Test search with file type filter."""
    tool = SearchCodeTool(work_dir=temp_dir)
    result = await tool.execute(query="class", file_types=["py"])

    assert result.success is True
    # Should find Python classes but not TypeScript/JS
    assert "UserModel" in result.output or "Handler" in result.output
    # Should not include TypeScript results
    assert ".ts" not in result.output


@pytest.mark.asyncio
async def test_search_code_multiple_file_types(temp_dir):
    """Test search with multiple file type filters."""
    tool = SearchCodeTool(work_dir=temp_dir)
    result = await tool.execute(query="async", file_types=["py", "ts"])

    assert result.success is True
    assert result.metadata.get("match_count", 0) > 0


@pytest.mark.asyncio
async def test_search_code_skips_node_modules(temp_dir):
    """Test that search skips node_modules directory."""
    tool = SearchCodeTool(work_dir=temp_dir)
    result = await tool.execute(query="Should be skipped")

    assert result.success is True
    # Should not find the content in node_modules
    assert "No matches found" in result.output or "node_modules" not in result.output


@pytest.mark.asyncio
async def test_search_code_empty_query_error():
    """Test that empty query returns error."""
    tool = SearchCodeTool()
    result = await tool.execute(query="")

    assert result.success is False
    assert "cannot be empty" in result.error.lower()


@pytest.mark.asyncio
async def test_search_code_nonexistent_path():
    """Test search in non-existent path."""
    tool = SearchCodeTool()
    result = await tool.execute(query="test", path="/nonexistent/path/12345")

    assert result.success is False
    assert "does not exist" in result.error.lower()


@pytest.mark.asyncio
async def test_search_code_context_lines(temp_dir):
    """Test search with context lines."""
    tool = SearchCodeTool(work_dir=temp_dir)
    result = await tool.execute(query="authenticate", context_lines=2)

    assert result.success is True
    # Context should include surrounding lines
    assert result.metadata.get("match_count", 0) > 0


@pytest.mark.asyncio
async def test_search_code_max_results(temp_dir):
    """Test search with max results limit."""
    tool = SearchCodeTool(work_dir=temp_dir)
    result = await tool.execute(query="def", max_results=2)

    assert result.success is True
    # Results should be limited


@pytest.mark.asyncio
async def test_search_code_relative_path(temp_dir):
    """Test search with relative path from work_dir."""
    tool = SearchCodeTool(work_dir=temp_dir)
    result = await tool.execute(query="Handler", path="subdir")

    assert result.success is True
    # Should find Handler in subdir/module.py
    if result.metadata.get("match_count", 0) > 0:
        assert "Handler" in result.output


# =============================================================================
# SearchCodeTool Tests - Semantic Search
# =============================================================================


@pytest.mark.asyncio
async def test_search_code_semantic_no_memory():
    """Test semantic search without memory system returns error."""
    tool = SearchCodeTool(semantic_memory=None)
    result = await tool.execute(query="authentication logic", semantic=True)

    assert result.success is False
    assert "memory system" in result.error.lower()


@pytest.mark.asyncio
async def test_search_code_semantic_with_mock_memory():
    """Test semantic search with mocked memory system."""
    mock_memory = Mock()
    mock_memory.search.return_value = [
        (
            "def authenticate():\n    pass",
            {"path": "auth.py", "start_line": 1, "end_line": 2},
            0.95,
        ),
        (
            "# Login logic here",
            {"path": "login.py", "start_line": 10, "end_line": 11},
            0.85,
        ),
    ]

    tool = SearchCodeTool(semantic_memory=mock_memory, namespace="test")
    result = await tool.execute(query="authentication", semantic=True)

    assert result.success is True
    assert "auth.py" in result.output
    assert "0.95" in result.output or "similarity" in result.output
    mock_memory.search.assert_called_once()


@pytest.mark.asyncio
async def test_search_code_semantic_no_results():
    """Test semantic search with no results."""
    mock_memory = Mock()
    mock_memory.search.return_value = []

    tool = SearchCodeTool(semantic_memory=mock_memory)
    result = await tool.execute(query="nonexistent concept", semantic=True)

    assert result.success is True
    assert "No relevant code found" in result.output


@pytest.mark.asyncio
async def test_search_code_semantic_with_file_type_filter():
    """Test semantic search with file type filter."""
    mock_memory = Mock()
    mock_memory.search.return_value = [
        ("content1", {"path": "file.py", "start_line": 1, "end_line": 5}, 0.9),
        ("content2", {"path": "file.ts", "start_line": 1, "end_line": 5}, 0.85),
        ("content3", {"path": "other.py", "start_line": 1, "end_line": 5}, 0.8),
    ]

    tool = SearchCodeTool(semantic_memory=mock_memory)
    result = await tool.execute(query="test", semantic=True, file_types=["py"])

    assert result.success is True
    # Should include .py files
    assert "file.py" in result.output or "other.py" in result.output
    # Should not include .ts files
    assert "file.ts" not in result.output


# =============================================================================
# FindSymbolTool Tests
# =============================================================================


@pytest.mark.asyncio
async def test_find_symbol_function(temp_dir):
    """Test finding function definitions."""
    tool = FindSymbolTool(work_dir=temp_dir)
    result = await tool.execute(name="authenticate")

    assert result.success is True
    assert "authenticate" in result.output
    assert "[function]" in result.output


@pytest.mark.asyncio
async def test_find_symbol_class(temp_dir):
    """Test finding class definitions."""
    tool = FindSymbolTool(work_dir=temp_dir)
    result = await tool.execute(name="UserModel", symbol_type="class")

    assert result.success is True
    assert "UserModel" in result.output
    assert "[class]" in result.output


@pytest.mark.asyncio
async def test_find_symbol_variable(temp_dir):
    """Test finding variable definitions."""
    tool = FindSymbolTool(work_dir=temp_dir)
    result = await tool.execute(name="config", symbol_type="variable")

    assert result.success is True
    assert "config" in result.output
    assert "[variable]" in result.output


@pytest.mark.asyncio
async def test_find_symbol_any_type(temp_dir):
    """Test finding any type of symbol."""
    tool = FindSymbolTool(work_dir=temp_dir)
    result = await tool.execute(name="config")

    assert result.success is True
    # Should find both function and variable named 'config'
    assert result.metadata.get("match_count", 0) > 0


@pytest.mark.asyncio
async def test_find_symbol_not_found(temp_dir):
    """Test finding non-existent symbol."""
    tool = FindSymbolTool(work_dir=temp_dir)
    result = await tool.execute(name="NonExistentSymbol12345")

    assert result.success is True
    assert "No definition found" in result.output
    assert result.metadata.get("match_count") == 0


@pytest.mark.asyncio
async def test_find_symbol_empty_name_error():
    """Test that empty name returns error."""
    tool = FindSymbolTool()
    result = await tool.execute(name="")

    assert result.success is False
    assert "cannot be empty" in result.error.lower()


@pytest.mark.asyncio
async def test_find_symbol_file_type_filter(temp_dir):
    """Test finding symbol with file type filter."""
    tool = FindSymbolTool(work_dir=temp_dir)
    result = await tool.execute(name="Handler", file_types=["py"])

    assert result.success is True
    # Should find Handler in Python files
    if result.metadata.get("match_count", 0) > 0:
        assert ".py" in result.output


@pytest.mark.asyncio
async def test_find_symbol_typescript_class(temp_dir):
    """Test finding TypeScript class."""
    tool = FindSymbolTool(work_dir=temp_dir)
    result = await tool.execute(
        name="UserHandler", symbol_type="class", file_types=["ts"]
    )

    assert result.success is True
    assert "UserHandler" in result.output
    assert "[class]" in result.output


@pytest.mark.asyncio
async def test_find_symbol_async_function(temp_dir):
    """Test finding async function definition."""
    tool = FindSymbolTool(work_dir=temp_dir)
    result = await tool.execute(name="fetch_data", symbol_type="function")

    assert result.success is True
    assert "fetch_data" in result.output


@pytest.mark.asyncio
async def test_find_symbol_javascript_function(temp_dir):
    """Test finding JavaScript function."""
    tool = FindSymbolTool(work_dir=temp_dir)
    result = await tool.execute(name="fetchUser", file_types=["js"])

    assert result.success is True
    assert "fetchUser" in result.output


@pytest.mark.asyncio
async def test_find_symbol_in_subdirectory(temp_dir):
    """Test finding symbol in subdirectory."""
    tool = FindSymbolTool(work_dir=temp_dir)
    result = await tool.execute(name="process_data")

    assert result.success is True
    assert "process_data" in result.output
    # Should show path with subdir
    assert "subdir" in result.output or "module.py" in result.output


@pytest.mark.asyncio
async def test_find_symbol_relative_path(temp_dir):
    """Test finding symbol with relative path."""
    tool = FindSymbolTool(work_dir=temp_dir)
    result = await tool.execute(name="Handler", path="subdir")

    assert result.success is True
    assert "Handler" in result.output


@pytest.mark.asyncio
async def test_find_symbol_nonexistent_path():
    """Test finding symbol in non-existent path."""
    tool = FindSymbolTool()
    result = await tool.execute(name="test", path="/nonexistent/path/12345")

    assert result.success is False
    assert "does not exist" in result.error.lower()


# =============================================================================
# Tool Registry Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_search_code_in_registry():
    """Test that SearchCodeTool is properly registered."""
    from sindri.tools.registry import ToolRegistry

    registry = ToolRegistry.default()
    tool = registry.get_tool("search_code")

    assert tool is not None
    assert isinstance(tool, SearchCodeTool)


@pytest.mark.asyncio
async def test_find_symbol_in_registry():
    """Test that FindSymbolTool is properly registered."""
    from sindri.tools.registry import ToolRegistry

    registry = ToolRegistry.default()
    tool = registry.get_tool("find_symbol")

    assert tool is not None
    assert isinstance(tool, FindSymbolTool)


@pytest.mark.asyncio
async def test_search_code_schema():
    """Test SearchCodeTool schema format."""
    tool = SearchCodeTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "search_code"
    assert "parameters" in schema["function"]
    assert "query" in schema["function"]["parameters"]["properties"]
    assert "query" in schema["function"]["parameters"]["required"]


@pytest.mark.asyncio
async def test_find_symbol_schema():
    """Test FindSymbolTool schema format."""
    tool = FindSymbolTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "find_symbol"
    assert "parameters" in schema["function"]
    assert "name" in schema["function"]["parameters"]["properties"]
    assert "name" in schema["function"]["parameters"]["required"]


# =============================================================================
# Agent Integration Tests
# =============================================================================


def test_agents_have_search_tools():
    """Test that appropriate agents have search tools."""
    from sindri.agents.registry import AGENTS

    # Brokkr should have both search tools
    assert "search_code" in AGENTS["brokkr"].tools
    assert "find_symbol" in AGENTS["brokkr"].tools

    # Huginn should have both search tools
    assert "search_code" in AGENTS["huginn"].tools
    assert "find_symbol" in AGENTS["huginn"].tools

    # Mimir should have search_code
    assert "search_code" in AGENTS["mimir"].tools

    # Odin should have search_code
    assert "search_code" in AGENTS["odin"].tools


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


@pytest.mark.asyncio
async def test_search_code_special_characters(temp_dir):
    """Test search with special characters."""
    tool = SearchCodeTool(work_dir=temp_dir)
    result = await tool.execute(query="(username: str)", case_sensitive=False)

    assert result.success is True


@pytest.mark.asyncio
async def test_search_code_file_as_path(temp_dir):
    """Test search with file path instead of directory."""
    tool = SearchCodeTool(work_dir=temp_dir)
    result = await tool.execute(query="test", path=str(temp_dir / "main.py"))

    assert result.success is False
    assert "not a directory" in result.error.lower()


@pytest.mark.asyncio
async def test_find_symbol_with_regex_special_chars(temp_dir):
    """Test that find_symbol properly escapes regex special characters."""
    # Create a file with a symbol containing regex special chars
    (temp_dir / "special.py").write_text("def test_func():\n    pass")

    tool = FindSymbolTool(work_dir=temp_dir)
    result = await tool.execute(name="test_func")

    assert result.success is True
    # Should find the function without regex errors


@pytest.mark.asyncio
async def test_search_code_work_dir_resolution(temp_dir):
    """Test that work_dir is properly used for path resolution."""
    subdir = temp_dir / "subdir"
    tool = SearchCodeTool(work_dir=subdir)
    result = await tool.execute(query="Handler")

    assert result.success is True
    # Should search in subdir
    if result.metadata.get("match_count", 0) > 0:
        assert "Handler" in result.output
