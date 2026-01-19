"""Tests for web scraping tool."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sindri.tools.scraping import (
    WebScrapeTool,
    _is_blocked_url,
    _is_cloud_metadata_ip,
    _extract_by_selector,
    _html_to_text,
)


# =============================================================================
# Security Tests (Internal-Only Mode)
# =============================================================================


class TestURLBlocking:
    """Tests for URL security blocking in internal-only mode.

    In internal-only mode, localhost and private IPs are ALLOWED.
    Only cloud metadata endpoints and file:// protocol are blocked.
    """

    def test_localhost_allowed(self):
        """Test that localhost is allowed in internal-only mode."""
        assert _is_blocked_url("http://localhost:8080") is False
        assert _is_blocked_url("https://localhost/path") is False

    def test_loopback_ip_allowed(self):
        """Test that 127.0.0.1 is allowed in internal-only mode."""
        assert _is_blocked_url("http://127.0.0.1:3000") is False
        assert _is_blocked_url("http://127.0.0.1") is False

    def test_private_ip_allowed(self):
        """Test that private IPs are allowed in internal-only mode."""
        assert _is_blocked_url("http://192.168.1.1") is False
        assert _is_blocked_url("http://10.0.0.1") is False
        assert _is_blocked_url("http://172.16.0.1") is False

    def test_cloud_metadata_blocked(self):
        """Test that cloud metadata endpoint is blocked."""
        assert _is_blocked_url("http://169.254.169.254/latest/meta-data/") is True
        assert _is_blocked_url("http://metadata.google.internal/") is True
        assert _is_blocked_url("http://169.254.170.2/") is True

    def test_file_protocol_blocked(self):
        """Test that file:// protocol is blocked."""
        assert _is_blocked_url("file:///etc/passwd") is True
        assert _is_blocked_url("file://localhost/etc/passwd") is True

    def test_public_urls_allowed(self):
        """Test that public URLs are allowed."""
        assert _is_blocked_url("https://example.com") is False
        assert _is_blocked_url("https://google.com") is False
        assert _is_blocked_url("https://github.com") is False


# =============================================================================
# HTML Processing Tests
# =============================================================================


class TestHtmlToText:
    """Tests for HTML to text conversion."""

    def test_basic_html(self):
        """Test basic HTML to text conversion."""
        html = "<p>Hello World</p>"
        text = _html_to_text(html)
        assert "Hello World" in text

    def test_strips_script_tags(self):
        """Test that script tags are removed."""
        html = "<p>Hello</p><script>alert('xss')</script><p>World</p>"
        text = _html_to_text(html)
        assert "Hello" in text
        assert "World" in text
        assert "alert" not in text

    def test_strips_style_tags(self):
        """Test that style tags are removed."""
        html = "<p>Hello</p><style>p { color: red; }</style><p>World</p>"
        text = _html_to_text(html)
        assert "Hello" in text
        assert "World" in text
        assert "color" not in text

    def test_removes_tags(self):
        """Test that HTML tags are removed."""
        html = "<div><h1>Title</h1><p>Content</p></div>"
        text = _html_to_text(html)
        assert "Title" in text
        assert "Content" in text
        assert "<" not in text
        assert ">" not in text

    def test_normalizes_whitespace(self):
        """Test that whitespace is normalized."""
        html = "<p>Hello    World</p>"
        text = _html_to_text(html)
        assert "Hello World" in text or "Hello    World" not in text


