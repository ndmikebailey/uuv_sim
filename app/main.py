"""Hugging Face/Gradio entrypoint for the UUV mission planning app."""

from __future__ import annotations

import math
from typing import Any

import gradio as gr

from app.components.map_iframe import build_leaflet_iframe
from app.ui.reporting import (
    build_battery_sustainment_rows,
    build_distribution_chart,
    build_energy_equivalence_rows,
    build_energy_planner_summary_html,
    build_report_table_html,
    build_energy_time_chart,
    build_energy_summary_rows,
    build_environmental_input_rows,
    build_mapping_snapshot_chart,
    build_mission_geometry_summary_rows,
    build_sustainment_projection_rows,
    context_markdown,
    env_table_to_html,
    metoc_html,
    rows_to_dataframe,
)
from core.energy import run_energy_simulation
from core.geometry import manual_payload_route, manual_rectangle_area
from core.mission import build_mission_context
from models.environment_model import EnvironmentData
from models.mission_model import MissionArea, MissionAreaSet
from models.vehicle_model import VEHICLE_CATALOG
from services.marine_api import OpenMeteoMarineClient
from services.metoc_fusion import MetocFusionService
from services.run_logger import write_run_record
from services.weather_api import OpenMeteoWeatherClient
from utils.constants import APP_NAME, APP_VERSION, ISR_MISSIONS, MISSION_TYPES, PAYLOAD_MISSIONS, REGION_PRESETS, SEARCH_MISSIONS
from utils.parsing import parse_rng_seed, safe_float, safe_int

METOC_SERVICE = MetocFusionService(
    marine_client=OpenMeteoMarineClient(),
    weather_client=OpenMeteoWeatherClient(),
    salinity_enabled=True,
)

CUSTOM_CSS = """
.uuv-card {
  border: 1px solid #374151;
  border-radius: 12px;
  padding: 14px 16px;
  background: #111827;
  margin: 10px 0;
}
.full-width-card { width: 100%; }
.uuv-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.uuv-table th, .uuv-table td {
  border-bottom: 1px solid #374151;
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
}
.uuv-table th { background: #1f2937; }
.uuv-table .value { font-weight: 700; }
.uuv-attribution, .small-muted { color: #9ca3af; font-size: 12px; margin-top: 8px; }
.planner-summary {
  border-color: #2563eb;
  background: #0f172a;
}
.planner-summary h3 { margin-top: 0; }
.planner-summary p { margin: 8px 0; line-height: 1.45; }
.mission-decision-brief h2 { margin: 0 0 12px 0; }
.decision-topline { display: grid; grid-template-columns: minmax(120px, 180px) 1fr; gap: 14px; align-items: stretch; }
.decision-status { display: flex; align-items: center; justify-content: center; border-radius: 8px; padding: 14px; font-weight: 900; font-size: 20px; }
.decision-status.green, .decision-kpi.green { background: #064e3b; border-color: #10b981; }
.decision-status.yellow, .decision-kpi.yellow { background: rgba(234, 179, 8, 0.16); border-color: #eab308; }
.decision-status.red, .decision-kpi.red { background: #7f1d1d; border-color: #ef4444; }
.decision-status.gray, .decision-kpi.gray { background: #374151; border-color: #9ca3af; }
.decision-kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); gap: 10px; margin-top: 14px; }
.decision-kpi { border: 1px solid #475569; border-radius: 8px; padding: 10px; min-height: 76px; }
.decision-kpi-label { color: #cbd5e1; font-size: 12px; font-weight: 700; }
.decision-kpi-value { font-size: 20px; font-weight: 900; margin-top: 6px; }
.decision-kpi-note { color: #e5e7eb; font-size: 12px; margin-top: 4px; }
.executive-results-summary {
  border: 1px solid #334155;
  border-left: 3px solid #60a5fa;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.72);
  padding: 10px 12px;
  margin-top: 12px;
}
.executive-results-title { color: #cbd5e1; font-size: 12px; font-weight: 800; text-transform: uppercase; }
.executive-results-text { color: #e5e7eb; font-size: 13px; line-height: 1.45; margin: 5px 0 0 0; }
.traceability-detail { margin: 10px 0; }
.traceability-detail summary { cursor: pointer; font-weight: 800; padding: 10px 0; }
.metoc-assessment, .metoc-panel, .metoc-card-grid { width: 100%; max-width: none; }
.metoc-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.posture { font-weight: 800; font-size: 18px; padding: 8px 12px; border-radius: 10px; background: #1f2937; }
.report-table { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 14px; }
.report-table th, .report-table td {
  border-bottom: 1px solid #374151;
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
  word-wrap: break-word;
  overflow-wrap: anywhere;
}
.report-table th { background: #1f2937; }
.report-table .metric-col { width: 60%; }
.report-table .value-col { width: 40%; }
.metoc-grid, .metoc-card-grid { width: 100%; max-width: none; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 12px; }
.metoc-card { width: 100%; min-width: 0; max-width: none; border-radius: 10px; padding: 10px; min-height: 120px; border: 2px solid #4b5563; }
.metoc-card.green { background: #064e3b; border-color: #10b981; }
.metoc-card.yellow { background: rgba(234, 179, 8, 0.16); border-color: #eab308; }
.metoc-card.red { background: #7f1d1d; border-color: #ef4444; }
.metoc-card.gray { background: #374151; border-color: #9ca3af; }
.metoc-title { font-weight: 800; font-size: 15px; }
.metoc-level { font-weight: 900; font-size: 17px; margin: 6px 0; }
.metoc-value { font-size: 14px; }
.metoc-note { font-size: 12px; color: #e5e7eb; margin-top: 6px; }
.gradio-container .plot-container, .gradio-container .js-plotly-plot { max-width: 100%; }
.build-label {
  color: #9ca3af;
  font-size: 12px;
  margin: -4px 0 10px 0;
}
.view-results-btn {
  border: none;
  border-radius: 10px;
  padding: 10px 18px;
  font-weight: 700;
  cursor: pointer;
  margin-top: 8px;
}
.view-results-btn.disabled {
  background: #555;
  color: #bbb;
  cursor: not-allowed;
}
.view-results-btn.active {
  background: #d86b6b;
  color: #ffffff;
  cursor: pointer;
}
"""

