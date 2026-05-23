"""Pure UUV mission energy calculations."""

from __future__ import annotations

import math
import secrets
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from core.battery import (
    lithium_temperature_capacity_factor,
    sample_usable_battery_fraction,
    usable_battery_energy_kwh,
)
from core.environment import (
    current_components,
    environmental_uplift_factor,
    payload_current_penalty,
    salinity_buoyancy_penalty,
    search_current_duration_multiplier,
)
from core.sustainment import compute_sustainment_projection
from core.geometry import clipped_search_lanes, isr_path_distance_per_loop_km
from core.power import power_model_breakdown, sample_power_model_breakdown, speed_adjusted_power_kw
from models.environment_model import EnvironmentData
from models.mission_model import MissionArea
from models.vehicle_model import VehicleState
from utils.constants import (
    ISR_MISSIONS,
    MONTE_CARLO_RUNS,
    PAYLOAD_MISSIONS,
    SEARCH_MISSIONS,
)


@dataclass(frozen=True)
class SearchPlan:
    """Search lane plan for one track orientation."""

    orientation: str
    track_heading_deg: float
    track_length_km: float
    lanes: int
    turns: int
    total_distance_km: float
    track_distance_km: float
    turn_distance_km: float
    segments: list[tuple[float, float, float, float]]


@dataclass(frozen=True)
class ISRPersistenceResult:
    """ISR endurance calculation for one environmental condition."""

    loop_distance_km: float
    endurance_speed_kts: float
    endurance_speed_kmh: float
    loop_time_hr: float
    available_mission_energy_kwh: float
    power_draw_kw: float
    environmental_multiplier: float
    adjusted_power_draw_kw: float
    max_time_on_station_hr: float
    completed_loops: int
    remaining_partial_loop_pct: float


@dataclass
class SimulationResult:
    """Energy model output and plot-ready arrays."""

    summary: dict[str, object]
    result_rows: list[tuple[str, object, str]]
    equivalent_rows: list[tuple[str, object, str]]
    energy_samples_kwh: np.ndarray
    duration_samples_hr: np.ndarray
    power_samples_kw: np.ndarray
    hotel_power_samples_kw: np.ndarray
    propulsion_power_samples_kw: np.ndarray
    low_speed_penalty_samples_kw: np.ndarray
    mission_sensor_power_samples_kw: np.ndarray
    transit_sensor_power_samples_kw: np.ndarray
    mission_sensor_energy_samples_kwh: np.ndarray
    active_sensor_energy_samples_kwh: np.ndarray
    transit_sensor_energy_samples_kwh: np.ndarray
    active_sensor_duration_samples_hr: np.ndarray
    total_active_power_samples_kw: np.ndarray


def route_leg_time_hr(
    distance_km: float,
    vehicle_speed_kts: float,
    current_speed_kts: float,
    current_dir_deg: float,
    heading_deg: float,
) -> float:
    """Return route-leg time after along-track current adjustment."""
    vehicle_speed_kmh = vehicle_speed_kts * 1.852
    along_kmh = current_components(current_speed_kts, current_dir_deg, heading_deg)[0] * 1.852
    speed_over_ground_kmh = max(vehicle_speed_kmh + along_kmh, vehicle_speed_kmh * 0.25)
    return distance_km / speed_over_ground_kmh if speed_over_ground_kmh > 0 else 9999.0


def search_plan(area: MissionArea, track_spacing_m: float, track_heading_deg: float) -> SearchPlan:
    """Build a clipped swath-lane plan for a search orientation."""
    orientation = "North-South" if track_heading_deg == 0 else "East-West"
    lanes = clipped_search_lanes(area, max(track_spacing_m, 1.0), orientation)
    spacing_km = max(track_spacing_m / 1000.0, 0.001)
    turn_distance = int(lanes["turns"]) * spacing_km * 0.5
    track_distance = float(lanes["track_distance_km"])
    lane_count = max(1, int(lanes["lane_count"]))
    return SearchPlan(
        orientation=orientation,
        track_heading_deg=track_heading_deg,
        track_length_km=track_distance / lane_count,
        lanes=lane_count,
        turns=int(lanes["turns"]),
        total_distance_km=track_distance + turn_distance,
        track_distance_km=track_distance,
        turn_distance_km=turn_distance,
        segments=list(lanes["segments"]),  # type: ignore[arg-type]
    )


def isr_current_power_penalty(current_speed_kts: float, endurance_speed_kts: float) -> float:
    """Return a modest ISR power uplift for station-keeping/current burden."""
    return 0.08 * min(max(current_speed_kts, 0.0) / max(endurance_speed_kts, 0.1), 2.0)


def estimate_power_at_speed_kw(
    vehicle: VehicleState,
    speed_kts: float,
    hotel_fraction: float | None = None,
    speed_exponent: float = 3.0,
    propulsion_multiplier: float = 1.0,
) -> float:
    """Estimate UUV power draw at requested speed using fixed hotel load plus cubic propulsion scaling."""
    return power_model_breakdown(
        vehicle,
        speed_kts,
        hotel_fraction=hotel_fraction,
        speed_exponent=speed_exponent,
        propulsion_multiplier=propulsion_multiplier,
    ).total_power_kw


def sample_mission_sensor_power_kw(mission_type: str, rng: Any) -> float:
    """Return sampled mission-mode onboard sensor/equipment power in kW."""
    if mission_type in PAYLOAD_MISSIONS:
        return float(rng.uniform(0.0, 25.0)) / 1000.0
    if mission_type in ISR_MISSIONS:
        return float(rng.uniform(50.0, 75.0)) / 1000.0
    if mission_type in SEARCH_MISSIONS:
        return float(rng.uniform(75.0, 150.0)) / 1000.0
    return 0.0


def deterministic_mission_sensor_power_kw(mission_type: str) -> float:
    """Return midpoint mission-mode onboard sensor/equipment power in kW."""
    if mission_type in PAYLOAD_MISSIONS:
        return 0.0125
    if mission_type in ISR_MISSIONS:
        return 0.0625
    if mission_type in SEARCH_MISSIONS:
        return 0.1125
    return 0.0


def mission_sensor_power_basis(mission_type: str, enabled: bool = True) -> tuple[str, str]:
    """Return active sensor mode and public-specification basis text."""
    if not enabled:
        return "Disabled", "Mission sensor-mode power sampling disabled."
    if mission_type in PAYLOAD_MISSIONS:
        return (
            "Endurance / Transit",
            "Uniform 0-25 W mission sensor-mode range for low-burden route/transit operation.",
        )
    if mission_type in ISR_MISSIONS:
        return (
            "ISR / Persistence",
            "Uniform 50-75 W mission sensor-mode range for sensing, navigation, processing, communications, and persistence demand.",
        )
    if mission_type in SEARCH_MISSIONS:
        return (
            "Search/MCM / Area Search",
            "Uniform 75-150 W mission sensor-mode range for active Search/MCM sensors, onboard processing, navigation support, and mission-equipment demand.",
        )
    return "None", "No mission sensor-mode range applies to this mission type."


def payload_weight_energy_multiplier(
    payload_weight_kg: float,
    vehicle_energy_kwh: float,
    max_penalty_pct: float = 5.0,
    penalty_per_kg_per_kwh_pct: float = 0.30,
) -> float:
    """
    Convert payload weight into a bounded planning multiplier.

    Payload weight is scaled against vehicle energy class as a small bounded
    trim/integration planning proxy. It is not a direct drag model.
    """
    payload_weight = max(float(payload_weight_kg or 0.0), 0.0)
    energy_class = max(float(vehicle_energy_kwh or 0.0), 0.0)
    if payload_weight <= 0 or energy_class <= 0:
        return 1.0
    penalty_pct = (payload_weight / energy_class) * max(float(penalty_per_kg_per_kwh_pct), 0.0)
    bounded_penalty_pct = min(max(float(max_penalty_pct), 0.0), max(penalty_pct, 0.0))
    return 1.0 + (bounded_penalty_pct / 100.0)


