#!/bin/bash

# Legal AI System Stop Script
# This script stops the complete Local Legal AI system

echo "🛑 Stopping Local Legal AI System..."
echo "====================================="

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to stop a service by PID
stop_service() {
    local pid_file=$1
    local service_name=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        echo -n "Stopping $service_name (PID: $pid)... "
        
        if kill "$pid" 2>/dev/null; then
            echo -e "${GREEN}✓ Stopped${NC}"
            rm -f "$pid_file"
        else
            echo -e "${YELLOW}⚠ Process not found${NC}"
            rm -f "$pid_file"
        fi
    else
        echo -e "${YELLOW}No PID file found for $service_name${NC}"
    fi
}

# Stop services using saved PIDs
if [ -d "logs" ]; then
    stop_service "logs/backend.pid" "Backend"
    stop_service "logs/frontend.pid" "Frontend"
fi

# Kill any remaining processes (fallback)
echo -e "${YELLOW}Ensuring all processes are stopped...${NC}"
pkill -f "uvicorn.*backend" 2>/dev/null && echo -e "${GREEN}✓ Killed remaining backend processes${NC}" || true
pkill -f "streamlit.*frontend" 2>/dev/null && echo -e "${GREEN}✓ Killed remaining frontend processes${NC}" || true

# Wait a moment for processes to terminate
sleep 2

# Check if services are actually stopped
echo ""
echo "Verifying shutdown..."
if ! curl -s -f "http://localhost:8000/health" >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Backend stopped${NC}"
else
    echo -e "${RED}✗ Backend still running${NC}"
fi

if ! curl -s -f "http://localhost:8501/" >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Frontend stopped${NC}"
else
    echo -e "${RED}✗ Frontend still running${NC}"
fi

echo ""
echo -e "${GREEN}🛑 Local Legal AI System shutdown complete!${NC}" 