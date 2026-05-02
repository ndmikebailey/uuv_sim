"""Mission geometry and mission context dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

GeometryType = Literal["rectangle", "polygon", "line"]


@dataclass(frozen=True)
class LatLon:
    """Geodetic point in decimal degrees."""

    lat: float
    lon: float


@dataclass(frozen=True)
class LocalPoint:
    """Local tangent-plane point in kilometers."""

    x: float
    y: float


@dataclass(frozen=True)
class Bounds:
    """North/south/east/west bounds in decimal degrees."""

    north: float
    south: float
    east: float
    west: float


@dataclass
class MissionArea:
    """Search area or payload route selected from the map."""

    geometry_type: GeometryType
    centroid_lat: float
    centroid_lon: float
    area_km2: Optional[float] = None
    width_km: Optional[float] = None
    height_km: Optional[float] = None
    bounds: Optional[Bounds] = None
    vertices: list[LatLon] = field(default_factory=list)
    local_polygon_km: list[LocalPoint] = field(default_factory=list)
    centroid_local_km: Optional[LocalPoint] = None
    route_points: list[LatLon] = field(default_factory=list)
    route_distance_km: Optional[float] = None
    route_heading_deg: Optional[float] = None

    @property
    def is_search_area(self) -> bool:
        """Return True for rectangle and polygon search geometries."""
        return self.geometry_type in {"rectangle", "polygon"}

    @property
    def is_payload_route(self) -> bool:
        """Return True for payload route geometries."""
        return self.geometry_type == "line"

    def to_dict(self) -> dict[str, object]:
        """Serialize the mission area into a Gradio-state friendly dict."""
        return {
            "geometry_type": self.geometry_type,
            "centroid_lat": self.centroid_lat,
            "centroid_lon": self.centroid_lon,
            "area_km2": self.area_km2,
            "width_km": self.width_km,
            "height_km": self.height_km,
            "bounds": None if self.bounds is None else self.bounds.__dict__,
            "vertices": [point.__dict__ for point in self.vertices],
            "local_polygon_km": [point.__dict__ for point in self.local_polygon_km],
            "centroid_local_km": None if self.centroid_local_km is None else self.centroid_local_km.__dict__,
            "route_points": [point.__dict__ for point in self.route_points],
            "route_distance_km": self.route_distance_km,
            "route_heading_deg": self.route_heading_deg,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "MissionArea":
        """Build a ``MissionArea`` from serialized Gradio state."""
        bounds_data = data.get("bounds")
        centroid_local = data.get("centroid_local_km")
        return cls(
            geometry_type=str(data.get("geometry_type", "rectangle")),  # type: ignore[arg-type]
            centroid_lat=float(data.get("centroid_lat") or 0.0),
            centroid_lon=float(data.get("centroid_lon") or 0.0),
            area_km2=None if data.get("area_km2") is None else float(data.get("area_km2")),  # type: ignore[arg-type]
            width_km=None if data.get("width_km") is None else float(data.get("width_km")),  # type: ignore[arg-type]
            height_km=None if data.get("height_km") is None else float(data.get("height_km")),  # type: ignore[arg-type]
            bounds=Bounds(**bounds_data) if isinstance(bounds_data, dict) else None,
            vertices=[LatLon(**point) for point in data.get("vertices", []) if isinstance(point, dict)],  # type: ignore[arg-type]
            local_polygon_km=[LocalPoint(**point) for point in data.get("local_polygon_km", []) if isinstance(point, dict)],  # type: ignore[arg-type]
            centroid_local_km=LocalPoint(**centroid_local) if isinstance(centroid_local, dict) else None,
            route_points=[LatLon(**point) for point in data.get("route_points", []) if isinstance(point, dict)],  # type: ignore[arg-type]
            route_distance_km=None if data.get("route_distance_km") is None else float(data.get("route_distance_km")),  # type: ignore[arg-type]
            route_heading_deg=None if data.get("route_heading_deg") is None else float(data.get("route_heading_deg")),  # type: ignore[arg-type]
        )


@dataclass
class MissionAreaSet:
    """Multiple search areas treated as one aggregate Search/MCM mission plan."""

    areas: list[MissionArea]
    total_area_km2: float
    representative_points: list[tuple[float, float]]
    geometry_type: str = "MultiArea"

    @property
    def area_km2(self) -> float:
        """Return aggregate search area."""
        return self.total_area_km2

    @property
    def centroid_lat(self) -> float:
        """Return mean representative latitude for display fallback."""
        if not self.representative_points:
            return 0.0
        return sum(point[0] for point in self.representative_points) / len(self.representative_points)

    @property
    def centroid_lon(self) -> float:
        """Return mean representative longitude for display fallback."""
        if not self.representative_points:
            return 0.0
        return sum(point[1] for point in self.representative_points) / len(self.representative_points)

    @property
    def is_search_area(self) -> bool:
        """Return True because area sets are only used for Search/MCM."""
        return True

    @property
    def is_payload_route(self) -> bool:
        """Return False because area sets are not payload routes."""
        return False

    @property
    def width_km(self) -> float:
        """Return aggregate square width used by current combined search planner."""
        return self.total_area_km2 ** 0.5 if self.total_area_km2 > 0 else 0.0

    @property
    def height_km(self) -> float:
        """Return aggregate square height used by current combined search planner."""
        return self.width_km

    def aggregate_area(self) -> MissionArea:
        """Return a single equivalent area for existing search-energy logic."""
        from core.geometry import manual_rectangle_area

        side_km = max(self.total_area_km2, 0.1) ** 0.5
        area = manual_rectangle_area(side_km, side_km, self.total_area_km2)
        area.centroid_lat = self.centroid_lat
        area.centroid_lon = self.centroid_lon
        return area

    def to_dict(self) -> dict[str, object]:
        """Serialize the area set into Gradio-state friendly data."""
        return {
            "geometry_type": self.geometry_type,
            "areas": [area.to_dict() for area in self.areas],
            "total_area_km2": self.total_area_km2,
            "area_km2": self.total_area_km2,
            "number_of_search_areas": len(self.areas),
            "representative_points": [
                {"lat": point[0], "lon": point[1]}
                for point in self.representative_points
            ],
            "centroid_lat": self.centroid_lat,
            "centroid_lon": self.centroid_lon,
            "width_km": self.width_km,
            "height_km": self.height_km,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "MissionAreaSet":
        """Build a ``MissionAreaSet`` from serialized Gradio state."""
        areas = [
            MissionArea.from_dict(area)
            for area in data.get("areas", [])
            if isinstance(area, dict)
        ]
        representative_points: list[tuple[float, float]] = []
        for point in data.get("representative_points", []):
            if isinstance(point, dict):
                representative_points.append((float(point.get("lat", 0.0)), float(point.get("lon", 0.0))))
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                representative_points.append((float(point[0]), float(point[1])))
        if not representative_points:
            representative_points = [(area.centroid_lat, area.centroid_lon) for area in areas]
        total_area = data.get("total_area_km2", data.get("area_km2"))
        return cls(
            areas=areas,
            total_area_km2=float(total_area or sum(float(area.area_km2 or 0.0) for area in areas)),
            representative_points=representative_points,
        )


@dataclass
class MissionContext:
    """Mission type, selected geometry, and fused environment values."""

    mission_type: str
    area: MissionArea | MissionAreaSet
    environment: object

    def to_dict(self) -> dict[str, object]:
        """Serialize the mission context for Gradio state."""
        env = self.environment
        env_dict = env.to_dict() if hasattr(env, "to_dict") else {}
        return {
            "mission_type": self.mission_type,
            "area": self.area.to_dict(),
            "environment": env_dict,
            **self.area.to_dict(),
            **env_dict,
        }
