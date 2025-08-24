import asyncio
import json
from decimal import Decimal

from django.conf import settings
from django.http import JsonResponse, HttpResponseNotFound, HttpResponseServerError, HttpResponseForbidden, HttpResponseBadRequest
from django.views import View
from asgiref.sync import sync_to_async

from django.utils import timezone

from .models import DiecastCar, MarketPrice, MARKETPLACE_CHOICES
from .market_services import MarketService, convert_to_inr

class FetchMarketPriceView(View):
    async def get(self, request, car_id):
        try:
            car = await sync_to_async(DiecastCar.objects.get)(pk=car_id)
        except DiecastCar.DoesNotExist:
            return HttpResponseNotFound("Car not found")

        gemini_api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not gemini_api_key:
            return HttpResponseServerError("GEMINI_API_KEY not configured")

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

        return JsonResponse({
            'average_price_inr': avg_price,
            'quotes': quotes,
            'car_id': car_id,
            'purchase_price_inr': str(round(purchase_price_inr, 2)) if purchase_price_inr else None,
            'percent_change_from_purchase': percent_change_from_purchase,
        })


class CalculatePortfolioView(View):
    async def get(self, request):
        gemini_api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not gemini_api_key:
            return HttpResponseServerError("GEMINI_API_KEY not configured")

        cars = await sync_to_async(list)(DiecastCar.objects.all())
        
        # Limit concurrency to avoid rate-limiting
        semaphore = asyncio.Semaphore(5)

        async def fetch_with_semaphore(car):
            async with semaphore:
                svc = MarketService()
                return await sync_to_async(svc.fetch_and_record)(
                    car,
                    save_extracted_markdown=False,
                    include_search_queries=False,
                    log_search_data=True,
                )

        tasks = [fetch_with_semaphore(car) for car in cars]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        total_value = Decimal('0')
        cars_processed = 0
        cars_failed = 0
        detailed_results = []

        for car, result in zip(cars, results):
            if isinstance(result, dict) and result.get('all_avg_price') is not None:
                avg_inr = result.get('all_avg_price')
                if isinstance(avg_inr, Decimal):
                    total_value += avg_inr
                cars_processed += 1
                detailed_results.append({
                    'car_id': car.id,
                    'model_name': car.model_name,
                    'average_price_inr': str(round(avg_inr, 2)) if isinstance(avg_inr, Decimal) else str(avg_inr),
                })
            else:
                cars_failed += 1
                detailed_results.append({
                    'car_id': car.id,
                    'model_name': car.model_name,
                    'error': str(result) if isinstance(result, Exception) else 'Failed to fetch price',
                })

        return JsonResponse({
            'total_portfolio_value_inr': str(round(total_value, 2)),
            'cars_processed': cars_processed,
            'cars_failed': cars_failed,
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
