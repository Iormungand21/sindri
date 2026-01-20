"""AI-powered test generation tools for Sindri.

Phase 13: Provides tools for generating unit tests, suggesting test cases,
creating test fixtures, and generating property-based tests.

Tools:
- SuggestTestCasesTool: Analyze code and suggest test scenarios
- GenerateUnitTestsTool: Generate unit test scaffolding
- GenerateTestFixturesTool: Generate pytest fixtures and mocks
- GeneratePropertyTestsTool: Generate hypothesis property-based tests
"""

import importlib.util
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import aiofiles
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()

# Check for tree-sitter availability
TREE_SITTER_AVAILABLE = importlib.util.find_spec("tree_sitter") is not None

if TYPE_CHECKING:
    from tree_sitter import Node, Parser

# ═══════════════════════════════════════════════════════════════════════════════
# Language Configuration (reused from ast_refactoring.py patterns)
# ═══════════════════════════════════════════════════════════════════════════════

LANGUAGE_CONFIG: dict[str, tuple[str, str]] = {
    ".py": ("tree_sitter_python", "language"),
    ".pyi": ("tree_sitter_python", "language"),
    ".js": ("tree_sitter_javascript", "language"),
    ".jsx": ("tree_sitter_javascript", "language"),
    ".ts": ("tree_sitter_typescript", "language_typescript"),
    ".tsx": ("tree_sitter_typescript", "language_tsx"),
}

EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}

# Test framework detection files
FRAMEWORK_MARKERS: dict[str, list[str]] = {
    "pytest": ["conftest.py", "pytest.ini", "pyproject.toml"],
    "unittest": ["test_*.py"],
    "jest": ["jest.config.js", "jest.config.ts", "package.json"],
    "vitest": ["vitest.config.js", "vitest.config.ts"],
}

# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ParameterInfo:
    """Information about a function parameter."""

    name: str
    type_hint: Optional[str] = None
    default: Optional[str] = None
    is_optional: bool = False


@dataclass
class FunctionInfo:
    """Extracted function information."""

    name: str
    parameters: list[ParameterInfo] = field(default_factory=list)
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    is_async: bool = False
    decorators: list[str] = field(default_factory=list)
    line_number: int = 0


@dataclass
class ClassInfo:
    """Extracted class information."""

    name: str
    methods: list[FunctionInfo] = field(default_factory=list)
    base_classes: list[str] = field(default_factory=list)
    docstring: Optional[str] = None
    init_params: list[ParameterInfo] = field(default_factory=list)
    line_number: int = 0


@dataclass
class SuggestedTestCase:
    """A suggested test case."""

    description: str
    category: str  # "basic", "edge_case", "error_case", "boundary"
    target: str  # function/class name
    priority: str = "medium"  # "high", "medium", "low"


# ═══════════════════════════════════════════════════════════════════════════════
# Test Suggestion Rules
# ═══════════════════════════════════════════════════════════════════════════════

PARAM_SUGGESTIONS: dict[str, list[str]] = {
    "str": [
        "Test with empty string",
        "Test with whitespace only",
        "Test with unicode characters",
        "Test with very long string (1000+ chars)",
    ],
    "int": [
        "Test with zero",
        "Test with negative number",
        "Test with positive number",
        "Test with boundary values (MAX_INT, MIN_INT)",
    ],
    "float": [
        "Test with zero",
        "Test with negative number",
        "Test with positive number",
        "Test with very small number (1e-10)",
        "Test with very large number (1e10)",
    ],
    "list": [
        "Test with empty list",
        "Test with single element",
        "Test with many elements",
        "Test with nested lists",
    ],
    "dict": [
        "Test with empty dict",
        "Test with single key-value",
        "Test with many keys",
        "Test with nested dicts",
    ],
    "bool": [
        "Test with True",
        "Test with False",
    ],
    "Optional": [
        "Test with None value",
        "Test with non-None value",
    ],
    "Path": [
        "Test with existing path",
        "Test with non-existent path",
        "Test with directory path",
        "Test with file path",
    ],
}

RETURN_TYPE_SUGGESTIONS: dict[str, list[str]] = {
    "bool": ["Verify True return case", "Verify False return case"],
    "list": ["Verify empty list case", "Verify non-empty list case"],
    "dict": ["Verify returned dict structure", "Verify key presence"],
    "Optional": ["Verify None return case", "Verify non-None return case"],
    "int": ["Verify expected integer value", "Verify value range"],
    "str": ["Verify expected string value", "Verify string format"],
}

