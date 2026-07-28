from playwright.async_api import Locator

from core.browser import BrowserManager
from collectors.google_maps.parser import GoogleMapsParser
from collectors.google_maps import locators


class GoogleMapsCollector:

    def __init__(self):
        self.browser = BrowserManager()
        self.page = None
        self.parser = GoogleMapsParser()

    async def start(self):
        self.page = await self.browser.start()
        await self.page.goto("https://www.google.com/maps")

    async def search(self, brand_name: str):

        search_box = self.page.get_by_role(locators.SEARCH_BOX)

        await search_box.fill("")
        await search_box.fill(brand_name)
        await search_box.press("Enter")

        await self.page.wait_for_timeout(5000)

    async def get_cards(self):

        return self.page.get_by_role(locators.RESULT_CARD)

    async def collect(self):

        cards = await self.get_cards()

        count = await cards.count()

        branches = []

        print(f"\nFound {count} branches\n")

        for i in range(count):

            card = cards.nth(i)

            branch = await self.extract_branch(card)

            if branch:
                branches.append(branch)

        return branches

    async def extract_branch(self, card: Locator):

        try:

            name = await card.locator(locators.TITLE).inner_text()

        except:

            name = ""

        try:

            rating = await card.locator(locators.RATING).inner_text()

        except:

            rating = ""

        try:

            reviews = await card.locator(locators.REVIEWS).inner_text()

        except:

            reviews = ""

        try:

            blocks = card.locator("div.W4Efsd")

            address = ""

            if await blocks.count() >= 2:
                address = await blocks.nth(1).inner_text()

        except:

            address = ""

        branch = self.parser.parse(
            name,
            rating,
            reviews,
            address
        )

        print(branch)

        return branch

    async def stop(self):
        await self.browser.stop()