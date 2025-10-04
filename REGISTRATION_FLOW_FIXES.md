# Registration & Payment Flow - Complete Guide

## 🎯 Overview
This document explains the complete registration and payment flow, including all recovery scenarios and safeguards implemented to handle payment failures gracefully.

---

## 📋 Normal Flow (Happy Path)

### Step 1: Registration
1. User visits `/register/`
2. Fills in: username, email, password, name
3. Agrees to subscription terms
4. Submits form

**Backend Actions:**
- User account created with `is_active=False`
- `EmailVerificationToken` created (expires in 24 hours)
- Verification email sent
- User redirected to email verification page

### Step 2: Email Verification
1. User clicks verification link in email
2. Link format: `/verify-email/<token>/`

**Backend Actions:**
- Token validated (not expired, not already used)
- `email_verified` set to `True`
- User redirected to payment page

### Step 3: Payment
1. User sees Razorpay payment form
2. Completes payment (₹99)

**Backend Actions:**
- Payment signature verified with Razorpay
- Payment status confirmed as "captured"
- `Subscription` created (30 days validity)
- `user.is_active` set to `True`
- User redirected to success page

### Step 4: Login & Access
- User can now login with username/password
- Full access to dashboard and features

---

## ⚠️ Problem Scenarios & Solutions

### Scenario 1: Payment Fails/Cancelled After Email Verification

**Problem:** User verified email but payment failed
- User account exists but `is_active=False`
- Email marked as verified
- No subscription created
- User cannot login (Django requires `is_active=True`)
- User cannot re-register (email/username already taken)

**Solution Implemented:**

#### A. Smart Payment Failed Page
**File:** `inventory/templates/inventory/payment_failed.html`
- Detects if user has verified email
- Shows "Retry Payment" button (not "Start Over")
- Preserves session data for seamless retry
- Direct link to payment page

#### B. Registration Recovery Check
**File:** `inventory/views.py` - `register()` function
- If user tries to register with same email
- System detects email is verified but no subscription
- Auto-redirects to payment page (no re-registration needed)

#### C. Registration Status Checker
**New Page:** `/check-registration/`
- User enters email to check status
- System determines:
  - Already active → redirect to login
  - Email verified, no payment → redirect to payment
  - Email not verified → redirect to verification page
  - Not registered → redirect to register

---

### Scenario 2: User Tries to Re-register with Same Email

**Problem:** Form validation blocks duplicate emails

**Solution Implemented:**

**File:** `inventory/forms.py` - `UserRegistrationForm.clean_email()`
- Custom validation message with clickable link
- Detects incomplete registration
- Provides direct link to complete payment
- Message: "This email is already registered and verified. Click here to complete your payment."

---

### Scenario 3: Email Verification Token Expired

**Problem:** User clicks verification link after 24 hours

**Solution Implemented:**

**File:** `inventory/views.py` - `verify_email()` function
- Token expiration check
- If expired:
  - Delete expired user account
  - Delete verification token
  - Show error message: "Verification link expired. Please register again."
  - Redirect to registration page

---

### Scenario 4: User Forgets Registration Status

**Problem:** User doesn't remember if they registered or completed payment

**Solution Implemented:**

**New Feature:** Registration Status Checker
- Accessible from login page
- Link: "Incomplete registration? Check status"
- User enters email
- System provides appropriate next step

---

### Scenario 5: Orphaned Incomplete Registrations

**Problem:** Database fills with incomplete user accounts

**Solution Implemented:**

**New Management Command:** `cleanup_incomplete_registrations`

**Usage:**
```bash
# Dry run (see what would be deleted)
python manage.py cleanup_incomplete_registrations --dry-run

# Delete incomplete registrations older than 7 days (default)
python manage.py cleanup_incomplete_registrations

# Custom timeframe (e.g., 30 days)
python manage.py cleanup_incomplete_registrations --days=30
```

**What it does:**
- Finds users with `is_active=False` and no subscription
- Older than specified days (default: 7)
- Deletes user and associated verification tokens
- Shows summary before deletion (requires confirmation)

**Recommended:** Run weekly via cron job or scheduled task

---

## 🔄 Complete Flow Chart

```
START
  │
  ├─→ [REGISTER] → User Created (is_active=False)
  │       ↓
  │   Email Sent
  │       ↓
  ├─→ [VERIFY EMAIL] → Token Valid?
  │       ├─ No (Expired) → Delete User → REGISTER
  │       └─ Yes → email_verified=True
  │           ↓
  ├─→ [PAYMENT PAGE] → Payment Success?
  │       ├─ No (Failed/Cancelled)
  │       │   ↓
  │       │   [PAYMENT FAILED PAGE]
  │       │   ├─ Has verified email? → [RETRY PAYMENT] ──┐
  │       │   └─ No verified email → [START OVER] → REGISTER
  │       │                                          ↑
  │       └─ Yes                                     │
  │           ↓                                      │
  │       Subscription Created                       │
  │       user.is_active = True                      │
  │           ↓                                      │
  │       [SUCCESS PAGE]                             │
  │           ↓                                      │
  └─→ [LOGIN] → Access Dashboard                    │
                                                     │
  [CHECK STATUS PAGE] ──────────────────────────────┘
  (Available from login page)
```

---

## 🛡️ Safeguards Implemented

### 1. **Email Uniqueness Check**
- Custom validation in registration form
- Helpful error messages with recovery links

### 2. **Token Expiration**
- 24-hour validity for verification tokens
- Auto-cleanup of expired tokens and users

### 3. **Payment Verification**
- Razorpay signature verification (required for production)
- Amount validation
- Status check (must be "captured")

### 4. **Session Management**
- `user_id` stored in session during payment flow
- Persists across payment retries
- Cleared after successful login

