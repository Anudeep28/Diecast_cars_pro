import razorpay
import os
from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    help = 'Setup Razorpay subscription plan'
    
    def handle(self, *args, **kwargs):
        razorpay_key_id = settings.RAZORPAY_KEY_ID
        razorpay_key_secret = settings.RAZORPAY_KEY_SECRET
        
        if not razorpay_key_id or not razorpay_key_secret:
            self.stderr.write(self.style.ERROR('Razorpay credentials not found in settings'))
            return
            
        client = razorpay.Client(auth=(razorpay_key_id, razorpay_key_secret))
        
        try:
            # Check if plan already exists
            try:
                plans = client.plan.all()
                for plan in plans['items']:
                    if plan['item']['name'] == 'Monthly Subscription':
                        self.stdout.write(self.style.SUCCESS(
                            f"Plan already exists with ID: {plan['id']}"
                        ))
                        self.stdout.write("Add this plan ID to settings.py as RAZORPAY_SUBSCRIPTION_PLAN_ID")
                        return
            except Exception as e:
                self.stdout.write(f"Could not check existing plans: {str(e)}")
                
            # Create a new plan
            plan_data = {
                'period': 'monthly',
                'interval': 1,
                'item': {
                    'name': 'Monthly Subscription',
                    'description': 'Monthly subscription for DiecastCollector Pro',
                    'amount': settings.SUBSCRIPTION_AMOUNT,
                    'currency': 'INR'
                }
            }
            
            plan = client.plan.create(data=plan_data)
            
            if plan and 'id' in plan:
                self.stdout.write(self.style.SUCCESS(f"Plan created successfully with ID: {plan['id']}"))
                self.stdout.write("Add this plan ID to settings.py as RAZORPAY_SUBSCRIPTION_PLAN_ID")
            else:
                self.stdout.write(self.style.ERROR("Failed to create plan"))
                
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error creating Razorpay plan: {str(e)}"))
