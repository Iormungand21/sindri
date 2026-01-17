"""AST-based refactoring tools using tree-sitter.

Provides precise code analysis and refactoring using tree-sitter parsers:
- ASTParserTool: Parse source code and return AST structure
- FindReferencesTool: Find all references to a symbol
- ASTSymbolInfoTool: Get detailed info about a symbol
- ASTRefactorRenameTool: Precise symbol renaming using AST
"""

import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import aiofiles
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()

# Check for tree-sitter availability
TREE_SITTER_AVAILABLE = importlib.util.find_spec("tree_sitter") is not None

if TYPE_CHECKING:
    from tree_sitter import Language, Node, Parser, Tree


# Language configurations: extension -> (module_name, language_getter)
LANGUAGE_CONFIG: dict[str, tuple[str, str]] = {
    ".py": ("tree_sitter_python", "language"),
    ".pyi": ("tree_sitter_python", "language"),
    ".js": ("tree_sitter_javascript", "language"),
    ".jsx": ("tree_sitter_javascript", "language"),
    ".ts": ("tree_sitter_typescript", "language_typescript"),
    ".tsx": ("tree_sitter_typescript", "language_tsx"),
    ".rs": ("tree_sitter_rust", "language"),
    ".go": ("tree_sitter_go", "language"),
}

# Node types that define symbols in each language
SYMBOL_DEFINITION_NODES: dict[str, set[str]] = {
    "python": {
        "function_definition",
        "class_definition",
        "assignment",
        "global_statement",
    },
    "javascript": {
        "function_declaration",
        "class_declaration",
        "variable_declaration",
        "lexical_declaration",
        "arrow_function",
    },
    "typescript": {
        "function_declaration",
        "class_declaration",
        "variable_declaration",
        "lexical_declaration",
        "type_alias_declaration",
        "interface_declaration",
    },
    "rust": {
        "function_item",
        "struct_item",
        "enum_item",
        "impl_item",
        "trait_item",
        "const_item",
        "static_item",
    },
    "go": {
        "function_declaration",
        "method_declaration",
        "type_declaration",
        "const_declaration",
        "var_declaration",
    },
}

# Node types that represent identifiers/references
IDENTIFIER_NODES: dict[str, set[str]] = {
    "python": {"identifier"},
    "javascript": {"identifier", "property_identifier"},
    "typescript": {"identifier", "property_identifier", "type_identifier"},
    "rust": {"identifier", "type_identifier"},
    "go": {"identifier", "type_identifier"},
}

# Map file extensions to language names
EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
}

# Directories to skip
SKIP_DIRS = {
    "node_modules",
    "__pycache__",
    ".git",
    ".svn",
    ".hg",
    "dist",
    "build",
    "target",
    "venv",
    ".venv",
    "env",
    ".tox",
    ".nox",
    ".pytest_cache",
    ".mypy_cache",
}


def _get_parser(extension: str) -> Optional["Parser"]:
    """Get a tree-sitter parser for the given file extension."""
    if not TREE_SITTER_AVAILABLE:
        return None

    if extension not in LANGUAGE_CONFIG:
        return None

    module_name, lang_func = LANGUAGE_CONFIG[extension]

    try:
        # Import tree_sitter core
        from tree_sitter import Language, Parser

        # Import language module
        lang_module = importlib.import_module(module_name)
        lang_func_callable = getattr(lang_module, lang_func)
        lang_ptr = lang_func_callable()

        # Create Language and Parser
        language = Language(lang_ptr)
        parser = Parser(language)
        return parser
    except ImportError as e:
        log.warning("tree_sitter_import_failed", error=str(e), extension=extension)
        return None
    except Exception as e:
        log.warning("parser_creation_failed", error=str(e), extension=extension)
        return None