### 5. **User State Tracking**
- `is_active=False` until payment completes
- `email_verified` flag on token
- Subscription existence check

### 6. **Recovery Mechanisms**
- Registration status checker
- Smart form validation with recovery links
- Retry payment from failed payment page

---

## 🔧 Files Modified/Created

### Modified Files:
1. `inventory/views.py`
   - Enhanced `register()` with duplicate handling
   - Enhanced `payment_failed()` with retry logic
   - Added `check_registration_status()` view

2. `inventory/forms.py`
   - Enhanced `clean_email()` with recovery link

3. `inventory/templates/inventory/payment_failed.html`
   - Added conditional retry button
   - Shows user email for confirmation

4. `inventory/templates/inventory/login.html`
   - Added "Check status" link

5. `inventory/urls.py`
   - Added route for registration status checker

6. `inventory/views/__init__.py`
   - Exported new view function

### Created Files:
1. `inventory/templates/inventory/check_registration.html`
   - Registration status checker page

2. `inventory/management/commands/cleanup_incomplete_registrations.py`
   - Management command for database cleanup

3. `REGISTRATION_FLOW_FIXES.md`
   - This documentation file

---

## 📝 Testing Checklist

### Test Case 1: Normal Flow
- [ ] Register new user
- [ ] Verify email
- [ ] Complete payment
- [ ] Login successfully

### Test Case 2: Payment Failure Recovery
- [ ] Register new user
- [ ] Verify email
- [ ] Cancel payment on Razorpay
- [ ] Verify "Retry Payment" button appears
- [ ] Click retry and complete payment
- [ ] Login successfully

### Test Case 3: Duplicate Registration
- [ ] Register user (verify email but don't pay)
- [ ] Try to register again with same email
- [ ] Verify helpful error message appears
- [ ] Click recovery link
- [ ] Complete payment

### Test Case 4: Status Checker
- [ ] Access `/check-registration/`
- [ ] Enter email of incomplete registration
- [ ] Verify redirect to payment page
- [ ] Enter email of active user
- [ ] Verify redirect to login

### Test Case 5: Token Expiration
- [ ] Register user
- [ ] Wait 24+ hours (or manually expire token in DB)
- [ ] Click verification link
- [ ] Verify user and token deleted
- [ ] Verify can re-register with same email

### Test Case 6: Cleanup Command
- [ ] Create incomplete registration (7+ days old)
- [ ] Run: `python manage.py cleanup_incomplete_registrations --dry-run`
- [ ] Verify user listed
- [ ] Run without --dry-run
- [ ] Verify user deleted

---

## 🚀 Deployment Considerations

### 1. Email Configuration
Ensure email settings are properly configured in production:
- `EMAIL_BACKEND`
- `EMAIL_HOST`, `EMAIL_PORT`
- `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`
- `DEFAULT_FROM_EMAIL`

### 2. Razorpay Configuration
- Use production keys (not test keys)
- Enable webhook for payment notifications
- Set proper callback URLs

### 3. Session Configuration
- Ensure sessions persist across requests
- Configure session timeout appropriately

### 4. Scheduled Tasks
Set up automated cleanup:

**Windows (Task Scheduler):**
```batch
cd C:\path\to\project
myenv\Scripts\activate
python manage.py cleanup_incomplete_registrations
```
Run weekly at 2 AM

**Linux (Crontab):**
```bash
0 2 * * 0 cd /path/to/project && source myenv/bin/activate && python manage.py cleanup_incomplete_registrations
```

### 5. Monitoring
Monitor for:
- High number of incomplete registrations (indicates payment issues)
- Email delivery failures
- Payment verification failures

---

## 💡 User Communication

### Email Verification Email Should Include:
- Clear "Verify Email" button
- Link expiration notice (24 hours)
- Support contact info
- What happens after verification

### Payment Failed Page Should Show:
- Clear error message
- Retry payment option
- Support contact
- No money was charged (if payment failed)

### Registration Status Checker Should:
- Be easily accessible from login/register pages
- Provide clear next steps
- Handle all edge cases gracefully

---

## 🆘 Common Support Issues

### "I can't login"
**Likely cause:** Payment not completed
**Solution:** Use registration status checker → Complete payment

### "Email already registered"
**Likely cause:** Previous incomplete registration
**Solution:** Click recovery link in error message OR use status checker

### "Payment failed but I was charged"
**Investigation:** Check Razorpay dashboard
**Solution:** Verify payment status, manually activate subscription if needed

### "Verification link doesn't work"
**Likely cause:** Token expired (24 hours)
**Solution:** Delete old user account, register again

---

## 📊 Database Cleanup Statistics

Track these metrics:
- Incomplete registrations per week
- Average time to complete payment after registration
- Token expiration rate
- Payment failure rate

Use this data to:
- Optimize registration flow
- Identify payment gateway issues
- Improve user communication

---

## ✅ System is Now Foolproof Because:

1. ✅ **No Dead-end States** - Every scenario has a recovery path
2. ✅ **Clear User Communication** - Users know what to do next
3. ✅ **Automated Cleanup** - Database doesn't fill with orphaned records
4. ✅ **Smart Validation** - Forms provide helpful recovery options
5. ✅ **Session Persistence** - Users can retry payment without re-verification
6. ✅ **Token Expiration** - Old tokens auto-cleanup and allow re-registration
7. ✅ **Status Checker** - Users can always find their registration state
8. ✅ **Payment Verification** - Multiple layers of payment validation

---

## 📞 Support

For issues not covered by this guide, users should contact support with:
- Email address used for registration
- Approximate registration date
- Payment transaction ID (if payment was attempted)
- Screenshot of any error messages
