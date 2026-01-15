"""Dependency analysis for Python projects."""

import ast
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
import structlog

from sindri.analysis.results import DependencyInfo

log = structlog.get_logger()

# Standard library modules (Python 3.11+)
STDLIB_MODULES = {
    "abc", "aifc", "argparse", "array", "ast", "asyncio", "atexit",
    "base64", "bdb", "binascii", "binhex", "bisect", "builtins",
    "bz2", "calendar", "cgi", "cgitb", "chunk", "cmath", "cmd",
    "code", "codecs", "codeop", "collections", "colorsys", "compileall",
    "concurrent", "configparser", "contextlib", "contextvars", "copy",
    "copyreg", "cProfile", "crypt", "csv", "ctypes", "curses",
    "dataclasses", "datetime", "dbm", "decimal", "difflib", "dis",
    "distutils", "doctest", "email", "encodings", "enum", "errno",
    "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch",
    "fractions", "ftplib", "functools", "gc", "getopt", "getpass",
    "gettext", "glob", "graphlib", "grp", "gzip", "hashlib", "heapq",
    "hmac", "html", "http", "idlelib", "imaplib", "imghdr", "imp",
    "importlib", "inspect", "io", "ipaddress", "itertools", "json",
    "keyword", "lib2to3", "linecache", "locale", "logging", "lzma",
    "mailbox", "mailcap", "marshal", "math", "mimetypes", "mmap",
    "modulefinder", "multiprocessing", "netrc", "nis", "nntplib",
    "numbers", "operator", "optparse", "os", "pathlib", "pdb", "pickle",
    "pickletools", "pipes", "pkgutil", "platform", "plistlib", "poplib",
    "posix", "posixpath", "pprint", "profile", "pstats", "pty", "pwd",
    "py_compile", "pyclbr", "pydoc", "queue", "quopri", "random", "re",
    "readline", "reprlib", "resource", "rlcompleter", "runpy", "sched",
    "secrets", "select", "selectors", "shelve", "shlex", "shutil",
    "signal", "site", "smtpd", "smtplib", "sndhdr", "socket", "socketserver",
    "spwd", "sqlite3", "ssl", "stat", "statistics", "string", "stringprep",
    "struct", "subprocess", "sunau", "symtable", "sys", "sysconfig",
    "syslog", "tabnanny", "tarfile", "telnetlib", "tempfile", "termios",
    "test", "textwrap", "threading", "time", "timeit", "tkinter", "token",
    "tokenize", "tomllib", "trace", "traceback", "tracemalloc", "tty",
    "turtle", "turtledemo", "types", "typing", "typing_extensions",
    "unicodedata", "unittest", "urllib", "uu", "uuid", "venv", "warnings",
    "wave", "weakref", "webbrowser", "winreg", "winsound", "wsgiref",
    "xdrlib", "xml", "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib",
}


