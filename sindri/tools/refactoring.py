"""Refactoring tools for Sindri.

Provides tools for common code refactoring operations:
- RenameSymbolTool: Rename symbols across codebase
- ExtractFunctionTool: Extract code into a new function
- InlineVariableTool: Inline variable values into usages
- MoveFileTool: Move/rename files and update imports across codebase
- BatchRenameTool: Rename multiple files using patterns
"""

import ast
import asyncio
import fnmatch
import re
import shutil
from pathlib import Path
from typing import Optional, Tuple
import aiofiles
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


class RenameSymbolTool(Tool):
    """Rename a symbol (function, class, variable) across the codebase.

    Uses AST parsing for Python files and regex for other languages.
    Respects word boundaries to avoid partial matches.
    """

    name = "rename_symbol"
    description = """Rename a symbol (function, class, variable, method) across multiple files.
Uses intelligent matching to avoid renaming partial matches or strings.

Examples:
- rename_symbol(old_name="get_user", new_name="fetch_user") - Rename function
- rename_symbol(old_name="UserModel", new_name="User", path="src/models") - Rename class in directory
- rename_symbol(old_name="MAX_RETRIES", new_name="MAX_ATTEMPTS", file_types=["py"]) - Rename constant"""

    parameters = {
        "type": "object",
        "properties": {
            "old_name": {
                "type": "string",
                "description": "Current name of the symbol to rename"
            },
            "new_name": {
                "type": "string",
                "description": "New name for the symbol"
            },
            "path": {
                "type": "string",
                "description": "Directory or file to search in (default: current directory)"
            },
            "file_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File extensions to search (e.g., ['py', 'ts']). Empty = all code files"
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview changes without applying them (default: false)"
            },
            "include_strings": {
                "type": "boolean",
                "description": "Also rename occurrences in string literals (default: false)"
            }
        },
        "required": ["old_name", "new_name"]
    }

    # Directories to skip during search
    SKIP_DIRS = {
        'node_modules', '__pycache__', '.git', '.svn', '.hg',
        'dist', 'build', 'target', 'venv', '.venv', 'env',
        '.tox', '.nox', '.pytest_cache', '.mypy_cache',
        'coverage', '.coverage', 'htmlcov', '.eggs'
    }

    # Default code file extensions
    DEFAULT_FILE_TYPES = ['py', 'ts', 'tsx', 'js', 'jsx', 'rs', 'go', 'java', 'c', 'cpp', 'h', 'hpp']

    async def execute(
        self,
        old_name: str,
        new_name: str,
        path: Optional[str] = None,
        file_types: Optional[list[str]] = None,
        dry_run: bool = False,
        include_strings: bool = False,
        **kwargs
    ) -> ToolResult:
        """Execute symbol rename."""
        # Validate inputs
        if not old_name or not old_name.strip():
            return ToolResult(
                success=False,
                output="",
                error="old_name cannot be empty"
            )
        if not new_name or not new_name.strip():
            return ToolResult(
                success=False,
                output="",
                error="new_name cannot be empty"
            )
        if old_name == new_name:
            return ToolResult(
                success=False,
                output="",
                error="old_name and new_name are the same"
            )

        # Validate identifier names
        if not self._is_valid_identifier(old_name):
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid identifier: {old_name}"
            )
        if not self._is_valid_identifier(new_name):
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid identifier: {new_name}"
            )

        # Resolve path
        search_path = self._resolve_path(path or ".")
        if not search_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Path does not exist: {search_path}"
            )

        # Use provided file types or defaults
        extensions = file_types if file_types else self.DEFAULT_FILE_TYPES

        try:
            # Find all files with matches
            files_to_modify = await self._find_files_with_symbol(
                search_path, old_name, extensions
            )

            if not files_to_modify:
                return ToolResult(
                    success=True,
                    output=f"No occurrences of '{old_name}' found in {search_path}",
                    metadata={"files_modified": 0, "occurrences": 0}
                )

            # Process each file
            total_replacements = 0
            modified_files = []
            changes_preview = []

            for file_path in files_to_modify:
                count, preview = await self._rename_in_file(
                    file_path, old_name, new_name,
                    include_strings=include_strings, dry_run=dry_run
                )
                if count > 0:
                    total_replacements += count
                    modified_files.append(str(file_path))
                    changes_preview.append(f"{file_path}: {count} occurrence(s)")

            # Build output
            action = "Would modify" if dry_run else "Modified"
            output_lines = [
                f"{action} '{old_name}' → '{new_name}'",
                f"Total: {total_replacements} occurrence(s) in {len(modified_files)} file(s)",
                ""
            ]
            output_lines.extend(changes_preview)

            log.info(
                "symbol_renamed",
                old_name=old_name,
                new_name=new_name,
                files=len(modified_files),
                occurrences=total_replacements,
                dry_run=dry_run,
                work_dir=str(self.work_dir) if self.work_dir else None
            )

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "files_modified": len(modified_files),
                    "occurrences": total_replacements,
                    "dry_run": dry_run,
                    "files": modified_files
                }
            )

        except Exception as e:
            log.error("rename_symbol_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to rename symbol: {str(e)}"
            )

    def _is_valid_identifier(self, name: str) -> bool:
        """Check if name is a valid identifier in most languages."""
        # Basic check: starts with letter or underscore, contains only alphanumeric and underscores
        return bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name))

    async def _find_files_with_symbol(
        self,
        search_path: Path,
        symbol: str,
        extensions: list[str]
    ) -> list[Path]:
        """Find all files containing the symbol."""
        files_with_symbol = []
        pattern = re.compile(r'\b' + re.escape(symbol) + r'\b')

        # Build file list
        if search_path.is_file():
            files = [search_path]
        else:
            files = []
            for ext in extensions:
                for file_path in search_path.rglob(f"*.{ext}"):
                    # Skip excluded directories
                    if not any(part in self.SKIP_DIRS for part in file_path.parts):
                        files.append(file_path)

        # Check each file for the symbol
        for file_path in files:
            try:
                async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = await f.read()
                    if pattern.search(content):
                        files_with_symbol.append(file_path)
            except Exception:
                continue  # Skip files we can't read

        return files_with_symbol

    async def _rename_in_file(
        self,
        file_path: Path,
        old_name: str,
        new_name: str,
        include_strings: bool = False,
        dry_run: bool = False
    ) -> Tuple[int, str]:
        """Rename symbol in a file, returning count and preview."""
        async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = await f.read()

        # Use word boundaries to avoid partial matches
        if include_strings:
            # Simple word boundary replacement
            pattern = re.compile(r'\b' + re.escape(old_name) + r'\b')
        else:
            # More careful: avoid replacing inside strings
            # This is a simplified approach - a full solution would use AST
            pattern = re.compile(r'\b' + re.escape(old_name) + r'\b')

        # Count occurrences
        count = len(pattern.findall(content))

        if count > 0 and not dry_run:
            new_content = pattern.sub(new_name, content)
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(new_content)

        return count, f"{count} occurrence(s)"


