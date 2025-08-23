"""
AI-powered market price scraper for diecast model cars.
- Generates a focused web search query using Gemini from manufacturer, model, and scale
- Uses googlesearch to fetch top URLs
- Crawls each URL with crawl4ai and extracts structured price info via LLM schema (Pydantic)
Returns a tuple: (List[PriceItem], markdown_by_url: dict, query_used: str)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Optional, Tuple, Dict

import requests
from pydantic import BaseModel, Field, ValidationError

# Set up logging
logger = logging.getLogger(__name__)

# crawl4ai imports: use top-level exports for compatibility with current versions
from crawl4ai import (
    BrowserConfig,
    AsyncWebCrawler,
    LLMExtractionStrategy,
    LLMConfig,
    DefaultMarkdownGenerator,
    BM25ContentFilter,
)

from googlesearch import search as google_search

# Pydantic schema for extracted price items
class PriceItem(BaseModel):
    price: float = Field(..., description="Product price amount (numeric)")
    currency: str = Field(..., description="Currency code or symbol, e.g., USD, INR, $, ₹")
    title: Optional[str] = Field(None, description="Page or product title")
    url: Optional[str] = Field(None, description="Source URL")
    model_name: Optional[str] = Field(None, description="Model car name, e.g., 'Ferrari 488 GTB'")
    manufacturer: Optional[str] = Field(None, description="Brand/manufacturer, e.g., Hot Wheels, AUTOart")
    scale: Optional[str] = Field(None, description="Scale notation like '1:18' or '1/64'")
    seller: Optional[str] = Field(None, description="Seller or marketplace name")


def _call_gemini_generate(api_key: str, prompt: str) -> str:
    """Call Gemini generateContent endpoint and return text output."""
    api_url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-1.5-flash:generateContent"
    )
    params = {"key": api_key}
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ]
    }
    r = requests.post(api_url, params=params, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    if not parts:
        return ""
    text = parts[0].get("text") or ""
    return text.strip()


def generate_search_query(manufacturer: str, model: str, scale: Optional[str], api_key: str) -> str:
    """Use Gemini to produce a single focused web search query for pricing pages."""
    manu = (manufacturer or "").strip()
    mdl = (model or "").strip()
    scl = (scale or "").strip()
    context = f"Manufacturer: {manu}\nModel: {mdl}\nScale: {scl if scl else 'N/A'}"
    prompt = f"""
Create ONE concise web search query to find current market prices and listings to buy the following diecast model car.
Include brand, model, and scale if provided. Prefer keywords like price, for sale, buy, listing, shop.
Avoid quotes, code fences, or extra commentary. Return ONLY the query text.

