from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db.models import Subquery, OuterRef
import json
from .models import DiecastCar, Subscription

class DiecastCarForm(forms.ModelForm):
    SCALE_CHOICES = [
        ('1:8', '1:8'),
        ('1:12', '1:12'),
        ('1:18', '1:18'),
        ('1:24', '1:24'),
        ('1:32', '1:32'),
        ('1:36', '1:36'),
        ('1:43', '1:43'),
        ('1:48', '1:48'),
        ('1:50', '1:50'),
        ('1:64', '1:64'),
        ('1:72', '1:72'),
        ('1:76', '1:76'),
        ('1:87', '1:87'),
        ('1:100', '1:100'),
        ('1:144', '1:144'),
        ('1:160', '1:160'),
        ('Other', 'Other')
    ]
    
    scale = forms.ChoiceField(choices=SCALE_CHOICES)
    
    # Custom fields with datalist options
    manufacturer = forms.CharField(max_length=100, required=True)
    seller_name = forms.CharField(max_length=200, required=True)
    
    # Fields with default values
    price = forms.DecimalField(max_digits=10, decimal_places=2, required=True, initial=0)
    shipping_cost = forms.DecimalField(max_digits=10, decimal_places=2, required=True, initial=0)
    advance_payment = forms.DecimalField(max_digits=10, decimal_places=2, required=True, initial=0)
    
    def __init__(self, *args, user=None, **kwargs):
        super(DiecastCarForm, self).__init__(*args, **kwargs)
        
        # If we have a user, get their unique manufacturers and sellers
        if user:
            # Get unique manufacturers for this user
            manufacturers = DiecastCar.objects.filter(user=user).values_list('manufacturer', flat=True).distinct().order_by('manufacturer')
            manufacturers_list = [m for m in list(manufacturers) if m]  # Filter out None/empty values
            
            # Get unique seller names for this user
            sellers = DiecastCar.objects.filter(user=user).values_list('seller_name', flat=True).distinct().order_by('seller_name')
            sellers_list = [s for s in list(sellers) if s]  # Filter out None/empty values
            
            # Store these lists in the form for template use
            self.manufacturers_list = manufacturers_list
            self.sellers_list = sellers_list
        else:
            self.manufacturers_list = []
            self.sellers_list = []
        
        # Ensure money fields have default value of 0 when they're None
        if self.instance:
            # For existing records, set default values if fields are None
            if self.instance.price is None:
                self.initial['price'] = 0
            if self.instance.shipping_cost is None:
                self.initial['shipping_cost'] = 0
            if self.instance.advance_payment is None:
                self.initial['advance_payment'] = 0
        
        # Add Bootstrap classes to all form fields
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
            
            # Add list attributes for dropdown fields
            if field_name == 'manufacturer':
                field.widget.attrs['list'] = 'manufacturers-list'
                field.widget.attrs['autocomplete'] = 'off'
            elif field_name == 'seller_name':
                field.widget.attrs['list'] = 'sellers-list'
                field.widget.attrs['autocomplete'] = 'off'
            
            # Set placeholder for money fields
            if field_name in ['price', 'shipping_cost', 'advance_payment']:
                field.widget.attrs['placeholder'] = '0.00'
    
    class Meta:
        model = DiecastCar
        fields = ['model_name', 'manufacturer', 'scale', 'price', 'shipping_cost', 'advance_payment', 'purchase_date', 'seller_name', 'seller_info', 'contact_mobile', 'website_url', 'facebook_page', 'delivery_due_date', 'delivered_date', 'tracking_id', 'delivery_service', 'status', 'image']
        widgets = {
            'purchase_date': forms.DateInput(attrs={'type': 'date'}),
            'delivery_due_date': forms.DateInput(attrs={'type': 'date'}),
            'delivered_date': forms.DateInput(attrs={'type': 'date'}),
        }

class FeedbackForm(forms.ModelForm):
    class Meta:
        model = DiecastCar
        fields = ['packaging_quality', 'product_quality', 'feedback_notes']


class SubscriptionForm(forms.Form):
    auto_renew = forms.BooleanField(
        required=False,
        initial=True,
        label="Enable automatic renewal"
    )

class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=False, help_text='Optional')
    last_name = forms.CharField(max_length=30, required=False, help_text='Optional')
    agree_subscription = forms.BooleanField(
        required=True,
        label="I agree to subscribe for the monthly plan at ₹99 per month"
    )
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2', 'agree_subscription']
    
    def clean_email(self):
        """Validate that the email is unique or belongs to an incomplete registration"""
        email = self.cleaned_data.get('email')
        existing_users = User.objects.filter(email=email)
        
        if existing_users.exists():
            user = existing_users.first()
            
            # Check if this is an incomplete registration (verified email but no subscription)
            if not user.is_active:
                try:
                    verification = user.email_verification
                    if verification.email_verified:
                        # This user has verified email but didn't complete payment
                        raise forms.ValidationError(
                            f'This email is already registered and verified. '
                            f'<a href="/register/?email={email}">Click here to complete your payment</a>.'
                        )
                except:
                    pass
            
            raise forms.ValidationError("An account with this email address already exists.")
        return email
    
    def clean_username(self):
        """Validate that the username is unique (with custom message)"""
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken. Please choose a different one.")
        return username
        
    def save(self, commit=True):
        user = super(UserRegistrationForm, self).save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.is_active = False  # User will be activated after payment
        
        if commit:
            user.save()
        return user
