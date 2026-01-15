"""Tests for tool execution retry functionality."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from sindri.tools.base import Tool, ToolResult
from sindri.tools.registry import ToolRegistry, ToolRetryConfig
from sindri.core.errors import ErrorCategory


class MockTool(Tool):
    """Mock tool for testing."""

    name = "mock_tool"
    description = "A mock tool for testing"
    parameters = {"type": "object", "properties": {}}

    def __init__(self, results=None, exceptions=None):
        """Initialize with sequence of results or exceptions to return."""
        super().__init__()
        self.results = results or []
        self.exceptions = exceptions or []
        self.call_count = 0

    async def execute(self, **kwargs) -> ToolResult:
        """Return next result or raise next exception."""
        idx = self.call_count
        self.call_count += 1

        if self.exceptions and idx < len(self.exceptions):
            if self.exceptions[idx]:
                raise self.exceptions[idx]

        if self.results and idx < len(self.results):
            return self.results[idx]

        return ToolResult(success=True, output="default success")


class TestToolRetryConfig:
    """Test ToolRetryConfig dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = ToolRetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay == 0.5
        assert config.max_delay == 5.0
        assert config.exponential_base == 2.0

    def test_custom_values(self):
        """Should accept custom values."""
        config = ToolRetryConfig(
            max_attempts=5,
            base_delay=1.0,
            max_delay=10.0,
            exponential_base=3.0
        )
        assert config.max_attempts == 5
        assert config.base_delay == 1.0


