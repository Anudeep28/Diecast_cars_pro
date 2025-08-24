from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any
from decimal import Decimal
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import logging
import re
from urllib.parse import urlencode
import os
import json

import requests
from bs4 import BeautifulSoup
import time

from .models import DiecastCar, CarMarketLink, MarketPrice
from .market_types import MarketQuote
from .web_search import search_and_extract_prices
from .ai_market_scraper import search_market_prices_for_car as ai_search_market_prices_for_car
from .search_logger import get_logger, save_all_logs


# ---------------------
# FX conversion helpers
# ---------------------
_FX_CACHE = {"ts": 0.0, "per_inr": {}}  # maps CURRENCY -> amount of that currency per 1 INR
_FX_TTL_SECONDS = 3600

_CURRENCY_MAP = {
    '₹': 'INR', 'RS': 'INR', 'RS.': 'INR', 'INR': 'INR',
    '$': 'USD', 'US$': 'USD', 'USD': 'USD',
    '€': 'EUR', 'EUR': 'EUR',
    '£': 'GBP', 'GBP': 'GBP',
    '¥': 'JPY', 'JPY': 'JPY',
    'C$': 'CAD', 'CAD': 'CAD',
    'A$': 'AUD', 'AUD': 'AUD',
    'SG$': 'SGD', 'SGD': 'SGD',
    'RM': 'MYR', 'MYR': 'MYR',
    'CNY': 'CNY', 'RMB': 'CNY',
}


def _normalize_currency(cur: Optional[str]) -> str:
    if not cur:
        return 'INR'
    s = str(cur).strip()
    if not s:
        return 'INR'
    up = s.upper()
    if up in _CURRENCY_MAP:
        return _CURRENCY_MAP[up]
    # Single-symbol checks
    if s in _CURRENCY_MAP:
        return _CURRENCY_MAP[s]
    # Common prefixes
    if up.startswith('US$'):
        return 'USD'
    if up.startswith('RS'):
        return 'INR'
    return up  # assume it's already an ISO code like 'USD'


def _get_per_inr_rates() -> dict:
    now = time.time()
    if now - _FX_CACHE["ts"] > _FX_TTL_SECONDS or not _FX_CACHE["per_inr"]:
        try:
            resp = requests.get('https://api.exchangerate.host/latest?base=INR', timeout=8)
            resp.raise_for_status()
            data = resp.json() or {}
            rates = data.get('rates') or {}
            per_inr = {}
            for code, val in rates.items():
                try:
                    per_inr[code.upper()] = Decimal(str(val))
                except Exception:  # noqa: BLE001
                    continue
            if per_inr:
                _FX_CACHE["per_inr"] = per_inr
                _FX_CACHE["ts"] = now
        except Exception:  # noqa: BLE001
            # leave cache as-is; fallbacks handled in convert
            pass
    return _FX_CACHE["per_inr"]


def convert_to_inr(amount: Decimal, currency: Optional[str]) -> Decimal:
    """Convert an amount in the given currency to INR using cached FX rates.
    Falls back to static approximations if live rates are unavailable.
    """
    try:
        amt = Decimal(str(amount))
    except Exception:  # noqa: BLE001
        return Decimal('0')
    cur = _normalize_currency(currency)
    if cur == 'INR':
        return amt
    rates = _get_per_inr_rates()  # currency per 1 INR
    per_inr = rates.get(cur)
    try:
        if per_inr and per_inr != 0:
            # amount (cur) -> INR: divide by (cur per INR)
            return (amt / per_inr)
    except Exception:  # noqa: BLE001
        pass
    # Static fallbacks: INR per unit of currency
    INR_PER = {
        'USD': Decimal('84'),
        'EUR': Decimal('92'),
        'GBP': Decimal('108'),
        'JPY': Decimal('0.55'),
        'CAD': Decimal('62'),
        'AUD': Decimal('57'),
        'SGD': Decimal('62'),
        'MYR': Decimal('18'),
        'CNY': Decimal('11'),
    }
    if cur in INR_PER:
        return amt * INR_PER[cur]
    # Unknown currency: assume already INR
    return amt


class BaseProvider:
    def fetch(self, car: DiecastCar, link: Optional[CarMarketLink] = None) -> List[MarketQuote]:
        return []


