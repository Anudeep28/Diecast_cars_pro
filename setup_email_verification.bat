@echo off
echo ========================================
echo  Email Verification Setup
echo  DiecastCollector Pro
echo ========================================
echo.

REM Check if virtual environment exists
if not exist "myenv\Scripts\activate.bat" (
    echo ERROR: Virtual environment 'myenv' not found!
    echo Please make sure you're in the correct directory.
    pause
    exit /b 1
)

echo [Step 1] Activating virtual environment...
call myenv\Scripts\activate.bat

echo.
echo [Step 2] Creating database migrations...
python manage.py makemigrations inventory

echo.
echo [Step 3] Applying migrations to database...
python manage.py migrate

echo.
echo ========================================
echo  Setup Complete!
echo ========================================
echo.
echo Email verification has been set up successfully!
echo.
echo NEXT STEPS:
echo 1. Configure email settings in .env file
echo 2. Start the server: run_server.bat
echo 3. Test registration at: http://localhost:8000/register/
echo.
echo See EMAIL_VERIFICATION_SETUP.md for detailed instructions.
echo.
pause