def _node_to_dict(node: "Node", include_positions: bool = True) -> dict[str, Any]:
    """Convert a tree-sitter node to a dictionary representation."""
    result: dict[str, Any] = {
        "type": node.type,
    }

    # Include text for leaf nodes (identifiers, literals)
    if node.child_count == 0:
        result["text"] = node.text.decode("utf-8") if node.text else ""

    if include_positions:
        result["start"] = {"line": node.start_point[0] + 1, "column": node.start_point[1]}
        result["end"] = {"line": node.end_point[0] + 1, "column": node.end_point[1]}

    # Recursively process children
    if node.child_count > 0:
        result["children"] = [
            _node_to_dict(child, include_positions) for child in node.children
        ]

    return result


def _find_identifiers(
    node: "Node", target_name: str, results: list[dict[str, Any]]
) -> None:
    """Recursively find all identifier nodes matching target_name."""
    # Check if this is an identifier node with matching name
    if node.type in {"identifier", "property_identifier", "type_identifier"}:
        if node.text and node.text.decode("utf-8") == target_name:
            results.append(
                {
                    "line": node.start_point[0] + 1,
                    "column": node.start_point[1],
                    "end_column": node.end_point[1],
                    "type": node.type,
                    "parent_type": node.parent.type if node.parent else None,
                }
            )

    # Recurse into children
    for child in node.children:
        _find_identifiers(child, target_name, results)


def _find_symbol_definition(
    node: "Node", symbol_name: str, lang: str
) -> Optional["Node"]:
    """Find the definition node for a symbol."""
    definition_types = SYMBOL_DEFINITION_NODES.get(lang, set())

    def _search(n: "Node") -> Optional["Node"]:
        if n.type in definition_types:
            # Check if this definition defines our symbol
            name_node = n.child_by_field_name("name")
            if name_node and name_node.text:
                if name_node.text.decode("utf-8") == symbol_name:
                    return n

            # For assignments in Python, check left side
            if n.type == "assignment" and lang == "python":
                left = n.child_by_field_name("left")
                if left and left.type == "identifier" and left.text:
                    if left.text.decode("utf-8") == symbol_name:
                        return n

        for child in n.children:
            result = _search(child)
            if result:
                return result

        return None

    return _search(node)


def _get_docstring(node: "Node", lang: str, source_bytes: bytes) -> Optional[str]:
    """Extract docstring from a function or class definition."""
    if lang == "python":
        # Python: look for expression_statement > string as first child in body
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
                        # Remove quotes
                        if doc.startswith('"""') or doc.startswith("'''"):
                            return doc[3:-3].strip()
                        elif doc.startswith('"') or doc.startswith("'"):
                            return doc[1:-1].strip()
    elif lang in {"javascript", "typescript"}:
        # JS/TS: look for leading comment
        if node.prev_sibling and node.prev_sibling.type == "comment":
            comment = source_bytes[
                node.prev_sibling.start_byte : node.prev_sibling.end_byte
            ].decode("utf-8")
            # Strip comment markers
            if comment.startswith("/**"):
                return comment[3:-2].strip()
            elif comment.startswith("//"):
                return comment[2:].strip()

    return None


def _get_function_params(node: "Node", lang: str) -> list[dict[str, Any]]:
    """Extract function parameters."""
    params = []

    if lang == "python":
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for child in params_node.children:
                if child.type in {"identifier", "typed_parameter", "default_parameter"}:
                    name = child.child_by_field_name("name") or child
                    if name.text:
                        param_info: dict[str, Any] = {
                            "name": name.text.decode("utf-8")
                        }
                        # Get type annotation if present
                        type_node = child.child_by_field_name("type")
                        if type_node and type_node.text:
                            param_info["type"] = type_node.text.decode("utf-8")
                        params.append(param_info)

    elif lang in {"javascript", "typescript"}:
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for child in params_node.children:
                if child.type in {
                    "identifier",
                    "required_parameter",
                    "optional_parameter",
                }:
                    name = child.child_by_field_name("name") or (
                        child if child.type == "identifier" else None
                    )
                    if name and name.text:
                        param_info = {"name": name.text.decode("utf-8")}
                        type_node = child.child_by_field_name("type")
                        if type_node and type_node.text:
                            param_info["type"] = type_node.text.decode("utf-8")
                        params.append(param_info)

    elif lang == "rust":
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for child in params_node.children:
                if child.type == "parameter":
                    name = child.child_by_field_name("pattern")
                    if name and name.text:
                        param_info = {"name": name.text.decode("utf-8")}
                        type_node = child.child_by_field_name("type")
                        if type_node and type_node.text:
                            param_info["type"] = type_node.text.decode("utf-8")
                        params.append(param_info)

    elif lang == "go":
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for child in params_node.children:
                if child.type == "parameter_declaration":
                    # Go can have multiple names per type
                    type_node = child.child_by_field_name("type")
                    type_str = type_node.text.decode("utf-8") if type_node and type_node.text else None
                    for name_child in child.children:
                        if name_child.type == "identifier":
                            param_info = {"name": name_child.text.decode("utf-8")}
                            if type_str:
                                param_info["type"] = type_str
                            params.append(param_info)

    return params


