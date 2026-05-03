"""Structured environment data returned by services."""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class EnvironmentData:
    """Marine and weather conditions used by planning calculations."""

    current_speed_kts_mean: Optional[float] = None
    current_direction_deg_mean: Optional[float] = None
    sea_surface_temp_c_mean: Optional[float] = None
    sea_surface_salinity_psu: Optional[float] = None
    sea_water_density_kg_m3: Optional[float] = None
    sea_level_height_m: Optional[float] = None
    wave_height_m: Optional[float] = None
    wave_direction_deg: Optional[float] = None
    wave_period_s: Optional[float] = None
    wind_wave_height_m: Optional[float] = None
    swell_wave_height_m: Optional[float] = None
    air_temp_c: Optional[float] = None
    relative_humidity_pct: Optional[float] = None
    apparent_temp_c: Optional[float] = None
    precipitation_mm: Optional[float] = None
    weather_code: Optional[float] = None
    weather_summary: Optional[str] = None
    cloud_cover_pct: Optional[float] = None
    pressure_msl_hpa: Optional[float] = None
    surface_pressure_hpa: Optional[float] = None
    wind_speed_kts_mean: Optional[float] = None
    wind_direction_deg_mean: Optional[float] = None
    wind_gusts_kts: Optional[float] = None
    marine_error: Optional[str] = None
    weather_error: Optional[str] = None
    salinity_error: Optional[str] = None
    raw_marine_api_json: dict[str, Any] = field(default_factory=dict)
    raw_weather_api_json: dict[str, Any] = field(default_factory=dict)
    raw_salinity_api_json: dict[str, Any] = field(default_factory=dict)
    marine_query_params: dict[str, Any] = field(default_factory=dict)
    weather_query_params: dict[str, Any] = field(default_factory=dict)
    salinity_query_params: dict[str, Any] = field(default_factory=dict)
    salinity_metadata: dict[str, Any] = field(default_factory=dict)
    salinity_source: str = "standard_assumption"
    source: str = "Open-Meteo"
    loaded_at_utc: str = ""

    def __post_init__(self) -> None:
        """Default timestamp to creation time when omitted."""
        if not self.loaded_at_utc:
            self.loaded_at_utc = datetime.now(timezone.utc).isoformat()

    @property
    def salinity_psu(self) -> Optional[float]:
        """Alias for sea-surface salinity in practical salinity units."""
        return self.sea_surface_salinity_psu

    @salinity_psu.setter
    def salinity_psu(self, value: Optional[float]) -> None:
        self.sea_surface_salinity_psu = value

    def merged(self, other: "EnvironmentData") -> "EnvironmentData":
        """Return a new environment object with non-null values from ``other``."""
        data = self.to_dict()
        for key, value in other.to_dict().items():
            if value is None or value == "":
                continue
            if isinstance(value, (dict, list)) and not value:
                continue
            data[key] = value
        return EnvironmentData(**data)

    def to_dict(self) -> dict[str, object]:
        """Serialize environment values."""
        return asdict(self)

    def table_rows(self, centroid_lat: float, centroid_lon: float) -> list[tuple[str, object, str]]:
        """Return operator-facing environment rows."""
        return [
            ("Environment lookup latitude", centroid_lat, "deg"),
            ("Environment lookup longitude", centroid_lon, "deg"),
            ("Current speed mean", self.current_speed_kts_mean, "kts"),
            ("Current direction mean", self.current_direction_deg_mean, "deg"),
            ("Sea surface temperature", self.sea_surface_temp_c_mean, "deg C"),
            ("Sea surface salinity", self.sea_surface_salinity_psu, "PSU"),
            ("Sea water density", self.sea_water_density_kg_m3, "kg/m3"),
            ("Salinity source", self.salinity_source, ""),
            ("Sea level height MSL", self.sea_level_height_m, "m"),
            ("Wave height", self.wave_height_m, "m"),
            ("Wave direction", self.wave_direction_deg, "deg"),
            ("Wave period", self.wave_period_s, "s"),
            ("Wind speed", self.wind_speed_kts_mean, "kts"),
            ("Wind direction", self.wind_direction_deg_mean, "deg"),
            ("Wind gusts", self.wind_gusts_kts, "kts"),
            ("Air temperature", self.air_temp_c, "deg C"),
            ("Cloud cover", self.cloud_cover_pct, "%"),
            ("Pressure MSL", self.pressure_msl_hpa, "hPa"),
            ("Weather summary", self.weather_summary, ""),
        ]
