import re

from collectors.dedupe import review_content_hash
from collectors.iran_geo import province_lookup
from models.branch import Branch
from models.review import Review

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_IRAN_PROVINCES = province_lookup()


class GoogleMapsParser:
    def normalize_digits(self, value: str) -> str:
        return (value or "").translate(_PERSIAN_DIGITS).replace("٫", ".").replace("،", ",")

    def detect_language(self, text: str) -> str:
        if re.search(r"[\u0600-\u06FF]", text or ""):
            return "fa"
        if re.search(r"[A-Za-z]", text or ""):
            return "en"
        return ""

    def infer_city_province(self, address: str) -> tuple[str, str]:
        lowered = (address or "").casefold()
        for needle, (city, province) in _IRAN_PROVINCES.items():
            if needle.casefold() in lowered:
                return city, province
        # Heuristic: "City, Province, Iran"
        parts = [p.strip() for p in (address or "").split(",") if p.strip()]
        if len(parts) >= 2:
            return parts[0], parts[1]
        return "", ""

    def parse_branch(
        self,
        name: str,
        rating: str | float | None,
        reviews: str | int | None,
        address: str = "",
        maps_url: str = "",
        place_id: str = "",
        company_name: str = "",
        phone: str = "",
        latitude: float | None = None,
        longitude: float | None = None,
        city: str = "",
        province: str = "",
        metadata: dict | None = None,
    ) -> Branch | None:
        clean_name = (name or "").strip()
        if not clean_name:
            return None
        inferred_city, inferred_province = self.infer_city_province(address)
        return Branch(
            name=clean_name,
            rating=self._to_float(rating),
            review_count=self.extract_review_count(reviews),
            address=(address or "").strip(),
            maps_url=(maps_url or "").strip(),
            place_id=(place_id or "").strip(),
            company_name=(company_name or "").strip(),
            phone=(phone or "").strip(),
            latitude=latitude,
            longitude=longitude,
            city=(city or inferred_city or "").strip(),
            province=(province or inferred_province or "").strip(),
            metadata=metadata or {},
        )

    def parse_review(
        self,
        author: str,
        rating: str | float | None,
        text: str,
        published_at: str = "",
        external_id: str = "",
        branch_name: str = "",
        owner_response: str = "",
        owner_response_at: str = "",
        language: str = "",
    ) -> Review | None:
        clean_text = (text or "").strip()
        clean_author = (author or "").strip()
        if not clean_text and not clean_author:
            return None

        review = Review(
            author=clean_author,
            rating=self._to_float(rating),
            text=clean_text,
            published_at=(published_at or "").strip(),
            language=(language or self.detect_language(clean_text)).strip(),
            external_id=(external_id or "").strip(),
            branch_name=(branch_name or "").strip(),
            source="google_maps",
            owner_response=(owner_response or "").strip(),
            owner_response_at=(owner_response_at or "").strip(),
            raw={
                "author": clean_author,
                "rating": rating,
                "text": clean_text,
                "published_at": published_at,
                "owner_response": owner_response,
                "owner_response_at": owner_response_at,
            },
        )
        review.content_hash = review_content_hash(review)
        return review

    def parse(self, name, rating, reviews, address):
        return self.parse_branch(name, rating, reviews, address)

    def _to_float(self, value: str | float | int | None) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        normalized = self.normalize_digits(str(value))
        match = re.search(r"\d+(?:\.\d+)?", normalized.replace(",", ""))
        if not match:
            return 0.0
        try:
            return float(match.group())
        except ValueError:
            return 0.0

    def extract_review_count(self, value: str | int | None) -> int:
        if value is None:
            return 0
        if isinstance(value, int):
            return value
        normalized = self.normalize_digits(str(value))
        patterns = [
            r"\(([0-9][0-9,]*)\)",
            r"([0-9][0-9,]*)\s*(?:reviews?|review|نظر|مرور)",
            r"(?:reviews?|review|نظر|مرور)\s*([0-9][0-9,]*)",
        ]
        for pattern in patterns:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if match:
                return self._to_int(match.group(1))
        return 0

    def _to_int(self, value: str | int | None) -> int:
        if value is None:
            return 0
        if isinstance(value, int):
            return value
        normalized = self.normalize_digits(str(value))
        match = re.search(r"\d+", normalized.replace(",", ""))
        if not match:
            return 0
        try:
            return int(match.group())
        except ValueError:
            return 0
