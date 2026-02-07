#!/bin/bash
# Called after tool use - updates presence timestamp
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"
python -c "from daemon.presence import ping; ping()" 2>/dev/null &