class WebSearchProvider(BaseProvider):
    def fetch(self, car: DiecastCar, link: Optional[CarMarketLink] = None) -> List[MarketQuote]:
        """Simplified web search using crawl4ai + Gemini extraction with intelligent filtering."""
        logger = logging.getLogger(__name__)
        gemini_key = getattr(settings, 'GEMINI_API_KEY', None)
        
        if not gemini_key:
            logger.warning("No Gemini API key - skipping web search")
            return []
            
        manu = (car.manufacturer or '').strip()
        model = (car.model_name or '').strip()
        scale = (car.scale or '').strip()
        
        # Use the AI market scraper as the primary method
        try:
            # Ensure car has required attributes
            if not manu or not model:
                return []
                
            items = None
            try:
                from .ai_market_scraper import search_market_prices_for_car as ai_search_market_prices_for_car
                result = ai_search_market_prices_for_car(car, gemini_key, num_results=4)
                if result and isinstance(result, tuple) and len(result) >= 2:
                    items = result[0]  # First item is extracted data
                    # Second is extracted markdown if we need it
                    self.last_extracted_markdown = result[1] if len(result) > 1 else {}
                    # Display the Gemini-generated search query in the terminal
                    if len(result) > 2 and result[2]:
                        query = result[2]
                        # Use logger for more reliable terminal output
                        logger.info("\n" + "=" * 80)
                        logger.info(f"GEMINI SEARCH QUERY: \"{query}\"")
                        logger.info("=" * 80)
                        # Also use print for direct terminal output
                        print("\n" + "=" * 80)
                        print(f"GEMINI SEARCH QUERY: \"{query}\"")
                        print("=" * 80)
                        # Store the query for potential later use
                        self.last_search_query = query
            except Exception as e:
                pass
            quotes: List[MarketQuote] = []
            for item in items or []:
                try:
                    # Simple validation - just check if we have a valid price
                    if not hasattr(item, 'price') or not item.price or item.price <= 0:
                        continue
                    
                    # INTELLIGENT FILTERING: Validate if the extracted item matches our target car
                    if not self._is_relevant_match(car, item, logger):
                        continue
                        
                    # Extract seller from URL if not provided
                    seller = getattr(item, 'seller', None)
                    if not seller and getattr(item, 'url', None):
                        seller = self._extract_seller_from_url(item.url)
                    
                    quote = MarketQuote(
                        'web',
                        Decimal(str(item.price)),
                        currency=getattr(item, 'currency', 'USD') or 'USD',
                        source_listing_url=getattr(item, 'url', None),
                        title=getattr(item, 'title', None),
                        model_name=getattr(item, 'model_name', None),
                        manufacturer=getattr(item, 'manufacturer', None),
                        scale=getattr(item, 'scale', None),
                        seller=seller,
                    )
                    
                    quotes.append(quote)
                except Exception as e:
                    continue
                    
        except Exception as e:
            pass
            
        return quotes
        
    def _is_relevant_match(self, target_car: DiecastCar, extracted_item, logger) -> bool:
        """AI-powered agentic validation to check if extracted item matches target car specifications."""
        try:
            # Try agentic validation first
            from .agentic_validator import get_agentic_validator
            validator = get_agentic_validator()
            
            if validator:
                validation_result = validator.validate_quote_relevance(target_car, extracted_item)
                
                pass
                
                # Use AI decision if confidence is reasonable
                if validation_result['confidence'] >= 0.3:
                    return validation_result['is_relevant']
                else:
                    pass
            
            # Fallback to basic validation if AI is unavailable or low confidence
            return self._basic_relevance_check(target_car, extracted_item, logger)
            
        except Exception as e:
            return self._basic_relevance_check(target_car, extracted_item, logger)
    
    def _basic_relevance_check(self, target_car: DiecastCar, extracted_item, logger) -> bool:
        """Permissive fallback validation when AI is unavailable - relies on search query accuracy."""
        try:
            return True  # Allow all quotes when AI is unavailable
            
        except Exception as e:
            return True  # Permissive fallback
    
    # All hard-coded validation methods removed - now using AI-powered agentic validation only
    
    def _extract_seller_from_url(self, url: str) -> Optional[str]:
        """Extract seller name from URL domain."""
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # Common marketplace mappings
            marketplace_map = {
                'ebay.com': 'eBay', 'ebay.in': 'eBay', 'ebay.co.uk': 'eBay',
                'amazon.com': 'Amazon', 'amazon.in': 'Amazon',
                'flipkart.com': 'Flipkart',
                'aliexpress.com': 'AliExpress',
                'etsy.com': 'Etsy',
                'facebook.com': 'Facebook',
                'reddit.com': 'Reddit',
            }
            
            for domain_key, name in marketplace_map.items():
                if domain.endswith(domain_key):
                    return name
                    
            # Extract main domain name
            parts = domain.split('.')
            if len(parts) >= 2:
                return parts[-2].capitalize()
                
            return domain.capitalize()
        except Exception:
            return None

