"""Elara daemon modules - presence and state tracking."""
from .presence import ping, get_absence_duration, format_absence, end_session, get_stats
from .state import get_mood, adjust_mood, describe_mood, start_session, end_session as end_mood_session
