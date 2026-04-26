"""Small parsing and formatting helpers used across modules."""

from __future__ import annotations

import json
from typing import Any, Optional


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Return ``value`` as a float, or ``default`` when conversion fails."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Return ``value`` as an int, or ``default`` when conversion fails."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_rng_seed(seed_text: str | None) -> int | None:
    """Parse an optional non-negative Monte Carlo random seed."""
    if seed_text is None:
        return None
    cleaned = str(seed_text).strip()
    if cleaned == "":
        return None
    try:
        seed = int(cleaned)
    except ValueError as exc:
        raise ValueError("Monte Carlo seed must be a non-negative integer or blank.") from exc
    if seed < 0:
        raise ValueError("Monte Carlo seed must be non-negative.")
    return seed


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from text and raise a useful ``ValueError``."""
    if not text or not text.strip():
        raise ValueError("Draw a rectangle, polygon, or line on the map first.")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse map geometry JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("Map geometry JSON must be an object.")
    return value


def fmt(value: Any, digits: int = 3) -> str:
    """Format numeric values consistently for operator-facing labels."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)
