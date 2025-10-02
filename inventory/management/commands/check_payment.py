from django.core.management.base import BaseCommand
from inventory.models import Subscription
from django.contrib.auth.models import User
from django.utils import timezone


class Command(BaseCommand):
    help = 'Check recent payments and subscription status'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            help='Check specific user by username',
        )

    def handle(self, *args, **options):
        username = options.get('username')
        
        if username:
            try:
                user = User.objects.get(username=username)
                self._check_user_subscription(user)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'User "{username}" not found'))
        else:
            # Show all recent subscriptions
            recent_subs = Subscription.objects.all().order_by('-start_date')[:10]
            
            if not recent_subs:
                self.stdout.write(self.style.WARNING('No subscriptions found in the database'))
                return
            
            self.stdout.write(self.style.SUCCESS(f'\nFound {recent_subs.count()} recent subscriptions:\n'))
            
            for sub in recent_subs:
                self._check_user_subscription(sub.user)
                self.stdout.write('---')

    def _check_user_subscription(self, user):
        self.stdout.write(f'\n{self.style.HTTP_INFO}User: {user.username} (ID: {user.id})}')
        self.stdout.write(f'Email: {user.email}')
        self.stdout.write(f'Active: {user.is_active}')
        
        try:
            sub = Subscription.objects.get(user=user)
            self.stdout.write(f'\n{self.style.SUCCESS("✓ Subscription Found:")}')
            self.stdout.write(f'  Payment ID: {sub.razorpay_payment_id}')
            self.stdout.write(f'  Order ID: {sub.razorpay_subscription_id}')
            self.stdout.write(f'  Start Date: {sub.start_date}')
            self.stdout.write(f'  End Date: {sub.end_date}')
            self.stdout.write(f'  Is Active: {sub.is_active}')
            self.stdout.write(f'  Is Valid: {sub.is_valid}')
            self.stdout.write(f'  Days Remaining: {sub.days_remaining}')
            
            if sub.is_valid:
                self.stdout.write(self.style.SUCCESS('  Status: ✓ ACTIVE'))
            else:
                self.stdout.write(self.style.ERROR('  Status: ✗ EXPIRED/INACTIVE'))
        except Subscription.DoesNotExist:
            self.stdout.write(self.style.ERROR('\n✗ No subscription found for this user'))
