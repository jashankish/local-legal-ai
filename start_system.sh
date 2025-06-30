#!/bin/bash

# Legal AI System Startup Script
# This script starts the complete Local Legal AI system

set -e  # Exit on error

echo "🚀 Starting Local Legal AI System..."
echo "======================================"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to check if a service is running
check_service() {
    local url=$1
    local service_name=$2
    echo -n "Checking $service_name... "
    if curl -s -f "$url" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Running${NC}"
        return 0
    else
        echo -e "${RED}✗ Not running${NC}"
        return 1
    fi
}

# Function to wait for service to start
wait_for_service() {
    local url=$1
    local service_name=$2
    local max_attempts=30
    local attempt=1
    
    echo "Waiting for $service_name to start..."
    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "$url" >/dev/null 2>&1; then
            echo -e "${GREEN}✓ $service_name is ready!${NC}"
            return 0
        fi
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
    echo -e "\n${RED}✗ $service_name failed to start after $max_attempts attempts${NC}"
    return 1
}

# Check Python version
echo -e "${YELLOW}Checking Python version...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is required but not installed${NC}"
    exit 1
fi
python3 --version

# Check if we're in the right directory
if [ ! -f ".env" ] || [ ! -d "backend" ] || [ ! -d "frontend" ]; then
    echo -e "${RED}Error: Please run this script from the project root directory${NC}"
    exit 1
fi

# Set essential environment variables manually
echo -e "${YELLOW}Setting environment variables...${NC}"
export SECRET_KEY="fo0sfu4vsmqjuVn4Q4jxIWE8Pp3PB37_bpXJ4JevI1s"
export DEBUG="false"
export HOST="0.0.0.0"
export PORT="8000"
export JWT_ALGORITHM="HS256"
export ACCESS_TOKEN_EXPIRE_MINUTES="1440"
echo -e "${GREEN}✓ Environment variables set${NC}"

# Check if virtual environment exists and dependencies are installed
echo -e "${YELLOW}Checking dependencies...${NC}"
if ! python3 -c "import streamlit" 2>/dev/null; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip3 install -r requirements_phase4.txt
fi

# Kill any existing processes
echo -e "${YELLOW}Stopping any existing services...${NC}"
pkill -f "uvicorn.*backend" 2>/dev/null || true
pkill -f "streamlit.*frontend" 2>/dev/null || true
sleep 3

# Create logs directory if it doesn't exist
mkdir -p logs

# Start Backend Service
echo -e "${YELLOW}Starting Backend Service...${NC}"
nohup python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload > logs/backend.log 2>&1 &
BACKEND_PID=$!

# Wait for backend to be ready
if wait_for_service "http://localhost:8000/health" "Backend"; then
    echo -e "${GREEN}Backend started successfully (PID: $BACKEND_PID)${NC}"
else
    echo -e "${RED}Failed to start backend. Check logs/backend.log for details.${NC}"
    cat logs/backend.log | tail -10
    exit 1
fi

# Start Frontend Service
echo -e "${YELLOW}Starting Frontend Service...${NC}"
nohup streamlit run frontend/streamlit_app.py --server.port 8501 --server.headless true > logs/frontend.log 2>&1 &
FRONTEND_PID=$!

# Wait for frontend to be ready
if wait_for_service "http://localhost:8501/" "Frontend"; then
    echo -e "${GREEN}Frontend started successfully (PID: $FRONTEND_PID)${NC}"
else
    echo -e "${RED}Failed to start frontend. Check logs/frontend.log for details.${NC}"
    cat logs/frontend.log | tail -10
    exit 1
fi

# Final system check
echo ""
echo "======================================"
echo -e "${GREEN}🎉 System Status Check${NC}"
echo "======================================"

check_service "http://localhost:8000/health" "Backend API"
check_service "http://localhost:8501/" "Frontend UI"

echo ""
echo -e "${GREEN}✅ Local Legal AI System is ready!${NC}"
echo ""
echo "📊 Access Points:"
echo "  • Backend API: http://localhost:8000"
echo "  • Frontend UI: http://localhost:8501"
echo "  • API Docs: http://localhost:8000/docs"
echo ""
echo "📁 Log Files:"
echo "  • Backend: logs/backend.log"
echo "  • Frontend: logs/frontend.log"
echo ""
echo "🛑 To stop the system, run: ./stop_system.sh"
echo ""

# Save process IDs for easy shutdown
echo "$BACKEND_PID" > logs/backend.pid
echo "$FRONTEND_PID" > logs/frontend.pid

echo "Process IDs saved for clean shutdown." 