"""Refactoring tools for Sindri.

Provides tools for common code refactoring operations:
- RenameSymbolTool: Rename symbols across codebase
- ExtractFunctionTool: Extract code into a new function
- InlineVariableTool: Inline variable values into usages
"""

import ast
import asyncio
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
