#!/bin/bash
# Elara Brain Control — start, stop, pause, resume, status
#
# Usage:
#   scripts/brain-control.sh start    # Start the brain scheduler
#   scripts/brain-control.sh stop     # Stop the brain scheduler (kills process)
#   scripts/brain-control.sh pause    # Pause thinking (keeps scheduler alive)
#   scripts/brain-control.sh resume   # Resume thinking
#   scripts/brain-control.sh status   # Show current state
#   scripts/brain-control.sh restart  # Stop + start

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OVERNIGHT_DIR="$HOME/.claude/overnight"
PID_FILE="$OVERNIGHT_DIR/scheduler.pid"
PAUSE_FILE="$OVERNIGHT_DIR/brain-pause"
LOG_FILE="$OVERNIGHT_DIR/overnight.log"
META_FILE="$OVERNIGHT_DIR/last-run-meta.json"

mkdir -p "$OVERNIGHT_DIR"

_is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            return 0
        else
            rm -f "$PID_FILE"
        fi
    fi
    return 1
}

_start() {
    if _is_running; then
        echo "[Brain] Already running (PID $(cat $PID_FILE))"
        return 0
    fi

    # Activate venv
    if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
        source "$SCRIPT_DIR/venv/bin/activate"
    fi

    cd "$SCRIPT_DIR"
    nohup "$SCRIPT_DIR/venv/bin/python3" -c "
from daemon.overnight.scheduler import BrainScheduler
BrainScheduler().run()
" >> "$LOG_FILE" 2>&1 &

    DAEMON_PID=$!
    sleep 2

    if _is_running; then
        echo "[Brain] Started (PID $(cat $PID_FILE))"
        echo "[Brain] Log: $LOG_FILE"
        # Remove pause file if it exists (fresh start = running)
        rm -f "$PAUSE_FILE"
    else
        echo "[Brain] Failed to start — check $LOG_FILE"
        tail -5 "$LOG_FILE" 2>/dev/null
        return 1
    fi
}

_stop() {
    if ! _is_running; then
        echo "[Brain] Not running"
        return 0
    fi

    PID=$(cat "$PID_FILE")
    kill "$PID"
    echo "[Brain] Stopping (PID $PID) — finishing current round..."

    # Wait up to 30s for graceful stop
    for i in $(seq 1 30); do
        if ! kill -0 "$PID" 2>/dev/null; then
            echo "[Brain] Stopped"
            rm -f "$PID_FILE"
            return 0
        fi
        sleep 1
    done

    # Force kill
    kill -9 "$PID" 2>/dev/null
    rm -f "$PID_FILE"
    echo "[Brain] Force killed"
}

_pause() {
    touch "$PAUSE_FILE"
    echo "[Brain] Paused — thinking disabled"
    echo "[Brain] To resume: $0 resume"
}

_resume() {
    if [ -f "$PAUSE_FILE" ]; then
        rm -f "$PAUSE_FILE"
        echo "[Brain] Resumed — thinking enabled"
    else
        echo "[Brain] Already running (not paused)"
    fi

    if ! _is_running; then
        echo "[Brain] Scheduler not running — starting it"
        _start
    fi
}

_status() {
    echo "=== Elara Brain Status ==="

    # Scheduler status
    if _is_running; then
        PID=$(cat "$PID_FILE")
        UPTIME=$(ps -o etime= -p "$PID" 2>/dev/null | tr -d ' ')
        echo "Scheduler: RUNNING (PID $PID, uptime: $UPTIME)"
    else
        echo "Scheduler: STOPPED"
    fi

    # Pause status
    if [ -f "$PAUSE_FILE" ]; then
        echo "Thinking:  PAUSED"
    else
        echo "Thinking:  ENABLED"
    fi

    # Last run
    if [ -f "$META_FILE" ]; then
        ENDED=$(python3 -c "import json; print(json.load(open('$META_FILE')).get('ended','?'))" 2>/dev/null)
        echo "Last run:  $ENDED"
    else
        echo "Last run:  (no record)"
    fi

    # GPU status
    echo ""
    echo "=== GPU Status ==="
    nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null || echo "(nvidia-smi not available)"

    # Recent log
    echo ""
    echo "=== Recent Log (last 5 non-waiting entries) ==="
    grep -v "Waiting —" "$LOG_FILE" 2>/dev/null | tail -5
}

case "${1:-status}" in
    start)   _start ;;
    stop)    _stop ;;
    pause)   _pause ;;
    resume)  _resume ;;
    restart) _stop && sleep 2 && _start ;;
    status)  _status ;;
    *)
        echo "Usage: $0 {start|stop|pause|resume|restart|status}"
        exit 1
        ;;
esac
