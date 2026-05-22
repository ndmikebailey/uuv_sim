"""Battery capacity sampling and temperature derating helpers."""

from __future__ import annotations

from typing import Any


TEMPERATURE_CAPACITY_FACTOR_POINTS: tuple[tuple[float, float], ...] = (
    (-20.0, 0.65),
    (-10.0, 0.85),
    (2.0, 0.95),
    (15.0, 1.00),
    (32.0, 1.00),
    (52.0, 0.95),
    (62.0, 0.85),
)


def _clamp(value: float, low: float, high: float) -> float:
    """Clamp a floating-point value to a closed interval."""
    return min(max(float(value), low), high)


def _piecewise_linear_factor(temp_c: float, points: tuple[tuple[float, float], ...]) -> float:
    """Return linearly interpolated capacity factor for a temperature table."""
    ordered = sorted(points, key=lambda item: item[0])
    if temp_c <= ordered[0][0]:
        return ordered[0][1]
    if temp_c >= ordered[-1][0]:
        return ordered[-1][1]

    for (x0, y0), (x1, y1) in zip(ordered, ordered[1:]):
        if x0 <= temp_c <= x1:
            fraction = (temp_c - x0) / (x1 - x0)
            return y0 + fraction * (y1 - y0)

    return 1.0


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
    return _piecewise_linear_factor(float(temp_c), TEMPERATURE_CAPACITY_FACTOR_POINTS)


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
