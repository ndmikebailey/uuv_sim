"""Battery capacity sampling and temperature derating helpers."""

from __future__ import annotations

from typing import Any


def _clamp(value: float, low: float, high: float) -> float:
    """Clamp a floating-point value to a closed interval."""
    return min(max(float(value), low), high)


def sample_usable_battery_fraction(
    rng: Any,
    condition: str = "medium",
    deterministic_fraction: float = 0.88,
    stochastic_enabled: bool = True,
) -> float:
    """
    Sample practical usable battery fraction for one Monte Carlo run.

    This represents battery condition, state of charge, age, and field-use variation.
    It is separate from operator reserve margin and temperature derating.
    """
    if not stochastic_enabled:
        return _clamp(deterministic_fraction, 0.50, 1.00)

    distributions = {
        "low": (0.75, 0.82, 0.90),
        "medium": (0.80, 0.88, 0.95),
        "high": (0.88, 0.93, 0.98),
    }
    left, mode, right = distributions.get(str(condition).strip().lower(), distributions["medium"])
    return _clamp(float(rng.triangular(left, mode, right)), 0.50, 1.00)


def lithium_temperature_capacity_factor(temp_c: float) -> float:
    """
    Planning-level lithium-ion usable-capacity derating curve.

    This is not a high-fidelity electrochemistry model.
    """
    temp = float(temp_c)
    if temp >= 10.0:
        return 1.00
    if temp >= 0.0:
        return 0.96
    if temp >= -10.0:
        return 0.88
    if temp >= -20.0:
        return 0.82
    return 0.75


def usable_battery_energy_kwh(
    rated_capacity_kwh: float,
    usable_fraction: float,
    reserve_fraction: float,
    temperature_capacity_factor: float = 1.0,
) -> float:
    """Return usable mission energy after capacity, temperature, and reserve factors."""
    rated = max(float(rated_capacity_kwh), 0.0)
    usable = _clamp(usable_fraction, 0.0, 1.0)
    reserve = _clamp(reserve_fraction, 0.0, 0.95)
    temp_factor = _clamp(temperature_capacity_factor, 0.0, 1.0)
    return rated * usable * temp_factor * (1.0 - reserve)
