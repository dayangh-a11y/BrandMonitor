"""Playwright browser wrapper with timeout + retry support."""

from __future__ import annotations

from types import TracebackType

from loguru import logger
from playwright.sync_api import Browser, Page, Playwright, TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from src.utils.retry import FetchError, TimeoutError_, with_retry
from src.utils.settings import Settings, get_settings


class BrowserClient:
    """Thin sync Playwright helper used by datasource implementations."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    def __enter__(self) -> BrowserClient:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def start(self) -> None:
        if self._browser is not None:
            return
        logger.info(
            "Starting Playwright (headless={})",
            self.settings.browser_headless,
        )
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.settings.browser_headless,
        )

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        logger.debug("Playwright closed")

    def _new_page(self) -> Page:
        if self._browser is None:
            self.start()
        assert self._browser is not None
        page = self._browser.new_page()
        page.set_default_timeout(self.settings.browser_timeout_ms)
        page.set_default_navigation_timeout(self.settings.browser_navigation_timeout_ms)
        return page

    def fetch_html(self, url: str, *, wait_until: str = "domcontentloaded") -> str:
        """Navigate to URL and return full HTML with retries."""

        @with_retry(
            max_attempts=self.settings.max_retries,
            min_wait=self.settings.retry_wait_seconds,
        )
        def _fetch() -> str:
            page = self._new_page()
            try:
                logger.info("Fetching {}", url)
                page.goto(url, wait_until=wait_until)
                # Allow client hydration briefly for dynamic bits
                page.wait_for_timeout(500)
                html = page.content()
                if not html or len(html) < 200:
                    raise FetchError(f"Empty/short HTML for {url}")
                return html
            except PlaywrightTimeout as exc:
                raise TimeoutError_(f"Timeout fetching {url}: {exc}") from exc
            except TimeoutError_ :
                raise
            except FetchError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise FetchError(f"Failed fetching {url}: {exc}") from exc
            finally:
                page.close()

        return _fetch()
