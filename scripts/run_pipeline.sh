#!/bin/bash
set -e

echo "Starting Backend API..."
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

echo "Starting Frontend App..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo "Systems are running! Press Ctrl+C to stop."

trap "echo 'Stopping all processes...'; kill $BACKEND_PID; kill $FRONTEND_PID; exit" SIGINT SIGTERM

wait