CUSTOM_JS = """
function() {
  function findTabByText(words) {
    const candidates = Array.from(document.querySelectorAll('button, [role="tab"], .tabitem button'));
    return candidates.find((el) => {
      if (el.classList.contains("view-results-btn")) return false;
      const text = (el.innerText || el.textContent || "").trim().toLowerCase();
      return words.some((word) => text.includes(word));
    });
  }
  window.goToResultsTab = function goToResultsTab() {
    const target = findTabByText(["results", "report"]);
    if (target) {
      target.click();
    }
    setTimeout(() => {
      const anchor = document.querySelector("#results-anchor");
      if (anchor) {
        anchor.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }, 400);
  };
  window.goToSimulatorTab = function goToSimulatorTab() {
    const target = findTabByText(["single-uuv", "simulator"]);
    if (target) {
      target.click();
    }
  };
  function setGeometryBox(text) {
    const box = document.querySelector('#geometry_json_box textarea');
    if (!box) return;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    setter.call(box, text);
    box.dispatchEvent(new Event('input', { bubbles: true }));
    box.dispatchEvent(new Event('change', { bubbles: true }));
  }
  window.addEventListener('message', function(event) {
    if (!event.data || event.data.type !== 'uuv_geometry') return;
    setGeometryBox(JSON.stringify(event.data.payload || {}, null, 2));
  });
}
"""

BUILD_MISSION_JS = """
(missionType, geometryText) => {
  let text = geometryText || "";
  if (!text.trim()) {
    try {
      const iframe = document.querySelector('#uuv_map_iframe');
      const raw = iframe && iframe.contentWindow && iframe.contentWindow.document.getElementById('raw_output');
      if (raw && (raw.innerText || raw.textContent || "").trim()) {
        text = raw.innerText || raw.textContent || "";
      }
    } catch (e) {
      console.log("Could not read map iframe geometry output", e);
    }
  }
  return [missionType, text];
}
"""

BUILD_MISSION_AND_GO_JS = """
(missionType, geometryText) => {
  let text = geometryText || "";
  if (!text.trim()) {
    try {
      const iframe = document.querySelector('#uuv_map_iframe');
      const raw = iframe && iframe.contentWindow && iframe.contentWindow.document.getElementById('raw_output');
      if (raw && (raw.innerText || raw.textContent || "").trim()) {
        text = raw.innerText || raw.textContent || "";
      }
    } catch (e) {
      console.log("Could not read map iframe geometry output", e);
    }
  }
  setTimeout(() => {
    if (window.goToSimulatorTab) {
      window.goToSimulatorTab();
    }
  }, 800);
  return [missionType, text];
}
"""

DEFAULT_RESULTS_BUTTON_HTML = """
<button class="view-results-btn disabled" disabled>
  View Results
</button>
"""

ACTIVE_RESULTS_BUTTON_HTML = """
<button class="view-results-btn active" onclick="goToResultsTab()">
  View Results
</button>
<div class="small-muted">Go to Results tab. Your simulation is ready.</div>
"""

MISSION_READY_FOR_SIM_TEXT = "Now that mission parameters are set, go to UUV simulation."


