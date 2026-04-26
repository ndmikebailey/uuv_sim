"""Environment-data merge traceability tests."""

from __future__ import annotations

import unittest

from models.environment_model import EnvironmentData


class EnvironmentMergeTests(unittest.TestCase):
    """Regression tests for preserving raw API payloads during fusion."""

    def test_empty_weather_marine_payload_does_not_overwrite_marine_payload(self) -> None:
        """Weather defaults should not erase marine raw payloads or query params."""
        marine = EnvironmentData(
            current_speed_kts_mean=0.7,
            raw_marine_api_json={"current": {"ocean_current_velocity": 0.7}},
            marine_query_params={"latitude": 13.4, "longitude": 144.8},
        )
        weather = EnvironmentData(
            wind_speed_kts_mean=8.0,
            raw_weather_api_json={"current": {"wind_speed_10m": 8.0}},
            weather_query_params={"latitude": 13.4, "longitude": 144.8},
        )
        fused = marine.merged(weather)
        self.assertEqual(fused.raw_marine_api_json, marine.raw_marine_api_json)
        self.assertEqual(fused.marine_query_params, marine.marine_query_params)
        self.assertEqual(fused.raw_weather_api_json, weather.raw_weather_api_json)
        self.assertEqual(fused.weather_query_params, weather.weather_query_params)

    def test_empty_dicts_do_not_overwrite_existing_raw_payloads(self) -> None:
        """Empty dict/list values should not replace populated traceability payloads."""
        marine = EnvironmentData(
            current_speed_kts_mean=2.2,
            raw_marine_api_json={"current": {"ocean_current_velocity": 2.2}},
            marine_query_params={"latitude": 13.4, "longitude": 144.7},
        )
        weather = EnvironmentData(
            air_temp_c=29.0,
            raw_marine_api_json={},
            marine_query_params={},
        )

        merged = marine.merged(weather)

        self.assertEqual(merged.current_speed_kts_mean, 2.2)
        self.assertEqual(merged.air_temp_c, 29.0)
        self.assertEqual(merged.raw_marine_api_json, {"current": {"ocean_current_velocity": 2.2}})
        self.assertEqual(merged.marine_query_params, {"latitude": 13.4, "longitude": 144.7})


if __name__ == "__main__":
    unittest.main()
