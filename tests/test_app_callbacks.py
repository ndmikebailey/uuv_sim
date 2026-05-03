"""Gradio callback smoke tests with mocked METOC data."""

from __future__ import annotations

import csv
import json
import shutil
import unittest
from pathlib import Path

import matplotlib.pyplot as plt

import app.main as main
from app.ui.reporting import build_energy_equivalence_rows
from models.environment_model import EnvironmentData
from utils.constants import APP_VERSION, ENERGY_MODEL_VERSION


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

MULTI_AREA_GEOMETRY = {
    "geometry_type": "MultiArea",
    "areas": [
        RECTANGLE_GEOMETRY,
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

    def _executive_summary_text(self, html: object) -> str:
        """Extract the compact executive summary block for report contract checks."""
        text = str(html)
        start = text.index("Executive Results Summary")
        end = text.index("decision-kpi-grid", start)
        return text[start:end]

    def test_search_geometry_report_outputs_and_run_record_traceability(self) -> None:
        """ISR area geometry should run as endurance patrols and preserve traceability."""
        for geometry in [RECTANGLE_GEOMETRY, CONVEX_POLYGON_GEOMETRY, CONCAVE_POLYGON_GEOMETRY]:
            with self.subTest(geometry=geometry["geometry_type"]):
                _, result = self._run_isr_geometry(geometry)
                self.assertEqual(len(result), 14)
                self.assertIn("Estimated ISR endurance", str(result[0]))
                self.assertIn("view-results-btn active", str(result[1]))
                self.assertIn("isr_loop_distance_km", result[10])
                self.assertIn("Mission Decision Brief", str(result[11]))
                self.assertIn("BLUF", str(result[11]))
                self.assertLess(str(result[11]).index("BLUF"), str(result[11]).index("Executive Results Summary"))
                self.assertLess(str(result[11]).index("Executive Results Summary"), str(result[11]).index("Technical Traceability / Model Detail"))
                self.assertIn("Technical Traceability / Model Detail", str(result[11]))
                self.assertIn("Patrol loop distance", str(result[11]))
                self.assertIn("Endurance per set", str(result[11]))
                executive_summary = self._executive_summary_text(result[11])
                self.assertIn("100 Monte Carlo trials", executive_summary)
                self.assertIn("using deterministic seed 12345", executive_summary)
                self.assertIn("ISR persistence", executive_summary)
                self.assertIn("patrol-loop endurance", executive_summary)
                self.assertIn("P50", executive_summary)
                self.assertIn("P80", executive_summary)
                self.assertIn("P95", executive_summary)
                self.assertNotIn("None", executive_summary)
                self.assertNotIn("Battery sets P80", str(result[11]))
                self.assertNotIn("Battery sets P95", str(result[11]))
                self.assertNotIn("Available battery inventory", str(result[11]))
                self.assertIn("Conservative mission energy estimate (P95)", str(result[12]))
                self.assertIn("Barrel-of-oil equivalent", str(result[12]))
                self.assertEqual(result[8]["visible"], True)
                self.assertEqual(result[9]["visible"], False)
                csv_files = sorted(Path("runs").glob("*_energy_planner.csv"))
                self.assertTrue(csv_files)
                with csv_files[-1].open(newline="", encoding="utf-8") as handle:
                    record = next(csv.DictReader(handle))
                self.assertEqual(record["app_version"], APP_VERSION)
                self.assertEqual(record["model_version"], ENERGY_MODEL_VERSION)
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
        self.assertIn("Mission Decision Brief", str(result[11]))
        self.assertIn("Search/MCM planning", str(result[11]))
        executive_summary = self._executive_summary_text(result[11])
        self.assertIn("Executive Results Summary", executive_summary)
        self.assertIn("mission-total energy", executive_summary)
        self.assertIn("planning energy demand", executive_summary)
        self.assertIn("conservative demand", executive_summary)
        self.assertIn("battery sufficiency driven primarily by", executive_summary)
        self.assertNotIn("None", executive_summary)
        self.assertIn("Battery sets P80", str(result[11]))
        self.assertIn("Battery sets P95", str(result[11]))
        self.assertIn("Conservative mission energy estimate (P95)", str(result[12]))
        self.assertEqual(result[8]["visible"], True)
        self.assertEqual(result[9]["visible"], False)
        self.assertNotIn("isr_loop_distance_km", result[10])

    def test_multi_area_search_report_includes_area_and_metoc_counts(self) -> None:
        """Multi-area Search/MCM should report aggregate area and METOC sample count."""
        built = main.build_mission_and_prefill("Area Search / MCM", json.dumps(MULTI_AREA_GEOMETRY))
        self.assertTrue(built[0], built[1])
        loaded_text = main.context_markdown(built[0])
        self.assertIn("Multi-area search plan", loaded_text)
        self.assertIn("METOC sampled points:** 2", loaded_text)
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
        summary = result[10]
        self.assertEqual(summary["number_of_search_areas"], 2)
        self.assertEqual(summary["metoc_sample_count"], 2)
        self.assertEqual(summary["metoc_aggregation_method"], "area-centroid vector average")
        self.assertGreater(summary["total_search_area_km2"], 0.0)
        self.assertIn("Number of search areas", str(result[4]))
        self.assertIn("METOC sampled points", str(result[4]))
        self.assertIn("uses 2 selected search area", str(result[11]))

    def test_isr_reports_single_set_and_total_inventory_endurance(self) -> None:
        """ISR should distinguish installed-set endurance from total available inventory."""
        built = main.build_mission_and_prefill("ISR", json.dumps(RECTANGLE_GEOMETRY))
        self.assertTrue(built[0], built[1])
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
            3,
            True,
            1,
            "12345",
            0.6,
            85,
            26,
            built[0],
        )
        summary = result[10]
        self.assertIn("isr_single_set_endurance_hr", summary)
        self.assertIn("isr_total_inventory_endurance_hr", summary)
        self.assertIn("isr_completed_loops_single_set", summary)
        self.assertIn("isr_completed_loops_total_inventory", summary)
        self.assertIn("isr_completed_loops_full_single_set", summary)
        self.assertIn("isr_partial_loop_distance_km_single_set", summary)
        self.assertIn("isr_total_patrol_distance_km_single_set", summary)
        self.assertIn("isr_total_patrol_distance_km_total_inventory", summary)
        self.assertGreaterEqual(
            summary["isr_completed_loops_total_inventory"],
            summary["isr_completed_loops_single_set"],
        )
        self.assertGreaterEqual(
            summary["isr_total_patrol_distance_km_single_set"],
            summary["isr_completed_loops_full_single_set"] * summary["isr_loop_distance_km"],
        )
        self.assertIn("One installed set supports", str(result[11]))
        self.assertIn("Feasible", str(result[11]))
        self.assertNotIn("Not feasible", str(result[11]))
        executive_summary = self._executive_summary_text(result[11])
        self.assertIn("100 Monte Carlo trials", executive_summary)
        self.assertIn("using deterministic seed 12345", executive_summary)
        self.assertIn("ISR persistence", executive_summary)
        self.assertIn("patrol-loop endurance", executive_summary)
        self.assertIn("one installed set supports", executive_summary)
        self.assertNotIn("None", executive_summary)
        self.assertIn("Patrol loop distance", str(result[11]))
        self.assertIn("Endurance per set", str(result[11]))
        self.assertIn("Recovery/swap", str(result[11]))
        self.assertNotIn("Battery sets P80", str(result[11]))
        self.assertNotIn("Battery sets P95", str(result[11]))
        self.assertIn("before recovery/swap", str(result[11]))
        self.assertIn("Total available inventory supports", str(result[11]))
        self.assertIn("before battery exhaustion", str(result[11]))
        self.assertNotIn("completed patrol loop(s)", str(result[11]))
        self.assertIn("plus", str(result[11]))
        self.assertIn("Total patrol distance before recovery/swap", str(result[11]))
        self.assertIn("Total patrol distance before battery exhaustion", str(result[11]))
        self.assertGreater(len(result[7].axes[0].patches), 0)
        self.assertIn("ISR Mission Energy Uncertainty Distribution", result[7].axes[0].get_title())
        self.assertGreater(len(result[6].axes[0].collections), 0)

    def test_report_css_supports_full_width_metoc(self) -> None:
        """METOC assessment should use full-width responsive card-grid styling."""
        css = main.CUSTOM_CSS
        self.assertIn(".metoc-assessment", css)
        self.assertIn("max-width: none", css)
        self.assertIn("repeat(auto-fit, minmax(220px, 1fr))", css)
        html = main.metoc_html(EnvironmentData(), main.METOC_SERVICE)
        self.assertIn("metoc-assessment", html)
        self.assertIn("metoc-card-grid", html)

    def test_small_energy_equivalents_do_not_round_to_zero(self) -> None:
        """Small secondary equivalence values should retain useful precision."""
        rows = dict(build_energy_equivalence_rows(3.8, "test basis"))
        self.assertRegex(rows["Gigajoules"], r"0\.014 GJ")
        self.assertRegex(rows["Tonnes of oil equivalent"], r"0\.000327 TOE")
        self.assertRegex(rows["Barrel-of-oil equivalent"], r"0\.002235 BOE")

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
        self.assertIn("Mission Decision Brief", str(payload_run[11]))
        self.assertIn("Technical Traceability / Model Detail", str(payload_run[11]))
        self.assertLess(str(payload_run[11]).index("BLUF"), str(payload_run[11]).index("Executive Results Summary"))
        self.assertLess(str(payload_run[11]).index("Executive Results Summary"), str(payload_run[11]).index("Technical Traceability / Model Detail"))
        self.assertIn("Energy Detail", str(payload_run[2]))
        self.assertIn("Battery and Sustainment Detail", str(payload_run[3]))
        self.assertIn("Sustainment Projection Lens", str(payload_run[3]))
        self.assertIn("Single mission default", str(payload_run[3]))
        self.assertIn("Mission Geometry Detail", str(payload_run[4]))
        self.assertIn("Environmental Detail", str(payload_run[5]))
        self.assertIn("METOC Assessment", str(payload_run[13]))
        self.assertIn("Energy Storage Equivalence Lens", str(payload_run[12]))
        self.assertIn("Payload mission planning", str(payload_run[11]))
        executive_summary = self._executive_summary_text(payload_run[11])
        self.assertIn("Executive Results Summary", executive_summary)
        self.assertIn("100 Monte Carlo trials", executive_summary)
        self.assertIn("using deterministic seed 12345", executive_summary)
        self.assertIn("mission-total energy", executive_summary)
        self.assertIn("planning energy demand", executive_summary)
        self.assertIn("conservative demand", executive_summary)
        self.assertIn("P50", executive_summary)
        self.assertIn("P80", executive_summary)
        self.assertIn("P95", executive_summary)
        self.assertNotIn("None", executive_summary)
        self.assertIn("Planning energy P80", str(payload_run[11]))
        self.assertIn("Conservative energy P95", str(payload_run[11]))
        self.assertIn("Battery sets P80", str(payload_run[11]))
        self.assertIn("Battery sets P95", str(payload_run[11]))
        self.assertNotIn("dry-weight", str(payload_run[4]).lower())
        self.assertNotIn("dry weight", str(payload_run[4]).lower())
        self.assertIn("Kilocalories", str(payload_run[12]))
        self.assertIn("Gigajoules", str(payload_run[12]))
        self.assertNotIn("0.0 GJ", str(payload_run[12]))
        self.assertEqual(payload_run[8]["visible"], True)
        self.assertIsNotNone(payload_run[8]["value"])
        self.assertIn("Mission Visual Summary", "Mission Visual Summary")
        payload_legend = payload_run[8]["value"].axes[0].get_legend()
        self.assertIsNotNone(payload_legend)
        self.assertIn("Current vector", [text.get_text() for text in payload_legend.get_texts()])
        self.assertNotIn("Current", [text.get_text() for text in payload_run[8]["value"].axes[0].texts])
        self.assertEqual(payload_run[9]["visible"], False)
        self.assertEqual(payload_run[10]["sustainment_planning_weeks"], 1.0)
        self.assertEqual(payload_run[10]["sustainment_total_missions"], 1.0)

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
        isr_legend = isr_run[8]["value"].axes[0].get_legend()
        self.assertIsNotNone(isr_legend)
        isr_labels = [text.get_text() for text in isr_legend.get_texts()]
        self.assertIn("ISR patrol route", isr_labels)
        self.assertIn("Current vector", isr_labels)
        self.assertNotIn("Return leg", isr_labels)
        self.assertEqual(isr_run[9]["visible"], False)

    def test_view_results_button_calls_results_tab_helper(self) -> None:
        """Active shortcut should use the robust Results/Report tab helper."""
        self.assertIn("goToResultsTab()", main.ACTIVE_RESULTS_BUTTON_HTML)
        self.assertIn('window.goToResultsTab = function goToResultsTab()', main.CUSTOM_JS)
        self.assertIn('findTabByText(["results", "report"])', main.CUSTOM_JS)
        self.assertIn("scrollIntoView", main.CUSTOM_JS)
        self.assertIn("window.goToSimulatorTab = function goToSimulatorTab()", main.CUSTOM_JS)
        self.assertIn("Load Mission and Go to Simulator", Path("app/main.py").read_text(encoding="utf-8"))
        self.assertIn("BUILD_MISSION_AND_GO_JS", Path("app/main.py").read_text(encoding="utf-8"))
        self.assertIn("Now that mission parameters are set, go to UUV simulation.", Path("app/main.py").read_text(encoding="utf-8"))
        self.assertIn("Go to Results tab. Your simulation is ready.", main.ACTIVE_RESULTS_BUTTON_HTML)
        self.assertNotIn("Energy Planner CSV Export", Path("app/main.py").read_text(encoding="utf-8"))
        self.assertNotIn("Manual salinity", Path("app/main.py").read_text(encoding="utf-8"))

    def test_loaded_mission_text_is_mode_specific(self) -> None:
        """Loaded mission text should avoid payload/ISR centroid and search leakage."""
        payload = main.build_mission_and_prefill("Payload Delivery", json.dumps(LINE_GEOMETRY))
        payload_text = main.context_markdown(payload[0])
        self.assertIn("Mission loaded:** Payload Delivery", payload_text)
        self.assertIn("Geometry:** Route", payload_text)
        self.assertIn("METOC lookup point:** route midpoint", payload_text)
        self.assertIn("Now that mission parameters are set, go to UUV simulation.", payload_text)
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

    def test_sustainment_projection_controls_are_optional(self) -> None:
        """Sustainment projection inputs should stay hidden until requested."""
        hidden = main.sustainment_projection_visibility(False)
        shown = main.sustainment_projection_visibility(True)
        self.assertEqual(hidden["visible"], False)
        self.assertEqual(shown["visible"], True)

    def test_default_run_reports_single_mission_projection(self) -> None:
        """Unchecked sustainment lens should force a one-mission, one-week default."""
        result = main.run_from_ui(
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
            "",
            0.5,
            90,
            25,
            {},
            "Medium",
            5,
            "1 month",
            0.84,
            0,
        )
        self.assertIn("Single mission default", str(result[3]))
        self.assertEqual(result[10]["sustainment_missions_per_week"], 1.0)
        self.assertEqual(result[10]["sustainment_planning_weeks"], 1.0)
        self.assertEqual(result[10]["sustainment_total_missions"], 1.0)

    def test_enabled_sustainment_projection_uses_operator_values(self) -> None:
        """Checked sustainment lens should use the editable projection values."""
        result = main.run_from_ui(
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
            "",
            0.5,
            90,
            25,
            {},
            "Medium",
            2,
            "1 month",
            0.84,
            0,
            True,
        )
        self.assertIn("Optional mission projection lens", str(result[3]))
        self.assertEqual(result[10]["sustainment_missions_per_week"], 2.0)
        self.assertEqual(result[10]["sustainment_planning_weeks"], 4.0)
        self.assertEqual(result[10]["sustainment_total_missions"], 8.0)

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

    def test_standalone_simulation_uses_standard_salinity_assumption(self) -> None:
        """Manual standalone simulation should not imply live salinity lookup."""
        result = main.run_from_ui(
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
            "",
            0.5,
            90,
            25,
            {},
            "Medium",
            1,
            "1 month",
            0.84,
            0,
        )
        self.assertIn("standard_assumption", str(result[5]))
        self.assertIn("standard seawater assumption used", str(result[5]))
        executive_summary = self._executive_summary_text(result[11])
        self.assertIn("without a fixed deterministic seed", executive_summary)
        self.assertNotIn("None", executive_summary)


if __name__ == "__main__":
    unittest.main()