class EbayProvider(BaseProvider):
    def fetch(self, car: DiecastCar, link: Optional[CarMarketLink] = None) -> List[MarketQuote]:
        """Use eBay Finding API to search by keywords if APP ID configured.
        Docs: https://developer.ebay.com/devzone/finding/callref/finditemsbykeywords.html
        """
        app_id = getattr(settings, 'EBAY_APP_ID', None)
        keywords = f"{car.manufacturer} {car.model_name} {car.scale}".strip()
        # If explicit identifier provided, include it to increase precision
        if link and link.external_id:
            keywords = f"{keywords} {link.external_id}"
        quotes: List[MarketQuote] = []
        if app_id:
            endpoint = "https://svcs.ebay.com/services/search/FindingService/v1"
            params = {
                'OPERATION-NAME': 'findItemsByKeywords',
                'SERVICE-VERSION': '1.0.0',
                'SECURITY-APPNAME': app_id,
                'RESPONSE-DATA-FORMAT': 'JSON',
                'REST-PAYLOAD': 'true',
                'keywords': keywords,
                'paginationInput.entriesPerPage': 5,
                'sortOrder': 'PricePlusShippingLowest',
            }

            try:
                resp = requests.get(endpoint, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                items = data.get('findItemsByKeywordsResponse', [{}])[0].get('searchResult', [{}])[0].get('item', [])
                for it in items:
                    selling = it.get('sellingStatus', [{}])[0]
                    curr = selling.get('currentPrice', [{}])[0]
                    price_str = curr.get('__value__')
                    currency = curr.get('@currencyId', 'USD')
                    url = it.get('viewItemURL', [None])[0]
                    title = it.get('title', [None])[0]
                    if price_str:
                        try:
                            price = Decimal(str(price_str))
                            quotes.append(MarketQuote('ebay', price, currency=currency, source_listing_url=url, title=title))
                        except Exception:  # noqa: BLE001
                            continue
            except Exception as e:  # noqa: BLE001
                pass

        # Fallback: scrape eBay search results page if API not configured or yielded no quotes
        if not quotes:
            try:
                search_url = "https://www.ebay.com/sch/i.html?_nkw=" + requests.utils.quote(keywords)
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
                    'Accept-Language': 'en-US,en;q=0.9',
                }
                r = requests.get(search_url, headers=headers, timeout=10)
                r.raise_for_status()
                soup = BeautifulSoup(r.text, 'html.parser')
                items = soup.select('.s-item')
                for node in items[:5]:
                    # Title and link
                    atag = node.select_one('a.s-item__link')
                    title_el = node.select_one('.s-item__title')
                    price_el = node.select_one('.s-item__price')
                    if not price_el:
                        continue
                    price_match = _extract_price_from_text(price_el.get_text(' ', strip=True))
                    if not price_match:
                        continue
                    amount, currency = price_match
                    url = atag['href'] if atag and atag.has_attr('href') else search_url
                    title = title_el.get_text(' ', strip=True) if title_el else None
                    quotes.append(MarketQuote('ebay', amount, currency=currency, source_listing_url=url, title=title))
                return quotes
            except Exception as e:  # noqa: BLE001
                pass
        return quotes


class HobbyDbProvider(BaseProvider):
    def fetch(self, car: DiecastCar, link: Optional[CarMarketLink] = None) -> List[MarketQuote]:
        """Try hobbyDB API if key present; else fall back to scraping link URL if provided."""
        api_key = getattr(settings, 'HOBBYDB_API_KEY', None)
        # hobbyDB API access is limited; without an API we attempt scraping the provided URL
        if link and link.url:
            quote = _scrape_price_from_url(link.url)
            return [MarketQuote('hobbydb', quote[0], currency=quote[1], source_listing_url=link.url, title=quote[2])] if quote else []
        return []


class DiecastAuctionProvider(BaseProvider):
    def fetch(self, car: DiecastCar, link: Optional[CarMarketLink] = None) -> List[MarketQuote]:
        """Scrape price from the provided auction page URL if present."""
        if link and link.url:
            quote = _scrape_price_from_url(link.url)
            return [MarketQuote('diecast_auction', quote[0], currency=quote[1], source_listing_url=link.url, title=quote[2])] if quote else []
        return []


