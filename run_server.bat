@echo off
echo Starting Django Application...

REM Run environment check script
echo Checking environment setup...
python ensure_environment.py
if %ERRORLEVEL% NEQ 0 (
    echo Environment setup failed. Please activate virtual environment manually.
    echo Command: myenv\Scripts\activate.bat
    pause > nul
    exit /b 1
)

REM Check if virtual environment is activated
if not defined VIRTUAL_ENV (
    echo Activating virtual environment...
    call myenv\Scripts\activate.bat
) else (
    echo Virtual environment is already active.
)

REM Install required packages from requirements.txt inside virtual environment
echo Installing/updating required packages from requirements.txt...
call myenv\Scripts\python -m pip install --upgrade pip
call myenv\Scripts\python -m pip install -r requirements.txt

REM Start the Django development server
echo Starting Django server...
python manage.py runserver

REM Keep the window open after server stops
echo.
echo Server has stopped. Press any key to exit.
pause > nul
