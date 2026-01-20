"""AI-powered code improvement tools for Sindri.

Phase 13 Tier 4: Provides tools for refactoring suggestions, performance optimization,
antipattern detection, design pattern recommendations, and type hint generation.

Tools:
- SuggestRefactoringTool: Analyze code for refactoring opportunities
- OptimizePerformanceTool: Identify performance bottlenecks and suggest optimizations
- DetectAntipatternsTool: Find coding antipatterns in source code
- SuggestDesignPatternsTool: Recommend applicable design patterns
- GenerateTypeHintsTool: Generate or improve type annotations for Python code
"""

import ast
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import aiofiles
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()

# ═══════════════════════════════════════════════════════════════════════════════
# Language Configuration
# ═══════════════════════════════════════════════════════════════════════════════

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


class RefactoringType(str, Enum):
    """Types of refactoring suggestions."""
    EXTRACT_METHOD = "extract_method"
    EXTRACT_VARIABLE = "extract_variable"
    INLINE_VARIABLE = "inline_variable"
    SIMPLIFY_CONDITIONAL = "simplify_conditional"
    REMOVE_DUPLICATION = "remove_duplication"
    INTRODUCE_PARAMETER_OBJECT = "introduce_parameter_object"
    REPLACE_MAGIC_NUMBER = "replace_magic_number"
    RENAME_FOR_CLARITY = "rename_for_clarity"


class PerformanceIssueType(str, Enum):
    """Types of performance issues."""
    ALGORITHM_COMPLEXITY = "algorithm_complexity"
    UNNECESSARY_COMPUTATION = "unnecessary_computation"
    MISSING_CACHE = "missing_cache"
    INEFFICIENT_DATA_STRUCTURE = "inefficient_data_structure"
    BLOCKING_IO = "blocking_io"
    N_PLUS_ONE = "n_plus_one"
    STRING_CONCATENATION = "string_concatenation"
    REPEATED_ATTRIBUTE_ACCESS = "repeated_attribute_access"


class AntipatternType(str, Enum):
    """Types of code antipatterns."""
    GOD_OBJECT = "god_object"
    FEATURE_ENVY = "feature_envy"
    PRIMITIVE_OBSESSION = "primitive_obsession"
    CALLBACK_HELL = "callback_hell"
    LONG_METHOD = "long_method"
    LONG_PARAMETER_LIST = "long_parameter_list"
    DATA_CLUMP = "data_clump"
    SPECULATIVE_GENERALITY = "speculative_generality"


class DesignPatternType(str, Enum):
    """Types of design patterns."""
    FACTORY = "factory"
    STRATEGY = "strategy"
    OBSERVER = "observer"
    DECORATOR = "decorator"
    SINGLETON = "singleton"
    BUILDER = "builder"
    ADAPTER = "adapter"
    COMMAND = "command"
    TEMPLATE_METHOD = "template_method"
    STATE = "state"


class Confidence(str, Enum):
    """Confidence levels for suggestions."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Severity(str, Enum):
    """Severity levels for issues."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class RefactoringSuggestion:
    """A refactoring suggestion with before/after examples."""
    refactoring_type: str
    target: str  # function/class/variable name
    file_path: str
    line_number: int
    end_line: int
    description: str
    rationale: str
    before_snippet: str
    after_snippet: str
    confidence: str = "medium"
    impact: str = "medium"


@dataclass
class PerformanceIssue:
    """A detected performance issue."""
    issue_type: str
    location: str  # function/method name
    file_path: str
    line_number: int
    description: str
    current_complexity: Optional[str] = None
    suggested_complexity: Optional[str] = None
    suggestion: str = ""
    code_snippet: str = ""
    severity: str = "warning"


@dataclass
class Antipattern:
    """A detected code antipattern."""
    pattern_type: str
    name: str  # affected element name
    file_path: str
    line_number: int
    description: str
    severity: str
    suggestion: str
    code_snippet: str = ""
    metrics: dict = field(default_factory=dict)


@dataclass
class PatternRecommendation:
    """A design pattern recommendation."""
    pattern: str
    applicability: str  # high/medium/low
    context: str  # where it would apply
    file_path: str
    line_number: int
    description: str
    problem_indicators: list[str] = field(default_factory=list)
    example_before: str = ""
    example_after: str = ""
    benefits: list[str] = field(default_factory=list)


@dataclass
class TypeHintSuggestion:
    """A type hint suggestion for a function or variable."""
    target: str  # function or variable name
    target_type: str  # "function", "variable", "parameter"
    file_path: str
    line_number: int
    original_signature: str
    suggested_signature: str
    inferred_types: dict[str, str] = field(default_factory=dict)
    confidence: str = "medium"
    reasoning: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════


def _get_source_files(path: Path, recursive: bool = False) -> list[Path]:
    """Get source files from path."""
    supported = {".py", ".js", ".jsx", ".ts", ".tsx"}

    if path.is_file():
        if path.suffix in supported:
            return [path]
        return []

    files = []
    if recursive:
        for p in path.rglob("*"):
            if p.is_file() and p.suffix in supported:
                if not any(skip in p.parts for skip in SKIP_DIRS):
                    files.append(p)
    else:
        for p in path.iterdir():
            if p.is_file() and p.suffix in supported:
                files.append(p)

    return sorted(files)


def _get_code_snippet(source: str, line_start: int, line_end: int, context: int = 2) -> str:
    """Extract a code snippet with context lines."""
    lines = source.splitlines()
    start = max(0, line_start - 1 - context)
    end = min(len(lines), line_end + context)
    snippet_lines = lines[start:end]
    return "\n".join(snippet_lines)


