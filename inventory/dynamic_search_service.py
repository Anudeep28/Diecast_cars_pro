"""
New service for dynamically generating search queries and extracting market prices.
"""
import asyncio
import json
import logging
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig, LLMExtractionStrategy, LLMConfig
from decimal import Decimal
from googlesearch import search

from .models import DiecastCar
from .currency_utils import convert_to_inr

# Pydantic schema for price extraction
class MarketPriceInfo(BaseModel):
    price: float = Field(..., description="Product price amount (numeric)")
    currency: str = Field(..., description="Currency code or symbol, e.g., USD, INR, $, ₹")
    title: Optional[str] = Field(None, description="Page or product title")
    model_name: Optional[str] = Field(None, description="Model car name, e.g., 'Ferrari 488 GTB'")
    manufacturer: Optional[str] = Field(None, description="Brand/manufacturer, e.g., Hot Wheels, AUTOart")
    scale: Optional[str] = Field(None, description="Scale notation like '1:18' or '1/64'")
    seller: Optional[str] = Field(None, description="Seller or marketplace name")


class SearchResult(BaseModel):
    average_price_inr: Optional[Decimal] = None
    quotes: List[MarketPriceInfo] = []


class DynamicSearchService:
    def __init__(self, gemini_api_key: str):
        self.gemini_api_key = gemini_api_key
        self.logger = logging.getLogger(__name__)

    def _generate_search_queries(self, car: DiecastCar) -> List[str]:
        """Generates a list of search queries for a given car."""
        manu = (car.manufacturer or '').strip()
        model = (car.model_name or '').strip()
        scale = (car.scale or '').strip()

        base_tokens = f"{manu} {model}".strip()
        tokens_with_scale = f"{base_tokens} {scale}".strip()

        queries = [
            f'{tokens_with_scale} diecast price',
            f'{tokens_with_scale} for sale',
            f'{base_tokens} {scale} model car price',
            f'{base_tokens} price',
            f'{model} {scale} diecast',
        ]

        # Deduplicate and filter empty queries
        seen = set()
        return [q for q in queries if q and not (q in seen or seen.add(q))]

    async def search_and_extract(self, car: DiecastCar) -> SearchResult:
        """Orchestrates the search and extraction process."""
        queries = self._generate_search_queries(car)
        self.logger.info(f"Generated {len(queries)} queries for '{car.model_name}'")

        all_urls = []
        for query in queries:
            try:
                # Using googlesearch-python
                search_results = list(search(query, num_results=3))
                all_urls.extend(search_results)
            except Exception as e:
                self.logger.warning(f"Google search failed for query '{query}': {e}")
                continue

        # Get unique URLs
        unique_urls = list(dict.fromkeys(all_urls))
        self.logger.info(f"Found {len(unique_urls)} unique URLs to crawl.")

        tasks = [self._crawl_and_extract(url) for url in unique_urls[:5]]  # Limit to 5 URLs for now
        results = await asyncio.gather(*tasks)

        # Filter out None results
        extracted_data = [item for item in results if item]
        self.logger.info(f"Successfully extracted data from {len(extracted_data)} URLs.")

        return self._process_results(extracted_data)

    def _process_results(self, results: List[MarketPriceInfo]) -> SearchResult:
        """Converts prices to INR and calculates the average."""
        if not results:
            return SearchResult()

        total_price_inr = Decimal('0')
        valid_quotes = 0

        for quote in results:
            try:
                price_inr = convert_to_inr(Decimal(quote.price), quote.currency)
                if price_inr > 0:
                    total_price_inr += price_inr
                    valid_quotes += 1
            except Exception as e:
                self.logger.warning(f"Could not convert price for quote '{quote.title}': {e}")

        average_price = total_price_inr / valid_quotes if valid_quotes > 0 else None

        return SearchResult(
            average_price_inr=average_price,
            quotes=results
        )

    async def _crawl_and_extract(self, url: str) -> Optional[MarketPriceInfo]:
        """Crawl a single URL and extract market price information."""
        api_provider = "gemini/gemini-1.5-flash"

        llm_extraction_strategy = LLMExtractionStrategy(
            llm_config=LLMConfig(provider=api_provider, api_token=self.gemini_api_key),
            schema=MarketPriceInfo.model_json_schema(),
            extraction_type="schema",
            instruction=(
                "Extract details for the diecast model on this page. "
                "If multiple prices exist, choose the current selling price. "
                "Return strict JSON with all fields from the schema. "
                "If a field is unknown, set it to null."
            ),
        )

        crawler_config = CrawlerRunConfig(
            extraction_strategy=llm_extraction_strategy,
            page_timeout=60000,
            wait_until="networkidle",
        )

        browser_config = BrowserConfig(headless=True, text_mode=True)

        async with AsyncWebCrawler(config=browser_config) as crawler:
            try:
                result = await crawler.arun(url=url, config=crawler_config)
                if not result.extracted_content:
                    return None

                content = result.extracted_content
                if isinstance(content, str):
                    try:
                        data = json.loads(content)
                    except json.JSONDecodeError:
                        self.logger.error(f"Failed to parse JSON from {url}")
                        return None
                else:
                    data = content

                # Ensure data is a list and take the first item
                if isinstance(data, list) and data:
                    data = data[0]
                
                if isinstance(data, dict):
                    try:
                        # Ensure required fields are present
                        if 'price' in data and 'currency' in data:
                            return MarketPriceInfo(**data)
                        else:
                            self.logger.warning(f"Missing required fields in data from {url}: {data}")
                    except ValidationError as e:
                        self.logger.warning(f"Pydantic validation failed for {url}: {e}")

            except Exception as e:
                self.logger.error(f"Error crawling or extracting from {url}: {e}")
            
            return None
