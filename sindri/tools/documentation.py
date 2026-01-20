"""AI-powered code documentation tools for Sindri.

Phase 13 Tier 2: Provides tools for generating docstrings, README files,
API documentation, code explanations, and changelogs.

Tools:
- GenerateDocstringsTool: Generate/update docstrings for functions and classes
- GenerateReadmeTool: Create README.md from project analysis
- GenerateApiDocsTool: Generate API documentation from source code
- ExplainCodeTool: Generate natural language code explanations
- GenerateChangelogTool: Generate changelog from git commits
"""

from __future__ import annotations

import asyncio
import importlib.util
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import aiofiles
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()

# Check for tree-sitter availability
TREE_SITTER_AVAILABLE = importlib.util.find_spec("tree_sitter") is not None

# Language configuration for tree-sitter parsing
LANGUAGE_CONFIG = {
    ".py": {"module": "tree_sitter_python", "language": "python"},
    ".js": {"module": "tree_sitter_javascript", "language": "javascript"},
    ".jsx": {"module": "tree_sitter_javascript", "language": "javascript"},
    ".ts": {"module": "tree_sitter_typescript", "language": "typescript"},
    ".tsx": {"module": "tree_sitter_typescript", "language": "tsx"},
}

# Supported file extensions for documentation
SUPPORTED_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}


class DocstringStyle(str, Enum):
    """Supported docstring styles."""

    GOOGLE = "google"
    NUMPY = "numpy"
    SPHINX = "sphinx"


@dataclass
class ParameterInfo:
    """Information about a function parameter."""

    name: str
    type_hint: str = ""
    default: str = ""
    description: str = ""


@dataclass
class FunctionDocInfo:
    """Extracted function information for documentation."""

    name: str
    parameters: list[ParameterInfo] = field(default_factory=list)
    return_type: str = ""
    return_description: str = ""
    docstring: str = ""
    is_async: bool = False
    decorators: list[str] = field(default_factory=list)
    line_number: int = 0
    end_line: int = 0
    body: str = ""
    raises: list[str] = field(default_factory=list)


@dataclass
class ClassDocInfo:
    """Extracted class information for documentation."""

    name: str
    methods: list[FunctionDocInfo] = field(default_factory=list)
    base_classes: list[str] = field(default_factory=list)
    docstring: str = ""
    attributes: list[ParameterInfo] = field(default_factory=list)
    line_number: int = 0
    end_line: int = 0


