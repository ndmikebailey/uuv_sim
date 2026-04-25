"""Open-Meteo marine API client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from models.environment_model import EnvironmentData
from utils.constants import OPEN_METEO_MARINE_URL, REQUEST_TIMEOUT, USER_AGENT


@dataclass
class OpenMeteoMarineClient:
    """Structured client for Open-Meteo marine conditions."""

    url: str = OPEN_METEO_MARINE_URL
    timeout: int = REQUEST_TIMEOUT
    user_agent: str = USER_AGENT

    def fetch(self, lat: float, lon: float) -> EnvironmentData:
        """Fetch marine data and return an ``EnvironmentData`` object."""
        variables = [
            "ocean_current_velocity",
            "ocean_current_direction",
            "sea_surface_temperature",
            "sea_level_height_msl",
            "wave_height",
            "wave_direction",
            "wave_period",
            "wind_wave_height",
            "swell_wave_height",
        ]
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": ",".join(variables),
            "hourly": ",".join(variables),
            "forecast_hours": 24,
            "past_hours": 6,
            "cell_selection": "sea",
            "velocity_unit": "kn",
            "timeformat": "iso8601",
        }
        try:
            response = requests.get(self.url, params=params, timeout=self.timeout, headers={"User-Agent": self.user_agent})
            response.raise_for_status()
            payload = response.json()
            current: dict[str, Any] = payload.get("current", {})
            return EnvironmentData(
                current_speed_kts_mean=current.get("ocean_current_velocity"),
                current_direction_deg_mean=current.get("ocean_current_direction"),
                sea_surface_temp_c_mean=current.get("sea_surface_temperature"),
                sea_level_height_m=current.get("sea_level_height_msl"),
                wave_height_m=current.get("wave_height"),
                wave_direction_deg=current.get("wave_direction"),
                wave_period_s=current.get("wave_period"),
                wind_wave_height_m=current.get("wind_wave_height"),
                swell_wave_height_m=current.get("swell_wave_height"),
                raw_marine_api_json=payload,
                marine_query_params=params,
            )
        except Exception as exc:
            return EnvironmentData(
                marine_error=str(exc),
                marine_query_params=params,
            )
