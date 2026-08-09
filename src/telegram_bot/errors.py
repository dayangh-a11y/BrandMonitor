"""User-facing errors for the Telegram bot (no stack traces)."""

from __future__ import annotations


class TelegramBotError(Exception):
    """Base bot error with a safe Persian user message."""

    def __init__(self, user_message: str) -> None:
        self.user_message = user_message
        super().__init__(user_message)


class ApiUnavailableError(TelegramBotError):
    def __init__(self) -> None:
        super().__init__(
            "⚠️ سرویس تحلیل در حال حاضر در دسترس نیست. لطفاً کمی بعد دوباره تلاش کنید."
        )


class RaceNotFoundError(TelegramBotError):
    def __init__(self) -> None:
        super().__init__("⚠️ مسابقه موردنظر پیدا نشد.")


class HorseNotFoundError(TelegramBotError):
    def __init__(self) -> None:
        super().__init__("⚠️ اطلاعات این اسب پیدا نشد.")


class DatasetUnavailableError(TelegramBotError):
    def __init__(self) -> None:
        super().__init__("⚠️ داده اصلی مسابقات هنوز برای محیط عملیاتی فعال نشده است.")


class ValidationUserError(TelegramBotError):
    pass
