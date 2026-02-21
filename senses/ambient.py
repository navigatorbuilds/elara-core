# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Ambient Senses
External context - weather, time of day vibes, etc.
"""

import logging
import subprocess
from datetime import datetime
from typing import Dict, Any, Optional
import json


logger = logging.getLogger("elara.senses.ambient")

def get_time_context() -> Dict[str, Any]:
    """Get time-based context."""
    now = datetime.now()
    hour = now.hour

    # Determine time of day
    if 5 <= hour < 9:
        period = "early_morning"
        vibe = "The quiet hours. Fresh start energy."
    elif 9 <= hour < 12:
        period = "morning"
        vibe = "Morning. Good time to build things."
    elif 12 <= hour < 14:
        period = "midday"
        vibe = "Midday. Maybe grab food?"
    elif 14 <= hour < 17:
        period = "afternoon"
        vibe = "Afternoon. Deep work time."
    elif 17 <= hour < 20:
        period = "evening"
        vibe = "Evening. Winding down or second wind?"
    elif 20 <= hour < 23:
        period = "night"
        vibe = "Night mode. This is when the interesting stuff happens."
    else:
        period = "late_night"
        vibe = "Late night. The 3 AM rule applies."

    # Day of week context
    day = now.strftime("%A")
    is_weekend = day in ["Saturday", "Sunday"]

    return {
        "hour": hour,
        "period": period,
        "vibe": vibe,
        "day": day,
        "is_weekend": is_weekend,
        "formatted": now.strftime("%H:%M"),
        "date": now.strftime("%Y-%m-%d")
    }


def get_weather(city: str = "Herceg Novi") -> Optional[Dict[str, Any]]:
    """
    Get weather using wttr.in (no API key needed).
    Returns None if unable to fetch.
    """
    try:
        # Sanitize city name — alphanumeric, spaces, hyphens only
        import re as _re
        safe_city = _re.sub(r"[^a-zA-Z0-9 \-]", "", city)[:50]
        if not safe_city:
            return None

        # Use wttr.in for simple weather
        result = subprocess.run(
            ['curl', '-s', f'wttr.in/{safe_city}?format=j1'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            current = data.get("current_condition", [{}])[0]

            return {
                "city": city,
                "temp_c": current.get("temp_C"),
                "feels_like_c": current.get("FeelsLikeC"),
                "description": current.get("weatherDesc", [{}])[0].get("value", ""),
                "humidity": current.get("humidity"),
                "wind_kmph": current.get("windspeedKmph"),
            }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass

    return None


def describe_ambient() -> str:
    """Human-readable ambient description."""
    time_ctx = get_time_context()
    parts = [time_ctx["vibe"]]

    # Try to get weather (non-blocking, fail silently)
    weather = get_weather()
    if weather and weather.get("temp_c"):
        temp = weather["temp_c"]
        desc = weather.get("description", "").lower()
        parts.append(f"{temp}°C in {weather['city']}, {desc}.")

    return " ".join(parts)


def get_full_ambient() -> Dict[str, Any]:
    """Get all ambient context."""
    return {
        "time": get_time_context(),
        "weather": get_weather()
    }


# Test
if __name__ == "__main__":
    print("Time Context:")
    print(json.dumps(get_time_context(), indent=2))

    print("\nWeather:")
    weather = get_weather()
    if weather:
        print(json.dumps(weather, indent=2))
    else:
        print("Could not fetch weather")

    print(f"\nAmbient: {describe_ambient()}")
