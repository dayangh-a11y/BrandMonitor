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


def races_keyboard(races: list[dict[str, Any]], *, prefix: str = "predict") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for race in races[:20]:
        rid = race.get("race_id")
        track = (race.get("track") or "مسابقه")[:20]
        rows.append(
            [
                InlineKeyboardButton(
                    f"{track} — {rid}",
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
