from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal
import random

from inventory.models import DiecastCar, MarketPrice
from inventory.market_services import MarketService


class Command(BaseCommand):
    help = "Fetch market prices for cars. Use --simulate to generate sample prices without calling external APIs."

    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, help='Username to limit cars to a specific user')
        parser.add_argument('--car-id', type=int, help='Specific DiecastCar ID to update')
        parser.add_argument('--simulate', action='store_true', help='Generate simulated market prices')

    def handle(self, *args, **options):
        qs = DiecastCar.objects.all()
        if options.get('user'):
            qs = qs.filter(user__username=options['user'])
        if options.get('car_id'):
            qs = qs.filter(pk=options['car_id'])

        total_quotes = 0
        svc = MarketService()

        for car in qs:
            if options.get('simulate'):
                # Simulate between 1 and 3 quotes around purchase price with variance
                base = float(car.price) if car.price else 1000.0
                for marketplace in ['ebay', 'hobbydb', 'diecast_auction']:
                    if random.random() < 0.8:  # 80% chance to generate a quote
                        price = Decimal(str(round(base * random.uniform(0.8, 1.3), 2)))
                        MarketPrice.objects.create(
                            car=car,
                            marketplace=marketplace,
                            price=price,
                            currency='INR',
                            fetched_at=timezone.now(),
                            source_listing_url=None,
                            title=f"Simulated {marketplace.capitalize()} quote"
                        )
                        total_quotes += 1
                self.stdout.write(self.style.SUCCESS(f"Simulated quotes recorded for car {car.id}: {car.model_name}"))
            else:
                recorded = svc.fetch_and_record(car)
                total_quotes += recorded
                self.stdout.write(self.style.SUCCESS(f"Fetched {recorded} quotes for car {car.id}: {car.model_name}"))

        self.stdout.write(self.style.SUCCESS(f"Done. Total quotes recorded: {total_quotes}"))
