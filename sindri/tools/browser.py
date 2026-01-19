"""Browser automation tools for Sindri using Playwright."""

import asyncio
import os
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()

# Try to import Playwright
try:
    from playwright.async_api import (
        Browser,
        BrowserContext,
        Page,
        async_playwright,
        TimeoutError as PlaywrightTimeoutError,
    )

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Browser = None
    BrowserContext = None
    Page = None
    async_playwright = None
    PlaywrightTimeoutError = TimeoutError


# Security: Only block cloud metadata endpoints (internal-only mode)
# Localhost and private IPs are allowed for local service integration
BLOCKED_HOSTS = {
    "metadata.google.internal",  # GCP metadata
    "169.254.169.254",  # AWS/GCP metadata
    "169.254.170.2",  # ECS metadata
}


def _is_cloud_metadata_ip(ip: str) -> bool:
    """Check if an IP address is a cloud metadata endpoint."""
    # Only block link-local metadata IPs (169.254.x.x used by cloud providers)
    try:
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        octets = [int(p) for p in parts]
        # 169.254.169.254 and 169.254.170.2 (cloud metadata)
        if octets[0] == 169 and octets[1] == 254:
            if (octets[2] == 169 and octets[3] == 254) or (octets[2] == 170 and octets[3] == 2):
                return True
        return False
    except (ValueError, IndexError):
        return False


def _is_blocked_url(url: str, allow_localhost: bool = True) -> bool:
    """Check if a URL should be blocked for security.

    In internal-only mode, only cloud metadata endpoints are blocked.
    Localhost and private IPs are allowed for local service integration.
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        host_lower = host.lower()
        # Block cloud metadata hosts
        if host_lower in BLOCKED_HOSTS:
            return True
        if _is_cloud_metadata_ip(host):
            return True
        # Block file:// protocol (security risk)
        if parsed.scheme == "file":
            return True
        return False
    except Exception:
        return True  # Block on parse error


# =============================================================================
# Browser Session Manager (Singleton)
# =============================================================================


class BrowserSession:
    """Manages browser lifecycle across tool invocations."""

    _instance: Optional["BrowserSession"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._headless: bool = True
        self._initialized: bool = False

    @classmethod
    async def get_instance(cls, headless: bool = True) -> "BrowserSession":
        """Get or create the singleton browser session."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            if not cls._instance._initialized:
                await cls._instance._initialize(headless)
            return cls._instance

    async def _initialize(self, headless: bool = True) -> None:
        """Initialize browser (called lazily)."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright not available")

        self._headless = headless
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            args=["--disable-dev-shm-usage"],  # Helps with Docker/CI
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Sindri/1.0 (Browser Automation Tool)",
        )
        self._page = await self._context.new_page()
        self._initialized = True

        log.info("browser_session_initialized", headless=headless)

    async def get_page(self) -> Page:
        """Get the current page (or create if needed)."""
        if self._page is None or self._page.is_closed():
            if self._context is None:
                raise RuntimeError("Browser context not initialized")
            self._page = await self._context.new_page()
        return self._page

    async def close(self) -> None:
        """Clean up browser resources."""
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            log.warning("browser_close_error", error=str(e))
        finally:
            self._browser = None
            self._context = None
            self._page = None
            self._playwright = None
            self._initialized = False
            BrowserSession._instance = None
            log.info("browser_session_closed")

    @classmethod
    async def reset(cls) -> None:
        """Reset browser session (new clean context)."""
        if cls._instance:
            await cls._instance.close()
        cls._instance = None


# =============================================================================
# BrowserNavigateTool
# =============================================================================


class BrowserNavigateTool(Tool):
    """Navigate browser to a URL and wait for page load."""

    name = "browser_navigate"
    description = """Navigate to a URL and wait for the page to load.

