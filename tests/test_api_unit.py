from api.errors import error_body
from api.schemas import CompanyOut, PaginatedReviews


def test_error_body_shape():
    body = error_body("company_not_found", "missing", details={"id": 1})
    assert body["error"]["code"] == "company_not_found"
    assert body["error"]["message"] == "missing"
    assert body["error"]["details"]["id"] == 1


def test_company_out_defaults():
    company = CompanyOut(
        id=1,
        name="Tipax",
        source="google_maps",
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert company.branch_count == 0
    assert company.latest_score is None


def test_paginated_reviews_model():
    page = PaginatedReviews(items=[], total=0, limit=20, offset=0)
    assert page.total == 0
    assert page.limit == 20