PATTERN_SUGGESTIONS: dict[str, list[str]] = {
    "file_operation": [
        "Test file not found error",
        "Test permission denied error",
        "Test empty file",
    ],
    "network_call": [
        "Test timeout error",
        "Test connection error",
        "Test invalid response",
    ],
    "division": [
        "Test divide by zero case",
    ],
    "regex": [
        "Test no match case",
        "Test multiple matches",
        "Test malformed input",
    ],
    "validation": [
        "Test valid input passes",
        "Test invalid input fails",
        "Test boundary values",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# Code Analysis Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _get_parser(extension: str) -> Optional["Parser"]:
    """Get a tree-sitter parser for the given file extension."""
    if not TREE_SITTER_AVAILABLE:
        return None

    if extension not in LANGUAGE_CONFIG:
        return None

    module_name, lang_func = LANGUAGE_CONFIG[extension]

    try:
        from tree_sitter import Language, Parser

        lang_module = importlib.import_module(module_name)
        lang_func_callable = getattr(lang_module, lang_func)
        lang_ptr = lang_func_callable()

        language = Language(lang_ptr)
        parser = Parser(language)
        return parser
    except ImportError as e:
        log.warning("tree_sitter_import_failed", error=str(e), extension=extension)
        return None
    except Exception as e:
        log.warning("parser_creation_failed", error=str(e), extension=extension)
        return None


def _extract_docstring(node: "Node", lang: str, source_bytes: bytes) -> Optional[str]:
    """Extract docstring from a function or class definition."""
    if lang == "python":
        body = node.child_by_field_name("body")
        if body and body.child_count > 0:
            first_stmt = body.children[0]
            if first_stmt.type == "expression_statement":
                if first_stmt.child_count > 0:
                    expr = first_stmt.children[0]
                    if expr.type == "string":
                        doc = source_bytes[expr.start_byte : expr.end_byte].decode(
                            "utf-8"
                        )
                        if doc.startswith('"""') or doc.startswith("'''"):
                            return doc[3:-3].strip()
                        elif doc.startswith('"') or doc.startswith("'"):
                            return doc[1:-1].strip()
    return None


def _extract_parameters(
    node: "Node", lang: str, source_bytes: bytes
) -> list[ParameterInfo]:
    """Extract function parameters from AST node."""
    params = []

    if lang == "python":
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for child in params_node.children:
                if child.type in {
                    "identifier",
                    "typed_parameter",
                    "default_parameter",
                    "typed_default_parameter",
                }:
                    name_node = child.child_by_field_name("name") or child
                    if name_node.text:
                        name = name_node.text.decode("utf-8")
                        # Skip self/cls
                        if name in ("self", "cls"):
                            continue

                        param = ParameterInfo(name=name)

                        # Get type annotation
                        type_node = child.child_by_field_name("type")
                        if type_node and type_node.text:
                            param.type_hint = type_node.text.decode("utf-8")
                            if "Optional" in param.type_hint:
                                param.is_optional = True

                        # Get default value
                        if child.type in {"default_parameter", "typed_default_parameter"}:
                            value_node = child.child_by_field_name("value")
                            if value_node and value_node.text:
                                param.default = value_node.text.decode("utf-8")
                                if param.default == "None":
                                    param.is_optional = True

                        params.append(param)

    elif lang in {"javascript", "typescript"}:
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for child in params_node.children:
                if child.type in {
                    "identifier",
                    "required_parameter",
                    "optional_parameter",
                }:
                    name_node = child.child_by_field_name("pattern") or child
                    if name_node.text:
                        param = ParameterInfo(name=name_node.text.decode("utf-8"))

                        type_node = child.child_by_field_name("type")
                        if type_node and type_node.text:
                            param.type_hint = type_node.text.decode("utf-8")

                        if child.type == "optional_parameter":
                            param.is_optional = True

                        params.append(param)

    return params


def _extract_return_type(node: "Node", lang: str) -> Optional[str]:
    """Extract return type annotation."""
    if lang == "python":
        return_type = node.child_by_field_name("return_type")
        if return_type and return_type.text:
            return return_type.text.decode("utf-8")
    elif lang in {"javascript", "typescript"}:
        return_type = node.child_by_field_name("return_type")
        if return_type and return_type.text:
            return return_type.text.decode("utf-8")
    return None


def _extract_decorators(node: "Node", lang: str, source_bytes: bytes) -> list[str]:
    """Extract decorators from function/class definition."""
    decorators = []
    if lang == "python":
        # Look for decorator nodes before the definition
        parent = node.parent
        if parent and parent.type == "decorated_definition":
            for child in parent.children:
                if child.type == "decorator":
                    dec_text = source_bytes[child.start_byte : child.end_byte].decode(
                        "utf-8"
                    )
                    decorators.append(dec_text.strip())
    return decorators


def _is_async_function(node: "Node", lang: str) -> bool:
    """Check if function is async."""
    if lang == "python":
        # Check for async keyword
        for child in node.children:
            if child.type == "async":
                return True
        # Also check node type
        return node.type == "async_function_definition"
    return False


def _extract_functions(
    root_node: "Node", lang: str, source_bytes: bytes
) -> list[FunctionInfo]:
    """Extract all function definitions from AST."""
    functions = []

    def _search(node: "Node"):
        if node.type in {"function_definition", "async_function_definition"}:
            name_node = node.child_by_field_name("name")
            if name_node and name_node.text:
                func = FunctionInfo(
                    name=name_node.text.decode("utf-8"),
                    parameters=_extract_parameters(node, lang, source_bytes),
                    return_type=_extract_return_type(node, lang),
                    docstring=_extract_docstring(node, lang, source_bytes),
                    is_async=_is_async_function(node, lang),
                    decorators=_extract_decorators(node, lang, source_bytes),
                    line_number=node.start_point[0] + 1,
                )
                functions.append(func)

        # For JS/TS, also check arrow functions and function expressions
        elif lang in {"javascript", "typescript"}:
            if node.type == "function_declaration":
                name_node = node.child_by_field_name("name")
                if name_node and name_node.text:
                    func = FunctionInfo(
                        name=name_node.text.decode("utf-8"),
                        parameters=_extract_parameters(node, lang, source_bytes),
                        return_type=_extract_return_type(node, lang),
                        line_number=node.start_point[0] + 1,
                    )
                    functions.append(func)

        for child in node.children:
            _search(child)

    _search(root_node)
    return functions


def _extract_classes(
    root_node: "Node", lang: str, source_bytes: bytes
) -> list[ClassInfo]:
    """Extract all class definitions from AST."""
    classes = []

    def _search(node: "Node"):
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node and name_node.text:
                cls = ClassInfo(
                    name=name_node.text.decode("utf-8"),
                    docstring=_extract_docstring(node, lang, source_bytes),
                    line_number=node.start_point[0] + 1,
                )

                # Extract base classes
                bases = node.child_by_field_name("superclasses")
                if bases:
                    for child in bases.children:
                        if child.type == "identifier" and child.text:
                            cls.base_classes.append(child.text.decode("utf-8"))

                # Extract methods
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        if child.type in {
                            "function_definition",
                            "async_function_definition",
                        }:
                            method_name_node = child.child_by_field_name("name")
                            if method_name_node and method_name_node.text:
                                method = FunctionInfo(
                                    name=method_name_node.text.decode("utf-8"),
                                    parameters=_extract_parameters(
                                        child, lang, source_bytes
                                    ),
                                    return_type=_extract_return_type(child, lang),
                                    docstring=_extract_docstring(
                                        child, lang, source_bytes
                                    ),
                                    is_async=_is_async_function(child, lang),
                                    decorators=_extract_decorators(
                                        child, lang, source_bytes
                                    ),
                                    line_number=child.start_point[0] + 1,
                                )
                                cls.methods.append(method)

                                # Check for __init__ params
                                if method.name == "__init__":
                                    cls.init_params = method.parameters

                classes.append(cls)

        for child in node.children:
            _search(child)

    _search(root_node)
    return classes


def _extract_imports(source_code: str, lang: str) -> list[str]:
    """Extract import statements from source code."""
    imports = []
    if lang == "python":
        # Match import and from...import statements
        import_pattern = r"^(?:from\s+([\w.]+)\s+)?import\s+(.+)$"
        for line in source_code.split("\n"):
            line = line.strip()
            match = re.match(import_pattern, line)
            if match:
                if match.group(1):
                    imports.append(match.group(1))
                else:
                    # Handle 'import x, y, z'
                    for item in match.group(2).split(","):
                        item = item.strip().split(" as ")[0].split(".")[0]
                        if item:
                            imports.append(item)
    return imports


def _detect_patterns(source_code: str) -> list[str]:
    """Detect code patterns that suggest specific test cases."""
    patterns = []

    # File operations
    if any(
        x in source_code
        for x in ["open(", "Path(", "read_file", "write_file", ".read(", ".write("]
    ):
        patterns.append("file_operation")

    # Network calls
    if any(
        x in source_code
        for x in ["requests.", "httpx.", "aiohttp.", "urllib.", "fetch("]
    ):
        patterns.append("network_call")

    # Division operations
    if "/" in source_code and "//" not in source_code:  # Avoid comments
        patterns.append("division")

    # Regex operations
    if any(x in source_code for x in ["re.", "regex", "match(", "search("]):
        patterns.append("regex")

    # Validation patterns
    if any(x in source_code for x in ["validate", "is_valid", "check_", "verify_"]):
        patterns.append("validation")

    return patterns


def _detect_test_framework(project_path: Path) -> str:
    """Detect the test framework used in a project."""
    # Check for pytest markers
    if (project_path / "conftest.py").exists():
        return "pytest"
    if (project_path / "pytest.ini").exists():
        return "pytest"

    # Check pyproject.toml for pytest
    pyproject = project_path / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        if "[tool.pytest" in content:
            return "pytest"

    # Check for jest
    if (project_path / "jest.config.js").exists():
        return "jest"
    if (project_path / "jest.config.ts").exists():
        return "jest"

    # Check package.json for jest
    pkg_json = project_path / "package.json"
    if pkg_json.exists():
        try:
            content = json.loads(pkg_json.read_text())
            if "jest" in content.get("devDependencies", {}):
                return "jest"
            if "jest" in content.get("dependencies", {}):
                return "jest"
        except json.JSONDecodeError:
            pass

    # Default to pytest for Python
    return "pytest"


# ═══════════════════════════════════════════════════════════════════════════════
# Test Templates
# ═══════════════════════════════════════════════════════════════════════════════

PYTEST_IMPORTS = '''"""Tests for {module_name}."""

import pytest
{additional_imports}

from {module_path} import {targets}
'''

PYTEST_FUNCTION_TEMPLATE = '''
def test_{func_name}_basic():
    """Test {func_name} with valid inputs."""
    {setup_code}
    result = {call_expression}
    assert result is not None  # TODO: Add specific assertion
'''

PYTEST_ASYNC_FUNCTION_TEMPLATE = '''
@pytest.mark.asyncio
async def test_{func_name}_basic():
    """Test {func_name} with valid inputs."""
    {setup_code}
    result = await {call_expression}
    assert result is not None  # TODO: Add specific assertion
'''

PYTEST_CLASS_TEMPLATE = '''
class Test{class_name}:
    """Tests for {class_name}."""

    @pytest.fixture
    def instance(self):
        """Create {class_name} instance for testing."""
        return {class_name}({default_args})

    def test_init(self, instance):
        """Test {class_name} initialization."""
        assert instance is not None
{method_tests}
'''

PYTEST_METHOD_TEMPLATE = '''
    def test_{method_name}_basic(self, instance):
        """Test {method_name} method."""
        result = instance.{method_name}({args})
        assert result is not None  # TODO: Add specific assertion
'''

PYTEST_ASYNC_METHOD_TEMPLATE = '''
    @pytest.mark.asyncio
    async def test_{method_name}_basic(self, instance):
        """Test {method_name} method."""
        result = await instance.{method_name}({args})
        assert result is not None  # TODO: Add specific assertion
'''

CONFTEST_TEMPLATE = '''"""Test fixtures for {module_name}."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

{imports}

# ═══════════════════════════════════════════════════════════════════════════════
# Mock Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

{mock_fixtures}

# ═══════════════════════════════════════════════════════════════════════════════
# Data Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

{data_fixtures}
'''

MOCK_FIXTURE_TEMPLATE = '''
@pytest.fixture
def mock_{dep_name}():
    """Mock {dep_name} for testing."""
    with patch("{module_path}.{dep_name}") as mock:
        mock.return_value = MagicMock()
        yield mock
'''

ASYNC_MOCK_FIXTURE_TEMPLATE = '''
@pytest.fixture
def mock_{dep_name}():
    """Mock {dep_name} for testing."""
    with patch("{module_path}.{dep_name}") as mock:
        mock.return_value = AsyncMock()
        yield mock
'''

HYPOTHESIS_TEMPLATE = '''"""Property-based tests for {module_name}."""

from hypothesis import given, strategies as st, settings, assume
import pytest

from {module_path} import {function}


@given({strategies})
@settings(max_examples={max_examples})
def test_{function}_property({params}):
    """Property test: {property_description}"""
    {assumptions}
    result = {call_expression}
    {assertions}
'''

TYPE_TO_HYPOTHESIS_STRATEGY: dict[str, str] = {
    "int": "st.integers()",
    "str": "st.text()",
    "float": "st.floats(allow_nan=False, allow_infinity=False)",
    "bool": "st.booleans()",
    "list": "st.lists(st.integers())",
    "List": "st.lists(st.integers())",
    "dict": "st.dictionaries(st.text(min_size=1), st.integers())",
    "Dict": "st.dictionaries(st.text(min_size=1), st.integers())",
    "bytes": "st.binary()",
    "Optional[int]": "st.none() | st.integers()",
    "Optional[str]": "st.none() | st.text()",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Tool Implementations
# ═══════════════════════════════════════════════════════════════════════════════


class SuggestTestCasesTool(Tool):
    """Analyze code and suggest test scenarios."""

    name = "suggest_test_cases"
    description = """Analyze source code and suggest test cases without generating code.

Returns a list of suggested test scenarios including basic tests, edge cases,
and error cases based on function signatures and code patterns.

Examples:
- suggest_test_cases(source_file="src/auth.py") - Analyze all functions
- suggest_test_cases(source_file="src/utils.py", target="validate_email") - Specific function
- suggest_test_cases(source_file="src/api.py", output_format="json") - JSON output"""

    parameters = {
        "type": "object",
        "properties": {
            "source_file": {
                "type": "string",
                "description": "Path to source file to analyze",
            },
            "target": {
                "type": "string",
                "description": "Specific function or class name to analyze (optional)",
            },
            "include_edge_cases": {
                "type": "boolean",
                "description": "Include edge case suggestions (default: true)",
            },
            "include_error_cases": {
                "type": "boolean",
                "description": "Include error handling test suggestions (default: true)",
            },
            "output_format": {
                "type": "string",
                "description": "Output format: 'text', 'json', or 'markdown' (default: markdown)",
                "enum": ["text", "json", "markdown"],
            },
        },
        "required": ["source_file"],
    }

    async def execute(
        self,
        source_file: str,
        target: Optional[str] = None,
        include_edge_cases: bool = True,
        include_error_cases: bool = True,
        output_format: str = "markdown",
        **kwargs,
    ) -> ToolResult:
        """Execute test case suggestion."""
        path = self._resolve_path(source_file)
        if not path.exists():
            return ToolResult(
                success=False, output="", error=f"File not found: {path}"
            )

        extension = path.suffix.lower()
        lang = EXT_TO_LANG.get(extension)
        if not lang:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsupported file type: {extension}. Supported: .py, .js, .ts",
            )

        try:
            async with aiofiles.open(path, "rb") as f:
                source_bytes = await f.read()
            source_code = source_bytes.decode("utf-8")

            # Try AST parsing first
            functions = []
            classes = []

            parser = _get_parser(extension)
            if parser:
                tree = parser.parse(source_bytes)
                functions = _extract_functions(tree.root_node, lang, source_bytes)
                classes = _extract_classes(tree.root_node, lang, source_bytes)
            else:
                # Fallback to regex-based extraction for basic info
                functions = self._regex_extract_functions(source_code, lang)

            # Filter by target if specified
            if target:
                functions = [f for f in functions if f.name == target]
                classes = [c for c in classes if c.name == target]

            if not functions and not classes:
                if target:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Target '{target}' not found in {path}",
                    )
                return ToolResult(
                    success=False,
                    output="",
                    error=f"No functions or classes found in {path}",
                )

            # Detect patterns in source
            patterns = _detect_patterns(source_code)

            # Generate suggestions
            suggestions = []

            for func in functions:
                suggestions.extend(
                    self._suggest_for_function(
                        func, patterns, include_edge_cases, include_error_cases
                    )
                )

            for cls in classes:
                suggestions.extend(
                    self._suggest_for_class(
                        cls, patterns, include_edge_cases, include_error_cases
                    )
                )

            # Format output
            output = self._format_suggestions(suggestions, output_format, path.stem)

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "file": str(path),
                    "functions_analyzed": len(functions),
                    "classes_analyzed": len(classes),
                    "suggestions_count": len(suggestions),
                    "patterns_detected": patterns,
                },
            )

        except Exception as e:
            log.error("suggest_test_cases_failed", error=str(e), file=str(path))
            return ToolResult(
                success=False, output="", error=f"Failed to analyze file: {e}"
            )

    def _regex_extract_functions(
        self, source_code: str, lang: str
    ) -> list[FunctionInfo]:
        """Fallback regex-based function extraction."""
        functions = []
        if lang == "python":
            # Match function definitions
            pattern = r"(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)"
            for match in re.finditer(pattern, source_code):
                name = match.group(1)
                params_str = match.group(2)
                is_async = "async def" in source_code[
                    max(0, match.start() - 10) : match.start() + 10
                ]

                params = []
                for param in params_str.split(","):
                    param = param.strip()
                    if param and param not in ("self", "cls"):
                        # Parse param name and type
                        if ":" in param:
                            p_name, p_type = param.split(":", 1)
                            p_name = p_name.strip()
                            p_type = p_type.split("=")[0].strip()
                            params.append(
                                ParameterInfo(name=p_name, type_hint=p_type)
                            )
                        else:
                            p_name = param.split("=")[0].strip()
                            params.append(ParameterInfo(name=p_name))

                functions.append(
                    FunctionInfo(name=name, parameters=params, is_async=is_async)
                )
        return functions

    def _suggest_for_function(
        self,
        func: FunctionInfo,
        patterns: list[str],
        include_edge_cases: bool,
        include_error_cases: bool,
    ) -> list[SuggestedTestCase]:
        """Generate test suggestions for a function."""
        suggestions = []

        # Basic test
        suggestions.append(
            SuggestedTestCase(
                description=f"Test {func.name} with valid inputs returns expected result",
                category="basic",
                target=func.name,
                priority="high",
            )
        )

        # Parameter-based suggestions
        for param in func.parameters:
            type_hint = param.type_hint or ""
            base_type = type_hint.split("[")[0].replace("Optional", "").strip("[]")

            if base_type in PARAM_SUGGESTIONS:
                for suggestion in PARAM_SUGGESTIONS[base_type]:
                    suggestions.append(
                        SuggestedTestCase(
                            description=f"{suggestion} for parameter '{param.name}'",
                            category="edge_case" if include_edge_cases else "basic",
                            target=func.name,
                            priority="medium",
                        )
                    )

            if param.is_optional or "Optional" in type_hint:
                suggestions.append(
                    SuggestedTestCase(
                        description=f"Test {func.name} with {param.name}=None",
                        category="edge_case",
                        target=func.name,
                        priority="medium",
                    )
                )

        # Return type suggestions
        if func.return_type:
            base_return = func.return_type.split("[")[0]
            if base_return in RETURN_TYPE_SUGGESTIONS:
                for suggestion in RETURN_TYPE_SUGGESTIONS[base_return]:
                    suggestions.append(
                        SuggestedTestCase(
                            description=suggestion,
                            category="basic",
                            target=func.name,
                            priority="medium",
                        )
                    )

        # Pattern-based suggestions
        if include_error_cases:
            for pattern in patterns:
                if pattern in PATTERN_SUGGESTIONS:
                    for suggestion in PATTERN_SUGGESTIONS[pattern]:
                        suggestions.append(
                            SuggestedTestCase(
                                description=suggestion,
                                category="error_case",
                                target=func.name,
                                priority="medium",
                            )
                        )

        # Async function suggestion
        if func.is_async:
            suggestions.append(
                SuggestedTestCase(
                    description="Test async function completes without timeout",
                    category="basic",
                    target=func.name,
                    priority="medium",
                )
            )

        return suggestions

    def _suggest_for_class(
        self,
        cls: ClassInfo,
        patterns: list[str],
        include_edge_cases: bool,
        include_error_cases: bool,
    ) -> list[SuggestedTestCase]:
        """Generate test suggestions for a class."""
        suggestions = []

        # Init test
        suggestions.append(
            SuggestedTestCase(
                description=f"Test {cls.name} initialization with valid arguments",
                category="basic",
                target=cls.name,
                priority="high",
            )
        )

        # Init params edge cases
        for param in cls.init_params:
            if param.is_optional:
                suggestions.append(
                    SuggestedTestCase(
                        description=f"Test {cls.name} init with {param.name}=None",
                        category="edge_case",
                        target=cls.name,
                        priority="medium",
                    )
                )

        # Method tests
        for method in cls.methods:
            if not method.name.startswith("_"):  # Skip private methods
                suggestions.extend(
                    self._suggest_for_function(
                        method, patterns, include_edge_cases, include_error_cases
                    )
                )

        return suggestions

    def _format_suggestions(
        self, suggestions: list[SuggestedTestCase], format: str, module_name: str
    ) -> str:
        """Format suggestions for output."""
        if format == "json":
            return json.dumps(
                [
                    {
                        "description": s.description,
                        "category": s.category,
                        "target": s.target,
                        "priority": s.priority,
                    }
                    for s in suggestions
                ],
                indent=2,
            )

        elif format == "markdown":
            lines = [f"# Test Suggestions for {module_name}\n"]

            # Group by target
            by_target: dict[str, list[SuggestedTestCase]] = {}
            for s in suggestions:
                if s.target not in by_target:
                    by_target[s.target] = []
                by_target[s.target].append(s)

            for target, target_suggestions in by_target.items():
                lines.append(f"\n## {target}\n")

                # Group by category
                basic = [s for s in target_suggestions if s.category == "basic"]
                edge = [s for s in target_suggestions if s.category == "edge_case"]
                error = [s for s in target_suggestions if s.category == "error_case"]

                if basic:
                    lines.append("\n### Basic Tests")
                    for s in basic:
                        lines.append(f"- [ ] {s.description}")

                if edge:
                    lines.append("\n### Edge Cases")
                    for s in edge:
                        lines.append(f"- [ ] {s.description}")

                if error:
                    lines.append("\n### Error Cases")
                    for s in error:
                        lines.append(f"- [ ] {s.description}")

            return "\n".join(lines)

        else:  # text
            lines = [f"Test Suggestions for {module_name}:", ""]
            for s in suggestions:
                lines.append(f"[{s.category.upper()}] {s.target}: {s.description}")
            return "\n".join(lines)


