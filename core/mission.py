"""Mission validation and mission-context orchestration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from core.geometry import parse_geometry_json
from models.environment_model import EnvironmentData
from models.mission_model import MissionArea, MissionAreaSet, MissionContext
from services.metoc_fusion import MetocFusionService
from utils.constants import ISR_MISSIONS, PAYLOAD_MISSIONS, SEARCH_MISSIONS


@dataclass
class MissionBuildResult:
    """Result returned when map geometry is loaded into a mission."""

    ok: bool
    status: str
    context: MissionContext | None
    environment_rows: list[tuple[str, object, str]]


def validate_mission_geometry(mission_type: str, area: MissionArea | MissionAreaSet) -> None:
    """Validate mission type against selected map geometry."""
    if isinstance(area, MissionAreaSet):
        if mission_type not in SEARCH_MISSIONS:
            raise ValueError("Multi-area geometry is supported for Area Search / MCM only.")
        if not area.areas:
            raise ValueError("Multi-area Search/MCM requires at least one search area.")
        return
    if mission_type in PAYLOAD_MISSIONS and not area.is_payload_route:
        raise ValueError("Payload Delivery requires a line route. Draw a line from drop point to target site.")
    if mission_type in SEARCH_MISSIONS and not area.is_search_area:
        raise ValueError(f"{mission_type} requires a rectangle or polygon search area.")
    if mission_type in ISR_MISSIONS and not (area.is_payload_route or area.is_search_area):
        raise ValueError("ISR requires a line, rectangle, or polygon patrol geometry.")


def choose_environment_lookup_point(mission_type: str, area: MissionArea) -> tuple[float, float]:
    """Choose the METOC lookup point for the mission type and geometry."""
    points: list[tuple[float, float]] = []
    if area.route_points:
        points = [(point.lat, point.lon) for point in area.route_points]
    elif area.vertices:
        points = [(point.lat, point.lon) for point in area.vertices]

    centroid = (area.centroid_lat, area.centroid_lon)
    if mission_type in SEARCH_MISSIONS:
        return centroid

    if mission_type in PAYLOAD_MISSIONS and len(points) >= 2:
        start = points[0]
        end = points[-1]
        return (start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0

    if mission_type in ISR_MISSIONS and points:
        return points[0]

    if points:
        avg_lat = sum(point[0] for point in points) / len(points)
        avg_lon = sum(point[1] for point in points) / len(points)
        return avg_lat, avg_lon

    return centroid


def choose_environment_lookup_points(mission_type: str, area: MissionArea | MissionAreaSet) -> list[tuple[float, float]]:
    """Choose one or more METOC lookup points for a mission."""
    if isinstance(area, MissionAreaSet) and mission_type in SEARCH_MISSIONS:
        return list(area.representative_points)
    return [choose_environment_lookup_point(mission_type, area)]  # type: ignore[arg-type]


def _mean(values: list[float]) -> float | None:
    """Return the mean of available scalar values."""
    return sum(values) / len(values) if values else None


def _vector_average_current(environments: list[EnvironmentData]) -> tuple[float | None, float | None]:
    """Average current vectors using compass-direction convention."""
    vectors: list[tuple[float, float]] = []
    for environment in environments:
        speed = environment.current_speed_kts_mean
        direction = environment.current_direction_deg_mean
        if speed is None or direction is None:
            continue
        radians = math.radians(direction)
        vectors.append((speed * math.sin(radians), speed * math.cos(radians)))
    if not vectors:
        return None, None
    mean_u = sum(vector[0] for vector in vectors) / len(vectors)
    mean_v = sum(vector[1] for vector in vectors) / len(vectors)
    speed = math.hypot(mean_u, mean_v)
    direction = (math.degrees(math.atan2(mean_u, mean_v)) + 360.0) % 360.0
    return speed, direction


def aggregate_environments(
    environments: list[EnvironmentData],
    lookup_points: list[tuple[float, float]],
) -> EnvironmentData:
    """Aggregate per-area METOC data into one planning environment."""
    if not environments:
        return EnvironmentData(
            marine_error="No per-area METOC values were available.",
            weather_error="No per-area METOC values were available.",
        )

    current_speed, current_direction = _vector_average_current(environments)

    def scalar(name: str) -> float | None:
        values = [float(value) for env in environments if (value := getattr(env, name)) is not None]
        return _mean(values)

    marine_errors = [env.marine_error for env in environments if env.marine_error]
    weather_errors = [env.weather_error for env in environments if env.weather_error]
    salinity_errors = [env.salinity_error for env in environments if env.salinity_error]
    salinity_sources = [env.salinity_source for env in environments if env.salinity_source]
    salinity_value = scalar("sea_surface_salinity_psu")
    density_value = scalar("sea_water_density_kg_m3")
    if salinity_value is not None:
        salinity_source = "copernicus_marine area-centroid average"
    elif salinity_sources:
        salinity_source = salinity_sources[0]
    else:
        salinity_source = "standard_assumption"
    return EnvironmentData(
        current_speed_kts_mean=current_speed,
        current_direction_deg_mean=current_direction,
        sea_surface_temp_c_mean=scalar("sea_surface_temp_c_mean"),
        sea_surface_salinity_psu=salinity_value,
        sea_water_density_kg_m3=density_value,
        sea_level_height_m=scalar("sea_level_height_m"),
        wave_height_m=scalar("wave_height_m"),
        wave_direction_deg=scalar("wave_direction_deg"),
        wave_period_s=scalar("wave_period_s"),
        wind_wave_height_m=scalar("wind_wave_height_m"),
        swell_wave_height_m=scalar("swell_wave_height_m"),
        air_temp_c=scalar("air_temp_c"),
        relative_humidity_pct=scalar("relative_humidity_pct"),
        apparent_temp_c=scalar("apparent_temp_c"),
        precipitation_mm=scalar("precipitation_mm"),
        weather_code=scalar("weather_code"),
        cloud_cover_pct=scalar("cloud_cover_pct"),
        pressure_msl_hpa=scalar("pressure_msl_hpa"),
        surface_pressure_hpa=scalar("surface_pressure_hpa"),
        wind_speed_kts_mean=scalar("wind_speed_kts_mean"),
        wind_direction_deg_mean=scalar("wind_direction_deg_mean"),
        wind_gusts_kts=scalar("wind_gusts_kts"),
        weather_summary="Averaged from area centroid lookup points.",
        marine_error="; ".join(marine_errors) or None,
        weather_error="; ".join(weather_errors) or None,
        salinity_error="; ".join(salinity_errors) or None,
        raw_marine_api_json={
            "aggregation_method": "area-centroid vector average",
            "lookup_points": lookup_points,
            "samples": [env.raw_marine_api_json for env in environments],
        },
        raw_weather_api_json={
            "aggregation_method": "area-centroid vector average",
            "lookup_points": lookup_points,
            "samples": [env.raw_weather_api_json for env in environments],
        },
        marine_query_params={"lookup_points": lookup_points},
        weather_query_params={"lookup_points": lookup_points},
        salinity_query_params={
            "lookup_points": lookup_points,
            "samples": [env.salinity_query_params for env in environments],
        },
        salinity_metadata={
            "aggregation_method": "area-centroid scalar average",
            "lookup_points": lookup_points,
            "sample_count": len(environments),
            "sources": salinity_sources,
        },
        salinity_source=salinity_source,
        source="Open-Meteo area-centroid average",
    )


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

    lookup_points = choose_environment_lookup_points(mission_type, area)
    environments: list[EnvironmentData] = []
    errors: list[str] = []
    for lookup_lat, lookup_lon in lookup_points:
        try:
            environments.append(metoc_service.fetch(lookup_lat, lookup_lon))
        except Exception as exc:
            errors.append(f"{lookup_lat:.5f},{lookup_lon:.5f}: {exc}")
    if len(lookup_points) > 1:
        environment = aggregate_environments(environments, lookup_points)
        if errors:
            environment.marine_error = "; ".join(filter(None, [environment.marine_error, *errors]))
        lookup_lat, lookup_lon = area.centroid_lat, area.centroid_lon  # type: ignore[union-attr]
    elif environments:
        environment = environments[0]
        lookup_lat, lookup_lon = lookup_points[0]
    else:
        environment = EnvironmentData(marine_error="; ".join(errors), weather_error="; ".join(errors))
        lookup_lat, lookup_lon = lookup_points[0]
    context = MissionContext(mission_type=mission_type, area=area, environment=environment)
    rows = environment.table_rows(lookup_lat, lookup_lon)
    if len(lookup_points) > 1:
        rows.extend(
            [
                ("METOC aggregation method", "area-centroid vector average", ""),
                ("METOC sampled points", len(lookup_points), "points"),
            ]
        )
    status = "Mission geometry and Open-Meteo environmental data loaded."
    if len(lookup_points) > 1:
        status = f"Multi-area Search/MCM mission loaded with {len(lookup_points)} area centroid METOC samples."
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
