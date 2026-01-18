"""Web scraping tool for Sindri (lightweight, no browser required)."""

import re
from typing import Any, Optional
from urllib.parse import urlparse

import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()

# Try to import httpx (should be available as dev dependency)
try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

# Try to import html2text for markdown conversion
try:
    import html2text

    HTML2TEXT_AVAILABLE = True
except ImportError:
    HTML2TEXT_AVAILABLE = False


# Security: Blocked hosts and private IP ranges
BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
    "169.254.169.254",
}


def _is_private_ip(ip: str) -> bool:
    """Check if an IP address is in a private range."""
    try:
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        octets = [int(p) for p in parts]
        # 10.0.0.0/8
        if octets[0] == 10:
            return True
        # 172.16.0.0/12
        if octets[0] == 172 and 16 <= octets[1] <= 31:
            return True
        # 192.168.0.0/16
        if octets[0] == 192 and octets[1] == 168:
            return True
        # 127.0.0.0/8 (loopback)
        if octets[0] == 127:
            return True
        return False
    except (ValueError, IndexError):
        return False


def _is_blocked_url(url: str, allow_localhost: bool = False) -> bool:
    """Check if a URL should be blocked for security."""
    if allow_localhost:
        return False
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        host_lower = host.lower()
        if host_lower in BLOCKED_HOSTS:
            return True
        if _is_private_ip(host):
            return True
        # Block file:// protocol
        if parsed.scheme == "file":
            return True
        return False
    except Exception:
        return True  # Block on parse error


def _extract_by_selector(html: str, selector: str) -> Optional[str]:
    """Simple CSS selector extraction using regex patterns.

    Supports basic selectors: tag, .class, #id, tag.class, tag#id
    """
    # Parse selector
    tag_match = re.match(r"^(\w+)?", selector)
    class_match = re.search(r"\.([a-zA-Z_-][\w-]*)", selector)
    id_match = re.search(r"#([a-zA-Z_-][\w-]*)", selector)

    tag = tag_match.group(1) if tag_match and tag_match.group(1) else r"\w+"

    # Build pattern
    if id_match:
        # ID selector - find element with id attribute
        id_val = id_match.group(1)
        pattern = rf"<{tag}[^>]*\bid=['\"]?{re.escape(id_val)}['\"]?[^>]*>(.*?)</{tag}>"
    elif class_match:
        # Class selector - find element with class attribute containing the class
        class_val = class_match.group(1)
        pattern = rf"<{tag}[^>]*\bclass=['\"][^'\"]*\b{re.escape(class_val)}\b[^'\"]*['\"][^>]*>(.*?)</{tag}>"
    else:
        # Tag-only selector
        pattern = rf"<{tag}[^>]*>(.*?)</{tag}>"

    match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _html_to_text(html: str) -> str:
    """Convert HTML to plain text."""
    # Remove script and style tags
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Clean up whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class WebScrapeTool(Tool):
    """Scrape web page content to markdown or JSON."""

    name = "web_scrape"
    description = """Scrape a URL and convert to markdown or extract structured data.

This is a lightweight alternative to browser tools - no JavaScript rendering.
Best for static pages, APIs, and simple content extraction.

Examples:
- web_scrape(url="https://example.com") - Get as markdown
- web_scrape(url="https://api.example.com/data", as_json=True) - Parse JSON response
- web_scrape(url="https://example.com", selector="article") - Extract specific section
- web_scrape(url="https://example.com", text_only=True) - Plain text, no formatting"""

    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to scrape"},
            "selector": {
                "type": "string",
                "description": "CSS selector to extract specific content (basic: tag, .class, #id)",
            },
            "as_json": {
                "type": "boolean",
                "description": "Parse response as JSON (default: false)",
            },
            "text_only": {
                "type": "boolean",
                "description": "Return plain text without markdown formatting (default: false)",
            },
            "timeout": {
                "type": "number",
                "description": "Request timeout in seconds (default: 30)",
            },
            "headers": {
                "type": "object",
                "description": "Custom HTTP headers",
            },
            "max_length": {
                "type": "integer",
                "description": "Maximum output length in characters (default: 50000)",
            },
        },
        "required": ["url"],
    }

    async def execute(
        self,
        url: str,
        selector: Optional[str] = None,
        as_json: bool = False,
        text_only: bool = False,
        timeout: float = 30.0,
        headers: Optional[dict[str, str]] = None,
        max_length: int = 50000,
        **kwargs: Any,
    ) -> ToolResult:
        """Scrape a URL."""
        log.info("web_scrape_start", url=url, selector=selector, as_json=as_json)

        if not HTTPX_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="httpx not installed. Install with: pip install httpx",
            )

        if _is_blocked_url(url):
            return ToolResult(
                success=False,
                output="",
                error=f"URL blocked for security: {url}. Cannot access localhost, private IPs, or file:// URLs.",
            )

        try:
            # Prepare headers
            request_headers = {
                "User-Agent": "Sindri/1.0 (Web Scraper)",
                "Accept": "text/html,application/json,application/xhtml+xml,*/*",
            }
            if headers:
                request_headers.update(headers)

            # Make request
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url, headers=request_headers)
                response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            content = response.text

            # JSON mode
            if as_json or "application/json" in content_type:
                try:
                    import json
                    data = response.json()
                    output = json.dumps(data, indent=2)
                    if len(output) > max_length:
                        output = output[:max_length] + "\n... (truncated)"
                    return ToolResult(
                        success=True,
                        output=output,
                        metadata={
                            "url": str(response.url),
                            "content_type": content_type,
                            "status_code": response.status_code,
                            "format": "json",
                        },
                    )
                except Exception as e:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Failed to parse JSON: {e}",
                    )

            # HTML mode
            html = content

            # Extract by selector if provided
            if selector:
                extracted = _extract_by_selector(html, selector)
                if extracted is None:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"No content found matching selector: {selector}",
                    )
                html = extracted

            # Convert to output format
            if text_only:
                output = _html_to_text(html)
            elif HTML2TEXT_AVAILABLE:
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = False
                h.body_width = 0  # No wrapping
                output = h.handle(html)
            else:
                # Fallback: basic conversion
                output = _html_to_text(html)
                log.warning("html2text_not_available", using="basic_conversion")

            # Truncate if too long
            if len(output) > max_length:
                output = output[:max_length] + "\n\n... (truncated)"

            log.info("web_scrape_success", url=url, length=len(output))

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "url": str(response.url),
                    "content_type": content_type,
                    "status_code": response.status_code,
                    "length": len(output),
                    "selector": selector,
                    "format": "text" if text_only else "markdown",
                },
            )

        except httpx.HTTPStatusError as e:
            log.error("web_scrape_http_error", url=url, status=e.response.status_code)
            return ToolResult(
                success=False,
                output="",
                error=f"HTTP error {e.response.status_code}: {e.response.reason_phrase}",
            )
        except httpx.TimeoutException:
            log.error("web_scrape_timeout", url=url, timeout=timeout)
            return ToolResult(
                success=False,
                output="",
                error=f"Request timed out after {timeout}s",
            )
        except Exception as e:
            log.error("web_scrape_error", url=url, error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Scraping failed: {e}",
            )
