from django.utils import timezone
from .models import DiecastCar

def overdue_notification(request):
    """
    Context processor to add overdue count to all templates
    """
    context = {
        'overdue_count': 0
    }
    
    if request.user.is_authenticated:
        today = timezone.now().date()
        # Count overdue cars
        context['overdue_count'] = DiecastCar.objects.filter(
            user=request.user,
            delivery_due_date__lt=today,
            delivered_date__isnull=True,
            status__in=['Purchased/Paid', 'Shipped', 'Overdue']
        ).count()
    
    return context
