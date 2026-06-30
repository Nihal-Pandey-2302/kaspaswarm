#!/bin/bash
#
# KaspaSwarm launcher — starts backend + frontend, waits for them to be healthy,
# prints the URLs, and shuts both down cleanly on Ctrl-C.
#
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# ── prerequisites ────────────────────────────────────────────
if [ ! -x backend/venv/bin/python3 ]; then
  echo "❌ Python venv not found at backend/venv. Run ./setup.sh first."
  exit 1
fi
if [ ! -d frontend/node_modules ]; then
  echo "❌ Frontend deps not installed. Run ./setup.sh first."
  exit 1
fi
if [ ! -f .env ]; then
  echo "⚠️  No .env found — creating from .env.example (defaults to simulation mode)."
  cp .env.example .env
fi

# ── read mode/port from .env (display only) ──────────────────
MODE=$(grep -E '^MOCK_MODE=' .env | head -1 | cut -d= -f2 | tr -d ' "')
API_PORT=$(grep -E '^API_PORT=' .env | head -1 | cut -d= -f2 | tr -d ' "')
API_PORT=${API_PORT:-8000}
if [ "$MODE" = "false" ]; then
  MODE_LABEL="🟢 LIVE (real Kaspa transactions)"
else
  MODE_LABEL="🟡 SIMULATION (in-memory, no node needed)"
fi

# ── clean up any stale processes ─────────────────────────────
pkill -f "main.py" 2>/dev/null
pkill -f "vite" 2>/dev/null
sleep 1

BACKEND_PID=""
FRONTEND_PID=""
cleanup() {
  echo ""
  echo "🛑 Stopping services..."
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
  exit 0
}
trap cleanup INT TERM

echo "🐝 KaspaSwarm  |  Mode: $MODE_LABEL"
echo "======================================"

# ── backend ──────────────────────────────────────────────────
echo "🚀 Starting backend (port $API_PORT)..."
( cd backend && exec ./venv/bin/python3 main.py ) > backend.log 2>&1 &
BACKEND_PID=$!

for _ in $(seq 1 40); do
  if curl -s "http://localhost:$API_PORT/" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "❌ Backend crashed on startup. Last log lines:"
    tail -n 20 backend.log
    exit 1
  fi
  sleep 1
done

# ── frontend ─────────────────────────────────────────────────
echo "🎨 Starting frontend..."
( cd frontend && exec npm run dev ) > frontend.log 2>&1 &
FRONTEND_PID=$!

FRONT_URL=""
for _ in $(seq 1 40); do
  FRONT_URL=$(grep -oE 'http://localhost:[0-9]+' frontend.log | head -1)
  [ -n "$FRONT_URL" ] && break
  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    echo "❌ Frontend crashed on startup. Last log lines:"
    tail -n 20 frontend.log
    cleanup
  fi
  sleep 1
done
[ -z "$FRONT_URL" ] && FRONT_URL="http://localhost:3000  (check frontend.log)"

echo ""
echo "✅ KaspaSwarm is running"
echo "   App:      $FRONT_URL"
echo "   Backend:  http://localhost:$API_PORT   ($MODE_LABEL)"
echo "   Logs:     backend.log / frontend.log"
echo ""
echo "Press [Ctrl-C] to stop both services."
wait
