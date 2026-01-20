"""Tests for Phase 13 Test Generation Tools.

Tests for:
- SuggestTestCasesTool
- GenerateUnitTestsTool
- GenerateTestFixturesTool
- GeneratePropertyTestsTool
"""

import json
import tempfile
from pathlib import Path

import pytest

from sindri.tools.test_generation import (
    SuggestTestCasesTool,
    GenerateUnitTestsTool,
    GenerateTestFixturesTool,
    GeneratePropertyTestsTool,
    FunctionInfo,
    ClassInfo,
    ParameterInfo,
    SuggestedTestCase,
    _extract_imports,
    _detect_patterns,
    _detect_test_framework,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Sample Python Code for Testing
# ═══════════════════════════════════════════════════════════════════════════════

SAMPLE_PYTHON_CODE = '''"""Sample module for testing."""

from pathlib import Path
from typing import Optional, List
import requests


def validate_email(email: str) -> bool:
    """Validate an email address.

    Args:
        email: The email address to validate.

    Returns:
        True if valid, False otherwise.
    """
    if not email:
        return False
    return "@" in email and "." in email.split("@")[-1]


def calculate_total(items: List[dict], discount: float = 0.0) -> float:
    """Calculate total price with optional discount.

    Args:
        items: List of items with 'price' key.
        discount: Discount percentage (0.0 to 1.0).

    Returns:
        Total price after discount.
    """
    total = sum(item.get("price", 0) for item in items)
    return total * (1 - discount)


async def fetch_data(url: str, timeout: Optional[int] = None) -> dict:
    """Fetch data from URL.

    Args:
        url: The URL to fetch.
        timeout: Optional timeout in seconds.

    Returns:
        Response data as dict.
    """
    response = requests.get(url, timeout=timeout)
    return response.json()


class UserService:
    """Service for managing users."""

    def __init__(self, db_path: str, cache_enabled: bool = True):
        """Initialize the service.

        Args:
            db_path: Path to database.
            cache_enabled: Whether to enable caching.
        """
        self.db_path = db_path
        self.cache_enabled = cache_enabled

    def get_user(self, user_id: int) -> Optional[dict]:
        """Get user by ID.

        Args:
            user_id: The user ID.

        Returns:
            User data or None if not found.
        """
        # Implementation here
        pass

    async def create_user(self, name: str, email: str) -> dict:
        """Create a new user.

        Args:
            name: User's name.
            email: User's email.

        Returns:
            Created user data.
        """
        # Implementation here
        pass
'''

SAMPLE_PYTHON_WITH_PATTERNS = '''"""Module with various patterns."""

import re
from pathlib import Path


def divide(a: int, b: int) -> float:
    """Divide two numbers."""
    return a / b


def read_config(path: str) -> dict:
    """Read config file."""
    with open(path) as f:
        return json.load(f)


def validate_input(data: str) -> bool:
    """Validate input string."""
    pattern = re.compile(r"^[a-z]+$")
    return bool(pattern.match(data))
'''


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def temp_python_file(tmp_path):
    """Create a temporary Python file with sample code."""
    file_path = tmp_path / "sample.py"
    file_path.write_text(SAMPLE_PYTHON_CODE)
    return file_path


@pytest.fixture
def temp_python_with_patterns(tmp_path):
    """Create a temporary Python file with patterns."""
    file_path = tmp_path / "patterns.py"
    file_path.write_text(SAMPLE_PYTHON_WITH_PATTERNS)
    return file_path


@pytest.fixture
def suggest_tool():
    """Create SuggestTestCasesTool instance."""
    return SuggestTestCasesTool()


@pytest.fixture
def generate_tool():
    """Create GenerateUnitTestsTool instance."""
    return GenerateUnitTestsTool()


@pytest.fixture
def fixture_tool():
    """Create GenerateTestFixturesTool instance."""
    return GenerateTestFixturesTool()


@pytest.fixture
def property_tool():
    """Create GeneratePropertyTestsTool instance."""
    return GeneratePropertyTestsTool()


# ═══════════════════════════════════════════════════════════════════════════════
# Test Data Classes
# ═══════════════════════════════════════════════════════════════════════════════


class TestDataClasses:
    """Tests for dataclasses."""

    def test_parameter_info_creation(self):
        """Test ParameterInfo dataclass."""
        param = ParameterInfo(name="email", type_hint="str", default="None")
        assert param.name == "email"
        assert param.type_hint == "str"
        assert param.default == "None"
        assert param.is_optional is False

    def test_function_info_creation(self):
        """Test FunctionInfo dataclass."""
        func = FunctionInfo(
            name="validate",
            parameters=[ParameterInfo(name="x", type_hint="int")],
            return_type="bool",
            is_async=False,
        )
        assert func.name == "validate"
        assert len(func.parameters) == 1
        assert func.return_type == "bool"
        assert func.is_async is False

    def test_class_info_creation(self):
        """Test ClassInfo dataclass."""
        cls = ClassInfo(
            name="UserService",
            methods=[FunctionInfo(name="get_user")],
            base_classes=["BaseService"],
        )
        assert cls.name == "UserService"
        assert len(cls.methods) == 1
        assert cls.base_classes == ["BaseService"]

    def test_suggested_test_case_creation(self):
        """Test SuggestedTestCase dataclass."""
        suggestion = SuggestedTestCase(
            description="Test with empty string",
            category="edge_case",
            target="validate_email",
            priority="medium",
        )
        assert suggestion.description == "Test with empty string"
        assert suggestion.category == "edge_case"


# ═══════════════════════════════════════════════════════════════════════════════
# Test Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_extract_imports_python(self):
        """Test extracting imports from Python code."""
        code = """
from pathlib import Path
import requests
from typing import Optional
import json
"""
        imports = _extract_imports(code, "python")
        assert "pathlib" in imports
        assert "requests" in imports
        assert "typing" in imports
        assert "json" in imports

    def test_extract_imports_empty(self):
        """Test extracting imports from code with no imports."""
        code = "def foo(): pass"
        imports = _extract_imports(code, "python")
        assert imports == []

    def test_detect_patterns_file_operation(self):
        """Test detecting file operation patterns."""
        code = "with open(path) as f: data = f.read()"
        patterns = _detect_patterns(code)
        assert "file_operation" in patterns

    def test_detect_patterns_network(self):
        """Test detecting network patterns."""
        code = "response = requests.get(url)"
        patterns = _detect_patterns(code)
        assert "network_call" in patterns

    def test_detect_patterns_division(self):
        """Test detecting division patterns."""
        code = "result = a / b"
        patterns = _detect_patterns(code)
        assert "division" in patterns

    def test_detect_patterns_regex(self):
        """Test detecting regex patterns."""
        code = "match = re.search(pattern, text)"
        patterns = _detect_patterns(code)
        assert "regex" in patterns

    def test_detect_patterns_validation(self):
        """Test detecting validation patterns."""
        code = "def validate_input(data): return is_valid(data)"
        patterns = _detect_patterns(code)
        assert "validation" in patterns

    def test_detect_test_framework_pytest(self, tmp_path):
        """Test detecting pytest framework."""
        (tmp_path / "conftest.py").write_text("import pytest")
        framework = _detect_test_framework(tmp_path)
        assert framework == "pytest"

    def test_detect_test_framework_default(self, tmp_path):
        """Test default framework is pytest."""
        framework = _detect_test_framework(tmp_path)
        assert framework == "pytest"


# ═══════════════════════════════════════════════════════════════════════════════
# Test SuggestTestCasesTool
# ═══════════════════════════════════════════════════════════════════════════════


class TestSuggestTestCasesTool:
    """Tests for SuggestTestCasesTool."""

    def test_tool_metadata(self, suggest_tool):
        """Test tool name and description."""
        assert suggest_tool.name == "suggest_test_cases"
        assert "suggest" in suggest_tool.description.lower()

    @pytest.mark.asyncio
    async def test_suggest_file_not_found(self, suggest_tool):
        """Test handling of non-existent file."""
        result = await suggest_tool.execute(source_file="/nonexistent/file.py")
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_suggest_unsupported_file(self, suggest_tool, tmp_path):
        """Test handling of unsupported file type."""
        file_path = tmp_path / "file.xyz"
        file_path.write_text("content")
        result = await suggest_tool.execute(source_file=str(file_path))
        assert result.success is False
        assert "unsupported" in result.error.lower()

    @pytest.mark.asyncio
    async def test_suggest_basic(self, suggest_tool, temp_python_file):
        """Test basic suggestion generation."""
        result = await suggest_tool.execute(source_file=str(temp_python_file))
        assert result.success is True
        assert "validate_email" in result.output
        assert result.metadata["functions_analyzed"] > 0

    @pytest.mark.asyncio
    async def test_suggest_specific_target(self, suggest_tool, temp_python_file):
        """Test suggestion for specific function."""
        result = await suggest_tool.execute(
            source_file=str(temp_python_file), target="validate_email"
        )
        assert result.success is True
        assert "validate_email" in result.output
        # Should only analyze the target function
        assert result.metadata["functions_analyzed"] == 1

    @pytest.mark.asyncio
    async def test_suggest_target_not_found(self, suggest_tool, temp_python_file):
        """Test handling of non-existent target."""
        result = await suggest_tool.execute(
            source_file=str(temp_python_file), target="nonexistent_function"
        )
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_suggest_markdown_format(self, suggest_tool, temp_python_file):
        """Test markdown output format."""
        result = await suggest_tool.execute(
            source_file=str(temp_python_file), output_format="markdown"
        )
        assert result.success is True
        assert "# Test Suggestions" in result.output
        assert "## " in result.output  # Section headers
        assert "- [ ]" in result.output  # Checkboxes

    @pytest.mark.asyncio
    async def test_suggest_json_format(self, suggest_tool, temp_python_file):
        """Test JSON output format."""
        result = await suggest_tool.execute(
            source_file=str(temp_python_file), output_format="json"
        )
        assert result.success is True
        suggestions = json.loads(result.output)
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0
        assert "description" in suggestions[0]
        assert "category" in suggestions[0]

    @pytest.mark.asyncio
    async def test_suggest_text_format(self, suggest_tool, temp_python_file):
        """Test text output format."""
        result = await suggest_tool.execute(
            source_file=str(temp_python_file), output_format="text"
        )
        assert result.success is True
        assert "[BASIC]" in result.output or "[EDGE_CASE]" in result.output

    @pytest.mark.asyncio
    async def test_suggest_edge_cases(self, suggest_tool, temp_python_file):
        """Test edge case suggestions are included."""
        result = await suggest_tool.execute(
            source_file=str(temp_python_file),
            include_edge_cases=True,
            output_format="json",
        )
        assert result.success is True
        suggestions = json.loads(result.output)
        categories = [s["category"] for s in suggestions]
        assert "edge_case" in categories

    @pytest.mark.asyncio
    async def test_suggest_error_cases(self, suggest_tool, temp_python_with_patterns):
        """Test error case suggestions for patterns."""
        result = await suggest_tool.execute(
            source_file=str(temp_python_with_patterns),
            include_error_cases=True,
            output_format="json",
        )
        assert result.success is True
        suggestions = json.loads(result.output)
        categories = [s["category"] for s in suggestions]
        assert "error_case" in categories

    @pytest.mark.asyncio
    async def test_suggest_class_tests(self, suggest_tool, temp_python_file):
        """Test suggestions for classes."""
        result = await suggest_tool.execute(
            source_file=str(temp_python_file), target="UserService"
        )
        assert result.success is True
        assert "UserService" in result.output
        assert result.metadata["classes_analyzed"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Test GenerateUnitTestsTool
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateUnitTestsTool:
    """Tests for GenerateUnitTestsTool."""

    def test_tool_metadata(self, generate_tool):
        """Test tool name and description."""
        assert generate_tool.name == "generate_unit_tests"
        assert "generate" in generate_tool.description.lower()

    @pytest.mark.asyncio
    async def test_generate_file_not_found(self, generate_tool):
        """Test handling of non-existent file."""
        result = await generate_tool.execute(source_file="/nonexistent/file.py")
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_generate_basic(self, generate_tool, temp_python_file, tmp_path):
        """Test basic test generation."""
        output_file = tmp_path / "test_sample.py"
        result = await generate_tool.execute(
            source_file=str(temp_python_file), output_file=str(output_file)
        )
        assert result.success is True
        assert output_file.exists()
        content = output_file.read_text()
        assert "import pytest" in content
        assert "def test_" in content

    @pytest.mark.asyncio
    async def test_generate_dry_run(self, generate_tool, temp_python_file, tmp_path):
        """Test dry run mode."""
        output_file = tmp_path / "test_dry.py"
        result = await generate_tool.execute(
            source_file=str(temp_python_file),
            output_file=str(output_file),
            dry_run=True,
        )
        assert result.success is True
        assert "DRY RUN" in result.output
        assert not output_file.exists()  # File should not be created
        assert result.metadata["dry_run"] is True

    @pytest.mark.asyncio
    async def test_generate_specific_target(
        self, generate_tool, temp_python_file, tmp_path
    ):
        """Test generating tests for specific function."""
        result = await generate_tool.execute(
            source_file=str(temp_python_file), target="validate_email", dry_run=True
        )
        assert result.success is True
        assert "test_validate_email" in result.output
        assert result.metadata["functions_count"] == 1

    @pytest.mark.asyncio
    async def test_generate_target_not_found(self, generate_tool, temp_python_file):
        """Test handling of non-existent target."""
        result = await generate_tool.execute(
            source_file=str(temp_python_file), target="nonexistent_function"
        )
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_generate_async_function(
        self, generate_tool, temp_python_file, tmp_path
    ):
        """Test generation for async functions."""
        result = await generate_tool.execute(
            source_file=str(temp_python_file), target="fetch_data", dry_run=True
        )
        assert result.success is True
        assert "@pytest.mark.asyncio" in result.output
        assert "async def test_" in result.output

    @pytest.mark.asyncio
    async def test_generate_class_tests(
        self, generate_tool, temp_python_file, tmp_path
    ):
        """Test generation for classes."""
        result = await generate_tool.execute(
            source_file=str(temp_python_file), target="UserService", dry_run=True
        )
        assert result.success is True
        assert "class TestUserService" in result.output
        assert "@pytest.fixture" in result.output
        assert "def instance" in result.output

    @pytest.mark.asyncio
    async def test_generate_with_framework(
        self, generate_tool, temp_python_file, tmp_path
    ):
        """Test specifying framework."""
        result = await generate_tool.execute(
            source_file=str(temp_python_file), framework="pytest", dry_run=True
        )
        assert result.success is True
        assert result.metadata["framework"] == "pytest"

    @pytest.mark.asyncio
    async def test_generate_default_output_path(
        self, generate_tool, temp_python_file, tmp_path
    ):
        """Test default output path generation."""
        result = await generate_tool.execute(
            source_file=str(temp_python_file), dry_run=True
        )
        assert result.success is True
        assert "test_sample.py" in result.metadata["output_file"]


# ═══════════════════════════════════════════════════════════════════════════════
# Test GenerateTestFixturesTool
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateTestFixturesTool:
    """Tests for GenerateTestFixturesTool."""

    def test_tool_metadata(self, fixture_tool):
        """Test tool name and description."""
        assert fixture_tool.name == "generate_test_fixtures"
        assert "fixture" in fixture_tool.description.lower()

    @pytest.mark.asyncio
    async def test_fixtures_file_not_found(self, fixture_tool):
        """Test handling of non-existent file."""
        result = await fixture_tool.execute(source_file="/nonexistent/file.py")
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_fixtures_basic(self, fixture_tool, temp_python_file, tmp_path):
        """Test basic fixture generation."""
        output_file = tmp_path / "conftest.py"
        result = await fixture_tool.execute(
            source_file=str(temp_python_file), output_file=str(output_file)
        )
        assert result.success is True
        assert output_file.exists()
        content = output_file.read_text()
        assert "import pytest" in content
        assert "@pytest.fixture" in content

    @pytest.mark.asyncio
    async def test_fixtures_dry_run(self, fixture_tool, temp_python_file, tmp_path):
        """Test dry run mode."""
        output_file = tmp_path / "conftest.py"
        result = await fixture_tool.execute(
            source_file=str(temp_python_file),
            output_file=str(output_file),
            dry_run=True,
        )
        assert result.success is True
        assert "DRY RUN" in result.output
        assert not output_file.exists()

    @pytest.mark.asyncio
    async def test_fixtures_auto_detect_deps(self, fixture_tool, temp_python_file):
        """Test auto-detection of dependencies to mock."""
        result = await fixture_tool.execute(
            source_file=str(temp_python_file), dry_run=True
        )
        assert result.success is True
        # requests is in sample code, should be detected
        assert "requests" in result.metadata.get("dependencies_mocked", [])

    @pytest.mark.asyncio
    async def test_fixtures_specific_deps(self, fixture_tool, temp_python_file):
        """Test specifying dependencies to mock."""
        result = await fixture_tool.execute(
            source_file=str(temp_python_file),
            dependencies_to_mock=["requests", "httpx"],
            dry_run=True,
        )
        assert result.success is True
        assert "mock_requests" in result.output

    @pytest.mark.asyncio
    async def test_fixtures_scope(self, fixture_tool, temp_python_file):
        """Test fixture scope setting."""
        result = await fixture_tool.execute(
            source_file=str(temp_python_file), fixture_scope="module", dry_run=True
        )
        assert result.success is True
        assert result.metadata["fixture_scope"] == "module"

    @pytest.mark.asyncio
    async def test_fixtures_includes_data_fixtures(
        self, fixture_tool, temp_python_file
    ):
        """Test that data fixtures are included."""
        result = await fixture_tool.execute(
            source_file=str(temp_python_file), dry_run=True
        )
        assert result.success is True
        assert "sample_data" in result.output
        assert "temp_file" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# Test GeneratePropertyTestsTool
# ═══════════════════════════════════════════════════════════════════════════════


class TestGeneratePropertyTestsTool:
    """Tests for GeneratePropertyTestsTool."""

    def test_tool_metadata(self, property_tool):
        """Test tool name and description."""
        assert property_tool.name == "generate_property_tests"
        assert "property" in property_tool.description.lower()

    @pytest.mark.asyncio
    async def test_property_file_not_found(self, property_tool):
        """Test handling of non-existent file."""
        result = await property_tool.execute(
            source_file="/nonexistent/file.py", target="func"
        )
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_property_target_required(self, property_tool, temp_python_file):
        """Test that target is required."""
        # The schema requires target, so this should work with explicit target
        result = await property_tool.execute(
            source_file=str(temp_python_file), target="validate_email", dry_run=True
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_property_target_not_found(self, property_tool, temp_python_file):
        """Test handling of non-existent target."""
        result = await property_tool.execute(
            source_file=str(temp_python_file), target="nonexistent"
        )
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_property_basic(self, property_tool, temp_python_file, tmp_path):
        """Test basic property test generation."""
        output_file = tmp_path / "test_props.py"
        result = await property_tool.execute(
            source_file=str(temp_python_file),
            target="validate_email",
            output_file=str(output_file),
        )
        assert result.success is True
        assert output_file.exists()
        content = output_file.read_text()
        assert "hypothesis" in content
        assert "@given" in content

    @pytest.mark.asyncio
    async def test_property_dry_run(self, property_tool, temp_python_file):
        """Test dry run mode."""
        result = await property_tool.execute(
            source_file=str(temp_python_file), target="validate_email", dry_run=True
        )
        assert result.success is True
        assert "DRY RUN" in result.output
        assert result.metadata["dry_run"] is True

    @pytest.mark.asyncio
    async def test_property_max_examples(self, property_tool, temp_python_file):
        """Test max_examples setting."""
        result = await property_tool.execute(
            source_file=str(temp_python_file),
            target="validate_email",
            max_examples=200,
            dry_run=True,
        )
        assert result.success is True
        assert "max_examples=200" in result.output
        assert result.metadata["max_examples"] == 200

    @pytest.mark.asyncio
    async def test_property_roundtrip(self, property_tool, temp_python_file):
        """Test roundtrip property generation."""
        result = await property_tool.execute(
            source_file=str(temp_python_file),
            target="validate_email",
            properties_to_test=["roundtrip"],
            dry_run=True,
        )
        assert result.success is True
        assert "roundtrip" in result.output.lower()

    @pytest.mark.asyncio
    async def test_property_idempotent(self, property_tool, temp_python_file):
        """Test idempotent property generation."""
        result = await property_tool.execute(
            source_file=str(temp_python_file),
            target="validate_email",
            properties_to_test=["idempotent"],
            dry_run=True,
        )
        assert result.success is True
        assert "idempotent" in result.output.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Test Tool Registration
# ═══════════════════════════════════════════════════════════════════════════════


class TestToolRegistration:
    """Tests for tool registration."""

    def test_tools_in_registry(self):
        """Test that all tools are registered."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()

        assert registry.get_tool("suggest_test_cases") is not None
        assert registry.get_tool("generate_unit_tests") is not None
        assert registry.get_tool("generate_test_fixtures") is not None
        assert registry.get_tool("generate_property_tests") is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Test Agent Integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentIntegration:
    """Tests for agent integration."""

    def test_skald_has_test_generation_tools(self):
        """Test that Skald agent has test generation tools."""
        from sindri.agents.registry import AGENTS

        skald = AGENTS.get("skald")
        assert skald is not None

        # Check for new test generation tools
        assert "suggest_test_cases" in skald.tools
        assert "generate_unit_tests" in skald.tools
        assert "generate_test_fixtures" in skald.tools
        assert "generate_property_tests" in skald.tools

    def test_skald_still_has_original_tools(self):
        """Test that Skald still has its original tools."""
        from sindri.agents.registry import AGENTS

        skald = AGENTS.get("skald")
        assert skald is not None

        # Original tools should still be present
        assert "read_file" in skald.tools
        assert "write_file" in skald.tools
        assert "run_tests" in skald.tools
        assert "check_syntax" in skald.tools
        assert "shell" in skald.tools
