from dataclasses import dataclass
from typing import List, Optional
from decimal import Decimal
from django.utils import timezone
from django.conf import settings

from .models import DiecastCar, CarMarketLink, MarketPrice


@dataclass
class MarketQuote:
    marketplace: str
    price: Decimal
    currency: str = "USD"
    source_listing_url: Optional[str] = None
    title: Optional[str] = None


class BaseProvider:
    def fetch(self, car: DiecastCar, link: Optional[CarMarketLink] = None) -> List[MarketQuote]:
        return []


class EbayProvider(BaseProvider):
    def fetch(self, car: DiecastCar, link: Optional[CarMarketLink] = None) -> List[MarketQuote]:
        # Placeholder: implement eBay Finding API/Search API here using settings.EBAY_APP_ID
        # Return empty for now to avoid external calls
        return []


class HobbyDbProvider(BaseProvider):
    def fetch(self, car: DiecastCar, link: Optional[CarMarketLink] = None) -> List[MarketQuote]:
        # Placeholder for hobbyDB API integration (requires API key)
        return []


class DiecastAuctionProvider(BaseProvider):
    def fetch(self, car: DiecastCar, link: Optional[CarMarketLink] = None) -> List[MarketQuote]:
        # Placeholder for diecast auction aggregator scraping/API
        return []


class MarketService:
    providers = {
        'ebay': EbayProvider(),
        'hobbydb': HobbyDbProvider(),
        'diecast_auction': DiecastAuctionProvider(),
    }

    def fetch_and_record(self, car: DiecastCar) -> int:
        """
        Fetch quotes from all configured sources for a car and record them as MarketPrice entries.
        Returns number of quotes recorded.
        """
        count = 0
        links = {l.marketplace: l for l in car.market_links.all()}
        for marketplace, provider in self.providers.items():
            link = links.get(marketplace)
            quotes = provider.fetch(car, link)
            for q in quotes:
                MarketPrice.objects.create(
                    car=car,
                    marketplace=marketplace,
                    price=q.price,
                    currency=q.currency,
                    fetched_at=timezone.now(),
                    source_listing_url=q.source_listing_url,
                    title=q.title,
                )
                count += 1
        return count

    @staticmethod
    def latest_and_previous(car: DiecastCar):
        qs = MarketPrice.objects.filter(car=car).order_by('-fetched_at')
        latest = qs.first()
        previous = qs[1] if qs.count() > 1 else None
        return latest, previous
