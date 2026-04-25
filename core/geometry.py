"""Pure geometry calculations for mission areas and routes."""

from __future__ import annotations

import math
from typing import Any, Iterable, Optional

from models.mission_model import Bounds, LatLon, LocalPoint, MissionArea
from utils.constants import EARTH_RADIUS_KM
from utils.parsing import parse_json_object, safe_float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance between two lat/lon points in kilometers."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return initial bearing from point 1 to point 2 in degrees clockwise from north."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_lam = math.radians(lon2 - lon1)
    y = math.sin(d_lam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lam)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def clean_latlon_vertices(raw_vertices: Any) -> list[LatLon]:
    """Normalize mixed Leaflet vertex payloads into ``LatLon`` values."""
    vertices: list[LatLon] = []
    for item in raw_vertices or []:
        lat = lon = None
        if isinstance(item, dict):
            lat = safe_float(item.get("lat"))
            lon = safe_float(item.get("lon", item.get("lng")))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            lat = safe_float(item[0])
            lon = safe_float(item[1])
        if lat is not None and lon is not None:
            vertices.append(LatLon(float(lat), float(lon)))

    if len(vertices) > 1 and vertices[0] == vertices[-1]:
        vertices.pop()
    return vertices


def bounds_from_dict(data: Any) -> Optional[Bounds]:
    """Parse a bounds mapping into ``Bounds``."""
    if not isinstance(data, dict):
        return None
    north = safe_float(data.get("north"))
    south = safe_float(data.get("south"))
    east = safe_float(data.get("east"))
    west = safe_float(data.get("west"))
    if None in (north, south, east, west):
        return None
    return Bounds(north=float(north), south=float(south), east=float(east), west=float(west))


def rectangle_vertices(bounds: Bounds) -> list[LatLon]:
    """Return rectangle vertices in clockwise local order."""
    return [
        LatLon(bounds.south, bounds.west),
        LatLon(bounds.south, bounds.east),
        LatLon(bounds.north, bounds.east),
        LatLon(bounds.north, bounds.west),
    ]


def project_latlon_vertices(vertices: list[LatLon]) -> tuple[list[tuple[float, float]], float, float, float]:
    """Project lat/lon vertices to a local tangent plane in kilometers."""
    lat0 = sum(v.lat for v in vertices) / len(vertices)
    lon0 = sum(v.lon for v in vertices) / len(vertices)
    cos_lat0 = max(abs(math.cos(math.radians(lat0))), 1e-6)
    points = [
        (
            EARTH_RADIUS_KM * math.radians(vertex.lon - lon0) * cos_lat0,
            EARTH_RADIUS_KM * math.radians(vertex.lat - lat0),
        )
        for vertex in vertices
    ]
    return points, lat0, lon0, cos_lat0


def shoelace_area_centroid(points: list[tuple[float, float]]) -> tuple[float, tuple[float, float]]:
    """Return polygon area and centroid in local coordinates."""
    twice_area = 0.0
    cx_sum = 0.0
    cy_sum = 0.0
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % len(points)]
        cross = x0 * y1 - x1 * y0
        twice_area += cross
        cx_sum += (x0 + x1) * cross
        cy_sum += (y0 + y1) * cross

    signed_area = twice_area / 2.0
    if abs(signed_area) < 1e-9:
        return 0.0, (
            sum(x for x, _ in points) / len(points),
            sum(y for _, y in points) / len(points),
        )
    return abs(signed_area), (cx_sum / (6.0 * signed_area), cy_sum / (6.0 * signed_area))


def polygon_bounds(vertices: Iterable[LatLon]) -> Bounds:
    """Return geodetic bounds for vertices."""
    vertex_list = list(vertices)
    return Bounds(
        north=max(v.lat for v in vertex_list),
        south=min(v.lat for v in vertex_list),
        east=max(v.lon for v in vertex_list),
        west=min(v.lon for v in vertex_list),
    )


