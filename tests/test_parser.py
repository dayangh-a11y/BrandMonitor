from collectors.google_maps.parser import GoogleMapsParser


def test_persian_digits_and_branch_parse():
    parser = GoogleMapsParser()
    branch = parser.parse_branch(
        name="تیپاکس",
        rating="۲٫۳",
        reviews="۹۷ مرور",
        address="تهران",
    )
    assert branch is not None
    assert branch.rating == 2.3
    assert branch.review_count == 97


def test_rating_text_is_not_treated_as_review_count():
    parser = GoogleMapsParser()
    branch = parser.parse_branch(
        name="تیپاکس",
        rating="2.3",
        reviews="2.3",
        address="تهران",
    )
    assert branch is not None
    assert branch.rating == 2.3
    assert branch.review_count == 0


def test_review_parse():
    parser = GoogleMapsParser()
    review = parser.parse_review(
        author="علی",
        rating="۵ ستاره",
        text="عالی بود",
        external_id="r1",
        branch_name="تیپاکس",
    )
    assert review is not None
    assert review.rating == 5.0
    assert review.text == "عالی بود"
