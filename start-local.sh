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

PYTHON_CMD=${PYTHON_CMD:-python3.10}

ensure_python_cmd() {
    if command -v "$PYTHON_CMD" >/dev/null 2>&1; then
        return
    fi

    echo "Required interpreter '$PYTHON_CMD' not found."
    if command -v brew >/dev/null 2>&1; then
        echo "Attempting to install python@3.10 via Homebrew..."
        if brew install python@3.10; then
            return
        fi
        echo "Homebrew installation failed. Please install python@3.10 manually and re-run." >&2
    else
        echo "Homebrew not found. Install python 3.10+ and set PYTHON_CMD accordingly." >&2
    fi
    exit 1
}

# --- Environment preparation ---
# Ensure user-level Python scripts (pip, uvicorn, etc.) are discoverable.
ensure_user_python_bin_on_path() {
    if command -v "$PYTHON_CMD" >/dev/null 2>&1; then
        local user_bin
        user_bin="$($PYTHON_CMD -m site --user-base 2>/dev/null)/bin"
        if [ -n "$user_bin" ] && [ -d "$user_bin" ]; then
            case ":$PATH:" in
                *":$user_bin:"*) ;;
                *) export PATH="$user_bin:$PATH" ;;
            esac
        fi
    fi
}

# Install pip if it's missing (helps first-time setups on fresh machines).
ensure_pip() {
    if "$PYTHON_CMD" -m pip --version >/dev/null 2>&1; then
        return
    fi

    echo "pip not found for $PYTHON_CMD. Attempting to install via ensurepip ..."
    if ! "$PYTHON_CMD" -m ensurepip --upgrade >/dev/null; then
        echo "Failed to install pip automatically. Please install pip for $PYTHON_CMD and re-run the script." >&2
        exit 1
    fi

    ensure_user_python_bin_on_path

    if ! "$PYTHON_CMD" -m pip --version >/dev/null 2>&1; then
        echo "pip installation succeeded but command still not found. Make sure your PATH includes $($PYTHON_CMD -m site --user-base)/bin." >&2
        exit 1
    fi
}

ensure_python_cmd
ensure_user_python_bin_on_path
ensure_pip

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

start_backend() {
    local max_attempts=5
    local attempt=1
    local port_cursor=$DEFAULT_BACKEND_PORT

    while (( attempt <= max_attempts )); do
        echo "Selecting backend port (attempt ${attempt}/${max_attempts})..."
        SELECTED_BACKEND_PORT=$(find_free_port "$port_cursor" 8100)
        if [ -z "$SELECTED_BACKEND_PORT" ]; then
            echo "Failed to find a free backend port in range ${DEFAULT_BACKEND_PORT}-8100" >&2
            exit 1
        fi
        export BACKEND_PORT="$SELECTED_BACKEND_PORT"

        echo "Starting backend server on port ${BACKEND_PORT} in the background using $PYTHON_CMD..."
        set -m
        "$PYTHON_CMD" -m uvicorn main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" &
        BACKEND_PID=$!
        set +m

        # Give uvicorn a moment to crash if the port is already in use
        sleep 1
        if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
            echo "Backend process exited immediately. Retrying with a different port..."
            attempt=$((attempt + 1))
            port_cursor=$((SELECTED_BACKEND_PORT + 1))
            continue
        fi

        echo "Waiting for backend to become ready on http://localhost:${BACKEND_PORT} ..."
        if wait_for_backend "$BACKEND_PORT" 50 0.2; then
            echo "Backend server started with PID: $BACKEND_PID. API is available at http://localhost:${BACKEND_PORT}"
            return 0
        fi

        echo "Backend did not become ready on port ${BACKEND_PORT}. Retrying..."
        if [ -n "$BACKEND_PID" ]; then
            kill -9 -$BACKEND_PID >/dev/null 2>&1 || true
            BACKEND_PID=""
        fi
        attempt=$((attempt + 1))
        port_cursor=$((SELECTED_BACKEND_PORT + 1))
    done

    echo "Unable to start backend after ${max_attempts} attempts." >&2
    exit 1
}

# Allow overrides
DEFAULT_BACKEND_PORT=${BACKEND_PORT:-8000}
DEFAULT_FRONTEND_PORT=${FRONTEND_PORT:-5173}

# --- Backend ---
echo "--- Setting up Python backend ---"
cd backend

echo "Installing Python dependencies from requirements.txt using $PYTHON_CMD..."
"$PYTHON_CMD" -m pip install --disable-pip-version-check --quiet -r requirements.txt

start_backend
cd ..


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
