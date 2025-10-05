@echo off
REM ============================================================
REM DiecastCollector Pro - Manual Alert Sender
REM ============================================================
echo.
echo ============================================================
echo  DiecastCollector Pro - Delivery Alert Sender
echo ============================================================
echo.

REM Change to project directory
cd /d "%~dp0"

REM Check if virtual environment exists
if not exist "myenv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found!
    echo Please ensure 'myenv' directory exists in the project root.
    pause
    exit /b 1
)

REM Activate virtual environment
echo Activating virtual environment...
call myenv\Scripts\activate.bat

REM Check for options
if "%1"=="--dry-run" (
    echo Running in DRY RUN mode - no emails will be sent
    python manage.py send_delivery_alerts --dry-run
) else if "%1"=="--user" (
    if "%2"=="" (
        echo ERROR: Please provide a username after --user
        echo Example: send_alerts.bat --user john_doe
        pause
        exit /b 1
    )
    echo Sending alerts to user: %2
    python manage.py send_delivery_alerts --user=%2
) else if "%1"=="--help" (
    echo.
    echo Usage: send_alerts.bat [OPTIONS]
    echo.
    echo Options:
    echo   --dry-run          Preview what would be sent without sending emails
    echo   --user USERNAME    Send alerts to specific user only
    echo   --help             Show this help message
    echo   [no options]       Send alerts to all users with delivery alerts
    echo.
    echo Examples:
    echo   send_alerts.bat
    echo   send_alerts.bat --dry-run
    echo   send_alerts.bat --user john_doe
    echo.
    pause
    exit /b 0
) else (
    echo Sending delivery alerts to all users...
    python manage.py send_delivery_alerts
)

echo.
echo ============================================================
echo.
pause
