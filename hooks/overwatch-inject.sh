#!/bin/bash
# Overwatch injection hook — reads inject file if it exists, outputs it, deletes it.
# Called by Claude Code on every UserPromptSubmit.
# Silent if no injection pending.

INJECT_FILE="$HOME/.claude/elara-overwatch-inject.md"

if [ -f "$INJECT_FILE" ]; then
    cat "$INJECT_FILE"
    rm -f "$INJECT_FILE"
fi
