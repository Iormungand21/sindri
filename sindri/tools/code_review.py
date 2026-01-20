"""AI-powered code review and quality analysis tools for Sindri.

Phase 13 Tier 3: Provides tools for code quality analysis, code smell detection,
security auditing, dead code detection, and comprehensive review report generation.

Tools:
- AnalyzeCodeQualityTool: Calculate quality metrics (complexity, maintainability)
- DetectCodeSmellsTool: Identify code anti-patterns and smells
- SecurityAuditTool: Static security analysis for vulnerabilities
- DetectDeadCodeTool: Find unused code (imports, functions, variables)
- GenerateReviewReportTool: Generate comprehensive code review reports
"""

import ast
import hashlib
import importlib.util
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
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
# Language Configuration
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

# Directories to skip during analysis
SKIP_DIRS: set[str] = {
    "node_modules", "__pycache__", ".git", "dist", "build", ".tox",
    "venv", ".venv", "env", ".env", "target", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "site-packages", "egg-info", ".eggs",
}

# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════


class Severity(str, Enum):
    """Severity levels for findings."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    WARNING = "warning"
    HIGH = "high"
    ERROR = "error"
    CRITICAL = "critical"


class SmellType(str, Enum):
    """Types of code smells."""
    LONG_METHOD = "long_method"
    LARGE_CLASS = "large_class"
    DEEP_NESTING = "deep_nesting"
    LONG_PARAM_LIST = "long_parameter_list"
    MAGIC_NUMBER = "magic_number"
    DUPLICATE_CODE = "duplicate_code"
    GOD_CLASS = "god_class"
    COMPLEX_CONDITION = "complex_condition"


class SecurityCheckType(str, Enum):
    """Types of security checks."""
    HARDCODED_SECRET = "hardcoded_secret"
    SQL_INJECTION = "sql_injection"
    COMMAND_INJECTION = "command_injection"
    PATH_TRAVERSAL = "path_traversal"
    INSECURE_DESERIALIZATION = "insecure_deserialization"
    WEAK_CRYPTO = "weak_crypto"
    DEBUG_CODE = "debug_code"
    INSECURE_RANDOM = "insecure_random"
    EVAL_USAGE = "eval_usage"


class DeadCodeType(str, Enum):
    """Types of dead code."""
    UNUSED_IMPORT = "unused_import"
    UNUSED_FUNCTION = "unused_function"
    UNUSED_VARIABLE = "unused_variable"
    UNUSED_CLASS = "unused_class"
    UNREACHABLE_CODE = "unreachable_code"
    UNUSED_PARAMETER = "unused_parameter"


# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class QualityMetrics:
    """Quality metrics for a code unit."""
    total_lines: int = 0
    source_lines: int = 0  # SLOC (non-blank, non-comment)
    comment_lines: int = 0
    blank_lines: int = 0
    cyclomatic_complexity: int = 1
    cognitive_complexity: int = 0
    maintainability_index: float = 100.0
    halstead_volume: float = 0.0
    halstead_difficulty: float = 0.0
    halstead_effort: float = 0.0


@dataclass
class FunctionMetrics:
    """Metrics for a single function."""
    name: str
    file_path: str
    line_number: int
    line_count: int
    cyclomatic_complexity: int
    cognitive_complexity: int
    parameter_count: int
    nesting_depth: int
    return_count: int = 1


@dataclass
class CodeSmell:
    """Detected code smell."""
    smell_type: SmellType
    severity: Severity
    file_path: str
    line_number: int
    end_line: int
    name: str
    message: str
    suggestion: str
    code_snippet: str = ""


@dataclass
class SecurityFinding:
    """Security vulnerability finding."""
    rule_id: str
    check_type: SecurityCheckType
    severity: Severity
    confidence: str  # "low", "medium", "high"
    cwe_id: str
    title: str
    description: str
    file_path: str
    line_number: int
    column: int
    code_snippet: str
    remediation: str


@dataclass
class DeadCodeItem:
    """Detected dead code."""
    item_type: DeadCodeType
    name: str
    file_path: str
    line_number: int
    confidence: str  # "high", "medium", "low"
    reason: str
    suggestion: str


@dataclass
class FileAnalysis:
    """Analysis results for a single file."""
    file_path: str
    language: str
    metrics: QualityMetrics
    functions: list[FunctionMetrics] = field(default_factory=list)
    smells: list[CodeSmell] = field(default_factory=list)
    security_findings: list[SecurityFinding] = field(default_factory=list)
    dead_code: list[DeadCodeItem] = field(default_factory=list)


@dataclass
class ReviewReport:
    """Complete code review report."""
    title: str
    generated_at: str
    source_path: str
    files_analyzed: int
    total_issues: int
    quality_grade: str  # A, B, C, D, F
    summary_metrics: QualityMetrics
    file_analyses: list[FileAnalysis] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# Security Patterns
# ═══════════════════════════════════════════════════════════════════════════════

# Patterns for detecting hardcoded secrets
SECRET_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\']([^"\']{16,})["\']'), "API Key", "CWE-798"),
    (re.compile(r'(?i)(secret[_-]?key|secretkey)\s*[:=]\s*["\']([^"\']{16,})["\']'), "Secret Key", "CWE-798"),
    (re.compile(r'(?i)(password|passwd|pwd)\s*[:=]\s*["\']([^"\']{4,})["\']'), "Password", "CWE-798"),
    (re.compile(r'(?i)(aws[_-]?access[_-]?key)\s*[:=]\s*["\']([A-Z0-9]{20})["\']'), "AWS Access Key", "CWE-798"),
    (re.compile(r'(?i)(aws[_-]?secret)\s*[:=]\s*["\']([^"\']{40})["\']'), "AWS Secret", "CWE-798"),
    (re.compile(r'(?i)(token|auth[_-]?token)\s*[:=]\s*["\']([^"\']{20,})["\']'), "Token", "CWE-798"),
    (re.compile(r'(?i)(private[_-]?key)\s*[:=]\s*["\']([^"\']{20,})["\']'), "Private Key", "CWE-798"),
    (re.compile(r'AKIA[0-9A-Z]{16}'), "AWS Access Key ID", "CWE-798"),
    (re.compile(r'ghp_[a-zA-Z0-9]{36}'), "GitHub Token", "CWE-798"),
    (re.compile(r'sk-[a-zA-Z0-9]{48}'), "OpenAI API Key", "CWE-798"),
]

# SQL injection patterns
SQL_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'execute\s*\(\s*f["\'].*\{.*\}'), "f-string in SQL execute"),
    (re.compile(r'execute\s*\(\s*["\'].*%s.*%'), "% formatting in SQL"),
    (re.compile(r'execute\s*\(\s*.*\+.*\+'), "String concatenation in SQL"),
    (re.compile(r'cursor\.execute\s*\(\s*f["\']'), "f-string in cursor.execute"),
    (re.compile(r'\.format\s*\(.*\).*execute'), ".format() with execute"),
    # Detect SQL-like f-strings assigned to variables (query = f"SELECT...")
    (re.compile(r'=\s*f["\']SELECT\s+.*\{'), "f-string SQL SELECT assigned to variable"),
    (re.compile(r'=\s*f["\']INSERT\s+.*\{'), "f-string SQL INSERT assigned to variable"),
    (re.compile(r'=\s*f["\']UPDATE\s+.*\{'), "f-string SQL UPDATE assigned to variable"),
    (re.compile(r'=\s*f["\']DELETE\s+.*\{'), "f-string SQL DELETE assigned to variable"),
]

# Command injection patterns
COMMAND_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'subprocess\.(call|run|Popen)\s*\([^)]*shell\s*=\s*True'), "shell=True in subprocess"),
    (re.compile(r'os\.system\s*\(\s*f["\']'), "f-string in os.system"),
    (re.compile(r'os\.system\s*\([^)]*\+'), "String concat in os.system"),
    (re.compile(r'os\.popen\s*\(\s*f["\']'), "f-string in os.popen"),
    (re.compile(r'eval\s*\(\s*[^"\']+\)'), "eval with variable"),
    (re.compile(r'exec\s*\(\s*[^"\']+\)'), "exec with variable"),
]

# Insecure deserialization patterns
DESERIALIZATION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'pickle\.loads?\s*\('), "pickle.load usage"),
    (re.compile(r'yaml\.load\s*\([^)]*(?!Loader)'), "yaml.load without SafeLoader"),
    (re.compile(r'yaml\.unsafe_load'), "yaml.unsafe_load"),
    (re.compile(r'marshal\.loads?\s*\('), "marshal.load usage"),
]

# Weak crypto patterns
WEAK_CRYPTO_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'hashlib\.md5\s*\('), "MD5 hash (weak)"),
    (re.compile(r'hashlib\.sha1\s*\('), "SHA1 hash (weak for security)"),
    (re.compile(r'DES\.new\s*\('), "DES encryption (weak)"),
    (re.compile(r'RC4\.new\s*\('), "RC4 encryption (weak)"),
    (re.compile(r'Blowfish\.new\s*\('), "Blowfish encryption (weak)"),
]

# Debug code patterns
DEBUG_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'^\s*import\s+pdb'), "pdb import"),
    (re.compile(r'pdb\.set_trace\s*\('), "pdb.set_trace()"),
    (re.compile(r'breakpoint\s*\(\s*\)'), "breakpoint()"),
    (re.compile(r'^\s*debugger\s*;?$', re.MULTILINE), "debugger statement"),
    (re.compile(r'console\.log\s*\('), "console.log"),
    (re.compile(r'print\s*\(\s*["\']DEBUG'), "DEBUG print statement"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════


def _calculate_entropy(s: str) -> float:
    """Calculate Shannon entropy of a string."""
    if not s:
        return 0.0
    freq = Counter(s)
    length = len(s)
    entropy = -sum((count / length) * math.log2(count / length) for count in freq.values())
    return entropy


def _is_likely_secret(value: str) -> bool:
    """Check if a value is likely a secret based on entropy and length."""
    if len(value) < 8:
        return False
    # High entropy (>4.0) suggests randomness typical of secrets
    entropy = _calculate_entropy(value)
    return entropy > 4.0 and len(value) >= 16


def _calculate_cyclomatic_complexity(source: str, language: str = "python") -> int:
    """Calculate cyclomatic complexity from source code."""
    if language != "python":
        # Simple regex-based counting for non-Python
        complexity = 1
        decision_keywords = [
            r'\bif\b', r'\belse\s+if\b', r'\belif\b', r'\bfor\b', r'\bwhile\b',
            r'\bcatch\b', r'\bcase\b', r'\b\?\s*:', r'\band\b', r'\bor\b',
            r'\b&&\b', r'\b\|\|\b',
        ]
        for pattern in decision_keywords:
            complexity += len(re.findall(pattern, source))
        return complexity

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 1

    complexity = 1
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            complexity += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            complexity += 1
            if node.ifs:
                complexity += len(node.ifs)
        elif isinstance(node, (ast.IfExp,)):  # Ternary
            complexity += 1
        elif isinstance(node, ast.Match):  # Python 3.10+ match
            complexity += 1
        elif isinstance(node, ast.match_case):
            complexity += 1

    return complexity


def _calculate_cognitive_complexity(source: str, language: str = "python") -> int:
    """Calculate cognitive complexity (nesting-aware)."""
    if language != "python":
        return _calculate_cyclomatic_complexity(source, language)

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0

    complexity = 0
    nesting_level = 0

    class CognitiveVisitor(ast.NodeVisitor):
        nonlocal complexity, nesting_level

        def visit_If(self, node):
            nonlocal complexity, nesting_level
            complexity += 1 + nesting_level
            nesting_level += 1
            self.generic_visit(node)
            nesting_level -= 1

        def visit_For(self, node):
            nonlocal complexity, nesting_level
            complexity += 1 + nesting_level
            nesting_level += 1
            self.generic_visit(node)
            nesting_level -= 1

        def visit_While(self, node):
            nonlocal complexity, nesting_level
            complexity += 1 + nesting_level
            nesting_level += 1
            self.generic_visit(node)
            nesting_level -= 1

        def visit_ExceptHandler(self, node):
            nonlocal complexity, nesting_level
            complexity += 1 + nesting_level
            nesting_level += 1
            self.generic_visit(node)
            nesting_level -= 1

        def visit_BoolOp(self, node):
            nonlocal complexity
            complexity += len(node.values) - 1
            self.generic_visit(node)

        def visit_FunctionDef(self, node):
            nonlocal nesting_level
            old_nesting = nesting_level
            nesting_level = 0
            self.generic_visit(node)
            nesting_level = old_nesting

        visit_AsyncFunctionDef = visit_FunctionDef

    CognitiveVisitor().visit(tree)
    return complexity


def _calculate_maintainability_index(
    halstead_volume: float,
    cyclomatic_complexity: int,
    loc: int
) -> float:
    """Calculate Microsoft maintainability index (0-100 scale)."""
    if halstead_volume <= 0 or loc <= 0:
        return 100.0

    # Original formula
    mi = 171 - 5.2 * math.log(halstead_volume) - 0.23 * cyclomatic_complexity - 16.2 * math.log(loc)

    # Normalize to 0-100
    mi = max(0, min(100, mi * 100 / 171))
    return round(mi, 2)


def _calculate_halstead_metrics(source: str, language: str = "python") -> tuple[float, float, float]:
    """Calculate Halstead metrics: volume, difficulty, effort."""
    if language != "python":
        # Simplified for non-Python: estimate from token count
        tokens = re.findall(r'\b\w+\b|[^\w\s]', source)
        n1 = len(set(t for t in tokens if not t.isalnum()))  # Unique operators
        n2 = len(set(t for t in tokens if t.isalnum()))  # Unique operands
        N1 = len([t for t in tokens if not t.isalnum()])  # Total operators
        N2 = len([t for t in tokens if t.isalnum()])  # Total operands

        n = n1 + n2  # Vocabulary
        N = N1 + N2  # Length

        if n == 0 or n2 == 0:
            return 0.0, 0.0, 0.0

        volume = N * math.log2(n) if n > 0 else 0
        difficulty = (n1 / 2) * (N2 / n2) if n2 > 0 else 0
        effort = volume * difficulty

        return volume, difficulty, effort

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0.0, 0.0, 0.0

    operators: set[str] = set()
    operands: set[str] = set()
    total_operators = 0
    total_operands = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp):
            operators.add(type(node.op).__name__)
            total_operators += 1
        elif isinstance(node, ast.UnaryOp):
            operators.add(type(node.op).__name__)
            total_operators += 1
        elif isinstance(node, ast.Compare):
            for op in node.ops:
                operators.add(type(op).__name__)
                total_operators += 1
        elif isinstance(node, ast.BoolOp):
            operators.add(type(node.op).__name__)
            total_operators += 1
        elif isinstance(node, ast.Name):
            operands.add(node.id)
            total_operands += 1
        elif isinstance(node, ast.Constant):
            operands.add(str(node.value))
            total_operands += 1

    n1 = len(operators)
    n2 = len(operands)
    N1 = total_operators
    N2 = total_operands

    n = n1 + n2  # Vocabulary
    N = N1 + N2  # Length

    if n == 0 or n2 == 0:
        return 0.0, 0.0, 0.0

    volume = N * math.log2(n) if n > 0 else 0
    difficulty = (n1 / 2) * (N2 / n2) if n2 > 0 else 0
    effort = volume * difficulty

    return round(volume, 2), round(difficulty, 2), round(effort, 2)


def _count_lines(source: str) -> tuple[int, int, int, int]:
    """Count total, source, comment, and blank lines."""
    lines = source.splitlines()
    total = len(lines)
    blank = sum(1 for line in lines if not line.strip())
    comment = 0
    source_lines = 0

    in_docstring = False
    docstring_char = None

    for line in lines:
        stripped = line.strip()

        # Handle docstrings
        if not in_docstring:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                docstring_char = stripped[:3]
                if stripped.count(docstring_char) >= 2 and len(stripped) > 6:
                    comment += 1
                else:
                    in_docstring = True
                    comment += 1
                continue
        else:
            comment += 1
            if docstring_char in stripped and not stripped.startswith(docstring_char):
                in_docstring = False
            continue

        if not stripped:
            continue
        elif stripped.startswith('#') or stripped.startswith('//'):
            comment += 1
        else:
            source_lines += 1

    return total, source_lines, comment, blank


def _calculate_nesting_depth(source: str, language: str = "python") -> int:
    """Calculate maximum nesting depth."""
    if language != "python":
        # Simple brace counting for non-Python
        max_depth = 0
        current = 0
        for char in source:
            if char == '{':
                current += 1
                max_depth = max(max_depth, current)
            elif char == '}':
                current = max(0, current - 1)
        return max_depth

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0

    max_depth = 0

    def get_depth(node, current_depth=0):
        nonlocal max_depth
        max_depth = max(max_depth, current_depth)

        nested_types = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)

        for child in ast.iter_child_nodes(node):
            if isinstance(child, nested_types):
                get_depth(child, current_depth + 1)
            else:
                get_depth(child, current_depth)

    get_depth(tree)
    return max_depth


def _extract_functions_python(source: str, file_path: str) -> list[FunctionMetrics]:
    """Extract function metrics from Python source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    functions: list[FunctionMetrics] = []
    lines = source.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Get function body source
            start_line = node.lineno - 1
            end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line + 1
            func_lines = lines[start_line:end_line]
            func_source = '\n'.join(func_lines)

            # Calculate metrics
            line_count = len(func_lines)
            complexity = _calculate_cyclomatic_complexity(func_source)
            cognitive = _calculate_cognitive_complexity(func_source)
            param_count = len(node.args.args) + len(node.args.kwonlyargs)
            if node.args.vararg:
                param_count += 1
            if node.args.kwarg:
                param_count += 1

            nesting = _calculate_nesting_depth(func_source)

            # Count returns
            return_count = sum(1 for n in ast.walk(node) if isinstance(n, ast.Return))

            functions.append(FunctionMetrics(
                name=node.name,
                file_path=file_path,
                line_number=node.lineno,
                line_count=line_count,
                cyclomatic_complexity=complexity,
                cognitive_complexity=cognitive,
                parameter_count=param_count,
                nesting_depth=nesting,
                return_count=return_count,
            ))

    return functions


