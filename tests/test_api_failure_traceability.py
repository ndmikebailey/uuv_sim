"""API-failure traceability tests."""

from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from services.marine_api import OpenMeteoMarineClient
from services.weather_api import OpenMeteoWeatherClient


class ApiFailureTraceabilityTests(unittest.TestCase):
    """Failure paths should still preserve query context."""

    def test_marine_failure_preserves_query_params(self) -> None:
        """Marine API exceptions should return the attempted query."""
        with patch("services.marine_api.requests.get", side_effect=RuntimeError("network down")):
            result = OpenMeteoMarineClient().fetch(13.4, 144.8)
        self.assertIn("network down", result.marine_error or "")
        self.assertEqual(result.marine_query_params["latitude"], 13.4)
        self.assertEqual(result.marine_query_params["longitude"], 144.8)
        self.assertNotIn("sea_surface_salinity", result.marine_query_params["current"])
        self.assertEqual(
            result.marine_query_params["salinity_query_status"],
            "not_requested_open_meteo_marine_unsupported",
        )

    def test_marine_success_parses_salinity(self) -> None:
        """Marine API responses should preserve sea-surface salinity when available."""
        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {
                    "current": {
                        "ocean_current_velocity": 0.8,
                        "ocean_current_direction": 90.0,
                        "sea_surface_temperature": 26.0,
                        "sea_surface_salinity": 34.7,
                    }
                }

        with patch("services.marine_api.requests.get", return_value=FakeResponse()):
            result = OpenMeteoMarineClient().fetch(13.4, 144.8)

        self.assertEqual(result.sea_surface_salinity_psu, 34.7)
        self.assertNotIn("sea_surface_salinity", result.marine_query_params["current"])
        self.assertEqual(
            result.marine_query_params["salinity_query_status"],
            "not_requested_open_meteo_marine_unsupported",
        )

    def test_weather_failure_preserves_query_params(self) -> None:
        """Weather API exceptions should return the attempted query."""
        with patch("services.weather_api.requests.get", side_effect=RuntimeError("network down")):
            result = OpenMeteoWeatherClient().fetch(13.4, 144.8)
        self.assertIn("network down", result.weather_error or "")
        self.assertEqual(result.weather_query_params["latitude"], 13.4)
        self.assertEqual(result.weather_query_params["longitude"], 144.8)

    def test_selected_environment_time_uses_nearest_hourly_values(self) -> None:
        """Marine and weather clients should use the requested UTC forecast hour."""
        requested = datetime(2026, 7, 24, 13, 20, tzinfo=timezone.utc)

        class MarineResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {
                    "hourly": {
                        "time": ["2026-07-24T12:00", "2026-07-24T13:00", "2026-07-24T14:00"],
                        "ocean_current_velocity": [0.2, 0.7, 1.1],
                        "ocean_current_direction": [80.0, 90.0, 100.0],
                        "sea_surface_temperature": [25.0, 26.0, 27.0],
                    }
                }

        class WeatherResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {
                    "hourly": {
                        "time": ["2026-07-24T12:00", "2026-07-24T13:00", "2026-07-24T14:00"],
                        "temperature_2m": [28.0, 29.0, 30.0],
                        "weather_code": [0, 2, 3],
                        "wind_speed_10m": [5.0, 7.0, 9.0],
                    }
                }

        with patch("services.marine_api.requests.get", return_value=MarineResponse()):
            marine = OpenMeteoMarineClient().fetch(13.4, 144.8, requested)
        with patch("services.weather_api.requests.get", return_value=WeatherResponse()):
            weather = OpenMeteoWeatherClient().fetch(13.4, 144.8, requested)

        self.assertEqual(marine.current_speed_kts_mean, 0.7)
        self.assertEqual(marine.valid_at_utc, "2026-07-24T13:00:00Z")
        self.assertEqual(weather.wind_speed_kts_mean, 7.0)
        self.assertEqual(weather.weather_summary, "Partly cloudy")
        self.assertEqual(weather.valid_at_utc, "2026-07-24T13:00:00Z")
        self.assertEqual(marine.marine_query_params["start_date"], "2026-07-24")
        self.assertEqual(weather.weather_query_params["end_date"], "2026-07-24")


if __name__ == "__main__":
    unittest.main()
