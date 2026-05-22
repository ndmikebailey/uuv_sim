"""Pure environmental uplift and vector calculations."""

from __future__ import annotations

import math


TEMPERATURE_CAPACITY_PENALTY_POINTS: tuple[tuple[float, float], ...] = (
    (-20.0, 0.35),
    (-10.0, 0.15),
    (2.0, 0.05),
    (15.0, 0.0),
    (32.0, 0.0),
    (52.0, 0.05),
    (62.0, 0.15),
)


def current_components(current_speed_kts: float, current_direction_deg: float, heading_deg: float) -> tuple[float, float]:
    """Resolve current into along-track and cross-track components in knots."""
    rel = math.radians((current_direction_deg - heading_deg + 180) % 360 - 180)
    return current_speed_kts * math.cos(rel), current_speed_kts * math.sin(rel)


def _piecewise_linear_penalty(temp_c: float, points: tuple[tuple[float, float], ...]) -> float:
    """Return linearly interpolated penalty for a sorted temperature table."""
    ordered = sorted(points, key=lambda item: item[0])
    if temp_c <= ordered[0][0]:
        return ordered[0][1]
    if temp_c >= ordered[-1][0]:
        return ordered[-1][1]

    for (x0, y0), (x1, y1) in zip(ordered, ordered[1:]):
        if x0 <= temp_c <= x1:
            fraction = (temp_c - x0) / (x1 - x0)
            return y0 + fraction * (y1 - y0)

    return 0.0


def temperature_energy_penalty(temp_c: float) -> float:
    """Return usable battery-capacity penalty from sea/battery temperature."""
    return _piecewise_linear_penalty(float(temp_c), TEMPERATURE_CAPACITY_PENALTY_POINTS)


def payload_current_penalty(current_speed_kts: float, current_direction_deg: float, heading_deg: float, vehicle_speed_kts: float) -> float:
    """Return the existing cross-current payload energy penalty."""
    _, cross = current_components(current_speed_kts, current_direction_deg, heading_deg)
    return 0.04 * min(abs(cross) / max(vehicle_speed_kts, 0.1), 2.0)


def search_current_duration_multiplier(current_speed_kts: float, current_direction_deg: float, heading_deg: float, vehicle_speed_kts: float) -> float:
    """Return the existing search-mission current uplift multiplier."""
    along, cross = current_components(current_speed_kts, current_direction_deg, heading_deg)
    along_penalty = 0.35 * abs(along) / max(vehicle_speed_kts, 0.1)
    cross_penalty = 0.10 * abs(cross) / max(vehicle_speed_kts, 0.1)
    return 1.0 + along_penalty + cross_penalty


def salinity_buoyancy_penalty(
    salinity_psu: float | None,
    reference_psu: float = 35.0,
    penalty_per_psu: float = 0.005,
    max_penalty: float = 0.10,
) -> float:
    """Return a bounded planning penalty for salinity-driven trim/buoyancy burden."""
    if salinity_psu is None:
        return 0.0
    deviation = abs(float(salinity_psu) - reference_psu)
    return min(max_penalty, deviation * penalty_per_psu)


def environmental_uplift_factor(temp_c: float, current_penalty: float = 0.0, salinity_penalty: float = 0.0) -> float:
    """Return demand-side environmental uplift; temperature is handled as capacity derating."""
    del temp_c
    return 1.0 + current_penalty + salinity_penalty