class ASTParserTool(Tool):
    """Parse source code and return AST structure using tree-sitter."""

    name = "parse_ast"
    description = """Parse source code into an Abstract Syntax Tree (AST) using tree-sitter.

Supports: Python, JavaScript, TypeScript, Rust, Go.

Returns a JSON representation of the AST with node types, names, and positions.
Useful for understanding code structure before refactoring.

Examples:
- parse_ast(file_path="src/main.py") - Parse Python file
- parse_ast(file_path="index.ts", include_positions=false) - Parse without positions"""

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the source file to parse",
            },
            "include_positions": {
                "type": "boolean",
                "description": "Include line/column positions for each node (default: true)",
            },
        },
        "required": ["file_path"],
    }

    async def execute(
        self,
        file_path: str,
        include_positions: bool = True,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute AST parsing."""
        if not TREE_SITTER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="tree-sitter not installed. Install with: pip install sindri[ast]",
            )

        path = self._resolve_path(file_path)
        if not path.exists():
            return ToolResult(
                success=False, output="", error=f"File not found: {path}"
            )

        extension = path.suffix.lower()
        if extension not in LANGUAGE_CONFIG:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsupported file type: {extension}. Supported: {', '.join(LANGUAGE_CONFIG.keys())}",
            )

        try:
            async with aiofiles.open(path, "rb") as f:
                source_bytes = await f.read()

            parser = _get_parser(extension)
            if not parser:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to create parser for {extension}",
                )

            tree = parser.parse(source_bytes)
            ast_dict = _node_to_dict(tree.root_node, include_positions)

            output = json.dumps(ast_dict, indent=2)

            log.info(
                "ast_parsed",
                file=str(path),
                node_type=tree.root_node.type,
                work_dir=str(self.work_dir) if self.work_dir else None,
            )

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "file": str(path),
                    "language": EXT_TO_LANG.get(extension, "unknown"),
                    "root_type": tree.root_node.type,
                },
            )

        except Exception as e:
            log.error("ast_parse_failed", file=str(path), error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class FindReferencesTool(Tool):
    """Find all references to a symbol using AST analysis."""

    name = "find_references"
    description = """Find all references to a symbol across files using AST analysis.

More accurate than grep as it only finds actual code references, not strings or comments.
Supports: Python, JavaScript, TypeScript, Rust, Go.

Examples:
- find_references(symbol_name="calculate_total") - Find all usages
- find_references(symbol_name="UserModel", path="src/") - Search in directory
- find_references(symbol_name="handler", file_types=["ts", "tsx"]) - TypeScript only"""

    parameters = {
        "type": "object",
        "properties": {
            "symbol_name": {
                "type": "string",
                "description": "Name of the symbol to find references for",
            },
            "path": {
                "type": "string",
                "description": "Directory or file to search in (default: current directory)",
            },
            "file_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File extensions to search (e.g., ['py', 'ts']). Empty = all supported",
            },
        },
        "required": ["symbol_name"],
    }

    async def execute(
        self,
        symbol_name: str,
        path: Optional[str] = None,
        file_types: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute reference finding."""
        if not TREE_SITTER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="tree-sitter not installed. Install with: pip install sindri[ast]",
            )

        if not symbol_name or not symbol_name.strip():
            return ToolResult(
                success=False, output="", error="symbol_name cannot be empty"
            )

        search_path = self._resolve_path(path or ".")
        if not search_path.exists():
            return ToolResult(
                success=False, output="", error=f"Path not found: {search_path}"
            )

        # Build list of extensions to search
        if file_types:
            extensions = [f".{ft.lstrip('.')}" for ft in file_types]
            extensions = [e for e in extensions if e in LANGUAGE_CONFIG]
        else:
            extensions = list(LANGUAGE_CONFIG.keys())

        if not extensions:
            return ToolResult(
                success=False,
                output="",
                error="No valid file types specified",
            )

        try:
            all_references: list[dict[str, Any]] = []

            # Find files
            if search_path.is_file():
                files = [search_path]
            else:
                files = []
                for ext in extensions:
                    for file_path in search_path.rglob(f"*{ext}"):
                        if not any(skip in file_path.parts for skip in SKIP_DIRS):
                            files.append(file_path)

            # Search each file
            for file_path in files:
                refs = await self._find_refs_in_file(file_path, symbol_name)
                for ref in refs:
                    ref["file"] = str(file_path)
                    all_references.append(ref)

            # Format output
            if not all_references:
                return ToolResult(
                    success=True,
                    output=f"No references to '{symbol_name}' found",
                    metadata={"count": 0, "files_searched": len(files)},
                )

            output_lines = [f"Found {len(all_references)} reference(s) to '{symbol_name}':", ""]
            for ref in all_references:
                output_lines.append(
                    f"  {ref['file']}:{ref['line']}:{ref['column']} ({ref.get('parent_type', 'unknown')})"
                )

            log.info(
                "references_found",
                symbol=symbol_name,
                count=len(all_references),
                files=len(files),
            )

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "count": len(all_references),
                    "files_searched": len(files),
                    "references": all_references,
                },
            )

        except Exception as e:
            log.error("find_references_failed", symbol=symbol_name, error=str(e))
            return ToolResult(success=False, output="", error=str(e))

    async def _find_refs_in_file(
        self, file_path: Path, symbol_name: str
    ) -> list[dict[str, Any]]:
        """Find references in a single file."""
        extension = file_path.suffix.lower()
        if extension not in LANGUAGE_CONFIG:
            return []

        parser = _get_parser(extension)
        if not parser:
            return []

        try:
            async with aiofiles.open(file_path, "rb") as f:
                source_bytes = await f.read()

            tree = parser.parse(source_bytes)
            results: list[dict[str, Any]] = []
            _find_identifiers(tree.root_node, symbol_name, results)
            return results

        except Exception as e:
            log.warning("parse_file_failed", file=str(file_path), error=str(e))
            return []


