"""Hugging Face/Gradio entrypoint for the UUV mission planning app."""

from __future__ import annotations

import math
from typing import Any

import gradio as gr

from app.components.map_iframe import build_leaflet_iframe
from app.ui.reporting import (
    build_distribution_chart,
    build_energy_time_chart,
    build_mapping_snapshot_chart,
    build_search_overlay_chart,
    context_markdown,
    env_table_to_html,
    metoc_html,
    results_html,
    rows_to_dataframe,
)
from core.energy import run_energy_simulation
from core.geometry import manual_payload_route, manual_rectangle_area
from core.mission import build_mission_context
from models.environment_model import EnvironmentData
from models.mission_model import MissionArea
from models.vehicle_model import VEHICLE_CATALOG
from services.marine_api import OpenMeteoMarineClient
from services.metoc_fusion import MetocFusionService
from services.run_logger import write_run_record
from services.weather_api import OpenMeteoWeatherClient
from utils.constants import APP_NAME, MISSION_TYPES, REGION_PRESETS, SEARCH_MISSIONS
from utils.parsing import safe_float, safe_int

METOC_SERVICE = MetocFusionService(
    marine_client=OpenMeteoMarineClient(),
    weather_client=OpenMeteoWeatherClient(),
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
.metoc-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.posture { font-weight: 800; font-size: 18px; padding: 8px 12px; border-radius: 10px; background: #1f2937; }
.metoc-grid { display: grid; grid-template-columns: repeat(5, minmax(140px, 1fr)); gap: 10px; margin-top: 12px; }
.metoc-card { border-radius: 10px; padding: 10px; min-height: 120px; border: 2px solid #4b5563; }
.metoc-card.green { background: #064e3b; border-color: #10b981; }
.metoc-card.yellow { background: rgba(234, 179, 8, 0.16); border-color: #eab308; }
.metoc-card.red { background: #7f1d1d; border-color: #ef4444; }
.metoc-card.gray { background: #374151; border-color: #9ca3af; }
.metoc-title { font-weight: 800; font-size: 15px; }
.metoc-level { font-weight: 900; font-size: 17px; margin: 6px 0; }
.metoc-value { font-size: 14px; }
.metoc-note { font-size: 12px; color: #e5e7eb; margin-top: 6px; }
.gradio-container .plot-container, .gradio-container .js-plotly-plot { max-width: 100%; }
"""

CUSTOM_JS = """
function() {
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


def mission_visibility(mission_type: str) -> tuple[Any, Any, Any, Any]:
    """Toggle search and payload controls."""
    is_payload = mission_type == "Payload Delivery"
    return (
        gr.update(visible=not is_payload),
        gr.update(visible=is_payload),
        gr.update(visible=not is_payload),
        gr.update(visible=is_payload),
    )


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
            gr.update(visible=mission_type == "Payload Delivery"),
        )

    context = result.context
    area = context.area
    environment = context.environment
    context_dict = context.to_dict()
    context_dict["source_geometry_json"] = geometry_json_text
    return (
        context_dict,
        result.status,
        df,
        html,
        geometry_json_text,
        mission_type,
        area.area_km2 or 10,
        area.width_km or 3,
        area.height_km or 3,
        area.route_distance_km or 10,
        area.route_heading_deg or 0,
        environment.current_speed_kts_mean or 0.5,
        environment.current_direction_deg_mean or 0,
        environment.sea_surface_temp_c_mean or 25,
        gr.update(visible=mission_type in SEARCH_MISSIONS),
        gr.update(visible=mission_type == "Payload Delivery"),
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
) -> tuple[str, MissionArea, EnvironmentData]:
    """Rebuild structured area/environment values from Gradio state."""
    if context:
        mission_type = str(context.get("mission_type") or mission_type)
        area_payload = context.get("area", {})
        env_payload = context.get("environment", {})
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
    else:
        area = manual_payload_route(
            safe_float(route_distance_km, 10.0) or 10.0,
            safe_float(route_heading_deg, 0.0) or 0.0,
        )
    return mission_type, area, environment


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
) -> tuple[Any, ...]:
    """Run the simulation and return all Gradio result outputs."""
    parsed_seed = None
    if rng_seed is not None and str(rng_seed).strip():
        seed_text = str(rng_seed).strip()
        try:
            parsed_seed = int(seed_text)
            if parsed_seed < 0:
                raise ValueError
        except ValueError:
            return (
                "Invalid seed. Enter a non-negative integer or leave blank.",
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(value=None),
                gr.update(value=None),
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
    vehicle = VEHICLE_CATALOG[platform_name]
    result = run_energy_simulation(
        vehicle=vehicle,
        mission_type=mission_type,
        area=area,
        environment=environment,
        additional_transit_km=safe_float(additional_transit_km, 0.0) or 0.0,
        track_spacing_m=safe_float(track_spacing_m, 200.0) or 200.0,
        return_to_start=bool(return_to_start),
        speed_kts=safe_float(speed_kts, vehicle.nominal_speed_kts) or vehicle.nominal_speed_kts,
        battery_sets_available=max(1, safe_int(battery_sets_available, 1)),
        recharge_allowed=bool(recharge_allowed),
        mission_sequences=max(1, safe_int(mission_sequences, 1)),
        rng_seed=parsed_seed,
    )
    summary = result.summary
    status = (
        f"Simulation complete. P80 energy: {float(summary['p80_energy_kwh']):.2f} kWh. "
        f"Battery sets required at P80: {summary['battery_sets_required_p80']}."
    )
    if summary["battery_inventory_sufficient_no_recharge"]:
        status += " Battery inventory is sufficient without recharge."
    elif recharge_allowed:
        status += f" Battery inventory shortfall: {summary['battery_shortfall_p80']} set(s); recharge/swap sequence required."
    else:
        status += f" Battery inventory shortfall: {summary['battery_shortfall_p80']} set(s); recharge is not enabled."
    if mission_type in SEARCH_MISSIONS:
        status += f" Recommended track orientation: {summary['recommended_track_orientation']}."

    results_df = rows_to_dataframe(result.result_rows, ("Output", "Value", "Unit"))
    equivalents_df = rows_to_dataframe(result.equivalent_rows, ("Energy Lens", "Value", "Unit"))
    fig_time = build_energy_time_chart(
        result.energy_samples_kwh,
        result.duration_samples_hr,
        float(summary["usable_battery_per_set_kwh"]),
        int(summary["battery_sets_available"]),
        vehicle.recharge_hr,
    )
    fig_dist = build_distribution_chart(result.energy_samples_kwh, float(summary["p80_energy_kwh"]), float(summary["total_available_kwh"]))
    fig_snapshot = build_mapping_snapshot_chart(summary, area, environment, safe_float(track_spacing_m, 200.0) or 200.0)
    fig_overlay = build_search_overlay_chart(summary, area, environment, safe_float(track_spacing_m, 200.0) or 200.0)
    simulation_inputs = {
        "additional_transit_km": safe_float(additional_transit_km, 0.0) or 0.0,
        "track_spacing_m": safe_float(track_spacing_m, 200.0) or 200.0,
        "return_to_start": bool(return_to_start),
        "speed_kts": safe_float(speed_kts, vehicle.nominal_speed_kts) or vehicle.nominal_speed_kts,
        "battery_sets_available": max(1, safe_int(battery_sets_available, 1)),
        "recharge_allowed": bool(recharge_allowed),
        "mission_sequences": max(1, safe_int(mission_sequences, 1)),
        "rng_seed_requested": parsed_seed,
        "rng_seed_used": summary.get("rng_seed"),
        "manual_current_speed_kts": safe_float(current_mean_kts),
        "manual_current_direction_deg": safe_float(current_direction_deg),
        "manual_sea_surface_temp_c": safe_float(temp_mean_c),
    }
    source_geometry_json = context.get("source_geometry_json") if context else None
    json_record_path, csv_record_path = write_run_record(
        mission_type=mission_type,
        area=area,
        vehicle=vehicle,
        environment=environment,
        simulation_inputs=simulation_inputs,
        simulation_summary=summary,
        result_rows=result.result_rows,
        source_geometry_json=str(source_geometry_json) if source_geometry_json else None,
    )
    return (
        status,
        results_df,
        equivalents_df,
        fig_time,
        fig_dist,
        fig_snapshot,
        fig_overlay,
        summary,
        results_html(summary),
        metoc_html(environment, METOC_SERVICE),
        json_record_path,
        csv_record_path,
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

        with gr.Tab("1. Mission Builder"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### Mission Setup")
                    mission_type_builder = gr.Dropdown(MISSION_TYPES, value="ISR", label="Mission type")
                    region_select = gr.Dropdown(list(REGION_PRESETS.keys()), value="Guam", label="Operating region")
                    refresh_map_btn = gr.Button("Refresh Map Region")
                    search_note = gr.Markdown("Draw a **rectangle or polygon** for ISR or Area Search / MCM.", visible=True)
                    payload_note = gr.Markdown("Draw a **line** from drop point / launch point to target site.", visible=False)
                    geometry_json = gr.Textbox(label="Map geometry", lines=1, visible=False, elem_id="geometry_json_box")
                    build_fetch_btn = gr.Button("Build Mission and Load Environment", variant="primary")
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
                    recharge_allowed = gr.Checkbox(label="Recharge / battery swap allowed if required", value=True)
                    mission_sequences = gr.Number(label="Mission sequences / repeated route runs", value=1, precision=0)
                    rng_seed = gr.Textbox(label="Monte Carlo random seed, optional", placeholder="Leave blank to generate and record a seed")
                    gr.Markdown("### Environment")
                    current_mean = gr.Number(label="Current speed mean, kts", value=0.5)
                    current_dir = gr.Number(label="Current direction mean, deg", value=0)
                    temp_mean = gr.Number(label="Sea surface temperature mean, deg C", value=25)

                with gr.Column(scale=1):
                    search_group = gr.Group(visible=True)
                    with search_group:
                        gr.Markdown("### Search Mission Inputs")
                        manual_area_km2 = gr.Number(label="Mission search area, sq km", value=10)
                        width_km = gr.Number(label="Search area width, km", value=3, visible=False)
                        height_km = gr.Number(label="Search area height, km", value=3, visible=False)
                        track_spacing_m = gr.Number(label="Swath lane width / track spacing, meters", value=200)
                        gr.Markdown("The app calculates lanes, track length, turn burden, and recommended orientation in the background.")
                    payload_group = gr.Group(visible=False)
                    with payload_group:
                        gr.Markdown("### Payload Delivery Inputs")
                        route_distance_km = gr.Number(label="Route distance, km", value=10)
                        route_heading_deg = gr.Number(label="Route heading, deg", value=0)
                        return_to_start = gr.Checkbox(label="Vehicle returns to start after delivery", value=True)
                    additional_transit_km = gr.Number(label="Additional transit distance, km", value=0)
                    run_btn = gr.Button("Run UUV Energy Simulation", variant="primary")
                    run_status = gr.Textbox(label="Run Status", lines=4, interactive=False)

        with gr.Tab("3. Results"):
            results_card = gr.HTML("<div class='uuv-card'>Run a mission simulation to populate results.</div>")
            metoc_results_card = gr.HTML("")
            results_table = gr.Dataframe(label="Energy and Battery Outputs", interactive=False, wrap=True)
            equivalents_table = gr.Dataframe(label="Energy Equivalency Lens", interactive=False, wrap=True)
            energy_time_plot = gr.Plot(label="Mission Energy Progress and Battery Lens")
            results_plot = gr.Plot(label="Mission Energy Uncertainty Distribution")
            with gr.Row():
                mission_map_snapshot_plot = gr.Plot(label="Mission Map Snapshot")
                search_overlay_plot = gr.Plot(label="Recommended Search Pattern Overlay")
            with gr.Row():
                run_record_json = gr.File(label="Run record JSON")
                run_results_csv = gr.File(label="Run results CSV")

        refresh_map_btn.click(refresh_map, inputs=[region_select], outputs=[map_html])
        mission_type_builder.change(mission_visibility, inputs=[mission_type_builder], outputs=[search_note, payload_note, search_group, payload_group])
        mission_type_sim.change(mission_visibility, inputs=[mission_type_sim], outputs=[search_note, payload_note, search_group, payload_group])
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
            ],
            outputs=[
                run_status,
                results_table,
                equivalents_table,
                energy_time_plot,
                results_plot,
                mission_map_snapshot_plot,
                search_overlay_plot,
                sim_results_state,
                results_card,
                metoc_results_card,
                run_record_json,
                run_results_csv,
            ],
        )
    return demo


demo = create_demo()


def launch() -> None:
    """Launch the app with Gradio 6-compatible page CSS and JavaScript."""
    demo.launch(css=CUSTOM_CSS, js=CUSTOM_JS)


if __name__ == "__main__":
    launch()