def payload_weight_penalty_pct(payload_weight_kg: float, vehicle_energy_kwh: float) -> float:
    """Return the active payload penalty percentage for reporting."""
    return (payload_weight_energy_multiplier(payload_weight_kg, vehicle_energy_kwh) - 1.0) * 100.0


def payload_recovery_mode(vehicle: VehicleState, return_to_start: bool) -> str:
    """Resolve payload recovery mode from vehicle flags and UI return setting."""
    default_mode = (vehicle.default_payload_recovery_mode or "").strip().lower()
    if default_mode in {"one_way", "one-way", "no_return"}:
        return "one_way"
    if vehicle.recoverable is False or vehicle.rechargeable is False:
        return "one_way"
    return "return_to_start" if return_to_start else "one_way"


def is_vehicle_recoverable(vehicle: VehicleState) -> bool:
    """Return whether launch/recovery overhead should apply by default."""
    return vehicle.recoverable is not False


def is_vehicle_rechargeable(vehicle: VehicleState) -> bool:
    """Return whether recharge wording should apply by default."""
    if vehicle.rechargeable is not None:
        return bool(vehicle.rechargeable)
    return vehicle.recharge_hr > 0


def recharge_feasibility_lens(
    p95_energy_kwh: float,
    mission_duration_hr: float,
    usable_battery_per_set_kwh: float,
    battery_sets_available: int,
    recharge_hr: float,
    rechargeable: bool,
    recoverable: bool,
    recharge_allowed: bool,
) -> dict[str, object]:
    """Return recharge/swap feasibility interpretation from already-computed mission values."""
    p95 = max(float(p95_energy_kwh), 0.0)
    duration = max(float(mission_duration_hr), 0.0)
    usable_per_set = max(float(usable_battery_per_set_kwh), 0.001)
    sets_available = max(int(battery_sets_available), 1)
    recharge_time = max(float(recharge_hr), 0.0)
    total_inventory = usable_per_set * sets_available
    shortfall = max(p95 - total_inventory, 0.0)
    energy_rate = p95 / duration if duration > 0 and p95 > 0 else 0.0
    runtime_per_set = usable_per_set / energy_rate if energy_rate > 0 else 0.0
    recharge_window = runtime_per_set * max(0, sets_available - 1)
    applies = bool(rechargeable and recoverable and recharge_allowed)
    charged_inventory_sufficient = p95 <= total_inventory
    recharge_bottleneck = bool(applies and shortfall > 0 and recharge_time > recharge_window)
    recharge_supported = bool(
        shortfall > 0
        and applies
        and sets_available >= 2
        and recharge_time <= recharge_window
    )
    vehicle_can_recharge = bool(rechargeable and recoverable)
    if not vehicle_can_recharge:
        status = "Not applicable for one-way/non-rechargeable vehicle"
        category = "not_applicable"
    elif not recharge_allowed:
        status = "Recharge not enabled"
        category = "recharge_disabled"
    elif charged_inventory_sufficient:
        status = "Charged inventory sufficient"
        category = "charged_inventory"
    elif recharge_supported:
        status = "Feasible with continuous recharge/swap support"
        category = "recharge_supported"
    elif recharge_bottleneck:
        status = "Recharge bottleneck"
        category = "recharge_bottleneck"
    else:
        status = "Not feasible under current recharge assumptions"
        category = "not_feasible"
    return {
        "recharge_feasibility_status": status,
        "recharge_feasibility_category": category,
        "recharge_energy_rate_kwh_per_hr": energy_rate,
        "runtime_per_battery_set_hr": runtime_per_set,
        "recharge_time_per_set_hr": recharge_time,
        "available_recharge_window_hr": recharge_window,
        "recharge_bottleneck": recharge_bottleneck,
        "in_mission_recharge_shortfall_kwh": shortfall,
        "recharge_energy_required_during_mission_kwh": shortfall,
    }


def launch_recovery_energy_kwh(vehicle: VehicleState, enabled: bool = True) -> tuple[float, float, float]:
    """Return launch/recovery energy, duration, and power for recoverable missions."""
    if not enabled or not is_vehicle_recoverable(vehicle):
        return 0.0, 0.0, 0.0
    overhead_hr = 0.25
    power_kw = max(0.5 * vehicle.average_power_kw, 0.0)
    return overhead_hr * power_kw, overhead_hr, power_kw


def compute_stockpile_requirement(
    conservative_energy_kwh: float,
    usable_battery_per_set_kwh: float,
    missions_per_week: float,
    planning_horizon_days: float,
    generator_efficiency: float = 0.84,
    fuel_energy_kwh_per_gal: float = 38.0,
) -> dict[str, float]:
    """Estimate battery stockpile and recharge fuel requirements for a planning horizon."""
    missions_in_horizon = max(missions_per_week, 0.0) * max(planning_horizon_days, 0.0) / 7.0
    total_mission_energy_kwh = max(conservative_energy_kwh, 0.0) * missions_in_horizon
    usable_per_set = max(usable_battery_per_set_kwh, 0.001)
    generator_eff = max(generator_efficiency, 0.001)
    fuel_energy = max(fuel_energy_kwh_per_gal, 0.001)
    generator_input_energy_kwh = total_mission_energy_kwh / generator_eff
    return {
        "missions_in_horizon": missions_in_horizon,
        "total_mission_energy_kwh": total_mission_energy_kwh,
        "total_mission_energy_joules": total_mission_energy_kwh * 3_600_000.0,
        "battery_sets_without_recharge": float(math.ceil(total_mission_energy_kwh / usable_per_set)),
        "generator_input_energy_kwh": generator_input_energy_kwh,
        "fuel_gallons_equivalent": generator_input_energy_kwh / fuel_energy,
    }


def compute_energy_recommendation_metrics(
    energy_samples_kwh: np.ndarray | list[float],
    validation_adjusted_energy_kwh: float | None = None,
) -> dict[str, float | str | None]:
    """Return recommendation-led energy metrics from Monte Carlo energy samples."""
    samples = np.asarray(energy_samples_kwh, dtype=float)
    samples = samples[np.isfinite(samples)]
    upper_tail_fraction = 0.10
    recommendation_basis = (
        "Mean simulated energy plus one standard deviation; validation-adjusted value used only when provided. "
        "Stress case is the average of the upper 10% of Monte Carlo energy outcomes."
    )
    if samples.size == 0:
        expected = 0.0
        uncertainty = 0.0
        conservative_stress = 0.0
    else:
        expected = float(np.mean(samples))
        uncertainty = float(np.std(samples, ddof=1)) if samples.size > 1 else 0.0
        sorted_samples = np.sort(samples)
        tail_count = max(1, int(math.ceil(upper_tail_fraction * samples.size)))
        conservative_stress = float(np.mean(sorted_samples[-tail_count:]))
    distribution_recommended = expected + uncertainty
    validation_adjusted = (
        float(validation_adjusted_energy_kwh)
        if validation_adjusted_energy_kwh is not None
        else None
    )
    recommended = (
        max(distribution_recommended, validation_adjusted)
        if validation_adjusted is not None
        else distribution_recommended
    )
    return {
        "expected_energy_kwh": expected,
        "energy_uncertainty_allowance_kwh": uncertainty,
        "distribution_recommended_energy_kwh": distribution_recommended,
        "validation_adjusted_energy_kwh": validation_adjusted,
        "recommended_planning_energy_kwh": recommended,
        "conservative_stress_energy_kwh": conservative_stress,
        "upper_tail_fraction": upper_tail_fraction,
        "recommendation_basis": recommendation_basis,
    }


