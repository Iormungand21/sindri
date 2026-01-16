"""Code search tools for Sindri."""

import asyncio
import shutil
from pathlib import Path
from typing import Optional
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


class SearchCodeTool(Tool):
    """Search for code patterns in the codebase.

    Supports two modes:
    1. Text search (default) - Fast literal/regex search using ripgrep
    2. Semantic search - Conceptual search using embeddings

    Text search is fast and precise for known patterns.
    Semantic search is useful for finding conceptually related code.
    """

    name = "search_code"
    description = """Search for code in the codebase. Supports literal text search (default) or semantic search for conceptual queries.

Examples:
- search_code(query="def authenticate") - Find authentication functions
- search_code(query="TODO", file_types=["py", "ts"]) - Find TODOs in Python/TypeScript
- search_code(query="user validation logic", semantic=true) - Semantic search for related code
- search_code(query="class.*Handler", regex=true) - Regex search for Handler classes"""

    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query - literal text, regex pattern, or semantic description"
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (default: current directory)"
            },
            "file_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File extensions to search (e.g., ['py', 'ts']). Empty = all files"
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Case sensitive search (default: false)"
            },
            "regex": {
                "type": "boolean",
                "description": "Treat query as regex pattern (default: false)"
            },
            "semantic": {
                "type": "boolean",
                "description": "Use semantic (embedding-based) search for conceptual queries (default: false)"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default: 20)"
            },
            "context_lines": {
                "type": "integer",
                "description": "Lines of context around matches for text search (default: 2)"
            }
        },
        "required": ["query"]
    }

    # File extensions to skip
    SKIP_DIRS = {
        'node_modules', '__pycache__', '.git', '.svn', '.hg',
        'dist', 'build', 'target', 'venv', '.venv', 'env',
        '.tox', '.nox', '.pytest_cache', '.mypy_cache',
        'coverage', '.coverage', 'htmlcov'
    }

    def __init__(
        self,
        work_dir: Optional[Path] = None,
        semantic_memory: Optional['SemanticMemory'] = None,
        namespace: str = "codebase"
    ):
        """Initialize search tool.

        Args:
            work_dir: Working directory for searches
            semantic_memory: SemanticMemory instance for semantic search
            namespace: Namespace for semantic memory index
        """
        super().__init__(work_dir)
        self.semantic_memory = semantic_memory
        self.namespace = namespace
        self._rg_available: Optional[bool] = None

    def _check_ripgrep(self) -> bool:
        """Check if ripgrep is available."""
        if self._rg_available is None:
            self._rg_available = shutil.which("rg") is not None
        return self._rg_available

    async def execute(
        self,
        query: str,
        path: Optional[str] = None,
        file_types: Optional[list[str]] = None,
        case_sensitive: bool = False,
        regex: bool = False,
        semantic: bool = False,
        max_results: int = 20,
        context_lines: int = 2,
        **kwargs
    ) -> ToolResult:
        """Execute code search.

        Args:
            query: Search query (literal, regex, or semantic description)
            path: Directory to search in
            file_types: File extensions to include
            case_sensitive: Case sensitive search
            regex: Treat query as regex
            semantic: Use semantic search
            max_results: Maximum results
            context_lines: Context lines for text search
        """
        if not query.strip():
            return ToolResult(
                success=False,
                output="",
                error="Search query cannot be empty"
            )

        # Resolve search path
        search_path = self._resolve_path(path or ".")
        if not search_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Search path does not exist: {search_path}"
            )
        if not search_path.is_dir():
            return ToolResult(
                success=False,
                output="",
                error=f"Search path is not a directory: {search_path}"
            )

        log.info(
            "search_code_execute",
            query=query,
            path=str(search_path),
            semantic=semantic,
            regex=regex,
            file_types=file_types
        )

        if semantic:
            return await self._semantic_search(
                query, search_path, file_types, max_results
            )
        else:
            return await self._text_search(
                query, search_path, file_types, case_sensitive,
                regex, max_results, context_lines
            )

    async def _text_search(
        self,
        query: str,
        path: Path,
        file_types: Optional[list[str]],
        case_sensitive: bool,
        regex: bool,
        max_results: int,
        context_lines: int
    ) -> ToolResult:
        """Perform text-based search using ripgrep or grep."""
        try:
            if self._check_ripgrep():
                return await self._ripgrep_search(
                    query, path, file_types, case_sensitive,
                    regex, max_results, context_lines
                )
            else:
                return await self._grep_search(
                    query, path, file_types, case_sensitive,
                    regex, max_results, context_lines
                )
        except Exception as e:
            log.error("text_search_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Text search failed: {str(e)}"
            )

    async def _ripgrep_search(
        self,
        query: str,
        path: Path,
        file_types: Optional[list[str]],
        case_sensitive: bool,
        regex: bool,
        max_results: int,
        context_lines: int
    ) -> ToolResult:
        """Search using ripgrep."""
        cmd = ["rg", "--line-number", "--with-filename"]

        # Case sensitivity
        if not case_sensitive:
            cmd.append("-i")

        # Regex vs literal
        if not regex:
            cmd.extend(["-F"])  # Fixed string (literal)

        # Context lines
        if context_lines > 0:
            cmd.extend(["-C", str(context_lines)])

        # Max results (multiply by 3 for context)
        effective_max = max_results * (1 + 2 * context_lines) if context_lines else max_results
        cmd.extend(["-m", str(effective_max)])

        # File type filters
        if file_types:
            for ft in file_types:
                # Remove leading dot if present
                ft_clean = ft.lstrip('.')
                cmd.extend(["--type-add", f"custom:*.{ft_clean}", "-t", "custom"])

        # Skip directories (use -g shorthand for cleaner command)
        for skip_dir in self.SKIP_DIRS:
            cmd.extend(["-g", f"!{skip_dir}/"])

        # Query and path
        cmd.append(query)
        cmd.append(str(path))

        log.debug("ripgrep_command", cmd=" ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        output = stdout.decode('utf-8', errors='replace')
        errors = stderr.decode('utf-8', errors='replace')

        # ripgrep returns 1 for no matches, 2 for errors
        if proc.returncode == 2:
            return ToolResult(
                success=False,
                output="",
                error=f"ripgrep error: {errors}"
            )

        # Format output
        if not output.strip():
            return ToolResult(
                success=True,
                output="No matches found.",
                metadata={"match_count": 0, "tool": "ripgrep"}
            )

        # Count matches
        match_count = len([line for line in output.split('\n') if line and ':' in line and not line.startswith('--')])

        return ToolResult(
            success=True,
            output=output.strip(),
            metadata={"match_count": match_count, "tool": "ripgrep"}
        )

    async def _grep_search(
        self,
        query: str,
        path: Path,
        file_types: Optional[list[str]],
        case_sensitive: bool,
        regex: bool,
        max_results: int,
        context_lines: int
    ) -> ToolResult:
        """Fallback search using grep."""
        cmd = ["grep", "-r", "-n"]  # recursive, line numbers

        # Case sensitivity
        if not case_sensitive:
            cmd.append("-i")

        # Regex vs literal
        if not regex:
            cmd.append("-F")  # Fixed string

        # Context lines
        if context_lines > 0:
            cmd.extend(["-C", str(context_lines)])

        # File type filters
        if file_types:
            for ft in file_types:
                ft_clean = ft.lstrip('.')
                cmd.extend(["--include", f"*.{ft_clean}"])

        # Skip directories
        for skip_dir in self.SKIP_DIRS:
            cmd.extend(["--exclude-dir", skip_dir])

        # Query and path
        cmd.append(query)
        cmd.append(str(path))

        log.debug("grep_command", cmd=" ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        output = stdout.decode('utf-8', errors='replace')

        # Limit results
        lines = output.strip().split('\n')
        if len(lines) > max_results:
            lines = lines[:max_results]
            lines.append(f"... (truncated, showing first {max_results} results)")
            output = '\n'.join(lines)

        if not output.strip() or (proc.returncode == 1 and not output.strip()):
            return ToolResult(
                success=True,
                output="No matches found.",
                metadata={"match_count": 0, "tool": "grep"}
            )

        match_count = len([line for line in output.split('\n') if line and ':' in line])

        return ToolResult(
            success=True,
            output=output.strip(),
            metadata={"match_count": match_count, "tool": "grep"}
        )

    async def _semantic_search(
        self,
        query: str,
        path: Path,
        file_types: Optional[list[str]],
        max_results: int
    ) -> ToolResult:
        """Perform semantic (embedding-based) search."""
        if not self.semantic_memory:
            return ToolResult(
                success=False,
                output="",
                error="Semantic search requires memory system. Use text search instead (semantic=false)."
            )

        try:
            # Perform semantic search
            results = self.semantic_memory.search(
                namespace=self.namespace,
                query=query,
                limit=max_results * 2  # Get more to filter by file type
            )

            if not results:
                return ToolResult(
                    success=True,
                    output="No relevant code found for query.",
                    metadata={"match_count": 0, "tool": "semantic"}
                )

            # Filter by file types if specified
            if file_types:
                file_types_set = {f".{ft.lstrip('.')}" for ft in file_types}
                results = [
                    (content, meta, score) for content, meta, score in results
                    if any(meta.get('path', '').endswith(ext) for ext in file_types_set)
                ]

            # Limit results
            results = results[:max_results]

            if not results:
                return ToolResult(
                    success=True,
                    output="No matches found for specified file types.",
                    metadata={"match_count": 0, "tool": "semantic"}
                )

            # Format output
            output_parts = []
            for content, meta, score in results:
                file_path = meta.get('path', 'unknown')
                start_line = meta.get('start_line', '?')
                end_line = meta.get('end_line', '?')
                similarity = f"{score:.3f}"

                output_parts.append(
                    f"=== {file_path}:{start_line}-{end_line} (similarity: {similarity}) ===\n{content}"
                )

            return ToolResult(
                success=True,
                output='\n\n'.join(output_parts),
                metadata={"match_count": len(results), "tool": "semantic"}
            )

        except Exception as e:
            log.error("semantic_search_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Semantic search failed: {str(e)}"
            )


class FindSymbolTool(Tool):
    """Find function/class/variable definitions in code.

    Uses pattern matching to locate symbol definitions.
    """

    name = "find_symbol"
    description = """Find where a symbol (function, class, or variable) is defined.

Examples:
- find_symbol(name="UserModel") - Find UserModel class definition
- find_symbol(name="authenticate", symbol_type="function") - Find authenticate function
- find_symbol(name="config", symbol_type="variable", file_types=["py"]) - Find config variable in Python"""

    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Symbol name to find"
            },
            "symbol_type": {
                "type": "string",
                "enum": ["any", "function", "class", "variable"],
                "description": "Type of symbol to find (default: any)"
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (default: current directory)"
            },
            "file_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File extensions to search (e.g., ['py', 'ts'])"
            }
        },
        "required": ["name"]
    }

    # Language-specific patterns for symbol definitions
    PATTERNS = {
        "py": {
            "function": r"^\s*(?:async\s+)?def\s+{name}\s*\(",
            "class": r"^\s*class\s+{name}\s*[\(:]",
            "variable": r"^\s*{name}\s*[:=]"
        },
        "ts": {
            "function": r"^\s*(?:export\s+)?(?:async\s+)?function\s+{name}\s*[\(<]|^\s*(?:const|let|var)\s+{name}\s*=\s*(?:async\s+)?(?:\([^)]*\)|[^=]*)\s*=>",
            "class": r"^\s*(?:export\s+)?class\s+{name}\s*[\{{<]",
            "variable": r"^\s*(?:export\s+)?(?:const|let|var)\s+{name}\s*[:=]"
        },
        "js": {
            "function": r"^\s*(?:export\s+)?(?:async\s+)?function\s+{name}\s*\(|^\s*(?:const|let|var)\s+{name}\s*=\s*(?:async\s+)?(?:\([^)]*\)|[^=]*)\s*=>",
            "class": r"^\s*(?:export\s+)?class\s+{name}\s*[\{{]",
            "variable": r"^\s*(?:export\s+)?(?:const|let|var)\s+{name}\s*[:=]"
        },
        "default": {
            "function": r"(?:def|function|func|fn)\s+{name}\s*\(",
            "class": r"(?:class|struct|interface)\s+{name}\s*[\(:\{{<]",
            "variable": r"^\s*(?:const|let|var|val)?\s*{name}\s*[:=]"
        }
    }

    async def execute(
        self,
        name: str,
        symbol_type: str = "any",
        path: Optional[str] = None,
        file_types: Optional[list[str]] = None,
        **kwargs
    ) -> ToolResult:
        """Find symbol definition."""
        import re

        if not name.strip():
            return ToolResult(
                success=False,
                output="",
                error="Symbol name cannot be empty"
            )

        search_path = self._resolve_path(path or ".")
        if not search_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Search path does not exist: {search_path}"
            )

        # Determine which patterns to use
        search_types = ["function", "class", "variable"] if symbol_type == "any" else [symbol_type]

        results = []

        # Search files
        for file_path in search_path.rglob("*"):
            if not file_path.is_file():
                continue

            # Filter by file type
            ext = file_path.suffix.lstrip('.')
            if file_types and ext not in file_types:
                continue

            # Skip hidden and common ignore dirs
            if any(p.startswith('.') for p in file_path.parts):
                continue
            if any(d in file_path.parts for d in ['node_modules', '__pycache__', 'dist', 'build', '.venv', 'venv']):
                continue

            # Get patterns for this file type
            patterns_dict = self.PATTERNS.get(ext, self.PATTERNS["default"])

            try:
                content = file_path.read_text(errors='ignore')
                lines = content.split('\n')

                for line_num, line in enumerate(lines, 1):
                    for stype in search_types:
                        pattern_template = patterns_dict.get(stype)
                        if not pattern_template:
                            continue

                        pattern = pattern_template.format(name=re.escape(name))
                        if re.search(pattern, line):
                            rel_path = str(file_path.relative_to(search_path)) if search_path in file_path.parents else str(file_path)
                            results.append({
                                "path": rel_path,
                                "line": line_num,
                                "type": stype,
                                "content": line.strip()
                            })

            except Exception as e:
                log.warning("find_symbol_read_error", path=str(file_path), error=str(e))
                continue

        if not results:
            return ToolResult(
                success=True,
                output=f"No definition found for symbol '{name}'",
                metadata={"match_count": 0}
            )

        # Format output
        output_parts = []
        for r in results:
            output_parts.append(f"{r['path']}:{r['line']} [{r['type']}] {r['content']}")

        return ToolResult(
            success=True,
            output='\n'.join(output_parts),
            metadata={"match_count": len(results)}
        )