def _find_source_files(path: Path, recursive: bool = False) -> list[Path]:
    """Find all source files in a path."""
    files: list[Path] = []

    if path.is_file():
        if path.suffix in LANGUAGE_CONFIG:
            files.append(path)
    elif path.is_dir():
        pattern = "**/*" if recursive else "*"
        for ext in LANGUAGE_CONFIG:
            for file_path in path.glob(f"{pattern}{ext}"):
                # Skip excluded directories
                if any(skip in file_path.parts for skip in SKIP_DIRS):
                    continue
                files.append(file_path)

    return sorted(files)


def _format_output(data: Any, output_format: str) -> str:
    """Format output in the specified format."""
    if output_format == "json":
        return json.dumps(data, indent=2, default=str)
    elif output_format == "markdown":
        return _format_as_markdown(data)
    elif output_format == "sarif":
        return _format_as_sarif(data)
    else:  # text
        return _format_as_text(data)


def _format_as_markdown(data: Any) -> str:
    """Format data as markdown."""
    lines: list[str] = []

    if isinstance(data, dict):
        if "metrics" in data:
            # Quality metrics output
            metrics = data["metrics"]
            lines.append("# Code Quality Analysis\n")
            lines.append(f"**File:** `{data.get('file', 'N/A')}`\n")
            lines.append("## Metrics Summary\n")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| Total Lines | {metrics.get('total_lines', 0)} |")
            lines.append(f"| Source Lines (SLOC) | {metrics.get('source_lines', 0)} |")
            lines.append(f"| Comment Lines | {metrics.get('comment_lines', 0)} |")
            lines.append(f"| Blank Lines | {metrics.get('blank_lines', 0)} |")
            lines.append(f"| Cyclomatic Complexity | {metrics.get('cyclomatic_complexity', 1)} |")
            lines.append(f"| Cognitive Complexity | {metrics.get('cognitive_complexity', 0)} |")
            lines.append(f"| Maintainability Index | {metrics.get('maintainability_index', 100):.1f} |")
            lines.append(f"| Comment Ratio | {metrics.get('comment_ratio', 0):.1%} |")

            if "functions" in data and data["functions"]:
                lines.append("\n## Function Metrics\n")
                lines.append("| Function | Lines | Complexity | Parameters | Nesting |")
                lines.append("|----------|-------|------------|------------|---------|")
                for func in data["functions"]:
                    lines.append(
                        f"| `{func['name']}` | {func['line_count']} | "
                        f"{func['cyclomatic_complexity']} | {func['parameter_count']} | "
                        f"{func['nesting_depth']} |"
                    )

            if "issues" in data and data["issues"]:
                lines.append("\n## Issues Found\n")
                for issue in data["issues"]:
                    severity_icon = {"error": "🔴", "warning": "⚠️", "info": "ℹ️"}.get(
                        issue.get("severity", "info"), "ℹ️"
                    )
                    lines.append(f"- {severity_icon} **{issue.get('message', '')}**")
                    lines.append(f"  - Location: Line {issue.get('line', 0)}")
                    if issue.get("suggestion"):
                        lines.append(f"  - Suggestion: {issue['suggestion']}")

        elif "smells" in data:
            # Code smells output
            lines.append("# Code Smell Detection\n")
            lines.append(f"**Files Analyzed:** {data.get('files_analyzed', 0)}\n")
            lines.append(f"**Total Smells Found:** {data.get('total_smells', 0)}\n")

            if data.get("smells"):
                # Group by severity
                by_severity: dict[str, list] = {}
                for smell in data["smells"]:
                    sev = smell.get("severity", "info")
                    by_severity.setdefault(sev, []).append(smell)

                for severity in ["error", "warning", "info"]:
                    if severity in by_severity:
                        icon = {"error": "🔴", "warning": "⚠️", "info": "ℹ️"}[severity]
                        lines.append(f"\n## {icon} {severity.title()} ({len(by_severity[severity])})\n")
                        for smell in by_severity[severity]:
                            lines.append(f"### {smell.get('smell_type', 'Unknown')}: `{smell.get('name', '')}`")
                            lines.append(f"- **File:** `{smell.get('file_path', '')}:{smell.get('line_number', 0)}`")
                            lines.append(f"- **Message:** {smell.get('message', '')}")
                            if smell.get("suggestion"):
                                lines.append(f"- **Suggestion:** {smell['suggestion']}")
                            lines.append("")

        elif "findings" in data:
            # Security findings output
            lines.append("# Security Audit Report\n")
            lines.append(f"**Files Scanned:** {data.get('files_scanned', 0)}\n")
            lines.append(f"**Total Findings:** {data.get('total_findings', 0)}\n")

            severity_counts = data.get("severity_counts", {})
            if severity_counts:
                lines.append("\n## Severity Summary\n")
                lines.append("| Severity | Count |")
                lines.append("|----------|-------|")
                for sev in ["critical", "high", "medium", "low", "info"]:
                    if sev in severity_counts:
                        lines.append(f"| {sev.upper()} | {severity_counts[sev]} |")

            if data.get("findings"):
                lines.append("\n## Findings\n")
                for finding in data["findings"]:
                    severity_icon = {
                        "critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "ℹ️"
                    }.get(finding.get("severity", "info"), "ℹ️")
                    lines.append(f"### {severity_icon} {finding.get('rule_id', '')}: {finding.get('title', '')}")
                    lines.append(f"- **Severity:** {finding.get('severity', 'N/A').upper()}")
                    lines.append(f"- **CWE:** {finding.get('cwe_id', 'N/A')}")
                    lines.append(f"- **File:** `{finding.get('file_path', '')}:{finding.get('line_number', 0)}`")
                    lines.append(f"- **Description:** {finding.get('description', '')}")
                    if finding.get("remediation"):
                        lines.append(f"- **Remediation:** {finding['remediation']}")
                    if finding.get("code_snippet"):
                        lines.append(f"\n```\n{finding['code_snippet']}\n```\n")

        elif "dead_code" in data:
            # Dead code output
            lines.append("# Dead Code Detection\n")
            lines.append(f"**Files Analyzed:** {data.get('files_analyzed', 0)}\n")
            lines.append(f"**Dead Code Items Found:** {data.get('total_items', 0)}\n")

            if data.get("dead_code"):
                # Group by type
                by_type: dict[str, list] = {}
                for item in data["dead_code"]:
                    item_type = item.get("item_type", "unknown")
                    by_type.setdefault(item_type, []).append(item)

                for item_type, items in by_type.items():
                    lines.append(f"\n## {item_type.replace('_', ' ').title()} ({len(items)})\n")
                    for item in items:
                        lines.append(f"- `{item.get('name', '')}` at `{item.get('file_path', '')}:{item.get('line_number', 0)}`")
                        lines.append(f"  - Confidence: {item.get('confidence', 'N/A')}")
                        lines.append(f"  - Reason: {item.get('reason', 'N/A')}")

    return '\n'.join(lines)


