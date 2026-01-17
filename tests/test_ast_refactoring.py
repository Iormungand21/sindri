"""Tests for AST-based refactoring tools."""

import json
import pytest

from sindri.tools.ast_refactoring import (
    ASTParserTool,
    FindReferencesTool,
    ASTSymbolInfoTool,
    ASTRefactorRenameTool,
    TREE_SITTER_AVAILABLE,
    _get_parser,
    _node_to_dict,
    _find_identifiers,
)


# Skip all tests if tree-sitter is not available
pytestmark = pytest.mark.skipif(
    not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed"
)


class TestParserCreation:
    """Tests for parser creation helper."""

    def test_get_python_parser(self):
        """Test creating Python parser."""
        parser = _get_parser(".py")
        assert parser is not None

    def test_get_javascript_parser(self):
        """Test creating JavaScript parser."""
        parser = _get_parser(".js")
        assert parser is not None

    def test_get_typescript_parser(self):
        """Test creating TypeScript parser."""
        parser = _get_parser(".ts")
        assert parser is not None

    def test_get_rust_parser(self):
        """Test creating Rust parser."""
        parser = _get_parser(".rs")
        assert parser is not None

    def test_get_go_parser(self):
        """Test creating Go parser."""
        parser = _get_parser(".go")
        assert parser is not None

    def test_unsupported_extension(self):
        """Test unsupported file extension returns None."""
        parser = _get_parser(".xyz")
        assert parser is None

    def test_pyi_uses_python_parser(self):
        """Test .pyi uses Python parser."""
        parser = _get_parser(".pyi")
        assert parser is not None

    def test_jsx_uses_javascript_parser(self):
        """Test .jsx uses JavaScript parser."""
        parser = _get_parser(".jsx")
        assert parser is not None

    def test_tsx_uses_typescript_parser(self):
        """Test .tsx uses TypeScript parser."""
        parser = _get_parser(".tsx")
        assert parser is not None


class TestASTParserTool:
    """Tests for the ASTParserTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create an ASTParserTool instance."""
        return ASTParserTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_parse_python_file(self, tool, tmp_path):
        """Test parsing a Python file."""
        python_file = tmp_path / "test.py"
        python_file.write_text(
            """
def hello(name: str) -> str:
    '''Say hello.'''
    return f"Hello, {name}!"
"""
        )

        result = await tool.execute(file_path=str(python_file))
        assert result.success
        assert "module" in result.output
        assert result.metadata["language"] == "python"

    @pytest.mark.asyncio
    async def test_parse_javascript_file(self, tool, tmp_path):
        """Test parsing a JavaScript file."""
        js_file = tmp_path / "test.js"
        js_file.write_text(
            """
function greet(name) {
    return "Hello, " + name;
}
"""
        )

        result = await tool.execute(file_path=str(js_file))
        assert result.success
        assert "program" in result.output
        assert result.metadata["language"] == "javascript"

    @pytest.mark.asyncio
    async def test_parse_typescript_file(self, tool, tmp_path):
        """Test parsing a TypeScript file."""
        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
interface User {
    name: string;
    age: number;
}

function greet(user: User): string {
    return `Hello, ${user.name}!`;
}
"""
        )

        result = await tool.execute(file_path=str(ts_file))
        assert result.success
        assert "program" in result.output
        assert result.metadata["language"] == "typescript"

    @pytest.mark.asyncio
    async def test_parse_rust_file(self, tool, tmp_path):
        """Test parsing a Rust file."""
        rs_file = tmp_path / "test.rs"
        rs_file.write_text(
            """
fn hello(name: &str) -> String {
    format!("Hello, {}!", name)
}
"""
        )

        result = await tool.execute(file_path=str(rs_file))
        assert result.success
        assert "source_file" in result.output
        assert result.metadata["language"] == "rust"

    @pytest.mark.asyncio
    async def test_parse_go_file(self, tool, tmp_path):
        """Test parsing a Go file."""
        go_file = tmp_path / "test.go"
        go_file.write_text(
            """
package main

