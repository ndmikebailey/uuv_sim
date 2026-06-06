"""Hugging Face/Gradio entrypoint for the UUV mission planning app."""

from __future__ import annotations

import math
from typing import Any
from uuid import uuid4

import gradio as gr

from app.components.map_iframe import build_leaflet_iframe, build_report_map_overlay_iframe
from app.ui.reporting import (
    build_battery_sustainment_rows,
    build_battery_detail_helper,
    build_detail_section_html,
    build_distribution_chart,
    build_energy_equivalence_rows,
    build_energy_detail_helper,
    build_energy_planner_summary_html,
    build_energy_time_chart,
    build_energy_summary_rows,
    build_engineering_snapshot_caption,
    build_environment_detail_helper,
    build_environmental_input_rows,
    build_geometry_detail_helper,
    build_mapping_snapshot_chart,
    build_mission_geometry_summary_rows,
    build_sustainment_projection_helper,
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
from services.metoc_fusion import MetocFusionService, standard_seawater_environment
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
:root {
  color-scheme: light dark;
  --uuv-panel-bg: #ffffff;
  --uuv-panel-soft-bg: #f8fafc;
  --uuv-table-head-bg: #e5edf7;
  --uuv-border: #cbd5e1;
  --uuv-border-strong: #94a3b8;
  --uuv-text: #0f172a;
  --uuv-heading: #020617;
  --uuv-muted: #334155;
  --uuv-subtle: #64748b;
  --uuv-marker: #0f172a;
  --uuv-warning-bg: #fef3c7;
  --uuv-warning-text: #713f12;
  --uuv-link: #1d4ed8;
}
.light, [data-theme="light"], .gradio-container.light {
  --uuv-panel-bg: #ffffff;
  --uuv-panel-soft-bg: #f8fafc;
  --uuv-table-head-bg: #e5edf7;
  --uuv-border: #cbd5e1;
  --uuv-border-strong: #94a3b8;
  --uuv-text: #0f172a;
  --uuv-heading: #020617;
  --uuv-muted: #334155;
  --uuv-subtle: #64748b;
  --uuv-marker: #0f172a;
  --uuv-warning-bg: #fef3c7;
  --uuv-warning-text: #713f12;
  --uuv-link: #1d4ed8;
}
.dark, [data-theme="dark"], .gradio-container.dark {
  --uuv-panel-bg: #111827;
  --uuv-panel-soft-bg: rgba(15, 23, 42, 0.72);
  --uuv-table-head-bg: #1f2937;
  --uuv-border: #374151;
  --uuv-border-strong: #475569;
  --uuv-text: #e5e7eb;
  --uuv-heading: #f9fafb;
  --uuv-muted: #cbd5e1;
  --uuv-subtle: #9ca3af;
  --uuv-marker: #f9fafb;
  --uuv-warning-bg: rgba(234, 179, 8, 0.18);
  --uuv-warning-text: #fef3c7;
  --uuv-link: #60a5fa;
}
.uuv-card {
  border: 1px solid var(--uuv-border);
  border-radius: 12px;
  padding: 14px 16px;
  background: var(--uuv-panel-bg);
  color: var(--uuv-text);
  margin: 10px 0;
}
.uuv-card h1, .uuv-card h2, .uuv-card h3,
.detail-section-card h1, .detail-section-card h2, .detail-section-card h3,
.mission-decision-brief h1, .mission-decision-brief h2, .mission-decision-brief h3 {
  color: var(--uuv-heading);
}
.uuv-card a { color: var(--uuv-link); }
.full-width-card { width: 100%; }
.uuv-table { width: 100%; border-collapse: collapse; font-size: 14px; color: var(--uuv-text); }
.uuv-table th, .uuv-table td {
  border-bottom: 1px solid var(--uuv-border);
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
  color: var(--uuv-text);
}
.uuv-table th { background: var(--uuv-table-head-bg); color: var(--uuv-heading); }
.uuv-table tbody tr { background: var(--uuv-panel-bg); }
.uuv-table .value { font-weight: 700; }
.uuv-attribution, .small-muted { color: var(--uuv-subtle); font-size: 12px; margin-top: 8px; }
.uuv-render-cycle { width: 100%; }
.planner-summary {
  border-color: #2563eb;
  background: var(--uuv-panel-bg);
}
.planner-summary h3 { margin-top: 0; }
.planner-summary p { margin: 8px 0; line-height: 1.45; }
.mission-decision-brief h2 { margin: 0 0 12px 0; }
.decision-topline { display: grid; grid-template-columns: minmax(120px, 180px) 1fr; gap: 14px; align-items: stretch; }
.decision-status { display: flex; align-items: center; justify-content: center; border-radius: 8px; padding: 14px; font-weight: 900; font-size: 20px; }
.decision-status.green, .decision-kpi.green { background: #064e3b; border-color: #10b981; }
.decision-status.yellow, .decision-kpi.yellow { background: var(--uuv-warning-bg); border-color: #eab308; color: var(--uuv-warning-text); }
.decision-status.red, .decision-kpi.red { background: #7f1d1d; border-color: #ef4444; }
.decision-status.green, .decision-kpi.green, .decision-status.red, .decision-kpi.red { color: #f9fafb; }
.decision-status.gray, .decision-kpi.gray { background: var(--uuv-table-head-bg); border-color: var(--uuv-border-strong); color: var(--uuv-text); }
.decision-kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); gap: 10px; margin-top: 14px; }
.decision-kpi { border: 1px solid var(--uuv-border-strong); border-radius: 8px; padding: 10px; min-height: 76px; color: var(--uuv-text); }
.decision-kpi-label { color: var(--uuv-muted); font-size: 12px; font-weight: 700; }
.decision-kpi-value { font-size: 20px; font-weight: 900; margin-top: 6px; }
.decision-kpi-note { color: var(--uuv-text); font-size: 12px; margin-top: 4px; }
.decision-kpi.green .decision-kpi-label, .decision-kpi.green .decision-kpi-note,
.decision-kpi.green .decision-kpi-value,
.decision-kpi.red .decision-kpi-label, .decision-kpi.red .decision-kpi-note,
.decision-kpi.red .decision-kpi-value {
  color: #e5e7eb;
}
.decision-kpi.yellow .decision-kpi-label, .decision-kpi.yellow .decision-kpi-note,
.decision-kpi.yellow .decision-kpi-value {
  color: var(--uuv-warning-text);
}
.planning-scope-radio .wrap {
  display: grid;
  grid-template-columns: repeat(2, minmax(160px, 1fr));
  gap: 10px;
}
.planning-scope-radio label {
  border: 1px solid var(--uuv-border-strong);
  border-radius: 8px;
  background: var(--uuv-table-head-bg);
  color: var(--uuv-text);
  font-weight: 800;
  padding: 10px 12px;
}
.planning-scope-radio label:has(input:checked) {
  background: #ef4444;
  border-color: #f87171;
  color: #f9fafb;
}
.executive-results-summary {
  border: 1px solid var(--uuv-border);
  border-left: 3px solid #60a5fa;
  border-radius: 8px;
  background: var(--uuv-panel-soft-bg);
  color: var(--uuv-text);
  padding: 10px 12px;
  margin-top: 12px;
}
.executive-results-title { color: var(--uuv-muted); font-size: 12px; font-weight: 800; text-transform: uppercase; }
.executive-results-text { color: var(--uuv-text); font-size: 13px; line-height: 1.45; margin: 5px 0 0 0; }
.detail-section-card h3 { margin-bottom: 6px; }
.section-note { color: var(--uuv-muted); font-size: 13px; line-height: 1.45; margin: 0 0 10px 0; }
.detail-table-wrap { margin-top: 10px; }
.section-insight-card {
  border: 1px solid var(--uuv-border);
  border-radius: 8px;
  background: var(--uuv-panel-soft-bg);
  color: var(--uuv-text);
  padding: 10px 12px;
  margin: 8px 0 10px 0;
}
.mini-title { color: var(--uuv-muted); font-size: 12px; font-weight: 800; margin-bottom: 8px; }
.mini-caption { color: var(--uuv-text); font-size: 12px; margin-top: 7px; }
.mini-bar { position: relative; height: 14px; border-radius: 999px; overflow: hidden; background: var(--uuv-table-head-bg); border: 1px solid var(--uuv-border-strong); }
.mini-bar.secondary { margin-top: 6px; opacity: 0.92; }
.mini-range { height: 24px; overflow: visible; margin: 16px 4px 20px 4px; }
.mini-fill { display: inline-block; height: 100%; vertical-align: top; background: #60a5fa; }
.mini-fill.planning { background: #60a5fa; }
.mini-fill.conservative { background: #f87171; }
.mini-fill.neutral { background: #94a3b8; }
.mini-marker { position: absolute; top: -5px; height: 32px; border-left: 2px solid var(--uuv-marker); }
.mini-marker span { position: absolute; top: 30px; left: -12px; color: var(--uuv-muted); font-size: 10px; font-weight: 800; }
.report-plot label { display: none !important; }
.report-visual-grid {
  gap: 12px;
  align-items: stretch;
}
.report-visual-card {
  width: 100%;
  min-width: 0;
  overflow: visible;
}
.report-plot {
  width: 100%;
  min-height: 470px;
  display: block;
  overflow: visible;
}
.report-map-card {
  border: 1px solid var(--uuv-border);
  border-radius: 12px;
  padding: 12px;
  background: var(--uuv-panel-bg);
  color: var(--uuv-text);
  box-sizing: border-box;
  min-height: 0;
  overflow: visible;
}
.report-map-card h3 { margin: 0 0 10px 0; }
.report-map-card iframe { width: 100%; height: 410px; min-height: 410px; display: block; }
.report-map-output { width: 100%; }
.report-map-unavailable { min-height: 0; color: var(--uuv-muted); font-size: 13px; }
.engineering-snapshot-caption {
  color: var(--uuv-muted);
  font-size: 12px;
  margin-top: -6px;
  padding: 0 4px 8px 4px;
}
.traceability-detail { margin: 10px 0; }
.traceability-detail summary { cursor: pointer; font-weight: 800; padding: 10px 0; }
.metoc-assessment, .metoc-panel, .metoc-card-grid { width: 100%; max-width: none; }
.metoc-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.metoc-provider-status { display: flex; flex-wrap: wrap; gap: 8px 14px; }
.posture { font-weight: 800; font-size: 18px; padding: 8px 12px; border-radius: 10px; background: var(--uuv-table-head-bg); color: var(--uuv-text); }
.report-table { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 14px; color: var(--uuv-text); }
.report-table th, .report-table td {
  border-bottom: 1px solid var(--uuv-border);
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
  word-wrap: break-word;
  overflow-wrap: anywhere;
  color: var(--uuv-text);
}
.report-table th { background: var(--uuv-table-head-bg); color: var(--uuv-heading); }
.report-table tbody tr { background: var(--uuv-panel-bg); }
.report-table .metric-col { width: 60%; }
.report-table .value-col { width: 40%; }
.metoc-grid, .metoc-card-grid { width: 100%; max-width: none; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 12px; }
.metoc-card { width: 100%; min-width: 0; max-width: none; border-radius: 10px; padding: 10px; min-height: 120px; border: 2px solid #4b5563; }
.metoc-card.green { background: #064e3b; border-color: #10b981; }
.metoc-card.yellow { background: var(--uuv-warning-bg); border-color: #eab308; color: var(--uuv-warning-text); }
.metoc-card.red { background: #7f1d1d; border-color: #ef4444; }
.metoc-card.green, .metoc-card.red { color: #f9fafb; }
.metoc-card.gray { background: var(--uuv-table-head-bg); border-color: var(--uuv-border-strong); color: var(--uuv-text); }
.metoc-title { font-weight: 800; font-size: 15px; }
.metoc-level { font-weight: 900; font-size: 17px; margin: 6px 0; }
.metoc-value { font-size: 14px; }
.metoc-note { font-size: 12px; color: var(--uuv-text); margin-top: 6px; }
.metoc-card.green .metoc-title, .metoc-card.green .metoc-level, .metoc-card.green .metoc-value, .metoc-card.green .metoc-note,
.metoc-card.red .metoc-title, .metoc-card.red .metoc-level, .metoc-card.red .metoc-value, .metoc-card.red .metoc-note {
  color: #e5e7eb;
}
.metoc-card.yellow .metoc-title, .metoc-card.yellow .metoc-level, .metoc-card.yellow .metoc-value, .metoc-card.yellow .metoc-note {
  color: var(--uuv-warning-text);
}
.gradio-container .plot-container, .gradio-container .js-plotly-plot { max-width: 100%; }
.build-label {
  color: var(--uuv-subtle);
  font-size: 12px;
  margin: -4px 0 10px 0;
}
"""

CUSTOM_JS = """
function() {
  function requestLayoutRefresh() {
    const refresh = function() {
      try {
        window.dispatchEvent(new Event('resize'));
        const doc = document.documentElement;
        const body = document.body;
        const root = document.querySelector('.gradio-container') || body;
        const rootRect = root && root.getBoundingClientRect ? root.getBoundingClientRect() : { bottom: 0 };
        const height = Math.ceil(Math.max(
          doc ? doc.scrollHeight : 0,
          body ? body.scrollHeight : 0,
          rootRect.bottom || 0
        ) + 32);
        if (window.parentIFrame && typeof window.parentIFrame.size === 'function') {
          window.parentIFrame.size(height);
        }
      } catch (error) {
        console.log("Could not refresh UUV layout", error);
      }
    };
    [0, 80, 240, 700].forEach(function(delay) {
      window.setTimeout(function() { window.requestAnimationFrame(refresh); }, delay);
    });
  }
  window.uuvRequestLayoutRefresh = requestLayoutRefresh;

  function setGeometryBox(text) {
    const box = document.querySelector('#geometry_json_box textarea');
    if (!box) return;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    setter.call(box, text);
    box.dispatchEvent(new Event('input', { bubbles: true }));
    box.dispatchEvent(new Event('change', { bubbles: true }));
  }

  if (window.__uuvGeometryMessageHandler) {
    window.removeEventListener('message', window.__uuvGeometryMessageHandler);
  }
  window.__uuvGeometryMessageHandler = function(event) {
    if (!event.data || event.data.type !== 'uuv_geometry') return;
    setGeometryBox(JSON.stringify(event.data.payload || {}, null, 2));
    requestLayoutRefresh();
  };
  window.addEventListener('message', window.__uuvGeometryMessageHandler);

  if (!window.__uuvLayoutObserver) {
    let layoutTimer = null;
    const schedule = function() {
      window.clearTimeout(layoutTimer);
      layoutTimer = window.setTimeout(requestLayoutRefresh, 60);
    };
    const attachObserver = function() {
      const root = document.querySelector('.gradio-container') || document.body;
      if (!root) return;
      window.__uuvLayoutObserver = new MutationObserver(schedule);
      window.__uuvLayoutObserver.observe(root, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['style', 'class', 'hidden', 'data-uuv-render-token']
      });
      document.addEventListener('click', function(event) {
        const target = event.target;
        if (target && target.closest && target.closest('button, [role="tab"]')) {
          requestLayoutRefresh();
        }
      }, true);
      requestLayoutRefresh();
    };
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', attachObserver, { once: true });
    } else {
      attachObserver();
    }
  } else {
    requestLayoutRefresh();
  }
}
"""

BUILD_MISSION_JS = """
(missionType, geometryText) => {
  let text = geometryText || "";
  if (!text.trim()) {
    try {
      const frames = Array.from(document.querySelectorAll('iframe.uuv-map-iframe, #uuv_map_iframe'));
      const iframe = frames.reverse().find(frame => frame && frame.isConnected && frame.contentWindow);
      const raw = iframe && iframe.contentWindow && iframe.contentWindow.document.getElementById('raw_output');
      if (raw && (raw.innerText || raw.textContent || "").trim()) {
        text = raw.innerText || raw.textContent || "";
      }
    } catch (e) {
      console.log("Could not read map iframe geometry output", e);
    }
  }
  if (window.uuvRequestLayoutRefresh) window.uuvRequestLayoutRefresh();
  return [missionType, text];
}
"""

DEFAULT_RESULTS_BUTTON_UPDATE = gr.update(value="Go to Results", interactive=False)
ACTIVE_RESULTS_BUTTON_UPDATE = gr.update(value="Go to Results", interactive=True)

MISSION_READY_FOR_SIM_TEXT = "Now that mission parameters are set, go to UUV simulation."
MONTE_CARLO_MODE = "Monte Carlo run"
DETERMINISTIC_MODE = "Deterministic run"
DEFAULT_MONTE_CARLO_RUNS = 1000
MIN_MONTE_CARLO_RUNS = 10
MAX_MONTE_CARLO_RUNS = 10000
SINGLE_MISSION_SCOPE = "Single UUV mission"
MULTI_MISSION_PLANNING_SCOPE = "Multi-mission planning"


def _with_render_token(html_value: str, namespace: str) -> str:
    """Wrap dynamic HTML so Gradio/browser state cannot reuse stale markup."""
    if not html_value:
        return html_value
    token = f"{namespace}-{uuid4().hex}"
    return f"<div class='uuv-render-cycle' data-uuv-render-token='{token}'>{html_value}</div>"


def clear_results_before_run() -> tuple[Any, ...]:
    """Clear dynamic report outputs before mounting a fresh simulation result."""
    return (
        "Preparing a fresh results render...",
        DEFAULT_RESULTS_BUTTON_UPDATE,
        "",
        "",
        "",
        "",
        gr.update(value=None),
        gr.update(value=None),
        gr.update(value=None, visible=False),
        gr.update(value="", visible=False),
        {},
        _with_render_token("<div class='uuv-card'>Running mission simulation...</div>", "results-cleared"),
        "",
        "",
        "",
    )


def select_workflow_tab(tab_id: str) -> Any:
    """Select a top-level workflow tab through Gradio state instead of DOM clicks."""
    return gr.update(selected=tab_id)


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
    """Choose the report energy value for the secondary equivalence lens."""
    if _sustainment_projection_enabled(summary.get("sustainment_projection_enabled")):
        projected_total = safe_float(summary.get("sustainment_total_conservative_energy_kwh"))
        if projected_total is not None:
            return projected_total, "Planning horizon total"
    for label, key in (
        ("Stress case", "conservative_stress_energy_kwh"),
        ("Planning recommendation", "recommended_planning_energy_kwh"),
        ("Expected energy", "expected_energy_kwh"),
        ("Mission energy fallback", "p95_energy_kwh"),
    ):
        value = safe_float(summary.get(key))
        if value is not None:
            return value, label
    return 0.0, "Mission energy unavailable"


def _sustainment_projection_enabled(value: object) -> bool:
    """Return whether the operator selected the multi-mission planning scope."""
    if isinstance(value, str):
        return value == MULTI_MISSION_PLANNING_SCOPE
    return bool(value)


def mission_input_visibility(mission_type: str) -> tuple[Any, Any, Any, Any]:
    """Toggle simulator input groups by mission mode."""
    return (
        gr.update(visible=mission_type in SEARCH_MISSIONS),
        gr.update(visible=mission_type in PAYLOAD_MISSIONS),
        gr.update(visible=mission_type in ISR_MISSIONS),
        _mission_sequence_visibility(mission_type),
    )


def sustainment_projection_visibility(enabled: object) -> Any:
    """Show optional mission projection controls only when requested."""
    return gr.update(visible=_sustainment_projection_enabled(enabled))


def simulation_mode_visibility(simulation_mode: str) -> tuple[Any, Any]:
    """Show Monte Carlo setup controls only for Monte Carlo mode."""
    monte_carlo_enabled = str(simulation_mode or MONTE_CARLO_MODE) == MONTE_CARLO_MODE
    return (
        gr.update(visible=monte_carlo_enabled, interactive=monte_carlo_enabled),
        gr.update(visible=monte_carlo_enabled, interactive=monte_carlo_enabled),
    )


def _monte_carlo_run_count(value: object) -> int:
    """Return guarded Monte Carlo run count from UI input."""
    runs = safe_int(value, DEFAULT_MONTE_CARLO_RUNS)
    return min(MAX_MONTE_CARLO_RUNS, max(MIN_MONTE_CARLO_RUNS, runs))


def resolve_simulation_mode(simulation_mode: str, monte_carlo_runs: object) -> tuple[bool, int]:
    """Resolve UI simulation mode into deterministic flag and run count."""
    deterministic = str(simulation_mode or MONTE_CARLO_MODE) == DETERMINISTIC_MODE
    if deterministic:
        return True, 1
    return False, _monte_carlo_run_count(monte_carlo_runs)


def refresh_map(region: str) -> str:
    """Refresh the Leaflet map iframe for the selected region."""
    return build_leaflet_iframe(region)


def _metoc_points_from_environment(environment: EnvironmentData) -> list[dict[str, float]]:
    """Return report-map METOC point dictionaries from traced query params."""
    points: list[dict[str, float]] = []
    for params in (environment.marine_query_params, environment.weather_query_params):
        if not params:
            continue
        lat = safe_float(params.get("latitude"))
        lon = safe_float(params.get("longitude"))
        if lat is None or lon is None:
            continue
        point = {"lat": float(lat), "lon": float(lon)}
        if point not in points:
            points.append(point)
    return points


def _report_map_overlay_update(
    context: dict[str, Any] | None,
    mission_type: str,
    environment: EnvironmentData,
) -> Any:
    """Build the optional report map overlay only for loaded GPS geometry."""
    if not context:
        return gr.update(value="", visible=False)
    geometry = context.get("source_geometry_json")
    if not isinstance(geometry, str) or not geometry.strip():
        return gr.update(value="", visible=False)
    try:
        import json

        geometry_payload = json.loads(geometry)
    except (TypeError, ValueError):
        return gr.update(
            value=_with_render_token(
                "<div class='report-visual-card report-map-card report-map-unavailable'>Map overlay unavailable; engineering geometry snapshot shown.</div>",
                "report-map-unavailable",
            ),
            visible=True,
        )
    overlay = build_report_map_overlay_iframe(
        geometry_payload,
        mission_type,
        safe_float(environment.current_speed_kts_mean),
        safe_float(environment.current_direction_deg_mean),
        _metoc_points_from_environment(environment),
    )
    if not overlay:
        return gr.update(
            value=_with_render_token(
                "<div class='report-visual-card report-map-card report-map-unavailable'>Map overlay unavailable; engineering geometry snapshot shown.</div>",
                "report-map-unavailable",
            ),
            visible=True,
        )
    return gr.update(value=_with_render_token(overlay, "report-map"), visible=True)


def build_mission_and_prefill(mission_type: str, geometry_json_text: str) -> tuple[Any, ...]:
    """Build a mission context and prefill simulator inputs."""
    result = build_mission_context(mission_type, geometry_json_text, METOC_SERVICE)
    df = rows_to_dataframe(result.environment_rows, ("Environmental / Geometry Item", "Value", "Unit"))
    html = _with_render_token(
        env_table_to_html(result.environment_rows, "Mission Geometry and Environmental Data" if result.ok else "Mission Build Status"),
        "mission-env",
    )
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
        environment.current_speed_kts_mean if environment.current_speed_kts_mean is not None else 0.5,
        environment.current_direction_deg_mean if environment.current_direction_deg_mean is not None else 0,
        environment.sea_surface_temp_c_mean if environment.sea_surface_temp_c_mean is not None else 25,
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
        if environment.sea_surface_salinity_psu is None:
            return environment.merged(standard_seawater_environment())
        if not environment.salinity_source:
            environment.salinity_source = "Standard seawater assumption"
        return environment
    standard = standard_seawater_environment()
    standard.current_speed_kts_mean = environment.current_speed_kts_mean
    standard.current_direction_deg_mean = environment.current_direction_deg_mean
    standard.sea_surface_temp_c_mean = environment.sea_surface_temp_c_mean
    standard.salinity_error = None
    standard.salinity_query_params = {"source": "Standard seawater assumption", "note": "manual/no-GPS mission; live salinity providers not called"}
    return standard


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
    sustainment_projection_enabled: object = False,
    simulation_mode: str = MONTE_CARLO_MODE,
    monte_carlo_runs: int = DEFAULT_MONTE_CARLO_RUNS,
) -> tuple[Any, ...]:
    """Run the simulation and return all Gradio result outputs."""
    deterministic_run, effective_monte_carlo_runs = resolve_simulation_mode(simulation_mode, monte_carlo_runs)
    try:
        parsed_seed = None if deterministic_run else parse_rng_seed(rng_seed)
    except ValueError as exc:
        return (
            f"Invalid seed: {exc}",
            DEFAULT_RESULTS_BUTTON_UPDATE,
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(value=None, visible=False),
            gr.update(),
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
    projection_enabled = _sustainment_projection_enabled(sustainment_projection_enabled)
    effective_operations_per_week = safe_float(operations_per_week, 1.0) or 1.0
    effective_planning_duration = str(planning_duration or "1 week")
    if not projection_enabled:
        effective_operations_per_week = 1.0
        effective_planning_duration = "1 week"
    simulation_area = area.aggregate_area() if isinstance(area, MissionAreaSet) and mission_type in SEARCH_MISSIONS else area
    effective_seed = 0 if deterministic_run else parsed_seed
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
        rng_seed=effective_seed,
        monte_carlo_runs=effective_monte_carlo_runs,
        battery_condition=str(battery_condition).lower(),
        stochastic_usable_battery_enabled=not deterministic_run,
        reserve_fraction=0.0,
        sustainment_missions_per_week=effective_operations_per_week,
        sustainment_planning_weeks=_planning_weeks(effective_planning_duration),
        sustainment_generator_efficiency=safe_float(generator_efficiency, 0.84) or 0.84,
        payload_weight_kg=safe_float(payload_weight_kg, 0.0) or 0.0,
        deterministic_mode=deterministic_run,
    )
    summary = result.summary
    summary["simulation_mode"] = DETERMINISTIC_MODE if deterministic_run else MONTE_CARLO_MODE
    summary["deterministic_run"] = deterministic_run
    summary["monte_carlo_runs_requested"] = effective_monte_carlo_runs
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
    elif mission_type in SEARCH_MISSIONS:
        summary["number_of_search_areas"] = 1
        summary["total_search_area_km2"] = area.area_km2
        summary["search_area_km2"] = area.area_km2
    summary["return_to_start"] = summary.get("payload_recovery_mode") == "return_to_start"
    summary["additional_transit_km"] = safe_float(additional_transit_km, 0.0) or 0.0
    one_way_inventory = summary.get("vehicle_rechargeable") is False
    inventory_label = "vehicle units" if one_way_inventory else "battery sets"
    recommended_energy = float(summary.get("recommended_planning_energy_kwh", summary.get("planning_energy_kwh", 0)) or 0)
    stress_energy = float(summary.get("conservative_stress_energy_kwh", summary.get("conservative_energy_kwh", 0)) or 0)
    if one_way_inventory:
        inventory_sentence = (
            "Vehicle inventory is sufficient without recharge."
            if summary.get("battery_inventory_sufficient_no_recharge")
            else "Vehicle inventory is insufficient without recharge."
        )
    else:
        inventory_sentence = (
            "Battery inventory is sufficient without recharge."
            if summary.get("battery_inventory_sufficient_no_recharge")
            else "Battery inventory is insufficient without recharge."
        )
    status = (
        f"Simulation complete. Planning recommendation: {recommended_energy:.1f} kWh. "
        f"Stress case: {stress_energy:.1f} kWh. "
        f"{inventory_sentence}"
    )
    if mission_type in ISR_MISSIONS:
        endurance = float(summary.get("isr_total_inventory_endurance_hr", 0) or 0)
        loops = int(summary.get("isr_completed_loops_total_inventory", 0) or 0)
        shortfall_kwh = max(recommended_energy - float(summary.get("total_available_kwh", 0) or 0), 0.0)
        if loops >= 1:
            status += f" ISR endurance estimate: {endurance:.1f} hr using available inventory; completed patrol loops: {loops}."
            if shortfall_kwh > 0:
                status += f" Recommended planning shortfall: {shortfall_kwh:.1f} kWh."
            status += " Plan recovery at the endurance window."
        else:
            partial_km = float(summary.get("isr_partial_loop_distance_km_total_inventory") or summary.get("isr_partial_loop_distance_km_single_set") or 0)
            status += f" ISR endurance estimate: {endurance:.1f} hr; partial patrol coverage: {partial_km:.1f} km. Full patrol loop not completed."
        status += " Go to Results tab."
        summary["rng_seed_requested"] = parsed_seed
        summary["rng_seed_used"] = summary.get("rng_seed")
    else:
        recharge_category = str(summary.get("recharge_feasibility_category") or "")
        if not one_way_inventory and recharge_category == "charged_inventory":
            pass
        elif not one_way_inventory and recharge_category == "recharge_supported":
            status += (
                f" Initial charged inventory is short by {float(summary.get('in_mission_recharge_shortfall_kwh') or 0.0):.1f} kWh, "
                "but continuous recharge/swap support prevents a battery-cycle bottleneck."
            )
        elif not one_way_inventory and recharge_category == "recharge_bottleneck":
            status += f" Battery inventory shortfall: {summary['battery_shortfall_recommended']} set(s); recharge cycle is a bottleneck under current assumptions."
        elif not one_way_inventory and recharge_category == "recharge_disabled" and float(summary.get("in_mission_recharge_shortfall_kwh") or 0.0) > 0:
            status += f" Battery inventory shortfall: {summary['battery_shortfall_recommended']} set(s); recharge is not enabled."
        elif summary["battery_inventory_sufficient_no_recharge"]:
            pass
        elif one_way_inventory:
            status += f" Vehicle inventory shortfall: {summary['battery_shortfall_recommended']} unit(s); add one-way inventory or reduce mission burden."
        elif summary.get("recharge_allowed"):
            status += f" Battery inventory shortfall: {summary['battery_shortfall_recommended']} set(s); recharge/swap sequence required."
        else:
            status += f" Battery inventory shortfall: {summary['battery_shortfall_recommended']} set(s); recharge is not enabled."
        if mission_type in SEARCH_MISSIONS:
            status += f" Recommended track orientation: {summary['recommended_track_orientation']}."
        status += " Go to Results tab."
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
        "simulation_mode": summary.get("simulation_mode"),
        "monte_carlo_runs_requested": effective_monte_carlo_runs,
        "manual_current_speed_kts": safe_float(current_mean_kts),
        "manual_current_direction_deg": safe_float(current_direction_deg),
        "manual_sea_surface_temp_c": safe_float(temp_mean_c),
        "battery_condition": str(battery_condition).lower(),
        "payload_weight_kg": safe_float(payload_weight_kg, 0.0) or 0.0,
        "sustainment_projection_enabled": projection_enabled,
        "operations_per_week": effective_operations_per_week,
        "planning_duration": effective_planning_duration,
        "generator_efficiency": safe_float(generator_efficiency, 0.84) or 0.84,
    }
    summary["sustainment_projection_enabled"] = projection_enabled
    energy_summary_html = build_detail_section_html(
        build_energy_summary_rows(summary),
        "Energy Detail",
        "Energy detail compares expected energy, uncertainty allowance, planning recommendation, and stress case. The planning recommendation is derived from the Monte Carlo output distribution using the mean simulated energy plus one standard deviation. The stress case is calculated as the average of the highest-energy 10% of simulation runs. Percentile values are retained in Technical Traceability for auditability, but they are not the primary decision language.",
        build_energy_detail_helper(summary),
    )
    battery_sustainment_html = build_detail_section_html(
        build_battery_sustainment_rows(summary),
        "Battery and Sustainment Detail",
        (
            "Battery sufficiency compares the planning recommendation and stress case against usable inventory energy after reserve, temperature, and battery-condition assumptions. "
            "Single mission default is used because the optional sustainment projection lens is not enabled."
            if not projection_enabled and not bool(context)
            else "Battery sufficiency compares the planning recommendation and stress case against usable inventory energy after reserve, temperature, and battery-condition assumptions."
        ),
        build_battery_detail_helper(summary),
    )
    if projection_enabled:
        battery_sustainment_html += build_detail_section_html(
            build_sustainment_projection_rows(summary),
            "Sustainment Projection Lens",
            "The sustainment lens is an energy-flow projection for the selected horizon and operations tempo. Fuel-equivalent estimate is based on generator input energy using a conservative 10.0 kWh/gal JP-8/diesel tactical-generator planning factor. This is a sustainment-planning estimate, not a generator certification curve.",
            build_sustainment_projection_helper(summary),
            render_title=True,
        )
    geometry_note = (
        "ISR persistence is evaluated as total endurance-window mission energy, with loop distance retained for patrol coverage accounting."
        if mission_type in ISR_MISSIONS
        else "Mission geometry defines the route, transit, or search burden used by the energy model."
    )
    mission_geometry_html = build_detail_section_html(
        build_mission_geometry_summary_rows(summary, area, environment, simulation_inputs),
        "Mission Geometry Detail",
        geometry_note,
        build_geometry_detail_helper(summary),
    )
    environmental_inputs_html = build_detail_section_html(
        build_environmental_input_rows(summary, environment),
        "Environmental Detail",
        "Environmental burden is applied as a planning modifier; Open-Meteo values support planning context. Salinity and density are planning modifiers only and are not tactical oceanographic authority.",
        build_environment_detail_helper(summary),
    )
    equivalence_energy_kwh, equivalence_basis = _energy_equivalence_planning_basis(summary)
    energy_equivalence_title = "Energy Storage Equivalence Lens" if projection_enabled else "Energy Conversion"
    energy_equivalence_note = (
        "Energy-equivalence values are provided as a secondary sustainment-planning lens. Oil-equivalent values are approximate conversions and do not imply direct fuel interchangeability."
        if projection_enabled
        else "Energy conversion values use the single-mission stress case. Oil-equivalent values are approximate conversions and do not imply direct fuel interchangeability."
    )
    energy_equivalence_html = build_detail_section_html(
        build_energy_equivalence_rows(
            equivalence_energy_kwh,
            equivalence_basis,
            float(summary.get("sustainment_fuel_gallons_equivalent") or 0.0),
        ),
        energy_equivalence_title,
        energy_equivalence_note,
        render_title=True,
    )
    fig_time = build_energy_time_chart(
        result.energy_samples_kwh,
        result.duration_samples_hr,
        float(summary["usable_battery_per_set_kwh"]),
        int(summary["battery_sets_available"]),
        vehicle.recharge_hr,
        int(summary["battery_sets_required_recommended"]),
        mission_type=mission_type,
    )
    fig_dist = build_distribution_chart(
        result.energy_samples_kwh,
        float(summary["recommended_planning_energy_kwh"]),
        float(summary["total_available_kwh"]),
        mission_type=mission_type,
        inventory_label="Vehicle inventory" if one_way_inventory else "Battery inventory",
    )
    fig_snapshot = build_mapping_snapshot_chart(summary, area, environment, safe_float(track_spacing_m, 200.0) or 200.0)
    engineering_snapshot_caption = (
        f"<div class='engineering-snapshot-caption'>{build_engineering_snapshot_caption(summary)}</div>"
    )
    primary_visual_update = gr.update(value=fig_snapshot, visible=True)
    overlay_update = _report_map_overlay_update(context, mission_type, environment)
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
        ACTIVE_RESULTS_BUTTON_UPDATE,
        _with_render_token(energy_summary_html, "energy-detail"),
        _with_render_token(battery_sustainment_html, "battery-detail"),
        _with_render_token(mission_geometry_html, "geometry-detail"),
        _with_render_token(environmental_inputs_html, "environment-detail"),
        fig_time,
        fig_dist,
        primary_visual_update,
        overlay_update,
        summary,
        _with_render_token(build_energy_planner_summary_html(summary, area, environment, vehicle), "results-card"),
        _with_render_token(energy_equivalence_html, "energy-equivalence"),
        _with_render_token(metoc_html(environment, METOC_SERVICE), "metoc-results"),
        _with_render_token(engineering_snapshot_caption, "engineering-caption"),
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
        gr.Markdown(f"<div class='build-label'>Current build: {APP_VERSION}</div>")

        with gr.Tabs(selected="builder", elem_id="workflow-tabs") as workflow_tabs:
            with gr.Tab("1. Mission Builder", id="builder"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### Mission Setup")
                        mission_type_builder = gr.Dropdown(MISSION_TYPES, value="ISR", label="Mission type")
                        region_select = gr.Dropdown(list(REGION_PRESETS.keys()), value="Guam", label="Operating region")
                        refresh_map_btn = gr.Button("Refresh Map Region")
                        search_note = gr.Markdown("Draw a **line, rectangle, or polygon** for ISR; draw a **rectangle or polygon** for Area Search / MCM.", visible=True)
                        payload_note = gr.Markdown("Draw a **line** for Route / Transit planning.", visible=False)
                        geometry_json = gr.Textbox(label="Map geometry", lines=1, visible=False, elem_id="geometry_json_box")
                        build_fetch_btn = gr.Button("Build Mission and Load Environment", variant="primary")
                        build_go_sim_btn = gr.Button("Go to UUV Simulator")
                        mission_status = gr.Textbox(label="Mission Builder Status", lines=3, interactive=False)
                    with gr.Column(scale=2):
                        map_html = gr.HTML(value=build_leaflet_iframe("Guam"), label="Mission Map")

                mission_env_html = gr.HTML(value=env_table_to_html(empty_rows), label="Mission Geometry and Environmental Data")
                env_table = gr.Dataframe(value=empty_df, label="Mission Geometry and Environmental Data Raw Table", interactive=False, wrap=True, visible=False)

            with gr.Tab("2. Single-UUV Simulator", id="simulator"):
                mission_loaded_md = gr.Markdown("No mission context loaded. You can still run the simulator with manual inputs.")
                gr.Markdown("### UUV Profile")
                with gr.Row():
                    with gr.Column(scale=1):
                        platform_select = gr.Dropdown(list(VEHICLE_CATALOG.keys()), value="REMUS 300 - 4.5 kWh", label="UUV platform")
                        mission_type_sim = gr.Dropdown(MISSION_TYPES, value="ISR", label="Mission type")
                    with gr.Column(scale=1):
                        speed_default, info_default = platform_defaults("REMUS 300 - 4.5 kWh")
                        speed_kts = gr.Number(label="Vehicle speed through water, kts", value=speed_default)
                        platform_info = gr.Textbox(label="Platform baseline / source note", lines=5, interactive=False, value=info_default)

                gr.Markdown("### Mission Inputs")
                search_group = gr.Group(visible=False)
                with search_group:
                    manual_area_km2 = gr.Number(label="Mission search area, sq km", value=10)
                    width_km = gr.Number(label="Search area width, km", value=3, visible=False)
                    height_km = gr.Number(label="Search area height, km", value=3, visible=False)
                    track_spacing_m = gr.Number(label="Swath lane width / track spacing, meters", value=200)
                    gr.Markdown("The app calculates lanes, track length, turn burden, and recommended orientation in the background.")
                isr_group = gr.Group(visible=True)
                with isr_group:
                    gr.Markdown("ISR uses the loaded patrol route or perimeter and reports maximum endurance-based time on station.")
                payload_group = gr.Group(visible=False)
                with payload_group:
                    route_distance_km = gr.Number(label="Route distance, km", value=10)
                    route_heading_deg = gr.Number(label="Route heading, deg", value=0)
                    payload_weight = gr.Number(label="Carried equipment weight, kg", value=0)
                    gr.Markdown("Optional carried sensor/equipment mass used as a small trim/integration planning burden. Leave 0 if unknown.")
                    return_to_start = gr.Checkbox(label="Vehicle returns to start after route", value=True)
                additional_transit_km = gr.Number(label="Additional transit distance, km", value=0)

                gr.Markdown("### Battery and Inventory")
                with gr.Row():
                    battery_sets_available = gr.Number(label="Battery sets on hand", value=1, precision=0)
                    battery_condition = gr.Dropdown(["Low", "Medium", "High"], value="Medium", label="Battery condition / starting efficiency")
                with gr.Row():
                    recharge_allowed = gr.Checkbox(label="Recharge / battery swap allowed if required", value=True)
                    mission_sequences = gr.Number(label="Mission sequences (route/search only)", value=1, precision=0, visible=False)
                    sustainment_projection_enabled = gr.Radio(
                        [SINGLE_MISSION_SCOPE, MULTI_MISSION_PLANNING_SCOPE],
                        value=SINGLE_MISSION_SCOPE,
                        label="Planning scope",
                        elem_classes=["planning-scope-radio"],
                    )
                sustainment_projection_group = gr.Group(visible=False)
                with sustainment_projection_group:
                    gr.Markdown("### Sustainment Projection")
                    with gr.Row():
                        operations_per_week = gr.Number(label="Operations per week", value=1)
                        planning_duration = gr.Dropdown(["1 week", "1 month", "3 months"], value="1 week", label="Planning duration")
                        generator_efficiency = gr.Number(label="Generator efficiency", value=0.84)

                gr.Markdown("### Environment")
                with gr.Row():
                    current_mean = gr.Number(label="Current speed mean, kts", value=0.5)
                    current_dir = gr.Number(label="Current direction mean, deg", value=0)
                    temp_mean = gr.Number(label="Sea surface temperature mean, deg C", value=25)

                gr.Markdown("### Simulation Mode / Monte Carlo Setup")
                with gr.Group():
                    simulation_mode = gr.Radio(
                        [MONTE_CARLO_MODE, DETERMINISTIC_MODE],
                        value=MONTE_CARLO_MODE,
                        label="Simulation mode",
                    )
                    with gr.Row():
                        monte_carlo_runs_input = gr.Number(
                            label="Number of Monte Carlo runs",
                            value=DEFAULT_MONTE_CARLO_RUNS,
                            precision=0,
                            minimum=MIN_MONTE_CARLO_RUNS,
                            maximum=MAX_MONTE_CARLO_RUNS,
                        )
                        rng_seed = gr.Textbox(label="Random seed, optional", placeholder="Leave blank to generate and record a seed")
                run_btn = gr.Button("Run UUV Energy Simulation", variant="primary")
                run_status = gr.Textbox(label="Run Status", lines=4, interactive=False)
                view_results_button = gr.Button("Go to Results", interactive=False)

            with gr.Tab("3. Results", id="results"):
                gr.HTML("<div id='results-anchor'></div>")
                results_card = gr.HTML("<div class='uuv-card'>Run a mission simulation to populate results.</div>")
                metoc_results_card = gr.HTML("")
                with gr.Row(elem_classes=["report-visual-grid"]):
                    with gr.Column(scale=1, min_width=360, elem_classes=["report-visual-card"]):
                        report_map_overlay = gr.HTML("", visible=False, elem_classes=["report-map-output"])
                    with gr.Column(scale=1, min_width=360, elem_classes=["report-visual-card"]):
                        results_plot = gr.Plot(label=None, show_label=False, elem_classes=["report-plot"])
                with gr.Row(elem_classes=["report-visual-grid"]):
                    with gr.Column(scale=1, min_width=360, elem_classes=["report-visual-card"]):
                        mission_map_snapshot_plot = gr.Plot(label=None, show_label=False, elem_classes=["report-plot"], visible=True)
                        engineering_snapshot_caption_html = gr.HTML("")
                    with gr.Column(scale=1, min_width=360, elem_classes=["report-visual-card"]):
                        energy_time_plot = gr.Plot(label=None, show_label=False, elem_classes=["report-plot"])
                gr.Markdown("### Energy Detail")
                energy_summary_table = gr.HTML("")
                gr.Markdown("### Battery and Sustainment Detail")
                battery_sustainment_table = gr.HTML("")
                gr.Markdown("### Mission Geometry Detail")
                mission_geometry_summary_table = gr.HTML("")
                gr.Markdown("### Environmental Detail")
                environmental_inputs_table = gr.HTML("")
                energy_equivalence_table = gr.HTML("")
                search_overlay_plot = gr.Plot(label=None, show_label=False, elem_classes=["report-plot"], visible=False)

        refresh_map_btn.click(refresh_map, inputs=[region_select], outputs=[map_html])
        mission_type_builder.change(mission_builder_visibility, inputs=[mission_type_builder], outputs=[search_note, payload_note])
        mission_type_sim.change(mission_input_visibility, inputs=[mission_type_sim], outputs=[search_group, payload_group, isr_group, mission_sequences])
        sustainment_projection_enabled.change(sustainment_projection_visibility, inputs=[sustainment_projection_enabled], outputs=[sustainment_projection_group])
        simulation_mode.change(simulation_mode_visibility, inputs=[simulation_mode], outputs=[monte_carlo_runs_input, rng_seed])
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
            lambda: select_workflow_tab("simulator"),
            inputs=None,
            outputs=[workflow_tabs],
        )
        run_inputs = [
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
            simulation_mode,
            monte_carlo_runs_input,
        ]
        run_outputs = [
            run_status,
            view_results_button,
            energy_summary_table,
            battery_sustainment_table,
            mission_geometry_summary_table,
            environmental_inputs_table,
            energy_time_plot,
            results_plot,
            mission_map_snapshot_plot,
            report_map_overlay,
            sim_results_state,
            results_card,
            energy_equivalence_table,
            metoc_results_card,
            engineering_snapshot_caption_html,
        ]
        run_btn.click(
            clear_results_before_run,
            inputs=None,
            outputs=run_outputs,
            queue=False,
        ).then(
            run_from_ui,
            inputs=run_inputs,
            outputs=run_outputs,
            trigger_mode="once",
        )
        view_results_button.click(
            lambda: select_workflow_tab("results"),
            inputs=None,
            outputs=[workflow_tabs],
        )
        demo.queue(default_concurrency_limit=1)
    return demo

demo = create_demo()


def launch(**kwargs) -> None:
    """Launch the Gradio app."""
    kwargs.setdefault("server_name", "0.0.0.0")
    kwargs.setdefault("show_error", True)
    kwargs.setdefault("ssr_mode", False)
    demo.launch(
        css=CUSTOM_CSS,
        js=CUSTOM_JS,
        **kwargs,
    )


if __name__ == "__main__":
    launch()