class FacebookProvider(BaseProvider):
    def fetch(self, car: DiecastCar, link: Optional[CarMarketLink] = None) -> List[MarketQuote]:
        """Attempt to fetch price from a Facebook Marketplace link. Requires login; we support
        optional cookie via settings.FACEBOOK_COOKIE for best results. Falls back to public scraping.
        """
        if not link or not link.url:
            return []
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        cookie = getattr(settings, 'FACEBOOK_COOKIE', None)
        if cookie:
            headers['Cookie'] = cookie
        try:
            r = requests.get(link.url, headers=headers, timeout=15)
            r.raise_for_status()
            # Facebook often serves minimal HTML; try to extract price patterns
            quote = _extract_price_from_text(r.text)
            if quote:
                price, currency = quote
                title = _extract_title_from_html(r.text)
                return [MarketQuote('facebook', price, currency=currency, source_listing_url=link.url, title=title)]
        except Exception as e:  # noqa: BLE001
            pass
        return []


class MarketService:
    providers = {
        'web': WebSearchProvider(),
        # Temporarily disable eBay provider due to fallback data issues
        # 'ebay': EbayProvider(),
        'hobbydb': HobbyDbProvider(),
        'diecast_auction': DiecastAuctionProvider(),
        'facebook': FacebookProvider(),
    }

    def fetch_and_record(self, car: DiecastCar, save_extracted_markdown: bool = False,
                      include_search_queries: bool = False, log_search_data: bool = True) -> dict:
        """
        Fetch quotes from all configured sources for a car, record as MarketPrice entries,
        and calculate average prices and comparisons with the user's car value.
        
        Args:
            car: The DiecastCar object to fetch prices for
            save_extracted_markdown: If True, save the extracted markdown from Gemini
            include_search_queries: If True, include search queries used for URL finding
            log_search_data: If True, save logs of search data
        
        Returns a stats dict with:
            count: total quotes recorded (int)
            all_avg_price: Decimal - average price across all sources (INR)
            car_value_comparison: dict containing comparison between market value and user's car value
            market_quotes: dict of quotes by marketplace, each with current price data
            user_value: the current value of the user's car (from car.price)
            search_queries: list of queries used (if include_search_queries=True)
            extracted_markdown: raw markdown content from Gemini (if save_extracted_markdown=True)
        """
        count = 0
        quotes_by_source = {}
        all_quotes_this_run = []
        per_market_counts = {name: 0 for name in self.providers.keys()}
        market_details = {name: [] for name in self.providers.keys()}
        search_queries_used = []
        extracted_markdown = {}
        saved_count = 0
        # Use a single timestamp for this fetch run to group quotes together
        batch_time = timezone.now()
        stats = {
            'count': 0,                   # How many quotes we successfully saved
            'web_avg_price': None,        # Average market price from web results
            'all_avg_price': None,        # All sources average price in INR
            'user_value': None,           # User's assigned value for this car
            'source_averages': {},        # Per-source price averages
            'per_source_quotes': {},      # Dict of source -> List[MarketQuote] 
            'per_market_counts': {},      # Dict of marketplace -> count
        }
        
        # Get user's car value (converted to INR if needed)
        user_value = None
        if car.price is not None and car.price > 0:
            user_value = convert_to_inr(car.price, 'INR')
        
        # Initialize logger for this car if logging is enabled
        logger = None
        if log_search_data:
            logger = get_logger(car.id, f"{car.manufacturer} {car.model_name}")
            
        # Create extracted_markdown directory if needed
        if save_extracted_markdown:
            markdown_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'extracted_markdown')
            os.makedirs(markdown_dir, exist_ok=True)
        
        # Simplified duplicate detection - only check exact URL matches within the same run
        def is_duplicate(new_quote, existing_quotes):
            """Check for exact URL duplicates only within the SAME RUN."""
            if not existing_quotes:
                return False
        
            # Support either key to be safe
            new_url = new_quote.get('source_listing_url') or new_quote.get('url')
            if not new_url:
                return False  # No URL to compare
        
            for q in existing_quotes:
                q_url = q.get('source_listing_url') or q.get('url')
                if q_url and q_url == new_url:
                    return True
            return False
        
        # Fetch from each provider
        links = {l.marketplace: l for l in car.market_links.all()}
        for marketplace, provider in self.providers.items():
            # Always run 'web'. Other providers only run if a link exists.
            if marketplace not in ('web',) and marketplace not in links:
                continue
                
            link = links.get(marketplace)
            quotes = provider.fetch(car, link)
            quotes_by_source[marketplace] = []
            
            pass
            
            # If it's the web provider and we need to track search queries
            if marketplace == 'web':
                # Get search query from WebSearchProvider if available
                if hasattr(provider, 'last_search_query') and getattr(provider, 'last_search_query', None):
                    query = getattr(provider, 'last_search_query')
                    search_queries_used = [query]
                # For backward compatibility
                elif include_search_queries and hasattr(provider, 'last_queries'):
                    search_queries_used = getattr(provider, 'last_queries', [])
                
            # If we need to save extracted markdown and it's available
            if save_extracted_markdown and hasattr(provider, 'last_extracted_markdown'):
                try:
                    md_content = getattr(provider, 'last_extracted_markdown', {})
                    if md_content:
                        extracted_markdown[marketplace] = md_content
                except Exception as md_err:
                    logging.warning(f"Failed to get extracted markdown: {md_err}")
                        
            # Process each quote from this provider
            for idx, q in enumerate(quotes):
                try:
                    pass
                    
                    # Always convert to INR for consistency
                    try:
                        price_decimal = Decimal(str(q.price))
                        inr_val = convert_to_inr(price_decimal, q.currency)
                        if inr_val <= 0:
                            continue
                    except Exception as conv_err:
                        continue
                        
                    # Store the quote details
                    quote_details = {
                        'title': q.title,
                        'price_inr': inr_val,
                        'original_price': q.price,
                        'original_currency': q.currency,
                        'currency': 'INR',
                        # Provide source_listing_url explicitly for API consumers
                        'source_listing_url': q.source_listing_url,
                        # Keep legacy key for any older front-ends
                        'url': q.source_listing_url,
                        'model_name': q.model_name,
                        'manufacturer': q.manufacturer,
                        'scale': q.scale,
                        'seller': q.seller,
                        'fetched_at': batch_time.isoformat(),
                    }
                    
                    # Only check for exact URL duplicates in this run
                    if is_duplicate(quote_details, quotes_by_source[marketplace]):
                        continue
                    
                    # Save to database with additional fields
                    price_obj = MarketPrice.objects.create(
                        car=car,
                        marketplace=marketplace,
                        price=inr_val,
                        currency='INR',  # We save everything in INR for consistency
                        fetched_at=batch_time,
                        source_listing_url=q.source_listing_url,
                        title=q.title or f"{q.manufacturer or ''} {q.model_name or ''}".strip() or 'Unknown'
                    )
                    saved_count += 1
                    
                    # Log the saved price if logging is enabled
                    if log_search_data and logger:
                        pass
                    
                    # Track in our per-market breakdowns
                    per_market_counts[marketplace] = per_market_counts.get(marketplace, 0) + 1
                    
                    # Add to our tracking collections
                    quotes_by_source[marketplace].append(quote_details)
                    market_details[marketplace].append(quote_details)
                    all_quotes_this_run.append(inr_val)
                    count += 1
                    
                except Exception as e:  # noqa: BLE001
                    pass
        
        # Disable logging
        pass
        
        # Calculate overall average from all sources
        all_avg = None
        if all_quotes_this_run:
            nonzero = [v for v in all_quotes_this_run if v and v > 0]
            if nonzero:
                all_avg = sum(nonzero) / Decimal(len(nonzero))
        
        # Create comparison with user's car value
        comparison = None
        if user_value is not None and all_avg is not None:
            diff = user_value - all_avg
            pct = None
            if all_avg > 0:
                pct = (diff / all_avg) * Decimal('100')
                
            comparison = {
                'diff_absolute': diff,
                'diff_percentage': pct,
                'is_undervalued': diff < 0,
                'is_overvalued': diff > 0
            }
        
        # Print final result for user
        if all_quotes_this_run:
            print(f"✅ Found {count} market quotes for {car.manufacturer} {car.model_name}")
            if all_avg:
                print(f"💰 Average market price: ₹{all_avg:.2f}")
        else:
            print(f"ℹ️ No market quotes found for {car.manufacturer} {car.model_name}")
            
        # Clean up market_details to only include sources with actual data
        market_quotes = {k: v for k, v in market_details.items() if v}

        result = {
            'count': count,
            'all_avg_price': all_avg,
            'user_value': user_value,
            'car_value_comparison': comparison,
            'source_averages': {},
            'market_quotes': market_quotes,
            'per_market_counts': per_market_counts,
        }
        
        # Add optional data if requested
        if include_search_queries:
            result['search_queries'] = search_queries_used
            
        if save_extracted_markdown:
            result['extracted_markdown'] = extracted_markdown
            
        return result

    @staticmethod
    def latest_and_previous(car: DiecastCar):
        qs = MarketPrice.objects.filter(car=car).order_by('-fetched_at')
        latest = qs.first()
        previous = qs[1] if qs.count() > 1 else None
        return latest, previous


