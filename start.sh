#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "═══════════════════════════════════════════════"
echo "  Repo Visualizer — Full Stack Launcher"
echo "═══════════════════════════════════════════════"

# ─── 1. Python Backend ───
echo ""
echo "▸ Starting FastAPI backend on :8000 ..."
if [ -d "server/.venv" ] && [ -f "server/.venv/bin/uvicorn" ]; then
  server/.venv/bin/uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload &
elif python3 -m venv server/.venv 2>/dev/null; then
  server/.venv/bin/pip install -q -r server/requirements.txt
  server/.venv/bin/uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload &
else
  # venv unavailable — use system python directly
  rm -rf server/.venv 2>/dev/null || true
  pip3 install --break-system-packages -q -r server/requirements.txt 2>/dev/null || true
  python3 -m uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload &
fi
BACKEND_PID=$!

# ─── 2. Dashboard ───
echo "▸ Starting Visualization Dashboard on :5173 ..."
cd dashboard
if [ ! -d "node_modules" ]; then
  npm install --silent
fi
npm run dev &
DASHBOARD_PID=$!
cd ..

# ─── 3. Demo App ───
echo "▸ Starting Demo App on :3001 ..."
cd demo-app
if [ ! -d "node_modules" ]; then
  npm install --silent
fi
npm run dev &
DEMO_PID=$!
cd ..

# ─── 4. Initial scan of the demo app ───
echo ""
echo "▸ Waiting for backend to start..."
sleep 3
DEMO_PATH="$(cd demo-app && pwd)"
curl -s -X POST http://localhost:8000/api/scan \
  -H "Content-Type: application/json" \
  -d "{\"repoPath\": \"$DEMO_PATH\"}" || true

echo ""
echo "═══════════════════════════════════════════════"
echo "  ✓ All services running!"
echo ""
echo "  Dashboard:  http://localhost:5173"
echo "  Demo App:   http://localhost:3001"
echo "  Backend:    http://localhost:8000/api/health"
echo ""
echo "  Press Ctrl+C to stop all services."
echo "═══════════════════════════════════════════════"

# Cleanup on exit
cleanup() {
  echo ""
  echo "Shutting down..."
  kill $BACKEND_PID $DASHBOARD_PID $DEMO_PID 2>/dev/null || true
  wait 2>/dev/null
}
trap cleanup EXIT INT TERM

# Wait for all background processes
wait