def _format_as_text(data: Any) -> str:
    """Format data as plain text."""
    lines: list[str] = []

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{key}:")
                for k, v in value.items():
                    lines.append(f"  {k}: {v}")
            elif isinstance(value, list):
                lines.append(f"{key}: ({len(value)} items)")
                for item in value[:10]:  # Limit output
                    if isinstance(item, dict):
                        lines.append(f"  - {item.get('name', item.get('title', str(item)))}")
                    else:
                        lines.append(f"  - {item}")
                if len(value) > 10:
                    lines.append(f"  ... and {len(value) - 10} more")
            else:
                lines.append(f"{key}: {value}")

    return '\n'.join(lines)


def _format_as_sarif(data: Any) -> str:
    """Format data as SARIF 2.1.0 for GitHub Security tab."""
    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "sindri-code-review",
                    "version": "1.0.0",
                    "informationUri": "https://github.com/sindri",
                    "rules": []
                }
            },
            "results": []
        }]
    }

    run = sarif["runs"][0]
    rules_map: dict[str, int] = {}

    # Handle security findings
    if "findings" in data:
        for finding in data["findings"]:
            rule_id = finding.get("rule_id", "UNKNOWN")
            if rule_id not in rules_map:
                rules_map[rule_id] = len(run["tool"]["driver"]["rules"])
                run["tool"]["driver"]["rules"].append({
                    "id": rule_id,
                    "name": finding.get("title", rule_id),
                    "shortDescription": {"text": finding.get("description", "")},
                    "help": {"text": finding.get("remediation", "")},
                    "properties": {"cwe": finding.get("cwe_id", "")}
                })

            severity_map = {"critical": "error", "high": "error", "medium": "warning", "low": "note", "info": "note"}

            run["results"].append({
                "ruleId": rule_id,
                "ruleIndex": rules_map[rule_id],
                "level": severity_map.get(finding.get("severity", "info"), "note"),
                "message": {"text": finding.get("description", "")},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": finding.get("file_path", "")},
                        "region": {
                            "startLine": finding.get("line_number", 1),
                            "startColumn": finding.get("column", 1)
                        }
                    }
                }]
            })

    # Handle code smells
    elif "smells" in data:
        for smell in data["smells"]:
            rule_id = f"SMELL-{smell.get('smell_type', 'UNKNOWN').upper()}"
            if rule_id not in rules_map:
                rules_map[rule_id] = len(run["tool"]["driver"]["rules"])
                run["tool"]["driver"]["rules"].append({
                    "id": rule_id,
                    "name": smell.get("smell_type", "unknown"),
                    "shortDescription": {"text": smell.get("message", "")},
                    "help": {"text": smell.get("suggestion", "")}
                })

            severity_map = {"error": "error", "warning": "warning", "info": "note"}

            run["results"].append({
                "ruleId": rule_id,
                "ruleIndex": rules_map[rule_id],
                "level": severity_map.get(smell.get("severity", "info"), "note"),
                "message": {"text": smell.get("message", "")},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": smell.get("file_path", "")},
                        "region": {
                            "startLine": smell.get("line_number", 1),
                            "endLine": smell.get("end_line", smell.get("line_number", 1))
                        }
                    }
                }]
            })

    return json.dumps(sarif, indent=2)


