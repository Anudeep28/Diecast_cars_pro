"""
Robust agentic market search implementation using Gemini for both search and extraction.
Simplified approach with better error handling and direct web scraping.
"""
import logging
import json
import requests
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass
import re
from urllib.parse import quote_plus
import time
from .enhanced_currency_detector import detect_currency_from_webpage
import asyncio
from bs4 import BeautifulSoup
from difflib import SequenceMatcher
from .ai_market_scraper import _extract_from_url, PriceItem

logger = logging.getLogger(__name__)

@dataclass
class MarketListing:
    """Simple dataclass for market listings"""
    price: float
    currency: str
    title: str
    url: str
    seller: Optional[str] = None
    confidence: float = 1.0

class AgenticMarketSearch:
    """Agentic market search using Gemini for intelligent search and extraction"""
    
    def __init__(self, gemini_api_key: str, verbose: bool = False):
        self.api_key = gemini_api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        self.verbose = verbose
        
    def _call_gemini(self, prompt: str, temperature: float = 0.3) -> str:
        """Direct Gemini API call with error handling"""
        try:
            params = {"key": self.api_key}
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}]
                    }
                ],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": 4096,
                }
            }
            
            response = requests.post(
                self.base_url,
                params=params,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            candidates = data.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
        return ""
    
    def _debug(self, msg: str) -> None:
        """Emit debug output only when verbose toggle is enabled."""
        if getattr(self, 'verbose', False):
            try:
                print(msg)
            except Exception:
                pass
    
    def _normalize_currency(self, currency: str) -> str:
        """Normalize currency to standard ISO codes"""
        if not currency:
            return 'INR'
        
        currency_str = str(currency).strip().upper()
        
        # Direct mapping for common currencies
        currency_map = {
            'INR': 'INR', 'RUPEES': 'INR', 'RUPEE': 'INR', 'RS': 'INR', 'RS.': 'INR',
            'USD': 'USD', 'DOLLARS': 'USD', 'DOLLAR': 'USD', 'US$': 'USD',
            'EUR': 'EUR', 'EUROS': 'EUR', 'EURO': 'EUR',
            'GBP': 'GBP', 'POUNDS': 'GBP', 'POUND': 'GBP',
            'JPY': 'JPY', 'YEN': 'JPY',
            'CAD': 'CAD', 'CANADIAN': 'CAD',
            'AUD': 'AUD', 'AUSTRALIAN': 'AUD',
            'SGD': 'SGD', 'SINGAPORE': 'SGD',
            'MYR': 'MYR', 'RINGGIT': 'MYR',
            'CNY': 'CNY', 'YUAN': 'CNY', 'RMB': 'CNY'
        }
        
        # Check for exact matches
        if currency_str in currency_map:
            return currency_map[currency_str]
        
        # Check for symbols in original string
        original = str(currency).strip()
        if '₹' in original or 'Rs' in original or 'INR' in original.upper():
            return 'INR'
        elif '$' in original and 'US' not in original.upper():
            return 'USD'
        elif '€' in original:
            return 'EUR'
        elif '£' in original:
            return 'GBP'
        elif '¥' in original:
            return 'JPY'
        
        # Default fallback
        return 'INR'
    
    def _try_parse_float(self, s: Optional[str]) -> Optional[float]:
        """Parse a numeric string into float, handling commas and stray symbols."""
        if not s:
            return None
        try:
            cleaned = str(s).strip()
            # Remove common currency symbols and spaces
            cleaned = cleaned.replace(',', '')
            cleaned = cleaned.replace('$', '').replace('₹', '').replace('€', '').replace('£', '').replace('¥', '')
            cleaned = cleaned.replace('US$', '').replace('USD', '').replace('INR', '')
            cleaned = cleaned.strip()
            if not cleaned:
                return None
            return float(cleaned)
        except Exception:
            return None
    
    def _extract_structured_price(self, soup) -> Tuple[Optional[float], Optional[str]]:
        """Try to extract the main product price from structured data/meta tags.
        Returns (price, currency) if found.
        """
        try:
            # 1) Meta tags commonly used for price
            meta_props = ['og:price:amount', 'product:price:amount']
            for prop in meta_props:
                tag = soup.find('meta', attrs={'property': prop})
                if tag and tag.get('content'):
                    price = self._try_parse_float(tag['content'])
                    if price is not None and price > 0:
                        # Try currency alongside
                        cur_tag = soup.find('meta', attrs={'property': 'og:price:currency'}) or \
                                  soup.find('meta', attrs={'property': 'product:price:currency'})
                        currency = None
                        if cur_tag and cur_tag.get('content'):
                            currency = self._normalize_currency(cur_tag['content'])
                        return price, currency
            
            # 2) itemprop price
            ip = soup.find(attrs={'itemprop': 'price'})
            if ip is not None:
                content = ip.get('content') or ip.get_text(strip=True)
                price = self._try_parse_float(content)
                if price and price > 0:
                    # currency may be specified nearby
                    cur = None
                    cur_tag = soup.find(attrs={'itemprop': 'priceCurrency'})
                    if cur_tag is not None:
                        cur_content = cur_tag.get('content') or cur_tag.get_text(strip=True)
                        cur = self._normalize_currency(cur_content) if cur_content else None
                    return price, cur
            
            # 3) JSON-LD structured data (Product/offers)
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(script.string or '')
                except Exception:
                    continue
                # Normalize into list of dicts
                candidates = []
                if isinstance(data, dict):
                    candidates = [data]
                elif isinstance(data, list):
                    candidates = [d for d in data if isinstance(d, dict)]
                for d in candidates:
                    # Price directly
                    price = None
                    currency = None
                    if 'price' in d:
                        price = self._try_parse_float(d.get('price'))
                    # Offers nested
                    offers = d.get('offers')
                    if offers:
                        if isinstance(offers, dict):
                            if 'price' in offers and price is None:
                                price = self._try_parse_float(offers.get('price'))
                            if 'priceCurrency' in offers:
                                currency = self._normalize_currency(offers.get('priceCurrency'))
                        elif isinstance(offers, list):
                            for off in offers:
                                if isinstance(off, dict) and 'price' in off:
                                    price = self._try_parse_float(off.get('price')) or price
                                    if 'priceCurrency' in off and not currency:
                                        currency = self._normalize_currency(off.get('priceCurrency'))
                    # Currency fields at top-level
                    if not currency and 'priceCurrency' in d:
                        currency = self._normalize_currency(d.get('priceCurrency'))
                    if price and price > 0:
                        return price, currency
            
            # 4) Common CSS selectors (e.g., eBay and generic storefronts)
            selector_candidates = [
                'span[itemprop="price"]',
                'meta[itemprop="price"]',
                '#prcIsum',
                '#mm-saleDscPrc',
                '#prcIsum_bidPrice',
                '.x-price-primary .ux-textspans',
                '.price .amount',
                '.product-price .amount',
                '.price-current',
                '.price .price',
            ]
            for sel in selector_candidates:
                el = soup.select_one(sel)
                if not el:
                    continue
                content = el.get('content') or el.get_text(" ", strip=True)
                price = self._try_parse_float(content)
                if price and price > 0:
                    # Try to detect currency nearby
                    currency = None
                    cur_el = soup.select_one('[itemprop="priceCurrency"]')
                    if cur_el:
                        cur_content = cur_el.get('content') or cur_el.get_text(strip=True)
                        if cur_content:
                            currency = self._normalize_currency(cur_content)
                    if not currency:
                        # Try meta fallback
                        cur_tag = soup.find('meta', attrs={'property': 'og:price:currency'}) or \
                                  soup.find('meta', attrs={'property': 'product:price:currency'})
                        if cur_tag and cur_tag.get('content'):
                            currency = self._normalize_currency(cur_tag['content'])
                    return price, currency
        except Exception:
            pass
        return None, None
    
    def _maybe_correct_price(self, extracted_price: float, extracted_currency: str, soup, text: str) -> Tuple[float, Optional[str]]:
        """Correct common order-of-magnitude mistakes using structured page data.
        Returns (final_price, correction_reason)
        """
        try:
            struct_price, struct_cur = self._extract_structured_price(soup)
            if struct_price and struct_price > 0:
                # If currency differs but struct currency present, require match
                if struct_cur and extracted_currency and struct_cur != self._normalize_currency(extracted_currency):
                    pass  # don't use structured price from different currency
                else:
                    # Check for x10 or x100 mistakes
                    ratio = extracted_price / struct_price if struct_price > 0 else 1.0
                    # Helper to check near equality within 5%
                    def near(x, y, pct=0.05):
                        if y == 0:
                            return False
                        return abs(x - y) <= pct * y
                    if near(ratio, 1.0):
                        # Already matches structured price scale
                        return extracted_price, None
                    if near(ratio, 10.0):
                        return struct_price, 'corrected_by_jsonld_x10'
                    if near(ratio, 100.0):
                        return struct_price, 'corrected_by_jsonld_x100'
                    if near(ratio, 1000.0):
                        return struct_price, 'corrected_by_jsonld_x1000'
                    # If extracted is huge while struct is small (< 50), trust struct
                    if extracted_price >= 100 and struct_price < 50 and extracted_price >= struct_price * 50:
                        return struct_price, 'corrected_by_jsonld_plausibility'
            
            # Fallback regex for decimal candidates when extracted seems scaled
            if extracted_price >= 100:
                # Capture decimal USD amounts from text
                decimal_candidates = []
                for m in re.finditer(r'(?:US\$|USD|\$)\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2}))', text):
                    val = self._try_parse_float(m.group(1))
                    if val is not None:
                        decimal_candidates.append(val)
                if decimal_candidates:
                    # If any candidate matches extracted/100 closely, correct
                    target = extracted_price / 100.0
                    for cand in decimal_candidates:
                        if abs(cand - target) <= 0.05:
                            return cand, 'corrected_by_regex_x100'
                    # Also try /10
                    target10 = extracted_price / 10.0
                    for cand in decimal_candidates:
                        if abs(cand - target10) <= 0.05:
                            return cand, 'corrected_by_regex_x10'
        except Exception:
            pass
        return extracted_price, None
    
    def _run_coro_safely(self, coro):
        """Run an async coroutine safely from sync context, even if a loop is running."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import threading
            result_box = {}
            def runner():
                new_loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(new_loop)
                    result_box['result'] = new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()
            t = threading.Thread(target=runner)
            t.start()
            t.join()
            return result_box.get('result')
        else:
            return asyncio.run(coro)

    def _similarity(self, a: str, b: str) -> float:
        """Simple similarity score between two strings [0..1]."""
        if not a or not b:
            return 0.0
        try:
            return SequenceMatcher(None, a.lower(), b.lower()).ratio()
        except Exception:
            return 0.0

    def _select_best_item(self, items: List["PriceItem"], car_context: Dict) -> Tuple[Optional["PriceItem"], float]:
        """Select the most relevant PriceItem based on manufacturer/model/scale match."""
        best_item = None
        best_score = 0.0
        manu = str(car_context.get('manufacturer') or '').strip()
        model = str(car_context.get('model_name') or '').strip()
        scale = str(car_context.get('scale') or '').strip()

        for it in items:
            try:
                score = 0.0
                manu_sim = self._similarity(manu, getattr(it, 'manufacturer', '') or '')
                model_sim = self._similarity(model, getattr(it, 'model_name', '') or '')
                if manu and manu_sim >= 0.6:
                    score += 0.3 * manu_sim
                if model and model_sim >= 0.7:
                    score += 0.6 * model_sim
                scl = getattr(it, 'scale', None) or ''
                if scale and scl:
                    scl_norm = scl.replace('/', ':').replace(' ', '')
                    scale_norm = scale.replace('/', ':').replace(' ', '')
                    if scl_norm == scale_norm:
                        score += 0.1
                if score > best_score:
                    best_score = score
                    best_item = it
            except Exception:
                continue

        return best_item, best_score

    def _extract_with_crawl4ai(self, url: str, car_context: Dict) -> Optional[MarketListing]:
        """Run Crawl4AI-based extraction for a single URL and return MarketListing if suitable."""
        try:
            items, markdown = self._run_coro_safely(_extract_from_url(url, self.api_key))
        except Exception as e:
            logger.warning(f"Crawl4AI extraction failed for {url}: {e}")
            items = []

        if not items:
            return None

        selected, rel_score = self._select_best_item(items, car_context)
        if not selected:
            selected = items[0]
            rel_score = 0.5

        # Fetch HTML to support currency fallback and price correction
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = None
        soup = None
        text = ''
        title = ''
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            for s in soup(["script", "style"]):
                s.decompose()
            text = ' '.join(soup.get_text().split())[:8000]
            title = soup.title.string if soup.title else ''
        except Exception:
            pass

        # Currency post-extraction
        currency = None
        if getattr(selected, 'currency', None):
            currency = self._normalize_currency(getattr(selected, 'currency'))
        fallback_confidence = None
        source_label = 'extracted'
        if not currency:
            try:
                if response is not None:
                    currency_result = detect_currency_from_webpage(url, response.text, text)
                    currency = currency_result.currency
                    fallback_confidence = currency_result.confidence
                    source_label = f"fallback:{currency_result.detection_method}"
            except Exception:
                currency = 'INR'  # safe default
                source_label = 'fallback:default'

        self._debug(f"    💱 Currency (post-extraction): {currency} (source: {source_label}{f', conf: {fallback_confidence:.2f}' if fallback_confidence is not None else ''})")

        # Price correction
        extracted_price = float(getattr(selected, 'price'))
        corrected_price, reason = self._maybe_correct_price(extracted_price, currency, soup, text)
        if reason:
            self._debug(f"    🔧 Price correction applied: {extracted_price} -> {corrected_price} ({reason})")
            pass

        # Confidence mapping from relevance score
        base_confidence = 0.6 + 0.4 * max(0.0, min(rel_score, 1.0))

        return MarketListing(
            price=float(corrected_price),
            currency=currency,
            title=(getattr(selected, 'title', None) or title)[:200] if (getattr(selected, 'title', None) or title) else '',
            url=url,
            seller=getattr(selected, 'seller', None),
            confidence=min(max(base_confidence, 0.0), 1.0)
        )
    
    def generate_search_query(self, manufacturer: str, model_name: str, scale: str) -> str:
        """Generate optimized search query for finding market prices"""
        prompt = f"""
Generate a single optimized web search query to find current market prices for this specific diecast model car.
The query should help find actual listings where this model is for sale.

Manufacturer: {manufacturer}
Model Name: {model_name}
Scale: {scale}

Requirements:
- Include the exact manufacturer and model name
- Include the scale if provided
- Add keywords like "diecast", "for sale", "price", "buy"
- Make it specific enough to find this exact model
- Return ONLY the search query, no explanations

Example output format:
Hot Wheels Ferrari 488 GTB 1:64 diecast for sale price
"""
        
        query = self._call_gemini(prompt, temperature=0.1)
        if not query or len(query) > 200:
            # Fallback to simple query
            query = f"{manufacturer} {model_name} {scale} diecast for sale price".strip()
        
        # Clean up the query
        query = query.strip().strip('"').strip("'")
        
        self._debug("\n" + "=" * 80)
        self._debug(f"GENERATED SEARCH QUERY: {query}")
        self._debug("=" * 80 + "\n")
        
        return query
    
    def search_web(self, query: str, num_results: int = 5) -> List[str]:
        """Use direct web scraping to get search results"""
        urls = []
        
        # Method 1: Direct Google search scraping
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
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
        
        # Fallback to DuckDuckGo HTML scraping
        if not urls:
            self._debug("Google search returned no results, trying DuckDuckGo...")
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
                response = requests.get(search_url, headers=headers, timeout=10)
                response.raise_for_status()
                
                # Parse DuckDuckGo results more reliably
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find result links
                for result in soup.find_all('a', class_='result__a'):
                    href = result.get('href')
                    if href and href.startswith('http'):
                        if 'duckduckgo.com' not in href and 'youtube.com' not in href and 'wikipedia.org' not in href:
                            urls.append(href)
                            if len(urls) >= num_results:
                                break
                
                # If no results found with class, try alternative pattern
                if not urls:
                    pattern = r'href="(https?://[^"]+)"'
                    matches = re.findall(pattern, response.text)
                    seen = set()
                    for url in matches[:num_results * 3]:  # Get extra to filter
                        if url not in seen and 'duckduckgo.com' not in url and 'youtube.com' not in url:
                            urls.append(url)
                            seen.add(url)
                        if len(urls) >= num_results:
                            break
                
                if urls:
                    logger.info(f"Found {len(urls)} URLs via DuckDuckGo")
                            
            except Exception as e:
                logger.warning(f"DuckDuckGo search failed: {e}")
                self._debug(f"DuckDuckGo search error: {e}")
        
        # Final fallback: Bing search
        if not urls:
            self._debug("Trying Bing search as final fallback...")
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                bing_url = f"https://www.bing.com/search?q={quote_plus(query)}"
                response = requests.get(bing_url, headers=headers, timeout=10)
                response.raise_for_status()
                
                # Parse Bing results
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
                    
            except Exception as e:
                logger.warning(f"Bing search failed: {e}")
                self._debug(f"Bing search error: {e}")
        
        # If still no URLs, provide some default marketplaces
        if not urls:
            self._debug("All search methods failed, using default marketplace URLs...")
            default_urls = [
                f"https://www.ebay.com/sch/i.html?_nkw={quote_plus(query)}",
                f"https://www.amazon.com/s?k={quote_plus(query)}",
                f"https://www.etsy.com/search?q={quote_plus(query)}"
            ]
            urls = default_urls[:num_results]
        
        return urls[:num_results]
    
    def extract_price_from_url(self, url: str, car_context: Dict) -> Optional[MarketListing]:
        """Extract price information from a URL using Crawl4AI first, then Gemini fallback."""
        try:
            # First try Crawl4AI-based structured extraction
            crawl_listing = self._extract_with_crawl4ai(url, car_context)
            if crawl_listing:
                return crawl_listing

            # Fallback: Fetch the webpage content
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()

            # Get text content (limit to avoid token limits)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()

            # Get text and limit it
            text = soup.get_text()
            text = ' '.join(text.split())[:8000]  # Limit characters

            # Extract title
            title = soup.title.string if soup.title else ""
            
            # Use Gemini to extract price information (currency must be inferred from page content only)
            prompt = f"""
Analyze this webpage content and extract the price information for a diecast model car.

Context - We are looking for:
Manufacturer: {car_context.get('manufacturer', 'Unknown')}
Model: {car_context.get('model_name', 'Unknown')}
Scale: {car_context.get('scale', 'Unknown')}

Webpage URL: {url}
Title: {title}
Content (truncated): {text[:5000]}

Extract the following information:
1. Price: numeric value only, preserve decimal digits EXACTLY as shown on the page. Remove only currency symbols and thousands separators (commas/spaces). Do NOT round. Do NOT change scale. Examples: "$3.95" → 3.95; "₹2,499.00" → 2499.00; "$19" → 19
2. Currency: ISO code inferred from page content ONLY (symbols/text near the price such as ₹/Rs/INR, $/USD, €/EUR, £/GBP, ¥/JPY). Do NOT assume from the domain.
3. Product title from the page
4. Seller/marketplace name if identifiable
5. Confidence score (0-1) that this is the correct model

IMPORTANT:
- Only extract if the listing matches or is very similar to the target model
- If multiple prices exist, choose the MAIN selling price (not shipping, not taxes, not strikethrough MSRP/was/list price)
- Prefer labels like "Price", "Our Price", "Now", "Sale", "Add to Cart" over "MSRP", "Was", "Compare at"
- If you can't find a valid price or it's not the right model, return "NO_MATCH"

Return ONLY a JSON object like this (no extra text):
{{"price": 99.99, "currency": "USD", "title": "Product Title", "seller": "eBay", "confidence": 0.95}}

Currency examples:
- ₹2200 or Rs. 2200 or 2200 Rupees → currency: "INR"
- $25.99 or 25.99 USD → currency: "USD"
- €45.00 or 45 EUR → currency: "EUR"
- £35.50 or 35.50 GBP → currency: "GBP"

Or return: NO_MATCH
"""
            
            result = self._call_gemini(prompt, temperature=0.1)
            
            # Parse the result
            if "NO_MATCH" in result:
                return None
            
            # Try to extract JSON from the response
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    
                    # Validate required fields
                    if 'price' in data and data['price'] > 0:
                        # Post-extraction currency handling
                        extracted_currency = data.get('currency')
                        source_label = 'extracted'
                        currency = None
                        
                        if extracted_currency:
                            currency = self._normalize_currency(extracted_currency)
                        
                        # Fallback: detect from page content ONLY AFTER extraction if currency missing
                        fallback_confidence = None
                        if not currency:
                            try:
                                currency_result = detect_currency_from_webpage(url, response.text, text)
                                currency = currency_result.currency
                                fallback_confidence = currency_result.confidence
                                source_label = f"fallback:{currency_result.detection_method}"
                            except Exception:
                                currency = 'INR'  # safe default
                                source_label = 'fallback:default'
                        
                        self._debug(f"    💱 Currency (post-extraction): {currency} (source: {source_label}{f', conf: {fallback_confidence:.2f}' if fallback_confidence is not None else ''})")
                        
                        # Price correction using structured data/regex to avoid decimal scaling mistakes
                        extracted_price = float(data['price'])
                        corrected_price, reason = self._maybe_correct_price(extracted_price, currency, soup, text)
                        if reason:
                            self._debug(f"    🔧 Price correction applied: {extracted_price} -> {corrected_price} ({reason})")
                            pass
                        
                        # Confidence handling (do not rely on pre-detection)
                        base_confidence = float(data.get('confidence', 0.8))
                        final_confidence = base_confidence
                        if fallback_confidence is not None and fallback_confidence >= 0.9:
                            final_confidence = min(base_confidence + 0.05, 1.0)
                        
                        return MarketListing(
                            price=float(corrected_price),
                            currency=currency,
                            title=data.get('title', title)[:200],
                            url=url,
                            seller=data.get('seller'),
                            confidence=final_confidence
                        )
                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    logger.warning(f"Failed to parse extraction result: {e}")
            
        except Exception as e:
            logger.warning(f"Failed to extract from {url}: {e}")
        
        return None
    
    def search_and_extract(self, manufacturer: str, model_name: str, scale: str, 
                          num_results: int = 3) -> Tuple[List[MarketListing], str]:
        """Main method to search and extract market prices"""
        
        # Generate search query
        query = self.generate_search_query(manufacturer, model_name, scale)
        
        # Search the web
        urls = self.search_web(query, num_results=num_results + 2)  # Get extra URLs
        
        self._debug(f"Found {len(urls)} URLs to analyze")
        
        # Prepare context for extraction
        car_context = {
            'manufacturer': manufacturer,
            'model_name': model_name,
            'scale': scale
        }
        
        # Extract prices from each URL
        listings = []
        for i, url in enumerate(urls[:num_results + 2], 1):
            self._debug(f"Analyzing URL {i}/{len(urls[:num_results+2])}: {url[:80]}...")
            
            listing = self.extract_price_from_url(url, car_context)
            if listing and listing.confidence >= 0.5:
                listings.append(listing)
                self._debug(f"  ✓ Found: {listing.currency} {listing.price:.2f} (confidence: {listing.confidence:.2f})")
            else:
                self._debug(f"  ✗ No valid price found or low confidence")
                pass
            
            # Stop if we have enough results
            if len(listings) >= num_results:
                break
            
            # Small delay to be respectful
            time.sleep(0.5)
        
        return listings, query
    
    def validate_and_filter(self, listings: List[MarketListing], 
                           min_confidence: float = 0.5) -> List[MarketListing]:
        """Filter listings by confidence and remove outliers"""
        
        self._debug(f"\n🔍 FILTERING DEBUG: Starting with {len(listings)} listings")
        for i, listing in enumerate(listings, 1):
            self._debug(f"  {i}. {listing.currency} {listing.price:.2f} (confidence: {listing.confidence:.2f})")
        
        # Filter by confidence
        filtered = [l for l in listings if l.confidence >= min_confidence]
        self._debug(f"📊 After confidence filter (>= {min_confidence}): {len(filtered)} listings")
        
        if len(filtered) <= 2:
            self._debug(f"✅ Keeping all {len(filtered)} listings (≤ 2 items)")
            return filtered
        
        # Remove price outliers (optional) - but be more lenient
        prices = [l.price for l in filtered]
        if prices:
            avg_price = sum(prices) / len(prices)
            self._debug(f"💰 Average price: {avg_price:.2f}")
            
            # Be more lenient with outlier detection - allow up to 10x difference
            before_outlier_filter = len(filtered)
            filtered = [l for l in filtered if 0.1 * avg_price <= l.price <= 10 * avg_price]
            self._debug(f"🎯 After outlier filter (0.1x to 10x avg): {len(filtered)} listings")
            
            if len(filtered) < before_outlier_filter:
                self._debug(f"⚠️  Removed {before_outlier_filter - len(filtered)} outliers")
                pass
        
        self._debug(f"✅ Final result: {len(filtered)} listings\n")
        return filtered


def search_market_prices_agentic(car, gemini_api_key: str, num_results: int = 3, verbose: bool = False) -> Dict:
    """
    Main entry point for agentic market search.
    Returns a dictionary with listings and statistics.
    """
    
    if not gemini_api_key:
        logger.error("No Gemini API key provided")
        return {'listings': [], 'query': '', 'error': 'No API key'}
    
    # Extract car details
    manufacturer = getattr(car, 'manufacturer', '') or ''
    model_name = getattr(car, 'model_name', '') or ''
    scale = getattr(car, 'scale', '') or ''
    
    if not manufacturer or not model_name:
        return {'listings': [], 'query': '', 'error': 'Missing car details'}
    
    try:
        # Initialize the agentic search
        searcher = AgenticMarketSearch(gemini_api_key, verbose=verbose)
        
        # Perform search and extraction
        listings, query = searcher.search_and_extract(
            manufacturer, model_name, scale, num_results
        )
        
        # Validate and filter results
        valid_listings = searcher.validate_and_filter(listings)
        
        # Convert to dictionary format for compatibility
        results = []
        for listing in valid_listings:
            results.append({
                'price': listing.price,
                'currency': listing.currency,
                'title': listing.title,
                'url': listing.url,
                'seller': listing.seller,
                'confidence': listing.confidence,
                'source_listing_url': listing.url,  # For compatibility
                'manufacturer': manufacturer,
                'model_name': model_name,
                'scale': scale
            })
        
        return {
            'listings': results,
            'query': query,
            'count': len(results),
            'success': True
        }
        
    except Exception as e:
        logger.error(f"Agentic search failed: {e}")
        return {
            'listings': [],
            'query': '',
            'error': str(e),
            'success': False
        }
