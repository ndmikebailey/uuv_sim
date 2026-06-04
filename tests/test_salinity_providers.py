"""Salinity provider-chain tests without live internet."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from app.ui.reporting import build_environmental_input_rows, build_sustainment_projection_rows
from models.environment_model import EnvironmentData
from services.metoc_fusion import MetocFusionService, standard_seawater_environment
from services.noaa_coops_salinity import NoaaCoopsSalinityProvider
from services.woa23_salinity import get_woa23_salinity


class FakeMarineClient:
    def fetch(self, lat: float, lon: float) -> EnvironmentData:
        return EnvironmentData(
            current_speed_kts_mean=0.7,
            sea_surface_temp_c_mean=26.0,
            marine_query_params={"latitude": lat, "longitude": lon},
        )


class FakeWeatherClient:
    def fetch(self, lat: float, lon: float) -> EnvironmentData:
        return EnvironmentData(
            wind_speed_kts_mean=11.0,
            weather_query_params={"latitude": lat, "longitude": lon},
        )


class FakeUnavailableProvider:
    def fetch(self, lat: float, lon: float, when_utc=None) -> EnvironmentData:
        return EnvironmentData(salinity_source="provider_unavailable")


def fake_woa_success(lat: float, lon: float, month=None, depth_m: float = 0.0) -> dict:
    return {
        "salinity_psu": 34.6,
        "density_kg_m3": 1024.7,
        "salinity_source": "NOAA WOA23 climatology",
    }


def fake_woa_unexpected(lat: float, lon: float, month=None, depth_m: float = 0.0) -> dict:
    raise AssertionError("WOA should not be called when CO-OPS succeeds")


class SalinityProviderTests(unittest.TestCase):
    """Provider-chain and report wording behavior."""

    def test_standard_seawater_fallback_fields(self) -> None:
        result = standard_seawater_environment()
        self.assertEqual(result.sea_surface_salinity_psu, 35.0)
        self.assertEqual(result.sea_water_density_kg_m3, 1025.0)
        self.assertEqual(result.salinity_source, "Standard seawater assumption")

    def test_noaa_unavailable_is_structured(self) -> None:
        with patch("services.noaa_coops_salinity.requests.get", side_effect=RuntimeError("offline")):
            result = NoaaCoopsSalinityProvider().fetch(13.4, 144.8)
        self.assertEqual(result.salinity_source, "noaa_coops_unavailable")
        self.assertIsNone(result.sea_surface_salinity_psu)

    def test_woa_success_contract_is_simple(self) -> None:
        rows = ((13.5, 144.5, 34.7),)
        with patch("services.woa23_salinity._fetch_woa_rows", return_value=rows):
            result = get_woa23_salinity(13.45, 144.7, month=5)
        self.assertEqual(set(result.keys()), {"salinity_psu", "density_kg_m3", "salinity_source"})
        self.assertEqual(result["salinity_source"], "NOAA WOA23 climatology")
        self.assertEqual(result["salinity_psu"], 34.7)

    def test_woa_missing_nearest_searches_neighboring_cells(self) -> None:
        rows = ((14.5, 145.5, 34.9),)
        with patch("services.woa23_salinity._fetch_woa_rows", return_value=rows):
            result = get_woa23_salinity(13.45, 144.7, month=5)
        self.assertEqual(result["salinity_source"], "NOAA WOA23 climatology")
        self.assertEqual(result["salinity_psu"], 34.9)

    def test_woa_failure_returns_standard_seawater(self) -> None:
        with patch("services.woa23_salinity._fetch_woa_rows", side_effect=RuntimeError("offline")):
            result = get_woa23_salinity(13.45, 144.7, month=5)
        self.assertEqual(result, {"salinity_psu": 35.0, "density_kg_m3": 1025.0, "salinity_source": "Standard seawater assumption"})

    def test_gps_metoc_preserves_open_meteo_when_salinity_falls_back(self) -> None:
        service = MetocFusionService(
            FakeMarineClient(),
            FakeWeatherClient(),
            salinity_enabled=True,
            noaa_salinity_provider=FakeUnavailableProvider(),  # type: ignore[arg-type]
            woa_salinity_provider=lambda lat, lon, month=None, depth_m=0.0: {
                "salinity_psu": 35.0,
                "density_kg_m3": 1025.0,
                "salinity_source": "Standard seawater assumption",
            },
        )
        result = service.fetch(13.4, 144.8)
        self.assertEqual(result.current_speed_kts_mean, 0.7)
        self.assertEqual(result.sea_surface_temp_c_mean, 26.0)
        self.assertEqual(result.wind_speed_kts_mean, 11.0)
        self.assertEqual(result.salinity_source, "Standard seawater assumption")

    def test_coops_failure_falls_through_to_woa(self) -> None:
        service = MetocFusionService(
            FakeMarineClient(),
            FakeWeatherClient(),
            salinity_enabled=True,
            noaa_salinity_provider=FakeUnavailableProvider(),  # type: ignore[arg-type]
            woa_salinity_provider=fake_woa_success,
        )
        result = service.fetch(13.4, 144.8)
        self.assertEqual(result.current_speed_kts_mean, 0.7)
        self.assertEqual(result.salinity_source, "NOAA WOA23 climatology")
        self.assertEqual(result.sea_surface_salinity_psu, 34.6)

    def test_gps_metoc_attempts_coops_first(self) -> None:
        class FakeCoopsProvider:
            def fetch(self, lat: float, lon: float, when_utc=None) -> EnvironmentData:
                return EnvironmentData(
                    sea_surface_salinity_psu=33.9,
                    sea_water_density_kg_m3=1024.1,
                    salinity_source="NOAA CO-OPS station observation",
                )

        service = MetocFusionService(
            FakeMarineClient(),
            FakeWeatherClient(),
            salinity_enabled=True,
            noaa_salinity_provider=FakeCoopsProvider(),  # type: ignore[arg-type]
            woa_salinity_provider=fake_woa_unexpected,
        )
        result = service.fetch(13.4, 144.8)
        self.assertEqual(result.salinity_source, "NOAA CO-OPS station observation")
        self.assertEqual(result.sea_surface_salinity_psu, 33.9)

    def test_no_active_copernicus_import_remains(self) -> None:
        for path in [*Path("app").rglob("*.py"), *Path("core").rglob("*.py"), *Path("models").rglob("*.py"), *Path("services").rglob("*.py")]:
            self.assertNotIn("copernicus", path.read_text(encoding="utf-8").lower(), str(path))

    def test_report_code_does_not_claim_removed_sources_active(self) -> None:
        report_text = Path("app/ui/reporting.py").read_text(encoding="utf-8").lower()
        main_text = Path("app/main.py").read_text(encoding="utf-8").lower()
        for token in ("copernicus", "hycom", "smap", "argo"):
            self.assertNotIn(token, report_text)
            self.assertNotIn(token, main_text)

    def test_report_salinity_source_wording(self) -> None:
        rows = build_environmental_input_rows({}, standard_seawater_environment())
        labels = [row[0] for row in rows]
        self.assertIn("Salinity source", labels)
        self.assertIn(("Salinity source", "Standard seawater assumption.", ""), rows)
        self.assertNotIn("Salinity provider note", labels)
        self.assertNotIn("Salinity validation status", labels)

    def test_report_environment_rows_include_compact_provider_status(self) -> None:
        error = (
            "429 Client Error: Too Many Requests for url: "
            "https://api.open-meteo.com/v1/forecast?latitude=13.5&longitude=144.6"
        )
        rows = build_environmental_input_rows({}, EnvironmentData(weather_error=error))
        self.assertIn(("Marine status", "OK", ""), rows)
        self.assertIn(("Weather status", "Unavailable: 429 Too Many Requests", ""), rows)
        self.assertNotIn("api.open-meteo.com", str(rows))

    def test_sustainment_projection_reports_fuel_lens_without_removing_energy(self) -> None:
        rows = build_sustainment_projection_rows(
            {
                "sustainment_projection_enabled": True,
                "sustainment_recharge_energy_required_kwh": 3.0,
                "sustainment_generator_input_energy_kwh": 12.0,
                "sustainment_generator_kwh_per_gallon": 10.0,
                "sustainment_fuel_gallons_equivalent": 1.2,
                "in_mission_recharge_shortfall_kwh": 3.0,
            }
        )
        self.assertIn(("In-mission recharge shortfall", 3.0, "kWh"), rows)
        self.assertIn(("Generator input energy to reset consumed energy", 12.0, "kWh"), rows)
        self.assertNotIn(("Fuel-equivalent estimate", 1.2, "gal JP-8/diesel"), rows)


if __name__ == "__main__":
    unittest.main()
