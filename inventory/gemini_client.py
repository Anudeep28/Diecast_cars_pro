"""
Gemini API client for extracting pricing information from URLs.
Provides direct extraction of price details for model car listings.
"""
import json
import logging
import requests
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal
from dataclasses import dataclass


@dataclass
class GeminiPriceExtraction:
    price: Decimal
    currency: str
    title: Optional[str] = None
    model_name: Optional[str] = None
    manufacturer: Optional[str] = None
    scale: Optional[str] = None
    seller: Optional[str] = None
    url: Optional[str] = None
    listing_date: Optional[str] = None


class GeminiClient:
    """Client for interacting with the Gemini API for price extraction."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        self.logger = logging.getLogger(__name__)
    
    def extract_price_from_html(self, html_content: str, url: str = None) -> Optional[GeminiPriceExtraction]:
        """
        Extract price information from HTML content using Gemini API.
        
        Args:
            html_content: HTML content to analyze
            url: Source URL for reference
            
        Returns:
            GeminiPriceExtraction object if successful, None otherwise
        """
        prompt = self._create_extraction_prompt(html_content, url)
        
        try:
            response = self._call_gemini_api(prompt)
            extraction = self._parse_gemini_response(response, url)
            return extraction
        except Exception as e:
            self.logger.warning(f"Gemini extraction failed: {e}")
            return None
    
    def extract_price_from_url(self, url: str) -> Optional[GeminiPriceExtraction]:
        """
        Fetch a URL and extract price information using Gemini API.
        
        Args:
            url: URL to fetch and analyze
            
        Returns:
            GeminiPriceExtraction object if successful, None otherwise
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            return self.extract_price_from_html(response.text, url)
        except Exception as e:
            self.logger.warning(f"Failed to fetch URL {url}: {e}")
            return None
    
    def _create_extraction_prompt(self, html_content: str, url: Optional[str] = None) -> str:
        """Create a prompt for Gemini to extract price information."""
        url_info = f"from URL: {url}" if url else ""
        
        # Only use a portion of the HTML to avoid token limits
        html_preview = html_content[:25000]
        
        return f"""
        Extract model car pricing information {url_info}. 
        
        Examine the HTML content and extract the following information in JSON format:
        
        1. price: The numeric price value (without currency symbol)
        2. currency: The currency code or symbol (USD, EUR, INR, etc.)
        3. title: The title of the listing or product
        4. model_name: The model car name (e.g., "Ferrari 488 GTB")
        5. manufacturer: The brand/manufacturer (e.g., Hot Wheels, AUTOart)
        6. scale: The scale notation like "1:18" or "1/64"
        7. seller: The seller or marketplace name
        8. listing_date: Date of the listing if available
        
        If you can't find specific information, set those values to null.
        Return ONLY the JSON response and nothing else.
        
        HTML Content:
        {html_preview}
        """
    
    def _call_gemini_api(self, prompt: str) -> Dict[str, Any]:
        """Call the Gemini API with the given prompt."""
        params = {
            "key": self.api_key
        }
        
        payload = {
            "contents": [{
                "role": "user",
                "parts": [{
                    "text": prompt
                }]
            }]
        }
        
        response = requests.post(
            self.api_url, 
            params=params,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()
    
    def _parse_gemini_response(self, response: Dict[str, Any], url: Optional[str] = None) -> Optional[GeminiPriceExtraction]:
        """Parse Gemini API response to extract structured pricing data."""
        try:
            # Validate response structure
            if not isinstance(response, dict):
                self.logger.warning(f"Invalid response type: {type(response)}")
                return None
                
            candidates = response.get("candidates")
            if not candidates or not isinstance(candidates, list) or len(candidates) == 0:
                self.logger.warning("No candidates in Gemini response")
                return None
                
            content = candidates[0].get("content")
            if not isinstance(content, dict):
                self.logger.warning(f"Invalid content type: {type(content)}")
                return None
            
            parts = content.get("parts")
            if not parts or not isinstance(parts, list) or len(parts) == 0:
                self.logger.warning("No parts in Gemini response content")
                return None
                
            text_response = parts[0].get("text", "")
            if not text_response:
                self.logger.warning("Empty text response from Gemini")
                return None
            
            # Extract JSON from response (might be wrapped in code blocks)
            json_match = text_response.strip()
            if "```json" in text_response:
                try:
                    json_match = text_response.split("```json")[1].split("```")[0].strip()
                except IndexError:
                    self.logger.warning("Malformed JSON code block in response")
                    return None
            elif "```" in text_response:
                try:
                    json_match = text_response.split("```")[1].split("```")[0].strip()
                except IndexError:
                    self.logger.warning("Malformed code block in response")
                    return None
                
            # Clean and parse JSON
            try:
                data = json.loads(json_match)
            except json.JSONDecodeError as e:
                self.logger.warning(f"JSON decode error: {e}. Raw response: {json_match[:200]}...")
                return None
                
            if not isinstance(data, dict):
                self.logger.warning(f"Parsed data is not a dict: {type(data)}")
                return None
                
            self.logger.info(f"Successfully parsed Gemini JSON: {data}")
            
            # Safely extract and validate price
            price_raw = data.get("price")
            if price_raw is None:
                self.logger.warning("No price field in response")
                return None
                
            # Handle various price formats
            try:
                if isinstance(price_raw, (int, float)):
                    price = Decimal(str(price_raw))
                elif isinstance(price_raw, str):
                    # Clean price string - remove common non-numeric characters
                    price_clean = price_raw.strip().replace(',', '').replace('$', '').replace('₹', '').replace('€', '').replace('£', '')
                    if not price_clean or price_clean.lower() in ['null', 'none', 'n/a', 'na']:
                        self.logger.warning(f"Invalid price value: {price_raw}")
                        return None
                    price = Decimal(price_clean)
                else:
                    self.logger.warning(f"Unsupported price type: {type(price_raw)} - {price_raw}")
                    return None
                    
                if price <= 0:
                    self.logger.warning(f"Invalid price value: {price}")
                    return None
                    
            except (ValueError, TypeError, Exception) as e:
                self.logger.warning(f"Failed to convert price '{price_raw}' to Decimal: {e}")
                return None
            
            # Safely extract currency with fallback
            currency = data.get("currency")
            if not currency or not isinstance(currency, str):
                currency = "USD"  # Default fallback
            else:
                currency = currency.strip()
                if not currency or currency.lower() in ['null', 'none', 'n/a', 'na']:
                    currency = "USD"
            
            # Safely extract other fields
            def safe_extract(field_name: str) -> Optional[str]:
                value = data.get(field_name)
                if value is None or (isinstance(value, str) and value.lower() in ['null', 'none', 'n/a', 'na']):
                    return None
                return str(value).strip() if value else None
            
            return GeminiPriceExtraction(
                price=price,
                currency=currency,
                title=safe_extract("title"),
                model_name=safe_extract("model_name"),
                manufacturer=safe_extract("manufacturer"),
                scale=safe_extract("scale"),
                seller=safe_extract("seller"),
                url=url,
                listing_date=safe_extract("listing_date")
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to parse Gemini response: {type(e).__name__}: {e}")
            return None