def _calculate_grade(metrics: QualityMetrics, smell_count: int, security_count: int) -> str:
    """Calculate overall quality grade A-F."""
    score = 100

    # Penalize low maintainability
    if metrics.maintainability_index < 20:
        score -= 40
    elif metrics.maintainability_index < 40:
        score -= 25
    elif metrics.maintainability_index < 60:
        score -= 10

    # Penalize high complexity
    if metrics.cyclomatic_complexity > 50:
        score -= 30
    elif metrics.cyclomatic_complexity > 30:
        score -= 20
    elif metrics.cyclomatic_complexity > 20:
        score -= 10

    # Penalize code smells
    score -= min(30, smell_count * 2)

    # Penalize security issues (heavier penalty)
    score -= min(40, security_count * 5)

    # Map to grade
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: AnalyzeCodeQualityTool
# ═══════════════════════════════════════════════════════════════════════════════


class AnalyzeCodeQualityTool(Tool):
    """Analyze code quality metrics including complexity, maintainability, and LOC."""

    name = "analyze_code_quality"
    description = (
        "Calculate comprehensive code quality metrics including cyclomatic complexity, "
        "maintainability index, lines of code, comment ratio, and Halstead metrics."
    )
    parameters = {
        "type": "object",
        "properties": {
            "source_path": {
                "type": "string",
                "description": "Path to source file or directory to analyze"
            },
            "recursive": {
                "type": "boolean",
                "description": "Recursively analyze directories (default: false)"
            },
            "threshold_complexity": {
                "type": "integer",
                "description": "Cyclomatic complexity threshold for warnings (default: 10)"
            },
            "threshold_maintainability": {
                "type": "number",
                "description": "Maintainability index threshold (default: 20)"
            },
            "output_format": {
                "type": "string",
                "enum": ["text", "json", "markdown"],
                "description": "Output format (default: markdown)"
            },
            "include_functions": {
                "type": "boolean",
                "description": "Include per-function metrics (default: true)"
            }
        },
        "required": ["source_path"]
    }

    async def execute(
        self,
        source_path: str,
        recursive: bool = False,
        threshold_complexity: int = 10,
        threshold_maintainability: float = 20.0,
        output_format: str = "markdown",
        include_functions: bool = True,
        **kwargs
    ) -> ToolResult:
        """Execute code quality analysis."""
        try:
            path = self._resolve_path(source_path)

            if not path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path not found: {path}"
                )

            files = _find_source_files(path, recursive)
            if not files:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"No supported source files found in {path}"
                )

            # Aggregate metrics
            total_metrics = QualityMetrics()
            all_functions: list[dict] = []
            all_issues: list[dict] = []

            for file_path in files:
                async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    source = await f.read()

                lang = EXT_TO_LANG.get(file_path.suffix, "python")
                total, sloc, comments, blank = _count_lines(source)
                complexity = _calculate_cyclomatic_complexity(source, lang)
                cognitive = _calculate_cognitive_complexity(source, lang)
                volume, difficulty, effort = _calculate_halstead_metrics(source, lang)
                mi = _calculate_maintainability_index(volume, complexity, sloc)

                total_metrics.total_lines += total
                total_metrics.source_lines += sloc
                total_metrics.comment_lines += comments
                total_metrics.blank_lines += blank
                total_metrics.cyclomatic_complexity += complexity
                total_metrics.cognitive_complexity += cognitive
                total_metrics.halstead_volume += volume
                total_metrics.halstead_difficulty += difficulty
                total_metrics.halstead_effort += effort

                # Extract function metrics
                if include_functions and lang == "python":
                    funcs = _extract_functions_python(source, str(file_path))
                    for func in funcs:
                        all_functions.append({
                            "name": func.name,
                            "file": str(file_path),
                            "line_number": func.line_number,
                            "line_count": func.line_count,
                            "cyclomatic_complexity": func.cyclomatic_complexity,
                            "cognitive_complexity": func.cognitive_complexity,
                            "parameter_count": func.parameter_count,
                            "nesting_depth": func.nesting_depth,
                        })

                        # Check thresholds
                        if func.cyclomatic_complexity > threshold_complexity:
                            all_issues.append({
                                "severity": "warning",
                                "message": f"Function `{func.name}` has high complexity ({func.cyclomatic_complexity})",
                                "line": func.line_number,
                                "file": str(file_path),
                                "suggestion": f"Consider refactoring to reduce complexity below {threshold_complexity}"
                            })

                # File-level issues
                if mi < threshold_maintainability:
                    all_issues.append({
                        "severity": "warning",
                        "message": f"Low maintainability index ({mi:.1f})",
                        "file": str(file_path),
                        "suggestion": "Improve code structure, add comments, reduce complexity"
                    })

            # Calculate aggregate maintainability
            if total_metrics.source_lines > 0:
                total_metrics.maintainability_index = _calculate_maintainability_index(
                    total_metrics.halstead_volume,
                    total_metrics.cyclomatic_complexity,
                    total_metrics.source_lines
                )

            # Prepare output
            comment_ratio = (
                total_metrics.comment_lines / total_metrics.source_lines
                if total_metrics.source_lines > 0 else 0
            )

            result_data = {
                "file": str(path),
                "files_analyzed": len(files),
                "metrics": {
                    "total_lines": total_metrics.total_lines,
                    "source_lines": total_metrics.source_lines,
                    "comment_lines": total_metrics.comment_lines,
                    "blank_lines": total_metrics.blank_lines,
                    "cyclomatic_complexity": total_metrics.cyclomatic_complexity,
                    "cognitive_complexity": total_metrics.cognitive_complexity,
                    "maintainability_index": total_metrics.maintainability_index,
                    "comment_ratio": comment_ratio,
                    "halstead_volume": total_metrics.halstead_volume,
                    "halstead_difficulty": total_metrics.halstead_difficulty,
                    "halstead_effort": total_metrics.halstead_effort,
                },
                "functions": all_functions if include_functions else [],
                "issues": all_issues,
            }

            output = _format_output(result_data, output_format)

            log.info(
                "code_quality_analyzed",
                path=str(path),
                files=len(files),
                complexity=total_metrics.cyclomatic_complexity,
                maintainability=total_metrics.maintainability_index,
            )

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "files_analyzed": len(files),
                    "total_lines": total_metrics.total_lines,
                    "cyclomatic_complexity": total_metrics.cyclomatic_complexity,
                    "maintainability_index": total_metrics.maintainability_index,
                    "issues_found": len(all_issues),
                }
            )

        except Exception as e:
            log.error("code_quality_analysis_failed", error=str(e), path=source_path)
            return ToolResult(
                success=False,
                output="",
                error=f"Quality analysis failed: {e}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: DetectCodeSmellsTool
# ═══════════════════════════════════════════════════════════════════════════════


class DetectCodeSmellsTool(Tool):
    """Detect code smells and anti-patterns."""

    name = "detect_code_smells"
    description = (
        "Identify code anti-patterns and 'smells' such as long methods, large classes, "
        "deep nesting, duplicate code patterns, and magic numbers."
    )
    parameters = {
        "type": "object",
        "properties": {
            "source_path": {
                "type": "string",
                "description": "Path to source file or directory"
            },
            "recursive": {
                "type": "boolean",
                "description": "Recursively analyze directories (default: false)"
            },
            "smells_to_check": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific smells to check (default: all)"
            },
            "thresholds": {
                "type": "object",
                "description": "Custom thresholds for smell detection"
            },
            "output_format": {
                "type": "string",
                "enum": ["text", "json", "markdown", "sarif"],
                "description": "Output format (default: markdown)"
            },
            "severity_filter": {
                "type": "string",
                "enum": ["all", "warning", "error"],
                "description": "Filter by severity (default: all)"
            }
        },
        "required": ["source_path"]
    }

    # Default thresholds
    DEFAULT_THRESHOLDS = {
        "method_lines": 50,
        "class_lines": 300,
        "class_methods": 20,
        "nesting_depth": 4,
        "parameters": 5,
        "complexity": 10,
    }

    async def execute(
        self,
        source_path: str,
        recursive: bool = False,
        smells_to_check: Optional[list[str]] = None,
        thresholds: Optional[dict] = None,
        output_format: str = "markdown",
        severity_filter: str = "all",
        **kwargs
    ) -> ToolResult:
        """Execute code smell detection."""
        try:
            path = self._resolve_path(source_path)

            if not path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path not found: {path}"
                )

            files = _find_source_files(path, recursive)
            if not files:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"No supported source files found in {path}"
                )

            # Merge thresholds
            thresh = {**self.DEFAULT_THRESHOLDS, **(thresholds or {})}

            # Determine which smells to check
            all_smell_types = [s.value for s in SmellType]
            checks = smells_to_check if smells_to_check else all_smell_types

            all_smells: list[dict] = []

            for file_path in files:
                async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    source = await f.read()

                lang = EXT_TO_LANG.get(file_path.suffix, "python")
                lines = source.splitlines()

                # Python-specific analysis
                if lang == "python":
                    try:
                        tree = ast.parse(source)
                        smells = self._detect_python_smells(tree, source, str(file_path), thresh, checks)
                        all_smells.extend(smells)
                    except SyntaxError:
                        pass

                # Language-agnostic checks
                if SmellType.MAGIC_NUMBER.value in checks:
                    magic_smells = self._detect_magic_numbers(lines, str(file_path))
                    all_smells.extend(magic_smells)

                if SmellType.DEEP_NESTING.value in checks:
                    nesting_smells = self._detect_deep_nesting(source, str(file_path), lang, thresh["nesting_depth"])
                    all_smells.extend(nesting_smells)

            # Apply severity filter
            if severity_filter != "all":
                all_smells = [s for s in all_smells if s["severity"] == severity_filter]

            result_data = {
                "files_analyzed": len(files),
                "total_smells": len(all_smells),
                "smells": all_smells,
                "thresholds_used": thresh,
            }

            output = _format_output(result_data, output_format)

            log.info(
                "code_smells_detected",
                path=str(path),
                files=len(files),
                smells=len(all_smells),
            )

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "files_analyzed": len(files),
                    "total_smells": len(all_smells),
                    "by_type": Counter(s["smell_type"] for s in all_smells),
                }
            )

        except Exception as e:
            log.error("code_smell_detection_failed", error=str(e), path=source_path)
            return ToolResult(
                success=False,
                output="",
                error=f"Smell detection failed: {e}"
            )

    def _detect_python_smells(
        self,
        tree: ast.AST,
        source: str,
        file_path: str,
        thresh: dict,
        checks: list[str]
    ) -> list[dict]:
        """Detect Python-specific code smells."""
        smells: list[dict] = []
        lines = source.splitlines()

        for node in ast.walk(tree):
            # Long method
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if SmellType.LONG_METHOD.value in checks:
                    end_line = getattr(node, 'end_lineno', node.lineno + 1)
                    line_count = end_line - node.lineno
                    if line_count > thresh["method_lines"]:
                        smells.append({
                            "smell_type": SmellType.LONG_METHOD.value,
                            "severity": "warning" if line_count < thresh["method_lines"] * 2 else "error",
                            "file_path": file_path,
                            "line_number": node.lineno,
                            "end_line": end_line,
                            "name": node.name,
                            "message": f"Method `{node.name}` is too long ({line_count} lines, max {thresh['method_lines']})",
                            "suggestion": "Extract helper methods or break into smaller functions",
                        })

                # Long parameter list
                if SmellType.LONG_PARAM_LIST.value in checks:
                    param_count = len(node.args.args) + len(node.args.kwonlyargs)
                    if node.args.vararg:
                        param_count += 1
                    if node.args.kwarg:
                        param_count += 1

                    if param_count > thresh["parameters"]:
                        smells.append({
                            "smell_type": SmellType.LONG_PARAM_LIST.value,
                            "severity": "warning",
                            "file_path": file_path,
                            "line_number": node.lineno,
                            "end_line": node.lineno,
                            "name": node.name,
                            "message": f"Function `{node.name}` has too many parameters ({param_count}, max {thresh['parameters']})",
                            "suggestion": "Consider using a configuration object or dataclass",
                        })

            # Large class
            if isinstance(node, ast.ClassDef):
                if SmellType.LARGE_CLASS.value in checks:
                    end_line = getattr(node, 'end_lineno', node.lineno + 1)
                    line_count = end_line - node.lineno

                    method_count = sum(
                        1 for child in ast.iter_child_nodes(node)
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    )

                    if line_count > thresh["class_lines"] or method_count > thresh["class_methods"]:
                        reason = []
                        if line_count > thresh["class_lines"]:
                            reason.append(f"{line_count} lines")
                        if method_count > thresh["class_methods"]:
                            reason.append(f"{method_count} methods")

                        smells.append({
                            "smell_type": SmellType.LARGE_CLASS.value,
                            "severity": "warning",
                            "file_path": file_path,
                            "line_number": node.lineno,
                            "end_line": end_line,
                            "name": node.name,
                            "message": f"Class `{node.name}` is too large ({', '.join(reason)})",
                            "suggestion": "Consider splitting into smaller, focused classes",
                        })

                # God class (many dependencies)
                if SmellType.GOD_CLASS.value in checks:
                    # Count unique attribute accesses and method calls
                    class_source = '\n'.join(lines[node.lineno - 1:getattr(node, 'end_lineno', node.lineno)])
                    dependencies = set()

                    for child in ast.walk(node):
                        if isinstance(child, ast.Attribute):
                            if isinstance(child.value, ast.Name) and child.value.id != 'self':
                                dependencies.add(f"{child.value.id}.{child.attr}")

                    if len(dependencies) > 10:  # Threshold for external dependencies
                        smells.append({
                            "smell_type": SmellType.GOD_CLASS.value,
                            "severity": "warning",
                            "file_path": file_path,
                            "line_number": node.lineno,
                            "end_line": getattr(node, 'end_lineno', node.lineno),
                            "name": node.name,
                            "message": f"Class `{node.name}` has too many external dependencies ({len(dependencies)})",
                            "suggestion": "Apply Single Responsibility Principle - split class by concern",
                        })

        return smells

    def _detect_magic_numbers(self, lines: list[str], file_path: str) -> list[dict]:
        """Detect magic numbers in code."""
        smells: list[dict] = []
        # Pattern for standalone numbers (not 0, 1, -1 which are common)
        magic_pattern = re.compile(r'(?<![.\w])(\d{2,}|[2-9])(?![.\w])')

        # Skip certain contexts
        skip_patterns = [
            r'^\s*#',  # Comments
            r'^\s*"""',  # Docstrings
            r"^\s*'''",
            r'range\s*\(',  # range() calls
            r':\s*\d+',  # Type hints
            r'version\s*=',  # Version strings
            r'port\s*=',  # Port numbers (sometimes acceptable)
        ]

        for i, line in enumerate(lines):
            # Skip if line matches skip patterns
            if any(re.search(p, line, re.IGNORECASE) for p in skip_patterns):
                continue

            matches = magic_pattern.findall(line)
            for match in matches:
                try:
                    num = int(match)
                    # Skip small numbers that are commonly acceptable
                    if num in (0, 1, 2, 10, 100, 1000):
                        continue

                    smells.append({
                        "smell_type": SmellType.MAGIC_NUMBER.value,
                        "severity": "info",
                        "file_path": file_path,
                        "line_number": i + 1,
                        "end_line": i + 1,
                        "name": f"magic_{num}",
                        "message": f"Magic number `{num}` found",
                        "suggestion": f"Consider extracting to a named constant",
                        "code_snippet": line.strip()[:80],
                    })
                except ValueError:
                    pass

        return smells

    def _detect_deep_nesting(
        self,
        source: str,
        file_path: str,
        language: str,
        max_depth: int
    ) -> list[dict]:
        """Detect deep nesting in code."""
        smells: list[dict] = []

        if language == "python":
            try:
                tree = ast.parse(source)
            except SyntaxError:
                return smells

            def check_depth(node, depth=0, func_name=None):
                nested_types = (ast.If, ast.For, ast.While, ast.With, ast.Try)

                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_name = node.name
                    depth = 0

                if isinstance(node, nested_types) and depth > max_depth:
                    smells.append({
                        "smell_type": SmellType.DEEP_NESTING.value,
                        "severity": "warning",
                        "file_path": file_path,
                        "line_number": node.lineno,
                        "end_line": getattr(node, 'end_lineno', node.lineno),
                        "name": func_name or "module",
                        "message": f"Nesting depth {depth} exceeds maximum {max_depth}",
                        "suggestion": "Extract nested logic into separate functions or use early returns",
                    })

                for child in ast.iter_child_nodes(node):
                    if isinstance(node, nested_types):
                        check_depth(child, depth + 1, func_name)
                    else:
                        check_depth(child, depth, func_name)

            check_depth(tree)

        return smells


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: SecurityAuditTool
# ═══════════════════════════════════════════════════════════════════════════════