class GenerateUnitTestsTool(Tool):
    """Generate unit test scaffolding for functions and classes."""

    name = "generate_unit_tests"
    description = """Generate unit test scaffolding for functions and classes.

Analyzes source code and generates appropriate test files with test functions,
fixtures, and assertions based on the detected patterns.

Examples:
- generate_unit_tests(source_file="src/auth.py") - Generate tests for all
- generate_unit_tests(source_file="src/utils.py", target="validate_email") - Specific function
- generate_unit_tests(source_file="src/api.py", framework="pytest", dry_run=true) - Preview"""

    parameters = {
        "type": "object",
        "properties": {
            "source_file": {
                "type": "string",
                "description": "Path to source file to generate tests for",
            },
            "target": {
                "type": "string",
                "description": "Specific function or class name (optional - tests all if not specified)",
            },
            "framework": {
                "type": "string",
                "description": "Test framework: 'pytest', 'unittest', 'jest' (auto-detected)",
                "enum": ["pytest", "unittest", "jest", "vitest"],
            },
            "output_file": {
                "type": "string",
                "description": "Output test file path (default: test_{source}.py)",
            },
            "test_style": {
                "type": "string",
                "description": "Test organization: 'class' or 'function' (default: function for pytest)",
                "enum": ["class", "function"],
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview tests without writing file (default: false)",
            },
        },
        "required": ["source_file"],
    }

    async def execute(
        self,
        source_file: str,
        target: Optional[str] = None,
        framework: Optional[str] = None,
        output_file: Optional[str] = None,
        test_style: str = "function",
        dry_run: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Execute test generation."""
        path = self._resolve_path(source_file)
        if not path.exists():
            return ToolResult(
                success=False, output="", error=f"File not found: {path}"
            )

        extension = path.suffix.lower()
        lang = EXT_TO_LANG.get(extension)
        if not lang:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsupported file type: {extension}. Supported: .py, .js, .ts",
            )

        # Auto-detect framework
        if not framework:
            framework = _detect_test_framework(path.parent)

        try:
            async with aiofiles.open(path, "rb") as f:
                source_bytes = await f.read()

            # Parse source
            functions = []
            classes = []

            parser = _get_parser(extension)
            if parser:
                tree = parser.parse(source_bytes)
                functions = _extract_functions(tree.root_node, lang, source_bytes)
                classes = _extract_classes(tree.root_node, lang, source_bytes)

            # Filter by target
            if target:
                functions = [f for f in functions if f.name == target]
                classes = [c for c in classes if c.name == target]

            if not functions and not classes:
                if target:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Target '{target}' not found in {path}",
                    )
                return ToolResult(
                    success=False,
                    output="",
                    error=f"No functions or classes found in {path}",
                )

            # Generate test code
            test_code = self._generate_tests(
                path, functions, classes, framework, test_style, lang
            )

            # Determine output path
            if output_file:
                out_path = self._resolve_path(output_file)
            else:
                out_path = path.parent / f"test_{path.stem}.py"

            # Write or preview
            if dry_run:
                output = f"=== DRY RUN: Would write to {out_path} ===\n\n{test_code}"
            else:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(out_path, "w") as f:
                    await f.write(test_code)
                output = f"Generated tests written to: {out_path}\n\n{test_code}"

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "source_file": str(path),
                    "output_file": str(out_path),
                    "framework": framework,
                    "functions_count": len(functions),
                    "classes_count": len(classes),
                    "dry_run": dry_run,
                },
            )

        except Exception as e:
            log.error("generate_unit_tests_failed", error=str(e), file=str(path))
            return ToolResult(
                success=False, output="", error=f"Failed to generate tests: {e}"
            )

    def _generate_tests(
        self,
        source_path: Path,
        functions: list[FunctionInfo],
        classes: list[ClassInfo],
        framework: str,
        style: str,
        lang: str,
    ) -> str:
        """Generate test code."""
        if framework == "pytest" and lang == "python":
            return self._generate_pytest_tests(
                source_path, functions, classes, style
            )
        elif framework == "jest" and lang in {"javascript", "typescript"}:
            return self._generate_jest_tests(source_path, functions, classes)
        else:
            # Default to pytest style
            return self._generate_pytest_tests(
                source_path, functions, classes, style
            )

    def _generate_pytest_tests(
        self,
        source_path: Path,
        functions: list[FunctionInfo],
        classes: list[ClassInfo],
        style: str,
    ) -> str:
        """Generate pytest tests."""
        module_name = source_path.stem
        module_path = source_path.stem  # Simplified, would need proper relative import

        # Collect targets for import
        targets = [f.name for f in functions] + [c.name for c in classes]

        # Check if any async functions
        has_async = any(f.is_async for f in functions) or any(
            any(m.is_async for m in c.methods) for c in classes
        )

        additional_imports = ""
        if has_async:
            additional_imports = "import asyncio"

        lines = [
            PYTEST_IMPORTS.format(
                module_name=module_name,
                module_path=module_path,
                targets=", ".join(targets) if targets else module_name,
                additional_imports=additional_imports,
            )
        ]

        # Generate function tests
        for func in functions:
            if func.is_async:
                template = PYTEST_ASYNC_FUNCTION_TEMPLATE
            else:
                template = PYTEST_FUNCTION_TEMPLATE

            # Build call expression
            args = ", ".join(
                f"{p.name}={p.default or self._default_value(p.type_hint)}"
                for p in func.parameters
            )
            call = f"{func.name}({args})"

            lines.append(
                template.format(
                    func_name=func.name,
                    setup_code="# TODO: Add setup",
                    call_expression=call,
                )
            )

        # Generate class tests
        for cls in classes:
            method_tests = []
            for method in cls.methods:
                if method.name.startswith("_") and method.name != "__init__":
                    continue

                if method.name == "__init__":
                    continue

                if method.is_async:
                    template = PYTEST_ASYNC_METHOD_TEMPLATE
                else:
                    template = PYTEST_METHOD_TEMPLATE

                args = ", ".join(
                    f"{p.name}={p.default or self._default_value(p.type_hint)}"
                    for p in method.parameters
                )

                method_tests.append(
                    template.format(method_name=method.name, args=args)
                )

            # Default args for init
            default_args = ", ".join(
                f"{p.name}={p.default or self._default_value(p.type_hint)}"
                for p in cls.init_params
            )

            lines.append(
                PYTEST_CLASS_TEMPLATE.format(
                    class_name=cls.name,
                    default_args=default_args,
                    method_tests="".join(method_tests),
                )
            )

        return "\n".join(lines)

    def _generate_jest_tests(
        self,
        source_path: Path,
        functions: list[FunctionInfo],
        classes: list[ClassInfo],
    ) -> str:
        """Generate Jest tests."""
        module_name = source_path.stem
        lines = [
            f"// Tests for {module_name}",
            f"",
            f"import {{ {', '.join(f.name for f in functions)} }} from './{module_name}';",
            f"",
        ]

        for func in functions:
            args = ", ".join(
                self._default_value_js(p.type_hint) for p in func.parameters
            )
            lines.extend(
                [
                    f"describe('{func.name}', () => {{",
                    f"  it('should return expected result with valid inputs', () => {{",
                    f"    const result = {func.name}({args});",
                    f"    expect(result).toBeDefined();",
                    f"  }});",
                    f"}});",
                    f"",
                ]
            )

        return "\n".join(lines)

    def _default_value(self, type_hint: Optional[str]) -> str:
        """Get default value for a type in Python."""
        if not type_hint:
            return "None"
        base = type_hint.split("[")[0].strip()
        defaults = {
            "str": '""',
            "int": "0",
            "float": "0.0",
            "bool": "False",
            "list": "[]",
            "dict": "{}",
            "List": "[]",
            "Dict": "{}",
            "Optional": "None",
            "Path": 'Path(".")',
        }
        return defaults.get(base, "None")

    def _default_value_js(self, type_hint: Optional[str]) -> str:
        """Get default value for a type in JavaScript."""
        if not type_hint:
            return "null"
        base = type_hint.split("[")[0].strip()
        defaults = {
            "string": '""',
            "number": "0",
            "boolean": "false",
            "array": "[]",
            "object": "{}",
        }
        return defaults.get(base.lower(), "null")


class GenerateTestFixturesTool(Tool):
    """Generate test fixtures and mock objects."""

    name = "generate_test_fixtures"
    description = """Generate test fixtures and mock objects for pytest.

Analyzes source code dependencies and generates appropriate fixtures,
mocks, and conftest.py files.

Examples:
- generate_test_fixtures(source_file="src/api.py") - Auto-detect dependencies
- generate_test_fixtures(source_file="src/db.py", dependencies_to_mock=["sqlalchemy"]) - Specific mocks
- generate_test_fixtures(source_file="src/service.py", fixture_scope="module") - Module-scoped"""

    parameters = {
        "type": "object",
        "properties": {
            "source_file": {
                "type": "string",
                "description": "Path to source file to analyze for dependencies",
            },
            "dependencies_to_mock": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of dependencies to generate mocks for (auto-detected if not specified)",
            },
            "framework": {
                "type": "string",
                "description": "Test framework: 'pytest' or 'jest' (auto-detected)",
                "enum": ["pytest", "jest"],
            },
            "output_file": {
                "type": "string",
                "description": "Output file path (default: conftest.py)",
            },
            "fixture_scope": {
                "type": "string",
                "description": "Pytest fixture scope (default: function)",
                "enum": ["function", "class", "module", "session"],
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview without writing file (default: false)",
            },
        },
        "required": ["source_file"],
    }

    # Common dependencies that should be mocked
    MOCKABLE_DEPS = {
        "requests": "HTTP client",
        "httpx": "Async HTTP client",
        "aiohttp": "Async HTTP client",
        "sqlalchemy": "Database ORM",
        "redis": "Redis client",
        "boto3": "AWS SDK",
        "asyncpg": "Async PostgreSQL",
        "aiofiles": "Async file I/O",
        "httpcore": "HTTP core",
    }

    async def execute(
        self,
        source_file: str,
        dependencies_to_mock: Optional[list[str]] = None,
        framework: Optional[str] = None,
        output_file: Optional[str] = None,
        fixture_scope: str = "function",
        dry_run: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Execute fixture generation."""
        path = self._resolve_path(source_file)
        if not path.exists():
            return ToolResult(
                success=False, output="", error=f"File not found: {path}"
            )

        extension = path.suffix.lower()
        lang = EXT_TO_LANG.get(extension)
        if not lang:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsupported file type: {extension}",
            )

        if not framework:
            framework = _detect_test_framework(path.parent)

        try:
            async with aiofiles.open(path, "r") as f:
                source_code = await f.read()

            # Extract imports to find dependencies
            imports = _extract_imports(source_code, lang)

            # Filter to mockable dependencies
            if dependencies_to_mock:
                deps_to_mock = dependencies_to_mock
            else:
                deps_to_mock = [
                    imp for imp in imports if imp in self.MOCKABLE_DEPS
                ]

            # Generate fixtures
            fixture_code = self._generate_fixtures(
                path, deps_to_mock, framework, fixture_scope, lang
            )

            # Determine output path
            if output_file:
                out_path = self._resolve_path(output_file)
            else:
                out_path = path.parent / "conftest.py"

            if dry_run:
                output = f"=== DRY RUN: Would write to {out_path} ===\n\n{fixture_code}"
            else:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(out_path, "w") as f:
                    await f.write(fixture_code)
                output = f"Generated fixtures written to: {out_path}\n\n{fixture_code}"

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "source_file": str(path),
                    "output_file": str(out_path),
                    "dependencies_mocked": deps_to_mock,
                    "fixture_scope": fixture_scope,
                    "dry_run": dry_run,
                },
            )

        except Exception as e:
            log.error("generate_test_fixtures_failed", error=str(e), file=str(path))
            return ToolResult(
                success=False, output="", error=f"Failed to generate fixtures: {e}"
            )

    def _generate_fixtures(
        self,
        source_path: Path,
        deps: list[str],
        framework: str,
        scope: str,
        lang: str,
    ) -> str:
        """Generate fixture code."""
        module_name = source_path.stem

        mock_fixtures = []
        for dep in deps:
            desc = self.MOCKABLE_DEPS.get(dep, dep)

            # Use async mock for async libraries
            if dep in {"httpx", "aiohttp", "asyncpg", "aiofiles"}:
                template = ASYNC_MOCK_FIXTURE_TEMPLATE
            else:
                template = MOCK_FIXTURE_TEMPLATE

            mock_fixtures.append(
                template.format(
                    dep_name=dep,
                    module_path=module_name,
                )
            )

        # Add common data fixtures
        data_fixtures = [
            """
@pytest.fixture
def sample_data():
    \"\"\"Sample test data.\"\"\"
    return {
        "id": 1,
        "name": "test",
        "active": True,
    }
""",
            """
@pytest.fixture
def temp_file(tmp_path):
    \"\"\"Create a temporary file for testing.\"\"\"
    file_path = tmp_path / "test_file.txt"
    file_path.write_text("test content")
    return file_path
""",
        ]

        return CONFTEST_TEMPLATE.format(
            module_name=module_name,
            imports="",
            mock_fixtures="\n".join(mock_fixtures),
            data_fixtures="\n".join(data_fixtures),
        )


