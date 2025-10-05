"""
Notification utilities for sending email alerts to users
"""
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.utils import timezone
from django.contrib.sites.shortcuts import get_current_site
from datetime import timedelta
import logging

from .models import DiecastCar, NotificationPreferences

logger = logging.getLogger(__name__)


def send_delivery_alert_email(user, request=None):
    """
    Send delivery alert email to user with overdue and upcoming items
    
    Args:
        user: User object
        request: Optional request object for building absolute URLs
        
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    try:
        # Check user preferences
        prefs = NotificationPreferences.get_or_create_for_user(user)
        
        # Skip if user has disabled email alerts
        if not prefs.email_overdue_alerts and not prefs.email_upcoming_alerts:
            logger.info(f"Email alerts disabled for user {user.username}")
            return False
        
        today = timezone.now().date()
        alert_days = prefs.alert_days_before_delivery
        upcoming_date = today + timedelta(days=alert_days)
        
        # Get overdue cars
        overdue_cars = DiecastCar.objects.filter(
            user=user,
            delivery_due_date__lt=today,
            delivered_date__isnull=True,
            status__in=['Purchased/Paid', 'Shipped', 'Overdue']
        ).order_by('delivery_due_date')
        
        # Get upcoming deliveries (based on user preference)
        upcoming_cars = DiecastCar.objects.filter(
            user=user,
            delivery_due_date__gte=today,
            delivery_due_date__lte=upcoming_date,
            delivered_date__isnull=True,
            status__in=['Purchased/Paid', 'Shipped', 'Pre-Order']
        ).order_by('delivery_due_date')
        
        # Filter based on user preferences
        if not prefs.email_overdue_alerts:
            overdue_cars = DiecastCar.objects.none()
        if not prefs.email_upcoming_alerts:
            upcoming_cars = DiecastCar.objects.none()
        
        # Skip if no alerts
        if not overdue_cars.exists() and not upcoming_cars.exists():
            logger.info(f"No delivery alerts for user {user.username}")
            return False
        
        # Build dashboard URL
        if request:
            domain = get_current_site(request).domain
            protocol = 'https' if request.is_secure() else 'http'
            dashboard_url = f"{protocol}://{domain}/dashboard/"
        else:
            # Fallback to settings or local
            dashboard_url = "http://localhost:8000/dashboard/"
        
        # Prepare context for email templates
        context = {
            'user': user,
            'overdue_cars': list(overdue_cars),
            'upcoming_cars': list(upcoming_cars),
            'overdue_count': overdue_cars.count(),
            'upcoming_count': upcoming_cars.count(),
            'dashboard_url': dashboard_url,
        }
        
        # Render email templates
        html_content = render_to_string('inventory/emails/delivery_alert_email.html', context)
        text_content = render_to_string('inventory/emails/delivery_alert_email.txt', context)
        
        # Create email subject
        subject = f"🚗 Delivery Alert: {overdue_cars.count()} Overdue"
        if upcoming_cars.count() > 0:
            subject += f", {upcoming_cars.count()} Upcoming"
        
        # Create email message
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        email.attach_alternative(html_content, "text/html")
        
        # Send email
        email.send(fail_silently=False)
        logger.info(f"Delivery alert email sent to {user.email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send delivery alert email to {user.email}: {str(e)}")
        return False


def send_immediate_overdue_alert(user, car, request=None):
    """
    Send immediate alert when a car becomes overdue
    
    Args:
        user: User object
        car: DiecastCar object that just became overdue
        request: Optional request object
        
    Returns:
        bool: True if email was sent successfully
    """
    try:
        # Build dashboard URL
        if request:
            domain = get_current_site(request).domain
            protocol = 'https' if request.is_secure() else 'http'
            dashboard_url = f"{protocol}://{domain}/dashboard/"
        else:
            dashboard_url = "http://localhost:8000/dashboard/"
        
        context = {
            'user': user,
            'overdue_cars': [car],
            'upcoming_cars': [],
            'overdue_count': 1,
            'upcoming_count': 0,
            'dashboard_url': dashboard_url,
        }
        
        # Render email templates
        html_content = render_to_string('inventory/emails/delivery_alert_email.html', context)
        text_content = render_to_string('inventory/emails/delivery_alert_email.txt', context)
        
        subject = f"⚠️ Overdue Alert: {car.model_name}"
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)
        
        logger.info(f"Immediate overdue alert sent to {user.email} for {car.model_name}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send immediate overdue alert: {str(e)}")
        return False


def get_users_with_alerts():
    """
    Get all users who have delivery alerts (overdue or upcoming)
    
    Returns:
        QuerySet: Users with delivery alerts
    """
    from django.contrib.auth.models import User
    
    today = timezone.now().date()
    three_days_from_now = today + timedelta(days=3)
    
    # Get users with overdue or upcoming deliveries
    users_with_overdue = DiecastCar.objects.filter(
        delivery_due_date__lt=today,
        delivered_date__isnull=True,
        status__in=['Purchased/Paid', 'Shipped', 'Overdue']
    ).values_list('user', flat=True).distinct()
    
    users_with_upcoming = DiecastCar.objects.filter(
        delivery_due_date__gte=today,
        delivery_due_date__lte=three_days_from_now,
        delivered_date__isnull=True,
        status__in=['Purchased/Paid', 'Shipped', 'Pre-Order']
    ).values_list('user', flat=True).distinct()
    
    # Combine and get unique user IDs
    user_ids = set(users_with_overdue) | set(users_with_upcoming)
    
    return User.objects.filter(id__in=user_ids, email__isnull=False).exclude(email='')
