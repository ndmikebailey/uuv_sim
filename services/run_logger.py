"""Run-record export for validation and physical-test traceability."""

from __future__ import annotations

import csv
import json
import os
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from models.environment_model import EnvironmentData
from models.mission_model import MissionArea
from models.vehicle_model import VehicleState
from utils.constants import APP_VERSION, ENERGY_MODEL_VERSION, VEHICLE_CATALOG_VERSION


ENERGY_PLANNER_CSV_FIELDS = [
    "run_id",
    "timestamp_utc",
    "app_version",
    "model_version",
    "vehicle_catalog_version",
    "git_commit",
    "mission_type",
    "geometry_type",
    "platform_name",
    "battery_configuration",
    "payload_return_to_start",
    "payload_recovery_mode",
    "payload_weight_kg",
    "payload_weight_penalty_pct",
    "payload_weight_multiplier",
    "payload_weight_penalty_basis",
    "launch_recovery_energy_kwh",
    "mission_sensor_power_mean_kw",
    "mission_sensor_power_p10_kw",
    "mission_sensor_power_p50_kw",
    "mission_sensor_power_p90_kw",
    "mission_sensor_power_basis",
    "active_sensor_mode",
    "mission_duration_hr",
    "route_distance_km",
    "additional_transit_km",
    "total_distance_km",
    "search_area_km2",
    "track_spacing_m",
    "recommended_orientation",
    "isr_loop_distance_km",
    "isr_loop_time_hr",
    "isr_time_on_station_hr",
    "isr_completed_loops",
    "usable_battery_per_set_kwh",
    "battery_condition_assumption",
    "battery_usable_fraction_p10",
    "battery_usable_fraction_p50",
    "battery_usable_fraction_p90",
    "operator_reserve_fraction",
    "temperature_capacity_factor",
    "temperature_derating_pct",
    "battery_sets_available",
    "total_available_energy_kwh",
    "reserve_fraction",
    "reserve_energy_kwh",
    "p50_energy_kwh",
    "p80_energy_kwh",
    "p95_energy_kwh",
    "p50_energy_margin_kwh",
    "p80_energy_margin_kwh",
    "p95_energy_margin_kwh",
    "p80_battery_sets_required",
    "p80_battery_shortfall_kwh",
    "recharge_or_swap_required",
    "metoc_lookup_lat",
    "metoc_lookup_lon",
    "current_speed_kts",
    "current_direction_deg",
    "sea_surface_temp_c",
    "sea_surface_salinity_psu",
    "sea_water_density_kg_m3",
    "salinity_source",
    "wind_speed_kts",
    "weather_summary",
    "environmental_multiplier",
    "current_uplift_pct",
    "temp_uplift_pct",
    "salinity_uplift_pct",
    "total_uplift_pct",
    "battery_inventory_sufficient",
    "estimated_recharge_need",
    "sustainment_total_missions",
    "sustainment_total_conservative_energy_kwh",
    "sustainment_inventory_cycles_required",
    "sustainment_generator_input_energy_kwh",
    "planner_note",
]


def _build_commit() -> str:
    """Return the current build commit from environment or local git metadata."""
    env_commit = os.environ.get("GIT_COMMIT") or os.environ.get("SPACE_COMMIT_SHA") or os.environ.get("HF_SPACE_COMMIT_SHA")
    if env_commit:
        return env_commit
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        commit = result.stdout.strip()
        return commit or "unknown"
    except Exception:
        return "unknown"


def _blank_if_none(value: Any) -> Any:
    """Return a CSV-friendly blank for non-applicable values."""
    return "" if value is None else value


def _number(value: Any) -> float | str:
    """Return a float for numeric values, or a blank for missing/non-numeric values."""
    if value is None or value == "":
        return ""
    try:
        return float(value)
    except (TypeError, ValueError):
        return ""


def _yes_no(value: Any) -> str:
    """Return Yes/No text for planner-facing boolean fields."""
    return "Yes" if bool(value) else "No"


def _metoc_lookup_point(environment: EnvironmentData) -> tuple[Any, Any]:
    """Return the traced METOC lookup point from preserved query parameters."""
    for params in (environment.marine_query_params, environment.weather_query_params):
        if not params:
            continue
        lat = params.get("latitude")
        lon = params.get("longitude")
        if lat is not None and lon is not None:
            return lat, lon
    return "", ""