def mission_builder_visibility(mission_type: str) -> tuple[Any, Any]:
    """Toggle Mission Builder geometry hints."""
    return (
        gr.update(visible=mission_type in ISR_MISSIONS or mission_type in SEARCH_MISSIONS),
        gr.update(visible=mission_type in PAYLOAD_MISSIONS),
    )


def _mission_sequence_visibility(mission_type: str) -> Any:
    """Hide manual repeat sequencing for ISR endurance planning."""
    if mission_type in ISR_MISSIONS:
        return gr.update(visible=False, value=1)
    return gr.update(visible=True)


def _energy_equivalence_planning_basis(summary: dict[str, Any]) -> tuple[float, str]:
    """Choose the conservative report energy value for the secondary equivalence lens."""
    for label, key in (
        ("Conservative mission energy estimate (P95)", "p95_energy_kwh"),
        ("Planning-level mission energy estimate (P80)", "p80_energy_kwh"),
        ("Expected mission energy estimate (P50)", "p50_energy_kwh"),
    ):
        value = safe_float(summary.get(key))
        if value is not None:
            return value, label
    return 0.0, "Mission energy unavailable"


def mission_input_visibility(mission_type: str) -> tuple[Any, Any, Any, Any]:
    """Toggle simulator input groups by mission mode."""
    return (
        gr.update(visible=mission_type in SEARCH_MISSIONS),
        gr.update(visible=mission_type in PAYLOAD_MISSIONS),
        gr.update(visible=mission_type in ISR_MISSIONS),
        _mission_sequence_visibility(mission_type),
    )


def sustainment_projection_visibility(enabled: bool) -> Any:
    """Show optional mission projection controls only when requested."""
    return gr.update(visible=bool(enabled))


def refresh_map(region: str) -> str:
    """Refresh the Leaflet map iframe for the selected region."""
    return build_leaflet_iframe(region)


def build_mission_and_prefill(mission_type: str, geometry_json_text: str) -> tuple[Any, ...]:
    """Build a mission context and prefill simulator inputs."""
    result = build_mission_context(mission_type, geometry_json_text, METOC_SERVICE)
    df = rows_to_dataframe(result.environment_rows, ("Environmental / Geometry Item", "Value", "Unit"))
    html = env_table_to_html(result.environment_rows, "Mission Geometry and Environmental Data" if result.ok else "Mission Build Status")
    if not result.ok or result.context is None:
        return (
            {},
            result.status,
            df,
            html,
            geometry_json_text,
            mission_type,
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(visible=mission_type in SEARCH_MISSIONS),
            gr.update(visible=mission_type in PAYLOAD_MISSIONS),
            gr.update(visible=mission_type in ISR_MISSIONS),
            _mission_sequence_visibility(mission_type),
        )

    context = result.context
    area = context.area
    environment = context.environment
    context_dict = context.to_dict()
    context_dict["source_geometry_json"] = geometry_json_text
    area_km2 = getattr(area, "total_area_km2", area.area_km2)
    width_km = getattr(area, "width_km", None)
    height_km = getattr(area, "height_km", None)
    return (
        context_dict,
        f"{result.status}\n\n{MISSION_READY_FOR_SIM_TEXT}",
        df,
        html,
        geometry_json_text,
        mission_type,
        area_km2 or 10,
        width_km or 3,
        height_km or 3,
        getattr(area, "route_distance_km", None) or 10,
        getattr(area, "route_heading_deg", None) or 0,
        environment.current_speed_kts_mean or 0.5,
        environment.current_direction_deg_mean or 0,
        environment.sea_surface_temp_c_mean or 25,
        gr.update(visible=mission_type in SEARCH_MISSIONS),
        gr.update(visible=mission_type in PAYLOAD_MISSIONS),
        gr.update(visible=mission_type in ISR_MISSIONS),
        _mission_sequence_visibility(mission_type),
    )