@dataclass
class ModuleDocInfo:
    """Extracted module information for documentation."""

    name: str
    docstring: str = ""
    functions: list[FunctionDocInfo] = field(default_factory=list)
    classes: list[ClassDocInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    constants: list[tuple[str, str]] = field(default_factory=list)  # (name, value)


@dataclass
class ProjectInfo:
    """Extracted project information for README generation."""

    name: str = ""
    description: str = ""
    version: str = ""
    author: str = ""
    license: str = ""
    python_version: str = ""
    dependencies: list[str] = field(default_factory=list)
    dev_dependencies: list[str] = field(default_factory=list)
    entry_points: dict[str, str] = field(default_factory=dict)
    project_type: str = "python"  # python, node, rust, go
    has_tests: bool = False
    has_docs: bool = False


@dataclass
class CommitInfo:
    """Information about a git commit."""

    hash: str
    short_hash: str
    message: str
    body: str
    author: str
    date: datetime
    commit_type: str = ""  # feat, fix, docs, refactor, etc.
    scope: str = ""
    breaking: bool = False


# Docstring templates for different styles
GOOGLE_DOCSTRING_TEMPLATE = '''"""{summary}

{description}
Args:
{args}
{raises}
Returns:
{returns}

Example:
{example}
"""'''

NUMPY_DOCSTRING_TEMPLATE = '''"""{summary}

{description}
Parameters
----------
{params}
{raises}
Returns
-------
{returns}

Examples
--------
{example}
"""'''

SPHINX_DOCSTRING_TEMPLATE = '''"""{summary}

{description}
{params}
{raises}
{returns}

Example::

{example}
"""'''

# Simple docstring templates (no example section)
GOOGLE_SIMPLE_TEMPLATE = '''"""{summary}

Args:
{args}

Returns:
{returns}
"""'''

NUMPY_SIMPLE_TEMPLATE = '''"""{summary}

Parameters
----------
{params}

Returns
-------
{returns}
"""'''

SPHINX_SIMPLE_TEMPLATE = '''"""{summary}

{params}

{returns}
"""'''


def _get_tree_sitter_parser(extension: str):
    """Get tree-sitter parser for a file extension."""
    if not TREE_SITTER_AVAILABLE:
        return None

    config = LANGUAGE_CONFIG.get(extension)
    if not config:
        return None

    try:
        import tree_sitter

        lang_module = importlib.import_module(config["module"])
        language = tree_sitter.Language(lang_module.language())
        parser = tree_sitter.Parser(language)
        return parser
    except Exception as e:
        log.debug("tree_sitter_init_failed", error=str(e), extension=extension)
        return None


def _extract_functions_tree_sitter(
    source: bytes, extension: str
) -> list[FunctionDocInfo]:
    """Extract function information using tree-sitter."""
    parser = _get_tree_sitter_parser(extension)
    if not parser:
        return []

    tree = parser.parse(source)
    functions = []

    def traverse(node, depth=0):
        # Python function definitions
        if node.type in ("function_definition", "async_function_definition"):
            func = _parse_python_function(node, source)
            if func:
                functions.append(func)
        # JavaScript/TypeScript function definitions
        elif node.type in (
            "function_declaration",
            "arrow_function",
            "method_definition",
        ):
            func = _parse_js_function(node, source)
            if func:
                functions.append(func)

        for child in node.children:
            traverse(child, depth + 1)

    traverse(tree.root_node)
    return functions


def _parse_python_function(node, source: bytes) -> FunctionDocInfo | None:
    """Parse a Python function node."""
    name = ""
    params = []
    return_type = ""
    docstring = ""
    decorators = []
    is_async = node.type == "async_function_definition"

    for child in node.children:
        if child.type == "identifier":
            name = source[child.start_byte : child.end_byte].decode("utf-8")
        elif child.type == "parameters":
            params = _parse_python_params(child, source)
        elif child.type == "type":
            return_type = source[child.start_byte : child.end_byte].decode("utf-8")
        elif child.type == "block":
            # Check for docstring as first statement
            for stmt in child.children:
                if stmt.type == "expression_statement":
                    for expr in stmt.children:
                        if expr.type == "string":
                            raw = source[expr.start_byte : expr.end_byte].decode(
                                "utf-8"
                            )
                            docstring = raw.strip("\"'").strip()
                            break
                    break
                elif stmt.type not in ("comment",):
                    break
        elif child.type == "decorator":
            dec_text = source[child.start_byte : child.end_byte].decode("utf-8")
            decorators.append(dec_text)

    if not name:
        return None

    # Get function body for analysis
    body = source[node.start_byte : node.end_byte].decode("utf-8")

    return FunctionDocInfo(
        name=name,
        parameters=params,
        return_type=return_type,
        docstring=docstring,
        is_async=is_async,
        decorators=decorators,
        line_number=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        body=body,
    )


def _parse_python_params(node, source: bytes) -> list[ParameterInfo]:
    """Parse Python function parameters."""
    params = []

    for child in node.children:
        if child.type in ("identifier", "typed_parameter", "default_parameter"):
            param = _parse_single_param(child, source)
            if param and param.name not in ("self", "cls"):
                params.append(param)
        elif child.type == "typed_default_parameter":
            param = _parse_single_param(child, source)
            if param and param.name not in ("self", "cls"):
                params.append(param)

    return params


def _parse_single_param(node, source: bytes) -> ParameterInfo | None:
    """Parse a single parameter node."""
    name = ""
    type_hint = ""
    default = ""

    if node.type == "identifier":
        name = source[node.start_byte : node.end_byte].decode("utf-8")
    elif node.type == "typed_parameter":
        for child in node.children:
            if child.type == "identifier":
                name = source[child.start_byte : child.end_byte].decode("utf-8")
            elif child.type == "type":
                type_hint = source[child.start_byte : child.end_byte].decode("utf-8")
    elif node.type in ("default_parameter", "typed_default_parameter"):
        for child in node.children:
            if child.type == "identifier":
                name = source[child.start_byte : child.end_byte].decode("utf-8")
            elif child.type == "type":
                type_hint = source[child.start_byte : child.end_byte].decode("utf-8")
            elif child.type not in ("=", "identifier", "type"):
                default = source[child.start_byte : child.end_byte].decode("utf-8")

    if not name:
        return None

    return ParameterInfo(name=name, type_hint=type_hint, default=default)


def _parse_js_function(node, source: bytes) -> FunctionDocInfo | None:
    """Parse a JavaScript/TypeScript function node."""
    name = ""
    params = []
    return_type = ""
    is_async = False

    for child in node.children:
        if child.type == "identifier":
            name = source[child.start_byte : child.end_byte].decode("utf-8")
        elif child.type == "formal_parameters":
            params = _parse_js_params(child, source)
        elif child.type == "type_annotation":
            return_type = source[child.start_byte : child.end_byte].decode("utf-8")
        elif child.type == "async":
            is_async = True

    # For arrow functions, try to get name from parent
    if not name and node.parent and node.parent.type == "variable_declarator":
        for sibling in node.parent.children:
            if sibling.type == "identifier":
                name = source[sibling.start_byte : sibling.end_byte].decode("utf-8")
                break

    if not name:
        return None

    body = source[node.start_byte : node.end_byte].decode("utf-8")

    return FunctionDocInfo(
        name=name,
        parameters=params,
        return_type=return_type,
        is_async=is_async,
        line_number=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        body=body,
    )


def _parse_js_params(node, source: bytes) -> list[ParameterInfo]:
    """Parse JavaScript function parameters."""
    params = []

    for child in node.children:
        if child.type == "identifier":
            name = source[child.start_byte : child.end_byte].decode("utf-8")
            params.append(ParameterInfo(name=name))
        elif child.type in (
            "required_parameter",
            "optional_parameter",
            "assignment_pattern",
        ):
            param = _parse_js_single_param(child, source)
            if param:
                params.append(param)

    return params


def _parse_js_single_param(node, source: bytes) -> ParameterInfo | None:
    """Parse a single JS parameter."""
    name = ""
    type_hint = ""
    default = ""

    for child in node.children:
        if child.type == "identifier":
            name = source[child.start_byte : child.end_byte].decode("utf-8")
        elif child.type == "type_annotation":
            type_hint = source[child.start_byte : child.end_byte].decode("utf-8")
            type_hint = type_hint.lstrip(": ")
        elif child.type not in ("identifier", "type_annotation", "=", "?"):
            if not default:
                default = source[child.start_byte : child.end_byte].decode("utf-8")

    if not name:
        return None

    return ParameterInfo(name=name, type_hint=type_hint, default=default)


def _extract_classes_tree_sitter(source: bytes, extension: str) -> list[ClassDocInfo]:
    """Extract class information using tree-sitter."""
    parser = _get_tree_sitter_parser(extension)
    if not parser:
        return []

    tree = parser.parse(source)
    classes = []

    def traverse(node):
        if node.type == "class_definition":
            cls = _parse_python_class(node, source)
            if cls:
                classes.append(cls)
        elif node.type == "class_declaration":
            cls = _parse_js_class(node, source)
            if cls:
                classes.append(cls)

        for child in node.children:
            traverse(child)

    traverse(tree.root_node)
    return classes


def _parse_python_class(node, source: bytes) -> ClassDocInfo | None:
    """Parse a Python class node."""
    name = ""
    base_classes = []
    docstring = ""
    methods = []
    attributes = []

    for child in node.children:
        if child.type == "identifier":
            name = source[child.start_byte : child.end_byte].decode("utf-8")
        elif child.type == "argument_list":
            for arg in child.children:
                if arg.type in ("identifier", "attribute"):
                    base = source[arg.start_byte : arg.end_byte].decode("utf-8")
                    base_classes.append(base)
        elif child.type == "block":
            # Check for docstring and methods
            for stmt in child.children:
                if stmt.type == "expression_statement":
                    for expr in stmt.children:
                        if expr.type == "string" and not docstring:
                            raw = source[expr.start_byte : expr.end_byte].decode(
                                "utf-8"
                            )
                            docstring = raw.strip("\"'").strip()
                elif stmt.type in ("function_definition", "async_function_definition"):
                    method = _parse_python_function(stmt, source)
                    if method:
                        methods.append(method)

    if not name:
        return None

    return ClassDocInfo(
        name=name,
        base_classes=base_classes,
        docstring=docstring,
        methods=methods,
        attributes=attributes,
        line_number=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
    )


def _parse_js_class(node, source: bytes) -> ClassDocInfo | None:
    """Parse a JavaScript class node."""
    name = ""
    base_classes = []
    methods = []

    for child in node.children:
        if child.type == "identifier":
            name = source[child.start_byte : child.end_byte].decode("utf-8")
        elif child.type == "class_heritage":
            for heritage in child.children:
                if heritage.type == "identifier":
                    base = source[heritage.start_byte : heritage.end_byte].decode(
                        "utf-8"
                    )
                    base_classes.append(base)
        elif child.type == "class_body":
            for member in child.children:
                if member.type == "method_definition":
                    method = _parse_js_function(member, source)
                    if method:
                        methods.append(method)

    if not name:
        return None

    return ClassDocInfo(
        name=name,
        base_classes=base_classes,
        methods=methods,
        line_number=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
    )


# Regex fallback patterns
PYTHON_FUNCTION_PATTERN = re.compile(
    r"^(?P<indent>\s*)(?P<decorators>(?:@\w+(?:\([^)]*\))?\s*\n\s*)*)?"
    r"(?P<async>async\s+)?def\s+(?P<name>\w+)\s*\("
    r"(?P<params>[^)]*)\)\s*(?:->\s*(?P<return>[^:]+))?\s*:",
    re.MULTILINE,
)

PYTHON_CLASS_PATTERN = re.compile(
    r"^(?P<indent>\s*)class\s+(?P<name>\w+)"
    r"(?:\((?P<bases>[^)]*)\))?\s*:",
    re.MULTILINE,
)

JS_FUNCTION_PATTERN = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(?P<name>\w+)\s*\("
    r"(?P<params>[^)]*)\)\s*(?::\s*(?P<return>[^{]+))?\s*\{",
    re.MULTILINE,
)


def _extract_functions_regex(source: str, extension: str) -> list[FunctionDocInfo]:
    """Fallback regex extraction for functions."""
    functions = []

    if extension == ".py":
        for match in PYTHON_FUNCTION_PATTERN.finditer(source):
            is_async = bool(match.group("async"))
            params = _parse_params_string(match.group("params") or "")
            decorators = []
            if match.group("decorators"):
                decorators = [
                    d.strip()
                    for d in match.group("decorators").strip().split("\n")
                    if d.strip()
                ]

            functions.append(
                FunctionDocInfo(
                    name=match.group("name"),
                    parameters=params,
                    return_type=match.group("return") or "",
                    is_async=is_async,
                    decorators=decorators,
                    line_number=source[: match.start()].count("\n") + 1,
                )
            )
    elif extension in (".js", ".jsx", ".ts", ".tsx"):
        for match in JS_FUNCTION_PATTERN.finditer(source):
            params = _parse_params_string(match.group("params") or "")
            functions.append(
                FunctionDocInfo(
                    name=match.group("name"),
                    parameters=params,
                    return_type=match.group("return") or "",
                    is_async="async" in match.group(0),
                    line_number=source[: match.start()].count("\n") + 1,
                )
            )

    return functions


def _extract_classes_regex(source: str, extension: str) -> list[ClassDocInfo]:
    """Fallback regex extraction for classes."""
    classes = []

    if extension == ".py":
        for match in PYTHON_CLASS_PATTERN.finditer(source):
            bases = []
            if match.group("bases"):
                bases = [b.strip() for b in match.group("bases").split(",")]

            classes.append(
                ClassDocInfo(
                    name=match.group("name"),
                    base_classes=bases,
                    line_number=source[: match.start()].count("\n") + 1,
                )
            )

    return classes


def _parse_params_string(params_str: str) -> list[ParameterInfo]:
    """Parse a parameter string into ParameterInfo list."""
    params = []
    if not params_str.strip():
        return params

    # Simple parsing, handles basic cases
    for param in params_str.split(","):
        param = param.strip()
        if not param or param in ("self", "cls"):
            continue

        name = param
        type_hint = ""
        default = ""

        # Check for default value
        if "=" in param:
            parts = param.split("=", 1)
            param = parts[0].strip()
            default = parts[1].strip()

        # Check for type hint
        if ":" in param:
            parts = param.split(":", 1)
            name = parts[0].strip()
            type_hint = parts[1].strip()
        else:
            name = param

        if name and name not in ("self", "cls", "*", "**"):
            # Clean up *args, **kwargs
            name = name.lstrip("*")
            params.append(ParameterInfo(name=name, type_hint=type_hint, default=default))

    return params


def _detect_docstring_style(source: str) -> DocstringStyle:
    """Detect the docstring style used in a file."""
    # Look for style indicators - use regex for flexibility with indentation
    # NumPy style: Parameters/Returns followed by dashed underlines
    if re.search(r"Parameters\s*\n\s*-{3,}", source) or re.search(
        r"Returns\s*\n\s*-{3,}", source
    ):
        return DocstringStyle.NUMPY
    elif ":param " in source or ":type " in source or ":returns:" in source:
        return DocstringStyle.SPHINX
    elif "Args:" in source or "Returns:" in source:
        return DocstringStyle.GOOGLE

    # Default to Google style
    return DocstringStyle.GOOGLE


def _generate_docstring(
    func: FunctionDocInfo, style: DocstringStyle, include_example: bool = False
) -> str:
    """Generate a docstring for a function in the specified style."""
    summary = f"TODO: Add description for {func.name}."
    description = ""

    if style == DocstringStyle.GOOGLE:
        return _generate_google_docstring(func, summary, description, include_example)
    elif style == DocstringStyle.NUMPY:
        return _generate_numpy_docstring(func, summary, description, include_example)
    else:
        return _generate_sphinx_docstring(func, summary, description, include_example)


def _generate_google_docstring(
    func: FunctionDocInfo, summary: str, description: str, include_example: bool
) -> str:
    """Generate Google-style docstring."""
    lines = [f'"""{summary}']

    if description:
        lines.append("")
        lines.append(f"    {description}")

    if func.parameters:
        lines.append("")
        lines.append("    Args:")
        for param in func.parameters:
            type_str = f" ({param.type_hint})" if param.type_hint else ""
            default_str = f" Defaults to {param.default}." if param.default else ""
            lines.append(
                f"        {param.name}{type_str}: TODO: Describe {param.name}.{default_str}"
            )

    if func.return_type and func.return_type.lower() not in ("none", "void"):
        lines.append("")
        lines.append("    Returns:")
        lines.append(f"        {func.return_type}: TODO: Describe return value.")

    if include_example:
        lines.append("")
        lines.append("    Example:")
        lines.append(f"        >>> {func.name}()")
        lines.append("        # TODO: Add expected output")

    lines.append('    """')
    return "\n".join(lines)


def _generate_numpy_docstring(
    func: FunctionDocInfo, summary: str, description: str, include_example: bool
) -> str:
    """Generate NumPy-style docstring."""
    lines = [f'"""{summary}']

    if description:
        lines.append("")
        lines.append(f"    {description}")

    if func.parameters:
        lines.append("")
        lines.append("    Parameters")
        lines.append("    ----------")
        for param in func.parameters:
            type_str = param.type_hint or "type"
            lines.append(f"    {param.name} : {type_str}")
            default_str = f" (default: {param.default})" if param.default else ""
            lines.append(f"        TODO: Describe {param.name}.{default_str}")

    if func.return_type and func.return_type.lower() not in ("none", "void"):
        lines.append("")
        lines.append("    Returns")
        lines.append("    -------")
        lines.append(f"    {func.return_type}")
        lines.append("        TODO: Describe return value.")

    if include_example:
        lines.append("")
        lines.append("    Examples")
        lines.append("    --------")
        lines.append(f"    >>> {func.name}()")
        lines.append("    # TODO: Add expected output")

    lines.append('    """')
    return "\n".join(lines)


def _generate_sphinx_docstring(
    func: FunctionDocInfo, summary: str, description: str, include_example: bool
) -> str:
    """Generate Sphinx-style docstring."""
    lines = [f'"""{summary}']

    if description:
        lines.append("")
        lines.append(f"    {description}")

    if func.parameters:
        lines.append("")
        for param in func.parameters:
            lines.append(f"    :param {param.name}: TODO: Describe {param.name}.")
            if param.type_hint:
                lines.append(f"    :type {param.name}: {param.type_hint}")

    if func.return_type and func.return_type.lower() not in ("none", "void"):
        lines.append(f"    :returns: TODO: Describe return value.")
        lines.append(f"    :rtype: {func.return_type}")

    if include_example:
        lines.append("")
        lines.append("    Example::")
        lines.append("")
        lines.append(f"        >>> {func.name}()")
        lines.append("        # TODO: Add expected output")

    lines.append('    """')
    return "\n".join(lines)


def _generate_class_docstring(cls: ClassDocInfo, style: DocstringStyle) -> str:
    """Generate a docstring for a class."""
    summary = f"TODO: Add description for {cls.name}."

    if style == DocstringStyle.GOOGLE:
        lines = [f'"""{summary}']
        if cls.attributes:
            lines.append("")
            lines.append("    Attributes:")
            for attr in cls.attributes:
                type_str = f" ({attr.type_hint})" if attr.type_hint else ""
                lines.append(f"        {attr.name}{type_str}: TODO: Describe.")
        lines.append('    """')
        return "\n".join(lines)

    elif style == DocstringStyle.NUMPY:
        lines = [f'"""{summary}']
        if cls.attributes:
            lines.append("")
            lines.append("    Attributes")
            lines.append("    ----------")
            for attr in cls.attributes:
                type_str = attr.type_hint or "type"
                lines.append(f"    {attr.name} : {type_str}")
                lines.append("        TODO: Describe.")
        lines.append('    """')
        return "\n".join(lines)

    else:  # Sphinx
        lines = [f'"""{summary}']
        if cls.attributes:
            lines.append("")
            for attr in cls.attributes:
                lines.append(f"    :ivar {attr.name}: TODO: Describe.")
                if attr.type_hint:
                    lines.append(f"    :vartype {attr.name}: {attr.type_hint}")
        lines.append('    """')
        return "\n".join(lines)


async def _detect_project_info(project_path: Path) -> ProjectInfo:
    """Detect project information from configuration files."""
    info = ProjectInfo()

    # Try pyproject.toml
    pyproject = project_path / "pyproject.toml"
    if pyproject.exists():
        info.project_type = "python"
        try:
            async with aiofiles.open(pyproject, "r") as f:
                content = await f.read()

            # Parse basic info (simple regex, not full TOML parser)
            name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
            if name_match:
                info.name = name_match.group(1)

            version_match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if version_match:
                info.version = version_match.group(1)

            desc_match = re.search(r'description\s*=\s*["\']([^"\']+)["\']', content)
            if desc_match:
                info.description = desc_match.group(1)

            python_match = re.search(
                r'requires-python\s*=\s*["\']([^"\']+)["\']', content
            )
            if python_match:
                info.python_version = python_match.group(1)

            # Extract dependencies
            deps_match = re.search(
                r"dependencies\s*=\s*\[(.*?)\]", content, re.DOTALL
            )
            if deps_match:
                deps_str = deps_match.group(1)
                info.dependencies = re.findall(r'["\']([^"\']+)["\']', deps_str)

        except Exception as e:
            log.debug("pyproject_parse_error", error=str(e))

    # Try setup.py
    setup_py = project_path / "setup.py"
    if setup_py.exists() and not info.name:
        info.project_type = "python"
        try:
            async with aiofiles.open(setup_py, "r") as f:
                content = await f.read()

            name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
            if name_match:
                info.name = name_match.group(1)

        except Exception as e:
            log.debug("setup_py_parse_error", error=str(e))

    # Try package.json
    package_json = project_path / "package.json"
    if package_json.exists():
        info.project_type = "node"
        try:
            async with aiofiles.open(package_json, "r") as f:
                content = await f.read()

            import json

            data = json.loads(content)
            info.name = data.get("name", "")
            info.version = data.get("version", "")
            info.description = data.get("description", "")
            info.author = data.get("author", "")
            info.license = data.get("license", "")

            deps = data.get("dependencies", {})
            info.dependencies = list(deps.keys())

            dev_deps = data.get("devDependencies", {})
            info.dev_dependencies = list(dev_deps.keys())

        except Exception as e:
            log.debug("package_json_parse_error", error=str(e))

    # Try Cargo.toml
    cargo_toml = project_path / "Cargo.toml"
    if cargo_toml.exists():
        info.project_type = "rust"
        try:
            async with aiofiles.open(cargo_toml, "r") as f:
                content = await f.read()

            name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
            if name_match:
                info.name = name_match.group(1)

            version_match = re.search(r'version\s*=\s*"([^"]+)"', content)
            if version_match:
                info.version = version_match.group(1)

        except Exception as e:
            log.debug("cargo_toml_parse_error", error=str(e))

    # Try go.mod
    go_mod = project_path / "go.mod"
    if go_mod.exists():
        info.project_type = "go"
        try:
            async with aiofiles.open(go_mod, "r") as f:
                content = await f.read()

            module_match = re.search(r"module\s+(\S+)", content)
            if module_match:
                info.name = module_match.group(1).split("/")[-1]

        except Exception as e:
            log.debug("go_mod_parse_error", error=str(e))

    # Detect tests directory
    info.has_tests = (project_path / "tests").exists() or (
        project_path / "test"
    ).exists()

    # Detect docs directory
    info.has_docs = (project_path / "docs").exists()

    # Try to detect license
    for license_file in ["LICENSE", "LICENSE.md", "LICENSE.txt"]:
        lf = project_path / license_file
        if lf.exists() and not info.license:
            try:
                async with aiofiles.open(lf, "r") as f:
                    content = await f.read()
                    if "MIT" in content:
                        info.license = "MIT"
                    elif "Apache" in content:
                        info.license = "Apache-2.0"
                    elif "GPL" in content:
                        info.license = "GPL"
                    elif "BSD" in content:
                        info.license = "BSD"
            except Exception:
                pass

    # Use directory name as fallback
    if not info.name:
        info.name = project_path.name

    return info


def _generate_readme(info: ProjectInfo) -> str:
    """Generate README.md content from project info."""
    lines = [f"# {info.name}", ""]

    if info.description:
        lines.append(info.description)
        lines.append("")

    # Badges
    badges = []
    if info.version:
        badges.append(f"![Version](https://img.shields.io/badge/version-{info.version}-blue)")
    if info.license:
        badges.append(f"![License](https://img.shields.io/badge/license-{info.license}-green)")
    if info.python_version:
        badges.append(f"![Python](https://img.shields.io/badge/python-{info.python_version}-blue)")

    if badges:
        lines.append(" ".join(badges))
        lines.append("")

    # Installation
    lines.append("## Installation")
    lines.append("")

    if info.project_type == "python":
        lines.append("```bash")
        lines.append(f"pip install {info.name}")
        lines.append("```")
    elif info.project_type == "node":
        lines.append("```bash")
        lines.append(f"npm install {info.name}")
        lines.append("```")
    elif info.project_type == "rust":
        lines.append("```bash")
        lines.append(f"cargo install {info.name}")
        lines.append("```")
    elif info.project_type == "go":
        lines.append("```bash")
        lines.append(f"go install {info.name}@latest")
        lines.append("```")

    lines.append("")

    # Usage
    lines.append("## Usage")
    lines.append("")
    lines.append("```python")
    lines.append(f"# TODO: Add usage examples for {info.name}")
    lines.append("```")
    lines.append("")

    # Dependencies
    if info.dependencies:
        lines.append("## Dependencies")
        lines.append("")
        for dep in info.dependencies[:10]:  # Limit to 10
            lines.append(f"- {dep}")
        if len(info.dependencies) > 10:
            lines.append(f"- ... and {len(info.dependencies) - 10} more")
        lines.append("")

    # Development
    if info.has_tests or info.dev_dependencies:
        lines.append("## Development")
        lines.append("")
        if info.project_type == "python":
            lines.append("```bash")
            lines.append("# Install dev dependencies")
            lines.append('pip install -e ".[dev]"')
            lines.append("")
            lines.append("# Run tests")
            lines.append("pytest tests/ -v")
            lines.append("```")
        elif info.project_type == "node":
            lines.append("```bash")
            lines.append("npm install")
            lines.append("npm test")
            lines.append("```")
        lines.append("")

    # License
    if info.license:
        lines.append("## License")
        lines.append("")
        lines.append(f"This project is licensed under the {info.license} License.")
        lines.append("")

    return "\n".join(lines)


def _parse_conventional_commit(message: str) -> tuple[str, str, bool]:
    """Parse a conventional commit message.

    Returns (type, scope, is_breaking).
    """
    # Pattern: type(scope)!: description
    pattern = r"^(?P<type>\w+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?\s*:\s*"
    match = re.match(pattern, message)

    if match:
        commit_type = match.group("type")
        scope = match.group("scope") or ""
        breaking = bool(match.group("breaking"))
        return commit_type, scope, breaking

    return "", "", False


async def _get_git_commits(
    project_path: Path, since: str | None = None, until: str | None = None
) -> list[CommitInfo]:
    """Get git commits from the repository."""
    commits = []

    try:
        cmd = [
            "git",
            "log",
            "--format=%H|%h|%s|%b|%an|%aI",
            "--no-merges",
        ]

        if since:
            cmd.append(f"--since={since}")
        if until:
            cmd.append(f"--until={until}")

        result = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await result.communicate()

        for line in stdout.decode("utf-8").strip().split("\n"):
            if not line:
                continue

            parts = line.split("|", 5)
            if len(parts) < 6:
                continue

            hash_full, hash_short, subject, body, author, date_str = parts

            commit_type, scope, breaking = _parse_conventional_commit(subject)

            try:
                date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                date = datetime.now()

            commits.append(
                CommitInfo(
                    hash=hash_full,
                    short_hash=hash_short,
                    message=subject,
                    body=body,
                    author=author,
                    date=date,
                    commit_type=commit_type,
                    scope=scope,
                    breaking=breaking,
                )
            )

    except Exception as e:
        log.debug("git_log_error", error=str(e))

    return commits


def _generate_changelog(
    commits: list[CommitInfo], version: str = "Unreleased"
) -> str:
    """Generate changelog in Keep a Changelog format."""
    lines = [
        "# Changelog",
        "",
        "All notable changes to this project will be documented in this file.",
        "",
        "The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),",
        "and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).",
        "",
    ]

    # Group commits by type
    added = []
    changed = []
    deprecated = []
    removed = []
    fixed = []
    security = []
    other = []

    type_mapping = {
        "feat": added,
        "feature": added,
        "add": added,
        "fix": fixed,
        "bugfix": fixed,
        "change": changed,
        "refactor": changed,
        "perf": changed,
        "deprecate": deprecated,
        "remove": removed,
        "security": security,
        "docs": other,
        "test": other,
        "chore": other,
        "ci": other,
        "build": other,
    }

    for commit in commits:
        target = type_mapping.get(commit.commit_type.lower(), other)
        scope_str = f"**{commit.scope}**: " if commit.scope else ""
        breaking_str = "**BREAKING** " if commit.breaking else ""

        # Clean up message (remove type prefix)
        msg = commit.message
        if commit.commit_type:
            msg = re.sub(r"^\w+(?:\([^)]+\))?!?\s*:\s*", "", msg)

        target.append(f"- {breaking_str}{scope_str}{msg} ({commit.short_hash})")

    # Generate version section
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines.append(f"## [{version}] - {date_str}")
    lines.append("")

    sections = [
        ("Added", added),
        ("Changed", changed),
        ("Deprecated", deprecated),
        ("Removed", removed),
        ("Fixed", fixed),
        ("Security", security),
    ]

    for section_name, items in sections:
        if items:
            lines.append(f"### {section_name}")
            lines.append("")
            lines.extend(items)
            lines.append("")

    # Add other commits if any
    if other:
        lines.append("### Other")
        lines.append("")
        lines.extend(other)
        lines.append("")

    return "\n".join(lines)


class GenerateDocstringsTool(Tool):
    """Generate or update docstrings for functions and classes."""

    name = "generate_docstrings"
    description = """Generate or update docstrings for functions and classes in a source file.

Analyzes code structure and generates docstrings in Google, NumPy, or Sphinx style.

Examples:
- generate_docstrings(source_file="src/utils.py") - Add docstrings to all functions
- generate_docstrings(source_file="src/api.py", target="process_data") - Specific function
- generate_docstrings(source_file="src/models.py", style="numpy") - NumPy style
- generate_docstrings(source_file="src/core.py", dry_run=True) - Preview changes"""

    parameters = {
        "type": "object",
        "properties": {
            "source_file": {
                "type": "string",
                "description": "Path to the source file to document",
            },
            "target": {
                "type": "string",
                "description": "Specific function or class name (optional, documents all if not specified)",
            },
            "style": {
                "type": "string",
                "enum": ["google", "numpy", "sphinx", "auto"],
                "description": "Docstring style (default: auto-detect from existing code)",
            },
            "include_examples": {
                "type": "boolean",
                "description": "Include example sections in docstrings (default: false)",
            },
            "overwrite": {
                "type": "boolean",
                "description": "Overwrite existing docstrings (default: false)",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview changes without writing (default: false)",
            },
        },
        "required": ["source_file"],
    }

    def __init__(self, work_dir: Path | None = None):
        self.work_dir = work_dir or Path.cwd()

    async def execute(
        self,
        source_file: str,
        target: str | None = None,
        style: str = "auto",
        include_examples: bool = False,
        overwrite: bool = False,
        dry_run: bool = False,
    ) -> ToolResult:
        path = Path(source_file)
        if not path.is_absolute():
            path = self.work_dir / path

        if not path.exists():
            return ToolResult(success=False, output="", error=f"File not found: {path}")

        extension = path.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsupported file type: {extension}. Supported: {SUPPORTED_EXTENSIONS}",
            )

        try:
            async with aiofiles.open(path, "rb") as f:
                source_bytes = await f.read()
            source = source_bytes.decode("utf-8")

            # Detect or use specified style
            if style == "auto":
                doc_style = _detect_docstring_style(source)
            else:
                doc_style = DocstringStyle(style)

            # Extract functions and classes
            if TREE_SITTER_AVAILABLE:
                functions = _extract_functions_tree_sitter(source_bytes, extension)
                classes = _extract_classes_tree_sitter(source_bytes, extension)
            else:
                functions = _extract_functions_regex(source, extension)
                classes = _extract_classes_regex(source, extension)

            # Filter by target if specified
            if target:
                functions = [f for f in functions if f.name == target]
                classes = [c for c in classes if c.name == target]

            if not functions and not classes:
                if target:
                    return ToolResult(
                        success=False, output="", error=f"Target not found: {target}"
                    )
                return ToolResult(
                    success=False, output="", error="No functions or classes found to document"
                )

            # Generate docstrings
            changes = []
            modified_source = source

            for func in functions:
                if func.docstring and not overwrite:
                    continue

                docstring = _generate_docstring(func, doc_style, include_examples)
                changes.append(
                    {"type": "function", "name": func.name, "line": func.line_number}
                )

                # Insert docstring after function definition
                lines = modified_source.split("\n")
                # Find the line with the function definition
                for i, line in enumerate(lines):
                    if i + 1 >= func.line_number and f"def {func.name}" in line:
                        # Insert docstring on next line
                        indent = len(line) - len(line.lstrip()) + 4
                        docstring_lines = docstring.split("\n")
                        docstring_indented = "\n".join(
                            " " * indent + dl.strip() if dl.strip() else ""
                            for dl in docstring_lines
                        )
                        lines.insert(i + 1, docstring_indented)
                        break

                modified_source = "\n".join(lines)

            for cls in classes:
                if cls.docstring and not overwrite:
                    continue

                docstring = _generate_class_docstring(cls, doc_style)
                changes.append(
                    {"type": "class", "name": cls.name, "line": cls.line_number}
                )

            output = f"Generated {len(changes)} docstrings in {doc_style.value} style:\n"
            for change in changes:
                output += f"  - {change['type']} {change['name']} (line {change['line']})\n"

            if dry_run:
                output += "\n--- Preview ---\n"
                output += modified_source[:2000]
                if len(modified_source) > 2000:
                    output += "\n... (truncated)"
            else:
                async with aiofiles.open(path, "w") as f:
                    await f.write(modified_source)
                output += f"\nWrote changes to {path}"

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "file": str(path),
                    "style": doc_style.value,
                    "changes": len(changes),
                    "dry_run": dry_run,
                },
            )

        except Exception as e:
            log.error("generate_docstrings_failed", error=str(e), file=str(path))
            return ToolResult(success=False, output="", error=f"Failed to generate docstrings: {e}")