def _payload_total_distance_km(area: MissionArea, simulation_inputs: dict[str, Any]) -> float | str:
    """Return total payload route distance including return leg and added transit."""
    route_distance = area.route_distance_km
    if route_distance is None:
        return ""
    return_to_start = bool(simulation_inputs.get("return_to_start"))
    additional_transit = float(simulation_inputs.get("additional_transit_km") or 0.0)
    multiplier = 2.0 if return_to_start else 1.0
    return route_distance * multiplier + additional_transit


def _planner_note(mission_type: str, summary: dict[str, Any], simulation_inputs: dict[str, Any]) -> str:
    """Return a short mission-specific sustainment note."""
    if mission_type in {"Payload", "Payload Delivery", "Delivery", "Route / Transit", "Endurance / Transit", "Transit"}:
        return "Route/transit energy reflects route distance, recovery mode, carried equipment weight, launch/recovery overhead when applicable, current, added transit, and low-burden sensor-mode uncertainty."
    if mission_type in {"ISR", "Intelligence, Surveillance, and Reconnaissance"}:
        return "ISR reports maximum endurance-based time on station before recovery or battery swap."
    if mission_type in {"Area Search / MCM", "Area Search", "MCM", "Mine Countermeasures", "Search"}:
        return "Search/MCM planning uses swath spacing and recommended track orientation."
    return "Planner values are based on the current mission configuration."


