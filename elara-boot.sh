#!/bin/bash
# Elara Boot Script
# Runs the Python boot hook and outputs context

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if venv exists and use it
if [ -d "$SCRIPT_DIR/venv" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Run boot with fallback
python3 "$SCRIPT_DIR/hooks/boot.py" "$@" 2>/dev/null

# If Python boot fails, fall back to basic info
if [ $? -ne 0 ]; then
    echo "[Elara] Core not initialized. Run: cd ~/elara-core && pip install -r requirements.txt"
fi