class GenerateReadmeTool(Tool):
    """Generate README.md from project analysis."""

    name = "generate_readme"
    description = """Generate a README.md file from project structure and configuration.

Analyzes pyproject.toml, package.json, Cargo.toml, or go.mod to extract project info.

Examples:
- generate_readme(project_path=".") - Generate README for current project
- generate_readme(project_path="./mylib", output="README.md") - Specify output
- generate_readme(project_path=".", dry_run=true) - Preview without writing"""

    parameters = {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": "Path to project root directory",
            },
            "output": {
                "type": "string",
                "description": "Output file path (default: README.md in project root)",
            },
            "include_badges": {
                "type": "boolean",
                "description": "Include version/license badges (default: true)",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview without writing (default: false)",
            },
        },
        "required": ["project_path"],
    }

    def __init__(self, work_dir: Path | None = None):
        self.work_dir = work_dir or Path.cwd()

    async def execute(
        self,
        project_path: str,
        output: str | None = None,
        include_badges: bool = True,
        dry_run: bool = False,
    ) -> ToolResult:
        path = Path(project_path)
        if not path.is_absolute():
            path = self.work_dir / path

        if not path.exists():
            return ToolResult(success=False, output="", error=f"Project path not found: {path}")

        if not path.is_dir():
            return ToolResult(success=False, output="", error=f"Not a directory: {path}")

        try:
            # Detect project info
            info = await _detect_project_info(path)

            # Generate README content
            readme_content = _generate_readme(info)

            # Determine output path
            out_path = Path(output) if output else path / "README.md"
            if not out_path.is_absolute():
                out_path = path / out_path

            output_text = f"Generated README for {info.name} ({info.project_type} project)\n"
            output_text += f"Version: {info.version or 'not specified'}\n"
            output_text += f"License: {info.license or 'not specified'}\n"
            output_text += f"Dependencies: {len(info.dependencies)}\n"

            if dry_run:
                output_text += "\n--- Preview ---\n"
                output_text += readme_content
            else:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(out_path, "w") as f:
                    await f.write(readme_content)
                output_text += f"\nWrote README to {out_path}"

            return ToolResult(
                success=True,
                output=output_text,
                metadata={
                    "project_name": info.name,
                    "project_type": info.project_type,
                    "output_path": str(out_path),
                    "dry_run": dry_run,
                },
            )

        except Exception as e:
            log.error("generate_readme_failed", error=str(e), path=str(path))
            return ToolResult(success=False, output="", error=f"Failed to generate README: {e}")