Examples:
- browser_navigate(url="https://example.com") - Navigate and wait for load
- browser_navigate(url="https://example.com", wait_for="networkidle") - Wait for network idle
- browser_navigate(url="https://example.com", timeout=60) - Custom timeout"""

    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to navigate to"},
            "wait_for": {
                "type": "string",
                "enum": ["load", "domcontentloaded", "networkidle"],
                "description": "Wait condition (default: load)",
            },
            "timeout": {
                "type": "number",
                "description": "Navigation timeout in seconds (default: 30)",
            },
            "headless": {
                "type": "boolean",
                "description": "Run in headless mode (default: true)",
            },
        },
        "required": ["url"],
    }

    async def execute(
        self,
        url: str,
        wait_for: str = "load",
        timeout: float = 30.0,
        headless: bool = True,
        **kwargs: Any,
    ) -> ToolResult:
        """Navigate to a URL."""
        log.info("browser_navigate_start", url=url, wait_for=wait_for)

        if not PLAYWRIGHT_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Playwright not installed. Install with: pip install 'sindri[browser]' && playwright install chromium",
            )

        if _is_blocked_url(url):
            return ToolResult(
                success=False,
                output="",
                error=f"URL blocked for security: {url}. Cannot access cloud metadata endpoints or file:// URLs.",
            )

        try:
            session = await BrowserSession.get_instance(headless=headless)
            page = await session.get_page()

            # Navigate
            await page.goto(
                url,
                wait_until=wait_for,
                timeout=timeout * 1000,  # Playwright uses ms
            )

            title = await page.title()
            current_url = page.url

            log.info("browser_navigate_success", title=title, url=current_url)

            return ToolResult(
                success=True,
                output=f"Navigated to: {current_url}\nPage title: {title}",
                metadata={
                    "url": current_url,
                    "title": title,
                    "wait_for": wait_for,
                },
            )

        except PlaywrightTimeoutError:
            log.error("browser_navigate_timeout", url=url, timeout=timeout)
            return ToolResult(
                success=False,
                output="",
                error=f"Navigation timed out after {timeout}s: {url}",
            )
        except Exception as e:
            log.error("browser_navigate_error", url=url, error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Navigation failed: {e}",
            )


# =============================================================================
# BrowserClickTool
# =============================================================================


class BrowserClickTool(Tool):
    """Click an element on the page."""

    name = "browser_click"
    description = """Click an element by CSS selector or text content.

Examples:
- browser_click(selector="button#submit") - Click by CSS selector
- browser_click(text="Sign In") - Click by visible text
- browser_click(selector=".menu-item", index=2) - Click 3rd matching element"""

    parameters = {
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector for element"},
            "text": {"type": "string", "description": "Visible text to find and click"},
            "index": {
                "type": "integer",
                "description": "Index if multiple matches (default: 0)",
            },
            "timeout": {
                "type": "number",
                "description": "Wait timeout in seconds (default: 10)",
            },
            "force": {
                "type": "boolean",
                "description": "Force click even if not visible (default: false)",
            },
        },
    }

    async def execute(
        self,
        selector: Optional[str] = None,
        text: Optional[str] = None,
        index: int = 0,
        timeout: float = 10.0,
        force: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Click an element."""
        log.info("browser_click_start", selector=selector, text=text, index=index)

        if not PLAYWRIGHT_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Playwright not installed. Install with: pip install 'sindri[browser]' && playwright install chromium",
            )

        if not selector and not text:
            return ToolResult(
                success=False,
                output="",
                error="Must provide either 'selector' or 'text' parameter",
            )

        try:
            session = await BrowserSession.get_instance()
            page = await session.get_page()

            # Build locator
            if text:
                locator = page.get_by_text(text, exact=False)
            else:
                locator = page.locator(selector)

            # Get specific index if multiple matches
            if index > 0:
                locator = locator.nth(index)

            # Wait for element and click
            await locator.wait_for(timeout=timeout * 1000, state="visible")
            await locator.click(force=force, timeout=timeout * 1000)

            # Get info about clicked element
            tag_name = await locator.evaluate("el => el.tagName.toLowerCase()")
            element_text = await locator.inner_text()
            element_text = element_text[:100] if element_text else ""

            log.info("browser_click_success", tag=tag_name, text=element_text[:50])

            return ToolResult(
                success=True,
                output=f"Clicked <{tag_name}>: {element_text}",
                metadata={
                    "tag": tag_name,
                    "text": element_text,
                    "selector": selector,
                    "index": index,
                },
            )

        except PlaywrightTimeoutError:
            target = selector or f'text="{text}"'
            log.error("browser_click_timeout", target=target)
            return ToolResult(
                success=False,
                output="",
                error=f"Element not found within {timeout}s: {target}",
            )
        except Exception as e:
            log.error("browser_click_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Click failed: {e}",
            )


# =============================================================================
# BrowserTypeTool
# =============================================================================


