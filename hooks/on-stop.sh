#!/bin/bash
# Called when session ends - records session stats and saves context
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

# End presence session
python -c "from daemon.presence import end_session; end_session()" 2>/dev/null &

# Save context for quick resume (runs in background, non-blocking)
# Context is passed via environment or defaults to "session ended"
python -c "from daemon.context import save_context; save_context(last_exchange='session ended')" 2>/dev/null &

# Touch session marker so brain scheduler knows we just left
touch "$HOME/.claude/elara-session-ended" 2>/dev/null &