def _isr_loop_coverage(endurance_hr: float, loop_time_hr: float, loop_distance_km: float) -> dict[str, float]:
    """Return full-loop, partial-loop, and patrol-distance coverage for an ISR endurance window."""
    if loop_time_hr <= 0 or loop_distance_km <= 0 or endurance_hr <= 0:
        return {
            "completed_loops_full": 0.0,
            "partial_loop_fraction": 0.0,
            "partial_loop_distance_km": 0.0,
            "total_patrol_distance_km": 0.0,
        }
    completed_loops_full = math.floor(endurance_hr / loop_time_hr)
    remaining_time_hr = max(endurance_hr - (completed_loops_full * loop_time_hr), 0.0)
    partial_loop_fraction = min(max(remaining_time_hr / loop_time_hr, 0.0), 1.0 - 1e-12)
    partial_loop_distance_km = partial_loop_fraction * loop_distance_km
    total_patrol_distance_km = (completed_loops_full * loop_distance_km) + partial_loop_distance_km
    return {
        "completed_loops_full": float(completed_loops_full),
        "partial_loop_fraction": partial_loop_fraction,
        "partial_loop_distance_km": partial_loop_distance_km,
        "total_patrol_distance_km": total_patrol_distance_km,
    }


def compute_isr_persistence(
    loop_distance_km: float,
    usable_energy_kwh: float,
    reserve_fraction: float,
    endurance_speed_kts: float,
    endurance_power_kw: float,
    environmental_multiplier: float,
) -> ISRPersistenceResult:
    """Compute maximum ISR time on station from route/perimeter length and usable energy."""
    # TODO(v3.5+): Model contested-delay stochastic hover/loiter interruptions after speed-power validation stabilizes.
    endurance_speed_kmh = max(endurance_speed_kts * 1.852, 0.001)
    available_mission_energy_kwh = max(usable_energy_kwh * (1.0 - reserve_fraction), 0.0)
    adjusted_power_draw_kw = max(endurance_power_kw * environmental_multiplier, 0.001)
    max_time_on_station_hr = available_mission_energy_kwh / adjusted_power_draw_kw
    loop_time_hr = max(loop_distance_km, 0.0) / endurance_speed_kmh
    completed_loops = int(max_time_on_station_hr // loop_time_hr) if loop_time_hr > 0 else 0
    remaining_partial_loop_pct = (
        (max_time_on_station_hr % loop_time_hr) / loop_time_hr * 100.0
        if loop_time_hr > 0
        else 0.0
    )
    return ISRPersistenceResult(
        loop_distance_km=loop_distance_km,
        endurance_speed_kts=endurance_speed_kts,
        endurance_speed_kmh=endurance_speed_kmh,
        loop_time_hr=loop_time_hr,
        available_mission_energy_kwh=available_mission_energy_kwh,
        power_draw_kw=endurance_power_kw,
        environmental_multiplier=environmental_multiplier,
        adjusted_power_draw_kw=adjusted_power_draw_kw,
        max_time_on_station_hr=max_time_on_station_hr,
        completed_loops=completed_loops,
        remaining_partial_loop_pct=remaining_partial_loop_pct,
    )


def energy_equivalent_rows(kwh: float) -> list[tuple[str, object, str]]:
    """Return equivalent-energy rows for report tables."""
    wh = kwh * 1000.0
    joules = wh * 3600.0
    mj = joules / 1_000_000.0
    gj = mj / 1000.0
    toe = kwh / 11630.0
    barrel_oil_equiv = gj / 6.12 if gj else 0.0
    coal_kg_equiv = mj / 30.0 if mj else 0.0
    return [
        ("Mission energy", kwh, "kWh"),
        ("Mission energy", mj, "MJ"),
        ("Mission energy", gj, "GJ"),
        ("Tonne of oil equivalent", toe, "TOE"),
        ("Barrels-of-oil equivalent", barrel_oil_equiv, "BOE"),
        ("Coal-equivalent energy", coal_kg_equiv, "kg coal @ 30 MJ/kg"),
    ]


def run_energy_simulation(
    vehicle: VehicleState,
    mission_type: str,
    area: MissionArea,
    environment: Optional[EnvironmentData],
    additional_transit_km: float,
    track_spacing_m: float,
    return_to_start: bool,
    speed_kts: float,
    battery_sets_available: int,
    recharge_allowed: bool,
    mission_sequences: int,
    rng_seed: Optional[int] = None,
    monte_carlo_runs: int = MONTE_CARLO_RUNS,
    battery_condition: str = "medium",
    stochastic_usable_battery_enabled: bool = True,
    reserve_fraction: float = 0.0,
    sustainment_missions_per_week: float = 1.0,
    sustainment_planning_weeks: float = 4.0,
    sustainment_generator_efficiency: float = 0.84,
    payload_weight_kg: float = 0.0,
    mission_sensor_power_enabled: bool = True,
    validation_adjusted_energy_kwh: float | None = None,
    deterministic_mode: bool = False,
) -> SimulationResult:
    """Run the single-UUV Monte Carlo mission energy model."""
    environment = environment or EnvironmentData()
    seed_used = int(rng_seed) if rng_seed is not None else secrets.randbits(32)
    if seed_used < 0:
        raise ValueError("rng_seed must be a non-negative integer")
    rng = np.random.default_rng(seed_used)
    n = 1 if deterministic_mode else max(1, int(monte_carlo_runs))
    mission_sequences = max(1, int(mission_sequences))

    current_mean = float(environment.current_speed_kts_mean if environment.current_speed_kts_mean is not None else 0.5)
    current_dir = float(environment.current_direction_deg_mean if environment.current_direction_deg_mean is not None else 0.0)
    temp_mean = float(environment.sea_surface_temp_c_mean if environment.sea_surface_temp_c_mean is not None else 25.0)
    salinity_penalty = salinity_buoyancy_penalty(environment.sea_surface_salinity_psu)
    payload_propulsion_multiplier = payload_weight_energy_multiplier(payload_weight_kg, vehicle.battery_kwh)
    payload_penalty_pct = payload_weight_penalty_pct(payload_weight_kg, vehicle.battery_kwh)
    payload_weight_basis = "energy_class_scaled" if max(float(payload_weight_kg or 0.0), 0.0) > 0 else "No payload carriage penalty applied."
    recovery_mode = payload_recovery_mode(vehicle, bool(return_to_start))
    payload_returns_to_start = recovery_mode == "return_to_start"
    launch_recovery_energy, launch_recovery_overhead_hr, launch_recovery_power_kw = launch_recovery_energy_kwh(vehicle)
    input_speed_kts = max(float(speed_kts or vehicle.nominal_speed_kts), 0.1)
    input_power_breakdown = power_model_breakdown(vehicle, input_speed_kts)
    current_sigma_kts = 0.0 if current_mean <= 0.0 else max(0.02, 0.25 * current_mean)
    sampled_current = (
        np.full(n, max(current_mean, 0.0))
        if deterministic_mode
        else np.clip(rng.normal(current_mean, current_sigma_kts, n), 0, None)
    )
    sampled_temp = np.full(n, temp_mean) if deterministic_mode else rng.normal(temp_mean, 1.5, n)
    sampled_temperature_capacity_factor = np.array([lithium_temperature_capacity_factor(float(temp)) for temp in sampled_temp])
    sampled_battery_fraction = np.array(
        [
            sample_usable_battery_fraction(
                rng,
                condition=battery_condition,
                deterministic_fraction=vehicle.usable_fraction,
                stochastic_enabled=stochastic_usable_battery_enabled and not deterministic_mode,
            )
            for _ in range(n)
        ]
    )
    sampled_usable_battery_per_set = np.array(
        [
            usable_battery_energy_kwh(
                vehicle.battery_kwh,
                usable_fraction=fraction,
                reserve_fraction=reserve_fraction,
                temperature_capacity_factor=temp_factor,
            )
            for fraction, temp_factor in zip(sampled_battery_fraction, sampled_temperature_capacity_factor)
        ]
    )

    usable_battery_per_set = float(np.percentile(sampled_usable_battery_per_set, 50))
    total_available_kwh = usable_battery_per_set * max(1, battery_sets_available)
    energies: list[float] = []
    durations: list[float] = []
    power_samples_kw: list[float] = []
    hotel_power_samples_kw: list[float] = []
    propulsion_power_samples_kw: list[float] = []
    low_speed_penalty_samples_kw: list[float] = []
    mission_sensor_power_samples_kw: list[float] = []
    transit_sensor_power_samples_kw: list[float] = []
    mission_sensor_energy_samples_kwh: list[float] = []
    active_sensor_energy_samples_kwh: list[float] = []
    transit_sensor_energy_samples_kwh: list[float] = []
    active_sensor_duration_samples_hr: list[float] = []
    total_active_power_samples_kw: list[float] = []
    speed_exponent_samples: list[float] = []
    hotel_fraction_samples: list[float] = []
    propulsion_multiplier_samples: list[float] = []
    nominal_power_scale_samples: list[float] = []
    recommended_orientations: list[str] = []
    isr_persistence_results: list[ISRPersistenceResult] = []

    search_options: list[SearchPlan] = []
    if mission_type in SEARCH_MISSIONS:
        search_options = [
            search_plan(area, track_spacing_m, 0),
            search_plan(area, track_spacing_m, 90),
        ]
    isr_loop_distance_km = isr_path_distance_per_loop_km(area) if mission_type in ISR_MISSIONS else 0.0

    for index in range(n):
        cur = float(sampled_current[index])
        temp = float(sampled_temp[index])
        usable_battery_sample = float(sampled_usable_battery_per_set[index])
        sampled_power = (
            power_model_breakdown(vehicle, input_speed_kts)
            if deterministic_mode
            else sample_power_model_breakdown(vehicle, input_speed_kts, rng)
        )
        active_power = sampled_power
        sampled_mission_sensor_power_kw = (
            deterministic_mission_sensor_power_kw(mission_type)
            if deterministic_mode
            else sample_mission_sensor_power_kw(mission_type, rng)
        )
        sampled_transit_sensor_power_kw = (
            (
                deterministic_mission_sensor_power_kw("Route / Transit")
                if deterministic_mode
                else sample_mission_sensor_power_kw("Route / Transit", rng)
            )
            if mission_type in SEARCH_MISSIONS
            else sampled_mission_sensor_power_kw
        )
        mission_sensor_power_kw = sampled_mission_sensor_power_kw if mission_sensor_power_enabled else 0.0
        transit_sensor_power_kw = sampled_transit_sensor_power_kw if mission_sensor_power_enabled else 0.0
        mission_sensor_energy_kwh = 0.0
        active_sensor_energy_kwh = 0.0
        transit_sensor_energy_kwh = 0.0
        active_sensor_duration_hr = 0.0
        total_active_power_kw = active_power.total_power_kw + mission_sensor_power_kw

        if mission_type in PAYLOAD_MISSIONS:
            route_distance = float(area.route_distance_km or 10.0)
            route_heading = float(area.route_heading_deg or 0.0)
            outbound_time = route_leg_time_hr(route_distance, input_speed_kts, cur, current_dir, route_heading)
            return_time = 0.0
            if payload_returns_to_start:
                return_time = route_leg_time_hr(route_distance, input_speed_kts, cur, current_dir, (route_heading + 180) % 360)
            transit_time = additional_transit_km / max(input_speed_kts * 1.852, 0.1)
            duration_single = outbound_time + return_time + transit_time + launch_recovery_overhead_hr
            current_penalty = payload_current_penalty(cur, current_dir, route_heading, input_speed_kts)
            outbound_power = power_model_breakdown(
                vehicle,
                input_speed_kts,
                hotel_fraction=sampled_power.hotel_fraction,
                speed_exponent=sampled_power.speed_exponent,
                propulsion_multiplier=sampled_power.propulsion_multiplier * payload_propulsion_multiplier,
                nominal_power_scale=sampled_power.nominal_power_scale,
                low_speed_penalty_fraction=sampled_power.low_speed_penalty_fraction,
            )
            return_power = sampled_power
            outbound_power_kw = outbound_power.total_power_kw
            return_power_kw = return_power.total_power_kw
            moving_duration = max(outbound_time + transit_time + return_time, 0.001)
            active_power = power_model_breakdown(
                vehicle,
                input_speed_kts,
                hotel_fraction=sampled_power.hotel_fraction,
                speed_exponent=sampled_power.speed_exponent,
                propulsion_multiplier=sampled_power.propulsion_multiplier
                * (((outbound_time + transit_time) * payload_propulsion_multiplier + return_time) / moving_duration),
                nominal_power_scale=sampled_power.nominal_power_scale,
                low_speed_penalty_fraction=sampled_power.low_speed_penalty_fraction,
            )
            environmental_multiplier = environmental_uplift_factor(temp, current_penalty, salinity_penalty)
            total_active_power_kw = active_power.total_power_kw + mission_sensor_power_kw
            active_sensor_duration_hr = outbound_time + return_time + transit_time
            energy_single = (
                (
                    ((outbound_power_kw + mission_sensor_power_kw) * (outbound_time + transit_time))
                    + ((return_power_kw + mission_sensor_power_kw) * return_time)
                )
                * environmental_multiplier
            ) + launch_recovery_energy
            mission_sensor_energy_kwh = mission_sensor_power_kw * active_sensor_duration_hr * environmental_multiplier
            active_sensor_energy_kwh = mission_sensor_energy_kwh
        elif mission_type in ISR_MISSIONS:
            endurance_speed_kts = input_speed_kts
            current_penalty = isr_current_power_penalty(cur, endurance_speed_kts)
            environmental_multiplier = environmental_uplift_factor(temp, current_penalty, salinity_penalty)
            endurance_power_kw = sampled_power.total_power_kw + mission_sensor_power_kw
            total_active_power_kw = endurance_power_kw
            persistence = compute_isr_persistence(
                loop_distance_km=isr_loop_distance_km,
                usable_energy_kwh=usable_battery_sample,
                reserve_fraction=0.0,
                endurance_speed_kts=endurance_speed_kts,
                endurance_power_kw=endurance_power_kw,
                environmental_multiplier=environmental_multiplier,
            )
            isr_persistence_results.append(persistence)
            energy_single = persistence.available_mission_energy_kwh
            duration_single = persistence.max_time_on_station_hr
            active_sensor_duration_hr = duration_single
            mission_sensor_energy_kwh = mission_sensor_power_kw * active_sensor_duration_hr * environmental_multiplier
            active_sensor_energy_kwh = mission_sensor_energy_kwh
        else:
            option_results: list[tuple[float, float, float, float, SearchPlan]] = []
            for option in search_options:
                search_base_duration = option.total_distance_km / max(input_speed_kts * 1.852, 0.1)
                search_duration = search_base_duration * search_current_duration_multiplier(cur, current_dir, option.track_heading_deg, input_speed_kts)
                search_duration += option.turns * 0.01
                transit_duration = additional_transit_km / max(input_speed_kts * 1.852, 0.1)
                duration_candidate = search_duration + transit_duration
                requested_power_kw = sampled_power.total_power_kw
                energy_candidate = (
                    ((requested_power_kw + mission_sensor_power_kw) * search_duration)
                    + ((requested_power_kw + transit_sensor_power_kw) * transit_duration)
                ) * (1 + salinity_penalty)
                option_results.append((energy_candidate, duration_candidate, search_duration, transit_duration, option))

            best_energy, best_duration, best_search_duration, best_transit_duration, best_option = min(option_results, key=lambda item: item[0])
            energy_single = best_energy
            duration_single = best_duration
            total_active_power_kw = active_power.total_power_kw + mission_sensor_power_kw
            active_sensor_duration_hr = best_search_duration
            active_sensor_energy_kwh = mission_sensor_power_kw * best_search_duration * (1 + salinity_penalty)
            transit_sensor_energy_kwh = transit_sensor_power_kw * best_transit_duration * (1 + salinity_penalty)
            mission_sensor_energy_kwh = active_sensor_energy_kwh + transit_sensor_energy_kwh
            recommended_orientations.append(best_option.orientation)

        energies.append(energy_single * mission_sequences)
        durations.append(duration_single * mission_sequences)
        power_samples_kw.append(total_active_power_kw)
        hotel_power_samples_kw.append(active_power.hotel_power_kw)
        propulsion_power_samples_kw.append(active_power.propulsion_power_kw)
        low_speed_penalty_samples_kw.append(active_power.low_speed_penalty_kw)
        mission_sensor_power_samples_kw.append(mission_sensor_power_kw)
        transit_sensor_power_samples_kw.append(transit_sensor_power_kw)
        mission_sensor_energy_samples_kwh.append(mission_sensor_energy_kwh * mission_sequences)
        active_sensor_energy_samples_kwh.append(active_sensor_energy_kwh * mission_sequences)
        transit_sensor_energy_samples_kwh.append(transit_sensor_energy_kwh * mission_sequences)
        active_sensor_duration_samples_hr.append(active_sensor_duration_hr * mission_sequences)
        total_active_power_samples_kw.append(total_active_power_kw)
        speed_exponent_samples.append(active_power.speed_exponent)
        hotel_fraction_samples.append(active_power.hotel_fraction)
        propulsion_multiplier_samples.append(active_power.propulsion_multiplier)
        nominal_power_scale_samples.append(active_power.nominal_power_scale)

    energy_arr = np.array(energies)
    duration_arr = np.array(durations)
    power_arr = np.array(power_samples_kw)
    hotel_power_arr = np.array(hotel_power_samples_kw)
    propulsion_power_arr = np.array(propulsion_power_samples_kw)
    low_speed_penalty_arr = np.array(low_speed_penalty_samples_kw)
    mission_sensor_power_arr = np.array(mission_sensor_power_samples_kw)
    transit_sensor_power_arr = np.array(transit_sensor_power_samples_kw)
    mission_sensor_energy_arr = np.array(mission_sensor_energy_samples_kwh)
    active_sensor_energy_arr = np.array(active_sensor_energy_samples_kwh)
    transit_sensor_energy_arr = np.array(transit_sensor_energy_samples_kwh)
    active_sensor_duration_arr = np.array(active_sensor_duration_samples_hr)
    total_active_power_arr = np.array(total_active_power_samples_kw)
    speed_exponent_arr = np.array(speed_exponent_samples)
    hotel_fraction_arr = np.array(hotel_fraction_samples)
    propulsion_multiplier_arr = np.array(propulsion_multiplier_samples)
    nominal_power_scale_arr = np.array(nominal_power_scale_samples)
    p50 = float(np.percentile(energy_arr, 50))
    p80 = float(np.percentile(energy_arr, 80))
    p95 = float(np.percentile(energy_arr, 95))
    mean_energy = float(np.mean(energy_arr))
    recommendation_metrics = compute_energy_recommendation_metrics(
        energy_arr,
        validation_adjusted_energy_kwh=validation_adjusted_energy_kwh,
    )
    expected_energy = float(recommendation_metrics["expected_energy_kwh"] or 0.0)
    recommended_planning_energy = float(recommendation_metrics["recommended_planning_energy_kwh"] or 0.0)
    conservative_stress_energy = float(recommendation_metrics["conservative_stress_energy_kwh"] or 0.0)
    mean_duration = float(np.mean(duration_arr))
    available_inventory_samples = sampled_usable_battery_per_set * max(1, battery_sets_available)
    inventory_probability = float(np.mean(energy_arr <= available_inventory_samples) * 100.0)
    battery_sets_required_recommended = max(1, math.ceil(recommended_planning_energy / max(usable_battery_per_set, 0.001)))
    battery_sets_required_stress = max(1, math.ceil(conservative_stress_energy / max(usable_battery_per_set, 0.001)))
    battery_sets_required_p80 = max(1, math.ceil(p80 / max(usable_battery_per_set, 0.001)))
    battery_sets_required_p95 = max(1, math.ceil(p95 / max(usable_battery_per_set, 0.001)))
    battery_shortfall_recommended = max(0, battery_sets_required_recommended - max(1, battery_sets_available))
    battery_shortfall_stress = max(0, battery_sets_required_stress - max(1, battery_sets_available))
    battery_shortfall = max(0, battery_sets_required_p80 - max(1, battery_sets_available))
    battery_shortfall_p95 = max(0, battery_sets_required_p95 - max(1, battery_sets_available))
    effective_recharge_allowed = bool(recharge_allowed) and is_vehicle_rechargeable(vehicle)
    recharge_sequences_required = battery_shortfall_recommended if effective_recharge_allowed else 0
    recharge_downtime_hr = recharge_sequences_required * vehicle.recharge_hr
    orientation_summary = "N/A"
    if mission_type in SEARCH_MISSIONS and recommended_orientations:
        orientation_summary = max(set(recommended_orientations), key=recommended_orientations.count)
    search_summary: dict[str, object] = {}
    if mission_type in SEARCH_MISSIONS and search_options:
        selected_search_plan = next(
            (option for option in search_options if option.orientation == orientation_summary),
            search_options[0],
        )
        search_summary = {
            "search_track_distance_km": selected_search_plan.track_distance_km,
            "search_turn_distance_km": selected_search_plan.turn_distance_km,
            "search_total_distance_km": selected_search_plan.total_distance_km + additional_transit_km,
            "search_active_survey_distance_km": selected_search_plan.total_distance_km,
            "search_additional_transit_distance_km": max(float(additional_transit_km or 0.0), 0.0),
            "search_lane_count": selected_search_plan.lanes,
        }
    isr_summary: dict[str, object] = {}
    if isr_persistence_results:
        loop_times = np.array([result.loop_time_hr for result in isr_persistence_results])
        station_times = np.array([result.max_time_on_station_hr for result in isr_persistence_results])
        adjusted_powers = np.array([result.adjusted_power_draw_kw for result in isr_persistence_results])
        env_multipliers = np.array([result.environmental_multiplier for result in isr_persistence_results])
        completed_loops = np.array([result.completed_loops for result in isr_persistence_results])
        loop_energies = adjusted_powers * loop_times
        partial_loops = np.array([result.remaining_partial_loop_pct for result in isr_persistence_results])
        single_set_endurance_hr = float(np.percentile(station_times, 50))
        loop_time_hr = float(np.percentile(loop_times, 50))
        completed_loops_single_set = int(np.percentile(completed_loops, 50))
        total_inventory_endurance_hr = single_set_endurance_hr * max(1, battery_sets_available)
        completed_loops_total_inventory = int(total_inventory_endurance_hr // loop_time_hr) if loop_time_hr > 0 else 0
        adjusted_power_kw = float(np.percentile(adjusted_powers, 50))
        single_set_coverage = _isr_loop_coverage(single_set_endurance_hr, loop_time_hr, isr_loop_distance_km)
        total_inventory_coverage = _isr_loop_coverage(total_inventory_endurance_hr, loop_time_hr, isr_loop_distance_km)
        isr_summary = {
            "isr_loop_distance_km": isr_loop_distance_km,
            "isr_loop_time_hr": loop_time_hr,
            "isr_max_time_on_station_hr": single_set_endurance_hr,
            "isr_p10_time_on_station_hr": float(np.percentile(station_times, 10)),
            "isr_p90_time_on_station_hr": float(np.percentile(station_times, 90)),
            "isr_completed_loops": completed_loops_single_set,
            "isr_remaining_partial_loop_pct": float(np.percentile(partial_loops, 50)),
            "isr_available_mission_energy_kwh": usable_battery_per_set,
            "isr_power_draw_kw": speed_adjusted_power_kw(vehicle, input_speed_kts),
            "isr_adjusted_power_draw_kw": adjusted_power_kw,
            "isr_single_set_endurance_hr": single_set_endurance_hr,
            "isr_total_inventory_endurance_hr": total_inventory_endurance_hr,
            "isr_completed_loops_single_set": completed_loops_single_set,
            "isr_completed_loops_total_inventory": completed_loops_total_inventory,
            "isr_completed_loops_full_single_set": int(single_set_coverage["completed_loops_full"]),
            "isr_completed_loops_full_total_inventory": int(total_inventory_coverage["completed_loops_full"]),
            "isr_partial_loop_fraction_single_set": single_set_coverage["partial_loop_fraction"],
            "isr_partial_loop_fraction_total_inventory": total_inventory_coverage["partial_loop_fraction"],
            "isr_partial_loop_distance_km_single_set": single_set_coverage["partial_loop_distance_km"],
            "isr_partial_loop_distance_km_total_inventory": total_inventory_coverage["partial_loop_distance_km"],
            "isr_total_patrol_distance_km_single_set": single_set_coverage["total_patrol_distance_km"],
            "isr_total_patrol_distance_km_total_inventory": total_inventory_coverage["total_patrol_distance_km"],
            "isr_swap_window_hr": single_set_endurance_hr,
            "isr_adjusted_power_kw": adjusted_power_kw,
            "isr_loop_energy_kwh": float(np.percentile(loop_energies, 50)),
            "isr_total_inventory_usable_energy_kwh": total_available_kwh,
            "isr_environmental_multiplier": float(np.percentile(env_multipliers, 50)),
            "isr_patrol_geometry": area.geometry_type,
        }

    mean_temperature_capacity_factor = lithium_temperature_capacity_factor(temp_mean)
    mean_temperature_derating_pct = (1.0 - mean_temperature_capacity_factor) * 100.0
    mean_temp_uplift_pct = 0.0
    mean_salinity_uplift_pct = salinity_penalty * 100.0
    mean_current_uplift_pct = 0.0
    mean_environmental_multiplier = 1.0 + (mean_temp_uplift_pct + mean_salinity_uplift_pct) / 100.0
    payload_total_modeled_distance_km = 0.0
    if mission_type in PAYLOAD_MISSIONS:
        route_distance_for_summary = float(area.route_distance_km or 10.0)
        payload_total_modeled_distance_km = (
            route_distance_for_summary * (2.0 if payload_returns_to_start else 1.0)
        ) + max(float(additional_transit_km or 0.0), 0.0)
        mean_current_uplift_pct = payload_current_penalty(
            current_mean,
            current_dir,
            float(area.route_heading_deg or 0.0),
            input_speed_kts,
        ) * 100.0
        mean_environmental_multiplier = 1.0 + (mean_temp_uplift_pct + mean_current_uplift_pct + mean_salinity_uplift_pct) / 100.0
    elif mission_type in ISR_MISSIONS:
        mean_current_uplift_pct = isr_current_power_penalty(current_mean, input_speed_kts) * 100.0
        mean_environmental_multiplier = 1.0 + (mean_temp_uplift_pct + mean_current_uplift_pct + mean_salinity_uplift_pct) / 100.0
    elif mission_type in SEARCH_MISSIONS and search_options:
        selected_search_plan = next(
            (option for option in search_options if option.orientation == orientation_summary),
            search_options[0],
        )
        mean_current_uplift_pct = (
            search_current_duration_multiplier(
                current_mean,
                current_dir,
                selected_search_plan.track_heading_deg,
                input_speed_kts,
            )
            - 1.0
        ) * 100.0
        mean_environmental_multiplier = (1.0 + mean_current_uplift_pct / 100.0) * (1.0 + (mean_temp_uplift_pct + mean_salinity_uplift_pct) / 100.0)

    if mission_type in ISR_MISSIONS:
        planning_energy_basis = "mission_total"
        planning_energy_kwh = recommended_planning_energy
        planning_duration_basis = "endurance_window"
        planning_duration_hr = float(isr_summary.get("isr_single_set_endurance_hr", mean_duration))
    else:
        planning_energy_basis = "mission_total"
        planning_energy_kwh = recommended_planning_energy
        planning_duration_basis = "mission_duration"
        planning_duration_hr = mean_duration

    sustainment_projection = compute_sustainment_projection(
        planning_energy_kwh=planning_energy_kwh,
        missions_per_week=sustainment_missions_per_week,
        planning_weeks=sustainment_planning_weeks,
        usable_battery_per_set_kwh=usable_battery_per_set,
        battery_sets_available=max(1, battery_sets_available),
        generator_efficiency=sustainment_generator_efficiency,
    )
    recharge_feasibility = recharge_feasibility_lens(
        p95_energy_kwh=recommended_planning_energy,
        mission_duration_hr=mean_duration,
        usable_battery_per_set_kwh=usable_battery_per_set,
        battery_sets_available=max(1, battery_sets_available),
        recharge_hr=vehicle.recharge_hr,
        rechargeable=is_vehicle_rechargeable(vehicle),
        recoverable=is_vehicle_recoverable(vehicle),
        recharge_allowed=bool(recharge_allowed),
    )
    active_sensor_mode, sensor_power_basis = mission_sensor_power_basis(
        mission_type,
        enabled=bool(mission_sensor_power_enabled),
    )

    summary = {
        "platform": vehicle.name,
        "mission_type": mission_type,
        "mean_energy_kwh": mean_energy,
        **recommendation_metrics,
        "p50_energy_kwh": p50,
        "p80_energy_kwh": p80,
        "p95_energy_kwh": p95,
        "planning_energy_basis": planning_energy_basis,
        "planning_percentile": "recommendation",
        "planning_energy_kwh": planning_energy_kwh,
        "conservative_energy_kwh": conservative_stress_energy,
        "planning_duration_basis": planning_duration_basis,
        "planning_duration_hr": planning_duration_hr,
        "mean_duration_hr": mean_duration,
        "elapsed_with_recharge_hr": mean_duration + recharge_downtime_hr,
        "inventory_sufficiency_probability_pct": inventory_probability,
        "battery_inventory_sufficient_no_recharge": battery_shortfall_recommended == 0,
        "battery_inventory_sufficient_recommended": battery_shortfall_recommended == 0,
        "battery_inventory_sufficient_stress": battery_shortfall_stress == 0,
        "battery_sets_required_recommended": battery_sets_required_recommended,
        "battery_sets_required_recommended_planning": battery_sets_required_recommended,
        "battery_sets_required_stress": battery_sets_required_stress,
        "battery_sets_required_conservative_stress": battery_sets_required_stress,
        "battery_sets_required_p80": battery_sets_required_p80,
        "battery_sets_required_p95": battery_sets_required_p95,
        "battery_sets_available": max(1, battery_sets_available),
        "battery_shortfall_recommended": battery_shortfall_recommended,
        "battery_shortfall_stress": battery_shortfall_stress,
        "battery_shortfall_p80": battery_shortfall,
        "battery_shortfall_p95": battery_shortfall_p95,
        "recharge_sequences_required": recharge_sequences_required,
        "recharge_allowed": effective_recharge_allowed,
        "vehicle_recoverable": is_vehicle_recoverable(vehicle),
        "vehicle_rechargeable": is_vehicle_rechargeable(vehicle),
        "vehicle_recharge_hr": vehicle.recharge_hr,
        "payload_recovery_mode": recovery_mode if mission_type in PAYLOAD_MISSIONS else "not_applicable",
        "payload_one_way_catalog_note": (
            "Vehicle catalog marks this platform as one-way/non-rechargeable; route/transit planning uses one-way route energy."
            if mission_type in PAYLOAD_MISSIONS and recovery_mode == "one_way" and (vehicle.recoverable is False or not is_vehicle_rechargeable(vehicle))
            else ""
        ),
        "launch_recovery_overhead_hr": launch_recovery_overhead_hr if mission_type in PAYLOAD_MISSIONS else 0.0,
        "launch_recovery_power_kw": launch_recovery_power_kw if mission_type in PAYLOAD_MISSIONS else 0.0,
        "launch_recovery_energy_kwh": launch_recovery_energy if mission_type in PAYLOAD_MISSIONS else 0.0,
        "recharge_downtime_hr": recharge_downtime_hr,
        "recommended_track_orientation": orientation_summary,
        "monte_carlo_runs": n,
        "mission_sequences": mission_sequences,
        "rng_seed": seed_used,
        "battery_nameplate_kwh": vehicle.battery_kwh,
        "usable_fraction": vehicle.usable_fraction,
        "usable_battery_per_set_kwh": usable_battery_per_set,
        "total_available_kwh": total_available_kwh,
        "usable_battery_variability_enabled": bool(stochastic_usable_battery_enabled),
        "battery_condition_assumption": str(battery_condition).lower(),
        "battery_usable_fraction_p10": float(np.percentile(sampled_battery_fraction, 10)),
        "battery_usable_fraction_p50": float(np.percentile(sampled_battery_fraction, 50)),
        "battery_usable_fraction_p90": float(np.percentile(sampled_battery_fraction, 90)),
        "battery_usable_fraction_mean": float(np.mean(sampled_battery_fraction)),
        "operator_reserve_fraction": max(0.0, min(float(reserve_fraction), 0.95)),
        "temperature_capacity_factor": mean_temperature_capacity_factor,
        "temperature_derating_pct": mean_temperature_derating_pct,
        "temperature_derating_basis": "lithium_temperature_capacity_derating_v1",
        "source_note": vehicle.source_note,
        "usable_basis": vehicle.usable_basis,
        "track_spacing_m": track_spacing_m,
        "speed_kts": input_speed_kts,
        "nominal_speed_kts": input_power_breakdown.nominal_speed_kts,
        "nominal_average_power_kw": input_power_breakdown.nominal_power_kw,
        "speed_adjusted_power_kw": input_power_breakdown.total_power_kw,
        "hotel_power_kw": input_power_breakdown.hotel_power_kw,
        "propulsion_power_kw": input_power_breakdown.propulsion_power_kw,
        "low_speed_penalty_kw": input_power_breakdown.low_speed_penalty_kw,
        "hotel_power_fraction": input_power_breakdown.hotel_fraction,
        "min_efficient_speed_kts": input_power_breakdown.min_efficient_speed_kts,
        "mission_sensor_power_enabled": bool(mission_sensor_power_enabled),
        "mission_sensor_power_mean_kw": float(np.mean(mission_sensor_power_arr)),
        "mission_sensor_power_p10_kw": float(np.percentile(mission_sensor_power_arr, 10)),
        "mission_sensor_power_p50_kw": float(np.percentile(mission_sensor_power_arr, 50)),
        "mission_sensor_power_p90_kw": float(np.percentile(mission_sensor_power_arr, 90)),
        "mission_sensor_power_mean_w": float(np.mean(mission_sensor_power_arr) * 1000.0),
        "mission_sensor_power_p10_w": float(np.percentile(mission_sensor_power_arr, 10) * 1000.0),
        "mission_sensor_power_p50_w": float(np.percentile(mission_sensor_power_arr, 50) * 1000.0),
        "mission_sensor_power_p90_w": float(np.percentile(mission_sensor_power_arr, 90) * 1000.0),
        "mission_sensor_power_range_kw": f"{float(np.min(mission_sensor_power_arr)):.3f}-{float(np.max(mission_sensor_power_arr)):.3f}",
        "mission_sensor_power_basis": sensor_power_basis,
        "active_sensor_mode": active_sensor_mode,
        "active_sensor_duration_mean_hr": float(np.mean(active_sensor_duration_arr)),
        "mission_sensor_energy_mean_kwh": float(np.mean(mission_sensor_energy_arr)),
        "mission_sensor_energy_p50_kwh": float(np.percentile(active_sensor_energy_arr, 50)),
        "mission_sensor_total_energy_p50_kwh": float(np.percentile(mission_sensor_energy_arr, 50)),
        "transit_sensor_energy_p50_kwh": float(np.percentile(transit_sensor_energy_arr, 50)),
        "search_active_survey_duration_mean_hr": float(np.mean(active_sensor_duration_arr)) if mission_type in SEARCH_MISSIONS else 0.0,
        "search_additional_transit_duration_mean_hr": max(float(np.mean(duration_arr) - np.mean(active_sensor_duration_arr)), 0.0) if mission_type in SEARCH_MISSIONS else 0.0,
        "transit_sensor_power_mean_kw": float(np.mean(transit_sensor_power_arr)),
        "transit_sensor_power_p50_kw": float(np.percentile(transit_sensor_power_arr, 50)),
        "transit_sensor_power_mean_w": float(np.mean(transit_sensor_power_arr) * 1000.0),
        "transit_sensor_power_p50_w": float(np.percentile(transit_sensor_power_arr, 50) * 1000.0),
        "total_active_power_mean_kw": float(np.mean(total_active_power_arr)),
        "total_active_power_p50_kw": float(np.percentile(total_active_power_arr, 50)),
        "vehicle_speed_power_p50_kw": float(np.percentile(total_active_power_arr - mission_sensor_power_arr, 50)),
        "power_draw_mean_kw": float(np.mean(power_arr)),
        "power_draw_p10_kw": float(np.percentile(power_arr, 10)),
        "power_draw_p50_kw": float(np.percentile(power_arr, 50)),
        "power_draw_p90_kw": float(np.percentile(power_arr, 90)),
        "speed_exponent_mean": float(np.mean(speed_exponent_arr)),
        "hotel_fraction_mean": float(np.mean(hotel_fraction_arr)),
        "propulsion_multiplier_mean": float(np.mean(propulsion_multiplier_arr)),
        "nominal_power_scale_mean": float(np.mean(nominal_power_scale_arr)),
        "search_area_km2": area.area_km2 if mission_type in SEARCH_MISSIONS else None,
        "search_width_km": area.width_km,
        "search_height_km": area.height_km,
        "route_distance_km": area.route_distance_km,
        "payload_total_modeled_distance_km": payload_total_modeled_distance_km if mission_type in PAYLOAD_MISSIONS else 0.0,
        "route_heading_deg": area.route_heading_deg,
        "current_uplift_pct": mean_current_uplift_pct,
        "temp_uplift_pct": mean_temp_uplift_pct,
        "salinity_uplift_pct": mean_salinity_uplift_pct,
        "environmental_multiplier": mean_environmental_multiplier,
        "payload_weight_kg": max(float(payload_weight_kg or 0.0), 0.0),
        "payload_weight_penalty_pct": payload_penalty_pct if mission_type in PAYLOAD_MISSIONS else 0.0,
        "payload_weight_multiplier": payload_propulsion_multiplier if mission_type in PAYLOAD_MISSIONS else 1.0,
        "payload_weight_penalty_multiplier": payload_propulsion_multiplier if mission_type in PAYLOAD_MISSIONS else 1.0,
        "payload_weight_penalty_basis": payload_weight_basis if mission_type in PAYLOAD_MISSIONS else "Not applicable to this mission type.",
        "payload_weight_basis": payload_weight_basis if mission_type in PAYLOAD_MISSIONS else "Not applicable to this mission type.",
        "reserve_margin_per_set_kwh": max(vehicle.battery_kwh - usable_battery_per_set, 0.0),
        "battery_remaining_pct_recommended": max(0.0, min(100.0, 100.0 * (1.0 - recommended_planning_energy / max(total_available_kwh, 0.001)))),
        "battery_remaining_pct_stress": max(0.0, min(100.0, 100.0 * (1.0 - conservative_stress_energy / max(total_available_kwh, 0.001)))),
        "battery_remaining_pct_p80": max(0.0, min(100.0, 100.0 * (1.0 - p80 / max(total_available_kwh, 0.001)))),
        **{f"sustainment_{key}": value for key, value in sustainment_projection.items()},
        **recharge_feasibility,
        **search_summary,
        **isr_summary,
    }
    if mission_type in ISR_MISSIONS:
        summary["endurance_window_hr"] = summary.get("isr_total_inventory_endurance_hr")
        summary["total_inventory_endurance_hr"] = summary.get("isr_total_inventory_endurance_hr")
        summary["single_set_endurance_hr"] = summary.get("isr_single_set_endurance_hr")

    one_way_inventory = not is_vehicle_rechargeable(vehicle)
    inventory_unit_plural = "units" if one_way_inventory else "sets"
    rows = [
        ("Platform", vehicle.name, ""),
        ("Mission type", mission_type, ""),
        ("Mission sequences", mission_sequences, "runs"),
        ("Expected energy", expected_energy, "kWh"),
        ("Uncertainty allowance", recommendation_metrics["energy_uncertainty_allowance_kwh"], "kWh"),
        ("Planning recommendation", recommended_planning_energy, "kWh"),
        ("Stress case", conservative_stress_energy, "kWh"),
        ("Mean mission duration", mean_duration, "hr"),
        ("Battery nameplate capacity", vehicle.battery_kwh, "kWh"),
        ("Usable planning energy per vehicle unit" if one_way_inventory else "Usable planning energy per set", usable_battery_per_set, "kWh"),
        ("Battery condition assumption", str(battery_condition).lower(), ""),
        ("Temperature capacity factor", mean_temperature_capacity_factor, ""),
        ("Operator reserve fraction", reserve_fraction, ""),
        ("Usable battery basis", vehicle.usable_basis, ""),
        ("Nominal average power", input_power_breakdown.nominal_power_kw, "kW"),
        ("Speed-adjusted power", input_power_breakdown.total_power_kw, "kW"),
        ("Hotel power component", input_power_breakdown.hotel_power_kw, "kW"),
        ("Propulsion power component", input_power_breakdown.propulsion_power_kw, "kW"),
        ("Low-speed power correction", input_power_breakdown.low_speed_penalty_kw, "kW"),
        ("Sensor load", summary["mission_sensor_power_p50_w"], "W"),
        (
            "Sensor load range",
            f"{summary['mission_sensor_power_p10_w']:.0f}-{summary['mission_sensor_power_p90_w']:.0f}",
            "W",
        ),
        ("Mission sensor active duration", summary["active_sensor_duration_mean_hr"], "hr"),
        ("Sensor energy", summary["mission_sensor_energy_p50_kwh"], "kWh"),
        ("Transit sensor energy", summary["transit_sensor_energy_p50_kwh"], "kWh"),
        ("Sensor-load basis", summary["mission_sensor_power_basis"], ""),
        (
            "Sensor-use logic",
            "Active search/survey receives Search/MCM sensor-mode power; added transit receives Route/Transit sensor-mode power."
            if mission_type in SEARCH_MISSIONS
            else "",
            "",
        ),
        ("Carried equipment weight", max(float(payload_weight_kg or 0.0), 0.0), "kg"),
        ("Equipment carriage penalty", payload_penalty_pct if mission_type in PAYLOAD_MISSIONS else 0.0, "%"),
        ("Equipment propulsion penalty multiplier", payload_propulsion_multiplier if mission_type in PAYLOAD_MISSIONS else 1.0, ""),
        ("Launch/recovery overhead", launch_recovery_energy if mission_type in PAYLOAD_MISSIONS else 0.0, "kWh"),
        ("Vehicle units on hand" if one_way_inventory else "Battery sets on hand", battery_sets_available, inventory_unit_plural),
        ("Vehicle inventory sufficiency" if one_way_inventory else "Battery inventory without recharge", "Sufficient" if battery_shortfall_recommended == 0 else "Not sufficient", ""),
        ("Vehicle inventory sufficiency across Monte Carlo runs" if one_way_inventory else "Battery inventory sufficiency across Monte Carlo runs", inventory_probability, "%"),
        ("Vehicle units needed" if one_way_inventory else "Battery sets needed", battery_sets_required_recommended, inventory_unit_plural),
        ("Stress-case vehicle units" if one_way_inventory else "Stress-case battery sets", battery_sets_required_stress, inventory_unit_plural),
        ("Vehicle inventory shortfall" if one_way_inventory else "Battery shortfall", battery_shortfall_recommended, inventory_unit_plural),
        ("Stress-case vehicle shortfall" if one_way_inventory else "Stress-case battery shortfall", battery_shortfall_stress, inventory_unit_plural),
        ("Replacement inventory units required" if one_way_inventory else "Recharge / swap sequences required", battery_shortfall_recommended if one_way_inventory else recharge_sequences_required, inventory_unit_plural if one_way_inventory else "sequences"),
        ("Replacement inventory planning delay" if one_way_inventory else "Recharge downtime", 0.0 if one_way_inventory else recharge_downtime_hr, "hr"),
        ("Elapsed mission time" if one_way_inventory else "Elapsed time incl. recharge", mean_duration if one_way_inventory else mean_duration + recharge_downtime_hr, "hr"),
    ]
    if mission_type in ISR_MISSIONS:
        rows.extend(
            [
                ("ISR patrol geometry", area.geometry_type, ""),
                ("ISR patrol loop distance", isr_summary.get("isr_loop_distance_km", 0.0), "km"),
                ("ISR loop time", isr_summary.get("isr_loop_time_hr", 0.0), "hr"),
                ("Estimated ISR time on station", isr_summary.get("isr_single_set_endurance_hr", 0.0), "hr"),
                ("ISR endurance per installed set", isr_summary.get("isr_single_set_endurance_hr", 0.0), "hr"),
                ("ISR endurance using total inventory", isr_summary.get("isr_total_inventory_endurance_hr", 0.0), "hr"),
                ("Completed ISR patrol loops per installed set", isr_summary.get("isr_completed_loops_single_set", 0), "loops"),
                ("Completed ISR patrol loops using total inventory", isr_summary.get("isr_completed_loops_total_inventory", 0), "loops"),
                ("Partial next-loop distance per installed set", isr_summary.get("isr_partial_loop_distance_km_single_set", 0.0), "km"),
                ("Partial next-loop distance using total inventory", isr_summary.get("isr_partial_loop_distance_km_total_inventory", 0.0), "km"),
                ("Total patrol distance per installed set", isr_summary.get("isr_total_patrol_distance_km_single_set", 0.0), "km"),
                ("Total patrol distance using total inventory", isr_summary.get("isr_total_patrol_distance_km_total_inventory", 0.0), "km"),
                ("Remaining partial loop", isr_summary.get("isr_remaining_partial_loop_pct", 0.0), "%"),
                ("Adjusted endurance power draw", isr_summary.get("isr_adjusted_power_draw_kw", 0.0), "kW"),
                ("ISR loop energy", isr_summary.get("isr_loop_energy_kwh", 0.0), "kWh"),
                ("Reserve / battery-health margin per set", summary["reserve_margin_per_set_kwh"], "kWh"),
            ]
        )
    if mission_type in SEARCH_MISSIONS:
        rows.extend(
            [
                ("Recommended track orientation", orientation_summary, ""),
                ("Estimated search track distance", search_summary.get("search_track_distance_km", 0.0), "km"),
                ("Estimated total search distance", search_summary.get("search_total_distance_km", 0.0), "km"),
                ("Search lane count", search_summary.get("search_lane_count", 0), "lanes"),
            ]
        )
    rows.extend(
        [
            ("Monte Carlo random seed", seed_used, ""),
            ("Monte Carlo runs", n, "fixed"),
        ]
    )
    return SimulationResult(
        summary=summary,
        result_rows=rows,
        equivalent_rows=energy_equivalent_rows(p80),
        energy_samples_kwh=energy_arr,
        duration_samples_hr=duration_arr,
        power_samples_kw=power_arr,
        hotel_power_samples_kw=hotel_power_arr,
        propulsion_power_samples_kw=propulsion_power_arr,
        low_speed_penalty_samples_kw=low_speed_penalty_arr,
        mission_sensor_power_samples_kw=mission_sensor_power_arr,
        transit_sensor_power_samples_kw=transit_sensor_power_arr,
        mission_sensor_energy_samples_kwh=mission_sensor_energy_arr,
        active_sensor_energy_samples_kwh=active_sensor_energy_arr,
        transit_sensor_energy_samples_kwh=transit_sensor_energy_arr,
        active_sensor_duration_samples_hr=active_sensor_duration_arr,
        total_active_power_samples_kw=total_active_power_arr,
    )
