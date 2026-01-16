"""Tests for HTTP request tools."""

import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from sindri.tools.http import HttpRequestTool, HttpGetTool, HttpPostTool


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_response():
    """Create a mock httpx Response."""
    response = MagicMock()
    response.status_code = 200
    response.reason_phrase = "OK"
    response.headers = {
        "content-type": "application/json",
        "content-length": "100",
        "date": "Mon, 15 Jan 2026 12:00:00 GMT",
        "server": "TestServer"
    }
    response.url = "https://api.example.com/test"
    response.text = '{"message": "success", "data": [1, 2, 3]}'
    response.content = b'{"message": "success", "data": [1, 2, 3]}'
    response.json.return_value = {"message": "success", "data": [1, 2, 3]}
    response.elapsed = MagicMock()
    response.elapsed.total_seconds.return_value = 0.5
    response.is_redirect = False
    response.is_success = True
    response.is_error = False
    return response


@pytest.fixture
def mock_error_response():
    """Create a mock error response."""
    response = MagicMock()
    response.status_code = 404
    response.reason_phrase = "Not Found"
    response.headers = {"content-type": "text/plain"}
    response.url = "https://api.example.com/notfound"
    response.text = "Resource not found"
    response.content = b"Resource not found"
    response.elapsed = MagicMock()
    response.elapsed.total_seconds.return_value = 0.1
    response.is_redirect = False
    response.is_success = False
    response.is_error = True
    return response


# =============================================================================
# HttpRequestTool Tests - Basic Functionality
# =============================================================================

@pytest.mark.asyncio
async def test_http_request_get_basic(mock_response):
    """Test basic GET request."""
    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(url="https://api.example.com/test")

        assert result.success is True
        assert "200" in result.output
        assert "success" in result.output
        assert result.metadata["status_code"] == 200


@pytest.mark.asyncio
async def test_http_request_post_with_json(mock_response):
    """Test POST request with JSON body."""
    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(
            url="https://api.example.com/data",
            method="POST",
            json={"key": "value"}
        )

        assert result.success is True
        mock_client_instance.request.assert_called_once()
        call_kwargs = mock_client_instance.request.call_args[1]
        assert call_kwargs.get("json") == {"key": "value"}


@pytest.mark.asyncio
async def test_http_request_with_headers(mock_response):
    """Test request with custom headers."""
    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(
            url="https://api.example.com/test",
            headers={"Authorization": "Bearer token123"}
        )

        assert result.success is True
        call_kwargs = mock_client_instance.request.call_args[1]
        assert call_kwargs.get("headers") == {"Authorization": "Bearer token123"}


@pytest.mark.asyncio
async def test_http_request_with_params(mock_response):
    """Test request with query parameters."""
    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(
            url="https://api.example.com/search",
            params={"q": "test", "page": "1"}
        )

        assert result.success is True
        call_kwargs = mock_client_instance.request.call_args[1]
        assert call_kwargs.get("params") == {"q": "test", "page": "1"}


# =============================================================================
# HttpRequestTool Tests - HTTP Methods
# =============================================================================

@pytest.mark.asyncio
async def test_http_request_put_method(mock_response):
    """Test PUT request."""
    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(
            url="https://api.example.com/resource/1",
            method="PUT",
            json={"updated": True}
        )

        assert result.success is True
        mock_client_instance.request.assert_called_with(
            "PUT", "https://api.example.com/resource/1",
            json={"updated": True}
        )


@pytest.mark.asyncio
async def test_http_request_patch_method(mock_response):
    """Test PATCH request."""
    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(
            url="https://api.example.com/resource/1",
            method="PATCH",
            json={"field": "new_value"}
        )

        assert result.success is True


@pytest.mark.asyncio
async def test_http_request_delete_method(mock_response):
    """Test DELETE request."""
    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(
            url="https://api.example.com/resource/1",
            method="DELETE"
        )

        assert result.success is True


@pytest.mark.asyncio
async def test_http_request_head_method(mock_response):
    """Test HEAD request."""
    tool = HttpRequestTool()
    mock_response.text = ""

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(
            url="https://api.example.com/resource",
            method="HEAD"
        )

        assert result.success is True


# =============================================================================
# HttpRequestTool Tests - Validation
# =============================================================================

@pytest.mark.asyncio
async def test_http_request_empty_url_error():
    """Test that empty URL returns error."""
    tool = HttpRequestTool()
    result = await tool.execute(url="")

    assert result.success is False
    assert "cannot be empty" in result.error.lower()