class GeneratePropertyTestsTool(Tool):
    """Generate property-based tests using hypothesis."""

    name = "generate_property_tests"
    description = """Generate property-based tests using hypothesis.

Creates tests that verify properties hold for all inputs, using
hypothesis strategies to generate test data automatically.

Examples:
- generate_property_tests(source_file="src/parser.py", target="parse")
- generate_property_tests(source_file="src/codec.py", target="encode", properties_to_test=["roundtrip"])
- generate_property_tests(source_file="src/math.py", target="add", max_examples=200)"""

    parameters = {
        "type": "object",
        "properties": {
            "source_file": {
                "type": "string",
                "description": "Path to source file",
            },
            "target": {
                "type": "string",
                "description": "Function name to generate property tests for",
            },
            "framework": {
                "type": "string",
                "description": "Property testing framework (default: hypothesis)",
                "enum": ["hypothesis", "fast-check"],
            },
            "output_file": {
                "type": "string",
                "description": "Output file path",
            },
            "max_examples": {
                "type": "integer",
                "description": "Maximum examples to generate (default: 100)",
            },
            "properties_to_test": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Properties to test: 'roundtrip', 'idempotent', 'commutative', 'invariant'",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview without writing file (default: false)",
            },
        },
        "required": ["source_file", "target"],
    }

    async def execute(
        self,
        source_file: str,
        target: str,
        framework: str = "hypothesis",
        output_file: Optional[str] = None,
        max_examples: int = 100,
        properties_to_test: Optional[list[str]] = None,
        dry_run: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Execute property test generation."""
        path = self._resolve_path(source_file)
        if not path.exists():
            return ToolResult(
                success=False, output="", error=f"File not found: {path}"
            )

        extension = path.suffix.lower()
        lang = EXT_TO_LANG.get(extension)
        if lang != "python":
            return ToolResult(
                success=False,
                output="",
                error="Property tests currently only support Python with hypothesis",
            )

        try:
            async with aiofiles.open(path, "rb") as f:
                source_bytes = await f.read()

            # Parse source
            parser = _get_parser(extension)
            if not parser:
                return ToolResult(
                    success=False,
                    output="",
                    error="tree-sitter not available for parsing",
                )

            tree = parser.parse(source_bytes)
            functions = _extract_functions(tree.root_node, lang, source_bytes)

            # Find target function
            target_func = None
            for func in functions:
                if func.name == target:
                    target_func = func
                    break

            if not target_func:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Function '{target}' not found in {path}",
                )

            # Generate property tests
            test_code = self._generate_hypothesis_tests(
                path,
                target_func,
                max_examples,
                properties_to_test or ["basic"],
            )

            # Output path
            if output_file:
                out_path = self._resolve_path(output_file)
            else:
                out_path = path.parent / f"test_{path.stem}_properties.py"

            if dry_run:
                output = f"=== DRY RUN: Would write to {out_path} ===\n\n{test_code}"
            else:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(out_path, "w") as f:
                    await f.write(test_code)
                output = f"Generated property tests written to: {out_path}\n\n{test_code}"

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "source_file": str(path),
                    "output_file": str(out_path),
                    "target": target,
                    "max_examples": max_examples,
                    "properties": properties_to_test or ["basic"],
                    "dry_run": dry_run,
                },
            )

        except Exception as e:
            log.error(
                "generate_property_tests_failed", error=str(e), file=str(path)
            )
            return ToolResult(
                success=False, output="", error=f"Failed to generate property tests: {e}"
            )

    def _generate_hypothesis_tests(
        self,
        source_path: Path,
        func: FunctionInfo,
        max_examples: int,
        properties: list[str],
    ) -> str:
        """Generate hypothesis property tests."""
        module_name = source_path.stem

        # Build strategies for parameters
        strategies = []
        param_names = []
        for param in func.parameters:
            param_names.append(param.name)
            type_hint = param.type_hint or "str"
            base_type = type_hint.split("[")[0].strip()

            strategy = TYPE_TO_HYPOTHESIS_STRATEGY.get(base_type, "st.text()")
            strategies.append(f"{param.name}={strategy}")

        strategies_str = ", ".join(strategies)
        params_str = ", ".join(param_names)
        call_expr = f"{func.name}({params_str})"

        lines = [
            f'"""Property-based tests for {module_name}."""',
            "",
            "from hypothesis import given, strategies as st, settings, assume",
            "import pytest",
            "",
            f"from {module_name} import {func.name}",
            "",
        ]

        # Generate tests for each property type
        for prop in properties:
            if prop == "basic":
                lines.extend(
                    [
                        f"@given({strategies_str})",
                        f"@settings(max_examples={max_examples})",
                        f"def test_{func.name}_handles_any_input({params_str}):",
                        f'    """Property: {func.name} should handle any valid input without crashing."""',
                        f"    try:",
                        f"        result = {call_expr}",
                        f"        # Function completed without exception",
                        f"    except (ValueError, TypeError) as e:",
                        f"        # Expected validation errors are acceptable",
                        f"        pass",
                        "",
                    ]
                )

            elif prop == "roundtrip":
                lines.extend(
                    [
                        f"@given({strategies_str})",
                        f"@settings(max_examples={max_examples})",
                        f"def test_{func.name}_roundtrip({params_str}):",
                        f'    """Property: encode then decode should return original value."""',
                        f"    # TODO: Implement roundtrip test",
                        f"    # encoded = encode({params_str})",
                        f"    # decoded = decode(encoded)",
                        f"    # assert decoded == original",
                        f"    pass",
                        "",
                    ]
                )

            elif prop == "idempotent":
                lines.extend(
                    [
                        f"@given({strategies_str})",
                        f"@settings(max_examples={max_examples})",
                        f"def test_{func.name}_idempotent({params_str}):",
                        f'    """Property: applying function twice should equal applying once."""',
                        f"    result1 = {call_expr}",
                        f"    # Create call with result1 - adjust based on actual function",
                        f"    # result2 = {func.name}(result1)",
                        f"    # assert result1 == result2",
                        f"    pass",
                        "",
                    ]
                )

            elif prop == "invariant":
                lines.extend(
                    [
                        f"@given({strategies_str})",
                        f"@settings(max_examples={max_examples})",
                        f"def test_{func.name}_preserves_invariant({params_str}):",
                        f'    """Property: function should preserve some invariant."""',
                        f"    result = {call_expr}",
                        f"    # TODO: Add invariant check",
                        f"    # e.g., assert len(result) == len(input)",
                        f"    pass",
                        "",
                    ]
                )

        return "\n".join(lines)
