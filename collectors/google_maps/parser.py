import re

from models.branch import Branch
from models.review import Review


class GoogleMapsParser:
    def parse_branch(
        self,
        name: str,
        rating: str | float | None,
        reviews: str | int | None,
        address: str = "",
        maps_url: str = "",
        place_id: str = "",
        company_name: str = "",
    ) -> Branch | None:
        clean_name = (name or "").strip()
        if not clean_name:
            return None

        return Branch(
            name=clean_name,
            rating=self._to_float(rating),
            review_count=self._to_int(reviews),
            address=(address or "").strip(),
            maps_url=(maps_url or "").strip(),
            place_id=(place_id or "").strip(),
            company_name=(company_name or "").strip(),
        )

    def parse_review(
        self,
        author: str,
        rating: str | float | None,
        text: str,
        published_at: str = "",
        external_id: str = "",
        branch_name: str = "",
    ) -> Review | None:
        clean_text = (text or "").strip()
        clean_author = (author or "").strip()
        if not clean_text and not clean_author:
            return None

        return Review(
            author=clean_author,
            rating=self._to_float(rating),
            text=clean_text,
            published_at=(published_at or "").strip(),
            external_id=(external_id or "").strip(),
            branch_name=(branch_name or "").strip(),
            source="google_maps",
            raw={
                "author": clean_author,
                "rating": rating,
                "text": clean_text,
                "published_at": published_at,
            },
        )

    # Backward-compatible method name used by older collector code.
    def parse(self, name, rating, reviews, address):
        return self.parse_branch(name, rating, reviews, address)

    def _to_float(self, value: str | float | int | None) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        match = re.search(r"\d+(?:[.,]\d+)?", str(value).replace(",", "."))
        if not match:
            return 0.0
        try:
            return float(match.group().replace(",", "."))
        except ValueError:
            return 0.0

    def _to_int(self, value: str | int | None) -> int:
        if value is None:
            return 0
        if isinstance(value, int):
            return value
        digits = re.sub(r"[^\d]", "", str(value))
        if not digits:
            return 0
        try:
            return int(digits)
        except ValueError:
            return 0
