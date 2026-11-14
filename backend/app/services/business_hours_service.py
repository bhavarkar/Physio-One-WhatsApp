"""Business Hours, Quiet Hours, and Timezone Scheduling Engine.

Single Organization Edition: Physio One Clinic.
Default Timezone: Asia/Kolkata.
Ensures no automated messages are sent during quiet hours, Sundays, or outside configured business hours.
"""
from datetime import datetime, time, timedelta, timezone
from typing import List, Optional
import zoneinfo

DEFAULT_TIMEZONE = "Asia/Kolkata"


def get_tz(tz_name: Optional[str] = None):
    """Return ZoneInfo object for named timezone with Windows fallback."""
    target_name = tz_name or DEFAULT_TIMEZONE
    try:
        return zoneinfo.ZoneInfo(target_name)
    except Exception:
        if target_name in ("Asia/Kolkata", "Asia/Calcutta", "IST"):
            return timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
        return timezone.utc


def parse_time_component(t_str: str) -> time:
    """Parse 'HH:MM' string to datetime.time."""
    parts = t_str.strip().split(":")
    return time(hour=int(parts[0]), minute=int(parts[1]))


def is_sunday_iso(dt_local: datetime) -> bool:
    """Return True if local datetime is Sunday (isoweekday == 7)."""
    return dt_local.isoweekday() == 7


def is_in_business_hours(
    dt: datetime,
    start_hour: str = "09:00",
    end_hour: str = "20:00",
    permitted_days: Optional[List[int]] = None,
    tz_name: str = DEFAULT_TIMEZONE,
) -> bool:
    """Check if datetime falls within permitted clinic business hours."""
    tz = get_tz(tz_name)
    local_dt = dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=timezone.utc).astimezone(tz)

    # Permitted days check (1 = Mon ... 7 = Sun)
    if permitted_days is None:
        permitted_days = [1, 2, 3, 4, 5, 6]  # Sunday excluded
    
    # Normalize permitted days in case 0 was passed for Sunday or Monday
    normalized_days = set()
    for d in permitted_days:
        if d == 0:
            # could be Sunday in 0-indexed or Monday
            normalized_days.add(7)
        else:
            normalized_days.add(d)

    if local_dt.isoweekday() not in normalized_days:
        return False

    t_start = parse_time_component(start_hour)
    t_end = parse_time_component(end_hour)
    cur_time = local_dt.time()

    return t_start <= cur_time < t_end


def is_in_quiet_hours(
    dt: datetime,
    quiet_start: str = "21:00",
    quiet_end: str = "09:00",
    tz_name: str = DEFAULT_TIMEZONE,
) -> bool:
    """Check if datetime falls into quiet hours (typically 21:00 to 09:00 IST)."""
    tz = get_tz(tz_name)
    local_dt = dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=timezone.utc).astimezone(tz)

    q_start = parse_time_component(quiet_start)
    q_end = parse_time_component(quiet_end)
    cur_time = local_dt.time()

    if q_start > q_end:
        # Crosses midnight (e.g. 21:00 to 09:00)
        return cur_time >= q_start or cur_time < q_end
    else:
        return q_start <= cur_time < q_end


def calculate_next_eligible_send_time(
    dt: datetime,
    start_hour: str = "09:00",
    end_hour: str = "20:00",
    quiet_start: str = "21:00",
    quiet_end: str = "09:00",
    permitted_days: Optional[List[int]] = None,
    tz_name: str = DEFAULT_TIMEZONE,
) -> datetime:
    """Calculate the next earliest valid timestamp for dispatch.
    
    If dt is currently within business hours and not in quiet hours, returns dt.
    Otherwise advances to the next permitted open window at start_hour.
    Never returns a time in the past.
    """
    tz = get_tz(tz_name)
    now_utc = datetime.now(timezone.utc)
    base_dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    # Do not schedule in the past
    if base_dt < now_utc:
        base_dt = now_utc

    local_dt = base_dt.astimezone(tz)

    if permitted_days is None:
        permitted_days = [1, 2, 3, 4, 5, 6]
    normalized_days = set()
    for d in permitted_days:
        if d == 0:
            normalized_days.add(7)
        else:
            normalized_days.add(d)

    # Check if currently valid
    if (
        is_in_business_hours(local_dt, start_hour, end_hour, permitted_days, tz_name)
        and not is_in_quiet_hours(local_dt, quiet_start, quiet_end, tz_name)
    ):
        return local_dt.astimezone(timezone.utc)

    # Otherwise scan forward day by day up to 14 days
    t_start = parse_time_component(start_hour)
    t_end = parse_time_component(end_hour)

    candidate = local_dt
    for _ in range(14):
        # If before start_hour today and today is permitted
        if candidate.isoweekday() in normalized_days:
            if candidate.time() < t_start:
                candidate = candidate.replace(hour=t_start.hour, minute=t_start.minute, second=0, microsecond=0)
                if not is_in_quiet_hours(candidate, quiet_start, quiet_end, tz_name):
                    return candidate.astimezone(timezone.utc)
            elif candidate.time() < t_end and not is_in_quiet_hours(candidate, quiet_start, quiet_end, tz_name):
                return candidate.astimezone(timezone.utc)

        # Advance to next day at start_hour
        candidate = (candidate + timedelta(days=1)).replace(
            hour=t_start.hour, minute=t_start.minute, second=0, microsecond=0
        )

    return candidate.astimezone(timezone.utc)
