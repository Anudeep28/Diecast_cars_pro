"""
Test script for the new agentic market search implementation
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'diecastcollector.settings')
django.setup()

from inventory.models import DiecastCar
from inventory.agentic_market_search import search_market_prices_agentic
from django.conf import settings

def test_market_search():
    # Get Gemini API key
    gemini_key = getattr(settings, 'GEMINI_API_KEY', None)
    
    if not gemini_key:
        print("❌ No GEMINI_API_KEY found in settings!")
        print("Please add GEMINI_API_KEY to your .env file")
        return
    
    print("✅ Gemini API key found")
    
    # Test with a sample car (you can modify these values)
    # Try to get a real car from database first
    try:
        car = DiecastCar.objects.first()
        if car:
            print(f"\n📦 Testing with car from database:")
            print(f"   Manufacturer: {car.manufacturer}")
            print(f"   Model: {car.model_name}")
            print(f"   Scale: {car.scale}")
        else:
            # Create a mock car object if no cars in database
            class MockCar:
                def __init__(self):
                    self.manufacturer = "Hot Wheels"
                    self.model_name = "Ferrari 488 GTB"
                    self.scale = "1:64"
            
            car = MockCar()
            print(f"\n📦 Testing with mock car:")
            print(f"   Manufacturer: {car.manufacturer}")
            print(f"   Model: {car.model_name}")
            print(f"   Scale: {car.scale}")
    except Exception as e:
        print(f"Error getting car from database: {e}")
        # Use mock car
        class MockCar:
            def __init__(self):
                self.manufacturer = "Hot Wheels"
                self.model_name = "Ferrari 488 GTB"
                self.scale = "1:64"
        
        car = MockCar()
        print(f"\n📦 Testing with mock car:")
        print(f"   Manufacturer: {car.manufacturer}")
        print(f"   Model: {car.model_name}")
        print(f"   Scale: {car.scale}")
    
    print("\n" + "="*80)
    print("Starting agentic market search...")
    print("="*80 + "\n")
    
    # Test the search
    result = search_market_prices_agentic(car, gemini_key, num_results=3)
    
    print("\n" + "="*80)
    print("SEARCH RESULTS")
    print("="*80)
    
    if result.get('success'):
        print(f"✅ Search successful!")
        print(f"Query used: {result.get('query', 'N/A')}")
        print(f"Found {result.get('count', 0)} listings\n")
        
        listings = result.get('listings', [])
        if listings:
            for i, listing in enumerate(listings, 1):
                print(f"\n📍 Listing {i}:")
                print(f"   Title: {listing.get('title', 'N/A')[:80]}")
                print(f"   Price: {listing.get('currency', 'USD')} {listing.get('price', 0):.2f}")
                print(f"   Seller: {listing.get('seller', 'Unknown')}")
                print(f"   URL: {listing.get('url', 'N/A')[:80]}")
                print(f"   Confidence: {listing.get('confidence', 0):.2f}")
            
            # Calculate average price
            prices = [l.get('price', 0) for l in listings if l.get('price', 0) > 0]
            if prices:
                avg_price = sum(prices) / len(prices)
                print(f"\n💰 Average Price: {listings[0].get('currency', 'USD')} {avg_price:.2f}")
        else:
            print("⚠️ No listings found")
    else:
        print(f"❌ Search failed: {result.get('error', 'Unknown error')}")
    
    print("\n" + "="*80)
    print("Test completed!")
    print("="*80)

if __name__ == "__main__":
    test_market_search()
