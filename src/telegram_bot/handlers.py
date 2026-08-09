"""Telegram command/callback handlers — UI only; all logic via API client."""

from __future__ import annotations

import re
from typing import Any

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from src.telegram_bot.api_client import PredictionApiClient
from src.telegram_bot.errors import TelegramBotError
from src.telegram_bot import formatters as fmt
from src.telegram_bot.keyboards import (
    fiveparreh_block_keyboard,
    fiveparreh_confirm_keyboard,
    horse_toggle_keyboard,
    main_menu_keyboard,
    races_keyboard,
)
from src.telegram_bot.race_program import consecutive_from_start, valid_starting_races
from src.telegram_bot.state import FiveParrehSession, SessionStore

_ID_RE = re.compile(r"^\d{1,12}$")
_MAX_MESSAGE = 3500


def _client(context: ContextTypes.DEFAULT_TYPE) -> PredictionApiClient:
    return context.application.bot_data["api_client"]


def _sessions(context: ContextTypes.DEFAULT_TYPE) -> SessionStore:
    return context.application.bot_data["sessions"]


def _settings(context: ContextTypes.DEFAULT_TYPE) -> Any:
    return context.application.bot_data["settings"]


async def _reply(update: Update, text: str, **kwargs: Any) -> None:
    text = fmt.truncate(text, _MAX_MESSAGE)
    if update.callback_query:
        await update.callback_query.answer()
        if update.callback_query.message:
            await update.callback_query.message.reply_text(text, **kwargs)
        return
    if update.effective_message:
        await update.effective_message.reply_text(text, **kwargs)


async def _safe(update: Update, context: ContextTypes.DEFAULT_TYPE, coro_factory) -> None:
    try:
        await coro_factory()
    except TelegramBotError as exc:
        logger.info("user_error chat={} msg={}", getattr(update.effective_chat, "id", None), exc.user_message)
        await _reply(update, exc.user_message, reply_markup=main_menu_keyboard())
    except Exception:  # noqa: BLE001
        logger.exception("Unhandled telegram handler error")
        await _reply(
            update,
            "⚠️ خطای داخلی رخ داد. لطفاً دوباره تلاش کنید.",
            reply_markup=main_menu_keyboard(),
        )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def run() -> None:
        logger.info("command=start chat={}", getattr(update.effective_chat, "id", None))
        await _reply(update, fmt.welcome_text(), reply_markup=main_menu_keyboard())

    await _safe(update, context, run)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def run() -> None:
        logger.info("command=help chat={}", getattr(update.effective_chat, "id", None))
        await _reply(update, fmt.help_text(), reply_markup=main_menu_keyboard())

    await _safe(update, context, run)


