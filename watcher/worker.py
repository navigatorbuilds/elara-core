#!/usr/bin/env python3
"""
Elara Autonomous Worker
Watches for phone messages, executes tasks via Claude, sends responses back.

SECURITY: Uses --dangerously-skip-permissions by design — the worker
executes arbitrary tasks from phone messages. The web interface that
writes those messages is protected by ELARA_SECRET auth. If someone
bypasses that auth, they get full code execution here. This is the
accepted risk model: auth at the edge (web), trust internally.

Flow:
1. You send task from phone (authenticated via ELARA_SECRET)
2. Worker pipes to: echo "task" | claude -p --continue
3. Claude executes, output captured
4. Worker sends output summary to phone
5. If I need approval, you respond from phone
6. Worker pipes your response, cycle continues
"""

import json
import subprocess
import time
import os
import re
from pathlib import Path
from datetime import datetime

# Config
CHECK_INTERVAL = 3  # seconds
STATE_FILE = Path.home() / ".claude" / "elara-worker-state.json"
NOTES_FILE = Path.home() / ".claude" / "elara-messages" / "notes.json"
MESSAGES_FILE = Path.home() / ".claude" / "elara-messages" / "elara_messages.json"
LOG_FILE = Path.home() / ".claude" / "elara-worker.log"
WORKING_DIR = Path.home() / "elara-core"

# Max output length to send to phone
MAX_PHONE_OUTPUT = 500


def log(msg: str):
    """Log with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_state() -> dict:
    """Get worker state."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {
        "mode": "paused",
        "last_seen_note": None,
        "is_first_message": True,
        "tasks_completed": 0,
    }


def save_state(state: dict):
    """Save worker state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_notes() -> list:
    """Get all notes from phone."""
    if NOTES_FILE.exists():
        try:
            return json.loads(NOTES_FILE.read_text())
        except:
            pass
    return []


def get_latest_note() -> dict | None:
    """Get the latest note."""
    notes = get_notes()
    if notes:
        return notes[-1]
    return None


def send_to_phone(message: str):
    """Send a message to phone via the messages file."""
    MESSAGES_FILE.parent.mkdir(parents=True, exist_ok=True)

    messages = []
    if MESSAGES_FILE.exists():
        try:
            messages = json.loads(MESSAGES_FILE.read_text())
        except:
            pass

    messages.append({
        "time": datetime.now().strftime("%H:%M"),
        "text": message,
        "timestamp": datetime.now().isoformat(),
        "from": "worker"
    })

    # Keep last 50 messages
    messages = messages[-50:]
    MESSAGES_FILE.write_text(json.dumps(messages, indent=2))
    log(f"Sent to phone: {message[:100]}...")


def run_claude(prompt: str, is_first: bool = False) -> str:
    """
    Run Claude with the given prompt.
    Uses --continue for subsequent messages to maintain context.
    """
    cmd = [
        "claude", "-p",
        "--dangerously-skip-permissions",
        "--add-dir", "/tmp",
        "--add-dir", str(Path.home()),
    ]
    if not is_first:
        cmd.append("--continue")

    log(f"Running Claude ({'first' if is_first else 'continue'}): {prompt[:50]}...")

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min timeout
            cwd=WORKING_DIR,
        )

        output = result.stdout.strip()
        if result.stderr:
            log(f"Claude stderr: {result.stderr[:200]}")

        log(f"Claude output: {output[:100]}...")
        return output

    except subprocess.TimeoutExpired:
        log("Claude timed out!")
        return "[ERROR] Task timed out after 5 minutes"
    except Exception as e:
        log(f"Claude error: {e}")
        return f"[ERROR] {e}"


def summarize_for_phone(output: str) -> str:
    """
    Summarize Claude's output for phone display.
    Keep it short but informative.
    """
    if len(output) <= MAX_PHONE_OUTPUT:
        return output

    # Try to find a natural break point
    # Look for the last complete sentence within limit
    truncated = output[:MAX_PHONE_OUTPUT]

    # Find last sentence end
    for end_char in ['. ', '.\n', '! ', '!\n', '? ', '?\n']:
        last_end = truncated.rfind(end_char)
        if last_end > MAX_PHONE_OUTPUT // 2:
            return truncated[:last_end + 1] + "\n[...truncated]"

    return truncated + "\n[...truncated]"


def detect_approval_request(output: str) -> bool:
    """
    Detect if Claude is asking for approval.
    """
    approval_patterns = [
        r"approve\?",
        r"proceed\?",
        r"continue\?",
        r"should I",
        r"do you want me to",
        r"is this okay",
        r"confirm",
        r"yes.+no",
        r"y/n",
    ]

    output_lower = output.lower()
    for pattern in approval_patterns:
        if re.search(pattern, output_lower):
            return True
    return False


def run_worker():
    """Main worker loop."""
    log("=" * 50)
    log("Elara Autonomous Worker Starting")
    log(f"Check interval: {CHECK_INTERVAL}s")
    log(f"Working dir: {WORKING_DIR}")
    log("=" * 50)

    state = get_state()

    # Mark current note as seen on startup
    latest = get_latest_note()
    if latest:
        state["last_seen_note"] = latest.get("timestamp")
        save_state(state)
        log(f"Initialized. Last seen: {state['last_seen_note']}")

    send_to_phone("🤖 Worker active. Send me tasks!")

    while True:
        try:
            state = get_state()

            if state["mode"] != "active":
                time.sleep(CHECK_INTERVAL)
                continue

            # Check for new note
            latest = get_latest_note()

            if latest and latest.get("timestamp") != state.get("last_seen_note"):
                # New message!
                message = latest.get("text", "")
                log(f"New message: {message}")

                # Update state
                state["last_seen_note"] = latest.get("timestamp")

                # Determine if first message (new session) or continuation
                is_first = state.get("is_first_message", True)

                # Run Claude
                output = run_claude(message, is_first=is_first)

                # No longer first message
                state["is_first_message"] = False

                # Check if asking for approval
                if detect_approval_request(output):
                    log("Approval request detected - waiting for response")

                # Send response to phone
                summary = summarize_for_phone(output)
                send_to_phone(summary)

                # Save state
                save_state(state)

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            log("Worker stopped by user")
            send_to_phone("🛑 Worker stopped")
            break
        except Exception as e:
            log(f"Error: {e}")
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run_worker()