def _area_environment_from_state(
    mission_type: str,
    manual_area_km2: float,
    width_km: float,
    height_km: float,
    route_distance_km: float,
    route_heading_deg: float,
    current_mean_kts: float,
    current_direction_deg: float,
    temp_mean_c: float,
    context: dict[str, Any],
) -> tuple[str, MissionArea | MissionAreaSet, EnvironmentData]:
    """Rebuild structured area/environment values from Gradio state."""
    if context:
        mission_type = str(context.get("mission_type") or mission_type)
        area_payload = context.get("area", {})
        env_payload = context.get("environment", {})
        if isinstance(area_payload, dict) and area_payload.get("geometry_type") == "MultiArea":
            area = MissionAreaSet.from_dict(area_payload)
        else:
            area = MissionArea.from_dict(area_payload if isinstance(area_payload, dict) else context)
        environment = EnvironmentData(**env_payload) if isinstance(env_payload, dict) else EnvironmentData()
        environment.current_speed_kts_mean = safe_float(current_mean_kts, environment.current_speed_kts_mean)
        environment.current_direction_deg_mean = safe_float(current_direction_deg, environment.current_direction_deg_mean)
        environment.sea_surface_temp_c_mean = safe_float(temp_mean_c, environment.sea_surface_temp_c_mean)
        return mission_type, area, environment

    environment = EnvironmentData(
        current_speed_kts_mean=safe_float(current_mean_kts, 0.5),
        current_direction_deg_mean=safe_float(current_direction_deg, 0.0),
        sea_surface_temp_c_mean=safe_float(temp_mean_c, 25.0),
    )
    if mission_type in SEARCH_MISSIONS:
        manual_area = safe_float(manual_area_km2, 10.0) or 10.0
        side_km = math.sqrt(max(manual_area, 0.1))
        area = manual_rectangle_area(
            side_km,
            side_km,
            manual_area,
        )
    elif mission_type in ISR_MISSIONS:
        manual_area = safe_float(manual_area_km2, 10.0) or 10.0
        width = safe_float(width_km, 0.0) or 0.0
        height = safe_float(height_km, 0.0) or 0.0
        if width <= 0 or height <= 0:
            side_km = math.sqrt(max(manual_area, 0.1))
            width = side_km
            height = side_km
        area = manual_rectangle_area(
            width,
            height,
            manual_area,
        )
    else:
        area = manual_payload_route(
            safe_float(route_distance_km, 10.0) or 10.0,
            safe_float(route_heading_deg, 0.0) or 0.0,
        )
    return mission_type, area, environment


def _planning_weeks(value: object) -> float:
    """Convert compact planning-duration UI text to weeks."""
    mapping = {
        "1 week": 1.0,
        "1 month": 4.0,
        "3 months": 13.0,
    }
    return mapping.get(str(value), safe_float(value, 4.0) or 4.0)


def _apply_salinity_policy(
    environment: EnvironmentData,
    has_loaded_context: bool,
) -> EnvironmentData:
    """Preserve Mission Builder salinity and keep standalone simulations on standard seawater."""
    if has_loaded_context:
        if not environment.salinity_source:
            environment.salinity_source = "standard_assumption"
        return environment
    environment.sea_surface_salinity_psu = None
    environment.sea_water_density_kg_m3 = None
    environment.salinity_source = "standard_assumption"
    environment.salinity_error = None
    environment.salinity_query_params = {"source": "standard_assumption", "note": "salinity not applied"}
    return environment


