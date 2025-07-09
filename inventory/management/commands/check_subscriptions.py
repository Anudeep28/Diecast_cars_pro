import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
from inventory.models import Subscription

class Command(BaseCommand):
    help = 'Check for expiring subscriptions and notify users'

    def handle(self, *args, **options):
        self.stdout.write('Checking for expiring subscriptions...')
        
        # Check subscriptions expiring in the next 7 days
        expiry_threshold = timezone.now() + timedelta(days=7)
        expiring_soon = Subscription.objects.filter(
            is_active=True,
            end_date__lte=expiry_threshold,
            end_date__gt=timezone.now()
        )
        
        for subscription in expiring_soon:
            user = subscription.user
            days_remaining = (subscription.end_date - timezone.now()).days
            
            self.stdout.write(f'Subscription for user {user.username} expires in {days_remaining} days')
            
            # Send email notification
            try:
                subject = f'Your DiecastCollector Pro subscription expires in {days_remaining} days'
                message = f'''Dear {user.first_name or user.username},

Your DiecastCollector Pro subscription will expire in {days_remaining} days on {subscription.end_date.strftime('%B %d, %Y')}.

To continue using all features of the application, please renew your subscription before it expires.

Click the link below to renew your subscription:
{settings.BASE_URL}/subscription/renew/

Thank you for using DiecastCollector Pro!

Best regards,
The DiecastCollector Team
'''
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )
                self.stdout.write(self.style.SUCCESS(f'Reminder email sent to {user.email}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Failed to send reminder email to {user.email}: {str(e)}'))
        
        # Check for expired subscriptions
        expired = Subscription.objects.filter(
            is_active=True,
            end_date__lte=timezone.now()
        )
        
        for subscription in expired:
            user = subscription.user
            self.stdout.write(f'Subscription for user {user.username} has expired')
            
            # Mark subscription as inactive
            subscription.is_active = False
            subscription.save()
            
            # Send expiration notification
            try:
                subject = 'Your DiecastCollector Pro subscription has expired'
                message = f'''Dear {user.first_name or user.username},

Your DiecastCollector Pro subscription has expired on {subscription.end_date.strftime('%B %d, %Y')}.

You will not be able to access the application until you renew your subscription.

Click the link below to renew your subscription:
{settings.BASE_URL}/subscription/renew/

Thank you for using DiecastCollector Pro!

Best regards,
The DiecastCollector Team
'''
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )
                self.stdout.write(self.style.SUCCESS(f'Expiration email sent to {user.email}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Failed to send expiration email to {user.email}: {str(e)}'))
        
        self.stdout.write(self.style.SUCCESS('Subscription check completed'))
