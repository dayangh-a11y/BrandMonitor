from __future__ import annotations

import os
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright


class BrowserManager:
    def __init__(self, headless: bool | None = None):
        if headless is None:
            headless = os.getenv("HEADLESS", "true").lower() != "false"
        self.headless = headless
        self._playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.storage_state_path = (os.getenv("BROWSER_STORAGE_STATE") or "").strip()
        self.proxy = (
            os.getenv("BROWSER_PROXY")
            or os.getenv("HTTPS_PROXY")
            or os.getenv("HTTP_PROXY")
            or ""
        ).strip()
        self.locale = os.getenv("BROWSER_LOCALE", "en-US")

    async def start(self) -> Page:
        self._playwright = await async_playwright().start()
        launch_kwargs: dict = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        }
        if self.proxy:
            launch_kwargs["proxy"] = {"server": self.proxy}

        self.browser = await self._playwright.chromium.launch(**launch_kwargs)

        context_kwargs: dict = {
            "locale": self.locale,
            "viewport": {"width": 1365, "height": 900},
            "user_agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            ),
        }
        if self.storage_state_path and Path(self.storage_state_path).is_file():
            context_kwargs["storage_state"] = self.storage_state_path

        self.context = await self.browser.new_context(**context_kwargs)
        self.page = await self.context.new_page()
        return self.page

    async def save_storage_state(self, path: str | None = None) -> str | None:
        """Persist cookies/localStorage for warmer residential/authenticated sessions."""
        target = (path or self.storage_state_path or "").strip()
        if not target or self.context is None:
            return None
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        await self.context.storage_state(path=target)
        return target

    async def stop(self) -> None:
        try:
            await self.save_storage_state()
        except Exception:
            pass
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
