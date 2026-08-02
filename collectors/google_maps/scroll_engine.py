from playwright.async_api import Locator, Page


class ScrollEngine:
    def __init__(self, page: Page, pause_ms: int = 1200):
        self.page = page
        self.pause_ms = pause_ms

    async def scroll_until_end(
        self,
        container: Locator,
        *,
        max_rounds: int = 40,
        stable_rounds: int = 3,
    ) -> int:
        """Scroll a scrollable container until content stops growing."""
        previous_count = -1
        same_count_rounds = 0
        rounds = 0

        while rounds < max_rounds:
            rounds += 1
            current_count = await container.evaluate(
                """(el) => {
                    el.scrollTop = el.scrollHeight;
                    return el.scrollHeight;
                }"""
            )
            await self.page.wait_for_timeout(self.pause_ms)

            if current_count == previous_count:
                same_count_rounds += 1
            else:
                same_count_rounds = 0
                previous_count = current_count

            if same_count_rounds >= stable_rounds:
                break

        return rounds

    async def scroll_feed(self, feed: Locator, rounds: int = 8) -> None:
        for _ in range(rounds):
            await feed.evaluate("(el) => { el.scrollTop = el.scrollHeight; }")
            await self.page.wait_for_timeout(self.pause_ms)
