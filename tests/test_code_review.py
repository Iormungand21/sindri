"""Tests for Phase 13 Tier 3 Code Review Tools.

Tests for:
- AnalyzeCodeQualityTool
- DetectCodeSmellsTool
- SecurityAuditTool
- DetectDeadCodeTool
- GenerateReviewReportTool
"""

import json
import tempfile
from pathlib import Path

import pytest

from sindri.tools.code_review import (
    AnalyzeCodeQualityTool,
    DetectCodeSmellsTool,
    SecurityAuditTool,
    DetectDeadCodeTool,
    GenerateReviewReportTool,
    # Data classes
    QualityMetrics,
    CodeSmell,
    SecurityFinding,
    DeadCodeItem,
    Severity,
    SmellType,
    SecurityCheckType,
    DeadCodeType,
    # Helper functions
    _calculate_cyclomatic_complexity,
    _calculate_cognitive_complexity,
    _calculate_maintainability_index,
    _calculate_halstead_metrics,
    _calculate_entropy,
    _is_likely_secret,
    _count_lines,
    _calculate_nesting_depth,
    _calculate_grade,
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
    """Create a complex Python file with code smells."""
    code = '''"""A complex module with issues."""

import os
import sys
import json  # Unused import
import unused_module  # Unused import


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


def unused_function():
    """This function is never called."""
    pass


unused_variable = 42
'''
    file_path = temp_dir / "complex.py"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def insecure_python_file(temp_dir):
    """Create a Python file with security issues."""
    code = '''"""A module with security vulnerabilities."""

import os
import pickle
import subprocess

# Hardcoded secrets
API_KEY = "sk-1234567890abcdefghijklmnopqrstuvwxyz"
PASSWORD = "super_secret_password_123"
AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"

def execute_query(user_input):
    """SQL injection vulnerability."""
    query = f"SELECT * FROM users WHERE name = '{user_input}'"
    cursor.execute(query)


def run_command(cmd):
    """Command injection vulnerability."""
    os.system(f"echo {cmd}")
    subprocess.call(cmd, shell=True)


def load_data(data):
    """Insecure deserialization."""
    return pickle.loads(data)


def weak_hash(password):
    """Weak cryptography."""
    import hashlib
    return hashlib.md5(password.encode()).hexdigest()


def debug_function():
    """Debug code in production."""
    import pdb
    pdb.set_trace()
    print("DEBUG: This is debug output")


def dangerous_eval(user_code):
    """Dangerous eval usage."""
    result = eval(user_code)
    return result
'''
    file_path = temp_dir / "insecure.py"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def dead_code_file(temp_dir):
    """Create a Python file with dead code."""
    code = '''"""A module with dead code."""

import os
import json  # Never used
from pathlib import Path  # Never used


def used_function():
    """This function is used."""
    return os.getcwd()


def unused_function():
    """This function is never called."""
    pass


def another_unused():
    """Another unused function."""
    return 42


class UsedClass:
    """This class is used."""
    pass


class UnusedClass:
    """This class is never instantiated."""
    pass


USED_CONSTANT = "used"
UNUSED_CONSTANT = "never used"


def function_with_unused_param(a, b, c):
    """Function with unused parameter c."""
    return a + b


def unreachable_code():
    """Function with unreachable code."""
    return 42
    x = 10  # Unreachable
    print(x)  # Unreachable


# Using some of the definitions
result = used_function()
instance = UsedClass()
print(USED_CONSTANT)
function_with_unused_param(1, 2, 3)
'''
    file_path = temp_dir / "dead_code.py"
    file_path.write_text(code)
    return file_path


# ═══════════════════════════════════════════════════════════════════════════════
# Helper Function Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_calculate_entropy_empty_string(self):
        """Test entropy of empty string."""
        assert _calculate_entropy("") == 0.0

    def test_calculate_entropy_single_char(self):
        """Test entropy of single repeated character."""
        assert _calculate_entropy("aaaa") == 0.0

    def test_calculate_entropy_high_entropy(self):
        """Test entropy of random-looking string."""
        # High entropy string
        entropy = _calculate_entropy("aB3$xY9@kL")
        assert entropy > 3.0  # Should be high

    def test_is_likely_secret_short_string(self):
        """Test that short strings are not detected as secrets."""
        assert _is_likely_secret("abc") is False

    def test_is_likely_secret_low_entropy(self):
        """Test that low entropy strings are not detected as secrets."""
        assert _is_likely_secret("aaaaaaaaaaaaaaaa") is False

    def test_is_likely_secret_high_entropy(self):
        """Test that high entropy strings are detected as secrets."""
        assert _is_likely_secret("sk1234567890abcdefghij") is True

    def test_calculate_cyclomatic_complexity_simple(self):
        """Test cyclomatic complexity of simple function."""
        code = "def simple(): return 42"
        assert _calculate_cyclomatic_complexity(code) == 1

    def test_calculate_cyclomatic_complexity_with_if(self):
        """Test cyclomatic complexity with if statement."""
        code = """
def test():
    if x:
        return 1
    return 0
"""
        assert _calculate_cyclomatic_complexity(code) >= 2

    def test_calculate_cyclomatic_complexity_with_loop(self):
        """Test cyclomatic complexity with loop."""
        code = """
def test():
    for i in range(10):
        print(i)
"""
        assert _calculate_cyclomatic_complexity(code) >= 2

    def test_calculate_cyclomatic_complexity_with_boolean(self):
        """Test cyclomatic complexity with boolean operators."""
        code = """
def test():
    if a and b or c:
        return True
"""
        complexity = _calculate_cyclomatic_complexity(code)
        assert complexity >= 3  # if + and + or

    def test_calculate_cognitive_complexity(self):
        """Test cognitive complexity calculation."""
        code = """
def nested():
    if a:
        if b:
            if c:
                return True
"""
        cognitive = _calculate_cognitive_complexity(code)
        assert cognitive > 3  # Nested ifs add extra complexity

    def test_calculate_maintainability_index_high(self):
        """Test maintainability index for good code."""
        mi = _calculate_maintainability_index(100, 2, 20)
        assert mi > 50  # Good code should have MI > 50

    def test_calculate_maintainability_index_low(self):
        """Test maintainability index for complex code."""
        mi = _calculate_maintainability_index(10000, 50, 500)
        assert mi < 50  # Complex code has lower MI

    def test_calculate_halstead_metrics(self):
        """Test Halstead metrics calculation."""
        code = "x = 1 + 2 * 3"
        volume, difficulty, effort = _calculate_halstead_metrics(code)
        assert volume >= 0
        assert difficulty >= 0
        assert effort >= 0

    def test_count_lines(self):
        """Test line counting."""
        code = '''# Comment
def func():
    """Docstring"""
    return 42

'''
        total, sloc, comments, blank = _count_lines(code)
        assert total == 5  # 5 lines: comment, def, docstring, return, blank
        assert blank >= 1
        assert comments >= 1  # At least the # comment

    def test_calculate_nesting_depth(self):
        """Test nesting depth calculation."""
        code = """
def test():
    if a:
        for i in range(10):
            if b:
                while c:
                    pass
"""
        depth = _calculate_nesting_depth(code)
        assert depth >= 4

    def test_calculate_grade_excellent(self):
        """Test grade calculation for excellent code."""
        metrics = QualityMetrics(maintainability_index=90, cyclomatic_complexity=5)
        grade = _calculate_grade(metrics, smell_count=0, security_count=0)
        assert grade in ("A", "B")

    def test_calculate_grade_poor(self):
        """Test grade calculation for poor code."""
        metrics = QualityMetrics(maintainability_index=10, cyclomatic_complexity=100)
        grade = _calculate_grade(metrics, smell_count=20, security_count=10)
        assert grade in ("D", "F")


# ═══════════════════════════════════════════════════════════════════════════════
# AnalyzeCodeQualityTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalyzeCodeQualityTool:
    """Tests for AnalyzeCodeQualityTool."""

    def test_tool_metadata(self):
        """Test tool has correct metadata."""
        tool = AnalyzeCodeQualityTool()
        assert tool.name == "analyze_code_quality"
        assert "cyclomatic" in tool.description.lower()
        assert "source_path" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_analyze_simple_file(self, simple_python_file):
        """Test analysis of simple Python file."""
        tool = AnalyzeCodeQualityTool()
        result = await tool.execute(source_path=str(simple_python_file))

        assert result.success is True
        assert result.metadata["files_analyzed"] == 1
        assert result.metadata["total_lines"] > 0
        assert result.metadata["cyclomatic_complexity"] >= 1

    @pytest.mark.asyncio
    async def test_analyze_with_json_output(self, simple_python_file):
        """Test JSON output format."""
        tool = AnalyzeCodeQualityTool()
        result = await tool.execute(
            source_path=str(simple_python_file),
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        assert "metrics" in data
        assert "functions" in data

    @pytest.mark.asyncio
    async def test_analyze_with_markdown_output(self, simple_python_file):
        """Test markdown output format."""
        tool = AnalyzeCodeQualityTool()
        result = await tool.execute(
            source_path=str(simple_python_file),
            output_format="markdown"
        )

        assert result.success is True
        assert "# Code Quality Analysis" in result.output
        assert "Cyclomatic Complexity" in result.output

    @pytest.mark.asyncio
    async def test_analyze_directory(self, temp_dir, simple_python_file):
        """Test analysis of directory."""
        # Create another file
        (temp_dir / "another.py").write_text("def foo(): return 1")

        tool = AnalyzeCodeQualityTool(work_dir=temp_dir)
        result = await tool.execute(
            source_path=str(temp_dir),
            recursive=True
        )

        assert result.success is True
        assert result.metadata["files_analyzed"] == 2

    @pytest.mark.asyncio
    async def test_analyze_nonexistent_file(self):
        """Test analysis of nonexistent file."""
        tool = AnalyzeCodeQualityTool()
        result = await tool.execute(source_path="/nonexistent/file.py")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_threshold_warnings(self, complex_python_file):
        """Test that threshold warnings are generated."""
        tool = AnalyzeCodeQualityTool()
        result = await tool.execute(
            source_path=str(complex_python_file),
            threshold_complexity=5,
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        # Should have warnings for complex functions
        assert len(data.get("issues", [])) > 0

    @pytest.mark.asyncio
    async def test_function_metrics_extraction(self, simple_python_file):
        """Test that per-function metrics are extracted."""
        tool = AnalyzeCodeQualityTool()
        result = await tool.execute(
            source_path=str(simple_python_file),
            include_functions=True,
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        functions = data.get("functions", [])
        assert len(functions) >= 2  # add and multiply
        func_names = [f["name"] for f in functions]
        assert "add" in func_names
        assert "multiply" in func_names


# ═══════════════════════════════════════════════════════════════════════════════
# DetectCodeSmellsTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDetectCodeSmellsTool:
    """Tests for DetectCodeSmellsTool."""

    def test_tool_metadata(self):
        """Test tool has correct metadata."""
        tool = DetectCodeSmellsTool()
        assert tool.name == "detect_code_smells"
        assert "anti-pattern" in tool.description.lower()

    @pytest.mark.asyncio
    async def test_detect_long_method(self, complex_python_file):
        """Test detection of long methods."""
        tool = DetectCodeSmellsTool()
        result = await tool.execute(
            source_path=str(complex_python_file),
            smells_to_check=["long_method"],
            thresholds={"method_lines": 10},
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        smells = data.get("smells", [])
        long_methods = [s for s in smells if s["smell_type"] == "long_method"]
        assert len(long_methods) > 0

    @pytest.mark.asyncio
    async def test_detect_large_class(self, complex_python_file):
        """Test detection of large classes."""
        tool = DetectCodeSmellsTool()
        result = await tool.execute(
            source_path=str(complex_python_file),
            smells_to_check=["large_class"],
            thresholds={"class_methods": 10},
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        smells = data.get("smells", [])
        large_classes = [s for s in smells if s["smell_type"] == "large_class"]
        assert len(large_classes) > 0
        assert any("GodClass" in s["name"] for s in large_classes)

    @pytest.mark.asyncio
    async def test_detect_deep_nesting(self, complex_python_file):
        """Test detection of deep nesting."""
        tool = DetectCodeSmellsTool()
        result = await tool.execute(
            source_path=str(complex_python_file),
            smells_to_check=["deep_nesting"],
            thresholds={"nesting_depth": 3},
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        smells = data.get("smells", [])
        nesting = [s for s in smells if s["smell_type"] == "deep_nesting"]
        assert len(nesting) > 0

    @pytest.mark.asyncio
    async def test_detect_long_parameter_list(self, complex_python_file):
        """Test detection of long parameter lists."""
        tool = DetectCodeSmellsTool()
        result = await tool.execute(
            source_path=str(complex_python_file),
            smells_to_check=["long_parameter_list"],
            thresholds={"parameters": 4},
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        smells = data.get("smells", [])
        param_smells = [s for s in smells if s["smell_type"] == "long_parameter_list"]
        assert len(param_smells) > 0

    @pytest.mark.asyncio
    async def test_detect_magic_numbers(self, temp_dir):
        """Test detection of magic numbers."""
        code = """
def calculate():
    x = 42  # Magic number
    y = 1337  # Another magic number
    return x + y + 100
"""
        file_path = temp_dir / "magic.py"
        file_path.write_text(code)

        tool = DetectCodeSmellsTool()
        result = await tool.execute(
            source_path=str(file_path),
            smells_to_check=["magic_number"],
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        smells = data.get("smells", [])
        magic = [s for s in smells if s["smell_type"] == "magic_number"]
        # Should find at least some magic numbers
        assert len(magic) >= 1

    @pytest.mark.asyncio
    async def test_output_formats(self, simple_python_file):
        """Test different output formats."""
        tool = DetectCodeSmellsTool()

        for fmt in ["text", "json", "markdown", "sarif"]:
            result = await tool.execute(
                source_path=str(simple_python_file),
                output_format=fmt
            )
            assert result.success is True
            assert len(result.output) > 0

    @pytest.mark.asyncio
    async def test_severity_filter(self, complex_python_file):
        """Test severity filtering."""
        tool = DetectCodeSmellsTool()

        # Get all smells first
        result_all = await tool.execute(
            source_path=str(complex_python_file),
            severity_filter="all",
            output_format="json"
        )

        # Get only errors
        result_error = await tool.execute(
            source_path=str(complex_python_file),
            severity_filter="error",
            output_format="json"
        )

        all_data = json.loads(result_all.output)
        error_data = json.loads(result_error.output)

        # Error-only should have fewer or equal smells
        assert len(error_data.get("smells", [])) <= len(all_data.get("smells", []))


# ═══════════════════════════════════════════════════════════════════════════════
# SecurityAuditTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecurityAuditTool:
    """Tests for SecurityAuditTool."""

    def test_tool_metadata(self):
        """Test tool has correct metadata."""
        tool = SecurityAuditTool()
        assert tool.name == "security_audit"
        assert "security" in tool.description.lower()

    @pytest.mark.asyncio
    async def test_detect_hardcoded_secrets(self, insecure_python_file):
        """Test detection of hardcoded secrets."""
        tool = SecurityAuditTool()
        result = await tool.execute(
            source_path=str(insecure_python_file),
            checks=["hardcoded_secret"],
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        findings = data.get("findings", [])
        secrets = [f for f in findings if f["check_type"] == "hardcoded_secret"]
        assert len(secrets) >= 2  # API_KEY, PASSWORD, etc.

    @pytest.mark.asyncio
    async def test_detect_sql_injection(self, insecure_python_file):
        """Test detection of SQL injection."""
        tool = SecurityAuditTool()
        result = await tool.execute(
            source_path=str(insecure_python_file),
            checks=["sql_injection"],
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        findings = data.get("findings", [])
        sql_issues = [f for f in findings if f["check_type"] == "sql_injection"]
        assert len(sql_issues) >= 1

    @pytest.mark.asyncio
    async def test_detect_command_injection(self, insecure_python_file):
        """Test detection of command injection."""
        tool = SecurityAuditTool()
        result = await tool.execute(
            source_path=str(insecure_python_file),
            checks=["command_injection"],
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        findings = data.get("findings", [])
        cmd_issues = [f for f in findings if f["check_type"] == "command_injection"]
        assert len(cmd_issues) >= 1

    @pytest.mark.asyncio
    async def test_detect_insecure_deserialization(self, insecure_python_file):
        """Test detection of insecure deserialization."""
        tool = SecurityAuditTool()
        result = await tool.execute(
            source_path=str(insecure_python_file),
            checks=["insecure_deserialization"],
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        findings = data.get("findings", [])
        deser_issues = [f for f in findings if f["check_type"] == "insecure_deserialization"]
        assert len(deser_issues) >= 1

    @pytest.mark.asyncio
    async def test_detect_weak_crypto(self, insecure_python_file):
        """Test detection of weak cryptography."""
        tool = SecurityAuditTool()
        result = await tool.execute(
            source_path=str(insecure_python_file),
            checks=["weak_crypto"],
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        findings = data.get("findings", [])
        crypto_issues = [f for f in findings if f["check_type"] == "weak_crypto"]
        assert len(crypto_issues) >= 1

    @pytest.mark.asyncio
    async def test_detect_debug_code(self, insecure_python_file):
        """Test detection of debug code."""
        tool = SecurityAuditTool()
        result = await tool.execute(
            source_path=str(insecure_python_file),
            checks=["debug_code"],
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        findings = data.get("findings", [])
        debug_issues = [f for f in findings if f["check_type"] == "debug_code"]
        assert len(debug_issues) >= 1

    @pytest.mark.asyncio
    async def test_detect_eval_usage(self, insecure_python_file):
        """Test detection of dangerous eval usage."""
        tool = SecurityAuditTool()
        result = await tool.execute(
            source_path=str(insecure_python_file),
            checks=["eval_usage"],
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        findings = data.get("findings", [])
        eval_issues = [f for f in findings if f["check_type"] == "eval_usage"]
        assert len(eval_issues) >= 1

    @pytest.mark.asyncio
    async def test_severity_filter(self, insecure_python_file):
        """Test severity filtering."""
        tool = SecurityAuditTool()

        # Get critical/high only
        result = await tool.execute(
            source_path=str(insecure_python_file),
            severity_filter="high",
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        for finding in data.get("findings", []):
            assert finding["severity"] in ("high", "critical")

    @pytest.mark.asyncio
    async def test_exclude_patterns(self, temp_dir, insecure_python_file):
        """Test exclude patterns."""
        # Copy insecure file to test directory
        (temp_dir / "test_insecure.py").write_text(insecure_python_file.read_text())

        tool = SecurityAuditTool()
        result = await tool.execute(
            source_path=str(temp_dir),
            exclude_patterns=["test_.*"],
            output_format="json"
        )

        assert result.success is True
        # Should have fewer or no findings since test file is excluded

    @pytest.mark.asyncio
    async def test_sarif_output(self, insecure_python_file):
        """Test SARIF output format."""
        tool = SecurityAuditTool()
        result = await tool.execute(
            source_path=str(insecure_python_file),
            output_format="sarif"
        )

        assert result.success is True
        sarif = json.loads(result.output)
        assert sarif["version"] == "2.1.0"
        assert "runs" in sarif
        assert len(sarif["runs"]) > 0

    @pytest.mark.asyncio
    async def test_cwe_mapping(self, insecure_python_file):
        """Test that findings have CWE IDs."""
        tool = SecurityAuditTool()
        result = await tool.execute(
            source_path=str(insecure_python_file),
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        for finding in data.get("findings", []):
            assert "cwe_id" in finding
            assert finding["cwe_id"].startswith("CWE-")


# ═══════════════════════════════════════════════════════════════════════════════
# DetectDeadCodeTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDetectDeadCodeTool:
    """Tests for DetectDeadCodeTool."""

    def test_tool_metadata(self):
        """Test tool has correct metadata."""
        tool = DetectDeadCodeTool()
        assert tool.name == "detect_dead_code"
        assert "unused" in tool.description.lower()

    @pytest.mark.asyncio
    async def test_detect_unused_imports(self, dead_code_file):
        """Test detection of unused imports."""
        tool = DetectDeadCodeTool()
        result = await tool.execute(
            source_path=str(dead_code_file),
            check_types=["unused_import"],
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        dead = data.get("dead_code", [])
        imports = [d for d in dead if d["item_type"] == "unused_import"]
        assert len(imports) >= 2  # json and Path

    @pytest.mark.asyncio
    async def test_detect_unused_functions(self, dead_code_file):
        """Test detection of unused functions."""
        tool = DetectDeadCodeTool()
        result = await tool.execute(
            source_path=str(dead_code_file),
            check_types=["unused_function"],
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        dead = data.get("dead_code", [])
        funcs = [d for d in dead if d["item_type"] == "unused_function"]
        func_names = [f["name"] for f in funcs]
        assert "unused_function" in func_names or "another_unused" in func_names

    @pytest.mark.asyncio
    async def test_detect_unused_classes(self, dead_code_file):
        """Test detection of unused classes."""
        tool = DetectDeadCodeTool()
        result = await tool.execute(
            source_path=str(dead_code_file),
            check_types=["unused_class"],
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        dead = data.get("dead_code", [])
        classes = [d for d in dead if d["item_type"] == "unused_class"]
        class_names = [c["name"] for c in classes]
        assert "UnusedClass" in class_names

    @pytest.mark.asyncio
    async def test_detect_unused_variables(self, dead_code_file):
        """Test detection of unused variables."""
        tool = DetectDeadCodeTool()
        result = await tool.execute(
            source_path=str(dead_code_file),
            check_types=["unused_variable"],
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        dead = data.get("dead_code", [])
        vars_dead = [d for d in dead if d["item_type"] == "unused_variable"]
        var_names = [v["name"] for v in vars_dead]
        assert "UNUSED_CONSTANT" in var_names

    @pytest.mark.asyncio
    async def test_detect_unreachable_code(self, dead_code_file):
        """Test detection of unreachable code."""
        tool = DetectDeadCodeTool()
        result = await tool.execute(
            source_path=str(dead_code_file),
            check_types=["unreachable"],
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        dead = data.get("dead_code", [])
        unreachable = [d for d in dead if d["item_type"] == "unreachable_code"]
        assert len(unreachable) >= 1

    @pytest.mark.asyncio
    async def test_ignore_patterns(self, dead_code_file):
        """Test ignore patterns for private functions."""
        tool = DetectDeadCodeTool()

        # Without ignore
        result1 = await tool.execute(
            source_path=str(dead_code_file),
            ignore_patterns=[],
            output_format="json"
        )

        # With ignore for underscore-prefixed
        result2 = await tool.execute(
            source_path=str(dead_code_file),
            ignore_patterns=["_*", "__*"],
            output_format="json"
        )

        # Results should be same or fewer with ignore
        data1 = json.loads(result1.output)
        data2 = json.loads(result2.output)
        assert len(data2.get("dead_code", [])) <= len(data1.get("dead_code", []))

    @pytest.mark.asyncio
    async def test_confidence_levels(self, dead_code_file):
        """Test that confidence levels are reported."""
        tool = DetectDeadCodeTool()
        result = await tool.execute(
            source_path=str(dead_code_file),
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        for item in data.get("dead_code", []):
            assert "confidence" in item
            assert item["confidence"] in ("high", "medium", "low")


# ═══════════════════════════════════════════════════════════════════════════════
# GenerateReviewReportTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateReviewReportTool:
    """Tests for GenerateReviewReportTool."""

    def test_tool_metadata(self):
        """Test tool has correct metadata."""
        tool = GenerateReviewReportTool()
        assert tool.name == "generate_review_report"
        assert "comprehensive" in tool.description.lower()

    @pytest.mark.asyncio
    async def test_generate_full_report(self, complex_python_file):
        """Test generation of full report."""
        tool = GenerateReviewReportTool()
        result = await tool.execute(
            source_path=str(complex_python_file),
            output_format="markdown"
        )

        assert result.success is True
        assert "# Code Review Report" in result.output or "Code Review" in result.output
        assert result.metadata["grade"] in ("A", "B", "C", "D", "F")

    @pytest.mark.asyncio
    async def test_report_contains_sections(self, simple_python_file):
        """Test that report contains all sections."""
        tool = GenerateReviewReportTool()
        result = await tool.execute(
            source_path=str(simple_python_file),
            include_sections=["summary", "quality_metrics", "code_smells", "security", "recommendations"],
            output_format="markdown"
        )

        assert result.success is True
        assert "Summary" in result.output or "Metrics" in result.output

    @pytest.mark.asyncio
    async def test_report_json_format(self, simple_python_file):
        """Test JSON report format."""
        tool = GenerateReviewReportTool()
        result = await tool.execute(
            source_path=str(simple_python_file),
            output_format="json"
        )

        assert result.success is True
        data = json.loads(result.output)
        assert "title" in data
        assert "grade" in data
        assert "quality" in data

    @pytest.mark.asyncio
    async def test_report_html_format(self, simple_python_file):
        """Test HTML report format."""
        tool = GenerateReviewReportTool()
        result = await tool.execute(
            source_path=str(simple_python_file),
            output_format="html"
        )

        assert result.success is True
        assert "<!DOCTYPE html>" in result.output
        assert "<html>" in result.output

    @pytest.mark.asyncio
    async def test_write_report_to_file(self, simple_python_file, temp_dir):
        """Test writing report to file."""
        output_file = temp_dir / "report.md"

        tool = GenerateReviewReportTool(work_dir=temp_dir)
        result = await tool.execute(
            source_path=str(simple_python_file),
            output_file=str(output_file),
            output_format="markdown"
        )

        assert result.success is True
        assert output_file.exists()
        content = output_file.read_text()
        assert "Code Review" in content

    @pytest.mark.asyncio
    async def test_dry_run(self, simple_python_file, temp_dir):
        """Test dry run mode."""
        output_file = temp_dir / "report.md"

        tool = GenerateReviewReportTool(work_dir=temp_dir)
        result = await tool.execute(
            source_path=str(simple_python_file),
            output_file=str(output_file),
            dry_run=True,
            output_format="markdown"
        )

        assert result.success is True
        assert not output_file.exists()  # File should not be created

    @pytest.mark.asyncio
    async def test_custom_title(self, simple_python_file):
        """Test custom report title."""
        tool = GenerateReviewReportTool()
        result = await tool.execute(
            source_path=str(simple_python_file),
            title="My Custom Review",
            output_format="markdown"
        )

        assert result.success is True
        assert "My Custom Review" in result.output

    @pytest.mark.asyncio
    async def test_grade_calculation(self, insecure_python_file):
        """Test that insecure code gets worse grade."""
        tool = GenerateReviewReportTool()
        result = await tool.execute(
            source_path=str(insecure_python_file),
            output_format="json"
        )

        assert result.success is True
        # Insecure file should have many issues, likely D or F grade
        assert result.metadata["security_findings"] > 0

    @pytest.mark.asyncio
    async def test_recommendations_generated(self, complex_python_file):
        """Test that recommendations are generated."""
        tool = GenerateReviewReportTool()
        result = await tool.execute(
            source_path=str(complex_python_file),
            include_sections=["recommendations"],
            output_format="markdown"
        )

        assert result.success is True
        assert "Recommendation" in result.output or "recommend" in result.output.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Data Class Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDataClasses:
    """Tests for data classes."""

    def test_quality_metrics_defaults(self):
        """Test QualityMetrics default values."""
        metrics = QualityMetrics()
        assert metrics.total_lines == 0
        assert metrics.cyclomatic_complexity == 1
        assert metrics.maintainability_index == 100.0

    def test_code_smell_creation(self):
        """Test CodeSmell creation."""
        smell = CodeSmell(
            smell_type=SmellType.LONG_METHOD,
            severity=Severity.WARNING,
            file_path="/test.py",
            line_number=10,
            end_line=50,
            name="long_function",
            message="Function is too long",
            suggestion="Split into smaller functions"
        )
        assert smell.smell_type == SmellType.LONG_METHOD
        assert smell.severity == Severity.WARNING

    def test_security_finding_creation(self):
        """Test SecurityFinding creation."""
        finding = SecurityFinding(
            rule_id="SEC001",
            check_type=SecurityCheckType.SQL_INJECTION,
            severity=Severity.CRITICAL,
            confidence="high",
            cwe_id="CWE-89",
            title="SQL Injection",
            description="Potential SQL injection vulnerability",
            file_path="/test.py",
            line_number=15,
            column=5,
            code_snippet="execute(f'SELECT * FROM users WHERE id = {user_id}')",
            remediation="Use parameterized queries"
        )
        assert finding.severity == Severity.CRITICAL
        assert finding.cwe_id == "CWE-89"

    def test_dead_code_item_creation(self):
        """Test DeadCodeItem creation."""
        item = DeadCodeItem(
            item_type=DeadCodeType.UNUSED_IMPORT,
            name="unused_module",
            file_path="/test.py",
            line_number=3,
            confidence="high",
            reason="Import never used",
            suggestion="Remove unused import"
        )
        assert item.item_type == DeadCodeType.UNUSED_IMPORT
        assert item.confidence == "high"


# ═══════════════════════════════════════════════════════════════════════════════
# Enum Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnums:
    """Tests for enum values."""

    def test_severity_values(self):
        """Test Severity enum values."""
        assert Severity.INFO.value == "info"
        assert Severity.CRITICAL.value == "critical"

    def test_smell_type_values(self):
        """Test SmellType enum values."""
        assert SmellType.LONG_METHOD.value == "long_method"
        assert SmellType.LARGE_CLASS.value == "large_class"

    def test_security_check_type_values(self):
        """Test SecurityCheckType enum values."""
        assert SecurityCheckType.SQL_INJECTION.value == "sql_injection"
        assert SecurityCheckType.HARDCODED_SECRET.value == "hardcoded_secret"

    def test_dead_code_type_values(self):
        """Test DeadCodeType enum values."""
        assert DeadCodeType.UNUSED_IMPORT.value == "unused_import"
        assert DeadCodeType.UNUSED_FUNCTION.value == "unused_function"


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestIntegration:
    """Integration tests for code review tools."""

    @pytest.mark.asyncio
    async def test_all_tools_work_together(self, complex_python_file):
        """Test that all tools can analyze the same file."""
        quality_tool = AnalyzeCodeQualityTool()
        smells_tool = DetectCodeSmellsTool()
        security_tool = SecurityAuditTool()
        dead_code_tool = DetectDeadCodeTool()
        report_tool = GenerateReviewReportTool()

        # All tools should succeed on the same file
        results = []
        for tool in [quality_tool, smells_tool, security_tool, dead_code_tool, report_tool]:
            result = await tool.execute(source_path=str(complex_python_file))
            results.append(result)

        for result in results:
            assert result.success is True

    @pytest.mark.asyncio
    async def test_empty_directory(self, temp_dir):
        """Test handling of directory with no source files."""
        tool = AnalyzeCodeQualityTool()
        result = await tool.execute(source_path=str(temp_dir))

        assert result.success is False
        assert "no supported source files" in result.error.lower()

    @pytest.mark.asyncio
    async def test_syntax_error_handling(self, temp_dir):
        """Test handling of files with syntax errors."""
        bad_code = "def broken( { this is not valid python"
        bad_file = temp_dir / "bad.py"
        bad_file.write_text(bad_code)

        tool = AnalyzeCodeQualityTool()
        result = await tool.execute(source_path=str(bad_file))

        # Should still succeed, just with limited analysis
        assert result.success is True
