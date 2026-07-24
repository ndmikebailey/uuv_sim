"""Session-scoped report and mission-package lifecycle management."""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from models.environment_model import EnvironmentData
from models.mission_model import MissionArea, MissionAreaSet
from models.vehicle_model import VehicleState
from services.run_logger import write_run_record


ARTIFACT_PREFIX = "uuv_sim_"
MAX_MISSION_FILE_BYTES = 10 * 1024 * 1024


def create_run_artifacts(
    *,
    mission_type: str,
    area: MissionArea | MissionAreaSet,
    vehicle: VehicleState,
    environment: EnvironmentData,
    simulation_inputs: dict[str, Any],
    simulation_summary: dict[str, Any],
    result_rows: list[tuple[str, object, str]],
    source_geometry_json: str | None,
    report_html: str,
) -> dict[str, str]:
    """Create downloadable files in a unique temporary directory."""
    directory = Path(tempfile.mkdtemp(prefix=ARTIFACT_PREFIX))
    json_path, csv_path = write_run_record(
        mission_type=mission_type,
        area=area,
        vehicle=vehicle,
        environment=environment,
        simulation_inputs=simulation_inputs,
        simulation_summary=simulation_summary,
        result_rows=result_rows,
        source_geometry_json=source_geometry_json,
        output_dir=directory,
    )
    report_path = directory / "uuv_mission_report.html"
    report_path.write_text(report_html, encoding="utf-8")
    package_path = directory / "uuv_mission_package.zip"
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(report_path, report_path.name)
        archive.write(json_path, "uuv_mission_record.json")
        archive.write(csv_path, "uuv_energy_planner.csv")
    return {
        "_artifact_dir": str(directory),
        "_report_path": str(report_path),
        "_package_path": str(package_path),
        "_json_path": str(json_path),
        "_csv_path": str(csv_path),
    }


def cleanup_run_artifacts(state: object) -> None:
    """Delete only the temporary artifact directory recorded for one session."""
    if not isinstance(state, dict):
        return
    raw_directory = state.get("_artifact_dir")
    if not raw_directory:
        return
    directory = Path(str(raw_directory)).resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    if directory.parent != temp_root or not directory.name.startswith(ARTIFACT_PREFIX):
        return
    shutil.rmtree(directory, ignore_errors=True)


def load_mission_record(file_path: str | Path) -> dict[str, Any]:
    """Read a mission JSON record directly or from a downloaded mission package."""
    path = Path(file_path)
    if not path.is_file():
        raise ValueError("Select a saved mission JSON file or mission-package ZIP file.")
    if path.stat().st_size > MAX_MISSION_FILE_BYTES:
        raise ValueError("The selected mission file is larger than 10 MB.")

    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            candidates = [
                info
                for info in archive.infolist()
                if not info.is_dir() and info.filename.lower().endswith(".json")
            ]
            if not candidates:
                raise ValueError("The mission package does not contain a JSON mission record.")
            selected = candidates[0]
            if selected.file_size > MAX_MISSION_FILE_BYTES:
                raise ValueError("The mission record inside the package is larger than 10 MB.")
            raw = archive.read(selected).decode("utf-8")
    elif path.suffix.lower() == ".json":
        raw = path.read_text(encoding="utf-8")
    else:
        raise ValueError("Select a .json or .zip mission file.")

    try:
        record = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("The selected file does not contain a valid mission record.") from exc
    if not isinstance(record, dict):
        raise ValueError("The mission record must contain one JSON object.")
    required = {"mission_type", "mission_area", "environment", "simulation_inputs"}
    if not required.issubset(record):
        raise ValueError("The selected file is missing required mission data.")
    return record
