import razorpay
from django.conf import settings
from datetime import datetime, timedelta

class RazorpayClient:
    def __init__(self):
        self.client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        
    def create_subscription_order(self, user_email, notes=None):
        """Create a one-time payment order for subscription"""
        if notes is None:
            notes = {}
            
        notes.update({
            'email': user_email,
            'purpose': 'monthly_subscription'
        })
        
        # Create one-time payment order
        data = {
            'amount': settings.SUBSCRIPTION_AMOUNT,  # amount in paise (99 INR)
            'currency': 'INR',
            'receipt': f'receipt_{datetime.now().strftime("%Y%m%d%H%M%S")}',
            'payment_capture': 1,
            'notes': notes
        }
        
        try:
            order = self.client.order.create(data=data)
            return order
        except Exception as e:
            # Handle any exceptions or errors from Razorpay
            print(f"Razorpay Order Creation Error: {str(e)}")
            return None
    
    def verify_payment_signature(self, razorpay_payment_id, razorpay_order_id, razorpay_signature):
        """Verify the payment signature to confirm payment authenticity"""
        try:
            self.client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })
            return True
        except Exception as e:
            print(f"Signature verification failed: {str(e)}")
            return False
    
    def fetch_payment_details(self, payment_id):
        """Fetch payment details from Razorpay"""
        try:
            return self.client.payment.fetch(payment_id)
        except Exception as e:
            print(f"Error fetching payment details: {str(e)}")
            return None
