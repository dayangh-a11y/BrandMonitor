from pydantic import BaseModel, Field


class Branch(BaseModel):
    name: str
    rating: float = 0.0
    review_count: int = 0
    address: str = ""
    maps_url: str = ""
    place_id: str = ""
    company_name: str = ""
