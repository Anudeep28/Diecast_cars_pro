"""
Search Logger - Utility for logging search queries, URLs, and Gemini extraction results.
"""
import os
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from django.conf import settings
from django.utils import timezone

# Configure log directory
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

class SearchLogger:
    """Logger for search queries, URLs, and extraction results"""
    
    def __init__(self, car_id: int, car_name: str):
        """Initialize logger for a specific car"""
        self.car_id = car_id
        self.car_name = car_name
        self.logs = {
            "car_id": car_id,
            "car_name": car_name,
            "timestamp": timezone.now().isoformat(),
            "queries": [],
            "results": [],
            "extracted_content": {},
            "final_prices": []
        }
        
        # Create timestamped filenames
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        self.log_filename = f"search_log_{car_id}_{timestamp}.json"
        
    def log_query(self, query: str, search_engine: str = "web"):
        """Log a search query"""
        self.logs["queries"].append({
            "query": query,
            "search_engine": search_engine,
            "timestamp": timezone.now().isoformat()
        })
        
    def log_urls(self, query: str, urls: List[str]):
        """Log URLs returned for a query"""
        query_entry = next((q for q in self.logs["queries"] if q["query"] == query), None)
        if query_entry:
            query_entry["urls"] = urls
        
    def log_extraction(self, url: str, markdown_content: str, extracted_data: Optional[Dict] = None):
        """Log markdown content and extracted data for a URL"""
        self.logs["extracted_content"][url] = {
            "markdown": markdown_content[:5000] if markdown_content else None,  # Limit size
            "extracted_data": extracted_data
        }
        
    def log_price_result(self, marketplace: str, price_item: Dict[str, Any]):
        """Log a price result that will be saved"""
        self.logs["final_prices"].append({
            "marketplace": marketplace,
            "price_details": price_item
        })
        
    def save(self):
        """Save the logs to a JSON file"""
        filepath = os.path.join(LOG_DIR, self.log_filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.logs, f, indent=2, ensure_ascii=False)
        return filepath


# Global registry of loggers by car_id
loggers = {}

def get_logger(car_id: int, car_name: str) -> SearchLogger:
    """Get or create a logger for the specified car"""
    if car_id not in loggers:
        loggers[car_id] = SearchLogger(car_id, car_name)
    return loggers[car_id]

def save_all_logs():
    """Save all active logs"""
    saved_files = []
    for car_id, logger in loggers.items():
        saved_files.append(logger.save())
    return saved_files
