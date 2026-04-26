"""Gradio callback smoke tests with mocked METOC data."""

from __future__ import annotations

import csv
import json
import shutil
import unittest
from pathlib import Path

import matplotlib.pyplot as plt

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
        plt.close("all")
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
            5,
            "12345",
            0.6,
            85,
            26,
            context,
        )
        return context, result

    def test_search_geometry_report_outputs_and_run_record_traceability(self) -> None:
        """ISR area geometry should run as endurance patrols and preserve traceability."""
        for geometry in [RECTANGLE_GEOMETRY, CONVEX_POLYGON_GEOMETRY, CONCAVE_POLYGON_GEOMETRY]:
            with self.subTest(geometry=geometry["geometry_type"]):
                _, result = self._run_isr_geometry(geometry)
                self.assertEqual(len(result), 14)
                self.assertIn("Estimated ISR endurance", str(result[0]))
                self.assertIn("view-results-btn active", str(result[1]))
                self.assertIn("isr_loop_distance_km", result[10])
                self.assertIn("Energy Planner Summary", str(result[11]))
                self.assertIn("Conservative planning energy", str(result[11]))
                self.assertIn("Environmental burden", str(result[11]))
                self.assertIn("Planning note", str(result[11]))
                self.assertNotIn("Energy demand", str(result[11]))
                self.assertNotIn("Available battery inventory", str(result[11]))
                self.assertEqual(result[12].iloc[0]["Value"], "Conservative mission energy estimate (P95)")
                self.assertIn("Barrel-of-oil equivalent", result[12]["Metric"].tolist())
                self.assertEqual(result[8]["visible"], True)
                self.assertEqual(result[9]["visible"], False)
                csv_files = sorted(Path("runs").glob("*_energy_planner.csv"))
                self.assertTrue(csv_files)
                with csv_files[-1].open(newline="", encoding="utf-8") as handle:
                    record = next(csv.DictReader(handle))
                self.assertEqual(record["app_version"], "v3.1-beta-dev")
                self.assertEqual(record["model_version"], "energy_model_v3_1_beta_dev")
                self.assertTrue(record["vehicle_catalog_version"])
                self.assertTrue(record["metoc_lookup_lat"])
                self.assertTrue(record["metoc_lookup_lon"])
                self.assertTrue(record["isr_loop_distance_km"])
                self.assertIn("energy_planner", str(csv_files[-1]))

    def test_area_search_reports_search_orientation(self) -> None:
        """Area Search / MCM should remain the swath-search mission mode."""
        built = main.build_mission_and_prefill("Area Search / MCM", json.dumps(RECTANGLE_GEOMETRY))
        self.assertTrue(built[0], built[1])
        result = main.run_from_ui(
            "REMUS 300 - 4.5 kWh",
            "Area Search / MCM",
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
            built[0],
        )
        self.assertIn("Recommended track orientation", str(result[0]))
        self.assertIn("Energy Planner Summary", str(result[11]))
        self.assertIn("Search/MCM planning", str(result[11]))
        self.assertEqual(result[12].iloc[0]["Value"], "Conservative mission energy estimate (P95)")
        self.assertEqual(result[8]["visible"], True)
        self.assertEqual(result[9]["visible"], False)
        self.assertNotIn("isr_loop_distance_km", result[10])

    def test_payload_line_runs_and_isr_accepts_line_geometry(self) -> None:
        """Payload and ISR should both accept line geometry with different mission logic."""
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
        self.assertEqual(len(payload_run), 14)
        self.assertNotIn("Recommended track orientation", str(payload_run[0]))
        self.assertIn("view-results-btn active", str(payload_run[1]))
        self.assertIn("Energy Planner Summary", str(payload_run[11]))
        self.assertIn("Payload mission planning", str(payload_run[11]))
        self.assertIn("Conservative planning energy", str(payload_run[11]))
        self.assertIn("Kilocalories", payload_run[12]["Metric"].tolist())
        self.assertEqual(payload_run[8]["visible"], True)
        self.assertEqual(payload_run[9]["visible"], False)

        isr_line = main.build_mission_and_prefill("ISR", json.dumps(LINE_GEOMETRY))
        self.assertTrue(isr_line[0], isr_line[1])
        isr_run = main.run_from_ui(
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
            5,
            "12345",
            0.6,
            85,
            26,
            isr_line[0],
        )
        self.assertIn("Estimated ISR endurance", str(isr_run[0]))
        self.assertEqual(isr_run[10]["isr_patrol_geometry"], "line")
        self.assertEqual(isr_run[10]["mission_sequences"], 1)
        self.assertEqual(isr_run[8]["visible"], True)
        self.assertEqual(isr_run[9]["visible"], False)

    def test_view_results_button_calls_results_tab_helper(self) -> None:
        """Active shortcut should use the robust Results/Report tab helper."""
        self.assertIn("goToResultsTab()", main.ACTIVE_RESULTS_BUTTON_HTML)
        self.assertIn("text.includes(\"results\") || text.includes(\"report\")", main.CUSTOM_JS)
        self.assertIn("window.goToResultsTab = goToResultsTab", main.CUSTOM_JS)
        self.assertNotIn("Energy Planner CSV Export", Path("app/main.py").read_text(encoding="utf-8"))

    def test_loaded_mission_text_is_mode_specific(self) -> None:
        """Loaded mission text should avoid payload/ISR centroid and search leakage."""
        payload = main.build_mission_and_prefill("Payload Delivery", json.dumps(LINE_GEOMETRY))
        payload_text = main.context_markdown(payload[0])
        self.assertIn("Mission loaded:** Payload Delivery", payload_text)
        self.assertIn("Geometry:** Route", payload_text)
        self.assertIn("METOC lookup point:** route midpoint", payload_text)
        self.assertNotIn("Centroid", payload_text)
        self.assertNotIn("ISR", payload_text)

        isr_line = main.build_mission_and_prefill("ISR", json.dumps(LINE_GEOMETRY))
        isr_line_text = main.context_markdown(isr_line[0])
        self.assertIn("Geometry:** Line patrol", isr_line_text)
        self.assertIn("Out-and-back patrol loop distance", isr_line_text)
        self.assertIn("METOC lookup point:** first route point", isr_line_text)
        self.assertNotIn("Route distance:** N/A", isr_line_text)
        self.assertNotIn("Centroid", isr_line_text)

        isr_polygon = main.build_mission_and_prefill("ISR", json.dumps(CONVEX_POLYGON_GEOMETRY))
        isr_polygon_text = main.context_markdown(isr_polygon[0])
        self.assertIn("perimeter patrol", isr_polygon_text)
        self.assertIn("Patrol loop distance", isr_polygon_text)
        self.assertIn("METOC lookup point:** first patrol point", isr_polygon_text)
        self.assertIn("reference only", isr_polygon_text)
        self.assertNotIn("Route distance:** N/A", isr_polygon_text)
        self.assertNotIn("Centroid", isr_polygon_text)

    def test_mission_input_visibility_separates_modes(self) -> None:
        """Search, payload, and ISR groups should be mutually exclusive."""
        search_update, payload_update, isr_update, sequence_update = main.mission_input_visibility("Payload Delivery")
        self.assertEqual(search_update["visible"], False)
        self.assertEqual(payload_update["visible"], True)
        self.assertEqual(isr_update["visible"], False)
        self.assertEqual(sequence_update["visible"], True)

        search_update, payload_update, isr_update, sequence_update = main.mission_input_visibility("ISR")
        self.assertEqual(search_update["visible"], False)
        self.assertEqual(payload_update["visible"], False)
        self.assertEqual(isr_update["visible"], True)
        self.assertEqual(sequence_update["visible"], False)
        self.assertEqual(sequence_update["value"], 1)

        search_update, payload_update, isr_update, sequence_update = main.mission_input_visibility("Area Search / MCM")
        self.assertEqual(search_update["visible"], True)
        self.assertEqual(payload_update["visible"], False)
        self.assertEqual(isr_update["visible"], False)
        self.assertEqual(sequence_update["visible"], True)

    def test_manual_search_area_derives_square_dimensions(self) -> None:
        """No-context manual area should control search dimensions."""
        _, area, _ = main._area_environment_from_state("Area Search / MCM", 50, 3, 3, 10, 0, 0.5, 90, 25, {})
        self.assertAlmostEqual(area.width_km or 0.0, 50 ** 0.5)
        self.assertAlmostEqual(area.height_km or 0.0, 50 ** 0.5)
        self.assertEqual(area.area_km2, 50)

    def test_manual_isr_uses_patrol_rectangle_defaults(self) -> None:
        """No-context ISR should use a perimeter patrol rectangle, not search lanes."""
        _, area, _ = main._area_environment_from_state("ISR", 50, 3, 4, 10, 0, 0.5, 90, 25, {})
        self.assertEqual(area.geometry_type, "rectangle")
        self.assertEqual(area.width_km, 3)
        self.assertEqual(area.height_km, 4)

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
        self.assertIn("view-results-btn disabled", str(result[1]))


if __name__ == "__main__":
    unittest.main()
