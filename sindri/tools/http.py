"""HTTP request tools for Sindri."""

import json
from pathlib import Path
from typing import Optional, Any
from urllib.parse import urlparse
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()

# Try to import httpx, fall back gracefully if not available
try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


class HttpRequestTool(Tool):
    """Make HTTP requests to APIs and web services.

    Supports GET, POST, PUT, PATCH, DELETE methods with
    headers, query parameters, and request bodies.
    """

    name = "http_request"
    description = """Make HTTP requests to APIs and web services.

Examples:
- http_request(url="https://api.github.com/users/octocat") - GET request
- http_request(url="https://api.example.com/data", method="POST", json={"key": "value"})
- http_request(url="https://api.example.com/resource", headers={"Authorization": "Bearer token"})
- http_request(url="https://httpbin.org/get", params={"foo": "bar"}) - With query params"""

    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to request"},
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
                "description": "HTTP method (default: GET)",
            },
            "headers": {
                "type": "object",
                "description": "Request headers as key-value pairs",
            },
            "params": {
                "type": "object",
                "description": "Query parameters as key-value pairs",
            },
            "json": {
                "type": "object",
                "description": "JSON body for POST/PUT/PATCH requests",
            },
            "data": {
                "type": "string",
                "description": "Raw body data for POST/PUT/PATCH requests",
            },
            "timeout": {
                "type": "number",
                "description": "Request timeout in seconds (default: 30)",
            },
            "follow_redirects": {
                "type": "boolean",
                "description": "Follow HTTP redirects (default: true)",
            },
        },
        "required": ["url"],
    }

    # Default timeout in seconds
    DEFAULT_TIMEOUT = 30.0

    # Maximum response size to return (to prevent memory issues)
    MAX_RESPONSE_SIZE = 1024 * 1024  # 1MB

    # Blocked hosts for security
    BLOCKED_HOSTS = {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "metadata.google.internal",  # GCP metadata
        "169.254.169.254",  # AWS/cloud metadata
    }

    def __init__(self, work_dir: Optional[Path] = None, allow_localhost: bool = False):
        """Initialize HTTP request tool.

        Args:
            work_dir: Working directory (not used, for API consistency)
            allow_localhost: Allow requests to localhost (default: False for security)
        """
        super().__init__(work_dir)
        self.allow_localhost = allow_localhost

    def _is_blocked_host(self, url: str) -> bool:
        """Check if the URL host is blocked for security."""
        if self.allow_localhost:
            return False

        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""

            # Check against blocked hosts
            if host.lower() in self.BLOCKED_HOSTS:
                return True

            # Block private IP ranges (basic check)
            if host.startswith("10.") or host.startswith("192.168."):
                return True
            if host.startswith("172."):
                parts = host.split(".")
                if len(parts) >= 2:
                    try:
                        second_octet = int(parts[1])
                        if 16 <= second_octet <= 31:
                            return True
                    except ValueError:
                        pass

            return False
        except Exception:
            return False

    async def execute(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, str]] = None,
        json: Optional[dict[str, Any]] = None,
        data: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        follow_redirects: bool = True,
        **kwargs,
    ) -> ToolResult:
        """Execute HTTP request.

        Args:
            url: The URL to request
            method: HTTP method (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS)
            headers: Request headers
            params: Query parameters
            json: JSON body (for POST/PUT/PATCH)
            data: Raw body data (for POST/PUT/PATCH)
            timeout: Request timeout in seconds
            follow_redirects: Follow redirects
        """
        if not HTTPX_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="httpx library not installed. Install with: pip install httpx",
            )

        # Validate URL
        if not url or not url.strip():
            return ToolResult(success=False, output="", error="URL cannot be empty")

        # Ensure URL has scheme
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Security check
        if self._is_blocked_host(url):
            return ToolResult(
                success=False,
                output="",
                error="Requests to this host are blocked for security reasons",
            )

        # Validate method
        method = method.upper()
        if method not in ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]:
            return ToolResult(
                success=False, output="", error=f"Invalid HTTP method: {method}"
            )

        # Validate timeout
        if timeout <= 0:
            timeout = self.DEFAULT_TIMEOUT
        if timeout > 300:  # Max 5 minutes
            timeout = 300

        log.info(
            "http_request_execute",
            url=url,
            method=method,
            has_headers=bool(headers),
            has_params=bool(params),
            has_json=bool(json),
            has_data=bool(data),
        )

        try:
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=follow_redirects
            ) as client:
                # Build request kwargs
                request_kwargs: dict[str, Any] = {}

                if headers:
                    request_kwargs["headers"] = headers

                if params:
                    request_kwargs["params"] = params

                if json is not None and method in ["POST", "PUT", "PATCH"]:
                    request_kwargs["json"] = json
                elif data is not None and method in ["POST", "PUT", "PATCH"]:
                    request_kwargs["content"] = data

                # Make the request
                response = await client.request(method, url, **request_kwargs)

                # Build response metadata
                metadata = {
                    "status_code": response.status_code,
                    "reason": response.reason_phrase,
                    "headers": dict(response.headers),
                    "url": str(response.url),
                    "method": method,
                    "elapsed_ms": (
                        response.elapsed.total_seconds() * 1000
                        if response.elapsed
                        else None
                    ),
                    "is_redirect": response.is_redirect,
                    "is_success": response.is_success,
                    "is_error": response.is_error,
                }

                # Get response content
                content_type = response.headers.get("content-type", "")
                content_length = int(response.headers.get("content-length", 0))

                # Check response size
                if content_length > self.MAX_RESPONSE_SIZE:
                    return ToolResult(
                        success=True,
                        output=f"Response too large ({content_length} bytes). Headers and status returned in metadata.",
                        metadata=metadata,
                    )

                # Try to get response body
                try:
                    body = response.text
                    if len(body) > self.MAX_RESPONSE_SIZE:
                        body = body[: self.MAX_RESPONSE_SIZE] + "\n... (truncated)"
                        metadata["truncated"] = True
                except Exception:
                    body = f"[Binary content, {len(response.content)} bytes]"
                    metadata["is_binary"] = True

                # Try to parse as JSON for better formatting
                if "application/json" in content_type:
                    try:
                        json_body = response.json()
                        body = self._format_json(json_body)
                        metadata["is_json"] = True
                    except Exception:
                        pass  # Keep raw text

                # Format output
                output_parts = [
                    f"HTTP {response.status_code} {response.reason_phrase}",
                    f"URL: {response.url}",
                    "",
                ]

                # Add selected headers to output
                important_headers = ["content-type", "content-length", "date", "server"]
                for header in important_headers:
                    if header in response.headers:
                        output_parts.append(f"{header}: {response.headers[header]}")

                output_parts.extend(["", "--- Response Body ---", body])

                return ToolResult(
                    success=True, output="\n".join(output_parts), metadata=metadata
                )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                output="",
                error=f"Request timed out after {timeout} seconds",
                metadata={"timeout": timeout, "url": url},
            )
        except httpx.ConnectError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Connection failed: {str(e)}",
                metadata={"url": url},
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"HTTP error: {e.response.status_code} {e.response.reason_phrase}",
                metadata={"status_code": e.response.status_code, "url": url},
            )
        except Exception as e:
            log.error("http_request_failed", url=url, error=str(e))
            return ToolResult(
                success=False, output="", error=f"Request failed: {str(e)}"
            )

    def _format_json(self, data: Any, indent: int = 2) -> str:
        """Format JSON data for readable output."""
        try:
            return json.dumps(data, indent=indent, ensure_ascii=False)
        except Exception:
            return str(data)