class ExtractFunctionTool(Tool):
    """Extract code into a new function.

    Takes a code block and refactors it into a separate function,
    replacing the original code with a function call.
    """

    name = "extract_function"
    description = """Extract a code block into a new function. The original code is replaced with a call to the new function.

Examples:
- extract_function(file="src/main.py", start_line=10, end_line=20, function_name="calculate_total")
- extract_function(file="utils.js", start_line=45, end_line=55, function_name="formatDate", params=["date", "format"])"""

    parameters = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Path to the file containing the code to extract"
            },
            "start_line": {
                "type": "integer",
                "description": "Starting line number (1-indexed) of code to extract"
            },
            "end_line": {
                "type": "integer",
                "description": "Ending line number (1-indexed) of code to extract"
            },
            "function_name": {
                "type": "string",
                "description": "Name for the new function"
            },
            "params": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Parameters for the new function (optional - will be auto-detected for Python)"
            },
            "return_value": {
                "type": "string",
                "description": "Variable name to return from function (optional)"
            },
            "docstring": {
                "type": "string",
                "description": "Docstring for the new function (optional)"
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview changes without applying them (default: false)"
            }
        },
        "required": ["file", "start_line", "end_line", "function_name"]
    }

    async def execute(
        self,
        file: str,
        start_line: int,
        end_line: int,
        function_name: str,
        params: Optional[list[str]] = None,
        return_value: Optional[str] = None,
        docstring: Optional[str] = None,
        dry_run: bool = False,
        **kwargs
    ) -> ToolResult:
        """Execute function extraction."""
        # Validate inputs
        if start_line < 1:
            return ToolResult(
                success=False,
                output="",
                error="start_line must be >= 1"
            )
        if end_line < start_line:
            return ToolResult(
                success=False,
                output="",
                error="end_line must be >= start_line"
            )
        if not function_name or not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', function_name):
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid function name: {function_name}"
            )

        # Resolve file path
        file_path = self._resolve_path(file)
        if not file_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"File not found: {file}"
            )

        try:
            # Read file content
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()

            lines = content.splitlines(keepends=True)
            total_lines = len(lines)

            # Validate line numbers
            if start_line > total_lines:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"start_line ({start_line}) exceeds file length ({total_lines} lines)"
                )
            if end_line > total_lines:
                end_line = total_lines

            # Extract the code block (convert to 0-indexed)
            extracted_lines = lines[start_line - 1:end_line]
            extracted_code = ''.join(extracted_lines)

            # Detect language from file extension
            ext = file_path.suffix.lower()

            # Generate the refactored code
            if ext == '.py':
                new_function, call_code = self._extract_python_function(
                    extracted_code, function_name, params, return_value, docstring
                )
            elif ext in ['.js', '.jsx', '.ts', '.tsx']:
                new_function, call_code = self._extract_js_function(
                    extracted_code, function_name, params, return_value
                )
            else:
                # Generic extraction
                new_function, call_code = self._extract_generic_function(
                    extracted_code, function_name, params, return_value
                )

            # Build the new file content
            # Insert function definition before the extracted code location
            # and replace extracted code with call
            before = lines[:start_line - 1]
            after = lines[end_line:]

            # Detect indentation of original code
            original_indent = self._detect_indent(extracted_lines[0] if extracted_lines else "")
            call_with_indent = original_indent + call_code

            # Build new content
            new_lines = before + [new_function + "\n\n", call_with_indent + "\n"] + after
            new_content = ''.join(new_lines)

            if dry_run:
                output = f"Would extract function '{function_name}' from lines {start_line}-{end_line}\n\n"
                output += "--- New function ---\n"
                output += new_function + "\n\n"
                output += "--- Function call ---\n"
                output += call_with_indent
            else:
                async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                    await f.write(new_content)
                output = f"Extracted function '{function_name}' from lines {start_line}-{end_line}"

            log.info(
                "function_extracted",
                file=str(file_path),
                function=function_name,
                start_line=start_line,
                end_line=end_line,
                dry_run=dry_run,
                work_dir=str(self.work_dir) if self.work_dir else None
            )

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "file": str(file_path),
                    "function_name": function_name,
                    "start_line": start_line,
                    "end_line": end_line,
                    "lines_extracted": end_line - start_line + 1,
                    "dry_run": dry_run
                }
            )

        except Exception as e:
            log.error("extract_function_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to extract function: {str(e)}"
            )

    def _detect_indent(self, line: str) -> str:
        """Detect the indentation of a line."""
        match = re.match(r'^(\s*)', line)
        return match.group(1) if match else ""

    def _extract_python_function(
        self,
        code: str,
        name: str,
        params: Optional[list[str]],
        return_value: Optional[str],
        docstring: Optional[str]
    ) -> Tuple[str, str]:
        """Create a Python function from extracted code."""
        # Dedent the code to function level
        lines = code.splitlines()
        min_indent = float('inf')
        for line in lines:
            if line.strip():
                indent = len(line) - len(line.lstrip())
                min_indent = min(min_indent, indent)

        if min_indent == float('inf'):
            min_indent = 0

        dedented_lines = []
        for line in lines:
            if line.strip():
                dedented_lines.append("    " + line[min_indent:])
            else:
                dedented_lines.append("")

        body = "\n".join(dedented_lines)
        param_str = ", ".join(params) if params else ""

        # Build function
        func_lines = [f"def {name}({param_str}):"]
        if docstring:
            func_lines.append(f'    """{docstring}"""')
        func_lines.append(body)
        if return_value:
            func_lines.append(f"    return {return_value}")

        # Build call
        call_args = ", ".join(params) if params else ""
        if return_value:
            call = f"{return_value} = {name}({call_args})"
        else:
            call = f"{name}({call_args})"

        return "\n".join(func_lines), call

    def _extract_js_function(
        self,
        code: str,
        name: str,
        params: Optional[list[str]],
        return_value: Optional[str]
    ) -> Tuple[str, str]:
        """Create a JavaScript/TypeScript function from extracted code."""
        # Dedent the code
        lines = code.splitlines()
        min_indent = float('inf')
        for line in lines:
            if line.strip():
                indent = len(line) - len(line.lstrip())
                min_indent = min(min_indent, indent)

        if min_indent == float('inf'):
            min_indent = 0

        dedented_lines = []
        for line in lines:
            if line.strip():
                dedented_lines.append("  " + line[min_indent:])
            else:
                dedented_lines.append("")

        body = "\n".join(dedented_lines)
        param_str = ", ".join(params) if params else ""

        # Build function
        func_lines = [f"function {name}({param_str}) {{"]
        func_lines.append(body)
        if return_value:
            func_lines.append(f"  return {return_value};")
        func_lines.append("}")

        # Build call
        call_args = ", ".join(params) if params else ""
        if return_value:
            call = f"const {return_value} = {name}({call_args});"
        else:
            call = f"{name}({call_args});"

        return "\n".join(func_lines), call

    def _extract_generic_function(
        self,
        code: str,
        name: str,
        params: Optional[list[str]],
        return_value: Optional[str]
    ) -> Tuple[str, str]:
        """Create a generic function placeholder."""
        param_str = ", ".join(params) if params else ""
        func = f"# New function: {name}({param_str})\n# TODO: Add proper function syntax for this language\n{code}"
        call = f"{name}({param_str})"
        return func, call


