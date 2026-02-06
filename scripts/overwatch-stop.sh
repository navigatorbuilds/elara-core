#!/bin/bash
# Stop the Elara Overwatch daemon.

PID_FILE="/tmp/elara-overwatch.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "[Overwatch] Stopped (PID $PID)"
    else
        echo "[Overwatch] Not running (stale PID file)"
        rm -f "$PID_FILE"
    fi
else
    echo "[Overwatch] Not running"
fi

# Clean up inject file
rm -f /tmp/elara-overwatch-inject.md
