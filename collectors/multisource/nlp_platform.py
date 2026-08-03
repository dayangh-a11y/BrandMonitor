"""Extended multi-source NLP classification."""

from __future__ import annotations

import re
from dataclasses import dataclass

from collectors.phase11.nlp import analyze_review as _base_analyze


# Map phase11 categories → platform taxonomy
_CAT_MAP = {
    "delivery_delay": "Delay",
    "lost_package": "Lost Package",
    "package_damage": "Damaged Package",
    "staff_behavior": "Staff Behavior",
    "support": "Customer Support",
    "tracking": "Tracking",
    "price": "Pricing",
    "other": "Other",
}

_APP = re.compile(r"اپ|اپلیکیشن|برنامه|بازار|مایکت|کرش|crash|bug|آپدیت|app", re.I)
_FAIL = re.compile(r"تحویل نشد|نرسید|failed delivery|عدم تحویل|برگشت خورد", re.I)


@dataclass
class PlatformNlp:
    complaint_category: str
    complaint_subcategory: str
    sentiment: str
    emotion: str
    urgency: str
    confidence_score: int


def analyze_platform_review(text: str, rating: float | None = None, *, source: str = "") -> PlatformNlp:
    base = _base_analyze(text or "", rating)
    cat = _CAT_MAP.get(base.complaint_category, "Other")
    sub = base.complaint_category
    if _APP.search(text or "") or source in {"cafebazaar", "myket"}:
        if base.sentiment == "Negative":
            cat = "Mobile App"
            sub = "app_issue"
    if _FAIL.search(text or ""):
        cat = "Delivery Failure"
        sub = "delivery_failure"

    urgency = base.urgency
    if urgency == "Critical":
        urgency = "High"  # platform taxonomy is Low/Medium/High

    return PlatformNlp(
        complaint_category=cat if base.sentiment == "Negative" else ("Other" if base.sentiment != "Positive" else "Other"),
        complaint_subcategory=sub,
        sentiment=base.sentiment,
        emotion=base.emotion,
        urgency=urgency if urgency in {"Low", "Medium", "High"} else "Medium",
        confidence_score=base.confidence_score,
    )
