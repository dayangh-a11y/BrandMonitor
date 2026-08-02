from pydantic import BaseModel, Field


class Review(BaseModel):
    author: str = ""
    rating: float = 0.0
    text: str = ""
    published_at: str = ""
    language: str = ""
    external_id: str = ""
    branch_name: str = ""
    source: str = "google_maps"
    raw: dict = Field(default_factory=dict)