class DependencyAnalyzer:
    """Analyzes Python project dependencies and import structure."""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.package_name = self._detect_package_name()

    def _detect_package_name(self) -> str:
        """Detect the main package name from the project."""
        # Check for common patterns
        for subdir in self.project_path.iterdir():
            if subdir.is_dir() and (subdir / "__init__.py").exists():
                # Skip common non-package directories
                if subdir.name not in {"tests", "test", "docs", "examples", "scripts"}:
                    return subdir.name

        # Fallback to project directory name
        return self.project_path.name

    def analyze(self) -> DependencyInfo:
        """Perform full dependency analysis.

        Returns:
            DependencyInfo with all analysis results
        """
        log.info("analyzing_dependencies", project=str(self.project_path))

        result = DependencyInfo()

        # Find all Python files
        python_files = self._find_python_files()

        # Parse imports from each file
        imports_by_file: Dict[str, Set[str]] = {}
        for py_file in python_files:
            imports = self._parse_imports(py_file)
            rel_path = self._relative_path(py_file)
            imports_by_file[rel_path] = imports

        # Categorize imports
        internal_deps: Dict[str, List[str]] = {}
        external: Set[str] = set()

        for file_path, imports in imports_by_file.items():
            internal = []
            for imp in imports:
                if self._is_internal(imp):
                    internal.append(imp)
                elif not self._is_stdlib(imp):
                    external.add(self._get_package_name(imp))

            if internal:
                internal_deps[file_path] = internal

        result.internal_dependencies = internal_deps
        result.external_packages = external

        # Detect circular dependencies
        result.circular_dependencies = self._find_circular_deps(internal_deps)

        # Find most imported modules
        result.most_imported = self._find_most_imported(internal_deps)

        # Find orphan modules
        result.orphan_modules = self._find_orphans(imports_by_file.keys(), internal_deps)

        # Find entry points
        result.entry_points = self._find_entry_points(python_files)

        log.info(
            "dependency_analysis_complete",
            files=len(python_files),
            internal_deps=len(internal_deps),
            external_packages=len(external),
            circular=len(result.circular_dependencies),
        )

        return result

    def _find_python_files(self) -> List[Path]:
        """Find all Python files in the project."""
        python_files = []
        for path in self.project_path.rglob("*.py"):
            # Skip hidden directories and common non-code directories
            parts = path.relative_to(self.project_path).parts
            if any(p.startswith(".") or p in {"__pycache__", "venv", ".venv", "node_modules"} for p in parts):
                continue
            python_files.append(path)
        return python_files

    def _relative_path(self, path: Path) -> str:
        """Get path relative to project root."""
        return str(path.relative_to(self.project_path))

    def _parse_imports(self, file_path: Path) -> Set[str]:
        """Parse imports from a Python file."""
        imports = set()

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module.split(".")[0])
                    elif node.level > 0:
                        # Relative import - mark as internal
                        imports.add(f"__relative__{node.level}")

        except SyntaxError as e:
            log.debug("syntax_error_parsing", file=str(file_path), error=str(e))
        except Exception as e:
            log.debug("error_parsing", file=str(file_path), error=str(e))

        return imports

    def _is_internal(self, module: str) -> bool:
        """Check if a module is internal to the project."""
        if module.startswith("__relative__"):
            return True
        return module == self.package_name or module.startswith(f"{self.package_name}.")

    def _is_stdlib(self, module: str) -> bool:
        """Check if a module is part of Python standard library."""
        base = module.split(".")[0]
        return base in STDLIB_MODULES

    def _get_package_name(self, module: str) -> str:
        """Get the top-level package name from an import."""
        return module.split(".")[0]

    def _find_circular_deps(self, deps: Dict[str, List[str]]) -> List[List[str]]:
        """Find circular dependencies using DFS."""
        cycles = []

        # Build adjacency list
        graph = defaultdict(set)
        for file_path, imports in deps.items():
            # Convert file path to module path
            module = self._file_to_module(file_path)
            for imp in imports:
                if imp != module and not imp.startswith("__relative__"):
                    graph[module].add(imp)

        # DFS for cycles
        visited = set()
        path_set = set()
        path = []

        def dfs(node: str):
            if node in path_set:
                # Found cycle
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                if len(cycle) > 2:  # Only interesting cycles
                    cycles.append(cycle)
                return

            if node in visited:
                return

            visited.add(node)
            path_set.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                if self._is_internal(neighbor):
                    dfs(neighbor)

            path.pop()
            path_set.remove(node)

        for node in graph:
            dfs(node)

        # Deduplicate cycles
        seen = set()
        unique_cycles = []
        for cycle in cycles:
            key = tuple(sorted(cycle[:-1]))  # Remove last (duplicate of first)
            if key not in seen:
                seen.add(key)
                unique_cycles.append(cycle[:-1])

        return unique_cycles

    def _file_to_module(self, file_path: str) -> str:
        """Convert file path to module name."""
        # Remove .py extension and convert slashes to dots
        module = file_path.replace("/", ".").replace("\\", ".")
        if module.endswith(".py"):
            module = module[:-3]
        if module.endswith(".__init__"):
            module = module[:-9]
        return module

    def _find_most_imported(self, deps: Dict[str, List[str]]) -> List[Tuple[str, int]]:
        """Find the most frequently imported internal modules."""
        import_count = defaultdict(int)

        for imports in deps.values():
            for imp in imports:
                if not imp.startswith("__relative__"):
                    import_count[imp] += 1

        # Sort by count descending
        sorted_imports = sorted(import_count.items(), key=lambda x: -x[1])
        return sorted_imports[:10]

    def _find_orphans(self, all_files: set, deps: Dict[str, List[str]]) -> List[str]:
        """Find modules that neither import nor are imported."""
        # Get all modules
        all_modules = {self._file_to_module(f) for f in all_files}

        # Get modules that import something
        importers = {self._file_to_module(f) for f in deps.keys()}

        # Get modules that are imported
        imported = set()
        for imports in deps.values():
            for imp in imports:
                if not imp.startswith("__relative__"):
                    imported.add(imp)

        # Find orphans - modules with no connections
        connected = importers | imported
        orphans = []

        for module in all_modules:
            # Check if module is connected
            module_base = module.split(".")[0] if "." in module else module
            if module not in connected and module_base not in connected:
                orphans.append(module)

        return orphans

    def _find_entry_points(self, files: List[Path]) -> List[str]:
        """Find likely entry point files."""
        entry_points = []

        entry_point_names = {
            "main.py", "__main__.py", "cli.py", "app.py",
            "run.py", "server.py", "manage.py", "setup.py"
        }

        for file_path in files:
            if file_path.name in entry_point_names:
                entry_points.append(self._relative_path(file_path))
                continue

            # Check for if __name__ == "__main__"
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if re.search(r'if\s+__name__\s*==\s*["\']__main__["\']', content):
                    entry_points.append(self._relative_path(file_path))
            except Exception:
                pass

        return sorted(set(entry_points))
