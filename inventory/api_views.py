import asyncio
import json
from decimal import Decimal

from django.conf import settings
from django.http import JsonResponse, HttpResponseNotFound, HttpResponseServerError, HttpResponseForbidden, HttpResponseBadRequest
from django.views import View
from asgiref.sync import sync_to_async

from django.utils import timezone

from .models import DiecastCar, MarketPrice, MARKETPLACE_CHOICES, MarketFetchCredit
from .market_services import MarketService, convert_to_inr

class FetchMarketPriceView(View):
    async def get(self, request, car_id):
        # Check if user is authenticated
        if not request.user.is_authenticated:
            return HttpResponseForbidden("Authentication required")
            
        try:
            car = await sync_to_async(DiecastCar.objects.select_related('user').get)(pk=car_id)
        except DiecastCar.DoesNotExist:
            return HttpResponseNotFound("Car not found")
            
        # Check if car belongs to the user
        if car.user != request.user:
            return HttpResponseForbidden("You can only fetch market prices for your own cars")

        # Check rate limiting
        try:
            credit = await sync_to_async(MarketFetchCredit.get_or_create_for_user)(request.user)
        except Exception as e:
            return HttpResponseServerError(f"Error checking credits: {e}")
            
        if credit.is_exhausted:
            next_reset = credit.next_reset_time
            return JsonResponse({
                'error': 'daily_limit_exceeded',
                'message': f'Daily limit of {MarketFetchCredit.DAILY_LIMIT} market fetches exceeded. Credits will reset at {next_reset.strftime("%Y-%m-%d %H:%M:%S")}',
                'credits_remaining': 0,
                'next_reset_time': next_reset.isoformat(),
                'daily_limit': MarketFetchCredit.DAILY_LIMIT
            }, status=429)  # 429 Too Many Requests

        deepseek_api_key = getattr(settings, 'DEEPSEEK_API_KEY', None)
        if not deepseek_api_key:
            return HttpResponseServerError("DEEPSEEK_API_KEY not configured")
            
        # Consume one credit before processing
        try:
            credit_consumed = await sync_to_async(credit.consume_credit)()
            if not credit_consumed:
                return JsonResponse({
                    'error': 'daily_limit_exceeded',
                    'message': 'Daily limit exceeded',
                    'credits_remaining': 0
                }, status=429)
        except Exception as e:
            return HttpResponseServerError(f"Error consuming credit: {e}")

        service = MarketService()
        try:
            stats = await sync_to_async(service.fetch_and_record)(
                car,
                save_extracted_markdown=False,
                include_search_queries=False,
                log_search_data=True,
            )
        except Exception as e:
            return HttpResponseServerError(f"An error occurred: {e}")

        # Flatten quotes across marketplaces and stringify Decimals
        quotes = []
        for source, items in (stats.get('market_quotes') or {}).items():
            for it in items:
                q = dict(it)
                # Ensure string serialization
                try:
                    if isinstance(q.get('price_inr'), Decimal):
                        q['price_inr'] = str(round(q['price_inr'], 2))
                    if isinstance(q.get('original_price'), Decimal):
                        q['original_price'] = str(round(q['original_price'], 2))
                except Exception:
                    pass
                q['source'] = source
                quotes.append(q)

        avg_raw = stats.get('all_avg_price')
        avg_price = avg_raw
        if isinstance(avg_price, Decimal):
            avg_price = str(round(avg_price, 2))

        # Compute purchase comparison
        purchase_price_inr = car.price or Decimal('0')
        percent_change_from_purchase = None
        try:
            if isinstance(avg_raw, Decimal) and purchase_price_inr and purchase_price_inr > 0:
                pct = ((avg_raw - purchase_price_inr) / purchase_price_inr) * Decimal('100')
                percent_change_from_purchase = str(round(pct, 2))
        except Exception:
            percent_change_from_purchase = None

        # Get updated credit info after consumption
        try:
            updated_credit = await sync_to_async(MarketFetchCredit.get_or_create_for_user)(request.user)
        except Exception:
            updated_credit = credit  # fallback to previous credit info

        return JsonResponse({
            'average_price_inr': avg_price,
            'quotes': quotes,
            'car_id': car_id,
            'purchase_price_inr': str(round(purchase_price_inr, 2)) if purchase_price_inr else None,
            'percent_change_from_purchase': percent_change_from_purchase,
            'credits_remaining': updated_credit.credits_remaining,
            'daily_limit': MarketFetchCredit.DAILY_LIMIT,
            'next_reset_time': updated_credit.next_reset_time.isoformat(),
        })


