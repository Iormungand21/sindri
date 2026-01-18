"""Tests for browser automation tools."""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Test imports work even without playwright
from sindri.tools.browser import (
    PLAYWRIGHT_AVAILABLE,
    BrowserNavigateTool,
    BrowserClickTool,
    BrowserTypeTool,
    BrowserScreenshotTool,
    BrowserExtractTool,
    BrowserExecuteJsTool,
    BrowserPdfTool,
    BrowserCloseTool,
    BrowserSession,
    _is_blocked_url,
    _is_private_ip,
)


# =============================================================================
# Security Tests
# =============================================================================


class TestURLBlocking:
    """Tests for URL security blocking."""

    def test_localhost_blocked(self):
        """Test that localhost is blocked."""
        assert _is_blocked_url("http://localhost:8080") is True
        assert _is_blocked_url("https://localhost/path") is True

    def test_loopback_ip_blocked(self):
        """Test that 127.0.0.1 is blocked."""
        assert _is_blocked_url("http://127.0.0.1:3000") is True
        assert _is_blocked_url("http://127.0.0.1") is True

    def test_private_ip_blocked(self):
        """Test that private IPs are blocked."""
        assert _is_blocked_url("http://192.168.1.1") is True
        assert _is_blocked_url("http://10.0.0.1") is True
        assert _is_blocked_url("http://172.16.0.1") is True

    def test_cloud_metadata_blocked(self):
        """Test that cloud metadata endpoint is blocked."""
        assert _is_blocked_url("http://169.254.169.254/latest/meta-data/") is True
        assert _is_blocked_url("http://metadata.google.internal/") is True

    def test_file_protocol_blocked(self):
        """Test that file:// protocol is blocked."""
        assert _is_blocked_url("file:///etc/passwd") is True
        assert _is_blocked_url("file://localhost/etc/passwd") is True

    def test_public_urls_allowed(self):
        """Test that public URLs are allowed."""
        assert _is_blocked_url("https://example.com") is False
        assert _is_blocked_url("https://google.com") is False
        assert _is_blocked_url("https://github.com") is False

    def test_localhost_allowed_when_enabled(self):
        """Test that localhost can be allowed."""
        assert _is_blocked_url("http://localhost:8080", allow_localhost=True) is False


class TestPrivateIP:
    """Tests for private IP detection."""

    def test_10_x_x_x_range(self):
        """Test 10.0.0.0/8 range."""
        assert _is_private_ip("10.0.0.1") is True
        assert _is_private_ip("10.255.255.255") is True

    def test_172_16_range(self):
        """Test 172.16.0.0/12 range."""
        assert _is_private_ip("172.16.0.1") is True
        assert _is_private_ip("172.31.255.255") is True
        assert _is_private_ip("172.15.0.1") is False
        assert _is_private_ip("172.32.0.1") is False

    def test_192_168_range(self):
        """Test 192.168.0.0/16 range."""
        assert _is_private_ip("192.168.0.1") is True
        assert _is_private_ip("192.168.255.255") is True

    def test_loopback(self):
        """Test loopback addresses."""
        assert _is_private_ip("127.0.0.1") is True
        assert _is_private_ip("127.255.255.255") is True

    def test_public_ips(self):
        """Test public IPs."""
        assert _is_private_ip("8.8.8.8") is False
        assert _is_private_ip("1.1.1.1") is False
        assert _is_private_ip("142.250.185.46") is False

    def test_invalid_ip(self):
        """Test invalid IP addresses."""
        assert _is_private_ip("not.an.ip") is False
        assert _is_private_ip("192.168.1") is False
        assert _is_private_ip("") is False


# =============================================================================
# BrowserNavigateTool Tests
# =============================================================================


