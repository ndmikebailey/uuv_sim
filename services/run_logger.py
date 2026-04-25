"""Run-record export for validation and physical-test traceability."""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from models.environment_model import EnvironmentData
from models.mission_model import MissionArea
from models.vehicle_model import VehicleState
from utils.constants import APP_VERSION, ENERGY_MODEL_VERSION, VEHICLE_CATALOG_VERSION


def _build_commit() -> str:
    """Return the deployed build commit when the hosting environment exposes it."""
    return (
        os.environ.get("GIT_COMMIT")
        or os.environ.get("SPACE_COMMIT_SHA")
        or os.environ.get("HF_SPACE_COMMIT_SHA")
        or "unknown"
    )


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
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{timestamp.replace(':', '').replace('+', 'Z')}_{run_id[:8]}"
    json_path = directory / f"{stem}.json"
    csv_path = directory / f"{stem}_results.csv"

    record = {
        "run_id": run_id,
        "timestamp_utc": timestamp,
        "app_version": APP_VERSION,
        "model_version": ENERGY_MODEL_VERSION,
        "git_commit": _build_commit(),
        "vehicle_catalog_version": VEHICLE_CATALOG_VERSION,
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
        "operator_notes": "",
        "actual_test_result": "",
    }
    json_path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Output", "Value", "Unit"])
        writer.writerows(result_rows)
    return str(json_path), str(csv_path)
