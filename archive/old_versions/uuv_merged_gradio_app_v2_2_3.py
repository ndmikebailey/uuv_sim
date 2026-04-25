
"""
UUV Mission Planning + Single-Mission Energy Simulator
Clean merged Gradio build for Colab/local review. V2.2.3 report cleanup: improved Monte Carlo chart scaling and search-pattern overlay readability.

Design rules:
- Gradio only. No Streamlit.
- Mission Builder creates an optional mission_context.
- Simulator still runs standalone if Mission Builder is skipped.
- Mission Builder context automatically pre-populates the simulator.
- Open-Meteo values are baseline environmental means; Monte Carlo samples around them.
- Monte Carlo runs are fixed at 100 for a simple operator-facing GUI.
"""

import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests


# ============================================================
# CONFIG
# ============================================================

APP_NAME = "UUV Mission Planning and Energy Simulator"
USER_AGENT = "uuv-capstone-gradio/0.22.1 (planning-scale research tool)"
REQUEST_TIMEOUT = 25
MONTE_CARLO_RUNS = 100
EARTH_RADIUS_KM = 6371.0088

OPEN_METEO_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"

REGION_PRESETS = {
    "Guam": (13.4443, 144.7937, 8),
    "Saipan": (15.1778, 145.7500, 9),
    "Tinian": (14.9997, 145.6197, 10),
    "Rota": (14.1693, 145.2444, 10),
    "Palau": (7.5150, 134.5825, 8),
    "Yap": (9.5167, 138.1167, 8),
    "Chuuk": (7.4167, 151.7833, 8),
    "Pohnpei": (6.9667, 158.2167, 8),
    "Majuro": (7.1164, 171.1850, 8),
}

MISSION_TYPES = ["ISR", "Area Search / MCM", "Payload Delivery"]
SEARCH_MISSIONS = {"ISR", "Area Search / MCM"}

# REMUS values from project manufacturer datasheet. IVER4/Knifefish are placeholders.
PLATFORMS = {
    "REMUS 300 - 1.5 kWh": {
        "battery_kwh": 1.5,
        "estimated_endurance_hr": 10.0,
        "nominal_speed_kts": 3.5,
        "max_speed_kts": 5.0,
        "recharge_hr": 6.0,
        "usable_fraction": 0.88,
        "usable_basis": "Planning assumption: 88% usable Li-ion energy after reserve / battery-health allowance.",
        "source_note": "Manufacturer-published REMUS 300M datasheet",
    },
    "REMUS 300 - 3.0 kWh": {
        "battery_kwh": 3.0,
        "estimated_endurance_hr": 20.0,
        "nominal_speed_kts": 3.5,
        "max_speed_kts": 5.0,
        "recharge_hr": 12.0,
        "usable_fraction": 0.88,
        "usable_basis": "Planning assumption: 88% usable Li-ion energy after reserve / battery-health allowance.",
        "source_note": "Manufacturer-published REMUS 300M datasheet",
    },
    "REMUS 300 - 4.5 kWh": {
        "battery_kwh": 4.5,
        "estimated_endurance_hr": 30.0,
        "nominal_speed_kts": 3.5,
        "max_speed_kts": 5.0,
        "recharge_hr": 18.0,
        "usable_fraction": 0.88,
        "usable_basis": "Planning assumption: 88% usable Li-ion energy after reserve / battery-health allowance.",
        "source_note": "Manufacturer-published REMUS 300M datasheet",
    },
    "IVER4": {
        "battery_kwh": 3.0,
        "estimated_endurance_hr": 20.0,
        "nominal_speed_kts": 3.5,
        "max_speed_kts": 5.0,
        "recharge_hr": 12.0,
        "usable_fraction": 0.85,
        "usable_basis": "Placeholder planning assumption: 85% usable energy until validated platform battery data are loaded.",
        "source_note": "PLACEHOLDER - replace with validated IVER4 data",
    },
    "Knifefish": {
        "battery_kwh": 8.0,
        "estimated_endurance_hr": 16.0,
        "nominal_speed_kts": 3.0,
        "max_speed_kts": 5.0,
        "recharge_hr": 16.0,
        "usable_fraction": 0.85,
        "usable_basis": "Placeholder planning assumption: 85% usable energy until validated platform battery data are loaded.",
        "source_note": "PLACEHOLDER - replace with validated Knifefish data",
    },
}


# ============================================================
# BASIC HELPERS
# ============================================================

def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_lam = math.radians(lon2 - lon1)
    y = math.sin(d_lam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lam)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def weather_code_to_text(code: Optional[float]) -> str:
    mapping = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle",
        53: "Moderate drizzle", 55: "Dense drizzle", 61: "Slight rain",
        63: "Moderate rain", 65: "Heavy rain", 80: "Slight rain showers",
        81: "Moderate rain showers", 82: "Violent rain showers",
        95: "Thunderstorm", 96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    if code is None:
        return "Unknown"
    return mapping.get(int(code), f"Weather code {int(code)}")


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _clean_latlon_vertices(raw_vertices: Any) -> List[Dict[str, float]]:
    vertices = []
    for item in raw_vertices or []:
        lat = lon = None
        if isinstance(item, dict):
            lat = safe_float(item.get("lat"))
            lon = safe_float(item.get("lon", item.get("lng")))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            lat = safe_float(item[0])
            lon = safe_float(item[1])
        if lat is not None and lon is not None:
            vertices.append({"lat": float(lat), "lon": float(lon)})

    if len(vertices) > 1:
        first = vertices[0]
        last = vertices[-1]
        if abs(first["lat"] - last["lat"]) < 1e-9 and abs(first["lon"] - last["lon"]) < 1e-9:
            vertices.pop()
    return vertices


def _vertices_from_bounds(bounds: Any) -> List[Dict[str, float]]:
    if not isinstance(bounds, dict):
        return []
    north = safe_float(bounds.get("north"))
    south = safe_float(bounds.get("south"))
    east = safe_float(bounds.get("east"))
    west = safe_float(bounds.get("west"))
    if None in (north, south, east, west):
        return []
    return [
        {"lat": float(south), "lon": float(west)},
        {"lat": float(south), "lon": float(east)},
        {"lat": float(north), "lon": float(east)},
        {"lat": float(north), "lon": float(west)},
    ]


def _project_latlon_vertices(vertices: List[Dict[str, float]]) -> Tuple[List[Tuple[float, float]], float, float, float]:
    lat0 = sum(v["lat"] for v in vertices) / len(vertices)
    lon0 = sum(v["lon"] for v in vertices) / len(vertices)
    cos_lat0 = max(abs(math.cos(math.radians(lat0))), 1e-6)
    points = []
    for vertex in vertices:
        x = EARTH_RADIUS_KM * math.radians(vertex["lon"] - lon0) * cos_lat0
        y = EARTH_RADIUS_KM * math.radians(vertex["lat"] - lat0)
        points.append((x, y))
    return points, lat0, lon0, cos_lat0


def _shoelace_area_centroid(points: List[Tuple[float, float]]) -> Tuple[float, Tuple[float, float]]:
    twice_area = 0.0
    cx_sum = 0.0
    cy_sum = 0.0
    for idx, (x0, y0) in enumerate(points):
        x1, y1 = points[(idx + 1) % len(points)]
        cross = x0 * y1 - x1 * y0
        twice_area += cross
        cx_sum += (x0 + x1) * cross
        cy_sum += (y0 + y1) * cross

    signed_area = twice_area / 2.0
    if abs(signed_area) < 1e-9:
        avg_x = sum(x for x, _ in points) / len(points)
        avg_y = sum(y for _, y in points) / len(points)
        return 0.0, (avg_x, avg_y)
    return abs(signed_area), (cx_sum / (6.0 * signed_area), cy_sum / (6.0 * signed_area))


