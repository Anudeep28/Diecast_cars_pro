"""
AI-powered agentic validation system for market quote relevance.
Uses Gemini AI to intelligently determine if extracted quotes match target car specifications.
"""
import json
import logging
import requests
import time
import hashlib
from typing import Dict, Any, Optional
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class AgenticQuoteValidator:
    """AI-powered validator that uses Gemini to assess quote relevance."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-1.5-flash:generateContent"
        )
        self.last_request_time = 0
        self.min_request_interval = 1.0  # Minimum 1 second between requests
        self.cache_ttl = 3600  # Cache results for 1 hour
    
    def validate_quote_relevance(self, target_car, extracted_quote) -> Dict[str, Any]:
        """
        Use AI to determine if an extracted quote is relevant to the target car.
        
        Args:
            target_car: DiecastCar object with manufacturer, model_name, scale
            extracted_quote: Extracted quote object with price, manufacturer, model_name, etc.
        
        Returns:
            Dict with 'is_relevant' (bool), 'confidence' (float), 'reasoning' (str)
        """
        try:
            # Prepare target car information
            target_info = {
                'manufacturer': getattr(target_car, 'manufacturer', '') or '',
                'model_name': getattr(target_car, 'model_name', '') or '',
                'scale': getattr(target_car, 'scale', '') or '',
            }
            
            # Prepare extracted quote information
            quote_info = {
                'manufacturer': getattr(extracted_quote, 'manufacturer', '') or '',
                'model_name': getattr(extracted_quote, 'model_name', '') or '',
                'scale': getattr(extracted_quote, 'scale', '') or '',
                'title': getattr(extracted_quote, 'title', '') or '',
                'price': getattr(extracted_quote, 'price', 0),
                'currency': getattr(extracted_quote, 'currency', ''),
            }
            
            # Check cache first
            cache_key = self._generate_cache_key(target_info, quote_info)
            cached_result = cache.get(cache_key)
            if cached_result:
                return cached_result
            
            # Create AI prompt for validation
            prompt = self._create_validation_prompt(target_info, quote_info)
            
            # Call Gemini API with rate limiting and retry
            response = self._call_gemini_api_with_retry(prompt)
            
            # Parse AI response
            result = self._parse_validation_response(response)
            
            # Cache the result
            cache.set(cache_key, result, self.cache_ttl)
            
            return result
            
        except Exception as e:
            # Fallback to permissive validation
            return {
                'is_relevant': True,
                'confidence': 0.2,  # Low confidence for fallback
                'reasoning': f'Validation error: {str(e)}, defaulting to accept'
            }
    
    def _create_validation_prompt(self, target_info: Dict, quote_info: Dict) -> str:
        """Create a structured prompt for AI validation."""
        prompt = f"""
You are an expert in diecast model cars and market analysis. Your task is to determine if an extracted market quote is relevant to a specific target diecast model car.

TARGET CAR SPECIFICATIONS:
- Manufacturer: {target_info['manufacturer']}
- Model Name: {target_info['model_name']}
- Scale: {target_info['scale']}

EXTRACTED QUOTE INFORMATION:
- Manufacturer: {quote_info['manufacturer']}
- Model Name: {quote_info['model_name']}
- Scale: {quote_info['scale']}
- Title: {quote_info['title']}
- Price: {quote_info['price']} {quote_info['currency']}

ANALYSIS INSTRUCTIONS:
1. Determine if the extracted quote is for the SAME or VERY SIMILAR diecast model car as the target
2. Consider manufacturer variations (e.g., "Hot Wheels" vs "Hotwheels", "BMW" variations)
3. Consider model name variations and partial matches
4. Consider scale compatibility (1:18 vs 1/18, missing scale info)
5. Use the title as additional context when structured data is incomplete
6. Be reasonably permissive for legitimate variations but reject clearly different models

IMPORTANT EXAMPLES:
- BMW R69S vs Honda RC213V = DIFFERENT (reject)
- Vespa 90ss vs Vespa Sprint = SIMILAR (accept if same brand)
- Hot Wheels Ferrari vs Hotwheels Ferrari = SAME (accept)
- Missing manufacturer but matching model in title = ACCEPT
- Completely unrelated model cars = REJECT

