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
    if str(summary.get("mission_type") or "") in ISR_MISSIONS:
        return _isr_status_text(summary)
    p80 = _as_float(summary.get("p80_energy_kwh"))
    p95 = _as_float(summary.get("p95_energy_kwh"))
    total_available = _as_float(summary.get("total_available_kwh"))
    sets_p80 = _as_int(summary.get("battery_sets_required_p80"))
    sets_available = _as_int(summary.get("battery_sets_available"))
    usable_per_set = _as_float(summary.get("usable_battery_per_set_kwh"))
    sets_p95 = math.ceil(p95 / usable_per_set) if p95 is not None and usable_per_set and usable_per_set > 0 else sets_p80
    margin_p80 = (total_available - p80) if total_available is not None and p80 is not None else None
    if sets_available is not None and sets_p95 is not None and sets_p95 <= sets_available:
        return "Feasible", "Proceed with the current battery inventory; preserve the recorded assumptions for review."
    if sets_available is not None and sets_p80 is not None and sets_p80 <= sets_available:
        return "Marginal", "Mission covers the planning case, but stage extra battery or recharge support for conservative conditions."
    if margin_p80 is not None and margin_p80 >= 0:
        return "Marginal", "Planning energy is covered, but conservative margin is limited; avoid repeated tasking without added inventory."
    return "Not feasible", "Add charged battery inventory, reduce route/search burden, or plan recharge/swap support before execution."


