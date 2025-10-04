"""
Management command to cleanup incomplete registrations (users who verified email but never paid).
This prevents database bloat from abandoned registrations.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from inventory.models import EmailVerificationToken, Subscription


class Command(BaseCommand):
    help = 'Cleanup incomplete registrations older than 7 days'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Delete incomplete registrations older than this many days (default: 7)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        cutoff_date = timezone.now() - timedelta(days=days)
        
        self.stdout.write(f"Looking for incomplete registrations older than {days} days...")
        
        # Find users who:
        # 1. Are not active (is_active=False)
        # 2. Have no subscription
        # 3. Have verified email tokens older than cutoff date
        
        incomplete_users = []
        
        for user in User.objects.filter(is_active=False):
            # Check if user has no subscription
            try:
                subscription = user.subscription
                continue  # Skip if user has subscription
            except Subscription.DoesNotExist:
                pass
            
            # Check if user has old verification token
            try:
                verification = user.email_verification
                if verification.created_at < cutoff_date:
                    incomplete_users.append({
                        'user': user,
                        'email': user.email,
                        'username': user.username,
                        'created': verification.created_at,
                        'email_verified': verification.email_verified
                    })
            except EmailVerificationToken.DoesNotExist:
                # User without verification token, check user creation date
                if user.date_joined < cutoff_date:
                    incomplete_users.append({
                        'user': user,
                        'email': user.email,
                        'username': user.username,
                        'created': user.date_joined,
                        'email_verified': False
                    })
        
        if not incomplete_users:
            self.stdout.write(self.style.SUCCESS('No incomplete registrations found.'))
            return
        
        self.stdout.write(f"\nFound {len(incomplete_users)} incomplete registration(s):")
        
        for item in incomplete_users:
            status = "✓ Verified" if item['email_verified'] else "✗ Not verified"
            self.stdout.write(
                f"  - {item['username']} ({item['email']}) - "
                f"Created: {item['created'].strftime('%Y-%m-%d %H:%M')} - {status}"
            )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n[DRY RUN] No users were deleted.'))
            self.stdout.write('Run without --dry-run to actually delete these users.')
        else:
            confirm = input('\nDo you want to delete these users? (yes/no): ')
            if confirm.lower() == 'yes':
                deleted_count = 0
                for item in incomplete_users:
                    user = item['user']
                    username = user.username
                    user.delete()  # This will cascade delete EmailVerificationToken
                    deleted_count += 1
                    self.stdout.write(f"  Deleted: {username}")
                
                self.stdout.write(
                    self.style.SUCCESS(f'\n✓ Successfully deleted {deleted_count} incomplete registration(s).')
                )
            else:
                self.stdout.write(self.style.WARNING('Deletion cancelled.'))
