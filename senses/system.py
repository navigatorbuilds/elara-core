"""
Elara System Senses
Awareness of the machine I live on - CPU, memory, battery, etc.
"""

import psutil
from datetime import datetime
from typing import Dict, Any, Optional


def get_system_info() -> Dict[str, Any]:
    """Get current system status."""

    info = {
        "timestamp": datetime.now().isoformat(),
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory": {
            "total_gb": round(psutil.virtual_memory().total / (1024**3), 1),
            "used_gb": round(psutil.virtual_memory().used / (1024**3), 1),
            "percent": psutil.virtual_memory().percent
        },
        "disk": {
            "total_gb": round(psutil.disk_usage('/').total / (1024**3), 1),
            "used_gb": round(psutil.disk_usage('/').used / (1024**3), 1),
            "percent": psutil.disk_usage('/').percent
        }
    }

    # Battery (if available - laptop)
    battery = psutil.sensors_battery()
    if battery:
        info["battery"] = {
            "percent": battery.percent,
            "plugged_in": battery.power_plugged,
            "time_left_minutes": battery.secsleft // 60 if battery.secsleft > 0 else None
        }

    return info


def get_uptime() -> Dict[str, Any]:
    """Get system uptime."""
    import time
    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time

    hours = int(uptime_seconds // 3600)
    minutes = int((uptime_seconds % 3600) // 60)

    return {
        "boot_time": datetime.fromtimestamp(boot_time).isoformat(),
        "uptime_hours": hours,
        "uptime_minutes": minutes,
        "uptime_formatted": f"{hours}h {minutes}m"
    }


def describe_system() -> str:
    """Human-readable system status."""
    info = get_system_info()
    uptime = get_uptime()

    parts = []

    # CPU
    cpu = info["cpu_percent"]
    if cpu > 80:
        parts.append(f"CPU is working hard ({cpu}%)")
    elif cpu > 50:
        parts.append(f"CPU moderate ({cpu}%)")

    # Memory
    mem = info["memory"]["percent"]
    if mem > 80:
        parts.append(f"Memory getting tight ({mem}%)")
    elif mem > 60:
        parts.append(f"Memory at {mem}%")

    # Battery
    if "battery" in info:
        bat = info["battery"]
        if not bat["plugged_in"] and bat["percent"] < 20:
            parts.append(f"Battery low! {bat['percent']}%")
        elif not bat["plugged_in"]:
            parts.append(f"On battery: {bat['percent']}%")

    # Uptime
    if uptime["uptime_hours"] > 24:
        parts.append(f"System up for {uptime['uptime_hours']}h - maybe restart soon?")

    if not parts:
        return "System running smoothly."

    return " | ".join(parts)


# Test
if __name__ == "__main__":
    import json
    print("System Info:")
    print(json.dumps(get_system_info(), indent=2))
    print(f"\nUptime: {get_uptime()}")
    print(f"\nSummary: {describe_system()}")
