from playwright.async_api import Page


class ScrollEngine:

    def __init__(self, page: Page):
        self.page = page

    async def scroll_until_end(self):
        pass