class SecurityAuditTool(Tool):
    """Static security analysis for vulnerabilities."""

    name = "security_audit"
    description = (
        "Static security analysis to detect hardcoded secrets, unsafe patterns, "
        "injection risks, and common security vulnerabilities."
    )
    parameters = {
        "type": "object",
        "properties": {
            "source_path": {
                "type": "string",
                "description": "Path to source file or directory"
            },
            "recursive": {
                "type": "boolean",
                "description": "Recursively scan directories (default: true)"
            },
            "checks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific checks to run (default: all)"
            },
            "exclude_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Patterns to exclude (e.g., test files)"
            },
            "output_format": {
                "type": "string",
                "enum": ["text", "json", "markdown", "sarif"],
                "description": "Output format (default: markdown)"
            },
            "severity_filter": {
                "type": "string",
                "enum": ["all", "low", "medium", "high", "critical"],
                "description": "Minimum severity to report (default: all)"
            }
        },
        "required": ["source_path"]
    }

    async def execute(
        self,
        source_path: str,
        recursive: bool = True,
        checks: Optional[list[str]] = None,
        exclude_patterns: Optional[list[str]] = None,
        output_format: str = "markdown",
        severity_filter: str = "all",
        **kwargs
    ) -> ToolResult:
        """Execute security audit."""
        try:
            path = self._resolve_path(source_path)

            if not path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path not found: {path}"
                )

            files = _find_source_files(path, recursive)
            if not files:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"No supported source files found in {path}"
                )

            # Apply exclude patterns
            if exclude_patterns:
                files = [
                    f for f in files
                    if not any(re.search(p, str(f)) for p in exclude_patterns)
                ]

            # Determine which checks to run
            all_checks = [c.value for c in SecurityCheckType]
            run_checks = checks if checks else all_checks

            all_findings: list[dict] = []
            severity_counts: Counter = Counter()

            for file_path in files:
                async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    source = await f.read()

                lines = source.splitlines()

                # Run security checks
                findings = self._run_security_checks(source, lines, str(file_path), run_checks)
                all_findings.extend(findings)

                for finding in findings:
                    severity_counts[finding["severity"]] += 1

            # Apply severity filter
            severity_order = ["info", "low", "medium", "high", "critical"]
            if severity_filter != "all":
                min_index = severity_order.index(severity_filter)
                all_findings = [
                    f for f in all_findings
                    if severity_order.index(f["severity"]) >= min_index
                ]

            result_data = {
                "files_scanned": len(files),
                "total_findings": len(all_findings),
                "severity_counts": dict(severity_counts),
                "findings": all_findings,
            }

            output = _format_output(result_data, output_format)

            log.info(
                "security_audit_complete",
                path=str(path),
                files=len(files),
                findings=len(all_findings),
            )

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "files_scanned": len(files),
                    "total_findings": len(all_findings),
                    "severity_counts": dict(severity_counts),
                }
            )

        except Exception as e:
            log.error("security_audit_failed", error=str(e), path=source_path)
            return ToolResult(
                success=False,
                output="",
                error=f"Security audit failed: {e}"
            )

    def _run_security_checks(
        self,
        source: str,
        lines: list[str],
        file_path: str,
        checks: list[str]
    ) -> list[dict]:
        """Run security checks on source code."""
        findings: list[dict] = []
        rule_counter = 1

        # Hardcoded secrets
        if SecurityCheckType.HARDCODED_SECRET.value in checks:
            for i, line in enumerate(lines):
                for pattern, secret_type, cwe in SECRET_PATTERNS:
                    if pattern.search(line):
                        # Check entropy for potential false positives
                        match = pattern.search(line)
                        if match:
                            value = match.group(0)
                            if _is_likely_secret(value) or len(value) > 30:
                                findings.append({
                                    "rule_id": f"SEC{rule_counter:03d}",
                                    "check_type": SecurityCheckType.HARDCODED_SECRET.value,
                                    "severity": "high",
                                    "confidence": "medium" if _is_likely_secret(value) else "low",
                                    "cwe_id": cwe,
                                    "title": f"Potential hardcoded {secret_type}",
                                    "description": f"Possible hardcoded {secret_type.lower()} detected",
                                    "file_path": file_path,
                                    "line_number": i + 1,
                                    "column": 1,
                                    "code_snippet": line.strip()[:100],
                                    "remediation": "Use environment variables or a secrets manager",
                                })
                                rule_counter += 1

        # SQL injection
        if SecurityCheckType.SQL_INJECTION.value in checks:
            for i, line in enumerate(lines):
                for pattern, desc in SQL_INJECTION_PATTERNS:
                    if pattern.search(line):
                        findings.append({
                            "rule_id": f"SEC{rule_counter:03d}",
                            "check_type": SecurityCheckType.SQL_INJECTION.value,
                            "severity": "critical",
                            "confidence": "high",
                            "cwe_id": "CWE-89",
                            "title": "Potential SQL injection",
                            "description": f"SQL injection risk: {desc}",
                            "file_path": file_path,
                            "line_number": i + 1,
                            "column": 1,
                            "code_snippet": line.strip()[:100],
                            "remediation": "Use parameterized queries instead of string formatting",
                        })
                        rule_counter += 1

        # Command injection
        if SecurityCheckType.COMMAND_INJECTION.value in checks:
            for i, line in enumerate(lines):
                for pattern, desc in COMMAND_INJECTION_PATTERNS:
                    if pattern.search(line):
                        findings.append({
                            "rule_id": f"SEC{rule_counter:03d}",
                            "check_type": SecurityCheckType.COMMAND_INJECTION.value,
                            "severity": "critical",
                            "confidence": "high",
                            "cwe_id": "CWE-78",
                            "title": "Potential command injection",
                            "description": f"Command injection risk: {desc}",
                            "file_path": file_path,
                            "line_number": i + 1,
                            "column": 1,
                            "code_snippet": line.strip()[:100],
                            "remediation": "Use subprocess with shell=False and list arguments",
                        })
                        rule_counter += 1

        # Insecure deserialization
        if SecurityCheckType.INSECURE_DESERIALIZATION.value in checks:
            for i, line in enumerate(lines):
                for pattern, desc in DESERIALIZATION_PATTERNS:
                    if pattern.search(line):
                        findings.append({
                            "rule_id": f"SEC{rule_counter:03d}",
                            "check_type": SecurityCheckType.INSECURE_DESERIALIZATION.value,
                            "severity": "high",
                            "confidence": "high",
                            "cwe_id": "CWE-502",
                            "title": "Insecure deserialization",
                            "description": f"Unsafe deserialization: {desc}",
                            "file_path": file_path,
                            "line_number": i + 1,
                            "column": 1,
                            "code_snippet": line.strip()[:100],
                            "remediation": "Use safe alternatives like json.loads() or yaml.safe_load()",
                        })
                        rule_counter += 1

        # Weak crypto
        if SecurityCheckType.WEAK_CRYPTO.value in checks:
            for i, line in enumerate(lines):
                for pattern, desc in WEAK_CRYPTO_PATTERNS:
                    if pattern.search(line):
                        findings.append({
                            "rule_id": f"SEC{rule_counter:03d}",
                            "check_type": SecurityCheckType.WEAK_CRYPTO.value,
                            "severity": "medium",
                            "confidence": "high",
                            "cwe_id": "CWE-327",
                            "title": "Weak cryptography",
                            "description": f"Weak cryptographic algorithm: {desc}",
                            "file_path": file_path,
                            "line_number": i + 1,
                            "column": 1,
                            "code_snippet": line.strip()[:100],
                            "remediation": "Use strong algorithms like SHA-256, AES-256",
                        })
                        rule_counter += 1

        # Debug code
        if SecurityCheckType.DEBUG_CODE.value in checks:
            for i, line in enumerate(lines):
                for pattern, desc in DEBUG_PATTERNS:
                    if pattern.search(line):
                        findings.append({
                            "rule_id": f"SEC{rule_counter:03d}",
                            "check_type": SecurityCheckType.DEBUG_CODE.value,
                            "severity": "low",
                            "confidence": "high",
                            "cwe_id": "CWE-489",
                            "title": "Debug code in production",
                            "description": f"Debug statement found: {desc}",
                            "file_path": file_path,
                            "line_number": i + 1,
                            "column": 1,
                            "code_snippet": line.strip()[:100],
                            "remediation": "Remove debug statements before deployment",
                        })
                        rule_counter += 1

        # Eval/exec usage
        if SecurityCheckType.EVAL_USAGE.value in checks:
            eval_pattern = re.compile(r'\b(eval|exec)\s*\(')
            for i, line in enumerate(lines):
                if eval_pattern.search(line):
                    # Skip if it's a literal string
                    if not re.search(r'(eval|exec)\s*\(\s*["\']', line):
                        findings.append({
                            "rule_id": f"SEC{rule_counter:03d}",
                            "check_type": SecurityCheckType.EVAL_USAGE.value,
                            "severity": "high",
                            "confidence": "medium",
                            "cwe_id": "CWE-95",
                            "title": "Dangerous eval/exec usage",
                            "description": "eval() or exec() with non-literal argument",
                            "file_path": file_path,
                            "line_number": i + 1,
                            "column": 1,
                            "code_snippet": line.strip()[:100],
                            "remediation": "Avoid eval/exec; use safe alternatives like ast.literal_eval()",
                        })
                        rule_counter += 1

        return findings


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: DetectDeadCodeTool
# ═══════════════════════════════════════════════════════════════════════════════


