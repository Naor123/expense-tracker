@echo off
cd /d "%~dp0"
echo ============================================
echo  Expense Tracker - First Time Setup
echo ============================================
echo.
echo This will take a minute or two. Just wait for it to finish.
echo.

echo [1/2] Setting up the backend (Python)...
cd backend
python -m venv .venv
if errorlevel 1 (
    echo.
    echo ERROR: Python was not found. Please install Python first - see README.md.
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
pip install -r requirements.txt
if not exist .env copy .env.example .env
cd ..

echo.
echo [2/2] Setting up the frontend (Node.js)...
cd frontend
npm install
if errorlevel 1 (
    echo.
    echo ERROR: Node.js was not found. Please install Node.js first - see README.md.
    pause
    exit /b 1
)
if not exist .env copy .env.example .env
cd ..

echo.
echo ============================================
echo  Setup complete!
echo ============================================
echo.
echo Next step: double-click start.bat to launch the app.
echo.
echo (Optional: the "email me an insight" button needs some extra
echo  setup in backend\.env - see README.md. Everything else works
echo  without it.)
echo.
pause