def run_from_ui(
    platform_name: str,
    mission_type: str,
    manual_area_km2: float,
    width_km: float,
    height_km: float,
    route_distance_km: float,
    route_heading_deg: float,
    additional_transit_km: float,
    track_spacing_m: float,
    return_to_start: bool,
    speed_kts: float,
    battery_sets_available: int,
    recharge_allowed: bool,
    mission_sequences: int,
    rng_seed: str,
    current_mean_kts: float,
    current_direction_deg: float,
    temp_mean_c: float,
    context: dict[str, Any],
    battery_condition: str = "Medium",
    operations_per_week: float = 1.0,
    planning_duration: str = "1 week",
    generator_efficiency: float = 0.84,
    payload_weight_kg: float = 0.0,
    sustainment_projection_enabled: bool = False,
) -> tuple[Any, ...]:
    """Run the simulation and return all Gradio result outputs."""
    try:
        parsed_seed = parse_rng_seed(rng_seed)
    except ValueError as exc:
        return (
            f"Invalid seed: {exc}",
            DEFAULT_RESULTS_BUTTON_HTML,
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(value=None, visible=False),
            gr.update(),
            gr.update(value=None),
            gr.update(value=None),
            gr.update(),
        )
    mission_type, area, environment = _area_environment_from_state(
        mission_type,
        manual_area_km2,
        width_km,
        height_km,
        route_distance_km,
        route_heading_deg,
        current_mean_kts,
        current_direction_deg,
        temp_mean_c,
        context,
    )
    environment = _apply_salinity_policy(environment, bool(context))
    vehicle = VEHICLE_CATALOG[platform_name]
    effective_mission_sequences = 1 if mission_type in ISR_MISSIONS else max(1, safe_int(mission_sequences, 1))
    effective_operations_per_week = safe_float(operations_per_week, 1.0) or 1.0
    effective_planning_duration = str(planning_duration or "1 week")
    if not sustainment_projection_enabled:
        effective_operations_per_week = 1.0
        effective_planning_duration = "1 week"
    simulation_area = area.aggregate_area() if isinstance(area, MissionAreaSet) and mission_type in SEARCH_MISSIONS else area
    result = run_energy_simulation(
        vehicle=vehicle,
        mission_type=mission_type,
        area=simulation_area,
        environment=environment,
        additional_transit_km=safe_float(additional_transit_km, 0.0) or 0.0,
        track_spacing_m=safe_float(track_spacing_m, 200.0) or 200.0,
        return_to_start=bool(return_to_start),
        speed_kts=safe_float(speed_kts, vehicle.nominal_speed_kts) or vehicle.nominal_speed_kts,
        battery_sets_available=max(1, safe_int(battery_sets_available, 1)),
        recharge_allowed=bool(recharge_allowed),
        mission_sequences=effective_mission_sequences,
        rng_seed=parsed_seed,
        battery_condition=str(battery_condition).lower(),
        stochastic_usable_battery_enabled=True,
        reserve_fraction=0.0,
        sustainment_missions_per_week=effective_operations_per_week,
        sustainment_planning_weeks=_planning_weeks(effective_planning_duration),
        sustainment_generator_efficiency=safe_float(generator_efficiency, 0.84) or 0.84,
        payload_weight_kg=safe_float(payload_weight_kg, 0.0) or 0.0,
    )
    summary = result.summary
    if isinstance(area, MissionAreaSet) and mission_type in SEARCH_MISSIONS:
        summary.update(
            {
                "number_of_search_areas": len(area.areas),
                "metoc_sample_count": len(area.representative_points),
                "metoc_lookup_points": area.representative_points,
                "total_search_area_km2": area.total_area_km2,
                "metoc_aggregation_method": "area-centroid vector average",
            }
        )
    summary["return_to_start"] = summary.get("payload_recovery_mode") == "return_to_start"
    summary["additional_transit_km"] = safe_float(additional_transit_km, 0.0) or 0.0
    status = (
        f"Simulation complete. Conservative mission energy: {float(summary['p95_energy_kwh']):.1f} kWh (P95). "
        f"Planning-level battery sets required: {summary['battery_sets_required_p80']} (P80)."
    )
    if summary["battery_inventory_sufficient_no_recharge"]:
        status += " Battery inventory is sufficient without recharge."
    elif summary.get("vehicle_rechargeable") is False:
        status += f" Inventory shortfall: {summary['battery_shortfall_p80']} set(s); plan replacement one-way inventory or energy production."
    elif summary.get("recharge_allowed"):
        status += f" Battery inventory shortfall: {summary['battery_shortfall_p80']} set(s); recharge/swap sequence required."
    else:
        status += f" Battery inventory shortfall: {summary['battery_shortfall_p80']} set(s); recharge is not enabled."
    if mission_type in SEARCH_MISSIONS:
        status += f" Recommended track orientation: {summary['recommended_track_orientation']}."
    if mission_type in ISR_MISSIONS:
        status += (
            f" Estimated ISR endurance: {float(summary.get('isr_total_inventory_endurance_hr', 0)):.1f} hr using available inventory; "
            f"completed patrol loops using inventory: {summary.get('isr_completed_loops_total_inventory', 0)}."
        )
    status += " Go to Results tab. Your simulation is ready."
    summary["rng_seed_requested"] = parsed_seed
    summary["rng_seed_used"] = summary.get("rng_seed")

    simulation_inputs = {
        "additional_transit_km": safe_float(additional_transit_km, 0.0) or 0.0,
        "track_spacing_m": safe_float(track_spacing_m, 200.0) or 200.0,
        "return_to_start": bool(return_to_start),
        "speed_kts": safe_float(speed_kts, vehicle.nominal_speed_kts) or vehicle.nominal_speed_kts,
        "battery_sets_available": max(1, safe_int(battery_sets_available, 1)),
        "recharge_allowed": bool(recharge_allowed),
        "mission_sequences": effective_mission_sequences,
        "rng_seed_requested": parsed_seed,
        "rng_seed_used": summary.get("rng_seed"),
        "manual_current_speed_kts": safe_float(current_mean_kts),
        "manual_current_direction_deg": safe_float(current_direction_deg),
        "manual_sea_surface_temp_c": safe_float(temp_mean_c),
        "battery_condition": str(battery_condition).lower(),
        "payload_weight_kg": safe_float(payload_weight_kg, 0.0) or 0.0,
        "sustainment_projection_enabled": bool(sustainment_projection_enabled),
        "operations_per_week": effective_operations_per_week,
        "planning_duration": effective_planning_duration,
        "generator_efficiency": safe_float(generator_efficiency, 0.84) or 0.84,
    }
    summary["sustainment_projection_enabled"] = bool(sustainment_projection_enabled)
    energy_summary_html = build_report_table_html(build_energy_summary_rows(summary), "Energy Detail")
    battery_sustainment_html = (
        build_report_table_html(build_battery_sustainment_rows(summary), "Battery and Sustainment Detail")
        + build_report_table_html(build_sustainment_projection_rows(summary), "Sustainment Projection Lens")
    )
    mission_geometry_html = build_report_table_html(
        build_mission_geometry_summary_rows(summary, area, environment, simulation_inputs),
        "Mission Geometry Detail",
    )
    environmental_inputs_html = build_report_table_html(
        build_environmental_input_rows(summary, environment),
        "Environmental Detail",
    )
    equivalence_energy_kwh, equivalence_basis = _energy_equivalence_planning_basis(summary)
    energy_equivalence_html = build_report_table_html(
        build_energy_equivalence_rows(equivalence_energy_kwh, equivalence_basis),
        "Energy Storage Equivalence Lens",
    )
    fig_time = build_energy_time_chart(
        result.energy_samples_kwh,
        result.duration_samples_hr,
        float(summary["usable_battery_per_set_kwh"]),
        int(summary["battery_sets_available"]),
        vehicle.recharge_hr,
        int(summary["battery_sets_required_p80"]),
        mission_type=mission_type,
    )
    fig_dist = build_distribution_chart(result.energy_samples_kwh, float(summary["p80_energy_kwh"]), float(summary["total_available_kwh"]), mission_type=mission_type)
    fig_snapshot = build_mapping_snapshot_chart(summary, area, environment, safe_float(track_spacing_m, 200.0) or 200.0)
    primary_visual_update = gr.update(value=fig_snapshot, visible=True)
    overlay_update = gr.update(value=None, visible=False)
    source_geometry_json = context.get("source_geometry_json") if context else None
    _json_record_path, _csv_record_path = write_run_record(
        mission_type=mission_type,
        area=simulation_area,
        vehicle=vehicle,
        environment=environment,
        simulation_inputs=simulation_inputs,
        simulation_summary=summary,
        result_rows=result.result_rows,
        source_geometry_json=str(source_geometry_json) if source_geometry_json else None,
    )
    return (
        status,
        ACTIVE_RESULTS_BUTTON_HTML,
        energy_summary_html,
        battery_sustainment_html,
        mission_geometry_html,
        environmental_inputs_html,
        fig_time,
        fig_dist,
        primary_visual_update,
        overlay_update,
        summary,
        build_energy_planner_summary_html(summary, area, environment, vehicle),
        energy_equivalence_html,
        metoc_html(environment, METOC_SERVICE),
    )


