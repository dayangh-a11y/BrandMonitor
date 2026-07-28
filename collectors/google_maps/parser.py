import re

from models.review import Branch


class GoogleMapsParser:

    def parse(
        self,
        name: str,
        rating: str,
        reviews: str,
        address: str,
    ) -> Branch:

        review_count = 0

        if reviews:
            match = re.search(r"\d+", reviews.replace(",", ""))

            if match:
                review_count = int(match.group())

        if rating == "":
            rating = "0"

        return Branch(
            name=name.strip(),
            rating=float(rating),
            review_count=review_count,
            address=address.strip(),
        )