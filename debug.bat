@echo off
title Douyin Viral Predictor - Debug Mode

echo ==========================================
echo     Douyin Viral Predictor - Debug Mode
echo ==========================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo [DEBUG] Step 1: Check .env file
if exist ".env" (
    echo [OK] .env file exists
) else (
    echo [ERROR] .env file not found
    pause
    exit /b 1
)
pause

echo.
echo [DEBUG] Step 2: Check Docker
docker --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Docker detected
) else (
    echo [INFO] Docker not found, will use local mode
)
pause

echo.
echo [DEBUG] Step 3: Check Python
python --version
if %errorlevel% equ 0 (
    echo [OK] Python OK
) else (
    echo [ERROR] Python failed
    pause
    exit /b 1
)
pause

echo.
echo [DEBUG] Step 4: Check Node.js
node --version
if %errorlevel% equ 0 (
    echo [OK] Node.js OK
) else (
    echo [ERROR] Node.js failed
    pause
    exit /b 1
)
pause

echo.
echo [DEBUG] Step 5: Check backend dependencies
pip show content-studio
if %errorlevel% equ 0 (
    echo [OK] Backend dependencies OK
) else (
    echo [INFO] Need to install backend dependencies
)
pause

echo.
echo [DEBUG] Step 6: Check frontend dependencies
if exist "%SCRIPT_DIR%\frontend\node_modules" (
    echo [OK] Frontend dependencies OK
) else (
    echo [INFO] Need to install frontend dependencies
)
pause

echo.
echo [SUCCESS] All checks passed!
echo Press any key to close...
pause