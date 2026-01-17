"""Style and convention analysis for projects."""

import ast
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import structlog

from sindri.analysis.results import StyleInfo

log = structlog.get_logger()


# Docstring style patterns
DOCSTRING_PATTERNS = {
    "google": [
        r"Args:\s*\n",
        r"Returns:\s*\n",
        r"Raises:\s*\n",
        r"Examples?:\s*\n",
    ],
    "numpy": [
        r"Parameters\s*\n\s*-+",
        r"Returns\s*\n\s*-+",
        r"Raises\s*\n\s*-+",
    ],
    "sphinx": [
        r":param\s+\w+:",
        r":returns?:",
        r":raises?\s+\w+:",
        r":type\s+\w+:",
    ],
    "epytext": [
        r"@param\s+\w+:",
        r"@return:",
        r"@raise\s+\w+:",
    ],
}

# Configuration file patterns
CONFIG_FILE_PATTERNS = {
    "black": [".black", "black.toml", "[tool.black]"],
    "ruff": ["ruff.toml", ".ruff.toml", "[tool.ruff]"],
    "flake8": [".flake8", "[flake8]"],
    "pylint": [".pylintrc", "pylintrc"],
    "mypy": ["mypy.ini", ".mypy.ini", "[mypy]"],
    "isort": [".isort.cfg", "[tool.isort]"],
    "prettier": [".prettierrc", "prettier.config.js"],
    "eslint": [".eslintrc", ".eslintrc.js", ".eslintrc.json"],
}


