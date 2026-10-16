#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "Starting backend (port 8001)..."
cd "$ROOT/backend"
source .venv/bin/activate
PYTHONPATH="$ROOT/backend" uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload &
BACKEND_PID=$!

echo "Starting frontend (port 3000)..."
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop both."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