def platform_defaults(platform_name: str) -> tuple[float, str]:
    """Return default speed and platform info for a selected vehicle."""
    vehicle = VEHICLE_CATALOG[platform_name]
    info = (
        f"Battery nameplate: {vehicle.battery_kwh} kWh | "
        f"Usable planning fraction: {vehicle.usable_fraction * 100:.0f}% | "
        f"Est. endurance: {vehicle.estimated_endurance_hr} hr | Recharge: {vehicle.recharge_hr} hr\n\n"
        f"{vehicle.source_note}\n{vehicle.usable_basis}"
    )
    return vehicle.nominal_speed_kts, info


def create_demo() -> gr.Blocks:
    """Create the Gradio Blocks application."""
    empty_rows = [("Draw a mission area or route, then click Build Mission and Load Environment.", "", "")]
    empty_df = rows_to_dataframe(empty_rows, ("Environmental / Geometry Item", "Value", "Unit"))

    with gr.Blocks(title=APP_NAME) as demo:
        mission_context_state = gr.State({})
        sim_results_state = gr.State({})

        gr.Markdown(
            """
# UUV Mission Planning and Energy Simulator

Build a mission first, then run a single-UUV energy estimate. The simulator can also run by itself if no map mission is built.
"""
        )
        gr.Markdown(f"<div class='build-label'>Current dev build: {APP_VERSION}</div>")

        with gr.Tab("1. Mission Builder"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### Mission Setup")
                    mission_type_builder = gr.Dropdown(MISSION_TYPES, value="ISR", label="Mission type")
                    region_select = gr.Dropdown(list(REGION_PRESETS.keys()), value="Guam", label="Operating region")
                    refresh_map_btn = gr.Button("Refresh Map Region")
                    search_note = gr.Markdown("Draw a **line, rectangle, or polygon** for ISR; draw a **rectangle or polygon** for Area Search / MCM.", visible=True)
                    payload_note = gr.Markdown("Draw a **line** from drop point / launch point to target site.", visible=False)
                    geometry_json = gr.Textbox(label="Map geometry", lines=1, visible=False, elem_id="geometry_json_box")
                    build_fetch_btn = gr.Button("Build Mission and Load Environment", variant="primary")
                    build_go_sim_btn = gr.Button("Load Mission and Go to Simulator")
                    mission_status = gr.Textbox(label="Mission Builder Status", lines=3, interactive=False)
                with gr.Column(scale=2):
                    map_html = gr.HTML(value=build_leaflet_iframe("Guam"), label="Mission Map")

            mission_env_html = gr.HTML(value=env_table_to_html(empty_rows), label="Mission Geometry and Environmental Data")
            env_table = gr.Dataframe(value=empty_df, label="Mission Geometry and Environmental Data Raw Table", interactive=False, wrap=True, visible=False)

        with gr.Tab("2. Single-UUV Simulator"):
            mission_loaded_md = gr.Markdown("No mission context loaded. You can still run the simulator with manual inputs.")
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### UUV Profile")
                    platform_select = gr.Dropdown(list(VEHICLE_CATALOG.keys()), value="REMUS 300 - 4.5 kWh", label="UUV platform")
                    speed_default, info_default = platform_defaults("REMUS 300 - 4.5 kWh")
                    platform_info = gr.Textbox(label="Platform baseline", lines=5, interactive=False, value=info_default)
                    mission_type_sim = gr.Dropdown(MISSION_TYPES, value="ISR", label="Mission type")
                    speed_kts = gr.Number(label="Vehicle speed through water, kts", value=speed_default)
                    battery_sets_available = gr.Number(label="Battery sets on hand", value=1, precision=0)
                    battery_condition = gr.Dropdown(["Low", "Medium", "High"], value="Medium", label="Battery condition / starting efficiency")
                    recharge_allowed = gr.Checkbox(label="Recharge / battery swap allowed if required", value=True)
                    mission_sequences = gr.Number(label="Mission sequences (payload/search only)", value=1, precision=0, visible=False)
                    rng_seed = gr.Textbox(label="Monte Carlo random seed, optional", placeholder="Leave blank to generate and record a seed")
                    gr.Markdown("### Environment")
                    current_mean = gr.Number(label="Current speed mean, kts", value=0.5)
                    current_dir = gr.Number(label="Current direction mean, deg", value=0)
                    temp_mean = gr.Number(label="Sea surface temperature mean, deg C", value=25)

                with gr.Column(scale=1):
                    search_group = gr.Group(visible=False)
                    with search_group:
                        gr.Markdown("### Search Mission Inputs")
                        manual_area_km2 = gr.Number(label="Mission search area, sq km", value=10)
                        width_km = gr.Number(label="Search area width, km", value=3, visible=False)
                        height_km = gr.Number(label="Search area height, km", value=3, visible=False)
                        track_spacing_m = gr.Number(label="Swath lane width / track spacing, meters", value=200)
                        gr.Markdown("The app calculates lanes, track length, turn burden, and recommended orientation in the background.")
                    isr_group = gr.Group(visible=True)
                    with isr_group:
                        gr.Markdown("### ISR Persistence Inputs")
                        gr.Markdown("ISR uses the loaded patrol route or perimeter and reports maximum endurance-based time on station.")
                    payload_group = gr.Group(visible=False)
                    with payload_group:
                        gr.Markdown("### Payload Delivery Inputs")
                        route_distance_km = gr.Number(label="Route distance, km", value=10)
                        route_heading_deg = gr.Number(label="Route heading, deg", value=0)
                        payload_weight = gr.Number(label="Payload weight, kg", value=0)
                        gr.Markdown("Optional payload mass carried by the UUV. Used as a small trim/integration planning burden. Leave 0 if unknown.")
                        return_to_start = gr.Checkbox(label="Vehicle returns to start after delivery", value=True)
                    additional_transit_km = gr.Number(label="Additional transit distance, km", value=0)
                    sustainment_projection_enabled = gr.Checkbox(label="Mission sustainment projection lens", value=False)
                    sustainment_projection_group = gr.Group(visible=False)
                    with sustainment_projection_group:
                        gr.Markdown("### Sustainment Projection")
                        operations_per_week = gr.Number(label="Operations per week", value=1)
                        planning_duration = gr.Dropdown(["1 week", "1 month", "3 months"], value="1 week", label="Planning duration")
                        generator_efficiency = gr.Number(label="Generator efficiency", value=0.84)
                    run_btn = gr.Button("Run UUV Energy Simulation", variant="primary")
                    run_status = gr.Textbox(label="Run Status", lines=4, interactive=False)
                    view_results_button = gr.HTML(DEFAULT_RESULTS_BUTTON_HTML)

        with gr.Tab("3. Results"):
            gr.HTML("<div id='results-anchor'></div>")
            results_card = gr.HTML("<div class='uuv-card'>Run a mission simulation to populate results.</div>")
            metoc_results_card = gr.HTML("")
            with gr.Row():
                mission_map_snapshot_plot = gr.Plot(label="Mission Visual Summary", visible=True)
                energy_time_plot = gr.Plot(label="Mission Energy Progress and Battery Lens")
            results_plot = gr.Plot(label="Mission Energy Uncertainty Distribution")
            gr.Markdown("### Energy Detail")
            gr.Markdown(
                "Expected, planning-level, and conservative estimates correspond to the 50th, 80th, "
                "and 95th percentile simulation results. They are used to show how mission energy "
                "demand changes under uncertainty."
            )
            energy_summary_table = gr.HTML("")
            gr.Markdown("### Battery and Sustainment Detail")
            battery_sustainment_table = gr.HTML("")
            gr.Markdown("### Mission Geometry Detail")
            mission_geometry_summary_table = gr.HTML("")
            gr.Markdown("### Environmental Detail")
            environmental_inputs_table = gr.HTML("")
            gr.Markdown("### Energy Storage Equivalence Lens")
            energy_equivalence_table = gr.HTML("")
            gr.Markdown(
                "Energy-equivalence values are provided as a secondary sustainment-planning lens. "
                "Oil-equivalent values are approximate conversions and do not imply direct fuel interchangeability."
            )
            search_overlay_plot = gr.Plot(label="Search Pattern Overlay", visible=False)

        refresh_map_btn.click(refresh_map, inputs=[region_select], outputs=[map_html])
        mission_type_builder.change(mission_builder_visibility, inputs=[mission_type_builder], outputs=[search_note, payload_note])
        mission_type_sim.change(mission_input_visibility, inputs=[mission_type_sim], outputs=[search_group, payload_group, isr_group, mission_sequences])
        sustainment_projection_enabled.change(sustainment_projection_visibility, inputs=[sustainment_projection_enabled], outputs=[sustainment_projection_group])
        platform_select.change(platform_defaults, inputs=[platform_select], outputs=[speed_kts, platform_info])
        build_fetch_btn.click(
            build_mission_and_prefill,
            inputs=[mission_type_builder, geometry_json],
            js=BUILD_MISSION_JS,
            outputs=[
                mission_context_state,
                mission_status,
                env_table,
                mission_env_html,
                geometry_json,
                mission_type_sim,
                manual_area_km2,
                width_km,
                height_km,
                route_distance_km,
                route_heading_deg,
                current_mean,
                current_dir,
                temp_mean,
                search_group,
                payload_group,
                isr_group,
                mission_sequences,
            ],
        ).then(context_markdown, inputs=[mission_context_state], outputs=[mission_loaded_md])
        build_go_sim_btn.click(
            build_mission_and_prefill,
            inputs=[mission_type_builder, geometry_json],
            js=BUILD_MISSION_AND_GO_JS,
            outputs=[
                mission_context_state,
                mission_status,
                env_table,
                mission_env_html,
                geometry_json,
                mission_type_sim,
                manual_area_km2,
                width_km,
                height_km,
                route_distance_km,
                route_heading_deg,
                current_mean,
                current_dir,
                temp_mean,
                search_group,
                payload_group,
                isr_group,
                mission_sequences,
            ],
        ).then(context_markdown, inputs=[mission_context_state], outputs=[mission_loaded_md])
        run_btn.click(
            run_from_ui,
            inputs=[
                platform_select,
                mission_type_sim,
                manual_area_km2,
                width_km,
                height_km,
                route_distance_km,
                route_heading_deg,
                additional_transit_km,
                track_spacing_m,
                return_to_start,
                speed_kts,
                battery_sets_available,
                recharge_allowed,
                mission_sequences,
                rng_seed,
                current_mean,
                current_dir,
                temp_mean,
                mission_context_state,
                battery_condition,
                operations_per_week,
                planning_duration,
                generator_efficiency,
                payload_weight,
                sustainment_projection_enabled,
            ],
            outputs=[
                run_status,
                view_results_button,
                energy_summary_table,
                battery_sustainment_table,
                mission_geometry_summary_table,
                environmental_inputs_table,
                energy_time_plot,
                results_plot,
                mission_map_snapshot_plot,
                search_overlay_plot,
                sim_results_state,
                results_card,
                energy_equivalence_table,
                metoc_results_card,
            ],
        )
    return demo

demo = create_demo()


def launch(**kwargs) -> None:
    """Launch the Gradio app."""
    demo.launch(
        css=CUSTOM_CSS,
        js=CUSTOM_JS,
        **kwargs,
    )


if __name__ == "__main__":
    launch()
