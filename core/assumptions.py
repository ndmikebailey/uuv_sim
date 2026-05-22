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
        value=0.40,
        rationale="Separates fixed hotel/sensor/control load from speed-dependent propulsion load.",
        source="Engineering planning assumption for v3.5 beta speed-aware power correction.",
        confidence="low-medium",
    ),
    "default_usable_battery_fraction": ModelAssumption(
        key="default_usable_battery_fraction",
        value=0.88,
        rationale="Legacy catalog value retained for compatibility; current simulations sample battery condition separately from operator reserve margin.",
        source="Public baseline catalog planning assumption retained in v3.5 beta.",
        confidence="medium",
    ),
    "usable_battery_fraction_range": ModelAssumption(
        key="usable_battery_fraction_range",
        value="low triangular(0.75,0.82,0.90); medium triangular(0.80,0.88,0.95); high triangular(0.88,0.93,0.98)",
        rationale="Models practical starting usable capacity variation from battery health, state of charge, age, and field use.",
        source="core.battery.sample_usable_battery_fraction.",
        confidence="low-medium",
    ),
    "default_generator_efficiency": ModelAssumption(
        key="default_generator_efficiency",
        value=0.84,
        rationale="Supports recharge energy-flow estimates for sustainment planning.",
        source="Engineering planning assumption in compute_sustainment_projection.",
        confidence="low-medium",
    ),
    "open_meteo_representative_point_policy": ModelAssumption(
        key="open_meteo_representative_point_policy",
        value="payload route midpoint; ISR first patrol point; search area centroid",
        rationale="Uses representative lookup points while multi-area Search/MCM samples each area centroid and aggregates METOC values.",
        source="core.mission.choose_environment_lookup_point.",
        confidence="medium",
    ),
    "temperature_derating_curve_status": ModelAssumption(
        key="temperature_derating_curve_status",
        value="capacity derating, not demand uplift",
        rationale="Temperature reduces usable battery capacity and is not also applied as a separate mission-energy demand penalty.",
        source="core.battery.lithium_temperature_capacity_factor.",
        confidence="medium",
    ),
    "temperature_derating_curve_v1": ModelAssumption(
        key="temperature_derating_curve_v1",
        value="-20C:0.65; -10C:0.85; 2C:0.95; 15-32C:1.00; 52C:0.95; 62C:0.85",
        rationale="Table-driven planning-level lithium capacity derating curve aligned to Bressan-style capacity-loss anchors.",
        source="core.battery.lithium_temperature_capacity_factor.",
        confidence="medium",
    ),
    "temperature_no_effect_band": ModelAssumption(
        key="temperature_no_effect_band",
        value="15C <= temp_c <= 32C",
        rationale="Normal operating band does not receive temperature capacity derating or additional demand uplift.",
        source="core.battery.lithium_temperature_capacity_factor.",
        confidence="medium",
    ),
    "temperature_derating_rationale": ModelAssumption(
        key="temperature_derating_rationale",
        value="temperature reduces usable capacity before reserve policy",
        rationale="Avoids double-counting temperature as both capacity loss and energy-demand uplift.",
        source="core.energy.run_energy_simulation.",
        confidence="medium",
    ),
    "temperature_model_limitation": ModelAssumption(
        key="temperature_model_limitation",
        value="planning curve only",
        rationale="Does not model cell chemistry, transient heating, discharge C-rate, or pack thermal management.",
        source="core.battery.lithium_temperature_capacity_factor.",
        confidence="medium",
    ),
    "salinity_baseline_psu": ModelAssumption(
        key="salinity_baseline_psu",
        value=35.0,
        rationale="Reference seawater salinity for zero salinity/buoyancy uplift.",
        source="core.environment.salinity_buoyancy_penalty.",
        confidence="medium",
    ),
    "seawater_density_baseline_kg_m3": ModelAssumption(
        key="seawater_density_baseline_kg_m3",
        value=1025.0,
        rationale="Reference seawater density for reporting and future density-aware refinements.",
        source="planning assumption.",
        confidence="medium",
    ),
    "salinity_source_policy": ModelAssumption(
        key="salinity_source_policy",
        value="NOAA CO-OPS station when available; NOAA WOA23 climatology when available; standard seawater otherwise",
        rationale="Open-Meteo remains primary METOC; salinity/density are planning modifiers with standard seawater as the safe fallback.",
        source="services.metoc_fusion, services.noaa_coops_salinity, services.woa23_salinity, and app.main.",
        confidence="medium",
    ),
    "generator_fuel_equivalent_factor": ModelAssumption(
        key="generator_fuel_equivalent_factor",
        value="10.0 kWh/gal JP-8/diesel tactical-generator planning factor",
        rationale="Provides a conservative secondary sustainment-planning lens from already computed generator-side energy without double-counting generator efficiency.",
        source="core.sustainment.compute_sustainment_projection.",
        confidence="low-medium",
    ),
    "salinity_buoyancy_penalty_curve": ModelAssumption(
        key="salinity_buoyancy_penalty_curve",
        value="0.5% energy uplift per PSU deviation from 35 PSU, capped at 10%",
        rationale="Represents planning-level trim/ballast and buoyancy burden from salinity-driven density variation.",
        source="Engineering planning assumption implemented in core.environment.salinity_buoyancy_penalty.",
        confidence="low",
    ),
    "salinity_buoyancy_penalty_rationale": ModelAssumption(
        key="salinity_buoyancy_penalty_rationale",
        value="bounded trim/ballast planning uplift",
        rationale="Models energy burden from density-driven trim/ballast correction without claiming high-fidelity hydrodynamics.",
        source="core.environment.salinity_buoyancy_penalty.",
        confidence="low",
    ),
    "payload_mass_penalty_curve": ModelAssumption(
        key="payload_mass_penalty_curve",
        value="multiplier = 1 + min(5, max(0, (payload_weight_kg / vehicle_energy_kwh) * 0.30)) / 100",
        rationale="Applies a small bounded trim/integration planning penalty because payload weight alone is not a direct hydrodynamic drag variable.",
        source="core.energy.payload_weight_energy_multiplier.",
        confidence="low",
    ),
    "payload_energy_class_policy": ModelAssumption(
        key="payload_energy_class_policy",
        value="not an active dependency",
        rationale="Payload burden does not rely on public dry-weight data; payload mass is scaled against vehicle energy class as a trim/integration planning proxy. Payload-specific drag modeling is future work if area, Cd, mounting, buoyancy, and trim data become available.",
        source="core.energy.payload_weight_energy_multiplier.",
        confidence="medium",
    ),
    "launch_recovery_overhead_policy": ModelAssumption(
        key="launch_recovery_overhead_policy",
        value="recoverable payload missions add 0.25 hr overhead; one-way/non-recoverable missions add 0",
        rationale="Represents planning-level launch/recovery burden without modeling docking physics.",
        source="core.energy.launch_recovery_energy_kwh.",
        confidence="low-medium",
    ),
    "launch_recovery_power_basis": ModelAssumption(
        key="launch_recovery_power_basis",
        value="0.5 * vehicle.average_power_kw",
        rationale="Uses a low-power/hover planning proxy when vehicle-specific launch/recovery power is unavailable.",
        source="core.energy.launch_recovery_energy_kwh.",
        confidence="low",
    ),
    "vehicle_specific_hotel_fraction_policy": ModelAssumption(
        key="vehicle_specific_hotel_fraction_policy",
        value="catalog hotel_fraction or hotel_power_fraction overrides default; clamped to 0.20-0.80",
        rationale="Allows heavier sensor/hotel-load vehicles to override the global split without requiring all catalog entries to carry the field.",
        source="core.power.power_model_breakdown.",
        confidence="low",
    ),
    "power_model_nominal_power_scale_sigma": ModelAssumption(
        key="power_model_nominal_power_scale_sigma",
        value=0.03,
        rationale="Samples public-spec and configuration uncertainty around catalog-derived nominal power.",
        source="core.power.sample_power_model_breakdown.",
        confidence="low-medium",
    ),
    "power_model_hotel_fraction_sigma": ModelAssumption(
        key="power_model_hotel_fraction_sigma",
        value=0.06,
        rationale="Samples uncertainty in fixed hotel/sensor/control load share without changing the catalog schema.",
        source="core.power.sample_power_model_breakdown.",
        confidence="low-medium",
    ),
    "power_model_propulsion_multiplier_sigma": ModelAssumption(
        key="power_model_propulsion_multiplier_sigma",
        value=0.10,
        rationale="Samples propulsion/load-state variation around the deterministic speed-power centerline.",
        source="core.power.sample_power_model_breakdown.",
        confidence="low-medium",
    ),
    "power_model_low_speed_penalty_fraction_sigma": ModelAssumption(
        key="power_model_low_speed_penalty_fraction_sigma",
        value=0.05,
        rationale="Samples bounded low-speed route-keeping inefficiency while preserving the existing cap.",
        source="core.power.sample_power_model_breakdown.",
        confidence="low",
    ),
    "power_model_speed_exponent_sigma": ModelAssumption(
        key="power_model_speed_exponent_sigma",
        value=0.25,
        rationale="Samples field variation around the cubic propulsion relationship.",
        source="core.power.sample_power_model_breakdown.",
        confidence="low-medium",
    ),
    "power_model_speed_exponent_clamp": ModelAssumption(
        key="power_model_speed_exponent_clamp",
        value="2.4 to 3.4",
        rationale="Prevents sampled speed-power exponents from leaving the planning-valid displacement/UUV range.",
        source="core.power.sample_power_model_breakdown.",
        confidence="medium",
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