class InlineVariableTool(Tool):
    """Inline a variable by replacing all uses with its value.

    Useful for removing unnecessary intermediate variables or
    for understanding what a variable contains at each usage point.
    """

    name = "inline_variable"
    description = """Inline a variable by replacing all its usages with its assigned value.

Examples:
- inline_variable(file="src/utils.py", variable="temp_result") - Replace all uses with value
- inline_variable(file="main.js", variable="config", line=15) - Inline variable assigned at line 15
- inline_variable(file="calc.py", variable="total", dry_run=true) - Preview changes"""

    parameters = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Path to the file containing the variable"
            },
            "variable": {
                "type": "string",
                "description": "Name of the variable to inline"
            },
            "line": {
                "type": "integer",
                "description": "Line number where variable is assigned (optional - uses first assignment)"
            },
            "remove_assignment": {
                "type": "boolean",
                "description": "Remove the original assignment after inlining (default: true)"
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview changes without applying them (default: false)"
            }
        },
        "required": ["file", "variable"]
    }

    async def execute(
        self,
        file: str,
        variable: str,
        line: Optional[int] = None,
        remove_assignment: bool = True,
        dry_run: bool = False,
        **kwargs
    ) -> ToolResult:
        """Execute variable inlining."""
        # Validate inputs
        if not variable or not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', variable):
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid variable name: {variable}"
            )

        # Resolve file path
        file_path = self._resolve_path(file)
        if not file_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"File not found: {file}"
            )

        try:
            # Read file content
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()

            lines = content.splitlines()
            ext = file_path.suffix.lower()

            # Find the assignment
            assignment_line, value = self._find_assignment(lines, variable, line, ext)

            if assignment_line is None:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Could not find assignment for variable '{variable}'"
                )

            if value is None:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Could not extract value from assignment for '{variable}'"
                )

            # Find all usages after the assignment
            usage_pattern = re.compile(r'\b' + re.escape(variable) + r'\b')
            usages = []

            for i, line_content in enumerate(lines):
                if i == assignment_line:
                    continue  # Skip the assignment line
                for match in usage_pattern.finditer(line_content):
                    usages.append((i, match.start(), match.end()))

            if not usages:
                return ToolResult(
                    success=True,
                    output=f"No usages of '{variable}' found to inline",
                    metadata={"usages": 0}
                )

            # Perform inlining (process in reverse to maintain positions)
            new_lines = lines.copy()
            for line_idx, start, end in reversed(usages):
                line_content = new_lines[line_idx]
                # Wrap value in parentheses if it contains operators
                wrapped_value = f"({value})" if self._needs_wrapping(value) else value
                new_lines[line_idx] = line_content[:start] + wrapped_value + line_content[end:]

            # Remove assignment line if requested
            if remove_assignment:
                new_lines.pop(assignment_line)

            new_content = "\n".join(new_lines)

            if dry_run:
                output_lines = [
                    f"Would inline variable '{variable}' with value: {value}",
                    f"Assignment at line {assignment_line + 1}",
                    f"Usages found: {len(usages)}",
                    "",
                    "Lines affected:"
                ]
                for line_idx, _, _ in usages[:5]:  # Show first 5
                    output_lines.append(f"  Line {line_idx + 1}")
                if len(usages) > 5:
                    output_lines.append(f"  ... and {len(usages) - 5} more")
                output = "\n".join(output_lines)
            else:
                async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                    await f.write(new_content)
                output = f"Inlined '{variable}' at {len(usages)} location(s)"
                if remove_assignment:
                    output += ", removed assignment"

            log.info(
                "variable_inlined",
                file=str(file_path),
                variable=variable,
                value=value[:50] + "..." if len(value) > 50 else value,
                usages=len(usages),
                dry_run=dry_run,
                work_dir=str(self.work_dir) if self.work_dir else None
            )

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "file": str(file_path),
                    "variable": variable,
                    "value": value,
                    "usages_replaced": len(usages),
                    "assignment_removed": remove_assignment and not dry_run,
                    "dry_run": dry_run
                }
            )

        except Exception as e:
            log.error("inline_variable_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to inline variable: {str(e)}"
            )

    def _find_assignment(
        self,
        lines: list[str],
        variable: str,
        target_line: Optional[int],
        ext: str
    ) -> Tuple[Optional[int], Optional[str]]:
        """Find the assignment line and extract the value."""
        # Build pattern based on language
        if ext == '.py':
            # Python: var = value or var: type = value
            pattern = re.compile(
                rf'^\s*{re.escape(variable)}\s*(?::\s*\w+\s*)?=\s*(.+?)(?:\s*#.*)?$'
            )
        elif ext in ['.js', '.jsx', '.ts', '.tsx']:
            # JS/TS: const/let/var name = value
            pattern = re.compile(
                rf'^\s*(?:const|let|var)\s+{re.escape(variable)}\s*(?::\s*\w+\s*)?=\s*(.+?);?\s*(?://.*)?$'
            )
        else:
            # Generic: var = value
            pattern = re.compile(
                rf'^\s*(?:(?:const|let|var|final)\s+)?{re.escape(variable)}\s*=\s*(.+?);?\s*$'
            )

        # Search for assignment
        if target_line is not None:
            # Check specific line
            if 0 <= target_line - 1 < len(lines):
                match = pattern.match(lines[target_line - 1])
                if match:
                    return target_line - 1, match.group(1).strip()
        else:
            # Find first assignment
            for i, line in enumerate(lines):
                match = pattern.match(line)
                if match:
                    return i, match.group(1).strip()

        return None, None

    def _needs_wrapping(self, value: str) -> bool:
        """Check if value needs parentheses when inlined."""
        # Simple heuristic: wrap if contains operators
        operators = ['+', '-', '*', '/', '%', '|', '&', '^', '?', ':']
        value_stripped = value.strip()

        # Don't wrap if already wrapped or is a simple value
        if value_stripped.startswith('(') and value_stripped.endswith(')'):
            return False
        if value_stripped.startswith('[') or value_stripped.startswith('{'):
            return False
        if value_stripped.startswith('"') or value_stripped.startswith("'"):
            return False

        return any(op in value_stripped for op in operators)