class BrowserTypeTool(Tool):
    """Type text into a form field."""

    name = "browser_type"
    description = """Type text into a form field identified by selector.

Examples:
- browser_type(selector="input[name='email']", text="user@example.com")
- browser_type(selector="#search", text="query", clear_first=True)
- browser_type(selector="textarea", text="content", press_enter=True)"""

    parameters = {
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector for input field"},
            "text": {"type": "string", "description": "Text to type"},
            "clear_first": {
                "type": "boolean",
                "description": "Clear field before typing (default: false)",
            },
            "press_enter": {
                "type": "boolean",
                "description": "Press Enter after typing (default: false)",
            },
            "delay": {
                "type": "number",
                "description": "Delay between keystrokes in ms (default: 0)",
            },
            "timeout": {
                "type": "number",
                "description": "Wait timeout in seconds (default: 10)",
            },
        },
        "required": ["selector", "text"],
    }

    async def execute(
        self,
        selector: str,
        text: str,
        clear_first: bool = False,
        press_enter: bool = False,
        delay: float = 0,
        timeout: float = 10.0,
        **kwargs: Any,
    ) -> ToolResult:
        """Type text into an element."""
        log.info("browser_type_start", selector=selector, text_len=len(text))

        if not PLAYWRIGHT_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Playwright not installed. Install with: pip install 'sindri[browser]' && playwright install chromium",
            )

        try:
            session = await BrowserSession.get_instance()
            page = await session.get_page()

            locator = page.locator(selector)
            await locator.wait_for(timeout=timeout * 1000, state="visible")

            # Clear if requested
            if clear_first:
                await locator.clear()

            # Type text
            await locator.type(text, delay=delay)

            # Press Enter if requested
            if press_enter:
                await locator.press("Enter")

            log.info("browser_type_success", selector=selector)

            return ToolResult(
                success=True,
                output=f"Typed {len(text)} characters into {selector}" + (" (Enter pressed)" if press_enter else ""),
                metadata={
                    "selector": selector,
                    "text_length": len(text),
                    "clear_first": clear_first,
                    "press_enter": press_enter,
                },
            )

        except PlaywrightTimeoutError:
            log.error("browser_type_timeout", selector=selector)
            return ToolResult(
                success=False,
                output="",
                error=f"Element not found within {timeout}s: {selector}",
            )
        except Exception as e:
            log.error("browser_type_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Type failed: {e}",
            )


# =============================================================================
# BrowserScreenshotTool
# =============================================================================


class BrowserScreenshotTool(Tool):
    """Capture a screenshot of the page or element."""

    name = "browser_screenshot"
    description = """Capture screenshot of page or specific element.

Examples:
- browser_screenshot(path="screenshot.png") - Full viewport screenshot
- browser_screenshot(path="element.png", selector=".hero-section") - Element only
- browser_screenshot(path="full.png", full_page=True) - Scrollable full page"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Output file path (PNG or JPEG)"},
            "selector": {
                "type": "string",
                "description": "CSS selector for element screenshot (optional)",
            },
            "full_page": {
                "type": "boolean",
                "description": "Capture full scrollable page (default: false)",
            },
            "quality": {
                "type": "integer",
                "description": "JPEG quality 0-100 (only for .jpg files)",
            },
        },
        "required": ["path"],
    }

    async def execute(
        self,
        path: str,
        selector: Optional[str] = None,
        full_page: bool = False,
        quality: Optional[int] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Capture a screenshot."""
        log.info("browser_screenshot_start", path=path, selector=selector, full_page=full_page)

        if not PLAYWRIGHT_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Playwright not installed. Install with: pip install 'sindri[browser]' && playwright install chromium",
            )

        try:
            session = await BrowserSession.get_instance()
            page = await session.get_page()

            # Resolve output path
            output_path = self._resolve_path(path)
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

            # Determine screenshot type
            screenshot_args: dict[str, Any] = {"path": str(output_path)}

            if quality is not None and str(output_path).lower().endswith((".jpg", ".jpeg")):
                screenshot_args["quality"] = quality

            if selector:
                # Element screenshot
                locator = page.locator(selector)
                await locator.wait_for(state="visible", timeout=10000)
                await locator.screenshot(**screenshot_args)
                mode = f"element ({selector})"
            else:
                # Page screenshot
                screenshot_args["full_page"] = full_page
                await page.screenshot(**screenshot_args)
                mode = "full page" if full_page else "viewport"

            # Get file info
            file_size = os.path.getsize(output_path)

            log.info("browser_screenshot_success", path=str(output_path), size=file_size)

            return ToolResult(
                success=True,
                output=f"Screenshot saved: {output_path} ({mode}, {file_size} bytes)",
                metadata={
                    "path": str(output_path),
                    "mode": mode,
                    "size": file_size,
                    "full_page": full_page,
                    "selector": selector,
                },
            )

        except Exception as e:
            log.error("browser_screenshot_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Screenshot failed: {e}",
            )


# =============================================================================
# BrowserExtractTool
# =============================================================================


