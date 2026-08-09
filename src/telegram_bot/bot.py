"""Telegram bot entrypoint (independent of FastAPI process)."""

from __future__ import annotations

import sys

from loguru import logger
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from src.telegram_bot.api_client import PredictionApiClient
from src.telegram_bot.config import TelegramBotSettings, get_telegram_settings
from src.telegram_bot.handlers import (
    cmd_fiveparreh,
    cmd_help,
    cmd_horse,
    cmd_horsevs,
    cmd_predict,
    cmd_races,
    cmd_start,
    on_callback,
    on_text_message,
)
from src.telegram_bot.state import HorseLookupStore, HorseVsStore, SessionStore


def build_application(settings: TelegramBotSettings | None = None) -> Application:
    settings = settings or get_telegram_settings()
    token = settings.require_token()
    client = PredictionApiClient(
        settings.api_base_url,
        timeout_seconds=settings.request_timeout_seconds,
    )
    sessions = SessionStore(ttl_seconds=settings.telegram_session_ttl_seconds)
    horsevs = HorseVsStore(ttl_seconds=settings.telegram_session_ttl_seconds)
    horse_lookup = HorseLookupStore()

    async def _post_shutdown(application: Application) -> None:
        client.close()

    app = (
        Application.builder()
        .token(token)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.bot_data["settings"] = settings
    app.bot_data["api_client"] = client
    app.bot_data["sessions"] = sessions
    app.bot_data["horsevs"] = horsevs
    app.bot_data["horse_lookup"] = horse_lookup
    # Race program / discovery is via API client only (no local DB reads).

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("races", cmd_races))
    app.add_handler(CommandHandler("predict", cmd_predict))
    app.add_handler(CommandHandler("horsevs", cmd_horsevs))
    app.add_handler(CommandHandler("horse", cmd_horse))
    app.add_handler(CommandHandler("fiveparreh", cmd_fiveparreh))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_message))
    return app


def main() -> None:
    settings = get_telegram_settings()
    try:
        settings.require_token()
    except RuntimeError as exc:
        logger.error("{}", exc)
        sys.exit(1)

    logger.info(
        "Starting Telegram bot → API {} (timeout={}s)",
        settings.api_base_url,
        settings.request_timeout_seconds,
    )
    application = build_application(settings)
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
