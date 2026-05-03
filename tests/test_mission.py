"""Mission orchestration and METOC lookup tests."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from core.geometry import parse_geometry_json
from core.mission import aggregate_environments, build_mission_context, choose_environment_lookup_point
from models.environment_model import EnvironmentData
from models.mission_model import MissionAreaSet
from services.metoc_fusion import MetocFusionService


LINE_GEOMETRY = {
    "geometry_type": "line",
    "route_points": [
        {"lat": 13.44, "lon": 144.79},
        {"lat": 13.46, "lon": 144.82},
    ],
}

POLYGON_GEOMETRY = {
    "geometry_type": "polygon",
    "bounds": {"north": 13.47, "south": 13.44, "east": 144.83, "west": 144.785},
    "vertices": [
        {"lat": 13.44, "lon": 144.79},
        {"lat": 13.44, "lon": 144.83},
        {"lat": 13.47, "lon": 144.82},
        {"lat": 13.465, "lon": 144.785},
    ],
}

MULTI_AREA_GEOMETRY = {
    "geometry_type": "MultiArea",
    "areas": [
        {
            "geometry_type": "rectangle",
            "bounds": {"north": 13.46, "south": 13.44, "east": 144.82, "west": 144.79},
            "vertices": [
                {"lat": 13.44, "lon": 144.79},
                {"lat": 13.44, "lon": 144.82},
                {"lat": 13.46, "lon": 144.82},
                {"lat": 13.46, "lon": 144.79},
            ],
        },
        {
            "geometry_type": "rectangle",
            "bounds": {"north": 13.49, "south": 13.47, "east": 144.86, "west": 144.83},
            "vertices": [
                {"lat": 13.47, "lon": 144.83},
                {"lat": 13.47, "lon": 144.86},
                {"lat": 13.49, "lon": 144.86},
                {"lat": 13.49, "lon": 144.83},
            ],
        },
    ],
}


class FakeMetocService:
    """Return deterministic area-specific METOC values."""

    def fetch(self, lat: float, lon: float) -> EnvironmentData:
        direction = 0.0 if lon < 144.83 else 90.0
        return EnvironmentData(
            current_speed_kts_mean=1.0,
            current_direction_deg_mean=direction,
            sea_surface_temp_c_mean=24.0 if lon < 144.83 else 26.0,
            sea_surface_salinity_psu=34.0 if lon < 144.83 else 36.0,
            wind_speed_kts_mean=8.0 if lon < 144.83 else 10.0,
            marine_query_params={"latitude": lat, "longitude": lon},
            weather_query_params={"latitude": lat, "longitude": lon},
        )


class FakeMarineClient:
    def fetch(self, lat: float, lon: float) -> EnvironmentData:
        return EnvironmentData(
            current_speed_kts_mean=0.5,
            current_direction_deg_mean=0.0,
            sea_surface_temp_c_mean=25.0,
            marine_query_params={"latitude": lat, "longitude": lon},
        )


class FakeWeatherClient:
    def fetch(self, lat: float, lon: float) -> EnvironmentData:
        return EnvironmentData(weather_query_params={"latitude": lat, "longitude": lon})


class MissionLookupTests(unittest.TestCase):
    """Mission-specific environmental lookup behavior."""

    def test_isr_uses_first_boundary_point_for_lookup(self) -> None:
        """ISR should avoid defaulting to polygon centroid."""
        area = parse_geometry_json(json.dumps(POLYGON_GEOMETRY))
        self.assertEqual(choose_environment_lookup_point("ISR", area), (13.44, 144.79))

    def test_payload_uses_route_midpoint_for_lookup(self) -> None:
        """Payload delivery should use a route-representative point."""
        area = parse_geometry_json(json.dumps(LINE_GEOMETRY))
        self.assertEqual(choose_environment_lookup_point("Payload Delivery", area), (13.45, 144.805))

    def test_area_search_uses_centroid_for_lookup(self) -> None:
        """Area search remains centroid-driven."""
        area = parse_geometry_json(json.dumps(POLYGON_GEOMETRY))
        self.assertEqual(choose_environment_lookup_point("Area Search / MCM", area), (area.centroid_lat, area.centroid_lon))

    def test_multi_area_geometry_sums_area_and_points(self) -> None:
        """Multi-area geometry should preserve individual search areas."""
        area_set = parse_geometry_json(json.dumps(MULTI_AREA_GEOMETRY))
        self.assertIsInstance(area_set, MissionAreaSet)
        assert isinstance(area_set, MissionAreaSet)
        self.assertEqual(len(area_set.areas), 2)
        self.assertEqual(len(area_set.representative_points), 2)
        self.assertAlmostEqual(
            area_set.total_area_km2,
            sum(float(area.area_km2 or 0.0) for area in area_set.areas),
        )

    def test_current_vector_average_avoids_angle_average(self) -> None:
        """Opposing near-north directions should average through north, not south."""
        environment = aggregate_environments(
            [
                EnvironmentData(current_speed_kts_mean=1.0, current_direction_deg_mean=350.0),
                EnvironmentData(current_speed_kts_mean=1.0, current_direction_deg_mean=10.0),
            ],
            [(0.0, 0.0), (1.0, 1.0)],
        )
        self.assertAlmostEqual(float(environment.current_direction_deg_mean or 0.0), 0.0, delta=1.0)
        self.assertGreater(float(environment.current_speed_kts_mean or 0.0), 0.9)

    def test_multi_area_mission_context_uses_centroid_samples(self) -> None:
        """Multi-area Search/MCM should fetch one METOC sample per area centroid."""
        result = build_mission_context("Area Search / MCM", json.dumps(MULTI_AREA_GEOMETRY), FakeMetocService())  # type: ignore[arg-type]
        self.assertTrue(result.ok, result.status)
        self.assertIsInstance(result.context.area, MissionAreaSet)
        assert isinstance(result.context.area, MissionAreaSet)
        self.assertEqual(len(result.context.area.representative_points), 2)
        self.assertIn("area centroid METOC samples", result.status)
        self.assertEqual(result.context.environment.source, "Open-Meteo area-centroid average")
        self.assertAlmostEqual(float(result.context.environment.sea_surface_salinity_psu or 0.0), 35.0)

    def test_metoc_fusion_attempts_salinity_when_enabled(self) -> None:
        """Mission Builder service path should supplement Open-Meteo with Copernicus when enabled."""
        service = MetocFusionService(FakeMarineClient(), FakeWeatherClient(), salinity_enabled=True)
        with patch("services.metoc_fusion.get_copernicus_salinity_density") as mocked:
            mocked.return_value = EnvironmentData(
                sea_surface_salinity_psu=34.4,
                sea_water_density_kg_m3=1024.0,
                salinity_source="copernicus_marine",
            )
            result = service.fetch(13.4, 144.8)
        mocked.assert_called_once()
        self.assertEqual(result.current_speed_kts_mean, 0.5)
        self.assertEqual(result.sea_surface_salinity_psu, 34.4)
        self.assertEqual(result.sea_water_density_kg_m3, 1024.0)

    def test_copernicus_unavailable_does_not_break_fusion(self) -> None:
        """Copernicus failure should preserve Open-Meteo values and clean fallback status."""
        service = MetocFusionService(FakeMarineClient(), FakeWeatherClient(), salinity_enabled=True)
        with patch("services.metoc_fusion.get_copernicus_salinity_density") as mocked:
            mocked.return_value = EnvironmentData(
                salinity_source="copernicus_unavailable",
                salinity_error="Copernicus Marine toolbox is not installed.",
            )
            result = service.fetch(13.4, 144.8)
        self.assertEqual(result.current_speed_kts_mean, 0.5)
        self.assertIsNone(result.sea_surface_salinity_psu)
        self.assertEqual(result.salinity_source, "copernicus_unavailable")


if __name__ == "__main__":
    unittest.main()
