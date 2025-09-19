from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import F
from datetime import timedelta, datetime
import uuid
import os

# Create your models here.

def car_image_upload_path(instance, filename):
    # Get the file extension
    ext = filename.split('.')[-1]
    # Generate a new filename using the car's model name and manufacturer
    new_filename = f"{instance.model_name}_{instance.manufacturer}_{uuid.uuid4().hex}.{ext}"
    # Return the upload path
    return os.path.join('car_images', new_filename)
class DiecastCar(models.Model):
    STATUS_CHOICES = [
        ('Purchased/Paid', 'Purchased/Paid'),
        ('Shipped', 'Shipped'),
        ('Delivered', 'Delivered'),
        ('Overdue', 'Overdue'),
        ('Pre-Order', 'Pre-Order'),
        ('Commented Sold', 'Commented Sold'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='diecast_cars')
    model_name = models.CharField(max_length=200)
    manufacturer = models.CharField(max_length=100)
    scale = models.CharField(max_length=20, default='1:43')
    purchase_date = models.DateField(default=timezone.now)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    advance_payment = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    remaining_payment = models.DecimalField(max_digits=10, decimal_places=2, default=0, editable=False)
    seller_name = models.CharField(max_length=200, default='Unknown Seller')
    seller_info = models.TextField()
    contact_mobile = models.CharField(max_length=20, blank=True, null=True)
    website_url = models.URLField(max_length=500, blank=True, null=True, help_text='Facebook page, website URL or other website')
    facebook_page = models.CharField(max_length=500, blank=True, null=True)
    delivery_due_date = models.DateField()
    delivered_date = models.DateField(blank=True, null=True)
    tracking_id = models.CharField(max_length=100, blank=True, null=True, help_text='Shipping tracking number')
    delivery_service = models.CharField(max_length=100, blank=True, null=True, help_text='Delivery service provider name')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Purchased/Paid')
    feedback_notes = models.TextField(blank=True, null=True)
    
    # Feedback fields
    packaging_quality = models.IntegerField(choices=[(i, i) for i in range(1, 6)], null=True, blank=True)
    product_quality = models.IntegerField(choices=[(i, i) for i in range(1, 6)], null=True, blank=True)
    
    # Image field
    image = models.ImageField(upload_to=car_image_upload_path, null=True, blank=True, help_text='Upload an image of your model car')
    
    def save(self, *args, **kwargs):
        # Auto-calculate remaining payment
        self.remaining_payment = self.price + self.shipping_cost - self.advance_payment
        
        # Auto-update status based on payment and delivery due date
        today = timezone.now().date()
        
        # If delivered_date is set, update status to 'Delivered'
        if self.delivered_date is not None:
            self.status = 'Delivered'
            # Skip other status checks if the car is delivered
        # Otherwise, set status based on advance payment and delivery date
        elif self.advance_payment == 0:
            # No advance payment means 'Commented Sold'
            self.status = 'Commented Sold'
        elif self.advance_payment > 0 and self.advance_payment < self.price + self.shipping_cost:
            # Partial payment means 'Pre-Order'
            self.status = 'Pre-Order'
        else:
            # Full payment or delivery date logic
            # If delivery due date is in the past and car hasn't been delivered yet
            if self.delivery_due_date < today and not self.delivered_date and self.status not in ['Delivered']:
                self.status = 'Overdue'
            # If delivery due date is in the future and current status is Overdue, reset to Purchased/Paid
            elif self.delivery_due_date >= today and self.status == 'Overdue':
                self.status = 'Purchased/Paid'
            # If status is not already set and full payment is made
            elif self.advance_payment >= self.price + self.shipping_cost and self.status not in ['Shipped', 'Delivered']:
                self.status = 'Purchased/Paid'
            
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"{self.model_name} by {self.manufacturer}"
    
    # Convenience: latest known market price across sources
    def latest_market_price(self):
        return MarketPrice.objects.filter(car=self).order_by('-fetched_at').first()
    
    class Meta:
        ordering = ['-purchase_date']


class Subscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')
    razorpay_payment_id = models.CharField(max_length=100, null=True, blank=True)
    razorpay_subscription_id = models.CharField(max_length=100, null=True, blank=True)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True)
    is_active = models.BooleanField(default=False)
    auto_renew = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s subscription"
    
    @property
    def is_valid(self):
        # Check if subscription is active and has a valid end date
        if not self.is_active:
            return False
            
        # Handle case where end_date might be None
        if not self.end_date:
            return False
            
        # Compare end_date with current time
        return self.end_date > timezone.now()
    
    @property
    def days_remaining(self):
        if not self.is_valid:
            return 0
        return (self.end_date - timezone.now()).days
    
    @property
    def expiring_soon(self):
        if not self.is_valid:
            return False
        return 0 < self.days_remaining <= 7

