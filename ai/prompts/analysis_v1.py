from __future__ import annotations

import json
from typing import Any

from ai.taxonomy import CATEGORY_TAXONOMY, PROMPT_VERSION, SCHEMA_VERSION

ANALYSIS_PROMPT_ID = "analysis_prompt_v1"


SYSTEM_PROMPT = f"""You are BrandMonitor's logistics review analyst for Iranian courier/delivery companies.
Extract structured signals from one customer review. Respond with a single JSON object only (no markdown).

Schema version: {SCHEMA_VERSION}
Prompt version: {PROMPT_VERSION}
Prompt id: {ANALYSIS_PROMPT_ID}

Allowed category values (complaint_categories and positive_categories):
{sorted(CATEGORY_TAXONOMY)}

Required JSON keys:
- sentiment: "Positive" | "Neutral" | "Negative"
- complaint_categories: string[] (from taxonomy only)
- positive_categories: string[] (from taxonomy only)
- delivery_speed: "fast" | "normal" | "slow" | null
- customer_service: "good" | "average" | "bad" | null
- staff_behavior: "good" | "average" | "bad" | null
- package_damage: true | false | null
- pricing: "cheap" | "fair" | "expensive" | null
- tracking: "good" | "average" | "bad" | null
- professionalism: "good" | "average" | "bad" | null
- mentioned_employees: string[] (person names only)
- mentioned_city: string | null
- mentioned_branch: string | null
- urgency: "low" | "medium" | "high"
- evidence_spans: object mapping field -> short quote from the review
- confidence_overall: number 0..1
- confidence_by_field: object with keys sentiment, complaint_categories, positive_categories,
  delivery_speed, customer_service, staff_behavior, package_damage, pricing, tracking,
  professionalism, mentioned_employees, mentioned_city, mentioned_branch (each 0..1)
- language: "fa" | "en" | other BCP47-ish code | null

Rules:
- Use null when the review does not support a field.
- Do not invent categories outside the taxonomy; use "other" if needed.
- evidence_spans must quote the review text (Persian or English).
- Prefer precision over recall for employee/branch/city extraction.
"""


def build_user_prompt(review_text: str, *, branch_name: str = "", rating: float | None = None) -> str:
    payload: dict[str, Any] = {
        "review_text": review_text,
        "branch_name_hint": branch_name or None,
        "star_rating_hint": rating,
    }
    return (
        "Analyze this logistics review and return the JSON object described in the system prompt.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def expected_json_keys() -> list[str]:
    return [
        "sentiment",
        "complaint_categories",
        "positive_categories",
        "delivery_speed",
        "customer_service",
        "staff_behavior",
        "package_damage",
        "pricing",
        "tracking",
        "professionalism",
        "mentioned_employees",
        "mentioned_city",
        "mentioned_branch",
        "urgency",
        "evidence_spans",
        "confidence_overall",
        "confidence_by_field",
        "language",
    ]
