from __future__ import annotations

import asyncio
import logging

# Use the inventory logger for better log organization
logger = logging.getLogger('inventory.web_search')
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from django.conf import settings

from inventory.models import CarMarketLink, DiecastCar
from inventory.market_types import MarketQuote

try:
    # crawl4ai imports (optional at runtime) - use top-level exports for compatibility
    from crawl4ai import (
        BrowserConfig,
        BM25ContentFilter,
        DefaultMarkdownGenerator,
        LLMExtractionStrategy,
        LLMConfig,
        AsyncWebCrawler,
    )
    CRAWL4AI_AVAILABLE = True
except Exception:  # noqa: BLE001
    CRAWL4AI_AVAILABLE = False

try:
    from pydantic import BaseModel, Field
    PYDANTIC_AVAILABLE = True
except Exception:  # noqa: BLE001
    PYDANTIC_AVAILABLE = False

from .search_logger import get_logger

# -------------------------
# Pydantic schema for prices
# -------------------------
if PYDANTIC_AVAILABLE:
    class WebSearchProvider(BaseModel):
        last_queries: List[str] = []
        last_extracted_markdown: dict = {}

        class PriceItem(BaseModel):
            price: float = Field(..., description="Product price amount (numeric)")
            currency: str = Field(..., description="Currency code or symbol, e.g., USD, INR, $, ₹")
            title: Optional[str] = Field(None, description="Page or product title")
            url: Optional[str] = Field(None, description="Source URL")
            model_name: Optional[str] = Field(None, description="Model car name, e.g., 'Ferrari 488 GTB'")
            manufacturer: Optional[str] = Field(None, description="Brand/manufacturer, e.g., Hot Wheels, AUTOart")
            scale: Optional[str] = Field(None, description="Scale notation like '1:18' or '1/64'")
            seller: Optional[str] = Field(None, description="Seller or marketplace name")

        def fetch(self, car: DiecastCar, link: Optional[CarMarketLink] = None) -> List[MarketQuote]:
            """Use search engines to build queries for the model car and run searches."""
            quotes: List[MarketQuote] = []
            model = car.model_name
            brand = car.manufacturer
            deepseek_key = getattr(settings, 'DEEPSEEK_API_KEY', None)
            
            # Reset tracking for this run
            self.last_queries = []
            self.last_extracted_markdown = {}
            
            # Build search queries for the specific car
            queries = []
            if brand and model:
                queries.append(f"{brand} {model} diecast model car price")
                # Add scale if available
                if car.scale:
                    queries.append(f"{brand} {model} diecast model {car.scale} scale price")
            
            if not queries:  # Fallback
                queries.append(f"diecast model car {model} price")
                
            # Store the queries for reference
            self.last_queries = queries.copy()
            
            # Log the query terms we're using
            log = logging.getLogger(__name__)
            log.warning("WebSearchProvider: Running %d queries for car %s: %s", len(queries), car.id, ", ".join(queries))
            
            for q in queries:
                try:
                    results, markdown_content = search_and_extract_prices(
                        q, deepseek_key, max_results=8, 
                        car_id=car.id, car_name=f"{brand} {model}"
                    )
                    
                    # Store extracted markdown content for reference
                    self.last_extracted_markdown.update(markdown_content)
                    
                    if not results:
                        continue
                    
                    for item in results:
                        market_quote = MarketQuote(
                            'web',
                            item.price,
                            currency=item.currency,
                            source_listing_url=item.url,
                            title=item.title,
                            model_name=item.model_name,
                            manufacturer=item.manufacturer,
                            scale=item.scale,
                            seller=item.seller
                        )
                        
                        # Log the final price result
                        try:
                            if car and car.id:
                                logger = get_logger(car.id, f"{brand} {model}")
                                logger.log_price_result('web', {
                                    'title': item.title,
                                    'price': float(item.price),
                                    'currency': item.currency,
                                    'url': item.url,
                                    'model_name': item.model_name,
                                    'manufacturer': item.manufacturer,
                                    'scale': item.scale,
                                    'seller': item.seller
                                })
                        except Exception as log_err:
                            # Don't let logging errors affect the main flow
                            logger.warning(f"Failed to log price result: {log_err}")
                            
                        quotes.append(market_quote)
                except Exception as e:  # noqa: BLE001
                    logging.exception("WebSearchProvider failed on query '%s': %s", q, e)
                        
            return quotes
