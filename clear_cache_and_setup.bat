@echo off
echo ========================================
echo  Clearing Python Cache and Setting Up
echo  Email Verification
echo ========================================
echo.

echo [Step 1] Clearing Python cache files...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
del /s /q *.pyc 2>nul
echo Cache cleared!

echo.
echo [Step 2] Activating virtual environment...
call myenv\Scripts\activate.bat

echo.
echo [Step 3] Creating database migrations...
python manage.py makemigrations inventory

echo.
echo [Step 4] Applying migrations to database...
python manage.py migrate

echo.
echo ========================================
echo  Setup Complete!
echo ========================================
echo.
echo You can now start the server with:
echo    run_server.bat
echo.
echo Or test registration at:
echo    http://localhost:8000/register/
echo.
pause