# Marketplace integration models
MARKETPLACE_CHOICES = [
    ('ebay', 'eBay'),
    ('hobbydb', 'hobbyDB'),
    ('diecast_auction', 'Diecast Auction'),
    ('facebook', 'Facebook'),
    ('web', 'Web Search'),
]


class CarMarketLink(models.Model):
    car = models.ForeignKey(DiecastCar, on_delete=models.CASCADE, related_name='market_links')
    marketplace = models.CharField(max_length=32, choices=MARKETPLACE_CHOICES)
    external_id = models.CharField(max_length=255, help_text='Marketplace identifier (item ID, slug, etc.)')
    url = models.URLField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.car} @ {self.marketplace}: {self.external_id}"


class MarketPrice(models.Model):
    car = models.ForeignKey(DiecastCar, on_delete=models.CASCADE, related_name='market_prices')
    marketplace = models.CharField(max_length=32, choices=MARKETPLACE_CHOICES)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=8, default='INR')
    fetched_at = models.DateTimeField(default=timezone.now, db_index=True)
    source_listing_url = models.URLField(max_length=500, blank=True, null=True)
    title = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['-fetched_at']
        indexes = [
            models.Index(fields=['car', 'marketplace', 'fetched_at']),
        ]

    def __str__(self):
        return f"{self.car} {self.marketplace} {self.price} {self.currency} @ {self.fetched_at}"


class MarketFetchCredit(models.Model):
    """
    Tracks daily market fetch usage for each user.
    Each user gets 5 credits per day that reset after 24 hours.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='market_fetch_credit')
    credits_used = models.IntegerField(default=0, help_text='Number of market fetches used today')
    last_reset_date = models.DateField(default=timezone.now, help_text='Date when credits were last reset')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    DAILY_LIMIT = 5  # Maximum fetches per day
    
    class Meta:
        verbose_name = 'Market Fetch Credit'
        verbose_name_plural = 'Market Fetch Credits'
        
    def __str__(self):
        return f"{self.user.username}: {self.credits_used}/{self.DAILY_LIMIT} used"
    
    @property
    def credits_remaining(self):
        """Return remaining credits for today"""
        self.check_and_reset_if_needed()
        return max(0, self.DAILY_LIMIT - self.credits_used)
    
    @property
    def is_exhausted(self):
        """Check if user has exhausted their daily credits"""
        return self.credits_remaining <= 0
    
    def check_and_reset_if_needed(self):
        """Reset credits if it's a new day"""
        today = timezone.now().date()
        if self.last_reset_date < today:
            self.credits_used = 0
            self.last_reset_date = today
            self.save(update_fields=['credits_used', 'last_reset_date', 'updated_at'])
    
    def consume_credit(self):
        """
        Consume one credit if available.
        Returns True if credit was consumed, False if exhausted.
        """
        self.check_and_reset_if_needed()
        if self.is_exhausted:
            return False
        
        self.credits_used += 1
        self.save(update_fields=['credits_used', 'updated_at'])
        return True
    
    @property 
    def next_reset_time(self):
        """Get the next reset time (midnight next day)"""
        tomorrow = self.last_reset_date + timedelta(days=1)
        return timezone.make_aware(
            datetime.combine(tomorrow, datetime.min.time())
        )
    
    @classmethod
    def get_or_create_for_user(cls, user):
        """Get or create credit tracker for user"""
        credit, created = cls.objects.get_or_create(
            user=user,
            defaults={'credits_used': 0, 'last_reset_date': timezone.now().date()}
        )
        if not created:
            credit.check_and_reset_if_needed()
        return credit