else:
    # Lightweight fallback if Pydantic missing
    @dataclass
    class PriceItem:
        price: float
        currency: str
        title: Optional[str] = None
        url: Optional[str] = None
        model_name: Optional[str] = None
        manufacturer: Optional[str] = None
        scale: Optional[str] = None
        seller: Optional[str] = None


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}


def _guess_seller_from_url(url: str) -> Optional[str]:
    """Derive a seller/marketplace name from the URL's domain."""
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        # Friendly names for common marketplaces
        mapping = {
            'ebay.com': 'eBay', 'ebay.in': 'eBay', 'ebay.co.uk': 'eBay', 'ebay.de': 'eBay',
            'amazon.com': 'Amazon', 'amazon.in': 'Amazon', 'amazon.co.uk': 'Amazon',
            'flipkart.com': 'Flipkart', 'aliexpress.com': 'AliExpress',
            'etsy.com': 'Etsy', 'mercari.com': 'Mercari', 'rakuten.co.jp': 'Rakuten',
            'olx.in': 'OLX', 'olx.com': 'OLX', 'walmart.com': 'Walmart',
        }
        for domain, name in mapping.items():
            if netloc.endswith(domain):
                return name
        # Fallback to the registrable domain part
        parts = netloc.split(':')[0].split('.')
        if len(parts) >= 2:
            return parts[-2].capitalize()
        return netloc
    except Exception:
        return None


def _guess_scale(text: str) -> Optional[str]:
    """Find a scale like 1:18 or 1/64 within text and normalize to 1:X."""
    if not text:
        return None
    try:
        import re
        # Try common patterns: 1:18, 1 / 18, 1/18, 1-18, 1×18
        m = re.search(r"\b1\s*[:/xX\-]\s*(\d{1,3})\b", text)
        if m:
            return f"1:{m.group(1)}"
        # Also allow pattern like "Scale 1:64"
        m = re.search(r"\bscale\s*1\s*[:/]\s*(\d{1,3})\b", text, re.I)
        if m:
            return f"1:{m.group(1)}"
        return None
    except Exception:
        return None


def _guess_brand(text: str) -> Optional[str]:
    """Heuristically detect a manufacturer brand from text/title."""
    if not text:
        return None
    brands = [
        'Hot Wheels', 'Maisto', 'Bburago', 'AUTOart', 'Minichamps', 'Kyosho', 'Tomica',
        'Matchbox', 'Tarmac Works', 'INNO64', 'Norev', 'GreenLight', 'Solido', 'Welly',
        'Sun Star', 'CMC', 'HPI', 'Spark', 'GT Spirit', 'IXO', 'Schuco', 'Hobby Japan',
    ]
    try:
        import re
        for b in brands:
            if re.search(rf"\b{re.escape(b)}\b", text, re.I):
                return b
        return None
    except Exception:
        return None


def _guess_model_name(title: Optional[str], manufacturer: Optional[str], scale: Optional[str]) -> Optional[str]:
    """Try to distill a model name from the title by removing brand and scale tokens."""
    if not title:
        return None
    try:
        import re
        t = title
        if manufacturer:
            t = re.sub(rf"\b{re.escape(manufacturer)}\b", " ", t, flags=re.I)
        # Remove scale tokens
        t = re.sub(r"\b1\s*[:/xX\-]\s*\d{1,3}\b", " ", t)
        t = re.sub(r"\bscale\s*1\s*[:/]\s*\d{1,3}\b", " ", t, flags=re.I)
        # Collapse spaces
        t = re.sub(r"\s+", " ", t).strip()
        return t or None
    except Exception:
        return None


