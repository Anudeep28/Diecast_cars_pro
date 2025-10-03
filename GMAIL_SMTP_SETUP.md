# Gmail SMTP Setup Guide

## Overview
This guide will help you configure Gmail SMTP for sending emails from your Django application. Gmail requires an "App Password" for third-party applications - you **cannot** use your regular Gmail password.

---

## Step-by-Step Setup Instructions

### Step 1: Enable 2-Factor Authentication (2FA)
App Passwords require 2-Factor Authentication to be enabled on your Google account.

1. Go to your **Google Account**: https://myaccount.google.com/
2. Click on **Security** in the left sidebar
3. Under "Signing in to Google", find **2-Step Verification**
4. If it's not enabled:
   - Click **2-Step Verification**
   - Follow the on-screen instructions to set it up
   - You'll need to verify your phone number
5. Once enabled, you'll see "2-Step Verification is on"

---

### Step 2: Generate an App Password

1. Go to your **Google Account** again: https://myaccount.google.com/
2. Click on **Security** in the left sidebar
3. Under "Signing in to Google", look for **App passwords**
   - If you don't see it, make sure 2FA is enabled first
4. Click on **App passwords**
   - You may need to sign in again
5. On the App passwords page:
   - Select app: Choose **Mail** (or **Other** and type "Django App")
   - Select device: Choose **Windows Computer** (or **Other** and type "Diecast Collector")
   - Click **Generate**
6. **IMPORTANT**: Google will show you a 16-character password like: `abcd efgh ijkl mnop`
   - **Copy this password immediately** - you won't be able to see it again!
   - Remove the spaces when copying (make it: `abcdefghijklmnop`)

---

### Step 3: Configure Your .env File

1. Open your `.env` file in the project root directory
2. Find the Gmail section (lines 13-16)
3. Uncomment the two lines and fill in your details:

```bash
# Option 1: Gmail SMTP (Recommended - Requires App Password)
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASSWORD=abcdefghijklmnop
```

**Replace:**
- `your-email@gmail.com` → Your actual Gmail address
- `abcdefghijklmnop` → The 16-character App Password from Step 2 (no spaces)

4. **Comment out** the Outlook settings (lines 18-24) to avoid conflicts:

```bash
# Option 2: Outlook/Microsoft 365 SMTP
#EMAIL_HOST=smtp-mail.outlook.com
#EMAIL_PORT=587
#EMAIL_USE_TLS=True
#EMAIL_HOST_USER=eneru_solutions@outlook.com
#EMAIL_HOST_PASSWORD=iycdozxgwjoortoz
#DEFAULT_FROM_EMAIL=eneru_solutions@outlook.com
```

5. Save the `.env` file

---

### Step 4: Test the Configuration

1. **Restart your Django server** (if it's running)
   - Stop the server with `Ctrl+C`
   - Double-click `run_server.bat` or run `python manage.py runserver`
   
2. You should see this message in the console:
   ```
   ✓ Gmail email backend configured (your-email@gmail.com)
   ```

3. **Test sending an email** using Django shell:

```bash
python manage.py shell
```

Then in the shell, run:

```python
from django.core.mail import send_mail

send_mail(
    'Test Email from Django',
    'This is a test email sent via Gmail SMTP.',
    'your-email@gmail.com',
    ['recipient@example.com'],  # Replace with your email to test
    fail_silently=False,
)
```

4. Check if the email was sent successfully
   - You should receive the email at the recipient address
   - Check your Gmail "Sent" folder to confirm

---

## Important Security Notes

### ✅ DO:
- **Keep your App Password secret** - treat it like a password
- Store it only in the `.env` file (which is in `.gitignore`)
- Never commit `.env` to Git/GitHub
- Use different App Passwords for different applications
- Revoke App Passwords you're not using

### ❌ DON'T:
- Never use your regular Gmail password
- Never hardcode the App Password in your code
- Never share your App Password publicly
- Never commit `.env` file to version control

---

## Troubleshooting

### Problem: "App passwords" option not showing
**Solution**: Make sure 2-Step Verification is fully enabled and activated.

### Problem: Authentication failed
**Solution**: 
- Double-check your Gmail address in `GMAIL_USER`
- Verify the App Password is correct (no spaces, 16 characters)
- Make sure you're using the App Password, not your regular password
- Try generating a new App Password

### Problem: "Username and Password not accepted"
**Solution**:
- The App Password might be incorrect - generate a new one
- Make sure there are no extra spaces in the `.env` file
- Restart your Django server after changing `.env`

### Problem: Email sent but not received
**Solution**:
- Check your Gmail "Sent" folder to confirm it was sent
- Check the recipient's spam/junk folder
- Verify the recipient email address is correct

---

## Gmail SMTP Settings Reference

The following settings are automatically configured in `settings.py`:

```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = GMAIL_USER  # From .env
EMAIL_HOST_PASSWORD = GMAIL_APP_PASSWORD  # From .env
DEFAULT_FROM_EMAIL = GMAIL_USER  # From .env
```

---

## For Production (Heroku)

When deploying to Heroku, add the environment variables:

```bash
heroku config:set GMAIL_USER=your-email@gmail.com
heroku config:set GMAIL_APP_PASSWORD=your-16-char-app-password
```

Or add them in the Heroku Dashboard → Settings → Config Vars

---

## Managing App Passwords

### To view or revoke App Passwords:
1. Go to https://myaccount.google.com/apppasswords
2. You'll see a list of all App Passwords you've created
3. Click the trash icon next to any password to revoke it
4. Revoking a password will immediately stop it from working

---

## Additional Resources

- **Google Account Security**: https://myaccount.google.com/security
- **App Passwords Help**: https://support.google.com/accounts/answer/185833
- **2-Step Verification**: https://support.google.com/accounts/answer/185839
- **Django Email Documentation**: https://docs.djangoproject.com/en/5.2/topics/email/

---

## Quick Reference

| Setting | Value |
|---------|-------|
| SMTP Host | smtp.gmail.com |
| SMTP Port | 587 |
| TLS/SSL | TLS (port 587) |
| Username | Your Gmail address |
| Password | 16-character App Password |

---

**Status**: Gmail SMTP has been successfully integrated into your Django application! 🎉
