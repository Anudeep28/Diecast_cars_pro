#!/usr/bin/env python3
"""
Test script for the new portfolio calculation functionality.
This script tests the updated CalculatePortfolioView that uses existing market data
instead of re-fetching.
"""

import os
import sys
import django
from django.conf import settings

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'diecastcollector.settings')
django.setup()

from django.contrib.auth.models import User
from django.test import RequestFactory
from django.http import JsonResponse
from inventory.models import DiecastCar, MarketPrice
from inventory.api_views import CalculatePortfolioView
import asyncio
from decimal import Decimal
from django.utils import timezone

async def test_portfolio_calculation():
    """Test the new portfolio calculation logic"""
    print("🔍 Testing Portfolio Calculation...")
    
    # Get the first user for testing
    try:
        from asgiref.sync import sync_to_async
        
        # Find a user who has cars
        def get_user_with_cars():
            from django.db.models import Count
            return User.objects.annotate(car_count=Count('diecast_cars')).filter(car_count__gt=0).first()
        
        user = await sync_to_async(get_user_with_cars)()
        if not user:
            print("❌ No users with cars found in database")
            # Try any user as fallback
            user = await sync_to_async(User.objects.first)()
            if not user:
                print("❌ No users found in database at all")
                return
            
        print(f"✅ Testing with user: {user.username}")
        
        # Get cars for this user
        cars = await sync_to_async(list)(DiecastCar.objects.filter(user=user))
        print(f"📊 Found {len(cars)} cars for user")
        
        if not cars:
            print("❌ No cars found for user - testing empty portfolio response")
            # Continue to test the API response even with no cars
        
        # Show current data state (only if cars exist)
        if cars:
            print("\n📋 Current car data:")
            for car in cars[:5]:  # Show first 5 cars
                def get_latest_market(car_id):
                    return MarketPrice.objects.filter(car_id=car_id, currency='INR').order_by('-fetched_at').first()
                
                latest_market = await sync_to_async(get_latest_market)(car.id)
                if latest_market:
                    print(f"  🚗 {car.model_name}: Market ₹{latest_market.price} ({latest_market.marketplace})")
                else:
                    purchase_price = car.price if car.price else 0
                    print(f"  🚗 {car.model_name}: Purchase ₹{purchase_price} (no market data)")
            
            if len(cars) > 5:
                print(f"  ... and {len(cars) - 5} more cars")
        
        # Create a test request
        factory = RequestFactory()
        request = factory.get('/api/portfolio/calculate_valuation/')
        request.user = user
        
        # Test the new portfolio view
        print(f"\n🧮 Calculating portfolio value...")
        view = CalculatePortfolioView()
        response = await view.get(request)
        
        if isinstance(response, JsonResponse):
            import json
            data = json.loads(response.content.decode())
            
            print(f"\n✅ Portfolio calculation successful!")
            print(f"💰 Total Portfolio Value: ₹{data['total_portfolio_value_inr']}")
            print(f"📈 Cars with market data: {data['cars_with_market_data']}")
            print(f"🛒 Cars using purchase price: {data['cars_with_purchase_price']}")
            print(f"❓ Cars without any price: {data['cars_without_any_price']}")
            print(f"📊 Total cars: {data['total_cars']}")
            
            # Show breakdown for first few cars
            if data.get('results'):
                print(f"\n📋 Sample breakdown:")
                for item in data['results'][:3]:
                    print(f"  🚗 {item['model_name']}: ₹{item['value_inr']} ({item['value_source']})")
                
                if len(data['results']) > 3:
                    print(f"  ... and {len(data['results']) - 3} more cars")
        else:
            print(f"❌ Unexpected response type: {type(response)}")
            
    except Exception as e:
        print(f"❌ Error during test: {str(e)}")
        import traceback
        traceback.print_exc()

def main():
    """Main test function"""
    print("🧪 Testing New Portfolio Calculation Feature")
    print("=" * 50)
    
    # Check if we're in the right environment
    try:
        # Check if myenv is activated
        if 'myenv' not in sys.executable:
            print("⚠️  Virtual environment 'myenv' is not activated")
            print("Please activate it first: myenv\\Scripts\\activate")
            return
        else:
            print("✅ Virtual environment 'myenv' is active")
            
        # Run the async test
        asyncio.run(test_portfolio_calculation())
        
        print("\n" + "=" * 50)
        print("🎉 Test completed!")
        print("\n💡 Key improvements:")
        print("   - No market data re-fetching")
        print("   - Uses existing market prices when available")
        print("   - Falls back to purchase prices")
        print("   - Instant calculation (no API calls)")
        
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
