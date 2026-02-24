"""Convert stored UTC timestamps to local time for display."""

from __future__ import annotations

from datetime import datetime, timezone

# Stored format: UTC "%Y-%m-%d %H:%M:%S"
DISPLAY_FMT = "%Y-%m-%d %H:%M:%S"
STORED_FMT = "%Y-%m-%d %H:%M:%S"


def utc_to_local(utc_str: str | None) -> str:
    """Convert a stored UTC datetime string to local time for display.
    Returns the original string if parsing fails (e.g. empty or invalid).
    """
    if not utc_str or not utc_str.strip():
        return utc_str or ""
    try:
        dt = datetime.strptime(utc_str.strip()[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        return dt.astimezone().strftime(DISPLAY_FMT)
    except (ValueError, TypeError):
        return utc_str
