"""Central registry of model assumptions for traceability and thesis documentation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelAssumption:
    """One named model assumption with rationale and provenance."""

    key: str
    value: str | float
    rationale: str
    source: str
    confidence: str


MODEL_ASSUMPTIONS: dict[str, ModelAssumption] = {
    "propulsion_speed_exponent": ModelAssumption(
        key="propulsion_speed_exponent",
        value=3.0,
        rationale="Approximates propulsion power scaling with speed for displacement-dominated underwater vehicles.",
        source="Engineering planning assumption; validate with vehicle-specific power curves when available.",
        confidence="medium",
    ),
    "default_hotel_load_fraction": ModelAssumption(
        key="default_hotel_load_fraction",
        value=0.35,
        rationale="Separates fixed hotel/sensor/control load from speed-dependent propulsion load.",
        source="Engineering planning assumption for v3.2 speed-power correction.",
        confidence="low-medium",
    ),
    "default_usable_battery_fraction": ModelAssumption(
        key="default_usable_battery_fraction",
        value=0.88,
        rationale="Represents planning reserve and battery-health allowance when platform-specific usable energy is not published.",
        source="v3.2 public baseline catalog planning assumption.",
        confidence="medium",
    ),
    "usable_battery_fraction_range": ModelAssumption(
        key="usable_battery_fraction_range",
        value="future stochastic range centered on catalog usable_fraction",
        rationale="Future stochastic model should express reserve, health, and operating uncertainty without changing nameplate capacity.",
        source="v3.2 model-validation plan.",
        confidence="planned",
    ),
    "default_generator_efficiency": ModelAssumption(
        key="default_generator_efficiency",
        value=0.84,
        rationale="Supports recharge/fuel equivalence estimates for sustainment planning.",
        source="Engineering planning assumption in compute_stockpile_requirement.",
        confidence="low-medium",
    ),
    "open_meteo_representative_point_policy": ModelAssumption(
        key="open_meteo_representative_point_policy",
        value="payload route midpoint; ISR first patrol point; search area centroid",
        rationale="Uses one representative point for current single-area/single-route METOC lookup until multi-area averaging is implemented.",
        source="core.mission.choose_environment_lookup_point.",
        confidence="medium",
    ),
    "temperature_derating_curve_status": ModelAssumption(
        key="temperature_derating_curve_status",
        value="simple planning penalty curve",
        rationale="Current temperature effect is a generalized energy uplift pending literature or test-backed refinement.",
        source="core.environment.temperature_energy_penalty.",
        confidence="low-medium",
    ),
    "oil_equivalent_conversion_caveat": ModelAssumption(
        key="oil_equivalent_conversion_caveat",
        value="energy-equivalence lens only",
        rationale="Oil-equivalent values support sustainment intuition and do not imply direct fuel interchangeability.",
        source="Results report Energy Storage Equivalence Lens caveat.",
        confidence="high",
    ),
}


def assumptions_as_rows() -> list[list[str, str, str, str, str]]:
    """Return assumptions as rows for documentation/export workflows."""
    return [
        [a.key, str(a.value), a.rationale, a.source, a.confidence]
        for a in MODEL_ASSUMPTIONS.values()
    ]