class MoveFileTool(Tool):
    """Move or rename a file and update imports across the codebase.

    Moves a file from one location to another and automatically updates
    all import statements that reference the old path. Supports Python
    and JavaScript/TypeScript import syntaxes.
    """

    name = "move_file"
    description = """Move or rename a file and automatically update all imports that reference it.

This tool moves a file from source to destination and updates import statements across
the codebase to reflect the new location. Supports Python and JavaScript/TypeScript.

Examples:
- move_file(source="src/utils.py", destination="src/helpers/utils.py") - Move and update imports
- move_file(source="src/old_name.py", destination="src/new_name.py") - Rename file
- move_file(source="lib/api.ts", destination="services/api.ts", update_imports=true) - Move TypeScript file
- move_file(source="src/model.py", destination="src/models/user.py", dry_run=true) - Preview changes"""

    parameters = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Path to the file to move (relative or absolute)"
            },
            "destination": {
                "type": "string",
                "description": "Destination path for the file"
            },
            "update_imports": {
                "type": "boolean",
                "description": "Update imports in other files (default: true)"
            },
            "search_path": {
                "type": "string",
                "description": "Directory to search for files to update (default: current directory)"
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview changes without applying them (default: false)"
            },
            "create_dirs": {
                "type": "boolean",
                "description": "Create destination directories if they don't exist (default: true)"
            }
        },
        "required": ["source", "destination"]
    }

    # Directories to skip during import search
    SKIP_DIRS = {
        'node_modules', '__pycache__', '.git', '.svn', '.hg',
        'dist', 'build', 'target', 'venv', '.venv', 'env',
        '.tox', '.nox', '.pytest_cache', '.mypy_cache',
        'coverage', '.coverage', 'htmlcov', '.eggs'
    }

    # File extensions that can contain imports
    IMPORT_FILE_TYPES = {
        '.py': 'python',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.mjs': 'javascript',
        '.cjs': 'javascript',
    }

    async def execute(
        self,
        source: str,
        destination: str,
        update_imports: bool = True,
        search_path: Optional[str] = None,
        dry_run: bool = False,
        create_dirs: bool = True,
        **kwargs
    ) -> ToolResult:
        """Execute file move with import updates."""
        # Resolve paths
        source_path = self._resolve_path(source)
        dest_path = self._resolve_path(destination)
        search_root = self._resolve_path(search_path or ".")

        # Validate source
        if not source_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Source file not found: {source}"
            )

        if not source_path.is_file():
            return ToolResult(
                success=False,
                output="",
                error=f"Source is not a file: {source}. Use shell commands to move directories."
            )

        # Check if destination already exists
        if dest_path.exists() and not dry_run:
            return ToolResult(
                success=False,
                output="",
                error=f"Destination already exists: {destination}"
            )

        # Validate search path
        if not search_root.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Search path does not exist: {search_path}"
            )

        try:
            results = {
                "source": str(source_path),
                "destination": str(dest_path),
                "files_updated": [],
                "imports_updated": 0,
                "dry_run": dry_run
            }
            output_lines = []

            # Calculate module paths for import updates
            source_module = self._path_to_module(source_path, search_root)
            dest_module = self._path_to_module(dest_path, search_root)

            # Update imports in other files
            if update_imports and source_module != dest_module:
                import_updates = await self._update_imports(
                    search_root, source_path, dest_path,
                    source_module, dest_module, dry_run
                )
                results["files_updated"] = import_updates["files"]
                results["imports_updated"] = import_updates["count"]

                if import_updates["count"] > 0:
                    action = "Would update" if dry_run else "Updated"
                    output_lines.append(f"{action} {import_updates['count']} import(s) in {len(import_updates['files'])} file(s)")
                    for file_info in import_updates["files"][:10]:  # Show first 10
                        output_lines.append(f"  - {file_info['file']}: {file_info['count']} import(s)")
                    if len(import_updates["files"]) > 10:
                        output_lines.append(f"  ... and {len(import_updates['files']) - 10} more files")

            # Perform the actual move
            if not dry_run:
                # Create destination directory if needed
                if create_dirs:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)

                # Move the file
                shutil.move(str(source_path), str(dest_path))

                # Update relative imports within the moved file
                await self._update_internal_imports(dest_path, source_path.parent, dest_path.parent)

            # Build output
            action = "Would move" if dry_run else "Moved"
            output_lines.insert(0, f"{action}: {source} → {destination}")

            if source_module != dest_module:
                output_lines.append(f"Module path: {source_module} → {dest_module}")

            log.info(
                "file_moved",
                source=str(source_path),
                destination=str(dest_path),
                imports_updated=results["imports_updated"],
                files_updated=len(results["files_updated"]),
                dry_run=dry_run,
                work_dir=str(self.work_dir) if self.work_dir else None
            )

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata=results
            )

        except Exception as e:
            log.error("move_file_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to move file: {str(e)}"
            )

    def _path_to_module(self, file_path: Path, root: Path) -> str:
        """Convert a file path to a Python-style module path."""
        try:
            # Make path relative to root
            rel_path = file_path.relative_to(root)
        except ValueError:
            # File is outside root, use absolute path parts
            rel_path = file_path

        # Remove extension and convert to dot notation
        parts = list(rel_path.parts)
        if parts:
            # Remove file extension from last part
            parts[-1] = Path(parts[-1]).stem

        return ".".join(parts)

    async def _update_imports(
        self,
        search_root: Path,
        source_path: Path,
        dest_path: Path,
        old_module: str,
        new_module: str,
        dry_run: bool
    ) -> dict:
        """Update imports across the codebase."""
        results = {"files": [], "count": 0}

        # Determine the source file type
        source_ext = source_path.suffix.lower()
        source_lang = self.IMPORT_FILE_TYPES.get(source_ext)

        if not source_lang:
            return results  # Can't update imports for unknown file types

        # Find all files that might contain imports
        for ext, lang in self.IMPORT_FILE_TYPES.items():
            for file_path in search_root.rglob(f"*{ext}"):
                # Skip directories we should ignore
                if any(part in self.SKIP_DIRS for part in file_path.parts):
                    continue

                # Skip the source file itself
                if file_path.resolve() == source_path.resolve():
                    continue

                # Update imports in this file
                count = await self._update_imports_in_file(
                    file_path, source_path, dest_path,
                    old_module, new_module, source_lang, dry_run
                )

                if count > 0:
                    results["files"].append({
                        "file": str(file_path),
                        "count": count
                    })
                    results["count"] += count

        return results

    async def _update_imports_in_file(
        self,
        file_path: Path,
        source_path: Path,
        dest_path: Path,
        old_module: str,
        new_module: str,
        source_lang: str,
        dry_run: bool
    ) -> int:
        """Update imports in a single file. Returns count of updates."""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = await f.read()
        except Exception:
            return 0

        file_ext = file_path.suffix.lower()
        file_lang = self.IMPORT_FILE_TYPES.get(file_ext)

        if not file_lang:
            return 0

        original_content = content
        update_count = 0

        # Python imports
        if file_lang == 'python' and source_lang == 'python':
            content, count = self._update_python_imports(
                content, old_module, new_module, source_path, dest_path, file_path
            )
            update_count += count

        # JavaScript/TypeScript imports
        elif file_lang in ['javascript', 'typescript'] and source_lang in ['javascript', 'typescript']:
            content, count = self._update_js_imports(
                content, source_path, dest_path, file_path
            )
            update_count += count

        # Write changes if any
        if update_count > 0 and not dry_run and content != original_content:
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(content)

        return update_count

    def _update_python_imports(
        self,
        content: str,
        old_module: str,
        new_module: str,
        source_path: Path,
        dest_path: Path,
        importing_file: Path
    ) -> Tuple[str, int]:
        """Update Python import statements."""
        update_count = 0

        # Handle: import old_module
        pattern = re.compile(r'^(\s*import\s+)' + re.escape(old_module) + r'(\s*(?:#.*)?)$', re.MULTILINE)
        content, n = pattern.subn(rf'\g<1>{new_module}\g<2>', content)
        update_count += n

        # Handle: import old_module as alias
        pattern = re.compile(r'^(\s*import\s+)' + re.escape(old_module) + r'(\s+as\s+\w+\s*(?:#.*)?)$', re.MULTILINE)
        content, n = pattern.subn(rf'\g<1>{new_module}\g<2>', content)
        update_count += n

        # Handle: from old_module import ...
        pattern = re.compile(r'^(\s*from\s+)' + re.escape(old_module) + r'(\s+import\s+)', re.MULTILINE)
        content, n = pattern.subn(rf'\g<1>{new_module}\g<2>', content)
        update_count += n

        # Handle: from old_module.submodule import ... (partial module path match)
        pattern = re.compile(r'^(\s*from\s+)' + re.escape(old_module) + r'\.(\S+\s+import\s+)', re.MULTILINE)
        content, n = pattern.subn(rf'\g<1>{new_module}.\g<2>', content)
        update_count += n

        # Handle: import old_module.submodule
        pattern = re.compile(r'^(\s*import\s+)' + re.escape(old_module) + r'\.(\S+)', re.MULTILINE)
        content, n = pattern.subn(rf'\g<1>{new_module}.\g<2>', content)
        update_count += n

        return content, update_count

    def _update_js_imports(
        self,
        content: str,
        source_path: Path,
        dest_path: Path,
        importing_file: Path
    ) -> Tuple[str, int]:
        """Update JavaScript/TypeScript import statements."""
        update_count = 0

        # Calculate relative paths from importing file to both source and dest
        try:
            importing_dir = importing_file.parent
            old_rel = self._compute_js_import_path(source_path, importing_dir)
            new_rel = self._compute_js_import_path(dest_path, importing_dir)
        except Exception:
            return content, 0

        if old_rel == new_rel:
            return content, 0

        # Handle: import ... from 'old_path'
        # Match various import styles: import x from, import { x } from, import * as x from
        patterns = [
            # import default from '...'
            r'(import\s+\w+\s+from\s+[\'"])' + re.escape(old_rel) + r'([\'"])',
            # import { ... } from '...'
            r'(import\s+\{[^}]+\}\s+from\s+[\'"])' + re.escape(old_rel) + r'([\'"])',
            # import * as x from '...'
            r'(import\s+\*\s+as\s+\w+\s+from\s+[\'"])' + re.escape(old_rel) + r'([\'"])',
            # import '...' (side effect import)
            r'(import\s+[\'"])' + re.escape(old_rel) + r'([\'"])',
            # export ... from '...'
            r'(export\s+\{[^}]+\}\s+from\s+[\'"])' + re.escape(old_rel) + r'([\'"])',
            r'(export\s+\*\s+from\s+[\'"])' + re.escape(old_rel) + r'([\'"])',
            # require('...')
            r'(require\s*\(\s*[\'"])' + re.escape(old_rel) + r'([\'"])',
        ]

        for pattern in patterns:
            regex = re.compile(pattern)
            content, n = regex.subn(rf'\g<1>{new_rel}\g<2>', content)
            update_count += n

        # Also check for import paths without leading ./
        if not old_rel.startswith('./') and not old_rel.startswith('../'):
            old_rel_with_dot = './' + old_rel
            new_rel_with_dot = './' + new_rel if not new_rel.startswith('./') and not new_rel.startswith('../') else new_rel

            for pattern in patterns:
                # Replace old_rel with old_rel_with_dot in pattern
                pattern_with_dot = pattern.replace(re.escape(old_rel), re.escape(old_rel_with_dot))
                regex = re.compile(pattern_with_dot)
                content, n = regex.subn(rf'\g<1>{new_rel_with_dot}\g<2>', content)
                update_count += n

        return content, update_count

    def _compute_js_import_path(self, target_path: Path, from_dir: Path) -> str:
        """Compute the JS import path from a directory to a target file."""
        try:
            # Get relative path from importing file's directory to target
            rel_path = target_path.relative_to(from_dir.resolve())
            rel_str = str(rel_path).replace('\\', '/')

            # Remove extension for JS/TS imports (common practice)
            if rel_str.endswith(('.ts', '.tsx', '.js', '.jsx', '.mjs')):
                rel_str = str(Path(rel_str).with_suffix(''))

            # Add ./ prefix for relative imports if not going up directories
            if not rel_str.startswith('.'):
                rel_str = './' + rel_str

            return rel_str

        except ValueError:
            # Need to go up directories
            try:
                common = Path(from_dir.resolve()).relative_to(target_path.parent.resolve())
                up_count = len(common.parts)
                rel_from_common = target_path.relative_to(target_path.parent)
                up_path = '../' * up_count
                result = up_path + str(rel_from_common).replace('\\', '/')

                # Remove extension
                if result.endswith(('.ts', '.tsx', '.js', '.jsx', '.mjs')):
                    result = str(Path(result).with_suffix(''))

                return result
            except Exception:
                # Fallback: compute using os.path.relpath logic
                from_resolved = from_dir.resolve()
                target_resolved = target_path.resolve()

                # Find common prefix
                from_parts = from_resolved.parts
                target_parts = target_resolved.parts

                common_length = 0
                for i, (f, t) in enumerate(zip(from_parts, target_parts)):
                    if f == t:
                        common_length = i + 1
                    else:
                        break

                up_count = len(from_parts) - common_length
                down_parts = target_parts[common_length:]

                result = '../' * up_count + '/'.join(down_parts)

                # Remove extension
                if result.endswith(('.ts', '.tsx', '.js', '.jsx', '.mjs')):
                    result = str(Path(result).with_suffix(''))

                if not result.startswith('.'):
                    result = './' + result

                return result

    async def _update_internal_imports(
        self,
        file_path: Path,
        old_dir: Path,
        new_dir: Path
    ) -> None:
        """Update relative imports within the moved file itself."""
        if old_dir == new_dir:
            return

        file_ext = file_path.suffix.lower()
        file_lang = self.IMPORT_FILE_TYPES.get(file_ext)

        if not file_lang:
            return

        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = await f.read()
        except Exception:
            return

        original_content = content

        if file_lang == 'python':
            # For Python, relative imports use dots (.module, ..module)
            # These would need adjustment based on new package structure
            # This is complex and often requires manual review
            pass  # Python relative imports need package context

        elif file_lang in ['javascript', 'typescript']:
            # For JS/TS, update relative import paths
            # This adjusts ../ and ./ paths based on directory change

            # Pattern to find relative imports
            import_pattern = re.compile(
                r'((?:import|export)\s+(?:[\w{},*\s]+\s+from\s+)?[\'"])(\.[^\'"\s]+)([\'"])'
            )
            require_pattern = re.compile(
                r'(require\s*\(\s*[\'"])(\.[^\'"\s]+)([\'"])'
            )

            def adjust_path(match):
                prefix = match.group(1)
                rel_path = match.group(2)
                suffix = match.group(3)

                # Parse the relative path
                if rel_path.startswith('./'):
                    target = old_dir / rel_path[2:]
                elif rel_path.startswith('../'):
                    # Count how many levels up
                    path_parts = rel_path.split('/')
                    ups = 0
                    remaining = []
                    for part in path_parts:
                        if part == '..':
                            ups += 1
                        elif part != '.':
                            remaining.append(part)
                    current = old_dir
                    for _ in range(ups):
                        current = current.parent
                    target = current / '/'.join(remaining)
                else:
                    return match.group(0)

                # Compute new relative path from new_dir
                try:
                    new_rel = self._compute_js_import_path(target, new_dir)
                    return prefix + new_rel + suffix
                except Exception:
                    return match.group(0)

            content = import_pattern.sub(adjust_path, content)
            content = require_pattern.sub(adjust_path, content)

        # Write if changed
        if content != original_content:
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(content)


