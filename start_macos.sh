#!/bin/bash

echo "=========================================="
echo "    Douyin Viral Predictor - Launch Script"
echo "=========================================="
echo ""

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$SCRIPT_DIR"

echo "[1/6] Checking environment..."

if [ ! -f ".env" ]; then
    echo "[ERROR] .env file not found!"
    echo "Creating .env from template..."
    cp .env.example .env
    echo "[INFO] .env file created. Please edit it with your API keys."
    read -p "Press Enter to exit..."
    exit 0
fi

if command -v docker &> /dev/null && command -v docker-compose &> /dev/null; then
    echo "[INFO] Docker detected, starting with Docker..."
    open "http://localhost:3000"
    docker-compose up --build
    exit 0
fi

echo "[INFO] Docker not found, using local mode..."

if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "[ERROR] Python not installed!"
    echo "Please install Python 3.11+ from https://www.python.org/downloads/"
    read -p "Press Enter to exit..."
    exit 1
fi

if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js not installed!"
    echo "Please install Node.js 18+ from https://nodejs.org/"
    read -p "Press Enter to exit..."
    exit 1
fi

PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD="python"
fi

echo "[OK] Environment OK"

echo ""
echo "[2/6] Checking backend dependencies..."
if ! $PYTHON_CMD -c "import content_studio" &> /dev/null; then
    echo "[INFO] Installing backend dependencies..."
    pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple
fi

echo "[OK] Backend OK"

echo ""
echo "[3/6] Checking frontend dependencies..."
if [ ! -d "frontend/node_modules" ]; then
    echo "[INFO] Installing frontend dependencies..."
    cd frontend
    npm install
    cd ..
fi

echo "[OK] Frontend OK"

echo ""
echo "[4/6] Starting backend service on port 8000..."
osascript -e 'tell application "Terminal" to do script "cd '\"$SCRIPT_DIR\"' && '$PYTHON_CMD' -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload"'

echo "[INFO] Waiting for backend..."
sleep 5

echo ""
echo "[5/6] Starting frontend service on port 3000..."
osascript -e 'tell application "Terminal" to do script "cd '\"$SCRIPT_DIR\"'/frontend && npm run dev"'

echo "[INFO] Waiting for frontend..."
sleep 8

echo ""
echo "[6/6] Opening browser..."
open "http://localhost:3000"

echo ""
echo "=========================================="
echo "[SUCCESS] Services Started!"
echo "=========================================="
echo ""
echo "Frontend:      http://localhost:3000"
echo "Backend API:   http://localhost:8000"
echo "API Docs:      http://localhost:8000/docs"
echo ""
echo "Two terminal windows should be open:"
echo "- Backend Server (Port 8000)"
echo "- Frontend Server (Port 3000)"
echo ""
echo "To stop the services:"
echo " 1. Close both terminal windows"
echo " 2. Or press Ctrl+C in each window"
echo ""
read -p "Press Enter to close this window..."