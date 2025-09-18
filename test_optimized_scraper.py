"""
Test script for the optimized AI market scraper
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'diecastcollector.settings')
django.setup()

from inventory.models import DiecastCar
from inventory.ai_market_scraper import search_market_prices_for_car
from django.conf import settings

def test_scraper():
    """Test the optimized market scraper"""
    
    # Get Gemini API key
    api_key = os.environ.get('GEMINI_API_KEY') or settings.GEMINI_API_KEY
    if not api_key:
        print("❌ No GEMINI_API_KEY found in environment or settings")
        return
    
    print("=" * 80)
    print("🧪 TESTING OPTIMIZED AI MARKET SCRAPER")
    print("=" * 80)
    
    # Create a test car object
    class TestCar:
        def __init__(self, manufacturer, model_name, scale):
            self.manufacturer = manufacturer
            self.model_name = model_name
            self.scale = scale
    
    # Test with a popular model that should have results
    test_car = TestCar(
        manufacturer="Hot Wheels",
        model_name="Ferrari F40",
        scale="1:64"
    )
    
    print(f"\n📦 Test Car Details:")
    print(f"  Manufacturer: {test_car.manufacturer}")
    print(f"  Model: {test_car.model_name}")
    print(f"  Scale: {test_car.scale}")
    print()
    
    try:
        # Run the scraper
        items, markdown_by_url, query = search_market_prices_for_car(
            test_car, 
            api_key, 
            num_results=3
        )
        
        print(f"\n📊 Results Summary:")
        print(f"  Search Query: {query}")
        print(f"  URLs Processed: {len(markdown_by_url)}")
        print(f"  Prices Found: {len(items)}")
        
        if items:
            print(f"\n💰 Extracted Prices:")
            for i, item in enumerate(items, 1):
                print(f"\n  [{i}] Price: {item.currency} {item.price}")
                print(f"      Title: {item.title[:80] if item.title else 'N/A'}")
                print(f"      Seller: {item.seller or 'Unknown'}")
                print(f"      URL: {item.url[:80] if item.url else 'N/A'}")
                if item.manufacturer:
                    print(f"      Detected Brand: {item.manufacturer}")
                if item.scale:
                    print(f"      Detected Scale: {item.scale}")
        else:
            print("\n⚠️ No prices were extracted. This could mean:")
            print("  - All search engines are blocking requests")
            print("  - The sites crawled have anti-bot protection")
            print("  - The extraction strategy needs adjustment")
        
        print("\n✅ Test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_scraper()