async def cmd_races(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def run() -> None:
        logger.info("command=races chat={}", getattr(update.effective_chat, "id", None))
        settings = _settings(context)
        payload = _client(context).list_races(limit=settings.telegram_races_page_size, offset=0)
        text = fmt.format_race_list(payload)
        races = payload.get("races") or []
        kb = races_keyboard(races, prefix="predict") if races else main_menu_keyboard()
        await _reply(update, text, reply_markup=kb)

    await _safe(update, context, run)


async def cmd_predict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def run() -> None:
        args = context.args or []
        logger.info("command=predict chat={} args={}", getattr(update.effective_chat, "id", None), args)
        if args:
            rid = args[0].strip()
            if not _ID_RE.match(rid):
                await _reply(update, "⚠️ شناسهٔ مسابقه نامعتبر است.")
                return
            await _send_prediction(update, context, rid)
            return
        settings = _settings(context)
        payload = _client(context).list_races(limit=settings.telegram_races_page_size, offset=0)
        races = payload.get("races") or []
        if not races:
            await _reply(update, "در حال حاضر مسابقه‌ای در دسترس نیست.", reply_markup=main_menu_keyboard())
            return
        await _reply(
            update,
            "یک مسابقه برای پیش‌بینی انتخاب کنید:",
            reply_markup=races_keyboard(races, prefix="predict"),
        )

    await _safe(update, context, run)


async def _send_prediction(update: Update, context: ContextTypes.DEFAULT_TYPE, race_id: str) -> None:
    payload = _client(context).get_race_prediction(race_id)
    await _reply(update, fmt.format_prediction(payload), reply_markup=main_menu_keyboard())


async def cmd_horse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def run() -> None:
        args = context.args or []
        logger.info("command=horse chat={} args={}", getattr(update.effective_chat, "id", None), args)
        if not args:
            await _reply(
                update,
                "شناسه اسب را بفرستید.\nمثال: /horse 3470",
                reply_markup=main_menu_keyboard(),
            )
            return
        hid = args[0].strip()
        if not _ID_RE.match(hid):
            await _reply(update, "⚠️ شناسهٔ اسب نامعتبر است.")
            return
        payload = _client(context).get_horse(hid)
        await _reply(update, fmt.format_horse(payload), reply_markup=main_menu_keyboard())

    await _safe(update, context, run)


async def cmd_fiveparreh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def run() -> None:
        user = update.effective_user
        if not user:
            return
        logger.info("command=fiveparreh chat={}", getattr(update.effective_chat, "id", None))
        store = _sessions(context)
        store.clear(user.id)

        # Fetch a wide catalog so meeting sequences can be resolved (not race_id+1).
        catalog: list[dict[str, Any]] = []
        offset = 0
        page_size = 100
        while offset < 500:
            payload = _client(context).list_races(limit=page_size, offset=offset)
            batch = list(payload.get("races") or [])
            catalog.extend(batch)
            total = int(payload.get("total") or 0)
            offset += page_size
            if not batch or offset >= total:
                break

        starts = valid_starting_races(catalog, count=5)
        if not starts:
            await _reply(
                update,
                "در حال حاضر برنامهٔ معتبری با ۵ کورس متوالی در دسترس نیست.",
                reply_markup=main_menu_keyboard(),
            )
            return

        store.set(user.id, FiveParrehSession(step="pick_start", race_index=0, catalog=catalog))
        await _reply(
            update,
            "🎟 پنج‌پره\n\n"
            "یک کورس شروع را انتخاب کنید.\n"
            "۴ کورس بعدی همان برنامه به‌صورت خودکار انتخاب می‌شوند.",
            reply_markup=races_keyboard(starts[:30], prefix="fp_start"),
        )

    await _safe(update, context, run)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def run() -> None:
        query = update.callback_query
        if not query or not query.data:
            return
        data = query.data.strip()
        if len(data) > 64:
            await _reply(update, "⚠️ درخواست نامعتبر است.")
            return
        logger.info("callback={} chat={}", data, getattr(update.effective_chat, "id", None))

        if data == "menu:home" or data == "menu:start":
            await _reply(update, fmt.welcome_text(), reply_markup=main_menu_keyboard())
            return
        if data == "menu:help":
            await _reply(update, fmt.help_text(), reply_markup=main_menu_keyboard())
            return
        if data == "menu:races":
            await cmd_races(update, context)
            return
        if data == "menu:predict":
            context.args = []
            await cmd_predict(update, context)
            return
        if data == "menu:horse":
            context.args = []
            await cmd_horse(update, context)
            return
        if data == "menu:fiveparreh":
            await cmd_fiveparreh(update, context)
            return

        if data.startswith("predict:"):
            rid = data.split(":", 1)[1]
            if not _ID_RE.match(rid):
                await _reply(update, "⚠️ شناسهٔ مسابقه نامعتبر است.")
                return
            await _send_prediction(update, context, rid)
            return

        if data.startswith("fp_start:"):
            await _fp_pick_start(update, context, data.split(":", 1)[1])
            return
        if data == "fp:block_ok":
            await _fp_begin_horse_selection(update, context)
            return
        if data.startswith("fp:tog:"):
            await _fp_toggle(update, context, data.split(":", 2)[2])
            return
        if data == "fp:ok":
            await _fp_confirm_horses(update, context)
            return
        if data == "fp:confirm":
            await _fp_submit(update, context)
            return
        if data == "fp:cancel":
            user = update.effective_user
            if user:
                _sessions(context).clear(user.id)
            await _reply(update, "جلسه پنج‌پره لغو شد.", reply_markup=main_menu_keyboard())
            return

        await _reply(update, "⚠️ دستور ناشناخته.", reply_markup=main_menu_keyboard())

    await _safe(update, context, run)


async def _fp_pick_start(update: Update, context: ContextTypes.DEFAULT_TYPE, race_id: str) -> None:
    user = update.effective_user
    if not user:
        return
    if not _ID_RE.match(race_id):
        await _reply(update, "⚠️ شناسهٔ مسابقه نامعتبر است.")
        return
    session = _sessions(context).get(user.id)
    if not session or session.step != "pick_start":
        await _reply(update, "جلسه پنج‌پره منقضی شده. /fiveparreh را دوباره بزنید.")
        return

    window = consecutive_from_start(session.catalog, race_id, count=5)
    if not window:
        await _reply(
            update,
            "⚠️ از این کورس شروع، ۵ کورس متوالی در همان برنامه موجود نیست.",
            reply_markup=main_menu_keyboard(),
        )
        return

    race_ids = [str(r.get("race_id")) for r in window]
    session.race_ids = race_ids
    session.horses_by_race = {rid: [] for rid in race_ids}
    session.race_index = 0
    session.step = "confirm_block"
    session.candidates = []
    session.touch()
    _sessions(context).set(user.id, session)

    await _reply(
        update,
        fmt.format_fiveparreh_race_block(race_ids),
        reply_markup=fiveparreh_block_keyboard(),
    )


async def _fp_begin_horse_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    session = _sessions(context).get(user.id)
    if not session or session.step != "confirm_block" or len(session.race_ids) != 5:
        await _reply(update, "جلسه پنج‌پره منقضی شده. /fiveparreh را دوباره بزنید.")
        return
    session.race_index = 0
    session.step = "pick_horses"
    session.touch()
    _sessions(context).set(user.id, session)
    await _fp_prompt_horses(update, context, session)


async def _fp_prompt_horses(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: FiveParrehSession,
) -> None:
    rid = session.current_race_id()
    if not rid:
        await _reply(update, "⚠️ کورس نامعتبر است.")
        return
    prediction = _client(context).get_race_prediction(rid)
    candidates = list(prediction.get("prediction") or [])
    if not candidates:
        await _reply(update, f"⚠️ برای کورس {rid} اسبی جهت انتخاب نیست.")
        return
    session.candidates = candidates
    session.touch()
    user = update.effective_user
    if user:
        _sessions(context).set(user.id, session)
    text = (
        f"کورس {session.race_index + 1} از ۵ — انتخاب اسب‌ها\n"
        f"(مسابقه {rid})\n\n"
        "حداقل یک اسب انتخاب کنید."
    )
    await _reply(
        update,
        text,
        reply_markup=horse_toggle_keyboard(candidates, set(session.selected_for_current())),
    )


async def _fp_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE, horse_id: str) -> None:
    user = update.effective_user
    if not user:
        return
    if not _ID_RE.match(horse_id):
        await _reply(update, "⚠️ شناسهٔ اسب نامعتبر است.")
        return
    session = _sessions(context).get(user.id)
    if not session or session.step != "pick_horses":
        await _reply(update, "جلسه پنج‌پره منقضی شده. /fiveparreh را دوباره بزنید.")
        return
    session.toggle_horse(horse_id)
    _sessions(context).set(user.id, session)
    selected = set(session.selected_for_current())
    # Edit keyboard in place when possible
    query = update.callback_query
    if query and query.message:
        await query.answer()
        await query.edit_message_reply_markup(
            reply_markup=horse_toggle_keyboard(session.candidates, selected)
        )
        return
    await _reply(
        update,
        "انتخاب به‌روز شد.",
        reply_markup=horse_toggle_keyboard(session.candidates, selected),
    )


