@echo off
REM ============================================================
REM DiecastCollector Pro - Notification System Setup
REM ============================================================
echo.
echo ============================================================
echo  Setting up Notification System
echo ============================================================
echo.

cd /d "%~dp0"

REM Check if virtual environment exists
if not exist "myenv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found!
    echo Please ensure 'myenv' directory exists.
    pause
    exit /b 1
)

echo [1/3] Activating virtual environment...
call myenv\Scripts\activate.bat

echo.
echo [2/3] Creating database migrations...
python manage.py makemigrations inventory --name add_notification_preferences

echo.
echo [3/3] Running migrations...
python manage.py migrate

echo.
echo ============================================================
echo  Setup Complete!
echo ============================================================
echo.
echo Next steps:
echo 1. Configure email settings in .env file
echo 2. Test with: python manage.py send_delivery_alerts --dry-run
echo 3. Set up Windows Task Scheduler for daily alerts
echo.
echo See NOTIFICATION_SYSTEM_GUIDE.md for detailed instructions.
echo.
pause