def _extract_price_regex(text: str) -> Optional[PriceItem]:
    # Simple regex fallback to detect common price patterns
    import re
    patterns = [
        # Symbol/code before amount
        re.compile(r"(?:₹|Rs\.?\s?|INR\s*)([\d,]+(?:\.\d{1,2})?)", re.I),
        re.compile(r"(?:US\$|USD|\$)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
        re.compile(r"(?:€|EUR)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
        re.compile(r"(?:£|GBP)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
        re.compile(r"(?:C\$|CA\$|CAD)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
        re.compile(r"(?:A\$|AUD)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
        re.compile(r"(?:SG\$|SGD)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
        re.compile(r"(?:RM|MYR)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
        re.compile(r"(?:CNY|RMB)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
        re.compile(r"(?:¥|JPY)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
        # Amount before code/symbol
        re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:₹|Rs\.?|INR)", re.I),
        re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:US\$|USD|\$)", re.I),
        re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:€|EUR)", re.I),
        re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:£|GBP)", re.I),
        re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:C\$|CA\$|CAD)", re.I),
        re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:A\$|AUD)", re.I),
        re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:SG\$|SGD)", re.I),
        re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:RM|MYR)", re.I),
        re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:CNY|RMB)", re.I),
        re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:¥|JPY)", re.I),
    ]
    for rx in patterns:
        m = rx.search(text)
        if not m:
            continue
        num = m.group(1).replace(',', '')
        try:
            val = float(num)
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
        return PriceItem(price=val, currency=currency)
    return None


def google_search_urls(query: str, max_links: int = 3) -> List[str]:
    # Add params to reduce localization prompts and increase direct results
    base = "https://www.google.com/search"
    params = {
        'q': query,
        'hl': 'en',
        'num': '10',
        'pws': '0',
    }
    r = requests.get(base, params=params, headers=HEADERS, timeout=12)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    links: List[str] = []
    for a in soup.select('a'):
        href = a.get('href')
        if not href:
            continue
        # Support both relative and absolute Google redirect URLs
        if href.startswith('/url?') or href.startswith('https://www.google.com/url?'):
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            target = qs.get('q', [None])[0] or qs.get('url', [None])[0]
            if target and target.startswith('http') and 'google.' not in urlparse(target).netloc:
                links.append(target)
        elif href.startswith('http'):
            # Direct external link
            netloc = urlparse(href).netloc
            if netloc and 'google.' not in netloc:
                links.append(href)
        if len(links) >= max_links:
            break
    return links


def duckduckgo_search_urls(query: str, max_links: int = 3) -> List[str]:
    url = "https://duckduckgo.com/html/?q=" + requests.utils.quote(query)
    r = requests.get(url, headers=HEADERS, timeout=12)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    links: List[str] = []
    for a in soup.select('a.result__a'):
        href = a.get('href')
        if not href:
            continue
        # DDG often uses redirect links like /l/?uddg=<encoded>
        if href.startswith('/l/?') or href.startswith('https://duckduckgo.com/l/?'):
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            target = qs.get('uddg', [None])[0]
            if target and target.startswith('http'):
                links.append(target)
        elif href.startswith('http'):
            links.append(href)
        if len(links) >= max_links:
            break
    return links


def search_engine_urls(query: str, max_links: int = 3) -> List[str]:
    # Try Google first, then fall back to DuckDuckGo
    try:
        urls = google_search_urls(query, max_links=max_links)
    except Exception:
        urls = []
    if not urls:
        try:
            urls = duckduckgo_search_urls(query, max_links=max_links)
        except Exception:
            urls = []
    return urls


