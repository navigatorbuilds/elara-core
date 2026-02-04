#!/bin/bash
# Called after tool use - updates presence timestamp
cd /home/neboo/elara-core
source venv/bin/activate
python -c "from daemon.presence import ping; ping()" 2>/dev/null &