def build_energy_planner_csv_row(
    summary: dict[str, Any],
    mission_context: dict[str, Any],
    vehicle: VehicleState,
    environment: EnvironmentData,
    run_metadata: dict[str, Any],
) -> dict[str, Any]:
    """
    Build one flat CSV row for energy planners.

    The output uses stable column names and blank values for non-applicable fields.
    """
    mission_type = str(mission_context.get("mission_type") or summary.get("mission_type") or "")
    area = mission_context.get("area")
    if not isinstance(area, MissionArea):
        raise TypeError("mission_context['area'] must be a MissionArea")
    simulation_inputs = mission_context.get("simulation_inputs")
    if not isinstance(simulation_inputs, dict):
        simulation_inputs = {}

    is_payload = mission_type in {"Payload", "Payload Delivery", "Delivery", "Route / Transit", "Endurance / Transit", "Transit"}
    is_isr = mission_type in {"ISR", "Intelligence, Surveillance, and Reconnaissance"}
    is_search = mission_type in {"Area Search / MCM", "Area Search", "MCM", "Mine Countermeasures", "Search"}

    total_available = float(summary.get("total_available_kwh") or 0.0)
    p50 = float(summary.get("p50_energy_kwh") or 0.0)
    p80 = float(summary.get("p80_energy_kwh") or 0.0)
    p95 = float(summary.get("p95_energy_kwh") or 0.0)
    usable_per_set = float(summary.get("usable_battery_per_set_kwh") or vehicle.usable_battery_per_set_kwh)
    reserve_fraction = max(0.0, 1.0 - float(summary.get("usable_fraction") or vehicle.usable_fraction))
    reserve_energy = max(float(summary.get("battery_nameplate_kwh") or vehicle.battery_kwh) - usable_per_set, 0.0)
    p80_shortfall_kwh = max(p80 - total_available, 0.0)
    battery_shortfall_sets = int(summary.get("battery_shortfall_p80") or 0)
    one_way_inventory = summary.get("vehicle_rechargeable") is False
    recharge_required = battery_shortfall_sets > 0
    inventory_sufficient = bool(summary.get("battery_inventory_sufficient_no_recharge"))
    metoc_lat, metoc_lon = _metoc_lookup_point(environment)

    environmental_multiplier = summary.get("isr_environmental_multiplier") or summary.get("environmental_multiplier")
    total_uplift_pct = ""
    if environmental_multiplier not in (None, ""):
        try:
            total_uplift_pct = (float(environmental_multiplier) - 1.0) * 100.0
        except (TypeError, ValueError):
            total_uplift_pct = ""

    estimated_recharge_need = "None"
    if recharge_required:
        if one_way_inventory:
            estimated_recharge_need = f"{battery_shortfall_sets} additional vehicle unit(s) required"
        elif not bool(summary.get("recharge_allowed")):
            estimated_recharge_need = f"{battery_shortfall_sets} additional battery set(s) required; recharge not enabled"
        else:
            estimated_recharge_need = f"{battery_shortfall_sets} battery set(s) or recharge/swap sequence(s)"

    row: dict[str, Any] = {field: "" for field in ENERGY_PLANNER_CSV_FIELDS}
    row.update(
        {
            "run_id": run_metadata.get("run_id", ""),
            "timestamp_utc": run_metadata.get("timestamp_utc", ""),
            "app_version": run_metadata.get("app_version", ""),
            "model_version": run_metadata.get("model_version", ""),
            "vehicle_catalog_version": run_metadata.get("vehicle_catalog_version", ""),
            "git_commit": run_metadata.get("git_commit", ""),
            "mission_type": mission_type,
            "geometry_type": area.geometry_type,
            "platform_name": vehicle.name,
            "battery_configuration": f"{int(summary.get('battery_sets_available') or 0)} set(s), {usable_per_set:.2f} kWh usable per set",
            "mission_sensor_power_mean_kw": _number(summary.get("mission_sensor_power_mean_kw")),
            "mission_sensor_power_p10_kw": _number(summary.get("mission_sensor_power_p10_kw")),
            "mission_sensor_power_p50_kw": _number(summary.get("mission_sensor_power_p50_kw")),
            "mission_sensor_power_p90_kw": _number(summary.get("mission_sensor_power_p90_kw")),
            "mission_sensor_power_basis": summary.get("mission_sensor_power_basis", ""),
            "active_sensor_mode": summary.get("active_sensor_mode", ""),
            "mission_duration_hr": _number(summary.get("mean_duration_hr")),
            "additional_transit_km": _number(simulation_inputs.get("additional_transit_km")),
            "usable_battery_per_set_kwh": usable_per_set,
            "battery_condition_assumption": summary.get("battery_condition_assumption", ""),
            "battery_usable_fraction_p10": _number(summary.get("battery_usable_fraction_p10")),
            "battery_usable_fraction_p50": _number(summary.get("battery_usable_fraction_p50")),
            "battery_usable_fraction_p90": _number(summary.get("battery_usable_fraction_p90")),
            "operator_reserve_fraction": _number(summary.get("operator_reserve_fraction")),
            "temperature_capacity_factor": _number(summary.get("temperature_capacity_factor")),
            "temperature_derating_pct": _number(summary.get("temperature_derating_pct")),
            "battery_sets_available": int(summary.get("battery_sets_available") or 0),
            "total_available_energy_kwh": total_available,
            "reserve_fraction": reserve_fraction,
            "reserve_energy_kwh": reserve_energy,
            "p50_energy_kwh": p50,
            "p80_energy_kwh": p80,
            "p95_energy_kwh": p95,
            "p50_energy_margin_kwh": total_available - p50,
            "p80_energy_margin_kwh": total_available - p80,
            "p95_energy_margin_kwh": total_available - p95,
            "p80_battery_sets_required": int(summary.get("battery_sets_required_p80") or 0),
            "p80_battery_shortfall_kwh": p80_shortfall_kwh,
            "recharge_or_swap_required": _yes_no(recharge_required),
            "metoc_lookup_lat": _blank_if_none(metoc_lat),
            "metoc_lookup_lon": _blank_if_none(metoc_lon),
            "current_speed_kts": _number(environment.current_speed_kts_mean),
            "current_direction_deg": _number(environment.current_direction_deg_mean),
            "sea_surface_temp_c": _number(environment.sea_surface_temp_c_mean),
            "sea_surface_salinity_psu": _number(environment.sea_surface_salinity_psu),
            "sea_water_density_kg_m3": _number(environment.sea_water_density_kg_m3),
            "salinity_source": environment.salinity_source or "",
            "wind_speed_kts": _number(environment.wind_speed_kts_mean),
            "weather_summary": environment.weather_summary or "",
            "environmental_multiplier": _number(environmental_multiplier),
            "current_uplift_pct": _number(summary.get("current_uplift_pct")),
            "temp_uplift_pct": _number(summary.get("temp_uplift_pct")),
            "salinity_uplift_pct": _number(summary.get("salinity_uplift_pct")),
            "total_uplift_pct": total_uplift_pct,
            "battery_inventory_sufficient": _yes_no(inventory_sufficient),
            "estimated_recharge_need": estimated_recharge_need,
            "sustainment_total_missions": _number(summary.get("sustainment_total_missions")),
            "sustainment_total_conservative_energy_kwh": _number(summary.get("sustainment_total_conservative_energy_kwh")),
            "sustainment_inventory_cycles_required": _number(summary.get("sustainment_inventory_cycles_required")),
            "sustainment_generator_input_energy_kwh": _number(summary.get("sustainment_generator_input_energy_kwh")),
            "planner_note": _planner_note(mission_type, summary, simulation_inputs),
        }
    )

    if is_payload:
        row.update(
            {
                "payload_return_to_start": _yes_no(summary.get("payload_recovery_mode") == "return_to_start"),
                "payload_recovery_mode": summary.get("payload_recovery_mode", ""),
                "payload_weight_kg": _number(summary.get("payload_weight_kg")),
                "payload_weight_penalty_pct": _number(summary.get("payload_weight_penalty_pct")),
                "payload_weight_multiplier": _number(summary.get("payload_weight_multiplier")),
                "payload_weight_penalty_basis": summary.get("payload_weight_penalty_basis", ""),
                "launch_recovery_energy_kwh": _number(summary.get("launch_recovery_energy_kwh")),
                "route_distance_km": _number(area.route_distance_km or summary.get("route_distance_km")),
                "total_distance_km": _number(summary.get("payload_total_modeled_distance_km") or _payload_total_distance_km(area, simulation_inputs)),
            }
        )
    if is_search:
        row.update(
            {
                "search_area_km2": _number(area.area_km2),
                "track_spacing_m": _number(simulation_inputs.get("track_spacing_m") or summary.get("track_spacing_m")),
                "recommended_orientation": summary.get("recommended_track_orientation") if summary.get("recommended_track_orientation") != "N/A" else "",
            }
        )
    if is_isr:
        row.update(
            {
                "isr_loop_distance_km": _number(summary.get("isr_loop_distance_km")),
                "isr_loop_time_hr": _number(summary.get("isr_loop_time_hr")),
                "isr_time_on_station_hr": _number(summary.get("isr_max_time_on_station_hr")),
                "isr_completed_loops": _blank_if_none(summary.get("isr_completed_loops")),
            }
        )
    return row


