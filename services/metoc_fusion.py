"""METOC fusion and risk assessment service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.environment_model import EnvironmentData
from services.marine_api import OpenMeteoMarineClient
from services.weather_api import OpenMeteoWeatherClient


def risk_level(value: Optional[float], low_max: float, mod_max: float, missing: str = "Unknown") -> tuple[str, str]:
    """Return qualitative risk and color token for thresholded values."""
    if value is None:
        return missing, "gray"
    if value <= low_max:
        return "Favorable", "green"
    if value <= mod_max:
        return "Marginal", "yellow"
    return "Unfavorable", "red"


def temp_risk_level(temp_c: Optional[float]) -> tuple[str, str]:
    """Return battery-temperature planning risk."""
    if temp_c is None:
        return "Unknown", "gray"
    if 10 <= temp_c <= 30:
        return "Favorable", "green"
    if 0 <= temp_c < 10 or 30 < temp_c <= 35:
        return "Marginal", "yellow"
    return "Unfavorable", "red"


def weather_risk_level(code: Optional[float], precip_mm: Optional[float]) -> tuple[str, str]:
    """Return general weather risk from Open-Meteo code and precipitation."""
    c = int(code) if code is not None else -1
    p = precip_mm or 0.0
    if c in [95, 96, 99] or p >= 10:
        return "Unfavorable", "red"
    if c in [3, 45, 48, 51, 53, 55, 61, 63, 65, 80, 81, 82] or p > 0:
        return "Marginal", "yellow"
    if c >= 0:
        return "Favorable", "green"
    return "Unknown", "gray"


@dataclass
class MetocFusionService:
    """Fetch and fuse marine/weather data into one structured object."""

    marine_client: OpenMeteoMarineClient
    weather_client: OpenMeteoWeatherClient

    def fetch(self, lat: float, lon: float) -> EnvironmentData:
        """Return fused environment values for a mission centroid."""
        marine = self.marine_client.fetch(lat, lon)
        weather = self.weather_client.fetch(lat, lon)
        return marine.merged(weather)

    def assessment(self, environment: EnvironmentData) -> dict[str, object]:
        """Return the METOC assessment used by the UI report cards."""
        current_level, current_color = risk_level(environment.current_speed_kts_mean, 0.5, 1.5)
        wave_level, wave_color = risk_level(environment.wave_height_m, 0.5, 1.5)
        wind_level, wind_color = risk_level(environment.wind_speed_kts_mean, 10, 20)
        temp_level, temp_color = temp_risk_level(environment.sea_surface_temp_c_mean)
        wx_level, wx_color = weather_risk_level(environment.weather_code, environment.precipitation_mm)
        order = {"green": 0, "yellow": 1, "red": 2, "gray": 1}
        colors = [current_color, wave_color, wind_color, temp_color, wx_color]
        worst = max(colors, key=lambda color: order.get(color, 1))
        posture = {"green": "Favorable", "yellow": "Marginal", "red": "Unfavorable", "gray": "Unknown"}[worst]
        return {
            "posture": posture,
            "items": [
                ("Current", current_level, current_color, environment.current_speed_kts_mean, "kts", "Route/track current burden."),
                ("Wave / Surf", wave_level, wave_color, environment.wave_height_m, "m", "Launch/recovery and surface-support lens."),
                ("Wind", wind_level, wind_color, environment.wind_speed_kts_mean, "kts", "Launch/recovery and support craft lens."),
                ("SST / Battery", temp_level, temp_color, environment.sea_surface_temp_c_mean, "deg C", "Battery derating lens for planning."),
                ("Weather", wx_level, wx_color, environment.weather_summary or "N/A", "", "General operating conditions."),
            ],
        }

