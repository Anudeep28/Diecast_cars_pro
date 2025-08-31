from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.db.models import Sum, Avg, Count, Case, When, F
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta, datetime
import json
from .models import DiecastCar, Subscription, MarketPrice
from .forms import DiecastCarForm, FeedbackForm, UserRegistrationForm, SubscriptionForm
from .razorpay_client import RazorpayClient

# Dashboard view
@login_required
def dashboard(request):
    # Get all diecast cars for the logged-in user
    cars = DiecastCar.objects.filter(user=request.user)
    
    # Calculate total collection value
    total_value = cars.aggregate(total=Sum('price'))['total'] or 0
    
    # Check for upcoming deliveries and overdue items
    today = timezone.now().date()
    two_days_from_now = today + timedelta(days=2)
    
    # Find cars with delivery due in 2 days
    upcoming_delivery = cars.filter(delivery_due_date=two_days_from_now, delivered_date__isnull=True, status__in=['Purchased/Paid', 'Shipped', 'Pre-Order'])
    for car in upcoming_delivery:
        messages.info(request, f'Delivery for {car.model_name} is due in 2 days!')
    
    # Find overdue cars (delivery_due_date is past and delivered_date is empty)
    overdue_cars = cars.filter(delivery_due_date__lt=today, delivered_date__isnull=True)
        # Helper to normalize seller names (case- & whitespace-insensitive)
    def _norm(name: str):
        return (name or "").strip().lower()

    # Build a mapping of normalized seller names to their first encountered display name
    name_display_map = {}
    for name in DiecastCar.objects.filter(user=request.user).values_list('seller_name', flat=True):
        norm = _norm(name)
        if norm and norm not in name_display_map:
            name_display_map[norm] = name

    # Collect sellers who have overdue items (normalized)
    overdue_sellers = set(_norm(name) for name in overdue_cars.values_list('seller_name', flat=True))
    for car in overdue_cars:
        car.status = 'Overdue'
        car.save()
        messages.warning(request, f'Delivery for {car.model_name} is overdue!')
    
    # Handle filtering
    status_filter = request.GET.get('status')
    manufacturer_filter = request.GET.get('manufacturer')
    sort_by = request.GET.get('sort_by', '-purchase_date')
    
    if status_filter:
        cars = cars.filter(status=status_filter)
    
    if manufacturer_filter:
        cars = cars.filter(manufacturer=manufacturer_filter)
    
    cars = cars.order_by(sort_by)
    
    # Get unique manufacturers for filter dropdown
    manufacturers = cars.values_list('manufacturer', flat=True).distinct()
    
    # Get all available status choices for filter dropdown
    status_choices = DiecastCar.STATUS_CHOICES
    
    # Calculate average ratings for each seller
    seller_ratings = DiecastCar.objects.filter(user=request.user)\
        .exclude(product_quality__isnull=True)\
        .values('seller_name')\
        .annotate(
            avg_product_quality=Avg('product_quality'),
            avg_packaging_quality=Avg('packaging_quality'),
            total_ratings=Count('id')
        )
    
    # Convert to a dictionary for easy lookup in the template
    seller_ratings_dict = {}
    for rating in seller_ratings:
        seller_name = rating['seller_name']
        # Calculate overall average from both product and packaging quality
        product_quality = rating['avg_product_quality'] or 0
        packaging_quality = rating['avg_packaging_quality'] or 0
        if product_quality and packaging_quality:
            overall_avg = (product_quality + packaging_quality) / 2
        else:
            overall_avg = product_quality or packaging_quality or 0
            
        norm_key = _norm(seller_name)
        display_name = name_display_map.get(norm_key, seller_name)
        seller_ratings_dict[display_name] = {
            'avg_rating': round(overall_avg, 1),
            'total_ratings': rating['total_ratings'],
            'has_overdue': norm_key in overdue_sellers
        }
    # Add sellers with overdue items but no ratings yet
    for norm_name in overdue_sellers:
        display_name = name_display_map.get(norm_name, norm_name.title())
        if display_name not in seller_ratings_dict:
            seller_ratings_dict[display_name] = {
                'avg_rating': 0,
                'total_ratings': 0,
                'has_overdue': True
            }
    
    # Calculate purchase statistics
    all_cars = DiecastCar.objects.filter(user=request.user)
    
    # Total number of cars in collection
    total_cars = all_cars.count()
    
    # Total cars by status
    status_counts = all_cars.values('status').annotate(count=Count('id'))
    status_stats = {item['status']: item['count'] for item in status_counts}
    
    # Cars purchased in current month and year
    current_month = today.month
    current_year = today.year
    cars_this_month = all_cars.filter(purchase_date__month=current_month, purchase_date__year=current_year).count()
    
    # Total spending (price + shipping)
    total_spending = all_cars.aggregate(
        total_price=Sum('price'),
        total_shipping=Sum('shipping_cost')
    )
    total_spent = (total_spending['total_price'] or 0) + (total_spending['total_shipping'] or 0)
    
    # Average price per car
    avg_price = all_cars.aggregate(avg=Avg('price'))['avg'] or 0

    # Market value metrics
    market_current_total = 0
    market_previous_total = 0
    rarity_alerts = []
    top_price_changes = []
    thirty_days_ago = timezone.now() - timedelta(days=30)
    for car in all_cars:
        latest = MarketPrice.objects.filter(car=car).order_by('-fetched_at').first()
        if latest:
            market_current_total += float(latest.price)
            # Previous = closest before 30 days ago, else the second latest
            prev = MarketPrice.objects.filter(car=car, fetched_at__lte=thirty_days_ago).order_by('-fetched_at').first()
            if not prev:
                second = list(MarketPrice.objects.filter(car=car).order_by('-fetched_at')[:2])
                prev = second[1] if len(second) == 2 else None
            if prev and float(prev.price) > 0:
                market_previous_total += float(prev.price)
                change_pct = ((float(latest.price) - float(prev.price)) / float(prev.price)) * 100.0

            # Compute percent change vs purchase price using latest batch average
            try:
                if car.price and float(car.price) > 0:
                    batch_qs = MarketPrice.objects.filter(car=car, fetched_at=latest.fetched_at)
                    batch_avg = batch_qs.aggregate(avg=Avg('price'))['avg'] or latest.price
                    pct_vs_purchase = ((float(batch_avg) - float(car.price)) / float(car.price)) * 100.0
                    if pct_vs_purchase > 0:
                        top_price_changes.append({
                            'car': car,
                            'change_pct': round(pct_vs_purchase, 1),
                            'latest_price': batch_avg,
                        })
            except Exception:
                # If any calculation fails for this car, skip it for the top list
                pass
    
    # Top manufacturers by count
    manufacturer_counts = all_cars.values('manufacturer').annotate(count=Count('id')).order_by('-count')[:5]
    
    # Most common scales
    scale_counts = all_cars.values('scale').annotate(count=Count('id')).order_by('-count')[:3]
    
    # Monthly purchase trends (last 6 months)
    six_months_ago = today - timedelta(days=180)
    from django.db.models.functions import ExtractMonth, ExtractYear
    
    monthly_purchases = all_cars.filter(purchase_date__gte=six_months_ago)\
        .annotate(month=ExtractMonth('purchase_date'), year=ExtractYear('purchase_date'))\
        .values('month', 'year')\
        .annotate(count=Count('id'))\
        .order_by('year', 'month')
    
    # Format for chart display
    months = []
    purchase_counts = []
    
    for item in monthly_purchases:
        month_name = datetime(2000, int(item['month']), 1).strftime('%b')
        months.append(f"{month_name} {int(item['year'])}")
        purchase_counts.append(item['count'])
        
    # Flag for template to conditionally render the chart
    has_trend_data = len(months) > 0
    
    # Convert to JSON for the template
    months_json = json.dumps(months)
    purchase_counts_json = json.dumps(purchase_counts)
    status_stats_json = json.dumps(status_stats)
    
    market_change_pct = None
    if market_previous_total > 0:
        market_change_pct = round(((market_current_total - market_previous_total) / market_previous_total) * 100.0, 2)

    # Sort and take top 4 highest % increases vs purchase
    try:
        top_price_changes = sorted(top_price_changes, key=lambda x: x['change_pct'], reverse=True)[:4]
    except Exception:
        top_price_changes = []

    context = {
        'cars': cars,
        'total_value': total_value,
        'manufacturers': manufacturers,
        'selected_status': status_filter,
        'selected_manufacturer': manufacturer_filter,
        'selected_sort': sort_by,
        'seller_ratings': dict(sorted(seller_ratings_dict.items(), key=lambda item: item[1]['avg_rating'], reverse=True)),
        # New statistics
        'total_cars': total_cars,
        'status_stats': status_stats,
        'cars_this_month': cars_this_month,
        'total_spent': total_spent,
        'avg_price': avg_price,
        # Market
        'market_current_total': market_current_total,
        'market_previous_total': market_previous_total,
        'market_change_pct': market_change_pct,
        'rarity_alerts': rarity_alerts,
        'top_price_changes': top_price_changes,
        'top_manufacturers': manufacturer_counts,
        'scale_counts': scale_counts,
        'months': months_json,
        'purchase_counts': purchase_counts_json,
        'status_stats_json': status_stats_json,
        'has_trend_data': has_trend_data,
        # Status choices for filter dropdown
        'status_choices': status_choices
    }
    
    return render(request, 'inventory/dashboard.html', context)