class TestExtractBySelector:
    """Tests for CSS selector extraction."""

    def test_extract_by_tag(self):
        """Test extraction by tag name."""
        html = "<html><body><h1>Title Here</h1><p>Content</p></body></html>"
        result = _extract_by_selector(html, "h1")
        assert result == "Title Here"

    def test_extract_by_id(self):
        """Test extraction by ID."""
        html = '<div id="main">Main Content</div><div id="sidebar">Side</div>'
        result = _extract_by_selector(html, "#main")
        assert result == "Main Content"

    def test_extract_by_class(self):
        """Test extraction by class."""
        html = '<div class="article">Article Text</div><div class="sidebar">Side</div>'
        result = _extract_by_selector(html, ".article")
        assert result == "Article Text"

    def test_extract_tag_with_class(self):
        """Test extraction by tag with class."""
        html = '<p class="intro">Intro text</p><p class="body">Body text</p>'
        result = _extract_by_selector(html, "p.intro")
        assert result == "Intro text"

    def test_extract_not_found(self):
        """Test extraction when selector not found."""
        html = "<div>Content</div>"
        result = _extract_by_selector(html, ".nonexistent")
        assert result is None


# =============================================================================
# WebScrapeTool Tests
# =============================================================================


class TestWebScrapeTool:
    """Tests for web scraping tool."""

    @pytest.fixture
    def tool(self):
        return WebScrapeTool()

    @pytest.mark.asyncio
    async def test_httpx_not_available(self, tool):
        """Test behavior when httpx is not installed."""
        with patch("sindri.tools.scraping.HTTPX_AVAILABLE", False):
            tool = WebScrapeTool()
            result = await tool.execute(url="https://example.com")
            assert result.success is False
            assert "httpx not installed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_blocked_cloud_metadata(self, tool):
        """Test that cloud metadata endpoints are blocked."""
        result = await tool.execute(url="http://169.254.169.254/latest/meta-data/")
        assert result.success is False
        assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_blocked_file_protocol(self, tool):
        """Test that file:// protocol is blocked."""
        result = await tool.execute(url="file:///etc/passwd")
        assert result.success is False
        assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_scrape_html_success(self, tool):
        """Test successful HTML scraping."""
        mock_response = MagicMock()
        mock_response.text = "<html><body><h1>Hello World</h1></body></html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("sindri.tools.scraping.HTTPX_AVAILABLE", True):
            with patch("sindri.tools.scraping.httpx.AsyncClient", return_value=mock_client):
                result = await tool.execute(url="https://example.com")

        assert result.success is True
        assert "Hello World" in result.output
        assert result.metadata["status_code"] == 200

    @pytest.mark.asyncio
    async def test_scrape_json_success(self, tool):
        """Test successful JSON scraping."""
        mock_response = MagicMock()
        mock_response.text = '{"key": "value", "count": 42}'
        mock_response.headers = {"content-type": "application/json"}
        mock_response.status_code = 200
        mock_response.url = "https://api.example.com/data"
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"key": "value", "count": 42})

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("sindri.tools.scraping.HTTPX_AVAILABLE", True):
            with patch("sindri.tools.scraping.httpx.AsyncClient", return_value=mock_client):
                result = await tool.execute(url="https://api.example.com/data")

        assert result.success is True
        assert '"key": "value"' in result.output
        assert result.metadata["format"] == "json"

    @pytest.mark.asyncio
    async def test_scrape_with_selector(self, tool):
        """Test scraping with CSS selector."""
        mock_response = MagicMock()
        mock_response.text = '<html><body><article>Article content here</article><aside>Sidebar</aside></body></html>'
        mock_response.headers = {"content-type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("sindri.tools.scraping.HTTPX_AVAILABLE", True):
            with patch("sindri.tools.scraping.httpx.AsyncClient", return_value=mock_client):
                result = await tool.execute(
                    url="https://example.com", selector="article"
                )

        assert result.success is True
        assert "Article content" in result.output
        assert "Sidebar" not in result.output

    @pytest.mark.asyncio
    async def test_scrape_selector_not_found(self, tool):
        """Test scraping with non-matching selector."""
        mock_response = MagicMock()
        mock_response.text = "<html><body><div>Content</div></body></html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("sindri.tools.scraping.HTTPX_AVAILABLE", True):
            with patch("sindri.tools.scraping.httpx.AsyncClient", return_value=mock_client):
                result = await tool.execute(
                    url="https://example.com", selector=".nonexistent"
                )

        assert result.success is False
        assert "no content found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_scrape_text_only(self, tool):
        """Test text-only scraping mode."""
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Hello <strong>World</strong></p></body></html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("sindri.tools.scraping.HTTPX_AVAILABLE", True):
            with patch("sindri.tools.scraping.httpx.AsyncClient", return_value=mock_client):
                result = await tool.execute(url="https://example.com", text_only=True)

        assert result.success is True
        assert "Hello" in result.output
        assert "World" in result.output
        assert result.metadata["format"] == "text"

    @pytest.mark.asyncio
    async def test_scrape_http_error(self, tool):
        """Test HTTP error handling."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.reason_phrase = "Not Found"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Not Found",
                request=MagicMock(),
                response=mock_response,
            )
        )

        with patch("sindri.tools.scraping.HTTPX_AVAILABLE", True):
            with patch("sindri.tools.scraping.httpx.AsyncClient", return_value=mock_client):
                with patch("sindri.tools.scraping.httpx.HTTPStatusError", httpx.HTTPStatusError):
                    result = await tool.execute(url="https://example.com/missing")

        assert result.success is False
        assert "404" in result.error

    @pytest.mark.asyncio
    async def test_scrape_timeout(self, tool):
        """Test timeout handling."""
        import httpx

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        with patch("sindri.tools.scraping.HTTPX_AVAILABLE", True):
            with patch("sindri.tools.scraping.httpx.AsyncClient", return_value=mock_client):
                with patch("sindri.tools.scraping.httpx.TimeoutException", httpx.TimeoutException):
                    result = await tool.execute(url="https://slow-site.com")

        assert result.success is False
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_scrape_max_length(self, tool):
        """Test max_length truncation."""
        long_content = "A" * 100000  # Very long content
        mock_response = MagicMock()
        mock_response.text = f"<html><body>{long_content}</body></html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("sindri.tools.scraping.HTTPX_AVAILABLE", True):
            with patch("sindri.tools.scraping.httpx.AsyncClient", return_value=mock_client):
                result = await tool.execute(
                    url="https://example.com", max_length=1000, text_only=True
                )

        assert result.success is True
        assert len(result.output) <= 1020  # 1000 + some truncation message
        assert "truncated" in result.output.lower()

    @pytest.mark.asyncio
    async def test_scrape_custom_headers(self, tool):
        """Test custom headers are passed."""
        mock_response = MagicMock()
        mock_response.text = "<html><body>Content</body></html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        custom_headers = {"Authorization": "Bearer token123"}

        with patch("sindri.tools.scraping.HTTPX_AVAILABLE", True):
            with patch("sindri.tools.scraping.httpx.AsyncClient", return_value=mock_client):
                result = await tool.execute(
                    url="https://example.com", headers=custom_headers
                )

        assert result.success is True
        # Verify headers were passed (they get merged with defaults)
        call_args = mock_client.get.call_args
        passed_headers = call_args.kwargs.get("headers", {})
        assert "Authorization" in passed_headers


# =============================================================================
# Integration Tests (with html2text if available)
# =============================================================================


class TestWithHtml2Text:
    """Tests that use html2text for markdown conversion."""

    @pytest.fixture
    def tool(self):
        return WebScrapeTool()

    @pytest.mark.asyncio
    async def test_markdown_conversion(self, tool):
        """Test markdown conversion when html2text is available."""
        mock_response = MagicMock()
        mock_response.text = """
        <html>
        <body>
            <h1>Main Title</h1>
            <p>This is a paragraph with <strong>bold</strong> and <em>italic</em> text.</p>
            <a href="https://example.com">Link here</a>
        </body>
        </html>
        """
        mock_response.headers = {"content-type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("sindri.tools.scraping.HTTPX_AVAILABLE", True):
            with patch("sindri.tools.scraping.httpx.AsyncClient", return_value=mock_client):
                result = await tool.execute(url="https://example.com")

        assert result.success is True
        # Content should be present regardless of html2text availability
        assert "Main Title" in result.output
        assert "paragraph" in result.output
        assert result.metadata["format"] == "markdown"
