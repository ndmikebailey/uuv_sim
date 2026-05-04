"""METOC fusion and risk assessment service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from models.environment_model import EnvironmentData
from services.marine_api import OpenMeteoMarineClient
from services.noaa_coops_salinity import NoaaCoopsSalinityProvider
from services.weather_api import OpenMeteoWeatherClient
from services.woa23_salinity import get_woa23_salinity


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


def standard_seawater_environment() -> EnvironmentData:
    """Return the explicit standard seawater fallback used when live providers fail."""
    return EnvironmentData(
        sea_surface_salinity_psu=35.0,
        sea_water_density_kg_m3=1025.0,
        salinity_source="Standard seawater assumption",
        salinity_query_params={"source": "Standard seawater assumption"},
    )


def _has_valid_salinity(environment: EnvironmentData) -> bool:
    """Return whether a provider produced usable salinity."""
    return environment.sea_surface_salinity_psu is not None


@dataclass
class MetocFusionService:
    """Fetch and fuse marine/weather data into one structured object."""

    marine_client: OpenMeteoMarineClient
    weather_client: OpenMeteoWeatherClient
    salinity_enabled: bool = False
    noaa_salinity_provider: NoaaCoopsSalinityProvider | None = None
    woa_salinity_provider: object | None = None

    def fetch(self, lat: float, lon: float, when_utc: datetime | None = None) -> EnvironmentData:
        """Return fused environment values for a mission centroid."""
        marine = self.marine_client.fetch(lat, lon)
        weather = self.weather_client.fetch(lat, lon)
        environment = marine.merged(weather)
        if not self.salinity_enabled:
            return environment
        salinity = self.fetch_salinity(lat, lon, when_utc)
        return environment.merged(salinity)

    def fetch_salinity(self, lat: float, lon: float, when_utc: datetime | None = None) -> EnvironmentData:
        """Attempt NOAA CO-OPS, then WOA23, then standard seawater."""
        noaa_provider = self.noaa_salinity_provider or NoaaCoopsSalinityProvider()
        noaa = noaa_provider.fetch(lat, lon, when_utc)
        if _has_valid_salinity(noaa):
            return noaa
        month = when_utc.month if when_utc else None
        provider = self.woa_salinity_provider or get_woa23_salinity
        try:
            woa = provider(lat, lon, month=month, depth_m=0.0)  # type: ignore[operator]
        except TypeError:
            woa = provider(lat, lon, month, 0.0)  # type: ignore[operator]
        result = EnvironmentData(
            sea_surface_salinity_psu=woa.get("salinity_psu"),
            sea_water_density_kg_m3=woa.get("density_kg_m3"),
            salinity_source=str(woa.get("salinity_source") or "Standard seawater assumption"),
            salinity_query_params={
                "provider_chain": [
                    "NOAA CO-OPS station observation",
                    "NOAA WOA23 climatology",
                    "Standard seawater assumption",
                ],
                "noaa_status": noaa.salinity_source,
                "woa_status": woa.get("salinity_source"),
            },
        )
        return result if _has_valid_salinity(result) else standard_seawater_environment()

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
