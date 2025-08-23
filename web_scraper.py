from typing import List, Optional
import asyncio
import json
from pydantic import BaseModel, Field
from crawl4ai import (
    AsyncWebCrawler,
    CrawlerRunConfig,
    BrowserConfig,
    CacheMode,
    LLMExtractionStrategy,
    DefaultMarkdownGenerator,
    BM25ContentFilter,
    LLMConfig,
)
from googlesearch import search
import time

# Define the schema for game theory examples
class GameTheoryExample(BaseModel):
    scenario: str = Field(..., description="Description of the game theory situation or problem")
    reasoning: str = Field(..., description="Step-by-step strategic analysis and thinking process")
    answer: str = Field(..., description="Final solution, equilibrium, or outcome of the scenario")

async def extract_game_theory_content(url: str, api_token: str):
    api_provider = "gemini/gemini-2.0-flash"

    browser_config = BrowserConfig(
        headless=True,
        text_mode=True,
        java_script_enabled=True
    )

    # Content filter for relevant game theory content
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
        }
    )

    # LLM Extraction Strategy
    llm_extraction_strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(provider=api_provider, api_token=api_token),
        schema=GameTheoryExample.model_json_schema(),
        extraction_type="schema",
        chunk_token_threshold=2048,
        overlap_rate=0.1,
        apply_chunking=True,
        instruction="""Given the content, extract game theory examples and structure them as follows:
        {
            "scenario": "Detailed description of the game theory situation",
            "reasoning": "Step-by-step analysis including:
                        1. Player identification
                        2. Available strategies
                        3. Payoff analysis
                        4. Strategic considerations
                        5. Key assumptions",
            "answer": "Final solution including:
                     - Nash Equilibrium (if applicable)
                     - Optimal strategies
                     - Real-world implications"
        }

        Important:
        - Focus on practical, real-world examples
        - Include numerical payoffs when present
        - Explain the strategic reasoning clearly
        - Ensure the output is a valid JSON object
        """,
        input_format="markdown.fit_markdown",
        extra_args={
            "temperature": 0.1,
            "max_tokens": 4096,
            "chunk_merge_strategy": "ordered_append",
            "stream": False,
        },
    )

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
        extraction_strategy=llm_extraction_strategy,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        try:
            result = await crawler.arun(url=url, config=crawler_config)
            print(f"\nProcessing URL: {url}")
            
            if not result.extracted_content:
                print("No content extracted from the webpage")
                return None

            content = result.extracted_content
            
            # Parse the extracted content
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    print(f"Error parsing JSON from {url}")
                    return None

            return content

        except Exception as e:
            print(f"Error processing {url}: {str(e)}")
            return None

async def process_urls(urls: List[str], api_token: str):
    results = []
    for url in urls:
        try:
            result = await extract_game_theory_content(url, api_token)
            if result:
                if isinstance(result, list):
                    results.extend(result)
                else:
                    results.append(result)
            time.sleep(2)  # Be nice to servers
        except Exception as e:
            print(f"Error processing {url}: {str(e)}")
            continue
    return results

def search_game_theory_examples(api_token: str, num_results: int = 5):
    # Search queries for game theory examples
    queries = [
        # "game theory examples for work place scenarios",
        # "game theory examples for family relationships",
        # "game theory examples for friendship",
        # "game theory examples for paying bills",
        # "game theory examples for planning decisions",
        # "game theory examples for architectural designing"
        # "game theory examples for building designs",
        # "game theory examples for construction projects",
        # "game theory examples for theatre sitting position",
        # "game theory examples for designing a consumer product",
        # "game theory examples for creating a marketing strategy",
        # "game theory examples for creating a presentation",
        # "game theory examples for cost allocation in water resources development projects",
        # "game theory examples for cost allocation in infrastructure development projects",
        # "game theory examples for cost allocation in energy production projects",
        # "game theory examples for cost allocation in transportation projects",
        # "game theory examples for cost allocation in healthcare projects",
        # "game theory examples for cost allocation in education projects",
        # "game theory application or examples for leading a team",
        # "game theory application or examples for strategies in tennis matches",
        # "game theory application or examples for strategies in chess matches",
        # "game theory application or examples for strategies in cricket matches",
        # "game theory application or examples for strategies in football matches",
        # "game theory application or examples for working in offices",
        # "game theory application or examples for interacting with colleagues",
        # "game theory application or examples for interacting with customers",
        "game theory application or examples for real life day to day scenarios",
        "game theory application or examples for maximizing profit or income",
        "game theory application or examples for driving a car",
        "game theory application or examples for farming",
        "game theory application or examples for handling animals",
        "game theory application or examples for providing a reply" 
    ]
    
    all_urls = []
    for query in queries:
        print(f"\nSearching for: {query}")
        try:
            # Get URLs from Google search
            search_results = list(search(query, num_results=num_results))
            all_urls.extend(search_results)
            time.sleep(2)  # Be nice to search engines
        except Exception as e:
            print(f"Error in search: {str(e)}")
            continue

    # Remove duplicates while preserving order
    all_urls = list(dict.fromkeys(all_urls))
    
    # Process all URLs
    results = asyncio.run(process_urls(all_urls, api_token))
    
    # Save results to JSON file
    with open('game_theory_solutions_7.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
    
    print(f"\nSuccessfully saved {len(results)} game theory examples to game_theory_solutions.json")

if __name__ == "__main__":
    API_TOKEN = "AIzaSyBbLj-Ynb8Qkte-GKBdY0Zgd-lujMWjq2w"  # Your Gemini API key
    search_game_theory_examples(API_TOKEN)