Respond with a JSON object containing:
{
    "is_relevant": boolean,
    "confidence": float (0.0 to 1.0),
    "reasoning": "Brief explanation of your decision"
}

Be decisive and provide clear reasoning. Focus on whether this quote would be useful for pricing the target car.
"""
        return prompt.strip()
    
    def _generate_cache_key(self, target_info: Dict, quote_info: Dict) -> str:
        """Generate a cache key for the validation request."""
        # Create a hash of the target and quote info for caching
        data_str = json.dumps({
            'target': target_info,
            'quote': {k: v for k, v in quote_info.items() if k != 'price'}  # Exclude price from cache key
        }, sort_keys=True)
        return f"agentic_validation_{hashlib.md5(data_str.encode()).hexdigest()}"
    
    def _call_gemini_api_with_retry(self, prompt: str, max_retries: int = 3) -> str:
        """Call Gemini API with rate limiting and retry logic."""
        for attempt in range(max_retries):
            try:
                # Rate limiting
                current_time = time.time()
                time_since_last = current_time - self.last_request_time
                if time_since_last < self.min_request_interval:
                    sleep_time = self.min_request_interval - time_since_last
                    pass
                    time.sleep(sleep_time)
                
                self.last_request_time = time.time()
                
                # Make API call
                response = self._call_gemini_api(prompt)
                return response
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Too Many Requests
                    wait_time = (2 ** attempt) * 2  # Exponential backoff: 2, 4, 8 seconds
                    pass
                    if attempt < max_retries - 1:
                        time.sleep(wait_time)
                        continue
                    else:
                        raise Exception(f"Rate limit exceeded after {max_retries} attempts")
                else:
                    raise e
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff for other errors
                    pass
                    time.sleep(wait_time)
                    continue
                else:
                    raise e
        
        raise Exception(f"Failed to call Gemini API after {max_retries} attempts")
    
    def _call_gemini_api(self, prompt: str) -> str:
        """Call Gemini API with the validation prompt."""
        params = {"key": self.api_key}
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.1,  # Low temperature for consistent decisions
                "maxOutputTokens": 500,
            }
        }
        
        response = requests.post(
            self.api_url,
            params=params,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30  # Increased timeout
        )
        response.raise_for_status()
        
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise Exception("No response from Gemini API")
        
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            raise Exception("Empty response from Gemini API")
        
        return parts[0].get("text", "").strip()
    
    def _parse_validation_response(self, response: str) -> Dict[str, Any]:
        """Parse the AI response into structured validation result."""
        try:
            # Clean response - remove markdown code blocks if present
            response_clean = response.strip()
            if response_clean.startswith('```json'):
                response_clean = response_clean[7:]
            if response_clean.endswith('```'):
                response_clean = response_clean[:-3]
            response_clean = response_clean.strip()
            
            # Parse JSON response
            result = json.loads(response_clean)
            
            # Validate required fields
            if not isinstance(result.get('is_relevant'), bool):
                raise ValueError("Missing or invalid 'is_relevant' field")
            
            confidence = result.get('confidence', 0.5)
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                confidence = 0.5
            
            reasoning = result.get('reasoning', 'No reasoning provided')
            if not isinstance(reasoning, str):
                reasoning = str(reasoning)
            
            return {
                'is_relevant': result['is_relevant'],
                'confidence': float(confidence),
                'reasoning': reasoning
            }
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            pass
            
            # Fallback parsing - look for key indicators in text
            response_lower = response.lower()
            if 'true' in response_lower and 'relevant' in response_lower:
                is_relevant = True
            elif 'false' in response_lower or 'not relevant' in response_lower:
                is_relevant = False
            else:
                is_relevant = True  # Default to permissive
            
            return {
                'is_relevant': is_relevant,
                'confidence': 0.5,
                'reasoning': f'Fallback parsing due to parse error: {str(e)}'
            }


def get_agentic_validator() -> Optional[AgenticQuoteValidator]:
    """Get an instance of the agentic validator if API key is available."""
    api_key = getattr(settings, 'GEMINI_API_KEY', None)
    if not api_key:
        logger.warning("No Gemini API key available for agentic validation")
        return None
    return AgenticQuoteValidator(api_key)