@pytest.mark.asyncio
async def test_http_request_invalid_method_error():
    """Test that invalid method returns error."""
    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient"):
        result = await tool.execute(url="https://api.example.com", method="INVALID")

    assert result.success is False
    assert "invalid" in result.error.lower()


@pytest.mark.asyncio
async def test_http_request_adds_https_prefix():
    """Test that URLs without scheme get https:// added."""
    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.reason_phrase = "OK"
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.url = "https://api.example.com"
        mock_response.text = "OK"
        mock_response.content = b"OK"
        mock_response.elapsed = MagicMock()
        mock_response.elapsed.total_seconds.return_value = 0.1
        mock_response.is_redirect = False
        mock_response.is_success = True
        mock_response.is_error = False
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(url="api.example.com/test")

        assert result.success is True
        # Should have added https://
        call_args = mock_client_instance.request.call_args
        assert call_args[0][1].startswith("https://")


# =============================================================================
# HttpRequestTool Tests - Security
# =============================================================================

@pytest.mark.asyncio
async def test_http_request_blocks_localhost():
    """Test that localhost requests are blocked by default."""
    tool = HttpRequestTool(allow_localhost=False)
    result = await tool.execute(url="http://localhost:8080/api")

    assert result.success is False
    assert "blocked" in result.error.lower()


@pytest.mark.asyncio
async def test_http_request_blocks_127001():
    """Test that 127.0.0.1 requests are blocked."""
    tool = HttpRequestTool(allow_localhost=False)
    result = await tool.execute(url="http://127.0.0.1:8080/api")

    assert result.success is False
    assert "blocked" in result.error.lower()


@pytest.mark.asyncio
async def test_http_request_blocks_metadata_ip():
    """Test that cloud metadata IP is blocked."""
    tool = HttpRequestTool(allow_localhost=False)
    result = await tool.execute(url="http://169.254.169.254/latest/meta-data")

    assert result.success is False
    assert "blocked" in result.error.lower()


@pytest.mark.asyncio
async def test_http_request_allows_localhost_when_enabled(mock_response):
    """Test that localhost is allowed when allow_localhost=True."""
    tool = HttpRequestTool(allow_localhost=True)

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(url="http://localhost:8080/api")

        assert result.success is True


# =============================================================================
# HttpRequestTool Tests - Error Handling
# =============================================================================

@pytest.mark.asyncio
async def test_http_request_timeout_error():
    """Test timeout error handling."""
    import httpx as real_httpx

    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.side_effect = real_httpx.TimeoutException("Request timed out")
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(url="https://api.example.com/slow", timeout=5)

        assert result.success is False
        assert "timed out" in result.error.lower()


@pytest.mark.asyncio
async def test_http_request_connection_error():
    """Test connection error handling."""
    import httpx as real_httpx

    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.side_effect = real_httpx.ConnectError("Connection refused")
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(url="https://api.example.com/down")

        assert result.success is False
        assert "connection" in result.error.lower()


@pytest.mark.asyncio
async def test_http_request_error_response(mock_error_response):
    """Test handling of error HTTP responses."""
    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_error_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(url="https://api.example.com/notfound")

        # Should still succeed (as a tool execution) but show 404
        assert result.success is True
        assert "404" in result.output
        assert result.metadata["status_code"] == 404


# =============================================================================
# HttpRequestTool Tests - Response Handling
# =============================================================================

@pytest.mark.asyncio
async def test_http_request_json_response_formatting(mock_response):
    """Test that JSON responses are formatted nicely."""
    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(url="https://api.example.com/json")

        assert result.success is True
        assert result.metadata.get("is_json") is True
        # JSON should be formatted with indentation
        assert "message" in result.output


@pytest.mark.asyncio
async def test_http_request_metadata_includes_timing(mock_response):
    """Test that response metadata includes timing info."""
    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(url="https://api.example.com/test")

        assert result.success is True
        assert "elapsed_ms" in result.metadata
        assert result.metadata["elapsed_ms"] == 500  # 0.5 seconds = 500ms


# =============================================================================
# HttpGetTool Tests
# =============================================================================

@pytest.mark.asyncio
async def test_http_get_basic(mock_response):
    """Test HttpGetTool basic usage."""
    tool = HttpGetTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(url="https://api.example.com/users")

        assert result.success is True
        mock_client_instance.request.assert_called_once()
        call_args = mock_client_instance.request.call_args
        assert call_args[0][0] == "GET"