func hello(name string) string {
    return "Hello, " + name
}
"""
        )

        result = await tool.execute(file_path=str(go_file))
        assert result.success
        assert "source_file" in result.output
        assert result.metadata["language"] == "go"

    @pytest.mark.asyncio
    async def test_parse_nonexistent_file(self, tool, tmp_path):
        """Test parsing a nonexistent file."""
        result = await tool.execute(file_path=str(tmp_path / "nonexistent.py"))
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_parse_unsupported_file_type(self, tool, tmp_path):
        """Test parsing an unsupported file type."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello, world!")

        result = await tool.execute(file_path=str(txt_file))
        assert not result.success
        assert "unsupported" in result.error.lower()

    @pytest.mark.asyncio
    async def test_parse_without_positions(self, tool, tmp_path):
        """Test parsing without position info."""
        python_file = tmp_path / "test.py"
        python_file.write_text("x = 1")

        result = await tool.execute(
            file_path=str(python_file), include_positions=False
        )
        assert result.success
        # Should not have start/end keys in output
        parsed = json.loads(result.output)
        assert "start" not in parsed

    @pytest.mark.asyncio
    async def test_parse_with_positions(self, tool, tmp_path):
        """Test parsing with position info (default)."""
        python_file = tmp_path / "test.py"
        python_file.write_text("x = 1")

        result = await tool.execute(file_path=str(python_file))
        assert result.success
        parsed = json.loads(result.output)
        assert "start" in parsed
        assert "end" in parsed


class TestFindReferencesTool:
    """Tests for the FindReferencesTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a FindReferencesTool instance."""
        return FindReferencesTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_find_references_in_python(self, tool, tmp_path):
        """Test finding references in Python code."""
        python_file = tmp_path / "test.py"
        python_file.write_text(
            """
def calculate(x):
    return x * 2

result = calculate(5)
print(calculate(10))
"""
        )

        result = await tool.execute(symbol_name="calculate", path=str(tmp_path))
        assert result.success
        assert result.metadata["count"] == 3  # definition + 2 calls
        assert "calculate" in result.output

    @pytest.mark.asyncio
    async def test_find_references_in_javascript(self, tool, tmp_path):
        """Test finding references in JavaScript code."""
        js_file = tmp_path / "test.js"
        js_file.write_text(
            """
function greet(name) {
    return "Hello, " + name;
}

const message = greet("World");
console.log(greet("User"));
"""
        )

        result = await tool.execute(symbol_name="greet", path=str(tmp_path))
        assert result.success
        assert result.metadata["count"] >= 3  # definition + 2 calls

    @pytest.mark.asyncio
    async def test_find_no_references(self, tool, tmp_path):
        """Test when no references are found."""
        python_file = tmp_path / "test.py"
        python_file.write_text("x = 1\ny = 2\n")

        result = await tool.execute(symbol_name="nonexistent", path=str(tmp_path))
        assert result.success
        assert result.metadata["count"] == 0
        assert "no references" in result.output.lower()

    @pytest.mark.asyncio
    async def test_find_references_with_file_types(self, tool, tmp_path):
        """Test filtering by file types."""
        py_file = tmp_path / "test.py"
        py_file.write_text("value = 1")

        js_file = tmp_path / "test.js"
        js_file.write_text("const value = 1;")

        # Search only Python
        result = await tool.execute(
            symbol_name="value", path=str(tmp_path), file_types=["py"]
        )
        assert result.success
        assert result.metadata["count"] == 1

    @pytest.mark.asyncio
    async def test_find_references_in_single_file(self, tool, tmp_path):
        """Test finding references in a single file."""
        python_file = tmp_path / "test.py"
        python_file.write_text(
            """
x = 1
y = x + 1
z = x * 2
"""
        )

        result = await tool.execute(symbol_name="x", path=str(python_file))
        assert result.success
        assert result.metadata["count"] == 3  # definition + 2 usages

    @pytest.mark.asyncio
    async def test_find_references_empty_symbol(self, tool, tmp_path):
        """Test with empty symbol name."""
        result = await tool.execute(symbol_name="", path=str(tmp_path))
        assert not result.success
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_find_references_nonexistent_path(self, tool, tmp_path):
        """Test with nonexistent path."""
        result = await tool.execute(
            symbol_name="test", path=str(tmp_path / "nonexistent")
        )
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_find_references_skips_excluded_dirs(self, tool, tmp_path):
        """Test that excluded directories are skipped."""
        # Create file in node_modules (should be skipped)
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        (node_modules / "test.js").write_text("const value = 1;")

        # Create file in regular directory
        src = tmp_path / "src"
        src.mkdir()
        (src / "test.js").write_text("const value = 1;")

        result = await tool.execute(symbol_name="value", path=str(tmp_path))
        assert result.success
        assert result.metadata["count"] == 1  # Only from src


