from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from inventory.models import Subscription

@login_required
def fix_subscription(request):
    """
    Debug view to manually fix a user's subscription
    """
    try:
        # Try to get the user's subscription
        try:
            subscription = request.user.subscription
            
            # Update the subscription
            subscription.is_active = True
            subscription.start_date = timezone.now()
            subscription.end_date = timezone.now() + timedelta(days=30)
            subscription.save()
            
            messages.success(request, "Your subscription has been manually activated for 30 days.")
            
        except Subscription.DoesNotExist:
            # Create a new subscription if one doesn't exist
            subscription = Subscription.objects.create(
                user=request.user,
                razorpay_payment_id="manual_fix",
                razorpay_subscription_id="manual_fix",
                start_date=timezone.now(),
                end_date=timezone.now() + timedelta(days=30),
                is_active=True
            )
            messages.success(request, "A new subscription has been created and activated for 30 days.")
            
        return redirect('subscription_details')
        
    except Exception as e:
        messages.error(request, f"Error fixing subscription: {str(e)}")
        return redirect('dashboard')
