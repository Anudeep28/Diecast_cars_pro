from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from inventory.models import DiecastCar
from inventory.market_services import MarketService, convert_to_inr
import logging

logger = logging.getLogger('inventory.management')


class Command(BaseCommand):
    help = 'Update market prices for diecast cars'

    def add_arguments(self, parser):
        parser.add_argument(
            '--car-id',
            type=int,
            help='Update prices for a specific car ID',
        )
        parser.add_argument(
            '--simulate',
            action='store_true',
            help='Simulate the update without saving to database',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Update prices for all cars',
        )

    def handle(self, *args, **options):
        car_id = options.get('car_id')
        simulate = options.get('simulate', False)
        update_all = options.get('all', False)

        if car_id:
            try:
                car = DiecastCar.objects.get(id=car_id)
                cars = [car]
                self.stdout.write(f"Updating market prices for car {car_id}: {car}")
            except DiecastCar.DoesNotExist:
                raise CommandError(f'Car with ID {car_id} does not exist')
        elif update_all:
            cars = DiecastCar.objects.all()
            self.stdout.write(f"Updating market prices for all {cars.count()} cars")
        else:
            raise CommandError('Please specify --car-id <ID> or --all')

        if simulate:
            self.stdout.write(self.style.WARNING('SIMULATION MODE - No data will be saved'))

        market_service = MarketService()
        total_updated = 0
        total_quotes = 0

        for car in cars:
            self.stdout.write(f"\nProcessing car {car.id}: {car.model_name} by {car.manufacturer}")
            
            try:
                # Fetch market data
                if simulate:
                    # For simulation, just fetch quotes without saving
                    result = {
                        'all_avg_price': None,
                        'user_value': None,
                        'source_averages': {},
                        'per_source_quotes': {},
                        'per_market_counts': {},
                    }
                    # Simulate by fetching quotes but not saving them
                    service = MarketService()
                    all_quotes = []
                    for marketplace, provider in service.providers.items():
                        try:
                            link = car.market_links.filter(marketplace=marketplace).first()
                            quotes = provider.fetch(car, link)
                            all_quotes.extend(quotes)
                            result['per_market_counts'][marketplace] = len(quotes)
                        except Exception:
                            result['per_market_counts'][marketplace] = 0
                    
                    if all_quotes:
                        # Calculate average for simulation
                        inr_prices = [convert_to_inr(q.price, q.currency) for q in all_quotes]
                        result['all_avg_price'] = sum(inr_prices) / len(inr_prices) if inr_prices else None
                else:
                    # Normal operation - fetch and save
                    result = market_service.fetch_and_record(car)
                
                quotes_count = sum(result.get('per_market_counts', {}).values())
                total_quotes += quotes_count
                
                if quotes_count > 0:
                    total_updated += 1
                    avg_price = result.get('all_avg_price')
                    if avg_price:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✓ Found {quotes_count} quotes, avg price: ₹{avg_price:.2f}"
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.SUCCESS(f"  ✓ Found {quotes_count} quotes")
                        )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"  ⚠ No quotes found")
                    )
                
                # Show per-marketplace counts
                market_counts = result.get('per_market_counts', {})
                if market_counts:
                    counts_str = ", ".join([f"{k}: {v}" for k, v in market_counts.items() if v > 0])
                    if counts_str:
                        self.stdout.write(f"    Sources: {counts_str}")
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  ✗ Error processing car {car.id}: {str(e)}")
                )
                logger.exception(f"Error processing car {car.id}: {e}")

        # Summary
        self.stdout.write(f"\n" + "="*50)
        self.stdout.write(f"Summary:")
        self.stdout.write(f"  Cars processed: {len(cars)}")
        self.stdout.write(f"  Cars with quotes: {total_updated}")
        self.stdout.write(f"  Total quotes found: {total_quotes}")
        
        if simulate:
            self.stdout.write(self.style.WARNING("  (Simulation mode - no data saved)"))
        else:
            self.stdout.write(self.style.SUCCESS("  Market prices updated successfully!"))
