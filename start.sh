#!/bin/bash

# Kill any existing processes
pkill -f "python3 main.py"
pkill -f "vite"

# Start Backend
echo "🚀 Starting KaspaSwarm Backend..."
cd backend
../backend/venv/bin/python3 main.py > ../backend.log 2>&1 &
BACKEND_PID=$!
cd ..

# Start Frontend
echo "🎨 Starting KaspaSwarm Frontend..."
cd frontend
npm run dev > ../frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

echo "✅ Services started!"
echo "   - Backend PID: $BACKEND_PID"
echo "   - Frontend PID: $FRONTEND_PID"
echo "   - Logs: backend.log, frontend.log"
echo "   - App URL: Check frontend.log for port (usually 3000 or 3001)"

# Wait for user to exit
read -p "Press [Enter] to stop servers..."

kill $BACKEND_PID
kill $FRONTEND_PID
echo "🛑 Services stopped."
