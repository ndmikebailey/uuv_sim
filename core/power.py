"""Speed-aware planning power calculations for UUV energy estimates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from models.vehicle_model import VehicleState


@dataclass(frozen=True)
class PowerModelBreakdown:
    """Diagnostic components for the speed-aware planning power model."""

    speed_kts: float
    nominal_speed_kts: float
    nominal_power_kw: float
    hotel_power_kw: float
    propulsion_power_kw: float
    low_speed_penalty_kw: float
    total_power_kw: float
    hotel_fraction: float
    min_efficient_speed_kts: float
    nominal_power_scale: float = 1.0
    propulsion_multiplier: float = 1.0
    speed_exponent: float = 3.0
    low_speed_penalty_fraction: float = 0.15


def _clamp(value: float, lower: float, upper: float) -> float:
    """Return value constrained to the inclusive lower/upper range."""
    return max(lower, min(upper, value))


def _vehicle_float(vehicle: VehicleState, attr_names: tuple[str, ...], default: float) -> float:
    """Read an optional float tuning parameter from a vehicle catalog entry."""
    for attr_name in attr_names:
        value = getattr(vehicle, attr_name, None)
        if value is not None:
            return float(value)
    return default


def _validated_vehicle_speed_kts(vehicle: VehicleState, speed_kts: float) -> float:
    """Return a bounded positive speed, rejecting values above the vehicle envelope."""
    requested_speed = float(speed_kts)
    max_speed = max(float(vehicle.max_speed_kts), 0.1)
    if requested_speed > max_speed:
        raise ValueError(
            f"Requested speed {requested_speed:.2f} kt exceeds "
            f"{vehicle.name} maximum speed of {max_speed:.2f} kt."
        )
    return max(requested_speed, 0.1)


def power_model_breakdown(
    vehicle: VehicleState,
    speed_kts: float,
    hotel_fraction: float | None = None,
    speed_exponent: float = 3.0,
    propulsion_multiplier: float = 1.0,
    nominal_power_scale: float = 1.0,
    low_speed_penalty_fraction: float | None = None,
) -> PowerModelBreakdown:
    """Return speed-aware planning power and component diagnostics."""
    v = _validated_vehicle_speed_kts(vehicle, speed_kts)
    v_nom = max(float(vehicle.nominal_speed_kts), 0.1)
    bounded_nominal_scale = _clamp(float(nominal_power_scale), 0.85, 1.20)
    p_nom = max(float(vehicle.average_power_kw) * bounded_nominal_scale, 0.001)

    selected_hotel_fraction = (
        float(hotel_fraction)
        if hotel_fraction is not None
        else _vehicle_float(vehicle, ("hotel_power_fraction", "hotel_fraction"), 0.40)
    )
    bounded_hotel_fraction = _clamp(selected_hotel_fraction, 0.25, 0.60)
    p_hotel = p_nom * bounded_hotel_fraction
    p_prop_nom = max(p_nom - p_hotel, 0.0)
    bounded_speed_exponent = _clamp(float(speed_exponent), 2.4, 3.4)
    bounded_propulsion_multiplier = _clamp(float(propulsion_multiplier), 0.75, 1.35)
    p_prop = p_prop_nom * (v / v_nom) ** bounded_speed_exponent * bounded_propulsion_multiplier

    min_efficient_speed = _vehicle_float(vehicle, ("min_efficient_speed_kts",), 0.65 * v_nom)
    min_efficient_speed = _clamp(min_efficient_speed, 0.1, v_nom)
    penalty_cap_fraction = max(_vehicle_float(vehicle, ("low_speed_penalty_cap_fraction",), 0.10), 0.0)
    selected_penalty_fraction = (
        float(low_speed_penalty_fraction)
        if low_speed_penalty_fraction is not None
        else _vehicle_float(vehicle, ("low_speed_penalty_fraction",), 0.15)
    )
    bounded_penalty_fraction = _clamp(selected_penalty_fraction, 0.0, 0.30)
    low_speed_penalty = 0.0
    if v < min_efficient_speed:
        raw_penalty = p_nom * bounded_penalty_fraction * ((min_efficient_speed - v) / min_efficient_speed) ** 2
        low_speed_penalty = min(raw_penalty, p_nom * penalty_cap_fraction)

    total_power = max(p_hotel, p_hotel + p_prop + low_speed_penalty)
    if v < v_nom:
        total_power = min(total_power, p_nom * (1.0 + penalty_cap_fraction))

    return PowerModelBreakdown(
        speed_kts=v,
        nominal_speed_kts=v_nom,
        nominal_power_kw=p_nom,
        hotel_power_kw=p_hotel,
        propulsion_power_kw=p_prop,
        low_speed_penalty_kw=low_speed_penalty,
        total_power_kw=total_power,
        hotel_fraction=bounded_hotel_fraction,
        min_efficient_speed_kts=min_efficient_speed,
        nominal_power_scale=bounded_nominal_scale,
        propulsion_multiplier=bounded_propulsion_multiplier,
        speed_exponent=bounded_speed_exponent,
        low_speed_penalty_fraction=bounded_penalty_fraction,
    )


def speed_adjusted_power_kw(vehicle: VehicleState, speed_kts: float) -> float:
    """Return total planning power at speed in kW."""
    return power_model_breakdown(vehicle, speed_kts).total_power_kw


def sample_power_model_breakdown(
    vehicle: VehicleState,
    speed_kts: float,
    rng: Any,
    propulsion_multiplier: float = 1.0,
) -> PowerModelBreakdown:
    """Return one sampled power-model draw around the deterministic centerline."""
    centerline = power_model_breakdown(vehicle, speed_kts, propulsion_multiplier=1.0)
    nominal_power_scale = _clamp(float(rng.normal(1.0, 0.03)), 0.85, 1.20)
    hotel_fraction = _clamp(float(rng.normal(centerline.hotel_fraction, 0.06)), 0.25, 0.60)
    sampled_propulsion_multiplier = _clamp(float(rng.normal(1.0, 0.10)), 0.75, 1.35)
    low_speed_penalty_fraction = _clamp(float(rng.normal(centerline.low_speed_penalty_fraction, 0.05)), 0.0, 0.30)
    speed_exponent = _clamp(float(rng.normal(3.0, 0.25)), 2.4, 3.4)

    return power_model_breakdown(
        vehicle,
        speed_kts,
        hotel_fraction=hotel_fraction,
        speed_exponent=speed_exponent,
        propulsion_multiplier=sampled_propulsion_multiplier * float(propulsion_multiplier),
        nominal_power_scale=nominal_power_scale,
        low_speed_penalty_fraction=low_speed_penalty_fraction,
    )