async def _crawl_and_extract(url: str, gemini_api_key: Optional[str]) -> tuple[Optional[PriceItem], Optional[str]]:
    """Use crawl4ai + Gemini extraction to pull a price from a page.
    Returns a tuple of (extracted_item, markdown_content)
    """
    if not (CRAWL4AI_AVAILABLE and PYDANTIC_AVAILABLE):
        logger.warning(f"Crawl4AI or Pydantic not available for URL: {url}")
        return None, None

    browser_config = BrowserConfig(headless=True, text_mode=True, java_script_enabled=True)
    bm25_filter = BM25ContentFilter()
    md_generator = DefaultMarkdownGenerator(
        content_filter=bm25_filter,
        options={
            "ignore_links": True,
            "ignore_images": True,
            "escape_html": True,
            "skip_internal_links": True,
            "body_width": 80,
        },
    )

    instruction = (
        "Extract details for the diecast model on this page. "
        "If multiple prices exist, choose the current selling price. "
        "Return strict JSON with fields: price (number), currency (symbol or code), title (string), url (string), "
        "model_name (string|null), manufacturer (string|null), scale (string|null), seller (string|null). "
        "Prefer scale formats like '1:18' or '1/64'. If a field is unknown, set it to null. "
        "Do not include extra fields."
    )

    # Only proceed with LLM extraction if we have a valid API key
    if not gemini_api_key:
        logger.warning(f"No Gemini API key available for URL: {url}, skipping LLM extraction")
        # We need to crawl first to get markdown content for regex fallback
        pass  # Continue with crawling to get markdown content

    markdown_content = None
    strategy = None
    
    # Only create extraction strategy if we have a valid API key
    if gemini_api_key:
        provider = "gemini/gemini-2.0-flash"
        api_token = gemini_api_key

        strategy = LLMExtractionStrategy(
            llm_config=LLMConfig(provider=provider, api_token=api_token),
            schema=PriceItem.model_json_schema(),
            extraction_type="schema",
            chunk_token_threshold=2048,
            overlap_rate=0.1,
            apply_chunking=True,
            instruction=instruction,
        )
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Run with or without extraction strategy depending on API key availability
        if strategy:
            result = await crawler.arun(
                url=url,
                content_filter=bm25_filter,
                markdown_generator=md_generator,
                extraction_strategy=strategy,
            )
        else:
            # Just crawl for markdown content without LLM extraction
            result = await crawler.arun(
                url=url,
                content_filter=bm25_filter,
                markdown_generator=md_generator,
            )
    
    # Save the generated markdown content
    try:
        if hasattr(result, 'markdown_content') and result.markdown_content:
            markdown_content = result.markdown_content
            logger.info(f"Crawl4AI markdown content length for {url}: {len(markdown_content) if markdown_content else 0}")
    except Exception:
        pass

    # Log all available attributes from the result
    logger.info(f"Crawl4AI result attributes for {url}: {[attr for attr in dir(result) if not attr.startswith('_')]}")
    
    # Try to get extracted content (only available if we used LLM extraction)
    data = getattr(result, 'extracted_content', None) if strategy else None
    logger.info(f"Raw extracted_content from Crawl4AI for {url}: {data}")
            # Handle dict or JSON string
    if not data:
        if not gemini_api_key:
            logger.info(f"No Gemini API key - using regex fallback for {url}")
        else:
            logger.warning(f"No extracted content from Gemini for URL: {url}")
        
        # Try regex fallback on the markdown content
        if markdown_content:
            regex_result = _extract_price_regex(markdown_content)
            if regex_result:
                logger.info(f"Regex fallback found price for URL: {url}")
                return regex_result, markdown_content
        return None, markdown_content

    try:
        if isinstance(data, dict):
            payload = data
        elif isinstance(data, str):
            import json
            try:
                payload = json.loads(data)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode error for {url}: {e}")
                # Try regex fallback
                if markdown_content:
                    regex_result = _extract_price_regex(markdown_content)
                    if regex_result:
                        logger.info(f"Regex fallback found price for URL: {url}")
                        return regex_result, markdown_content
                return None, markdown_content
        elif isinstance(data, list):
            logger.warning(f"Received list instead of dict from Gemini for {url}: {data}")
            # Try regex fallback
            if markdown_content:
                regex_result = _extract_price_regex(markdown_content)
                if regex_result:
                    logger.info(f"Regex fallback found price for URL: {url}")
                    return regex_result, markdown_content
            return None, markdown_content
        else:
            logger.warning(f"Unexpected data type from Gemini for {url}: {type(data)}")
            # Try regex fallback
            if markdown_content:
                regex_result = _extract_price_regex(markdown_content)
                if regex_result:
                    logger.info(f"Regex fallback found price for URL: {url}")
                    return regex_result, markdown_content
            return None, markdown_content
        
        price_raw = payload.get('price')
        if price_raw is None:
            logger.warning(f"No price field in extracted data for URL: {url}")
            # Try regex fallback
            if markdown_content:
                regex_result = _extract_price_regex(markdown_content)
                if regex_result:
                    logger.info(f"Regex fallback found price for URL: {url}")
                    return regex_result, markdown_content
            return None, markdown_content
            
        # Handle various price formats safely
        try:
            if isinstance(price_raw, (int, float)):
                price = float(price_raw)
            elif isinstance(price_raw, str):
                # Clean price string - remove common non-numeric characters
                price_clean = price_raw.strip().replace(',', '').replace('$', '').replace('₹', '').replace('€', '').replace('£', '')
                if not price_clean or price_clean.lower() in ['null', 'none', 'n/a', 'na']:
                    logger.warning(f"Invalid price string for {url}: {price_raw}")
                    # Try regex fallback
                    if markdown_content:
                        regex_result = _extract_price_regex(markdown_content)
                        if regex_result:
                            logger.info(f"Regex fallback found price for URL: {url}")
                            return regex_result, markdown_content
                    return None, markdown_content
                price = float(price_clean)
            else:
                logger.warning(f"Unsupported price type for {url}: {type(price_raw)} - {price_raw}")
                # Try regex fallback
                if markdown_content:
                    regex_result = _extract_price_regex(markdown_content)
                    if regex_result:
                        logger.info(f"Regex fallback found price for URL: {url}")
                        return regex_result, markdown_content
                return None, markdown_content
                
            if price <= 0:
                logger.warning(f"Invalid price value for {url}: {price}")
                # Try regex fallback
                if markdown_content:
                    regex_result = _extract_price_regex(markdown_content)
                    if regex_result:
                        logger.info(f"Regex fallback found price for URL: {url}")
                        return regex_result, markdown_content
                return None, markdown_content
                
        except (ValueError, TypeError) as e:
            logger.warning(f"Price conversion error for {url}: {e}")
            # Try regex fallback
            if markdown_content:
                regex_result = _extract_price_regex(markdown_content)
                if regex_result:
                    logger.info(f"Regex fallback found price for URL: {url}")
                    return regex_result, markdown_content
            return None, markdown_content
        currency = str(payload.get('currency') or '').strip() or 'USD'
        title = payload.get('title')
        model_name = payload.get('model_name')
        manufacturer = payload.get('manufacturer')
        scale = payload.get('scale')
        seller = payload.get('seller')

        # Log original extracted data before guess functions
        logger.info(f"Original extracted data for {url}: price={price}, currency={currency}, title={title}, model_name={model_name}, manufacturer={manufacturer}, scale={scale}, seller={seller}")
        
        # Heuristic fill-ins when the LLM/schema didn't populate
        original_seller = seller
        if not seller:
            seller = _guess_seller_from_url(url)
            logger.info(f"Guessed seller for {url}: {original_seller} -> {seller}")
            
        original_scale = scale
        if not scale:
            scale = _guess_scale(title or '')
            logger.info(f"Guessed scale for {url}: {original_scale} -> {scale}")
            
        original_manufacturer = manufacturer
        if not manufacturer:
            manufacturer = _guess_brand(title or '')
            logger.info(f"Guessed manufacturer for {url}: {original_manufacturer} -> {manufacturer}")
            
        original_model_name = model_name
        if not model_name:
            model_name = _guess_model_name(title, manufacturer, scale)
            logger.info(f"Guessed model_name for {url}: {original_model_name} -> {model_name}")

        # Log final data after guess functions
        logger.info(f"Final processed data for {url}: price={price}, currency={currency}, title={title}, model_name={model_name}, manufacturer={manufacturer}, scale={scale}, seller={seller}")
        
        logger.info(f"Successfully extracted price {price} {currency} from URL: {url}")
        return PriceItem(
            price=price,
            currency=currency,
            title=title,
            url=url,
            model_name=model_name,
            manufacturer=manufacturer,
            scale=scale,
            seller=seller,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to parse extracted data for URL {url}: {e}")
        # Try regex fallback
        if markdown_content:
            regex_result = _extract_price_regex(markdown_content)
            if regex_result:
                logger.info(f"Regex fallback found price for URL: {url}")
                return regex_result, markdown_content
        return None, markdown_content


def search_and_extract_prices(query: str, gemini_api_key: Optional[str], max_results: int = 3, 
                       car_id: Optional[int] = None, car_name: Optional[str] = None) -> tuple[List[PriceItem], dict]:
    """Run a Google search for the query, crawl the top results, and extract prices.
    Falls back to regex parsing if LLM or crawl4ai is unavailable.
    
    Returns:
    - A list of PriceItem objects with extracted price data
    - A dictionary of markdown content keyed by URL
    """
    urls: List[str] = []
    results: List[PriceItem] = []
    markdown_content: dict = {}
    urls = search_engine_urls(query, max_links=max_results)
    
    # Log the query and URLs if logging is enabled
    if car_id and car_name:
        logger = get_logger(car_id, car_name)
        logger.log_query(query)
        logger.log_urls(query, urls)

    async def _run(urls_: List[str]):
        items: List[PriceItem] = []
        md_content: dict = {}
        logger.info(f"Processing {len(urls_)} URLs for query: {query}")
        
        for u in urls_:
            logger.info(f"Processing URL: {u}")
            item, markdown = await _crawl_and_extract(u, gemini_api_key)
            
            if item:
                logger.info(f"Successfully extracted item from {u}: price={item.price}, currency={item.currency}")
                items.append(item)
                if markdown:
                    md_content[u] = markdown
            else:
                logger.warning(f"No item extracted from {u}")
            
            # Log extraction results if logging is enabled
            if car_id and car_name and markdown:
                logger = get_logger(car_id, car_name)
                extracted_data = item.dict() if item and hasattr(item, 'dict') else None
                logger.log_extraction(u, markdown, extracted_data)
                
        logger.info(f"Total items extracted for query '{query}': {len(items)}")
        return items, md_content

    if urls and CRAWL4AI_AVAILABLE and PYDANTIC_AVAILABLE:
        try:
            extracted, markdown_dict = asyncio.run(_run(urls))
            results.extend(extracted)
            markdown_content.update(markdown_dict)
        except Exception:
            pass

    # Fallback: regex scrape if nothing yet
    if not results:
        for u in urls:
            try:
                r = requests.get(u, headers=HEADERS, timeout=12)
                r.raise_for_status()
                item = _extract_price_regex(r.text)
                if item:
                    item.url = u
                    # Try to get title
                    try:
                        soup = BeautifulSoup(r.text, 'html.parser')
                        if soup.title and soup.title.text:
                            item.title = soup.title.text.strip()
                            
                        # Store the HTML as a simpler markdown representation for fallbacks
                        body_text = soup.get_text(separator="\n\n")
                        if body_text:
                            markdown_content[u] = f"# {item.title if item.title else 'Web Page'}\n\n{body_text[:1000]}..."
                    except Exception:
                        pass
                    # Heuristics for additional metadata
                    try:
                        page_text = (soup.title.text if soup.title else '')
                    except Exception:
                        page_text = ''
                    item.seller = _guess_seller_from_url(u)
                    guessed_scale = _guess_scale(page_text or r.text)
                    if guessed_scale:
                        item.scale = guessed_scale
                    guessed_brand = _guess_brand(page_text or r.text)
                    if guessed_brand:
                        item.manufacturer = guessed_brand
                    item.model_name = _guess_model_name(item.title, item.manufacturer, item.scale)
                    results.append(item)
            except Exception:
                continue

    return results, markdown_content
