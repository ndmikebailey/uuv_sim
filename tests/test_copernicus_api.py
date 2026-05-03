"""Copernicus Marine provider fallback tests."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from models.environment_model import EnvironmentData
from services.copernicus_api import get_copernicus_salinity_density


class CopernicusProviderTests(unittest.TestCase):
    """Provider should be credential-safe and optional."""

    def test_disabled_provider_returns_clear_environment(self) -> None:
        result = get_copernicus_salinity_density(13.4, 144.8, enabled=False)
        self.assertIsInstance(result, EnvironmentData)
        self.assertEqual(result.salinity_source, "off")
        self.assertIn("disabled", result.salinity_error or "")

    def test_missing_package_returns_gracefully(self) -> None:
        with patch.dict(sys.modules, {"copernicusmarine": None}):
            result = get_copernicus_salinity_density(13.4, 144.8, enabled=True)
        self.assertEqual(result.salinity_source, "copernicus_unavailable")
        self.assertIn("not installed", result.salinity_error or "")
        self.assertEqual(result.salinity_query_params["latitude"], 13.4)
        self.assertNotIn("COPERNICUSMARINE_PASSWORD", str(result.salinity_query_params))

    def test_salinity_merge_preserves_open_meteo_values(self) -> None:
        baseline = EnvironmentData(current_speed_kts_mean=0.7, sea_surface_temp_c_mean=26.0)
        salinity = EnvironmentData(
            sea_surface_salinity_psu=34.8,
            sea_water_density_kg_m3=1024.5,
            salinity_source="copernicus_marine",
        )
        merged = baseline.merged(salinity)
        self.assertEqual(merged.current_speed_kts_mean, 0.7)
        self.assertEqual(merged.sea_surface_temp_c_mean, 26.0)
        self.assertEqual(merged.sea_surface_salinity_psu, 34.8)
        self.assertEqual(merged.sea_water_density_kg_m3, 1024.5)


if __name__ == "__main__":
    unittest.main()