class GenerateApiDocsTool(Tool):
    """Generate API documentation from source code."""

    name = "generate_api_docs"
    description = """Generate API documentation from source code files.

Extracts functions, classes, and their docstrings to create documentation.

Examples:
- generate_api_docs(source_path="src/api.py") - Document single file
- generate_api_docs(source_path="src/", recursive=true) - Document directory
- generate_api_docs(source_path="lib/", format="rst") - reStructuredText output"""

    parameters = {
        "type": "object",
        "properties": {
            "source_path": {
                "type": "string",
                "description": "Path to source file or directory",
            },
            "output": {
                "type": "string",
                "description": "Output file path (default: docs/api.md)",
            },
            "format": {
                "type": "string",
                "enum": ["markdown", "rst", "html"],
                "description": "Output format (default: markdown)",
            },
            "recursive": {
                "type": "boolean",
                "description": "Process directories recursively (default: false)",
            },
            "include_private": {
                "type": "boolean",
                "description": "Include private members (_name) (default: false)",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview without writing (default: false)",
            },
        },
        "required": ["source_path"],
    }

    def __init__(self, work_dir: Path | None = None):
        self.work_dir = work_dir or Path.cwd()

    async def execute(
        self,
        source_path: str,
        output: str | None = None,
        format: str = "markdown",
        recursive: bool = False,
        include_private: bool = False,
        dry_run: bool = False,
    ) -> ToolResult:
        path = Path(source_path)
        if not path.is_absolute():
            path = self.work_dir / path

        if not path.exists():
            return ToolResult(success=False, output="", error=f"Source path not found: {path}")

        try:
            # Collect source files
            files = []
            if path.is_file():
                files = [path]
            else:
                pattern = "**/*" if recursive else "*"
                for ext in SUPPORTED_EXTENSIONS:
                    files.extend(path.glob(f"{pattern}{ext}"))

            if not files:
                return ToolResult(
                    success=False, output="", error=f"No supported source files found in {path}"
                )

            # Extract documentation from all files
            modules = []
            for file in sorted(files):
                module_doc = await self._extract_module_docs(file, include_private)
                if module_doc:
                    modules.append(module_doc)

            # Generate documentation
            if format == "markdown":
                doc_content = self._generate_markdown_docs(modules)
            elif format == "rst":
                doc_content = self._generate_rst_docs(modules)
            else:
                doc_content = self._generate_html_docs(modules)

            # Determine output path
            out_path = Path(output) if output else self.work_dir / "docs" / "api.md"
            if not out_path.is_absolute():
                out_path = self.work_dir / out_path

            output_text = f"Generated API documentation for {len(modules)} modules:\n"
            total_funcs = sum(len(m.functions) for m in modules)
            total_classes = sum(len(m.classes) for m in modules)
            output_text += f"  - {total_funcs} functions\n"
            output_text += f"  - {total_classes} classes\n"

            if dry_run:
                output_text += "\n--- Preview ---\n"
                output_text += doc_content[:3000]
                if len(doc_content) > 3000:
                    output_text += "\n... (truncated)"
            else:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(out_path, "w") as f:
                    await f.write(doc_content)
                output_text += f"\nWrote documentation to {out_path}"

            return ToolResult(
                success=True,
                output=output_text,
                metadata={
                    "modules": len(modules),
                    "functions": total_funcs,
                    "classes": total_classes,
                    "format": format,
                    "output_path": str(out_path),
                    "dry_run": dry_run,
                },
            )

        except Exception as e:
            log.error("generate_api_docs_failed", error=str(e), path=str(path))
            return ToolResult(success=False, output="", error=f"Failed to generate API docs: {e}")

    async def _extract_module_docs(
        self, file: Path, include_private: bool
    ) -> ModuleDocInfo | None:
        """Extract documentation info from a module."""
        try:
            async with aiofiles.open(file, "rb") as f:
                source_bytes = await f.read()
            source = source_bytes.decode("utf-8")

            extension = file.suffix.lower()

            # Extract functions and classes
            if TREE_SITTER_AVAILABLE:
                functions = _extract_functions_tree_sitter(source_bytes, extension)
                classes = _extract_classes_tree_sitter(source_bytes, extension)
            else:
                functions = _extract_functions_regex(source, extension)
                classes = _extract_classes_regex(source, extension)

            # Filter private members
            if not include_private:
                functions = [f for f in functions if not f.name.startswith("_")]
                classes = [c for c in classes if not c.name.startswith("_")]

            # Extract module docstring
            module_docstring = ""
            lines = source.split("\n")
            for line in lines[:20]:
                if line.strip().startswith('"""') or line.strip().startswith("'''"):
                    # Find end of docstring
                    start_idx = source.find(line.strip())
                    quote = line.strip()[:3]
                    end_idx = source.find(quote, start_idx + 3)
                    if end_idx > start_idx:
                        module_docstring = source[start_idx + 3 : end_idx].strip()
                    break
                elif line.strip() and not line.strip().startswith("#"):
                    break

            return ModuleDocInfo(
                name=file.stem,
                docstring=module_docstring,
                functions=functions,
                classes=classes,
            )

        except Exception as e:
            log.debug("module_extraction_failed", file=str(file), error=str(e))
            return None

    def _generate_markdown_docs(self, modules: list[ModuleDocInfo]) -> str:
        """Generate Markdown documentation."""
        lines = ["# API Documentation", "", "## Table of Contents", ""]

        # Generate TOC
        for module in modules:
            lines.append(f"- [{module.name}](#{module.name.lower().replace('_', '-')})")
            for cls in module.classes:
                lines.append(
                    f"  - [{cls.name}](#{cls.name.lower().replace('_', '-')})"
                )

        lines.append("")

        # Generate content
        for module in modules:
            lines.append(f"## {module.name}")
            lines.append("")
            if module.docstring:
                lines.append(module.docstring)
                lines.append("")

            # Functions
            for func in module.functions:
                lines.append(f"### `{func.name}`")
                lines.append("")

                # Signature
                params_str = ", ".join(
                    f"{p.name}: {p.type_hint}" if p.type_hint else p.name
                    for p in func.parameters
                )
                return_str = f" -> {func.return_type}" if func.return_type else ""
                async_str = "async " if func.is_async else ""
                lines.append(f"```python")
                lines.append(f"{async_str}def {func.name}({params_str}){return_str}")
                lines.append("```")
                lines.append("")

                if func.docstring:
                    lines.append(func.docstring)
                    lines.append("")

            # Classes
            for cls in module.classes:
                lines.append(f"### {cls.name}")
                lines.append("")

                bases_str = f"({', '.join(cls.base_classes)})" if cls.base_classes else ""
                lines.append(f"```python")
                lines.append(f"class {cls.name}{bases_str}")
                lines.append("```")
                lines.append("")

                if cls.docstring:
                    lines.append(cls.docstring)
                    lines.append("")

                # Methods
                if cls.methods:
                    lines.append("**Methods:**")
                    lines.append("")
                    for method in cls.methods:
                        if not method.name.startswith("_") or method.name == "__init__":
                            lines.append(f"- `{method.name}`")
                    lines.append("")

        return "\n".join(lines)

    def _generate_rst_docs(self, modules: list[ModuleDocInfo]) -> str:
        """Generate reStructuredText documentation."""
        lines = [
            "API Documentation",
            "=================",
            "",
        ]

        for module in modules:
            lines.append(module.name)
            lines.append("-" * len(module.name))
            lines.append("")

            if module.docstring:
                lines.append(module.docstring)
                lines.append("")

            for func in module.functions:
                lines.append(f".. function:: {func.name}")
                lines.append("")
                if func.docstring:
                    lines.append(f"   {func.docstring}")
                    lines.append("")

            for cls in module.classes:
                lines.append(f".. class:: {cls.name}")
                lines.append("")
                if cls.docstring:
                    lines.append(f"   {cls.docstring}")
                    lines.append("")

        return "\n".join(lines)

    def _generate_html_docs(self, modules: list[ModuleDocInfo]) -> str:
        """Generate HTML documentation."""
        html = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            "  <title>API Documentation</title>",
            "  <style>",
            "    body { font-family: sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; }",
            "    code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }",
            "    pre { background: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto; }",
            "    h2 { border-bottom: 2px solid #333; padding-bottom: 5px; }",
            "    h3 { color: #444; }",
            "  </style>",
            "</head>",
            "<body>",
            "  <h1>API Documentation</h1>",
        ]

        for module in modules:
            html.append(f"  <h2>{module.name}</h2>")
            if module.docstring:
                html.append(f"  <p>{module.docstring}</p>")

            for func in module.functions:
                html.append(f"  <h3><code>{func.name}</code></h3>")
                if func.docstring:
                    html.append(f"  <p>{func.docstring}</p>")

            for cls in module.classes:
                html.append(f"  <h3><code>class {cls.name}</code></h3>")
                if cls.docstring:
                    html.append(f"  <p>{cls.docstring}</p>")

        html.extend(["</body>", "</html>"])
        return "\n".join(html)