class BrowserExtractTool(Tool):
    """Extract structured data from the page."""

    name = "browser_extract"
    description = """Extract text, attributes, or structured data from page elements.

Examples:
- browser_extract(selector="h1") - Get text of first h1
- browser_extract(selector=".product", attributes=["data-id", "data-price"]) - Get attributes
- browser_extract(selector="table tr", as_table=True) - Extract as table rows
- browser_extract(selector="a", attribute="href", all=True) - Get all link hrefs"""

    parameters = {
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector for element(s)"},
            "attribute": {
                "type": "string",
                "description": "Single attribute to extract",
            },
            "attributes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Multiple attributes to extract",
            },
            "all": {
                "type": "boolean",
                "description": "Extract from all matching elements (default: false)",
            },
            "as_table": {
                "type": "boolean",
                "description": "Parse as table (for tr/td elements)",
            },
            "inner_html": {
                "type": "boolean",
                "description": "Get innerHTML instead of text (default: false)",
            },
            "timeout": {
                "type": "number",
                "description": "Wait timeout in seconds (default: 10)",
            },
        },
        "required": ["selector"],
    }

    async def execute(
        self,
        selector: str,
        attribute: Optional[str] = None,
        attributes: Optional[list[str]] = None,
        all: bool = False,
        as_table: bool = False,
        inner_html: bool = False,
        timeout: float = 10.0,
        **kwargs: Any,
    ) -> ToolResult:
        """Extract data from elements."""
        log.info("browser_extract_start", selector=selector, all=all)

        if not PLAYWRIGHT_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Playwright not installed. Install with: pip install 'sindri[browser]' && playwright install chromium",
            )

        try:
            session = await BrowserSession.get_instance()
            page = await session.get_page()

            locator = page.locator(selector)

            # Wait for at least one element
            try:
                await locator.first.wait_for(timeout=timeout * 1000, state="attached")
            except PlaywrightTimeoutError:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"No elements found matching: {selector}",
                )

            # Get element count
            count = await locator.count()

            # Extract data based on mode
            if as_table:
                # Table extraction
                rows = []
                row_locators = locator
                for i in range(await row_locators.count()):
                    row = row_locators.nth(i)
                    cells = row.locator("td, th")
                    cell_texts = []
                    for j in range(await cells.count()):
                        cell_texts.append(await cells.nth(j).inner_text())
                    rows.append(cell_texts)

                output = "\n".join([" | ".join(row) for row in rows])
                return ToolResult(
                    success=True,
                    output=f"Extracted {len(rows)} rows:\n{output}",
                    metadata={"rows": rows, "count": len(rows)},
                )

            elif attribute or attributes:
                # Attribute extraction
                attr_list = attributes or [attribute]
                results = []

                elements = locator.all() if all else [locator.first]
                if all:
                    elements = [locator.nth(i) for i in range(count)]
                else:
                    elements = [locator.first]

                for elem in elements:
                    item = {}
                    for attr in attr_list:
                        item[attr] = await elem.get_attribute(attr)
                    results.append(item)

                if len(results) == 1 and len(attr_list) == 1:
                    output = str(results[0].get(attr_list[0], ""))
                else:
                    import json
                    output = json.dumps(results, indent=2)

                return ToolResult(
                    success=True,
                    output=output,
                    metadata={"data": results, "count": len(results)},
                )

            else:
                # Text extraction
                if all:
                    texts = []
                    for i in range(count):
                        elem = locator.nth(i)
                        if inner_html:
                            texts.append(await elem.inner_html())
                        else:
                            texts.append(await elem.inner_text())
                    output = "\n---\n".join(texts)
                    return ToolResult(
                        success=True,
                        output=f"Extracted {len(texts)} elements:\n{output}",
                        metadata={"texts": texts, "count": len(texts)},
                    )
                else:
                    if inner_html:
                        text = await locator.first.inner_html()
                    else:
                        text = await locator.first.inner_text()
                    return ToolResult(
                        success=True,
                        output=text,
                        metadata={"text": text, "count": 1},
                    )

        except Exception as e:
            log.error("browser_extract_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Extraction failed: {e}",
            )


# =============================================================================
# BrowserExecuteJsTool
# =============================================================================


