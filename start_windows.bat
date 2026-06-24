@echo off
title Douyin Viral Predictor

echo ==========================================
echo     Douyin Viral Predictor - Launcher
echo ==========================================
echo.
echo Press any key to start...
pause >nul

set SCRIPT_DIR=%~dp0
cd /d %SCRIPT_DIR%

echo [1/6] Checking environment...

if not exist ".env" (
    echo [ERROR] .env file not found!
    echo Creating .env from template...
    copy .env.example .env
    echo [INFO] .env file created. Please edit it with your API keys.
    pause
    exit /b 1
)

docker --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Starting with Docker...
    start "" "http://localhost:3000"
    docker-compose up --build
    pause
    exit /b 0
)

echo [INFO] Docker not found, using local mode...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not installed!
    echo Please install Python 3.11+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not installed!
    echo Please install Node.js 18+ from https://nodejs.org/
    pause
    exit /b 1
)

echo [OK] Environment OK

echo.
echo [2/6] Checking backend dependencies...
pip show content-studio >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing backend dependencies...
    pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple
)

echo [OK] Backend OK

echo.
echo [3/6] Checking frontend dependencies...
if not exist "frontend\node_modules" (
    echo [INFO] Installing frontend dependencies...
    cd frontend
    npm install
    cd ..
)

echo [OK] Frontend OK

echo.
echo [4/6] Starting backend service on port 8000...
start "Backend Server" cmd /k "cd /d %SCRIPT_DIR% && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload"

echo [INFO] Waiting for backend...
timeout /t 5 /nobreak >nul

echo.
echo [5/6] Starting frontend service on port 3000...
start "Frontend Server" cmd /k "cd /d %SCRIPT_DIR%frontend && npm run dev"

echo [INFO] Waiting for frontend...
timeout /t 8 /nobreak >nul

echo.
echo [6/6] Opening browser...
start "" "http://localhost:3000"

echo.
echo ==========================================
echo [SUCCESS] Services Started!
echo ==========================================
echo.
echo Frontend:      http://localhost:3000
echo Backend API:   http://localhost:8000
echo API Docs:      http://localhost:8000/docs
echo.
echo Two server windows are running:
echo - Backend Server (Port 8000)
echo - Frontend Server (Port 3000)
echo.
echo Press any key to close this window...
pause >nul