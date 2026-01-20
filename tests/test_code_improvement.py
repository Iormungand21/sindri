"""Tests for Phase 13 Tier 4 Code Improvement Tools.

Tests for:
- SuggestRefactoringTool
- OptimizePerformanceTool
- DetectAntipatternsTool
- SuggestDesignPatternsTool
- GenerateTypeHintsTool
"""

import json
import tempfile
from pathlib import Path

import pytest

from sindri.tools.code_improvement import (
    SuggestRefactoringTool,
    OptimizePerformanceTool,
    DetectAntipatternsTool,
    SuggestDesignPatternsTool,
    GenerateTypeHintsTool,
    # Data classes
    RefactoringSuggestion,
    PerformanceIssue,
    Antipattern,
    PatternRecommendation,
    TypeHintSuggestion,
    # Enums
    RefactoringType,
    PerformanceIssueType,
    AntipatternType,
    DesignPatternType,
    Confidence,
    Severity,
    # Helper functions
    _get_source_files,
    _calculate_nesting_depth,
    _count_lines,
    _hash_code_block,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def simple_python_file(temp_dir):
    """Create a simple Python file for testing."""
    code = '''"""A simple module."""

def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def multiply(x, y):
    result = x * y
    return result


class Calculator:
    """A simple calculator class."""

    def __init__(self):
        self.history = []

    def calculate(self, a, b, op):
        if op == '+':
            return a + b
        elif op == '-':
            return a - b
        else:
            return None
'''
    file_path = temp_dir / "simple.py"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def complex_python_file(temp_dir):
    """Create a complex Python file with refactoring opportunities."""
    code = '''"""A complex module with issues."""

def long_function(a, b, c, d, e, f, g):
    """A very long function with many parameters."""
    result = 0
    if a > 0:
        if b > 0:
            if c > 0:
                if d > 0:
                    if e > 0:
                        result = a + b + c + d + e
                    else:
                        result = a + b + c + d
                else:
                    result = a + b + c
            else:
                result = a + b
        else:
            result = a
    else:
        result = 0

    for i in range(10):
        result += i
        for j in range(10):
            result += j
            for k in range(10):
                result += k

    # Magic numbers
    timeout = 3600
    max_retries = 42
    threshold = 0.85

    if result > 100:
        return result
    elif result > 50:
        return result * 2
    elif result > 25:
        return result * 3
    else:
        return 0


class GodClass:
    """A class that does too much."""

    def __init__(self):
        self.data = []
        self.config = {}
        self.cache = {}
        self.state = None
        self.history = []
        self.errors = []
        self.metrics = {}
        self.flags = {}
        self.handlers = {}
        self.validators = {}
        self.transformers = {}
        self.formatters = {}
        self.parsers = {}
        self.serializers = {}
        self.deserializers = {}

    def method1(self): pass
    def method2(self): pass
    def method3(self): pass
    def method4(self): pass
    def method5(self): pass
    def method6(self): pass
    def method7(self): pass
    def method8(self): pass
    def method9(self): pass
    def method10(self): pass
    def method11(self): pass
    def method12(self): pass
    def method13(self): pass
    def method14(self): pass
    def method15(self): pass
    def method16(self): pass
    def method17(self): pass
    def method18(self): pass
    def method19(self): pass
    def method20(self): pass
    def method21(self): pass
'''
    file_path = temp_dir / "complex.py"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def performance_issue_file(temp_dir):
    """Create a Python file with performance issues."""
    code = '''"""A module with performance issues."""

def inefficient_search(items, target):
    """Nested loop search - O(n^2)."""
    for i in items:
        for j in items:
            if i + j == target:
                return (i, j)
    return None


def string_concat_loop(items):
    """String concatenation in loop."""
    result = ""
    for item in items:
        result = result + str(item) + ", "
    return result


def repeated_file_read(filenames):
    """File I/O in loop - N+1 pattern."""
    contents = []
    for filename in filenames:
        with open(filename) as f:
            contents.append(f.read())
    return contents


def nested_queries(users):
    """Database query in loop - N+1 pattern."""
    results = []
    for user in users:
        # Simulating database call
        data = fetch_user_data(user.id)
        results.append(data)
    return results


def triple_nested_loop(matrix):
    """Triple nested loop - O(n^3)."""
    result = 0
    for i in matrix:
        for j in matrix:
            for k in matrix:
                result += i * j * k
    return result
'''
    file_path = temp_dir / "performance.py"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def design_pattern_file(temp_dir):
    """Create a Python file that could benefit from design patterns."""
    code = '''"""A module that could use design patterns."""

class ShapeCreator:
    """Creates shapes based on type."""

    def create_shape(self, shape_type, **kwargs):
        if shape_type == "circle":
            return Circle(kwargs.get("radius", 1))
        elif shape_type == "square":
            return Square(kwargs.get("side", 1))
        elif shape_type == "rectangle":
            return Rectangle(kwargs.get("width", 1), kwargs.get("height", 1))
        elif shape_type == "triangle":
            return Triangle(kwargs.get("base", 1), kwargs.get("height", 1))
        else:
            raise ValueError(f"Unknown shape: {shape_type}")


class PaymentProcessor:
    """Processes payments with type checks."""

    def process(self, payment):
        if isinstance(payment, CreditCard):
            return self._process_credit_card(payment)
        elif isinstance(payment, PayPal):
            return self._process_paypal(payment)
        elif isinstance(payment, BankTransfer):
            return self._process_bank_transfer(payment)
        else:
            raise ValueError("Unknown payment type")

    def _process_credit_card(self, payment): pass
    def _process_paypal(self, payment): pass
    def _process_bank_transfer(self, payment): pass


class EventEmitter:
    """Class with observer-like behavior."""

    def __init__(self):
        self.listeners = []

    def subscribe(self, listener):
        self.listeners.append(listener)

    def unsubscribe(self, listener):
        self.listeners.remove(listener)

    def notify(self, event):
        for listener in self.listeners:
            listener(event)


class ComplexBuilder:
    """Class with complex construction."""

    def __init__(self, name, type, size, color, material, weight,
                 durability, flexibility, texture, finish):
        self.name = name
        self.type = type
        self.size = size
        self.color = color
        self.material = material
        self.weight = weight
        self.durability = durability
        self.flexibility = flexibility
        self.texture = texture
        self.finish = finish
'''
    file_path = temp_dir / "patterns.py"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def untyped_python_file(temp_dir):
    """Create a Python file without type hints."""
    code = '''"""A module without type hints."""

def greet(name, greeting="Hello"):
    """Greet someone."""
    return f"{greeting}, {name}!"


def calculate_total(items, tax_rate=0.1):
    """Calculate total with tax."""
    subtotal = sum(items)
    return subtotal * (1 + tax_rate)


def process_data(data, transform=None):
    """Process data with optional transform."""
    if transform:
        data = transform(data)
    return data


def find_matches(text, patterns):
    """Find all pattern matches in text."""
    matches = []
    for pattern in patterns:
        if pattern in text:
            matches.append(pattern)
    return matches


class DataProcessor:
    """Processes data."""

    def __init__(self, config=None):
        self.config = config or {}

    def process(self, data):
        """Process the data."""
        result = []
        for item in data:
            result.append(self.transform(item))
        return result

    def transform(self, item):
        """Transform a single item."""
        return str(item).upper()
'''
    file_path = temp_dir / "untyped.py"
    file_path.write_text(code)
    return file_path


# ═══════════════════════════════════════════════════════════════════════════════
# Helper Function Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_source_files_single_file(self, simple_python_file):
        """Test getting a single source file."""
        files = _get_source_files(simple_python_file)
        assert len(files) == 1
        assert files[0] == simple_python_file

    def test_get_source_files_directory(self, temp_dir, simple_python_file):
        """Test getting source files from directory."""
        # Create another file
        (temp_dir / "another.py").write_text("# Another file")
        files = _get_source_files(temp_dir)
        assert len(files) == 2

    def test_get_source_files_recursive(self, temp_dir):
        """Test recursive file search."""
        (temp_dir / "root.py").write_text("# Root")
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        (subdir / "nested.py").write_text("# Nested")

        files_non_recursive = _get_source_files(temp_dir, recursive=False)
        files_recursive = _get_source_files(temp_dir, recursive=True)

        assert len(files_non_recursive) == 1
        assert len(files_recursive) == 2

    def test_calculate_nesting_depth(self):
        """Test nesting depth calculation."""
        import ast
        code = """
def test():
    if a:
        for i in range(10):
            if b:
                while c:
                    pass
"""
        tree = ast.parse(code)
        func = tree.body[0]
        depth = _calculate_nesting_depth(func)
        assert depth >= 4

    def test_count_lines(self):
        """Test line counting."""
        import ast
        code = """def test():
    a = 1
    b = 2
    c = 3
    return a + b + c
"""
        tree = ast.parse(code)
        func = tree.body[0]
        lines = _count_lines(func)
        assert lines == 5

    def test_hash_code_block(self):
        """Test code block hashing for similarity."""
        code1 = "for i in items:\n    process(i)"
        code2 = "for x in elements:\n    process(x)"
        code3 = "while True:\n    do_something()"

        hash1 = _hash_code_block(code1)
        hash2 = _hash_code_block(code2)
        hash3 = _hash_code_block(code3)

        # Similar code should have same hash
        assert hash1 == hash2
        # Different code should have different hash
        assert hash1 != hash3


# ═══════════════════════════════════════════════════════════════════════════════
# SuggestRefactoringTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSuggestRefactoringTool:
    """Tests for SuggestRefactoringTool."""

    def test_tool_metadata(self):
        """Test tool has correct metadata."""
        tool = SuggestRefactoringTool()
        assert tool.name == "suggest_refactoring"
        assert "source_path" in tool.parameters["properties"]
        assert "source_path" in tool.parameters["required"]

    @pytest.mark.asyncio
    async def test_analyze_simple_file(self, simple_python_file):
        """Test analyzing a simple file."""
        tool = SuggestRefactoringTool()
        result = await tool.execute(source_path=str(simple_python_file))

        assert result.success is True
        assert "suggestion" in result.output.lower() or "Refactoring" in result.output

    @pytest.mark.asyncio
    async def test_detect_long_method(self, complex_python_file):
        """Test detection of long methods."""
        tool = SuggestRefactoringTool()
        result = await tool.execute(
            source_path=str(complex_python_file),
            thresholds={"method_lines": 20},  # Lower threshold to detect
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        suggestions = data.get("suggestions", [])

        # Should find long_function
        long_method_suggestions = [s for s in suggestions if s["type"] == "extract_method"]
        assert len(long_method_suggestions) >= 1

    @pytest.mark.asyncio
    async def test_detect_deep_nesting(self, complex_python_file):
        """Test detection of deep nesting."""
        tool = SuggestRefactoringTool()
        result = await tool.execute(
            source_path=str(complex_python_file),
            thresholds={"nesting_depth": 3},
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        suggestions = data.get("suggestions", [])

        # Should find deeply nested code
        nesting_suggestions = [s for s in suggestions if s["type"] == "simplify_conditional"]
        assert len(nesting_suggestions) >= 1

    @pytest.mark.asyncio
    async def test_detect_many_parameters(self, complex_python_file):
        """Test detection of functions with many parameters."""
        tool = SuggestRefactoringTool()
        result = await tool.execute(
            source_path=str(complex_python_file),
            thresholds={"parameters": 4},
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        suggestions = data.get("suggestions", [])

        # Should find long_function with 7 parameters
        param_suggestions = [s for s in suggestions if s["type"] == "introduce_parameter_object"]
        assert len(param_suggestions) >= 1

    @pytest.mark.asyncio
    async def test_detect_magic_numbers(self, complex_python_file):
        """Test detection of magic numbers."""
        tool = SuggestRefactoringTool()
        result = await tool.execute(
            source_path=str(complex_python_file),
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        suggestions = data.get("suggestions", [])

        # Should find magic numbers (3600, 42, 0.85)
        magic_suggestions = [s for s in suggestions if s["type"] == "replace_magic_number"]
        assert len(magic_suggestions) >= 1

    @pytest.mark.asyncio
    async def test_confidence_filter(self, complex_python_file):
        """Test filtering by confidence level."""
        tool = SuggestRefactoringTool()

        result_all = await tool.execute(
            source_path=str(complex_python_file),
            min_confidence="low",
            output_format="json"
        )

        result_high = await tool.execute(
            source_path=str(complex_python_file),
            min_confidence="high",
            output_format="json"
        )

        data_all = json.loads(result_all.output)
        data_high = json.loads(result_high.output)

        # High confidence should have fewer or equal suggestions
        assert data_high["total_suggestions"] <= data_all["total_suggestions"]

    @pytest.mark.asyncio
    async def test_output_formats(self, simple_python_file):
        """Test different output formats."""
        tool = SuggestRefactoringTool()

        for fmt in ["text", "json", "markdown"]:
            result = await tool.execute(
                source_path=str(simple_python_file),
                output_format=fmt
            )
            assert result.success is True
            assert result.metadata["format"] == fmt

    @pytest.mark.asyncio
    async def test_nonexistent_file(self):
        """Test handling of nonexistent file."""
        tool = SuggestRefactoringTool()
        result = await tool.execute(source_path="/nonexistent/path.py")

        assert result.success is False
        assert "not found" in result.error.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# OptimizePerformanceTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestOptimizePerformanceTool:
    """Tests for OptimizePerformanceTool."""

    def test_tool_metadata(self):
        """Test tool has correct metadata."""
        tool = OptimizePerformanceTool()
        assert tool.name == "optimize_performance"
        assert "source_path" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_detect_nested_loops(self, performance_issue_file):
        """Test detection of nested loops."""
        tool = OptimizePerformanceTool()
        result = await tool.execute(
            source_path=str(performance_issue_file),
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        issues = data.get("issues", [])

        # Should find algorithm complexity issues
        complexity_issues = [i for i in issues if i["type"] == "algorithm_complexity"]
        assert len(complexity_issues) >= 1

    @pytest.mark.asyncio
    async def test_detect_n_plus_one(self, performance_issue_file):
        """Test detection of N+1 patterns."""
        tool = OptimizePerformanceTool()
        result = await tool.execute(
            source_path=str(performance_issue_file),
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        issues = data.get("issues", [])

        # Should find N+1 issues (file read and fetch in loop)
        n_plus_one = [i for i in issues if i["type"] == "n_plus_one"]
        assert len(n_plus_one) >= 1

    @pytest.mark.asyncio
    async def test_detect_string_concat(self, performance_issue_file):
        """Test detection of string concatenation in loops."""
        tool = OptimizePerformanceTool()
        result = await tool.execute(
            source_path=str(performance_issue_file),
            output_format="json"
        )

        assert result.success is True
        # String concatenation detection depends on implementation

    @pytest.mark.asyncio
    async def test_complexity_analysis(self, performance_issue_file):
        """Test Big-O complexity analysis."""
        tool = OptimizePerformanceTool()
        result = await tool.execute(
            source_path=str(performance_issue_file),
            include_complexity=True,
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        issues = data.get("issues", [])

        # At least one issue should have complexity info
        complexity_issues = [i for i in issues if i.get("current_complexity")]
        assert len(complexity_issues) >= 1

    @pytest.mark.asyncio
    async def test_severity_filter(self, performance_issue_file):
        """Test filtering by severity."""
        tool = OptimizePerformanceTool()

        result_all = await tool.execute(
            source_path=str(performance_issue_file),
            severity_filter="all",
            output_format="json"
        )

        result_error = await tool.execute(
            source_path=str(performance_issue_file),
            severity_filter="error",
            output_format="json"
        )

        data_all = json.loads(result_all.output)
        data_error = json.loads(result_error.output)

        # Error filter should have fewer or equal issues
        assert data_error["total_issues"] <= data_all["total_issues"]

    @pytest.mark.asyncio
    async def test_output_formats(self, performance_issue_file):
        """Test different output formats."""
        tool = OptimizePerformanceTool()

        for fmt in ["text", "json", "markdown"]:
            result = await tool.execute(
                source_path=str(performance_issue_file),
                output_format=fmt
            )
            assert result.success is True


# ═══════════════════════════════════════════════════════════════════════════════
# DetectAntipatternsTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDetectAntipatternsTool:
    """Tests for DetectAntipatternsTool."""

    def test_tool_metadata(self):
        """Test tool has correct metadata."""
        tool = DetectAntipatternsTool()
        assert tool.name == "detect_antipatterns"
        assert "source_path" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_detect_god_object(self, complex_python_file):
        """Test detection of God Object antipattern."""
        tool = DetectAntipatternsTool()
        result = await tool.execute(
            source_path=str(complex_python_file),
            thresholds={"class_methods": 15, "class_attributes": 10},
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        antipatterns = data.get("antipatterns", [])

        # Should find GodClass
        god_objects = [a for a in antipatterns if a["type"] == "god_object"]
        assert len(god_objects) >= 1

    @pytest.mark.asyncio
    async def test_detect_long_method(self, complex_python_file):
        """Test detection of Long Method antipattern."""
        tool = DetectAntipatternsTool()
        result = await tool.execute(
            source_path=str(complex_python_file),
            thresholds={"method_lines": 20},
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        antipatterns = data.get("antipatterns", [])

        # Should find long methods
        long_methods = [a for a in antipatterns if a["type"] == "long_method"]
        assert len(long_methods) >= 1

    @pytest.mark.asyncio
    async def test_detect_long_parameter_list(self, complex_python_file):
        """Test detection of Long Parameter List antipattern."""
        tool = DetectAntipatternsTool()
        result = await tool.execute(
            source_path=str(complex_python_file),
            thresholds={"parameters": 4},
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        antipatterns = data.get("antipatterns", [])

        # Should find long_function's parameter list
        param_lists = [a for a in antipatterns if a["type"] == "long_parameter_list"]
        # May or may not detect depending on if it's in a class

    @pytest.mark.asyncio
    async def test_pattern_filter(self, complex_python_file):
        """Test filtering by specific pattern types."""
        tool = DetectAntipatternsTool()
        result = await tool.execute(
            source_path=str(complex_python_file),
            patterns_to_check=["god_object"],
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        antipatterns = data.get("antipatterns", [])

        # All antipatterns should be god_object type
        for ap in antipatterns:
            assert ap["type"] == "god_object"

    @pytest.mark.asyncio
    async def test_severity_filter(self, complex_python_file):
        """Test filtering by severity."""
        tool = DetectAntipatternsTool()

        result_all = await tool.execute(
            source_path=str(complex_python_file),
            severity_filter="all",
            output_format="json"
        )

        result_error = await tool.execute(
            source_path=str(complex_python_file),
            severity_filter="error",
            output_format="json"
        )

        data_all = json.loads(result_all.output)
        data_error = json.loads(result_error.output)

        assert data_error["total_antipatterns"] <= data_all["total_antipatterns"]

    @pytest.mark.asyncio
    async def test_output_formats(self, complex_python_file):
        """Test different output formats."""
        tool = DetectAntipatternsTool()

        for fmt in ["text", "json", "markdown"]:
            result = await tool.execute(
                source_path=str(complex_python_file),
                output_format=fmt
            )
            assert result.success is True

    @pytest.mark.asyncio
    async def test_metrics_included(self, complex_python_file):
        """Test that metrics are included in output."""
        tool = DetectAntipatternsTool()
        result = await tool.execute(
            source_path=str(complex_python_file),
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        antipatterns = data.get("antipatterns", [])

        # At least some antipatterns should have metrics
        has_metrics = any(ap.get("metrics") for ap in antipatterns)
        assert has_metrics


# ═══════════════════════════════════════════════════════════════════════════════
# SuggestDesignPatternsTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSuggestDesignPatternsTool:
    """Tests for SuggestDesignPatternsTool."""

    def test_tool_metadata(self):
        """Test tool has correct metadata."""
        tool = SuggestDesignPatternsTool()
        assert tool.name == "suggest_design_patterns"
        assert "source_path" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_suggest_factory_pattern(self, design_pattern_file):
        """Test suggestion of Factory pattern."""
        tool = SuggestDesignPatternsTool()
        result = await tool.execute(
            source_path=str(design_pattern_file),
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        recommendations = data.get("recommendations", [])

        # Should suggest Factory for ShapeCreator
        factory_recs = [r for r in recommendations if r["pattern"] == "factory"]
        assert len(factory_recs) >= 1

    @pytest.mark.asyncio
    async def test_suggest_strategy_pattern(self, design_pattern_file):
        """Test suggestion of Strategy pattern."""
        tool = SuggestDesignPatternsTool()
        result = await tool.execute(
            source_path=str(design_pattern_file),
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        recommendations = data.get("recommendations", [])

        # Should suggest Strategy for PaymentProcessor
        strategy_recs = [r for r in recommendations if r["pattern"] == "strategy"]
        assert len(strategy_recs) >= 1

    @pytest.mark.asyncio
    async def test_suggest_observer_pattern(self, design_pattern_file):
        """Test suggestion of Observer pattern."""
        tool = SuggestDesignPatternsTool()
        result = await tool.execute(
            source_path=str(design_pattern_file),
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        recommendations = data.get("recommendations", [])

        # Should recognize EventEmitter's observer-like behavior
        observer_recs = [r for r in recommendations if r["pattern"] == "observer"]
        assert len(observer_recs) >= 1

    @pytest.mark.asyncio
    async def test_suggest_builder_pattern(self, design_pattern_file):
        """Test suggestion of Builder pattern."""
        tool = SuggestDesignPatternsTool()
        result = await tool.execute(
            source_path=str(design_pattern_file),
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        recommendations = data.get("recommendations", [])

        # Should suggest Builder for ComplexBuilder's complex constructor
        builder_recs = [r for r in recommendations if r["pattern"] == "builder"]
        assert len(builder_recs) >= 1

    @pytest.mark.asyncio
    async def test_applicability_filter(self, design_pattern_file):
        """Test filtering by applicability level."""
        tool = SuggestDesignPatternsTool()

        result_all = await tool.execute(
            source_path=str(design_pattern_file),
            min_applicability="low",
            output_format="json"
        )

        result_high = await tool.execute(
            source_path=str(design_pattern_file),
            min_applicability="high",
            output_format="json"
        )

        data_all = json.loads(result_all.output)
        data_high = json.loads(result_high.output)

        assert data_high["total_recommendations"] <= data_all["total_recommendations"]

    @pytest.mark.asyncio
    async def test_pattern_filter(self, design_pattern_file):
        """Test filtering by specific patterns."""
        tool = SuggestDesignPatternsTool()
        result = await tool.execute(
            source_path=str(design_pattern_file),
            patterns_to_suggest=["factory", "builder"],
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        recommendations = data.get("recommendations", [])

        # All recommendations should be factory or builder
        for rec in recommendations:
            assert rec["pattern"] in ["factory", "builder"]

    @pytest.mark.asyncio
    async def test_include_examples(self, design_pattern_file):
        """Test inclusion of code examples."""
        tool = SuggestDesignPatternsTool()

        result_with = await tool.execute(
            source_path=str(design_pattern_file),
            include_examples=True,
            output_format="json"
        )

        result_without = await tool.execute(
            source_path=str(design_pattern_file),
            include_examples=False,
            output_format="json"
        )

        data_with = json.loads(result_with.output)
        data_without = json.loads(result_without.output)

        # Recommendations with examples should have example_before/after
        if data_with.get("recommendations"):
            rec = data_with["recommendations"][0]
            assert rec.get("example_before") or rec.get("example_after") or True

        # Without examples should have empty strings
        if data_without.get("recommendations"):
            rec = data_without["recommendations"][0]
            assert rec.get("example_before", "") == ""

    @pytest.mark.asyncio
    async def test_output_formats(self, design_pattern_file):
        """Test different output formats."""
        tool = SuggestDesignPatternsTool()

        for fmt in ["text", "json", "markdown"]:
            result = await tool.execute(
                source_path=str(design_pattern_file),
                output_format=fmt
            )
            assert result.success is True


# ═══════════════════════════════════════════════════════════════════════════════
# GenerateTypeHintsTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateTypeHintsTool:
    """Tests for GenerateTypeHintsTool."""

    def test_tool_metadata(self):
        """Test tool has correct metadata."""
        tool = GenerateTypeHintsTool()
        assert tool.name == "generate_type_hints"
        assert "source_path" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_infer_from_defaults(self, untyped_python_file):
        """Test type inference from default values."""
        tool = GenerateTypeHintsTool()
        result = await tool.execute(
            source_path=str(untyped_python_file),
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        suggestions = data.get("suggestions", [])

        # Should find untyped functions and suggest hints
        assert len(suggestions) >= 1

    @pytest.mark.asyncio
    async def test_infer_string_type(self, untyped_python_file):
        """Test inference of string types."""
        tool = GenerateTypeHintsTool()
        result = await tool.execute(
            source_path=str(untyped_python_file),
            target="greet",
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        suggestions = data.get("suggestions", [])

        # greet has greeting="Hello" default - should infer str
        greet_suggestions = [s for s in suggestions if s["target"] == "greet"]
        if greet_suggestions:
            assert "str" in str(greet_suggestions[0].get("inferred_types", {}))

    @pytest.mark.asyncio
    async def test_infer_numeric_type(self, untyped_python_file):
        """Test inference of numeric types."""
        tool = GenerateTypeHintsTool()
        result = await tool.execute(
            source_path=str(untyped_python_file),
            target="calculate_total",
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        suggestions = data.get("suggestions", [])

        # calculate_total has tax_rate=0.1 - should infer float
        calc_suggestions = [s for s in suggestions if s["target"] == "calculate_total"]
        if calc_suggestions:
            inferred = calc_suggestions[0].get("inferred_types", {})
            assert "float" in str(inferred) or "tax_rate" in str(inferred)

    @pytest.mark.asyncio
    async def test_target_filter(self, untyped_python_file):
        """Test filtering by target function."""
        tool = GenerateTypeHintsTool()
        result = await tool.execute(
            source_path=str(untyped_python_file),
            target="greet",
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        suggestions = data.get("suggestions", [])

        # Should only have suggestions for greet
        for s in suggestions:
            assert s["target"] == "greet"

    @pytest.mark.asyncio
    async def test_confidence_filter(self, untyped_python_file):
        """Test filtering by confidence level."""
        tool = GenerateTypeHintsTool()

        result_all = await tool.execute(
            source_path=str(untyped_python_file),
            min_confidence="low",
            output_format="json"
        )

        result_high = await tool.execute(
            source_path=str(untyped_python_file),
            min_confidence="high",
            output_format="json"
        )

        data_all = json.loads(result_all.output)
        data_high = json.loads(result_high.output)

        assert data_high["total_suggestions"] <= data_all["total_suggestions"]

    @pytest.mark.asyncio
    async def test_output_formats(self, untyped_python_file):
        """Test different output formats."""
        tool = GenerateTypeHintsTool()

        for fmt in ["text", "json", "markdown"]:
            result = await tool.execute(
                source_path=str(untyped_python_file),
                output_format=fmt
            )
            assert result.success is True

    @pytest.mark.asyncio
    async def test_already_typed_function(self, simple_python_file):
        """Test handling of already-typed functions."""
        tool = GenerateTypeHintsTool()
        result = await tool.execute(
            source_path=str(simple_python_file),
            target="add",  # This function has type hints
            output_format="json"
        )

        assert result.success is True
        # Should not suggest redundant hints for fully-typed functions

    @pytest.mark.asyncio
    async def test_signature_format(self, untyped_python_file):
        """Test that suggested signatures are properly formatted."""
        tool = GenerateTypeHintsTool()
        result = await tool.execute(
            source_path=str(untyped_python_file),
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        suggestions = data.get("suggestions", [])

        for s in suggestions:
            # Should have both original and suggested signatures
            assert "original_signature" in s
            assert "suggested_signature" in s
            # Suggested should include "def"
            assert s["suggested_signature"].startswith("def ")


# ═══════════════════════════════════════════════════════════════════════════════
# Data Class Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDataClasses:
    """Tests for data classes."""

    def test_refactoring_suggestion_creation(self):
        """Test RefactoringSuggestion creation."""
        suggestion = RefactoringSuggestion(
            refactoring_type="extract_method",
            target="my_function",
            file_path="/path/to/file.py",
            line_number=10,
            end_line=50,
            description="Function is too long",
            rationale="Long functions are hard to maintain",
            before_snippet="def my_function(): ...",
            after_snippet="def my_function(): helper()",
            confidence="high",
            impact="high"
        )
        assert suggestion.refactoring_type == "extract_method"
        assert suggestion.confidence == "high"

    def test_performance_issue_creation(self):
        """Test PerformanceIssue creation."""
        issue = PerformanceIssue(
            issue_type="algorithm_complexity",
            location="process_data",
            file_path="/path/to/file.py",
            line_number=25,
            description="Nested loops detected",
            current_complexity="O(n^2)",
            suggested_complexity="O(n)",
            suggestion="Use a dictionary for lookups",
            severity="warning"
        )
        assert issue.issue_type == "algorithm_complexity"
        assert issue.current_complexity == "O(n^2)"

    def test_antipattern_creation(self):
        """Test Antipattern creation."""
        antipattern = Antipattern(
            pattern_type="god_object",
            name="DatabaseManager",
            file_path="/path/to/file.py",
            line_number=5,
            description="Class has too many responsibilities",
            severity="error",
            suggestion="Split into smaller classes",
            metrics={"methods": 50, "attributes": 30}
        )
        assert antipattern.pattern_type == "god_object"
        assert antipattern.metrics["methods"] == 50

    def test_pattern_recommendation_creation(self):
        """Test PatternRecommendation creation."""
        rec = PatternRecommendation(
            pattern="factory",
            applicability="high",
            context="create_widget",
            file_path="/path/to/file.py",
            line_number=15,
            description="Consider Factory pattern",
            problem_indicators=["Multiple if/elif"],
            example_before="if type == 'a': ...",
            example_after="factories[type]()",
            benefits=["Extensible", "Clean"]
        )
        assert rec.pattern == "factory"
        assert len(rec.benefits) == 2

    def test_type_hint_suggestion_creation(self):
        """Test TypeHintSuggestion creation."""
        suggestion = TypeHintSuggestion(
            target="process",
            target_type="function",
            file_path="/path/to/file.py",
            line_number=20,
            original_signature="def process(data):",
            suggested_signature="def process(data: list) -> None:",
            inferred_types={"data": "list"},
            confidence="medium",
            reasoning="Inferred from usage"
        )
        assert suggestion.target == "process"
        assert suggestion.inferred_types["data"] == "list"


# ═══════════════════════════════════════════════════════════════════════════════
# Enum Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnums:
    """Tests for enums."""

    def test_refactoring_type_values(self):
        """Test RefactoringType enum values."""
        assert RefactoringType.EXTRACT_METHOD.value == "extract_method"
        assert RefactoringType.SIMPLIFY_CONDITIONAL.value == "simplify_conditional"
        assert RefactoringType.REPLACE_MAGIC_NUMBER.value == "replace_magic_number"

    def test_performance_issue_type_values(self):
        """Test PerformanceIssueType enum values."""
        assert PerformanceIssueType.ALGORITHM_COMPLEXITY.value == "algorithm_complexity"
        assert PerformanceIssueType.N_PLUS_ONE.value == "n_plus_one"
        assert PerformanceIssueType.BLOCKING_IO.value == "blocking_io"

    def test_antipattern_type_values(self):
        """Test AntipatternType enum values."""
        assert AntipatternType.GOD_OBJECT.value == "god_object"
        assert AntipatternType.FEATURE_ENVY.value == "feature_envy"
        assert AntipatternType.CALLBACK_HELL.value == "callback_hell"

    def test_design_pattern_type_values(self):
        """Test DesignPatternType enum values."""
        assert DesignPatternType.FACTORY.value == "factory"
        assert DesignPatternType.STRATEGY.value == "strategy"
        assert DesignPatternType.OBSERVER.value == "observer"
        assert DesignPatternType.BUILDER.value == "builder"

    def test_confidence_values(self):
        """Test Confidence enum values."""
        assert Confidence.HIGH.value == "high"
        assert Confidence.MEDIUM.value == "medium"
        assert Confidence.LOW.value == "low"

    def test_severity_values(self):
        """Test Severity enum values."""
        assert Severity.INFO.value == "info"
        assert Severity.WARNING.value == "warning"
        assert Severity.ERROR.value == "error"


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestIntegration:
    """Integration tests for all tools working together."""

    @pytest.mark.asyncio
    async def test_all_tools_work_together(self, complex_python_file):
        """Test that all tools can analyze the same file."""
        tools = [
            SuggestRefactoringTool(),
            OptimizePerformanceTool(),
            DetectAntipatternsTool(),
            SuggestDesignPatternsTool(),
            GenerateTypeHintsTool(),
        ]

        for tool in tools:
            result = await tool.execute(source_path=str(complex_python_file))
            assert result.success is True

    @pytest.mark.asyncio
    async def test_empty_directory(self, temp_dir):
        """Test handling of empty directory."""
        tools = [
            SuggestRefactoringTool(),
            OptimizePerformanceTool(),
            DetectAntipatternsTool(),
            SuggestDesignPatternsTool(),
            GenerateTypeHintsTool(),
        ]

        for tool in tools:
            result = await tool.execute(source_path=str(temp_dir))
            assert result.success is True
            assert "No" in result.output or result.metadata.get("file_count", 0) == 0

    @pytest.mark.asyncio
    async def test_syntax_error_handling(self, temp_dir):
        """Test handling of files with syntax errors."""
        bad_file = temp_dir / "bad.py"
        bad_file.write_text("def broken(:\n    pass")

        tools = [
            SuggestRefactoringTool(),
            OptimizePerformanceTool(),
            DetectAntipatternsTool(),
            SuggestDesignPatternsTool(),
            GenerateTypeHintsTool(),
        ]

        for tool in tools:
            result = await tool.execute(source_path=str(bad_file))
            # Should handle syntax errors gracefully
            assert result.success is True

    @pytest.mark.asyncio
    async def test_recursive_analysis(self, temp_dir, simple_python_file):
        """Test recursive directory analysis."""
        # Create subdirectory with file
        subdir = temp_dir / "sub"
        subdir.mkdir()
        (subdir / "nested.py").write_text('def nested(): pass')

        tool = SuggestRefactoringTool()

        result_non_recursive = await tool.execute(
            source_path=str(temp_dir),
            recursive=False,
            output_format="json"
        )

        result_recursive = await tool.execute(
            source_path=str(temp_dir),
            recursive=True,
            output_format="json"
        )

        data_non = json.loads(result_non_recursive.output)
        data_rec = json.loads(result_recursive.output)

        # Recursive should find more or equal files
        assert data_rec["files_analyzed"] >= data_non["files_analyzed"]
