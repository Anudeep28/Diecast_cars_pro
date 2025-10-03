"""
Test Email Script for Gmail SMTP Configuration
================================================
This script helps you verify that Gmail SMTP is configured correctly.

Usage:
    python test_email.py recipient@example.com

Or run without arguments to use your own email as recipient.
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'diecastcollector.settings')
django.setup()

from django.core.mail import send_mail
from django.conf import settings


def test_email(recipient=None):
    """Send a test email to verify SMTP configuration."""
    
    print("\n" + "="*60)
    print("Gmail SMTP Configuration Test")
    print("="*60)
    
    # Display current email configuration
    print(f"\n📧 Email Backend: {settings.EMAIL_BACKEND}")
    
    if hasattr(settings, 'EMAIL_HOST'):
        print(f"📬 Email Host: {settings.EMAIL_HOST}")
        print(f"🔌 Email Port: {settings.EMAIL_PORT}")
        print(f"🔒 Use TLS: {settings.EMAIL_USE_TLS}")
        print(f"👤 Email User: {settings.EMAIL_HOST_USER}")
        print(f"📨 Default From: {settings.DEFAULT_FROM_EMAIL}")
    else:
        print("⚠️  Email settings not configured!")
        print("\nPlease configure Gmail SMTP in your .env file:")
        print("   GMAIL_USER=your-email@gmail.com")
        print("   GMAIL_APP_PASSWORD=your-16-char-app-password")
        print("\nSee GMAIL_SMTP_SETUP.md for detailed instructions.")
        return False
    
    # Determine recipient
    if recipient is None:
        if hasattr(settings, 'EMAIL_HOST_USER') and settings.EMAIL_HOST_USER:
            recipient = settings.EMAIL_HOST_USER
            print(f"\n📮 No recipient specified, using sender email: {recipient}")
        else:
            print("\n❌ Error: No recipient email specified and EMAIL_HOST_USER not set")
            print("Usage: python test_email.py recipient@example.com")
            return False
    else:
        print(f"\n📮 Recipient: {recipient}")
    
    # Prepare test email
    subject = "✅ Gmail SMTP Test - Diecast Collector App"
    message = """
Hello!

This is a test email from your Diecast Collector Django application.

If you're reading this, it means:
✅ Gmail SMTP is configured correctly
✅ App Password is working
✅ Email backend is functional

You can now send emails from your application!

---
Diecast Collector App
Powered by Django + Gmail SMTP
"""
    
    from_email = settings.DEFAULT_FROM_EMAIL
    
    print("\n🚀 Sending test email...")
    print(f"   Subject: {subject}")
    print(f"   From: {from_email}")
    print(f"   To: {recipient}")
    
    try:
        # Send the email
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[recipient],
            fail_silently=False,
        )
        
        print("\n✅ SUCCESS! Test email sent successfully!")
        print(f"\n📬 Check your inbox at: {recipient}")
        print("   (Also check spam/junk folder if you don't see it)")
        print("\n" + "="*60)
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: Failed to send email")
        print(f"   Error type: {type(e).__name__}")
        print(f"   Error message: {str(e)}")
        print("\n🔍 Troubleshooting tips:")
        print("   1. Check your GMAIL_USER is correct in .env")
        print("   2. Verify GMAIL_APP_PASSWORD is the 16-char App Password (no spaces)")
        print("   3. Make sure you're using App Password, not regular password")
        print("   4. Ensure 2-Factor Authentication is enabled on your Gmail account")
        print("   5. Try generating a new App Password")
        print("\n📖 See GMAIL_SMTP_SETUP.md for detailed setup instructions")
        print("\n" + "="*60)
        return False


if __name__ == "__main__":
    # Get recipient from command line argument or use None
    recipient_email = sys.argv[1] if len(sys.argv) > 1 else None
    
    # Run the test
    success = test_email(recipient_email)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)
