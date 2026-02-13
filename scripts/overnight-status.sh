#!/bin/bash
# Check Overnight thinking daemon status + recent output.

PID_FILE="$HOME/.claude/overnight/overnight.pid"
LOG_FILE="$HOME/.claude/overnight/overnight.log"
LATEST="$HOME/.claude/overnight/latest-findings.md"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "[Overnight] Running (PID $PID)"
        if [ -f "$LOG_FILE" ]; then
            echo "--- Last 10 log entries ---"
            tail -10 "$LOG_FILE"
        fi
    else
        echo "[Overnight] Not running (stale PID)"
        rm -f "$PID_FILE"
    fi
else
    echo "[Overnight] Not running"
fi

# Show latest findings info
if [ -f "$LATEST" ]; then
    echo ""
    echo "--- Latest findings ---"
    echo "File: $LATEST"
    echo "Size: $(wc -c < "$LATEST") bytes, $(wc -l < "$LATEST") lines"
    echo "Modified: $(stat -c '%y' "$LATEST" 2>/dev/null || stat -f '%Sm' "$LATEST" 2>/dev/null)"
    echo ""
    echo "First 5 lines:"
    head -5 "$LATEST"
fi
