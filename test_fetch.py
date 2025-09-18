"""Test the fetch market price functionality"""
import os
import sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'diecastcollector.settings')

import django
django.setup()

from inventory.models import DiecastCar
from inventory.market_services import MarketService
from django.conf import settings

# Get a car from the database
car = DiecastCar.objects.filter(manufacturer='Ixo Altaya', model_name='BMW R69S').first()
if not car:
    car = DiecastCar.objects.first()

if car:
    print(f"Testing with: {car.manufacturer} {car.model_name}")
    print("="*80)
    
    # Test the market service
    service = MarketService()
    result = service.fetch_and_record(car, save_extracted_markdown=False, include_search_queries=True)
    
    print(f"\nResults:")
    print(f"Count: {result.get('count', 0)}")
    print(f"Query used: {result.get('search_queries', ['None'])}")
    print(f"Average price: {result.get('all_avg_price', 'N/A')}")
    
    if result.get('market_quotes'):
        for source, quotes in result['market_quotes'].items():
            print(f"\n{source} quotes: {len(quotes)}")
            for q in quotes[:2]:
                print(f"  - {q.get('currency')} {q.get('price_inr', 0):.2f}: {q.get('title', 'N/A')[:50]}")
else:
    print("No cars found in database")
