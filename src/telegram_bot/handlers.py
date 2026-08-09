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
from src.telegram_bot.five_parreh_events import event_from_api_payload
from src.telegram_bot.keyboards import (
    fiveparreh_confirm_keyboard,
    fiveparreh_event_keyboard,
    fiveparreh_start_predict_keyboard,
    horse_pick_keyboard,
    horse_search_keyboard,
    horse_toggle_keyboard,
    main_menu_keyboard,
    meeting_races_keyboard,
    upcoming_meetings_keyboard,
)
from src.telegram_bot.state import (
    FiveParrehSession,
    HorseLookupStore,
    HorseVsSession,
    HorseVsStore,
    SessionStore,
)

_ID_RE = re.compile(r"^\d{1,12}$")
_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")
_MEETING_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")
_MAX_MESSAGE = 3500


def _client(context: ContextTypes.DEFAULT_TYPE) -> PredictionApiClient:
    return context.application.bot_data["api_client"]


def _sessions(context: ContextTypes.DEFAULT_TYPE) -> SessionStore:
    return context.application.bot_data["sessions"]


def _horsevs(context: ContextTypes.DEFAULT_TYPE) -> HorseVsStore:
    return context.application.bot_data["horsevs"]


def _settings(context: ContextTypes.DEFAULT_TYPE) -> Any:
    return context.application.bot_data["settings"]


def _horse_lookup(context: ContextTypes.DEFAULT_TYPE) -> HorseLookupStore:
    return context.application.bot_data["horse_lookup"]


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
    """Alias for upcoming race meetings (same race-program source as /predict)."""
    await cmd_predict(update, context)


async def cmd_predict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def run() -> None:
        logger.info("command=predict chat={}", getattr(update.effective_chat, "id", None))
        # Never ask the user for race_id — only future meetings from the race program.
        payload = _client(context).list_upcoming_meetings(days=7)
        meetings = payload.get("meetings") or []
        text = fmt.format_upcoming_meetings(payload)
        if not meetings:
            await _reply(update, text, reply_markup=main_menu_keyboard())
            return
        await _reply(update, text, reply_markup=upcoming_meetings_keyboard(meetings))

    await _safe(update, context, run)


async def _show_meeting_races(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    meeting_id: str,
) -> None:
    meeting = _client(context).get_upcoming_meeting(meeting_id)
    races = meeting.get("races") or []
    # Cache human-readable race meta for prediction display (ids stay out of UX copy).
    meta_store: dict[str, dict[str, Any]] = context.application.bot_data.setdefault(
        "predict_meta", {}
    )
    location = meeting.get("location") or meeting.get("track") or meeting.get("city")
    for race in races:
        rid = str(race.get("race_id") or "").strip()
        if not rid:
            continue
        meta_store[rid] = {
            "label": race.get("label"),
            "race_number": race.get("race_number"),
            "display_date": meeting.get("display_date"),
            "track": location,
        }
    text = fmt.format_meeting_races(meeting)
    if not races:
        await _reply(update, text, reply_markup=main_menu_keyboard())
        return
    await _reply(update, text, reply_markup=meeting_races_keyboard(meeting))


async def _send_prediction(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    race_id: str,
    *,
    meta: dict[str, Any] | None = None,
) -> None:
    payload = _client(context).get_race_prediction(race_id)
    await _reply(
        update,
        fmt.format_prediction(payload, meta=meta),
        reply_markup=main_menu_keyboard(),
    )


async def cmd_horse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def run() -> None:
        user = update.effective_user
        if not user:
            return
        args = context.args or []
        logger.info("command=horse chat={} args={}", getattr(update.effective_chat, "id", None), args)
        # Name may be provided as /horse دنزی بوی — never ask for horse_id.
        if args:
            await _search_and_offer_horses(update, context, " ".join(args))
            return
        _horse_lookup(context).ask(user.id)
        await _reply(
            update,
            "🐎 نام اسب را بنویسید.\nمثال: دنزی بوی",
            reply_markup=main_menu_keyboard(),
        )

    await _safe(update, context, run)