class ExplainCodeTool(Tool):
    """Generate natural language explanations of code."""

    name = "explain_code"
    description = """Generate natural language explanations of code.

Analyzes code structure and generates human-readable explanations.

Examples:
- explain_code(source_file="src/algorithm.py") - Explain entire file
- explain_code(source_file="src/utils.py", target="process_data") - Explain function
- explain_code(source_file="src/models.py", detail_level="detailed") - Detailed analysis"""

    parameters = {
        "type": "object",
        "properties": {
            "source_file": {
                "type": "string",
                "description": "Path to the source file",
            },
            "target": {
                "type": "string",
                "description": "Specific function or class name (optional)",
            },
            "detail_level": {
                "type": "string",
                "enum": ["brief", "standard", "detailed"],
                "description": "Level of detail (default: standard)",
            },
            "format": {
                "type": "string",
                "enum": ["markdown", "text"],
                "description": "Output format (default: markdown)",
            },
        },
        "required": ["source_file"],
    }

    def __init__(self, work_dir: Path | None = None):
        self.work_dir = work_dir or Path.cwd()

    async def execute(
        self,
        source_file: str,
        target: str | None = None,
        detail_level: str = "standard",
        format: str = "markdown",
    ) -> ToolResult:
        path = Path(source_file)
        if not path.is_absolute():
            path = self.work_dir / path

        if not path.exists():
            return ToolResult(success=False, output="", error=f"File not found: {path}")

        extension = path.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsupported file type: {extension}",
            )

        try:
            async with aiofiles.open(path, "rb") as f:
                source_bytes = await f.read()
            source = source_bytes.decode("utf-8")

            # Extract functions and classes
            if TREE_SITTER_AVAILABLE:
                functions = _extract_functions_tree_sitter(source_bytes, extension)
                classes = _extract_classes_tree_sitter(source_bytes, extension)
            else:
                functions = _extract_functions_regex(source, extension)
                classes = _extract_classes_regex(source, extension)

            # Filter by target
            if target:
                functions = [f for f in functions if f.name == target]
                classes = [c for c in classes if c.name == target]

            if not functions and not classes:
                if target:
                    return ToolResult(success=False, output="", error=f"Target not found: {target}")
                return ToolResult(
                    success=False, output="", error="No functions or classes found"
                )

            # Generate explanations
            explanations = []

            for func in functions:
                explanation = self._explain_function(func, detail_level)
                explanations.append(explanation)

            for cls in classes:
                explanation = self._explain_class(cls, detail_level)
                explanations.append(explanation)

            # Format output
            if format == "markdown":
                output = self._format_markdown(explanations, path.name)
            else:
                output = self._format_text(explanations, path.name)

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "file": str(path),
                    "functions": len(functions),
                    "classes": len(classes),
                    "detail_level": detail_level,
                },
            )

        except Exception as e:
            log.error("explain_code_failed", error=str(e), file=str(path))
            return ToolResult(success=False, output="", error=f"Failed to explain code: {e}")

    def _explain_function(self, func: FunctionDocInfo, detail_level: str) -> dict:
        """Generate explanation for a function."""
        explanation = {
            "type": "function",
            "name": func.name,
            "summary": "",
            "parameters": [],
            "returns": "",
            "complexity": "",
            "patterns": [],
        }

        # Generate summary
        async_str = "asynchronous " if func.is_async else ""
        param_count = len(func.parameters)
        explanation["summary"] = (
            f"This is an {async_str}function named `{func.name}` "
            f"that takes {param_count} parameter{'s' if param_count != 1 else ''}."
        )

        # Explain parameters
        for param in func.parameters:
            param_desc = f"`{param.name}`"
            if param.type_hint:
                param_desc += f" ({param.type_hint})"
            if param.default:
                param_desc += f" - defaults to {param.default}"
            explanation["parameters"].append(param_desc)

        # Explain return type
        if func.return_type:
            explanation["returns"] = f"Returns a value of type `{func.return_type}`"

        # Analyze complexity (basic)
        if func.body:
            loops = func.body.count("for ") + func.body.count("while ")
            conditionals = func.body.count("if ") + func.body.count("elif ")
            try_blocks = func.body.count("try:")

            if detail_level in ("standard", "detailed"):
                complexity_parts = []
                if loops > 0:
                    complexity_parts.append(f"{loops} loop(s)")
                if conditionals > 0:
                    complexity_parts.append(f"{conditionals} conditional(s)")
                if try_blocks > 0:
                    complexity_parts.append(f"{try_blocks} try-except block(s)")

                if complexity_parts:
                    explanation["complexity"] = f"Contains {', '.join(complexity_parts)}"

        # Detect patterns
        if func.body and detail_level == "detailed":
            patterns = []
            if "await " in func.body:
                patterns.append("Uses async/await for asynchronous operations")
            if "yield" in func.body:
                patterns.append("Generator function that yields values")
            if re.search(r"open\(|aiofiles\.open", func.body):
                patterns.append("Performs file I/O operations")
            if re.search(r"requests\.|httpx\.|aiohttp\.", func.body):
                patterns.append("Makes HTTP requests")
            if "raise " in func.body:
                patterns.append("Raises exceptions for error handling")

            explanation["patterns"] = patterns

        return explanation

    def _explain_class(self, cls: ClassDocInfo, detail_level: str) -> dict:
        """Generate explanation for a class."""
        explanation = {
            "type": "class",
            "name": cls.name,
            "summary": "",
            "inheritance": "",
            "methods": [],
            "patterns": [],
        }

        # Generate summary
        method_count = len(cls.methods)
        explanation["summary"] = (
            f"This is a class named `{cls.name}` "
            f"with {method_count} method{'s' if method_count != 1 else ''}."
        )

        # Explain inheritance
        if cls.base_classes:
            explanation["inheritance"] = f"Inherits from: {', '.join(cls.base_classes)}"

        # Explain methods
        if detail_level in ("standard", "detailed"):
            for method in cls.methods:
                method_desc = f"`{method.name}`"
                if method.is_async:
                    method_desc += " (async)"
                if method.parameters:
                    method_desc += f" - {len(method.parameters)} params"
                explanation["methods"].append(method_desc)

        return explanation

    def _format_markdown(self, explanations: list[dict], filename: str) -> str:
        """Format explanations as Markdown."""
        lines = [f"# Code Explanation: {filename}", ""]

        for exp in explanations:
            if exp["type"] == "function":
                lines.append(f"## Function: `{exp['name']}`")
            else:
                lines.append(f"## Class: `{exp['name']}`")
            lines.append("")
            lines.append(exp["summary"])
            lines.append("")

            if exp.get("inheritance"):
                lines.append(f"**Inheritance:** {exp['inheritance']}")
                lines.append("")

            if exp.get("parameters"):
                lines.append("**Parameters:**")
                for param in exp["parameters"]:
                    lines.append(f"- {param}")
                lines.append("")

            if exp.get("returns"):
                lines.append(f"**Returns:** {exp['returns']}")
                lines.append("")

            if exp.get("complexity"):
                lines.append(f"**Complexity:** {exp['complexity']}")
                lines.append("")

            if exp.get("methods"):
                lines.append("**Methods:**")
                for method in exp["methods"]:
                    lines.append(f"- {method}")
                lines.append("")

            if exp.get("patterns"):
                lines.append("**Patterns Detected:**")
                for pattern in exp["patterns"]:
                    lines.append(f"- {pattern}")
                lines.append("")

        return "\n".join(lines)

    def _format_text(self, explanations: list[dict], filename: str) -> str:
        """Format explanations as plain text."""
        lines = [f"Code Explanation: {filename}", "=" * 50, ""]

        for exp in explanations:
            lines.append(f"{exp['type'].upper()}: {exp['name']}")
            lines.append("-" * 30)
            lines.append(exp["summary"])
            lines.append("")

            if exp.get("parameters"):
                lines.append("Parameters:")
                for param in exp["parameters"]:
                    lines.append(f"  - {param}")
                lines.append("")

            if exp.get("returns"):
                lines.append(f"Returns: {exp['returns']}")
                lines.append("")

        return "\n".join(lines)


