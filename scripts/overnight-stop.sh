#!/bin/bash
# Stop the Elara Overnight thinking daemon gracefully.
# Sends SIGTERM — daemon will finish current round, then exit.

PID_FILE="$HOME/.claude/overnight/overnight.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "[Overnight] Stopping (PID $PID) — will finish current round"
    else
        echo "[Overnight] Not running (stale PID file)"
        rm -f "$PID_FILE"
    fi
else
    echo "[Overnight] Not running"
fi