def recompute_search_geometry(geom: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    geometry_type = geom.get("geometry_type")
    vertices = _clean_latlon_vertices(geom.get("vertices"))
    if geometry_type == "rectangle" and len(vertices) < 4:
        vertices = _vertices_from_bounds(geom.get("bounds"))

    min_vertices = 4 if geometry_type == "rectangle" else 3
    if len(vertices) < min_vertices:
        return {}, f"{geometry_type.title()} geometry did not include enough vertices."

    raw_points, lat0, lon0, cos_lat0 = _project_latlon_vertices(vertices)
    area_km2, (centroid_x, centroid_y) = _shoelace_area_centroid(raw_points)
    if area_km2 <= 0:
        return {}, f"{geometry_type.title()} geometry has no measurable area. Redraw the search area."

    xs = [x for x, _ in raw_points]
    ys = [y for _, y in raw_points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width_km = max(max_x - min_x, 0.0)
    height_km = max(max_y - min_y, 0.0)

    centroid_lat = lat0 + math.degrees(centroid_y / EARTH_RADIUS_KM)
    centroid_lon = lon0 + math.degrees(centroid_x / (EARTH_RADIUS_KM * cos_lat0))
    lats = [v["lat"] for v in vertices]
    lons = [v["lon"] for v in vertices]

    return {
        "geometry_type": geometry_type,
        "centroid_lat": centroid_lat,
        "centroid_lon": centroid_lon,
        "area_km2": area_km2,
        "width_km": width_km,
        "height_km": height_km,
        "bounds": {
            "north": max(lats),
            "south": min(lats),
            "east": max(lons),
            "west": min(lons),
        },
        "vertices": vertices,
        "local_polygon_km": [{"x": x - min_x, "y": y - min_y} for x, y in raw_points],
        "centroid_local_km": {"x": centroid_x - min_x, "y": centroid_y - min_y},
    }, "Search geometry parsed."


def search_polygon_points(context: Optional[Dict[str, Any]], width_km: float = 0.0, height_km: float = 0.0) -> List[Tuple[float, float]]:
    context = context or {}
    raw_points = context.get("local_polygon_km")
    points = []
    if raw_points:
        for point in raw_points:
            if isinstance(point, dict):
                x = safe_float(point.get("x"))
                y = safe_float(point.get("y"))
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                x = safe_float(point[0])
                y = safe_float(point[1])
            else:
                x = y = None
            if x is not None and y is not None:
                points.append((float(x), float(y)))
    if len(points) >= 3:
        return points

    width = max(safe_float(context.get("width_km"), width_km) or width_km, 0.0)
    height = max(safe_float(context.get("height_km"), height_km) or height_km, 0.0)
    if width > 0 and height > 0:
        return [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return []


def _polygon_bounds(points: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), max(xs), min(ys), max(ys)


def _lane_positions(start: float, end: float, spacing_km: float) -> List[float]:
    span = max(end - start, 0.0)
    if span <= 1e-9:
        return [start]
    count = max(1, int(math.ceil(span / max(spacing_km, 0.001))))
    step = span / count
    return [start + (idx + 0.5) * step for idx in range(count)]


def _dedupe_sorted(values: List[float], eps: float = 1e-8) -> List[float]:
    deduped = []
    for value in sorted(values):
        if not deduped or abs(value - deduped[-1]) > eps:
            deduped.append(value)
    return deduped


def _vertical_intervals(points: List[Tuple[float, float]], x: float) -> List[Tuple[float, float]]:
    intersections = []
    for idx, (x0, y0) in enumerate(points):
        x1, y1 = points[(idx + 1) % len(points)]
        if abs(x1 - x0) < 1e-10:
            continue
        if (x0 <= x < x1) or (x1 <= x < x0):
            ratio = (x - x0) / (x1 - x0)
            intersections.append(y0 + ratio * (y1 - y0))
    ys = _dedupe_sorted(intersections)
    return [(ys[i], ys[i + 1]) for i in range(0, len(ys) - 1, 2) if ys[i + 1] - ys[i] > 1e-8]


def _horizontal_intervals(points: List[Tuple[float, float]], y: float) -> List[Tuple[float, float]]:
    intersections = []
    for idx, (x0, y0) in enumerate(points):
        x1, y1 = points[(idx + 1) % len(points)]
        if abs(y1 - y0) < 1e-10:
            continue
        if (y0 <= y < y1) or (y1 <= y < y0):
            ratio = (y - y0) / (y1 - y0)
            intersections.append(x0 + ratio * (x1 - x0))
    xs = _dedupe_sorted(intersections)
    return [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2) if xs[i + 1] - xs[i] > 1e-8]


def clipped_search_lanes(context: Optional[Dict[str, Any]], width_km: float, height_km: float, track_spacing_m: float, orientation: str) -> Dict[str, Any]:
    points = search_polygon_points(context, width_km, height_km)
    if len(points) < 3:
        return {"points": [], "segments": [], "lane_count": 0, "turns": 0, "track_distance_km": 0.0}

    min_x, max_x, min_y, max_y = _polygon_bounds(points)
    spacing_km = max((safe_float(track_spacing_m, 200) or 200) / 1000.0, 0.001)
    segments = []
    lane_positions_with_coverage = 0

    if orientation == "North-South":
        for lane_idx, x in enumerate(_lane_positions(min_x, max_x, spacing_km)):
            intervals = _vertical_intervals(points, x)
            if intervals:
                lane_positions_with_coverage += 1
            for segment_idx, (y0, y1) in enumerate(intervals):
                if (lane_idx + segment_idx) % 2 == 1:
                    y0, y1 = y1, y0
                segments.append((x, y0, x, y1))
    else:
        for lane_idx, y in enumerate(_lane_positions(min_y, max_y, spacing_km)):
            intervals = _horizontal_intervals(points, y)
            if intervals:
                lane_positions_with_coverage += 1
            for segment_idx, (x0, x1) in enumerate(intervals):
                if (lane_idx + segment_idx) % 2 == 1:
                    x0, x1 = x1, x0
                segments.append((x0, y, x1, y))

    track_distance = sum(math.hypot(x1 - x0, y1 - y0) for x0, y0, x1, y1 in segments)
    turns = max(0, lane_positions_with_coverage - 1)
    return {
        "points": points,
        "segments": segments,
        "lane_count": lane_positions_with_coverage,
        "turns": turns,
        "track_distance_km": track_distance,
        "spacing_km": spacing_km,
        "bounds": (min_x, max_x, min_y, max_y),
    }


# ============================================================
# MAP / MISSION BUILDER
# ============================================================

def build_leaflet_iframe(region_name: str = "Guam") -> str:
    lat, lon, zoom = REGION_PRESETS.get(region_name, REGION_PRESETS["Guam"])

    inner_html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.css"/>
  <style>
    html, body {{
      margin: 0; padding: 0; background: #0b1220; color: white;
      font-family: Arial, sans-serif;
    }}
    #map {{ width: 100%; height: 560px; }}
    #output {{
      padding: 12px; background: #111827; min-height: 96px;
      font-family: Arial, sans-serif; font-size: 14px;
    }}
    #raw_output {{ display: none; }}
    .note {{ padding: 8px 10px; background: #1f2937; font-size: 12px; }}
    .snap-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
    .snap-card {{ border: 1px solid #374151; border-radius: 10px; padding: 10px; background: #0f172a; }}
    .snap-label {{ color: #9ca3af; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }}
    .snap-value {{ color: #ffffff; font-size: 20px; font-weight: 800; margin-top: 3px; }}
    .snap-sub {{ color: #cbd5e1; font-size: 12px; margin-top: 6px; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="note">
    Draw one rectangle or polygon for ISR or Area Search/MCM, or one line for Payload Delivery.
    The geometry will automatically load into the Mission Builder panel.
  </div>
  <div id="output">
    <div class="snap-grid">
      <div class="snap-card"><div class="snap-label">Mission Geometry</div><div class="snap-value">Not loaded</div><div class="snap-sub">Draw a rectangle, polygon, or line.</div></div>
      <div class="snap-card"><div class="snap-label">Area / Route</div><div class="snap-value">--</div><div class="snap-sub">Waiting on mission geometry.</div></div>
      <div class="snap-card"><div class="snap-label">Centroid</div><div class="snap-value">--</div><div class="snap-sub">Used for Open-Meteo lookup.</div></div>
    </div>
  </div>
  <pre id="raw_output"></pre>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.js"></script>

  <script>
    const map = L.map('map').setView([{lat}, {lon}], {zoom});

    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    const drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);

    const drawControl = new L.Control.Draw({{
      draw: {{
        polygon: true,
        polyline: true,
        rectangle: true,
        circle: false,
        circlemarker: false,
        marker: false
      }},
      edit: {{
        featureGroup: drawnItems,
        remove: true
      }}
    }});
    map.addControl(drawControl);

    function haversineKm(lat1, lon1, lat2, lon2) {{
      const R = 6371.0088;
      const toRad = deg => deg * Math.PI / 180;
      const dLat = toRad(lat2 - lat1);
      const dLon = toRad(lon2 - lon1);
      const a =
        Math.sin(dLat / 2) ** 2 +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
        Math.sin(dLon / 2) ** 2;
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
      return R * c;
    }}

    function bearingDeg(lat1, lon1, lat2, lon2) {{
      const toRad = deg => deg * Math.PI / 180;
      const toDeg = rad => rad * 180 / Math.PI;
      const phi1 = toRad(lat1);
      const phi2 = toRad(lat2);
      const dLon = toRad(lon2 - lon1);
      const y = Math.sin(dLon) * Math.cos(phi2);
      const x = Math.cos(phi1) * Math.sin(phi2) -
                Math.sin(phi1) * Math.cos(phi2) * Math.cos(dLon);
      return (toDeg(Math.atan2(y, x)) + 360) % 360;
    }}

    function searchAreaSummary(vertices, geometryType) {{
      if (!vertices || vertices.length < 3) {{
        return {{ geometry_type: geometryType, error: "Search area requires at least three points." }};
      }}

      const lats = vertices.map(v => v.lat);
      const lons = vertices.map(v => v.lon);
      const north = Math.max(...lats);
      const south = Math.min(...lats);
      const east = Math.max(...lons);
      const west = Math.min(...lons);
      const lat0 = lats.reduce((a, b) => a + b, 0) / lats.length;
      const lon0 = lons.reduce((a, b) => a + b, 0) / lons.length;
      const toRad = deg => deg * Math.PI / 180;
      const toDeg = rad => rad * 180 / Math.PI;
      const R = 6371.0088;
      const cosLat = Math.max(Math.abs(Math.cos(toRad(lat0))), 1e-6);
      const xy = vertices.map(v => ({{
        x: R * toRad(v.lon - lon0) * cosLat,
        y: R * toRad(v.lat - lat0)
      }}));

      let twiceArea = 0;
      let cxSum = 0;
      let cySum = 0;
      for (let i = 0; i < xy.length; i++) {{
        const p0 = xy[i];
        const p1 = xy[(i + 1) % xy.length];
        const cross = p0.x * p1.y - p1.x * p0.y;
        twiceArea += cross;
        cxSum += (p0.x + p1.x) * cross;
        cySum += (p0.y + p1.y) * cross;
      }}

      const signedArea = twiceArea / 2;
      const areaKm2 = Math.abs(signedArea);
      let centroidX = xy.reduce((sum, p) => sum + p.x, 0) / xy.length;
      let centroidY = xy.reduce((sum, p) => sum + p.y, 0) / xy.length;
      if (Math.abs(signedArea) > 1e-9) {{
        centroidX = cxSum / (6 * signedArea);
        centroidY = cySum / (6 * signedArea);
      }}

      const centroidLat = lat0 + toDeg(centroidY / R);
      const centroidLon = lon0 + toDeg(centroidX / (R * cosLat));
      const widthKm = haversineKm((north + south) / 2, west, (north + south) / 2, east);
      const heightKm = haversineKm(south, (east + west) / 2, north, (east + west) / 2);

      return {{
        geometry_type: geometryType,
        centroid_lat: +centroidLat.toFixed(6),
        centroid_lon: +centroidLon.toFixed(6),
        width_km: +widthKm.toFixed(3),
        height_km: +heightKm.toFixed(3),
        area_km2: +areaKm2.toFixed(3),
        bounds: {{
          north: +north.toFixed(6),
          south: +south.toFixed(6),
          east: +east.toFixed(6),
          west: +west.toFixed(6)
        }},
        vertices: vertices.map(v => ({{ lat: +v.lat.toFixed(6), lon: +v.lon.toFixed(6) }})),
        route_distance_km: null,
        route_heading_deg: null
      }};
    }}

    function rectangleSummary(layer) {{
      const bounds = layer.getBounds();
      const north = bounds.getNorth();
      const south = bounds.getSouth();
      const east = bounds.getEast();
      const west = bounds.getWest();
      return searchAreaSummary([
        {{ lat: south, lon: west }},
        {{ lat: south, lon: east }},
        {{ lat: north, lon: east }},
        {{ lat: north, lon: west }}
      ], "rectangle");
    }}

    function polygonSummary(layer) {{
      const rings = layer.getLatLngs();
      const pts = Array.isArray(rings[0]) ? rings[0] : rings;
      const vertices = pts.map(p => ({{ lat: p.lat, lon: p.lng }}));
      return searchAreaSummary(vertices, "polygon");
    }}

    function lineSummary(layer) {{
      const pts = layer.getLatLngs();
      if (!pts || pts.length < 2) {{
        return {{ geometry_type: "line", error: "Line requires at least two points." }};
      }}

      const start = pts[0];
      const end = pts[pts.length - 1];
      let totalKm = 0;
      for (let i = 0; i < pts.length - 1; i++) {{
        totalKm += haversineKm(pts[i].lat, pts[i].lng, pts[i + 1].lat, pts[i + 1].lng);
      }}

      const heading = bearingDeg(start.lat, start.lng, end.lat, end.lng);

      // Route centroid is the midpoint between first and last point. This fixes
      // the earlier line issue where no centroid was available for Open-Meteo.
      const centroidLat = (start.lat + end.lat) / 2;
      const centroidLon = (start.lng + end.lng) / 2;

      return {{
        geometry_type: "line",
        centroid_lat: +centroidLat.toFixed(6),
        centroid_lon: +centroidLon.toFixed(6),
        area_km2: null,
        width_km: null,
        height_km: null,
        bounds: null,
        route_start_lat: +start.lat.toFixed(6),
        route_start_lon: +start.lng.toFixed(6),
        route_end_lat: +end.lat.toFixed(6),
        route_end_lon: +end.lng.toFixed(6),
        route_distance_km: +totalKm.toFixed(3),
        route_heading_deg: +heading.toFixed(1)
      }};
    }}

    function snapshotHtml(summary) {{
      if (!summary || summary.error) {{
        return '<div class="snap-grid">' +
          '<div class="snap-card"><div class="snap-label">Mission Geometry</div><div class="snap-value">Error</div><div class="snap-sub">' + (summary && summary.error ? summary.error : 'Redraw geometry.') + '</div></div>' +
          '<div class="snap-card"><div class="snap-label">Area / Route</div><div class="snap-value">--</div><div class="snap-sub">No usable geometry.</div></div>' +
          '<div class="snap-card"><div class="snap-label">Centroid</div><div class="snap-value">--</div><div class="snap-sub">No lookup point.</div></div>' +
          '</div>';
      }}
      if (summary.geometry_type === 'rectangle' || summary.geometry_type === 'polygon') {{
        const shapeLabel = summary.geometry_type === 'polygon' ? 'Polygon search area' : 'Rectangle search area';
        const vertexNote = summary.geometry_type === 'polygon' ? 'Vertices: ' + (summary.vertices ? summary.vertices.length : 0) + '.' : 'Rectangle captured.';
        return '<div class="snap-grid">' +
          '<div class="snap-card"><div class="snap-label">Mission Geometry</div><div class="snap-value">Search Area</div><div class="snap-sub">' + shapeLabel + ' for ISR / Area Search / MCM. ' + vertexNote + '</div></div>' +
          '<div class="snap-card"><div class="snap-label">Area</div><div class="snap-value">' + summary.area_km2 + ' km²</div><div class="snap-sub">Dimensions: ' + summary.width_km + ' × ' + summary.height_km + ' km</div></div>' +
          '<div class="snap-card"><div class="snap-label">Centroid</div><div class="snap-value">' + summary.centroid_lat + ', ' + summary.centroid_lon + '</div><div class="snap-sub">Ready for environmental query.</div></div>' +
          '</div>';
      }}
      return '<div class="snap-grid">' +
        '<div class="snap-card"><div class="snap-label">Mission Geometry</div><div class="snap-value">Payload Route</div><div class="snap-sub">Line captured from launch/drop point to target.</div></div>' +
        '<div class="snap-card"><div class="snap-label">Route</div><div class="snap-value">' + summary.route_distance_km + ' km</div><div class="snap-sub">Heading: ' + summary.route_heading_deg + '°</div></div>' +
        '<div class="snap-card"><div class="snap-label">Centroid</div><div class="snap-value">' + summary.centroid_lat + ', ' + summary.centroid_lon + '</div><div class="snap-sub">Ready for environmental query.</div></div>' +
        '</div>';
    }}

    function sendGeometry(summary) {{
      const text = JSON.stringify(summary, null, 2);
      document.getElementById("raw_output").textContent = text;
      document.getElementById("output").innerHTML = snapshotHtml(summary);
      try {{
        window.parent.postMessage({{ type: "uuv_geometry", payload: summary }}, "*");
      }} catch (e) {{
        console.log("Could not post geometry to parent", e);
      }}
    }}

    function summarizeLayer(layer) {{
      if (layer instanceof L.Rectangle) {{
        sendGeometry(rectangleSummary(layer));
      }} else if (layer instanceof L.Polygon) {{
        sendGeometry(polygonSummary(layer));
      }} else if (layer instanceof L.Polyline) {{
        sendGeometry(lineSummary(layer));
      }} else {{
        sendGeometry({{ error: "Unsupported geometry type." }});
      }}
    }}

    map.on(L.Draw.Event.CREATED, function (event) {{
      drawnItems.clearLayers();
      const layer = event.layer;
      drawnItems.addLayer(layer);
      summarizeLayer(layer);
    }});

    map.on(L.Draw.Event.EDITED, function (event) {{
      event.layers.eachLayer(function(layer) {{
        summarizeLayer(layer);
      }});
    }});

    map.on(L.Draw.Event.DELETED, function () {{
      document.getElementById("raw_output").textContent = "";
      document.getElementById("output").innerHTML =
        '<div class="snap-grid">' +
        '<div class="snap-card"><div class="snap-label">Mission Geometry</div><div class="snap-value">Not loaded</div><div class="snap-sub">Draw a rectangle, polygon, or line.</div></div>' +
        '<div class="snap-card"><div class="snap-label">Area / Route</div><div class="snap-value">--</div><div class="snap-sub">Waiting on mission geometry.</div></div>' +
        '<div class="snap-card"><div class="snap-label">Centroid</div><div class="snap-value">--</div><div class="snap-sub">Used for Open-Meteo lookup.</div></div>' +
        '</div>';
      try {{
        window.parent.postMessage({{ type: "uuv_geometry", payload: {{}} }}, "*");
      }} catch (e) {{}}
    }});
  </script>
</body>
</html>
"""

    srcdoc = inner_html.replace("&", "&amp;").replace("'", "&apos;").replace('"', "&quot;")
    return f"""
<iframe
  id="uuv_map_iframe"
  title="uuv-mission-map"
  srcdoc="{srcdoc}"
  width="100%"
  height="700"
  style="border:none; border-radius:12px; overflow:hidden; background:#0b1220;"
></iframe>
"""


def parse_geometry_json(geometry_json_text: str) -> Tuple[Dict[str, Any], str]:
    if not geometry_json_text or not geometry_json_text.strip():
        return {}, "Draw a rectangle, polygon, or line on the map first."

    try:
        geom = json.loads(geometry_json_text)
    except json.JSONDecodeError as exc:
        return {}, f"Could not parse map geometry JSON: {exc}"

    if geom.get("error"):
        return {}, geom["error"]

    geometry_type = geom.get("geometry_type")
    if geometry_type not in {"rectangle", "polygon", "line"}:
        return {}, "Unsupported or missing geometry type."

    if geometry_type in {"rectangle", "polygon"}:
        search_context, msg = recompute_search_geometry(geom)
        if not search_context:
            return {}, msg
    else:
        centroid_lat = safe_float(geom.get("centroid_lat"))
        centroid_lon = safe_float(geom.get("centroid_lon"))
        if centroid_lat is None or centroid_lon is None:
            return {}, "Map geometry did not include a centroid. Redraw the shape and try again."
        search_context = {
            "geometry_type": geometry_type,
            "centroid_lat": centroid_lat,
            "centroid_lon": centroid_lon,
            "area_km2": safe_float(geom.get("area_km2")),
            "width_km": safe_float(geom.get("width_km")),
            "height_km": safe_float(geom.get("height_km")),
            "bounds": geom.get("bounds"),
        }

    context = {
        "mission_type": None,
        **search_context,
        "route_start_lat": safe_float(geom.get("route_start_lat")),
        "route_start_lon": safe_float(geom.get("route_start_lon")),
        "route_end_lat": safe_float(geom.get("route_end_lat")),
        "route_end_lon": safe_float(geom.get("route_end_lon")),
        "route_distance_km": safe_float(geom.get("route_distance_km")),
        "route_heading_deg": safe_float(geom.get("route_heading_deg")),
        "current_speed_kts_mean": None,
        "current_direction_deg_mean": None,
        "sea_surface_temp_c_mean": None,
        "wind_speed_kts_mean": None,
        "wind_direction_deg_mean": None,
        "weather_summary": None,
        "source": "Open-Meteo",
        "geometry_source": "Leaflet / OpenStreetMap",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    return context, "Geometry parsed."


# ============================================================
# OPEN-METEO ENVIRONMENT
# ============================================================

def _requests_get_json(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return response.json()


def get_open_meteo_marine(lat: float, lon: float) -> Dict[str, Any]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join([
            "ocean_current_velocity",
            "ocean_current_direction",
            "sea_surface_temperature",
            "sea_level_height_msl",
            "wave_height",
            "wave_direction",
            "wave_period",
            "wind_wave_height",
            "swell_wave_height",
        ]),
        "hourly": ",".join([
            "ocean_current_velocity",
            "ocean_current_direction",
            "sea_surface_temperature",
            "sea_level_height_msl",
            "wave_height",
            "wave_direction",
            "wave_period",
            "wind_wave_height",
            "swell_wave_height",
        ]),
        "forecast_hours": 24,
        "past_hours": 6,
        "cell_selection": "sea",
        "velocity_unit": "kn",
        "timeformat": "iso8601",
    }
    try:
        data = _requests_get_json(OPEN_METEO_MARINE_URL, params)
        current = data.get("current", {})
        return {
            "ok": True,
            "current_speed_kts_mean": current.get("ocean_current_velocity"),
            "current_direction_deg_mean": current.get("ocean_current_direction"),
            "sea_surface_temp_c_mean": current.get("sea_surface_temperature"),
            "sea_level_height_m": current.get("sea_level_height_msl"),
            "wave_height_m": current.get("wave_height"),
            "wave_direction_deg": current.get("wave_direction"),
            "wave_period_s": current.get("wave_period"),
            "wind_wave_height_m": current.get("wind_wave_height"),
            "swell_wave_height_m": current.get("swell_wave_height"),
            "raw": data,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def get_open_meteo_weather(lat: float, lon: float) -> Dict[str, Any]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "precipitation",
            "weather_code",
            "cloud_cover",
            "pressure_msl",
            "surface_pressure",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
        ]),
        "wind_speed_unit": "kn",
        "timeformat": "iso8601",
    }
    try:
        data = _requests_get_json(OPEN_METEO_WEATHER_URL, params)
        current = data.get("current", {})
        code = current.get("weather_code")
        return {
            "ok": True,
            "air_temp_c": current.get("temperature_2m"),
            "relative_humidity_pct": current.get("relative_humidity_2m"),
            "apparent_temp_c": current.get("apparent_temperature"),
            "precipitation_mm": current.get("precipitation"),
            "weather_code": code,
            "weather_summary": weather_code_to_text(code),
            "cloud_cover_pct": current.get("cloud_cover"),
            "pressure_msl_hpa": current.get("pressure_msl"),
            "surface_pressure_hpa": current.get("surface_pressure"),
            "wind_speed_kts_mean": current.get("wind_speed_10m"),
            "wind_direction_deg_mean": current.get("wind_direction_10m"),
            "wind_gusts_kts": current.get("wind_gusts_10m"),
            "raw": data,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def fetch_environment_for_context(context: Dict[str, Any]) -> Tuple[Dict[str, Any], str, pd.DataFrame]:
    if not context:
        return {}, "No mission geometry available.", pd.DataFrame()

    lat = safe_float(context.get("centroid_lat"))
    lon = safe_float(context.get("centroid_lon"))
    if lat is None or lon is None:
        return context, "Mission context has no valid centroid.", pd.DataFrame()

    marine = get_open_meteo_marine(lat, lon)
    weather = get_open_meteo_weather(lat, lon)

    if marine.get("ok"):
        for key in [
            "current_speed_kts_mean", "current_direction_deg_mean",
            "sea_surface_temp_c_mean", "sea_level_height_m",
            "wave_height_m", "wave_direction_deg", "wave_period_s",
            "wind_wave_height_m", "swell_wave_height_m",
        ]:
            context[key] = marine.get(key)
    else:
        context["marine_error"] = marine.get("error")

    if weather.get("ok"):
        for key in [
            "air_temp_c", "relative_humidity_pct", "apparent_temp_c",
            "precipitation_mm", "weather_code", "weather_summary",
            "cloud_cover_pct", "pressure_msl_hpa", "surface_pressure_hpa",
            "wind_speed_kts_mean", "wind_direction_deg_mean", "wind_gusts_kts",
        ]:
            context[key] = weather.get(key)
    else:
        context["weather_error"] = weather.get("error")

    context["environment_source"] = "Open-Meteo"
    context["environment_loaded_at_utc"] = datetime.now(timezone.utc).isoformat()

    rows = [
        ("Centroid latitude", context.get("centroid_lat"), "deg"),
        ("Centroid longitude", context.get("centroid_lon"), "deg"),
        ("Current speed mean", context.get("current_speed_kts_mean"), "kts"),
        ("Current direction mean", context.get("current_direction_deg_mean"), "deg"),
        ("Sea surface temperature", context.get("sea_surface_temp_c_mean"), "°C"),
        ("Sea level height MSL", context.get("sea_level_height_m"), "m"),
        ("Wave height", context.get("wave_height_m"), "m"),
        ("Wave direction", context.get("wave_direction_deg"), "deg"),
        ("Wave period", context.get("wave_period_s"), "s"),
        ("Wind speed", context.get("wind_speed_kts_mean"), "kts"),
        ("Wind direction", context.get("wind_direction_deg_mean"), "deg"),
        ("Wind gusts", context.get("wind_gusts_kts"), "kts"),
        ("Air temperature", context.get("air_temp_c"), "°C"),
        ("Cloud cover", context.get("cloud_cover_pct"), "%"),
        ("Pressure MSL", context.get("pressure_msl_hpa"), "hPa"),
        ("Weather summary", context.get("weather_summary"), ""),
    ]
    df = pd.DataFrame(rows, columns=["Environmental / Geometry Item", "Value", "Unit"])

    status = "Mission geometry and Open-Meteo environmental data loaded."
    if marine.get("error") or weather.get("error"):
        status += f"\nMarine status: {marine.get('error', 'OK')}\nWeather status: {weather.get('error', 'OK')}"
    return context, status, df



def env_table_to_html(df: pd.DataFrame, title: str = "Mission Geometry and Environmental Data") -> str:
    if df is None or df.empty:
        return "<div class='uuv-card'><b>No mission/environment data loaded.</b></div>"
    rows = []
    for _, row in df.iterrows():
        item = str(row.get("Environmental / Geometry Item", ""))
        val = row.get("Value", "")
        unit = str(row.get("Unit", ""))
        if isinstance(val, float):
            val_txt = f"{val:.3f}".rstrip("0").rstrip(".")
        else:
            val_txt = "" if val is None else str(val)
        rows.append(
            f"<tr><td>{item}</td><td class='value'>{val_txt}</td><td>{unit}</td></tr>"
        )
    return f"""
    <div class='uuv-card full-width-card'>
      <h3>{title}</h3>
      <table class='uuv-table'>
        <thead><tr><th>Item</th><th>Value</th><th>Unit</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <div class='uuv-attribution'><a href='https://open-meteo.com/'>Weather data by Open-Meteo.com</a></div>
    </div>
    """


def risk_level(value: Optional[float], low_max: float, mod_max: float, missing: str = "Unknown") -> Tuple[str, str]:
    val = safe_float(value)
    if val is None:
        return missing, "gray"
    if val <= low_max:
        return "Favorable", "green"
    if val <= mod_max:
        return "Marginal", "yellow"
    return "Unfavorable", "red"


def temp_risk_level(temp_c: Optional[float]) -> Tuple[str, str]:
    temp = safe_float(temp_c)
    if temp is None:
        return "Unknown", "gray"
    if 10 <= temp <= 30:
        return "Favorable", "green"
    if 0 <= temp < 10 or 30 < temp <= 35:
        return "Marginal", "yellow"
    return "Unfavorable", "red"


def weather_risk_level(code: Optional[float], precip_mm: Optional[float]) -> Tuple[str, str]:
    c = safe_int(code, -1)
    p = safe_float(precip_mm) or 0.0
    if c in [95, 96, 99] or p >= 10:
        return "Unfavorable", "red"
    if c in [3, 45, 48, 51, 53, 55, 61, 63, 65, 80, 81, 82] or p > 0:
        return "Marginal", "yellow"
    if c >= 0:
        return "Favorable", "green"
    return "Unknown", "gray"


def metoc_assessment(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    context = context or {}
    current_level, current_color = risk_level(context.get("current_speed_kts_mean"), 0.5, 1.5)
    wave_level, wave_color = risk_level(context.get("wave_height_m"), 0.5, 1.5)
    wind_level, wind_color = risk_level(context.get("wind_speed_kts_mean"), 10, 20)
    temp_level, temp_color = temp_risk_level(context.get("sea_surface_temp_c_mean"))
    wx_level, wx_color = weather_risk_level(context.get("weather_code"), context.get("precipitation_mm"))

    order = {"green": 0, "yellow": 1, "red": 2, "gray": 1}
    colors = [current_color, wave_color, wind_color, temp_color, wx_color]
    worst = max(colors, key=lambda c: order.get(c, 1))
    posture = {"green": "Favorable", "yellow": "Marginal", "red": "Unfavorable", "gray": "Unknown"}[worst]

    items = [
        ("Current", current_level, current_color, f"{fmt(context.get('current_speed_kts_mean'))} kts from {fmt(context.get('current_direction_deg_mean'), 0)}°", "Route/track current burden."),
        ("Wave / Surf", wave_level, wave_color, f"{fmt(context.get('wave_height_m'))} m, {fmt(context.get('wave_period_s'))} s", "Launch/recovery and surface-support lens."),
        ("Wind", wind_level, wind_color, f"{fmt(context.get('wind_speed_kts_mean'))} kts from {fmt(context.get('wind_direction_deg_mean'), 0)}°", "Launch/recovery and support craft lens."),
        ("SST / Battery", temp_level, temp_color, f"{fmt(context.get('sea_surface_temp_c_mean'), 1)} °C", "Battery derating lens for planning."),
        ("Weather", wx_level, wx_color, context.get("weather_summary") or "N/A", "General operating conditions."),
    ]
    return {"posture": posture, "items": items}


def metoc_html(context: Optional[Dict[str, Any]]) -> str:
    assessment = metoc_assessment(context)
    cards = []
    for name, level, color, value, note in assessment["items"]:
        cards.append(f"""
        <div class='metoc-card {color}'>
          <div class='metoc-title'>{name}</div>
          <div class='metoc-level'>{level}</div>
          <div class='metoc-value'>{value}</div>
          <div class='metoc-note'>{note}</div>
        </div>
        """)
    return f"""
    <div class='uuv-card'>
      <div class='metoc-header'>
        <div>
          <h3>METOC Assessment</h3>
          <div class='small-muted'>FOR PLANNING ONLY. Open-Meteo environmental data are used as mission-planning inputs, not tactical METOC authority.</div>
        </div>
        <div class='posture'>Overall: {assessment['posture']}</div>
      </div>
      <div class='metoc-grid'>{''.join(cards)}</div>
    </div>
    """


def energy_equivalent_rows(kwh: float) -> pd.DataFrame:
    kwh = safe_float(kwh, 0) or 0
    wh = kwh * 1000.0
    joules = wh * 3600.0
    mj = kwh * 3.6
    gj = mj / 1000.0
    toe = kwh / 11630.0  # 1 TOE ≈ 11.63 MWh
    barrel_oil_equiv = gj / 6.12 if gj else 0.0  # rough BOE, planning context
    coal_kg_equiv = mj / 30.0 if mj else 0.0
    rows = [
        ("Mission energy", kwh, "kWh"),
        ("Mission energy", mj, "MJ"),
        ("Mission energy", gj, "GJ"),
        ("Tonne of oil equivalent", toe, "TOE"),
        ("Barrels-of-oil equivalent", barrel_oil_equiv, "BOE"),
        ("Coal-equivalent energy", coal_kg_equiv, "kg coal @ 30 MJ/kg"),
    ]
    return pd.DataFrame(rows, columns=["Energy Lens", "Value", "Unit"])


def build_energy_time_chart(energy_arr: np.ndarray, duration_arr: np.ndarray, usable_battery_per_set: float, battery_sets_available: int, recharge_hr: float) -> Any:
    p50_e = float(np.percentile(energy_arr, 50))
    p10_e = float(np.percentile(energy_arr, 10))
    p90_e = float(np.percentile(energy_arr, 90))
    p50_t = max(float(np.percentile(duration_arr, 50)), 0.1)

    t = np.linspace(0, p50_t, 140)
    x = t / p50_t

    # Mission-phase curve: gentle launch/transit, heavier search/route middle, recovery tail.
    phase_curve = 0.10 * x + 0.75 * (x ** 1.08) + 0.15 * (x ** 2.4)
    phase_curve = phase_curve / max(phase_curve[-1], 1e-9)

    p50_line = p50_e * phase_curve
    p10_line = p10_e * phase_curve
    p90_line = p90_e * phase_curve

    fig, ax1 = plt.subplots(figsize=(9, 4.6))
    ax1.fill_between(t, p10_line, p90_line, alpha=0.25, label="Energy variance band (P10-P90)")
    ax1.plot(t, p50_line, linewidth=2, label="Median cumulative energy")
    ax1.set_xlabel("Mission Time (hours)")
    ax1.set_ylabel("Cumulative Energy (kWh)")
    ax1.set_title("Mission Energy Progress and Battery Lens")
    ax1.grid(True, alpha=0.3)

    # Battery voltage/SOC proxy lens on second axis.
    ax2 = ax1.twinx()
    available = max(usable_battery_per_set * max(1, battery_sets_available), 0.1)
    soc = np.clip(1 - p50_line / available, 0, 1)
    voltage_proxy = 3.0 + 1.2 * np.sqrt(soc)
    ax2.plot(t, voltage_proxy, linestyle="--", linewidth=2, label="Active battery voltage proxy")
    ax2.set_ylabel("Voltage Proxy (V)")

    # Battery-set boundaries and recharge lens.
    if usable_battery_per_set > 0:
        sets_crossed = int(np.floor(p50_e / usable_battery_per_set))
        for k in range(1, min(sets_crossed + 1, battery_sets_available + 1)):
            frac = min((k * usable_battery_per_set) / max(p50_e, 1e-9), 1.0)
            tx = float(np.interp(frac, phase_curve, t))
            ax1.axvline(tx, linestyle=":", alpha=0.45)
            ax1.text(tx, ax1.get_ylim()[1] * 0.93, f"B{k}", rotation=90, va="top", ha="right", fontsize=8)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    fig.tight_layout()
    return fig


def build_distribution_chart(energy_arr: np.ndarray, p80: float, usable_total_kwh: float) -> Any:
    """Planner-facing Monte Carlo energy distribution.

    V2.2.3 fix:
    - Do not force a large minimum x-axis span for small-energy missions.
    - Do not let large battery inventory stretch the x-axis.
    - Show P50/P80/P95 and keep battery inventory as an annotation unless it is
      inside the natural energy range.
    """
    fig, ax = plt.subplots(figsize=(9.5, 4.8), dpi=120)

    energy_arr = np.asarray(energy_arr, dtype=float)
    energy_arr = energy_arr[np.isfinite(energy_arr)]
    if energy_arr.size == 0:
        ax.text(0.5, 0.5, "No Monte Carlo energy results available.", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        fig.tight_layout()
        return fig

    p05 = float(np.percentile(energy_arr, 5))
    p50 = float(np.percentile(energy_arr, 50))
    p95 = float(np.percentile(energy_arr, 95))
    p01 = float(np.percentile(energy_arr, 1))
    p99 = float(np.percentile(energy_arr, 99))

    natural_spread = max(p99 - p01, abs(p50) * 0.02, 0.002)
    pad = natural_spread * 0.75
    xmin = max(0.0, min(p01, p80, p05) - pad)
    xmax = max(p99, p80, p95) + pad

    # If all samples are extremely tight, center on P50 with a small readable span.
    if xmax - xmin < max(abs(p50) * 0.04, 0.004):
        half_span = max(abs(p50) * 0.035, 0.003)
        xmin = max(0.0, p50 - half_span)
        xmax = p50 + half_span

    bins = min(24, max(10, int(np.sqrt(energy_arr.size) * 1.8)))
    ax.hist(energy_arr, bins=bins, alpha=0.82, edgecolor="black", linewidth=0.25)

    ax.axvline(p50, linestyle="-", linewidth=2, label=f"P50: {p50:.3g} kWh")
    ax.axvline(p80, linestyle="--", linewidth=2, label=f"P80: {p80:.3g} kWh")
    ax.axvline(p95, linestyle=":", linewidth=2, label=f"P95: {p95:.3g} kWh")

    # Battery inventory is a feasibility reference, not part of the uncertainty distribution.
    if xmin <= usable_total_kwh <= xmax:
        ax.axvline(usable_total_kwh, linestyle="-.", linewidth=2, label=f"Battery inventory: {usable_total_kwh:.3g} kWh")
    else:
        ax.text(
            0.98,
            0.95,
            f"Battery inventory without recharge: {usable_total_kwh:.2f} kWh",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=9,
            bbox=dict(boxstyle="round,pad=0.35", facecolor="#eef2f7", edgecolor="#94a3b8", alpha=0.95),
        )

    ax.set_xlim(xmin, xmax)
    ax.set_xlabel("Mission energy required, kWh")
    ax.set_ylabel("Monte Carlo count")
    ax.set_title("Mission Energy Uncertainty Distribution")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    return fig



def build_search_overlay_chart(summary: Dict[str, Any], context: Optional[Dict[str, Any]], track_spacing_m: float) -> Any:
    """Readable planning-view overlay of rectangle geometry and generated swath lanes.

    This is intentionally not a tactical chart. It is a report graphic showing how
    the user-selected mission area is converted into a background search pattern
    using the recommended track orientation and user-entered swath/track spacing.
    """
    fig, ax = plt.subplots(figsize=(10.5, 5.6), dpi=120)

    if not context or summary.get("mission_type") not in SEARCH_MISSIONS:
        ax.text(0.5, 0.5, "Search-pattern overlay applies to ISR / Area Search / MCM missions.",
                ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        fig.tight_layout()
        return fig

    width = safe_float(context.get("width_km"), 0) or 0
    height = safe_float(context.get("height_km"), 0) or 0
    if width <= 0 or height <= 0:
        ax.text(0.5, 0.5, "No rectangle geometry available for search overlay.",
                ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        fig.tight_layout()
        return fig

    spacing_km = max((safe_float(track_spacing_m, 200) or 200) / 1000.0, 0.001)
    orientation = summary.get("recommended_track_orientation", "East-West")

    # Boundary and soft mission-area fill.
    ax.fill([0, width, width, 0], [0, 0, height, height], alpha=0.08, label="Selected mission area")
    ax.plot([0, width, width, 0, 0], [0, 0, height, height, 0], linewidth=2.5, label="Mission area boundary")

    lane_count = 0
    if orientation == "North-South":
        xs = np.arange(spacing_km / 2, width, spacing_km)
        lane_count = len(xs)
        for idx, x in enumerate(xs):
            y0, y1 = (0, height) if idx % 2 == 0 else (height, 0)
            ax.plot([x, x], [y0, y1], linewidth=1.4, alpha=0.70)
            if lane_count <= 30 or idx % max(1, lane_count // 25) == 0:
                mid = height * 0.50
                dy = height * 0.10 if y1 > y0 else -height * 0.10
                ax.arrow(x, mid - dy / 2, 0, dy,
                         length_includes_head=True,
                         head_width=max(width * 0.010, 0.018),
                         head_length=max(height * 0.030, 0.025),
                         alpha=0.65)
    else:
        ys = np.arange(spacing_km / 2, height, spacing_km)
        lane_count = len(ys)
        for idx, y in enumerate(ys):
            x0, x1 = (0, width) if idx % 2 == 0 else (width, 0)
            ax.plot([x0, x1], [y, y], linewidth=1.4, alpha=0.70)
            if lane_count <= 30 or idx % max(1, lane_count // 25) == 0:
                mid = width * 0.50
                dx = width * 0.10 if x1 > x0 else -width * 0.10
                ax.arrow(mid - dx / 2, y, dx, 0,
                         length_includes_head=True,
                         head_width=max(height * 0.010, 0.018),
                         head_length=max(width * 0.030, 0.025),
                         alpha=0.65)

    # Current arrow and label.
    cur_speed = safe_float(context.get("current_speed_kts_mean"), 0) or 0
    cur_dir = safe_float(context.get("current_direction_deg_mean"), 0) or 0
    if cur_speed > 0:
        theta = math.radians(90 - cur_dir)
        arrow_len = max(min(width, height) * 0.22, 0.08)
        x0, y0 = width * 0.10, height * 0.12
        ax.arrow(x0, y0, arrow_len * math.cos(theta), arrow_len * math.sin(theta),
                 length_includes_head=True,
                 head_width=max(min(width, height) * 0.025, 0.025),
                 head_length=max(min(width, height) * 0.035, 0.035),
                 linestyle="--", linewidth=1.6)
        ax.text(x0, y0 + max(height * 0.09, 0.05), f"Current {cur_speed:.2f} kts @ {cur_dir:.0f}°", fontsize=9,
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#cbd5e1", alpha=0.85))

    ax.set_title(f"Recommended Search Pattern Overlay: {orientation}", pad=12, fontsize=14)
    ax.set_xlabel("Local east-west distance, km")
    ax.set_ylabel("Local north-south distance, km")

    # Use auto aspect for report readability. Equal aspect made narrow rectangles unreadable in the report pane.
    ax.set_aspect("auto")
    ax.set_xlim(-0.04 * width, width * 1.04)
    ax.set_ylim(-0.06 * height, height * 1.08)
    ax.grid(True, alpha=0.20)

    note = (
        f"Planning overlay only | swath/track spacing: {spacing_km:.3f} km | "
        f"generated lanes shown: {lane_count} | orientation selected by energy/current burden."
    )
    ax.text(0.01, -0.18, note, transform=ax.transAxes, fontsize=8.5, va="top")

    # Small mission geometry tag.
    ax.text(
        0.99, 0.02,
        f"Area: {width * height:.2f} km²\nBox: {width:.2f} × {height:.2f} km",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#eef2f7", edgecolor="#94a3b8", alpha=0.95),
    )

    fig.tight_layout()
    return fig



def _search_plot_inputs(context: Optional[Dict[str, Any]]) -> Tuple[float, float, List[Tuple[float, float]]]:
    context = context or {}
    width = safe_float(context.get("width_km"), 0) or 0
    height = safe_float(context.get("height_km"), 0) or 0
    return width, height, search_polygon_points(context, width, height)


def _draw_map_panel_background(ax) -> None:
    ax.set_facecolor("#eef7fb")
    for spine in ax.spines.values():
        spine.set_color("#6b7280")
        spine.set_linewidth(1.0)
    ax.grid(True, color="white", linewidth=0.9, alpha=0.85)
    ax.text(
        0.99,
        0.99,
        "Simplified map panel",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=8,
        color="#475569",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#ffffff", edgecolor="#cbd5e1", alpha=0.86),
    )


def _set_search_axes_limits(ax, points: List[Tuple[float, float]], equal_aspect: bool = False) -> Tuple[float, float, float, float]:
    min_x, max_x, min_y, max_y = _polygon_bounds(points)
    span_x = max(max_x - min_x, 0.001)
    span_y = max(max_y - min_y, 0.001)
    pad_x = max(span_x * 0.06, 0.04)
    pad_y = max(span_y * 0.08, 0.04)
    ax.set_xlim(min_x - pad_x, max_x + pad_x)
    ax.set_ylim(min_y - pad_y, max_y + pad_y)
    ax.set_aspect("equal" if equal_aspect else "auto", adjustable="box")
    return min_x, max_x, min_y, max_y


def _draw_search_area_and_lanes(
    ax,
    context: Dict[str, Any],
    width: float,
    height: float,
    track_spacing_m: float,
    orientation: str,
    arrow_density: int = 25,
) -> Dict[str, Any]:
    points = search_polygon_points(context, width, height)
    lanes = clipped_search_lanes(context, width, height, track_spacing_m, orientation)
    if len(points) < 3:
        return lanes

    xs = [p[0] for p in points] + [points[0][0]]
    ys = [p[1] for p in points] + [points[0][1]]
    ax.fill(xs, ys, color="#38bdf8", alpha=0.16, label="Selected mission area")
    ax.plot(xs, ys, color="#075985", linewidth=2.3, label="Mission area boundary")

    min_x, max_x, min_y, max_y = _polygon_bounds(points)
    span_x = max(max_x - min_x, 0.001)
    span_y = max(max_y - min_y, 0.001)
    segments = lanes.get("segments", [])
    for idx, (x0, y0, x1, y1) in enumerate(segments):
        ax.plot([x0, x1], [y0, y1], color="#0f766e", linewidth=1.35, alpha=0.78)
        show_arrow = len(segments) <= 30 or idx % max(1, len(segments) // max(1, arrow_density)) == 0
        if not show_arrow:
            continue
        dx = x1 - x0
        dy = y1 - y0
        seg_len = math.hypot(dx, dy)
        if seg_len <= 1e-9:
            continue
        arrow_len = min(seg_len * 0.22, max(span_x, span_y) * 0.12)
        ux = dx / seg_len
        uy = dy / seg_len
        mid_x = (x0 + x1) / 2
        mid_y = (y0 + y1) / 2
        ax.arrow(
            mid_x - ux * arrow_len / 2,
            mid_y - uy * arrow_len / 2,
            ux * arrow_len,
            uy * arrow_len,
            length_includes_head=True,
            head_width=max(min(span_x, span_y) * 0.012, 0.018),
            head_length=max(max(span_x, span_y) * 0.020, 0.025),
            color="#134e4a",
            alpha=0.72,
        )
    return lanes


def _draw_current_arrow(ax, context: Dict[str, Any], bounds: Tuple[float, float, float, float], label: bool = True) -> None:
    cur_speed = safe_float(context.get("current_speed_kts_mean"), 0) or 0
    cur_dir = safe_float(context.get("current_direction_deg_mean"), 0) or 0
    if cur_speed <= 0:
        return
    min_x, max_x, min_y, max_y = bounds
    span_x = max(max_x - min_x, 0.001)
    span_y = max(max_y - min_y, 0.001)
    theta = math.radians(90 - cur_dir)
    arrow_len = max(min(span_x, span_y) * 0.22, 0.08)
    x0 = min_x + span_x * 0.10
    y0 = min_y + span_y * 0.12
    ax.arrow(
        x0,
        y0,
        arrow_len * math.cos(theta),
        arrow_len * math.sin(theta),
        length_includes_head=True,
        head_width=max(min(span_x, span_y) * 0.025, 0.025),
        head_length=max(min(span_x, span_y) * 0.035, 0.035),
        linestyle="--",
        linewidth=1.6,
        color="#7c2d12",
    )
    if label:
        ax.text(
            x0,
            y0 + max(span_y * 0.09, 0.05),
            f"Current {cur_speed:.2f} kts @ {cur_dir:.0f} deg",
            fontsize=9,
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#cbd5e1", alpha=0.88),
        )


def _centroid_local_xy(context: Dict[str, Any], points: List[Tuple[float, float]]) -> Tuple[float, float]:
    centroid = context.get("centroid_local_km")
    if isinstance(centroid, dict):
        x = safe_float(centroid.get("x"))
        y = safe_float(centroid.get("y"))
        if x is not None and y is not None:
            return float(x), float(y)
    return sum(x for x, _ in points) / len(points), sum(y for _, y in points) / len(points)


def _nice_scale_km(extent_km: float) -> float:
    target = max(extent_km / 4.0, 0.001)
    magnitude = 10 ** math.floor(math.log10(target))
    for multiplier in [1, 2, 5, 10]:
        candidate = multiplier * magnitude
        if candidate >= target:
            return candidate
    return 10 * magnitude


def build_search_overlay_chart(summary: Dict[str, Any], context: Optional[Dict[str, Any]], track_spacing_m: float) -> Any:
    """Readable planning-view overlay of search geometry and generated swath lanes."""
    fig, ax = plt.subplots(figsize=(10.5, 5.6), dpi=120)

    if not context or summary.get("mission_type") not in SEARCH_MISSIONS:
        ax.text(0.5, 0.5, "Search-pattern overlay applies to ISR / Area Search / MCM missions.",
                ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        fig.tight_layout()
        return fig

    width, height, points = _search_plot_inputs(context)
    if width <= 0 or height <= 0 or len(points) < 3:
        ax.text(0.5, 0.5, "No search geometry available for search overlay.",
                ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        fig.tight_layout()
        return fig

    spacing_km = max((safe_float(track_spacing_m, 200) or 200) / 1000.0, 0.001)
    orientation = summary.get("recommended_track_orientation", "East-West")
    lanes = _draw_search_area_and_lanes(ax, context, width, height, track_spacing_m, orientation)
    bounds = _set_search_axes_limits(ax, points, equal_aspect=False)
    _draw_current_arrow(ax, context, bounds)

    ax.set_title(f"Recommended Search Pattern Overlay: {orientation}", pad=12, fontsize=14)
    ax.set_xlabel("Local east-west distance, km")
    ax.set_ylabel("Local north-south distance, km")
    ax.grid(True, alpha=0.20)

    note = (
        f"Planning overlay only | swath/track spacing: {spacing_km:.3f} km | "
        f"generated lanes shown: {lanes.get('lane_count', 0)} | orientation selected by energy/current burden."
    )
    ax.text(0.01, -0.18, note, transform=ax.transAxes, fontsize=8.5, va="top")

    shape_label = "Polygon" if context.get("geometry_type") == "polygon" else "Box"
    area_km2 = safe_float(context.get("area_km2"), width * height) or width * height
    ax.text(
        0.99, 0.02,
        f"Area: {area_km2:.2f} sq km\n{shape_label}: {width:.2f} x {height:.2f} km",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#eef2f7", edgecolor="#94a3b8", alpha=0.95),
    )

    fig.tight_layout()
    return fig


def build_mapping_snapshot_chart(summary: Dict[str, Any], context: Optional[Dict[str, Any]], track_spacing_m: float) -> Any:
    fig, ax = plt.subplots(figsize=(6.7, 5.6), dpi=120)

    if not context or summary.get("mission_type") not in SEARCH_MISSIONS:
        ax.text(0.5, 0.5, "Mission map snapshot applies to ISR / Area Search / MCM missions.",
                ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        fig.tight_layout()
        return fig

    width, height, points = _search_plot_inputs(context)
    if width <= 0 or height <= 0 or len(points) < 3:
        ax.text(0.5, 0.5, "No selected search area available for mission map snapshot.",
                ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        fig.tight_layout()
        return fig

    orientation = summary.get("recommended_track_orientation", "East-West")
    _draw_map_panel_background(ax)
    lanes = _draw_search_area_and_lanes(ax, context, width, height, track_spacing_m, orientation, arrow_density=18)
    bounds = _set_search_axes_limits(ax, points, equal_aspect=True)
    min_x, max_x, min_y, max_y = bounds
    span_x = max(max_x - min_x, 0.001)
    span_y = max(max_y - min_y, 0.001)
    extent = max(span_x, span_y)
    _draw_current_arrow(ax, context, _polygon_bounds(points))

    centroid_x, centroid_y = _centroid_local_xy(context, points)
    ax.scatter([centroid_x], [centroid_y], s=34, marker="o", color="#111827", zorder=5)

    north_x = min_x + span_x * 0.10
    north_y = min_y + span_y * 0.70
    north_len = max(span_y * 0.16, extent * 0.08)
    ax.arrow(
        north_x,
        north_y,
        0,
        north_len,
        length_includes_head=True,
        head_width=max(extent * 0.025, 0.025),
        head_length=max(extent * 0.040, 0.035),
        linewidth=1.6,
        color="black",
    )
    ax.text(north_x, north_y + north_len + max(extent * 0.025, 0.02), "N", ha="center", va="bottom", fontsize=10, fontweight="bold")

    scale_len = min(_nice_scale_km(extent), span_x * 0.70)
    scale_x = min_x + span_x * 0.10
    scale_y = min_y + span_y * 0.08
    ax.plot([scale_x, scale_x + scale_len], [scale_y, scale_y], color="black", linewidth=3)
    ax.plot([scale_x, scale_x], [scale_y - span_y * 0.015, scale_y + span_y * 0.015], color="black", linewidth=2)
    ax.plot([scale_x + scale_len, scale_x + scale_len], [scale_y - span_y * 0.015, scale_y + span_y * 0.015], color="black", linewidth=2)
    ax.text(scale_x + scale_len / 2, scale_y + max(span_y * 0.035, 0.03), f"{scale_len:.3g} km", ha="center", va="bottom", fontsize=8.5)

    spacing_m = safe_float(track_spacing_m, 200) or 200
    shape_label = "Polygon" if context.get("geometry_type") == "polygon" else "Rectangle"
    ax.set_title(f"Mission Map Snapshot: {shape_label}", pad=10, fontsize=13)
    ax.set_xlabel("Local east-west distance, km")
    ax.set_ylabel("Local north-south distance, km")
    ax.text(
        0.01,
        -0.18,
        f"Swath/track spacing: {spacing_m:.0f} m | Recommended orientation: {orientation} | Planning snapshot only",
        transform=ax.transAxes,
        fontsize=8,
        va="top",
    )
    ax.text(
        0.99,
        -0.18,
        f"Lanes: {lanes.get('lane_count', 0)}",
        transform=ax.transAxes,
        ha="right",
        fontsize=8,
        va="top",
    )

    fig.tight_layout()
    return fig


def make_results_html(summary: Dict[str, Any]) -> str:
    def yesno(v): return "Yes" if v else "No"
    rows = [
        ("Platform", summary.get("platform")),
        ("Mission type", summary.get("mission_type")),
        ("P80 mission energy", f"{summary.get('p80_energy_kwh', 0):.2f} kWh"),
        ("Mean mission duration", f"{summary.get('mean_duration_hr', 0):.1f} hr"),
        ("Battery nameplate capacity", f"{summary.get('battery_nameplate_kwh', 0):.2f} kWh"),
        ("Usable planning energy per set", f"{summary.get('usable_battery_per_set_kwh', 0):.2f} kWh"),
        ("Battery sets on hand", summary.get("battery_sets_available")),
        ("Battery sets required at P80", summary.get("battery_sets_required_p80")),
        ("Sufficient without recharge", yesno(summary.get("battery_inventory_sufficient_no_recharge"))),
        ("Recharge / swap sequences required", summary.get("recharge_sequences_required")),
        ("Mission sequences", summary.get("mission_sequences")),
    ]
    if summary.get("recommended_track_orientation") != "N/A":
        rows.append(("Recommended search-track orientation", summary.get("recommended_track_orientation")))
    tr = ''.join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return f"""
    <div class='uuv-card'>
      <h2>Mission Energy and Battery Summary</h2>
      <table class='uuv-table'><tbody>{tr}</tbody></table>
      <p class='small-muted'>Energy = Power × Time. Wh = W × hr. kWh = Wh / 1000. J = Wh × 3600. MJ = kWh × 3.6.</p>
    </div>
    """

# ============================================================
# SIMULATION LOGIC
# ============================================================

def platform_average_power_kw(platform: Dict[str, Any]) -> float:
    endurance = max(float(platform["estimated_endurance_hr"]), 0.1)
    return float(platform["battery_kwh"]) / endurance


def current_components(current_speed_kts: float, current_direction_deg: float, heading_deg: float) -> Tuple[float, float]:
    # Assumption: Open-Meteo current direction is treated as direction of flow.
    rel = math.radians((current_direction_deg - heading_deg + 180) % 360 - 180)
    along = current_speed_kts * math.cos(rel)
    cross = current_speed_kts * math.sin(rel)
    return along, cross


def route_leg_time_hr(distance_km: float, vehicle_speed_kts: float, current_speed_kts: float, current_dir_deg: float, heading_deg: float) -> float:
    vehicle_speed_kmh = vehicle_speed_kts * 1.852
    along_kmh = current_components(current_speed_kts, current_dir_deg, heading_deg)[0] * 1.852
    speed_over_ground_kmh = max(vehicle_speed_kmh + along_kmh, vehicle_speed_kmh * 0.25)
    return distance_km / speed_over_ground_kmh if speed_over_ground_kmh > 0 else 9999.0


def search_plan(width_km: float, height_km: float, track_spacing_m: float, track_heading_deg: float, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    orientation = "North-South" if track_heading_deg == 0 else "East-West"
    lanes = clipped_search_lanes(context, width_km, height_km, track_spacing_m, orientation)
    spacing_km = max(track_spacing_m / 1000.0, 0.001)
    turn_distance = lanes["turns"] * spacing_km * 0.5
    total_distance = lanes["track_distance_km"] + turn_distance

    return {
        "orientation": orientation,
        "track_heading_deg": track_heading_deg,
        "track_length_km": lanes["track_distance_km"] / max(lanes["lane_count"], 1),
        "lanes": max(1, lanes["lane_count"]),
        "turns": lanes["turns"],
        "total_distance_km": total_distance,
        "track_distance_km": lanes["track_distance_km"],
        "turn_distance_km": turn_distance,
        "segments": lanes["segments"],
    }


def run_simulation_core(
    platform_name: str,
    mission_type: str,
    mission_area_km2: float,
    width_km: float,
    height_km: float,
    route_distance_km: float,
    route_heading_deg: float,
    additional_transit_km: float,
    track_spacing_m: float,
    return_to_start: bool,
    speed_kts: float,
    battery_sets_available: int,
    recharge_allowed: bool,
    mission_sequences: int,
    current_mean_kts: float,
    current_direction_deg: float,
    temp_mean_c: float,
    context: Optional[Dict[str, Any]] = None,
) -> Tuple[str, pd.DataFrame, pd.DataFrame, Any, Any, Any, Any, Dict[str, Any], str, str]:
    platform = PLATFORMS[platform_name]
    rng = np.random.default_rng()  # hidden from user
    n = MONTE_CARLO_RUNS

    mission_sequences = max(1, safe_int(mission_sequences, 1))
    current_sigma_kts = max(0.10, 0.25 * max(current_mean_kts, 0.1))
    temp_sigma_c = 1.5

    sampled_current = np.clip(rng.normal(current_mean_kts, current_sigma_kts, n), 0, None)
    sampled_temp = rng.normal(temp_mean_c, temp_sigma_c, n)

    avg_power_kw = platform_average_power_kw(platform)
    battery_kwh = float(platform["battery_kwh"])
    usable_fraction = float(platform.get("usable_fraction", 0.85))
    usable_battery_per_set = battery_kwh * usable_fraction
    total_available_kwh = usable_battery_per_set * max(1, battery_sets_available)

    energies = []
    durations = []
    recommended_orientations = []

    search_options = []
    if mission_type in SEARCH_MISSIONS:
        width_km = max(width_km, 0.1)
        height_km = max(height_km, 0.1)
        track_spacing_m = max(track_spacing_m, 1.0)
        north_south = search_plan(width_km, height_km, track_spacing_m, 0, context)
        east_west = search_plan(width_km, height_km, track_spacing_m, 90, context)
        search_options = [north_south, east_west]

    for i in range(n):
        cur = float(sampled_current[i])
        temp = float(sampled_temp[i])

        # Temperature effect remains an engineering assumption. It affects energy required,
        # not the displayed nameplate battery capacity.
        temp_penalty = 0.0
        if temp < 15:
            temp_penalty += min(0.25, (15 - temp) * 0.01)
        elif temp > 32:
            temp_penalty += min(0.15, (temp - 32) * 0.005)

        if mission_type == "Payload Delivery":
            outbound_time = route_leg_time_hr(route_distance_km, speed_kts, cur, current_direction_deg, route_heading_deg)
            return_time = 0.0
            if return_to_start:
                return_time = route_leg_time_hr(
                    route_distance_km,
                    speed_kts,
                    cur,
                    current_direction_deg,
                    (route_heading_deg + 180) % 360,
                )
            transit_time = additional_transit_km / max(speed_kts * 1.852, 0.1)
            duration_single = outbound_time + return_time + transit_time
            cross_current = abs(current_components(cur, current_direction_deg, route_heading_deg)[1])
            cross_penalty = 0.04 * min(cross_current / max(speed_kts, 0.1), 2.0)
            energy_single = avg_power_kw * duration_single * (1 + cross_penalty + temp_penalty)

        else:
            # Background comparison: user sees only area and swath. The model compares candidate orientations.
            option_results = []
            for option in search_options:
                heading = option["track_heading_deg"]
                distance = option["total_distance_km"] + additional_transit_km
                base_duration = distance / max(speed_kts * 1.852, 0.1)

                along, cross = current_components(cur, current_direction_deg, heading)

                # Search missions have reciprocal legs. Along-current does not have full one-way effect.
                along_penalty = 0.35 * abs(along) / max(speed_kts, 0.1)
                cross_penalty = 0.10 * abs(cross) / max(speed_kts, 0.1)
                turn_penalty = option["turns"] * 0.01  # background planning assumption

                duration_candidate = base_duration * (1 + along_penalty + cross_penalty) + turn_penalty
                energy_candidate = avg_power_kw * duration_candidate * (1 + temp_penalty)
                option_results.append((energy_candidate, duration_candidate, option))

            best_energy, best_duration, best_option = min(option_results, key=lambda x: x[0])
            energy_single = best_energy
            duration_single = best_duration
            recommended_orientations.append(best_option["orientation"])

        energies.append(energy_single * mission_sequences)
        durations.append(duration_single * mission_sequences)

    energy_arr = np.array(energies)
    duration_arr = np.array(durations)

    p50 = float(np.percentile(energy_arr, 50))
    p80 = float(np.percentile(energy_arr, 80))
    p95 = float(np.percentile(energy_arr, 95))
    mean_energy = float(np.mean(energy_arr))
    mean_duration = float(np.mean(duration_arr))

    inventory_sufficiency_probability = float(np.mean(energy_arr <= total_available_kwh) * 100.0)
    battery_sets_required_p80 = max(1, math.ceil(p80 / max(usable_battery_per_set, 0.001)))
    battery_shortfall = max(0, battery_sets_required_p80 - max(1, battery_sets_available))
    battery_inventory_sufficient = battery_shortfall == 0
    recharge_sequences_required = battery_shortfall if recharge_allowed else 0
    recharge_downtime_hr = recharge_sequences_required * float(platform.get("recharge_hr", 0))
    elapsed_with_recharge_hr = mean_duration + recharge_downtime_hr

    orientation_summary = "N/A"
    if mission_type in SEARCH_MISSIONS and recommended_orientations:
        orientation_summary = max(set(recommended_orientations), key=recommended_orientations.count)

    summary = {
        "platform": platform_name,
        "mission_type": mission_type,
        "mean_energy_kwh": mean_energy,
        "p50_energy_kwh": p50,
        "p80_energy_kwh": p80,
        "p95_energy_kwh": p95,
        "mean_duration_hr": mean_duration,
        "elapsed_with_recharge_hr": elapsed_with_recharge_hr,
        "inventory_sufficiency_probability_pct": inventory_sufficiency_probability,
        "battery_inventory_sufficient_no_recharge": battery_inventory_sufficient,
        "battery_sets_required_p80": battery_sets_required_p80,
        "battery_sets_available": max(1, battery_sets_available),
        "battery_shortfall_p80": battery_shortfall,
        "recharge_sequences_required": recharge_sequences_required,
        "recharge_allowed": bool(recharge_allowed),
        "recharge_downtime_hr": recharge_downtime_hr,
        "recommended_track_orientation": orientation_summary,
        "monte_carlo_runs": MONTE_CARLO_RUNS,
        "mission_sequences": mission_sequences,
        "battery_nameplate_kwh": battery_kwh,
        "usable_fraction": usable_fraction,
        "usable_battery_per_set_kwh": usable_battery_per_set,
        "total_available_kwh": total_available_kwh,
        "source_note": platform["source_note"],
        "usable_basis": platform.get("usable_basis", ""),
        "track_spacing_m": track_spacing_m,
        "search_width_km": width_km,
        "search_height_km": height_km,
    }

    result_rows = [
        ("Platform", platform_name, ""),
        ("Mission type", mission_type, ""),
        ("Mission sequences", mission_sequences, "runs"),
        ("Mean energy required", mean_energy, "kWh"),
        ("P50 energy required", p50, "kWh"),
        ("P80 energy required", p80, "kWh"),
        ("P95 energy required", p95, "kWh"),
        ("Mean mission duration", mean_duration, "hr"),
        ("Battery nameplate capacity", battery_kwh, "kWh"),
        ("Usable planning energy per set", usable_battery_per_set, "kWh"),
        ("Usable battery basis", platform.get("usable_basis", ""), ""),
        ("Battery sets on hand", battery_sets_available, "sets"),
        ("Battery inventory without recharge", "Sufficient" if battery_inventory_sufficient else "Not sufficient", ""),
        ("Battery inventory sufficiency across Monte Carlo runs", inventory_sufficiency_probability, "%"),
        ("Battery sets required at P80", battery_sets_required_p80, "sets"),
        ("Battery shortfall at P80", battery_shortfall, "sets"),
        ("Recharge / swap sequences required", recharge_sequences_required, "sequences"),
        ("Recharge downtime", recharge_downtime_hr, "hr"),
        ("Elapsed time incl. recharge", elapsed_with_recharge_hr, "hr"),
        ("Recommended track orientation", orientation_summary, ""),
        ("Monte Carlo runs", MONTE_CARLO_RUNS, "fixed"),
    ]
    results_df = pd.DataFrame(result_rows, columns=["Output", "Value", "Unit"])
    equivalents_df = energy_equivalent_rows(p80)

    fig_energy_time = build_energy_time_chart(
        energy_arr=energy_arr,
        duration_arr=duration_arr,
        usable_battery_per_set=usable_battery_per_set,
        battery_sets_available=max(1, battery_sets_available),
        recharge_hr=float(platform.get("recharge_hr", 0)),
    )
    fig_dist = build_distribution_chart(energy_arr, p80, total_available_kwh)
    fig_snapshot = build_mapping_snapshot_chart(summary, context, track_spacing_m)
    fig_overlay = build_search_overlay_chart(summary, context, track_spacing_m)

    status = (
        f"Simulation complete. P80 energy: {p80:.2f} kWh. "
        f"Battery sets required at P80: {battery_sets_required_p80}. "
    )
    if battery_inventory_sufficient:
        status += "Battery inventory is sufficient without recharge."
    else:
        if recharge_allowed:
            status += f"Battery inventory shortfall: {battery_shortfall} set(s); recharge/swap sequence required."
        else:
            status += f"Battery inventory shortfall: {battery_shortfall} set(s); recharge is not enabled."
    if mission_type in SEARCH_MISSIONS:
        status += f" Recommended track orientation: {orientation_summary}."

    results_html = make_results_html(summary)
    metoc = metoc_html(context)

    return status, results_df, equivalents_df, fig_energy_time, fig_dist, fig_snapshot, fig_overlay, summary, results_html, metoc


# ============================================================
# UI CALLBACKS
# ============================================================

def mission_visibility(mission_type: str):
    is_payload = mission_type == "Payload Delivery"
    return (
        gr.update(visible=not is_payload),  # search geometry note
        gr.update(visible=is_payload),      # payload geometry note
        gr.update(visible=not is_payload),  # search manual group
        gr.update(visible=is_payload),      # payload manual group
    )


def refresh_map(region: str) -> str:
    return build_leaflet_iframe(region)


def build_mission_and_prefill(mission_type: str, geometry_json_text: str):
    context, msg = parse_geometry_json(geometry_json_text)
    if not context:
        empty_df = pd.DataFrame(
            [["Mission build failed", msg, ""]],
            columns=["Environmental / Geometry Item", "Value", "Unit"],
        )
        empty_html = env_table_to_html(empty_df, "Mission Build Status")
        return (
            context,
            f"Mission build failed: {msg}",
            empty_df,
            empty_html,
            geometry_json_text,
            mission_type,
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(visible=True),
            gr.update(visible=False),
        )

    # Enforce mission type/geometry compatibility.
    geom_type = context.get("geometry_type")
    if mission_type == "Payload Delivery" and geom_type != "line":
        df = pd.DataFrame([["Mission build failed", "Payload Delivery requires a line route.", ""]], columns=["Environmental / Geometry Item", "Value", "Unit"])
        return (
            {},
            "Payload Delivery requires a line route. Draw a line from drop point to target site.",
            df,
            env_table_to_html(df, "Mission Build Status"),
            geometry_json_text,
            mission_type,
            gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(), gr.update(visible=False), gr.update(visible=True),
        )

    if mission_type in SEARCH_MISSIONS and geom_type not in {"rectangle", "polygon"}:
        df = pd.DataFrame([["Mission build failed", f"{mission_type} requires a rectangle or polygon search area.", ""]], columns=["Environmental / Geometry Item", "Value", "Unit"])
        return (
            {},
            f"{mission_type} requires a rectangle or polygon search area. Draw a search area around the operating area.",
            df,
            env_table_to_html(df, "Mission Build Status"),
            geometry_json_text,
            mission_type,
            gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(), gr.update(visible=True), gr.update(visible=False),
        )

    context["mission_type"] = mission_type
    context, status, env_df = fetch_environment_for_context(context)
    env_html = env_table_to_html(env_df)

    # Defaults to push into UUV profile.
    mission_area = context.get("area_km2") or 10
    width = context.get("width_km") or 3
    height = context.get("height_km") or 3
    route_distance = context.get("route_distance_km") or 10
    route_heading = context.get("route_heading_deg") or 0
    current_speed = context.get("current_speed_kts_mean") or 0.5
    current_dir = context.get("current_direction_deg_mean") or 0
    temp = context.get("sea_surface_temp_c_mean") or 25

    return (
        context,
        status,
        env_df,
        env_html,
        geometry_json_text,
        mission_type,
        mission_area,
        width,
        height,
        route_distance,
        route_heading,
        current_speed,
        current_dir,
        temp,
        gr.update(visible=mission_type in SEARCH_MISSIONS),
        gr.update(visible=mission_type == "Payload Delivery"),
    )


def context_markdown(context: Dict[str, Any]) -> str:
    if not context:
        return "No mission context loaded. The simulator can still run with manual inputs."

    if context.get("mission_type") in SEARCH_MISSIONS:
        shape_label = "Polygon" if context.get("geometry_type") == "polygon" else "Rectangle"
        geom = (
            f"**Mission loaded:** {context.get('mission_type')}  \n"
            f"**Geometry:** {shape_label} search area  \n"
            f"**Area:** {fmt(context.get('area_km2'))} km²  \n"
            f"**Dimensions:** {fmt(context.get('width_km'))} km × {fmt(context.get('height_km'))} km  \n"
            f"**Centroid:** {fmt(context.get('centroid_lat'), 5)}, {fmt(context.get('centroid_lon'), 5)}"
        )
    else:
        geom = (
            f"**Mission loaded:** Payload Delivery  \n"
            f"**Geometry:** Line route  \n"
            f"**Route distance:** {fmt(context.get('route_distance_km'))} km  \n"
            f"**Route heading:** {fmt(context.get('route_heading_deg'), 1)}°  \n"
            f"**Centroid:** {fmt(context.get('centroid_lat'), 5)}, {fmt(context.get('centroid_lon'), 5)}"
        )

    env = (
        f"\n\n**Open-Meteo baseline:** current {fmt(context.get('current_speed_kts_mean'))} kts "
        f"from {fmt(context.get('current_direction_deg_mean'), 1)}°, "
        f"SST {fmt(context.get('sea_surface_temp_c_mean'), 1)} °C, "
        f"wind {fmt(context.get('wind_speed_kts_mean'))} kts.  \n"
        f"**Weather:** {context.get('weather_summary') or 'N/A'}"
    )
    return geom + env


def run_from_ui(
    platform_name: str,
    mission_type: str,
    manual_area_km2: float,
    width_km: float,
    height_km: float,
    route_distance_km: float,
    route_heading_deg: float,
    additional_transit_km: float,
    track_spacing_m: float,
    return_to_start: bool,
    speed_kts: float,
    battery_sets_available: int,
    recharge_allowed: bool,
    mission_sequences: int,
    current_mean_kts: float,
    current_direction_deg: float,
    temp_mean_c: float,
    context: Dict[str, Any],
):
    # Mission context is automatically used if present. Manual fields remain editable.
    if context:
        mission_type = context.get("mission_type") or mission_type

    status, df, equiv_df, fig_time, fig_dist, fig_snapshot, fig_overlay, summary, results_html, metoc = run_simulation_core(
        platform_name=platform_name,
        mission_type=mission_type,
        mission_area_km2=safe_float(manual_area_km2, 10) or 10,
        width_km=safe_float(width_km, 3) or 3,
        height_km=safe_float(height_km, 3) or 3,
        route_distance_km=safe_float(route_distance_km, 10) or 10,
        route_heading_deg=safe_float(route_heading_deg, 0) or 0,
        additional_transit_km=safe_float(additional_transit_km, 0) or 0,
        track_spacing_m=safe_float(track_spacing_m, 200) or 200,
        return_to_start=bool(return_to_start),
        speed_kts=safe_float(speed_kts, PLATFORMS[platform_name]["nominal_speed_kts"]) or PLATFORMS[platform_name]["nominal_speed_kts"],
        battery_sets_available=max(1, safe_int(battery_sets_available, 1)),
        recharge_allowed=bool(recharge_allowed),
        mission_sequences=max(1, safe_int(mission_sequences, 1)),
        current_mean_kts=safe_float(current_mean_kts, 0.5) or 0.5,
        current_direction_deg=safe_float(current_direction_deg, 0) or 0,
        temp_mean_c=safe_float(temp_mean_c, 25) or 25,
        context=context,
    )

    return status, df, equiv_df, fig_time, fig_dist, fig_snapshot, fig_overlay, summary, results_html, metoc


def platform_defaults(platform_name: str):
    p = PLATFORMS[platform_name]
    return (
        p["nominal_speed_kts"],
        f"Battery nameplate: {p['battery_kwh']} kWh | Usable planning fraction: {p.get('usable_fraction', 0.85)*100:.0f}% | Est. endurance: {p['estimated_endurance_hr']} hr | Recharge: {p['recharge_hr']} hr\n\n{p['source_note']}\n{p.get('usable_basis','')}",
    )


# ============================================================
# GRADIO APP
# ============================================================


CUSTOM_CSS = """
.uuv-card {
  border: 1px solid #374151;
  border-radius: 12px;
  padding: 14px 16px;
  background: #111827;
  margin: 10px 0;
}
.full-width-card { width: 100%; }
.uuv-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.uuv-table th, .uuv-table td {
  border-bottom: 1px solid #374151;
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
}
.uuv-table th {
  background: #1f2937;
}
.uuv-table .value {
  font-weight: 700;
}
.uuv-attribution, .small-muted {
  color: #9ca3af;
  font-size: 12px;
  margin-top: 8px;
}
.metoc-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.posture {
  font-weight: 800;
  font-size: 18px;
  padding: 8px 12px;
  border-radius: 10px;
  background: #1f2937;
}
.metoc-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(140px, 1fr));
  gap: 10px;
  margin-top: 12px;
}
.metoc-card {
  border-radius: 10px;
  padding: 10px;
  min-height: 120px;
  border: 2px solid #4b5563;
}
.metoc-card.green { background: #064e3b; border-color: #10b981; }
.metoc-card.yellow { background: rgba(234, 179, 8, 0.16); border-color: #eab308; }
.metoc-card.red { background: #7f1d1d; border-color: #ef4444; }
.metoc-card.gray { background: #374151; border-color: #9ca3af; }
.metoc-title {
  font-weight: 800;
  font-size: 15px;
}
.metoc-level {
  font-weight: 900;
  font-size: 17px;
  margin: 6px 0;
}
.metoc-value {
  font-size: 14px;
}
.metoc-note {
  font-size: 12px;
  color: #e5e7eb;
  margin-top: 6px;
}

/* V2.2.3 report cleanup */
.gradio-container .plot-container, .gradio-container .js-plotly-plot {
  max-width: 100%;
}
"""

CUSTOM_JS = """
function() {
  function setGeometryBox(text) {
    const box = document.querySelector('#geometry_json_box textarea');
    if (!box) return;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    setter.call(box, text);
    box.dispatchEvent(new Event('input', { bubbles: true }));
    box.dispatchEvent(new Event('change', { bubbles: true }));
  }

  window.addEventListener('message', function(event) {
    if (!event.data || event.data.type !== 'uuv_geometry') return;
    setGeometryBox(JSON.stringify(event.data.payload || {}, null, 2));
  });
}
"""

BUILD_MISSION_JS = """
(missionType, geometryText) => {
  let text = geometryText || "";
  if (!text.trim()) {
    try {
      const iframe = document.querySelector('#uuv_map_iframe');
      const raw = iframe && iframe.contentWindow && iframe.contentWindow.document.getElementById('raw_output');
      const output = iframe && iframe.contentWindow && iframe.contentWindow.document.getElementById('output');
      if (raw && (raw.innerText || raw.textContent || "").trim()) {
        text = raw.innerText || raw.textContent || "";
      } else if (output) {
        text = output.innerText || output.textContent || "";
      }
    } catch (e) {
      console.log("Could not read map iframe geometry output", e);
    }
  }
  return [missionType, text];
}
"""

with gr.Blocks(title=APP_NAME, js=CUSTOM_JS, css=CUSTOM_CSS) as demo:
    mission_context_state = gr.State({})
    sim_results_state = gr.State({})

    gr.Markdown(
        """
# UUV Mission Planning and Energy Simulator

Build a mission first, then run a single-UUV energy estimate. The simulator can also run by itself if no map mission is built.
"""
    )

    with gr.Tab("1. Mission Builder"):
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### Mission Setup")
                mission_type_builder = gr.Dropdown(
                    MISSION_TYPES,
                    value="ISR",
                    label="Mission type",
                )
                region_select = gr.Dropdown(
                    list(REGION_PRESETS.keys()),
                    value="Guam",
                    label="Operating region",
                )
                refresh_map_btn = gr.Button("Refresh Map Region")

                search_note = gr.Markdown(
                    "Draw a **rectangle or polygon** for ISR or Area Search / MCM. The app will calculate search-track orientation in the background.",
                    visible=True,
                )
                payload_note = gr.Markdown(
                    "Draw a **line** from drop point / launch point to target site.",
                    visible=False,
                )

                geometry_json = gr.Textbox(
                    label="Map geometry",
                    lines=1,
                    visible=False,
                    elem_id="geometry_json_box",
                    placeholder="Hidden geometry handoff from the map.",
                )

                build_fetch_btn = gr.Button(
                    "Build Mission and Load Environment",
                    variant="primary",
                )

                mission_status = gr.Textbox(
                    label="Mission Builder Status",
                    lines=3,
                    interactive=False,
                )

            with gr.Column(scale=2):
                map_html = gr.HTML(value=build_leaflet_iframe("Guam"), label="Mission Map")

        mission_env_html = gr.HTML(
            value=env_table_to_html(pd.DataFrame([["Draw a mission area or route, then click Build Mission and Load Environment.", "", ""]], columns=["Environmental / Geometry Item", "Value", "Unit"]), "Mission Geometry and Environmental Data"),
            label="Mission Geometry and Environmental Data",
        )
        env_table = gr.Dataframe(
            value=pd.DataFrame([["Draw a mission area or route, then click Build Mission and Load Environment.", "", ""]], columns=["Environmental / Geometry Item", "Value", "Unit"]),
            label="Mission Geometry and Environmental Data Raw Table",
            interactive=False,
            wrap=True,
            visible=False,
        )

    with gr.Tab("2. Single-UUV Simulator"):
        mission_loaded_md = gr.Markdown(
            "No mission context loaded. You can still run the simulator with manual inputs."
        )

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### UUV Profile")
                platform_select = gr.Dropdown(
                    list(PLATFORMS.keys()),
                    value="REMUS 300 - 4.5 kWh",
                    label="UUV platform",
                )
                platform_info = gr.Textbox(
                    label="Platform baseline",
                    lines=5,
                    interactive=False,
                    value="Battery nameplate: 4.5 kWh | Usable planning fraction: 88% | Est. endurance: 30 hr | Recharge: 18 hr\n\nManufacturer-published REMUS 300M datasheet\nPlanning assumption: 88% usable Li-ion energy after reserve / battery-health allowance.",
                )

                mission_type_sim = gr.Dropdown(
                    MISSION_TYPES,
                    value="ISR",
                    label="Mission type",
                )

                speed_kts = gr.Number(label="Vehicle speed through water, kts", value=3.5)
                battery_sets_available = gr.Number(label="Battery sets on hand", value=1, precision=0)
                recharge_allowed = gr.Checkbox(label="Recharge / battery swap allowed if required", value=True)
                mission_sequences = gr.Number(label="Mission sequences / repeated route runs", value=1, precision=0)

                gr.Markdown("### Environment")
                current_mean = gr.Number(label="Current speed mean, kts", value=0.5)
                current_dir = gr.Number(label="Current direction mean, deg", value=0)
                temp_mean = gr.Number(label="Sea surface temperature mean, °C", value=25)

            with gr.Column(scale=1):
                search_group = gr.Group(visible=True)
                with search_group:
                    gr.Markdown("### Search Mission Inputs")
                    manual_area_km2 = gr.Number(label="Mission search area, km²", value=10)
                    # Hidden but used by geometry. Not shown to user as an input.
                    width_km = gr.Number(label="Search area width, km", value=3, visible=False)
                    height_km = gr.Number(label="Search area height, km", value=3, visible=False)
                    track_spacing_m = gr.Number(label="Swath lane width / track spacing, meters", value=200)
                    gr.Markdown("The app calculates lanes, track length, turn burden, and recommended orientation in the background.")

                payload_group = gr.Group(visible=False)
                with payload_group:
                    gr.Markdown("### Payload Delivery Inputs")
                    route_distance_km = gr.Number(label="Route distance, km", value=10)
                    route_heading_deg = gr.Number(label="Route heading, deg", value=0)
                    return_to_start = gr.Checkbox(label="Vehicle returns to start after delivery", value=True)

                additional_transit_km = gr.Number(label="Additional transit distance, km", value=0)

                run_btn = gr.Button("Run UUV Energy Simulation", variant="primary")
                run_status = gr.Textbox(label="Run Status", lines=4, interactive=False)

    with gr.Tab("3. Results"):
        results_html = gr.HTML("<div class='uuv-card'>Run a mission simulation to populate results.</div>")
        metoc_results_html = gr.HTML("")
        results_table = gr.Dataframe(label="Energy and Battery Outputs", interactive=False, wrap=True)
        equivalents_table = gr.Dataframe(label="Energy Equivalency Lens", interactive=False, wrap=True)
        energy_time_plot = gr.Plot(label="Mission Energy Progress and Battery Lens")
        results_plot = gr.Plot(label="Mission Energy Uncertainty Distribution")
        with gr.Row():
            mission_map_snapshot_plot = gr.Plot(label="Mission Map Snapshot")
            search_overlay_plot = gr.Plot(label="Recommended Search Pattern Overlay")

    # UI events
    refresh_map_btn.click(refresh_map, inputs=[region_select], outputs=[map_html])

    mission_type_builder.change(
        mission_visibility,
        inputs=[mission_type_builder],
        outputs=[search_note, payload_note, search_group, payload_group],
    )

    mission_type_sim.change(
        mission_visibility,
        inputs=[mission_type_sim],
        outputs=[search_note, payload_note, search_group, payload_group],
    )

    platform_select.change(
        platform_defaults,
        inputs=[platform_select],
        outputs=[speed_kts, platform_info],
    )

    build_fetch_btn.click(
        build_mission_and_prefill,
        inputs=[mission_type_builder, geometry_json],
        js=BUILD_MISSION_JS,
        outputs=[
            mission_context_state,
            mission_status,
            env_table,
            mission_env_html,
            geometry_json,
            mission_type_sim,
            manual_area_km2,
            width_km,
            height_km,
            route_distance_km,
            route_heading_deg,
            current_mean,
            current_dir,
            temp_mean,
            search_group,
            payload_group,
        ],
    ).then(
        context_markdown,
        inputs=[mission_context_state],
        outputs=[mission_loaded_md],
    )

    run_btn.click(
        run_from_ui,
        inputs=[
            platform_select,
            mission_type_sim,
            manual_area_km2,
            width_km,
            height_km,
            route_distance_km,
            route_heading_deg,
            additional_transit_km,
            track_spacing_m,
            return_to_start,
            speed_kts,
            battery_sets_available,
            recharge_allowed,
            mission_sequences,
            current_mean,
            current_dir,
            temp_mean,
            mission_context_state,
        ],
        outputs=[
            run_status,
            results_table,
            equivalents_table,
            energy_time_plot,
            results_plot,
            mission_map_snapshot_plot,
            search_overlay_plot,
            sim_results_state,
            results_html,
            metoc_results_html,
        ],
    )


if __name__ == "__main__":
    demo.launch(share=True, debug=True)