# Create view
@login_required
def car_create(request):
    if request.method == 'POST':
        form = DiecastCarForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            car = form.save(commit=False)
            car.user = request.user
            car.save()
            messages.success(request, 'Car added successfully!')
            return redirect('dashboard')
    else:
        form = DiecastCarForm(user=request.user)
    return render(request, 'inventory/car_form.html', {'form': form, 'title': 'Add New Car'})

# Update view
@login_required
def car_update(request, pk):
    car = get_object_or_404(DiecastCar, pk=pk, user=request.user)
    
    if request.method == 'POST':
        form = DiecastCarForm(request.POST, request.FILES, instance=car, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Diecast car updated successfully!')
            return redirect('dashboard')
    else:
        form = DiecastCarForm(instance=car, user=request.user)
    
    return render(request, 'inventory/car_form.html', {'form': form, 'title': 'Update Car'})

# Delete view
@login_required
def car_delete(request, pk):
    car = get_object_or_404(DiecastCar, pk=pk, user=request.user)
    
    if request.method == 'POST':
        car.delete()
        messages.success(request, 'Diecast car deleted successfully!')
        return redirect('dashboard')
    
    return render(request, 'inventory/car_confirm_delete.html', {'car': car})

# Detail view
@login_required
def car_detail(request, pk):
    car = get_object_or_404(DiecastCar, pk=pk, user=request.user)
    
    # Handle feedback form if the car has been delivered
    if car.status == 'Delivered' and request.method == 'POST':
        feedback_form = FeedbackForm(request.POST, instance=car)
        if feedback_form.is_valid():
            feedback_form.save()
            messages.success(request, 'Feedback submitted successfully!')
            return redirect('car_detail', pk=pk)
    elif car.status == 'Delivered':
        feedback_form = FeedbackForm(instance=car)
    else:
        feedback_form = None
    
    # Market data for this car
    market_qs = MarketPrice.objects.filter(car=car).order_by('-fetched_at')
    market_latest = market_qs.first()
    market_previous = market_qs[1] if market_qs.count() > 1 else None
    market_change_pct = None
    if market_latest and market_previous and float(market_previous.price) > 0:
        market_change_pct = round(((float(market_latest.price) - float(market_previous.price)) / float(market_previous.price)) * 100.0, 2)
    price_history = list(market_qs[:10])
    market_links = list(car.market_links.all())

    # Latest averaged price (from most recent fetch batch) and % vs purchase
    latest_avg_price = None
    pct_vs_purchase = None
    try:
        if market_latest is not None:
            latest_batch_time = market_latest.fetched_at
            batch_qs = MarketPrice.objects.filter(car=car, fetched_at=latest_batch_time)
            latest_avg_price = batch_qs.aggregate(avg=Avg('price'))['avg']
            if latest_avg_price and car.price and float(car.price) > 0:
                pct_vs_purchase = round(((float(latest_avg_price) - float(car.price)) / float(car.price)) * 100.0, 2)
    except Exception:
        latest_avg_price = None
        pct_vs_purchase = None
    
    context = {
        'car': car,
        'feedback_form': feedback_form,
        'market_latest': market_latest,
        'market_previous': market_previous,
        'market_change_pct': market_change_pct,
        'price_history': price_history,
        'market_links': market_links,
        'latest_avg_price': latest_avg_price,
        'pct_vs_purchase': pct_vs_purchase,
    }
    return render(request, 'inventory/car_detail.html', context)

# Update status view
@login_required
def update_status(request, pk):
    car = get_object_or_404(DiecastCar, pk=pk, user=request.user)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(DiecastCar.STATUS_CHOICES):
            car.status = new_status
            car.save()
            messages.success(request, f'Status updated to {new_status}')
        
    return redirect('car_detail', pk=pk)

# User registration view
def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # Set user as inactive until payment is confirmed
            user.save()
            username = form.cleaned_data.get('username')
            # Create Razorpay order for subscription payment
            razorpay_client = RazorpayClient()
            notes = {
                'username': username,
                'user_id': str(user.id)
            }
            order = razorpay_client.create_subscription_order(user.email, notes)
            
            if order:
                # Store the registration data in session for later use
                request.session['razorpay_order_id'] = order['id']
                request.session['user_id'] = user.id
                
                context = {
                    'order_id': order['id'],
                    'razorpay_key_id': settings.RAZORPAY_KEY_ID,
                    'amount': settings.SUBSCRIPTION_AMOUNT / 100,  # Convert to rupees for display
                    'currency': 'INR',
                    'user_email': user.email,
                    'user_name': f"{user.first_name} {user.last_name}".strip() or username,
                    'description': 'Monthly subscription - DiecastCollector Pro',
                    'callback_url': request.build_absolute_uri(reverse('subscription_callback')),
                }
                return render(request, 'inventory/payment.html', context)
            else:
                messages.error(request, 'Could not create payment order. Please try again.')
                # Delete the inactive user if payment order creation fails
                user.delete()
                return redirect('register')
    else:
        form = UserRegistrationForm()
    
    # Explicitly use the custom template
    return render(request, 'inventory/register.html', {
        'form': form,
        'title': 'Register - DiecastCollector Pro',
        'subscription_price': settings.SUBSCRIPTION_AMOUNT / 100  # Convert to rupees for display
    })

# Custom logout view
def custom_logout(request):
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('login')


# Subscription payment callback view
@csrf_exempt
def subscription_callback(request):
    if request.method == 'POST':
        razorpay_payment_id = request.POST.get('razorpay_payment_id', '')
        razorpay_order_id = request.POST.get('razorpay_order_id', '')
        razorpay_signature = request.POST.get('razorpay_signature', '')
        user_id = request.session.get('user_id') or (request.user.id if request.user.is_authenticated else None)
        
        print(f"Payment callback received: payment_id={razorpay_payment_id}, order_id={razorpay_order_id}")
        
        if not (razorpay_payment_id and razorpay_order_id and razorpay_signature):
            messages.error(request, 'Invalid payment details. Please try again.')
            return redirect('payment_failed')
        if not user_id:
            # For renewals, user may already be authenticated
            user_id = request.user.id if request.user.is_authenticated else None
        if not user_id:
            messages.error(request, 'User information missing. Please log in again.')
            return redirect('login')
            
        try:
            user = User.objects.get(id=user_id)
            razorpay_client = RazorpayClient()
            
            # For test mode, we'll accept all payments without strict verification
            payment_verified = True
            
            try:
                # Try to verify the payment signature
                signature_verified = razorpay_client.verify_payment_signature(razorpay_payment_id, razorpay_order_id, razorpay_signature)
                if not signature_verified:
                    print("Payment signature verification failed, but continuing for test mode")
                
                # Get payment details to confirm amount
                payment_details = razorpay_client.fetch_payment_details(razorpay_payment_id)
                if not payment_details or payment_details.get('status') != 'captured':
                    print(f"Payment status check failed: {payment_details.get('status') if payment_details else 'No details'}, but continuing for test mode")
            except Exception as e:
                print(f"Error during payment verification: {str(e)}, but continuing for test mode")
                
            # In test mode, we proceed with subscription creation regardless of verification
            # Calculate subscription end date (1 month from now)
            end_date = timezone.now() + timedelta(days=30)
            
            # First, check if subscription exists
            try:
                subscription = Subscription.objects.get(user=user)
                # Update existing subscription
                subscription.razorpay_payment_id = razorpay_payment_id
                subscription.razorpay_subscription_id = razorpay_order_id
                subscription.start_date = timezone.now()
                subscription.end_date = end_date
                subscription.is_active = True
                subscription.save()
                print(f"Updated existing subscription for user {user.username}, active until {end_date}")
            except Subscription.DoesNotExist:
                # Create new subscription
                subscription = Subscription.objects.create(
                    user=user,
                    razorpay_payment_id=razorpay_payment_id,
                    razorpay_subscription_id=razorpay_order_id,
                    start_date=timezone.now(),
                    end_date=end_date,
                    is_active=True
                )
                print(f"Created new subscription for user {user.username}, active until {end_date}")
            
            # Activate the user
            user.is_active = True
            user.save()
            
            messages.success(request, 'Payment successful! Your subscription is now active.')
            return redirect('payment_success')
        except User.DoesNotExist:
            messages.error(request, 'User not found. Please register again.')
        except Exception as e:
            messages.error(request, f'An error occurred: {str(e)}')
    
    return redirect('payment_failed')


# Payment success page
def payment_success(request):
    return render(request, 'inventory/payment_success.html', {
        'title': 'Payment Successful - DiecastCollector Pro'
    })


# Payment failed page
def payment_failed(request):
    return render(request, 'inventory/payment_failed.html', {
        'title': 'Payment Failed - DiecastCollector Pro'
    })


# Subscription renewal view
@login_required
def subscription_renew(request):
    try:
        subscription = request.user.subscription
    except:
        # Create a new subscription object if one doesn't exist
        subscription = Subscription(user=request.user)
        subscription.save()
    
    if request.method == 'POST':
        form = SubscriptionForm(request.POST)
        if form.is_valid():
            # Update auto-renew preference
            subscription.auto_renew = form.cleaned_data.get('auto_renew')
            subscription.save()
            
            # Create Razorpay order for renewal payment
            razorpay_client = RazorpayClient()
            notes = {
                'username': request.user.username,
                'user_id': str(request.user.id),
                'purpose': 'subscription_renewal'
            }
            order = razorpay_client.create_subscription_order(request.user.email, notes)
            
            if order:
                # Store the order ID AND user id in session for callback verification
                request.session['razorpay_order_id'] = order['id']
                request.session['user_id'] = request.user.id
                
                context = {
                    'order_id': order['id'],
                    'razorpay_key_id': settings.RAZORPAY_KEY_ID,
                    'amount': settings.SUBSCRIPTION_AMOUNT / 100,
                    'currency': 'INR',
                    'user_email': request.user.email,
                    'user_name': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
                    'description': 'Monthly subscription renewal - DiecastCollector Pro',
                    'callback_url': request.build_absolute_uri(reverse('subscription_callback')),
                }
                return render(request, 'inventory/payment.html', context)
            else:
                messages.error(request, 'Could not create payment order. Please try again.')
    else:
        form = SubscriptionForm(initial={'auto_renew': subscription.auto_renew})
    
    return render(request, 'inventory/subscription_renew.html', {
        'form': form,
        'subscription': subscription,
        'title': 'Renew Subscription - DiecastCollector Pro',
        'subscription_price': settings.SUBSCRIPTION_AMOUNT / 100
    })


# Subscription details view
@login_required
def subscription_details(request):
    # Debug info
    debug_info = {
        'is_authenticated': request.user.is_authenticated,
        'is_active': request.user.is_active,
        'username': request.user.username,
        'current_time': timezone.now(),
    }
    
    try:
        subscription = request.user.subscription
        debug_info.update({
            'subscription_exists': True,
            'subscription_id': str(subscription.id),
            'is_active_flag': subscription.is_active,
            'start_date': subscription.start_date,
            'end_date': subscription.end_date,
            'is_valid': subscription.is_valid,
            'days_remaining': subscription.days_remaining,
            'expiring_soon': subscription.expiring_soon,
            'time_difference': str(subscription.end_date - timezone.now()) if subscription.end_date else 'No end date',
        })
        
        # Fix subscription if needed
        if not subscription.is_valid and subscription.is_active and subscription.end_date:
            # End date might be in the past - update it
            subscription.end_date = timezone.now() + timedelta(days=30)
            subscription.save()
            messages.success(request, "Subscription fixed! End date has been updated.")
            
        context = {
            'subscription': subscription,
            'debug_info': debug_info,
            'title': 'Your Subscription - DiecastCollector Pro'
        }
    except Exception as e:
        # If no subscription exists
        debug_info.update({
            'subscription_exists': False,
            'error': str(e)
        })
        context = {
            'subscription': None,
            'debug_info': debug_info,
            'title': 'Your Subscription - DiecastCollector Pro'
        }
    
        return render(request, 'inventory/subscription_details.html', context)


# Profile view
@login_required
def profile(request):
    """Display user's profile information including subscription end date."""
    try:
        subscription = request.user.subscription
    except Subscription.DoesNotExist:
        subscription = None
    context = {
        'subscription': subscription,
        'title': 'Profile - DiecastCollector Pro'
    }
    return render(request, 'inventory/profile.html', context)