class TestBrowserNavigateTool:
    """Tests for browser navigation."""

    @pytest.fixture
    def tool(self):
        return BrowserNavigateTool()

    @pytest.mark.asyncio
    async def test_playwright_not_available(self, tool):
        """Test behavior when Playwright is not installed."""
        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", False):
            tool = BrowserNavigateTool()
            result = await tool.execute(url="https://example.com")
            assert result.success is False
            assert "playwright not installed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_blocked_localhost(self, tool):
        """Test that localhost is blocked."""
        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            result = await tool.execute(url="http://localhost:8080")
        assert result.success is False
        assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_blocked_private_ip(self, tool):
        """Test that private IPs are blocked."""
        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            result = await tool.execute(url="http://192.168.1.1")
        assert result.success is False
        assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_successful_navigation(self, tool):
        """Test successful page navigation with mocked browser."""
        mock_page = AsyncMock()
        mock_page.title = AsyncMock(return_value="Example Page")
        mock_page.url = "https://example.com"
        mock_page.goto = AsyncMock()

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(url="https://example.com")

        assert result.success is True
        assert "Example Page" in result.output
        assert result.metadata["url"] == "https://example.com"
        mock_page.goto.assert_called_once()

    @pytest.mark.asyncio
    async def test_navigation_timeout(self, tool):
        """Test navigation timeout handling."""
        # Import the timeout error class
        from sindri.tools.browser import PlaywrightTimeoutError

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=PlaywrightTimeoutError("Timeout"))

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(url="https://example.com", timeout=5)

        assert result.success is False
        assert "timed out" in result.error.lower()


# =============================================================================
# BrowserClickTool Tests
# =============================================================================


class TestBrowserClickTool:
    """Tests for browser click."""

    @pytest.fixture
    def tool(self):
        return BrowserClickTool()

    @pytest.mark.asyncio
    async def test_missing_selector_and_text(self, tool):
        """Test that either selector or text must be provided."""
        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            result = await tool.execute()
        assert result.success is False
        assert "selector" in result.error.lower() or "text" in result.error.lower()

    @pytest.mark.asyncio
    async def test_click_by_selector(self, tool):
        """Test clicking by CSS selector."""
        mock_locator = AsyncMock()
        mock_locator.wait_for = AsyncMock()
        mock_locator.click = AsyncMock()
        mock_locator.evaluate = AsyncMock(return_value="button")
        mock_locator.inner_text = AsyncMock(return_value="Click Me")

        mock_page = AsyncMock()
        mock_page.locator = MagicMock(return_value=mock_locator)

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(selector="button#submit")

        assert result.success is True
        assert "button" in result.output.lower()
        mock_locator.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_click_by_text(self, tool):
        """Test clicking by visible text."""
        mock_locator = AsyncMock()
        mock_locator.wait_for = AsyncMock()
        mock_locator.click = AsyncMock()
        mock_locator.evaluate = AsyncMock(return_value="a")
        mock_locator.inner_text = AsyncMock(return_value="Sign In")

        mock_page = AsyncMock()
        mock_page.get_by_text = MagicMock(return_value=mock_locator)

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(text="Sign In")

        assert result.success is True
        mock_page.get_by_text.assert_called_once_with("Sign In", exact=False)


# =============================================================================
# BrowserTypeTool Tests
# =============================================================================


class TestBrowserTypeTool:
    """Tests for browser type."""

    @pytest.fixture
    def tool(self):
        return BrowserTypeTool()

    @pytest.mark.asyncio
    async def test_type_into_field(self, tool):
        """Test typing into a form field."""
        mock_locator = AsyncMock()
        mock_locator.wait_for = AsyncMock()
        mock_locator.type = AsyncMock()

        mock_page = AsyncMock()
        mock_page.locator = MagicMock(return_value=mock_locator)

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(
                    selector="input[name='email']", text="user@example.com"
                )

        assert result.success is True
        assert "16" in result.output  # len("user@example.com")
        mock_locator.type.assert_called_once()

    @pytest.mark.asyncio
    async def test_type_with_clear(self, tool):
        """Test typing with clear_first option."""
        mock_locator = AsyncMock()
        mock_locator.wait_for = AsyncMock()
        mock_locator.clear = AsyncMock()
        mock_locator.type = AsyncMock()

        mock_page = AsyncMock()
        mock_page.locator = MagicMock(return_value=mock_locator)

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(
                    selector="#search", text="query", clear_first=True
                )

        assert result.success is True
        mock_locator.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_type_with_enter(self, tool):
        """Test typing with press_enter option."""
        mock_locator = AsyncMock()
        mock_locator.wait_for = AsyncMock()
        mock_locator.type = AsyncMock()
        mock_locator.press = AsyncMock()

        mock_page = AsyncMock()
        mock_page.locator = MagicMock(return_value=mock_locator)

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(
                    selector="#search", text="query", press_enter=True
                )

        assert result.success is True
        assert "Enter" in result.output
        mock_locator.press.assert_called_once_with("Enter")


