"""Gradio callback smoke tests with mocked METOC data."""

from __future__ import annotations

from dataclasses import replace
import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt

import app.main as main
from app.ui.reporting import (
    build_battery_detail_helper,
    build_battery_sustainment_rows,
    build_energy_equivalence_rows,
    build_engineering_snapshot_caption,
    build_energy_planner_summary_html,
    build_sustainment_projection_rows,
)
from core.energy import multi_area_search_plan, multi_area_transit_distance_km, search_plan
from core.geometry import manual_rectangle_area
from models.environment_model import EnvironmentData
from models.mission_model import MissionAreaSet
from utils.constants import APP_VERSION, ENERGY_MODEL_VERSION


class FakeMetocService:
    """Deterministic METOC service for app callback tests."""

    current_speed_kts_mean = 0.6

    def fetch(self, lat: float, lon: float) -> EnvironmentData:
        """Return stable environment data while preserving query traceability."""
        return EnvironmentData(
            current_speed_kts_mean=self.current_speed_kts_mean,
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
        self._existing_artifact_dirs = set(
            Path(tempfile.gettempdir()).glob("uuv_sim_*")
        )

    def tearDown(self) -> None:
        """Restore globals and remove generated run artifacts."""
        main.METOC_SERVICE = self._original_metoc
        plt.close("all")
        shutil.rmtree("runs", ignore_errors=True)
        for path in set(Path(tempfile.gettempdir()).glob("uuv_sim_*")) - self._existing_artifact_dirs:
            shutil.rmtree(path, ignore_errors=True)

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
                self.assertEqual(len(result), 17)
                self.assertIn("ISR endurance estimate", str(result[0]))
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
                self.assertIn("1000 Monte Carlo trials", executive_summary)
                self.assertIn("using deterministic seed 12345", executive_summary)
                self.assertIn("mission-total endurance case", executive_summary)
                self.assertIn("kWh per loop", executive_summary)
                self.assertIn("percentile outputs are retained in technical traceability", executive_summary)
                self.assertIn("Monte Carlo runs", str(result[11]))
                self.assertIn("Technical percentile traceability", str(result[11]))
                self.assertNotIn("None", executive_summary)
                self.assertNotIn("Battery sets P80", str(result[11]))
                self.assertNotIn("Battery sets P95", str(result[11]))
                self.assertNotIn("Available battery inventory", str(result[11]))
                self.assertIn("Energy Conversion", str(result[12]))
                self.assertIn("<td>Stress case</td>", str(result[12]))
                self.assertNotIn("Energy Storage Equivalence Lens", str(result[12]))
                self.assertEqual(result[8]["visible"], True)
                self.assertEqual(result[9]["visible"], True)
                self.assertIn("Mission Map Overlay", str(result[9]["value"]))
                self.assertIn("report-visual-card report-map-card", str(result[9]["value"]))
                self.assertIn("uuv-report-map-overlay", str(result[9]["value"]))
                self.assertIn("Engineering Snapshot", result[8]["value"].axes[0].get_title())
                csv_path = Path(str(result[10]["_csv_path"]))
                self.assertTrue(csv_path.is_file())
                self.assertNotEqual(csv_path.parent.resolve(), Path("runs").resolve())
                with csv_path.open(newline="", encoding="utf-8") as handle:
                    record = next(csv.DictReader(handle))
                self.assertEqual(record["app_version"], APP_VERSION)
                self.assertEqual(record["model_version"], ENERGY_MODEL_VERSION)
                self.assertTrue(record["vehicle_catalog_version"])
                self.assertTrue(record["metoc_lookup_lat"])
                self.assertTrue(record["metoc_lookup_lon"])
                self.assertTrue(record["isr_loop_distance_km"])
                self.assertIn("energy_planner", str(csv_path))
                self.assertTrue(Path(str(result[10]["_report_path"])).is_file())
                self.assertTrue(Path(str(result[10]["_package_path"])).is_file())

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
        self.assertIn("Feasible. The selected platform can complete the mission with declared charged battery inventory.", str(result[11]))
        self.assertNotIn("Search/MCM planning", str(result[11]))
        executive_summary = self._executive_summary_text(result[11])
        self.assertIn("Executive Results Summary", executive_summary)
        self.assertLess(executive_summary.index("The modeled search/MCM mission"), executive_summary.index("Monte Carlo"))
        self.assertIn("Planning recommendation is", executive_summary)
        self.assertIn("stress case is", executive_summary)
        self.assertIn("track-relative current burden", executive_summary)
        self.assertNotIn("None", executive_summary)
        self.assertIn("Battery sets needed", str(result[11]))
        self.assertIn("Stress-case battery sets", str(result[11]))
        self.assertNotIn("METOC risk", str(result[11]))
        self.assertIn("Energy Conversion", str(result[12]))
        self.assertIn("<td>Stress case</td>", str(result[12]))
        self.assertNotIn("Energy Storage Equivalence Lens", str(result[12]))
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

    def test_search_area_report_uses_canonical_simulation_area(self) -> None:
        """Search executive text, geometry detail, and visual caption should use the same polygon area."""
        built = main.build_mission_and_prefill("Area Search / MCM", json.dumps(CONVEX_POLYGON_GEOMETRY))
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
            2,
            True,
            1,
            "12345",
            0.6,
            85,
            26,
            built[0],
        )
        summary = result[10]
        canonical_area = float(summary["total_search_area_km2"])
        self.assertAlmostEqual(canonical_area, float(summary["search_area_km2"]), places=3)
        area_text = f"{canonical_area:.1f} sq km"
        executive_summary = self._executive_summary_text(result[11])
        self.assertIn(area_text, executive_summary)
        self.assertIn(area_text, str(result[4]))
        self.assertIn(area_text, build_engineering_snapshot_caption(summary))
        bbox_area = float(summary["search_width_km"]) * float(summary["search_height_km"])
        if abs(bbox_area - canonical_area) > 0.05:
            self.assertNotIn(f"{bbox_area:.1f} sq km", executive_summary)
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
        area_set = MissionAreaSet.from_dict(built[0]["area"])
        heading = 0 if summary["recommended_track_orientation"] == "North-South" else 90
        preserved_plan = multi_area_search_plan(area_set, 200, heading)
        side_km = area_set.total_area_km2 ** 0.5
        equivalent_plan = search_plan(
            manual_rectangle_area(side_km, side_km, area_set.total_area_km2),
            200,
            heading,
        )
        self.assertAlmostEqual(
            float(summary["search_track_distance_km"]),
            preserved_plan.track_distance_km,
        )
        self.assertAlmostEqual(
            float(summary["search_inter_area_transit_distance_km"]),
            multi_area_transit_distance_km(area_set),
        )
        self.assertGreater(float(summary["search_inter_area_transit_distance_km"]), 0.0)
        self.assertGreater(
            abs(preserved_plan.track_distance_km - equivalent_plan.track_distance_km),
            0.01,
        )

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
        self.assertIn("1000 Monte Carlo trials", executive_summary)
        self.assertIn("using deterministic seed 12345", executive_summary)
        self.assertIn("mission-total endurance case", executive_summary)
        self.assertIn("declared inventory supports", executive_summary)
        self.assertNotIn("None", executive_summary)
        self.assertNotIn("ISR persistence planning", str(result[11]))
        self.assertNotIn("patrol loop distance is", str(result[11]))
        self.assertIn("Patrol loop distance", str(result[11]))
        self.assertIn("Endurance per set", str(result[11]))
        self.assertNotIn("Recovery/swap</div>", str(result[11]))
        self.assertNotIn("Expected energy</div>", str(result[11]))
        self.assertNotIn("Battery sets P80", str(result[11]))
        self.assertNotIn("Battery sets P95", str(result[11]))
        self.assertIn("sequential recovery/swap", str(result[11]))
        self.assertNotIn("completed patrol loop(s)", str(result[11]))
        self.assertIn("Total patrol distance per installed set", str(result[4]))
        self.assertIn("Total patrol distance using total inventory", str(result[4]))
        self.assertIn("Battery swap required", str(result[3]))
        self.assertNotIn("Runtime per battery set", str(result[3]))
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

    def test_downloaded_html_embeds_browser_report_styling(self) -> None:
        """The standalone report should retain the in-app card and grid layout."""
        report = main.build_downloadable_report_html(
            status="Simulation complete.",
            mission_type="ISR",
            results_html="<div class='uuv-card'><div class='decision-kpi-grid'>Result</div></div>",
            metoc_results_html="",
            energy_html="",
            battery_html="",
            geometry_html="",
            environment_html="",
            equivalence_html="",
            figures=[],
        )

        self.assertIn(".decision-kpi-grid { display: grid", report)
        self.assertIn(".uuv-card {", report)
        self.assertIn('body class="report-document light"', report)
        self.assertIn("Result", report)

    def test_report_css_declares_light_and_dark_table_contrast(self) -> None:
        """Custom report tables should not inherit unreadable light-theme text."""
        css = main.CUSTOM_CSS
        self.assertIn(":root {\n  color-scheme: light dark;\n  --uuv-panel-bg: #ffffff", css)
        self.assertIn("--uuv-panel-bg: #ffffff", css)
        self.assertIn(".dark, [data-theme=\"dark\"], .gradio-container.dark", css)
        self.assertIn("--uuv-panel-bg: #111827", css)
        self.assertIn(".uuv-table { width: 100%; border-collapse: collapse; font-size: 14px; color: var(--uuv-text); }", css)
        self.assertIn(".report-table { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 14px; color: var(--uuv-text); }", css)
        self.assertIn(".uuv-table th { background: var(--uuv-table-head-bg); color: var(--uuv-heading); }", css)
        self.assertIn(".report-table th { background: var(--uuv-table-head-bg); color: var(--uuv-heading); }", css)
        self.assertIn(".uuv-table tbody tr { background: var(--uuv-panel-bg); }", css)
        self.assertIn(".report-table tbody tr { background: var(--uuv-panel-bg); }", css)
        self.assertIn(".decision-kpi.red .decision-kpi-value", css)
        self.assertIn(".metoc-card.green .metoc-title, .metoc-card.green .metoc-level, .metoc-card.green .metoc-value, .metoc-card.green .metoc-note", css)
        self.assertIn(".planning-scope-radio label", css)
        self.assertIn("background: #ef4444", css)
        self.assertIn("background: var(--uuv-table-head-bg)", css)

    def test_leaflet_iframe_summary_uses_light_theme_by_default(self) -> None:
        """Mission Builder map summary cards should not default to dark in light mode."""
        html = main.build_leaflet_iframe("Guam")
        self.assertIn("--map-shell-bg: #ffffff", html)
        self.assertIn("html.light, body.light", html)
        self.assertIn("syncColorTheme()", html)
        self.assertIn("background:#ffffff", html)

    def test_small_energy_equivalents_do_not_round_to_zero(self) -> None:
        """Small secondary equivalence values should retain useful precision."""
        rows = dict(build_energy_equivalence_rows(3.8, "test basis"))
        self.assertRegex(rows["Gigajoules"], r"0\.014 GJ")
        self.assertRegex(rows["Tonnes of oil equivalent"], r"0\.000327 TOE")
        self.assertRegex(rows["Barrel-of-oil equivalent"], r"0\.002235 BOE")
        self.assertNotIn("Metric tons oil equivalent", rows)
        fuel_rows = dict(build_energy_equivalence_rows(3.8, "test basis", 0.38))
        self.assertEqual(fuel_rows["Fuel-equivalent estimate based on generator input energy"], "0.38 gal JP-8/diesel")

    def test_battery_sustainment_rows_match_negative_energy_margins(self) -> None:
        """Battery detail should not hide stress-case shortfalls behind ISR set wording."""
        summary = {
            "mission_type": "ISR",
            "usable_battery_per_set_kwh": 13.2,
            "battery_nameplate_kwh": 15.0,
            "p80_energy_kwh": 13.6,
            "p95_energy_kwh": 13.8,
            "total_available_kwh": 13.2,
            "battery_sets_available": 1,
            "battery_sets_required_p80": 2,
            "battery_inventory_sufficient_no_recharge": False,
            "operator_reserve_fraction": 0.0,
            "sustainment_generator_efficiency": 0.84,
        }
        rows = {label: value for label, value, _ in build_battery_sustainment_rows(summary)}
        self.assertAlmostEqual(rows["Recommended planning shortfall"], 0.4)
        self.assertAlmostEqual(rows["Stress-case shortfall"], 0.6)
        self.assertEqual(rows["Planning inventory sufficient"], "No")
        self.assertEqual(rows["Stress-case inventory sufficient"], "No")
        self.assertEqual(rows["Battery sets needed"], 2)
        self.assertEqual(rows["Stress-case battery sets"], 2)
        self.assertIn("Usable-energy allowance", rows)
        self.assertNotIn("Reserve energy per set", rows)

    def test_inventory_coverage_and_generator_labels_use_true_basis(self) -> None:
        """Report labels should show over-100% usage and generator-input fuel basis."""
        summary = {
            "total_available_kwh": 13.2,
            "p80_energy_kwh": 13.6,
            "p95_energy_kwh": 13.8,
            "sustainment_projection_enabled": True,
            "sustainment_planning_weeks": 1,
            "sustainment_missions_per_week": 1,
            "sustainment_total_missions": 1,
            "sustainment_conservative_energy_per_mission_kwh": 13.8,
            "sustainment_total_conservative_energy_kwh": 13.8,
            "sustainment_usable_inventory_energy_per_cycle_kwh": 13.2,
            "sustainment_inventory_cycles_required": 2,
            "sustainment_recharge_energy_required_kwh": 0.6,
            "sustainment_generator_efficiency": 0.84,
            "sustainment_generator_input_energy_kwh": 16.43,
            "sustainment_generator_kwh_per_gallon": 10.0,
        }
        helper = build_battery_detail_helper(summary)
        self.assertIn("Planning recommendation uses 103.0% of inventory", helper)
        self.assertIn("stress case uses 104.5%", helper)
        self.assertIn("Visual gauge capped at 100%", helper)
        sustainment_rows = {label: value for label, value, _ in build_sustainment_projection_rows(summary)}
        self.assertEqual(sustainment_rows["Generator efficiency"], "84%")

    def test_recharge_feasibility_rows_and_bluf_distinguish_charged_inventory(self) -> None:
        """Charged-inventory feasible cases should not require recharge cycling."""
        summary = {
            "mission_type": "Area Search / MCM",
            "platform": "Test UUV",
            "p50_energy_kwh": 3.5,
            "p80_energy_kwh": 4.2,
            "p95_energy_kwh": 5.0,
            "planning_energy_kwh": 5.0,
            "planning_energy_basis": "mission_total",
            "usable_battery_per_set_kwh": 2.0,
            "battery_sets_available": 3,
            "battery_sets_required_p80": 3,
            "total_available_kwh": 6.0,
            "mean_duration_hr": 10.0,
            "battery_inventory_sufficient_no_recharge": True,
            "vehicle_rechargeable": True,
            "recharge_allowed": True,
            "recharge_feasibility_category": "charged_inventory",
            "recharge_feasibility_status": "Charged inventory sufficient",
            "runtime_per_battery_set_hr": 4.0,
            "recharge_time_per_set_hr": 3.0,
            "available_recharge_window_hr": 8.0,
            "recharge_bottleneck": False,
            "in_mission_recharge_shortfall_kwh": 0.0,
            "recharge_energy_required_during_mission_kwh": 0.0,
        }
        rows = {label: value for label, value, _ in build_battery_sustainment_rows(summary)}
        self.assertEqual(rows["Recharge feasibility status"], "Charged inventory sufficient")
        self.assertEqual(rows["Runtime per battery set"], 4.0)
        self.assertEqual(rows["Recharge time per set"], 3.0)
        self.assertEqual(rows["Available recharge window before set reuse"], 8.0)
        html = build_energy_planner_summary_html(summary, manual_rectangle_area(3.0, 3.0, 9.0), EnvironmentData())
        self.assertIn("Feasible. The selected platform can complete the mission with declared charged battery inventory.", html)

    def test_recharge_supported_shortfall_is_not_labeled_not_feasible(self) -> None:
        """Recharge-supported missions should be feasible when rotation window beats recharge time."""
        summary = {
            "mission_type": "Area Search / MCM",
            "platform": "Test UUV",
            "p50_energy_kwh": 7.5,
            "p80_energy_kwh": 8.0,
            "p95_energy_kwh": 8.4,
            "planning_energy_kwh": 8.4,
            "planning_energy_basis": "mission_total",
            "usable_battery_per_set_kwh": 1.3,
            "battery_sets_available": 4,
            "battery_sets_required_p80": 7,
            "total_available_kwh": 5.2,
            "mean_duration_hr": 54.3,
            "battery_inventory_sufficient_no_recharge": False,
            "vehicle_rechargeable": True,
            "recharge_allowed": True,
            "recharge_feasibility_category": "recharge_supported",
            "recharge_feasibility_status": "Feasible with continuous recharge/swap support",
            "runtime_per_battery_set_hr": 8.4,
            "recharge_time_per_set_hr": 6.0,
            "available_recharge_window_hr": 25.2,
            "recharge_bottleneck": False,
            "in_mission_recharge_shortfall_kwh": 3.2,
            "recharge_energy_required_during_mission_kwh": 3.2,
        }
        html = build_energy_planner_summary_html(summary, manual_rectangle_area(3.0, 3.0, 9.0), EnvironmentData())
        self.assertIn("Feasible with continuous recharge/swap support", html)
        self.assertIn("Initial charged inventory is short by 3.2 kWh", html)
        self.assertNotIn("Not feasible under current recharge assumptions", html)
        rows = {
            label: value
            for label, value, _ in build_sustainment_projection_rows(
                {
                    **summary,
                    "sustainment_projection_enabled": True,
                    "sustainment_recharge_energy_required_kwh": 3.2,
                }
            )
        }
        self.assertEqual(rows["Energy beyond initial charged inventory"], 3.2)

    def test_recharge_bottleneck_and_non_rechargeable_cases_are_distinct(self) -> None:
        """Recharge bottlenecks and one-way platforms should not share recharge-supported wording."""
        bottleneck = {
            "mission_type": "Area Search / MCM",
            "platform": "Test UUV",
            "p50_energy_kwh": 7.5,
            "p80_energy_kwh": 8.0,
            "p95_energy_kwh": 8.4,
            "planning_energy_kwh": 8.4,
            "planning_energy_basis": "mission_total",
            "usable_battery_per_set_kwh": 1.3,
            "battery_sets_available": 4,
            "battery_sets_required_p80": 7,
            "total_available_kwh": 5.2,
            "mean_duration_hr": 54.3,
            "battery_inventory_sufficient_no_recharge": False,
            "vehicle_rechargeable": True,
            "recharge_allowed": True,
            "recharge_feasibility_category": "recharge_bottleneck",
            "recharge_feasibility_status": "Recharge bottleneck",
            "runtime_per_battery_set_hr": 8.4,
            "recharge_time_per_set_hr": 30.0,
            "available_recharge_window_hr": 25.2,
            "recharge_bottleneck": True,
            "in_mission_recharge_shortfall_kwh": 3.2,
            "recharge_energy_required_during_mission_kwh": 3.2,
        }
        html = build_energy_planner_summary_html(bottleneck, manual_rectangle_area(3.0, 3.0, 9.0), EnvironmentData())
        self.assertIn("Not feasible under current recharge assumptions", html)
        self.assertIn("recharge cycle cannot recover depleted sets before reuse", html)

        one_way = {**bottleneck, "vehicle_rechargeable": False, "recharge_feasibility_category": "not_applicable", "recharge_feasibility_status": "Not applicable for one-way/non-rechargeable vehicle"}
        one_way_rows = build_battery_sustainment_rows(one_way)
        rows = {label: value for label, value, _ in one_way_rows}
        self.assertEqual(rows["Recharge feasibility status"], "Not applicable for one-way/non-rechargeable vehicle")
        self.assertIn("Runtime per vehicle unit", rows)
        self.assertIn("Replacement inventory required", rows)
        self.assertIn("Replacement inventory shortfall", rows)
        labels = [label for label, _, _ in one_way_rows]
        self.assertNotIn("Recharge time per set", labels)
        self.assertNotIn("Available recharge window before set reuse", labels)
        self.assertNotIn("Recharge bottleneck", labels)
        self.assertNotIn("Recharge energy required during mission", labels)
        sustainment_rows = {label: value for label, value, _ in build_sustainment_projection_rows({**one_way, "sustainment_inventory_cycles_required": 3, "sustainment_generator_input_energy_kwh": 12.0})}
        self.assertIn("Generator input energy equivalent", sustainment_rows)
        self.assertNotIn("Generator input energy to reset consumed energy", sustainment_rows)

    def test_recharge_disabled_rechargeable_vehicle_is_not_one_way(self) -> None:
        """Rechargeable vehicles with recharge disabled should not appear non-rechargeable."""
        result = main.run_from_ui(
            "REMUS 300 - 4.5 kWh",
            "Payload Delivery",
            10,
            3,
            3,
            120,
            90,
            0,
            200,
            True,
            3.5,
            1,
            False,
            1,
            "11223",
            0.6,
            85,
            26,
            {},
        )
        report_text = f"{result[0]} {result[3]} {result[11]}"
        self.assertIn("Recharge not enabled", report_text)
        self.assertNotIn("Not applicable for one-way/non-rechargeable vehicle", report_text)

    def test_rechargeable_status_reports_recharge_bottleneck_when_rotation_fails(self) -> None:
        """Rechargeable platforms should report a bottleneck when recharge cannot keep up."""
        result = main.run_from_ui(
            "REMUS 100B - 1.5 kWh",
            "Payload Delivery",
            10,
            3,
            3,
            500,
            90,
            0,
            200,
            True,
            3.5,
            1,
            True,
            1,
            "24680",
            0.6,
            85,
            26,
            {},
        )
        status = str(result[0])
        self.assertIn("Battery inventory is insufficient", status)
        self.assertIn("Planning recommendation", status)
        self.assertIn("Stress case", status)
        self.assertIn("recharge cycle is a bottleneck under current assumptions", status)

    def test_isr_run_status_uses_endurance_language_not_generic_bottleneck(self) -> None:
        """ISR status should follow ISR endurance feasibility rather than generic recharge status."""
        built = main.build_mission_and_prefill("ISR", json.dumps(RECTANGLE_GEOMETRY))
        self.assertTrue(built[0], built[1])
        result = main.run_from_ui(
            "REMUS 620 - 3 batteries / no payload",
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
            built[0],
        )
        status = str(result[0])
        self.assertIn("ISR endurance estimate", status)
        self.assertIn("completed patrol loops", status)
        self.assertNotIn("recharge cycle is a bottleneck", status)
        self.assertNotIn("Battery inventory shortfall", status)

    def test_one_way_non_rechargeable_report_uses_vehicle_inventory_language(self) -> None:
        """Non-rechargeable platforms should use vehicle-unit inventory wording."""
        synthetic_name = "Synthetic one-way callback test vehicle"
        main.VEHICLE_CATALOG[synthetic_name] = replace(
            main.VEHICLE_CATALOG["REMUS 300 - 1.5 kWh"],
            name=synthetic_name,
            recharge_hr=0.0,
            recoverable=False,
            rechargeable=False,
            default_payload_recovery_mode="one_way",
            usable_fraction=1.0,
        )
        self.addCleanup(main.VEHICLE_CATALOG.pop, synthetic_name, None)
        result = main.run_from_ui(
            synthetic_name,
            "Payload Delivery",
            10,
            3,
            3,
            50,
            90,
            0,
            200,
            True,
            4.0,
            1,
            True,
            1,
            "13579",
            0.6,
            85,
            26,
            {},
        )
        status = str(result[0])
        report_text = " ".join(str(result[index]) for index in (2, 3, 11))
        normal_output = f"{status} {report_text}"
        self.assertIn("Vehicle inventory is insufficient", status)
        self.assertIn("Planning recommendation", status)
        self.assertIn("Stress case", status)
        self.assertIn("Vehicle inventory", normal_output)
        self.assertIn("one-way inventory", normal_output)
        self.assertNotIn("recharge/swap sequence required", normal_output)
        self.assertNotIn("Recharge/swap required", normal_output)
        self.assertNotIn("Battery sets required", normal_output)
        self.assertNotIn("effector", normal_output.lower())
        self.assertIn("non-rechargeable", str(result[11]).lower())

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
        self.assertEqual(len(payload_run), 17)
        self.assertNotIn("Recommended track orientation", str(payload_run[0]))
        self.assertEqual(payload_run[1]["value"], "Go to Results")
        self.assertEqual(payload_run[1]["interactive"], True)
        self.assertIn("Mission Decision Brief", str(payload_run[11]))
        self.assertIn("Technical Traceability / Model Detail", str(payload_run[11]))
        self.assertLess(str(payload_run[11]).index("BLUF"), str(payload_run[11]).index("Executive Results Summary"))
        self.assertLess(str(payload_run[11]).index("Executive Results Summary"), str(payload_run[11]).index("Technical Traceability / Model Detail"))
        self.assertNotIn("Energy Detail", str(payload_run[2]))
        self.assertIn("Speed-adjusted power", str(payload_run[2]))
        self.assertIn("Hotel power component", str(payload_run[2]))
        self.assertIn("section-insight-card", str(payload_run[2]))
        self.assertIn("report-table", str(payload_run[2]))
        self.assertNotIn("Battery and Sustainment Detail", str(payload_run[3]))
        self.assertNotIn("Sustainment Projection Lens", str(payload_run[3]))
        self.assertIn("mini-bar", str(payload_run[3]))
        self.assertIn("report-table", str(payload_run[3]))
        self.assertNotIn("Single mission default", str(payload_run[3]))
        self.assertNotIn("Mission Geometry Detail", str(payload_run[4]))
        self.assertIn("section-insight-card", str(payload_run[4]))
        self.assertNotIn("Environmental Detail", str(payload_run[5]))
        self.assertIn("fixed-scale-gauge", str(payload_run[5]))
        self.assertIn("Total environmental burden:", str(payload_run[5]))
        self.assertNotIn("width:100.0%", str(payload_run[5]))
        self.assertIn("report-table", str(payload_run[5]))
        self.assertIn("METOC Assessment", str(payload_run[13]))
        self.assertIn("Energy Conversion", str(payload_run[12]))
        self.assertIn("<td>Stress case</td>", str(payload_run[12]))
        self.assertNotIn("Energy Storage Equivalence Lens", str(payload_run[12]))
        self.assertNotIn("Payload mission planning", str(payload_run[11]))
        executive_summary = self._executive_summary_text(payload_run[11])
        self.assertIn("Executive Results Summary", executive_summary)
        self.assertLess(executive_summary.index("The modeled route/transit mission"), executive_summary.index("Monte Carlo"))
        self.assertIn("1000 Monte Carlo trials", executive_summary)
        self.assertIn("using deterministic seed 12345", executive_summary)
        self.assertIn("Planning recommendation is", executive_summary)
        self.assertIn("stress case is", executive_summary)
        self.assertIn("return transit distance and route current", executive_summary)
        self.assertIn("Return-to-start planning increases modeled distance", executive_summary)
        self.assertIn("Monte Carlo Technical Traceability", str(payload_run[11]))
        self.assertNotIn("None", executive_summary)
        self.assertIn("Planning recommendation", str(payload_run[11]))
        self.assertIn("Stress case", str(payload_run[11]))
        self.assertIn("Battery sets needed", str(payload_run[11]))
        self.assertIn("Stress-case battery sets", str(payload_run[11]))
        self.assertNotIn("METOC risk", str(payload_run[11]))

        sustainment_run = main.run_from_ui(
            "REMUS 300 - 4.5 kWh",
            "Route / Transit",
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
            "Medium",
            2,
            "1 week",
            0.84,
            0,
            True,
        )
        self.assertIn("Sustainment Projection Lens", str(sustainment_run[3]))
        self.assertIn("The sustainment lens is an energy-flow projection", str(sustainment_run[3]))
        self.assertIn("Energy Storage Equivalence Lens", str(sustainment_run[12]))
        self.assertIn("Energy-equivalence values are provided as a secondary sustainment-planning lens", str(sustainment_run[12]))
        self.assertIn("Planning horizon total", str(sustainment_run[12]))
        self.assertNotIn("dry-weight", str(payload_run[4]).lower())
        self.assertNotIn("dry weight", str(payload_run[4]).lower())
        self.assertIn("Kilocalories", str(sustainment_run[12]))
        self.assertIn("Gigajoules", str(sustainment_run[12]))
        self.assertNotIn("0.0 GJ", str(sustainment_run[12]))
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
        self.assertIn("ISR endurance estimate", str(isr_run[0]))
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

    def test_zero_current_prefill_remains_zero(self) -> None:
        """A fetched zero-current condition should not be replaced by the manual default."""
        service = FakeMetocService()
        service.current_speed_kts_mean = 0.0
        main.METOC_SERVICE = service  # type: ignore[assignment]
        built = main.build_mission_and_prefill("ISR", json.dumps(RECTANGLE_GEOMETRY))
        self.assertEqual(built[11], 0.0)

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
        self.assertIn(".uuv-render-cycle", main.CUSTOM_CSS)
        self.assertIn("report-visual-grid", main_text)
        self.assertIn("report-visual-card", main_text)
        self.assertIn("report-map-card", main_text)
        self.assertNotIn("equal_height=True", main_text)
        self.assertIn("uuvRequestLayoutRefresh", main_text)
        self.assertIn("clear_results_before_run", main_text)
        self.assertIn("queue=False", main_text)
        self.assertIn('trigger_mode="once"', main_text)
        self.assertIn("demo.queue(default_concurrency_limit=4)", main_text)
        self.assertIn('kwargs.setdefault("server_name", "0.0.0.0")', main_text)
        self.assertIn('kwargs.setdefault("ssr_mode", False)', main_text)
        self.assertNotIn('gr.Plot(label="Mission Visual Summary"', main_text)
        self.assertNotIn('gr.Plot(label="Mission Energy Progress and Battery Lens"', main_text)
        self.assertNotIn('gr.Plot(label="Mission Energy Uncertainty Distribution"', main_text)
        self.assertNotIn("Energy Planner CSV Export", Path("app/main.py").read_text(encoding="utf-8"))
        self.assertNotIn("Manual salinity", Path("app/main.py").read_text(encoding="utf-8"))

    def test_space_and_package_gradio_pins_match(self) -> None:
        """HF Space metadata and Python dependency files should pin the same Gradio build."""
        readme = Path("README.md").read_text(encoding="utf-8")
        requirements = Path("requirements.txt").read_text(encoding="utf-8")
        pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("sdk_version: 6.16.0", readme)
        self.assertIn("gradio==6.16.0", requirements)
        self.assertIn('"gradio==6.16.0"', pyproject)

    def test_clear_results_before_run_matches_result_output_contract(self) -> None:
        """The stale-DOM guard should clear every dynamic Results output before a run."""
        cleared = main.clear_results_before_run()
        self.assertEqual(len(cleared), 15)
        self.assertIn("fresh results render", cleared[0])
        self.assertEqual(cleared[1]["interactive"], False)
        self.assertEqual(cleared[2], "")
        self.assertEqual(cleared[5], "")
        self.assertEqual(cleared[8]["visible"], False)
        self.assertEqual(cleared[9]["visible"], False)
        self.assertEqual(cleared[10], {})
        self.assertIn("uuv-render-cycle", cleared[11])

    def test_dynamic_html_outputs_are_render_tokened(self) -> None:
        """Repeated report renders should produce fresh HTML for Gradio/browser remounts."""
        first = main._with_render_token("<div>Report</div>", "test")
        second = main._with_render_token("<div>Report</div>", "test")
        self.assertIn("uuv-render-cycle", first)
        self.assertIn("data-uuv-render-token='test-", first)
        self.assertNotEqual(first, second)

    def test_leaflet_iframes_include_render_tokens(self) -> None:
        """Mission and report map iframes should not be reused as stale DOM nodes."""
        builder_html = main.build_leaflet_iframe("Guam")
        report_html = main.build_report_map_overlay_iframe(RECTANGLE_GEOMETRY, "ISR")
        self.assertIn("data-uuv-render-token", builder_html)
        self.assertIn("class=\"uuv-map-iframe\"", builder_html)
        self.assertIn("height=\"760\"", builder_html)
        self.assertIn("data-uuv-render-token", report_html)
        self.assertIn("class=\"uuv-report-map-iframe\"", report_html)

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
        search_update, payload_update, isr_update, sequence_update = main.mission_input_visibility("Route / Transit")
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

    def test_simulation_mode_controls_are_mutually_exclusive(self) -> None:
        """Monte Carlo mode should be the default and deterministic mode should hide stochastic controls."""
        self.assertEqual(main.MONTE_CARLO_MODE, "Monte Carlo run")
        self.assertEqual(main.DEFAULT_MONTE_CARLO_RUNS, 1000)

        deterministic, runs = main.resolve_simulation_mode(main.MONTE_CARLO_MODE, "")
        self.assertFalse(deterministic)
        self.assertEqual(runs, 1000)

        deterministic, runs = main.resolve_simulation_mode(main.MONTE_CARLO_MODE, 5)
        self.assertFalse(deterministic)
        self.assertEqual(runs, 10)

        deterministic, runs = main.resolve_simulation_mode(main.DETERMINISTIC_MODE, 1000)
        self.assertTrue(deterministic)
        self.assertEqual(runs, 1)

        mc_runs_update, seed_update = main.simulation_mode_visibility(main.MONTE_CARLO_MODE)
        self.assertEqual(mc_runs_update["visible"], True)
        self.assertEqual(mc_runs_update["interactive"], True)
        self.assertEqual(seed_update["visible"], True)
        self.assertEqual(seed_update["interactive"], True)

        mc_runs_update, seed_update = main.simulation_mode_visibility(main.DETERMINISTIC_MODE)
        self.assertEqual(mc_runs_update["visible"], False)
        self.assertEqual(mc_runs_update["interactive"], False)
        self.assertEqual(seed_update["visible"], False)
        self.assertEqual(seed_update["interactive"], False)

    def test_simulation_mode_seed_and_status_contract(self) -> None:
        """Run mode should control run count and seed traceability without percentile-led status wording."""
        generated = main.run_from_ui(
            "REMUS 300 - 4.5 kWh",
            "Route / Transit",
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
            "1 week",
            0.84,
            0,
            False,
            main.MONTE_CARLO_MODE,
            10,
        )
        self.assertIn("Planning recommendation:", str(generated[0]))
        self.assertIn("Stress case:", str(generated[0]))
        self.assertNotIn("P80", str(generated[0]))
        self.assertNotIn("P95", str(generated[0]))
        self.assertIsNone(generated[10]["rng_seed_requested"])
        self.assertIsNotNone(generated[10]["rng_seed_used"])
        self.assertEqual(generated[10]["monte_carlo_runs"], 10)

        provided = main.run_from_ui(
            "REMUS 300 - 4.5 kWh",
            "Route / Transit",
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
            0.5,
            90,
            25,
            {},
            "Medium",
            1,
            "1 week",
            0.84,
            0,
            False,
            main.MONTE_CARLO_MODE,
            10,
        )
        self.assertEqual(provided[10]["rng_seed_requested"], 12345)
        self.assertEqual(provided[10]["rng_seed_used"], 12345)

        deterministic = main.run_from_ui(
            "REMUS 300 - 4.5 kWh",
            "Route / Transit",
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
            "-1",
            0.5,
            90,
            25,
            {},
            "Medium",
            1,
            "1 week",
            0.84,
            0,
            False,
            main.DETERMINISTIC_MODE,
            1000,
        )
        self.assertEqual(deterministic[10]["simulation_mode"], main.DETERMINISTIC_MODE)
        self.assertEqual(deterministic[10]["monte_carlo_runs"], 1)
        self.assertEqual(deterministic[10]["current_sampling_sigma_kts"], 0.0)
        self.assertEqual(
            deterministic[10]["current_sampling_lower_bound_kts"],
            deterministic[10]["current_sampling_upper_bound_kts"],
        )
        self.assertFalse(deterministic[10]["sustainment_projection_variance_enabled"])
        self.assertNotIn("Invalid seed", str(deterministic[0]))

    def test_v1_report_hierarchy_keeps_percentiles_in_traceability(self) -> None:
        """Main report should stay decision-focused while traceability keeps percentile details."""
        result = main.run_from_ui(
            "REMUS 300 - 4.5 kWh",
            "Route / Transit",
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
            0.5,
            90,
            25,
            {},
            "Medium",
            1,
            "1 week",
            0.84,
            0,
            False,
            main.MONTE_CARLO_MODE,
            10,
        )
        status = str(result[0])
        energy_detail = str(result[2])
        battery_detail = str(result[3])
        geometry_detail = str(result[4])
        environmental_detail = str(result[5])
        decision_and_traceability = str(result[11])
        energy_equivalence = str(result[12])
        decision_card = decision_and_traceability.split("Technical Traceability / Model Detail")[0]

        self.assertIn("Planning recommendation:", status)
        self.assertIn("Stress case:", status)
        self.assertNotIn("P80", status)
        self.assertNotIn("P95", status)

        for forbidden in (
            "Technical P50 simulated energy",
            "Technical P80 simulated energy",
            "Technical P95 simulated energy",
            "P50 simulation value",
            "P80 simulation value",
            "P95 simulation value",
            "Recommendation basis",
        ):
            self.assertNotIn(forbidden, energy_detail)
        self.assertIn("Expected energy", energy_detail)
        self.assertIn("Uncertainty allowance", energy_detail)
        self.assertIn("Planning recommendation", energy_detail)
        self.assertIn("Stress case", energy_detail)
        self.assertIn("Sensor load", energy_detail)
        self.assertIn("Sensor load range", energy_detail)
        self.assertNotIn("P50", energy_detail)
        self.assertNotIn("P80", energy_detail)
        self.assertNotIn("P95", energy_detail)
        self.assertNotIn("Recommended planning energy", energy_detail)
        self.assertNotIn("Conservative stress estimate", energy_detail)

        self.assertIn("Monte Carlo Technical Traceability", decision_and_traceability)
        self.assertIn("P50 simulation value", decision_and_traceability)
        self.assertIn("P80 simulation value", decision_and_traceability)
        self.assertIn("P95 simulation value", decision_and_traceability)
        self.assertIn("Recommendation basis", decision_and_traceability)
        self.assertIn("P50/P80/P95 are percentiles of the Monte Carlo output distribution", decision_and_traceability)
        self.assertIn("Expected energy definition", decision_and_traceability)
        self.assertIn("Upper-tail fraction", decision_and_traceability)

        self.assertNotIn("P50", decision_card)
        self.assertNotIn("P80", decision_card)
        self.assertNotIn("P95", decision_card)
        self.assertNotIn("Planning-level", decision_card)
        self.assertNotIn("Recommended planning energy", decision_card)
        self.assertNotIn("Conservative stress estimate", decision_card)

        self.assertEqual(energy_detail.count("Energy Detail"), 0)
        self.assertEqual(battery_detail.count("Battery and Sustainment Detail"), 0)
        self.assertEqual(geometry_detail.count("Mission Geometry Detail"), 0)
        self.assertEqual(environmental_detail.count("Environmental Detail"), 0)
        self.assertIn("Energy Conversion", energy_equivalence)
        self.assertIn("<td>Stress case</td>", energy_equivalence)
        self.assertNotIn("Energy Storage Equivalence Lens", energy_equivalence)
        self.assertEqual(decision_and_traceability.count("Technical Traceability / Model Detail"), 1)

        distribution_labels = [text.get_text() for text in result[7].axes[0].get_legend().get_texts()]
        self.assertTrue(any(label.startswith("Expected") for label in distribution_labels))
        self.assertTrue(any(label.startswith("Planning recommendation") for label in distribution_labels))
        self.assertTrue(any(label.startswith("Stress case") for label in distribution_labels))
        self.assertTrue(any(label.startswith("Battery available") for label in distribution_labels))
        self.assertFalse(any("P50" in label or "P80" in label or "P95" in label for label in distribution_labels))

        time_labels = [text.get_text() for text in result[6].axes[0].get_legend().get_texts()]
        self.assertIn("Expected", time_labels)
        self.assertIn("Battery available", time_labels)
        self.assertFalse(any("P50" in label or "P80" in label or "P95" in label for label in time_labels))

    def test_sustainment_projection_controls_are_optional(self) -> None:
        """Sustainment projection inputs should stay hidden until requested."""
        hidden = main.sustainment_projection_visibility(False)
        shown = main.sustainment_projection_visibility(True)
        hidden_scope = main.sustainment_projection_visibility(main.SINGLE_MISSION_SCOPE)
        shown_scope = main.sustainment_projection_visibility(main.MULTI_MISSION_PLANNING_SCOPE)
        self.assertEqual(hidden["visible"], False)
        self.assertEqual(shown["visible"], True)
        self.assertEqual(hidden_scope["visible"], False)
        self.assertEqual(shown_scope["visible"], True)

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
        self.assertIn("Energy Conversion", str(result[12]))
        self.assertIn("<td>Stress case</td>", str(result[12]))
        self.assertNotIn("Energy Storage Equivalence Lens", str(result[12]))

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
        self.assertIn("Energy Storage Equivalence Lens", str(result[12]))
        self.assertIn("Planning horizon total", str(result[12]))
        self.assertNotIn("<td>Stress case</td>", str(result[12]))

    def test_six_month_projection_is_prominent_in_report(self) -> None:
        """The thesis six-month outlook should appear near the top of the report."""
        result = main.run_from_ui(
            "REMUS 300 - 4.5 kWh",
            "Route / Transit",
            10,
            3,
            3,
            10,
            0,
            0,
            200,
            True,
            3.5,
            2,
            True,
            1,
            "12345",
            0.5,
            90,
            25,
            {},
            "Medium",
            3,
            "6 months",
            0.84,
            0,
            main.MULTI_MISSION_PLANNING_SCOPE,
        )
        self.assertEqual(main._planning_weeks("6 months"), 26.0)
        self.assertEqual(result[10]["sustainment_planning_weeks"], 26.0)
        self.assertEqual(result[10]["sustainment_total_missions"], 78.0)
        report = str(result[11])
        self.assertLess(report.index("Mission Decision Brief"), report.index("Sustainment Outlook"))
        self.assertLess(report.index("Sustainment Outlook"), report.index("Technical Traceability / Model Detail"))
        self.assertIn("26 weeks", report)
        self.assertIn("Stochastic P10-P90", report)
        self.assertIn("independently resamples", report)
        self.assertLess(report.index("Sustainment Outlook"), report.index("Uncertainty allowance"))
        self.assertIn("Current speed sampling bounds", str(result[5]))
        self.assertIn("Current direction treatment", str(result[5]))

    def test_loaded_mission_clears_on_mission_type_change(self) -> None:
        """Changing mission type must not silently retain incompatible map geometry."""
        built = main.build_mission_and_prefill("ISR", json.dumps(RECTANGLE_GEOMETRY))
        cleared, message = main.clear_incompatible_mission_context(
            "Route / Transit",
            built[0],
        )
        self.assertEqual(cleared, {})
        self.assertIn("cleared", message)
        result = main.run_from_ui(
            "REMUS 300 - 4.5 kWh",
            "Route / Transit",
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
            built[0],
        )
        self.assertTrue(str(result[0]).startswith("Input error:"))
        self.assertIn("loaded map mission is ISR", str(result[0]))

    def test_manual_isr_line_geometry_and_input_validation(self) -> None:
        """Manual ISR lines should run and invalid numeric entries should be rejected."""
        result = main.run_from_ui(
            platform_name="REMUS 300 - 4.5 kWh",
            mission_type="ISR",
            manual_area_km2=10,
            width_km=3,
            height_km=3,
            route_distance_km=10,
            route_heading_deg=0,
            additional_transit_km=0,
            track_spacing_m=200,
            return_to_start=True,
            speed_kts=3.5,
            battery_sets_available=1,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed="12345",
            current_mean_kts=0.5,
            current_direction_deg=90,
            temp_mean_c=25,
            context={},
            isr_geometry_type="Line patrol",
            isr_patrol_distance_km=12,
            isr_patrol_heading_deg=45,
        )
        self.assertIn("Simulation complete", str(result[0]))
        self.assertEqual(result[10]["isr_patrol_geometry"], "line")

        invalid = main.run_from_ui(
            platform_name="REMUS 300 - 4.5 kWh",
            mission_type="Route / Transit",
            manual_area_km2=10,
            width_km=3,
            height_km=3,
            route_distance_km=-1,
            route_heading_deg=400,
            additional_transit_km=-2,
            track_spacing_m=200,
            return_to_start=True,
            speed_kts=0,
            battery_sets_available=1.5,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed="",
            current_mean_kts=-0.5,
            current_direction_deg=500,
            temp_mean_c=25,
            context={},
        )
        self.assertTrue(str(invalid[0]).startswith("Input error:"))
        self.assertIn("Route distance must be greater than zero", str(invalid[0]))
        self.assertEqual(invalid[1]["interactive"], False)

    def test_downloaded_mission_package_can_be_reloaded_and_deleted(self) -> None:
        """A session package should restore inputs and delete only its own files."""
        result = main.run_from_ui(
            "REMUS 300 - 4.5 kWh",
            "Route / Transit",
            10,
            3,
            3,
            12,
            45,
            2,
            200,
            True,
            3.5,
            2,
            True,
            1,
            "12345",
            0.5,
            90,
            25,
            {},
        )
        state = result[10]
        package_path = Path(str(state["_package_path"]))
        artifact_dir = Path(str(state["_artifact_dir"]))
        loaded = main.load_saved_mission_for_ui(str(package_path))
        self.assertEqual(loaded[0]["mission_type"], "Route / Transit")
        self.assertIn("Saved mission loaded", str(loaded[1]))
        self.assertEqual(float(loaded[9]), 12.0)
        cleared_state, _, _, status = main.delete_session_files(state)
        self.assertEqual(cleared_state, {})
        self.assertEqual(status, "Session files deleted.")
        self.assertFalse(artifact_dir.exists())

    def test_radio_sustainment_projection_uses_operator_values(self) -> None:
        """Radio planning scope should behave the same as the legacy checked value."""
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
            "",
            0.5,
            90,
            25,
            {},
            "Medium",
            3,
            "1 month",
            0.84,
            0,
            main.MULTI_MISSION_PLANNING_SCOPE,
        )
        self.assertEqual(result[10]["sustainment_total_missions"], 12.0)
        self.assertIn("Planning horizon total", str(result[12]))
        self.assertIn("Fuel-equivalent estimate based on generator input energy", str(result[12]))

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
        self.assertIn("generated seed recorded for traceability", executive_summary)
        self.assertNotIn("None", executive_summary)


if __name__ == "__main__":
    unittest.main()
