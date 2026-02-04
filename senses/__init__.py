"""Elara senses - awareness of the environment."""
from .system import get_system_info, describe_system, get_uptime
from .activity import get_activity_summary, describe_activity, is_user_present, get_windows_idle_time
from .ambient import get_time_context, get_weather, describe_ambient, get_full_ambient
