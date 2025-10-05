import re
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages
from django.utils import timezone

class SubscriptionCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Paths that don't require subscription check
        self.excluded_paths = [
            r'^/$',  # Landing page
            r'^/login/',
            r'^/logout/',
            r'^/register/',
            r'^/payment/',
            r'^/subscription/',
            r'^/admin/',
            r'^/static/',
            r'^/password-reset/',
            r'^/media/',
        ]

    def __call__(self, request):
        if not request.user.is_authenticated:
            return self.get_response(request)

        # Skip check for excluded paths
        path = request.path_info
        if any(re.match(pattern, path) for pattern in self.excluded_paths):
            return self.get_response(request)

        # Check if user has a valid subscription
        try:
            # Use a direct database query to check subscription status
            from inventory.models import Subscription
            from django.utils import timezone
            
            try:
                subscription = Subscription.objects.get(user=request.user)
                
                # Do not auto-extend subscriptions; proceed with normal checks
                if not subscription.is_active:
                    messages.error(
                        request,
                        "Your subscription is inactive. Please renew to continue using the application."
                    )
                    return redirect('subscription_renew')
                
                if subscription.end_date and subscription.end_date < timezone.now():
                    messages.error(
                        request,
                        "Your subscription has expired. Please renew to continue using the application."
                    )
                    return redirect('subscription_renew')
            except Subscription.DoesNotExist:
                # If user doesn't have a subscription yet
                messages.error(
                    request,
                    "You need an active subscription to access this application."
                )
                return redirect('subscription_renew')
        except Exception as e:
            # Log any errors but don't block access in case of system error
            print(f"Error checking subscription: {e}")
            pass

        response = self.get_response(request)
        return response
