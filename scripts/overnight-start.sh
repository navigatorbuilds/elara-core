#!/bin/bash
# Start the Elara Overnight thinking daemon in background.
#
# Usage:
#   scripts/overnight-start.sh                    # auto mode
#   scripts/overnight-start.sh --mode exploratory # force exploratory
#   scripts/overnight-start.sh --mode directed    # force directed

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$HOME/.claude/overnight/overnight.pid"
LOG_FILE="$HOME/.claude/overnight/overnight.log"

# Create dir if needed
mkdir -p "$HOME/.claude/overnight"

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "[Overnight] Already running (PID $PID)"
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
nohup "$SCRIPT_DIR/venv/bin/python3" -m daemon.overnight "$@" >> "$LOG_FILE" 2>&1 &
DAEMON_PID=$!

# Wait for PID file (up to 5 seconds — overnight takes a moment to init)
for i in 1 2 3 4 5; do
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        echo "[Overnight] Started (PID $PID)"
        echo "[Overnight] Log: $LOG_FILE"
        echo "[Overnight] Findings will be in: ~/.claude/overnight/$(date +%Y-%m-%d)/"
        exit 0
    fi
    sleep 1
done

# Check if process is still alive even without PID file
if kill -0 "$DAEMON_PID" 2>/dev/null; then
    echo "[Overnight] Started (PID $DAEMON_PID) — PID file delayed"
    echo "[Overnight] Log: $LOG_FILE"
else
    echo "[Overnight] Failed to start — check $LOG_FILE"
    tail -5 "$LOG_FILE" 2>/dev/null
    exit 1
fi
