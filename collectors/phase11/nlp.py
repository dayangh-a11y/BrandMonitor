"""Phase 11 rule-based NLP for review enrichment (no external LLM required)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


COMPLAINT_CATS = (
    "delivery_delay",
    "staff_behavior",
    "package_damage",
    "lost_package",
    "price",
    "tracking",
    "support",
    "other",
)

_DELAY = re.compile(
    r"تاخیر|تأخیر|دیر|کند|معطل|هفته|روزه?\s*است|delay|late|slow|waiting",
    re.I,
)
_STAFF = re.compile(
    r"برخورد|رفتار|بی‌ادب|بی ادب|rude|staff|employee|کارمند|پرسنل|جوابگو",
    re.I,
)
_DAMAGE = re.compile(r"آسیب|خراب|شکست|پاره|damage|broken|smashed", re.I)
_LOST = re.compile(r"گم|مفقود|نرسید|پیدا نشد|lost|missing|never arrived", re.I)
_PRICE = re.compile(r"گران|قیمت|هزینه|پول|expensive|price|cost|fee", re.I)
_TRACK = re.compile(r"پیگیری|رهگیری|کد پیگیری|track|tracking|status", re.I)
_SUPPORT = re.compile(r"پشتیبانی|پاسخگو|تلفن|پاسخ نم|support|call center|no answer", re.I)

_POS = re.compile(
    r"عالی|خوب|ممنون|مرسی|سریع|عالی بود|راضی|پیشنهاد|excellent|great|good|fast|thanks|recommend",
    re.I,
)
_NEG = re.compile(
    r"بد|افتضاح|ضعیف|مشکل|ناراضی|خراب|تاخیر|گم|هرگز|terrible|worst|bad|awful|hate|scam",
    re.I,
)

_ANGRY = re.compile(r"افتضاح|خجالت|دزدی|کلاه|angry|furious|scam|worst|ننگ", re.I)
_FRUST = re.compile(r"خسته|معطل|پیگیری|جوابگو نیست|frustrated|waiting|no answer", re.I)
_DISAP = re.compile(r"متاسف|ناامید|disappoint|expected|انتظار", re.I)
_HAPPY = re.compile(r"عالی|خوشحال|love|amazing|perfect|عالی بود", re.I)
_SATIS = re.compile(r"راضی|خوب بود|ممنون|مرسی|satisfied|ok|good", re.I)

_DURATION = re.compile(
    r"(\d+)\s*(روز|هفته|ساعت|ماه|day|days|week|weeks|hour|hours|month)",
    re.I,
)
_MONEY = re.compile(r"(\d+[\d,\.]*)\s*(تومان|ریال|هزار|میلیون|toman|irr|\$)", re.I)
_TRACKING_NO = re.compile(r"(?:کد|شماره)\s*(?:مرسوله|پیگیری)?\s*[:#]?\s*([A-Za-z0-9\-]{6,})", re.I)
_EMPLOYEE = re.compile(r"(?:آقای|خانم|کارمند|پرسنل)\s+([آ-ی]{2,12})", re.I)


@dataclass
class NlpResult:
    sentiment: str  # Positive / Neutral / Negative
    emotion: str
    complaint_category: str
    urgency: str  # Low / Medium / High / Critical
    confidence_score: int
    entities: dict = field(default_factory=dict)


def analyze_review(text: str, rating: float | None = None) -> NlpResult:
    raw = text or ""
    t = raw.strip()
    rating = float(rating or 0)

    # Sentiment
    pos_hit = bool(_POS.search(t))
    neg_hit = bool(_NEG.search(t))
    if rating >= 4 and not neg_hit:
        sentiment = "Positive"
    elif rating <= 2 and not pos_hit:
        sentiment = "Negative"
    elif rating <= 2 and neg_hit:
        sentiment = "Negative"
    elif rating >= 4 and pos_hit:
        sentiment = "Positive"
    elif neg_hit and not pos_hit:
        sentiment = "Negative"
    elif pos_hit and not neg_hit:
        sentiment = "Positive"
    elif rating == 3:
        sentiment = "Neutral"
    elif not t:
        sentiment = "Neutral"
    else:
        sentiment = "Neutral"

    # Complaint category (primary)
    cats = []
    if _DELAY.search(t):
        cats.append("delivery_delay")
    if _STAFF.search(t):
        cats.append("staff_behavior")
    if _DAMAGE.search(t):
        cats.append("package_damage")
    if _LOST.search(t):
        cats.append("lost_package")
    if _PRICE.search(t):
        cats.append("price")
    if _TRACK.search(t):
        cats.append("tracking")
    if _SUPPORT.search(t):
        cats.append("support")
    if sentiment == "Negative" and not cats:
        cats.append("other")
    complaint = cats[0] if cats else ("other" if sentiment == "Negative" else "other")
    if sentiment != "Negative" and not cats:
        complaint = "other"

    # Emotion
    if _ANGRY.search(t) or (sentiment == "Negative" and rating == 1):
        emotion = "Angry"
    elif _FRUST.search(t):
        emotion = "Frustrated"
    elif _DISAP.search(t) or sentiment == "Negative":
        emotion = "Disappointed"
    elif _HAPPY.search(t) or (sentiment == "Positive" and rating >= 5):
        emotion = "Happy"
    elif sentiment == "Positive":
        emotion = "Satisfied"
    else:
        emotion = "Satisfied" if sentiment == "Positive" else "Disappointed" if sentiment == "Negative" else "Satisfied"

    # Urgency
    if _LOST.search(t) or _ANGRY.search(t) or rating == 1:
        urgency = "Critical" if (_LOST.search(t) or rating == 1 and _ANGRY.search(t)) else "High"
    elif sentiment == "Negative" and (_DELAY.search(t) or _DAMAGE.search(t)):
        urgency = "High"
    elif sentiment == "Negative":
        urgency = "Medium"
    elif sentiment == "Neutral":
        urgency = "Low"
    else:
        urgency = "Low"
    if urgency == "Critical" and not (_LOST.search(t) or (rating == 1 and len(t) > 40)):
        urgency = "High"

    # Confidence
    conf = 40
    if t:
        conf += 15
    if rating > 0:
        conf += 15
    if cats:
        conf += 10
    if pos_hit or neg_hit:
        conf += 10
    if len(t) > 80:
        conf += 10
    conf = max(0, min(100, conf))

    entities: dict = {}
    dur = _DURATION.search(t)
    if dur:
        entities["delay_duration"] = f"{dur.group(1)} {dur.group(2)}"
    money = _MONEY.search(t)
    if money:
        entities["amount"] = f"{money.group(1)} {money.group(2)}"
    track = _TRACKING_NO.search(t)
    if track:
        entities["shipment_id"] = track.group(1)
    emp = _EMPLOYEE.search(t)
    if emp:
        entities["employee_name"] = emp.group(1)
    # service type hints
    if re.search(r"پیک|express|فوری|vip", t, re.I):
        entities["service_type"] = "express"
    elif re.search(r"پس‌کرایه|پس کرایه|cod", t, re.I):
        entities["service_type"] = "cod"

    return NlpResult(
        sentiment=sentiment,
        emotion=emotion,
        complaint_category=complaint if sentiment == "Negative" or cats else "other",
        urgency=urgency,
        confidence_score=conf,
        entities=entities,
    )
