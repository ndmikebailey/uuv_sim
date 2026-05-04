"""Gradio callback smoke tests with mocked METOC data."""

from __future__ import annotations

import csv
import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

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
                self.assertEqual(len(result), 15)
                self.assertIn("Estimated ISR endurance", str(result[0]))
                self.assertEqual(result[1]["value"], "Go to Results")
                self.assertEqual(result[1]["interactive"], True)
                self.assertIn("isr_loop_distance_km", result[10])
                self.assertAlmostEqual(
                    float(result[10]["isr_total_inventory_endurance_hr"]),
                    float(result[10]["isr_single_set_endurance_hr"]),
                    places=6,
                )
                self.assertAlmostEqual(
                    float(result[10]["isr_total_patrol_distance_km_total_inventory"]),
                    float(result[10]["isr_total_patrol_distance_km_single_set"]),
                    places=6,
                )
                self.assertIn("Mission Decision Brief", str(result[11]))
                self.assertIn("BLUF", str(result[11]))
                self.assertLess(str(result[11]).index("BLUF"), str(result[11]).index("Executive Results Summary"))
                self.assertLess(str(result[11]).index("Executive Results Summary"), str(result[11]).index("Technical Traceability / Model Detail"))
                self.assertIn("Technical Traceability / Model Detail", str(result[11]))
                self.assertIn("Patrol loop distance", str(result[11]))
                self.assertIn("Endurance per set", str(result[11]))
                executive_summary = self._executive_summary_text(result[11])
                self.assertLess(executive_summary.index("The modeled ISR mission"), executive_summary.index("Monte Carlo"))
                self.assertIn("100 Monte Carlo trials", executive_summary)
                self.assertIn("using deterministic seed 12345", executive_summary)
                self.assertIn("mission-total endurance case", executive_summary)
                self.assertIn("kWh per loop", executive_summary)
                self.assertIn("percentile outputs are retained in technical traceability", executive_summary)
                self.assertIn("Monte Carlo runs", str(result[11]))
                self.assertIn("Percentile output definitions", str(result[11]))
                self.assertNotIn("None", executive_summary)
                self.assertNotIn("Battery sets P80", str(result[11]))
                self.assertNotIn("Battery sets P95", str(result[11]))
                self.assertNotIn("Available battery inventory", str(result[11]))
                self.assertIn("Conservative mission energy estimate (P95)", str(result[12]))
                self.assertIn("Barrel-of-oil equivalent", str(result[12]))
                self.assertEqual(result[8]["visible"], True)
                self.assertEqual(result[9]["visible"], True)
                self.assertIn("Mission Map Overlay", str(result[9]["value"]))
                self.assertIn("report-visual-card report-map-card", str(result[9]["value"]))
                self.assertIn("uuv-report-map-overlay", str(result[9]["value"]))
                self.assertIn("Engineering Snapshot", result[8]["value"].axes[0].get_title())
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
        self.assertIn("Feasible. The selected platform can complete the search/MCM plan", str(result[11]))
        self.assertNotIn("Search/MCM planning", str(result[11]))
        executive_summary = self._executive_summary_text(result[11])
        self.assertIn("Executive Results Summary", executive_summary)
        self.assertLess(executive_summary.index("The modeled search/MCM mission"), executive_summary.index("Monte Carlo"))
        self.assertIn("Planning energy is", executive_summary)
        self.assertIn("conservative energy is", executive_summary)
        self.assertIn("route/track current burden", executive_summary)
        self.assertNotIn("None", executive_summary)
        self.assertIn("Battery sets P80", str(result[11]))
        self.assertIn("Battery sets P95", str(result[11]))
        self.assertNotIn("METOC risk", str(result[11]))
        self.assertIn("Conservative mission energy estimate (P95)", str(result[12]))
        self.assertEqual(result[8]["visible"], True)
        self.assertEqual(result[9]["visible"], True)
        self.assertIn("Mission Map Overlay", str(result[9]["value"]))
        self.assertIn("report-map-card", str(result[9]["value"]))
        search_ax = result[8]["value"].axes[0]
        self.assertIn("Engineering Snapshot - Search Area", search_ax.get_title())
        self.assertNotIn("Swath/track spacing", " ".join(text.get_text() for text in search_ax.texts))
        search_legend = search_ax.get_legend()
        self.assertIsNotNone(search_legend)
        search_labels = [text.get_text() for text in search_legend.get_texts()]
        self.assertIn("Search area", " ".join(search_labels))
        self.assertIn("Search lanes", search_labels)
        self.assertIn("Current vector", search_labels)
        self.assertIn("Area:", str(result[14]))
        self.assertIn("Track spacing:", str(result[14]))
        self.assertIn("Orientation:", str(result[14]))
        self.assertIn("Lanes:", str(result[14]))
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
        self.assertIn("section-insight-card", str(result[4]))

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
        self.assertGreater(
            summary["isr_total_inventory_endurance_hr"],
            summary["isr_single_set_endurance_hr"],
        )
        self.assertGreaterEqual(
            summary["isr_completed_loops_total_inventory"],
            summary["isr_completed_loops_single_set"],
        )
        self.assertGreater(
            summary["isr_total_patrol_distance_km_total_inventory"],
            summary["isr_total_patrol_distance_km_single_set"],
        )
        self.assertGreaterEqual(
            summary["isr_total_patrol_distance_km_single_set"],
            summary["isr_completed_loops_full_single_set"] * summary["isr_loop_distance_km"],
        )
        self.assertIn("One installed set supports", str(result[11]))
        self.assertIn("declared inventory supports", str(result[11]))
        self.assertIn("Feasible", str(result[11]))
        self.assertNotIn("Not feasible", str(result[11]))
        executive_summary = self._executive_summary_text(result[11])
        self.assertLess(executive_summary.index("The modeled ISR mission"), executive_summary.index("Monte Carlo"))
        self.assertIn("100 Monte Carlo trials", executive_summary)
        self.assertIn("using deterministic seed 12345", executive_summary)
        self.assertIn("mission-total endurance case", executive_summary)
        self.assertIn("declared inventory supports", executive_summary)
        self.assertNotIn("None", executive_summary)
        self.assertNotIn("ISR persistence planning", str(result[11]))
        self.assertNotIn("patrol loop distance is", str(result[11]))
        self.assertIn("Patrol loop distance", str(result[11]))
        self.assertIn("Endurance per set", str(result[11]))
        self.assertIn("Recovery/swap", str(result[11]))
        self.assertNotIn("Battery sets P80", str(result[11]))
        self.assertNotIn("Battery sets P95", str(result[11]))
        self.assertIn("sequential recovery/swap", str(result[11]))
        self.assertNotIn("completed patrol loop(s)", str(result[11]))
        self.assertIn("Total patrol distance per installed set", str(result[4]))
        self.assertIn("Total patrol distance using total inventory", str(result[4]))
        self.assertIn("section-insight-card", str(result[4]))
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
        fuel_rows = dict(build_energy_equivalence_rows(3.8, "test basis", 0.38))
        self.assertEqual(fuel_rows["Fuel-equivalent estimate"], "0.38 gal JP-8/diesel")

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
        self.assertEqual(len(payload_run), 15)
        self.assertNotIn("Recommended track orientation", str(payload_run[0]))
        self.assertEqual(payload_run[1]["value"], "Go to Results")
        self.assertEqual(payload_run[1]["interactive"], True)
        self.assertIn("Mission Decision Brief", str(payload_run[11]))
        self.assertIn("Technical Traceability / Model Detail", str(payload_run[11]))
        self.assertLess(str(payload_run[11]).index("BLUF"), str(payload_run[11]).index("Executive Results Summary"))
        self.assertLess(str(payload_run[11]).index("Executive Results Summary"), str(payload_run[11]).index("Technical Traceability / Model Detail"))
        self.assertIn("Energy Detail", str(payload_run[2]))
        self.assertIn("section-insight-card", str(payload_run[2]))
        self.assertIn("report-table", str(payload_run[2]))
        self.assertIn("Battery and Sustainment Detail", str(payload_run[3]))
        self.assertIn("Sustainment Projection Lens", str(payload_run[3]))
        self.assertIn("mini-bar", str(payload_run[3]))
        self.assertIn("report-table", str(payload_run[3]))
        self.assertIn("Single mission default", str(payload_run[3]))
        self.assertIn("Mission Geometry Detail", str(payload_run[4]))
        self.assertIn("section-insight-card", str(payload_run[4]))
        self.assertIn("Environmental Detail", str(payload_run[5]))
        self.assertIn("fixed-scale-gauge", str(payload_run[5]))
        self.assertIn("Total environmental burden:", str(payload_run[5]))
        self.assertNotIn("width:100.0%", str(payload_run[5]))
        self.assertIn("report-table", str(payload_run[5]))
        self.assertIn("METOC Assessment", str(payload_run[13]))
        self.assertIn("Energy Storage Equivalence Lens", str(payload_run[12]))
        self.assertNotIn("Payload mission planning", str(payload_run[11]))
        executive_summary = self._executive_summary_text(payload_run[11])
        self.assertIn("Executive Results Summary", executive_summary)
        self.assertLess(executive_summary.index("The modeled payload mission"), executive_summary.index("Monte Carlo"))
        self.assertIn("100 Monte Carlo trials", executive_summary)
        self.assertIn("using deterministic seed 12345", executive_summary)
        self.assertIn("Planning energy is", executive_summary)
        self.assertIn("conservative energy is", executive_summary)
        self.assertIn("return transit distance and route current", executive_summary)
        self.assertIn("Return-to-start planning increases modeled distance", executive_summary)
        self.assertIn("Percentile output definitions", str(payload_run[11]))
        self.assertNotIn("None", executive_summary)
        self.assertIn("Planning energy P80", str(payload_run[11]))
        self.assertIn("Conservative energy P95", str(payload_run[11]))
        self.assertIn("Battery sets P80", str(payload_run[11]))
        self.assertIn("Battery sets P95", str(payload_run[11]))
        self.assertNotIn("METOC risk", str(payload_run[11]))
        self.assertNotIn("dry-weight", str(payload_run[4]).lower())
        self.assertNotIn("dry weight", str(payload_run[4]).lower())
        self.assertIn("Kilocalories", str(payload_run[12]))
        self.assertIn("Gigajoules", str(payload_run[12]))
        self.assertNotIn("0.0 GJ", str(payload_run[12]))
        self.assertEqual(payload_run[8]["visible"], True)
        self.assertIsNotNone(payload_run[8]["value"])
        self.assertIn("Engineering Snapshot", payload_run[8]["value"].axes[0].get_title())
        self.assertIn("Mission Map Overlay", str(payload_run[9]["value"]))
        self.assertIn("Current vector", str(payload_run[9]["value"]))
        self.assertIn("METOC point", str(payload_run[9]["value"]))
        payload_legend = payload_run[8]["value"].axes[0].get_legend()
        self.assertIsNotNone(payload_legend)
        self.assertIn("Current vector", [text.get_text() for text in payload_legend.get_texts()])
        self.assertNotIn("Current", [text.get_text() for text in payload_run[8]["value"].axes[0].texts])
        self.assertEqual(payload_run[9]["visible"], True)
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
        self.assertEqual(isr_run[9]["visible"], True)
        self.assertIn("Mission Map Overlay", str(isr_run[9]["value"]))
        isr_legend = isr_run[8]["value"].axes[0].get_legend()
        self.assertIsNotNone(isr_legend)
        isr_labels = [text.get_text() for text in isr_legend.get_texts()]
        self.assertIn("ISR patrol route", isr_labels)
        self.assertIn("Current vector", isr_labels)
        self.assertNotIn("Return leg", isr_labels)

    def test_navigation_uses_native_gradio_tabs(self) -> None:
        """Workflow navigation should use Gradio tab state instead of brittle HTML click helpers."""
        self.assertEqual(main.select_workflow_tab("simulator")["selected"], "simulator")
        self.assertEqual(main.select_workflow_tab("results")["selected"], "results")
        main_text = Path("app/main.py").read_text(encoding="utf-8")
        self.assertIn('with gr.Tabs(selected="builder", elem_id="workflow-tabs") as workflow_tabs', main_text)
        self.assertIn('with gr.Tab("1. Mission Builder", id="builder")', main_text)
        self.assertIn('with gr.Tab("2. Single-UUV Simulator", id="simulator")', main_text)
        self.assertIn('with gr.Tab("3. Results", id="results")', main_text)
        self.assertIn('build_fetch_btn = gr.Button("Build Mission and Load Environment"', main_text)
        self.assertIn('build_go_sim_btn = gr.Button("Go to UUV Simulator")', main_text)
        self.assertIn('lambda: select_workflow_tab("simulator")', main_text)
        self.assertIn('lambda: select_workflow_tab("results")', main_text)
        self.assertNotIn("Load Mission and Go to Simulator", main_text)
        self.assertNotIn("BUILD_MISSION_AND_GO_JS", main_text)
        self.assertIn("Go to Results", str(main.ACTIVE_RESULTS_BUTTON_UPDATE))
        self.assertIn("Now that mission parameters are set, go to UUV simulation.", Path("app/main.py").read_text(encoding="utf-8"))
        self.assertIn("gr.Plot(label=None, show_label=False", main_text)
        self.assertIn('elem_classes=["report-plot"]', main_text)
        self.assertIn(".report-plot label { display: none !important; }", main.CUSTOM_CSS)
        self.assertIn("report-visual-grid", main_text)
        self.assertIn("report-visual-card", main_text)
        self.assertIn("report-map-card", main_text)
        self.assertIn("equal_height=True", main_text)
        self.assertNotIn('gr.Plot(label="Mission Visual Summary"', main_text)
        self.assertNotIn('gr.Plot(label="Mission Energy Progress and Battery Lens"', main_text)
        self.assertNotIn('gr.Plot(label="Mission Energy Uncertainty Distribution"', main_text)
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
        self.assertEqual(result[1]["value"], "Go to Results")
        self.assertEqual(result[1]["interactive"], False)

    def test_standalone_simulation_uses_standard_salinity_assumption(self) -> None:
        """Manual standalone simulation should not imply live salinity lookup."""
        with (
            patch("services.noaa_coops_salinity.NoaaCoopsSalinityProvider.fetch") as coops_fetch,
            patch("services.woa23_salinity.get_woa23_salinity") as woa_fetch,
        ):
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
        coops_fetch.assert_not_called()
        woa_fetch.assert_not_called()
        self.assertIn("Salinity source", str(result[5]))
        self.assertIn("Standard seawater assumption.", str(result[5]))
        self.assertNotIn("Salinity provider note", str(result[5]))
        self.assertEqual(result[9]["visible"], False)
        self.assertNotIn("Mission Map Overlay", str(result[9].get("value", "")))
        executive_summary = self._executive_summary_text(result[11])
        self.assertIn("without a fixed deterministic seed", executive_summary)
        self.assertNotIn("None", executive_summary)


if __name__ == "__main__":
    unittest.main()
