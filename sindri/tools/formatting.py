"""Code formatting tools for Sindri."""

import asyncio
import json
import re
from pathlib import Path
from typing import Optional

import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


class FormatCodeTool(Tool):
    """Format code using language-appropriate formatters."""

    name = "format_code"
    description = """Format code using the appropriate formatter for the language.

Supports: Python (black/autopep8/ruff), JavaScript/TypeScript (prettier),
Rust (rustfmt), Go (gofmt), JSON, YAML, CSS, HTML, Markdown.

Can format a single file, directory, or inline code string."""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to file or directory to format (mutually exclusive with 'code')",
            },
            "code": {
                "type": "string",
                "description": "Code string to format (mutually exclusive with 'path')",
            },
            "language": {
                "type": "string",
                "description": "Language to format as (auto-detected from extension if path provided)",
                "enum": [
                    "python",
                    "javascript",
                    "typescript",
                    "rust",
                    "go",
                    "json",
                    "yaml",
                    "css",
                    "html",
                    "markdown",
                ],
            },
            "formatter": {
                "type": "string",
                "description": "Specific formatter to use (auto-selected if not specified)",
                "enum": [
                    "black",
                    "autopep8",
                    "ruff",
                    "prettier",
                    "rustfmt",
                    "gofmt",
                    "json",
                    "yamlfmt",
                ],
            },
            "check_only": {
                "type": "boolean",
                "description": "Only check if formatting needed, don't modify (default: false)",
            },
            "line_length": {
                "type": "integer",
                "description": "Maximum line length (default: 88 for Python, 80 for others)",
            },
            "indent_size": {
                "type": "integer",
                "description": "Indentation size in spaces (default: 4 for Python, 2 for JS/TS)",
            },
        },
        "required": [],
    }

    # File extension to language mapping
    EXTENSION_MAP = {
        ".py": "python",
        ".pyi": "python",
        ".js": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".rs": "rust",
        ".go": "go",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".css": "css",
        ".scss": "css",
        ".less": "css",
        ".html": "html",
        ".htm": "html",
        ".md": "markdown",
        ".markdown": "markdown",
    }

    # Default formatters per language
    DEFAULT_FORMATTERS = {
        "python": "black",
        "javascript": "prettier",
        "typescript": "prettier",
        "rust": "rustfmt",
        "go": "gofmt",
        "json": "json",  # Built-in
        "yaml": "prettier",
        "css": "prettier",
        "html": "prettier",
        "markdown": "prettier",
    }

    async def execute(
        self,
        path: Optional[str] = None,
        code: Optional[str] = None,
        language: Optional[str] = None,
        formatter: Optional[str] = None,
        check_only: bool = False,
        line_length: Optional[int] = None,
        indent_size: Optional[int] = None,
        **kwargs,
    ) -> ToolResult:
        """Format code using the appropriate formatter."""
        try:
            # Validate inputs
            if path and code:
                return ToolResult(
                    success=False,
                    output="",
                    error="Cannot specify both 'path' and 'code'. Use one or the other.",
                )

            if not path and not code:
                return ToolResult(
                    success=False,
                    output="",
                    error="Must specify either 'path' or 'code' to format.",
                )

            work_dir = self.work_dir or Path.cwd()

            # Handle inline code formatting
            if code:
                if not language:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Must specify 'language' when formatting inline code.",
                    )
                return await self._format_inline(
                    code=code,
                    language=language,
                    formatter=formatter,
                    line_length=line_length,
                    indent_size=indent_size,
                    work_dir=work_dir,
                )

            # Handle file/directory formatting
            file_path = work_dir / path if not Path(path).is_absolute() else Path(path)

            if not file_path.exists():
                return ToolResult(
                    success=False, output="", error=f"Path does not exist: {file_path}"
                )

            # Auto-detect language from extension if not specified
            if not language and file_path.is_file():
                ext = file_path.suffix.lower()
                language = self.EXTENSION_MAP.get(ext)
                if not language:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Could not detect language for extension: {ext}. Please specify 'language' parameter.",
                    )

            if not language:
                return ToolResult(
                    success=False,
                    output="",
                    error="Cannot auto-detect language for directory. Please specify 'language' parameter.",
                )

            # Select formatter
            if not formatter:
                formatter = self.DEFAULT_FORMATTERS.get(language)
                if not formatter:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"No default formatter for language: {language}",
                    )

            log.info(
                "format_code",
                path=str(file_path),
                language=language,
                formatter=formatter,
            )

            # Format based on formatter
            if formatter == "black":
                return await self._format_black(file_path, check_only, line_length)
            elif formatter == "autopep8":
                return await self._format_autopep8(file_path, check_only, line_length)
            elif formatter == "ruff":
                return await self._format_ruff(file_path, check_only, line_length)
            elif formatter == "prettier":
                return await self._format_prettier(
                    file_path, check_only, line_length, indent_size
                )
            elif formatter == "rustfmt":
                return await self._format_rustfmt(file_path, check_only)
            elif formatter == "gofmt":
                return await self._format_gofmt(file_path, check_only)
            elif formatter == "json":
                return await self._format_json(file_path, check_only, indent_size)
            elif formatter == "yamlfmt":
                return await self._format_yamlfmt(file_path, check_only)
            else:
                return ToolResult(
                    success=False, output="", error=f"Unknown formatter: {formatter}"
                )

        except Exception as e:
            log.error("format_code_error", error=str(e))
            return ToolResult(
                success=False, output="", error=f"Failed to format code: {str(e)}"
            )

    async def _format_inline(
        self,
        code: str,
        language: str,
        formatter: Optional[str],
        line_length: Optional[int],
        indent_size: Optional[int],
        work_dir: Path,
    ) -> ToolResult:
        """Format inline code string."""
        if not formatter:
            formatter = self.DEFAULT_FORMATTERS.get(language)

        # For JSON, use built-in Python formatting
        if language == "json" or formatter == "json":
            try:
                parsed = json.loads(code)
                indent = indent_size or 2
                formatted = json.dumps(parsed, indent=indent, sort_keys=False)
                return ToolResult(
                    success=True,
                    output=formatted,
                    metadata={"formatter": "json", "language": language},
                )
            except json.JSONDecodeError as e:
                return ToolResult(
                    success=False, output="", error=f"Invalid JSON: {str(e)}"
                )

        # For Python with black
        if language == "python" and formatter in ("black", None):
            try:
                import black

                mode = black.Mode(
                    line_length=line_length or 88,
                    string_normalization=True,
                    is_pyi=False,
                )
                formatted = black.format_str(code, mode=mode)
                return ToolResult(
                    success=True,
                    output=formatted,
                    metadata={"formatter": "black", "language": language},
                )
            except ImportError:
                # Fall back to subprocess
                pass
            except Exception as e:
                return ToolResult(
                    success=False, output="", error=f"Black formatting failed: {str(e)}"
                )

        # Use subprocess for other formatters
        import tempfile

        ext_map = {
            "python": ".py",
            "javascript": ".js",
            "typescript": ".ts",
            "rust": ".rs",
            "go": ".go",
            "json": ".json",
            "yaml": ".yaml",
            "css": ".css",
            "html": ".html",
            "markdown": ".md",
        }
        ext = ext_map.get(language, ".txt")

        with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False) as f:
            f.write(code)
            temp_path = Path(f.name)

        try:
            # Format the temp file
            if formatter == "black":
                result = await self._format_black(temp_path, False, line_length)
            elif formatter == "autopep8":
                result = await self._format_autopep8(temp_path, False, line_length)
            elif formatter == "ruff":
                result = await self._format_ruff(temp_path, False, line_length)
            elif formatter == "prettier":
                result = await self._format_prettier(
                    temp_path, False, line_length, indent_size
                )
            elif formatter == "rustfmt":
                result = await self._format_rustfmt(temp_path, False)
            elif formatter == "gofmt":
                result = await self._format_gofmt(temp_path, False)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Cannot format inline code with formatter: {formatter}",
                )

            if result.success:
                # Read formatted content
                formatted = temp_path.read_text()
                return ToolResult(
                    success=True,
                    output=formatted,
                    metadata={"formatter": formatter, "language": language},
                )
            return result
        finally:
            temp_path.unlink(missing_ok=True)

    async def _format_black(
        self, file_path: Path, check_only: bool, line_length: Optional[int]
    ) -> ToolResult:
        """Format Python code using black."""
        cmd_parts = ["python", "-m", "black"]

        if check_only:
            cmd_parts.append("--check")

        if line_length:
            cmd_parts.extend(["--line-length", str(line_length)])

        cmd_parts.append(str(file_path))

        return await self._run_formatter(cmd_parts, "black", file_path, check_only)

    async def _format_autopep8(
        self, file_path: Path, check_only: bool, line_length: Optional[int]
    ) -> ToolResult:
        """Format Python code using autopep8."""
        cmd_parts = ["python", "-m", "autopep8"]

        if check_only:
            cmd_parts.append("--diff")
        else:
            cmd_parts.append("--in-place")

        if line_length:
            cmd_parts.extend(["--max-line-length", str(line_length)])

        cmd_parts.append(str(file_path))

        return await self._run_formatter(cmd_parts, "autopep8", file_path, check_only)

    async def _format_ruff(
        self, file_path: Path, check_only: bool, line_length: Optional[int]
    ) -> ToolResult:
        """Format Python code using ruff."""
        cmd_parts = ["ruff", "format"]

        if check_only:
            cmd_parts.append("--check")

        if line_length:
            cmd_parts.extend(["--line-length", str(line_length)])

        cmd_parts.append(str(file_path))

        return await self._run_formatter(cmd_parts, "ruff", file_path, check_only)

    async def _format_prettier(
        self,
        file_path: Path,
        check_only: bool,
        line_length: Optional[int],
        indent_size: Optional[int],
    ) -> ToolResult:
        """Format code using prettier."""
        cmd_parts = ["npx", "prettier"]

        if check_only:
            cmd_parts.append("--check")
        else:
            cmd_parts.append("--write")

        if line_length:
            cmd_parts.extend(["--print-width", str(line_length)])

        if indent_size:
            cmd_parts.extend(["--tab-width", str(indent_size)])

        cmd_parts.append(str(file_path))

        return await self._run_formatter(cmd_parts, "prettier", file_path, check_only)

    async def _format_rustfmt(self, file_path: Path, check_only: bool) -> ToolResult:
        """Format Rust code using rustfmt."""
        cmd_parts = ["rustfmt"]

        if check_only:
            cmd_parts.append("--check")

        cmd_parts.append(str(file_path))

        return await self._run_formatter(cmd_parts, "rustfmt", file_path, check_only)

    async def _format_gofmt(self, file_path: Path, check_only: bool) -> ToolResult:
        """Format Go code using gofmt."""
        if check_only:
            # gofmt -d shows diff
            cmd_parts = ["gofmt", "-d", str(file_path)]
        else:
            # gofmt -w writes in place
            cmd_parts = ["gofmt", "-w", str(file_path)]

        return await self._run_formatter(cmd_parts, "gofmt", file_path, check_only)

    async def _format_json(
        self, file_path: Path, check_only: bool, indent_size: Optional[int]
    ) -> ToolResult:
        """Format JSON using built-in Python json module."""
        try:
            content = file_path.read_text()
            parsed = json.loads(content)
            indent = indent_size or 2
            formatted = json.dumps(parsed, indent=indent, ensure_ascii=False) + "\n"

            if check_only:
                needs_formatting = content != formatted
                return ToolResult(
                    success=not needs_formatting,
                    output=(
                        "File would be reformatted"
                        if needs_formatting
                        else "File is properly formatted"
                    ),
                    metadata={
                        "formatter": "json",
                        "needs_formatting": needs_formatting,
                    },
                )
            else:
                file_path.write_text(formatted)
                changed = content != formatted
                return ToolResult(
                    success=True,
                    output=(
                        f"Formatted {file_path}"
                        if changed
                        else f"No changes needed for {file_path}"
                    ),
                    metadata={"formatter": "json", "changed": changed},
                )

        except json.JSONDecodeError as e:
            return ToolResult(
                success=False, output="", error=f"Invalid JSON in {file_path}: {str(e)}"
            )

    async def _format_yamlfmt(self, file_path: Path, check_only: bool) -> ToolResult:
        """Format YAML using yamlfmt or prettier."""
        # Try yamlfmt first
        cmd_parts = ["yamlfmt"]
        if check_only:
            cmd_parts.append("-dry")
        cmd_parts.append(str(file_path))

        proc = await asyncio.create_subprocess_shell(
            " ".join(cmd_parts),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            return ToolResult(
                success=True,
                output=(
                    f"Formatted {file_path}"
                    if not check_only
                    else "File is properly formatted"
                ),
                metadata={"formatter": "yamlfmt"},
            )

        # Fall back to prettier
        return await self._format_prettier(file_path, check_only, None, None)

    async def _run_formatter(
        self,
        cmd_parts: list[str],
        formatter_name: str,
        file_path: Path,
        check_only: bool,
    ) -> ToolResult:
        """Run a formatter command and return results."""
        cmd = " ".join(cmd_parts)

        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        stdout_text = stdout.decode() if stdout else ""
        stderr_text = stderr.decode() if stderr else ""
        combined = stdout_text + stderr_text

        if check_only:
            # For check mode, non-zero usually means formatting needed
            if proc.returncode == 0:
                return ToolResult(
                    success=True,
                    output="File is properly formatted",
                    metadata={"formatter": formatter_name, "needs_formatting": False},
                )
            else:
                return ToolResult(
                    success=False,
                    output=combined or "File needs formatting",
                    error="File needs formatting",
                    metadata={"formatter": formatter_name, "needs_formatting": True},
                )
        else:
            # For format mode
            if proc.returncode == 0:
                return ToolResult(
                    success=True,
                    output=f"Formatted {file_path}",
                    metadata={"formatter": formatter_name},
                )
            else:
                return ToolResult(
                    success=False,
                    output=combined,
                    error=f"{formatter_name} failed: {combined}",
                    metadata={
                        "formatter": formatter_name,
                        "returncode": proc.returncode,
                    },
                )


class LintCodeTool(Tool):
    """Run linters on code to check for issues."""

    name = "lint_code"
    description = """Run linters to check code for issues and style violations.

Supports: Python (ruff/flake8/pylint), JavaScript/TypeScript (eslint),
Rust (clippy), Go (golint/staticcheck)."""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to file or directory to lint",
            },
            "language": {
                "type": "string",
                "description": "Language to lint (auto-detected from extension if not specified)",
                "enum": ["python", "javascript", "typescript", "rust", "go"],
            },
            "linter": {
                "type": "string",
                "description": "Specific linter to use (auto-selected if not specified)",
                "enum": [
                    "ruff",
                    "flake8",
                    "pylint",
                    "mypy",
                    "eslint",
                    "clippy",
                    "golint",
                    "staticcheck",
                ],
            },
            "fix": {
                "type": "boolean",
                "description": "Automatically fix issues where possible (default: false)",
            },
        },
        "required": ["path"],
    }

    EXTENSION_MAP = {
        ".py": "python",
        ".pyi": "python",
        ".js": "javascript",
        ".mjs": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".rs": "rust",
        ".go": "go",
    }

    DEFAULT_LINTERS = {
        "python": "ruff",
        "javascript": "eslint",
        "typescript": "eslint",
        "rust": "clippy",
        "go": "staticcheck",
    }

    async def execute(
        self,
        path: str,
        language: Optional[str] = None,
        linter: Optional[str] = None,
        fix: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Run linter on the specified code."""
        try:
            work_dir = self.work_dir or Path.cwd()
            file_path = work_dir / path if not Path(path).is_absolute() else Path(path)

            if not file_path.exists():
                return ToolResult(
                    success=False, output="", error=f"Path does not exist: {file_path}"
                )

            # Auto-detect language
            if not language and file_path.is_file():
                ext = file_path.suffix.lower()
                language = self.EXTENSION_MAP.get(ext)
                if not language:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Could not detect language for extension: {ext}",
                    )
            elif not language:
                return ToolResult(
                    success=False,
                    output="",
                    error="Cannot auto-detect language for directory. Please specify 'language'.",
                )

            # Select linter
            if not linter:
                linter = self.DEFAULT_LINTERS.get(language)

            log.info("lint_code", path=str(file_path), language=language, linter=linter)

            # Run appropriate linter
            if linter == "ruff":
                return await self._lint_ruff(file_path, fix)
            elif linter == "flake8":
                return await self._lint_flake8(file_path)
            elif linter == "pylint":
                return await self._lint_pylint(file_path)
            elif linter == "mypy":
                return await self._lint_mypy(file_path)
            elif linter == "eslint":
                return await self._lint_eslint(file_path, fix)
            elif linter == "clippy":
                return await self._lint_clippy(file_path, fix, work_dir)
            elif linter in ("golint", "staticcheck"):
                return await self._lint_go(file_path, linter)
            else:
                return ToolResult(
                    success=False, output="", error=f"Unknown linter: {linter}"
                )

        except Exception as e:
            log.error("lint_code_error", error=str(e))
            return ToolResult(
                success=False, output="", error=f"Failed to lint code: {str(e)}"
            )

    async def _lint_ruff(self, file_path: Path, fix: bool) -> ToolResult:
        """Lint Python code using ruff."""
        cmd_parts = ["ruff", "check"]
        if fix:
            cmd_parts.append("--fix")
        cmd_parts.append(str(file_path))

        return await self._run_linter(cmd_parts, "ruff")

    async def _lint_flake8(self, file_path: Path) -> ToolResult:
        """Lint Python code using flake8."""
        cmd_parts = ["python", "-m", "flake8", str(file_path)]
        return await self._run_linter(cmd_parts, "flake8")

    async def _lint_pylint(self, file_path: Path) -> ToolResult:
        """Lint Python code using pylint."""
        cmd_parts = ["python", "-m", "pylint", "--output-format=text", str(file_path)]
        return await self._run_linter(cmd_parts, "pylint")

    async def _lint_mypy(self, file_path: Path) -> ToolResult:
        """Type check Python code using mypy."""
        cmd_parts = ["python", "-m", "mypy", str(file_path)]
        return await self._run_linter(cmd_parts, "mypy")

    async def _lint_eslint(self, file_path: Path, fix: bool) -> ToolResult:
        """Lint JavaScript/TypeScript using eslint."""
        cmd_parts = ["npx", "eslint"]
        if fix:
            cmd_parts.append("--fix")
        cmd_parts.append(str(file_path))

        return await self._run_linter(cmd_parts, "eslint")

    async def _lint_clippy(
        self, file_path: Path, fix: bool, work_dir: Path
    ) -> ToolResult:
        """Lint Rust code using clippy."""
        cmd_parts = ["cargo", "clippy"]
        if fix:
            cmd_parts.append("--fix")
        cmd_parts.extend(["--", "-D", "warnings"])

        proc = await asyncio.create_subprocess_shell(
            " ".join(cmd_parts),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(work_dir),
        )
        stdout, stderr = await proc.communicate()
        combined = stdout.decode() + stderr.decode()

        # Clippy returns 0 even with warnings, check output
        issues = self._parse_clippy_output(combined)

        if proc.returncode != 0 or issues["errors"] > 0:
            return ToolResult(
                success=False,
                output=combined,
                error=f"Found {issues['errors']} error(s) and {issues['warnings']} warning(s)",
                metadata={"linter": "clippy", **issues},
            )

        return ToolResult(
            success=True,
            output=combined or "No issues found",
            metadata={"linter": "clippy", **issues},
        )

    async def _lint_go(self, file_path: Path, linter: str) -> ToolResult:
        """Lint Go code using golint or staticcheck."""
        if linter == "staticcheck":
            cmd_parts = ["staticcheck", str(file_path)]
        else:
            cmd_parts = ["golint", str(file_path)]

        return await self._run_linter(cmd_parts, linter)

    async def _run_linter(self, cmd_parts: list[str], linter_name: str) -> ToolResult:
        """Run a linter command and return results."""
        cmd = " ".join(cmd_parts)

        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        stdout_text = stdout.decode() if stdout else ""
        stderr_text = stderr.decode() if stderr else ""
        combined = stdout_text + stderr_text

        # Parse issue counts
        issues = self._parse_lint_output(combined, linter_name)

        if proc.returncode == 0 and issues["total"] == 0:
            return ToolResult(
                success=True,
                output="No issues found",
                metadata={"linter": linter_name, **issues},
            )
        elif proc.returncode == 0:
            # Some linters return 0 even with warnings
            return ToolResult(
                success=True,
                output=combined,
                metadata={"linter": linter_name, **issues},
            )
        else:
            return ToolResult(
                success=False,
                output=combined,
                error=f"Found {issues['total']} issue(s)",
                metadata={"linter": linter_name, **issues},
            )

    def _parse_lint_output(self, output: str, linter: str) -> dict:
        """Parse linter output to count issues."""
        issues = {"errors": 0, "warnings": 0, "total": 0}

        if linter == "ruff":
            # Count lines that look like issues
            issue_lines = re.findall(r"^\S+:\d+:\d+:", output, re.MULTILINE)
            issues["total"] = len(issue_lines)

        elif linter == "flake8":
            issue_lines = re.findall(r"^\S+:\d+:\d+:", output, re.MULTILINE)
            issues["total"] = len(issue_lines)

        elif linter == "pylint":
            # Look for score line or count issues
            score_match = re.search(r"rated at ([\d.]+)/10", output)
            issue_lines = re.findall(r"^[CRWEF]:", output, re.MULTILINE)
            issues["total"] = len(issue_lines)
            if score_match:
                issues["score"] = float(score_match.group(1))

        elif linter == "eslint":
            # Look for problem count
            problems_match = re.search(r"(\d+) problems?", output)
            if problems_match:
                issues["total"] = int(problems_match.group(1))

        elif linter == "mypy":
            error_match = re.search(r"Found (\d+) errors?", output)
            if error_match:
                issues["errors"] = int(error_match.group(1))
                issues["total"] = issues["errors"]

        return issues

    def _parse_clippy_output(self, output: str) -> dict:
        """Parse clippy output for issue counts."""
        issues = {"errors": 0, "warnings": 0, "total": 0}

        errors = len(re.findall(r"^error(\[E\d+\])?:", output, re.MULTILINE))
        warnings = len(re.findall(r"^warning:", output, re.MULTILINE))

        issues["errors"] = errors
        issues["warnings"] = warnings
        issues["total"] = errors + warnings

        return issues
