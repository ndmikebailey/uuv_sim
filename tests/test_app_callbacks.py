"""Gradio callback smoke tests with mocked METOC data."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

import app.main as main
from models.environment_model import EnvironmentData


class FakeMetocService:
    """Deterministic METOC service for app callback tests."""

    def fetch(self, lat: float, lon: float) -> EnvironmentData:
        """Return stable environment data while preserving query traceability."""
        return EnvironmentData(
            current_speed_kts_mean=0.6,
            current_direction_deg_mean=85.0,
            sea_surface_temp_c_mean=26.0,
            wind_speed_kts_mean=10.0,
            raw_marine_api_json={"marine": {"lat": lat, "lon": lon}},
            raw_weather_api_json={"weather": {"lat": lat, "lon": lon}},
            marine_query_params={"latitude": lat, "longitude": lon},
            weather_query_params={"latitude": lat, "longitude": lon},
        )

    def assessment(self, environment: EnvironmentData) -> dict[str, object]:
        """Return a minimal stable METOC assessment for report rendering."""
        return {
            "posture": "Favorable",
            "items": [
                ("Current", "Favorable", "green", environment.current_speed_kts_mean, "kts", "Test current assessment."),
                ("Wave / Surf", "Unknown", "gray", environment.wave_height_m, "m", "Test wave assessment."),
                ("Wind", "Favorable", "green", environment.wind_speed_kts_mean, "kts", "Test wind assessment."),
                ("SST / Battery", "Favorable", "green", environment.sea_surface_temp_c_mean, "deg C", "Test temperature assessment."),
                ("Weather", "Unknown", "gray", environment.weather_summary or "N/A", "", "Test weather assessment."),
            ],
        }


RECTANGLE_GEOMETRY = {
    "geometry_type": "rectangle",
    "bounds": {"north": 13.46, "south": 13.44, "east": 144.82, "west": 144.79},
    "vertices": [
        {"lat": 13.44, "lon": 144.79},
        {"lat": 13.44, "lon": 144.82},
        {"lat": 13.46, "lon": 144.82},
        {"lat": 13.46, "lon": 144.79},
    ],
}

CONVEX_POLYGON_GEOMETRY = {
    "geometry_type": "polygon",
    "bounds": {"north": 13.47, "south": 13.44, "east": 144.83, "west": 144.785},
    "vertices": [
        {"lat": 13.44, "lon": 144.79},
        {"lat": 13.44, "lon": 144.83},
        {"lat": 13.47, "lon": 144.82},
        {"lat": 13.465, "lon": 144.785},
    ],
}

CONCAVE_POLYGON_GEOMETRY = {
    "geometry_type": "polygon",
    "bounds": {"north": 13.475, "south": 13.44, "east": 144.84, "west": 144.79},
    "vertices": [
        {"lat": 13.44, "lon": 144.79},
        {"lat": 13.44, "lon": 144.84},
        {"lat": 13.465, "lon": 144.825},
        {"lat": 13.455, "lon": 144.81},
        {"lat": 13.475, "lon": 144.79},
    ],
}

LINE_GEOMETRY = {
    "geometry_type": "line",
    "route_points": [
        {"lat": 13.44, "lon": 144.79},
        {"lat": 13.46, "lon": 144.82},
    ],
    "vertices": [
        {"lat": 13.44, "lon": 144.79},
        {"lat": 13.46, "lon": 144.82},
    ],
}


class AppCallbackSmokeTests(unittest.TestCase):
    """Smoke-test report-producing app callbacks without live API calls."""

    def setUp(self) -> None:
        """Install deterministic METOC service."""
        self._original_metoc = main.METOC_SERVICE
        main.METOC_SERVICE = FakeMetocService()  # type: ignore[assignment]

    def tearDown(self) -> None:
        """Restore globals and remove generated run artifacts."""
        main.METOC_SERVICE = self._original_metoc
        shutil.rmtree("runs", ignore_errors=True)

    def _run_isr_geometry(self, geometry: dict[str, object]) -> tuple[dict[str, object], tuple[object, ...]]:
        built = main.build_mission_and_prefill("ISR", json.dumps(geometry))
        self.assertTrue(built[0], built[1])
        context = built[0]
        result = main.run_from_ui(
            "REMUS 300 - 4.5 kWh",
            "ISR",
            10,
            3,
            3,
            10,
            0,
            0,
            200,
            True,
            3.5,
            1,
            True,
            1,
            "12345",
            0.6,
            85,
            26,
            context,
        )
        return context, result

    def test_search_geometry_report_outputs_and_run_record_traceability(self) -> None:
        """Rectangle, convex polygon, and concave polygon should all run and render report figures."""
        for geometry in [RECTANGLE_GEOMETRY, CONVEX_POLYGON_GEOMETRY, CONCAVE_POLYGON_GEOMETRY]:
            with self.subTest(geometry=geometry["geometry_type"]):
                _, result = self._run_isr_geometry(geometry)
                self.assertEqual(len(result), 12)
                self.assertIn("Recommended track orientation", str(result[0]))
                self.assertIsNotNone(result[5])
                self.assertIsNotNone(result[6])
                record = json.loads(Path(str(result[10])).read_text(encoding="utf-8"))
                self.assertEqual(record["app_version"], "v3.0-alpha")
                self.assertEqual(record["model_version"], "energy_model_v3_0_alpha")
                self.assertTrue(record["raw_marine_api_json"])
                self.assertTrue(record["raw_weather_api_json"])
                self.assertTrue(record["marine_query_params"])
                self.assertTrue(record["weather_query_params"])

    def test_payload_line_runs_and_isr_rejects_line_geometry(self) -> None:
        """Payload route geometry should run for payload missions and reject ISR loading."""
        payload = main.build_mission_and_prefill("Payload Delivery", json.dumps(LINE_GEOMETRY))
        self.assertTrue(payload[0], payload[1])
        payload_run = main.run_from_ui(
            "REMUS 300 - 4.5 kWh",
            "Payload Delivery",
            10,
            3,
            3,
            10,
            0,
            0,
            200,
            True,
            3.5,
            1,
            True,
            1,
            "12345",
            0.6,
            85,
            26,
            payload[0],
        )
        self.assertEqual(len(payload_run), 12)
        self.assertNotIn("Recommended track orientation", str(payload_run[0]))

        rejected = main.build_mission_and_prefill("ISR", json.dumps(LINE_GEOMETRY))
        self.assertFalse(rejected[0])
        self.assertIn("requires a rectangle or polygon", rejected[1])

    def test_manual_search_area_derives_square_dimensions(self) -> None:
        """No-context manual area should control search dimensions."""
        _, area, _ = main._area_environment_from_state("ISR", 50, 3, 3, 10, 0, 0.5, 90, 25, {})
        self.assertAlmostEqual(area.width_km or 0.0, 50 ** 0.5)
        self.assertAlmostEqual(area.height_km or 0.0, 50 ** 0.5)
        self.assertEqual(area.area_km2, 50)

    def test_invalid_seed_is_returned_to_operator(self) -> None:
        """Invalid UI seed text should not silently become seed zero."""
        result = main.run_from_ui(
            "REMUS 300 - 4.5 kWh",
            "ISR",
            10,
            3,
            3,
            10,
            0,
            0,
            200,
            True,
            3.5,
            1,
            True,
            1,
            "abc",
            0.5,
            90,
            25,
            {},
        )
        self.assertTrue(str(result[0]).startswith("Invalid seed"))


if __name__ == "__main__":
    unittest.main()
