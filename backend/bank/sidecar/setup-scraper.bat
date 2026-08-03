@echo off
cd /d "%~dp0"
echo ============================================
echo  Bank Scraper Sidecar - Setup
echo ============================================
echo.
echo This builds israeli-bank-scrapers from an unmerged fork that adds
echo Hapoalim OTP/2FA support (PR eshaham/israeli-bank-scrapers#1084,
echo branch avivghilai/israeli-bank-scrapers#feat/hapoalim-2fa-device-trust).
echo It ships as source only, so it has to be built locally.
echo.

if not exist .vendor mkdir .vendor
if exist .vendor\israeli-bank-scrapers-fork (
    echo Fork already cloned, skipping clone.
) else (
    echo [1/3] Cloning the fork...
    git clone --quiet --branch feat/hapoalim-2fa-device-trust --depth 1 https://github.com/avivghilai/israeli-bank-scrapers.git .vendor\israeli-bank-scrapers-fork
    if errorlevel 1 (
        echo ERROR: git clone failed. Is git installed and on PATH?
        pause
        exit /b 1
    )
)

echo [2/3] Installing and building the fork...
cd .vendor\israeli-bank-scrapers-fork
call npm install
if errorlevel 1 (
    echo ERROR: npm install failed inside the fork.
    pause
    exit /b 1
)
call npm run build
if errorlevel 1 (
    echo ERROR: build failed inside the fork.
    pause
    exit /b 1
)
cd ..\..

echo [3/3] Installing the sidecar (points at the built fork)...
call npm install
if errorlevel 1 (
    echo ERROR: npm install failed in the sidecar.
    pause
    exit /b 1
)

echo.
echo Done. The scraper provider is ready to use.
pause
