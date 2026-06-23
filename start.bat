@echo off
cd /d "%~dp0"
echo Starting Expense Tracker...
echo.

start "Expense Tracker - Backend (do not close)" cmd /k "cd backend && call .venv\Scripts\activate.bat && uvicorn main:app --reload --port 8000"
start "Expense Tracker - Frontend (do not close)" cmd /k "cd frontend && npm run dev"

timeout /t 5 /nobreak >nul
start http://localhost:5173

echo Two new black windows just opened - leave them running while you use the app.
echo Your browser should now be open at http://localhost:5173
echo.
echo When you're done, just close those two black windows.
echo You can close this window now.
pause
