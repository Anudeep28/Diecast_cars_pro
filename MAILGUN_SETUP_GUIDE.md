# Mailgun Email Setup Guide

This guide explains how to configure Mailgun for sending emails (password resets, notifications, etc.) in your Django DiecastCollector Pro application.

---

## Prerequisites

✓ Mailgun account created  
✓ Access to Mailgun dashboard

---

## Step 1: Get Mailgun SMTP Credentials

### A. Access Mailgun Dashboard
1. Log into [Mailgun](https://app.mailgun.com/)
2. Navigate to **Sending** → **Domains**

### B. Choose Your Domain
You have two options:

**Option 1: Sandbox Domain (Testing - Free)**
- Use the free sandbox domain provided by Mailgun
- Format: `sandboxXXXXXXXXXXXXXX.mailgun.org`
- Limitation: Can only send emails to **authorized recipients** (you need to verify recipient emails)
- Good for: Testing and development

**Option 2: Custom Domain (Production)**
- Add your own domain (e.g., `modeldiecast.in`)
- Requires DNS configuration
- Can send emails to anyone
- Good for: Production deployment

### C. Get SMTP Credentials
1. Click on your domain
2. Go to **Domain settings** → **SMTP credentials**
3. Note down:
   - **SMTP hostname**: `smtp.mailgun.org`
   - **Port**: `587`
   - **Username**: Usually `postmaster@your-domain.mailgun.org`
   - **Password**: Click "Reset Password" to generate a new SMTP password

---

## Step 2: Configure Local Development

### A. Update Your .env File

Open `c:\Users\PC\Documents\Model_car_inventory\.env` and replace the placeholders:

```env
# Mailgun Email Settings
MAILGUN_SMTP_USERNAME=postmaster@sandboxXXXXXX.mailgun.org
MAILGUN_SMTP_PASSWORD=your_actual_smtp_password_here
MAILGUN_SENDER_EMAIL=noreply@sandboxXXXXXX.mailgun.org
```

**Important:** 
- Replace `sandboxXXXXXX.mailgun.org` with your actual Mailgun domain
- Replace `your_actual_smtp_password_here` with your SMTP password from Mailgun
- Keep quotes off (no quotes around values in .env)

### B. For Sandbox Domain - Authorize Recipients

If using sandbox domain:
1. Go to **Sending** → **Overview** → **Authorized Recipients**
2. Add your test email addresses (e.g., `anupatil28@gmail.com`)
3. Click "Save Recipient"
4. Check your email and click the verification link

---

## Step 3: Test Email Configuration

### A. Restart Django Server

Stop your current server (Ctrl+C) and restart:

```bash
python manage.py runserver
```

You should see:
```
✓ Mailgun email backend configured
```

If you see `Using console email backend`, check your .env file for typos.

### B. Test Password Reset

1. Go to `http://127.0.0.1:8000/login/`
2. Click "Forgot Password?"
3. Enter your email address
4. Click "Send Reset Link"
5. Check your email inbox (including spam folder)

### C. Test from Django Shell (Optional)

```bash
python manage.py shell
```

```python
from django.core.mail import send_mail

send_mail(
    'Test Email from DiecastCollector Pro',
    'If you receive this, Mailgun is working!',
    'noreply@your-domain.mailgun.org',
    ['your-test-email@gmail.com'],
    fail_silently=False,
)
```

---

## Step 4: Production Deployment (Heroku)

### A. Set Heroku Config Vars

Instead of using `.env`, set environment variables in Heroku:

```bash
heroku config:set MAILGUN_SMTP_USERNAME=postmaster@your-domain.mailgun.org
heroku config:set MAILGUN_SMTP_PASSWORD=your_smtp_password
heroku config:set MAILGUN_SENDER_EMAIL=noreply@your-domain.mailgun.org
```

Or via Heroku Dashboard:
1. Go to your app → **Settings** → **Config Vars**
2. Click "Reveal Config Vars"
3. Add the three variables above

### B. Use Custom Domain (Recommended)

For production, use your verified domain instead of sandbox:

1. In Mailgun, go to **Sending** → **Domains** → **Add New Domain**
2. Enter your domain: `modeldiecast.in`
3. Follow DNS configuration instructions:
   - Add TXT records for domain verification
   - Add MX records for receiving emails
   - Add CNAME records for tracking
4. Wait for verification (usually 24-48 hours)
5. Update your Heroku config vars with the new domain

---

## Step 5: Monitor Email Delivery

### View Sent Emails
1. Go to Mailgun Dashboard → **Sending** → **Logs**
2. See delivery status, bounces, failures

### Check Mailgun Limits
- **Sandbox**: 300 emails/month (to authorized recipients only)
- **Flex Plan**: $0 base + $0.80 per 1,000 emails
- **Foundation**: $35/month for 50,000 emails

---

## Troubleshooting

### Issue 1: Still Seeing Console Backend
**Problem**: Emails printing to terminal instead of sending via Mailgun

**Solution**:
- Check `.env` file has correct variable names
- Ensure no spaces around `=` in .env
- Verify variables are not commented out
- Restart Django server

### Issue 2: Authentication Failed
**Problem**: `SMTP Authentication Error`

**Solution**:
- Verify SMTP username (must include domain: `postmaster@domain.mailgun.org`)
- Reset SMTP password in Mailgun dashboard
- Check for typos in `.env` file

### Issue 3: Emails Not Received (Sandbox)
**Problem**: Email not arriving when using sandbox domain

**Solution**:
- Verify recipient email is authorized in Mailgun
- Check spam/junk folder
- Check Mailgun logs for delivery status

### Issue 4: Relay Access Denied
**Problem**: `Relay access denied` error

**Solution**:
- Ensure sender email uses your Mailgun domain
- Update `MAILGUN_SENDER_EMAIL` in `.env`
- Don't use generic email addresses like `@gmail.com` as sender

---

## Security Best Practices

✓ **Never commit .env to Git** - Already in .gitignore  
✓ **Use environment variables** - Done via .env and Heroku Config Vars  
✓ **Rotate SMTP passwords** - Change periodically in Mailgun dashboard  
✓ **Monitor usage** - Watch for unusual activity in Mailgun logs  
✓ **Use TLS encryption** - Already configured (port 587)

---

## Files Modified

1. **`.env`** - Added Mailgun credentials (local development)
2. **`.env.example`** - Added Mailgun template variables
3. **`diecastcollector/settings.py`** - Configured Mailgun SMTP backend

---

## What Emails Will Use Mailgun?

✓ **Password reset emails** - When users click "Forgot Password?"  
✓ **Account verification emails** (if you implement it later)  
✓ **Subscription renewal reminders** (if you implement it later)  
✓ **Admin notifications** (if you implement it later)

---

## Next Steps

1. ✅ Get Mailgun SMTP credentials from dashboard
2. ✅ Update `.env` file with real credentials
3. ✅ Test password reset locally
4. ⬜ For production: Add custom domain in Mailgun
5. ⬜ For production: Set Heroku config vars
6. ⬜ Monitor email delivery in Mailgun logs

---

## Support

- **Mailgun Documentation**: https://documentation.mailgun.com/
- **Django Email Documentation**: https://docs.djangoproject.com/en/5.2/topics/email/
- **Mailgun Support**: support@mailgun.com
