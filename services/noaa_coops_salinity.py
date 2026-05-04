"""NOAA CO-OPS station salinity provider."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any

import requests

from models.environment_model import EnvironmentData
from utils.constants import REQUEST_TIMEOUT, USER_AGENT


NOAA_COOPS_DATAGETTER_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
NOAA_COOPS_STATIONS_URL = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json"
MAX_STATION_DISTANCE_NMI = 50.0


def _coops_day(when_utc: datetime | None) -> str:
    """Return the compact CO-OPS day string."""
    when = when_utc or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).strftime("%Y%m%d")


def _as_float(value: Any) -> float | None:
    """Return a float when possible."""
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _distance_nmi(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Return great-circle distance in nautical miles."""
    radius_nmi = 3440.065
    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    d_phi = math.radians(lat_b - lat_a)
    d_lam = math.radians(lon_b - lon_a)
    a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lam / 2.0) ** 2
    return radius_nmi * 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(1.0 - a, 0.0)))


@dataclass
class NoaaCoopsSalinityProvider:
    """Fetch station salinity from NOAA CO-OPS when a station is available."""

    url: str = NOAA_COOPS_DATAGETTER_URL
    stations_url: str = NOAA_COOPS_STATIONS_URL
    timeout: int = REQUEST_TIMEOUT
    user_agent: str = USER_AGENT
    max_station_distance_nmi: float = MAX_STATION_DISTANCE_NMI

    def find_station(self, lat: float, lon: float) -> str | None:
        """Return a nearby station id, if station discovery has been configured."""
        try:
            response = requests.get(
                self.stations_url,
                params={"type": "physocean"},
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent},
            )
            response.raise_for_status()
            stations = response.json().get("stations", [])
        except Exception:
            return None
        candidates: list[tuple[float, str]] = []
        for station in stations:
            station_lat = _as_float(station.get("lat") if isinstance(station, dict) else None)
            station_lon = _as_float(station.get("lng") if isinstance(station, dict) else None)
            station_id = str(station.get("id") or "") if isinstance(station, dict) else ""
            if station_lat is None or station_lon is None or not station_id:
                continue
            distance = _distance_nmi(float(lat), float(lon), station_lat, station_lon)
            if distance <= self.max_station_distance_nmi:
                candidates.append((distance, station_id))
        if not candidates:
            return None
        return min(candidates, key=lambda item: item[0])[1]

    def fetch(
        self,
        lat: float,
        lon: float,
        when_utc: datetime | None = None,
        station_id: str | None = None,
    ) -> EnvironmentData:
        """Return salinity for a NOAA station, or a structured unavailable result."""
        station = station_id or self.find_station(lat, lon)
        query_day = _coops_day(when_utc)
        query_params: dict[str, object] = {
            "provider": "noaa_coops",
            "latitude": lat,
            "longitude": lon,
            "station": station or "",
            "query_day": query_day,
            "product": "salinity",
        }
        if not station:
            return EnvironmentData(
                salinity_source="noaa_coops_unavailable",
                salinity_error="No NOAA CO-OPS salinity station id was available.",
                salinity_query_params=query_params,
            )

        params = {
            "begin_date": query_day,
            "end_date": query_day,
            "station": station,
            "product": "salinity",
            "datum": "MLLW",
            "time_zone": "gmt",
            "units": "metric",
            "format": "json",
            "application": "uuv_sustainment_sim",
        }
        try:
            response = requests.get(self.url, params=params, timeout=self.timeout, headers={"User-Agent": self.user_agent})
            response.raise_for_status()
            payload = response.json()
            values = [
                salinity
                for item in payload.get("data", [])
                if (salinity := _as_float(item.get("s") if isinstance(item, dict) else None)) is not None
                or (salinity := _as_float(item.get("v") if isinstance(item, dict) else None)) is not None
            ]
            if not values:
                return EnvironmentData(
                    salinity_source="noaa_coops_unavailable",
                    salinity_error="NOAA CO-OPS salinity product returned no usable values.",
                    raw_salinity_api_json=payload,
                    salinity_query_params=query_params,
                )
            return EnvironmentData(
                sea_surface_salinity_psu=sum(values) / len(values),
                salinity_source="NOAA CO-OPS station observation",
                raw_salinity_api_json=payload,
                salinity_query_params=query_params,
            )
        except Exception as exc:
            return EnvironmentData(
                salinity_source="noaa_coops_unavailable",
                salinity_error=str(exc),
                salinity_query_params=query_params,
            )
