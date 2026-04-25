"""Open-Meteo weather API client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from models.environment_model import EnvironmentData
from utils.constants import OPEN_METEO_WEATHER_URL, REQUEST_TIMEOUT, USER_AGENT


def weather_code_to_text(code: float | None) -> str:
    """Return a short Open-Meteo weather-code label."""
    mapping = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    if code is None:
        return "Unknown"
    return mapping.get(int(code), f"Weather code {int(code)}")


@dataclass
class OpenMeteoWeatherClient:
    """Structured client for Open-Meteo forecast weather."""

    url: str = OPEN_METEO_WEATHER_URL
    timeout: int = REQUEST_TIMEOUT
    user_agent: str = USER_AGENT

    def fetch(self, lat: float, lon: float) -> EnvironmentData:
        """Fetch current weather and return an ``EnvironmentData`` object."""
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": ",".join(
                [
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
                ]
            ),
            "wind_speed_unit": "kn",
            "timeformat": "iso8601",
        }
        try:
            response = requests.get(self.url, params=params, timeout=self.timeout, headers={"User-Agent": self.user_agent})
            response.raise_for_status()
            payload = response.json()
            current: dict[str, Any] = payload.get("current", {})
            code = current.get("weather_code")
            return EnvironmentData(
                air_temp_c=current.get("temperature_2m"),
                relative_humidity_pct=current.get("relative_humidity_2m"),
                apparent_temp_c=current.get("apparent_temperature"),
                precipitation_mm=current.get("precipitation"),
                weather_code=code,
                weather_summary=weather_code_to_text(code),
                cloud_cover_pct=current.get("cloud_cover"),
                pressure_msl_hpa=current.get("pressure_msl"),
                surface_pressure_hpa=current.get("surface_pressure"),
                wind_speed_kts_mean=current.get("wind_speed_10m"),
                wind_direction_deg_mean=current.get("wind_direction_10m"),
                wind_gusts_kts=current.get("wind_gusts_10m"),
                raw_weather_api_json=payload,
                weather_query_params=params,
            )
        except Exception as exc:
            return EnvironmentData(
                weather_error=str(exc),
                weather_query_params=params,
            )
