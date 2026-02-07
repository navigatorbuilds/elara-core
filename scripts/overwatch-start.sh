#!/bin/bash
# Start the Elara Overwatch daemon in background.

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$HOME/.claude/elara-overwatch.pid"

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "[Overwatch] Already running (PID $PID)"
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

# Activate venv if it exists
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Start daemon using venv python directly
cd "$SCRIPT_DIR"
nohup "$SCRIPT_DIR/venv/bin/python3" -m daemon.overwatch >> "$HOME/.claude/elara-overwatch.log" 2>&1 &
DAEMON_PID=$!

# Wait for PID file (up to 3 seconds)
for i in 1 2 3; do
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        echo "[Overwatch] Started (PID $PID)"
        exit 0
    fi
    sleep 1
done

# Check if process is still alive even without PID file
if kill -0 "$DAEMON_PID" 2>/dev/null; then
    echo "[Overwatch] Started (PID $DAEMON_PID) — PID file delayed"
else
    echo "[Overwatch] Failed to start — check ~/.claude/elara-overwatch.log"
    exit 1
fi
