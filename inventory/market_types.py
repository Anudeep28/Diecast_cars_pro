from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class MarketQuote:
    marketplace: str
    price: Decimal
    currency: str = "INR"
    source_listing_url: Optional[str] = None
    title: Optional[str] = None
    model_name: Optional[str] = None
    manufacturer: Optional[str] = None
    scale: Optional[str] = None
    seller: Optional[str] = None
