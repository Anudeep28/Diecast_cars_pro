# 🔔 Notification System Guide

## Overview

The enhanced notification system provides:
- **Modern UI Notifications**: Interactive banner with overdue and upcoming deliveries
- **Email Alerts**: Automated email notifications for delivery status
- **User Preferences**: Customizable notification settings per user
- **Scheduled Alerts**: Daily automated email summary

---

## Features

### 1. UI Notifications

#### Notification Banner
- Displays at the top of every page when logged in
- Shows **overdue items** (in red) and **upcoming deliveries** (in blue)
- Lists up to 5 items per category with details
- Dismissible alerts with smooth animations
- Quick action buttons to filter relevant items

#### Notification Badge
- Bell icon in navigation bar
- Shows count of total alerts
- Changes from outline to filled when alerts present
- Red badge with number of pending notifications

### 2. Email Notifications

#### Delivery Alert Emails
- **HTML and plain text versions** for email client compatibility
- Beautiful, responsive design
- Summary of overdue and upcoming items
- Direct links to dashboard
- Sent based on user preferences

#### Email Content
- Overdue items with days overdue
- Upcoming deliveries (within next 3 days by default)
- Seller information for quick contact
- Purchase dates and tracking info
- Clear call-to-action buttons

### 3. User Preferences

Users can customize their notification settings:

- **Email Overdue Alerts**: Receive emails for overdue deliveries (default: ON)
- **Email Upcoming Alerts**: Receive emails for upcoming deliveries (default: ON)
- **Email Daily Summary**: Receive daily summary email (default: OFF)
- **Alert Days Before Delivery**: How many days before delivery to alert (default: 3)

Access preferences via:
- Admin panel: `/admin/inventory/notificationpreferences/`
- Profile page (coming soon)

---

## Setup Instructions

### Step 1: Run Migrations

Create the database tables for notification preferences:

```bash
# Activate virtual environment
myenv\Scripts\activate

# Create and run migrations
python manage.py makemigrations
python manage.py migrate
```

### Step 2: Configure Email Settings

Ensure your `.env` file has email configuration (Gmail, Outlook, or Mailgun):

**For Gmail:**
```env
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASSWORD=your-app-specific-password
```

**For Outlook:**
```env
EMAIL_HOST_USER=your-email@outlook.com
EMAIL_HOST_PASSWORD=your-password
EMAIL_HOST=smtp-mail.outlook.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
```

### Step 3: Test Email Notifications

Test the notification system manually:

```bash
# Send alerts to a specific user
python manage.py send_delivery_alerts --user=your_username

# Dry run (see what would be sent without sending)
python manage.py send_delivery_alerts --dry-run

# Send to all users with alerts
python manage.py send_delivery_alerts
```

### Step 4: Schedule Daily Alerts

#### Option A: Windows Task Scheduler (Recommended for Windows)

1. Open **Task Scheduler** (search in Start menu)
2. Click **Create Basic Task**
3. Name: "DiecastCollector Daily Alerts"
4. Trigger: **Daily** at your preferred time (e.g., 9:00 AM)
5. Action: **Start a program**
   - Program: `C:\Users\PC\Documents\Model_car_inventory\myenv\Scripts\python.exe`
   - Arguments: `manage.py send_delivery_alerts`
   - Start in: `C:\Users\PC\Documents\Model_car_inventory`
6. Check "Open Properties dialog" and click Finish
7. In Properties, check "Run whether user is logged on or not"
8. Click OK and enter your Windows password

#### Option B: Manual Script

Create a batch file `send_alerts.bat`:

```batch
@echo off
cd /d C:\Users\PC\Documents\Model_car_inventory
call myenv\Scripts\activate
python manage.py send_delivery_alerts
pause
```

Double-click to run manually or schedule with Task Scheduler.

---

## Usage Examples

### For Developers

#### Send Email Notification Programmatically

```python
from inventory.notification_utils import send_delivery_alert_email

# Send alert to a specific user
user = User.objects.get(username='john')
success = send_delivery_alert_email(user, request)

if success:
    print("Email sent successfully")
```

#### Check User Notification Preferences

```python
from inventory.models import NotificationPreferences

prefs = NotificationPreferences.get_or_create_for_user(user)

if prefs.email_overdue_alerts:
    # User wants overdue alerts
    pass
```

#### Get Users with Alerts

```python
from inventory.notification_utils import get_users_with_alerts

users = get_users_with_alerts()
for user in users:
    send_delivery_alert_email(user)
```

---

## Management Commands

### send_delivery_alerts

Send delivery alert emails to users.

**Options:**
- `--dry-run`: Show what would be sent without actually sending
- `--user USERNAME`: Send alert to specific user

**Examples:**
```bash
# Send to all users with alerts
python manage.py send_delivery_alerts

# Dry run to preview
python manage.py send_delivery_alerts --dry-run

# Send to specific user
python manage.py send_delivery_alerts --user=john_doe
```

**Output:**
```
============================================================
🚗 Delivery Alert Email Service
============================================================
Time: 2025-01-05 09:00:00

📊 Found 5 user(s) with delivery alerts
  ✓ Sent to: john_doe (john@example.com)
  ✓ Sent to: jane_smith (jane@example.com)
  ⚠️  alice_wonder: No email address
  
============================================================
📈 Summary
============================================================
✓ Successfully sent: 2
⚠️  Skipped (no email): 1

✅ Delivery alert process completed
```

---

## Troubleshooting

### Emails Not Sending

1. **Check email configuration** in `.env`
2. **Test email backend**:
   ```bash
   python test_email.py
   ```
3. **Check logs** for error messages
4. **Verify user email addresses** are set in admin panel

### UI Notifications Not Showing

1. **Clear browser cache** and refresh
2. **Check user is logged in**
3. **Verify there are overdue/upcoming items**
4. **Check console for JavaScript errors**

### Scheduled Task Not Running

1. **Verify Task Scheduler task is enabled**
2. **Check task history** in Task Scheduler
3. **Ensure Python path is correct** in task configuration
4. **Run manually** to test: `python manage.py send_delivery_alerts`

---

## Customization

### Change Alert Timing

Edit the default in `models.py`:

```python
alert_days_before_delivery = models.IntegerField(
    default=3,  # Change this value
    help_text='How many days before delivery to send upcoming alerts'
)
```

### Modify Email Templates

Templates are located in:
- HTML: `inventory/templates/inventory/emails/delivery_alert_email.html`
- Text: `inventory/templates/inventory/emails/delivery_alert_email.txt`

### Change Notification Display

Edit the banner component:
- File: `inventory/templates/inventory/components/notification_banner.html`

---

## Best Practices

1. **Enable email verification** before sending notifications
2. **Set up proper email authentication** (SPF, DKIM) to avoid spam filters
3. **Test notifications** in development before production
4. **Monitor email delivery rates** and adjust as needed
5. **Respect user preferences** - always check before sending
6. **Keep email content concise** and actionable
7. **Include unsubscribe options** for compliance

---

## Future Enhancements

Planned features:
- [ ] In-app notification center
- [ ] Push notifications (browser)
- [ ] SMS alerts (Twilio integration)
- [ ] Slack/Discord webhooks
- [ ] Notification history log
- [ ] User-facing preference settings page
- [ ] Notification scheduling preferences (time of day)
- [ ] Weekly digest emails

---

## Support

For issues or questions:
- Check logs in `inventory/logs/`
- Review Django logs
- Test with `--dry-run` flag first
- Verify email configuration

---

**Last Updated:** January 2025
**Version:** 1.0.0
