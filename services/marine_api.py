"""Open-Meteo marine API client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from models.environment_model import EnvironmentData
from services.open_meteo_time import isoformat_utc, select_hourly_record
from utils.constants import OPEN_METEO_MARINE_URL, REQUEST_TIMEOUT, USER_AGENT


@dataclass
class OpenMeteoMarineClient:
    """Structured client for Open-Meteo marine conditions."""

    url: str = OPEN_METEO_MARINE_URL
    timeout: int = REQUEST_TIMEOUT
    user_agent: str = USER_AGENT

    def fetch(self, lat: float, lon: float, when_utc: datetime | None = None) -> EnvironmentData:
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
            "cell_selection": "sea",
            "velocity_unit": "kn",
            "timeformat": "iso8601",
            "timezone": "GMT",
        }
        if when_utc is None:
            params.update({"forecast_hours": 24, "past_hours": 6})
        else:
            selected_date = when_utc.date().isoformat()
            params.update({"start_date": selected_date, "end_date": selected_date})
        trace_params = {
            **params,
            "salinity_query_status": "not_requested_open_meteo_marine_unsupported",
        }
        try:
            response = requests.get(self.url, params=params, timeout=self.timeout, headers={"User-Agent": self.user_agent})
            response.raise_for_status()
            payload = response.json()
            if when_utc is None:
                current: dict[str, Any] = payload.get("current", {})
                valid_at_utc = str(current.get("time") or "")
            else:
                current, valid_at_utc = select_hourly_record(payload, when_utc)
            return EnvironmentData(
                current_speed_kts_mean=current.get("ocean_current_velocity"),
                current_direction_deg_mean=current.get("ocean_current_direction"),
                sea_surface_temp_c_mean=current.get("sea_surface_temperature"),
                sea_surface_salinity_psu=(
                    current.get("sea_surface_salinity")
                    or current.get("ocean_salinity")
                    or current.get("salinity")
                ),
                sea_level_height_m=current.get("sea_level_height_msl"),
                wave_height_m=current.get("wave_height"),
                wave_direction_deg=current.get("wave_direction"),
                wave_period_s=current.get("wave_period"),
                wind_wave_height_m=current.get("wind_wave_height"),
                swell_wave_height_m=current.get("swell_wave_height"),
                raw_marine_api_json=payload,
                marine_query_params=trace_params,
                requested_at_utc=isoformat_utc(when_utc),
                valid_at_utc=valid_at_utc,
            )
        except Exception as exc:
            return EnvironmentData(
                marine_error=str(exc),
                marine_query_params=trace_params,
                requested_at_utc=isoformat_utc(when_utc),
            )