@pytest.mark.asyncio
async def test_http_get_with_headers(mock_response):
    """Test HttpGetTool with headers."""
    tool = HttpGetTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(
            url="https://api.example.com/users",
            headers={"Accept": "application/json"}
        )

        assert result.success is True


# =============================================================================
# HttpPostTool Tests
# =============================================================================

@pytest.mark.asyncio
async def test_http_post_basic(mock_response):
    """Test HttpPostTool basic usage."""
    tool = HttpPostTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(
            url="https://api.example.com/data",
            json={"name": "test"}
        )

        assert result.success is True
        call_args = mock_client_instance.request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[1].get("json") == {"name": "test"}


@pytest.mark.asyncio
async def test_http_post_with_headers(mock_response):
    """Test HttpPostTool with custom headers."""
    tool = HttpPostTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(
            url="https://api.example.com/data",
            json={"name": "test"},
            headers={"X-Custom": "header"}
        )

        assert result.success is True


# =============================================================================
# Tool Registry Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_http_tools_in_registry():
    """Test that HTTP tools are properly registered."""
    from sindri.tools.registry import ToolRegistry

    registry = ToolRegistry.default()

    assert registry.get_tool("http_request") is not None
    assert registry.get_tool("http_get") is not None
    assert registry.get_tool("http_post") is not None


@pytest.mark.asyncio
async def test_http_request_schema():
    """Test HttpRequestTool schema format."""
    tool = HttpRequestTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "http_request"
    assert "parameters" in schema["function"]
    assert "url" in schema["function"]["parameters"]["properties"]
    assert "url" in schema["function"]["parameters"]["required"]


@pytest.mark.asyncio
async def test_http_get_schema():
    """Test HttpGetTool schema format."""
    tool = HttpGetTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "http_get"


@pytest.mark.asyncio
async def test_http_post_schema():
    """Test HttpPostTool schema format."""
    tool = HttpPostTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "http_post"


# =============================================================================
# Agent Integration Tests
# =============================================================================

def test_agents_have_http_request():
    """Test that appropriate agents have http_request tool."""
    from sindri.agents.registry import AGENTS

    # Brokkr should have http_request
    assert "http_request" in AGENTS["brokkr"].tools

    # Huginn should have http_request
    assert "http_request" in AGENTS["huginn"].tools

    # Skald should have http_request (for API testing)
    assert "http_request" in AGENTS["skald"].tools

    # Fenrir should have http_request (for data fetching)
    assert "http_request" in AGENTS["fenrir"].tools


# =============================================================================
# Edge Cases
# =============================================================================

@pytest.mark.asyncio
async def test_http_request_with_raw_data(mock_response):
    """Test POST request with raw data body."""
    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(
            url="https://api.example.com/raw",
            method="POST",
            data="raw body content"
        )

        assert result.success is True
        call_kwargs = mock_client_instance.request.call_args[1]
        assert call_kwargs.get("content") == "raw body content"


@pytest.mark.asyncio
async def test_http_request_large_response_truncated():
    """Test that large responses are truncated."""
    tool = HttpRequestTool()
    # Reduce max size for testing
    tool.MAX_RESPONSE_SIZE = 100

    large_response = MagicMock()
    large_response.status_code = 200
    large_response.reason_phrase = "OK"
    large_response.headers = {"content-type": "text/plain", "content-length": "50"}
    large_response.url = "https://api.example.com/large"
    large_response.text = "x" * 200  # Larger than MAX_RESPONSE_SIZE
    large_response.content = b"x" * 200
    large_response.elapsed = MagicMock()
    large_response.elapsed.total_seconds.return_value = 0.1
    large_response.is_redirect = False
    large_response.is_success = True
    large_response.is_error = False

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = large_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(url="https://api.example.com/large")

        assert result.success is True
        assert "truncated" in result.output.lower() or len(result.output) <= 200


@pytest.mark.asyncio
async def test_http_request_follow_redirects_disabled(mock_response):
    """Test request with follow_redirects disabled."""
    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(
            url="https://api.example.com/redirect",
            follow_redirects=False
        )

        assert result.success is True
        # Check that follow_redirects was passed to client
        mock_client.assert_called_with(timeout=30.0, follow_redirects=False)


@pytest.mark.asyncio
async def test_http_request_custom_timeout(mock_response):
    """Test request with custom timeout."""
    tool = HttpRequestTool()

    with patch("sindri.tools.http.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await tool.execute(
            url="https://api.example.com/slow",
            timeout=60
        )

        assert result.success is True
        mock_client.assert_called_with(timeout=60, follow_redirects=True)
