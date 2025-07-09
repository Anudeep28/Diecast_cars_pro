# DiecastCollector Pro

A Django-based inventory management system for diecast model cars with purchase tracking, delivery notifications, status updates, and feedback collection.

## Features

- **User Authentication**: Secure login/signup with Django's built-in authentication
- **Diecast Model Management**: Track your diecast car collection
- **Automated Notifications**: 3-day delivery alerts and overdue notifications
- **Feedback System**: Add/update feedback after delivery
- **Dashboard & Reporting**: Total collection value and filtering options

## Setup Instructions

1. Ensure you have Python and the 'myenv' virtual environment installed
2. Activate the virtual environment:
   ```
   .\myenv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```
   pip install django
   ```
4. Apply migrations:
   ```
   python manage.py migrate
   ```
5. Create a superuser:
   ```
   python manage.py createsuperuser
   ```
6. Run the development server:
   ```
   python manage.py runserver
   ```
7. Visit `http://127.0.0.1:8000/` in your browser

## Usage

1. Log in with your superuser account or create a new account
2. Add new diecast cars to your inventory
3. Update status as cars are shipped and delivered
4. Provide feedback after delivery
5. View your total collection value on the dashboard

## Notification System

To check for upcoming deliveries and update overdue statuses, run:
```
python manage.py check_deliveries
```

In a production environment, you would set this up as a daily cron job.
