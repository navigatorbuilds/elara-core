#!/bin/bash
# Check Overwatch daemon status.

PID_FILE="/tmp/elara-overwatch.pid"
LOG_FILE="$HOME/.claude/elara-overwatch.log"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "[Overwatch] Running (PID $PID)"
        if [ -f "$LOG_FILE" ]; then
            echo "--- Last 5 log entries ---"
            tail -5 "$LOG_FILE"
        fi
    else
        echo "[Overwatch] Not running (stale PID)"
        rm -f "$PID_FILE"
    fi
else
    echo "[Overwatch] Not running"
fi
