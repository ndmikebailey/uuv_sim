"""Time-selection helpers shared by Open-Meteo service clients."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def as_utc_datetime(value: object | None) -> datetime | None:
    """Normalize a UI or service timestamp to a timezone-aware UTC datetime."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(float(value), tz=timezone.utc)
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError("Environment time must be a valid date and time.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def isoformat_utc(value: datetime | None) -> str:
    """Return a compact UTC ISO-8601 timestamp."""
    if value is None:
        return ""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def select_hourly_record(
    payload: dict[str, Any],
    requested_time_utc: datetime,
) -> tuple[dict[str, Any], str]:
    """Return values from the hourly record nearest the requested UTC time."""
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise ValueError("The environmental provider returned no hourly data.")
    raw_times = hourly.get("time")
    if not isinstance(raw_times, list) or not raw_times:
        raise ValueError("The environmental provider returned no hourly timestamps.")

    parsed_times: list[datetime] = []
    for raw_time in raw_times:
        parsed = as_utc_datetime(raw_time)
        if parsed is None:
            raise ValueError("The environmental provider returned an invalid hourly timestamp.")
        parsed_times.append(parsed)
    selected_index = min(
        range(len(parsed_times)),
        key=lambda index: abs((parsed_times[index] - requested_time_utc).total_seconds()),
    )
    record: dict[str, Any] = {}
    for key, values in hourly.items():
        if key == "time" or not isinstance(values, list):
            continue
        if selected_index < len(values):
            record[key] = values[selected_index]
    return record, isoformat_utc(parsed_times[selected_index])
