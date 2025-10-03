# Outlook/Microsoft 365 SMTP Setup Guide

Simple guide to use your existing Outlook account for sending emails from your Django app.

---

## ✅ Advantages of Using Outlook

- **Already have an account** - No new service needed
- **No recipient restrictions** - Send to anyone
- **Free** - No additional costs
- **Trusted sender** - Better email deliverability
- **Simple setup** - Just username and password

---

## Step 1: Get Your Outlook Password

### ⚠️ Important: Use App Password (Recommended)

If you have 2-factor authentication enabled on your Outlook account (recommended for security), you need to create an **App Password**:

1. Go to [Microsoft Account Security](https://account.microsoft.com/security)
2. Sign in with your Outlook account
3. Go to **Security** → **Advanced security options**
4. Find **App passwords** section
5. Click "Create a new app password"
6. Copy the generated password (you'll use this instead of your regular password)

### Regular Password (If 2FA Not Enabled)

If you don't have 2-factor authentication, you can use your regular Outlook password. However, enabling 2FA + App Password is more secure.

---

## Step 2: Configure Your `.env` File

Open `c:\Users\PC\Documents\Model_car_inventory\.env` and update:

```env
# Option 1: Outlook/Microsoft 365 SMTP
EMAIL_HOST=smtp-mail.outlook.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=eneru_solutions@outlook.com
EMAIL_HOST_PASSWORD=your_app_password_or_regular_password
DEFAULT_FROM_EMAIL=eneru_solutions@outlook.com

# Comment out Mailgun settings if you have them
# MAILGUN_SMTP_USERNAME=...
# MAILGUN_SMTP_PASSWORD=...
# MAILGUN_SENDER_EMAIL=...
```

**Replace:**
- `EMAIL_HOST_PASSWORD` with your App Password (or regular password)

---

## Step 3: Test the Configuration

### A. Restart Django Server

```bash
python manage.py runserver
```

You should see:
```
✓ Outlook email backend configured (eneru_solutions@outlook.com)
```

### B. Test Password Reset

1. Go to `http://127.0.0.1:8000/login/`
2. Click "Forgot Password?"
3. Enter any email address (can be your Outlook email or any other)
4. Check the recipient's inbox

### C. Test from Django Shell (Optional)

```bash
python manage.py shell
```

```python
from django.core.mail import send_mail

send_mail(
    'Test Email',
    'This is a test from DiecastCollector Pro!',
    'eneru_solutions@outlook.com',
    ['recipient@example.com'],
    fail_silently=False,
)
```

---

## Outlook SMTP Details

| Setting | Value |
|---------|-------|
| **SMTP Server** | `smtp-mail.outlook.com` |
| **Port** | `587` (TLS) or `465` (SSL) |
| **Encryption** | TLS/STARTTLS |
| **Username** | Your full Outlook email |
| **Password** | App Password (or regular password) |
| **Sender Email** | Your Outlook email |

---

## Troubleshooting

### Issue 1: Authentication Failed

**Error**: `SMTPAuthenticationError: Username and Password not accepted`

**Solutions**:
- ✅ Use an **App Password** if 2FA is enabled
- ✅ Check for typos in email/password
- ✅ Ensure your Outlook account is not locked
- ✅ Try signing in to Outlook web to verify credentials

### Issue 2: Less Secure App Access

**Error**: `Sign-in blocked` or `Less secure app access`

**Solution**:
- Microsoft has deprecated "less secure apps"
- **Use App Password instead** (see Step 1)

### Issue 3: Rate Limiting

**Error**: Too many emails sent

**Solution**:
- Outlook has sending limits:
  - **Free account**: ~100 recipients per day
  - **Microsoft 365**: Higher limits
- For bulk emails, consider Mailgun

### Issue 4: Emails Going to Spam

**Solution**:
- Ensure sender email is your real Outlook email
- Recipients may need to mark as "Not Spam"
- For production, consider using a custom domain with Mailgun

---

## Outlook vs Mailgun Comparison

| Feature | Outlook | Mailgun |
|---------|---------|---------|
| **Setup Complexity** | ⭐ Easy | ⭐⭐ Medium |
| **Cost** | ✅ Free | ⚠️ Paid after free tier |
| **Sending Limits** | ~100/day (free) | 5,000/month (free), then pay-as-you-go |
| **Professional Sender** | Personal email | Custom domain email |
| **Recipient Restrictions** | None | Sandbox: Authorized only |
| **Deliverability** | Good | Excellent |
| **Best For** | Development & Testing | Production |
| **Analytics** | ❌ No | ✅ Yes |

---

## Recommendation

### For Development/Testing:
✅ **Use Outlook** - Simple, free, no restrictions

### For Production (Heroku):
✅ **Use Mailgun with Custom Domain** - Professional, better deliverability, analytics

### Current Setup:
Your app now supports **both**! It checks for Outlook settings first, then falls back to Mailgun if needed.

---

## Production Note (Heroku)

When deploying to Heroku, you can use either:

**Option A: Outlook (Simple)**
```bash
heroku config:set EMAIL_HOST=smtp-mail.outlook.com
heroku config:set EMAIL_PORT=587
heroku config:set EMAIL_USE_TLS=True
heroku config:set EMAIL_HOST_USER=eneru_solutions@outlook.com
heroku config:set EMAIL_HOST_PASSWORD=your_app_password
heroku config:set DEFAULT_FROM_EMAIL=eneru_solutions@outlook.com
```

**Option B: Mailgun (Professional)**
```bash
heroku config:set MAILGUN_SMTP_USERNAME=postmaster@modeldiecast.in
heroku config:set MAILGUN_SMTP_PASSWORD=your_password
heroku config:set MAILGUN_SENDER_EMAIL=noreply@modeldiecast.in
```

---

## Security Best Practices

✅ **Enable 2FA** on your Outlook account  
✅ **Use App Passwords** instead of regular password  
✅ **Never commit `.env` to Git** - Already in .gitignore  
✅ **Rotate passwords** periodically  
✅ **Monitor sent emails** for suspicious activity

---

## Next Steps

1. ✅ Update `.env` with your Outlook password
2. ✅ Restart Django server
3. ✅ Test password reset functionality
4. ⬜ For production, consider Mailgun with custom domain
