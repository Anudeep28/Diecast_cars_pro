@echo off
echo Starting Django Application...

REM Check if virtual environment is activated
if not defined VIRTUAL_ENV (
    echo Activating virtual environment...
    call myenv\Scripts\activate.bat
) else (
    echo Virtual environment is already active.
)

REM Start the Django development server
echo Starting Django server...
python manage.py runserver

REM Keep the window open after server stops
echo.
echo Server has stopped. Press any key to exit.
pause > nul
