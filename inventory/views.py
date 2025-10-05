from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.db.models import Sum, Avg, Count, Case, When, F
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from datetime import timedelta, datetime
import json
import csv
from .models import DiecastCar, Subscription, MarketPrice, EmailVerificationToken
from .forms import DiecastCarForm, FeedbackForm, UserRegistrationForm, SubscriptionForm
from .razorpay_client import RazorpayClient

# Landing page view
def landing_page(request):
    """Landing page for non-authenticated users showcasing app features"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    context = {
        'subscription_price': settings.SUBSCRIPTION_AMOUNT / 100,  # Convert from paise to rupees
        'title': 'Welcome to DiecastCollector Pro'
    }
    return render(request, 'inventory/landing.html', context)

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

    # Market value metrics - Calculate portfolio value using latest batch averages
    # For cars without market data, use purchase price as fallback
    market_current_total = 0
    market_previous_total = 0
    purchase_portfolio_value = 0
    cars_with_market_data = 0
    cars_without_market_data = 0
    rarity_alerts = []
    top_price_changes = []
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    for car in all_cars:
        # Add to purchase portfolio value
        if car.price and float(car.price) > 0:
            purchase_portfolio_value += float(car.price)
        
        latest = MarketPrice.objects.filter(car=car).order_by('-fetched_at').first()
        if latest:
            # Calculate average from latest batch (matching car_detail logic)
            batch_qs = MarketPrice.objects.filter(car=car, fetched_at=latest.fetched_at)
            batch_avg = batch_qs.aggregate(avg=Avg('price'))['avg']
            
            if batch_avg:
                market_current_total += float(batch_avg)
                cars_with_market_data += 1
                
                # Previous batch for 30-day comparison
                prev = MarketPrice.objects.filter(car=car, fetched_at__lte=thirty_days_ago).order_by('-fetched_at').first()
                if not prev:
                    # Fallback to second latest batch
                    all_batches = MarketPrice.objects.filter(car=car).values('fetched_at').distinct().order_by('-fetched_at')[:2]
                    if len(all_batches) >= 2:
                        prev_time = all_batches[1]['fetched_at']
                        prev_batch_avg = MarketPrice.objects.filter(car=car, fetched_at=prev_time).aggregate(avg=Avg('price'))['avg']
                        if prev_batch_avg and float(prev_batch_avg) > 0:
                            market_previous_total += float(prev_batch_avg)
                elif prev:
                    prev_batch_avg = MarketPrice.objects.filter(car=car, fetched_at=prev.fetched_at).aggregate(avg=Avg('price'))['avg']
                    if prev_batch_avg and float(prev_batch_avg) > 0:
                        market_previous_total += float(prev_batch_avg)
                
                # Compute percent change vs purchase price using latest batch average
                try:
                    if car.price and float(car.price) > 0:
                        pct_vs_purchase = ((float(batch_avg) - float(car.price)) / float(car.price)) * 100.0
                        if pct_vs_purchase > 0:
                            top_price_changes.append({
                                'car': car,
                                'change_pct': round(pct_vs_purchase, 1),
                                'latest_price': batch_avg,
                            })
                except Exception:
                    pass
        else:
            # No market data available - use purchase price as fallback for portfolio valuation
            cars_without_market_data += 1
            if car.price and float(car.price) > 0:
                market_current_total += float(car.price)
    
    # Calculate portfolio gain/loss
    portfolio_gain_loss = market_current_total - purchase_portfolio_value
    portfolio_gain_loss_pct = None
    if purchase_portfolio_value > 0:
        portfolio_gain_loss_pct = round((portfolio_gain_loss / purchase_portfolio_value) * 100.0, 2)
    
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
        # Market Portfolio
        'market_current_total': market_current_total,
        'market_previous_total': market_previous_total,
        'market_change_pct': market_change_pct,
        'purchase_portfolio_value': purchase_portfolio_value,
        'portfolio_gain_loss': portfolio_gain_loss,
        'portfolio_gain_loss_pct': portfolio_gain_loss_pct,
        'cars_with_market_data': cars_with_market_data,
        'cars_without_market_data': cars_without_market_data,
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
    
    # Prepare price trend chart data (group by fetched_at timestamp and calculate averages)
    price_chart_labels = []
    price_chart_values = []
    try:
        # Get distinct fetched_at timestamps (batches)
        distinct_batches = MarketPrice.objects.filter(car=car).values('fetched_at').distinct().order_by('fetched_at')
        
        for batch in distinct_batches:
            batch_time = batch['fetched_at']
            # Calculate average for this batch
            batch_avg = MarketPrice.objects.filter(car=car, fetched_at=batch_time).aggregate(avg=Avg('price'))['avg']
            if batch_avg:
                # Format date for display (e.g., "Jan 15, 2025")
                formatted_date = batch_time.strftime('%b %d, %Y')
                price_chart_labels.append(formatted_date)
                price_chart_values.append(float(batch_avg))
    except Exception:
        pass
    
    # Convert to JSON for template
    price_chart_labels_json = json.dumps(price_chart_labels)
    price_chart_values_json = json.dumps(price_chart_values)
    
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
        'price_chart_labels_json': price_chart_labels_json,
        'price_chart_values_json': price_chart_values_json,
        'has_price_history': len(price_chart_labels) > 0,
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
    # Handle case where user with verified email but no payment tries to register again
    if request.method == 'GET':
        email = request.GET.get('email')
        if email:
            # Check if this email belongs to a user with verified email but no subscription
            try:
                user = User.objects.get(email=email, is_active=False)
                try:
                    verification = user.email_verification
                    if verification.email_verified:
                        # User has verified email but didn't complete payment
                        messages.info(request, f'Your email is already verified. Redirecting to payment...')
                        return redirect('proceed_to_payment', user_id=user.id)
                except EmailVerificationToken.DoesNotExist:
                    pass
            except User.DoesNotExist:
                pass
    
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # Set user as inactive until email is verified
            user.save()
            username = form.cleaned_data.get('username')
            
            # Create email verification token
            verification_token = EmailVerificationToken.objects.create(user=user)
            
            # Build verification URL
            verification_url = request.build_absolute_uri(
                reverse('verify_email', kwargs={'token': verification_token.token})
            )
            
            # Send verification email
            try:
                subject = 'Verify Your Email - DiecastCollector Pro'
                html_message = render_to_string('inventory/email_verification_email.html', {
                    'user': user,
                    'verification_url': verification_url,
                    'expires_hours': 24
                })
                plain_message = strip_tags(html_message)
                
                send_mail(
                    subject=subject,
                    message=plain_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    html_message=html_message,
                    fail_silently=False,
                )
                
                messages.success(request, f'Registration successful! Please check your email ({user.email}) to verify your account.')
                return redirect('email_verification_sent')
            except Exception as e:
                # If email fails, delete the user and show error
                messages.error(request, f'Failed to send verification email. Please try again. Error: {str(e)}')
                verification_token.delete()
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
            
            # Verify payment signature (REQUIRED for LIVE mode security)
            try:
                signature_verified = razorpay_client.verify_payment_signature(razorpay_payment_id, razorpay_order_id, razorpay_signature)
                if not signature_verified:
                    print("CRITICAL: Payment signature verification failed!")
                    messages.error(request, 'Payment verification failed. Please contact support if amount was deducted.')
                    return redirect('payment_failed')
                
                print(f"✓ Payment signature verified successfully for payment_id: {razorpay_payment_id}")
                
                # Get payment details to confirm status and amount
                payment_details = razorpay_client.fetch_payment_details(razorpay_payment_id)
                if not payment_details:
                    print("ERROR: Could not fetch payment details from Razorpay")
                    messages.error(request, 'Could not verify payment status. Please contact support.')
                    return redirect('payment_failed')
                
                payment_status = payment_details.get('status')
                payment_amount = payment_details.get('amount', 0)
                
                print(f"Payment details - Status: {payment_status}, Amount: {payment_amount}")
                
                # Verify payment is captured and amount is correct
                if payment_status != 'captured':
                    print(f"ERROR: Payment not captured. Status: {payment_status}")
                    messages.error(request, f'Payment status: {payment_status}. Please try again or contact support.')
                    return redirect('payment_failed')
                
                if payment_amount != settings.SUBSCRIPTION_AMOUNT:
                    print(f"WARNING: Amount mismatch! Expected: {settings.SUBSCRIPTION_AMOUNT}, Received: {payment_amount}")
                    # Continue anyway as payment is captured, but log the discrepancy
                
                print("✓ Payment fully verified - proceeding with subscription creation")
                
            except Exception as e:
                print(f"CRITICAL ERROR during payment verification: {str(e)}")
                messages.error(request, 'Payment verification error. Please contact support if amount was deducted.')
                return redirect('payment_failed')
                
            # Payment verified successfully, proceed with subscription creation
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
    # Check if user has verified email but no active subscription
    user_id = request.session.get('user_id')
    can_retry_payment = False
    user_email = None
    
    if user_id:
        try:
            user = User.objects.get(id=user_id)
            # Check if email is verified
            try:
                verification = user.email_verification
                if verification.email_verified:
                    can_retry_payment = True
                    user_email = user.email
            except EmailVerificationToken.DoesNotExist:
                pass
        except User.DoesNotExist:
            pass
    
    return render(request, 'inventory/payment_failed.html', {
        'title': 'Payment Failed - DiecastCollector Pro',
        'can_retry_payment': can_retry_payment,
        'user_id': user_id,
        'user_email': user_email
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

        context = {
            'subscription': subscription,
            'debug_info': debug_info,
            'title': 'Your Subscription - DiecastCollector Pro'
        }
        return render(request, 'inventory/subscription_details.html', context)
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


# Email verification sent page
def email_verification_sent(request):
    """Display page informing user to check their email for verification link"""
    return render(request, 'inventory/email_verification_sent.html', {
        'title': 'Verify Your Email - DiecastCollector Pro'
    })


# Email verification handler
def verify_email(request, token):
    """Handle email verification link clicked by user"""
    try:
        verification = EmailVerificationToken.objects.get(token=token)
        
        # Check if token is valid
        if not verification.is_valid:
            if verification.email_verified:
                messages.info(request, 'Your email has already been verified. You can proceed with payment.')
                # Redirect to payment page if already verified
                return redirect('proceed_to_payment', user_id=verification.user.id)
            else:
                messages.error(request, 'This verification link has expired. Please register again.')
                # Delete expired user and token
                user = verification.user
                verification.delete()
                user.delete()
                return redirect('register')
        
        # Mark email as verified
        verification.email_verified = True
        verification.save()
        
        messages.success(request, 'Email verified successfully! Please proceed with payment to activate your account.')
        
        # Store user_id in session for payment
        request.session['user_id'] = verification.user.id
        
        # Redirect to payment page
        return redirect('proceed_to_payment', user_id=verification.user.id)
        
    except EmailVerificationToken.DoesNotExist:
        messages.error(request, 'Invalid verification link. Please register again.')
        return redirect('register')


# Proceed to payment after email verification
def proceed_to_payment(request, user_id):
    """Show payment page after email verification"""
    try:
        user = User.objects.get(id=user_id)
        
        # Check if email is verified
        try:
            verification = user.email_verification
            if not verification.email_verified:
                messages.error(request, 'Please verify your email first.')
                return redirect('register')
        except EmailVerificationToken.DoesNotExist:
            messages.error(request, 'Verification token not found. Please register again.')
            return redirect('register')
        
        # Create Razorpay order for subscription payment
        razorpay_client = RazorpayClient()
        notes = {
            'username': user.username,
            'user_id': str(user.id)
        }
        order = razorpay_client.create_subscription_order(user.email, notes)
        
        if order:
            # Store the order ID in session for callback verification
            request.session['razorpay_order_id'] = order['id']
            request.session['user_id'] = user.id
            
            context = {
                'order_id': order['id'],
                'razorpay_key_id': settings.RAZORPAY_KEY_ID,
                'amount': settings.SUBSCRIPTION_AMOUNT / 100,  # Convert to rupees for display
                'currency': 'INR',
                'user_email': user.email,
                'user_name': f"{user.first_name} {user.last_name}".strip() or user.username,
                'description': 'Monthly subscription - DiecastCollector Pro',
                'callback_url': request.build_absolute_uri(reverse('subscription_callback')),
            }
            return render(request, 'inventory/payment.html', context)
        else:
            messages.error(request, 'Could not create payment order. Please try again.')
            return redirect('register')
            
    except User.DoesNotExist:
        messages.error(request, 'User not found. Please register again.')
        return redirect('register')


# Debug endpoint (staff-only): show active storage backend and sample image URLs
@login_required
def storage_debug(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        from django.conf import settings
        info = {
            'DEFAULT_FILE_STORAGE': getattr(settings, 'DEFAULT_FILE_STORAGE', None),
            'CLOUDINARY_URL_valid': bool(getattr(settings, 'CLOUDINARY_URL', '').startswith('cloudinary://')),
            'cloudinary_in_INSTALLED_APPS': 'cloudinary' in settings.INSTALLED_APPS,
            'cloudinary_storage_in_INSTALLED_APPS': 'cloudinary_storage' in settings.INSTALLED_APPS,
            'MEDIA_URL': getattr(settings, 'MEDIA_URL', None),
            'MEDIA_ROOT': str(getattr(settings, 'MEDIA_ROOT', '')),
            'DEBUG': bool(getattr(settings, 'DEBUG', None)),
        }
        samples = []
        for car in DiecastCar.objects.filter(user=request.user).order_by('-id')[:3]:
            item = {'id': car.id, 'model': car.model_name}
            if car.image:
                item['image_name'] = car.image.name
                try:
                    item['image_url'] = car.image.url
                except Exception as e:
                    item['image_url_error'] = str(e)
            samples.append(item)
        return JsonResponse({'ok': True, 'info': info, 'samples': samples})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)


# Registration status check view
def check_registration_status(request):
    """
    Allow users to check if they have an incomplete registration and complete payment.
    Useful when users forget their registration status.
    """
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        
        if not email:
            messages.error(request, 'Please enter your email address.')
            return render(request, 'inventory/check_registration.html')
        
        try:
            user = User.objects.get(email=email)
            
            # Check if user is already active with subscription
            if user.is_active:
                try:
                    subscription = user.subscription
                    if subscription.is_active:
                        messages.info(request, 'Your account is already active. You can login now.')
                        return redirect('login')
                    else:
                        messages.warning(request, 'Your subscription has expired. Please renew.')
                        return redirect('login')
                except Subscription.DoesNotExist:
                    messages.warning(request, 'Your account exists but has no active subscription.')
                    return redirect('login')
            
            # Check if email is verified but payment not completed
            try:
                verification = user.email_verification
                if verification.email_verified:
                    messages.success(request, 
                        f'Found your registration! Your email is verified. Redirecting to payment...')
                    # Set session for payment
                    request.session['user_id'] = user.id
                    return redirect('proceed_to_payment', user_id=user.id)
                else:
                    if verification.is_expired:
                        messages.error(request, 
                            'Your verification link has expired. Please register again.')
                        return redirect('register')
                    else:
                        messages.info(request, 
                            'Please check your email for the verification link.')
                        return redirect('email_verification_sent')
            except EmailVerificationToken.DoesNotExist:
                messages.error(request, 
                    'Registration found but no verification token. Please register again.')
                return redirect('register')
                
        except User.DoesNotExist:
            messages.error(request, 
                'No registration found with this email. Please register first.')
            return redirect('register')
    
    return render(request, 'inventory/check_registration.html', {
        'title': 'Check Registration Status - DiecastCollector Pro'
    })

@login_required
def export_collection_csv(request):
    """Export user's diecast collection to CSV format"""
    # Create the HttpResponse object with CSV header
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="diecast_collection_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    
    # Write header row
    writer.writerow([
        'Model Name',
        'Manufacturer',
        'Scale',
        'Price (₹)',
        'Shipping Cost (₹)',
        'Advance Payment (₹)',
        'Remaining Payment (₹)',
        'Purchase Date',
        'Delivery Due Date',
        'Delivered Date',
        'Status',
        'Seller Name',
        'Purchase Link',
        'Product Quality',
        'Packaging Quality',
        'Notes'
    ])
    
    # Get all cars for the user
    cars = DiecastCar.objects.filter(user=request.user).order_by('-purchase_date')
    
    # Write data rows
    for car in cars:
        writer.writerow([
            car.model_name,
            car.manufacturer,
            car.scale or '',
            car.price,
            car.shipping_cost,
            car.advance_payment,
            car.remaining_payment,
            car.purchase_date.strftime('%Y-%m-%d') if car.purchase_date else '',
            car.delivery_due_date.strftime('%Y-%m-%d') if car.delivery_due_date else '',
            car.delivered_date.strftime('%Y-%m-%d') if car.delivered_date else '',
            car.status,
            car.seller_name or '',
            car.purchase_link or '',
            car.product_quality or '',
            car.packaging_quality or '',
            car.notes or ''
        ])
    
    return response