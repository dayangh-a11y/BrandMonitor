from __future__ import annotations

import hashlib
import re

from ai.adapters.base import ModelAdapter
from ai.taxonomy import PROMPT_VERSION, SCHEMA_VERSION
from models.analysis import AnalysisDTO, ConfidenceByField
from models.review import Review

_NEGATIVE_HINTS = ("bad", "worst", "delay", "damage", "awful", "terrible", "ضعیف", "بد", "تأخیر", "آسیب")
_POSITIVE_HINTS = ("good", "great", "fast", "excellent", "عالی", "خوب", "سریع")
_DAMAGE_HINTS = ("damage", "broken", "آسیب", "خراب")
_TRACKING_HINTS = ("track", "پیگیری", "رهگیری")
_PRICE_HINTS = ("expensive", "گران", "قیمت")
_CITY_HINTS = ("tehran", "تهران", "mashhad", "مشهد", "isfahan", "اصفهان")


class FakeAdapter(ModelAdapter):
    """Deterministic mock analyzer for pipeline tests (no external AI)."""

    @property
    def id(self) -> str:
        return "fake-v1"

    async def extract(self, review: Review, *, meta: dict | None = None) -> AnalysisDTO:
        text = (review.text or "").strip()
        if len(text) < 3:
            return AnalysisDTO(
                sentiment="Neutral",
                status="skipped",
                error="empty_or_too_short",
                provider="fake",
                model_id=self.id,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                confidence_overall=0.0,
                raw_response={"reason": "skipped_short_text"},
            )

        lowered = text.casefold()
        negative = any(hint in lowered for hint in _NEGATIVE_HINTS)
        positive = any(hint in lowered for hint in _POSITIVE_HINTS)

        if negative and not positive:
            sentiment = "Negative"
            complaint = ["delivery_speed"]
            positive_cats: list[str] = []
            urgency = "medium"
            delivery_speed = "slow"
            customer_service = "bad"
            confidence = 0.82
        elif positive and not negative:
            sentiment = "Positive"
            complaint = []
            positive_cats = ["customer_service"]
            urgency = "low"
            delivery_speed = "fast"
            customer_service = "good"
            confidence = 0.86
        else:
            sentiment = "Neutral"
            complaint = []
            positive_cats = []
            urgency = "low"
            delivery_speed = None
            customer_service = "average"
            confidence = 0.55

        if any(hint in lowered for hint in _DAMAGE_HINTS):
            if "package_damage" not in complaint:
                complaint.append("package_damage")
            package_damage = True
        else:
            package_damage = False if sentiment == "Positive" else None

        tracking = "bad" if any(hint in lowered for hint in _TRACKING_HINTS) and negative else None
        if tracking == "bad" and "tracking" not in complaint:
            complaint.append("tracking")

        pricing = "expensive" if any(hint in lowered for hint in _PRICE_HINTS) else None
        if pricing == "expensive" and "pricing" not in complaint:
            complaint.append("pricing")

        mentioned_city = None
        for city in _CITY_HINTS:
            if city in lowered:
                mentioned_city = "Tehran" if city in {"tehran", "تهران"} else city.title()
                break

        mentioned_branch = review.branch_name or None
        employee_match = re.search(r"\b(mr\.?\s+\w+|خانم\s+\w+|آقای\s+\w+)\b", text, flags=re.I)
        mentioned_employees = [employee_match.group(0)] if employee_match else []

        # Stable pseudo evidence id from text for determinism checks.
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]

        return AnalysisDTO(
            sentiment=sentiment,  # type: ignore[arg-type]
            complaint_categories=complaint,
            positive_categories=positive_cats,
            delivery_speed=delivery_speed,  # type: ignore[arg-type]
            customer_service=customer_service,  # type: ignore[arg-type]
            staff_behavior="good" if sentiment == "Positive" else ("bad" if sentiment == "Negative" else None),
            package_damage=package_damage,
            pricing=pricing,  # type: ignore[arg-type]
            tracking=tracking,  # type: ignore[arg-type]
            professionalism="good" if sentiment == "Positive" else None,
            mentioned_employees=mentioned_employees,
            mentioned_city=mentioned_city,
            mentioned_branch=mentioned_branch,
            urgency=urgency,  # type: ignore[arg-type]
            evidence_spans={"sentiment": text[:120], "digest": digest},
            confidence_overall=confidence,
            confidence_by_field=ConfidenceByField(
                sentiment=confidence,
                complaint_categories=0.7 if complaint else 0.4,
                positive_categories=0.7 if positive_cats else 0.4,
                delivery_speed=0.65 if delivery_speed else 0.2,
                customer_service=0.65 if customer_service else 0.2,
                staff_behavior=0.5,
                package_damage=0.7 if package_damage is not None else 0.2,
                pricing=0.6 if pricing else 0.2,
                tracking=0.6 if tracking else 0.2,
                professionalism=0.5,
                mentioned_employees=0.8 if mentioned_employees else 0.1,
                mentioned_city=0.8 if mentioned_city else 0.1,
                mentioned_branch=0.6 if mentioned_branch else 0.1,
            ),
            language="fa" if re.search(r"[\u0600-\u06FF]", text) else "en",
            status="succeeded",
            provider="fake",
            model_id=self.id,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            raw_response={
                "adapter": self.id,
                "meta": meta or {},
                "digest": digest,
                "negative": negative,
                "positive": positive,
            },
        )
