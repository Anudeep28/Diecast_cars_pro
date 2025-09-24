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
import time

import requests
from bs4 import BeautifulSoup
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

from urllib.parse import quote_plus
import re

# Pydantic schema for extracted price items
class PriceItem(BaseModel):
    price: float = Field(..., description="Product price amount (numeric)")
    currency: str = Field(..., description="Currency code (INR, USD, EUR, GBP, JPY, etc.). For Indian Rupees use 'INR', for US Dollars use 'USD', etc.")
    title: Optional[str] = Field(None, description="Page or product title")
    url: Optional[str] = Field(None, description="Source URL")
    model_name: Optional[str] = Field(None, description="Model car name, e.g., 'Ferrari 488 GTB'")
    manufacturer: Optional[str] = Field(None, description="Brand/manufacturer, e.g., Hot Wheels, AUTOart")
    scale: Optional[str] = Field(None, description="Scale notation like '1:18' or '1/64'")
    seller: Optional[str] = Field(None, description="Seller or marketplace name")


def _call_gemini_generate(api_key: str, prompt: str, max_retries: int = 3) -> str:
    """Call Gemini generateContent endpoint with rate limiting and retry logic."""
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
    
    for attempt in range(max_retries):
        try:
            # Add delay between API calls to respect rate limits
            if attempt > 0:
                delay = min(2 ** attempt, 10)  # Exponential backoff, max 10 seconds
                logger.info(f"Retrying Gemini API call in {delay}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            
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
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Rate limit error
                if attempt < max_retries - 1:
                    logger.warning(f"Rate limit hit, retrying in {2 ** (attempt + 1)}s...")
                    continue
                else:
                    logger.error(f"Rate limit exceeded after {max_retries} attempts")
                    raise
            else:
                raise
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Gemini API error: {e}, retrying...")
                continue
            else:
                raise
    
    return ""


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
    """Optimized crawl URL and extract structured price info using crawl4ai + Gemini.
    Returns (List[PriceItem], markdown_content or None)
    """
    # Browser configuration compatible with current crawl4ai version
    browser_config = BrowserConfig(
        headless=True,
        text_mode=True,
        java_script_enabled=True
    )
    
    # Content filter for relevant pricing content
    bm25_filter = BM25ContentFilter()
    
    # Optimized markdown generator
    md_generator = DefaultMarkdownGenerator(
        content_filter=bm25_filter,
        options={
            "ignore_links": True,
            "ignore_images": True,
            "escape_html": True,
            "skip_internal_links": True,
            "body_width": 120,
            "emphasis_marker": "_",
            "bullets": "-",
        },
    )

    # Comprehensive extraction instruction with explicit JSON schema and example
    instruction = (
        "You are extracting structured market listing data for diecast model cars from the provided page content.\n\n"
        "Goal:\n"
        "- Identify the main product/listing price(s). Ignore shipping, taxes, strikethrough MSRP/compare-at/was price, coupon values, and totals.\n"
        "- Prefer the current, in-stock selling price. If both MRP and Sale/Discount price exist, take the Sale price.\n"
        "- If the page has multiple distinct listings (e.g., search results), return multiple items (one per listing). If it is a single product page, return exactly one item.\n\n"
        "Output format:\n"
        "- Return ONLY valid JSON, no markdown or commentary.\n"
        "- Return an array of objects. If only one item is found, still return a one-element array.\n"
        "- Keys: price, currency, title, url, model_name, manufacturer, scale, seller.\n"
        "- Set any unknown fields to null. Do not invent values. Do not include extra keys.\n\n"
        "Field requirements:\n"
        "- price: number. Remove currency symbols and thousands separators. Use '.' as the decimal separator. Example: '₹2,499.00' → 2499.0, '$24.99' → 24.99.\n"
        "- currency: ISO 4217 code. Examples: INR, USD, EUR, GBP, JPY, CAD, AUD, SGD, MYR, CNY.\n"
        "  Mapping help: ₹/Rs./Rupee → INR; $ with US context → USD; € → EUR; £ → GBP; ¥/Yen → JPY.\n"
        "  If ambiguous '$', infer from site context (domain/TLD, payment methods). Default to INR for Indian sites. If still unclear, set to null.\n"
        "- title: the product/listing title as shown on the page, trimmed.\n"
        "- url: the page URL for this item. Use the source page URL if not explicitly shown on the card.\n"
        "- model_name: the specific car/bike model (e.g., 'Ferrari 488 GTB', 'BMW R69S').\n"
        "- manufacturer: brand making the diecast (e.g., 'Hot Wheels', 'AUTOart', 'Maisto', 'Tarmac Works').\n"
        "- scale: normalized form like '1:18', '1:64', '1:43'. Convert variants like '1/18', '1 18' to '1:18'.\n"
        "- seller: marketplace or seller/store name (e.g., 'eBay', 'Amazon', 'hobbyDB', or seller username/shop).\n\n"
        "Selection rules:\n"
        "- On list/search pages, extract up to 5 best matches relevant to diecast models, not accessories.\n"
        "- Ignore prices that are clearly for shipping-only, spare parts, or unrelated products.\n\n"
        "If nothing valid is found, return [].\n\n"
        "Example output (illustrative; your output must be raw JSON without code fences):\n"
        "[\n"
        "  {\n"
        "    \"price\": 2499.0,\n"
        "    \"currency\": \"INR\",\n"
        "    \"title\": \"Hot Wheels Premium Ferrari 488 GTB 1:64\",\n"
        "    \"url\": \"https://example-shop.in/product/ferrari-488-gtb-1-64\",\n"
        "    \"model_name\": \"Ferrari 488 GTB\",\n"
        "    \"manufacturer\": \"Hot Wheels\",\n"
        "    \"scale\": \"1:64\",\n"
        "    \"seller\": \"Example Shop\"\n"
        "  },\n"
        "  {\n"
        "    \"price\": 124.99,\n"
        "    \"currency\": \"USD\",\n"
        "    \"title\": \"AUTOart BMW M3 E46 1:18 Diecast Model\",\n"
        "    \"url\": \"https://www.example.com/listing/autoart-bmw-m3-e46-1-18\",\n"
        "    \"model_name\": \"BMW M3 E46\",\n"
        "    \"manufacturer\": \"AUTOart\",\n"
        "    \"scale\": \"1:18\",\n"
        "    \"seller\": \"eBay\"\n"
        "  }\n"
        "]\n"
    )


    # Optimized extraction strategy
    strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider="gemini/gemini-1.5-flash",  # Using 1.5-flash instead of 2.0 for better rate limits
            api_token=api_token,
        ),
        schema=PriceItem.model_json_schema(),
        extraction_type="schema",
        chunk_token_threshold=2000,  # Reduced to minimize API calls
        overlap_rate=0.1,  # Reduced overlap to minimize chunks
        apply_chunking=False,  # Disable chunking to reduce API calls
        instruction=instruction,
        input_format="markdown.fit_markdown",
        extra_args={
            "temperature": 0.1,  # Slightly higher for more natural output
            "max_tokens": 1024,  # Reduced to minimize processing time
            "top_p": 0.9,
            "stream": False,
        },
    )

    # Crawler configuration with supported parameters
    from crawl4ai import CrawlerRunConfig, CacheMode
    
    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,  # Always get fresh data for prices
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
    result = None
    
    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            # Add timeout for the entire crawl operation
            result = await asyncio.wait_for(
                crawler.arun(url=url, config=crawler_config),
                timeout=35.0  # Total timeout for crawling
            )
    except asyncio.TimeoutError:
        logger.warning(f"Timeout crawling {url}")
        return [], None
    except Exception as e:
        logger.warning(f"Error crawling {url}: {e}")
        return [], None
    
    # Extract markdown content (no currency detection — rely on LLM JSON only)
    try:
        if result:
            if hasattr(result, 'markdown_content') and result.markdown_content:
                markdown_content = result.markdown_content
            elif hasattr(result, 'markdown') and result.markdown:
                markdown_content = result.markdown
    except Exception:
        pass

    # Improved debug logging with less verbosity
    logger.debug(f"Processing URL: {url}")
    
    if not result:
        logger.warning(f"No result object for {url}")
        return [], markdown_content
    
    data = getattr(result, 'extracted_content', None)
    if not data:
        logger.debug(f"No extracted_content for {url}")
        return [], markdown_content

    logger.debug(f"Extracted data type: {type(data)}")

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
                extracted_currency = candidate.get('currency', 'INR')  # Default to INR
                if not extracted_currency or (isinstance(extracted_currency, str) and extracted_currency.lower() in ['null', 'none', 'n/a', 'na']):
                    candidate['currency'] = 'INR'  # Default fallback
                else:
                    currency_str = str(extracted_currency).strip()
                    # Normalize common currency symbols to codes
                    currency_map = {
                        '$': 'USD', 'us$': 'USD', 'usd': 'USD', 'dollar': 'USD', 'dollars': 'USD',
                        '₹': 'INR', 'rs': 'INR', 'rs.': 'INR', 'inr': 'INR', 'rupees': 'INR', 'rupee': 'INR',
                        '€': 'EUR', 'eur': 'EUR', 'euro': 'EUR', 'euros': 'EUR',
                        '£': 'GBP', 'gbp': 'GBP', 'pound': 'GBP', 'pounds': 'GBP',
                        '¥': 'JPY', 'jpy': 'JPY', 'yen': 'JPY',
                        'c$': 'CAD', 'cad': 'CAD', 'ca$': 'CAD', 'canadian dollar': 'CAD',
                        'a$': 'AUD', 'aud': 'AUD', 'au$': 'AUD', 'australian dollar': 'AUD',
                        'sg$': 'SGD', 'sgd': 'SGD', 'singapore dollar': 'SGD',
                        'rm': 'MYR', 'myr': 'MYR', 'ringgit': 'MYR',
                        'cny': 'CNY', 'rmb': 'CNY', 'yuan': 'CNY',
                    }
                    currency_lower = currency_str.lower()
                    normalized_currency = currency_map.get(currency_lower, currency_str.upper())
                    
                    # Enhanced currency validation with context
                    price_value = candidate.get('price', 0)
                    if price_value > 0:
                        if normalized_currency == 'USD' and price_value > 1000:
                            logger.warning(f"Suspicious USD price {price_value} for {url} - might be INR")
                        elif normalized_currency == 'INR' and price_value < 50:
                            logger.warning(f"Suspicious INR price {price_value} for {url} - might be USD")
                    
                    # Log currency decision
                    logger.info(f"Currency set for {url}: {normalized_currency} (price: {price_value})")
                    
                    candidate['currency'] = normalized_currency
                
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
    """Process multiple URLs concurrently with rate limiting"""
    results: List[PriceItem] = []
    markdown_by_url: Dict[str, str] = {}
    
    # Process URLs with reduced concurrency to avoid rate limits
    import asyncio
    semaphore = asyncio.Semaphore(1)  # Reduced from 2 to 1 to avoid rate limits
    
    async def process_with_semaphore(url: str) -> Tuple[List[PriceItem], Optional[str]]:
        async with semaphore:
            try:
                print(f"  ↓ Crawling: {url[:80]}...")
                # Add delay between URL processing to avoid rate limits
                await asyncio.sleep(2)  # 2 second delay between URLs
                items, markdown = await _extract_from_url(url, api_token)
                if items:
                    print(f"    ✓ Extracted {len(items)} price(s)")
                else:
                    print(f"    ✗ No prices found")
                return items, markdown
            except Exception as e:
                logger.warning(f"Error processing URL {url}: {e}")
                print(f"    ✗ Error: {str(e)[:50]}")
                return [], None
    
    # Create tasks for all URLs
    tasks = [process_with_semaphore(url) for url in urls]
    
    # Process all URLs concurrently
    results_list = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Collect results
    for i, result in enumerate(results_list):
        if isinstance(result, Exception):
            logger.warning(f"Task failed for URL {urls[i]}: {result}")
        elif result:
            items, markdown = result
            results.extend(items)
            if markdown:
                markdown_by_url[urls[i]] = markdown
    
    return results, markdown_by_url


