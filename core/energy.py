"""Pure UUV mission energy calculations."""

from __future__ import annotations

import math
import secrets
from dataclasses import dataclass
from typing import Optional

import numpy as np

from core.environment import (
    current_components,
    environmental_uplift_factor,
    payload_current_penalty,
    search_current_duration_multiplier,
    temperature_energy_penalty,
)
from core.geometry import clipped_search_lanes, isr_path_distance_per_loop_km
from models.environment_model import EnvironmentData
from models.mission_model import MissionArea
from models.vehicle_model import VehicleState
from utils.constants import ISR_MISSIONS, MONTE_CARLO_RUNS, PAYLOAD_MISSIONS, SEARCH_MISSIONS


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


def compute_isr_persistence(
    loop_distance_km: float,
    usable_energy_kwh: float,
    reserve_fraction: float,
    endurance_speed_kts: float,
    endurance_power_kw: float,
    environmental_multiplier: float,
) -> ISRPersistenceResult:
    """Compute maximum ISR time on station from route/perimeter length and usable energy."""
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
) -> SimulationResult:
    """Run the single-UUV Monte Carlo mission energy model."""
    environment = environment or EnvironmentData()
    seed_used = int(rng_seed) if rng_seed is not None else secrets.randbits(32)
    if seed_used < 0:
        raise ValueError("rng_seed must be a non-negative integer")
    rng = np.random.default_rng(seed_used)
    n = max(1, int(monte_carlo_runs))
    mission_sequences = max(1, int(mission_sequences))

    current_mean = float(environment.current_speed_kts_mean if environment.current_speed_kts_mean is not None else 0.5)
    current_dir = float(environment.current_direction_deg_mean if environment.current_direction_deg_mean is not None else 0.0)
    temp_mean = float(environment.sea_surface_temp_c_mean if environment.sea_surface_temp_c_mean is not None else 25.0)
    current_sigma_kts = max(0.10, 0.25 * max(current_mean, 0.1))
    sampled_current = np.clip(rng.normal(current_mean, current_sigma_kts, n), 0, None)
    sampled_temp = rng.normal(temp_mean, 1.5, n)

    usable_battery_per_set = vehicle.usable_battery_per_set_kwh
    total_available_kwh = usable_battery_per_set * max(1, battery_sets_available)
    energies: list[float] = []
    durations: list[float] = []
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
        temp_penalty = temperature_energy_penalty(temp)

        if mission_type in PAYLOAD_MISSIONS:
            route_distance = float(area.route_distance_km or 10.0)
            route_heading = float(area.route_heading_deg or 0.0)
            outbound_time = route_leg_time_hr(route_distance, speed_kts, cur, current_dir, route_heading)
            return_time = 0.0
            if return_to_start:
                return_time = route_leg_time_hr(route_distance, speed_kts, cur, current_dir, (route_heading + 180) % 360)
            transit_time = additional_transit_km / max(speed_kts * 1.852, 0.1)
            duration_single = outbound_time + return_time + transit_time
            current_penalty = payload_current_penalty(cur, current_dir, route_heading, speed_kts)
            energy_single = vehicle.average_power_kw * duration_single * environmental_uplift_factor(temp, current_penalty)
        elif mission_type in ISR_MISSIONS:
            endurance_speed_kts = max(float(speed_kts or vehicle.nominal_speed_kts), 0.1)
            current_penalty = isr_current_power_penalty(cur, endurance_speed_kts)
            environmental_multiplier = environmental_uplift_factor(temp, current_penalty)
            persistence = compute_isr_persistence(
                loop_distance_km=isr_loop_distance_km,
                usable_energy_kwh=usable_battery_per_set,
                reserve_fraction=0.0,
                endurance_speed_kts=endurance_speed_kts,
                endurance_power_kw=vehicle.average_power_kw,
                environmental_multiplier=environmental_multiplier,
            )
            isr_persistence_results.append(persistence)
            energy_single = persistence.available_mission_energy_kwh
            duration_single = persistence.max_time_on_station_hr
        else:
            option_results: list[tuple[float, float, SearchPlan]] = []
            for option in search_options:
                distance = option.total_distance_km + additional_transit_km
                base_duration = distance / max(speed_kts * 1.852, 0.1)
                duration_candidate = base_duration * search_current_duration_multiplier(cur, current_dir, option.track_heading_deg, speed_kts)
                duration_candidate += option.turns * 0.01
                energy_candidate = vehicle.average_power_kw * duration_candidate * (1 + temp_penalty)
                option_results.append((energy_candidate, duration_candidate, option))

            best_energy, best_duration, best_option = min(option_results, key=lambda item: item[0])
            energy_single = best_energy
            duration_single = best_duration
            recommended_orientations.append(best_option.orientation)

        energies.append(energy_single * mission_sequences)
        durations.append(duration_single * mission_sequences)

    energy_arr = np.array(energies)
    duration_arr = np.array(durations)
    p50 = float(np.percentile(energy_arr, 50))
    p80 = float(np.percentile(energy_arr, 80))
    p95 = float(np.percentile(energy_arr, 95))
    mean_energy = float(np.mean(energy_arr))
    mean_duration = float(np.mean(duration_arr))
    inventory_probability = float(np.mean(energy_arr <= total_available_kwh) * 100.0)
    battery_sets_required_p80 = max(1, math.ceil(p80 / max(usable_battery_per_set, 0.001)))
    battery_shortfall = max(0, battery_sets_required_p80 - max(1, battery_sets_available))
    recharge_sequences_required = battery_shortfall if recharge_allowed else 0
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
            "search_lane_count": selected_search_plan.lanes,
        }
    isr_summary: dict[str, object] = {}
    if isr_persistence_results:
        loop_times = np.array([result.loop_time_hr for result in isr_persistence_results])
        station_times = np.array([result.max_time_on_station_hr for result in isr_persistence_results])
        adjusted_powers = np.array([result.adjusted_power_draw_kw for result in isr_persistence_results])
        env_multipliers = np.array([result.environmental_multiplier for result in isr_persistence_results])
        completed_loops = np.array([result.completed_loops for result in isr_persistence_results])
        partial_loops = np.array([result.remaining_partial_loop_pct for result in isr_persistence_results])
        isr_summary = {
            "isr_loop_distance_km": isr_loop_distance_km,
            "isr_loop_time_hr": float(np.percentile(loop_times, 50)),
            "isr_max_time_on_station_hr": float(np.percentile(station_times, 50)),
            "isr_p10_time_on_station_hr": float(np.percentile(station_times, 10)),
            "isr_p90_time_on_station_hr": float(np.percentile(station_times, 90)),
            "isr_completed_loops": int(np.percentile(completed_loops, 50)),
            "isr_remaining_partial_loop_pct": float(np.percentile(partial_loops, 50)),
            "isr_available_mission_energy_kwh": usable_battery_per_set,
            "isr_power_draw_kw": vehicle.average_power_kw,
            "isr_adjusted_power_draw_kw": float(np.percentile(adjusted_powers, 50)),
            "isr_environmental_multiplier": float(np.percentile(env_multipliers, 50)),
            "isr_patrol_geometry": area.geometry_type,
        }

    mean_temp_uplift_pct = temperature_energy_penalty(temp_mean) * 100.0
    mean_current_uplift_pct = 0.0
    mean_environmental_multiplier = 1.0 + (mean_temp_uplift_pct / 100.0)
    if mission_type in PAYLOAD_MISSIONS:
        mean_current_uplift_pct = payload_current_penalty(
            current_mean,
            current_dir,
            float(area.route_heading_deg or 0.0),
            speed_kts,
        ) * 100.0
        mean_environmental_multiplier = 1.0 + (mean_temp_uplift_pct + mean_current_uplift_pct) / 100.0
    elif mission_type in ISR_MISSIONS:
        mean_current_uplift_pct = isr_current_power_penalty(current_mean, max(float(speed_kts or vehicle.nominal_speed_kts), 0.1)) * 100.0
        mean_environmental_multiplier = 1.0 + (mean_temp_uplift_pct + mean_current_uplift_pct) / 100.0
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
                speed_kts,
            )
            - 1.0
        ) * 100.0
        mean_environmental_multiplier = (1.0 + mean_current_uplift_pct / 100.0) * (1.0 + mean_temp_uplift_pct / 100.0)

    summary = {
        "platform": vehicle.name,
        "mission_type": mission_type,
        "mean_energy_kwh": mean_energy,
        "p50_energy_kwh": p50,
        "p80_energy_kwh": p80,
        "p95_energy_kwh": p95,
        "mean_duration_hr": mean_duration,
        "elapsed_with_recharge_hr": mean_duration + recharge_downtime_hr,
        "inventory_sufficiency_probability_pct": inventory_probability,
        "battery_inventory_sufficient_no_recharge": battery_shortfall == 0,
        "battery_sets_required_p80": battery_sets_required_p80,
        "battery_sets_available": max(1, battery_sets_available),
        "battery_shortfall_p80": battery_shortfall,
        "recharge_sequences_required": recharge_sequences_required,
        "recharge_allowed": bool(recharge_allowed),
        "recharge_downtime_hr": recharge_downtime_hr,
        "recommended_track_orientation": orientation_summary,
        "monte_carlo_runs": n,
        "mission_sequences": mission_sequences,
        "rng_seed": seed_used,
        "battery_nameplate_kwh": vehicle.battery_kwh,
        "usable_fraction": vehicle.usable_fraction,
        "usable_battery_per_set_kwh": usable_battery_per_set,
        "total_available_kwh": total_available_kwh,
        "source_note": vehicle.source_note,
        "usable_basis": vehicle.usable_basis,
        "track_spacing_m": track_spacing_m,
        "speed_kts": speed_kts,
        "search_width_km": area.width_km,
        "search_height_km": area.height_km,
        "route_distance_km": area.route_distance_km,
        "route_heading_deg": area.route_heading_deg,
        "current_uplift_pct": mean_current_uplift_pct,
        "temp_uplift_pct": mean_temp_uplift_pct,
        "environmental_multiplier": mean_environmental_multiplier,
        "reserve_margin_per_set_kwh": max(vehicle.battery_kwh - usable_battery_per_set, 0.0),
        "battery_remaining_pct_p80": max(0.0, min(100.0, 100.0 * (1.0 - p80 / max(total_available_kwh, 0.001)))),
        **search_summary,
        **isr_summary,
    }

    rows = [
        ("Platform", vehicle.name, ""),
        ("Mission type", mission_type, ""),
        ("Mission sequences", mission_sequences, "runs"),
        ("Mean energy required", mean_energy, "kWh"),
        ("P50 energy required", p50, "kWh"),
        ("P80 energy required", p80, "kWh"),
        ("P95 energy required", p95, "kWh"),
        ("Mean mission duration", mean_duration, "hr"),
        ("Battery nameplate capacity", vehicle.battery_kwh, "kWh"),
        ("Usable planning energy per set", usable_battery_per_set, "kWh"),
        ("Usable battery basis", vehicle.usable_basis, ""),
        ("Battery sets on hand", battery_sets_available, "sets"),
        ("Battery inventory without recharge", "Sufficient" if battery_shortfall == 0 else "Not sufficient", ""),
        ("Battery inventory sufficiency across Monte Carlo runs", inventory_probability, "%"),
        ("Battery sets required at P80", battery_sets_required_p80, "sets"),
        ("Battery shortfall at P80", battery_shortfall, "sets"),
        ("Recharge / swap sequences required", recharge_sequences_required, "sequences"),
        ("Recharge downtime", recharge_downtime_hr, "hr"),
        ("Elapsed time incl. recharge", mean_duration + recharge_downtime_hr, "hr"),
    ]
    if mission_type in ISR_MISSIONS:
        rows.extend(
            [
                ("ISR patrol geometry", area.geometry_type, ""),
                ("ISR patrol loop distance", isr_summary.get("isr_loop_distance_km", 0.0), "km"),
                ("ISR loop time", isr_summary.get("isr_loop_time_hr", 0.0), "hr"),
                ("Estimated ISR time on station", isr_summary.get("isr_max_time_on_station_hr", 0.0), "hr"),
                ("Completed ISR patrol loops", isr_summary.get("isr_completed_loops", 0), "loops"),
                ("Remaining partial loop", isr_summary.get("isr_remaining_partial_loop_pct", 0.0), "%"),
                ("Adjusted endurance power draw", isr_summary.get("isr_adjusted_power_draw_kw", 0.0), "kW"),
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
    )
