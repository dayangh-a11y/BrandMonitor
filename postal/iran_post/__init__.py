"""Dedicated Iran Post module — national operator, not a regular private carrier."""

from postal.iran_post.compare import FairComparison, NationalRanking, compare
from postal.iran_post.provider import IranPostModule

__all__ = [
    "IranPostModule",
    "NationalRanking",
    "FairComparison",
    "compare",
]