class DetectDeadCodeTool(Tool):
    """Detect unused code (imports, functions, variables, classes)."""

    name = "detect_dead_code"
    description = (
        "Find unused imports, functions, variables, classes, and unreachable code blocks."
    )
    parameters = {
        "type": "object",
        "properties": {
            "source_path": {
                "type": "string",
                "description": "Path to source file or directory"
            },
            "recursive": {
                "type": "boolean",
                "description": "Recursively analyze directories (default: false)"
            },
            "check_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Types to check: imports, functions, variables, classes, unreachable"
            },
            "ignore_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Name patterns to ignore (e.g., '_*' for private)"
            },
            "ignore_init": {
                "type": "boolean",
                "description": "Ignore __init__.py re-exports (default: true)"
            },
            "output_format": {
                "type": "string",
                "enum": ["text", "json", "markdown"],
                "description": "Output format (default: markdown)"
            }
        },
        "required": ["source_path"]
    }

    async def execute(
        self,
        source_path: str,
        recursive: bool = False,
        check_types: Optional[list[str]] = None,
        ignore_patterns: Optional[list[str]] = None,
        ignore_init: bool = True,
        output_format: str = "markdown",
        **kwargs
    ) -> ToolResult:
        """Execute dead code detection."""
        try:
            path = self._resolve_path(source_path)

            if not path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path not found: {path}"
                )

            files = _find_source_files(path, recursive)
            if not files:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"No supported source files found in {path}"
                )

            # Determine check types - map user-friendly names to enum values
            all_types = [t.value for t in DeadCodeType]
            if check_types:
                # Map shorthand names to full enum values
                type_mapping = {
                    "imports": "unused_import",
                    "functions": "unused_function",
                    "variables": "unused_variable",
                    "classes": "unused_class",
                    "unreachable": "unreachable_code",
                    "parameters": "unused_parameter",
                }
                checks = []
                for ct in check_types:
                    ct_lower = ct.lower()
                    if ct_lower in type_mapping:
                        checks.append(type_mapping[ct_lower])
                    elif ct_lower in all_types:
                        checks.append(ct_lower)
                    else:
                        # Try to find partial match
                        for t in all_types:
                            if ct_lower in t or t in ct_lower:
                                checks.append(t)
                                break
            else:
                checks = all_types

            # Patterns to ignore
            ignore = ignore_patterns or ["_*", "__*__"]

            all_dead_code: list[dict] = []

            for file_path in files:
                # Skip __init__.py if requested
                if ignore_init and file_path.name == "__init__.py":
                    continue

                async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    source = await f.read()

                lang = EXT_TO_LANG.get(file_path.suffix, "python")

                if lang == "python":
                    dead_items = self._detect_python_dead_code(
                        source, str(file_path), checks, ignore
                    )
                    all_dead_code.extend(dead_items)

            result_data = {
                "files_analyzed": len(files),
                "total_items": len(all_dead_code),
                "dead_code": all_dead_code,
            }

            output = _format_output(result_data, output_format)

            log.info(
                "dead_code_detected",
                path=str(path),
                files=len(files),
                items=len(all_dead_code),
            )

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "files_analyzed": len(files),
                    "total_items": len(all_dead_code),
                    "by_type": Counter(i["item_type"] for i in all_dead_code),
                }
            )

        except Exception as e:
            log.error("dead_code_detection_failed", error=str(e), path=source_path)
            return ToolResult(
                success=False,
                output="",
                error=f"Dead code detection failed: {e}"
            )

    def _detect_python_dead_code(
        self,
        source: str,
        file_path: str,
        checks: list[str],
        ignore: list[str]
    ) -> list[dict]:
        """Detect dead code in Python source."""
        dead_items: list[dict] = []

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return dead_items

        # Collect all defined names and their usage
        definitions: dict[str, tuple[int, str]] = {}  # name -> (line, type)
        usages: set[str] = set()

        # First pass: collect definitions
        for node in ast.walk(tree):
            name = None
            node_type = None
            line = getattr(node, 'lineno', 0)

            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    if DeadCodeType.UNUSED_IMPORT.value in checks:
                        definitions[name] = (line, "import")

            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    if name != "*" and DeadCodeType.UNUSED_IMPORT.value in checks:
                        definitions[name] = (line, "import")

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if DeadCodeType.UNUSED_FUNCTION.value in checks:
                    definitions[node.name] = (line, "function")

            elif isinstance(node, ast.ClassDef):
                if DeadCodeType.UNUSED_CLASS.value in checks:
                    definitions[node.name] = (line, "class")

            elif isinstance(node, ast.Assign):
                if DeadCodeType.UNUSED_VARIABLE.value in checks:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            definitions[target.id] = (line, "variable")

        # Second pass: collect usages
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                if isinstance(node.ctx, ast.Load):
                    usages.add(node.id)

            elif isinstance(node, ast.Attribute):
                # Track attribute access on names
                if isinstance(node.value, ast.Name):
                    usages.add(node.value.id)

            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    usages.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name):
                        usages.add(node.func.value.id)

        # Find unused definitions
        for name, (line, def_type) in definitions.items():
            # Check ignore patterns
            if any(
                (p.endswith('*') and name.startswith(p[:-1])) or
                (p.startswith('*') and name.endswith(p[1:])) or
                name == p
                for p in ignore
            ):
                continue

            # Skip special names
            if name in ("__all__", "__name__", "__doc__", "__file__"):
                continue

            if name not in usages:
                type_map = {
                    "import": DeadCodeType.UNUSED_IMPORT.value,
                    "function": DeadCodeType.UNUSED_FUNCTION.value,
                    "class": DeadCodeType.UNUSED_CLASS.value,
                    "variable": DeadCodeType.UNUSED_VARIABLE.value,
                }

                dead_items.append({
                    "item_type": type_map.get(def_type, "unknown"),
                    "name": name,
                    "file_path": file_path,
                    "line_number": line,
                    "confidence": "high" if def_type == "import" else "medium",
                    "reason": f"Defined but never used in this file",
                    "suggestion": f"Remove unused {def_type} `{name}`" if def_type != "variable" else f"Remove or use variable `{name}`",
                })

        # Detect unreachable code
        if DeadCodeType.UNREACHABLE_CODE.value in checks:
            unreachable = self._find_unreachable_code(tree, source, file_path)
            dead_items.extend(unreachable)

        return dead_items

    def _find_unreachable_code(
        self,
        tree: ast.AST,
        source: str,
        file_path: str
    ) -> list[dict]:
        """Find unreachable code after return/raise statements."""
        unreachable: list[dict] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check for code after return/raise in function body
                for i, stmt in enumerate(node.body[:-1]):
                    if isinstance(stmt, (ast.Return, ast.Raise)):
                        # Check if there's code after this that isn't a string (docstring)
                        remaining = node.body[i + 1:]
                        for next_stmt in remaining:
                            if not (isinstance(next_stmt, ast.Expr) and isinstance(next_stmt.value, ast.Constant)):
                                unreachable.append({
                                    "item_type": DeadCodeType.UNREACHABLE_CODE.value,
                                    "name": f"code_after_{stmt.__class__.__name__.lower()}",
                                    "file_path": file_path,
                                    "line_number": next_stmt.lineno,
                                    "confidence": "high",
                                    "reason": f"Code after {stmt.__class__.__name__.lower()} statement is unreachable",
                                    "suggestion": "Remove unreachable code or restructure logic",
                                })
                                break
                        break

        return unreachable


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: GenerateReviewReportTool
# ═══════════════════════════════════════════════════════════════════════════════


