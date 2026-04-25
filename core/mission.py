"""Mission validation and mission-context orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from core.geometry import parse_geometry_json
from models.environment_model import EnvironmentData
from models.mission_model import MissionArea, MissionContext
from services.metoc_fusion import MetocFusionService
from utils.constants import SEARCH_MISSIONS


@dataclass
class MissionBuildResult:
    """Result returned when map geometry is loaded into a mission."""

    ok: bool
    status: str
    context: MissionContext | None
    environment_rows: list[tuple[str, object, str]]


def validate_mission_geometry(mission_type: str, area: MissionArea) -> None:
    """Validate mission type against selected map geometry."""
    if mission_type == "Payload Delivery" and not area.is_payload_route:
        raise ValueError("Payload Delivery requires a line route. Draw a line from drop point to target site.")
    if mission_type in SEARCH_MISSIONS and not area.is_search_area:
        raise ValueError(f"{mission_type} requires a rectangle or polygon search area.")


def build_mission_context(
    mission_type: str,
    geometry_json_text: str,
    metoc_service: MetocFusionService,
) -> MissionBuildResult:
    """Parse geometry, validate compatibility, and load fused METOC data."""
    try:
        area = parse_geometry_json(geometry_json_text)
        validate_mission_geometry(mission_type, area)
    except ValueError as exc:
        return MissionBuildResult(False, f"Mission build failed: {exc}", None, [("Mission build failed", str(exc), "")])

    environment = metoc_service.fetch(area.centroid_lat, area.centroid_lon)
    context = MissionContext(mission_type=mission_type, area=area, environment=environment)
    rows = environment.table_rows(area.centroid_lat, area.centroid_lon)
    status = "Mission geometry and Open-Meteo environmental data loaded."
    if environment.marine_error or environment.weather_error:
        status += f"\nMarine status: {environment.marine_error or 'OK'}\nWeather status: {environment.weather_error or 'OK'}"
    return MissionBuildResult(True, status, context, rows)


def blank_environment() -> EnvironmentData:
    """Return default manual environment values for standalone simulation."""
    return EnvironmentData(
        current_speed_kts_mean=0.5,
        current_direction_deg_mean=0.0,
        sea_surface_temp_c_mean=25.0,
    )

