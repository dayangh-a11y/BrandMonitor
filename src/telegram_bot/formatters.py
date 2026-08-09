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
        "/races — مسابقات آینده (بر اساس برنامه)\n"
        "/predict — انتخاب جلسه و کورس آینده (بدون شناسه)\n"
        "/horse — جستجوی اسب با نام (نه شناسه)\n"
        "/fiveparreh — رویدادهای پنج‌پرهٔ آینده از همان برنامهٔ مسابقات\n\n"
        "ربات فقط واسط کاربری است؛ محاسبات در API انجام می‌شود."
    )


def format_upcoming_meetings(payload: dict[str, Any]) -> str:
    meetings = payload.get("meetings") or []
    if not meetings:
        return payload.get("message") or "در ۷ روز آینده مسابقه‌ای برای پیش‌بینی ثبت نشده است."
    lines = ["🎯 مسابقات آینده", ""]
    for meeting in meetings:
        date = meeting.get("display_date") or "—"
        location = meeting.get("location") or meeting.get("track") or meeting.get("city") or "—"
        lines.append(f"📅 {date}")
        lines.append(f"📍 {location}")
        lines.append("🏇 برنامه مسابقات")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_meeting_races(meeting: dict[str, Any]) -> str:
    location = meeting.get("location") or meeting.get("track") or meeting.get("city") or "—"
    date = meeting.get("display_date") or "—"
    races = meeting.get("races") or []
    if not races:
        return "برای این جلسه مسابقهٔ آینده‌ای باقی نمانده است."
    lines = [f"🏇 مسابقات {location}", f"📅 {date}", ""]
    for race in races:
        num = race.get("race_number")
        label = race.get("label") or (f"کورس {num}" if num is not None else "کورس")
        # Prefer numbered list without exposing race_id.
        prefix = f"{num}️⃣" if num is not None else "•"
        lines.append(f"{prefix} {label}")
        if race.get("scheduled_start") is None or race.get("status") == "unknown_time":
            lines.append("   زمان مسابقه مشخص نیست")
    return "\n".join(lines)


def format_race_list(payload: dict[str, Any]) -> str:
    """Backward-compatible helper; prefer format_upcoming_meetings for /predict."""
    if "meetings" in payload:
        return format_upcoming_meetings(payload)
    races = payload.get("races") or []
    if not races:
        return "در حال حاضر مسابقه‌ای در دسترس نیست."
    lines = ["🏁 مسابقات", ""]
    for i, race in enumerate(races, start=1):
        track = race.get("track") or race.get("location") or "نامشخص"
        date = race.get("race_date") or race.get("display_date") or "—"
        label = race.get("label") or race.get("race_number") or "کورس"
        lines.append(f"{i}️⃣ {track} — {label} ({date})")
    return "\n".join(lines)


def format_prediction(
    payload: dict[str, Any],
    *,
    top_n: int = 10,
    meta: dict[str, Any] | None = None,
) -> str:
    meta = meta or {}
    race_number = meta.get("race_number")
    label = meta.get("label")
    if race_number is not None:
        title = f"🏇 پیش‌بینی کورس {race_number}"
    elif label:
        title = f"🏇 پیش‌بینی {label}"
    else:
        # Do not lead with internal race_id in normal UX.
        title = "🏇 پیش‌بینی کورس"
    lines = [title]
    if meta.get("display_date"):
        lines.append(f"📅 {meta.get('display_date')}")
    if meta.get("track"):
        lines.append(f"📍 {meta.get('track')}")
    lines.append("")
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    preds = list(payload.get("prediction") or [])[:top_n]
    if not preds:
        lines.append("نتیجه‌ای موجود نیست.")
        return "\n".join(lines)
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

def format_horse_search_results(payload: dict[str, Any]) -> str:
    horses = payload.get("horses") or []
    if not horses:
        return "🐎 اسبی با این نام پیدا نشد."
    lines = ["🐎 نتایج جستجوی اسب", ""]
    for i, horse in enumerate(horses, start=1):
        name = horse.get("horse_name") or "—"
        breed = horse.get("breed")
        lines.append(f"{i}️⃣ {name}")
        if breed:
            lines.append(f"   نژاد: {breed}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_horse(payload: dict[str, Any]) -> str:
    name = payload.get("horse_name") or "اسب"
    lines = [f"🐎 تحلیل {name}", ""]
    if payload.get("observation_count") is not None:
        lines.append(f"تعداد مشاهده: {payload.get('observation_count')}")
    if payload.get("latest_race_date") is not None:
        lines.append(f"آخرین مسابقه: {payload.get('latest_race_date') or '—'}")
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


def _fp_field(event: Any, key: str, default: str = "—") -> str:
    if isinstance(event, dict):
        value = event.get(key)
    else:
        value = getattr(event, key, None)
    if value is None or value == "":
        return default
    return str(value)


def format_future_fiveparreh_events(events: list[Any]) -> str:
    if not events:
        return (
            "🎟 Five-Parreh های آینده\n\n"
            "در حال حاضر رویداد پنج‌پرهٔ آینده‌ای ثبت نشده است.\n"
            "رویدادها باید از منبع برنامهٔ مسابقات (آینده) تأمین شوند؛ "
            "از مسابقات گذشته ساخته نمی‌شوند."
        )
    lines = ["🎟 Five-Parreh های آینده", ""]
    for i, event in enumerate(events, start=1):
        track = _fp_field(event, "location", "") or _fp_field(event, "track")
        date = _fp_field(event, "display_date")
        title = _fp_field(event, "title", "پنج‌پره")
        lines.append(f"{i}️⃣ 📅 {date}")
        lines.append(f"📍 {track}")
        lines.append(f"🏇 {title}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_fiveparreh_event_detail(event: Any) -> str:
    track = _fp_field(event, "location", "") or _fp_field(event, "track")
    date = _fp_field(event, "display_date")
    title = _fp_field(event, "title", "پنج‌پره")
    lines = [f"🎟 {title} {track}", f"📅 {date}", "", "این پنج کورس در پنج‌پره هستند:", ""]
    if isinstance(event, dict):
        races = list(event.get("races") or [])
    else:
        races = list(getattr(event, "races", []) or [])
    for i, race in enumerate(races, start=1):
        if isinstance(race, dict):
            label = race.get("label") or f"کورس {race.get('race_number') or i}"
        else:
            label = getattr(race, "label", None) or f"کورس {i}"
        lines.append(f"{i}. {label}")
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