class GenerateChangelogTool(Tool):
    """Generate changelog from git commits."""

    name = "generate_changelog"
    description = """Generate a changelog from git commit history.

Parses conventional commits and generates Keep a Changelog format.

Examples:
- generate_changelog(project_path=".") - Generate changelog for project
- generate_changelog(project_path=".", since="2024-01-01") - Since date
- generate_changelog(project_path=".", version="1.2.0") - Set version header"""

    parameters = {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": "Path to git repository",
            },
            "output": {
                "type": "string",
                "description": "Output file path (default: CHANGELOG.md)",
            },
            "since": {
                "type": "string",
                "description": "Include commits since date (YYYY-MM-DD)",
            },
            "until": {
                "type": "string",
                "description": "Include commits until date (YYYY-MM-DD)",
            },
            "version": {
                "type": "string",
                "description": "Version string for header (default: Unreleased)",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview without writing (default: false)",
            },
        },
        "required": ["project_path"],
    }

    def __init__(self, work_dir: Path | None = None):
        self.work_dir = work_dir or Path.cwd()

    async def execute(
        self,
        project_path: str,
        output: str | None = None,
        since: str | None = None,
        until: str | None = None,
        version: str = "Unreleased",
        dry_run: bool = False,
    ) -> ToolResult:
        path = Path(project_path)
        if not path.is_absolute():
            path = self.work_dir / path

        if not path.exists():
            return ToolResult(success=False, output="", error=f"Project path not found: {path}")

        # Check if it's a git repository
        if not (path / ".git").exists():
            return ToolResult(success=False, output="", error=f"Not a git repository: {path}")

        try:
            # Get commits
            commits = await _get_git_commits(path, since, until)

            if not commits:
                return ToolResult(
                    success=False,
                    output="",
                    error="No commits found in specified range",
                )

            # Generate changelog
            changelog = _generate_changelog(commits, version)

            # Determine output path
            out_path = Path(output) if output else path / "CHANGELOG.md"
            if not out_path.is_absolute():
                out_path = path / out_path

            # Count commit types
            type_counts = {}
            for commit in commits:
                t = commit.commit_type or "other"
                type_counts[t] = type_counts.get(t, 0) + 1

            output_text = f"Generated changelog from {len(commits)} commits:\n"
            for t, count in sorted(type_counts.items()):
                output_text += f"  - {t}: {count}\n"

            if dry_run:
                output_text += "\n--- Preview ---\n"
                output_text += changelog
            else:
                async with aiofiles.open(out_path, "w") as f:
                    await f.write(changelog)
                output_text += f"\nWrote changelog to {out_path}"

            return ToolResult(
                success=True,
                output=output_text,
                metadata={
                    "commits": len(commits),
                    "version": version,
                    "output_path": str(out_path),
                    "type_counts": type_counts,
                    "dry_run": dry_run,
                },
            )

        except Exception as e:
            log.error("generate_changelog_failed", error=str(e), path=str(path))
            return ToolResult(success=False, output="", error=f"Failed to generate changelog: {e}")
