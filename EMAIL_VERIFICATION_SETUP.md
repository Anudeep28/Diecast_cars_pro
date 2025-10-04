# Email Verification Implementation Guide

## Overview
Added email verification functionality for new user registrations. Users must verify their email address before proceeding to payment.

## What Changed

### 1. **New Model: EmailVerificationToken**
- Stores verification tokens for each new user
- Tokens expire after 24 hours
- Tracks verification status

### 2. **Updated Registration Flow**
**Before:** Register → Payment → Account Active  
**After:** Register → Email Sent → Verify Email → Payment → Account Active

### 3. **New Views & URLs**
- `email_verification_sent` - Shows "check your email" page
- `verify_email/<token>` - Handles email verification link
- `proceed_to_payment/<user_id>` - Shows payment page after verification

### 4. **Email Templates**
- `email_verification_email.html` - Verification email sent to users
- `email_verification_sent.html` - Page shown after registration

---

## Setup Instructions

### Step 1: Create Database Migrations
Run these commands to update your database:

```bash
# Activate virtual environment (if not already active)
myenv\Scripts\activate

# Create migration for the new model
python manage.py makemigrations inventory

# Apply the migration
python manage.py migrate
```

### Step 2: Configure Email Backend
Make sure you have email configured in your `.env` file. Choose one:

#### Option A: Gmail (Recommended for Development)
```env
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASSWORD=your-app-specific-password
```

**How to get Gmail App Password:**
1. Go to Google Account Settings
2. Security → 2-Step Verification (must be enabled)
3. App passwords → Generate new password
4. Copy the 16-character password to `.env`

#### Option B: Outlook/Microsoft 365
```env
EMAIL_HOST_USER=your-email@outlook.com
EMAIL_HOST_PASSWORD=your-password
EMAIL_HOST=smtp-mail.outlook.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
```

#### Option C: Mailgun (Production)
```env
MAILGUN_SMTP_USERNAME=your-username
MAILGUN_SMTP_PASSWORD=your-password
MAILGUN_SENDER_EMAIL=noreply@yourdomain.com
```

### Step 3: Test the Flow

1. **Start the development server:**
   ```bash
   python manage.py runserver
   ```
   Or double-click `run_server.bat`

2. **Register a new user:**
   - Go to `http://localhost:8000/register/`
   - Fill in the registration form
   - Submit

3. **Check your email:**
   - You should receive a verification email
   - Click the "Verify My Email Address" button
   - Or copy/paste the verification link

4. **Complete payment:**
   - After verification, you'll be redirected to the payment page
   - Complete the payment process
   - Your account will be activated

---

## User Experience Flow

### Registration Process:
```
1. User visits /register/
   ↓
2. Fills in: Username, Email, Password, First/Last Name
   ↓
3. Clicks "Register" button
   ↓
4. System creates inactive user account
   ↓
5. System generates unique verification token (expires in 24h)
   ↓
6. System sends verification email
   ↓
7. User sees "Check Your Email" page
```

### Email Verification:
```
1. User checks email inbox
   ↓
2. Opens verification email from DiecastCollector Pro
   ↓
3. Clicks "Verify My Email Address" button
   ↓
4. Browser opens verification link
   ↓
5. System validates token (checks if not expired)
   ↓
6. System marks email as verified
   ↓
7. User redirected to payment page
```

### Payment & Activation:
```
1. User sees Razorpay payment form
   ↓
2. Enters payment details (₹99 monthly subscription)
   ↓
3. Completes payment
   ↓
4. System verifies payment with Razorpay
   ↓
5. System creates subscription record
   ↓
6. System activates user account
   ↓
7. User can now log in and access dashboard
```

---

## Security Features

✅ **Token Expiration**: Verification links expire after 24 hours  
✅ **One-Time Use**: Tokens are marked as used after verification  
✅ **Secure Random Tokens**: Uses Python's `secrets` module  
✅ **Email Validation**: Checks email uniqueness during registration  
✅ **Inactive Users**: Users remain inactive until payment confirmed  
✅ **Automatic Cleanup**: Expired users can be deleted if needed

---

## Admin Panel

The new model is registered in Django admin:
- Access at: `http://localhost:8000/admin/`
- View all verification tokens
- Check verification status
- See expiration times
- Manually verify emails if needed

---

## Troubleshooting

### Email Not Sending?
1. **Check console output** - If no email backend configured, emails print to console
2. **Check `.env` file** - Ensure email credentials are correct
3. **Check spam folder** - Verification emails might be in spam
4. **Gmail blocking?** - Use App Password, not regular password
5. **Port blocked?** - Some ISPs block port 587, try port 465 with SSL

### Token Expired?
- Users must register again
- Expired tokens automatically invalidate
- System deletes inactive user if token expires

### Already Verified?
- If user clicks verification link again, they're redirected to payment
- No error shown, just info message

### Payment Failed?
- User account remains inactive
- Can retry payment from subscription renewal page
- Contact admin to manually activate if needed

---

## Testing in Development

### Console Email Backend (No SMTP Setup)
If you don't configure any email service, Django will print emails to console:

```bash
python manage.py runserver
```

When user registers, verification email will appear in terminal output.  
Copy the verification URL from console and paste in browser.

---

## Production Considerations

1. **Email Service**: Use reliable service (Mailgun, SendGrid, AWS SES)
2. **Email Deliverability**: Configure SPF, DKIM records for your domain
3. **Rate Limiting**: Add rate limiting to prevent email abuse
4. **Monitoring**: Track verification rates and email delivery
5. **Cleanup Job**: Schedule task to delete expired unverified users
6. **Error Logging**: Log email sending failures for debugging

---

## Future Enhancements (Optional)

- [ ] Resend verification email button
- [ ] Email change verification for existing users
- [ ] Notification preferences
- [ ] Welcome email after payment
- [ ] Admin notifications for new registrations

---

## Questions?

If you encounter any issues:
1. Check Django server console for errors
2. Check email credentials in `.env`
3. Verify migrations are applied: `python manage.py showmigrations`
4. Check admin panel for token status
5. Review user account status in admin

---

**Implementation Complete! 🎉**

Your application now requires email verification before payment, improving security and ensuring valid email addresses for all users.
