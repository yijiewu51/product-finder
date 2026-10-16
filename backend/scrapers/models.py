from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Review:
    source: str          # "amazon_uk" | "reddit"
    product_name: str
    text: str            # title + body combined
    rating: Optional[float] = None
    date: Optional[str] = None
    helpful_votes: int = 0
    url: Optional[str] = None
