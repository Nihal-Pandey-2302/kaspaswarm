#!/bin/bash

# KaspaSwarm Quick Start Script

set -e

echo "🐝 KaspaSwarm - Quick Start"
echo "======================================"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo -e "${BLUE}Checking Python version...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}Python 3 not found. Please install Python 3.11+${NC}"
    exit 1
fi

python_version=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo -e "${GREEN}✓ Python $python_version found${NC}"

# Check Node.js version
echo -e "${BLUE}Checking Node.js version...${NC}"
if ! command -v node &> /dev/null; then
    echo -e "${YELLOW}Node.js not found. Please install Node.js 18+${NC}"
    exit 1
fi

node_version=$(node --version)
echo -e "${GREEN}✓ Node.js $node_version found${NC}"

# Backend setup
echo ""
echo -e "${BLUE}Setting up backend...${NC}"
cd backend

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing Python dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo -e "${GREEN}✓ Backend setup complete${NC}"

# Create .env if it doesn't exist
cd ..
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo -e "${GREEN}✓ Created .env file${NC}"
fi

# Frontend setup
echo ""
echo -e "${BLUE}Setting up frontend...${NC}"
cd frontend

if [ ! -d "node_modules" ]; then
    echo "Installing Node.js dependencies..."
    npm install
else
    echo "Node modules already installed"
fi

echo -e "${GREEN}✓ Frontend setup complete${NC}"

# Success
cd ..
echo ""
echo "======================================"
echo -e "${GREEN}✅ Setup complete!${NC}"
echo ""
echo "Fastest way to run everything:"
echo "  ./start.sh        # starts backend + frontend, prints the app URL"
echo ""
echo "Or run them separately:"
echo "  Terminal 1:  cd backend && python main.py"
echo "  Terminal 2:  cd frontend && npm run dev"
echo ""
echo -e "${YELLOW}Simulation mode runs out of the box (MOCK_MODE=true).${NC}"
echo "For LIVE on-chain mode, edit .env (MOCK_MODE=false + COORDINATOR_*"
echo "+ AGENT_MASTER_SEED), start a synced kaspad node, then:"
echo "  python backend/fund_agents.py fund 25   # fund solver wallets"
echo "  python backend/live_test.py             # verify the on-chain bus"
echo "======================================"
