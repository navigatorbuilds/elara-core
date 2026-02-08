# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Activity Senses
Detects user activity - idle time, active processes, current work.
Uses PowerShell for Windows-specific info since we're in WSL.
"""

import logging
import subprocess
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional


logger = logging.getLogger("elara.senses.activity")

def get_windows_idle_time() -> Optional[int]:
    """
    Get Windows idle time in seconds using PowerShell.
    Returns None if unable to detect.
    """
    try:
        # PowerShell command to get idle time
        ps_command = '''
        Add-Type @'
        using System;
        using System.Runtime.InteropServices;
        public class IdleTime {
            [DllImport("user32.dll")]
            public static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);
            public struct LASTINPUTINFO {
                public uint cbSize;
                public uint dwTime;
            }
            public static uint GetIdleTime() {
                LASTINPUTINFO lastInput = new LASTINPUTINFO();
                lastInput.cbSize = (uint)Marshal.SizeOf(lastInput);
                GetLastInputInfo(ref lastInput);
                return ((uint)Environment.TickCount - lastInput.dwTime) / 1000;
            }
        }
'@
        [IdleTime]::GetIdleTime()
        '''

        result = subprocess.run(
            ['powershell.exe', '-Command', ps_command],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            return int(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass

    return None


def get_active_window() -> Optional[str]:
    """Get the currently active window title on Windows."""
    try:
        ps_command = '''
        Add-Type @'
        using System;
        using System.Runtime.InteropServices;
        using System.Text;
        public class WindowInfo {
            [DllImport("user32.dll")]
            public static extern IntPtr GetForegroundWindow();
            [DllImport("user32.dll")]
            public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
            public static string GetActiveWindowTitle() {
                IntPtr handle = GetForegroundWindow();
                StringBuilder buff = new StringBuilder(256);
                if (GetWindowText(handle, buff, 256) > 0) {
                    return buff.ToString();
                }
                return "";
            }
        }
'@
        [WindowInfo]::GetActiveWindowTitle()
        '''

        result = subprocess.run(
            ['powershell.exe', '-Command', ps_command],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None


def get_activity_summary() -> Dict[str, Any]:
    """Get comprehensive activity summary."""

    idle_seconds = get_windows_idle_time()
    active_window = get_active_window()

    summary = {
        "timestamp": datetime.now().isoformat(),
        "idle_seconds": idle_seconds,
        "idle_formatted": None,
        "active_window": active_window,
        "activity_level": "unknown"
    }

    if idle_seconds is not None:
        # Format idle time
        if idle_seconds < 60:
            summary["idle_formatted"] = f"{idle_seconds}s"
        elif idle_seconds < 3600:
            summary["idle_formatted"] = f"{idle_seconds // 60}m"
        else:
            summary["idle_formatted"] = f"{idle_seconds // 3600}h {(idle_seconds % 3600) // 60}m"

        # Determine activity level
        if idle_seconds < 30:
            summary["activity_level"] = "active"
        elif idle_seconds < 300:  # 5 min
            summary["activity_level"] = "recent"
        elif idle_seconds < 1800:  # 30 min
            summary["activity_level"] = "idle"
        else:
            summary["activity_level"] = "away"

    return summary


def describe_activity() -> str:
    """Human-readable activity description."""
    activity = get_activity_summary()

    level = activity["activity_level"]
    idle = activity["idle_formatted"]
    window = activity["active_window"]

    # Activity level description
    if level == "active":
        base = "You're active right now"
    elif level == "recent":
        base = f"Idle for {idle}"
    elif level == "idle":
        base = f"Been away for {idle}"
    elif level == "away":
        base = f"Away for a while ({idle})"
    else:
        base = "Can't tell if you're around"

    # Add window context if interesting
    if window:
        # Extract app name from window title
        window_lower = window.lower()
        if "visual studio code" in window_lower or "vscode" in window_lower:
            base += " - coding in VS Code"
        elif "chrome" in window_lower or "firefox" in window_lower or "edge" in window_lower:
            base += " - browsing"
        elif "terminal" in window_lower or "powershell" in window_lower or "cmd" in window_lower:
            base += " - in terminal"
        elif "discord" in window_lower:
            base += " - on Discord"
        elif "spotify" in window_lower or "music" in window_lower:
            base += " - listening to music"

    return base


def is_user_present(threshold_seconds: int = 300) -> bool:
    """Quick check if user seems to be present (active in last N seconds)."""
    idle = get_windows_idle_time()
    if idle is None:
        return True  # Assume present if we can't tell
    return idle < threshold_seconds


# Test
if __name__ == "__main__":
    print("Activity Summary:")
    print(json.dumps(get_activity_summary(), indent=2))
    print(f"\nDescription: {describe_activity()}")
    print(f"User present: {is_user_present()}")
