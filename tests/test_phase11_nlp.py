from collectors.phase11.dedupe_similarity import dedupe_reviews, text_similarity
from collectors.phase11.nlp import analyze_review


def test_nlp_negative_delay():
    r = analyze_review("بسته با تاخیر زیاد رسید و برخورد بد بود", rating=1)
    assert r.sentiment == "Negative"
    assert r.complaint_category in {"delivery_delay", "staff_behavior"}
    assert r.confidence_score >= 40


def test_nlp_positive():
    r = analyze_review("عالی بود خیلی سریع رسید ممنون", rating=5)
    assert r.sentiment == "Positive"
    assert r.emotion in {"Happy", "Satisfied"}


def test_dedupe_90_percent():
    rows = [
        {"brand": "Chapar", "branch_name": "A", "review_text": "خیلی بد بود تاخیر زیاد", "review_id": "1", "confidence_score": 50},
        {"brand": "Chapar", "branch_name": "A", "review_text": "خیلی بد بود تاخیر زیاد!", "review_id": "2", "confidence_score": 40},
        {"brand": "Chapar", "branch_name": "A", "review_text": "سرویس عالی و سریع", "review_id": "3", "confidence_score": 60},
    ]
    assert text_similarity(rows[0]["review_text"], rows[1]["review_text"]) >= 0.9
    kept, dropped = dedupe_reviews(rows, threshold=0.9)
    assert dropped >= 1
    assert len(kept) == 2
