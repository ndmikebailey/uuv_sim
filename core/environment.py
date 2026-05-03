"""Pure environmental uplift and vector calculations."""

from __future__ import annotations

import math


def current_components(current_speed_kts: float, current_direction_deg: float, heading_deg: float) -> tuple[float, float]:
    """Resolve current into along-track and cross-track components in knots."""
    rel = math.radians((current_direction_deg - heading_deg + 180) % 360 - 180)
    return current_speed_kts * math.cos(rel), current_speed_kts * math.sin(rel)


def temperature_energy_penalty(temp_c: float) -> float:
    """Return the existing battery/environment energy penalty from sea temperature."""
    if temp_c < 15:
        return min(0.25, (15 - temp_c) * 0.01)
    if temp_c > 32:
        return min(0.15, (temp_c - 32) * 0.005)
    return 0.0


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
    """Return combined multiplicative uplift for tests and planning calculations."""
    return 1.0 + temperature_energy_penalty(temp_c) + current_penalty + salinity_penalty