def _isr_status_text(summary: dict[str, object]) -> tuple[str, str]:
    """Return ISR feasibility using endurance/loop coverage rather than mission-total battery sets."""
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
        return (
            "Feasible",
            (
                f"ISR endurance is feasible for the selected patrol. One installed set supports approximately "
                f"{fmt1(single_set_endurance)} hr, {fmt_int(completed_single)} full patrol loop(s), plus "
                f"{fmt1(partial_single_km)} km of the next loop. Plan recovery/swap at approximately {fmt1(swap_window)} hr."
            ),
        )
    if single_set_endurance is not None and single_set_endurance > 0 and partial_km is not None and partial_km > 0:
        return (
            "Marginal",
            (
                "ISR patrol is endurance-limited. The vehicle cannot complete one full loop, "
                f"but can cover approximately {fmt1(total_distance or partial_km)} km before recovery/swap."
            ),
        )
    return (
        "Not feasible",
        "ISR patrol is not feasible with the selected inventory and route because no meaningful patrol distance/endurance is available.",
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
    metoc_risk = _metoc_risk_text(summary, environment)
    if mission_type in ISR_MISSIONS:
        partial_km = _as_float(summary.get("isr_partial_loop_distance_km_total_inventory"))
        partial_pct = _as_float(summary.get("isr_remaining_partial_loop_pct"))
        partial_text = f"{fmt1(partial_km)} km" if partial_km is not None else f"{fmt1(partial_pct)}%"
        return [
            _kpi_tile("Patrol loop distance", f"{fmt1(summary.get('isr_loop_distance_km'))} km"),
            _kpi_tile("Full loops", f"{fmt_int(summary.get('isr_completed_loops_total_inventory') or summary.get('isr_completed_loops_single_set'))} loops"),
            _kpi_tile("Partial next loop", partial_text),
            _kpi_tile("Endurance per set", f"{fmt1(summary.get('isr_single_set_endurance_hr') or summary.get('isr_max_time_on_station_hr'))} hr"),
            _kpi_tile("Total patrol distance", f"{fmt1(summary.get('isr_total_patrol_distance_km_total_inventory') or summary.get('isr_total_patrol_distance_km_single_set'))} km"),
            _kpi_tile("Recovery/swap", f"{fmt1(summary.get('isr_swap_window_hr') or summary.get('isr_single_set_endurance_hr'))} hr"),
            _kpi_tile("METOC risk", metoc_risk, status=metoc_risk),
        ]
    usable_per_set = _as_float(summary.get("usable_battery_per_set_kwh"))
    p80 = _as_float(summary.get("p80_energy_kwh"))
    p95 = _as_float(summary.get("p95_energy_kwh"))
    total_available = _as_float(summary.get("total_available_kwh"))
    sets_p80 = _as_int(summary.get("battery_sets_required_p80"))
    sets_p95 = math.ceil(p95 / usable_per_set) if p95 is not None and usable_per_set and usable_per_set > 0 else sets_p80
    margin = (total_available - p80) if total_available is not None and p80 is not None else None
    sets_available = int(summary.get("battery_sets_available") or 0)
    return [
        _kpi_tile("Planning energy P80", f"{fmt1(p80)} kWh"),
        _kpi_tile("Conservative energy P95", f"{fmt1(p95)} kWh"),
        _kpi_tile("Battery sets P80", fmt_int(sets_p80), status="sufficient" if sets_p80 and sets_p80 <= sets_available else "marginal"),
        _kpi_tile("Battery sets P95", fmt_int(sets_p95), status="sufficient" if sets_p95 and sets_p95 <= sets_available else "marginal"),
        _kpi_tile("Inventory margin", f"{fmt1(margin)} kWh", status="sufficient" if margin is not None and margin >= 0 else "shortfall"),
        _kpi_tile("Mission duration", f"{fmt1(summary.get('mean_duration_hr'))} hr"),
        _kpi_tile("METOC risk", metoc_risk, status=metoc_risk),
    ]


def _monte_carlo_phrase(summary: dict[str, object]) -> str:
    """Return the visible Monte Carlo ensemble phrase."""
    for key in ("monte_carlo_runs", "mc_runs", "simulation_count", "num_samples", "n_samples"):
        runs = _as_int(summary.get(key))
        if runs is not None and runs > 0:
            return f"{runs} Monte Carlo trials"
    return "the configured Monte Carlo ensemble"


def _seed_phrase(summary: dict[str, object]) -> str:
    """Return whether the run used a user-fixed deterministic seed."""
    requested_seed = summary.get("rng_seed_requested")
    if requested_seed not in (None, ""):
        return f"using deterministic seed {escape(str(requested_seed))}"
    if "rng_seed_requested" not in summary and summary.get("rng_seed") not in (None, ""):
        return f"using deterministic seed {escape(str(summary.get('rng_seed')))}"
    return "without a fixed deterministic seed"


def _planning_basis_phrase(summary: dict[str, object]) -> str:
    """Translate planning basis keys into executive-readable text."""
    basis = str(summary.get("planning_energy_basis") or "")
    if basis == "patrol_loop":
        return "patrol-loop endurance"
    if basis == "endurance_window":
        return "endurance-window"
    return "mission-total energy"


def _dominant_factor_phrase(summary: dict[str, object], mission_type: str) -> str:
    """Choose one compact driver phrase for the executive summary."""
    current = _as_float(summary.get("current_uplift_pct")) or 0.0
    salinity = _as_float(summary.get("salinity_uplift_pct")) or 0.0
    temp_derating = _as_float(summary.get("temperature_derating_pct")) or 0.0
    burdens = {
        "route/track current burden": current,
        "salinity/buoyancy burden": salinity,
        "cold-water battery-capacity derating": temp_derating,
    }
    best_label, best_value = max(burdens.items(), key=lambda item: item[1])
    if best_value > 0.0:
        return best_label
    payload_weight = _as_float(summary.get("payload_weight_kg")) or 0.0
    if payload_weight > 0.0:
        return "payload trim/integration burden"
    if mission_type in SEARCH_MISSIONS:
        return "search area and track-spacing burden"
    if mission_type in ISR_MISSIONS:
        return "patrol loop length and endurance-mode speed"
    return "mission geometry and selected vehicle energy capacity"


def _executive_results_summary_html(summary: dict[str, object], environment: EnvironmentData) -> str:
    """Render a compact scientific executive-results summary."""
    del environment
    mission_type = str(summary.get("mission_type") or "")
    ensemble = _monte_carlo_phrase(summary)
    seed = _seed_phrase(summary)
    basis = _planning_basis_phrase(summary)
    if mission_type in ISR_MISSIONS:
        first = (
            f"The simulation executed {ensemble} {seed}, evaluating ISR persistence as a "
            f"{basis} problem with expected (P50), planning-level (P80), and conservative (P95) uncertainty views."
        )
        details: list[str] = []
        endurance = _as_float(summary.get("isr_single_set_endurance_hr") or summary.get("isr_max_time_on_station_hr"))
        loops = _as_int(summary.get("isr_completed_loops_single_set") or summary.get("isr_completed_loops_total_inventory"))
        partial = _as_float(summary.get("isr_partial_loop_distance_km_single_set") or summary.get("isr_partial_loop_distance_km_total_inventory"))
        loop_distance = _as_float(summary.get("isr_loop_distance_km"))
        loop_time = _as_float(summary.get("isr_loop_time_hr"))
        swap_window = _as_float(summary.get("isr_swap_window_hr") or endurance)
        if loop_distance is not None and loop_time is not None:
            details.append(f"the patrol loop is {fmt1(loop_distance)} km over {fmt1(loop_time)} hr")
        if endurance is not None:
            details.append(f"one installed set supports about {fmt1(endurance)} hr")
        if loops is not None:
            loop_text = f"{fmt_int(loops)} full loop(s)"
            if partial is not None:
                loop_text += f" plus {fmt1(partial)} km of the next loop"
            details.append(loop_text)
        if swap_window is not None:
            details.append(f"recovery/swap is planned near {fmt1(swap_window)} hr")
        second = "The results indicate " + "; ".join(details) + "." if details else ""
    else:
        first = (
            f"The simulation executed {ensemble} {seed}, evaluating {basis} demand against selected battery "
            f"inventory with expected (P50), planning-level (P80), and conservative (P95) uncertainty views."
        )
        p80 = _as_float(summary.get("p80_energy_kwh"))
        p95 = _as_float(summary.get("p95_energy_kwh"))
        details = []
        if p80 is not None:
            details.append(f"planning energy demand of {fmt1(p80)} kWh")
        if p95 is not None:
            details.append(f"conservative demand of {fmt1(p95)} kWh")
        factor = _dominant_factor_phrase(summary, mission_type)
        second = (
            f"The results indicate {' and '.join(details)}, with battery sufficiency driven primarily by {factor}."
            if details
            else f"Battery sufficiency is driven primarily by {factor}."
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
            f"payload weight is {fmt1(payload_weight)} kg; payload carriage penalty: {fmt1(payload_penalty_pct or 0.0, '%')} trim/integration planning burden applied to outbound propulsion energy"
        )
    launch_recovery_energy = _as_float(summary.get("launch_recovery_energy_kwh"))
    if launch_recovery_energy and launch_recovery_energy > 0:
        parts.append(f"launch/recovery overhead is {fmt1(launch_recovery_energy)} kWh")
    catalog_note = str(summary.get("payload_one_way_catalog_note") or "")
    if catalog_note:
        parts.append(catalog_note)
    return "Payload mission planning: " + "; ".join(parts) + "." if parts else ""


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
        parts.append(f"patrol loop energy is {fmt1(loop_energy)} kWh")
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
    sets_required = _as_int(summary.get("battery_sets_required_p80"))
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
            parts.append(f"plan {sets_required - 1} battery swap window(s) for a single planning-level mission")
        elif sets_available is not None and sets_available >= 1:
            parts.append("one battery set covers the single planning-level mission")
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
    mission_type = str(summary.get("mission_type") or "")
    status, recommendation = _plain_status_text(summary)
    kpis = _decision_kpis(summary, environment)
    planning_note = _mission_planning_note(summary, area, environment)
    executive_summary = _executive_results_summary_html(summary, environment)
    decision_html = f"""
    <div class='uuv-card planner-summary mission-decision-brief'>
      <h2>Mission Decision Brief</h2>
      <div class='decision-topline'>
        <div class='decision-status {_risk_class(status)}'>{escape(status)}</div>
        <div>
          <h3>BLUF</h3>
          <p>{escape(recommendation)}</p>
          <p class='small-muted'>{escape(planning_note or '')}</p>
        </div>
      </div>
      {executive_summary}
      <div class='decision-kpi-grid'>{''.join(kpis)}</div>
    </div>
    """
    traceability_html = build_technical_traceability_html(summary, environment, vehicle)
    return decision_html + traceability_html


def build_technical_traceability_html(summary: dict[str, object], environment: EnvironmentData, vehicle: object | None = None) -> str:
    """Build the lower technical traceability/model-detail section."""
    source_note = getattr(vehicle, "source_note", "") if vehicle is not None else summary.get("source_note", "")
    usable_basis = getattr(vehicle, "usable_basis", "") if vehicle is not None else summary.get("usable_basis", "")
    rows = [
        ("App version", APP_VERSION, ""),
        ("Energy model version", ENERGY_MODEL_VERSION, ""),
        ("Vehicle catalog version", VEHICLE_CATALOG_VERSION, ""),
        ("Planning basis", summary.get("planning_energy_basis"), ""),
        ("Planning percentile", summary.get("planning_percentile"), ""),
        ("Monte Carlo seed", summary.get("rng_seed"), ""),
        ("Usable battery fraction P10", _float_or_blank(summary.get("battery_usable_fraction_p10")), ""),
        ("Usable battery fraction P50", _float_or_blank(summary.get("battery_usable_fraction_p50")), ""),
        ("Usable battery fraction P90", _float_or_blank(summary.get("battery_usable_fraction_p90")), ""),
        ("Temperature derating basis", summary.get("temperature_derating_basis"), ""),
        ("Salinity provider status", environment.salinity_source or "standard_assumption", ""),
        ("METOC lookup method", _trace_lookup_method(summary, environment), ""),
        ("Multi-area aggregation method", summary.get("metoc_aggregation_method"), ""),
        ("Run-record traceability status", summary.get("run_record_traceability_status", "recorded"), ""),
        ("Source note", source_note, ""),
        ("Usable battery basis", usable_basis, ""),
    ]
    table = build_report_table_html(rows, "Technical Traceability / Model Detail")
    if not table:
        return ""
    return f"<details class='traceability-detail'><summary>Technical Traceability / Model Detail</summary>{table}</details>"


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

    p95 = _as_float(summary.get("planning_energy_kwh") or summary.get("p95_energy_kwh"))
    planning_basis = str(summary.get("planning_energy_basis") or "mission_total")
    usable_per_set = _as_float(summary.get("usable_battery_per_set_kwh"))
    sets_required = _as_int(summary.get("battery_sets_required_p80"))
    sets_available = _as_int(summary.get("battery_sets_available"))
    inventory_sufficient_raw = summary.get("battery_inventory_sufficient_no_recharge")
    inventory_sufficient = bool(inventory_sufficient_raw) if inventory_sufficient_raw is not None else None
    recharge_allowed = bool(summary.get("recharge_allowed"))
    vehicle_rechargeable = bool(summary.get("vehicle_rechargeable", True))
    conservative_sets_required = math.ceil(p95 / usable_per_set) if p95 is not None and usable_per_set and usable_per_set > 0 else None
    conservative_inventory_sufficient = (
        conservative_sets_required <= sets_available
        if conservative_sets_required is not None and sets_available is not None
        else None
    )

    bluf: str | None = None
    if conservative_inventory_sufficient is True:
        bluf = "Mission is feasible with current battery inventory at the conservative planning level."
    elif conservative_inventory_sufficient is False and recharge_allowed:
        bluf = "Mission needs recharge, swap sequencing, or additional charged inventory at the conservative planning level."
    elif conservative_inventory_sufficient is False and not vehicle_rechargeable:
        bluf = "Mission needs additional one-way inventory or replacement energy production at the conservative planning level."
    elif conservative_inventory_sufficient is False:
        bluf = "Mission is not covered by current battery inventory at the conservative planning level unless additional charged batteries are staged."
    elif inventory_sufficient is True:
        bluf = "Mission is feasible with current battery inventory at the planning level."
    elif inventory_sufficient is False and recharge_allowed:
        bluf = "Mission needs recharge, swap sequencing, or additional charged inventory at the planning level."
    elif inventory_sufficient is False and not vehicle_rechargeable:
        bluf = "Mission needs additional one-way inventory or replacement energy production at the planning level."
    elif inventory_sufficient is False:
        bluf = "Mission is not covered by current battery inventory at the planning level unless additional charged batteries are staged."
    if p95 is not None:
        basis_text = "for the mission total" if planning_basis == "mission_total" else f"for {planning_basis.replace('_', ' ')}"
        energy_text = f"Conservative planning energy is {_fmt_value(p95)} kWh {basis_text}."
        bluf = f"{bluf} {energy_text}" if bluf else energy_text
    mission_type = str(summary.get("mission_type") or "")
    if mission_type in PAYLOAD_MISSIONS and p95 is not None:
        total_available = _as_float(summary.get("total_available_kwh"))
        if total_available is not None:
            conservative_margin = total_available - p95
            if conservative_margin >= 0:
                margin_text = f" Conservative energy margin is approximately {fmt1(conservative_margin)} kWh."
                if conservative_margin <= max(0.25, total_available * 0.10):
                    margin_text += " Margin is limited; consider additional battery inventory or recharge support before repeated tasking."
            else:
                margin_text = f" Conservative shortfall is approximately {fmt1(abs(conservative_margin))} kWh."
            bluf = f"{bluf}{margin_text}" if bluf else margin_text.strip()

    recharge_swap: str | None = None
    active_sets_required = conservative_sets_required or sets_required
    active_inventory_sufficient = conservative_inventory_sufficient if conservative_inventory_sufficient is not None else inventory_sufficient
    if active_sets_required is not None:
        if not vehicle_rechargeable:
            recharge_swap = "Catalog marks this platform as one-way/non-rechargeable; plan replacement inventory or energy production rather than recharge turnaround."
        elif active_sets_required > 1 and active_inventory_sufficient:
            recharge_swap = "Battery swap between staged sets is required; no recharge is required if all required sets are available."
        elif active_sets_required > 1:
            recharge_swap = "Battery swap or recharge sequencing is required to cover the conservative mission demand."
        else:
            recharge_swap = "No battery swap is required for the single conservative mission."

    sections = [
        _summary_bullet("BLUF", bluf),
        _summary_bullet("Recharge / swap", recharge_swap),
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
        detail_rows.append(("Payload route distance", f"{fmt1(summary.get('route_distance_km'))} km"))
        detail_rows.append(("Payload route heading", f"{fmt1(summary.get('route_heading_deg'))} deg"))
    details = "".join(f"<div><strong>{key}:</strong> {value}</div>" for key, value in detail_rows)
    return f"""
    <div class='uuv-card full-width-card metoc-assessment metoc-panel'>
      <h2>Run Summary</h2>
      <p><strong>{summary.get("mission_type")}</strong> on <strong>{summary.get("platform")}</strong></p>
      <p>
        Planning-level mission energy: <strong>{fmt1(summary.get('p80_energy_kwh'))} kWh (P80)</strong> |
        Duration: <strong>{fmt1(summary.get('mean_duration_hr'))} hr</strong> |
        Battery sets required at planning level: <strong>{fmt_int(summary.get("battery_sets_required_p80"))} (P80)</strong> |
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
    p80 = float(summary.get("p80_energy_kwh") or 0.0)
    p95 = float(summary.get("p95_energy_kwh") or 0.0)
    environmental_multiplier = summary.get("isr_environmental_multiplier") or summary.get("environmental_multiplier") or ""
    total_uplift_pct: float | str = ""
    if environmental_multiplier not in ("", None):
        try:
            total_uplift_pct = (float(environmental_multiplier) - 1.0) * 100.0
        except (TypeError, ValueError):
            total_uplift_pct = ""
    return [
        ("Expected mission energy (P50)", _float_or_blank(summary.get("p50_energy_kwh")), "kWh"),
        ("Planning-level mission energy (P80)", p80, "kWh"),
        ("Conservative mission energy (P95)", _float_or_blank(summary.get("p95_energy_kwh")), "kWh"),
        ("Mission duration", _float_or_blank(summary.get("mean_duration_hr")), "hr"),
        ("Total environmental uplift", total_uplift_pct, "%"),
        ("Planning-level energy margin (P80)", total_available - p80, "kWh"),
        ("Conservative energy margin (P95)", total_available - p95, "kWh"),
    ]


def build_battery_sustainment_rows(summary: dict[str, object]) -> list[tuple[str, object, str]]:
    """Build the battery and sustainment summary table rows."""
    usable_per_set = float(summary.get("usable_battery_per_set_kwh") or 0.0)
    nameplate = float(summary.get("battery_nameplate_kwh") or 0.0)
    reserve_energy = max(nameplate - usable_per_set, 0.0)
    p80 = float(summary.get("p80_energy_kwh") or 0.0)
    p95 = float(summary.get("p95_energy_kwh") or 0.0)
    total_available = float(summary.get("total_available_kwh") or 0.0)
    shortfall_kwh = max(p80 - total_available, 0.0)
    conservative_shortfall_kwh = max(p95 - total_available, 0.0)
    conservative_sets_required = max(1, math.ceil(p95 / max(usable_per_set, 0.001)))
    conservative_inventory_sufficient = conservative_shortfall_kwh <= 0.0
    recharge_required = conservative_shortfall_kwh > 0.0
    return [
        ("Usable battery per set", usable_per_set, "kWh"),
        ("Battery condition assumption", summary.get("battery_condition_assumption"), ""),
        ("Usable battery fraction expected", _float_or_blank(summary.get("battery_usable_fraction_p50")), ""),
        ("Usable battery fraction range", _usable_fraction_range(summary), ""),
        ("Operator reserve fraction", _float_or_blank(summary.get("operator_reserve_fraction")), ""),
        ("Temperature derating", _nonzero_float(summary.get("temperature_derating_pct")), "%"),
        ("Battery sets available", summary.get("battery_sets_available"), "sets"),
        ("Total available energy", total_available, "kWh"),
        ("Reserve energy per set", reserve_energy if reserve_energy > 0 else "", "kWh"),
        ("Battery sets required at conservative level (P95)", conservative_sets_required, "sets"),
        ("Battery sets required at planning level (P80)", summary.get("battery_sets_required_p80"), "sets"),
        ("Conservative shortfall (P95)", conservative_shortfall_kwh, "kWh"),
        ("Planning-level shortfall (P80)", shortfall_kwh, "kWh"),
        ("Recharge/swap required at conservative level", _yes_no(recharge_required), ""),
        ("Conservative battery inventory sufficient (P95)", _yes_no(conservative_inventory_sufficient), ""),
        ("Planning-level battery inventory sufficient (P80)", _yes_no(summary.get("battery_inventory_sufficient_no_recharge")), ""),
    ]


def _nonzero_float(value: object) -> float | str:
    """Return a float only when the value is meaningfully nonzero."""
    numeric = _as_float(value)
    if numeric is None or abs(numeric) < 1e-9:
        return ""
    return numeric


def _usable_fraction_range(summary: dict[str, object]) -> str:
    """Return compact P10/P50/P90 usable battery fraction text."""
    p10 = _as_float(summary.get("battery_usable_fraction_p10"))
    p50 = _as_float(summary.get("battery_usable_fraction_p50"))
    p90 = _as_float(summary.get("battery_usable_fraction_p90"))
    if p10 is None or p50 is None or p90 is None:
        return ""
    return f"P10 {fmt1(p10)} / P50 {fmt1(p50)} / P90 {fmt1(p90)}"


def build_sustainment_projection_rows(summary: dict[str, object]) -> list[tuple[str, object, str]]:
    """Build simplified sustainment energy-flow projection rows."""
    projection_enabled = bool(summary.get("sustainment_projection_enabled"))
    projection_mode = "Optional mission projection lens" if projection_enabled else "Single mission default"
    return [
        ("Projection mode", projection_mode, ""),
        ("Planning horizon", _float_or_blank(summary.get("sustainment_planning_weeks")), "weeks"),
        ("Operations per week", _float_or_blank(summary.get("sustainment_missions_per_week")), "missions"),
        ("Total projected missions", _float_or_blank(summary.get("sustainment_total_missions")), "missions"),
        ("Conservative energy per mission", _float_or_blank(summary.get("sustainment_conservative_energy_per_mission_kwh")), "kWh"),
        ("Conservative total energy demand", _float_or_blank(summary.get("sustainment_total_conservative_energy_kwh")), "kWh"),
        ("Usable inventory energy per cycle", _float_or_blank(summary.get("sustainment_usable_inventory_energy_per_cycle_kwh")), "kWh"),
        ("Inventory cycles required", _float_or_blank(summary.get("sustainment_inventory_cycles_required")), "cycles"),
        ("Recharge energy required", _float_or_blank(summary.get("sustainment_recharge_energy_required_kwh")), "kWh"),
        ("Generator efficiency", _float_or_blank(summary.get("sustainment_generator_efficiency")), ""),
        ("Generator input energy", _float_or_blank(summary.get("sustainment_generator_input_energy_kwh")), "kWh"),
    ]


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
            ("Estimated lane/route burden", _float_or_blank(summary.get("search_total_distance_km")), "km"),
            ("METOC sampled points", summary.get("metoc_sample_count", len(area.representative_points)), "points"),
            ("METOC aggregation method", summary.get("metoc_aggregation_method", "area-centroid vector average"), ""),
        ]
    if mission_type in PAYLOAD_MISSIONS:
        return [
            ("Route distance", _float_or_blank(area.route_distance_km or summary.get("route_distance_km")), "km"),
            ("Recovery mode", "Return to start" if summary.get("payload_recovery_mode") == "return_to_start" else "One-way / no return", ""),
            ("Total modeled distance", _float_or_blank(summary.get("payload_total_modeled_distance_km")), "km"),
            ("Payload weight", _nonzero_float(summary.get("payload_weight_kg")), "kg"),
            (
                "Payload carriage penalty",
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
            ("Battery swap/recovery window", _float_or_blank(summary.get("isr_swap_window_hr")), "hr"),
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
            ("Estimated lane/route burden", _float_or_blank(summary.get("search_total_distance_km") or summary.get("search_track_distance_km")), "km"),
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
    return [
        ("Current speed", _float_or_blank(environment.current_speed_kts_mean), "kts"),
        ("Current direction", _float_or_blank(environment.current_direction_deg_mean), "deg"),
        ("Sea surface temperature", _float_or_blank(environment.sea_surface_temp_c_mean), "deg C"),
        ("Sea surface salinity", _float_or_blank(environment.sea_surface_salinity_psu), "PSU"),
        ("Sea water density", _float_or_blank(environment.sea_water_density_kg_m3), "kg/m3"),
        ("Salinity source", environment.salinity_source or "", ""),
        ("Salinity provider note", "Salinity unavailable from configured provider; standard seawater assumption used." if environment.sea_surface_salinity_psu is None else "", ""),
        ("Wind speed", _float_or_blank(environment.wind_speed_kts_mean), "kts"),
        ("Weather summary", environment.weather_summary or "", ""),
        ("Current uplift", _nonzero_float(summary.get("current_uplift_pct")), "%"),
        ("Temperature uplift", _nonzero_float(summary.get("temp_uplift_pct")), "%"),
        ("Salinity uplift", _nonzero_float(summary.get("salinity_uplift_pct")), "%"),
        ("Total uplift", total_uplift_pct, "%"),
    ]


def build_energy_equivalence_rows(planning_energy_kwh: float, planning_basis: str) -> list[list[str, str]]:
    """Build secondary energy-storage equivalence rows for sustainment planning."""
    wh = planning_energy_kwh * 1000.0
    joules = wh * 3600.0
    mj = planning_energy_kwh * 3.6
    gj = mj / 1000.0
    kcal = planning_energy_kwh * 860.0
    toe = planning_energy_kwh / 11630.0
    boe = planning_energy_kwh / 1700.0
    tons_oil = planning_energy_kwh / 11400.0

    return [
        ["Planning basis", planning_basis],
        ["Conservative planning energy", f"{fmt1(planning_energy_kwh)} kWh"],
        ["Watt-hours", f"{wh:,.0f} Wh"],
        ["Joules", f"{joules:,.0f} J"],
        ["Megajoules", f"{mj:,.1f} MJ"],
        ["Gigajoules", f"{gj:,.3f} GJ"],
        ["Kilocalories", f"{kcal:,.0f} kcal"],
        ["Tonnes of oil equivalent", f"{toe:.6f} TOE"],
        ["Barrel-of-oil equivalent", f"{boe:.6f} BOE"],
        ["Metric tons oil equivalent", f"{tons_oil:.6f} metric tons oil equivalent"],
    ]


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
            f"**Mission loaded:** Payload Delivery  \n"
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
    cumulative_line, = ax1.plot(t, p50_series, linewidth=2.2, color="#1d4ed8", label="Expected cumulative energy (P50)")
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
        battery_line, = ax2.plot(t, active_remaining, linestyle="--", linewidth=2.1, color="#b91c1c", label="Battery energy remaining")
        ax2.set_ylabel("Active Battery Remaining (kWh)")
        ax2.set_ylim(0, usable_battery_per_set)
    else:
        total_remaining = np.clip(available - p50_series, 0.0, available)
        battery_line, = ax2.plot(t, total_remaining, linestyle="--", linewidth=2.1, color="#b91c1c", label="Battery energy remaining")
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
    ax1.legend([cumulative_line, battery_line], ["Expected cumulative energy (P50)", "Battery energy remaining"], loc="upper left")
    note = "Shaded band shows P10-P90 Monte Carlo cumulative-energy spread. Battery remaining is usable planning energy, not direct voltage/SOC."
    if narrow_spread:
        note = "Monte Carlo spread is narrow for this run; shaded band is widened slightly for visibility. Battery remaining is usable planning energy, not direct voltage/SOC."
    fig.text(0.5, 0.025, note, ha="center", va="bottom", fontsize=8.5)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    return fig


def build_distribution_chart(energy_arr: np.ndarray, p80: float, usable_total_kwh: float, mission_type: str = "") -> Any:
    """Render Monte Carlo energy distribution."""
    fig, ax = plt.subplots(figsize=(9.5, 4.8), dpi=120)
    p05 = float(np.percentile(energy_arr, 5))
    p50 = float(np.percentile(energy_arr, 50))
    p95 = float(np.percentile(energy_arr, 95))
    p01 = float(np.percentile(energy_arr, 1))
    p99 = float(np.percentile(energy_arr, 99))
    spread = max(p99 - p01, abs(p50) * 0.02, 0.002)
    xmin = max(0.0, min(p01, p80, p05) - spread * 0.75)
    xmax = max(p99, p80, p95) + spread * 0.75
    bins = min(24, max(10, int(np.sqrt(energy_arr.size) * 1.8)))
    ax.hist(energy_arr, bins=bins, alpha=0.82, edgecolor="black", linewidth=0.25)
    ax.axvline(p50, linestyle="-", linewidth=2, label=f"Expected energy (P50): {fmt1(p50)} kWh")
    ax.axvline(p80, linestyle="--", linewidth=2, label=f"Planning-level energy (P80): {fmt1(p80)} kWh")
    ax.axvline(p95, linestyle=":", linewidth=2, label=f"Conservative energy (P95): {fmt1(p95)} kWh")
    if xmin <= usable_total_kwh <= xmax:
        ax.axvline(usable_total_kwh, linestyle="-.", linewidth=2, label=f"Battery inventory: {fmt1(usable_total_kwh)} kWh")
    else:
        ax.text(0.98, 0.95, f"Battery inventory without recharge: {fmt1(usable_total_kwh)} kWh", transform=ax.transAxes, ha="right", va="top", fontsize=9, bbox=dict(boxstyle="round,pad=0.35", facecolor="#eef2f7", edgecolor="#94a3b8", alpha=0.95))
    ax.set_xlim(xmin, xmax)
    ax.set_xlabel("Mission energy required, kWh")
    ax.set_ylabel("Monte Carlo count")
    title = "ISR Mission Energy Uncertainty Distribution" if mission_type in ISR_MISSIONS else "Mission Energy Uncertainty Distribution"
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=9)
    if (p95 - p05) < max(0.01, p50 * 0.01):
        fig.text(
            0.5,
            0.02,
            "Monte Carlo spread is narrow for this run; samples are clustered near the displayed percentile values.",
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


def _dedupe_legend(ax: Any, max_items: int = 4) -> None:
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
        ax.legend(handles_limited, labels_limited, loc="upper right", fontsize=8)


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
    scale_len = min(_nice_scale_km(extent), span_x * 0.70 if span_x > 0.01 else extent * 0.45)
    scale_x = min_x + span_x * 0.10
    scale_y = min_y + span_y * 0.08
    ax.plot([scale_x, scale_x + scale_len], [scale_y, scale_y], color="black", linewidth=3)
    ax.plot([scale_x, scale_x], [scale_y - span_y * 0.015, scale_y + span_y * 0.015], color="black", linewidth=2)
    ax.plot([scale_x + scale_len, scale_x + scale_len], [scale_y - span_y * 0.015, scale_y + span_y * 0.015], color="black", linewidth=2)
    ax.text(scale_x + scale_len / 2, scale_y + max(span_y * 0.035, 0.03), f"{scale_len:.3g} km", ha="center", va="bottom", fontsize=8.5)


def _draw_north_arrow(ax: Any, min_x: float, max_x: float, min_y: float, max_y: float) -> None:
    """Draw a north arrow on a local-kilometer plot."""
    span_x = max(max_x - min_x, 0.001)
    span_y = max(max_y - min_y, 0.001)
    extent = max(span_x, span_y)
    north_x = min_x + span_x * 0.10
    north_y = min_y + span_y * 0.70
    north_len = max(span_y * 0.16, extent * 0.08)
    ax.arrow(north_x, north_y, 0, north_len, length_includes_head=True, head_width=max(extent * 0.025, 0.025), head_length=max(extent * 0.040, 0.035), linewidth=1.6, color="black")
    ax.text(north_x, north_y + north_len + max(extent * 0.025, 0.02), "N", ha="center", va="bottom", fontsize=10, fontweight="bold")


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
    fig, ax = plt.subplots(figsize=(6.7, 5.6), dpi=120)
    mission_type = str(summary.get("mission_type", ""))
    _style_snapshot_axes(ax)

    if mission_type in PAYLOAD_MISSIONS:
        route_points = _project_route_points(area)
        xs = [point[0] for point in route_points]
        ys = [point[1] for point in route_points]
        ax.plot(xs, ys, color="#075985", linewidth=2.5, marker="o", markersize=4, label="Payload route")
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
        ax.set_title("Payload Route and Current Snapshot", pad=10, fontsize=13)
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
        ax.set_title("ISR Patrol Route Snapshot", pad=10, fontsize=13)
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
        ax.set_title("Multi-Area Search Plan Snapshot", pad=10, fontsize=13)
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
    ax.set_title(f"Search Area and Swath Pattern Snapshot: {shape_label}", pad=10, fontsize=13)
    ax.text(0.01, -0.18, f"Swath/track spacing: {fmt_int(track_spacing_m)} m | Recommended orientation: {orientation} | Planning snapshot only", transform=ax.transAxes, fontsize=8, va="top")
    ax.text(0.99, -0.18, f"Lanes: {lanes.get('lane_count', 0)}", transform=ax.transAxes, ha="right", fontsize=8, va="top")
    ax.text(
        0.99,
        0.02,
        f"Area: {fmt1(area.area_km2 or 0)} sq km\nBounding box: {fmt1(area.width_km or 0)} x {fmt1(area.height_km or 0)} km",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#eef2f7", edgecolor="#94a3b8", alpha=0.95),
    )
    _dedupe_legend(ax, max_items=4)
    fig.tight_layout()
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