# ---------------------
# Helper scraping utils
# ---------------------

# Removed _string_similarity function - no longer needed with AI-powered validation

PRICE_REGEXES = [
    # Symbol/code before amount
    re.compile(r"(?:₹|Rs\.?\s?|INR\s*)([\d,]+(?:\.\d{1,2})?)", re.I),
    re.compile(r"(?:US\$|USD|\$)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
    re.compile(r"(?:€|EUR)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
    re.compile(r"(?:£|GBP)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
    re.compile(r"(?:¥|JPY)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
    re.compile(r"(?:C\$|CA\$|CAD)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
    re.compile(r"(?:A\$|AUD)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
    re.compile(r"(?:SG\$|SGD)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
    re.compile(r"(?:RM|MYR)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
    re.compile(r"(?:CNY|RMB)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
    # Amount before code/symbol
    re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:₹|Rs\.?|INR)", re.I),
    re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:US\$|USD|\$)", re.I),
    re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:€|EUR)", re.I),
    re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:£|GBP)", re.I),
    re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:¥|JPY)", re.I),
    re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:C\$|CA\$|CAD)", re.I),
    re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:A\$|AUD)", re.I),
    re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:SG\$|SGD)", re.I),
    re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:RM|MYR)", re.I),
    re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:CNY|RMB)", re.I),
]


