#!/bin/bash
# Called when session ends - records session stats
cd /home/neboo/elara-core
source venv/bin/activate
python -c "from daemon.presence import end_session; end_session()" 2>/dev/null &