def build_search_area(geometry_type: str, vertices: list[LatLon], bounds: Optional[Bounds] = None) -> MissionArea:
    """Build a rectangle or polygon mission area from vertices."""
    if geometry_type == "rectangle":
        if bounds is None:
            bounds = polygon_bounds(vertices)
        vertices = rectangle_vertices(bounds)
        centroid_lat = (bounds.north + bounds.south) / 2.0
        centroid_lon = (bounds.east + bounds.west) / 2.0
        width_km = haversine_km(centroid_lat, bounds.west, centroid_lat, bounds.east)
        height_km = haversine_km(bounds.south, centroid_lon, bounds.north, centroid_lon)
        area_km2 = width_km * height_km
        raw_points, lat0, lon0, cos_lat0 = project_latlon_vertices(vertices)
        centroid_x = EARTH_RADIUS_KM * math.radians(centroid_lon - lon0) * cos_lat0
        centroid_y = EARTH_RADIUS_KM * math.radians(centroid_lat - lat0)
    else:
        if len(vertices) < 3:
            raise ValueError("Polygon geometry did not include enough vertices.")
        bounds = polygon_bounds(vertices)
        raw_points, lat0, lon0, cos_lat0 = project_latlon_vertices(vertices)
        area_km2, (centroid_x, centroid_y) = shoelace_area_centroid(raw_points)
        if area_km2 <= 0:
            raise ValueError("Polygon geometry has no measurable area. Redraw the search area.")
        centroid_lat = lat0 + math.degrees(centroid_y / EARTH_RADIUS_KM)
        centroid_lon = lon0 + math.degrees(centroid_x / (EARTH_RADIUS_KM * cos_lat0))
        width_km = haversine_km((bounds.north + bounds.south) / 2, bounds.west, (bounds.north + bounds.south) / 2, bounds.east)
        height_km = haversine_km(bounds.south, (bounds.east + bounds.west) / 2, bounds.north, (bounds.east + bounds.west) / 2)

    min_x = min(x for x, _ in raw_points)
    min_y = min(y for _, y in raw_points)
    local_points = [LocalPoint(x - min_x, y - min_y) for x, y in raw_points]
    centroid_local = LocalPoint(centroid_x - min_x, centroid_y - min_y)
    return MissionArea(
        geometry_type=geometry_type,  # type: ignore[arg-type]
        centroid_lat=centroid_lat,
        centroid_lon=centroid_lon,
        area_km2=area_km2,
        width_km=width_km,
        height_km=height_km,
        bounds=bounds,
        vertices=vertices,
        local_polygon_km=local_points,
        centroid_local_km=centroid_local,
    )


def build_route(raw_points: list[LatLon]) -> MissionArea:
    """Build a payload route, preserving the existing endpoint-centroid behavior."""
    if len(raw_points) < 2:
        raise ValueError("Line requires at least two points.")
    start = raw_points[0]
    end = raw_points[-1]
    distance = sum(
        haversine_km(raw_points[index].lat, raw_points[index].lon, raw_points[index + 1].lat, raw_points[index + 1].lon)
        for index in range(len(raw_points) - 1)
    )
    return MissionArea(
        geometry_type="line",
        centroid_lat=(start.lat + end.lat) / 2.0,
        centroid_lon=(start.lon + end.lon) / 2.0,
        route_points=raw_points,
        route_distance_km=distance,
        route_heading_deg=bearing_deg(start.lat, start.lon, end.lat, end.lon),
    )


def parse_geometry_json(geometry_json_text: str) -> MissionArea:
    """Parse Leaflet geometry handoff JSON into a structured mission area."""
    geom = parse_json_object(geometry_json_text)
    if geom.get("error"):
        raise ValueError(str(geom["error"]))

    geometry_type = str(geom.get("geometry_type", ""))
    if geometry_type not in {"rectangle", "polygon", "line"}:
        raise ValueError("Unsupported or missing geometry type.")

    if geometry_type in {"rectangle", "polygon"}:
        bounds = bounds_from_dict(geom.get("bounds"))
        vertices = clean_latlon_vertices(geom.get("vertices"))
        if geometry_type == "rectangle" and len(vertices) < 4 and bounds is not None:
            vertices = rectangle_vertices(bounds)
        min_vertices = 4 if geometry_type == "rectangle" else 3
        if len(vertices) < min_vertices:
            raise ValueError(f"{geometry_type.title()} geometry did not include enough vertices.")
        return build_search_area(geometry_type, vertices, bounds)

    route_points = clean_latlon_vertices(geom.get("route_points") or geom.get("vertices"))
    if len(route_points) < 2:
        start_lat = safe_float(geom.get("route_start_lat"))
        start_lon = safe_float(geom.get("route_start_lon"))
        end_lat = safe_float(geom.get("route_end_lat"))
        end_lon = safe_float(geom.get("route_end_lon"))
        if None in (start_lat, start_lon, end_lat, end_lon):
            raise ValueError("Line geometry did not include start and end points.")
        route_points = [
            LatLon(float(start_lat), float(start_lon)),
            LatLon(float(end_lat), float(end_lon)),
        ]
    return build_route(route_points)


def manual_rectangle_area(width_km: float, height_km: float, area_km2: float | None = None) -> MissionArea:
    """Build a local rectangle for standalone simulator runs without map context."""
    width = max(width_km, 0.1)
    height = max(height_km, 0.1)
    return MissionArea(
        geometry_type="rectangle",
        centroid_lat=0.0,
        centroid_lon=0.0,
        area_km2=area_km2 if area_km2 is not None else width * height,
        width_km=width,
        height_km=height,
        local_polygon_km=[
            LocalPoint(0.0, 0.0),
            LocalPoint(width, 0.0),
            LocalPoint(width, height),
            LocalPoint(0.0, height),
        ],
        centroid_local_km=LocalPoint(width / 2.0, height / 2.0),
    )