class BrowserExecuteJsTool(Tool):
    """Execute JavaScript on the page."""

    name = "browser_execute_js"
    description = """Execute JavaScript code in page context.

Examples:
- browser_execute_js(script="return document.title") - Get page title
- browser_execute_js(script="window.scrollTo(0, document.body.scrollHeight)") - Scroll to bottom
- browser_execute_js(script="return JSON.stringify(window.appState)") - Get app state"""

    parameters = {
        "type": "object",
        "properties": {
            "script": {"type": "string", "description": "JavaScript code to execute"},
            "timeout": {
                "type": "number",
                "description": "Execution timeout in seconds (default: 30)",
            },
        },
        "required": ["script"],
    }

    async def execute(
        self,
        script: str,
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute JavaScript."""
        log.info("browser_execute_js_start", script_len=len(script))

        if not PLAYWRIGHT_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Playwright not installed. Install with: pip install 'sindri[browser]' && playwright install chromium",
            )

        try:
            session = await BrowserSession.get_instance()
            page = await session.get_page()

            # Execute with timeout
            result = await asyncio.wait_for(
                page.evaluate(script),
                timeout=timeout,
            )

            # Format result
            if result is None:
                output = "(no return value)"
            elif isinstance(result, (dict, list)):
                import json
                output = json.dumps(result, indent=2)
            else:
                output = str(result)

            log.info("browser_execute_js_success", result_type=type(result).__name__)

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "result": result,
                    "result_type": type(result).__name__,
                },
            )

        except asyncio.TimeoutError:
            log.error("browser_execute_js_timeout", timeout=timeout)
            return ToolResult(
                success=False,
                output="",
                error=f"Script execution timed out after {timeout}s",
            )
        except Exception as e:
            log.error("browser_execute_js_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"JavaScript execution failed: {e}",
            )


# =============================================================================
# BrowserPdfTool
# =============================================================================


class BrowserPdfTool(Tool):
    """Save the current page as a PDF."""

    name = "browser_pdf"
    description = """Save the current page as a PDF file.

Examples:
- browser_pdf(path="page.pdf") - Save as A4 PDF
- browser_pdf(path="report.pdf", format="Letter", landscape=True)
- browser_pdf(path="doc.pdf", print_background=True) - Include backgrounds"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Output PDF file path"},
            "format": {
                "type": "string",
                "enum": ["A4", "Letter", "Legal", "Tabloid", "A3", "A5"],
                "description": "Paper format (default: A4)",
            },
            "landscape": {
                "type": "boolean",
                "description": "Landscape orientation (default: false)",
            },
            "print_background": {
                "type": "boolean",
                "description": "Print background graphics (default: false)",
            },
            "scale": {
                "type": "number",
                "description": "Scale (0.1 to 2.0, default: 1.0)",
            },
            "margin": {
                "type": "object",
                "description": "Margins: {top, right, bottom, left} in CSS units",
            },
        },
        "required": ["path"],
    }

    async def execute(
        self,
        path: str,
        format: str = "A4",
        landscape: bool = False,
        print_background: bool = False,
        scale: float = 1.0,
        margin: Optional[dict[str, str]] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Save page as PDF."""
        log.info("browser_pdf_start", path=path, format=format)

        if not PLAYWRIGHT_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Playwright not installed. Install with: pip install 'sindri[browser]' && playwright install chromium",
            )

        try:
            session = await BrowserSession.get_instance()
            page = await session.get_page()

            # Resolve output path
            output_path = self._resolve_path(path)
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

            # Build PDF options
            pdf_options: dict[str, Any] = {
                "path": str(output_path),
                "format": format,
                "landscape": landscape,
                "print_background": print_background,
                "scale": scale,
            }

            if margin:
                pdf_options["margin"] = margin

            # Generate PDF
            await page.pdf(**pdf_options)

            file_size = os.path.getsize(output_path)

            log.info("browser_pdf_success", path=str(output_path), size=file_size)

            return ToolResult(
                success=True,
                output=f"PDF saved: {output_path} ({format}, {file_size} bytes)",
                metadata={
                    "path": str(output_path),
                    "format": format,
                    "landscape": landscape,
                    "size": file_size,
                },
            )

        except Exception as e:
            log.error("browser_pdf_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"PDF generation failed: {e}",
            )


# =============================================================================
# BrowserCloseTool
# =============================================================================


class BrowserCloseTool(Tool):
    """Close the browser session."""

    name = "browser_close"
    description = """Close the browser session and release resources.

Use this when you're done with browser automation to free memory.

Examples:
- browser_close() - Close browser session"""

    parameters = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Close browser session."""
        log.info("browser_close_start")

        if not PLAYWRIGHT_AVAILABLE:
            return ToolResult(
                success=True,
                output="Playwright not installed, nothing to close.",
                metadata={},
            )

        try:
            await BrowserSession.reset()

            log.info("browser_close_success")

            return ToolResult(
                success=True,
                output="Browser session closed.",
                metadata={},
            )

        except Exception as e:
            log.error("browser_close_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to close browser: {e}",
            )
