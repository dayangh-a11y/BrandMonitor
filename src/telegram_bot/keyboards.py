"""Inline keyboards for Telegram UI."""

from __future__ import annotations

from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🏁 مسابقات", callback_data="menu:races"),
                InlineKeyboardButton("🎯 پیش‌بینی", callback_data="menu:predict"),
            ],
            [
                InlineKeyboardButton("🎟 پنج‌پره", callback_data="menu:fiveparreh"),
                InlineKeyboardButton("🐎 تحلیل اسب", callback_data="menu:horse"),
            ],
            [InlineKeyboardButton("ℹ️ راهنما", callback_data="menu:help")],
        ]
    )


def upcoming_meetings_keyboard(meetings: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    """Buttons show location + date; callback carries internal meeting_id only."""
    rows: list[list[InlineKeyboardButton]] = []
    for meeting in meetings[:20]:
        mid = str(meeting.get("meeting_id") or "").strip()
        if not mid:
            continue
        location = str(
            meeting.get("location") or meeting.get("track") or meeting.get("city") or "مسابقه"
        ).strip()
        date = str(meeting.get("display_date") or "").strip()
        label = f"{location} — {date}" if date else location
        rows.append(
            [InlineKeyboardButton(label[:60], callback_data=f"mtg:{mid[:40]}")]
        )
    rows.append([InlineKeyboardButton("🏠 منو", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def meeting_races_keyboard(meeting: dict[str, Any]) -> InlineKeyboardMarkup:
    """Buttons show race labels/numbers; callback carries internal race_id only."""
    rows: list[list[InlineKeyboardButton]] = []
    for race in (meeting.get("races") or [])[:20]:
        rid = race.get("race_id")
        if rid is None:
            continue
        if not race.get("eligible_for_prediction", True):
            continue
        num = race.get("race_number")
        label = str(race.get("label") or (f"کورس {num}" if num is not None else "کورس")).strip()
        rows.append(
            [InlineKeyboardButton(label[:60], callback_data=f"prd:{rid}")]
        )
    rows.append([InlineKeyboardButton("🏠 منو", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def races_keyboard(races: list[dict[str, Any]], *, prefix: str = "prd") -> InlineKeyboardMarkup:
    """Deprecated freeze-list keyboard; kept for compatibility. Prefer meeting keyboards."""
    rows: list[list[InlineKeyboardButton]] = []
    for race in races[:20]:
        rid = race.get("race_id")
        label = race.get("label") or race.get("race_number") or "کورس"
        track = (race.get("track") or "")[:20]
        text = f"{track} — {label}" if track else str(label)
        rows.append(
            [
                InlineKeyboardButton(
                    text[:60],
                    callback_data=f"{prefix}:{rid}",
                )
            ]
        )
    rows.append([InlineKeyboardButton("🏠 منو", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def horse_toggle_keyboard(
    candidates: list[dict[str, Any]],
    selected: set[str],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in candidates[:15]:
        hid = str(item.get("horse_id"))
        name = item.get("horse_name") or f"اسب {hid}"
        score = item.get("score")
        mark = "✅" if hid in selected else "☑️"
        label = f"{mark} {name}"
        if score is not None:
            try:
                label += f" ({float(score):.1f})"
            except (TypeError, ValueError):
                pass
        rows.append([InlineKeyboardButton(label[:60], callback_data=f"fp:tog:{hid}")])
    rows.append(
        [
            InlineKeyboardButton("✅ تأیید انتخاب", callback_data="fp:ok"),
            InlineKeyboardButton("❌ انصراف", callback_data="fp:cancel"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def fiveparreh_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("تأیید", callback_data="fp:confirm"),
                InlineKeyboardButton("بازگشت", callback_data="fp:cancel"),
            ]
        ]
    )


def fiveparreh_event_keyboard(events: list[Any]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for event in events[:20]:
        if isinstance(event, dict):
            event_id = str(event.get("event_id") or "").strip()
            track = str(
                event.get("location") or event.get("track") or event.get("city") or "پنج‌پره"
            )
            date = str(event.get("display_date") or "").strip()
        else:
            event_id = str(getattr(event, "event_id", "")).strip()
            track = str(getattr(event, "track", "") or "پنج‌پره")
            date = str(getattr(event, "display_date", "") or "").strip()
        if not event_id or len(event_id) > 40:
            continue
        label = f"{track} — {date}" if date else f"انتخاب — {track}"
        rows.append(
            [InlineKeyboardButton(label[:60], callback_data=f"fp_event:{event_id}")]
        )
    rows.append([InlineKeyboardButton("🏠 منو", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def horse_search_keyboard(horses: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    """Buttons show horse names; callback carries internal horse_id only."""
    rows: list[list[InlineKeyboardButton]] = []
    for horse in horses[:15]:
        hid = horse.get("horse_id")
        name = str(horse.get("horse_name") or "").strip()
        if hid is None or not name:
            continue
        rows.append(
            [InlineKeyboardButton(name[:60], callback_data=f"horse_sel:{int(hid)}")]
        )
    rows.append([InlineKeyboardButton("🏠 منو", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def fiveparreh_start_predict_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("شروع پیش‌بینی", callback_data="fp:start_predict"),
                InlineKeyboardButton("بازگشت", callback_data="fp:cancel"),
            ]
        ]
    )