def manual_payload_route(route_distance_km: float, route_heading_deg: float) -> MissionArea:
    """Build a route-only payload mission for manual simulator runs."""
    return MissionArea(
        geometry_type="line",
        centroid_lat=0.0,
        centroid_lon=0.0,
        route_distance_km=max(route_distance_km, 0.1),
        route_heading_deg=route_heading_deg % 360,
    )


def search_polygon_points(area: MissionArea) -> list[tuple[float, float]]:
    """Return local polygon points for lane clipping."""
    if len(area.local_polygon_km) >= 3:
        return [(point.x, point.y) for point in area.local_polygon_km]
    width = area.width_km or 0.0
    height = area.height_km or 0.0
    if width > 0 and height > 0:
        return [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return []


def local_bounds(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """Return min_x, max_x, min_y, max_y for local points."""
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), max(xs), min(ys), max(ys)


def lane_positions(start: float, end: float, spacing_km: float) -> list[float]:
    """Return lane center positions that cover a local interval."""
    span = max(end - start, 0.0)
    if span <= 1e-9:
        return [start]
    count = max(1, int(math.ceil(span / max(spacing_km, 0.001))))
    step = span / count
    return [start + (index + 0.5) * step for index in range(count)]


def dedupe_sorted(values: list[float], eps: float = 1e-8) -> list[float]:
    """Sort and de-duplicate line intersection coordinates."""
    deduped: list[float] = []
    for value in sorted(values):
        if not deduped or abs(value - deduped[-1]) > eps:
            deduped.append(value)
    return deduped


def vertical_intervals(points: list[tuple[float, float]], x: float) -> list[tuple[float, float]]:
    """Clip a vertical line against a simple polygon."""
    intersections: list[float] = []
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % len(points)]
        if abs(x1 - x0) < 1e-10:
            continue
        if (x0 <= x < x1) or (x1 <= x < x0):
            ratio = (x - x0) / (x1 - x0)
            intersections.append(y0 + ratio * (y1 - y0))
    ys = dedupe_sorted(intersections)
    return [(ys[index], ys[index + 1]) for index in range(0, len(ys) - 1, 2) if ys[index + 1] - ys[index] > 1e-8]


def horizontal_intervals(points: list[tuple[float, float]], y: float) -> list[tuple[float, float]]:
    """Clip a horizontal line against a simple polygon."""
    intersections: list[float] = []
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % len(points)]
        if abs(y1 - y0) < 1e-10:
            continue
        if (y0 <= y < y1) or (y1 <= y < y0):
            ratio = (y - y0) / (y1 - y0)
            intersections.append(x0 + ratio * (x1 - x0))
    xs = dedupe_sorted(intersections)
    return [(xs[index], xs[index + 1]) for index in range(0, len(xs) - 1, 2) if xs[index + 1] - xs[index] > 1e-8]


def clipped_search_lanes(area: MissionArea, track_spacing_m: float, orientation: str) -> dict[str, object]:
    """Generate swath-lane segments clipped to a rectangle or polygon."""
    points = search_polygon_points(area)
    if len(points) < 3:
        return {"points": [], "segments": [], "lane_count": 0, "turns": 0, "track_distance_km": 0.0}

    min_x, max_x, min_y, max_y = local_bounds(points)
    spacing_km = max(track_spacing_m / 1000.0, 0.001)
    segments: list[tuple[float, float, float, float]] = []
    lane_count = 0

    if orientation == "North-South":
        for lane_index, x in enumerate(lane_positions(min_x, max_x, spacing_km)):
            intervals = vertical_intervals(points, x)
            if intervals:
                lane_count += 1
            for segment_index, (y0, y1) in enumerate(intervals):
                if (lane_index + segment_index) % 2 == 1:
                    y0, y1 = y1, y0
                segments.append((x, y0, x, y1))
    else:
        for lane_index, y in enumerate(lane_positions(min_y, max_y, spacing_km)):
            intervals = horizontal_intervals(points, y)
            if intervals:
                lane_count += 1
            for segment_index, (x0, x1) in enumerate(intervals):
                if (lane_index + segment_index) % 2 == 1:
                    x0, x1 = x1, x0
                segments.append((x0, y, x1, y))

    track_distance = sum(math.hypot(x1 - x0, y1 - y0) for x0, y0, x1, y1 in segments)
    return {
        "points": points,
        "segments": segments,
        "lane_count": lane_count,
        "turns": max(0, lane_count - 1),
        "track_distance_km": track_distance,
        "spacing_km": spacing_km,
        "bounds": (min_x, max_x, min_y, max_y),
    }
