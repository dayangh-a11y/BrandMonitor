import pytest
from pydantic import ValidationError

from ai.taxonomy import CATEGORY_TAXONOMY
from ai.validation import AnalysisValidationError, validate_analysis_payload
from models.analysis import AnalysisDTO


def test_taxonomy_contains_required_categories():
    required = {
        "delivery_speed",
        "customer_service",
        "staff_behavior",
        "package_damage",
        "pricing",
        "tracking",
        "professionalism",
    }
    assert required.issubset(CATEGORY_TAXONOMY)


def test_analysis_dto_accepts_valid_payload():
    dto = AnalysisDTO(
        sentiment="Negative",
        complaint_categories=["delivery_speed", "tracking"],
        positive_categories=[],
        delivery_speed="slow",
        customer_service="bad",
        staff_behavior="bad",
        package_damage=True,
        pricing="expensive",
        tracking="bad",
        professionalism=None,
        mentioned_employees=["Mr Karimi"],
        mentioned_city="Tehran",
        mentioned_branch="Tipax HQ",
        urgency="high",
        confidence_overall=0.9,
    )
    assert dto.sentiment == "Negative"
    assert dto.complaint_categories == ["delivery_speed", "tracking"]


def test_analysis_dto_rejects_unknown_category():
    with pytest.raises(ValidationError):
        AnalysisDTO(
            sentiment="Neutral",
            complaint_categories=["not_a_real_category"],
        )


def test_validate_analysis_payload_taxonomy_and_schema():
    payload = {
        "sentiment": "Positive",
        "complaint_categories": [],
        "positive_categories": ["customer_service"],
        "confidence_overall": 0.8,
        "schema_version": "analysis_dto_v1",
        "provider": "fake",
        "model_id": "fake-v1",
    }
    dto = validate_analysis_payload(payload)
    assert dto.positive_categories == ["customer_service"]

    with pytest.raises(AnalysisValidationError):
        validate_analysis_payload({**payload, "schema_version": "wrong"})
