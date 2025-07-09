from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.messages import constants as message_levels
from datetime import timedelta
from inventory.models import DiecastCar
from django.contrib import messages
from django.contrib.sessions.models import Session
from django.contrib.sessions.backends.db import SessionStore

class Command(BaseCommand):
    help = 'Check for upcoming and overdue deliveries and update statuses'

    def handle(self, *args, **options):
        today = timezone.now().date()
        three_days_from_now = today + timedelta(days=3)
        
        # Check for cars with delivery due in 3 days
        upcoming_delivery = DiecastCar.objects.filter(
            delivery_due_date=three_days_from_now, 
            status__in=['Purchased/Paid', 'Shipped']
        )
        
        for car in upcoming_delivery:
            self.stdout.write(
                self.style.WARNING(
                    f'Delivery for {car.model_name} by {car.manufacturer} is due in 3 days for {car.user.username}!'
                )
            )
            # Note: In a real production system, we would send an email notification here
            # self.send_notification(car.user, f'Delivery for {car.model_name} is due in 3 days!', 'info')
        
        # Check for overdue cars
        overdue_cars = DiecastCar.objects.filter(
            delivery_due_date__lt=today,
            status__in=['Purchased/Paid', 'Shipped']
        )
        
        for car in overdue_cars:
            car.status = 'Overdue'
            car.save()
            self.stdout.write(
                self.style.ERROR(
                    f'Delivery for {car.model_name} by {car.manufacturer} is overdue for {car.user.username}!'
                )
            )
            # Note: In a real production system, we would send an email notification here
            # self.send_notification(car.user, f'Delivery for {car.model_name} is overdue!', 'warning')
        
        self.stdout.write(
            self.style.SUCCESS('Successfully checked deliveries')
        )
    
    def send_notification(self, user, message, level):
        # This is a placeholder for sending actual notifications
        # In a real system, you would implement email notifications or use Django Channels
        self.stdout.write(f"Notification to {user.username}: {message} (Level: {level})")