class CalculatePortfolioView(View):
    async def get(self, request):
        # Get cars for the authenticated user only
        if not request.user.is_authenticated:
            return HttpResponseForbidden("Authentication required")
        
        cars = await sync_to_async(list)(
            DiecastCar.objects.filter(user=request.user)
            .prefetch_related('market_prices')
        )
        
        total_value = Decimal('0')
        cars_with_market_data = 0
        cars_with_purchase_price = 0
        cars_without_any_price = 0
        detailed_results = []

        for car in cars:
            car_value = None
            value_source = None
            
            # First, try to get the latest market price (existing data)
            latest_market_price = await sync_to_async(
                lambda: car.market_prices.filter(currency='INR').order_by('-fetched_at').first()
            )()
            
            if latest_market_price:
                # Use the latest market price if available
                car_value = latest_market_price.price
                value_source = f"Market Data ({latest_market_price.marketplace})"
                cars_with_market_data += 1
            elif car.price and car.price > 0:
                # Fallback to user's purchase price
                car_value = car.price
                value_source = "Purchase Price"
                cars_with_purchase_price += 1
            else:
                # No price data available
                cars_without_any_price += 1
                value_source = "No Price Data"
            
            # Add to total if we have a valid price
            if car_value and car_value > 0:
                total_value += car_value
            
            detailed_results.append({
                'car_id': car.id,
                'model_name': car.model_name,
                'manufacturer': car.manufacturer,
                'value_inr': str(round(car_value, 2)) if car_value else '0.00',
                'value_source': value_source,
                'market_data_available': latest_market_price is not None,
                'market_data_date': latest_market_price.fetched_at.isoformat() if latest_market_price else None,
            })

        return JsonResponse({
            'total_portfolio_value_inr': str(round(total_value, 2)),
            'cars_with_market_data': cars_with_market_data,
            'cars_with_purchase_price': cars_with_purchase_price,
            'cars_without_any_price': cars_without_any_price,
            'total_cars': len(cars),
            'results': detailed_results,
        })


class DeleteMarketPriceView(View):
    async def delete(self, request, price_id: int):
        try:
            price_obj = await sync_to_async(MarketPrice.objects.select_related('car').get)(pk=price_id)
        except MarketPrice.DoesNotExist:
            return HttpResponseNotFound("MarketPrice not found")

        # Authorization: only the owner of the car can delete
        if not request.user.is_authenticated or price_obj.car.user_id != request.user.id:
            return HttpResponseForbidden("Not allowed")

        await sync_to_async(price_obj.delete)()
        return JsonResponse({'success': True})


class AddManualMarketPriceView(View):
    async def post(self, request, car_id: int):
        # Ensure car exists and belongs to the user
        try:
            car = await sync_to_async(DiecastCar.objects.select_related('user').get)(pk=car_id)
        except DiecastCar.DoesNotExist:
            return HttpResponseNotFound("Car not found")

        if not request.user.is_authenticated or car.user_id != request.user.id:
            return HttpResponseForbidden("Not allowed")

        try:
            payload = json.loads(request.body or '{}')
        except Exception:
            return HttpResponseBadRequest("Invalid JSON body")

        # Validate inputs
        marketplace = (payload.get('marketplace') or '').strip()
        valid_marketplaces = {choice[0] for choice in MARKETPLACE_CHOICES}
        if marketplace not in valid_marketplaces:
            return HttpResponseBadRequest("Invalid marketplace")

        price_raw = payload.get('price')
        if price_raw is None:
            return HttpResponseBadRequest("Missing price")
        try:
            price_dec = Decimal(str(price_raw))
        except Exception:
            return HttpResponseBadRequest("Invalid price")
        if price_dec <= 0:
            return HttpResponseBadRequest("Price must be > 0")

        currency = (payload.get('currency') or 'INR').strip()
        title = (payload.get('title') or '').strip() or None
        src_url = (payload.get('source_listing_url') or payload.get('url') or '').strip() or None

        # Normalize to INR
        try:
            inr_val = convert_to_inr(price_dec, currency)
        except Exception as e:
            return HttpResponseServerError(f"Conversion failed: {e}")
        if not inr_val or inr_val <= 0:
            return HttpResponseBadRequest("Could not convert to INR or value <= 0")

        # Create MarketPrice
        fetched_at = timezone.now()
        price_obj = await sync_to_async(MarketPrice.objects.create)(
            car=car,
            marketplace=marketplace,
            price=inr_val,
            currency='INR',
            fetched_at=fetched_at,
            source_listing_url=src_url,
            title=title,
        )

        # Build response compatible with fetch endpoint quotes
        resp = {
            'id': price_obj.id,
            'marketplace': marketplace,
            'source': marketplace,
            'title': title,
            'price_inr': str(round(inr_val, 2)),
            'original_price': str(round(price_dec, 2)),
            'original_currency': currency,
            'currency': 'INR',
            'source_listing_url': src_url,
            'url': src_url,
            'model_name': car.model_name,
            'manufacturer': car.manufacturer,
            'scale': car.scale,
            'seller': payload.get('seller') or None,
            'fetched_at': fetched_at.isoformat(),
        }

        return JsonResponse({'success': True, 'quote': resp})


class MarketCreditStatusView(View):
    """Get current market fetch credit status for the authenticated user"""
    
    async def get(self, request):
        if not request.user.is_authenticated:
            return HttpResponseForbidden("Authentication required")
            
        try:
            credit = await sync_to_async(MarketFetchCredit.get_or_create_for_user)(request.user)
        except Exception as e:
            return HttpResponseServerError(f"Error getting credit status: {e}")
            
        return JsonResponse({
            'credits_remaining': credit.credits_remaining,
            'credits_used': credit.credits_used,
            'daily_limit': MarketFetchCredit.DAILY_LIMIT,
            'last_reset_date': credit.last_reset_date.isoformat(),
            'next_reset_time': credit.next_reset_time.isoformat(),
            'is_exhausted': credit.is_exhausted,
        })
