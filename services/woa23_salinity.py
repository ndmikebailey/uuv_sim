"""NOAA WOA23 salinity climatology provider."""

from __future__ import annotations

import csv
import gzip
import io
import math
from functools import lru_cache
from typing import Iterable

import requests

from utils.constants import REQUEST_TIMEOUT, USER_AGENT


STANDARD_SEAWATER = {
    "salinity_psu": 35.0,
    "density_kg_m3": 1025.0,
    "salinity_source": "Standard seawater assumption",
}
WOA23_SOURCE = "NOAA WOA23 climatology"
WOA23_BASE_URL = "https://www.ncei.noaa.gov/data/oceans/woa/WOA23/DATA/salinity/csv/decav/1.00"
MAX_NEIGHBOR_CELLS = 3


def _standard_seawater() -> dict[str, float | str]:
    return dict(STANDARD_SEAWATER)


def _month_code(month: int | None) -> str:
    if month is None:
        return "00"
    try:
        value = int(month)
    except (TypeError, ValueError):
        return "00"
    return f"{value:02d}" if 1 <= value <= 12 else "00"


def _as_float(value: object) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _valid_salinity(value: object) -> float | None:
    salinity = _as_float(value)
    if salinity is None or not (0.0 < salinity < 45.0):
        return None
    return salinity


def _density_from_salinity(salinity_psu: float) -> float:
    return 1025.0 + ((salinity_psu - 35.0) * 0.78)


def _parse_depth_index(header: str, depth_m: float) -> int:
    marker = "DEPTHS (M):"
    depths_text = header.split(marker, 1)[1] if marker in header else "0"
    depths: list[float] = []
    for item in depths_text.split(","):
        numeric = _as_float(item.strip())
        if numeric is not None:
            depths.append(numeric)
    if not depths:
        return 2
    nearest_offset = min(range(len(depths)), key=lambda index: abs(depths[index] - max(depth_m, 0.0)))
    return 2 + nearest_offset


@lru_cache(maxsize=13)
def _fetch_woa_rows(month_code: str) -> tuple[tuple[float, float, float], ...]:
    """Fetch WOA23 1-degree surface salinity rows for a month or annual code."""
    url = f"{WOA23_BASE_URL}/woa23_decav_s{month_code}mn01.csv.gz"
    response = requests.get(url, timeout=min(REQUEST_TIMEOUT, 8), headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    rows: list[tuple[float, float, float]] = []
    with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as gz_file:
        text = io.TextIOWrapper(gz_file, encoding="utf-8", newline="")
        depth_index = 2
        for raw_line in text:
            if raw_line.startswith("#COMMA SEPARATED"):
                depth_index = _parse_depth_index(raw_line, 0.0)
                continue
            if raw_line.startswith("#") or not raw_line.strip():
                continue
            parsed = next(csv.reader([raw_line]))
            if len(parsed) <= depth_index:
                continue
            lat = _as_float(parsed[0])
            lon = _as_float(parsed[1])
            salinity = _valid_salinity(parsed[depth_index])
            if lat is not None and lon is not None and salinity is not None:
                rows.append((lat, lon, salinity))
    return tuple(rows)


def _grid_center(value: float, *, longitude: bool = False) -> float:
    if longitude:
        wrapped = ((value + 180.0) % 360.0) - 180.0
        return math.floor(wrapped) + 0.5
    return math.floor(max(min(value, 89.5), -89.5)) + 0.5


def _lon_delta(a: float, b: float) -> float:
    return abs(((a - b + 180.0) % 360.0) - 180.0)


def _candidate_centers(lat: float, lon: float, radius: int = MAX_NEIGHBOR_CELLS) -> Iterable[tuple[float, float]]:
    center_lat = _grid_center(lat)
    center_lon = _grid_center(lon, longitude=True)
    candidates: list[tuple[float, float, float]] = []
    for d_lat in range(-radius, radius + 1):
        for d_lon in range(-radius, radius + 1):
            cand_lat = center_lat + d_lat
            if cand_lat < -89.5 or cand_lat > 89.5:
                continue
            cand_lon = ((center_lon + d_lon + 180.0) % 360.0) - 180.0
            distance = math.hypot(cand_lat - lat, _lon_delta(cand_lon, lon) * max(math.cos(math.radians(lat)), 0.01))
            candidates.append((distance, cand_lat, cand_lon))
    for _, cand_lat, cand_lon in sorted(candidates, key=lambda item: item[0]):
        yield cand_lat, cand_lon


def _nearest_valid_salinity(lat: float, lon: float, rows: Iterable[tuple[float, float, float]]) -> float | None:
    row_map = {(round(row_lat, 3), round(row_lon, 3)): salinity for row_lat, row_lon, salinity in rows}
    for cand_lat, cand_lon in _candidate_centers(lat, lon):
        salinity = row_map.get((round(cand_lat, 3), round(cand_lon, 3)))
        if salinity is not None:
            return salinity
    return None


def get_woa23_salinity(
    lat: float | None,
    lon: float | None,
    month: int | None = None,
    depth_m: float = 0.0,
) -> dict:
    """Return salinity_psu, density_kg_m3, and salinity_source."""
    del depth_m
    if lat is None or lon is None:
        return _standard_seawater()
    try:
        lat_value = float(lat)
        lon_value = float(lon)
    except (TypeError, ValueError):
        return _standard_seawater()
    if not math.isfinite(lat_value) or not math.isfinite(lon_value):
        return _standard_seawater()
    try:
        salinity = _nearest_valid_salinity(lat_value, lon_value, _fetch_woa_rows(_month_code(month)))
        if salinity is None:
            return _standard_seawater()
        return {
            "salinity_psu": salinity,
            "density_kg_m3": _density_from_salinity(salinity),
            "salinity_source": WOA23_SOURCE,
        }
    except Exception:
        return _standard_seawater()
