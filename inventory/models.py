from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import F
from datetime import timedelta
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
