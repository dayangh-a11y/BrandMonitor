"""Persian message formatters. Display Score as Score — never as probability %."""

from __future__ import annotations

from typing import Any


def format_money(value: int | float | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{int(value):,}"


def format_score(value: Any) -> str:
    """Format numeric score for display. Never treat as probability."""
    if value is None:
        return "—"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{f:.1f}"


# Technical API warning codes → user-facing Persian (never show raw codes).
_WARNING_MESSAGES: dict[str, str] = {
    "low_feature_coverage": "⚠️ اطلاعات کافی برای امتیازدهی این اسب وجود ندارد.",
    "score_unavailable_insufficient_features": (
        "⚠️ اطلاعات کافی برای امتیازدهی این اسب وجود ندارد."
    ),
}


def friendly_warnings(warnings: list[Any] | None) -> list[str]:
    """Map internal warning codes to friendly Persian; drop unknown codes."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in warnings or []:
        key = str(raw).strip()
        msg = _WARNING_MESSAGES.get(key)
        if not msg or msg in seen:
            continue
        seen.add(msg)
        out.append(msg)
    return out


def welcome_text() -> str:
    return (
        "🏇 سیستم تحلیل مسابقات اسب‌دوانی\n\n"
        "امکانات:\n\n"
        "🏁 مسابقات\n"
        "🎯 پیش‌بینی\n"
        "🎟 پنج‌پره\n"
        "🐎 تحلیل اسب\n\n"
        "توجه: امتیازها احتمال قطعی برد نیستند و تضمین سود وجود ندارد."
    )


def help_text() -> str:
    return (
        "ℹ️ راهنما\n\n"
        "/start — منوی اصلی\n"
        "/help — همین راهنما\n"
        "/races — فهرست مسابقات موجود\n"
        "/predict [شناسه] — پیش‌بینی یک مسابقه (Score، نه احتمال)\n"
        "/horse [شناسه] — تحلیل اسب از دیتاست\n"
        "/fiveparreh — ساخت ترکیب پنج‌پره با راهنمای گام‌به‌گام\n\n"
        "ربات فقط واسط کاربری است؛ محاسبات در API انجام می‌شود."
    )


def format_race_list(payload: dict[str, Any]) -> str:
    races = payload.get("races") or []
    if not races:
        return "در حال حاضر مسابقه‌ای در دسترس نیست."
    lines = ["🏁 مسابقات موجود", ""]
    for i, race in enumerate(races, start=1):
        track = race.get("track") or "نامشخص"
        rid = race.get("race_id")
        date = race.get("race_date") or "—"
        field = race.get("field_size")
        field_s = f" — {field} اسب" if field is not None else ""
        lines.append(f"{i}️⃣ {track} — کورس {rid} ({date}){field_s}")
    total = payload.get("total")
    if total is not None:
        lines.append("")
        lines.append(f"مجموع در دیتاست: {total}")
    return "\n".join(lines)


def format_prediction(payload: dict[str, Any], *, top_n: int = 10) -> str:
    rid = payload.get("race_id")
    lines = [f"🏇 پیش‌بینی کورس {rid}", ""]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    preds = list(payload.get("prediction") or [])[:top_n]
    if not preds:
        return f"🏇 پیش‌بینی کورس {rid}\n\nنتیجه‌ای موجود نیست."
    for item in preds:
        rank = item.get("rank")
        medal = medals.get(rank, f"{rank}.")
        name = item.get("horse_name") or f"اسب {item.get('horse_id')}"
        score = format_score(item.get("score"))
        lines.append(f"{medal} {name}")
        lines.append(f"امتیاز: {score}")
        for warning in friendly_warnings(item.get("warnings")):
            lines.append(warning)
        lines.append("")
    lines.append("ℹ️ امتیاز، احتمال برد نیست.")
    return "\n".join(lines).rstrip()


def format_horse(payload: dict[str, Any]) -> str:
    hid = payload.get("horse_id")
    name = payload.get("horse_name") or f"اسب {hid}"
    lines = [f"🐎 تحلیل اسب: {name}", f"شناسه: {hid}", ""]
    if payload.get("observation_count") is not None:
        lines.append(f"تعداد مشاهده: {payload.get('observation_count')}")
    if payload.get("latest_race_id") is not None:
        lines.append(
            f"آخرین مسابقه: {payload.get('latest_race_id')} ({payload.get('latest_race_date') or '—'})"
        )
    evidence = payload.get("evidence") or payload.get("latest_features") or []
    if evidence:
        lines.append("")
        lines.append("شواهد:")
        for ev in evidence[:8]:
            metric = ev.get("metric") if isinstance(ev, dict) else None
            value = ev.get("value") if isinstance(ev, dict) else None
            if metric is not None:
                lines.append(f"• {metric}: {value}")
    mapped = friendly_warnings(payload.get("warnings"))
    if mapped:
        lines.append("")
        lines.extend(mapped)
    note = payload.get("note")
    if note:
        # Avoid leaking English API internals; keep Persian-only user summary.
        if "probability" not in str(note).lower():
            lines.append("")
            lines.append(str(note)[:240])
    lines.append("")
    lines.append("ℹ️ امتیاز، احتمال برد نیست.")
    return "\n".join(lines)


def format_fiveparreh_race_block(race_ids: list[str | int]) -> str:
    lines = ["🎟 پنج‌پره", ""]
    for i, rid in enumerate(race_ids, start=1):
        lines.append(f"کورس {i}: {rid}")
    lines.append("")
    lines.append("۵ کورس متوالی از یک برنامه انتخاب شد.")
    lines.append("برای ادامه، اسب‌های کورس ۱ را انتخاب کنید.")
    return "\n".join(lines)


def format_fiveparreh_confirm(
    selections_per_race: list[int],
    *,
    total_combinations: int | None,
    price_per_combination: int | float,
) -> str:
    lines = ["🎟 پنج‌پره", ""]
    for i, n in enumerate(selections_per_race, start=1):
        lines.append(f"کورس {i}: {n} اسب")
    if total_combinations is not None:
        lines.append("")
        lines.append(f"تعداد ترکیب:\n{total_combinations}")
    lines.append("")
    lines.append(f"قیمت هر برگ:\n{format_money(price_per_combination)} تومان")
    if total_combinations is not None:
        total_cost = int(total_combinations) * int(price_per_combination)
        lines.append("")
        lines.append(f"هزینه کل:\n{format_money(total_cost)} تومان")
    return "\n".join(lines)


def format_fiveparreh_result(payload: dict[str, Any]) -> str:
    lines = [
        "🎟 نتیجه پنج‌پره",
        "",
        f"تعداد ترکیب: {payload.get('total_combinations')}",
        f"قیمت هر ترکیب: {format_money(payload.get('price_per_combination'))} تومان",
        f"هزینه کل: {format_money(payload.get('total_cost'))} تومان",
    ]
    if payload.get("combinations_omitted"):
        lines.append("")
        lines.append("تعداد ترکیب‌ها زیاد است؛ خلاصه نمایش داده می‌شود.")
    else:
        combos = payload.get("combinations") or []
        if combos and len(combos) <= 20:
            lines.append("")
            lines.append("نمونه ترکیب‌ها:")
            for c in combos[:10]:
                ids = c.get("horse_ids") or []
                lines.append("• " + " / ".join(str(x) for x in ids))
    return "\n".join(lines)


def truncate(text: str, max_len: int = 3500) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 20] + "\n…\n(کوتاه شد)"
