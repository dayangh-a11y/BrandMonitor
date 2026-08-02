from __future__ import annotations

import os
import re
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from collectors.google_maps import locators as L
from collectors.google_maps.parser import GoogleMapsParser
from collectors.google_maps.scroll_engine import ScrollEngine
from core.browser import BrowserManager
from models.branch import Branch
from models.review import Review


class GoogleMapsCollector:
    def __init__(
        self,
        *,
        headless: bool | None = None,
        max_branches: int | None = None,
        max_reviews_per_branch: int | None = None,
        scroll_pause_ms: int | None = None,
    ):
        self.browser = BrowserManager(headless=headless)
        self.page: Page | None = None
        self.parser = GoogleMapsParser()
        self.scroll: ScrollEngine | None = None

        self.max_branches = max_branches or int(os.getenv("MAX_BRANCHES", "3"))
        self.max_reviews_per_branch = max_reviews_per_branch or int(
            os.getenv("MAX_REVIEWS_PER_BRANCH", "20")
        )
        self.scroll_pause_ms = scroll_pause_ms or int(os.getenv("SCROLL_PAUSE_MS", "1200"))

    async def start(self) -> None:
        self.page = await self.browser.start()
        self.scroll = ScrollEngine(self.page, pause_ms=self.scroll_pause_ms)
        await self.page.goto("https://www.google.com/maps", wait_until="domcontentloaded")
        await self._dismiss_consent()
        await self.page.wait_for_timeout(1500)

    async def stop(self) -> None:
        await self.browser.stop()

    async def search(self, brand_name: str) -> None:
        assert self.page is not None
        search_box = self.page.locator(L.GoogleMapsLocators.SEARCH_INPUT).first
        await search_box.wait_for(state="visible", timeout=20000)
        await search_box.fill("")
        await search_box.fill(brand_name)
        await search_box.press("Enter")
        await self.page.wait_for_timeout(4000)
        await self._dismiss_consent()

        # Wait for either a feed of results or a single place page.
        try:
            await self.page.locator(L.GoogleMapsLocators.RESULTS_FEED).first.wait_for(
                state="visible",
                timeout=12000,
            )
        except PlaywrightTimeoutError:
            await self.page.locator(L.GoogleMapsLocators.PLACE_TITLE).first.wait_for(
                state="visible",
                timeout=12000,
            )

    async def collect_branches(self, company_name: str = "") -> list[Branch]:
        assert self.page is not None
        assert self.scroll is not None

        feed = self.page.locator(L.GoogleMapsLocators.RESULTS_FEED).first
        if await feed.count() == 0:
            branch = await self._extract_current_place(company_name=company_name)
            return [branch] if branch else []

        await self.scroll.scroll_feed(feed, rounds=min(10, max(3, self.max_branches)))

        cards = self.page.locator(L.GoogleMapsLocators.RESULT_CARD)
        if await cards.count() == 0:
            cards = self.page.locator(L.GoogleMapsLocators.RESULT_CARD_FALLBACK)

        total = await cards.count()
        limit = min(total, self.max_branches)
        print(f"\nFound {total} branch cards, collecting {limit}\n")

        branches: list[Branch] = []
        for index in range(limit):
            card = cards.nth(index)
            branch = await self._extract_branch_from_card(card, company_name=company_name)
            if branch:
                branches.append(branch)
                print(f"[branch] {branch.name} | {branch.rating} | {branch.review_count}")
        return branches

    async def collect_reviews_for_branch(self, branch: Branch) -> list[Review]:
        assert self.page is not None
        assert self.scroll is not None

        if branch.maps_url:
            await self.page.goto(branch.maps_url, wait_until="domcontentloaded")
            await self.page.wait_for_timeout(2500)
            await self._dismiss_consent()

        opened = await self._open_reviews_panel()
        if not opened:
            print(f"[reviews] could not open reviews for {branch.name}")
            return []

        await self._scroll_reviews_panel()
        reviews = await self._parse_visible_reviews(branch_name=branch.name)
        print(f"[reviews] {branch.name}: collected {len(reviews)}")
        return reviews[: self.max_reviews_per_branch]

    async def collect(
        self,
        brand_name: str,
        *,
        with_reviews: bool = True,
    ) -> tuple[list[Branch], list[Review]]:
        await self.search(brand_name)
        branches = await self.collect_branches(company_name=brand_name)
        all_reviews: list[Review] = []

        if not with_reviews:
            return branches, all_reviews

        for branch in branches:
            reviews = await self.collect_reviews_for_branch(branch)
            all_reviews.extend(reviews)

        return branches, all_reviews

    async def _extract_branch_from_card(
        self,
        card: Locator,
        company_name: str = "",
    ) -> Branch | None:
        assert self.page is not None

        href = await card.get_attribute("href") or ""
        aria = await card.get_attribute("aria-label") or ""

        # Clicking opens the place pane; then we read richer details.
        try:
            await card.click(timeout=8000)
            await self.page.wait_for_timeout(2200)
        except Exception:
            return self.parser.parse_branch(
                name=aria,
                rating=0,
                reviews=0,
                maps_url=href,
                place_id=self._extract_place_id(href),
                company_name=company_name,
            )

        branch = await self._extract_current_place(
            company_name=company_name,
            fallback_name=aria,
            fallback_url=href,
        )
        return branch

    async def _extract_current_place(
        self,
        *,
        company_name: str = "",
        fallback_name: str = "",
        fallback_url: str = "",
    ) -> Branch | None:
        assert self.page is not None

        name = fallback_name
        title = self.page.locator(L.GoogleMapsLocators.PLACE_TITLE).first
        if await title.count():
            try:
                name = (await title.inner_text(timeout=3000)).strip() or name
            except Exception:
                pass

        rating_text = ""
        rating_node = self.page.locator(L.GoogleMapsLocators.PLACE_RATING).first
        if await rating_node.count():
            try:
                rating_text = await rating_node.inner_text(timeout=2000)
            except Exception:
                rating_text = ""

        review_count_text = ""
        review_wrap = self.page.locator(L.GoogleMapsLocators.PLACE_REVIEW_COUNT).first
        if await review_wrap.count():
            try:
                review_count_text = await review_wrap.inner_text(timeout=2000)
            except Exception:
                review_count_text = ""

        address = ""
        address_btn = self.page.locator('button[data-item-id="address"]').first
        if await address_btn.count():
            try:
                address = (await address_btn.get_attribute("aria-label") or "").replace(
                    "Address:", ""
                ).replace("آدرس:", "").strip()
            except Exception:
                address = ""

        maps_url = self.page.url or fallback_url
        return self.parser.parse_branch(
            name=name,
            rating=rating_text,
            reviews=review_count_text,
            address=address,
            maps_url=maps_url,
            place_id=self._extract_place_id(maps_url),
            company_name=company_name,
        )

    async def _open_reviews_panel(self) -> bool:
        assert self.page is not None

        for selector in L.GoogleMapsLocators.REVIEWS_TAB_CANDIDATES:
            button = self.page.locator(selector).first
            if await button.count() == 0:
                continue
            try:
                await button.click(timeout=4000)
                await self.page.wait_for_timeout(2000)
                if await self.page.locator(L.GoogleMapsLocators.REVIEW_CARD).count() > 0:
                    return True
            except Exception:
                continue

        # Fallback: click the review-count control in the rating header.
        more = self.page.locator("button", has_text=re.compile(r"review|نظر", re.I)).first
        if await more.count():
            try:
                await more.click(timeout=4000)
                await self.page.wait_for_timeout(2000)
                return await self.page.locator(L.GoogleMapsLocators.REVIEW_CARD).count() > 0
            except Exception:
                return False
        return False

    async def _scroll_reviews_panel(self) -> None:
        assert self.page is not None
        assert self.scroll is not None

        # Reviews usually live in a dialog/pane with role=main or a scrollable section.
        candidates = [
            self.page.locator('div[role="main"]').first,
            self.page.locator("div.m6QErb.DxyBCb.kA9KIf.dS8AEf").first,
            self.page.locator("div.m6QErb.DxyBCb").first,
        ]

        for container in candidates:
            if await container.count() == 0:
                continue
            try:
                await self.scroll.scroll_until_end(
                    container,
                    max_rounds=max(6, self.max_reviews_per_branch // 2),
                    stable_rounds=2,
                )
                return
            except Exception:
                continue

        # Last resort: page-level mouse wheel.
        for _ in range(8):
            await self.page.mouse.wheel(0, 2400)
            await self.page.wait_for_timeout(self.scroll_pause_ms)

    async def _parse_visible_reviews(self, branch_name: str) -> list[Review]:
        assert self.page is not None
        cards = self.page.locator(L.GoogleMapsLocators.REVIEW_CARD)
        count = await cards.count()
        reviews: list[Review] = []

        for index in range(min(count, self.max_reviews_per_branch)):
            card = cards.nth(index)

            more = card.locator(L.GoogleMapsLocators.REVIEW_MORE).first
            if await more.count():
                try:
                    await more.click(timeout=1000)
                except Exception:
                    pass

            author = ""
            author_node = card.locator(L.GoogleMapsLocators.REVIEW_AUTHOR).first
            if await author_node.count():
                try:
                    author = (await author_node.inner_text()).strip()
                except Exception:
                    author = ""

            rating = 0.0
            rating_node = card.locator(L.GoogleMapsLocators.REVIEW_RATING).first
            if await rating_node.count():
                aria = await rating_node.get_attribute("aria-label") or ""
                rating = self.parser._to_float(aria)

            published_at = ""
            date_node = card.locator(L.GoogleMapsLocators.REVIEW_DATE).first
            if await date_node.count():
                try:
                    published_at = (await date_node.inner_text()).strip()
                except Exception:
                    published_at = ""

            text = ""
            text_node = card.locator(L.GoogleMapsLocators.REVIEW_TEXT).first
            if await text_node.count():
                try:
                    text = (await text_node.inner_text()).strip()
                except Exception:
                    text = ""

            external_id = await card.get_attribute("data-review-id") or ""
            review = self.parser.parse_review(
                author=author,
                rating=rating,
                text=text,
                published_at=published_at,
                external_id=external_id,
                branch_name=branch_name,
            )
            if review:
                reviews.append(review)

        return reviews

    async def _dismiss_consent(self) -> None:
        assert self.page is not None
        for selector in L.GoogleMapsLocators.CONSENT_BUTTONS:
            button = self.page.locator(selector).first
            if await button.count() == 0:
                continue
            try:
                await button.click(timeout=2000)
                await self.page.wait_for_timeout(1000)
                return
            except Exception:
                continue

        # Consent sometimes opens inside an iframe.
        for frame in self.page.frames:
            for selector in L.GoogleMapsLocators.CONSENT_BUTTONS:
                button = frame.locator(selector).first
                try:
                    if await button.count() == 0:
                        continue
                    await button.click(timeout=2000)
                    await self.page.wait_for_timeout(1000)
                    return
                except Exception:
                    continue

    def _extract_place_id(self, url: str) -> str:
        if not url:
            return ""
        match = re.search(r"!1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)", url)
        if match:
            return match.group(1)
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if "q" in query and query["q"]:
            return query["q"][0]
        return ""