class TestToolRegistryRetry:
    """Test retry behavior in ToolRegistry."""

    @pytest.fixture
    def fast_retry_config(self):
        """Fast retry config for testing (no real delays)."""
        return ToolRetryConfig(
            max_attempts=3,
            base_delay=0.001,  # 1ms for fast tests
            max_delay=0.01,
            exponential_base=2.0
        )

    @pytest.mark.asyncio
    async def test_success_on_first_try(self, fast_retry_config):
        """Should return immediately on success."""
        tool = MockTool(results=[
            ToolResult(success=True, output="success")
        ])
        registry = ToolRegistry(retry_config=fast_retry_config)
        registry.register(tool)

        result = await registry.execute("mock_tool", {})

        assert result.success is True
        assert result.output == "success"
        assert result.retries_attempted == 0
        assert tool.call_count == 1

    @pytest.mark.asyncio
    async def test_fatal_error_no_retry(self, fast_retry_config):
        """Should not retry on fatal errors."""
        tool = MockTool(results=[
            ToolResult(success=False, output="", error="File not found: missing.txt")
        ])
        registry = ToolRegistry(retry_config=fast_retry_config)
        registry.register(tool)

        result = await registry.execute("mock_tool", {})

        assert result.success is False
        assert result.error_category == ErrorCategory.FATAL
        assert "list_directory" in result.suggestion
        assert tool.call_count == 1  # No retry

    @pytest.mark.asyncio
    async def test_transient_error_retries(self, fast_retry_config):
        """Should retry on transient errors."""
        tool = MockTool(results=[
            ToolResult(success=False, output="", error="Connection refused"),
            ToolResult(success=False, output="", error="Connection refused"),
            ToolResult(success=True, output="success after retries")
        ])
        registry = ToolRegistry(retry_config=fast_retry_config)
        registry.register(tool)

        result = await registry.execute("mock_tool", {})

        assert result.success is True
        assert result.output == "success after retries"
        assert result.retries_attempted == 2
        assert tool.call_count == 3

    @pytest.mark.asyncio
    async def test_exhausted_retries(self, fast_retry_config):
        """Should return failure after exhausting retries."""
        tool = MockTool(results=[
            ToolResult(success=False, output="", error="Connection refused"),
            ToolResult(success=False, output="", error="Connection refused"),
            ToolResult(success=False, output="", error="Connection refused"),
        ])
        registry = ToolRegistry(retry_config=fast_retry_config)
        registry.register(tool)

        result = await registry.execute("mock_tool", {})

        assert result.success is False
        assert "Connection refused" in result.error
        assert result.error_category == ErrorCategory.TRANSIENT
        assert tool.call_count == 3

    @pytest.mark.asyncio
    async def test_exception_fatal_no_retry(self, fast_retry_config):
        """Should not retry fatal exceptions."""
        tool = MockTool(exceptions=[
            FileNotFoundError("No such file")
        ])
        registry = ToolRegistry(retry_config=fast_retry_config)
        registry.register(tool)

        result = await registry.execute("mock_tool", {})

        assert result.success is False
        assert result.error_category == ErrorCategory.FATAL
        assert tool.call_count == 1

    @pytest.mark.asyncio
    async def test_exception_transient_retries(self, fast_retry_config):
        """Should retry on transient exceptions."""
        tool = MockTool(exceptions=[
            ConnectionError("Connection failed"),
            ConnectionError("Connection failed"),
            None  # Success on third try
        ], results=[
            None, None,
            ToolResult(success=True, output="recovered")
        ])
        registry = ToolRegistry(retry_config=fast_retry_config)
        registry.register(tool)

        result = await registry.execute("mock_tool", {})

        assert result.success is True
        assert result.output == "recovered"
        assert tool.call_count == 3

    @pytest.mark.asyncio
    async def test_tool_not_found(self, fast_retry_config):
        """Should return error for unknown tool."""
        registry = ToolRegistry(retry_config=fast_retry_config)

        result = await registry.execute("unknown_tool", {})

        assert result.success is False
        assert "not found" in result.error
        assert result.error_category == ErrorCategory.FATAL

    @pytest.mark.asyncio
    async def test_invalid_json_arguments(self, fast_retry_config):
        """Should return error for invalid JSON arguments."""
        tool = MockTool()
        registry = ToolRegistry(retry_config=fast_retry_config)
        registry.register(tool)

        result = await registry.execute("mock_tool", "invalid json {")

        assert result.success is False
        assert "parse" in result.error.lower()
        assert result.error_category == ErrorCategory.FATAL

    @pytest.mark.asyncio
    async def test_retry_count_tracking(self, fast_retry_config):
        """Should track number of retries attempted."""
        tool = MockTool(results=[
            ToolResult(success=False, output="", error="timeout"),
            ToolResult(success=True, output="success")
        ])
        registry = ToolRegistry(retry_config=fast_retry_config)
        registry.register(tool)

        result = await registry.execute("mock_tool", {})

        assert result.retries_attempted == 1
        assert tool.call_count == 2

    @pytest.mark.asyncio
    async def test_error_category_set(self, fast_retry_config):
        """Should set error category on failed results."""
        tool = MockTool(results=[
            ToolResult(success=False, output="", error="Permission denied: /etc/shadow")
        ])
        registry = ToolRegistry(retry_config=fast_retry_config)
        registry.register(tool)

        result = await registry.execute("mock_tool", {})

        assert result.error_category == ErrorCategory.FATAL
        assert result.suggestion is not None

    @pytest.mark.asyncio
    async def test_suggestion_set(self, fast_retry_config):
        """Should set suggestion for known error patterns."""
        tool = MockTool(results=[
            ToolResult(success=False, output="", error="No such file: config.yaml")
        ])
        registry = ToolRegistry(retry_config=fast_retry_config)
        registry.register(tool)

        result = await registry.execute("mock_tool", {})

        assert result.suggestion is not None
        assert "list_directory" in result.suggestion


class TestToolRegistryDefaultBehavior:
    """Test default ToolRegistry behavior is preserved."""

    @pytest.mark.asyncio
    async def test_default_registry_works(self, tmp_path):
        """Default registry should work without retry config."""
        registry = ToolRegistry.default(work_dir=tmp_path)

        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")

        # Read it
        result = await registry.execute("read_file", {"path": str(test_file)})

        assert result.success is True
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_default_registry_error_handling(self, tmp_path):
        """Default registry should classify errors properly."""
        registry = ToolRegistry.default(work_dir=tmp_path)

        result = await registry.execute("read_file", {"path": "/nonexistent/file.txt"})

        assert result.success is False
        assert result.error_category == ErrorCategory.FATAL
        assert result.suggestion is not None