def _calculate_nesting_depth(node: ast.AST) -> int:
    """Calculate maximum nesting depth of a node."""
    max_depth = 0

    def walk(n: ast.AST, depth: int) -> None:
        nonlocal max_depth
        if isinstance(n, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)):
            depth += 1
            max_depth = max(max_depth, depth)
        for child in ast.iter_child_nodes(n):
            walk(child, depth)

    walk(node, 0)
    return max_depth


def _count_lines(node: ast.AST) -> int:
    """Count lines of a node."""
    if hasattr(node, "end_lineno") and hasattr(node, "lineno"):
        return node.end_lineno - node.lineno + 1
    return 0


def _hash_code_block(code: str) -> str:
    """Create a normalized hash of a code block for duplication detection."""
    # Normalize whitespace and variable names for similarity detection
    normalized = re.sub(r'\s+', ' ', code.strip())
    normalized = re.sub(r'\b[a-z_][a-z0-9_]*\b', 'VAR', normalized, flags=re.IGNORECASE)
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


def _format_output(
    data: dict[str, Any],
    output_format: str,
    title: str = "Analysis Results"
) -> str:
    """Format output in the specified format."""
    if output_format == "json":
        return json.dumps(data, indent=2, default=str)

    if output_format == "text":
        lines = [f"=== {title} ===", ""]
        for key, value in data.items():
            if isinstance(value, list):
                lines.append(f"{key}: {len(value)} items")
                for item in value[:10]:  # Limit display
                    if isinstance(item, dict):
                        lines.append(f"  - {item.get('description', item)}")
                    else:
                        lines.append(f"  - {item}")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)

    # Default: markdown
    lines = [f"# {title}", ""]
    for key, value in data.items():
        if isinstance(value, list) and value:
            lines.append(f"## {key.replace('_', ' ').title()}")
            lines.append("")
            for item in value:
                if isinstance(item, dict):
                    lines.append(f"### {item.get('target', item.get('name', 'Item'))}")
                    for k, v in item.items():
                        if k not in ("target", "name") and v:
                            if k in ("before_snippet", "after_snippet", "code_snippet", "example_before", "example_after"):
                                lines.append(f"**{k.replace('_', ' ').title()}:**")
                                lines.append("```python")
                                lines.append(str(v))
                                lines.append("```")
                            elif isinstance(v, list):
                                lines.append(f"**{k.replace('_', ' ').title()}:** {', '.join(str(x) for x in v)}")
                            else:
                                lines.append(f"**{k.replace('_', ' ').title()}:** {v}")
                    lines.append("")
        elif not isinstance(value, list):
            lines.append(f"**{key.replace('_', ' ').title()}:** {value}")
            lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Analysis Functions
# ═══════════════════════════════════════════════════════════════════════════════


def _analyze_function_for_refactoring(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    source: str,
    file_path: str,
    thresholds: dict
) -> list[RefactoringSuggestion]:
    """Analyze a function for refactoring opportunities."""
    suggestions: list[RefactoringSuggestion] = []
    func_name = func_node.name
    line_count = _count_lines(func_node)
    nesting = _calculate_nesting_depth(func_node)
    param_count = len(func_node.args.args)

    # Check for long method
    if line_count > thresholds.get("method_lines", 50):
        snippet = _get_code_snippet(source, func_node.lineno, func_node.end_lineno or func_node.lineno, context=0)
        suggestions.append(RefactoringSuggestion(
            refactoring_type=RefactoringType.EXTRACT_METHOD.value,
            target=func_name,
            file_path=file_path,
            line_number=func_node.lineno,
            end_line=func_node.end_lineno or func_node.lineno,
            description=f"Function '{func_name}' is {line_count} lines (threshold: {thresholds.get('method_lines', 50)})",
            rationale="Long methods are harder to understand and maintain. Consider extracting logical sections into separate functions.",
            before_snippet=snippet[:500] + "..." if len(snippet) > 500 else snippet,
            after_snippet=f"# Extract logical sections into:\n# def {func_name}_process_data(...):\n# def {func_name}_validate(...):\n# def {func_name}_format_output(...):",
            confidence="high",
            impact="high"
        ))

    # Check for deep nesting
    if nesting > thresholds.get("nesting_depth", 4):
        snippet = _get_code_snippet(source, func_node.lineno, func_node.end_lineno or func_node.lineno, context=0)
        suggestions.append(RefactoringSuggestion(
            refactoring_type=RefactoringType.SIMPLIFY_CONDITIONAL.value,
            target=func_name,
            file_path=file_path,
            line_number=func_node.lineno,
            end_line=func_node.end_lineno or func_node.lineno,
            description=f"Function '{func_name}' has nesting depth {nesting} (threshold: {thresholds.get('nesting_depth', 4)})",
            rationale="Deep nesting makes code hard to follow. Use early returns, guard clauses, or extract nested logic.",
            before_snippet=snippet[:400] + "..." if len(snippet) > 400 else snippet,
            after_snippet="# Use early returns:\nif not condition:\n    return\n# Main logic here without nesting",
            confidence="high",
            impact="medium"
        ))

    # Check for many parameters
    if param_count > thresholds.get("parameters", 5):
        params = [arg.arg for arg in func_node.args.args]
        suggestions.append(RefactoringSuggestion(
            refactoring_type=RefactoringType.INTRODUCE_PARAMETER_OBJECT.value,
            target=func_name,
            file_path=file_path,
            line_number=func_node.lineno,
            end_line=func_node.lineno,
            description=f"Function '{func_name}' has {param_count} parameters (threshold: {thresholds.get('parameters', 5)})",
            rationale="Many parameters make function calls hard to read. Group related parameters into a dataclass or TypedDict.",
            before_snippet=f"def {func_name}({', '.join(params)}): ...",
            after_snippet=f"@dataclass\nclass {func_name.title()}Params:\n    {chr(10).join(f'    {p}: ...' for p in params[:5])}\n\ndef {func_name}(params: {func_name.title()}Params): ...",
            confidence="medium",
            impact="medium"
        ))

    # Check for magic numbers
    magic_numbers: list[tuple[int, Any]] = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            # Exclude common values like 0, 1, 2, -1
            if node.value not in (0, 1, 2, -1, 0.0, 1.0, 100, 1000):
                if hasattr(node, "lineno"):
                    magic_numbers.append((node.lineno, node.value))

    if magic_numbers:
        for lineno, value in magic_numbers[:3]:  # Limit to first 3
            suggestions.append(RefactoringSuggestion(
                refactoring_type=RefactoringType.REPLACE_MAGIC_NUMBER.value,
                target=func_name,
                file_path=file_path,
                line_number=lineno,
                end_line=lineno,
                description=f"Magic number {value} in function '{func_name}'",
                rationale="Magic numbers reduce code readability. Use named constants instead.",
                before_snippet=f"... {value} ...",
                after_snippet=f"MEANINGFUL_NAME = {value}\n... MEANINGFUL_NAME ...",
                confidence="medium",
                impact="low"
            ))

    return suggestions