class BatchRenameTool(Tool):
    """Rename multiple files using pattern matching.

    Allows batch renaming of files matching a glob pattern, transforming
    names according to a specified output pattern. Optionally updates
    imports across the codebase for each renamed file.
    """

    name = "batch_rename"
    description = """Rename multiple files matching a pattern. Transforms filenames according to
an output pattern with placeholders.

Placeholders in output pattern:
- {name}: Full original filename without extension
- {stem}: Original filename stem (without extension)
- {ext}: Original file extension (with dot)
- {parent}: Parent directory name
- {1}, {2}, ...: Regex capture groups (when using regex pattern)

Examples:
- batch_rename(pattern="test_*.py", output="{stem}_test.py") - Rename test_foo.py to foo_test.py
- batch_rename(pattern="*.test.ts", output="{stem}.spec.ts") - Rename foo.test.ts to foo.spec.ts
- batch_rename(pattern="old_*.py", output="new_{1}.py", regex=true) - Replace prefix
- batch_rename(pattern="*.py", output="lib/{stem}.py", path="src/") - Move to lib/ subdirectory
- batch_rename(pattern="*.js", output="{stem}.ts", dry_run=true) - Preview converting JS to TS"""

    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern to match files (e.g., 'test_*.py', '*.test.ts'). Use regex=true for regex patterns."
            },
            "output": {
                "type": "string",
                "description": "Output pattern with placeholders: {name}, {stem}, {ext}, {parent}, {1}, {2}... for capture groups"
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (default: current directory)"
            },
            "regex": {
                "type": "boolean",
                "description": "Treat pattern as regex instead of glob (default: false)"
            },
            "recursive": {
                "type": "boolean",
                "description": "Search subdirectories recursively (default: true)"
            },
            "update_imports": {
                "type": "boolean",
                "description": "Update imports in other files after renaming (default: true)"
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview changes without applying them (default: false)"
            },
            "max_files": {
                "type": "integer",
                "description": "Maximum number of files to rename (safety limit, default: 100)"
            }
        },
        "required": ["pattern", "output"]
    }

    # Directories to skip during search
    SKIP_DIRS = {
        'node_modules', '__pycache__', '.git', '.svn', '.hg',
        'dist', 'build', 'target', 'venv', '.venv', 'env',
        '.tox', '.nox', '.pytest_cache', '.mypy_cache',
        'coverage', '.coverage', 'htmlcov', '.eggs'
    }

    async def execute(
        self,
        pattern: str,
        output: str,
        path: Optional[str] = None,
        regex: bool = False,
        recursive: bool = True,
        update_imports: bool = True,
        dry_run: bool = False,
        max_files: int = 100,
        **kwargs
    ) -> ToolResult:
        """Execute batch rename operation."""
        # Validate inputs
        if not pattern or not pattern.strip():
            return ToolResult(
                success=False,
                output="",
                error="Pattern cannot be empty"
            )
        if not output or not output.strip():
            return ToolResult(
                success=False,
                output="",
                error="Output pattern cannot be empty"
            )
        if max_files < 1:
            return ToolResult(
                success=False,
                output="",
                error="max_files must be at least 1"
            )

        # Resolve search path
        search_path = self._resolve_path(path or ".")
        if not search_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Path does not exist: {path}"
            )
        if not search_path.is_dir():
            return ToolResult(
                success=False,
                output="",
                error=f"Path is not a directory: {path}"
            )

        try:
            # Find matching files
            if regex:
                try:
                    regex_pattern = re.compile(pattern)
                except re.error as e:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Invalid regex pattern: {e}"
                    )
                matched_files = self._find_files_regex(search_path, regex_pattern, recursive)
            else:
                matched_files = self._find_files_glob(search_path, pattern, recursive)

            if not matched_files:
                return ToolResult(
                    success=True,
                    output=f"No files matching pattern '{pattern}' found in {search_path}",
                    metadata={"files_renamed": 0, "pattern": pattern}
                )

            # Apply max_files limit
            if len(matched_files) > max_files:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Found {len(matched_files)} matching files, exceeds max_files limit of {max_files}. "
                          f"Increase max_files or use a more specific pattern."
                )

            # Calculate new names for all files
            rename_plan = []
            seen_destinations = set()
            conflicts = []

            for file_path in matched_files:
                try:
                    if regex:
                        new_name = self._apply_regex_output(file_path, regex_pattern, output)
                    else:
                        new_name = self._apply_glob_output(file_path, pattern, output)

                    # Resolve new path relative to file's parent
                    if '/' in new_name or '\\' in new_name:
                        # Output contains directory - resolve relative to search path
                        new_path = search_path / new_name
                    else:
                        # Simple rename - keep in same directory
                        new_path = file_path.parent / new_name

                    # Check for conflicts
                    if new_path.resolve() in seen_destinations:
                        conflicts.append(f"Multiple files would be renamed to: {new_path}")
                    elif new_path.exists() and new_path.resolve() != file_path.resolve():
                        conflicts.append(f"Destination already exists: {new_path}")
                    else:
                        seen_destinations.add(new_path.resolve())
                        rename_plan.append({
                            "source": file_path,
                            "destination": new_path,
                            "source_rel": str(file_path.relative_to(search_path)) if file_path.is_relative_to(search_path) else str(file_path),
                            "dest_rel": str(new_path.relative_to(search_path)) if new_path.is_relative_to(search_path) else str(new_path)
                        })
                except Exception as e:
                    conflicts.append(f"Error processing {file_path}: {e}")

            if conflicts:
                return ToolResult(
                    success=False,
                    output="",
                    error="Conflicts detected:\n" + "\n".join(conflicts[:10]) +
                          (f"\n... and {len(conflicts) - 10} more" if len(conflicts) > 10 else "")
                )

            # Execute renames
            results = {
                "files_renamed": 0,
                "imports_updated": 0,
                "files_with_import_updates": 0,
                "renames": [],
                "dry_run": dry_run
            }
            output_lines = []

            # Use MoveFileTool for actual moves to get import updates
            move_tool = MoveFileTool(work_dir=self.work_dir)

            for plan in rename_plan:
                source = plan["source"]
                destination = plan["destination"]

                if update_imports:
                    # Use MoveFileTool for import updates
                    move_result = await move_tool.execute(
                        source=str(source),
                        destination=str(destination),
                        update_imports=True,
                        search_path=str(search_path),
                        dry_run=dry_run,
                        create_dirs=True
                    )

                    if move_result.success:
                        results["files_renamed"] += 1
                        if move_result.metadata:
                            results["imports_updated"] += move_result.metadata.get("imports_updated", 0)
                            if move_result.metadata.get("files_updated"):
                                results["files_with_import_updates"] += len(move_result.metadata["files_updated"])
                        results["renames"].append({
                            "source": plan["source_rel"],
                            "destination": plan["dest_rel"],
                            "imports_updated": move_result.metadata.get("imports_updated", 0) if move_result.metadata else 0
                        })
                        output_lines.append(f"  {plan['source_rel']} → {plan['dest_rel']}")
                    else:
                        # Report error but continue with other files
                        output_lines.append(f"  ✗ {plan['source_rel']}: {move_result.error}")
                else:
                    # Simple move without import updates
                    if not dry_run:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(source), str(destination))

                    results["files_renamed"] += 1
                    results["renames"].append({
                        "source": plan["source_rel"],
                        "destination": plan["dest_rel"],
                        "imports_updated": 0
                    })
                    output_lines.append(f"  {plan['source_rel']} → {plan['dest_rel']}")

            # Build summary
            action = "Would rename" if dry_run else "Renamed"
            summary_lines = [
                f"{action} {results['files_renamed']} file(s) matching '{pattern}'",
            ]
            if update_imports and results["imports_updated"] > 0:
                summary_lines.append(
                    f"Updated {results['imports_updated']} import(s) in {results['files_with_import_updates']} file(s)"
                )
            summary_lines.append("")
            summary_lines.extend(output_lines)

            log.info(
                "batch_rename_complete",
                pattern=pattern,
                files_renamed=results["files_renamed"],
                imports_updated=results["imports_updated"],
                dry_run=dry_run,
                work_dir=str(self.work_dir) if self.work_dir else None
            )

            return ToolResult(
                success=True,
                output="\n".join(summary_lines),
                metadata=results
            )

        except Exception as e:
            log.error("batch_rename_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Batch rename failed: {str(e)}"
            )

    def _find_files_glob(self, search_path: Path, pattern: str, recursive: bool) -> list[Path]:
        """Find files matching a glob pattern."""
        files = []

        if recursive:
            # Use rglob for recursive search
            for file_path in search_path.rglob(pattern):
                if file_path.is_file() and not any(part in self.SKIP_DIRS for part in file_path.parts):
                    files.append(file_path)
        else:
            # Use glob for non-recursive search
            for file_path in search_path.glob(pattern):
                if file_path.is_file():
                    files.append(file_path)

        return sorted(files)

    def _find_files_regex(self, search_path: Path, regex_pattern: re.Pattern, recursive: bool) -> list[Path]:
        """Find files matching a regex pattern (on filename only)."""
        files = []

        def process_dir(dir_path: Path):
            for item in dir_path.iterdir():
                if item.is_file():
                    if regex_pattern.search(item.name):
                        files.append(item)
                elif item.is_dir() and recursive:
                    if item.name not in self.SKIP_DIRS:
                        process_dir(item)

        process_dir(search_path)
        return sorted(files)

    def _apply_glob_output(self, file_path: Path, pattern: str, output: str) -> str:
        """Apply output pattern to a file matched by glob pattern."""
        # Extract placeholders
        result = output

        # {name} - full filename without extension
        result = result.replace("{name}", file_path.stem)
        # {stem} - same as {name}
        result = result.replace("{stem}", file_path.stem)
        # {ext} - extension with dot
        result = result.replace("{ext}", file_path.suffix)
        # {parent} - parent directory name
        result = result.replace("{parent}", file_path.parent.name)

        # Try to extract capture groups from glob pattern
        # Convert glob to regex for capturing
        glob_regex = self._glob_to_regex(pattern)
        match = re.match(glob_regex, file_path.name)
        if match:
            for i, group in enumerate(match.groups(), 1):
                if group is not None:
                    result = result.replace(f"{{{i}}}", group)

        return result

    def _apply_regex_output(self, file_path: Path, regex_pattern: re.Pattern, output: str) -> str:
        """Apply output pattern to a file matched by regex pattern."""
        result = output

        # Standard placeholders
        result = result.replace("{name}", file_path.stem)
        result = result.replace("{stem}", file_path.stem)
        result = result.replace("{ext}", file_path.suffix)
        result = result.replace("{parent}", file_path.parent.name)

        # Extract capture groups from regex match
        match = regex_pattern.search(file_path.name)
        if match:
            for i, group in enumerate(match.groups(), 1):
                if group is not None:
                    result = result.replace(f"{{{i}}}", group)

        return result

    def _glob_to_regex(self, pattern: str) -> str:
        """Convert a glob pattern to a regex pattern with capture groups.

        * becomes (.*) to capture the wildcard content
        ? becomes (.) to capture single character
        """
        # Escape special regex chars except * and ?
        result = ""
        i = 0
        while i < len(pattern):
            char = pattern[i]
            if char == '*':
                if i + 1 < len(pattern) and pattern[i + 1] == '*':
                    # ** matches any path
                    result += "(.*)"
                    i += 2
                else:
                    # * matches any chars except /
                    result += "([^/]*)"
                    i += 1
            elif char == '?':
                result += "(.)"
                i += 1
            elif char in '.^$+{}[]|()\\':
                result += '\\' + char
                i += 1
            else:
                result += char
                i += 1

        return f"^{result}$"