class TestASTSymbolInfoTool:
    """Tests for the ASTSymbolInfoTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create an ASTSymbolInfoTool instance."""
        return ASTSymbolInfoTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_symbol_info_python_function(self, tool, tmp_path):
        """Test getting info for a Python function."""
        python_file = tmp_path / "test.py"
        python_file.write_text(
            '''
def calculate(x: int, y: int) -> int:
    """Calculate the sum of two numbers."""
    return x + y
'''
        )

        result = await tool.execute(file_path=str(python_file), symbol_name="calculate")
        assert result.success
        assert result.metadata["found"]
        info = result.metadata["info"]
        assert info["type"] == "function_definition"
        assert info["name"] == "calculate"
        assert "parameters" in info
        assert len(info["parameters"]) == 2
        assert info["docstring"] == "Calculate the sum of two numbers."

    @pytest.mark.asyncio
    async def test_symbol_info_python_class(self, tool, tmp_path):
        """Test getting info for a Python class."""
        python_file = tmp_path / "test.py"
        python_file.write_text(
            '''
class MyClass:
    """A simple class."""
    pass
'''
        )

        result = await tool.execute(file_path=str(python_file), symbol_name="MyClass")
        assert result.success
        assert result.metadata["found"]
        info = result.metadata["info"]
        assert info["type"] == "class_definition"
        assert info["name"] == "MyClass"

    @pytest.mark.asyncio
    async def test_symbol_info_python_variable(self, tool, tmp_path):
        """Test getting info for a Python variable."""
        python_file = tmp_path / "test.py"
        python_file.write_text("MAX_VALUE = 100\n")

        result = await tool.execute(file_path=str(python_file), symbol_name="MAX_VALUE")
        assert result.success
        assert result.metadata["found"]
        info = result.metadata["info"]
        assert info["type"] == "assignment"

    @pytest.mark.asyncio
    async def test_symbol_info_not_found(self, tool, tmp_path):
        """Test when symbol is not found."""
        python_file = tmp_path / "test.py"
        python_file.write_text("x = 1\n")

        result = await tool.execute(
            file_path=str(python_file), symbol_name="nonexistent"
        )
        assert result.success
        assert not result.metadata["found"]
        assert "not found" in result.output.lower()

    @pytest.mark.asyncio
    async def test_symbol_info_javascript_function(self, tool, tmp_path):
        """Test getting info for a JavaScript function."""
        js_file = tmp_path / "test.js"
        js_file.write_text(
            """
function greet(name) {
    return "Hello, " + name;
}
"""
        )

        result = await tool.execute(file_path=str(js_file), symbol_name="greet")
        assert result.success
        assert result.metadata["found"]
        info = result.metadata["info"]
        assert info["type"] == "function_declaration"

    @pytest.mark.asyncio
    async def test_symbol_info_typescript_interface(self, tool, tmp_path):
        """Test getting info for a TypeScript interface."""
        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
interface User {
    name: string;
    age: number;
}
"""
        )

        result = await tool.execute(file_path=str(ts_file), symbol_name="User")
        assert result.success
        assert result.metadata["found"]
        info = result.metadata["info"]
        assert info["type"] == "interface_declaration"

    @pytest.mark.asyncio
    async def test_symbol_info_rust_function(self, tool, tmp_path):
        """Test getting info for a Rust function."""
        rs_file = tmp_path / "test.rs"
        rs_file.write_text(
            """
fn calculate(x: i32, y: i32) -> i32 {
    x + y
}
"""
        )

        result = await tool.execute(file_path=str(rs_file), symbol_name="calculate")
        assert result.success
        assert result.metadata["found"]
        info = result.metadata["info"]
        assert info["type"] == "function_item"

    @pytest.mark.asyncio
    async def test_symbol_info_go_function(self, tool, tmp_path):
        """Test getting info for a Go function."""
        go_file = tmp_path / "test.go"
        go_file.write_text(
            """
package main

