# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Notifications
Send desktop notifications to get the user's attention.
Works on both native Linux and WSL (via PowerShell).
"""

import logging
import subprocess
import os
from pathlib import Path
from typing import Optional


logger = logging.getLogger("elara.interface.notify")

def is_wsl() -> bool:
    """Check if running in WSL."""
    try:
        with open('/proc/version', 'r') as f:
            return 'microsoft' in f.read().lower()
    except OSError:
        return False


def notify_wsl(title: str, message: str, duration: int = 5000) -> bool:
    """Send notification via Windows PowerShell (for WSL)."""
    try:
        # Sanitize for PowerShell — strip dangerous chars, then escape quotes
        import re as _re
        safe_title = _re.sub(r"[;|&`$\{\}]", "", title)[:100]
        safe_message = _re.sub(r"[;|&`$\{\}]", "", message)[:500]
        safe_title = safe_title.replace("'", "''").replace('"', '""')
        safe_message = safe_message.replace("'", "''").replace('"', '""')

        # Use simple MessageBox - reliable and visible
        ps_script = f"""
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show('{safe_message}', '{safe_title}', 'OK', 'Information')
        """

        # Run in background so it doesn't block
        # Use full path for systemd service compatibility
        ps_path = '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'
        subprocess.Popen(
            [ps_path, '-WindowStyle', 'Hidden', '-Command', ps_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except (OSError, subprocess.SubprocessError) as e:
        logger.error("WSL notification failed: %s", e)
        return False


def notify_linux(title: str, message: str, duration: int = 5000) -> bool:
    """Send notification via notify-send (native Linux)."""
    try:
        result = subprocess.run(
            ['notify-send', '-t', str(duration), title, message],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except FileNotFoundError:
        logger.warning("notify-send not found. Install libnotify-bin.")
        return False
    except (OSError, subprocess.SubprocessError) as e:
        logger.error("Linux notification failed: %s", e)
        return False


def notify(title: str, message: str, duration: int = 5000) -> bool:
    """
    Send a desktop notification.
    Automatically detects WSL vs native Linux.
    """
    if is_wsl():
        return notify_wsl(title, message, duration)
    else:
        return notify_linux(title, message, duration)


def notify_note_received(note_text: str) -> bool:
    """Convenience function for note notifications."""
    return notify(
        "Elara - New Note",
        f"From mobile: {note_text[:100]}{'...' if len(note_text) > 100 else ''}"
    )


def notify_elara(message: str) -> bool:
    """General Elara notification."""
    return notify("Elara", message)


# Test
if __name__ == "__main__":
    print(f"WSL detected: {is_wsl()}")
    print("Sending test notification...")
    success = notify("Elara Test", "If you see this, notifications work!")
    print(f"Success: {success}")