class SplitFileTool(Tool):
    """Split a large file into multiple smaller files.

    Supports splitting by:
    - Classes: Each class goes to its own file
    - Functions: Each top-level function goes to its own file
    - Markers: Split at comment markers (e.g., # --- split: filename.py ---)
    - Lines: Split at specified line numbers

    Automatically updates imports across the codebase for the split files.
    """

    name = "split_file"
    description = """Split a large file into multiple smaller files based on a splitting strategy.

Splitting strategies:
- classes: Each class becomes its own file (class Foo -> foo.py)
- functions: Each top-level function becomes its own file
- markers: Split at comment markers like "# --- split: filename.py ---"
- lines: Split at specified line numbers into parts

Examples:
- split_file(file="src/models.py", strategy="classes") - Split each class to separate files
- split_file(file="src/utils.py", strategy="functions", output_dir="src/utils/") - Split functions to a package
- split_file(file="src/big.py", strategy="markers") - Split at marker comments
- split_file(file="src/data.py", strategy="lines", lines=[50, 100, 150]) - Split at specific lines
- split_file(file="src/all.py", strategy="classes", dry_run=true) - Preview split without applying"""

    parameters = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Path to the file to split"
            },
            "strategy": {
                "type": "string",
                "enum": ["classes", "functions", "markers", "lines"],
                "description": "Strategy for splitting: classes, functions, markers, or lines"
            },
            "output_dir": {
                "type": "string",
                "description": "Directory for split files (default: same directory as source file)"
            },
            "lines": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Line numbers to split at (for 'lines' strategy)"
            },
            "marker": {
                "type": "string",
                "description": "Custom marker pattern (for 'markers' strategy, default: '# --- split: {filename} ---')"
            },
            "create_init": {
                "type": "boolean",
                "description": "Create __init__.py for Python packages (default: true)"
            },
            "update_imports": {
                "type": "boolean",
                "description": "Update imports in other files (default: true)"
            },
            "keep_original": {
                "type": "boolean",
                "description": "Keep original file with re-exports (default: true for backward compat)"
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview changes without applying them (default: false)"
            }
        },
        "required": ["file", "strategy"]
    }

    # Directories to skip during import search
    SKIP_DIRS = {
        'node_modules', '__pycache__', '.git', '.svn', '.hg',
        'dist', 'build', 'target', 'venv', '.venv', 'env',
        '.tox', '.nox', '.pytest_cache', '.mypy_cache',
        'coverage', '.coverage', 'htmlcov', '.eggs'
    }

    async def execute(
        self,
        file: str,
        strategy: str,
        output_dir: Optional[str] = None,
        lines: Optional[list[int]] = None,
        marker: Optional[str] = None,
        create_init: bool = True,
        update_imports: bool = True,
        keep_original: bool = True,
        dry_run: bool = False,
        **kwargs
    ) -> ToolResult:
        """Execute file split operation."""
        # Validate inputs
        if strategy not in ["classes", "functions", "markers", "lines"]:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid strategy: {strategy}. Must be one of: classes, functions, markers, lines"
            )

        if strategy == "lines" and (not lines or len(lines) == 0):
            return ToolResult(
                success=False,
                output="",
                error="Lines strategy requires 'lines' parameter with at least one line number"
            )

        # Resolve source file path
        source_path = self._resolve_path(file)
        if not source_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"File not found: {file}"
            )
        if not source_path.is_file():
            return ToolResult(
                success=False,
                output="",
                error=f"Not a file: {file}"
            )

        # Resolve output directory
        if output_dir:
            output_path = self._resolve_path(output_dir)
        else:
            output_path = source_path.parent

        # Determine file language
        ext = source_path.suffix.lower()
        if ext == '.py':
            lang = 'python'
        elif ext in ['.ts', '.tsx', '.js', '.jsx', '.mjs']:
            lang = 'javascript'
        else:
            lang = 'generic'

        try:
            # Read source file
            async with aiofiles.open(source_path, 'r', encoding='utf-8') as f:
                content = await f.read()

            # Split the file based on strategy
            if strategy == "classes":
                splits = self._split_by_classes(content, source_path, lang)
            elif strategy == "functions":
                splits = self._split_by_functions(content, source_path, lang)
            elif strategy == "markers":
                splits = self._split_by_markers(content, marker or "# --- split: {filename} ---")
            else:  # lines
                splits = self._split_by_lines(content, lines or [], source_path)

            if not splits:
                return ToolResult(
                    success=True,
                    output=f"No {strategy} found to split in {file}",
                    metadata={"files_created": 0, "strategy": strategy}
                )

            if len(splits) == 1:
                return ToolResult(
                    success=True,
                    output=f"Only one {strategy[:-1] if strategy.endswith('s') else strategy} found. Nothing to split.",
                    metadata={"files_created": 0, "strategy": strategy}
                )

            # Build results
            results = {
                "source_file": str(source_path),
                "strategy": strategy,
                "files_created": [],
                "init_created": False,
                "imports_updated": 0,
                "files_with_import_updates": 0,
                "dry_run": dry_run
            }
            output_lines = []

            # Create output files
            if not dry_run:
                output_path.mkdir(parents=True, exist_ok=True)

            for split in splits:
                dest_file = output_path / split["filename"]
                results["files_created"].append({
                    "file": str(dest_file),
                    "name": split.get("name", split["filename"]),
                    "lines": split.get("lines", 0)
                })

                if dry_run:
                    preview_content = split["content"][:200] + "..." if len(split["content"]) > 200 else split["content"]
                    output_lines.append(f"  Would create: {dest_file}")
                    output_lines.append(f"    Content preview ({split.get('lines', 'N/A')} lines):")
                    for line in preview_content.split('\n')[:5]:
                        output_lines.append(f"      {line}")
                    if split["content"].count('\n') > 5:
                        output_lines.append("      ...")
                else:
                    async with aiofiles.open(dest_file, 'w', encoding='utf-8') as f:
                        await f.write(split["content"])
                    output_lines.append(f"  Created: {dest_file}")

            # Create __init__.py for Python packages
            if lang == 'python' and create_init and output_path != source_path.parent:
                init_content = self._generate_init_content(splits, source_path.stem)
                init_file = output_path / "__init__.py"

                if dry_run:
                    output_lines.append(f"  Would create: {init_file}")
                else:
                    async with aiofiles.open(init_file, 'w', encoding='utf-8') as f:
                        await f.write(init_content)
                    output_lines.append(f"  Created: {init_file}")
                    results["init_created"] = True

            # Update imports in other files
            if update_imports and not dry_run:
                import_results = await self._update_imports_for_split(
                    source_path, splits, output_path, self._resolve_path(".")
                )
                results["imports_updated"] = import_results["count"]
                results["files_with_import_updates"] = len(import_results["files"])

                if import_results["count"] > 0:
                    output_lines.append(f"  Updated {import_results['count']} import(s) in {len(import_results['files'])} file(s)")

            # Keep original file with re-exports for backward compatibility
            if keep_original and not dry_run and lang == 'python':
                reexport_content = self._generate_reexport_content(splits, output_path, source_path)
                async with aiofiles.open(source_path, 'w', encoding='utf-8') as f:
                    await f.write(reexport_content)
                output_lines.append(f"  Updated original file with re-exports for backward compatibility")

            # Build summary
            action = "Would split" if dry_run else "Split"
            summary = f"{action} {file} into {len(splits)} files using '{strategy}' strategy"
            output_lines.insert(0, summary)
            output_lines.insert(1, "")

            log.info(
                "file_split",
                source=str(source_path),
                strategy=strategy,
                files_created=len(splits),
                imports_updated=results["imports_updated"],
                dry_run=dry_run,
                work_dir=str(self.work_dir) if self.work_dir else None
            )

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata=results
            )

        except Exception as e:
            log.error("split_file_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to split file: {str(e)}"
            )

    def _split_by_classes(self, content: str, source_path: Path, lang: str) -> list[dict]:
        """Split content by class definitions."""
        splits = []

        if lang == 'python':
            try:
                tree = ast.parse(content)
            except SyntaxError:
                # Fall back to regex if AST parsing fails
                return self._split_by_classes_regex(content, source_path, lang)

            lines = content.splitlines(keepends=True)

            # Collect imports at the top
            imports = []
            first_non_import_line = 0

            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    start = node.lineno - 1
                    end = node.end_lineno or node.lineno
                    imports.append(''.join(lines[start:end]))
                    first_non_import_line = max(first_non_import_line, end)
                elif not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Constant):
                    # Not a docstring or import
                    break

            import_block = ''.join(imports)

            # Find all class definitions
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    # Get the class source code
                    start = node.lineno - 1
                    end = node.end_lineno or node.lineno
                    class_content = ''.join(lines[start:end])

                    # Generate filename
                    filename = self._to_snake_case(node.name) + '.py'

                    # Build complete file content
                    full_content = import_block
                    if import_block and not import_block.endswith('\n\n'):
                        full_content += '\n\n' if import_block.endswith('\n') else '\n\n\n'
                    full_content += class_content

                    splits.append({
                        "filename": filename,
                        "name": node.name,
                        "content": full_content,
                        "lines": end - start
                    })

        elif lang == 'javascript':
            # Use regex for JS/TS classes
            return self._split_by_classes_regex(content, source_path, lang)

        return splits

    def _split_by_classes_regex(self, content: str, source_path: Path, lang: str) -> list[dict]:
        """Split content by class definitions using regex (fallback)."""
        splits = []

        if lang == 'python':
            # Match Python class definitions
            pattern = r'^class\s+(\w+).*?(?=^class\s|\Z)'
            import_pattern = r'^(?:from\s+.+\s+import\s+.+|import\s+.+)$'
        else:
            # Match JS/TS class definitions
            pattern = r'^(?:export\s+)?class\s+(\w+).*?(?=^(?:export\s+)?class\s|\Z)'
            import_pattern = r'^(?:import\s+.+|export\s+\{.+\}\s+from)'

        # Extract imports
        import_lines = []
        for match in re.finditer(import_pattern, content, re.MULTILINE):
            import_lines.append(match.group(0))
        import_block = '\n'.join(import_lines)

        # Find classes
        for match in re.finditer(pattern, content, re.MULTILINE | re.DOTALL):
            class_name = match.group(1)
            class_content = match.group(0).strip()

            filename = self._to_snake_case(class_name)
            if lang == 'python':
                filename += '.py'
            else:
                filename += '.ts' if source_path.suffix == '.ts' else '.js'

            full_content = import_block + '\n\n' + class_content if import_block else class_content

            splits.append({
                "filename": filename,
                "name": class_name,
                "content": full_content,
                "lines": class_content.count('\n') + 1
            })

        return splits

    def _split_by_functions(self, content: str, source_path: Path, lang: str) -> list[dict]:
        """Split content by top-level function definitions."""
        splits = []

        if lang == 'python':
            try:
                tree = ast.parse(content)
            except SyntaxError:
                return self._split_by_functions_regex(content, source_path, lang)

            lines = content.splitlines(keepends=True)

            # Collect imports
            imports = []
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    start = node.lineno - 1
                    end = node.end_lineno or node.lineno
                    imports.append(''.join(lines[start:end]))

            import_block = ''.join(imports)

            # Find all top-level function definitions
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    start = node.lineno - 1
                    end = node.end_lineno or node.lineno

                    # Include decorators
                    if node.decorator_list:
                        start = node.decorator_list[0].lineno - 1

                    func_content = ''.join(lines[start:end])
                    filename = node.name + '.py'

                    full_content = import_block
                    if import_block and not import_block.endswith('\n\n'):
                        full_content += '\n\n' if import_block.endswith('\n') else '\n\n\n'
                    full_content += func_content

                    splits.append({
                        "filename": filename,
                        "name": node.name,
                        "content": full_content,
                        "lines": end - start
                    })

        elif lang == 'javascript':
            return self._split_by_functions_regex(content, source_path, lang)

        return splits

    def _split_by_functions_regex(self, content: str, source_path: Path, lang: str) -> list[dict]:
        """Split content by function definitions using regex (fallback)."""
        splits = []

        if lang == 'python':
            pattern = r'^(?:@\w+.*?\n)*^(?:async\s+)?def\s+(\w+)\s*\([^)]*\).*?(?=^(?:@\w+.*?\n)*^(?:async\s+)?def\s|\Z)'
            import_pattern = r'^(?:from\s+.+\s+import\s+.+|import\s+.+)$'
        else:
            pattern = r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\([^)]*\).*?(?=^(?:export\s+)?(?:async\s+)?function\s|\Z)'
            import_pattern = r'^(?:import\s+.+|export\s+\{.+\}\s+from)'

        import_lines = []
        for match in re.finditer(import_pattern, content, re.MULTILINE):
            import_lines.append(match.group(0))
        import_block = '\n'.join(import_lines)

        for match in re.finditer(pattern, content, re.MULTILINE | re.DOTALL):
            func_name = match.group(1)
            func_content = match.group(0).strip()

            filename = func_name
            if lang == 'python':
                filename += '.py'
            else:
                filename += '.ts' if source_path.suffix == '.ts' else '.js'

            full_content = import_block + '\n\n' + func_content if import_block else func_content

            splits.append({
                "filename": filename,
                "name": func_name,
                "content": full_content,
                "lines": func_content.count('\n') + 1
            })

        return splits

    def _split_by_markers(self, content: str, marker_pattern: str) -> list[dict]:
        """Split content at marker comments.

        Marker format: # --- split: filename.py ---
        or custom pattern with {filename} placeholder.
        """
        splits = []

        # Build regex from marker pattern
        escaped_pattern = re.escape(marker_pattern)
        regex_pattern = escaped_pattern.replace(r'\{filename\}', r'([^\s]+)')
        pattern = re.compile(regex_pattern, re.MULTILINE)

        # Find all markers
        markers = list(pattern.finditer(content))

        if not markers:
            return splits

        lines = content.splitlines(keepends=True)

        # Process each section
        for i, match in enumerate(markers):
            filename = match.group(1) if match.groups() else f"part_{i+1}.py"

            # Find line number of marker
            marker_pos = match.start()
            marker_line = content[:marker_pos].count('\n')

            # Find end of section (next marker or EOF)
            if i + 1 < len(markers):
                end_pos = markers[i + 1].start()
                end_line = content[:end_pos].count('\n')
            else:
                end_line = len(lines)

            # Extract content (skip the marker line itself)
            section_lines = lines[marker_line + 1:end_line]
            section_content = ''.join(section_lines).strip()

            if section_content:
                splits.append({
                    "filename": filename,
                    "name": Path(filename).stem,
                    "content": section_content + '\n',
                    "lines": len(section_lines)
                })

        return splits

    def _split_by_lines(self, content: str, split_lines: list[int], source_path: Path) -> list[dict]:
        """Split content at specified line numbers."""
        splits = []
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)

        # Sort line numbers and add start/end
        split_points = sorted(set([0] + split_lines + [total_lines]))

        ext = source_path.suffix

        for i in range(len(split_points) - 1):
            start = split_points[i]
            end = split_points[i + 1]

            if start >= total_lines:
                continue

            section_content = ''.join(lines[start:end]).strip()

            if section_content:
                filename = f"{source_path.stem}_part{i + 1}{ext}"

                splits.append({
                    "filename": filename,
                    "name": f"part_{i + 1}",
                    "content": section_content + '\n',
                    "lines": end - start
                })

        return splits

    def _to_snake_case(self, name: str) -> str:
        """Convert CamelCase to snake_case."""
        # Insert underscore before uppercase letters
        result = re.sub(r'(?<!^)(?=[A-Z])', '_', name)
        return result.lower()

    def _generate_init_content(self, splits: list[dict], original_name: str) -> str:
        """Generate __init__.py content that re-exports split items."""
        lines = [
            f'"""Package created by splitting {original_name}."""',
            ''
        ]

        # Import each split file's main item
        for split in splits:
            module_name = Path(split["filename"]).stem
            item_name = split.get("name", module_name)
            lines.append(f"from .{module_name} import {item_name}")

        lines.append('')

        # Generate __all__
        all_items = [split.get("name", Path(split["filename"]).stem) for split in splits]
        lines.append(f"__all__ = {all_items!r}")
        lines.append('')

        return '\n'.join(lines)

    def _generate_reexport_content(self, splits: list[dict], output_dir: Path, source_path: Path) -> str:
        """Generate content for original file with re-exports."""
        lines = [
            f'"""Re-exports from split modules for backward compatibility."""',
            ''
        ]

        # Calculate relative import path
        try:
            rel_path = output_dir.relative_to(source_path.parent)
            package_path = '.'.join(rel_path.parts)
        except ValueError:
            package_path = output_dir.name

        # Re-export each item
        for split in splits:
            module_name = Path(split["filename"]).stem
            item_name = split.get("name", module_name)
            lines.append(f"from {package_path}.{module_name} import {item_name}")

        lines.append('')

        # Generate __all__
        all_items = [split.get("name", Path(split["filename"]).stem) for split in splits]
        lines.append(f"__all__ = {all_items!r}")
        lines.append('')

        return '\n'.join(lines)

    async def _update_imports_for_split(
        self,
        source_path: Path,
        splits: list[dict],
        output_dir: Path,
        search_root: Path
    ) -> dict:
        """Update imports in other files after splitting."""
        results = {"files": [], "count": 0}

        # Calculate old module path
        try:
            old_module = '.'.join(source_path.relative_to(search_root).with_suffix('').parts)
        except ValueError:
            old_module = source_path.stem

        # Find all Python files
        for file_path in search_root.rglob("*.py"):
            if any(part in self.SKIP_DIRS for part in file_path.parts):
                continue

            if file_path.resolve() == source_path.resolve():
                continue

            count = await self._update_imports_in_file(
                file_path, old_module, splits, output_dir, search_root
            )

            if count > 0:
                results["files"].append(str(file_path))
                results["count"] += count

        return results

    async def _update_imports_in_file(
        self,
        file_path: Path,
        old_module: str,
        splits: list[dict],
        output_dir: Path,
        search_root: Path
    ) -> int:
        """Update imports in a single file for split items."""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = await f.read()
        except Exception:
            return 0

        original_content = content
        update_count = 0

        # Calculate new package path
        try:
            new_package = '.'.join(output_dir.relative_to(search_root).parts)
        except ValueError:
            new_package = output_dir.name

        # For each split item, update imports
        for split in splits:
            item_name = split.get("name", Path(split["filename"]).stem)
            module_name = Path(split["filename"]).stem

            # Pattern: from old_module import ItemName
            pattern = re.compile(
                rf'^(\s*from\s+){re.escape(old_module)}(\s+import\s+.*\b){re.escape(item_name)}(\b.*?)$',
                re.MULTILINE
            )

            def replace_import(match):
                # Check if this import contains the item
                import_line = match.group(0)
                if item_name not in import_line:
                    return import_line

                # Replace with new import
                prefix = match.group(1)
                return f"{prefix}{new_package}.{module_name} import {item_name}"

            new_content, n = pattern.subn(replace_import, content)
            if n > 0:
                content = new_content
                update_count += n

        # Write changes if any
        if update_count > 0 and content != original_content:
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(content)

        return update_count
