from django.utils import timezone
from datetime import timedelta
from .models import DiecastCar, Subscription

def overdue_notification(request):
    """
    Context processor to add detailed notification data to all templates
    """
    context = {
        'overdue_count': 0,
        'upcoming_count': 0,
        'overdue_cars': [],
        'upcoming_cars': [],
        'total_alerts': 0,
        'subscription_expiring': False,
        'subscription_days_remaining': 0
    }
    
    if request.user.is_authenticated:
        today = timezone.now().date()
        three_days_from_now = today + timedelta(days=3)
        
        # Get overdue cars
        overdue_cars = DiecastCar.objects.filter(
            user=request.user,
            delivery_due_date__lt=today,
            delivered_date__isnull=True,
            status__in=['Purchased/Paid', 'Shipped', 'Overdue']
        ).order_by('delivery_due_date')[:5]  # Limit to 5 for display
        
        # Get upcoming deliveries (next 3 days)
        upcoming_cars = DiecastCar.objects.filter(
            user=request.user,
            delivery_due_date__gte=today,
            delivery_due_date__lte=three_days_from_now,
            delivered_date__isnull=True,
            status__in=['Purchased/Paid', 'Shipped', 'Pre-Order']
        ).order_by('delivery_due_date')[:5]  # Limit to 5 for display
        
        # Check subscription expiration
        subscription_expiring = False
        subscription_days_remaining = 0
        try:
            subscription = Subscription.objects.get(user=request.user)
            if subscription.end_date and 0 < (subscription.end_date - timezone.now()).days <= 7:
                subscription_expiring = True
                subscription_days_remaining = (subscription.end_date - timezone.now()).days
        except Subscription.DoesNotExist:
            pass
        
        total_alerts = overdue_cars.count() + upcoming_cars.count()
        if subscription_expiring:
            total_alerts += 1
        
        context.update({
            'overdue_count': overdue_cars.count(),
            'upcoming_count': upcoming_cars.count(),
            'overdue_cars': list(overdue_cars),
            'upcoming_cars': list(upcoming_cars),
            'total_alerts': total_alerts,
            'subscription_expiring': subscription_expiring,
            'subscription_days_remaining': subscription_days_remaining
        })
    
    return context
