# Authentication Validations Documentation

## Registration Validations ✓

### 1. Username Validation
- **Uniqueness Check**: ✓ Implemented
  - Custom error message: "This username is already taken. Please choose a different one."
  - Location: `inventory/forms.py` - `UserRegistrationForm.clean_username()`
  - Django's User model also enforces uniqueness at database level

### 2. Email Validation
- **Required Field**: ✓ Implemented (forms.EmailField(required=True))
- **Email Format**: ✓ Implemented (Django's EmailField validates format)
- **Uniqueness Check**: ✓ Implemented
  - Custom error message: "An account with this email address already exists."
  - Location: `inventory/forms.py` - `UserRegistrationForm.clean_email()`

### 3. Password Validation
- **Password Strength**: ✓ Implemented (Django's UserCreationForm)
  - Minimum length requirement
  - Not entirely numeric
  - Not too similar to username/email
  - Not common password
- **Password Mismatch**: ✓ Implemented (Django's UserCreationForm)
  - Error message: "The two password fields didn't match."
  - Validates password1 == password2
- **Password Help Text**: ✓ Displayed in template
  - Location: `inventory/templates/inventory/register.html` (line 68-70)

### 4. Error Message Display
All registration errors are displayed with:
- Field-level errors (red border on invalid fields)
- Error messages below each field
- Bootstrap styling with `.is-invalid` class
- Location: `inventory/templates/inventory/register.html`

### 5. Additional Validations
- **Subscription Agreement**: ✓ Required checkbox
  - User must agree to monthly subscription
  - Location: `inventory/forms.py` - `agree_subscription` field

---

## Login Validations ✓

### 1. Authentication
- **Wrong Username/Password**: ✓ Implemented
  - Error message: "Please enter a correct username and password. Note that both fields may be case-sensitive."
  - Django's built-in LoginView handles authentication
  - Location: Uses `auth_views.LoginView`

### 2. Error Message Display
- **Login Failed Alert**: ✓ Implemented
  - Red alert box at top of form
  - Clear error message for failed login attempts
  - Field-level validation for username/password
  - Location: `inventory/templates/inventory/login.html` (lines 13-23)

### 3. Inactive Account
- Django automatically prevents login for inactive accounts (is_active=False)
- Accounts are set to inactive until payment is confirmed
- Location: `inventory/views.py` - `register()` view (line 439)

---

## Testing Instructions

### Test Registration:

1. **Duplicate Username**:
   - Try to register with an existing username
   - Expected: Error message "This username is already taken. Please choose a different one."

2. **Duplicate Email**:
   - Try to register with an existing email
   - Expected: Error message "An account with this email address already exists."

3. **Password Mismatch**:
   - Enter different passwords in password1 and password2
   - Expected: Error message "The two password fields didn't match."

4. **Weak Password**:
   - Try common passwords like "password123"
   - Expected: Error messages about password strength

5. **Empty Required Fields**:
   - Leave username, email, or password fields empty
   - Expected: "This field is required" error messages

### Test Login:

1. **Wrong Username**:
   - Enter non-existent username
   - Expected: "Please enter a correct username and password" error

2. **Wrong Password**:
   - Enter correct username but wrong password
   - Expected: "Please enter a correct username and password" error

3. **Inactive Account**:
   - Try to login before payment confirmation
   - Expected: Login fails (account not activated)

---

## Files Modified

1. **inventory/forms.py**:
   - Added `clean_email()` method for email uniqueness validation
   - Added `clean_username()` method for better username validation messaging

2. **inventory/templates/inventory/login.html**:
   - Added error message display section (lines 13-23)
   - Added field-level error display for username and password
   - Added `.is-invalid` Bootstrap class for visual feedback

---

## Security Features

- CSRF token protection on all forms
- Password hashing (Django default)
- Session-based authentication
- Inactive account protection
- Payment verification before account activation
