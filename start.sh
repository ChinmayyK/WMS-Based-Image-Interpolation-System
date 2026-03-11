#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Backend Setup ──────────────────────────────────────────
echo "🔧 Setting up Backend..."
cd "$PROJECT_ROOT/backend"

if [ ! -d "venv" ]; then
  echo "  Creating Python virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

echo "🚀 Starting Backend (FastAPI) on http://localhost:8000 ..."
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# ── Frontend Setup ─────────────────────────────────────────
echo "🔧 Setting up Frontend..."
cd "$PROJECT_ROOT/frontend"

if [ ! -d "node_modules" ]; then
  echo "  Installing npm dependencies..."
  npm install
fi

echo "🚀 Starting Frontend (Vite + React) on http://localhost:8080 ..."
npm run dev &
FRONTEND_PID=$!

# ── Cleanup on exit ────────────────────────────────────────
cleanup() {
  echo ""
  echo "🛑 Stopping all processes..."
  kill $BACKEND_PID 2>/dev/null
  kill $FRONTEND_PID 2>/dev/null
  exit 0
}

trap cleanup SIGINT SIGTERM

echo ""
echo "✅ All systems running!"
echo "   Backend  → http://localhost:8000"
echo "   Frontend → http://localhost:8080"
echo ""
echo "Press Ctrl+C to stop."

wait