def write_run_record(
    mission_type: str,
    area: MissionArea,
    vehicle: VehicleState,
    environment: EnvironmentData,
    simulation_inputs: dict[str, Any],
    simulation_summary: dict[str, Any],
    result_rows: list[tuple[str, object, str]],
    source_geometry_json: str | None = None,
    output_dir: str | Path = "runs",
) -> tuple[str, str]:
    """Write JSON and CSV run records and return their file paths."""
    run_id = str(uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    run_metadata = {
        "run_id": run_id,
        "timestamp_utc": timestamp,
        "app_version": APP_VERSION,
        "model_version": ENERGY_MODEL_VERSION,
        "git_commit": _build_commit(),
        "vehicle_catalog_version": VEHICLE_CATALOG_VERSION,
    }
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{timestamp.replace(':', '').replace('+', 'Z')}_{run_id[:8]}"
    json_path = directory / f"{stem}.json"
    csv_path = directory / f"{stem}_energy_planner.csv"
    planner_csv_row = build_energy_planner_csv_row(
        simulation_summary,
        {
            "mission_type": mission_type,
            "area": area,
            "simulation_inputs": simulation_inputs,
        },
        vehicle,
        environment,
        run_metadata,
    )

    record = {
        **run_metadata,
        "mission_type": mission_type,
        "geometry_json": source_geometry_json,
        "mission_area": area.to_dict(),
        "vehicle_config": asdict(vehicle),
        "simulation_inputs": simulation_inputs,
        "raw_marine_api_json": environment.raw_marine_api_json,
        "raw_weather_api_json": environment.raw_weather_api_json,
        "marine_query_params": environment.marine_query_params,
        "weather_query_params": environment.weather_query_params,
        "environment": environment.to_dict(),
        "simulation_outputs": simulation_summary,
        "result_rows": result_rows,
        "energy_planner_csv_row": planner_csv_row,
        "operator_notes": "",
        "actual_test_result": "",
    }
    json_path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ENERGY_PLANNER_CSV_FIELDS)
        writer.writeheader()
        writer.writerow(planner_csv_row)
    return str(json_path), str(csv_path)