{context}
"""
    text = _call_gemini_generate(api_key, prompt)
    # Clean common wrappers
    text = text.strip().strip('"').strip("'")
    # If Gemini returns multiple lines, pick the first non-empty
    for line in text.splitlines():
        q = line.strip().strip('"').strip("'")
        if q:
            return q
    # Fallback simple query
    base = f"{manu} {mdl} {scl}".strip()
    return f"{base} diecast price".strip()


async def _extract_from_url(url: str, api_token: str) -> Tuple[List[PriceItem], Optional[str]]:
    """Crawl URL and extract structured price info using crawl4ai + Gemini schema extraction.
    Returns (List[PriceItem], markdown_content or None)
    """
    browser_config = BrowserConfig(
        headless=True,
        text_mode=True,
        java_script_enabled=True
    )
    
    # Content filter for relevant pricing content
    bm25_filter = BM25ContentFilter()
    
    # Markdown generator configuration
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
        "Extract pricing details for the diecast model car on this page. "
        "Focus on the main product being sold. If multiple prices exist, choose the current selling price. "
        "Return a valid JSON object with these exact fields: "
        "price (numeric value only, no currency symbols), "
        "currency (currency code like USD, INR, EUR, or symbol like $, ₹, €), "
        "title (product/page title), "
        "url (source URL), "
        "model_name (car model name if identifiable), "
        "manufacturer (brand like Hot Wheels, AUTOart, etc.), "
        "scale (scale notation like 1:18, 1/64), "
        "seller (marketplace or seller name). "
        "Set unknown fields to null. Ensure the JSON is valid and parseable."
    )

    strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(provider="gemini/gemini-2.0-flash", api_token=api_token),
        schema=PriceItem.model_json_schema(),
        extraction_type="schema",
        chunk_token_threshold=2048,
        overlap_rate=0.1,
        apply_chunking=True,
        instruction=instruction,
        input_format="markdown.fit_markdown",
        extra_args={
            "temperature": 0.1,
            "max_tokens": 4096,
            "chunk_merge_strategy": "ordered_append",
            "stream": False,
        },
    )

    # Crawler configuration with proper settings
    from crawl4ai import CrawlerRunConfig, CacheMode
    
    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        excluded_tags=['script', 'style', 'meta', 'link', 'noscript', 'iframe'],
        exclude_external_images=True,
        exclude_external_links=True,
        exclude_social_media_links=True,
        markdown_generator=md_generator,
        check_robots_txt=True,
        page_timeout=60000,
        wait_until="networkidle",
        extraction_strategy=strategy,
    )

    markdown_content = None

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=crawler_config)

    try:
        if hasattr(result, 'markdown_content') and result.markdown_content:
            markdown_content = result.markdown_content
        elif hasattr(result, 'markdown') and result.markdown:
            markdown_content = result.markdown
    except Exception:
        pass

    # Debug logging
    logger.info(f"Processing URL: {url}")
    logger.info(f"Result type: {type(result)}")
    logger.info(f"Result attributes: {dir(result)}")
    logger.info(f"Result extracted: {result}")
    
    data = getattr(result, 'extracted_content', None)
    if not data:
        logger.warning(f"No extracted_content for {url}")
        return [], markdown_content

    logger.info(f"Extracted data type: {type(data)}")
    logger.info(f"Extracted data preview: {str(data)[:500]}...")

    try:
        items = []

        # Helper function to process candidate dicts
        def process_candidate(candidate, url):
            try:
                # Handle price field carefully
                price_raw = candidate.get('price')
                if price_raw is None:
                    logger.info(f"No price field in payload for {url}")
                    return None
                    
                # Clean and validate price
                if isinstance(price_raw, (int, float)):
                    price = float(price_raw)
                elif isinstance(price_raw, str):
                    # Remove common currency symbols and clean
                    price_clean = price_raw.strip().replace(',', '').replace('$', '').replace('₹', '').replace('€', '').replace('£', '').replace('¥', '').replace('C$', '').replace('A$', '')
                    # Remove any remaining non-numeric characters except decimal point
                    import re
                    price_clean = re.sub(r'[^0-9.]', '', price_clean)
                    
                    if not price_clean or price_clean.lower() in ['null', 'none', 'n/a', 'na']:
                        logger.info(f"Invalid price string for {url}: {price_raw}")
                        return None
                        
                    # Handle multiple decimal points
                    if price_clean.count('.') > 1:
                        # Keep only the last decimal point
                        parts = price_clean.split('.')
                        price_clean = '.'.join(parts[:-1]).replace('.', '') + '.' + parts[-1]
                        
                    price = float(price_clean)
                else:
                    logger.warning(f"Unsupported price type for {url}: {type(price_raw)}")
                    return None
                    
                if price <= 0:
                    logger.info(f"Invalid price value for {url}: {price}")
                    return None
                    
                candidate['price'] = price
                
                # Clean and normalize currency field
                currency = candidate.get('currency', 'USD')
                if not currency or (isinstance(currency, str) and currency.lower() in ['null', 'none', 'n/a', 'na']):
                    candidate['currency'] = 'USD'
                else:
                    currency_str = str(currency).strip()
                    # Normalize common currency symbols to codes
                    currency_map = {
                        '$': 'USD', 'us$': 'USD', 'usd': 'USD',
                        '₹': 'INR', 'rs': 'INR', 'rs.': 'INR', 'inr': 'INR', 'rupees': 'INR',
                        '€': 'EUR', 'eur': 'EUR', 'euro': 'EUR', 'euros': 'EUR',
                        '£': 'GBP', 'gbp': 'GBP', 'pound': 'GBP', 'pounds': 'GBP',
                        '¥': 'JPY', 'jpy': 'JPY', 'yen': 'JPY',
                        'c$': 'CAD', 'cad': 'CAD', 'ca$': 'CAD',
                        'a$': 'AUD', 'aud': 'AUD', 'au$': 'AUD',
                    }
                    currency_lower = currency_str.lower()
                    candidate['currency'] = currency_map.get(currency_lower, currency_str.upper())
                    
                # Clean other string fields
                for field in ['title', 'model_name', 'manufacturer', 'scale', 'seller']:
                    value = candidate.get(field)
                    if value is not None and isinstance(value, str) and value.lower() in ['null', 'none', 'n/a', 'na']:
                        candidate[field] = None
                    elif value is not None:
                        candidate[field] = str(value).strip() if str(value).strip() else None
                
                # Add URL into payload if extractor missed it
                candidate.setdefault('url', url)
                
                # Create PriceItem with validated data
                return PriceItem(**candidate)
                
            except (ValueError, TypeError, ValidationError) as e:
                logger.warning(f"Error processing candidate for {url}: {e}")
                return None

        # Process different data types
        if isinstance(data, dict):
            item = process_candidate(data, url)
            if item:
                items.append(item)
        elif isinstance(data, str):
            # Clean the string - remove markdown code blocks if present
            data_clean = data.strip()
            if data_clean.startswith('```json'):
                data_clean = data_clean[7:]
            if data_clean.endswith('```'):
                data_clean = data_clean[:-3]
            data_clean = data_clean.strip()
            
            try:
                payload = json.loads(data_clean)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode error for {url}: {e}")
                logger.warning(f"Raw data: {data_clean[:200]}...")
                return items, markdown_content
            
            if isinstance(payload, dict):
                item = process_candidate(payload, url)
                if item:
                    items.append(item)
            elif isinstance(payload, list):
                for elem in payload:
                    if isinstance(elem, dict):
                        item = process_candidate(elem, url)
                        if item:
                            items.append(item)
            else:
                logger.warning(f"Unexpected payload type after JSON parse: {type(payload)}")
        elif isinstance(data, list):
            for elem in data:
                if isinstance(elem, dict):
                    item = process_candidate(elem, url)
                    if item:
                        items.append(item)
        else:
            logger.warning(f"Unexpected data type from extraction: {type(data)}")
        
        logger.info(f"Extracted {len(items)} valid items from {url}")
        return items, markdown_content
        
    except Exception as e:
        logger.warning(f"Unexpected error processing data for {url}: {e}")
        return [], markdown_content


async def _process_urls(urls: List[str], api_token: str) -> Tuple[List[PriceItem], Dict[str, str]]:
    results: List[PriceItem] = []
    markdown_by_url: Dict[str, str] = {}
    for url in urls:
        try:
            items, markdown = await _extract_from_url(url, api_token)
            results.extend(items)
            if markdown:
                markdown_by_url[url] = markdown
        except Exception as e:
            logger.warning(f"Error processing URL {url}: {e}")
    return results, markdown_by_url


def search_market_prices_for_car(car, api_token: str, num_results: int = 3) -> Tuple[List[PriceItem], Dict[str, str], str]:
    """End-to-end flow:
    1) Generate a single focused query via Gemini
    2) Fetch top URLs via googlesearch
    3) Crawl and extract with crawl4ai + LLM schema
    Returns (items, markdown_by_url, query_used)
    """
    manufacturer = getattr(car, 'manufacturer', '') or ''
    model = getattr(car, 'model_name', '') or ''
    scale = getattr(car, 'scale', '') or ''

    query = generate_search_query(manufacturer, model, scale, api_token)

    urls: List[str] = []
    try:
        urls = list(google_search(query, num_results=num_results))
    except Exception:
        urls = []

    # dedupe and filter out YouTube URLs
    unique_urls = list(dict.fromkeys([u for u in urls if isinstance(u, str) and u.startswith('http') and 'youtube.com' not in u]))

    items: List[PriceItem] = []
    markdown_by_url: Dict[str, str] = {}
    if unique_urls:
        try:
            items, markdown_by_url = asyncio.run(_process_urls(unique_urls, api_token))
            logger.info(f"AI market scraper processed {len(unique_urls)} URLs, extracted {len(items)} items")
        except Exception as e:
            logger.warning(f"AI market scraper failed to process URLs: {e}")
            pass
    else:
        logger.warning(f"No URLs found for query: {query}")

    return items, markdown_by_url, query