class HttpGetTool(Tool):
    """Simplified GET request tool for quick API calls."""

    name = "http_get"
    description = """Make a simple HTTP GET request. For more options use http_request.

Examples:
- http_get(url="https://api.github.com/users/octocat")
- http_get(url="https://jsonplaceholder.typicode.com/posts/1")"""

    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to request"},
            "headers": {"type": "object", "description": "Optional request headers"},
        },
        "required": ["url"],
    }

    def __init__(self, work_dir: Optional[Path] = None):
        """Initialize HTTP GET tool."""
        super().__init__(work_dir)
        self._http_tool = HttpRequestTool(work_dir)

    async def execute(
        self, url: str, headers: Optional[dict[str, str]] = None, **kwargs
    ) -> ToolResult:
        """Execute HTTP GET request."""
        return await self._http_tool.execute(url=url, method="GET", headers=headers)


class HttpPostTool(Tool):
    """Simplified POST request tool for API submissions."""

    name = "http_post"
    description = """Make a simple HTTP POST request with JSON body.

Examples:
- http_post(url="https://api.example.com/data", json={"name": "test"})
- http_post(url="https://httpbin.org/post", json={"key": "value"})"""

    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to request"},
            "json": {"type": "object", "description": "JSON body to send"},
            "headers": {"type": "object", "description": "Optional request headers"},
        },
        "required": ["url"],
    }

    def __init__(self, work_dir: Optional[Path] = None):
        """Initialize HTTP POST tool."""
        super().__init__(work_dir)
        self._http_tool = HttpRequestTool(work_dir)

    async def execute(
        self,
        url: str,
        json: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        **kwargs,
    ) -> ToolResult:
        """Execute HTTP POST request."""
        return await self._http_tool.execute(
            url=url, method="POST", json=json, headers=headers
        )