async def on_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Receive horse name after /horse prompt (not a command)."""

    async def run() -> None:
        user = update.effective_user
        message = update.effective_message
        if not user or not message or not message.text:
            return
        if not _horse_lookup(context).is_waiting(user.id):
            return
        name = message.text.strip()
        if not name or name.startswith("/"):
            return
        _horse_lookup(context).clear(user.id)
        await _search_and_offer_horses(update, context, name)

    await _safe(update, context, run)


async def _search_and_offer_horses(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    name: str,
) -> None:
    payload = _client(context).search_horses(name, limit=15)
    horses = payload.get("horses") or []
    text = fmt.format_horse_search_results(payload)
    if not horses:
        await _reply(update, text, reply_markup=main_menu_keyboard())
        return
    # Single exact-ish result: still show button (name only) for confirmation.
    await _reply(update, text, reply_markup=horse_search_keyboard(horses))


async def _send_horse_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE, horse_id: str) -> None:
    payload = _client(context).get_horse(horse_id)
    await _reply(update, fmt.format_horse(payload), reply_markup=main_menu_keyboard())


async def cmd_horsevs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def run() -> None:
        user = update.effective_user
        if not user:
            return
        logger.info("command=horsevs chat={}", getattr(update.effective_chat, "id", None))
        store = _horsevs(context)
        store.clear(user.id)
        store.set(user.id, HorseVsSession(step="pick_meeting"))
        payload = _client(context).list_upcoming_meetings(days=7)
        meetings = payload.get("meetings") or []
        text = fmt.format_upcoming_meetings(payload)
        if not meetings:
            await _reply(update, text, reply_markup=main_menu_keyboard())
            return
        text = "⚔️ اسب مقابل اسب\n\n" + text
        await _reply(
            update,
            text,
            reply_markup=upcoming_meetings_keyboard(meetings, callback_prefix="hvs_mtg"),
        )

    await _safe(update, context, run)


async def cmd_fiveparreh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def run() -> None:
        user = update.effective_user
        if not user:
            return
        logger.info("command=fiveparreh chat={}", getattr(update.effective_chat, "id", None))
        store = _sessions(context)
        store.clear(user.id)

        # Same race-program API source as /predict — never invent from race_id sequences.
        payload = _client(context).list_five_parreh_events()
        events = payload.get("events") or []
        store.set(user.id, FiveParrehSession(step="pick_event"))
        text = fmt.format_future_fiveparreh_events(events)
        if not events:
            await _reply(update, text, reply_markup=main_menu_keyboard())
            return
        await _reply(update, text, reply_markup=fiveparreh_event_keyboard(events))

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
        if data == "menu:predict":
            context.args = []
            await cmd_predict(update, context)
            return
        if data == "menu:horsevs":
            await cmd_horsevs(update, context)
            return
        if data == "menu:horse":
            context.args = []
            await cmd_horse(update, context)
            return
        if data == "menu:fiveparreh":
            await cmd_fiveparreh(update, context)
            return

        if data.startswith("mtg:"):
            mid = data.split(":", 1)[1]
            if not _MEETING_ID_RE.match(mid):
                await _reply(update, "⚠️ جلسهٔ مسابقه نامعتبر است.")
                return
            await _show_meeting_races(update, context, mid)
            return

        if data.startswith("prd:"):
            # Internal race_id in callback only — never typed by the user.
            rid = data.split(":", 1)[1]
            if not _ID_RE.match(rid):
                await _reply(update, "⚠️ انتخاب مسابقه نامعتبر است.")
                return
            meta = context.application.bot_data.get("predict_meta", {}).get(rid)
            await _send_prediction(update, context, rid, meta=meta)
            return

        if data.startswith("hvs_mtg:"):
            mid = data.split(":", 1)[1]
            if not _MEETING_ID_RE.match(mid):
                await _reply(update, "⚠️ جلسهٔ مسابقه نامعتبر است.")
                return
            await _hvs_select_meeting(update, context, mid)
            return
        if data.startswith("hvs_race:"):
            rid = data.split(":", 1)[1]
            if not _ID_RE.match(rid):
                await _reply(update, "⚠️ انتخاب مسابقه نامعتبر است.")
                return
            await _hvs_select_race(update, context, rid)
            return
        if data.startswith("hvs_a:"):
            hid = data.split(":", 1)[1]
            if not _ID_RE.match(hid):
                await _reply(update, "⚠️ انتخاب اسب نامعتبر است.")
                return
            await _hvs_pick_a(update, context, hid)
            return
        if data.startswith("hvs_b:"):
            hid = data.split(":", 1)[1]
            if not _ID_RE.match(hid):
                await _reply(update, "⚠️ انتخاب اسب نامعتبر است.")
                return
            await _hvs_pick_b(update, context, hid)
            return
        if data == "hvs:cancel":
            user = update.effective_user
            if user:
                _horsevs(context).clear(user.id)
            await _reply(update, "مقایسه لغو شد.", reply_markup=main_menu_keyboard())
            return

        if data.startswith("horse_sel:"):
            hid = data.split(":", 1)[1]
            if not _ID_RE.match(hid):
                await _reply(update, "⚠️ انتخاب اسب نامعتبر است.")
                return
            # Internal id from callback only — never asked from the user.
            await _send_horse_analysis(update, context, hid)
            return

        if data.startswith("fp_event:"):
            await _fp_select_event(update, context, data.split(":", 1)[1])
            return
        if data == "fp:start_predict":
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


async def _fp_select_event(update: Update, context: ContextTypes.DEFAULT_TYPE, event_id: str) -> None:
    user = update.effective_user
    if not user:
        return
    if not _EVENT_ID_RE.match(event_id):
        await _reply(update, "⚠️ رویداد نامعتبر است.")
        return
    session = _sessions(context).get(user.id)
    if not session or session.step != "pick_event":
        # Allow selecting from a fresh menu even if session was cleared.
        session = _sessions(context).set(user.id, FiveParrehSession(step="pick_event"))

    try:
        payload = _client(context).get_five_parreh_event(event_id)
    except TelegramBotError:
        await _reply(
            update,
            "⚠️ این رویداد پنج‌پره دیگر در دسترس نیست (ممکن است مسابقه‌ای از آن گذشته باشد).",
            reply_markup=main_menu_keyboard(),
        )
        return

    event = event_from_api_payload(payload)
    if len(event.races) != 5:
        await _reply(update, "⚠️ رویداد پنج‌پره باید دقیقاً ۵ کورس داشته باشد.")
        return

    race_ids = event.race_ids
    session.event_id = event.event_id
    session.event_title = event.title
    session.event_track = event.track
    session.event_display_date = event.display_date
    session.race_ids = list(race_ids)
    session.race_labels = {r.race_id: r.label for r in event.races}
    session.horses_by_race = {rid: [] for rid in race_ids}
    session.race_index = 0
    session.step = "confirm_event"
    session.candidates = []
    session.touch()
    _sessions(context).set(user.id, session)

    await _reply(
        update,
        fmt.format_fiveparreh_event_detail(event),
        reply_markup=fiveparreh_start_predict_keyboard(),
    )


async def _fp_begin_horse_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    session = _sessions(context).get(user.id)
    if not session or session.step != "confirm_event" or len(session.race_ids) != 5:
        await _reply(update, "جلسه پنج‌پره منقضی شده. /fiveparreh را دوباره بزنید.")
        return
    # Re-check future eligibility via the shared race-program API.
    if session.event_id:
        try:
            _client(context).get_five_parreh_event(session.event_id)
        except TelegramBotError:
            _sessions(context).clear(user.id)
            await _reply(
                update,
                "⚠️ این رویداد دیگر آینده نیست و برای پیش‌بینی پنج‌پره مجاز نمی‌باشد.",
                reply_markup=main_menu_keyboard(),
            )
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
    # Reuse friendly /predict formatting for the ranked field, then ask for multi-select.
    pred_text = fmt.format_prediction(prediction)
    candidates = list(prediction.get("prediction") or [])
    if not candidates:
        await _reply(update, f"⚠️ برای {session.current_race_label()} اسبی جهت انتخاب نیست.")
        return
    session.candidates = candidates
    session.touch()
    user = update.effective_user
    if user:
        _sessions(context).set(user.id, session)
    text = (
        f"{pred_text}\n\n"
        f"✅ انتخاب اسب برای {session.current_race_label()} "
        f"(کورس {session.race_index + 1} از ۵)\n"
        "حداقل یک اسب را از دکمه‌ها انتخاب کنید."
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

    # Horses selected for all five locked races → combination summary (no pricing).
    session.step = "confirm"
    session.touch()
    _sessions(context).set(user.id, session)
    text = fmt.format_fiveparreh_confirm(
        session.selections_per_race(),
        total_combinations=session.total_combinations_estimate(),
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

    # Combination generation happens ONLY in the API / Five-Parreh engine (no pricing).
    result = _client(context).generate_five_parreh(
        session.to_api_payload(),
        include_combinations=True,
        max_combinations_in_response=20,
    )
    _sessions(context).clear(user.id)
    await _reply(update, fmt.format_fiveparreh_result(result), reply_markup=main_menu_keyboard())


async def _hvs_select_meeting(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    meeting_id: str,
) -> None:
    user = update.effective_user
    if not user:
        return
    meeting = _client(context).get_upcoming_meeting(meeting_id)
    races = meeting.get("races") or []
    meta_store: dict[str, dict[str, Any]] = context.application.bot_data.setdefault(
        "predict_meta", {}
    )
    location = meeting.get("location") or meeting.get("track") or meeting.get("city")
    for race in races:
        rid = str(race.get("race_id") or "").strip()
        if not rid:
            continue
        meta_store[rid] = {
            "label": race.get("label"),
            "race_number": race.get("race_number"),
            "display_date": meeting.get("display_date"),
            "track": location,
        }
    session = _horsevs(context).get(user.id) or HorseVsSession()
    session.step = "pick_race"
    session.meeting_id = meeting_id
    session.display_date = meeting.get("display_date")
    session.track = location
    session.touch()
    _horsevs(context).set(user.id, session)
    text = "⚔️ اسب مقابل اسب\n\n" + fmt.format_meeting_races(meeting)
    if not races:
        await _reply(update, text, reply_markup=main_menu_keyboard())
        return
    await _reply(
        update,
        text,
        reply_markup=meeting_races_keyboard(meeting, callback_prefix="hvs_race"),
    )


async def _hvs_select_race(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    race_id: str,
) -> None:
    user = update.effective_user
    if not user:
        return
    session = _horsevs(context).get(user.id)
    if not session or session.step not in {"pick_race", "pick_meeting", "pick_a"}:
        session = HorseVsSession(step="pick_race")
    meta = context.application.bot_data.get("predict_meta", {}).get(race_id) or {}
    # Ensure meta available even if user skipped /predict cache.
    if session.meeting_id and not meta:
        meeting = _client(context).get_upcoming_meeting(session.meeting_id)
        location = meeting.get("location") or meeting.get("track")
        for race in meeting.get("races") or []:
            if str(race.get("race_id")) == race_id:
                meta = {
                    "label": race.get("label"),
                    "race_number": race.get("race_number"),
                    "display_date": meeting.get("display_date"),
                    "track": location,
                }
                break
    prediction = _client(context).get_race_prediction(race_id)
    candidates = list(prediction.get("prediction") or [])
    if len(candidates) < 2:
        await _reply(update, "⚠️ برای مقایسه حداقل دو اسب در این کورس لازم است.")
        return
    # Enrich display names for buttons.
    for item in candidates:
        if not item.get("horse_name") and item.get("horse_id") is not None:
            item["horse_name"] = f"اسب {item.get('horse_id')}"
    session.step = "pick_a"
    session.race_id = race_id
    session.race_label = meta.get("label") or (
        f"کورس {meta.get('race_number')}" if meta.get("race_number") is not None else "کورس"
    )
    session.race_number = meta.get("race_number")
    session.display_date = meta.get("display_date") or session.display_date
    session.track = meta.get("track") or session.track
    session.horse_a_id = None
    session.horse_a_name = None
    session.candidates = candidates
    session.touch()
    _horsevs(context).set(user.id, session)
    text = fmt.format_horsevs_prompt(
        display_date=session.display_date,
        track=session.track,
        race_label=session.race_label,
        which="a",
    )
    await _reply(
        update,
        text,
        reply_markup=horse_pick_keyboard(candidates, callback_prefix="hvs_a"),
    )


async def _hvs_pick_a(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    horse_id: str,
) -> None:
    user = update.effective_user
    if not user:
        return
    session = _horsevs(context).get(user.id)
    if not session or session.step != "pick_a" or not session.race_id:
        await _reply(update, "جلسه مقایسه منقضی شده. /horsevs را دوباره بزنید.")
        return
    name = None
    for item in session.candidates:
        if str(item.get("horse_id")) == horse_id:
            name = item.get("horse_name")
            break
    if name is None:
        await _reply(update, "⚠️ این اسب در کورس انتخاب‌شده نیست.")
        return
    session.horse_a_id = horse_id
    session.horse_a_name = name
    session.step = "pick_b"
    session.touch()
    _horsevs(context).set(user.id, session)
    text = fmt.format_horsevs_prompt(
        display_date=session.display_date,
        track=session.track,
        race_label=session.race_label,
        which="b",
    )
    await _reply(
        update,
        text,
        reply_markup=horse_pick_keyboard(
            session.candidates,
            callback_prefix="hvs_b",
            exclude_ids={horse_id},
        ),
    )


async def _hvs_pick_b(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    horse_id: str,
) -> None:
    user = update.effective_user
    if not user:
        return
    session = _horsevs(context).get(user.id)
    if (
        not session
        or session.step != "pick_b"
        or not session.race_id
        or not session.horse_a_id
    ):
        await _reply(update, "جلسه مقایسه منقضی شده. /horsevs را دوباره بزنید.")
        return
    if horse_id == session.horse_a_id:
        await _reply(update, "⚠️ برای مقایسه باید دو اسب متفاوت انتخاب شوند.")
        return
    in_race = any(str(item.get("horse_id")) == horse_id for item in session.candidates)
    if not in_race:
        await _reply(update, "⚠️ هر دو اسب باید از همین کورس باشند.")
        return
    result = _client(context).compare_horses(session.race_id, session.horse_a_id, horse_id)
    meta = {
        "display_date": session.display_date,
        "track": session.track,
        "race_label": session.race_label,
    }
    _horsevs(context).clear(user.id)
    await _reply(
        update,
        fmt.format_horsevs_result(result, meta=meta),
        reply_markup=main_menu_keyboard(),
    )