# =============================================================================
# BrowserScreenshotTool Tests
# =============================================================================


class TestBrowserScreenshotTool:
    """Tests for browser screenshot."""

    @pytest.fixture
    def tool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield BrowserScreenshotTool(work_dir=Path(tmpdir))

    @pytest.mark.asyncio
    async def test_full_page_screenshot(self, tool):
        """Test full page screenshot."""
        mock_page = AsyncMock()

        # Create actual file to test
        def create_file(path, **kwargs):
            Path(path).write_bytes(b"fake png data")

        mock_page.screenshot = AsyncMock(side_effect=create_file)

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(path="screenshot.png", full_page=True)

        assert result.success is True
        assert "screenshot" in result.output.lower()
        assert result.metadata["full_page"] is True

    @pytest.mark.asyncio
    async def test_element_screenshot(self, tool):
        """Test element screenshot."""
        mock_locator = AsyncMock()
        mock_locator.wait_for = AsyncMock()

        def create_file(path, **kwargs):
            Path(path).write_bytes(b"fake png data")

        mock_locator.screenshot = AsyncMock(side_effect=create_file)

        mock_page = AsyncMock()
        mock_page.locator = MagicMock(return_value=mock_locator)

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(
                    path="element.png", selector=".hero-section"
                )

        assert result.success is True
        assert "element" in result.output.lower()
        assert result.metadata["selector"] == ".hero-section"


# =============================================================================
# BrowserExtractTool Tests
# =============================================================================


class TestBrowserExtractTool:
    """Tests for browser extraction."""

    @pytest.fixture
    def tool(self):
        return BrowserExtractTool()

    @pytest.mark.asyncio
    async def test_extract_text(self, tool):
        """Test extracting text from element."""
        mock_locator = AsyncMock()
        mock_locator.first = AsyncMock()
        mock_locator.first.wait_for = AsyncMock()
        mock_locator.first.inner_text = AsyncMock(return_value="Hello World")
        mock_locator.count = AsyncMock(return_value=1)

        mock_page = AsyncMock()
        mock_page.locator = MagicMock(return_value=mock_locator)

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(selector="h1")

        assert result.success is True
        assert "Hello World" in result.output

    @pytest.mark.asyncio
    async def test_extract_attribute(self, tool):
        """Test extracting attribute from element."""
        mock_locator = AsyncMock()
        mock_locator.first = AsyncMock()
        mock_locator.first.wait_for = AsyncMock()
        mock_locator.first.get_attribute = AsyncMock(return_value="https://example.com")
        mock_locator.count = AsyncMock(return_value=1)

        mock_page = AsyncMock()
        mock_page.locator = MagicMock(return_value=mock_locator)

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(selector="a", attribute="href")

        assert result.success is True
        assert "https://example.com" in result.output

    @pytest.mark.asyncio
    async def test_extract_all_elements(self, tool):
        """Test extracting from all matching elements."""
        mock_locator = AsyncMock()
        mock_locator.first = AsyncMock()
        mock_locator.first.wait_for = AsyncMock()
        mock_locator.count = AsyncMock(return_value=3)

        # Mock nth() to return different locators
        mock_elem1 = AsyncMock()
        mock_elem1.inner_text = AsyncMock(return_value="Item 1")
        mock_elem2 = AsyncMock()
        mock_elem2.inner_text = AsyncMock(return_value="Item 2")
        mock_elem3 = AsyncMock()
        mock_elem3.inner_text = AsyncMock(return_value="Item 3")

        mock_locator.nth = MagicMock(
            side_effect=lambda i: [mock_elem1, mock_elem2, mock_elem3][i]
        )

        mock_page = AsyncMock()
        mock_page.locator = MagicMock(return_value=mock_locator)

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(selector=".item", all=True)

        assert result.success is True
        assert "Item 1" in result.output
        assert "Item 2" in result.output
        assert "Item 3" in result.output
        assert result.metadata["count"] == 3


# =============================================================================
# BrowserExecuteJsTool Tests
# =============================================================================