func calculate(x int, y int) int {
    return x + y
}
"""
        )

        result = await tool.execute(file_path=str(go_file), symbol_name="calculate")
        assert result.success
        assert result.metadata["found"]
        info = result.metadata["info"]
        assert info["type"] == "function_declaration"

    @pytest.mark.asyncio
    async def test_symbol_info_nonexistent_file(self, tool, tmp_path):
        """Test with nonexistent file."""
        result = await tool.execute(
            file_path=str(tmp_path / "nonexistent.py"), symbol_name="test"
        )
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_symbol_info_unsupported_file(self, tool, tmp_path):
        """Test with unsupported file type."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("test")

        result = await tool.execute(file_path=str(txt_file), symbol_name="test")
        assert not result.success
        assert "unsupported" in result.error.lower()


class TestASTRefactorRenameTool:
    """Tests for the ASTRefactorRenameTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create an ASTRefactorRenameTool instance."""
        return ASTRefactorRenameTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_rename_python_function(self, tool, tmp_path):
        """Test renaming a Python function."""
        python_file = tmp_path / "test.py"
        python_file.write_text(
            """
def old_func(x):
    return x * 2

result = old_func(5)
"""
        )

        result = await tool.execute(old_name="old_func", new_name="new_func")
        assert result.success
        assert result.metadata["occurrences"] == 2
        assert result.metadata["files_modified"] == 1

        # Verify the file was modified
        content = python_file.read_text()
        assert "new_func" in content
        assert "old_func" not in content

    @pytest.mark.asyncio
    async def test_rename_dry_run(self, tool, tmp_path):
        """Test rename with dry run."""
        python_file = tmp_path / "test.py"
        original_content = """
def old_func(x):
    return x * 2

result = old_func(5)
"""
        python_file.write_text(original_content)

        result = await tool.execute(
            old_name="old_func", new_name="new_func", dry_run=True
        )
        assert result.success
        assert result.metadata["dry_run"]
        assert result.metadata["occurrences"] == 2

        # Verify the file was NOT modified
        content = python_file.read_text()
        assert content == original_content

    @pytest.mark.asyncio
    async def test_rename_across_multiple_files(self, tool, tmp_path):
        """Test renaming across multiple files."""
        file1 = tmp_path / "module1.py"
        file1.write_text("def helper(): pass\n")

        file2 = tmp_path / "module2.py"
        file2.write_text("from module1 import helper\nhelper()\n")

        result = await tool.execute(old_name="helper", new_name="utility")
        assert result.success
        assert result.metadata["occurrences"] >= 2
        assert result.metadata["files_modified"] == 2

        # Verify both files were modified
        assert "utility" in file1.read_text()
        assert "utility" in file2.read_text()

    @pytest.mark.asyncio
    async def test_rename_in_specific_directory(self, tool, tmp_path):
        """Test renaming in a specific directory."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        other_dir = tmp_path / "other"
        other_dir.mkdir()

        src_file = src_dir / "test.py"
        src_file.write_text("value = 1\n")

        other_file = other_dir / "test.py"
        other_file.write_text("value = 1\n")

        result = await tool.execute(
            old_name="value", new_name="data", path=str(src_dir)
        )
        assert result.success
        assert result.metadata["files_modified"] == 1

        # Only src file should be modified
        assert "data" in src_file.read_text()
        assert "value" in other_file.read_text()

    @pytest.mark.asyncio
    async def test_rename_with_file_types(self, tool, tmp_path):
        """Test renaming with file type filter."""
        py_file = tmp_path / "test.py"
        py_file.write_text("value = 1\n")

        js_file = tmp_path / "test.js"
        js_file.write_text("const value = 1;\n")

        result = await tool.execute(
            old_name="value", new_name="data", file_types=["py"]
        )
        assert result.success
        assert result.metadata["files_modified"] == 1

        # Only Python file should be modified
        assert "data" in py_file.read_text()
        assert "value" in js_file.read_text()

    @pytest.mark.asyncio
    async def test_rename_no_occurrences(self, tool, tmp_path):
        """Test when no occurrences are found."""
        python_file = tmp_path / "test.py"
        python_file.write_text("x = 1\n")

        result = await tool.execute(old_name="nonexistent", new_name="new_name")
        assert result.success
        assert result.metadata["occurrences"] == 0
        assert "no references" in result.output.lower()

    @pytest.mark.asyncio
    async def test_rename_empty_old_name(self, tool, tmp_path):
        """Test with empty old_name."""
        result = await tool.execute(old_name="", new_name="new_name")
        assert not result.success
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_rename_empty_new_name(self, tool, tmp_path):
        """Test with empty new_name."""
        result = await tool.execute(old_name="old_name", new_name="")
        assert not result.success
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_rename_same_name(self, tool, tmp_path):
        """Test with same old and new name."""
        result = await tool.execute(old_name="same", new_name="same")
        assert not result.success
        assert "same" in result.error.lower()

    @pytest.mark.asyncio
    async def test_rename_nonexistent_path(self, tool, tmp_path):
        """Test with nonexistent path."""
        result = await tool.execute(
            old_name="old", new_name="new", path=str(tmp_path / "nonexistent")
        )
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_rename_javascript(self, tool, tmp_path):
        """Test renaming in JavaScript code."""
        js_file = tmp_path / "test.js"
        js_file.write_text(
            """
