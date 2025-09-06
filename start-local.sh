#!/bin/bash

# This script automates the startup of the local development environment for the
# AI-Powered Observability Demo Generator on macOS.
#
# It performs the following steps:
# 1. Sets up and starts the Python/FastAPI backend in the background.
# 2. Sets up and starts the Node.js/React frontend in the foreground.
# 3. Sets up a trap to automatically shut down the backend when you stop the script (Ctrl+C).
#
# Prerequisites:
# - Node.js and npm
# - Python 3.9+ and pip

set -e # Exit immediately if a command fails.

# --- Cleanup Function ---
# This function is triggered on script exit to ensure the backend process is terminated.
cleanup() {
    echo -e "\n\nGracefully shutting down services..."
    if [ -n "$BACKEND_PID" ]; then
        echo "Stopping backend server (PID: $BACKEND_PID)..."
        # Kill the process group to ensure all child processes (like reload workers) are terminated.
        kill -9 -$BACKEND_PID > /dev/null 2>&1
    fi
    echo "Shutdown complete."
    exit 0
}

# Trap signals to ensure cleanup runs
trap cleanup SIGINT SIGTERM EXIT

# --- Helper functions ---
is_port_in_use() {
    local port=$1
    lsof -iTCP:${port} -sTCP:LISTEN >/dev/null 2>&1
}

find_free_port() {
    local start_port=$1
    local end_port=$2
    for ((port=start_port; port<=end_port; port++)); do
        if ! is_port_in_use "$port"; then
            echo "$port"
            return 0
        fi
    done
    return 1
}

wait_for_backend() {
    local port=$1
    local retries=${2:-30}
    local delay=${3:-0.2}
    for ((i=1; i<=retries; i++)); do
        if curl -s "http://127.0.0.1:${port}/" >/dev/null 2>&1; then
            return 0
        fi
        sleep "$delay"
    done
    return 1
}

# Allow overrides
DEFAULT_BACKEND_PORT=${BACKEND_PORT:-8000}
DEFAULT_FRONTEND_PORT=${FRONTEND_PORT:-5173}

# --- Backend ---
echo "--- Setting up Python backend ---"
cd backend

echo "Installing Python dependencies from requirements.txt..."
pip install --disable-pip-version-check --quiet -r requirements.txt

echo "Selecting backend port..."
SELECTED_BACKEND_PORT=$(find_free_port "$DEFAULT_BACKEND_PORT" 8100)
if [ -z "$SELECTED_BACKEND_PORT" ]; then
    echo "Failed to find a free backend port in range ${DEFAULT_BACKEND_PORT}-8100" >&2
    exit 1
fi
export BACKEND_PORT="$SELECTED_BACKEND_PORT"

echo "Starting backend server on port ${BACKEND_PORT} in the background..."
# set -m allows job control, which is important for killing the process group
set -m
uvicorn main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" &
BACKEND_PID=$!
set +m
cd ..

echo "Waiting for backend to become ready on http://localhost:${BACKEND_PORT} ..."
if ! wait_for_backend "$BACKEND_PORT" 50 0.2; then
    echo "Backend did not become ready on port ${BACKEND_PORT}" >&2
    exit 1
fi
echo "Backend server started with PID: $BACKEND_PID. API is available at http://localhost:${BACKEND_PORT}"


# --- Frontend ---
echo -e "\n--- Setting up React frontend ---"
cd frontend

echo "Installing Node.js dependencies from package.json..."
npm install --silent

echo "Selecting frontend port..."
SELECTED_FRONTEND_PORT=$(find_free_port "$DEFAULT_FRONTEND_PORT" 5200)
if [ -z "$SELECTED_FRONTEND_PORT" ]; then
    echo "Failed to find a free frontend port in range ${DEFAULT_FRONTEND_PORT}-5200" >&2
    exit 1
fi
export FRONTEND_PORT="$SELECTED_FRONTEND_PORT"

echo -e "\nStarting frontend dev server on port ${FRONTEND_PORT} (backend proxied at /api -> http://localhost:${BACKEND_PORT})... (Press Ctrl+C to stop everything)"
# The 'trap' will handle shutting down the backend when this command exits.
BACKEND_PORT="$BACKEND_PORT" FRONTEND_PORT="$FRONTEND_PORT" npm run dev -- --port "$FRONTEND_PORT"