def _analyze_class_for_antipatterns(
    class_node: ast.ClassDef,
    source: str,
    file_path: str,
    thresholds: dict
) -> list[Antipattern]:
    """Analyze a class for antipatterns."""
    antipatterns: list[Antipattern] = []
    class_name = class_node.name

    # Count methods and attributes
    methods = [n for n in class_node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    attributes: set[str] = set()

    for node in ast.walk(class_node):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                    if target.value.id == "self":
                        attributes.add(target.attr)

    method_count = len(methods)
    attr_count = len(attributes)
    line_count = _count_lines(class_node)

    # God Object detection
    if method_count > thresholds.get("class_methods", 20) or attr_count > thresholds.get("class_attributes", 15):
        antipatterns.append(Antipattern(
            pattern_type=AntipatternType.GOD_OBJECT.value,
            name=class_name,
            file_path=file_path,
            line_number=class_node.lineno,
            description=f"Class '{class_name}' may be a God Object ({method_count} methods, {attr_count} attributes)",
            severity="error",
            suggestion="Split into smaller, focused classes with single responsibilities",
            metrics={"methods": method_count, "attributes": attr_count, "lines": line_count}
        ))

    # Check individual methods for long method antipattern
    for method in methods:
        method_lines = _count_lines(method)
        if method_lines > thresholds.get("method_lines", 50):
            antipatterns.append(Antipattern(
                pattern_type=AntipatternType.LONG_METHOD.value,
                name=f"{class_name}.{method.name}",
                file_path=file_path,
                line_number=method.lineno,
                description=f"Method '{method.name}' is {method_lines} lines long",
                severity="warning",
                suggestion="Extract logical sections into private helper methods",
                metrics={"lines": method_lines}
            ))

        # Long parameter list
        param_count = len(method.args.args)
        if param_count > thresholds.get("parameters", 5) + 1:  # +1 for self
            antipatterns.append(Antipattern(
                pattern_type=AntipatternType.LONG_PARAMETER_LIST.value,
                name=f"{class_name}.{method.name}",
                file_path=file_path,
                line_number=method.lineno,
                description=f"Method '{method.name}' has {param_count - 1} parameters (excluding self)",
                severity="warning",
                suggestion="Use a parameter object or builder pattern",
                metrics={"parameters": param_count - 1}
            ))

    return antipatterns


def _analyze_for_performance(
    node: ast.AST,
    source: str,
    file_path: str,
    func_name: str
) -> list[PerformanceIssue]:
    """Analyze code for performance issues."""
    issues: list[PerformanceIssue] = []

    # Track loop nesting for complexity
    loop_depth = 0
    max_loop_depth = 0

    class PerformanceVisitor(ast.NodeVisitor):
        def __init__(self):
            self.loop_depth = 0
            self.max_loop_depth = 0
            self.in_loop = False
            self.loop_calls: list[tuple[int, str]] = []

        def visit_For(self, node: ast.For) -> None:
            self.loop_depth += 1
            self.max_loop_depth = max(self.max_loop_depth, self.loop_depth)
            old_in_loop = self.in_loop
            self.in_loop = True
            self.generic_visit(node)
            self.in_loop = old_in_loop
            self.loop_depth -= 1

        def visit_While(self, node: ast.While) -> None:
            self.loop_depth += 1
            self.max_loop_depth = max(self.max_loop_depth, self.loop_depth)
            old_in_loop = self.in_loop
            self.in_loop = True
            self.generic_visit(node)
            self.in_loop = old_in_loop
            self.loop_depth -= 1

        def visit_Call(self, node: ast.Call) -> None:
            if self.in_loop:
                # Check for potentially expensive calls in loops
                call_name = ""
                if isinstance(node.func, ast.Name):
                    call_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    call_name = node.func.attr

                expensive_calls = {"open", "read", "write", "query", "execute", "fetch", "request", "get", "post"}
                if call_name.lower() in expensive_calls:
                    self.loop_calls.append((node.lineno, call_name))

            self.generic_visit(node)

        def visit_BinOp(self, node: ast.BinOp) -> None:
            # Detect string concatenation in loops
            if self.in_loop and isinstance(node.op, ast.Add):
                if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                    issues.append(PerformanceIssue(
                        issue_type=PerformanceIssueType.STRING_CONCATENATION.value,
                        location=func_name,
                        file_path=file_path,
                        line_number=node.lineno,
                        description="String concatenation in loop",
                        suggestion="Use ''.join() or f-strings with list comprehension",
                        severity="warning"
                    ))
            self.generic_visit(node)

    visitor = PerformanceVisitor()
    visitor.visit(node)

    # Report nested loop complexity
    if visitor.max_loop_depth >= 2:
        complexity = "O(n)" if visitor.max_loop_depth == 1 else f"O(n^{visitor.max_loop_depth})"
        issues.append(PerformanceIssue(
            issue_type=PerformanceIssueType.ALGORITHM_COMPLEXITY.value,
            location=func_name,
            file_path=file_path,
            line_number=node.lineno if hasattr(node, "lineno") else 1,
            description=f"Nested loops detected (depth: {visitor.max_loop_depth})",
            current_complexity=complexity,
            suggested_complexity="O(n) or O(n log n)",
            suggestion="Consider using dict/set for lookups, or restructure algorithm",
            severity="warning" if visitor.max_loop_depth == 2 else "error"
        ))

    # Report expensive calls in loops
    for lineno, call_name in visitor.loop_calls:
        issues.append(PerformanceIssue(
            issue_type=PerformanceIssueType.N_PLUS_ONE.value,
            location=func_name,
            file_path=file_path,
            line_number=lineno,
            description=f"Potentially expensive call '{call_name}' inside loop",
            suggestion="Move call outside loop, batch operations, or use caching",
            severity="warning"
        ))

    return issues


def _suggest_design_patterns(
    tree: ast.AST,
    source: str,
    file_path: str
) -> list[PatternRecommendation]:
    """Analyze code and suggest applicable design patterns."""
    recommendations: list[PatternRecommendation] = []

    for node in ast.walk(tree):
        # Factory Pattern - multiple conditional object creation
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if_count = sum(1 for n in ast.walk(node) if isinstance(n, ast.If))
            return_count = sum(1 for n in ast.walk(node) if isinstance(n, ast.Return))

            # Function with multiple conditionals returning different objects
            if if_count >= 3 and return_count >= 3:
                if "create" in node.name.lower() or "get" in node.name.lower() or "make" in node.name.lower():
                    recommendations.append(PatternRecommendation(
                        pattern=DesignPatternType.FACTORY.value,
                        applicability="high",
                        context=node.name,
                        file_path=file_path,
                        line_number=node.lineno,
                        description=f"Function '{node.name}' has multiple conditional returns - consider Factory pattern",
                        problem_indicators=["Multiple if/elif creating different objects", "Type-based object creation"],
                        example_before="if type == 'a': return A()\nelif type == 'b': return B()",
                        example_after="factories = {'a': A, 'b': B}\nreturn factories[type]()",
                        benefits=["Easier to extend", "Single Responsibility", "Open/Closed Principle"]
                    ))

        # Strategy Pattern - type-based algorithm selection
        if isinstance(node, ast.ClassDef):
            methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

            for method in methods:
                # Check for isinstance checks suggesting polymorphism need
                isinstance_checks = [n for n in ast.walk(method)
                                    if isinstance(n, ast.Call)
                                    and isinstance(n.func, ast.Name)
                                    and n.func.id == "isinstance"]

                if len(isinstance_checks) >= 2:
                    recommendations.append(PatternRecommendation(
                        pattern=DesignPatternType.STRATEGY.value,
                        applicability="medium",
                        context=f"{node.name}.{method.name}",
                        file_path=file_path,
                        line_number=method.lineno,
                        description=f"Method '{method.name}' uses multiple isinstance checks - consider Strategy pattern",
                        problem_indicators=["Multiple isinstance() checks", "Type-based branching"],
                        example_before="if isinstance(obj, TypeA): ...\nelif isinstance(obj, TypeB): ...",
                        example_after="class Strategy(Protocol):\n    def execute(self): ...\n\nobj.strategy.execute()",
                        benefits=["Polymorphism over conditionals", "Easy to add new strategies", "Testable"]
                    ))

        # Builder Pattern - complex constructors
        if isinstance(node, ast.ClassDef):
            init_method = next((n for n in node.body
                               if isinstance(n, ast.FunctionDef) and n.name == "__init__"), None)

            if init_method:
                param_count = len(init_method.args.args) - 1  # Exclude self
                if param_count >= 6:
                    recommendations.append(PatternRecommendation(
                        pattern=DesignPatternType.BUILDER.value,
                        applicability="medium",
                        context=node.name,
                        file_path=file_path,
                        line_number=init_method.lineno,
                        description=f"Class '{node.name}' has {param_count} constructor parameters - consider Builder pattern",
                        problem_indicators=["Many constructor parameters", "Optional parameters with defaults"],
                        example_before=f"obj = {node.name}(a, b, c, d, e, f, ...)",
                        example_after=f"obj = {node.name}Builder().with_a(a).with_b(b).build()",
                        benefits=["Readable object construction", "Optional parameters", "Immutable objects"]
                    ))

        # Observer Pattern - callback registration
        if isinstance(node, ast.ClassDef):
            method_names = {n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

            observer_indicators = {"subscribe", "unsubscribe", "notify", "add_listener", "remove_listener",
                                   "on_change", "register", "emit", "trigger"}
            matches = method_names & observer_indicators

            if len(matches) >= 2:
                recommendations.append(PatternRecommendation(
                    pattern=DesignPatternType.OBSERVER.value,
                    applicability="high",
                    context=node.name,
                    file_path=file_path,
                    line_number=node.lineno,
                    description=f"Class '{node.name}' has observer-like methods ({', '.join(matches)}) - formalize with Observer pattern",
                    problem_indicators=["Manual listener management", "Callback lists"],
                    benefits=["Decoupled notification", "Multiple observers", "Event-driven architecture"]
                ))

    return recommendations


def _infer_type_hints(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    source: str,
    file_path: str
) -> list[TypeHintSuggestion]:
    """Infer type hints for a function."""
    suggestions: list[TypeHintSuggestion] = []

    # Get current signature
    params = func_node.args.args
    inferred_types: dict[str, str] = {}

    for param in params:
        if param.arg == "self" or param.arg == "cls":
            continue

        # Check if already has annotation
        if param.annotation:
            continue

        # Try to infer from default value
        default_idx = len(params) - len(func_node.args.defaults) + params.index(param) - (1 if params[0].arg in ("self", "cls") else 0)
        if 0 <= default_idx < len(func_node.args.defaults):
            default = func_node.args.defaults[default_idx]
            if isinstance(default, ast.Constant):
                if isinstance(default.value, str):
                    inferred_types[param.arg] = "str"
                elif isinstance(default.value, int):
                    inferred_types[param.arg] = "int"
                elif isinstance(default.value, float):
                    inferred_types[param.arg] = "float"
                elif isinstance(default.value, bool):
                    inferred_types[param.arg] = "bool"
                elif default.value is None:
                    inferred_types[param.arg] = "Optional[Any]"
            elif isinstance(default, ast.List):
                inferred_types[param.arg] = "list"
            elif isinstance(default, ast.Dict):
                inferred_types[param.arg] = "dict"
            elif isinstance(default, ast.Set):
                inferred_types[param.arg] = "set"

        # Try to infer from usage in function body
        if param.arg not in inferred_types:
            for node in ast.walk(func_node):
                if isinstance(node, ast.Call):
                    # Check if parameter is used in a typed context
                    if isinstance(node.func, ast.Attribute):
                        for arg in node.args:
                            if isinstance(arg, ast.Name) and arg.id == param.arg:
                                # Common method patterns
                                method = node.func.attr
                                if method in ("append", "extend", "insert"):
                                    inferred_types[param.arg] = "list"
                                elif method in ("add", "remove", "discard"):
                                    inferred_types[param.arg] = "set"
                                elif method in ("get", "keys", "values", "items", "update"):
                                    inferred_types[param.arg] = "dict"
                                elif method in ("read", "write", "readline"):
                                    inferred_types[param.arg] = "IO"
                                elif method in ("encode", "decode", "split", "join", "strip"):
                                    inferred_types[param.arg] = "str"

    # Infer return type
    return_type = None
    if not func_node.returns:
        returns: list[ast.Return] = [n for n in ast.walk(func_node) if isinstance(n, ast.Return)]

        if not returns or all(r.value is None for r in returns):
            return_type = "None"
        else:
            # Check return value types
            return_types: set[str] = set()
            for ret in returns:
                if ret.value:
                    if isinstance(ret.value, ast.Constant):
                        if isinstance(ret.value.value, str):
                            return_types.add("str")
                        elif isinstance(ret.value.value, int):
                            return_types.add("int")
                        elif isinstance(ret.value.value, float):
                            return_types.add("float")
                        elif isinstance(ret.value.value, bool):
                            return_types.add("bool")
                    elif isinstance(ret.value, ast.List):
                        return_types.add("list")
                    elif isinstance(ret.value, ast.Dict):
                        return_types.add("dict")
                    elif isinstance(ret.value, ast.Name):
                        if ret.value.id == "self":
                            return_types.add("Self")
                        elif ret.value.id in ("True", "False"):
                            return_types.add("bool")

            if len(return_types) == 1:
                return_type = return_types.pop()
            elif len(return_types) > 1:
                return_type = f"Union[{', '.join(sorted(return_types))}]"

    # Only create suggestion if we found types to add
    if inferred_types or return_type:
        # Build original signature
        orig_params = []
        for p in params:
            if p.annotation:
                orig_params.append(f"{p.arg}: {ast.unparse(p.annotation)}")
            else:
                orig_params.append(p.arg)
        orig_sig = f"def {func_node.name}({', '.join(orig_params)})"
        if func_node.returns:
            orig_sig += f" -> {ast.unparse(func_node.returns)}"

        # Build suggested signature
        new_params = []
        for p in params:
            if p.annotation:
                new_params.append(f"{p.arg}: {ast.unparse(p.annotation)}")
            elif p.arg in inferred_types:
                new_params.append(f"{p.arg}: {inferred_types[p.arg]}")
            else:
                new_params.append(p.arg)

        new_sig = f"def {func_node.name}({', '.join(new_params)})"
        if return_type:
            new_sig += f" -> {return_type}"
        elif func_node.returns:
            new_sig += f" -> {ast.unparse(func_node.returns)}"

        suggestions.append(TypeHintSuggestion(
            target=func_node.name,
            target_type="function",
            file_path=file_path,
            line_number=func_node.lineno,
            original_signature=orig_sig,
            suggested_signature=new_sig,
            inferred_types=inferred_types,
            confidence="medium" if len(inferred_types) > 0 else "low",
            reasoning="Inferred from default values and usage patterns"
        ))

    return suggestions


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: SuggestRefactoringTool
# ═══════════════════════════════════════════════════════════════════════════════


class SuggestRefactoringTool(Tool):
    """Analyze code and suggest refactoring opportunities."""

    name = "suggest_refactoring"
    description = (
        "Analyze source code and suggest refactoring opportunities including "
        "extract method, simplify conditionals, remove duplication, and more."
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
            "refactoring_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific refactoring types to check (default: all)"
            },
            "min_confidence": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Minimum confidence level for suggestions (default: medium)"
            },
            "include_snippets": {
                "type": "boolean",
                "description": "Include before/after code snippets (default: true)"
            },
            "output_format": {
                "type": "string",
                "enum": ["text", "json", "markdown"],
                "description": "Output format (default: markdown)"
            },
            "thresholds": {
                "type": "object",
                "description": "Custom thresholds: method_lines, nesting_depth, parameters"
            }
        },
        "required": ["source_path"]
    }

    async def execute(
        self,
        source_path: str,
        recursive: bool = False,
        refactoring_types: Optional[list[str]] = None,
        min_confidence: str = "medium",
        include_snippets: bool = True,
        output_format: str = "markdown",
        thresholds: Optional[dict] = None,
        **kwargs
    ) -> ToolResult:
        """Execute refactoring analysis."""
        try:
            path = self._resolve_path(source_path)
            if not path.exists():
                return ToolResult(success=False, output="", error=f"Path not found: {path}")

            # Set thresholds
            default_thresholds = {
                "method_lines": 50,
                "nesting_depth": 4,
                "parameters": 5,
            }
            if thresholds:
                default_thresholds.update(thresholds)

            # Confidence filter
            confidence_order = {"low": 0, "medium": 1, "high": 2}
            min_conf_level = confidence_order.get(min_confidence, 1)

            files = _get_source_files(path, recursive)
            if not files:
                return ToolResult(
                    success=True,
                    output="No supported source files found.",
                    metadata={"file_count": 0}
                )

            all_suggestions: list[RefactoringSuggestion] = []

            for file_path in files:
                if file_path.suffix != ".py":
                    continue  # Currently only Python supported

                async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    source = await f.read()

                try:
                    tree = ast.parse(source)
                except SyntaxError:
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        suggestions = _analyze_function_for_refactoring(
                            node, source, str(file_path), default_thresholds
                        )
                        all_suggestions.extend(suggestions)

            # Filter by confidence
            filtered = [s for s in all_suggestions
                       if confidence_order.get(s.confidence, 0) >= min_conf_level]

            # Filter by type if specified
            if refactoring_types:
                filtered = [s for s in filtered if s.refactoring_type in refactoring_types]

            # Remove snippets if not requested
            if not include_snippets:
                for s in filtered:
                    s.before_snippet = ""
                    s.after_snippet = ""

            # Format output
            data = {
                "total_suggestions": len(filtered),
                "files_analyzed": len(files),
                "suggestions": [
                    {
                        "type": s.refactoring_type,
                        "target": s.target,
                        "file": s.file_path,
                        "line": s.line_number,
                        "description": s.description,
                        "rationale": s.rationale,
                        "before_snippet": s.before_snippet,
                        "after_snippet": s.after_snippet,
                        "confidence": s.confidence,
                        "impact": s.impact,
                    }
                    for s in filtered
                ]
            }

            output = _format_output(data, output_format, "Refactoring Suggestions")

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "suggestion_count": len(filtered),
                    "files_analyzed": len(files),
                    "format": output_format
                }
            )

        except Exception as e:
            log.error("refactoring_analysis_failed", error=str(e))
            return ToolResult(success=False, output="", error=f"Analysis failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: OptimizePerformanceTool
# ═══════════════════════════════════════════════════════════════════════════════


class OptimizePerformanceTool(Tool):
    """Identify performance bottlenecks and suggest optimizations."""

    name = "optimize_performance"
    description = (
        "Analyze code for performance issues including algorithm complexity, "
        "unnecessary computations, missing caching, and N+1 query patterns."
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
            "issue_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific issue types to check (default: all)"
            },
            "include_complexity": {
                "type": "boolean",
                "description": "Include Big-O complexity analysis (default: true)"
            },
            "severity_filter": {
                "type": "string",
                "enum": ["all", "warning", "error"],
                "description": "Filter by severity (default: all)"
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
        issue_types: Optional[list[str]] = None,
        include_complexity: bool = True,
        severity_filter: str = "all",
        output_format: str = "markdown",
        **kwargs
    ) -> ToolResult:
        """Execute performance analysis."""
        try:
            path = self._resolve_path(source_path)
            if not path.exists():
                return ToolResult(success=False, output="", error=f"Path not found: {path}")

            files = _get_source_files(path, recursive)
            if not files:
                return ToolResult(
                    success=True,
                    output="No supported source files found.",
                    metadata={"file_count": 0}
                )

            all_issues: list[PerformanceIssue] = []

            for file_path in files:
                if file_path.suffix != ".py":
                    continue

                async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    source = await f.read()

                try:
                    tree = ast.parse(source)
                except SyntaxError:
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        issues = _analyze_for_performance(node, source, str(file_path), node.name)
                        all_issues.extend(issues)

            # Filter by type if specified
            if issue_types:
                all_issues = [i for i in all_issues if i.issue_type in issue_types]

            # Filter by severity
            if severity_filter != "all":
                all_issues = [i for i in all_issues if i.severity == severity_filter]

            # Remove complexity info if not requested
            if not include_complexity:
                for issue in all_issues:
                    issue.current_complexity = None
                    issue.suggested_complexity = None

            # Format output
            data = {
                "total_issues": len(all_issues),
                "files_analyzed": len(files),
                "issues": [
                    {
                        "type": i.issue_type,
                        "location": i.location,
                        "file": i.file_path,
                        "line": i.line_number,
                        "description": i.description,
                        "current_complexity": i.current_complexity,
                        "suggested_complexity": i.suggested_complexity,
                        "suggestion": i.suggestion,
                        "severity": i.severity,
                    }
                    for i in all_issues
                ]
            }

            output = _format_output(data, output_format, "Performance Analysis")

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "issue_count": len(all_issues),
                    "files_analyzed": len(files),
                    "format": output_format
                }
            )

        except Exception as e:
            log.error("performance_analysis_failed", error=str(e))
            return ToolResult(success=False, output="", error=f"Analysis failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: DetectAntipatternsTool
# ═══════════════════════════════════════════════════════════════════════════════


class DetectAntipatternsTool(Tool):
    """Find coding antipatterns in source code."""

    name = "detect_antipatterns"
    description = (
        "Detect coding antipatterns including God objects, feature envy, "
        "primitive obsession, callback hell, and more."
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
            "patterns_to_check": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific antipatterns to check (default: all)"
            },
            "severity_filter": {
                "type": "string",
                "enum": ["all", "info", "warning", "error"],
                "description": "Filter by severity (default: all)"
            },
            "output_format": {
                "type": "string",
                "enum": ["text", "json", "markdown"],
                "description": "Output format (default: markdown)"
            },
            "thresholds": {
                "type": "object",
                "description": "Custom thresholds: class_methods, class_attributes, method_lines, parameters"
            }
        },
        "required": ["source_path"]
    }

    async def execute(
        self,
        source_path: str,
        recursive: bool = False,
        patterns_to_check: Optional[list[str]] = None,
        severity_filter: str = "all",
        output_format: str = "markdown",
        thresholds: Optional[dict] = None,
        **kwargs
    ) -> ToolResult:
        """Execute antipattern detection."""
        try:
            path = self._resolve_path(source_path)
            if not path.exists():
                return ToolResult(success=False, output="", error=f"Path not found: {path}")

            # Set thresholds
            default_thresholds = {
                "class_methods": 20,
                "class_attributes": 15,
                "method_lines": 50,
                "parameters": 5,
            }
            if thresholds:
                default_thresholds.update(thresholds)

            files = _get_source_files(path, recursive)
            if not files:
                return ToolResult(
                    success=True,
                    output="No supported source files found.",
                    metadata={"file_count": 0}
                )

            all_antipatterns: list[Antipattern] = []

            for file_path in files:
                if file_path.suffix != ".py":
                    continue

                async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    source = await f.read()

                try:
                    tree = ast.parse(source)
                except SyntaxError:
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        patterns = _analyze_class_for_antipatterns(
                            node, source, str(file_path), default_thresholds
                        )
                        all_antipatterns.extend(patterns)

                    # Also check standalone functions for long method
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # Only top-level functions (not methods)
                        if not any(isinstance(p, ast.ClassDef) for p in ast.walk(tree)
                                  if hasattr(p, 'body') and node in getattr(p, 'body', [])):
                            method_lines = _count_lines(node)
                            if method_lines > default_thresholds.get("method_lines", 50):
                                all_antipatterns.append(Antipattern(
                                    pattern_type=AntipatternType.LONG_METHOD.value,
                                    name=node.name,
                                    file_path=str(file_path),
                                    line_number=node.lineno,
                                    description=f"Function '{node.name}' is {method_lines} lines long",
                                    severity="warning",
                                    suggestion="Break into smaller, focused functions",
                                    metrics={"lines": method_lines}
                                ))

            # Filter by pattern type
            if patterns_to_check:
                all_antipatterns = [a for a in all_antipatterns if a.pattern_type in patterns_to_check]

            # Filter by severity
            if severity_filter != "all":
                all_antipatterns = [a for a in all_antipatterns if a.severity == severity_filter]

            # Format output
            data = {
                "total_antipatterns": len(all_antipatterns),
                "files_analyzed": len(files),
                "antipatterns": [
                    {
                        "type": a.pattern_type,
                        "name": a.name,
                        "file": a.file_path,
                        "line": a.line_number,
                        "description": a.description,
                        "severity": a.severity,
                        "suggestion": a.suggestion,
                        "metrics": a.metrics,
                    }
                    for a in all_antipatterns
                ]
            }

            output = _format_output(data, output_format, "Antipattern Detection")

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "antipattern_count": len(all_antipatterns),
                    "files_analyzed": len(files),
                    "format": output_format
                }
            )

        except Exception as e:
            log.error("antipattern_detection_failed", error=str(e))
            return ToolResult(success=False, output="", error=f"Analysis failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: SuggestDesignPatternsTool
# ═══════════════════════════════════════════════════════════════════════════════


class SuggestDesignPatternsTool(Tool):
    """Recommend applicable design patterns for code structures."""

    name = "suggest_design_patterns"
    description = (
        "Analyze code structure and recommend applicable design patterns "
        "such as Factory, Strategy, Observer, Builder, and more."
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
            "patterns_to_suggest": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific patterns to consider (default: all)"
            },
            "min_applicability": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Minimum applicability score (default: medium)"
            },
            "include_examples": {
                "type": "boolean",
                "description": "Include before/after code examples (default: true)"
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
        patterns_to_suggest: Optional[list[str]] = None,
        min_applicability: str = "medium",
        include_examples: bool = True,
        output_format: str = "markdown",
        **kwargs
    ) -> ToolResult:
        """Execute design pattern suggestion."""
        try:
            path = self._resolve_path(source_path)
            if not path.exists():
                return ToolResult(success=False, output="", error=f"Path not found: {path}")

            # Applicability filter
            applicability_order = {"low": 0, "medium": 1, "high": 2}
            min_app_level = applicability_order.get(min_applicability, 1)

            files = _get_source_files(path, recursive)
            if not files:
                return ToolResult(
                    success=True,
                    output="No supported source files found.",
                    metadata={"file_count": 0}
                )

            all_recommendations: list[PatternRecommendation] = []

            for file_path in files:
                if file_path.suffix != ".py":
                    continue

                async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    source = await f.read()

                try:
                    tree = ast.parse(source)
                except SyntaxError:
                    continue

                recommendations = _suggest_design_patterns(tree, source, str(file_path))
                all_recommendations.extend(recommendations)

            # Filter by applicability
            filtered = [r for r in all_recommendations
                       if applicability_order.get(r.applicability, 0) >= min_app_level]

            # Filter by pattern type
            if patterns_to_suggest:
                filtered = [r for r in filtered if r.pattern in patterns_to_suggest]

            # Remove examples if not requested
            if not include_examples:
                for r in filtered:
                    r.example_before = ""
                    r.example_after = ""

            # Format output
            data = {
                "total_recommendations": len(filtered),
                "files_analyzed": len(files),
                "recommendations": [
                    {
                        "pattern": r.pattern,
                        "applicability": r.applicability,
                        "context": r.context,
                        "file": r.file_path,
                        "line": r.line_number,
                        "description": r.description,
                        "problem_indicators": r.problem_indicators,
                        "example_before": r.example_before,
                        "example_after": r.example_after,
                        "benefits": r.benefits,
                    }
                    for r in filtered
                ]
            }

            output = _format_output(data, output_format, "Design Pattern Recommendations")

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "recommendation_count": len(filtered),
                    "files_analyzed": len(files),
                    "format": output_format
                }
            )

        except Exception as e:
            log.error("design_pattern_suggestion_failed", error=str(e))
            return ToolResult(success=False, output="", error=f"Analysis failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: GenerateTypeHintsTool
# ═══════════════════════════════════════════════════════════════════════════════


class GenerateTypeHintsTool(Tool):
    """Generate or improve type annotations for Python code."""

    name = "generate_type_hints"
    description = (
        "Analyze Python code and generate type hints for functions and variables "
        "by inferring types from default values, usage patterns, and docstrings."
    )
    parameters = {
        "type": "object",
        "properties": {
            "source_path": {
                "type": "string",
                "description": "Path to Python source file or directory"
            },
            "recursive": {
                "type": "boolean",
                "description": "Recursively analyze directories (default: false)"
            },
            "target": {
                "type": "string",
                "description": "Specific function or class name to analyze (optional)"
            },
            "include_return": {
                "type": "boolean",
                "description": "Include return type hints (default: true)"
            },
            "min_confidence": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Minimum confidence level for suggestions (default: low)"
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
        target: Optional[str] = None,
        include_return: bool = True,
        min_confidence: str = "low",
        output_format: str = "markdown",
        **kwargs
    ) -> ToolResult:
        """Execute type hint generation."""
        try:
            path = self._resolve_path(source_path)
            if not path.exists():
                return ToolResult(success=False, output="", error=f"Path not found: {path}")

            # Confidence filter
            confidence_order = {"low": 0, "medium": 1, "high": 2}
            min_conf_level = confidence_order.get(min_confidence, 0)

            files = _get_source_files(path, recursive)
            # Only Python files for type hints
            files = [f for f in files if f.suffix in (".py", ".pyi")]

            if not files:
                return ToolResult(
                    success=True,
                    output="No Python source files found.",
                    metadata={"file_count": 0}
                )

            all_suggestions: list[TypeHintSuggestion] = []

            for file_path in files:
                async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    source = await f.read()

                try:
                    tree = ast.parse(source)
                except SyntaxError:
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # Filter by target if specified
                        if target and node.name != target:
                            continue

                        suggestions = _infer_type_hints(node, source, str(file_path))
                        all_suggestions.extend(suggestions)

            # Filter by confidence
            filtered = [s for s in all_suggestions
                       if confidence_order.get(s.confidence, 0) >= min_conf_level]

            # Format output
            data = {
                "total_suggestions": len(filtered),
                "files_analyzed": len(files),
                "suggestions": [
                    {
                        "target": s.target,
                        "target_type": s.target_type,
                        "file": s.file_path,
                        "line": s.line_number,
                        "original_signature": s.original_signature,
                        "suggested_signature": s.suggested_signature,
                        "inferred_types": s.inferred_types,
                        "confidence": s.confidence,
                        "reasoning": s.reasoning,
                    }
                    for s in filtered
                ]
            }

            output = _format_output(data, output_format, "Type Hint Suggestions")

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "suggestion_count": len(filtered),
                    "files_analyzed": len(files),
                    "format": output_format
                }
            )

        except Exception as e:
            log.error("type_hint_generation_failed", error=str(e))
            return ToolResult(success=False, output="", error=f"Analysis failed: {e}")