class GenerateReviewReportTool(Tool):
    """Generate comprehensive code review reports."""

    name = "generate_review_report"
    description = (
        "Generate comprehensive code review report combining quality metrics, "
        "code smells, security findings, and dead code analysis."
    )
    parameters = {
        "type": "object",
        "properties": {
            "source_path": {
                "type": "string",
                "description": "Path to source file or directory to review"
            },
            "recursive": {
                "type": "boolean",
                "description": "Recursively analyze directories (default: true)"
            },
            "include_sections": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Sections: summary, quality_metrics, code_smells, security, dead_code, recommendations"
            },
            "output_format": {
                "type": "string",
                "enum": ["markdown", "html", "json"],
                "description": "Output format (default: markdown)"
            },
            "output_file": {
                "type": "string",
                "description": "Path to write report (optional)"
            },
            "title": {
                "type": "string",
                "description": "Report title (default: 'Code Review Report')"
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview report without writing file (default: false)"
            }
        },
        "required": ["source_path"]
    }

    async def execute(
        self,
        source_path: str,
        recursive: bool = True,
        include_sections: Optional[list[str]] = None,
        output_format: str = "markdown",
        output_file: Optional[str] = None,
        title: str = "Code Review Report",
        dry_run: bool = False,
        **kwargs
    ) -> ToolResult:
        """Execute comprehensive code review."""
        try:
            path = self._resolve_path(source_path)

            if not path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path not found: {path}"
                )

            # Default sections
            sections = include_sections or [
                "summary", "quality_metrics", "code_smells", "security", "dead_code", "recommendations"
            ]

            # Run analyses using other tools
            quality_tool = AnalyzeCodeQualityTool(work_dir=self.work_dir)
            smells_tool = DetectCodeSmellsTool(work_dir=self.work_dir)
            security_tool = SecurityAuditTool(work_dir=self.work_dir)
            dead_code_tool = DetectDeadCodeTool(work_dir=self.work_dir)

            # Gather results
            quality_result = await quality_tool.execute(
                source_path=source_path,
                recursive=recursive,
                output_format="json",
                include_functions=True,
            )

            smells_result = await smells_tool.execute(
                source_path=source_path,
                recursive=recursive,
                output_format="json",
            )

            security_result = await security_tool.execute(
                source_path=source_path,
                recursive=recursive,
                output_format="json",
            )

            dead_code_result = await dead_code_tool.execute(
                source_path=source_path,
                recursive=recursive,
                output_format="json",
            )

            # Parse results
            quality_data = json.loads(quality_result.output) if quality_result.success else {}
            smells_data = json.loads(smells_result.output) if smells_result.success else {}
            security_data = json.loads(security_result.output) if security_result.success else {}
            dead_code_data = json.loads(dead_code_result.output) if dead_code_result.success else {}

            # Calculate grade
            metrics = quality_data.get("metrics", {})
            quality_metrics = QualityMetrics(
                total_lines=metrics.get("total_lines", 0),
                source_lines=metrics.get("source_lines", 0),
                comment_lines=metrics.get("comment_lines", 0),
                blank_lines=metrics.get("blank_lines", 0),
                cyclomatic_complexity=metrics.get("cyclomatic_complexity", 1),
                cognitive_complexity=metrics.get("cognitive_complexity", 0),
                maintainability_index=metrics.get("maintainability_index", 100),
            )

            smell_count = len(smells_data.get("smells", []))
            security_count = len(security_data.get("findings", []))
            grade = _calculate_grade(quality_metrics, smell_count, security_count)

            # Build report
            report = self._build_report(
                title=title,
                source_path=str(path),
                sections=sections,
                quality_data=quality_data,
                smells_data=smells_data,
                security_data=security_data,
                dead_code_data=dead_code_data,
                grade=grade,
                output_format=output_format,
            )

            # Write to file if requested
            if output_file and not dry_run:
                out_path = self._resolve_path(output_file)
                async with aiofiles.open(out_path, "w", encoding="utf-8") as f:
                    await f.write(report)
                log.info("report_written", path=str(out_path))

            total_issues = smell_count + security_count + len(dead_code_data.get("dead_code", []))

            log.info(
                "review_report_generated",
                path=str(path),
                grade=grade,
                issues=total_issues,
            )

            return ToolResult(
                success=True,
                output=report,
                metadata={
                    "grade": grade,
                    "files_analyzed": quality_data.get("files_analyzed", 0),
                    "total_issues": total_issues,
                    "code_smells": smell_count,
                    "security_findings": security_count,
                    "dead_code_items": len(dead_code_data.get("dead_code", [])),
                    "output_file": str(output_file) if output_file and not dry_run else None,
                }
            )

        except Exception as e:
            log.error("review_report_failed", error=str(e), path=source_path)
            return ToolResult(
                success=False,
                output="",
                error=f"Review report generation failed: {e}"
            )

    def _build_report(
        self,
        title: str,
        source_path: str,
        sections: list[str],
        quality_data: dict,
        smells_data: dict,
        security_data: dict,
        dead_code_data: dict,
        grade: str,
        output_format: str,
    ) -> str:
        """Build the complete report."""
        if output_format == "json":
            return json.dumps({
                "title": title,
                "generated_at": datetime.now().isoformat(),
                "source_path": source_path,
                "grade": grade,
                "quality": quality_data,
                "smells": smells_data,
                "security": security_data,
                "dead_code": dead_code_data,
            }, indent=2, default=str)

        # Markdown/HTML format
        lines: list[str] = []
        lines.append(f"# {title}\n")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Source:** `{source_path}`\n")

        # Summary section
        if "summary" in sections:
            grade_emoji = {"A": "🟢", "B": "🔵", "C": "🟡", "D": "🟠", "F": "🔴"}.get(grade, "⚪")
            lines.append(f"## Executive Summary\n")
            lines.append(f"**Overall Grade:** {grade_emoji} **{grade}**\n")

            metrics = quality_data.get("metrics", {})
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| Files Analyzed | {quality_data.get('files_analyzed', 0)} |")
            lines.append(f"| Total Lines | {metrics.get('total_lines', 0)} |")
            lines.append(f"| Maintainability Index | {metrics.get('maintainability_index', 100):.1f}/100 |")
            lines.append(f"| Code Smells | {len(smells_data.get('smells', []))} |")
            lines.append(f"| Security Issues | {len(security_data.get('findings', []))} |")
            lines.append(f"| Dead Code Items | {len(dead_code_data.get('dead_code', []))} |")
            lines.append("")

        # Quality metrics section
        if "quality_metrics" in sections:
            lines.append("## Quality Metrics\n")
            metrics = quality_data.get("metrics", {})
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| Source Lines (SLOC) | {metrics.get('source_lines', 0)} |")
            lines.append(f"| Comment Lines | {metrics.get('comment_lines', 0)} |")
            lines.append(f"| Comment Ratio | {metrics.get('comment_ratio', 0):.1%} |")
            lines.append(f"| Cyclomatic Complexity | {metrics.get('cyclomatic_complexity', 1)} |")
            lines.append(f"| Cognitive Complexity | {metrics.get('cognitive_complexity', 0)} |")
            lines.append(f"| Halstead Effort | {metrics.get('halstead_effort', 0):.0f} |")
            lines.append("")

            # Top complex functions
            functions = quality_data.get("functions", [])
            if functions:
                complex_funcs = sorted(functions, key=lambda x: x.get("cyclomatic_complexity", 0), reverse=True)[:5]
                if complex_funcs:
                    lines.append("### Most Complex Functions\n")
                    lines.append("| Function | Complexity | Lines |")
                    lines.append("|----------|------------|-------|")
                    for func in complex_funcs:
                        lines.append(f"| `{func['name']}` | {func['cyclomatic_complexity']} | {func['line_count']} |")
                    lines.append("")

        # Code smells section
        if "code_smells" in sections:
            smells = smells_data.get("smells", [])
            lines.append(f"## Code Smells ({len(smells)})\n")

            if smells:
                # Group by type
                by_type: dict[str, list] = {}
                for smell in smells:
                    by_type.setdefault(smell.get("smell_type", "unknown"), []).append(smell)

                for smell_type, items in by_type.items():
                    severity_icon = "⚠️" if items[0].get("severity") == "warning" else "ℹ️"
                    lines.append(f"### {severity_icon} {smell_type.replace('_', ' ').title()} ({len(items)})\n")
                    for item in items[:5]:  # Limit to 5 per type
                        lines.append(f"- **{item.get('name', 'N/A')}** at `{item.get('file_path', '')}:{item.get('line_number', 0)}`")
                        lines.append(f"  - {item.get('message', '')}")
                    if len(items) > 5:
                        lines.append(f"  - ... and {len(items) - 5} more")
                    lines.append("")
            else:
                lines.append("No code smells detected.\n")

        # Security section
        if "security" in sections:
            findings = security_data.get("findings", [])
            lines.append(f"## Security Findings ({len(findings)})\n")

            if findings:
                # Group by severity
                by_severity: dict[str, list] = {}
                for finding in findings:
                    by_severity.setdefault(finding.get("severity", "info"), []).append(finding)

                for severity in ["critical", "high", "medium", "low", "info"]:
                    if severity in by_severity:
                        icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "ℹ️"}[severity]
                        items = by_severity[severity]
                        lines.append(f"### {icon} {severity.upper()} ({len(items)})\n")
                        for item in items[:5]:
                            lines.append(f"- **{item.get('rule_id', '')}**: {item.get('title', '')}")
                            lines.append(f"  - File: `{item.get('file_path', '')}:{item.get('line_number', 0)}`")
                            lines.append(f"  - CWE: {item.get('cwe_id', 'N/A')}")
                        if len(items) > 5:
                            lines.append(f"  - ... and {len(items) - 5} more")
                        lines.append("")
            else:
                lines.append("No security issues detected.\n")

        # Dead code section
        if "dead_code" in sections:
            dead_items = dead_code_data.get("dead_code", [])
            lines.append(f"## Dead Code ({len(dead_items)})\n")

            if dead_items:
                # Group by type
                by_type: dict[str, list] = {}
                for item in dead_items:
                    by_type.setdefault(item.get("item_type", "unknown"), []).append(item)

                for item_type, items in by_type.items():
                    lines.append(f"### {item_type.replace('_', ' ').title()} ({len(items)})\n")
                    for item in items[:10]:
                        lines.append(f"- `{item.get('name', '')}` at `{item.get('file_path', '')}:{item.get('line_number', 0)}`")
                    if len(items) > 10:
                        lines.append(f"- ... and {len(items) - 10} more")
                    lines.append("")
            else:
                lines.append("No dead code detected.\n")

        # Recommendations section
        if "recommendations" in sections:
            lines.append("## Recommendations\n")
            recommendations = []

            # Generate recommendations based on findings
            metrics = quality_data.get("metrics", {})

            if metrics.get("maintainability_index", 100) < 40:
                recommendations.append("🔧 **Improve maintainability**: Refactor complex functions, add documentation")

            if metrics.get("cyclomatic_complexity", 0) > 30:
                recommendations.append("🔧 **Reduce complexity**: Break down large functions into smaller units")

            if len(security_data.get("findings", [])) > 0:
                critical = sum(1 for f in security_data.get("findings", []) if f.get("severity") in ("critical", "high"))
                if critical > 0:
                    recommendations.append(f"🔴 **Fix {critical} critical/high security issues immediately**")

            if len(smells_data.get("smells", [])) > 10:
                recommendations.append("⚠️ **Address code smells**: Focus on long methods and large classes first")

            if len(dead_code_data.get("dead_code", [])) > 5:
                recommendations.append("🗑️ **Remove dead code**: Clean up unused imports and functions")

            if metrics.get("comment_ratio", 0) < 0.1:
                recommendations.append("📝 **Add documentation**: Comment ratio is below 10%")

            if not recommendations:
                recommendations.append("✅ Code is in good shape! Continue following best practices.")

            for rec in recommendations:
                lines.append(f"- {rec}")
            lines.append("")

        report = '\n'.join(lines)

        if output_format == "html":
            # Basic HTML wrapper
            report = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background: #f5f5f5; }}
        code {{ background: #f5f5f5; padding: 2px 5px; border-radius: 3px; }}
        pre {{ background: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto; }}
        h1, h2, h3 {{ color: #333; }}
    </style>
</head>
<body>
{report}
</body>
</html>"""

        return report
