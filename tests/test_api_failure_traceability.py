"""API-failure traceability tests."""

from __future__ import annotations

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

    def test_weather_failure_preserves_query_params(self) -> None:
        """Weather API exceptions should return the attempted query."""
        with patch("services.weather_api.requests.get", side_effect=RuntimeError("network down")):
            result = OpenMeteoWeatherClient().fetch(13.4, 144.8)
        self.assertIn("network down", result.weather_error or "")
        self.assertEqual(result.weather_query_params["latitude"], 13.4)
        self.assertEqual(result.weather_query_params["longitude"], 144.8)


if __name__ == "__main__":
    unittest.main()
