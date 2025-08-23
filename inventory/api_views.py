import asyncio
from decimal import Decimal

from django.conf import settings
from django.http import JsonResponse, HttpResponseNotFound, HttpResponseServerError
from django.views import View
from asgiref.sync import sync_to_async

from .models import DiecastCar
from .market_services import MarketService

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

        avg_price = stats.get('all_avg_price')
        if isinstance(avg_price, Decimal):
            avg_price = str(round(avg_price, 2))

        return JsonResponse({
            'average_price_inr': avg_price,
            'quotes': quotes,
            'car_id': car_id,
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
