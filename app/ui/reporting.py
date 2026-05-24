"""UI-only table, HTML, and chart rendering helpers."""

from __future__ import annotations

import math
from html import escape
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from matplotlib.lines import Line2D

from core.environment import current_components, payload_current_penalty
from core.geometry import clipped_search_lanes, isr_path_distance_per_loop_km, local_bounds, search_polygon_points
from models.environment_model import EnvironmentData
from models.mission_model import MissionArea, MissionAreaSet
from services.metoc_fusion import MetocFusionService
from utils.constants import (
    APP_VERSION,
    EARTH_RADIUS_KM,
    ENERGY_MODEL_VERSION,
    ISR_MISSIONS,
    PAYLOAD_MISSIONS,
    SEARCH_MISSIONS,
    VEHICLE_CATALOG_VERSION,
)


def fmt1(value: object, suffix: str = "") -> str:
    """Format visible report values to one decimal place."""
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.1f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def fmt_int(value: object) -> str:
    """Format visible report counts as integers."""
    if value is None or value == "":
        return ""
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return str(value)


def fmt_coord(value: object) -> str:
    """Format visible report coordinates."""
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.5f}"
    except (TypeError, ValueError):
        return str(value)


def _format_display_cell(value: object, unit: str) -> object:
    """Format table cells for display without changing calculation precision."""
    if value is None or value == "":
        return ""
    unit_lower = unit.lower()
    if unit_lower in {"sets", "loops", "sequences", "runs", "lanes"}:
        return fmt_int(value)
    if unit_lower == "w" or unit_lower.startswith("w "):
        return fmt_int(value)
    if unit_lower in {"kwh", "km", "hr", "kts", "deg c", "%", "kw", "m", "kg/m3", "weeks", "missions"}:
        return fmt1(value)
    if isinstance(value, float):
        return fmt1(value)
    return value


def rows_to_dataframe(rows: list[tuple[str, object, str]], columns: tuple[str, str, str]) -> pd.DataFrame:
    """Convert row tuples into a display dataframe."""
    if len(columns) == 2:
        display_rows = [(row[0], row[1]) for row in rows]
    else:
        display_rows = [
            (item, _format_display_cell(value, unit), unit)
            for item, value, unit in rows
        ]
    return pd.DataFrame(display_rows, columns=list(columns))


def _display_value_with_unit(value: object, unit: str) -> str:
    """Return a compact visible value with unit text."""
    display_value = _format_display_cell(value, unit)
    if display_value == "":
        return ""
    return f"{display_value} {unit}".strip()


def build_report_table_html(rows: list[tuple[object, ...]], title: str | None = None) -> str:
    """Render fixed-width report rows as HTML for PDF-friendly display."""
    body: list[str] = []
    for row in rows:
        if len(row) >= 3:
            metric, value, unit = row[0], row[1], str(row[2])
            value_text = _display_value_with_unit(value, unit)
        elif len(row) >= 2:
            metric, value_text = row[0], row[1]
        else:
            continue
        if value_text in (None, ""):
            continue
        body.append(
            "<tr>"
            f"<td>{escape(str(metric))}</td>"
            f"<td>{escape(str(value_text))}</td>"
            "</tr>"
        )
    if not body:
        return ""
    heading = f"<h3>{escape(title)}</h3>" if title else ""
    return f"""
    <div class='uuv-card full-width-card'>
      {heading}
      <table class='report-table'>
        <thead>
          <tr><th class='metric-col'>Metric</th><th class='value-col'>Value</th></tr>
        </thead>
        <tbody>{''.join(body)}</tbody>
      </table>
    </div>
    """


def build_detail_section_html(
    rows: list[tuple[object, ...]],
    title: str,
    note: str = "",
    helper_html: str = "",
    render_title: bool = False,
) -> str:
    """Render a detail section with a short interpretation note, helper visual, and table."""
    table_html = build_report_table_html(rows, None)
    if not table_html:
        return ""
    heading_html = f"<h3>{escape(title)}</h3>" if render_title and title else ""
    note_html = f"<p class='section-note'>{escape(note)}</p>" if note else ""
    table_inner = table_html.replace("<div class='uuv-card full-width-card'>", "<div class='detail-table-wrap'>", 1)
    return f"""
    <div class='uuv-card full-width-card detail-section-card'>
      {heading_html}
      {note_html}
      {helper_html}
      {table_inner}
    </div>
    """


def _mini_marker(label: str, value: float, maximum: float, color: str) -> str:
    """Render one marker inside a compact mini bar."""
    if maximum <= 0:
        return ""
    pct = min(max(value / maximum * 100.0, 0.0), 100.0)
    return (
        f"<span class='mini-marker' style='left:{pct:.1f}%; border-color:{color};'>"
        f"<span>{escape(label)}</span></span>"
    )


def build_energy_detail_helper(summary: dict[str, object]) -> str:
    """Render a compact recommendation-led energy range helper."""
    expected = _as_float(summary.get("expected_energy_kwh") or summary.get("mean_energy_kwh"))
    recommended = _as_float(summary.get("recommended_planning_energy_kwh") or summary.get("planning_energy_kwh") or summary.get("p80_energy_kwh"))
    stress = _as_float(summary.get("conservative_stress_energy_kwh") or summary.get("conservative_energy_kwh") or summary.get("p95_energy_kwh"))
    values = [value for value in (expected, recommended, stress) if value is not None]
    if len(values) < 2 or max(values) <= 0:
        return ""
    maximum = max(values) * 1.15
    markers = "".join(
        marker
        for marker in (
            _mini_marker("Expected", expected or 0.0, maximum, "#60a5fa"),
            _mini_marker("Planning recommendation", recommended or 0.0, maximum, "#fbbf24"),
            _mini_marker("Stress case", stress or 0.0, maximum, "#f87171"),
        )
        if marker
    )
    return (
        "<div class='section-insight-card mini-range-card'>"
        "<div class='mini-title'>Energy uncertainty spread</div>"
        f"<div class='mini-bar mini-range'>{markers}</div>"
        f"<div class='mini-caption'>Expected {fmt1(expected)} kWh | Planning recommendation {fmt1(recommended)} kWh | Stress case {fmt1(stress)} kWh</div>"
        "</div>"
    )


def build_battery_detail_helper(summary: dict[str, object]) -> str:
    """Render recommended/stress demand against usable inventory."""
    total = _as_float(summary.get("total_available_kwh"))
    recommended = _as_float(summary.get("recommended_planning_energy_kwh") or summary.get("planning_energy_kwh") or summary.get("p80_energy_kwh"))
    stress = _as_float(summary.get("conservative_stress_energy_kwh") or summary.get("conservative_energy_kwh") or summary.get("p95_energy_kwh"))
    if not total or total <= 0 or recommended is None:
        return ""
    recommended_pct = max(recommended / total * 100.0, 0.0)
    stress_pct = max((stress or recommended) / total * 100.0, 0.0)
    recommended_bar_pct = min(recommended_pct, 100.0)
    stress_bar_pct = min(stress_pct, 100.0)
    cap_note = " Visual gauge capped at 100%." if recommended_pct > 100.0 or stress_pct > 100.0 else ""
    return (
        "<div class='section-insight-card'>"
        "<div class='mini-title'>Usable inventory coverage</div>"
        f"<div class='mini-bar'><span class='mini-fill planning' style='width:{recommended_bar_pct:.1f}%'></span></div>"
        f"<div class='mini-bar secondary'><span class='mini-fill conservative' style='width:{stress_bar_pct:.1f}%'></span></div>"
        f"<div class='mini-caption'>Planning recommendation uses {fmt1(recommended_pct)}% of inventory; stress case uses {fmt1(stress_pct)}%.{cap_note}</div>"
        "</div>"
    )


def build_sustainment_projection_helper(summary: dict[str, object]) -> str:
    """Render a compact sustainment demand/input comparison."""
    demand = _as_float(summary.get("sustainment_total_conservative_energy_kwh"))
    generator = _as_float(summary.get("sustainment_generator_input_energy_kwh"))
    missions = _as_float(summary.get("sustainment_total_missions"))
    maximum = max(demand or 0.0, generator or 0.0)
    if maximum <= 0:
        return ""
    demand_pct = min(max((demand or 0.0) / maximum * 100.0, 0.0), 100.0)
    generator_pct = min(max((generator or 0.0) / maximum * 100.0, 0.0), 100.0)
    return (
        "<div class='section-insight-card'>"
        "<div class='mini-title'>Projection energy flow</div>"
        f"<div class='mini-bar'><span class='mini-fill planning' style='width:{demand_pct:.1f}%'></span></div>"
        f"<div class='mini-bar secondary'><span class='mini-fill neutral' style='width:{generator_pct:.1f}%'></span></div>"
        f"<div class='mini-caption'>{fmt1(missions)} projected mission(s); {fmt1(demand)} kWh demand, {fmt1(generator)} kWh generator input.</div>"
        "</div>"
    )


def build_geometry_detail_helper(summary: dict[str, object]) -> str:
    """Render a mission-specific geometry scale helper."""
    mission_type = str(summary.get("mission_type") or "")
    if mission_type in ISR_MISSIONS:
        loop = _as_float(summary.get("isr_loop_distance_km"))
        total = _as_float(summary.get("isr_total_patrol_distance_km_total_inventory"))
        if not loop or not total:
            return ""
        loop_pct = min(max(loop / total * 100.0, 0.0), 100.0)
        return (
            "<div class='section-insight-card'>"
            "<div class='mini-title'>Patrol-loop scale</div>"
            f"<div class='mini-bar'><span class='mini-fill planning' style='width:{loop_pct:.1f}%'></span></div>"
            f"<div class='mini-caption'>{fmt1(loop)} km loop compared with {fmt1(total)} km total inventory patrol coverage.</div>"
            "</div>"
        )
    if mission_type in PAYLOAD_MISSIONS:
        route = _as_float(summary.get("route_distance_km"))
        total = _as_float(summary.get("payload_total_modeled_distance_km"))
        if not route or not total:
            return ""
        route_pct = min(max(route / total * 100.0, 0.0), 100.0)
        return (
            "<div class='section-insight-card'>"
            "<div class='mini-title'>Route / transit burden</div>"
            f"<div class='mini-bar'><span class='mini-fill planning' style='width:{route_pct:.1f}%'></span></div>"
            f"<div class='mini-caption'>{fmt1(route)} km direct route within {fmt1(total)} km total modeled distance.</div>"
            "</div>"
        )
    if mission_type in SEARCH_MISSIONS:
        distance = _as_float(summary.get("search_total_distance_km") or summary.get("search_track_distance_km"))
        area = _as_float(summary.get("total_search_area_km2"))
        if not distance and not area:
            return ""
        return (
            "<div class='section-insight-card'>"
            "<div class='mini-title'>Search geometry burden</div>"
            f"<div class='mini-caption'>{fmt1(area)} sq km search area with {fmt1(distance)} km estimated lane/route burden.</div>"
            "</div>"
        )
    return ""


def build_environment_detail_helper(summary: dict[str, object]) -> str:
    """Render a fixed-scale environmental-burden gauge."""
    segments = [
        ("Current", _as_float(summary.get("current_uplift_pct")) or 0.0, "planning"),
        ("Salinity", _as_float(summary.get("salinity_uplift_pct")) or 0.0, "neutral"),
        ("Temperature", _as_float(summary.get("temperature_derating_pct") or summary.get("temp_uplift_pct")) or 0.0, "conservative"),
    ]
    total = sum(value for _, value, _ in segments if value > 0.0)
    if total <= 0:
        return (
            "<div class='section-insight-card environmental-burden-gauge fixed-scale-gauge'>"
            "<div class='mini-title'>Environmental burden gauge</div>"
            "<div class='mini-caption'>No environmental uplift applied.</div>"
            "</div>"
        )
    scale = 10.0 if total <= 10.0 else 20.0
    fills = "".join(
        f"<span class='mini-fill {css}' style='width:{min(max(value / scale * 100.0, 0.0), 100.0):.1f}%'></span>"
        for _, value, css in segments
        if value > 0.0
    )
    labels = " | ".join(f"{label} {fmt1(value)}%" for label, value, _ in segments if value > 0.0)
    return (
        "<div class='section-insight-card environmental-burden-gauge fixed-scale-gauge'>"
        "<div class='mini-title'>Environmental burden gauge</div>"
        f"<div class='mini-bar segmented fixed-scale' data-scale='{scale:.0f}'>{fills}</div>"
        f"<div class='mini-caption'>Total environmental burden: {fmt1(total)}% on a fixed 0-{fmt1(scale, '%')} scale. {escape(labels)}</div>"
        "</div>"
    )


def build_engineering_snapshot_caption(summary: dict[str, object]) -> str:
    """Return a concise caption outside the engineering snapshot plot."""
    mission_type = str(summary.get("mission_type") or "")
    if mission_type in SEARCH_MISSIONS:
        area = _as_float(summary.get("total_search_area_km2") or summary.get("search_area_km2"))
        if area is None:
            width = _as_float(summary.get("search_width_km"))
            height = _as_float(summary.get("search_height_km"))
            area = width * height if width is not None and height is not None else None
        spacing = _as_float(summary.get("track_spacing_m"))
        orientation = str(summary.get("recommended_track_orientation") or "")
        lanes = _as_int(summary.get("search_lane_count"))
        return f"Area: {fmt1(area)} sq km | Track spacing: {fmt_int(spacing)} m | Orientation: {escape(orientation)} | Lanes: {fmt_int(lanes)}"
    if mission_type in ISR_MISSIONS:
        return (
            f"Loop distance: {fmt1(summary.get('isr_loop_distance_km'))} km | "
            f"Endurance: {fmt1(summary.get('isr_total_inventory_endurance_hr'))} hr | "
            f"Loops: {fmt_int(summary.get('isr_completed_loops_total_inventory'))}"
        )
    if mission_type in PAYLOAD_MISSIONS:
        mode = "Return to start" if summary.get("payload_recovery_mode") == "return_to_start" else "One-way / no return"
        return f"Route distance: {fmt1(summary.get('route_distance_km'))} km | Recovery mode: {mode}"
    return ""


def env_table_to_html(rows: list[tuple[str, object, str]], title: str = "Mission Geometry and Environmental Data") -> str:
    """Render mission/environment rows as a Gradio HTML card."""
    body = []
    for item, value, unit in rows:
        value_text = str(_format_display_cell(value, unit))
        body.append(f"<tr><td>{item}</td><td class='value'>{value_text}</td><td>{unit}</td></tr>")
    return f"""
    <div class='uuv-card full-width-card'>
      <h3>{title}</h3>
      <table class='uuv-table'>
        <thead><tr><th>Item</th><th>Value</th><th>Unit</th></tr></thead>
        <tbody>{''.join(body)}</tbody>
      </table>
      <div class='uuv-attribution'><a href='https://open-meteo.com/'>Weather data by Open-Meteo.com</a></div>
    </div>
    """