class ASTSymbolInfoTool(Tool):
    """Get detailed information about a symbol using AST analysis."""

    name = "symbol_info"
    description = """Get detailed information about a symbol (function, class, variable) in a file.

Returns: symbol type, line number, scope, docstring, parameters (for functions), etc.
Useful for understanding code before refactoring.

Examples:
- symbol_info(file_path="utils.py", symbol_name="calculate_total")
- symbol_info(file_path="models.ts", symbol_name="UserInterface")"""

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the source file",
            },
            "symbol_name": {
                "type": "string",
                "description": "Name of the symbol to get info for",
            },
        },
        "required": ["file_path", "symbol_name"],
    }

    async def execute(
        self,
        file_path: str,
        symbol_name: str,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute symbol info lookup."""
        if not TREE_SITTER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="tree-sitter not installed. Install with: pip install sindri[ast]",
            )

        path = self._resolve_path(file_path)
        if not path.exists():
            return ToolResult(
                success=False, output="", error=f"File not found: {path}"
            )

        extension = path.suffix.lower()
        if extension not in LANGUAGE_CONFIG:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsupported file type: {extension}",
            )

        lang = EXT_TO_LANG.get(extension, "python")

        try:
            async with aiofiles.open(path, "rb") as f:
                source_bytes = await f.read()

            parser = _get_parser(extension)
            if not parser:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to create parser for {extension}",
                )

            tree = parser.parse(source_bytes)
            def_node = _find_symbol_definition(tree.root_node, symbol_name, lang)

            if not def_node:
                return ToolResult(
                    success=True,
                    output=f"Symbol '{symbol_name}' not found as a definition in {path}",
                    metadata={"found": False},
                )

            # Build symbol info
            info: dict[str, Any] = {
                "name": symbol_name,
                "type": def_node.type,
                "line": def_node.start_point[0] + 1,
                "column": def_node.start_point[1],
                "end_line": def_node.end_point[0] + 1,
                "language": lang,
            }

            # Get docstring
            docstring = _get_docstring(def_node, lang, source_bytes)
            if docstring:
                info["docstring"] = docstring

            # Get parameters for functions
            if "function" in def_node.type or "method" in def_node.type:
                params = _get_function_params(def_node, lang)
                if params:
                    info["parameters"] = params

                # Get return type if present
                return_type = def_node.child_by_field_name("return_type")
                if return_type and return_type.text:
                    info["return_type"] = return_type.text.decode("utf-8")

            # Format output
            output_lines = [f"Symbol: {symbol_name}", f"Type: {info['type']}", f"Location: {path}:{info['line']}:{info['column']}"]

            if docstring:
                output_lines.append(f"Docstring: {docstring[:100]}{'...' if len(docstring) > 100 else ''}")

            if "parameters" in info:
                params_str = ", ".join(
                    p["name"] + (f": {p['type']}" if "type" in p else "")
                    for p in info["parameters"]
                )
                output_lines.append(f"Parameters: ({params_str})")

            if "return_type" in info:
                output_lines.append(f"Returns: {info['return_type']}")

            log.info("symbol_info_found", symbol=symbol_name, type=info["type"])

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={"found": True, "info": info},
            )

        except Exception as e:
            log.error("symbol_info_failed", symbol=symbol_name, error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class ASTRefactorRenameTool(Tool):
    """Precise symbol renaming using AST analysis."""

    name = "ast_rename"
    description = """Rename a symbol precisely using AST analysis.

More accurate than regex-based renaming - only renames actual code references,
not strings, comments, or partial matches.

Supports: Python, JavaScript, TypeScript, Rust, Go.

Examples:
- ast_rename(old_name="get_user", new_name="fetch_user") - Rename function
- ast_rename(old_name="UserModel", new_name="User", path="src/") - Rename in directory
- ast_rename(old_name="MAX_RETRIES", new_name="MAX_ATTEMPTS", dry_run=true) - Preview changes"""

    parameters = {
        "type": "object",
        "properties": {
            "old_name": {
                "type": "string",
                "description": "Current name of the symbol",
            },
            "new_name": {
                "type": "string",
                "description": "New name for the symbol",
            },
            "path": {
                "type": "string",
                "description": "Directory or file to search in (default: current directory)",
            },
            "file_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File extensions to search (e.g., ['py', 'ts']). Empty = all supported",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview changes without applying them (default: false)",
            },
        },
        "required": ["old_name", "new_name"],
    }

    async def execute(
        self,
        old_name: str,
        new_name: str,
        path: Optional[str] = None,
        file_types: Optional[list[str]] = None,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute AST-based symbol rename."""
        if not TREE_SITTER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="tree-sitter not installed. Install with: pip install sindri[ast]",
            )

        # Validate inputs
        if not old_name or not old_name.strip():
            return ToolResult(
                success=False, output="", error="old_name cannot be empty"
            )
        if not new_name or not new_name.strip():
            return ToolResult(
                success=False, output="", error="new_name cannot be empty"
            )
        if old_name == new_name:
            return ToolResult(
                success=False, output="", error="old_name and new_name are the same"
            )

        search_path = self._resolve_path(path or ".")
        if not search_path.exists():
            return ToolResult(
                success=False, output="", error=f"Path not found: {search_path}"
            )

        # Build list of extensions
        if file_types:
            extensions = [f".{ft.lstrip('.')}" for ft in file_types]
            extensions = [e for e in extensions if e in LANGUAGE_CONFIG]
        else:
            extensions = list(LANGUAGE_CONFIG.keys())

        if not extensions:
            return ToolResult(
                success=False,
                output="",
                error="No valid file types specified",
            )

        try:
            total_replacements = 0
            modified_files: list[str] = []
            changes: list[str] = []

            # Find files
            if search_path.is_file():
                files = [search_path]
            else:
                files = []
                for ext in extensions:
                    for file_path in search_path.rglob(f"*{ext}"):
                        if not any(skip in file_path.parts for skip in SKIP_DIRS):
                            files.append(file_path)

            # Process each file
            for file_path in files:
                count, file_changes = await self._rename_in_file(
                    file_path, old_name, new_name, dry_run
                )
                if count > 0:
                    total_replacements += count
                    modified_files.append(str(file_path))
                    changes.extend(file_changes)

            if total_replacements == 0:
                return ToolResult(
                    success=True,
                    output=f"No references to '{old_name}' found",
                    metadata={"files_modified": 0, "occurrences": 0},
                )

            action = "Would rename" if dry_run else "Renamed"
            output_lines = [
                f"{action} '{old_name}' -> '{new_name}'",
                f"Total: {total_replacements} occurrence(s) in {len(modified_files)} file(s)",
                "",
            ]
            output_lines.extend(changes)

            log.info(
                "ast_rename_complete",
                old_name=old_name,
                new_name=new_name,
                files=len(modified_files),
                occurrences=total_replacements,
                dry_run=dry_run,
            )

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "files_modified": len(modified_files),
                    "occurrences": total_replacements,
                    "modified_files": modified_files,
                    "dry_run": dry_run,
                },
            )

        except Exception as e:
            log.error("ast_rename_failed", old_name=old_name, error=str(e))
            return ToolResult(success=False, output="", error=str(e))

    async def _rename_in_file(
        self, file_path: Path, old_name: str, new_name: str, dry_run: bool
    ) -> tuple[int, list[str]]:
        """Rename symbol in a single file, returns (count, changes list)."""
        extension = file_path.suffix.lower()
        if extension not in LANGUAGE_CONFIG:
            return 0, []

        parser = _get_parser(extension)
        if not parser:
            return 0, []

        try:
            async with aiofiles.open(file_path, "rb") as f:
                source_bytes = await f.read()

            tree = parser.parse(source_bytes)

            # Find all identifier nodes matching old_name
            refs: list[dict[str, Any]] = []
            _find_identifiers(tree.root_node, old_name, refs)

            if not refs:
                return 0, []

            # Sort by position (reverse order for safe replacement)
            refs.sort(key=lambda r: (r["line"], r["column"]), reverse=True)

            # Build the modified source
            source_text = source_bytes.decode("utf-8")
            lines = source_text.splitlines(keepends=True)

            changes = []
            for ref in refs:
                line_idx = ref["line"] - 1
                col_start = ref["column"]
                col_end = ref["end_column"]

                if 0 <= line_idx < len(lines):
                    line = lines[line_idx]
                    # Replace the identifier
                    new_line = line[:col_start] + new_name + line[col_end:]
                    lines[line_idx] = new_line
                    changes.append(f"  {file_path}:{ref['line']}:{ref['column']}")

            if not dry_run:
                new_source = "".join(lines)
                async with aiofiles.open(file_path, "w") as f:
                    await f.write(new_source)

            return len(refs), changes

        except Exception as e:
            log.warning("rename_in_file_failed", file=str(file_path), error=str(e))
            return 0, []
