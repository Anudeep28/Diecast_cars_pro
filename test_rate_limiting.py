#!/usr/bin/env python3
"""
Test script for market fetch rate limiting functionality.
Tests the daily limit of 5 market fetches per user.
"""

import os
import sys
import django
from datetime import date

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'diecastcollector.settings')
django.setup()

from django.contrib.auth.models import User
from inventory.models import DiecastCar, MarketFetchCredit


def test_rate_limiting():
    """Test the rate limiting functionality"""
    
    print("🧪 Testing Market Fetch Rate Limiting")
    print("=" * 50)
    
    # Get or create test user
    test_user, created = User.objects.get_or_create(
        username='testuser',
        defaults={
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User'
        }
    )
    
    if created:
        test_user.set_password('testpass123')
        test_user.save()
        print(f"✅ Created test user: {test_user.username}")
    else:
        print(f"✅ Using existing test user: {test_user.username}")
    
    # Get or create MarketFetchCredit for user
    credit = MarketFetchCredit.get_or_create_for_user(test_user)
    print(f"📊 Initial credit status:")
    print(f"   - Credits used: {credit.credits_used}/{credit.DAILY_LIMIT}")
    print(f"   - Credits remaining: {credit.credits_remaining}")
    print(f"   - Is exhausted: {credit.is_exhausted}")
    print(f"   - Last reset date: {credit.last_reset_date}")
    
    # Test credit consumption
    print(f"\n🔄 Testing credit consumption...")
    
    for i in range(7):  # Try to consume 7 credits (should fail after 5)
        success = credit.consume_credit()
        print(f"   Attempt {i+1}: {'✅ Success' if success else '❌ Failed'} - Credits remaining: {credit.credits_remaining}")
        
        if not success:
            print(f"   🚫 Daily limit reached! Next reset: {credit.next_reset_time}")
            break
    
    # Test reset functionality by manually setting an older date
    print(f"\n🔄 Testing daily reset...")
    
    # Simulate next day
    from datetime import timedelta
    yesterday = date.today() - timedelta(days=1)
    credit.last_reset_date = yesterday
    credit.save()
    
    # Check and reset should occur automatically
    credit.check_and_reset_if_needed()
    print(f"   After simulating next day:")
    print(f"   - Credits used: {credit.credits_used}/{credit.DAILY_LIMIT}")
    print(f"   - Credits remaining: {credit.credits_remaining}")
    print(f"   - Is exhausted: {credit.is_exhausted}")
    
    # Test one more consumption after reset
    success = credit.consume_credit()
    print(f"   First consumption after reset: {'✅ Success' if success else '❌ Failed'}")
    
    print(f"\n✨ Rate limiting test completed!")


def show_all_credits():
    """Show all MarketFetchCredit records"""
    print("\n📋 All Market Fetch Credits:")
    print("-" * 50)
    
    credits = MarketFetchCredit.objects.all()
    
    if not credits:
        print("   No credit records found.")
        return
    
    for credit in credits:
        print(f"User: {credit.user.username}")
        print(f"  Credits used: {credit.credits_used}/{credit.DAILY_LIMIT}")
        print(f"  Credits remaining: {credit.credits_remaining}")
        print(f"  Last reset: {credit.last_reset_date}")
        print(f"  Is exhausted: {credit.is_exhausted}")
        print(f"  Next reset: {credit.next_reset_time}")
        print()


if __name__ == "__main__":
    try:
        test_rate_limiting()
        show_all_credits()
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