def _extract_title_from_html(html: str) -> Optional[str]:
    try:
        soup = BeautifulSoup(html, 'html.parser')
        if soup.title and soup.title.text:
            return soup.title.text.strip()
        og = soup.find('meta', attrs={'property': 'og:title'})
        if og and og.get('content'):
            return og['content'].strip()
    except Exception:  # noqa: BLE001
        return None
    return None


def _extract_price_from_text(text: str) -> Optional[Tuple[Decimal, str]]:
    for rx in PRICE_REGEXES:
        m = rx.search(text)
        if m:
            num = m.group(1).replace(',', '')
            try:
                val = Decimal(num)
            except Exception:  # noqa: BLE001
                continue
            s = m.group(0)
            s_up = s.upper()
            currency = 'INR'
            if '₹' in s or 'INR' in s_up or 'RS' in s_up:
                currency = 'INR'
            elif 'US$' in s_up or 'USD' in s_up or '$' in s:
                currency = 'USD'
            elif '€' in s or 'EUR' in s_up:
                currency = 'EUR'
            elif '£' in s or 'GBP' in s_up:
                currency = 'GBP'
            elif 'C$' in s or 'CA$' in s_up or 'CAD' in s_up:
                currency = 'CAD'
            elif 'A$' in s or 'AUD' in s_up:
                currency = 'AUD'
            elif 'SG$' in s_up or 'SGD' in s_up:
                currency = 'SGD'
            elif 'RM' in s_up or 'MYR' in s_up:
                currency = 'MYR'
            elif 'RMB' in s_up or 'CNY' in s_up:
                currency = 'CNY'
            elif '¥' in s or 'JPY' in s_up:
                currency = 'JPY'
            return val, currency
    return None


def _scrape_price_from_url(url: str) -> Optional[Tuple[Decimal, str, Optional[str]]]:
    """Extract price information from a URL using Gemini API or fallback methods."""
    from django.conf import settings
    gemini_api_key = getattr(settings, 'GEMINI_API_KEY', None)
    
    # Use Gemini if API key is available
    if gemini_api_key:
        try:
            from .gemini_client import GeminiClient
            client = GeminiClient(gemini_api_key)
            extraction = client.extract_price_from_url(url)
            if extraction and extraction.price > 0:
                return extraction.price, extraction.currency, extraction.title
        except Exception as e:
            logging.warning(f"Gemini extraction failed: {e}")
    
    # Fallback to traditional request/parsing if Gemini fails or is unavailable
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        title = _extract_title_from_html(r.text)
        price = _extract_price_from_text(r.text)
        if price:
            return price[0], price[1], title
    except Exception as e:  # noqa: BLE001
        pass
    
    return None
