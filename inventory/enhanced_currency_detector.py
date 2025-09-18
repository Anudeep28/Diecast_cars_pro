"""
Enhanced Currency Detection System
Combines multiple approaches for accurate currency detection from web content.
"""
import re
import requests
from typing import Optional, Dict, List, Tuple
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import logging
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)

@dataclass
class CurrencyDetectionResult:
    """Result of currency detection with confidence score"""
    currency: str
    confidence: float
    detection_method: str
    raw_indicators: List[str]

class EnhancedCurrencyDetector:
    """Enhanced currency detector using multiple detection methods"""
    
    def __init__(self):
        # Domain-based currency mapping (most reliable)
        self.domain_currency_map = {
            # Indian domains - specific sites first, then TLD
            'flipkart.com': 'INR', 'amazon.in': 'INR', 'snapdeal.com': 'INR',
            'myntra.com': 'INR', 'paytm.com': 'INR', 'shopclues.com': 'INR',
            'horizondiecast.com': 'INR',  # Known Indian diecast site
            'diecastxchange.com': 'INR',  # Another Indian diecast site
            '.in': 'INR',
            
            # US domains - specific sites
            'amazon.com': 'USD', 'ebay.com': 'USD', 'walmart.com': 'USD',
            'target.com': 'USD', 'bestbuy.com': 'USD', 'newegg.com': 'USD',
            # Note: Removed generic .com mapping as it's too broad
            
            # UK domains
            '.co.uk': 'GBP', 'amazon.co.uk': 'GBP', 'ebay.co.uk': 'GBP', 'argos.co.uk': 'GBP',
            
            # European domains
            '.de': 'EUR', '.fr': 'EUR', '.es': 'EUR', '.it': 'EUR', '.nl': 'EUR',
            'amazon.de': 'EUR', 'amazon.fr': 'EUR', 'amazon.es': 'EUR',
            
            # Other regions
            '.ca': 'CAD', 'amazon.ca': 'CAD',
            '.au': 'AUD', 'amazon.com.au': 'AUD',
            '.jp': 'JPY', 'amazon.co.jp': 'JPY',
            '.sg': 'SGD', 'lazada.sg': 'SGD',
            '.my': 'MYR', 'lazada.com.my': 'MYR',
            '.cn': 'CNY', 'taobao.com': 'CNY', 'tmall.com': 'CNY',
        }
        
        # Language-based currency indicators
        self.language_currency_map = {
            'hindi': 'INR', 'bengali': 'INR', 'tamil': 'INR', 'telugu': 'INR',
            'english-in': 'INR',  # English content with Indian context
            'chinese': 'CNY', 'japanese': 'JPY', 'korean': 'KRW',
            'german': 'EUR', 'french': 'EUR', 'spanish': 'EUR', 'italian': 'EUR',
        }
        
        # Enhanced symbol patterns with context
        self.currency_patterns = [
            # Indian Rupee patterns (high priority)
            (r'₹\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', 'INR', 0.95),
            (r'Rs\.?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', 'INR', 0.90),
            (r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:rupees?|INR)', 'INR', 0.85),
            (r'Indian\s+Rupees?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', 'INR', 0.90),
            
            # USD patterns
            (r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', 'USD', 0.80),  # Lower confidence as $ is ambiguous
            (r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*USD', 'USD', 0.90),
            (r'US\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', 'USD', 0.95),
            
            # Euro patterns
            (r'€\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', 'EUR', 0.95),
            (r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*EUR', 'EUR', 0.90),
            
            # GBP patterns
            (r'£\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', 'GBP', 0.95),
            (r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*GBP', 'GBP', 0.90),
            
            # Other currencies
            (r'¥\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', 'JPY', 0.85),  # Could be CNY too
            (r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*JPY', 'JPY', 0.90),
            (r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*CNY', 'CNY', 0.90),
        ]
    
    def detect_from_domain(self, url: str) -> Optional[CurrencyDetectionResult]:
        """Detect currency based on domain/URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Remove www prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # Check exact domain matches first (highest confidence)
            for domain_key, currency in self.domain_currency_map.items():
                if domain_key.startswith('.'):  # TLD check
                    if domain.endswith(domain_key):
                        return CurrencyDetectionResult(
                            currency=currency,
                            confidence=0.85,
                            detection_method='domain_tld',
                            raw_indicators=[domain_key]
                        )
                else:  # Exact domain match
                    if domain == domain_key or domain.endswith('.' + domain_key):
                        return CurrencyDetectionResult(
                            currency=currency,
                            confidence=0.95,
                            detection_method='domain_exact',
                            raw_indicators=[domain_key]
                        )
            
            return None
            
        except Exception as e:
            logger.warning(f"Domain currency detection failed: {e}")
            return None
    
    def detect_from_html_meta(self, html_content: str) -> Optional[CurrencyDetectionResult]:
        """Detect currency from HTML meta tags and structured data"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            indicators = []
            
            # Check meta tags
            meta_tags = [
                'currency', 'og:price:currency', 'product:price:currency',
                'twitter:data1', 'price:currency'
            ]
            
            for tag in meta_tags:
                meta = soup.find('meta', attrs={'name': tag}) or soup.find('meta', attrs={'property': tag})
                if meta and meta.get('content'):
                    content = meta.get('content').upper()
                    indicators.append(content)
                    
                    # Check if it's a valid currency code
                    if content in ['INR', 'USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD', 'SGD', 'MYR', 'CNY']:
                        return CurrencyDetectionResult(
                            currency=content,
                            confidence=0.90,
                            detection_method='html_meta',
                            raw_indicators=indicators
                        )
            
            # Check JSON-LD structured data
            json_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        # Look for price currency in structured data
                        currency = self._extract_currency_from_json(data)
                        if currency:
                            return CurrencyDetectionResult(
                                currency=currency,
                                confidence=0.85,
                                detection_method='json_ld',
                                raw_indicators=[f'json-ld:{currency}']
                            )
                except json.JSONDecodeError:
                    continue
            
            return None
            
        except Exception as e:
            logger.warning(f"HTML meta currency detection failed: {e}")
            return None
    
    def _extract_currency_from_json(self, data: dict) -> Optional[str]:
        """Recursively extract currency from JSON-LD data"""
        if isinstance(data, dict):
            # Common JSON-LD currency fields
            currency_fields = ['priceCurrency', 'currency', 'currencyCode']
            for field in currency_fields:
                if field in data and isinstance(data[field], str):
                    currency = data[field].upper()
                    if currency in ['INR', 'USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD', 'SGD', 'MYR', 'CNY']:
                        return currency
            
            # Recursively check nested objects
            for value in data.values():
                if isinstance(value, (dict, list)):
                    result = self._extract_currency_from_json(value)
                    if result:
                        return result
        elif isinstance(data, list):
            for item in data:
                result = self._extract_currency_from_json(item)
                if result:
                    return result
        
        return None
    
    def detect_from_content_patterns(self, content: str) -> Optional[CurrencyDetectionResult]:
        """Detect currency using enhanced pattern matching"""
        try:
            best_match = None
            best_confidence = 0
            all_indicators = []
            
            for pattern, currency, confidence in self.currency_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    all_indicators.extend([f"{currency}:{match}" for match in matches[:3]])  # Limit indicators
                    
                    # Boost confidence if multiple matches found
                    adjusted_confidence = min(confidence + (len(matches) - 1) * 0.05, 0.98)
                    
                    if adjusted_confidence > best_confidence:
                        best_confidence = adjusted_confidence
                        best_match = CurrencyDetectionResult(
                            currency=currency,
                            confidence=adjusted_confidence,
                            detection_method='content_pattern',
                            raw_indicators=all_indicators
                        )
            
            return best_match
            
        except Exception as e:
            logger.warning(f"Content pattern currency detection failed: {e}")
            return None
    
    def detect_from_context_clues(self, content: str, url: str) -> Optional[CurrencyDetectionResult]:
        """Detect currency from contextual clues in content"""
        try:
            content_lower = content.lower()
            indicators = []
            
            # Indian context clues (enhanced)
            indian_clues = [
                'india', 'indian', 'mumbai', 'delhi', 'bangalore', 'chennai', 'kolkata',
                'hyderabad', 'pune', 'ahmedabad', 'surat', 'jaipur', 'lucknow',
                'kanpur', 'nagpur', 'visakhapatnam', 'bhopal', 'patna', 'vadodara',
                'ghaziabad', 'ludhiana', 'coimbatore', 'agra', 'madurai', 'nashik',
                'free shipping in india', 'cod available', 'cash on delivery',
                'gst', 'inclusive of taxes', 'pan india delivery', 'upi', 'paytm',
                'phonepe', 'gpay', 'razorpay', 'indian rupees', 'inr', 'rupees',
                'pincode', 'pin code', 'indian postal', 'bharat', 'hindustan',
                'all india shipping', 'across india', 'throughout india'
            ]
            
            indian_score = sum(1 for clue in indian_clues if clue in content_lower)
            if indian_score >= 1:  # Reduced threshold - even 1 strong clue is significant
                indicators.extend([clue for clue in indian_clues if clue in content_lower][:5])
                
                # Boost confidence for strong Indian indicators
                base_confidence = 0.75 if indian_score >= 3 else 0.65
                final_confidence = min(base_confidence + indian_score * 0.05, 0.90)
                
                return CurrencyDetectionResult(
                    currency='INR',
                    confidence=final_confidence,
                    detection_method='context_indian',
                    raw_indicators=indicators
                )
            
            # US context clues
            us_clues = [
                'united states', 'usa', 'us shipping', 'ships from us',
                'new york', 'california', 'texas', 'florida', 'illinois',
                'pennsylvania', 'ohio', 'georgia', 'north carolina', 'michigan',
                'free shipping in us', 'domestic shipping', 'sales tax'
            ]
            
            us_score = sum(1 for clue in us_clues if clue in content_lower)
            if us_score >= 2:
                indicators.extend([clue for clue in us_clues if clue in content_lower][:5])
                return CurrencyDetectionResult(
                    currency='USD',
                    confidence=min(0.65 + us_score * 0.05, 0.80),
                    detection_method='context_us',
                    raw_indicators=indicators
                )
            
            return None
            
        except Exception as e:
            logger.warning(f"Context clues currency detection failed: {e}")
            return None
    
    def detect_currency_comprehensive(self, url: str, html_content: str, 
                                    text_content: str) -> CurrencyDetectionResult:
        """
        Comprehensive currency detection using all available methods.
        Returns the most confident result.
        """
        results = []
        
        # Method 1: Domain-based detection (highest confidence)
        domain_result = self.detect_from_domain(url)
        if domain_result:
            results.append(domain_result)
        
        # Method 2: HTML meta tags and structured data
        meta_result = self.detect_from_html_meta(html_content)
        if meta_result:
            results.append(meta_result)
        
        # Method 3: Content pattern matching
        pattern_result = self.detect_from_content_patterns(text_content)
        if pattern_result:
            results.append(pattern_result)
        
        # Method 4: Context clues
        context_result = self.detect_from_context_clues(text_content, url)
        if context_result:
            results.append(context_result)
        
        # Select the best result based on confidence and method priority
        if results:
            # Enhanced method priority - context clues are now more important
            method_priority = {
                'domain_exact': 5,      # Specific domain mapping (highest)
                'context_indian': 4,    # Indian context clues (very high)
                'context_us': 4,        # US context clues (very high)
                'html_meta': 3,         # Meta tags
                'json_ld': 3,           # Structured data
                'content_pattern': 2,   # Price patterns
                'domain_tld': 1,        # Generic TLD (lowest)
            }
            
            # First, try to find results with good confidence (>= 0.60)
            good_results = [r for r in results if r.confidence >= 0.60]
            if good_results:
                # Among good results, prefer by method priority, then confidence
                best_result = max(good_results, 
                                key=lambda x: (method_priority.get(x.detection_method, 0), x.confidence))
            else:
                # Fallback to highest confidence if no good results
                best_result = max(results, key=lambda x: x.confidence)
            
            return best_result
        
        # Fallback to INR if no detection method worked
        return CurrencyDetectionResult(
            currency='INR',
            confidence=0.30,
            detection_method='fallback_default',
            raw_indicators=['no_detection_method_succeeded']
        )

# Global instance for easy access
currency_detector = EnhancedCurrencyDetector()

def detect_currency_from_webpage(url: str, html_content: str, text_content: str) -> CurrencyDetectionResult:
    """
    Convenience function to detect currency from webpage data.
    
    Args:
        url: The webpage URL
        html_content: Raw HTML content
        text_content: Extracted text content
    
    Returns:
        CurrencyDetectionResult with currency and confidence score
    """
    return currency_detector.detect_currency_comprehensive(url, html_content, text_content)