class StyleAnalyzer:
    """Analyzes coding style and conventions in a project."""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)

    def analyze(self) -> StyleInfo:
        """Perform full style analysis.

        Returns:
            StyleInfo with detected conventions
        """
        log.info("analyzing_style", project=str(self.project_path))

        result = StyleInfo()

        # Find Python files for analysis
        python_files = self._find_python_files()

        # Detect indentation style
        indent_style, indent_size = self._detect_indentation(python_files)
        result.indentation = indent_style
        result.indent_size = indent_size

        # Detect naming conventions
        result.naming_conventions = self._detect_naming_conventions(python_files)

        # Detect docstring style
        result.docstring_style = self._detect_docstring_style(python_files)

        # Detect type hints usage
        result.has_type_hints = self._detect_type_hints(python_files)

        # Detect async patterns
        result.async_style = self._detect_async_style(python_files)

        # Detect formatting tools
        result.formatter, result.linter = self._detect_formatters()

        # Find formatting config files
        result.formatting_configs = self._find_config_files()

        # Detect test framework
        result.test_framework = self._detect_test_framework(python_files)

        log.info(
            "style_analysis_complete",
            indentation=result.indentation,
            indent_size=result.indent_size,
            docstring_style=result.docstring_style,
            has_type_hints=result.has_type_hints,
        )

        return result

    def _find_python_files(self) -> List[Path]:
        """Find Python files for analysis."""
        files = []
        for path in self.project_path.rglob("*.py"):
            parts = path.relative_to(self.project_path).parts
            if not any(
                p.startswith(".")
                or p in {"__pycache__", "venv", ".venv", "node_modules"}
                for p in parts
            ):
                files.append(path)
        return files[:30]  # Sample first 30 files

    def _detect_indentation(self, files: List[Path]) -> Tuple[str, int]:
        """Detect indentation style and size."""
        space_counts = defaultdict(int)
        tab_count = 0
        total_lines = 0

        for file_path in files[:20]:  # Sample first 20 files
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                lines = content.split("\n")

                for line in lines:
                    if not line or line.isspace():
                        continue

                    # Count leading whitespace
                    stripped = line.lstrip()
                    if stripped and line != stripped:
                        indent = line[: len(line) - len(stripped)]
                        total_lines += 1

                        if "\t" in indent:
                            tab_count += 1
                        else:
                            spaces = len(indent)
                            if spaces > 0:
                                space_counts[spaces] += 1

            except Exception:
                continue

        # Determine style
        if tab_count > total_lines * 0.3:
            return "tabs", 1

        # Find most common space indent that's a multiple of 2 or 4
        if space_counts:
            # Find smallest common indent
            for size in [2, 4, 3, 8]:
                count = sum(c for s, c in space_counts.items() if s % size == 0)
                if count > total_lines * 0.3:
                    return "spaces", size

            # Fallback to most common
            most_common = max(space_counts.keys(), key=lambda k: space_counts[k])
            return "spaces", min(most_common, 8)

        return "spaces", 4  # Default

    def _detect_naming_conventions(self, files: List[Path]) -> Dict[str, str]:
        """Detect naming conventions for different code elements."""
        conventions = {}

        function_names = []
        class_names = []
        constant_names = []
        variable_names = []

        for file_path in files[:15]:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        function_names.append(node.name)
                    elif isinstance(node, ast.ClassDef):
                        class_names.append(node.name)
                    elif isinstance(node, ast.Name):
                        if node.id.isupper() and len(node.id) > 1:
                            constant_names.append(node.id)
                        elif node.id.islower() or "_" in node.id:
                            variable_names.append(node.id)

            except Exception:
                continue

        # Analyze patterns
        if function_names:
            conventions["functions"] = self._identify_case(function_names)

        if class_names:
            conventions["classes"] = self._identify_case(class_names)

        if constant_names:
            conventions["constants"] = self._identify_case(constant_names)

        if variable_names:
            conventions["variables"] = self._identify_case(variable_names)

        return conventions

    def _identify_case(self, names: List[str]) -> str:
        """Identify the naming convention from a list of names."""
        if not names:
            return "unknown"

        snake_count = sum(1 for n in names if "_" in n and n.lower() == n)
        camel_count = sum(
            1 for n in names if n[0].islower() and any(c.isupper() for c in n[1:])
        )
        pascal_count = sum(
            1 for n in names if n[0].isupper() and any(c.islower() for c in n)
        )
        upper_count = sum(1 for n in names if n.isupper() and len(n) > 1)

        counts = {
            "snake_case": snake_count,
            "camelCase": camel_count,
            "PascalCase": pascal_count,
            "SCREAMING_SNAKE_CASE": upper_count,
        }

        best = max(counts.keys(), key=lambda k: counts[k])
        if counts[best] > len(names) * 0.3:
            return best

        return "mixed"

    def _detect_docstring_style(self, files: List[Path]) -> str:
        """Detect the docstring style used in the project."""
        style_scores = defaultdict(int)

        for file_path in files[:20]:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")

                # Look for docstrings
                docstrings = re.findall(r'"""[\s\S]*?"""', content)
                docstrings.extend(re.findall(r"'''[\s\S]*?'''", content))

                for doc in docstrings:
                    for style, patterns in DOCSTRING_PATTERNS.items():
                        for pattern in patterns:
                            if re.search(pattern, doc):
                                style_scores[style] += 1
                                break

            except Exception:
                continue

        if not style_scores:
            return "unknown"

        best_style = max(style_scores.keys(), key=lambda k: style_scores[k])
        return best_style

    def _detect_type_hints(self, files: List[Path]) -> bool:
        """Detect if the project uses type hints."""
        hint_count = 0
        function_count = 0

        for file_path in files[:20]:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        function_count += 1

                        # Check for return annotation
                        if node.returns:
                            hint_count += 1

                        # Check for argument annotations
                        for arg in node.args.args:
                            if arg.annotation:
                                hint_count += 1
                                break

            except Exception:
                continue

        # Consider type hints used if >30% of functions have them
        if function_count > 0:
            return hint_count / function_count > 0.3

        return False

    def _detect_async_style(self, files: List[Path]) -> bool:
        """Detect if the project uses async/await patterns."""
        async_count = 0

        for file_path in files[:20]:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, ast.AsyncFunctionDef):
                        async_count += 1
                    elif isinstance(node, ast.Await):
                        async_count += 1

            except Exception:
                continue

        return async_count >= 2  # At least 2 async patterns indicates async codebase

    def _detect_formatters(self) -> Tuple[Optional[str], Optional[str]]:
        """Detect formatting and linting tools from config files."""
        formatter = None
        linter = None

        # Check pyproject.toml
        pyproject = self.project_path / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                if "[tool.black]" in content:
                    formatter = "black"
                if "[tool.ruff]" in content:
                    linter = "ruff"
                if "[tool.isort]" in content and not formatter:
                    formatter = "isort"
                if "[tool.mypy]" in content:
                    linter = linter or "mypy"
            except Exception:
                pass

        # Check for standalone config files
        config_files = {
            ".black": "black",
            "ruff.toml": "ruff",
            ".ruff.toml": "ruff",
            ".flake8": "flake8",
            ".pylintrc": "pylint",
            "mypy.ini": "mypy",
            ".prettierrc": "prettier",
            ".eslintrc": "eslint",
            ".eslintrc.json": "eslint",
        }

        for file_name, tool in config_files.items():
            if (self.project_path / file_name).exists():
                if tool in {"black", "prettier", "isort"}:
                    formatter = formatter or tool
                else:
                    linter = linter or tool

        return formatter, linter

    def _find_config_files(self) -> List[str]:
        """Find all formatting/linting config files."""
        config_patterns = [
            ".black",
            ".flake8",
            ".pylintrc",
            "mypy.ini",
            ".mypy.ini",
            "ruff.toml",
            ".ruff.toml",
            ".isort.cfg",
            ".prettierrc",
            ".prettierrc.json",
            ".prettierrc.js",
            ".eslintrc",
            ".eslintrc.json",
            ".eslintrc.js",
            ".editorconfig",
            "tox.ini",
            "pytest.ini",
        ]

        found = []
        for pattern in config_patterns:
            if (self.project_path / pattern).exists():
                found.append(pattern)

        # Also check pyproject.toml sections
        pyproject = self.project_path / "pyproject.toml"
        if pyproject.exists():
            found.append("pyproject.toml")

        return found

    def _detect_test_framework(self, files: List[Path]) -> Optional[str]:
        """Detect the test framework used."""
        pytest_indicators = 0
        unittest_indicators = 0

        test_files = [f for f in files if "test" in str(f).lower()]

        for file_path in test_files[:10]:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")

                if "import pytest" in content or "@pytest" in content:
                    pytest_indicators += 1
                if "import unittest" in content or "unittest.TestCase" in content:
                    unittest_indicators += 1

            except Exception:
                continue

        # Check for conftest.py (strong pytest indicator)
        if (self.project_path / "conftest.py").exists() or any(
            (self.project_path / "tests" / "conftest.py").exists() for _ in [1]
        ):
            pytest_indicators += 2

        if pytest_indicators > unittest_indicators:
            return "pytest"
        elif unittest_indicators > 0:
            return "unittest"

        return None