class TestBrowserExecuteJsTool:
    """Tests for browser JavaScript execution."""

    @pytest.fixture
    def tool(self):
        return BrowserExecuteJsTool()

    @pytest.mark.asyncio
    async def test_execute_js_string_return(self, tool):
        """Test executing JS that returns a string."""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value="Example Page Title")

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(script="return document.title")

        assert result.success is True
        assert "Example Page Title" in result.output

    @pytest.mark.asyncio
    async def test_execute_js_object_return(self, tool):
        """Test executing JS that returns an object."""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value={"key": "value", "count": 42})

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(
                    script="return {key: 'value', count: 42}"
                )

        assert result.success is True
        assert '"key": "value"' in result.output
        assert '"count": 42' in result.output

    @pytest.mark.asyncio
    async def test_execute_js_no_return(self, tool):
        """Test executing JS with no return value."""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(
                    script="window.scrollTo(0, document.body.scrollHeight)"
                )

        assert result.success is True
        assert "no return" in result.output.lower()


# =============================================================================
# BrowserPdfTool Tests
# =============================================================================


class TestBrowserPdfTool:
    """Tests for browser PDF generation."""

    @pytest.fixture
    def tool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield BrowserPdfTool(work_dir=Path(tmpdir))

    @pytest.mark.asyncio
    async def test_generate_pdf(self, tool):
        """Test generating PDF from page."""
        mock_page = AsyncMock()

        def create_file(path, **kwargs):
            Path(path).write_bytes(b"%PDF-1.4 fake pdf data")

        mock_page.pdf = AsyncMock(side_effect=create_file)

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(path="page.pdf")

        assert result.success is True
        assert "pdf" in result.output.lower()
        assert result.metadata["format"] == "A4"

    @pytest.mark.asyncio
    async def test_generate_pdf_landscape(self, tool):
        """Test generating landscape PDF."""
        mock_page = AsyncMock()

        def create_file(path, **kwargs):
            Path(path).write_bytes(b"%PDF-1.4 fake pdf data")

        mock_page.pdf = AsyncMock(side_effect=create_file)

        mock_session = MagicMock()
        mock_session.get_page = AsyncMock(return_value=mock_page)

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(
                BrowserSession, "get_instance", AsyncMock(return_value=mock_session)
            ):
                result = await tool.execute(
                    path="report.pdf", format="Letter", landscape=True
                )

        assert result.success is True
        assert result.metadata["landscape"] is True
        assert result.metadata["format"] == "Letter"


# =============================================================================
# BrowserCloseTool Tests
# =============================================================================


class TestBrowserCloseTool:
    """Tests for browser close."""

    @pytest.fixture
    def tool(self):
        return BrowserCloseTool()

    @pytest.mark.asyncio
    async def test_close_browser(self, tool):
        """Test closing browser session."""
        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch.object(BrowserSession, "reset", AsyncMock()) as mock_reset:
                result = await tool.execute()

        assert result.success is True
        assert "closed" in result.output.lower()
        mock_reset.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_when_not_available(self, tool):
        """Test closing when Playwright not available."""
        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", False):
            result = await tool.execute()

        assert result.success is True  # Should succeed even if not installed


# =============================================================================
# BrowserSession Tests
# =============================================================================


class TestBrowserSession:
    """Tests for browser session management."""

    @pytest.mark.asyncio
    async def test_session_singleton(self):
        """Test that BrowserSession is a singleton."""
        # Reset any existing instance
        BrowserSession._instance = None

        with patch("sindri.tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch("sindri.tools.browser.async_playwright") as mock_playwright:
                mock_pw_instance = AsyncMock()
                mock_browser = AsyncMock()
                mock_context = AsyncMock()
                mock_page = AsyncMock()

                mock_pw_instance.start = AsyncMock(return_value=mock_pw_instance)
                mock_pw_instance.chromium = AsyncMock()
                mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)
                mock_browser.new_context = AsyncMock(return_value=mock_context)
                mock_context.new_page = AsyncMock(return_value=mock_page)

                mock_playwright.return_value.start = AsyncMock(
                    return_value=mock_pw_instance
                )

                session1 = await BrowserSession.get_instance()
                session2 = await BrowserSession.get_instance()

                assert session1 is session2

        # Clean up
        BrowserSession._instance = None

    @pytest.mark.asyncio
    async def test_session_reset(self):
        """Test session reset creates new instance."""
        BrowserSession._instance = None

        # Create a mock session
        mock_session = MagicMock()
        mock_session.close = AsyncMock()
        BrowserSession._instance = mock_session

        await BrowserSession.reset()

        assert BrowserSession._instance is None
        mock_session.close.assert_called_once()