async def _fp_confirm_horses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    session = _sessions(context).get(user.id)
    if not session or session.step != "pick_horses" or len(session.race_ids) != 5:
        await _reply(update, "جلسه پنج‌پره منقضی شده. /fiveparreh را دوباره بزنید.")
        return
    selected = session.selected_for_current()
    if not selected:
        await _reply(update, "⚠️ حداقل یک اسب برای این کورس لازم است.")
        return

    session.race_index += 1
    if session.race_index < 5:
        session.candidates = []
        session.touch()
        _sessions(context).set(user.id, session)
        await _fp_prompt_horses(update, context, session)
        return

    # Horses selected for all five locked races → cost confirmation
    session.step = "confirm"
    session.touch()
    _sessions(context).set(user.id, session)
    settings = _settings(context)
    price = settings.telegram_default_price_per_combination
    text = fmt.format_fiveparreh_confirm(
        session.selections_per_race(),
        total_combinations=session.total_combinations_estimate(),
        price_per_combination=price,
    )
    await _reply(update, text, reply_markup=fiveparreh_confirm_keyboard())


async def _fp_submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    session = _sessions(context).get(user.id)
    if not session or session.step != "confirm" or len(session.race_ids) != 5:
        await _reply(update, "جلسه پنج‌پره منقضی شده. /fiveparreh را دوباره بزنید.")
        return
    if any(len(session.horses_by_race.get(rid, [])) < 1 for rid in session.race_ids):
        await _reply(update, "⚠️ همهٔ پنج کورس باید حداقل یک اسب داشته باشند.")
        return

    settings = _settings(context)
    price = settings.telegram_default_price_per_combination
    # Combination generation happens ONLY in the API / Five-Parreh engine.
    result = _client(context).generate_five_parreh(
        session.to_api_payload(),
        price_per_combination=price,
        include_combinations=True,
        max_combinations_in_response=20,
    )
    _sessions(context).clear(user.id)
    await _reply(update, fmt.format_fiveparreh_result(result), reply_markup=main_menu_keyboard())