def search_web_with_fallbacks(query: str, num_results: int = 5) -> List[str]:
    """Robust web search with multiple fallbacks: Google → DuckDuckGo → Bing → Marketplace URLs"""
    urls = []
    
    # Method 1: Try googlesearch library first (simplest)
    try:
        from googlesearch import search as google_search
        urls = list(google_search(query, num_results=num_results + 2))
        if urls:
            logger.info(f"Found {len(urls)} URLs via googlesearch library")
            return urls[:num_results]
    except Exception as e:
        logger.warning(f"googlesearch library failed: {e}")
    
    # Method 2: Direct Google search scraping
    if not urls:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            google_url = f"https://www.google.com/search?q={quote_plus(query)}&num={num_results + 2}"
            response = requests.get(google_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract URLs from Google search results
                for g in soup.find_all('div', class_='g'):
                    link = g.find('a')
                    if link and link.get('href'):
                        url = link['href']
                        if url.startswith('http') and 'google.com' not in url and 'youtube.com' not in url:
                            urls.append(url)
                            if len(urls) >= num_results:
                                break
                
                if urls:
                    logger.info(f"Found {len(urls)} URLs via Google scraping")
                    return urls[:num_results]
        except Exception as e:
            logger.warning(f"Google scraping failed: {e}")
    
    # Method 3: DuckDuckGo HTML scraping
    if not urls:
        print("Google search failed, trying DuckDuckGo...")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            response = requests.get(search_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find result links
            for result in soup.find_all('a', class_='result__a'):
                href = result.get('href')
                if href and href.startswith('http'):
                    if 'duckduckgo.com' not in href and 'youtube.com' not in href:
                        urls.append(href)
                        if len(urls) >= num_results:
                            break
            
            # Alternative pattern if no results found
            if not urls:
                pattern = r'href="(https?://[^"]+)"'
                matches = re.findall(pattern, response.text)
                seen = set()
                for url in matches[:num_results * 3]:
                    if url not in seen and 'duckduckgo.com' not in url and 'youtube.com' not in url:
                        urls.append(url)
                        seen.add(url)
                    if len(urls) >= num_results:
                        break
            
            if urls:
                logger.info(f"Found {len(urls)} URLs via DuckDuckGo")
                return urls[:num_results]
                        
        except Exception as e:
            logger.warning(f"DuckDuckGo search failed: {e}")
    
    # Method 4: Bing search
    if not urls:
        print("DuckDuckGo failed, trying Bing...")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            bing_url = f"https://www.bing.com/search?q={quote_plus(query)}"
            response = requests.get(bing_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find organic results
            for result in soup.find_all('h2'):
                link = result.find('a')
                if link and link.get('href'):
                    href = link['href']
                    if href.startswith('http') and 'bing.com' not in href and 'youtube.com' not in href:
                        urls.append(href)
                        if len(urls) >= num_results:
                            break
            
            if urls:
                logger.info(f"Found {len(urls)} URLs via Bing")
                return urls[:num_results]
                
        except Exception as e:
            logger.warning(f"Bing search failed: {e}")
    
    # Final fallback: Direct marketplace URLs
    if not urls:
        print("All search engines failed/blocked. Using direct marketplace URLs...")
        marketplace_urls = [
            f"https://www.ebay.com/sch/i.html?_nkw={quote_plus(query)}",
            f"https://www.amazon.com/s?k={quote_plus(query)}",
            f"https://www.etsy.com/search?q={quote_plus(query)}",
            f"https://www.mercari.com/search/?keyword={quote_plus(query)}",
            f"https://www.carousell.sg/search/{quote_plus(query)}"
        ]
        urls = marketplace_urls[:num_results]
        logger.info(f"Using {len(urls)} direct marketplace URLs as fallback")
    
    return urls[:num_results]


def search_market_prices_for_car(car, api_token: str, num_results: int = 3) -> Tuple[List[PriceItem], Dict[str, str], str]:
    """End-to-end flow with robust fallbacks:
    1) Generate a focused query via Gemini
    2) Search web with multiple fallbacks (Google → DuckDuckGo → Bing → Marketplaces)
    3) Crawl and extract with optimized crawl4ai + LLM schema
    Returns (items, markdown_by_url, query_used)
    """
    manufacturer = getattr(car, 'manufacturer', '') or ''
    model = getattr(car, 'model_name', '') or ''
    scale = getattr(car, 'scale', '') or ''

    query = generate_search_query(manufacturer, model, scale, api_token)
    
    # Direct terminal output of the search query
    print("\n" + "=" * 80)
    print(f"🔍 GEMINI SEARCH QUERY: \"{query}\"")
    print("=" * 80)

    # Get URLs with robust fallback mechanism
    urls = search_web_with_fallbacks(query, num_results=num_results + 2)
    
    # Dedupe and filter out unwanted URLs
    unique_urls = []
    seen = set()
    for url in urls:
        if isinstance(url, str) and url.startswith('http'):
            # Skip video and social media sites
            skip_domains = ['youtube.com', 'facebook.com', 'twitter.com', 'instagram.com', 
                          'tiktok.com', 'pinterest.com', 'reddit.com', 'wikipedia.org']
            if not any(domain in url.lower() for domain in skip_domains):
                if url not in seen:
                    unique_urls.append(url)
                    seen.add(url)
    
    print(f"📊 Found {len(unique_urls)} unique URLs to analyze")
    
    items: List[PriceItem] = []
    markdown_by_url: Dict[str, str] = {}
    
    if unique_urls:
        try:
            items, markdown_by_url = asyncio.run(_process_urls(unique_urls[:num_results + 2], api_token))
            logger.info(f"AI market scraper processed {len(unique_urls[:num_results+2])} URLs, extracted {len(items)} items")
            
            if not items:
                print("⚠️ No prices extracted from URLs. Check if sites are blocking or have changed structure.")
        except Exception as e:
            logger.warning(f"AI market scraper failed to process URLs: {e}")
            print(f"❌ Error processing URLs: {e}")
    else:
        logger.warning(f"No URLs found for query: {query}")
        print("⚠️ No URLs found. All search methods may be blocked.")

    return items, markdown_by_url, query
