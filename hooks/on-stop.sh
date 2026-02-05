#!/bin/bash
# Called when session ends - records session stats and saves context
cd /home/neboo/elara-core
source venv/bin/activate

# End presence session
python -c "from daemon.presence import end_session; end_session()" 2>/dev/null &

# Save context for quick resume (runs in background, non-blocking)
# Context is passed via environment or defaults to "session ended"
python -c "from daemon.context import save_context; save_context(last_exchange='session ended')" 2>/dev/null &