function oldName() {}
const result = oldName();
"""
        )

        result = await tool.execute(old_name="oldName", new_name="newName")
        assert result.success
        assert result.metadata["occurrences"] == 2

        content = js_file.read_text()
        assert "newName" in content
        assert "oldName" not in content

    @pytest.mark.asyncio
    async def test_rename_typescript(self, tool, tmp_path):
        """Test renaming in TypeScript code."""
        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
interface OldInterface {
    name: string;
}

const obj: OldInterface = { name: "test" };
"""
        )

        result = await tool.execute(old_name="OldInterface", new_name="NewInterface")
        assert result.success
        assert result.metadata["occurrences"] == 2

        content = ts_file.read_text()
        assert "NewInterface" in content
        assert "OldInterface" not in content


class TestNodeToDictHelper:
    """Tests for the _node_to_dict helper function."""

    def test_node_to_dict_with_positions(self):
        """Test converting node to dict with positions."""
        parser = _get_parser(".py")
        tree = parser.parse(b"x = 1")
        result = _node_to_dict(tree.root_node, include_positions=True)

        assert "type" in result
        assert "start" in result
        assert "end" in result
        assert result["start"]["line"] == 1

    def test_node_to_dict_without_positions(self):
        """Test converting node to dict without positions."""
        parser = _get_parser(".py")
        tree = parser.parse(b"x = 1")
        result = _node_to_dict(tree.root_node, include_positions=False)

        assert "type" in result
        assert "start" not in result
        assert "end" not in result


class TestFindIdentifiersHelper:
    """Tests for the _find_identifiers helper function."""

    def test_find_identifiers_single(self):
        """Test finding a single identifier."""
        parser = _get_parser(".py")
        tree = parser.parse(b"x = 1")
        results = []
        _find_identifiers(tree.root_node, "x", results)

        assert len(results) == 1
        assert results[0]["line"] == 1

    def test_find_identifiers_multiple(self):
        """Test finding multiple identifiers."""
        parser = _get_parser(".py")
        tree = parser.parse(b"x = 1\ny = x + x")
        results = []
        _find_identifiers(tree.root_node, "x", results)

        assert len(results) == 3

    def test_find_identifiers_none(self):
        """Test when identifier is not found."""
        parser = _get_parser(".py")
        tree = parser.parse(b"x = 1")
        results = []
        _find_identifiers(tree.root_node, "y", results)

        assert len(results) == 0


class TestToolRegistration:
    """Tests for tool registration in the registry."""

    def test_tools_registered(self):
        """Test that AST tools are registered in the default registry."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()

        assert registry.get_tool("parse_ast") is not None
        assert registry.get_tool("find_references") is not None
        assert registry.get_tool("symbol_info") is not None
        assert registry.get_tool("ast_rename") is not None

    def test_tool_schemas_valid(self):
        """Test that tool schemas are valid."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()
        schemas = registry.get_schemas()

        # Find AST tool schemas
        ast_tool_names = {"parse_ast", "find_references", "symbol_info", "ast_rename"}
        ast_schemas = [s for s in schemas if s["function"]["name"] in ast_tool_names]

        assert len(ast_schemas) == 4

        for schema in ast_schemas:
            assert "function" in schema
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]
