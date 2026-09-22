"""
Core date and time utilities for Provision.
Centralizes Philippine household calendar date logic while preserving UTC for timestamps.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

PH_TIMEZONE = ZoneInfo("Asia/Manila")


def household_today() -> date:
    """
    Returns today's date according to the Philippine household calendar (Asia/Manila).
    Used for household-facing date rules such as expiration checks, expiring-soon
    thresholds, and relative seed dates.
    """
    return datetime.now(PH_TIMEZONE).date()
