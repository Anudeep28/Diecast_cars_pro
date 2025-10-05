"""
Management command to send delivery alert emails to users
Can be scheduled as a daily cron job or Windows Task Scheduler task
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from inventory.notification_utils import send_delivery_alert_email, get_users_with_alerts
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send delivery alert emails to users with overdue or upcoming deliveries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending emails',
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Send alert to specific user by username',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        specific_user = options.get('user')
        
        self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
        self.stdout.write(self.style.SUCCESS("🚗 Delivery Alert Email Service"))
        self.stdout.write(self.style.SUCCESS(f"{'='*60}"))
        self.stdout.write(f"Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\n⚠️  DRY RUN MODE - No emails will be sent"))
        
        try:
            if specific_user:
                # Send to specific user
                from django.contrib.auth.models import User
                try:
                    user = User.objects.get(username=specific_user)
                    users = [user]
                    self.stdout.write(f"\n📧 Sending alert to specific user: {specific_user}")
                except User.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"\n❌ User '{specific_user}' not found"))
                    return
            else:
                # Get all users with alerts
                users = get_users_with_alerts()
                self.stdout.write(f"\n📊 Found {users.count()} user(s) with delivery alerts")
            
            if not users:
                self.stdout.write(self.style.WARNING("\n✓ No users with delivery alerts"))
                return
            
            # Send emails
            sent_count = 0
            failed_count = 0
            skipped_count = 0
            
            for user in users:
                if not user.email:
                    self.stdout.write(self.style.WARNING(f"  ⚠️  {user.username}: No email address"))
                    skipped_count += 1
                    continue
                
                if dry_run:
                    self.stdout.write(f"  🔍 Would send to: {user.username} ({user.email})")
                    sent_count += 1
                else:
                    success = send_delivery_alert_email(user)
                    if success:
                        self.stdout.write(self.style.SUCCESS(f"  ✓ Sent to: {user.username} ({user.email})"))
                        sent_count += 1
                    else:
                        self.stdout.write(self.style.ERROR(f"  ✗ Failed: {user.username} ({user.email})"))
                        failed_count += 1
            
            # Summary
            self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
            self.stdout.write(self.style.SUCCESS("📈 Summary"))
            self.stdout.write(self.style.SUCCESS(f"{'='*60}"))
            
            if dry_run:
                self.stdout.write(f"Would send: {sent_count}")
            else:
                self.stdout.write(f"✓ Successfully sent: {sent_count}")
                if failed_count > 0:
                    self.stdout.write(self.style.ERROR(f"✗ Failed: {failed_count}"))
                if skipped_count > 0:
                    self.stdout.write(self.style.WARNING(f"⚠️  Skipped (no email): {skipped_count}"))
            
            self.stdout.write(self.style.SUCCESS(f"\n✅ Delivery alert process completed"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Error: {str(e)}"))
            logger.error(f"Delivery alert command failed: {str(e)}", exc_info=True)
            raise