def _as_float(value: object) -> float | None:
    """Return a float when a planner value is available."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: object) -> int | None:
    """Return an int when a planner value is available."""
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _fmt_value(value: float, digits: int = 2) -> str:
    """Format a report value without synthetic placeholders."""
    if digits == 0:
        return fmt_int(value)
    return fmt1(value)


def _summary_bullet(label: str, text: str | None) -> str:
    """Render one executive-summary bullet when content exists."""
    if not text:
        return ""
    return f"<li><b>{escape(label)}:</b> {escape(text)}</li>"


def _risk_class(label: str) -> str:
    """Map plain risk/status wording to report color classes."""
    lower = str(label or "").lower()
    if any(word in lower for word in ("not feasible", "shortfall", "not covered", "needs")):
        return "red"
    if any(word in lower for word in ("marginal", "limited", "swap", "recharge")):
        return "yellow"
    if any(word in lower for word in ("feasible", "sufficient", "favorable")):
        return "green"
    return "gray"


def _kpi_tile(label: str, value: object, note: str = "", status: str = "") -> str:
    """Render a compact KPI tile."""
    class_name = _risk_class(status or str(value))
    note_html = f"<div class='decision-kpi-note'>{escape(note)}</div>" if note else ""
    return (
        f"<div class='decision-kpi {class_name}'>"
        f"<div class='decision-kpi-label'>{escape(label)}</div>"
        f"<div class='decision-kpi-value'>{escape(str(value))}</div>"
        f"{note_html}</div>"
    )


def _plain_status_text(summary: dict[str, object]) -> tuple[str, str]:
    """Return top-line feasibility and action-oriented recommendation."""
    mission_type = str(summary.get("mission_type") or "")
    if mission_type in ISR_MISSIONS:
        return _isr_status_text(summary)
    recommended = _as_float(summary.get("recommended_planning_energy_kwh") or summary.get("planning_energy_kwh") or summary.get("p80_energy_kwh"))
    stress = _as_float(summary.get("conservative_stress_energy_kwh") or summary.get("conservative_energy_kwh") or summary.get("p95_energy_kwh"))
    total_available = _as_float(summary.get("total_available_kwh"))
    sets_recommended = _as_int(summary.get("battery_sets_required_recommended") or summary.get("battery_sets_required_recommended_planning") or summary.get("battery_sets_required_p80"))
    sets_available = _as_int(summary.get("battery_sets_available"))
    usable_per_set = _as_float(summary.get("usable_battery_per_set_kwh"))
    sets_stress = _as_int(summary.get("battery_sets_required_stress") or summary.get("battery_sets_required_conservative_stress"))
    if sets_stress is None:
        sets_stress = math.ceil(stress / usable_per_set) if stress is not None and usable_per_set and usable_per_set > 0 else sets_recommended
    margin_recommended = (total_available - recommended) if total_available is not None and recommended is not None else None
    stress_ok = sets_available is not None and sets_stress is not None and sets_stress <= sets_available
    planning_ok = sets_available is not None and sets_recommended is not None and sets_recommended <= sets_available
    one_way_inventory = summary.get("vehicle_rechargeable") is False
    recharge_category = str(summary.get("recharge_feasibility_category") or "")
    shortfall = _as_float(summary.get("in_mission_recharge_shortfall_kwh")) or 0.0
    if not one_way_inventory:
        if recharge_category == "charged_inventory":
            return "Feasible", "Feasible. The selected platform can complete the mission with declared charged battery inventory."
        if recharge_category == "recharge_supported":
            return (
                "Feasible with continuous recharge/swap support",
                f"Feasible with continuous recharge/swap support. Initial charged inventory is short by {fmt1(shortfall)} kWh, but recharge time does not create a battery-cycle bottleneck.",
            )
        if recharge_category == "recharge_bottleneck":
            return (
                "Not feasible",
                "Not feasible under current recharge assumptions. The mission exceeds charged inventory and the recharge cycle cannot recover depleted sets before reuse.",
            )
    if mission_type in PAYLOAD_MISSIONS:
        if stress_ok:
            inventory_phrase = "one-way vehicle inventory" if one_way_inventory else "battery inventory"
            return "Feasible", f"Feasible. The selected platform can complete the route/transit plan with the declared {inventory_phrase}; maintain the recorded METOC and energy assumptions for review."
        status = "Marginal" if planning_ok or (margin_recommended is not None and margin_recommended >= 0) else "Not feasible"
        if one_way_inventory:
            return status, f"{status}. The selected route/transit plan exceeds the declared one-way inventory margin; add vehicle units or reduce transit burden."
        return status, f"{status}. The selected route/transit plan exceeds the declared planning margin; reduce transit burden, add inventory, or plan recharge/swap support."
    if mission_type in SEARCH_MISSIONS:
        if stress_ok:
            return "Feasible", "Feasible. The selected platform can complete the search/MCM plan within the declared battery inventory and planning assumptions."
        status = "Marginal" if planning_ok or (margin_recommended is not None and margin_recommended >= 0) else "Not feasible"
        return status, f"{status}. The selected search/MCM plan exceeds declared inventory; reduce area, increase track spacing, add charged inventory, or plan recharge/swap support."
    if stress_ok:
        return "Feasible", "Feasible. The selected platform can complete the mission within the declared inventory and planning assumptions."
    if planning_ok or (margin_recommended is not None and margin_recommended >= 0):
        return "Marginal", "Marginal. The mission covers the recommended planning case, but stress margin is limited; stage extra battery or recharge support."
    return "Not feasible", "Not feasible. Add charged battery inventory, reduce mission burden, or plan recharge/swap support before execution."


def _isr_status_text(summary: dict[str, object]) -> tuple[str, str]:
    """Return ISR feasibility using endurance/loop coverage rather than mission-total battery sets."""
    one_way_inventory = summary.get("vehicle_rechargeable") is False
    recovery_phrase = "recovery/replacement" if one_way_inventory else "recovery/swap"
    completed_total = _as_int(summary.get("isr_completed_loops_total_inventory")) or 0
    completed_single = _as_int(summary.get("isr_completed_loops_single_set") or summary.get("isr_completed_loops")) or 0
    partial_total_km = _as_float(summary.get("isr_partial_loop_distance_km_total_inventory"))
    partial_single_km = _as_float(summary.get("isr_partial_loop_distance_km_single_set"))
    total_distance = _as_float(summary.get("isr_total_patrol_distance_km_total_inventory") or summary.get("isr_total_patrol_distance_km_single_set"))
    single_set_endurance = _as_float(summary.get("isr_single_set_endurance_hr") or summary.get("isr_max_time_on_station_hr"))
    swap_window = _as_float(summary.get("isr_swap_window_hr") or single_set_endurance)
    loop_count = max(completed_total, completed_single)
    partial_km = partial_total_km if partial_total_km is not None else partial_single_km
    if loop_count >= 1:
        if (_as_int(summary.get("battery_sets_available")) or 1) > 1 and total_distance is not None:
            total_inventory_endurance = _as_float(summary.get("isr_total_inventory_endurance_hr"))
            bluf = (
                f"Feasible. One installed set supports approximately {fmt1(single_set_endurance)} hr; "
                f"declared inventory supports approximately {fmt1(total_inventory_endurance)} hr if sequential {recovery_phrase} is available."
            )
        else:
            bluf = (
                f"Feasible. The selected platform supports the ISR patrol for approximately {fmt1(single_set_endurance)} hr "
                f"per installed set, completing {fmt_int(completed_single)} full loop(s) before {recovery_phrase}."
            )
        return (
            "Feasible",
            bluf,
        )
    if single_set_endurance is not None and single_set_endurance > 0 and partial_km is not None and partial_km > 0:
        return (
            "Marginal",
            (
                "Marginal. The selected vehicle cannot complete a full patrol loop, "
                f"but can cover approximately {fmt1(total_distance or partial_km)} km before {recovery_phrase}."
            ),
        )
    return (
        "Not feasible",
        "Not feasible. The selected vehicle does not provide meaningful ISR patrol endurance for the selected route and inventory.",
    )


def _metoc_risk_text(summary: dict[str, object], environment: EnvironmentData) -> str:
    """Return compact METOC risk text for the decision brief."""
    current_uplift = _as_float(summary.get("current_uplift_pct")) or 0.0
    salinity_uplift = _as_float(summary.get("salinity_uplift_pct")) or 0.0
    temp_derating = _as_float(summary.get("temperature_derating_pct")) or 0.0
    if max(current_uplift, salinity_uplift, temp_derating) >= 8.0:
        return "Review"
    if max(current_uplift, salinity_uplift, temp_derating) >= 3.0:
        return "Marginal"
    if environment.weather_summary:
        return "Review"
    return "Favorable"


def _decision_kpis(summary: dict[str, object], environment: EnvironmentData) -> list[str]:
    """Build mission-appropriate KPI tiles for the decision brief."""
    mission_type = str(summary.get("mission_type") or "")
    del environment
    if mission_type in ISR_MISSIONS:
        one_way_inventory = summary.get("vehicle_rechargeable") is False
        expected = _as_float(summary.get("expected_energy_kwh") or summary.get("mean_energy_kwh"))
        recommended = _as_float(summary.get("recommended_planning_energy_kwh") or summary.get("planning_energy_kwh") or summary.get("p80_energy_kwh"))
        stress = _as_float(summary.get("conservative_stress_energy_kwh") or summary.get("conservative_energy_kwh") or summary.get("p95_energy_kwh"))
        partial_km = _as_float(summary.get("isr_partial_loop_distance_km_total_inventory"))
        partial_pct = _as_float(summary.get("isr_remaining_partial_loop_pct"))
        partial_text = f"{fmt1(partial_km)} km" if partial_km is not None else f"{fmt1(partial_pct)}%"
        return [
            _kpi_tile("Expected energy", f"{fmt1(expected)} kWh"),
            _kpi_tile("Planning recommendation", f"{fmt1(recommended)} kWh"),
            _kpi_tile("Stress case", f"{fmt1(stress)} kWh"),
            _kpi_tile("Patrol loop distance", f"{fmt1(summary.get('isr_loop_distance_km'))} km"),
            _kpi_tile("Full loops", f"{fmt_int(summary.get('isr_completed_loops_total_inventory') or summary.get('isr_completed_loops_single_set'))} loops"),
            _kpi_tile("Partial next loop", partial_text),
            _kpi_tile("Endurance per set", f"{fmt1(summary.get('isr_single_set_endurance_hr') or summary.get('isr_max_time_on_station_hr'))} hr"),
            _kpi_tile("Total patrol distance", f"{fmt1(summary.get('isr_total_patrol_distance_km_total_inventory') or summary.get('isr_total_patrol_distance_km_single_set'))} km"),
            _kpi_tile("Recovery / replacement" if one_way_inventory else "Recovery/swap", f"{fmt1(summary.get('isr_swap_window_hr') or summary.get('isr_single_set_endurance_hr'))} hr"),
        ]
    usable_per_set = _as_float(summary.get("usable_battery_per_set_kwh"))
    expected = _as_float(summary.get("expected_energy_kwh") or summary.get("mean_energy_kwh"))
    uncertainty = _as_float(summary.get("energy_uncertainty_allowance_kwh"))
    recommended = _as_float(summary.get("recommended_planning_energy_kwh") or summary.get("planning_energy_kwh") or summary.get("p80_energy_kwh"))
    stress = _as_float(summary.get("conservative_stress_energy_kwh") or summary.get("conservative_energy_kwh") or summary.get("p95_energy_kwh"))
    total_available = _as_float(summary.get("total_available_kwh"))
    sets_recommended = _as_int(summary.get("battery_sets_required_recommended") or summary.get("battery_sets_required_recommended_planning") or summary.get("battery_sets_required_p80"))
    sets_stress = _as_int(summary.get("battery_sets_required_stress") or summary.get("battery_sets_required_conservative_stress"))
    if sets_stress is None:
        sets_stress = math.ceil(stress / usable_per_set) if stress is not None and usable_per_set and usable_per_set > 0 else sets_recommended
    margin = (total_available - recommended) if total_available is not None and recommended is not None else None
    sets_available = int(summary.get("battery_sets_available") or 0)
    one_way_inventory = summary.get("vehicle_rechargeable") is False
    recommended_label = "Vehicle units needed" if one_way_inventory else "Battery sets needed"
    stress_label = "Stress-case units" if one_way_inventory else "Stress-case battery sets"
    return [
        _kpi_tile("Expected energy", f"{fmt1(expected)} kWh"),
        _kpi_tile("Uncertainty allowance", f"{fmt1(uncertainty)} kWh"),
        _kpi_tile("Planning recommendation", f"{fmt1(recommended)} kWh"),
        _kpi_tile("Stress case", f"{fmt1(stress)} kWh"),
        _kpi_tile(recommended_label, fmt_int(sets_recommended), status="sufficient" if sets_recommended and sets_recommended <= sets_available else "marginal"),
        _kpi_tile(stress_label, fmt_int(sets_stress), status="sufficient" if sets_stress and sets_stress <= sets_available else "marginal"),
        _kpi_tile("Inventory margin", f"{fmt1(margin)} kWh", status="sufficient" if margin is not None and margin >= 0 else "shortfall"),
        _kpi_tile("Mission duration", f"{fmt1(summary.get('mean_duration_hr'))} hr"),
    ]


def _monte_carlo_phrase(summary: dict[str, object]) -> str:
    """Return the visible Monte Carlo ensemble phrase."""
    if summary.get("deterministic_run") or str(summary.get("simulation_mode") or "").lower().startswith("deterministic"):
        return "a deterministic single-case estimate"
    for key in ("monte_carlo_runs", "mc_runs", "simulation_count", "num_samples", "n_samples"):
        runs = _as_int(summary.get(key))
        if runs is not None and runs > 0:
            return f"{runs} Monte Carlo trials"
    return "the configured Monte Carlo ensemble"


def _seed_phrase(summary: dict[str, object]) -> str:
    """Return whether the run used a user-fixed deterministic seed."""
    if summary.get("deterministic_run") or str(summary.get("simulation_mode") or "").lower().startswith("deterministic"):
        return "using default assumptions"
    requested_seed = summary.get("rng_seed_requested")
    if requested_seed not in (None, ""):
        return f"using deterministic seed {escape(str(requested_seed))}"
    if "rng_seed_requested" not in summary and summary.get("rng_seed") not in (None, ""):
        return f"using deterministic seed {escape(str(summary.get('rng_seed')))}"
    if summary.get("rng_seed") not in (None, ""):
        return "with a generated seed recorded for traceability"
    return "without a recorded deterministic seed"


def _planning_basis_phrase(summary: dict[str, object]) -> str:
    """Translate planning basis keys into executive-readable text."""
    basis = str(summary.get("planning_energy_basis") or "")
    if basis == "patrol_loop":
        return "ISR mission-total endurance energy"
    if basis == "endurance_window":
        return "endurance-window"
    return "mission-total energy"


def _dominant_factor_phrase(summary: dict[str, object], mission_type: str) -> str:
    """Choose one compact driver phrase for the executive summary."""
    current = _as_float(summary.get("current_uplift_pct")) or 0.0
    salinity = _as_float(summary.get("salinity_uplift_pct")) or 0.0
    temp_derating = _as_float(summary.get("temperature_derating_pct")) or 0.0
    payload_weight = _as_float(summary.get("payload_weight_kg")) or 0.0
    if mission_type in PAYLOAD_MISSIONS and str(summary.get("payload_recovery_mode") or "") == "return_to_start":
        return "return transit distance and route current"
    payload_weight = _as_float(summary.get("payload_weight_kg")) or 0.0
    if payload_weight > 0.0:
        return "payload trim/integration burden and route current"
    if mission_type in SEARCH_MISSIONS:
        if current > 0.05:
            return "track-relative current burden, salinity adjustment, sensor load, and selected platform energy capacity"
        return "search area, track spacing, sensor load, and selected platform energy capacity"
    if current > 0.05:
        return "track-relative current burden"
    if mission_type in ISR_MISSIONS:
        return "patrol loop length and endurance-mode speed"
    if salinity > 0.0:
        return "salinity/buoyancy burden"
    if temp_derating > 0.0:
        return "battery temperature derating"
    return "mission geometry and selected vehicle energy capacity"


def _executive_results_summary_html(summary: dict[str, object], environment: EnvironmentData) -> str:
    """Render a compact scientific executive-results summary."""
    mission_type = str(summary.get("mission_type") or "")
    ensemble = _monte_carlo_phrase(summary)
    seed = _seed_phrase(summary)
    platform = str(summary.get("platform") or "the selected platform")
    if summary.get("deterministic_run") or str(summary.get("simulation_mode") or "").lower().startswith("deterministic"):
        method = f"The simulation used {ensemble} {seed}; technical traceability is retained for audit review."
    else:
        method = f"The simulation used {ensemble} {seed}; percentile outputs are retained in technical traceability."
    expected = _as_float(summary.get("expected_energy_kwh") or summary.get("mean_energy_kwh"))
    recommended = _as_float(summary.get("recommended_planning_energy_kwh") or summary.get("planning_energy_kwh") or summary.get("p80_energy_kwh"))
    stress = _as_float(summary.get("conservative_stress_energy_kwh") or summary.get("conservative_energy_kwh") or summary.get("p95_energy_kwh"))
    recommendation_sentence = (
        f"Expected energy is {fmt1(expected)} kWh. "
        f"Planning recommendation is {fmt1(recommended)} kWh after applying the uncertainty allowance. "
        f"The stress case is {fmt1(stress)} kWh based on the upper tail of the Monte Carlo output distribution."
    )
    if mission_type in ISR_MISSIONS:
        loop_distance = _as_float(summary.get("isr_loop_distance_km"))
        loop_time = _as_float(summary.get("isr_loop_time_hr"))
        loop_energy = _as_float(summary.get("isr_loop_energy_kwh"))
        total_endurance = _as_float(summary.get("isr_total_inventory_endurance_hr"))
        loops_total = _as_int(summary.get("isr_completed_loops_total_inventory"))
        first = (
            f"The modeled ISR mission uses {platform} as a mission-total endurance case: "
            f"{fmt1(loop_distance)} km per loop, {fmt1(loop_time)} hr per loop, and {fmt1(loop_energy)} kWh per loop for loop accounting."
        )
        second = (
            f"The declared inventory supports approximately {fmt1(total_endurance)} hr and {fmt_int(loops_total)} full loop(s), "
            f"with recovery/swap planned near the endurance window. {recommendation_sentence} {method}"
        )
    elif mission_type in SEARCH_MISSIONS:
        area = _as_float(summary.get("total_search_area_km2") or summary.get("search_area_km2"))
        if area is None:
            width = _as_float(summary.get("search_width_km"))
            height = _as_float(summary.get("search_height_km"))
            area = width * height if width is not None and height is not None else None
        spacing = _as_float(summary.get("track_spacing_m"))
        areas = _as_int(summary.get("number_of_search_areas")) or 1
        factor = _dominant_factor_phrase(summary, mission_type)
        first = (
            f"The modeled search/MCM mission uses {platform} across {fmt1(area)} sq km with {fmt1(spacing)} m spacing "
            f"across {fmt_int(areas)} selected area(s)."
        )
        second = (
            f"{recommendation_sentence} Battery sufficiency is driven by {factor}. {method}"
        )
    else:
        route = _as_float(summary.get("route_distance_km"))
        heading = _as_float(summary.get("route_heading_deg"))
        total_distance = _as_float(summary.get("payload_total_modeled_distance_km"))
        factor = _dominant_factor_phrase(summary, mission_type)
        first = (
            f"The modeled route/transit mission uses {platform} over a {fmt1(route)} km route on heading {fmt1(heading)} deg, "
            "with METOC sampled at the route midpoint."
        )
        distance_clause = (
            f" Return-to-start planning increases modeled distance to {fmt1(total_distance)} km."
            if str(summary.get("payload_recovery_mode") or "") == "return_to_start" and total_distance is not None
            else ""
        )
        second = (
            f"{recommendation_sentence} Battery sufficiency is primarily influenced by {factor}, declared inventory, and recovery mode."
            f"{distance_clause} {method}"
        )
    sentences = [sentence for sentence in (first, second) if sentence and "None" not in sentence]
    text = " ".join(sentences[:2])
    return (
        "<div class='executive-results-summary'>"
        "<div class='executive-results-title'>Executive Results Summary</div>"
        f"<p class='executive-results-text'>{escape(text)}</p>"
        "</div>"
    )


def _environmental_burden_text(summary: dict[str, object]) -> str | None:
    """Build the environmental uplift sentence from summary values."""
    multiplier = _as_float(summary.get("isr_environmental_multiplier") or summary.get("environmental_multiplier"))
    current_uplift = _as_float(summary.get("current_uplift_pct"))
    temp_uplift = _as_float(summary.get("temp_uplift_pct"))
    salinity_uplift = _as_float(summary.get("salinity_uplift_pct"))
    total_uplift = (multiplier - 1.0) * 100.0 if multiplier is not None else None
    if total_uplift is None and (current_uplift is not None or temp_uplift is not None or salinity_uplift is not None):
        total_uplift = (current_uplift or 0.0) + (temp_uplift or 0.0) + (salinity_uplift or 0.0)
    if total_uplift is None:
        return None
    detail = ""
    if current_uplift is not None or temp_uplift is not None or salinity_uplift is not None:
        detail = (
            f" (current {_fmt_value(current_uplift or 0.0, 1)}%, "
            f"temperature {_fmt_value(temp_uplift or 0.0, 1)}%, "
            f"salinity {_fmt_value(salinity_uplift or 0.0, 1)}%)"
        )
    return f"Current, temperature, and salinity add an estimated {_fmt_value(total_uplift, 1)}% energy uplift{detail}."


def _payload_planning_note(summary: dict[str, object], area: MissionArea, environment: EnvironmentData) -> str:
    """Build the mission-specific payload planning note."""
    parts: list[str] = []
    route_distance = _as_float(summary.get("route_distance_km") or area.route_distance_km)
    if route_distance is not None:
        parts.append(f"route distance is {_fmt_value(route_distance)} km")
    recovery_mode = str(summary.get("payload_recovery_mode") or "")
    if recovery_mode == "return_to_start":
        parts.append("recovery mode is return to start")
    elif recovery_mode == "one_way":
        parts.append("recovery mode is one-way / no return")
    total_distance = _as_float(summary.get("payload_total_modeled_distance_km"))
    if total_distance is not None and total_distance > 0:
        parts.append(f"total modeled distance is {_fmt_value(total_distance)} km")
    route_heading = _as_float(summary.get("route_heading_deg") or area.route_heading_deg)
    current_speed = _as_float(environment.current_speed_kts_mean)
    current_dir = _as_float(environment.current_direction_deg_mean)
    speed = _as_float(summary.get("speed_kts"))
    if route_heading is not None and current_speed is not None and current_dir is not None:
        along, cross = current_components(current_speed, current_dir, route_heading)
        if speed is not None:
            penalty_pct = payload_current_penalty(current_speed, current_dir, route_heading, speed) * 100.0
            parts.append(
                f"current impact is {fmt1(along, ' kts')} along-track and {fmt1(cross, ' kts')} cross-track, about {fmt1(penalty_pct, '%')} transit uplift"
            )
        else:
            parts.append(f"current impact is {fmt1(along, ' kts')} along-track and {fmt1(cross, ' kts')} cross-track")
    burden = _as_float(summary.get("environmental_multiplier"))
    if burden is not None:
        parts.append(f"expected environmental energy burden is about {_fmt_value((burden - 1.0) * 100.0, 1)}%")
    payload_weight = _as_float(summary.get("payload_weight_kg"))
    payload_penalty_pct = _as_float(summary.get("payload_weight_penalty_pct"))
    if payload_weight and payload_weight > 0:
        parts.append(
            f"carried equipment weight is {fmt1(payload_weight)} kg; equipment carriage penalty: {fmt1(payload_penalty_pct or 0.0, '%')} trim/integration planning burden applied to outbound propulsion energy"
        )
    launch_recovery_energy = _as_float(summary.get("launch_recovery_energy_kwh"))
    if launch_recovery_energy and launch_recovery_energy > 0:
        parts.append(f"launch/recovery overhead is {fmt1(launch_recovery_energy)} kWh")
    catalog_note = str(summary.get("payload_one_way_catalog_note") or "")
    if catalog_note:
        parts.append(catalog_note)
    return "Route / transit mission planning: " + "; ".join(parts) + "." if parts else ""


def _isr_planning_note(summary: dict[str, object]) -> str:
    """Build the mission-specific ISR planning note."""
    parts: list[str] = []
    loop_distance = _as_float(summary.get("isr_loop_distance_km"))
    loop_time = _as_float(summary.get("isr_loop_time_hr"))
    single_set_endurance = _as_float(summary.get("isr_single_set_endurance_hr") or summary.get("isr_max_time_on_station_hr"))
    total_inventory_endurance = _as_float(summary.get("isr_total_inventory_endurance_hr"))
    completed_loops_single = _as_int(summary.get("isr_completed_loops_single_set") or summary.get("isr_completed_loops"))
    completed_loops_total = _as_int(summary.get("isr_completed_loops_total_inventory"))
    loop_energy = _as_float(summary.get("isr_loop_energy_kwh"))
    partial_single_km = _as_float(summary.get("isr_partial_loop_distance_km_single_set"))
    partial_total_km = _as_float(summary.get("isr_partial_loop_distance_km_total_inventory"))
    total_distance_single_km = _as_float(summary.get("isr_total_patrol_distance_km_single_set"))
    total_distance_inventory_km = _as_float(summary.get("isr_total_patrol_distance_km_total_inventory"))
    if loop_distance is not None:
        parts.append(f"patrol loop distance is {fmt1(loop_distance)} km")
    if loop_time is not None:
        parts.append(f"patrol loop time is {fmt1(loop_time)} hr")
    if loop_energy is not None:
        parts.append(f"patrol loop energy for loop accounting is {fmt1(loop_energy)} kWh")
    if single_set_endurance is not None:
        partial_text = f", plus {fmt1(partial_single_km)} km of the next loop" if partial_single_km and partial_single_km > 0.05 else ""
        completed_text = f" after {fmt_int(completed_loops_single)} full loop(s)" if completed_loops_single is not None else ""
        parts.append(f"One installed set supports about {fmt1(single_set_endurance)} hr{completed_text}{partial_text}")
    if total_inventory_endurance is not None:
        partial_text = f", plus {fmt1(partial_total_km)} km of the next loop" if partial_total_km and partial_total_km > 0.05 else ""
        completed_text = f" after {fmt_int(completed_loops_total)} full loop(s)" if completed_loops_total is not None else ""
        parts.append(f"Total available inventory supports about {fmt1(total_inventory_endurance)} hr{completed_text}{partial_text}")
    if total_distance_single_km is not None:
        parts.append(f"Total patrol distance before recovery/swap is {fmt1(total_distance_single_km)} km per installed set")
    if total_distance_inventory_km is not None:
        parts.append(f"Total patrol distance before battery exhaustion using available inventory is {fmt1(total_distance_inventory_km)} km")
    if single_set_endurance is not None:
        parts.append(f"plan recovery or battery swap at about {fmt1(single_set_endurance)} hr per installed set before retasking")
    return "ISR persistence planning: " + "; ".join(parts) + "." if parts else ""


def _search_planning_note(summary: dict[str, object], area: MissionArea) -> str:
    """Build the mission-specific Search/MCM planning note."""
    parts: list[str] = []
    search_area = _as_float(summary.get("total_search_area_km2") or area.area_km2)
    area_count = _as_int(summary.get("number_of_search_areas"))
    metoc_count = _as_int(summary.get("metoc_sample_count"))
    track_spacing = _as_float(summary.get("track_spacing_m"))
    orientation = summary.get("recommended_track_orientation")
    track_distance = _as_float(summary.get("search_track_distance_km"))
    total_distance = _as_float(summary.get("search_total_distance_km"))
    sets_required = _as_int(summary.get("battery_sets_required_recommended") or summary.get("battery_sets_required_p80"))
    sets_available = _as_int(summary.get("battery_sets_available"))
    if search_area is not None:
        if area_count and area_count > 1:
            parts.append(f"uses {fmt_int(area_count)} selected search area(s), totaling {_fmt_value(search_area)} sq km")
        else:
            parts.append(f"search area is {_fmt_value(search_area)} sq km")
    if metoc_count and metoc_count > 1:
        parts.append(f"METOC inputs are averaged from {fmt_int(metoc_count)} area centroid lookup point(s)")
    if track_spacing is not None:
        parts.append(f"track spacing is {_fmt_value(track_spacing, 0)} m")
    if orientation and orientation != "N/A":
        parts.append(f"recommended orientation is {orientation}")
    if track_distance is not None:
        burden = f"estimated track burden is {_fmt_value(track_distance)} km"
        if total_distance is not None:
            burden += f" ({_fmt_value(total_distance)} km including turns/transit)"
        parts.append(burden)
    if sets_required is not None:
        if sets_required > 1:
            parts.append(f"plan {sets_required - 1} battery swap window(s) for a single recommended planning mission")
        elif sets_available is not None and sets_available >= 1:
            parts.append("one battery set covers the single recommended planning mission")
    return "Search/MCM planning: " + "; ".join(parts) + "." if parts else ""


def _mission_planning_note(summary: dict[str, object], area: MissionArea, environment: EnvironmentData) -> str | None:
    """Build a mission-specific planning note."""
    mission_type = str(summary.get("mission_type") or "")
    if mission_type in PAYLOAD_MISSIONS:
        return _payload_planning_note(summary, area, environment)
    if mission_type in ISR_MISSIONS:
        return _isr_planning_note(summary)
    if mission_type in SEARCH_MISSIONS:
        return _search_planning_note(summary, area)
    return None


def build_energy_planner_summary_html(summary: dict[str, object], area: MissionArea, environment: EnvironmentData, vehicle: object | None = None) -> str:
    """
    Build the top decision brief plus lower technical traceability.

    This should read as a planning product first, with reviewer detail below.
    """
    status, recommendation = _plain_status_text(summary)
    kpis = _decision_kpis(summary, environment)
    executive_summary = _executive_results_summary_html(summary, environment)
    decision_html = f"""
    <div class='uuv-card planner-summary mission-decision-brief'>
      <h2>Mission Decision Brief</h2>
      <div class='decision-topline'>
        <div class='decision-status {_risk_class(status)}'>{escape(status)}</div>
        <div>
          <h3>BLUF</h3>
          <p>{escape(recommendation)}</p>
        </div>
      </div>
      {executive_summary}
      <div class='decision-kpi-grid'>{''.join(kpis)}</div>
    </div>
    """
    traceability_html = build_technical_traceability_html(summary, environment, vehicle)
    validation_html = build_validation_comparison_html(summary)
    return decision_html + validation_html + traceability_html


def build_validation_comparison_html(summary: dict[str, object]) -> str:
    """Render an optional V&V comparison block when observed energy is provided."""
    observed = (
        _as_float(summary.get("observed_aus_energy_kwh"))
        or _as_float(summary.get("validation_observed_energy_kwh"))
        or _as_float(summary.get("observed_energy_kwh"))
    )
    if observed is None:
        return ""
    p50 = _as_float(summary.get("p50_energy_kwh"))
    p80 = _as_float(summary.get("p80_energy_kwh"))
    p95 = _as_float(summary.get("p95_energy_kwh"))
    if p50 is None or p80 is None or p95 is None:
        return ""
    if observed < p50:
        position = "below P50"
    elif observed <= p80:
        position = "between P50 and P80"
    elif observed <= p95:
        position = "between P80 and P95"
    else:
        position = "above P95"
    p80_error = ((p80 - observed) / observed * 100.0) if observed else 0.0
    p95_conservatism = ((p95 - observed) / observed * 100.0) if observed else 0.0
    rows = [
        ("Observed AUS energy", observed, "kWh"),
        ("Sim P50", p50, "kWh"),
        ("Sim P80", p80, "kWh"),
        ("Sim P95", p95, "kWh"),
        ("Observed position", position, ""),
        ("P80 error", p80_error, "%"),
        ("P95 conservatism", p95_conservatism, "%"),
        (
            "Validation interpretation",
            "The observed AUS mission energy falls between the revised expected and planning-level estimates."
            if position == "between P50 and P80"
            else f"The observed AUS mission energy is {position} for this Monte Carlo run.",
            "",
        ),
    ]
    return build_report_table_html(rows, "Validation Comparison")


def build_technical_traceability_html(summary: dict[str, object], environment: EnvironmentData, vehicle: object | None = None) -> str:
    """Build the lower technical traceability/model-detail section."""
    source_note = getattr(vehicle, "source_note", "") if vehicle is not None else summary.get("source_note", "")
    usable_basis = getattr(vehicle, "usable_basis", "") if vehicle is not None else summary.get("usable_basis", "")
    hotel_fraction_mean = _as_float(summary.get("hotel_fraction_mean"))
    monte_carlo_rows = [
        ("P50 simulation value", _float_or_blank(summary.get("p50_energy_kwh")), "kWh"),
        ("P80 simulation value", _float_or_blank(summary.get("p80_energy_kwh")), "kWh"),
        ("P95 simulation value", _float_or_blank(summary.get("p95_energy_kwh")), "kWh"),
        ("Recommendation basis", summary.get("recommendation_basis"), ""),
        ("Expected energy definition", "Arithmetic mean of Monte Carlo outputs.", ""),
        ("Uncertainty allowance definition", "Sample standard deviation of Monte Carlo outputs.", ""),
        ("Planning recommendation definition", "Maximum of mean plus one standard deviation and validation-adjusted mean when provided.", ""),
        ("Stress case definition", "Mean of the highest-energy 10% of Monte Carlo outcomes.", ""),
        ("Upper-tail fraction", "10%", ""),
        (
            "Percentile interpretation",
            "P50/P80/P95 are percentiles of the Monte Carlo output distribution. They are retained for audit traceability and are not p-values, z-test results, or statistical confidence intervals.",
            "",
        ),
    ]
    monte_carlo_table = build_report_table_html(monte_carlo_rows, None)
    monte_carlo_detail = (
        "<details class='traceability-detail monte-carlo-traceability'>"
        "<summary>Monte Carlo Technical Traceability</summary>"
        f"{monte_carlo_table}"
        "</details>"
        if monte_carlo_table
        else ""
    )
    rows = [
        ("App version", APP_VERSION, ""),
        ("Energy model version", ENERGY_MODEL_VERSION, ""),
        ("Vehicle catalog version", VEHICLE_CATALOG_VERSION, ""),
        ("Planning basis", summary.get("planning_energy_basis"), ""),
        ("Planning recommendation", _float_or_blank(summary.get("recommended_planning_energy_kwh") or summary.get("planning_energy_kwh") or summary.get("p80_energy_kwh")), "kWh"),
        ("Stress case", _float_or_blank(summary.get("conservative_stress_energy_kwh") or summary.get("conservative_energy_kwh")), "kWh"),
        ("Simulation mode", summary.get("simulation_mode"), ""),
        ("Monte Carlo runs", summary.get("monte_carlo_runs"), ""),
        ("Monte Carlo seed", summary.get("rng_seed"), ""),
        ("Usable battery fraction P10", _float_or_blank(summary.get("battery_usable_fraction_p10")), ""),
        ("Usable battery fraction P50", _float_or_blank(summary.get("battery_usable_fraction_p50")), ""),
        ("Usable battery fraction P90", _float_or_blank(summary.get("battery_usable_fraction_p90")), ""),
        ("Temperature derating basis", summary.get("temperature_derating_basis"), ""),
        ("Active power draw P10", _float_or_blank(summary.get("power_draw_p10_kw")), "kW"),
        ("Active power draw P50", _float_or_blank(summary.get("power_draw_p50_kw")), "kW"),
        ("Active power draw P90", _float_or_blank(summary.get("power_draw_p90_kw")), "kW"),
        ("Speed-adjusted power P50", _float_or_blank(summary.get("vehicle_speed_power_p50_kw") or summary.get("speed_adjusted_power_kw")), "kW"),
        ("Sensor load P50", _float_or_blank(summary.get("mission_sensor_power_p50_w")), "W"),
        ("Mean speed exponent", _float_or_blank(summary.get("speed_exponent_mean")), ""),
        ("Mean hotel power fraction", hotel_fraction_mean * 100.0 if hotel_fraction_mean is not None else "", "%"),
        ("Mean propulsion multiplier", _float_or_blank(summary.get("propulsion_multiplier_mean")), ""),
        ("Mean nominal power scale", _float_or_blank(summary.get("nominal_power_scale_mean")), ""),
        ("Mission sensor-mode model", "enabled" if summary.get("mission_sensor_power_enabled") else "disabled", ""),
        (
            "Sensor-use logic",
            "Active search/survey receives Search/MCM sensor-mode power; added transit receives Route/Transit sensor-mode power."
            if str(summary.get("mission_type") or "") in SEARCH_MISSIONS
            else "",
            "",
        ),
        ("METOC lookup method", _trace_lookup_method(summary, environment), ""),
        ("Multi-area aggregation method", summary.get("metoc_aggregation_method"), ""),
        ("Run-record traceability status", summary.get("run_record_traceability_status", "recorded"), ""),
        ("Source note", source_note, ""),
        ("Usable battery basis", usable_basis, ""),
    ]
    if summary.get("vehicle_rechargeable") is False:
        rows.append(
            (
                "Non-rechargeable inventory basis",
                "Vehicle catalog marks this platform as non-rechargeable; sustainment output is expressed as vehicle units rather than battery sets.",
                "",
            )
        )
    if environment.salinity_source and environment.salinity_source != "Standard seawater assumption":
        rows.insert(12, ("Salinity provider status", environment.salinity_source, ""))
    table = build_report_table_html(rows, None)
    if not table:
        return ""
    return f"<details class='traceability-detail'><summary>Technical Traceability / Model Detail</summary>{table}{monte_carlo_detail}</details>"


def _trace_lookup_method(summary: dict[str, object], environment: EnvironmentData) -> str:
    """Return a compact traceability phrase for METOC lookup."""
    if summary.get("metoc_aggregation_method"):
        return str(summary.get("metoc_aggregation_method"))
    if environment.marine_query_params or environment.weather_query_params:
        return "Mission geometry representative point"
    return "Manual simulator environment"


def _legacy_energy_planner_summary_html(summary: dict[str, object], area: MissionArea, environment: EnvironmentData, vehicle: object | None = None) -> str:
    """Legacy summary retained for reference while decision brief replaces it."""
    del vehicle
    mission_type = str(summary.get("mission_type") or "")
    if mission_type in ISR_MISSIONS:
        total_inventory_endurance = _as_float(summary.get("isr_total_inventory_endurance_hr"))
        single_set_endurance = _as_float(summary.get("isr_single_set_endurance_hr") or summary.get("isr_max_time_on_station_hr"))
        loop_energy = _as_float(summary.get("planning_energy_kwh") or summary.get("isr_loop_energy_kwh"))
        completed_single = _as_int(summary.get("isr_completed_loops_single_set") or summary.get("isr_completed_loops"))
        completed_total = _as_int(summary.get("isr_completed_loops_total_inventory"))
        swap_window = _as_float(summary.get("isr_swap_window_hr") or single_set_endurance)
        partial_single_km = _as_float(summary.get("isr_partial_loop_distance_km_single_set"))
        partial_total_km = _as_float(summary.get("isr_partial_loop_distance_km_total_inventory"))
        total_distance_single_km = _as_float(summary.get("isr_total_patrol_distance_km_single_set"))
        total_distance_inventory_km = _as_float(summary.get("isr_total_patrol_distance_km_total_inventory"))

        bluf = (
            f"ISR patrol endurance is estimated at {fmt1(total_inventory_endurance)} hr using the available battery inventory."
            if total_inventory_endurance is not None
            else None
        )
        energy_demand = (
            f"Conservative planning energy is {fmt1(loop_energy)} kWh per patrol loop."
            if loop_energy is not None
            else None
        )
        sustainment_parts: list[str] = []
        if single_set_endurance is not None:
            partial_text = f", plus {fmt1(partial_single_km)} km of the next loop" if partial_single_km and partial_single_km > 0.05 else ""
            sustainment_parts.append(
                f"One installed set supports approximately {fmt1(single_set_endurance)} hr before recovery/swap{partial_text}."
            )
        if total_inventory_endurance is not None:
            partial_text = f", plus {fmt1(partial_total_km)} km of the next loop" if partial_total_km and partial_total_km > 0.05 else ""
            sustainment_parts.append(
                f"Total available inventory supports approximately {fmt1(total_inventory_endurance)} hr before battery exhaustion{partial_text}."
            )
        if total_distance_single_km is not None:
            sustainment_parts.append(f"Total patrol distance before recovery/swap: {fmt1(total_distance_single_km)} km per installed set.")
        if total_distance_inventory_km is not None:
            sustainment_parts.append(f"Total patrol distance before battery exhaustion using available inventory: {fmt1(total_distance_inventory_km)} km.")
        recharge_swap = (
            f"Plan recovery or battery swap at approximately {fmt1(swap_window)} hr per installed set before retasking."
            if swap_window is not None
            else None
        )
        planning_note = (
            "ISR persistence planning is based on patrol loop distance, endurance-mode speed, "
            "environmental burden, and available battery inventory."
        )
        sections = [
            _summary_bullet("BLUF", bluf),
            _summary_bullet("Energy demand", energy_demand),
            _summary_bullet("Battery sustainment", " ".join(sustainment_parts) if sustainment_parts else None),
            _summary_bullet("Recharge / swap", recharge_swap),
            _summary_bullet("Environmental burden", _environmental_burden_text(summary)),
            _summary_bullet("Planning note", planning_note),
        ]
        return f"""
        <div class='uuv-card planner-summary'>
          <h3>Energy Planner Summary</h3>
          <ul>{''.join(sections)}</ul>
        </div>
        """

    recommended = _as_float(summary.get("recommended_planning_energy_kwh") or summary.get("planning_energy_kwh") or summary.get("p80_energy_kwh"))
    stress = _as_float(summary.get("conservative_stress_energy_kwh") or summary.get("conservative_energy_kwh") or summary.get("p95_energy_kwh"))
    planning_basis = str(summary.get("planning_energy_basis") or "mission_total")
    usable_per_set = _as_float(summary.get("usable_battery_per_set_kwh"))
    sets_required = _as_int(summary.get("battery_sets_required_recommended") or summary.get("battery_sets_required_p80"))
    sets_available = _as_int(summary.get("battery_sets_available"))
    inventory_sufficient_raw = summary.get("battery_inventory_sufficient_no_recharge")
    inventory_sufficient = bool(inventory_sufficient_raw) if inventory_sufficient_raw is not None else None
    recharge_allowed = bool(summary.get("recharge_allowed"))
    vehicle_rechargeable = summary.get("vehicle_rechargeable") is not False
    recharge_category = str(summary.get("recharge_feasibility_category") or "")
    recharge_status = str(summary.get("recharge_feasibility_status") or "")
    recharge_shortfall = _as_float(summary.get("in_mission_recharge_shortfall_kwh")) or 0.0
    conservative_sets_required = math.ceil(stress / usable_per_set) if stress is not None and usable_per_set and usable_per_set > 0 else None
    conservative_inventory_sufficient = (
        conservative_sets_required <= sets_available
        if conservative_sets_required is not None and sets_available is not None
        else None
    )

    bluf: str | None = None
    if vehicle_rechargeable and recharge_category == "charged_inventory":
        bluf = "Feasible. The selected platform can complete the mission with declared charged battery inventory."
    elif vehicle_rechargeable and recharge_category == "recharge_supported":
        bluf = (
            f"Feasible with continuous recharge/swap support. Initial charged inventory is short by {fmt1(recharge_shortfall)} kWh, "
            "but recharge time does not create a battery-cycle bottleneck."
        )
    elif vehicle_rechargeable and recharge_category == "recharge_bottleneck":
        bluf = "Not feasible under current recharge assumptions. The mission exceeds charged inventory and the recharge cycle cannot recover depleted sets before reuse."
    elif conservative_inventory_sufficient is True:
        inventory_label = "vehicle inventory" if not vehicle_rechargeable else "battery inventory"
        bluf = f"Mission is feasible with current {inventory_label} at the conservative stress level."
    elif conservative_inventory_sufficient is False and not vehicle_rechargeable:
        bluf = "Mission needs additional one-way inventory at the conservative stress level."
    elif conservative_inventory_sufficient is False and recharge_allowed:
        bluf = "Mission needs recharge, swap sequencing, or additional charged inventory at the conservative stress level."
    elif conservative_inventory_sufficient is False:
        bluf = "Mission is not covered by current battery inventory at the conservative stress level unless additional charged batteries are staged."
    elif inventory_sufficient is True:
        inventory_label = "vehicle inventory" if not vehicle_rechargeable else "battery inventory"
        bluf = f"Mission is feasible with current {inventory_label} at the planning level."
    elif inventory_sufficient is False and not vehicle_rechargeable:
        bluf = "Mission needs additional one-way inventory at the planning level."
    elif inventory_sufficient is False and recharge_allowed:
        bluf = "Mission needs recharge, swap sequencing, or additional charged inventory at the planning level."
    elif inventory_sufficient is False:
        bluf = "Mission is not covered by current battery inventory at the planning level unless additional charged batteries are staged."
    if recommended is not None:
        basis_text = "for the mission total" if planning_basis == "mission_total" else f"for {planning_basis.replace('_', ' ')}"
        energy_text = f"Planning recommendation is {_fmt_value(recommended)} kWh {basis_text}."
        bluf = f"{bluf} {energy_text}" if bluf else energy_text
    mission_type = str(summary.get("mission_type") or "")
    if mission_type in PAYLOAD_MISSIONS and stress is not None:
        total_available = _as_float(summary.get("total_available_kwh"))
        if total_available is not None:
            conservative_margin = total_available - stress
            if conservative_margin >= 0:
                margin_text = f" Stress-case margin is approximately {fmt1(conservative_margin)} kWh."
                if conservative_margin <= max(0.25, total_available * 0.10):
                    margin_text += " Margin is limited; consider additional battery inventory or recharge support before repeated tasking."
            else:
                margin_text = f" Conservative stress shortfall is approximately {fmt1(abs(conservative_margin))} kWh."
            bluf = f"{bluf}{margin_text}" if bluf else margin_text.strip()

    recharge_swap: str | None = None
    active_sets_required = conservative_sets_required or sets_required
    active_inventory_sufficient = conservative_inventory_sufficient if conservative_inventory_sufficient is not None else inventory_sufficient
    if active_sets_required is not None:
        if not vehicle_rechargeable:
            recharge_swap = "Selected platform is modeled as non-rechargeable for sustainment planning; use vehicle units and replacement inventory."
        elif recharge_category == "charged_inventory":
            recharge_swap = "Charged inventory is sufficient; no in-mission recharge is required for the recommended planning case."
        elif recharge_category == "recharge_supported":
            recharge_swap = "Initial charged inventory is insufficient, but recharge time is shorter than the battery rotation window; mission is feasible with continuous recharge/swap support."
        elif recharge_category == "recharge_bottleneck":
            recharge_swap = "Recharge time exceeds the battery rotation window; add charged sets, reduce mission burden, or increase recharge capacity."
        elif active_sets_required > 1 and active_inventory_sufficient:
            recharge_swap = "Battery swap between staged sets is required; no recharge is required if all required sets are available."
        elif active_sets_required > 1:
            recharge_swap = "Battery swap or recharge sequencing is required to cover the stress mission demand."
        else:
            recharge_swap = "No battery swap is required for the single recommended planning mission."

    sections = [
        _summary_bullet("BLUF", bluf),
        _summary_bullet("Recharge feasibility", recharge_status if vehicle_rechargeable else None),
        _summary_bullet("Inventory planning" if not vehicle_rechargeable else "Recharge / swap", recharge_swap),
        _summary_bullet("Environmental burden", _environmental_burden_text(summary)),
        _summary_bullet("Planning note", _mission_planning_note(summary, area, environment)),
    ]
    return f"""
    <div class='uuv-card planner-summary'>
      <h3>Energy Planner Summary</h3>
      <ul>{''.join(sections)}</ul>
    </div>
    """


def results_html(summary: dict[str, object]) -> str:
    """Render a compact run summary card above the planner tables."""
    def yesno(value: object) -> str:
        return "Yes" if value else "No"

    detail_rows = []
    if summary.get("recommended_track_orientation") != "N/A":
        detail_rows.append(("Recommended search-track orientation", summary.get("recommended_track_orientation")))
    if summary.get("mission_type") in ISR_MISSIONS:
        detail_rows.extend(
            [
                ("ISR patrol loop distance", f"{fmt1(summary.get('isr_loop_distance_km'))} km"),
                ("ISR loop time", f"{fmt1(summary.get('isr_loop_time_hr'))} hr"),
                ("Endurance per installed set", f"{fmt1(summary.get('isr_single_set_endurance_hr') or summary.get('isr_max_time_on_station_hr'))} hr"),
                ("Endurance using total inventory", f"{fmt1(summary.get('isr_total_inventory_endurance_hr'))} hr"),
                ("Completed loops per installed set", fmt_int(summary.get("isr_completed_loops_single_set") or summary.get("isr_completed_loops"))),
                ("Completed loops using total inventory", fmt_int(summary.get("isr_completed_loops_total_inventory"))),
            ]
        )
    if summary.get("mission_type") in PAYLOAD_MISSIONS and summary.get("route_distance_km") is not None:
        detail_rows.append(("Route distance", f"{fmt1(summary.get('route_distance_km'))} km"))
        detail_rows.append(("Route heading", f"{fmt1(summary.get('route_heading_deg'))} deg"))
    details = "".join(f"<div><strong>{key}:</strong> {value}</div>" for key, value in detail_rows)
    one_way_inventory = summary.get("vehicle_rechargeable") is False
    inventory_required_label = "Vehicle units needed" if one_way_inventory else "Battery sets needed"
    return f"""
    <div class='uuv-card full-width-card metoc-assessment metoc-panel'>
      <h2>Run Summary</h2>
      <p><strong>{summary.get("mission_type")}</strong> on <strong>{summary.get("platform")}</strong></p>
      <p>
        Planning recommendation: <strong>{fmt1(summary.get('recommended_planning_energy_kwh') or summary.get('planning_energy_kwh') or summary.get('p80_energy_kwh'))} kWh</strong> |
        Duration: <strong>{fmt1(summary.get('mean_duration_hr'))} hr</strong> |
        {inventory_required_label}: <strong>{fmt_int(summary.get("battery_sets_required_recommended") or summary.get("battery_sets_required_p80"))}</strong> |
        Inventory sufficient: <strong>{yesno(summary.get("battery_inventory_sufficient_no_recharge"))}</strong>
      </p>
      <div>{details}</div>
      <p><strong>Monte Carlo seed:</strong> {summary.get("rng_seed")}</p>
      <p class='small-muted'>Energy = Power x Time. Wh = W x hr. kWh = Wh / 1000. J = Wh x 3600. MJ = kWh x 3.6.</p>
    </div>
    """


def _float_or_blank(value: object) -> float | str:
    """Return a numeric display value or a blank for non-applicable cells."""
    if value is None or value == "":
        return ""
    try:
        return float(value)
    except (TypeError, ValueError):
        return ""


def _yes_no(value: object) -> str:
    """Return readable boolean text for planner tables."""
    return "Yes" if bool(value) else "No"


def _metoc_lookup_point(environment: EnvironmentData, area: MissionArea, label: str) -> str:
    """Return a display string for the traced METOC lookup point."""
    lat: object = None
    lon: object = None
    for params in (environment.marine_query_params, environment.weather_query_params):
        if not params:
            continue
        lat = params.get("latitude")
        lon = params.get("longitude")
        if lat is not None and lon is not None:
            break
    if lat is None or lon is None:
        label_lower = label.lower()
        if "first route" in label_lower and area.route_points:
            lat = area.route_points[0].lat
            lon = area.route_points[0].lon
        elif "first patrol" in label_lower:
            points = area.route_points or area.vertices
            if points:
                lat = points[0].lat
                lon = points[0].lon
        elif "route midpoint" in label_lower and len(area.route_points) >= 2:
            start = area.route_points[0]
            end = area.route_points[-1]
            lat = (start.lat + end.lat) / 2.0
            lon = (start.lon + end.lon) / 2.0
        else:
            lat = area.centroid_lat
            lon = area.centroid_lon
    try:
        return f"{label}, {fmt_coord(lat)}, {fmt_coord(lon)}"
    except (TypeError, ValueError):
        return f"{label}, unavailable"


def _payload_total_distance_km(area: MissionArea, simulation_inputs: dict[str, object]) -> float | str:
    """Return total payload distance including return leg and added transit."""
    if area.route_distance_km is None:
        return ""
    return_to_start = bool(simulation_inputs.get("return_to_start"))
    additional_transit = float(simulation_inputs.get("additional_transit_km") or 0.0)
    return area.route_distance_km * (2.0 if return_to_start else 1.0) + additional_transit


def build_energy_summary_rows(summary: dict[str, object]) -> list[tuple[str, object, str]]:
    """Build the compact energy summary table rows."""
    total_available = float(summary.get("total_available_kwh") or 0.0)
    recommended = float(summary.get("recommended_planning_energy_kwh") or summary.get("planning_energy_kwh") or summary.get("p80_energy_kwh") or 0.0)
    stress = float(summary.get("conservative_stress_energy_kwh") or summary.get("conservative_energy_kwh") or summary.get("p95_energy_kwh") or 0.0)
    environmental_multiplier = summary.get("isr_environmental_multiplier") or summary.get("environmental_multiplier") or ""
    total_uplift_pct: float | str = ""
    if environmental_multiplier not in ("", None):
        try:
            total_uplift_pct = (float(environmental_multiplier) - 1.0) * 100.0
        except (TypeError, ValueError):
            total_uplift_pct = ""
    rows = [
        ("Expected energy", _float_or_blank(summary.get("expected_energy_kwh") or summary.get("mean_energy_kwh")), "kWh"),
        ("Uncertainty allowance", _float_or_blank(summary.get("energy_uncertainty_allowance_kwh")), "kWh"),
        ("Planning recommendation", recommended, "kWh"),
        ("Stress case", stress, "kWh"),
        ("Mission duration", _float_or_blank(summary.get("mean_duration_hr")), "hr"),
        ("Environmental burden", total_uplift_pct, "%"),
        ("Nominal average power", _float_or_blank(summary.get("nominal_average_power_kw")), "kW"),
        ("Speed-adjusted power", _float_or_blank(summary.get("speed_adjusted_power_kw")), "kW"),
        ("Hotel power component", _float_or_blank(summary.get("hotel_power_kw")), "kW"),
        ("Propulsion power component", _float_or_blank(summary.get("propulsion_power_kw")), "kW"),
        ("Low-speed power correction", _float_or_blank(summary.get("low_speed_penalty_kw")), "kW"),
        ("Active power draw", _float_or_blank(summary.get("total_active_power_p50_kw") or summary.get("power_draw_p50_kw")), "kW"),
        ("Sensor load", _float_or_blank(summary.get("mission_sensor_power_p50_w")), "W"),
        (
            "Sensor load range",
            (
                f"{fmt_int(summary.get('mission_sensor_power_p10_w'))}-{fmt_int(summary.get('mission_sensor_power_p90_w'))}"
                if summary.get("mission_sensor_power_p10_w") not in (None, "")
                else ""
            ),
            "W",
        ),
        ("Sensor active duration", _float_or_blank(summary.get("active_sensor_duration_mean_hr")), "hr"),
        ("Sensor energy", _float_or_blank(summary.get("mission_sensor_energy_p50_kwh")), "kWh"),
        ("Transit sensor energy", _float_or_blank(summary.get("transit_sensor_energy_p50_kwh")), "kWh"),
        (
            "Sensor-use logic",
            "Active search/survey only; added transit uses Route/Transit sensor mode."
            if str(summary.get("mission_type") or "") in SEARCH_MISSIONS
            else "",
            "",
        ),
        ("Sensor-load basis", summary.get("mission_sensor_power_basis"), ""),
        ("Minimum efficient speed", _float_or_blank(summary.get("min_efficient_speed_kts")), "kts"),
        ("Planning margin", total_available - recommended, "kWh"),
        ("Stress-case margin", total_available - stress, "kWh"),
    ]
    hotel_fraction = _as_float(summary.get("hotel_power_fraction"))
    if hotel_fraction is not None:
        rows.insert(10, ("Hotel power fraction", hotel_fraction * 100.0, "%"))
    return rows


def build_battery_sustainment_rows(summary: dict[str, object]) -> list[tuple[str, object, str]]:
    """Build the battery and sustainment summary table rows."""
    usable_per_set = float(summary.get("usable_battery_per_set_kwh") or 0.0)
    nameplate = float(summary.get("battery_nameplate_kwh") or 0.0)
    reserve_energy = max(nameplate - usable_per_set, 0.0)
    recommended = float(summary.get("recommended_planning_energy_kwh") or summary.get("planning_energy_kwh") or summary.get("p80_energy_kwh") or 0.0)
    stress = float(summary.get("conservative_stress_energy_kwh") or summary.get("conservative_energy_kwh") or summary.get("p95_energy_kwh") or 0.0)
    total_available = float(summary.get("total_available_kwh") or 0.0)
    mission_type = str(summary.get("mission_type") or "")
    shortfall_kwh = max(recommended - total_available, 0.0)
    conservative_shortfall_kwh = max(stress - total_available, 0.0)
    recommended_sets_required = int(summary.get("battery_sets_required_recommended") or summary.get("battery_sets_required_recommended_planning") or max(1, math.ceil(recommended / max(usable_per_set, 0.001))))
    conservative_sets_required = int(summary.get("battery_sets_required_stress") or summary.get("battery_sets_required_conservative_stress") or max(1, math.ceil(stress / max(usable_per_set, 0.001))))
    conservative_inventory_sufficient = conservative_shortfall_kwh <= 0.0
    planning_inventory_sufficient = shortfall_kwh <= 0.0
    recharge_required = shortfall_kwh > 0.0
    one_way_inventory = summary.get("vehicle_rechargeable") is False
    inventory_unit = "units" if one_way_inventory else "sets"
    rows = [
        ("Usable energy per vehicle unit" if one_way_inventory else "Usable battery per set", usable_per_set, "kWh"),
        ("Battery condition assumption", summary.get("battery_condition_assumption"), ""),
        ("Usable battery fraction expected", _float_or_blank(summary.get("battery_usable_fraction_p50")), ""),
        ("Usable battery fraction range", _usable_fraction_range(summary), ""),
        ("Operator reserve fraction", _float_or_blank(summary.get("operator_reserve_fraction")), ""),
        ("Temperature derating", _nonzero_float(summary.get("temperature_derating_pct")), "%"),
        ("Vehicle units available" if one_way_inventory else "Battery sets available", summary.get("battery_sets_available"), inventory_unit),
        ("Total available energy", total_available, "kWh"),
        ("Usable-energy allowance per unit" if one_way_inventory else "Usable-energy allowance", reserve_energy if reserve_energy > 0 else "", "kWh"),
        ("Vehicle units needed" if one_way_inventory else "Battery sets needed", recommended_sets_required, inventory_unit),
        ("Stress-case vehicle units" if one_way_inventory else "Stress-case battery sets", conservative_sets_required, inventory_unit),
        ("Recommended planning shortfall", shortfall_kwh, "kWh"),
        ("Stress-case shortfall", conservative_shortfall_kwh, "kWh"),
        ("Replacement inventory required" if one_way_inventory else "Recharge/swap required", _yes_no(recharge_required), ""),
        ("Stress-case inventory sufficient", _yes_no(conservative_inventory_sufficient), ""),
        ("Planning inventory sufficient", _yes_no(planning_inventory_sufficient), ""),
        ("Recharge feasibility status", summary.get("recharge_feasibility_status"), ""),
    ]
    if one_way_inventory:
        rows.extend(
            [
                ("Runtime per vehicle unit", _float_or_blank(summary.get("runtime_per_battery_set_hr")), "hr"),
                ("Replacement inventory required", _yes_no(recharge_required), ""),
                ("Replacement inventory shortfall", conservative_shortfall_kwh, "kWh"),
                ("Replacement inventory energy equivalent", conservative_shortfall_kwh, "kWh"),
            ]
        )
        return rows
    rows.extend(
        [
            ("Runtime per battery set", _float_or_blank(summary.get("runtime_per_battery_set_hr")), "hr"),
        ("Recharge time per set", _float_or_blank(summary.get("recharge_time_per_set_hr")), "hr"),
        ("Available recharge window before set reuse", _float_or_blank(summary.get("available_recharge_window_hr")), "hr"),
        ("Recharge bottleneck", _yes_no(summary.get("recharge_bottleneck")), ""),
        ("In-mission recharge shortfall", _float_or_blank(summary.get("in_mission_recharge_shortfall_kwh")), "kWh"),
        ("Recharge energy required during mission", _float_or_blank(summary.get("recharge_energy_required_during_mission_kwh")), "kWh"),
        ]
    )
    return rows


def _nonzero_float(value: object) -> float | str:
    """Return a float only when the value is meaningfully nonzero."""
    numeric = _as_float(value)
    if numeric is None or abs(numeric) < 1e-9:
        return ""
    return numeric


def _usable_fraction_range(summary: dict[str, object]) -> str:
    """Return compact usable battery fraction range text for primary report areas."""
    p10 = _as_float(summary.get("battery_usable_fraction_p10"))
    p50 = _as_float(summary.get("battery_usable_fraction_p50"))
    p90 = _as_float(summary.get("battery_usable_fraction_p90"))
    if p10 is None or p50 is None or p90 is None:
        return ""
    return f"{fmt1(p10)}-{fmt1(p90)}; expected {fmt1(p50)}"


def build_sustainment_projection_rows(summary: dict[str, object]) -> list[tuple[str, object, str]]:
    """Build simplified sustainment energy-flow projection rows."""
    projection_enabled = bool(summary.get("sustainment_projection_enabled"))
    projection_mode = "Optional mission projection lens" if projection_enabled else "Single mission default"
    one_way_inventory = summary.get("vehicle_rechargeable") is False
    return [
        ("Projection mode", projection_mode, ""),
        ("Planning horizon", _float_or_blank(summary.get("sustainment_planning_weeks")), "weeks"),
        ("Operations per week", _float_or_blank(summary.get("sustainment_missions_per_week")), "missions"),
        ("Total projected missions", _float_or_blank(summary.get("sustainment_total_missions")), "missions"),
        ("Planning recommendation per mission", _float_or_blank(summary.get("sustainment_conservative_energy_per_mission_kwh")), "kWh"),
        ("Total mission energy throughput", _float_or_blank(summary.get("sustainment_total_conservative_energy_kwh")), "kWh"),
        ("Usable inventory energy per cycle", _float_or_blank(summary.get("sustainment_usable_inventory_energy_per_cycle_kwh")), "kWh"),
        ("Replacement inventory units required" if one_way_inventory else "Inventory cycles required", _float_or_blank(summary.get("sustainment_inventory_cycles_required")), "units" if one_way_inventory else "cycles"),
        ("Replacement inventory energy equivalent" if one_way_inventory else "In-mission recharge shortfall", _float_or_blank(summary.get("in_mission_recharge_shortfall_kwh")), "kWh"),
        ("Generator efficiency", _fmt_efficiency(summary.get("sustainment_generator_efficiency")), ""),
        ("Generator input energy equivalent" if one_way_inventory else "Generator input energy to reset consumed energy", _float_or_blank(summary.get("sustainment_generator_input_energy_kwh")), "kWh"),
        ("Generator planning factor", _float_or_blank(summary.get("sustainment_generator_kwh_per_gallon")), "kWh/gal"),
    ]


def _salinity_source_label(environment: EnvironmentData) -> str:
    """Return report wording for salinity source."""
    source = environment.salinity_source or ""
    if source == "NOAA CO-OPS station observation":
        return "NOAA CO-OPS station observation."
    if source == "NOAA WOA23 climatology":
        return "NOAA WOA23 climatology."
    if source == "Mixed salinity sources":
        return "Mixed salinity sources."
    if source == "Standard seawater assumption":
        return "Standard seawater assumption."
    return source


def build_mission_geometry_summary_rows(
    summary: dict[str, object],
    area: MissionArea | MissionAreaSet,
    environment: EnvironmentData,
    simulation_inputs: dict[str, object],
) -> list[tuple[str, object, str]]:
    """Build mission-specific geometry rows without search/ISR/payload leakage."""
    mission_type = str(summary.get("mission_type") or "")
    if mission_type in SEARCH_MISSIONS and isinstance(area, MissionAreaSet):
        return [
            ("Geometry", "Multi-area search plan", ""),
            ("Number of search areas", summary.get("number_of_search_areas", len(area.areas)), "areas"),
            ("Total search area", _float_or_blank(summary.get("total_search_area_km2", area.total_area_km2)), "sq km"),
            ("Track spacing", _float_or_blank(simulation_inputs.get("track_spacing_m") or summary.get("track_spacing_m")), "m"),
            ("Active search/survey distance", _float_or_blank(summary.get("search_active_survey_distance_km") or summary.get("search_track_distance_km")), "km"),
            ("Additional transit distance", _float_or_blank(summary.get("search_additional_transit_distance_km") or summary.get("additional_transit_km")), "km"),
            ("Active search/survey duration", _float_or_blank(summary.get("search_active_survey_duration_mean_hr")), "hr"),
            ("Additional transit duration", _float_or_blank(summary.get("search_additional_transit_duration_mean_hr")), "hr"),
            ("METOC sampled points", summary.get("metoc_sample_count", len(area.representative_points)), "points"),
            ("METOC aggregation method", summary.get("metoc_aggregation_method", "area-centroid vector average"), ""),
        ]
    if mission_type in PAYLOAD_MISSIONS:
        return [
            ("Route distance", _float_or_blank(area.route_distance_km or summary.get("route_distance_km")), "km"),
            ("Recovery mode", "Return to start" if summary.get("payload_recovery_mode") == "return_to_start" else "One-way / no return", ""),
            ("Total modeled distance", _float_or_blank(summary.get("payload_total_modeled_distance_km")), "km"),
            ("Carried equipment weight", _nonzero_float(summary.get("payload_weight_kg")), "kg"),
            (
                "Equipment carriage penalty",
                f"{fmt1(summary.get('payload_weight_penalty_pct'), '%')} trim/integration planning burden applied to outbound propulsion energy"
                if _as_float(summary.get("payload_weight_penalty_pct")) and (_as_float(summary.get("payload_weight_penalty_pct")) or 0) > 0
                else "",
                "",
            ),
            ("Launch/recovery overhead", _nonzero_float(summary.get("launch_recovery_energy_kwh")), "kWh"),
            ("One-way/non-rechargeable note", summary.get("payload_one_way_catalog_note"), ""),
            ("METOC lookup point", _metoc_lookup_point(environment, area, "route midpoint"), ""),
        ]
    if mission_type in ISR_MISSIONS:
        geometry_label = "Line patrol" if area.geometry_type == "line" else f"{area.geometry_type.title()} perimeter patrol"
        lookup_label = "first route point" if area.geometry_type == "line" else "first patrol point"
        rows = [
            ("Patrol geometry", geometry_label, ""),
            ("Loop distance", _float_or_blank(summary.get("isr_loop_distance_km")), "km"),
            ("Loop time", _float_or_blank(summary.get("isr_loop_time_hr")), "hr"),
            ("Endurance per installed set", _float_or_blank(summary.get("isr_single_set_endurance_hr") or summary.get("isr_max_time_on_station_hr")), "hr"),
            ("Endurance using total inventory", _float_or_blank(summary.get("isr_total_inventory_endurance_hr")), "hr"),
            ("Completed loops per installed set", summary.get("isr_completed_loops_single_set") or summary.get("isr_completed_loops"), "loops"),
            ("Completed loops using total inventory", summary.get("isr_completed_loops_total_inventory"), "loops"),
            ("Partial next-loop distance per installed set", _float_or_blank(summary.get("isr_partial_loop_distance_km_single_set")), "km"),
            ("Partial next-loop distance using total inventory", _float_or_blank(summary.get("isr_partial_loop_distance_km_total_inventory")), "km"),
            ("Total patrol distance per installed set", _float_or_blank(summary.get("isr_total_patrol_distance_km_single_set")), "km"),
            ("Total patrol distance using total inventory", _float_or_blank(summary.get("isr_total_patrol_distance_km_total_inventory")), "km"),
            ("Endurance / recovery window" if summary.get("vehicle_rechargeable") is False else "Battery swap/recovery window", _float_or_blank(summary.get("isr_swap_window_hr")), "hr"),
            ("METOC lookup point", _metoc_lookup_point(environment, area, lookup_label), ""),
        ]
        if area.area_km2 is not None:
            rows.append(("Area enclosed", area.area_km2, "sq km, reference only"))
        return rows
    if mission_type in SEARCH_MISSIONS:
        orientation = summary.get("recommended_track_orientation")
        if orientation == "N/A":
            orientation = ""
        return [
            ("Search area", _float_or_blank(area.area_km2), "sq km"),
            ("Number of search areas", summary.get("number_of_search_areas", 1), "areas"),
            ("Track spacing", _float_or_blank(simulation_inputs.get("track_spacing_m") or summary.get("track_spacing_m")), "m"),
            ("Recommended orientation", orientation, ""),
            ("Active search/survey distance", _float_or_blank(summary.get("search_active_survey_distance_km") or summary.get("search_track_distance_km")), "km"),
            ("Additional transit distance", _float_or_blank(summary.get("search_additional_transit_distance_km") or summary.get("additional_transit_km")), "km"),
            ("Active search/survey duration", _float_or_blank(summary.get("search_active_survey_duration_mean_hr")), "hr"),
            ("Additional transit duration", _float_or_blank(summary.get("search_additional_transit_duration_mean_hr")), "hr"),
            ("METOC sampled points", summary.get("metoc_sample_count", 1), "points"),
            ("METOC aggregation method", summary.get("metoc_aggregation_method"), ""),
            ("METOC lookup point", _metoc_lookup_point(environment, area, "area centroid"), ""),
        ]
    return [
        ("Geometry type", area.geometry_type, ""),
        ("METOC lookup point", _metoc_lookup_point(environment, area, "geometry center"), ""),
    ]


def build_environmental_input_rows(
    summary: dict[str, object],
    environment: EnvironmentData,
) -> list[tuple[str, object, str]]:
    """Build environmental input rows for planner report tables."""
    environmental_multiplier = summary.get("isr_environmental_multiplier") or summary.get("environmental_multiplier") or ""
    total_uplift_pct: float | str = ""
    if environmental_multiplier not in ("", None):
        try:
            total_uplift_pct = (float(environmental_multiplier) - 1.0) * 100.0
        except (TypeError, ValueError):
            total_uplift_pct = ""
    rows = [
        ("Current speed", _float_or_blank(environment.current_speed_kts_mean), "kts"),
        ("Current direction", _float_or_blank(environment.current_direction_deg_mean), "deg"),
        ("Sea surface temperature", _float_or_blank(environment.sea_surface_temp_c_mean), "deg C"),
        ("Sea surface salinity", _float_or_blank(environment.sea_surface_salinity_psu), "PSU"),
        ("Sea water density", _float_or_blank(environment.sea_water_density_kg_m3), "kg/m3"),
        ("Wind speed", _float_or_blank(environment.wind_speed_kts_mean), "kts"),
        ("Weather summary", environment.weather_summary or "", ""),
        ("Current burden", _nonzero_float(summary.get("current_uplift_pct")), "%"),
        ("Temperature uplift", _nonzero_float(summary.get("temp_uplift_pct")), "%"),
        ("Salinity burden", _nonzero_float(summary.get("salinity_uplift_pct")), "%"),
        ("Environmental burden", total_uplift_pct, "%"),
    ]
    if environment.salinity_source:
        rows.insert(5, ("Salinity source", _salinity_source_label(environment), ""))
    return rows


def _fmt_gallons(value: object) -> str:
    """Format fuel gallons with useful precision for small planning values."""
    numeric = _as_float(value)
    if numeric is None:
        return ""
    if abs(numeric) < 10.0:
        return f"{numeric:.2f}"
    return fmt1(numeric)


def _fmt_efficiency(value: object) -> str:
    """Format generator efficiency without rounding 0.84 down to 0.8."""
    numeric = _as_float(value)
    if numeric is None:
        return ""
    return f"{numeric * 100.0:.0f}%"


def build_energy_equivalence_rows(
    planning_energy_kwh: float,
    planning_basis: str,
    fuel_gallons_equivalent: float | None = None,
) -> list[list[str, str]]:
    """Build secondary energy-storage equivalence rows for sustainment planning."""
    wh = planning_energy_kwh * 1000.0
    joules = wh * 3600.0
    mj = planning_energy_kwh * 3.6
    gj = mj / 1000.0
    kcal = planning_energy_kwh * 860.0
    toe = planning_energy_kwh / 11630.0
    boe = planning_energy_kwh / 1700.0
    tons_oil = planning_energy_kwh / 11400.0

    rows = [
        ["Planning basis", planning_basis],
        ["Energy value", f"{fmt1(planning_energy_kwh)} kWh"],
        ["Watt-hours", f"{wh:,.0f} Wh"],
        ["Joules", f"{joules:,.0f} J"],
        ["Megajoules", f"{mj:,.1f} MJ"],
        ["Gigajoules", f"{gj:,.3f} GJ"],
        ["Kilocalories", f"{kcal:,.0f} kcal"],
        ["Tonnes of oil equivalent", f"{toe:.6f} TOE"],
        ["Barrel-of-oil equivalent", f"{boe:.6f} BOE"],
        ["Metric tons oil equivalent", f"{tons_oil:.6f} metric tons oil equivalent"],
    ]
    if fuel_gallons_equivalent is not None:
        rows.append(["Fuel-equivalent estimate based on generator input energy", f"{_fmt_gallons(fuel_gallons_equivalent)} gal JP-8/diesel"])
    return rows


def metoc_html(environment: EnvironmentData, fusion_service: MetocFusionService) -> str:
    """Render METOC risk cards."""
    assessment = fusion_service.assessment(environment)
    cards = []
    for name, level, color, value, unit, note in assessment["items"]:  # type: ignore[index]
        display = f"{fmt1(value)} {unit}".strip() if isinstance(value, (int, float)) else str(value)
        cards.append(f"""
        <div class='metoc-card {color}'>
          <div class='metoc-title'>{name}</div>
          <div class='metoc-level'>{level}</div>
          <div class='metoc-value'>{display}</div>
          <div class='metoc-note'>{note}</div>
        </div>
        """)
    return f"""
    <div class='uuv-card full-width-card metoc-assessment metoc-panel'>
      <div class='metoc-header'>
        <div>
          <h3>METOC Assessment</h3>
          <div class='small-muted'>FOR PLANNING ONLY. Open-Meteo environmental data are mission-planning inputs, not tactical METOC authority.</div>
        </div>
        <div class='posture'>Overall: {assessment['posture']}</div>
      </div>
      <div class='metoc-grid metoc-card-grid'>{''.join(cards)}</div>
    </div>
    """


def _points_from_dicts(raw_points: object) -> list[tuple[float, float]]:
    """Return lat/lon tuples from serialized point dictionaries."""
    points: list[tuple[float, float]] = []
    if not isinstance(raw_points, list):
        return points
    for point in raw_points:
        if not isinstance(point, dict):
            continue
        lat = point.get("lat")
        lon = point.get("lon")
        if lat is None or lon is None:
            continue
        try:
            points.append((float(lat), float(lon)))
        except (TypeError, ValueError):
            continue
    return points


def _fmt_lookup_point(label: str, lat: float | None, lon: float | None) -> str:
    """Format a METOC lookup point line."""
    if lat is None or lon is None:
        return f"**METOC lookup point:** {label}, N/A"
    return f"**METOC lookup point:** {label}, {fmt_coord(lat)}, {fmt_coord(lon)}"


def _mission_area_from_context(area_data: dict[str, Any]) -> MissionArea | None:
    """Rebuild a mission area from Gradio state when possible."""
    try:
        return MissionArea.from_dict(area_data)
    except Exception:
        return None


def context_markdown(context: dict[str, Any]) -> str:
    """Render loaded mission context for the simulator tab."""
    if not context:
        return "No mission context loaded. The simulator can still run with manual inputs."
    mission_type = str(context.get("mission_type"))
    area_data = context.get("area", {}) if isinstance(context.get("area"), dict) else context
    environment = context.get("environment", {}) if isinstance(context.get("environment"), dict) else context
    area_obj = _mission_area_from_context(area_data) if isinstance(area_data, dict) else None
    if mission_type in SEARCH_MISSIONS:
        if area_data.get("geometry_type") == "MultiArea":
            point_count = len(area_data.get("representative_points", [])) if isinstance(area_data.get("representative_points"), list) else 0
            geom = (
                f"**Mission loaded:** {mission_type}  \n"
                f"**Geometry:** Multi-area search plan  \n"
                f"**Number of search areas:** {fmt_int(area_data.get('number_of_search_areas'))}  \n"
                f"**Total search area:** {fmt1(area_data.get('total_area_km2') or area_data.get('area_km2'))} sq km  \n"
                f"**METOC sampled points:** {fmt_int(point_count)}  \n"
                f"**Planning environment:** averaged from area centroids"
            )
        else:
            shape_label = "Polygon" if area_data.get("geometry_type") == "polygon" else "Rectangle"
            geom = (
                f"**Mission loaded:** {mission_type}  \n"
                f"**Geometry:** {shape_label} search area  \n"
                f"**Area:** {fmt1(area_data.get('area_km2'))} sq km  \n"
                f"**Dimensions:** {fmt1(area_data.get('width_km'))} km x {fmt1(area_data.get('height_km'))} km  \n"
                f"**METOC lookup point:** area centroid, {fmt_coord(area_data.get('centroid_lat'))}, {fmt_coord(area_data.get('centroid_lon'))}"
            )
    elif mission_type in PAYLOAD_MISSIONS:
        route_points = _points_from_dicts(area_data.get("route_points") or area_data.get("vertices"))
        if len(route_points) >= 2:
            start = route_points[0]
            end = route_points[-1]
            lookup_lat = (start[0] + end[0]) / 2.0
            lookup_lon = (start[1] + end[1]) / 2.0
        else:
            lookup_lat = float(area_data.get("centroid_lat")) if area_data.get("centroid_lat") is not None else None
            lookup_lon = float(area_data.get("centroid_lon")) if area_data.get("centroid_lon") is not None else None
        geom = (
            f"**Mission loaded:** {mission_type}  \n"
            f"**Geometry:** Route  \n"
            f"**Route distance:** {fmt1(area_data.get('route_distance_km'))} km  \n"
            f"**Route heading:** {fmt1(area_data.get('route_heading_deg'))} deg  \n"
            f"{_fmt_lookup_point('route midpoint', lookup_lat, lookup_lon)}"
        )
    else:
        geometry_type = str(area_data.get("geometry_type") or "patrol route")
        loop_distance_km = isr_path_distance_per_loop_km(area_obj) if area_obj is not None else 0.0
        if geometry_type == "line":
            route_points = _points_from_dicts(area_data.get("route_points") or area_data.get("vertices"))
            lookup_lat, lookup_lon = route_points[0] if route_points else (None, None)
            one_way_km = float(area_data.get("route_distance_km") or 0.0)
            geom = (
                f"**Mission loaded:** ISR  \n"
                f"**Geometry:** Line patrol  \n"
                f"**One-way route distance:** {fmt1(one_way_km)} km  \n"
                f"**Out-and-back patrol loop distance:** {fmt1(loop_distance_km)} km  \n"
                f"{_fmt_lookup_point('first route point', lookup_lat, lookup_lon)}"
            )
        else:
            patrol_points = _points_from_dicts(area_data.get("vertices"))
            lookup_lat, lookup_lon = patrol_points[0] if patrol_points else (None, None)
            geometry_label = "Polygon" if geometry_type == "polygon" else "Rectangle"
            geom = (
                f"**Mission loaded:** ISR  \n"
                f"**Geometry:** {geometry_label} perimeter patrol  \n"
                f"**Patrol loop distance:** {fmt1(loop_distance_km)} km  \n"
                f"{_fmt_lookup_point('first patrol point', lookup_lat, lookup_lon)}  \n"
                f"**Area enclosed:** {fmt1(area_data.get('area_km2'))} sq km, reference only"
            )
    env = (
        f"\n\n**Open-Meteo baseline:** current {fmt1(environment.get('current_speed_kts_mean'))} kts "
        f"from {fmt1(environment.get('current_direction_deg_mean'))} deg, "
        f"SST {fmt1(environment.get('sea_surface_temp_c_mean'))} deg C, "
        f"wind {fmt1(environment.get('wind_speed_kts_mean'))} kts.  \n"
        f"**Weather:** {environment.get('weather_summary') or 'N/A'}"
    )
    return geom + env + "\n\nNow that mission parameters are set, go to UUV simulation."


def _interpolate_time_at_energy(time_hours: np.ndarray, energy_series: np.ndarray, threshold: float) -> float | None:
    """Return the time where cumulative energy first crosses a threshold."""
    if energy_series.size == 0 or threshold <= 0 or threshold > float(np.max(energy_series)):
        return None
    index = int(np.searchsorted(energy_series, threshold, side="left"))
    if index <= 0:
        return float(time_hours[0])
    if index >= energy_series.size:
        return float(time_hours[-1])
    e0 = float(energy_series[index - 1])
    e1 = float(energy_series[index])
    t0 = float(time_hours[index - 1])
    t1 = float(time_hours[index])
    if abs(e1 - e0) <= 1e-12:
        return t1
    return t0 + (threshold - e0) * (t1 - t0) / (e1 - e0)


def build_energy_time_chart(
    energy_arr: np.ndarray,
    duration_arr: np.ndarray,
    usable_battery_per_set: float,
    battery_sets_available: int,
    recharge_hr: float,
    battery_sets_required: int | None = None,
    mission_type: str = "",
) -> Any:
    """Render cumulative mission energy and battery lens."""
    del recharge_hr
    p50_e = float(np.percentile(energy_arr, 50))
    p10_e = float(np.percentile(energy_arr, 10))
    p90_e = float(np.percentile(energy_arr, 90))
    p50_t = max(float(np.percentile(duration_arr, 50)), 0.1)
    t = np.linspace(0, p50_t, 140)
    x = t / p50_t
    phase_curve = 0.10 * x + 0.75 * (x ** 1.08) + 0.15 * (x ** 2.4)
    phase_curve = phase_curve / max(phase_curve[-1], 1e-9)
    p50_series = p50_e * phase_curve
    p10_series = p10_e * phase_curve
    p90_series = p90_e * phase_curve
    narrow_spread = (p90_e - p10_e) < max(0.01, p50_e * 0.01)
    band_low = p10_series
    band_high = p90_series
    if narrow_spread:
        display_half_width = max(p50_e * 0.015, 0.01) * phase_curve
        band_low = np.maximum(p50_series - display_half_width, 0.0)
        band_high = p50_series + display_half_width

    fig, ax1 = plt.subplots(figsize=(9, 4.6))
    ax1.fill_between(t, band_low, band_high, alpha=0.22, color="#2563eb", label="_nolegend_")
    cumulative_line, = ax1.plot(t, p50_series, linewidth=2.2, color="#1d4ed8", label="Expected")
    ax1.scatter([0.0], [0.0], zorder=5, color="#1d4ed8")
    ax1.scatter([p50_t], [p50_e], zorder=5, color="#1d4ed8")
    ax1.set_xlabel("Mission Time (hours)")
    ax1.set_ylabel("Cumulative Energy (kWh)")
    title_prefix = "ISR " if mission_type in ISR_MISSIONS else ""
    ax1.set_title(f"{title_prefix}Mission Energy Progress and Battery Lens")
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()
    available = max(usable_battery_per_set * max(1, battery_sets_available), 0.1)
    if usable_battery_per_set > 0:
        consumed_in_set = np.mod(p50_series, usable_battery_per_set)
        active_remaining = usable_battery_per_set - consumed_in_set
        boundary_mask = (p50_series > 0) & np.isclose(consumed_in_set, 0.0, atol=max(usable_battery_per_set * 1e-8, 1e-9))
        active_remaining = np.where(boundary_mask, 0.0, active_remaining)
        active_remaining = np.clip(active_remaining, 0.0, usable_battery_per_set)
        battery_line, = ax2.plot(t, active_remaining, linestyle="--", linewidth=2.1, color="#b91c1c", label="Battery available")
        ax2.set_ylabel("Active Battery Remaining (kWh)")
        ax2.set_ylim(0, usable_battery_per_set)
    else:
        total_remaining = np.clip(available - p50_series, 0.0, available)
        battery_line, = ax2.plot(t, total_remaining, linestyle="--", linewidth=2.1, color="#b91c1c", label="Battery available")
        ax2.set_ylabel("Total Energy Remaining (kWh)")
        ax2.set_ylim(0, available)
    ax2.scatter([0.0], [ax2.get_ylim()[1]], zorder=5, color="#b91c1c")
    ax2.scatter([p50_t], [float(battery_line.get_ydata()[-1])], zorder=5, color="#b91c1c")
    ax1.set_xlim(0, p50_t)
    ax1.set_ylim(0, max(available, p90_e * 1.10, p50_e * 1.10, 0.1))
    if usable_battery_per_set > 0 and battery_sets_required is not None:
        thresholds = [usable_battery_per_set * index for index in range(1, max(1, battery_sets_required))]
        for index, threshold in enumerate(thresholds, start=1):
            swap_time = _interpolate_time_at_energy(t, p50_series, threshold)
            if swap_time is None:
                continue
            ax1.axvline(swap_time, linestyle=":", linewidth=1, color="#64748b", alpha=0.75)
            ax1.text(
                swap_time,
                ax1.get_ylim()[1] * 0.92,
                f"Swap B{index}",
                rotation=90,
                va="top",
                ha="right",
                fontsize=8,
                color="#334155",
            )
    ax1.legend([cumulative_line, battery_line], ["Expected", "Battery available"], loc="upper left")
    note = "Shaded band shows Monte Carlo cumulative-energy spread. Battery remaining is usable planning energy, not direct voltage/SOC."
    if narrow_spread:
        note = "Monte Carlo spread is narrow for this run; shaded band is widened slightly for visibility. Battery remaining is usable planning energy, not direct voltage/SOC."
    fig.text(0.5, 0.025, note, ha="center", va="bottom", fontsize=8.5)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    return fig


def build_distribution_chart(
    energy_arr: np.ndarray,
    recommended_energy_kwh: float,
    usable_total_kwh: float,
    mission_type: str = "",
    inventory_label: str = "Battery inventory",
) -> Any:
    """Render Monte Carlo energy distribution."""
    fig, ax = plt.subplots(figsize=(9.5, 4.8), dpi=120)
    p05 = float(np.percentile(energy_arr, 5))
    p50 = float(np.percentile(energy_arr, 50))
    sorted_energy = np.sort(energy_arr)
    tail_count = max(1, int(math.ceil(0.10 * sorted_energy.size)))
    stress_energy_kwh = float(np.mean(sorted_energy[-tail_count:]))
    p01 = float(np.percentile(energy_arr, 1))
    p99 = float(np.percentile(energy_arr, 99))
    spread = max(p99 - p01, abs(p50) * 0.02, 0.002)
    xmin = max(0.0, min(p01, recommended_energy_kwh, p05) - spread * 0.75)
    xmax = max(p99, recommended_energy_kwh, stress_energy_kwh) + spread * 0.75
    bins = min(24, max(10, int(np.sqrt(energy_arr.size) * 1.8)))
    ax.hist(energy_arr, bins=bins, alpha=0.82, edgecolor="black", linewidth=0.25)
    ax.axvline(p50, linestyle="-", linewidth=2, label=f"Expected: {fmt1(p50)} kWh")
    ax.axvline(recommended_energy_kwh, linestyle="--", linewidth=2, label=f"Planning recommendation: {fmt1(recommended_energy_kwh)} kWh")
    ax.axvline(stress_energy_kwh, linestyle=":", linewidth=2, label=f"Stress case: {fmt1(stress_energy_kwh)} kWh")
    if xmin <= usable_total_kwh <= xmax:
        ax.axvline(usable_total_kwh, linestyle="-.", linewidth=2, label=f"Battery available: {fmt1(usable_total_kwh)} kWh")
    else:
        ax.plot([], [], linestyle="-.", linewidth=2, label=f"Battery available: {fmt1(usable_total_kwh)} kWh")
        ax.text(0.98, 0.95, f"Battery available: {fmt1(usable_total_kwh)} kWh", transform=ax.transAxes, ha="right", va="top", fontsize=9, bbox=dict(boxstyle="round,pad=0.35", facecolor="#eef2f7", edgecolor="#94a3b8", alpha=0.95))
    ax.set_xlim(xmin, xmax)
    ax.set_xlabel("Mission energy required, kWh")
    ax.set_ylabel("Monte Carlo count")
    title = "ISR Mission Energy Uncertainty Distribution" if mission_type in ISR_MISSIONS else "Mission Energy Uncertainty Distribution"
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=9)
    if (stress_energy_kwh - p05) < max(0.01, p50 * 0.01):
        fig.text(
            0.5,
            0.02,
            "Monte Carlo spread is narrow for this run; samples are tightly clustered near the displayed energy values.",
            ha="center",
            va="bottom",
            fontsize=8.5,
            color="#334155",
        )
        fig.tight_layout(rect=(0, 0.06, 1, 1))
    else:
        fig.tight_layout()
    return fig


def _draw_current_arrow(ax: Any, environment: EnvironmentData, bounds: tuple[float, float, float, float]) -> None:
    current_speed = environment.current_speed_kts_mean or 0.0
    current_dir = environment.current_direction_deg_mean or 0.0
    if current_speed <= 0:
        return
    min_x, max_x, min_y, max_y = bounds
    span_x = max(max_x - min_x, 0.001)
    span_y = max(max_y - min_y, 0.001)
    theta = math.radians(90 - current_dir)
    arrow_len = max(min(span_x, span_y) * 0.16, 0.06)
    dx = arrow_len * math.cos(theta)
    dy = arrow_len * math.sin(theta)
    x0 = min_x + span_x * 0.16 if dx >= 0 else max_x - span_x * 0.16
    y0 = min_y + span_y * 0.20 if dy >= 0 else max_y - span_y * 0.20
    ax.arrow(
        x0,
        y0,
        dx,
        dy,
        length_includes_head=True,
        head_width=max(min(span_x, span_y) * 0.022, 0.022),
        head_length=max(min(span_x, span_y) * 0.032, 0.032),
        linestyle="--",
        linewidth=1.5,
        color="#7c2d12",
        zorder=6,
        label="Current vector",
    )


def _dedupe_legend(ax: Any, max_items: int = 4, outside: bool = False) -> None:
    """Render a compact legend with repeated labels collapsed."""
    handles, labels = ax.get_legend_handles_labels()
    deduped: dict[str, Any] = {}
    for handle, label in zip(handles, labels):
        if label and not label.startswith("_") and label not in deduped:
            deduped[label] = handle
    if "Current vector" in deduped:
        deduped["Current vector"] = Line2D([0], [0], color="#7c2d12", linestyle="--", linewidth=1.8)
    items = list(deduped.items())
    if "Current vector" in deduped and len(items) > max_items:
        items = [item for item in items if item[0] != "Current vector"][: max_items - 1] + [("Current vector", deduped["Current vector"])]
    limited = items[:max_items]
    if limited:
        labels_limited, handles_limited = zip(*[(label, handle) for label, handle in limited])
        if outside:
            ax.legend(
                handles_limited,
                labels_limited,
                loc="upper left",
                bbox_to_anchor=(1.01, 1.0),
                borderaxespad=0.0,
                fontsize=7.5,
                framealpha=0.92,
            )
        else:
            ax.legend(handles_limited, labels_limited, loc="upper right", fontsize=7.5, framealpha=0.9)


def _project_route_points(area: MissionArea) -> list[tuple[float, float]]:
    """Project route points to local kilometers, or synthesize a manual route."""
    if len(area.route_points) >= 2:
        lat0 = area.route_points[0].lat
        lon0 = area.route_points[0].lon
        cos_lat0 = max(abs(math.cos(math.radians(lat0))), 1e-6)
        return [
            (
                EARTH_RADIUS_KM * math.radians(point.lon - lon0) * cos_lat0,
                EARTH_RADIUS_KM * math.radians(point.lat - lat0),
            )
            for point in area.route_points
        ]
    distance = max(float(area.route_distance_km or 0.0), 0.1)
    heading = math.radians(float(area.route_heading_deg or 0.0))
    return [(0.0, 0.0), (distance * math.sin(heading), distance * math.cos(heading))]


def _draw_scale_bar(ax: Any, min_x: float, max_x: float, min_y: float, max_y: float) -> None:
    """Draw a compact scale bar on a local-kilometer plot."""
    span_x = max(max_x - min_x, 0.001)
    span_y = max(max_y - min_y, 0.001)
    extent = max(span_x, span_y)
    scale_len = min(_nice_scale_km(extent) * 0.75, span_x * 0.45 if span_x > 0.01 else extent * 0.35)
    scale_x = min_x + span_x * 0.08
    scale_y = min_y + span_y * 0.05
    ax.plot([scale_x, scale_x + scale_len], [scale_y, scale_y], color="black", linewidth=2, alpha=0.72)
    ax.plot([scale_x, scale_x], [scale_y - span_y * 0.010, scale_y + span_y * 0.010], color="black", linewidth=1.4, alpha=0.72)
    ax.plot([scale_x + scale_len, scale_x + scale_len], [scale_y - span_y * 0.010, scale_y + span_y * 0.010], color="black", linewidth=1.4, alpha=0.72)
    ax.text(scale_x + scale_len / 2, scale_y + max(span_y * 0.026, 0.02), f"{scale_len:.3g} km", ha="center", va="bottom", fontsize=7, alpha=0.78)


def _draw_north_arrow(ax: Any, min_x: float, max_x: float, min_y: float, max_y: float) -> None:
    """Draw a north arrow on a local-kilometer plot."""
    span_x = max(max_x - min_x, 0.001)
    span_y = max(max_y - min_y, 0.001)
    extent = max(span_x, span_y)
    north_x = max_x - span_x * 0.08
    north_y = max_y - span_y * 0.22
    north_len = min(max(span_y * 0.13, extent * 0.035), span_y * 0.24)
    ax.arrow(north_x, north_y, 0, north_len, length_includes_head=True, head_width=max(extent * 0.015, 0.016), head_length=max(extent * 0.024, 0.020), linewidth=1.1, color="black", alpha=0.78)
    ax.text(north_x, north_y + north_len + max(span_y * 0.018, 0.012), "N", ha="center", va="bottom", fontsize=8, fontweight="bold", alpha=0.82)


def _style_snapshot_axes(ax: Any) -> None:
    """Apply the report snapshot style."""
    ax.set_facecolor("#eef7fb")
    ax.grid(True, color="white", linewidth=0.9, alpha=0.85)
    ax.set_xlabel("Local east-west distance, km")
    ax.set_ylabel("Local north-south distance, km")


def _payload_current_impact_text(area: MissionArea, environment: EnvironmentData, speed_kts: float = 3.5) -> str:
    """Return a compact label for route current impact."""
    route_heading = float(area.route_heading_deg or 0.0)
    current_speed = float(environment.current_speed_kts_mean or 0.0)
    current_dir = float(environment.current_direction_deg_mean or 0.0)
    along, cross = current_components(current_speed, current_dir, route_heading)
    penalty_pct = payload_current_penalty(current_speed, current_dir, route_heading, speed_kts) * 100.0
    return f"Along-track current {fmt1(along)} kts | cross-track {fmt1(cross)} kts | transit uplift {fmt1(penalty_pct)}%"


def _draw_area_lanes(ax: Any, area: MissionArea, track_spacing_m: float, orientation: str, arrow_density: int = 25) -> dict[str, object]:
    points = search_polygon_points(area)
    lanes = clipped_search_lanes(area, track_spacing_m, orientation)
    xs = [p[0] for p in points] + [points[0][0]]
    ys = [p[1] for p in points] + [points[0][1]]
    ax.fill(xs, ys, color="#38bdf8", alpha=0.16, label="Search area(s)")
    ax.plot(xs, ys, color="#075985", linewidth=2.3)
    min_x, max_x, min_y, max_y = local_bounds(points)
    span_x = max(max_x - min_x, 0.001)
    span_y = max(max_y - min_y, 0.001)
    segments = list(lanes.get("segments", []))
    for index, (x0, y0, x1, y1) in enumerate(segments):
        ax.plot([x0, x1], [y0, y1], color="#0f766e", linewidth=1.35, alpha=0.78, label="Search lanes" if index == 0 else "_nolegend_")
        if len(segments) > 30 and index % max(1, len(segments) // max(1, arrow_density)) != 0:
            continue
        dx = x1 - x0
        dy = y1 - y0
        seg_len = math.hypot(dx, dy)
        if seg_len <= 1e-9:
            continue
        arrow_len = min(seg_len * 0.22, max(span_x, span_y) * 0.12)
        ux = dx / seg_len
        uy = dy / seg_len
        mid_x = (x0 + x1) / 2
        mid_y = (y0 + y1) / 2
        ax.arrow(mid_x - ux * arrow_len / 2, mid_y - uy * arrow_len / 2, ux * arrow_len, uy * arrow_len, length_includes_head=True, head_width=max(min(span_x, span_y) * 0.012, 0.018), head_length=max(max(span_x, span_y) * 0.020, 0.025), color="#134e4a", alpha=0.72)
    return lanes


def _set_limits(ax: Any, points: list[tuple[float, float]], equal_aspect: bool) -> tuple[float, float, float, float]:
    min_x, max_x, min_y, max_y = local_bounds(points)
    span_x = max(max_x - min_x, 0.001)
    span_y = max(max_y - min_y, 0.001)
    ax.set_xlim(min_x - max(span_x * 0.06, 0.04), max_x + max(span_x * 0.06, 0.04))
    ax.set_ylim(min_y - max(span_y * 0.08, 0.04), max_y + max(span_y * 0.08, 0.04))
    ax.set_aspect("equal" if equal_aspect else "auto", adjustable="box")
    return min_x, max_x, min_y, max_y


def build_mapping_snapshot_chart(summary: dict[str, object], area: MissionArea | MissionAreaSet, environment: EnvironmentData, track_spacing_m: float) -> Any:
    """Render the report map snapshot panel."""
    fig, ax = plt.subplots(figsize=(8.0, 4.8), dpi=120)
    mission_type = str(summary.get("mission_type", ""))
    _style_snapshot_axes(ax)

    if mission_type in PAYLOAD_MISSIONS:
        route_points = _project_route_points(area)
        xs = [point[0] for point in route_points]
        ys = [point[1] for point in route_points]
        ax.plot(xs, ys, color="#075985", linewidth=2.5, marker="o", markersize=4, label="Route / transit path")
        ax.scatter([xs[0]], [ys[0]], s=70, color="#16a34a", edgecolor="white", linewidth=0.8, zorder=5, label="Start")
        ax.scatter([xs[-1]], [ys[-1]], s=85, marker="*", color="#dc2626", edgecolor="white", linewidth=0.8, zorder=6, label="Target")
        bounds = _set_limits(ax, route_points, equal_aspect=True)
        _draw_current_arrow(ax, environment, bounds)
        _draw_north_arrow(ax, *bounds)
        _draw_scale_bar(ax, *bounds)
        distance = float(summary.get("route_distance_km") or area.route_distance_km or 0.0)
        fig.text(
            0.5,
            0.025,
            f"Route distance: {fmt1(distance)} km",
            ha="center",
            va="bottom",
            fontsize=8,
            wrap=True,
        )
        ax.set_title("Engineering Snapshot - Payload Route", pad=10, fontsize=13)
        _dedupe_legend(ax, max_items=4)
        fig.tight_layout(rect=(0, 0.06, 1, 1))
        return fig

    if mission_type in ISR_MISSIONS:
        if area.is_payload_route:
            patrol_points = _project_route_points(area)
            xs = [point[0] for point in patrol_points]
            ys = [point[1] for point in patrol_points]
            ax.plot(xs, ys, color="#075985", linewidth=2.4, marker="o", markersize=4, label="ISR patrol route")
        else:
            patrol_points = search_polygon_points(area)
            xs = [point[0] for point in patrol_points] + [patrol_points[0][0]]
            ys = [point[1] for point in patrol_points] + [patrol_points[0][1]]
            ax.fill(xs, ys, color="#38bdf8", alpha=0.16)
            ax.plot(xs, ys, color="#075985", linewidth=2.4, label="ISR patrol loop")
        bounds = _set_limits(ax, patrol_points, equal_aspect=True)
        _draw_current_arrow(ax, environment, bounds)
        _draw_north_arrow(ax, *bounds)
        _draw_scale_bar(ax, *bounds)
        ax.set_title("Engineering Snapshot - ISR Patrol", pad=10, fontsize=13)
        fig.text(
            0.5,
            0.025,
            (
                f"Loop distance: {fmt1(summary.get('isr_loop_distance_km'))} km | "
                f"Inventory endurance: {fmt1(summary.get('isr_total_inventory_endurance_hr'))} hr | "
                f"Loops: {fmt_int(summary.get('isr_completed_loops_total_inventory'))}"
            ),
            ha="center",
            va="bottom",
            fontsize=8,
            wrap=True,
        )
        _dedupe_legend(ax, max_items=4)
        fig.tight_layout(rect=(0, 0.06, 1, 1))
        return fig

    if mission_type in SEARCH_MISSIONS and isinstance(area, MissionAreaSet):
        all_vertices = [vertex for search_area in area.areas for vertex in search_area.vertices]
        if not all_vertices:
            ax.text(0.5, 0.5, "Multi-area search snapshot is unavailable for this geometry.", ha="center", va="center", wrap=True, transform=ax.transAxes)
            ax.axis("off")
            fig.tight_layout()
            return fig
        lat0 = sum(vertex.lat for vertex in all_vertices) / len(all_vertices)
        lon0 = sum(vertex.lon for vertex in all_vertices) / len(all_vertices)
        cos_lat0 = max(abs(math.cos(math.radians(lat0))), 1e-6)
        all_points: list[tuple[float, float]] = []
        for index, search_area in enumerate(area.areas, start=1):
            points = [
                (
                    EARTH_RADIUS_KM * math.radians(vertex.lon - lon0) * cos_lat0,
                    EARTH_RADIUS_KM * math.radians(vertex.lat - lat0),
                )
                for vertex in search_area.vertices
            ]
            if len(points) < 3:
                continue
            xs = [point[0] for point in points] + [points[0][0]]
            ys = [point[1] for point in points] + [points[0][1]]
            ax.fill(xs, ys, color="#38bdf8", alpha=0.12, label="Search area(s)" if index == 1 else "_nolegend_")
            ax.plot(xs, ys, color="#075985", linewidth=2.0)
            cx = sum(point[0] for point in points) / len(points)
            cy = sum(point[1] for point in points) / len(points)
            ax.text(cx, cy, f"A{index}", ha="center", va="center", fontsize=9, fontweight="bold")
            all_points.extend(points)
        if not all_points:
            ax.text(0.5, 0.5, "Multi-area search snapshot is unavailable for this geometry.", ha="center", va="center", wrap=True, transform=ax.transAxes)
            ax.axis("off")
            fig.tight_layout()
            return fig
        bounds = _set_limits(ax, all_points, equal_aspect=True)
        _draw_current_arrow(ax, environment, bounds)
        _draw_north_arrow(ax, *bounds)
        _draw_scale_bar(ax, *bounds)
        ax.set_title("Engineering Snapshot - Search Area", pad=10, fontsize=13)
        _dedupe_legend(ax, max_items=4)
        fig.text(
            0.5,
            0.025,
            (
                f"Areas: {fmt_int(len(area.areas))} | Total area: {fmt1(area.total_area_km2)} sq km | "
                "Swath overlay currently shown for aggregate planning; per-area lane rendering is simplified."
            ),
            ha="center",
            va="bottom",
            fontsize=8,
            wrap=True,
        )
        fig.tight_layout(rect=(0, 0.08, 1, 1))
        return fig

    if mission_type not in SEARCH_MISSIONS or not area.is_search_area:
        ax.text(0.5, 0.5, "Mission map snapshot is unavailable for this geometry.", ha="center", va="center", wrap=True, transform=ax.transAxes)
        ax.axis("off")
        fig.tight_layout()
        return fig

    points = search_polygon_points(area)
    orientation = str(summary.get("recommended_track_orientation", "East-West"))
    lanes = _draw_area_lanes(ax, area, track_spacing_m, orientation, arrow_density=18)
    bounds = _set_limits(ax, points, equal_aspect=True)
    _draw_current_arrow(ax, environment, bounds)
    _draw_north_arrow(ax, *bounds)
    _draw_scale_bar(ax, *bounds)
    if area.centroid_local_km:
        ax.scatter([area.centroid_local_km.x], [area.centroid_local_km.y], s=34, marker="o", color="#111827", zorder=5)
    shape_label = "Polygon" if area.geometry_type == "polygon" else "Rectangle"
    ax.set_title(f"Engineering Snapshot - Search Area: {shape_label}", pad=10, fontsize=13)
    ax.text(
        0.99,
        0.04,
        f"Area: {fmt1(area.area_km2 or 0)} sq km\nBox: {fmt1(area.width_km or 0)} x {fmt1(area.height_km or 0)} km",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=7.5,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#eef2f7", edgecolor="#94a3b8", alpha=0.82),
    )
    _dedupe_legend(ax, max_items=3, outside=True)
    fig.tight_layout(rect=(0, 0, 0.84, 1))
    return fig


def _nice_scale_km(extent_km: float) -> float:
    """Choose a readable map scale-bar length."""
    target = max(extent_km / 4.0, 0.001)
    magnitude = 10 ** math.floor(math.log10(target))
    for multiplier in [1, 2, 5, 10]:
        candidate = multiplier * magnitude
        if candidate >= target:
            return candidate
    return 10 * magnitude
