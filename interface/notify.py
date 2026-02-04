"""
Elara Notifications
Send desktop notifications to get the user's attention.
Works on both native Linux and WSL (via PowerShell).
"""

import subprocess
import os
from pathlib import Path
from typing import Optional


def is_wsl() -> bool:
    """Check if running in WSL."""
    try:
        with open('/proc/version', 'r') as f:
            return 'microsoft' in f.read().lower()
    except:
        return False


def notify_wsl(title: str, message: str, duration: int = 5000) -> bool:
    """Send notification via Windows PowerShell (for WSL)."""
    try:
        # Escape quotes in message
        safe_title = title.replace("'", "''").replace('"', '`"')
        safe_message = message.replace("'", "''").replace('"', '`"')

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
    except Exception as e:
        print(f"WSL notification failed: {e}")
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
        print("notify-send not found. Install libnotify-bin.")
        return False
    except Exception as e:
        print(f"Linux notification failed: {e}")
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
