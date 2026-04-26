"""UI-only table, HTML, and chart rendering helpers."""

from __future__ import annotations

import math
from html import escape
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from core.environment import current_components, payload_current_penalty
from core.geometry import clipped_search_lanes, isr_path_distance_per_loop_km, local_bounds, search_polygon_points
from models.environment_model import EnvironmentData
from models.mission_model import MissionArea
from services.metoc_fusion import MetocFusionService
from utils.constants import EARTH_RADIUS_KM, ISR_MISSIONS, PAYLOAD_MISSIONS, SEARCH_MISSIONS
from utils.parsing import fmt


def rows_to_dataframe(rows: list[tuple[str, object, str]], columns: tuple[str, str, str]) -> pd.DataFrame:
    """Convert row tuples into a display dataframe."""
    return pd.DataFrame(rows, columns=list(columns))


def env_table_to_html(rows: list[tuple[str, object, str]], title: str = "Mission Geometry and Environmental Data") -> str:
    """Render mission/environment rows as a Gradio HTML card."""
    body = []
    for item, value, unit in rows:
        value_text = f"{value:.3f}".rstrip("0").rstrip(".") if isinstance(value, float) else ("" if value is None else str(value))
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
    text = f"{value:.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _summary_bullet(label: str, text: str | None) -> str:
    """Render one executive-summary bullet when content exists."""
    if not text:
        return ""
    return f"<li><b>{escape(label)}:</b> {escape(text)}</li>"


def _environmental_burden_text(summary: dict[str, object]) -> str | None:
    """Build the environmental uplift sentence from summary values."""
    multiplier = _as_float(summary.get("isr_environmental_multiplier") or summary.get("environmental_multiplier"))
    current_uplift = _as_float(summary.get("current_uplift_pct"))
    temp_uplift = _as_float(summary.get("temp_uplift_pct"))
    total_uplift = (multiplier - 1.0) * 100.0 if multiplier is not None else None
    if total_uplift is None and (current_uplift is not None or temp_uplift is not None):
        total_uplift = (current_uplift or 0.0) + (temp_uplift or 0.0)
    if total_uplift is None:
        return None
    detail = ""
    if current_uplift is not None or temp_uplift is not None:
        detail = f" (current {_fmt_value(current_uplift or 0.0, 1)}%, temperature {_fmt_value(temp_uplift or 0.0, 1)}%)"
    return f"Current and temperature add an estimated {_fmt_value(total_uplift, 1)}% energy uplift{detail}."


def _payload_planning_note(summary: dict[str, object], area: MissionArea, environment: EnvironmentData) -> str:
    """Build the mission-specific payload planning note."""
    parts: list[str] = []
    route_distance = _as_float(summary.get("route_distance_km") or area.route_distance_km)
    if route_distance is not None:
        parts.append(f"route distance is {_fmt_value(route_distance)} km")
    if "return_to_start" in summary:
        parts.append(f"return-to-start is {'enabled' if bool(summary.get('return_to_start')) else 'disabled'}")
    route_heading = _as_float(summary.get("route_heading_deg") or area.route_heading_deg)
    current_speed = _as_float(environment.current_speed_kts_mean)
    current_dir = _as_float(environment.current_direction_deg_mean)
    speed = _as_float(summary.get("speed_kts"))
    if route_heading is not None and current_speed is not None and current_dir is not None:
        along, cross = current_components(current_speed, current_dir, route_heading)
        if speed is not None:
            penalty_pct = payload_current_penalty(current_speed, current_dir, route_heading, speed) * 100.0
            parts.append(
                f"current impact is {along:+.2f} kts along-track and {cross:+.2f} kts cross-track, about {_fmt_value(penalty_pct, 1)}% transit uplift"
            )
        else:
            parts.append(f"current impact is {along:+.2f} kts along-track and {cross:+.2f} kts cross-track")
    burden = _as_float(summary.get("environmental_multiplier"))
    if burden is not None:
        parts.append(f"expected environmental energy burden is about {_fmt_value((burden - 1.0) * 100.0, 1)}%")
    return "Payload mission planning: " + "; ".join(parts) + "." if parts else ""


def _isr_planning_note(summary: dict[str, object]) -> str:
    """Build the mission-specific ISR planning note."""
    parts: list[str] = []
    loop_distance = _as_float(summary.get("isr_loop_distance_km"))
    station_time = _as_float(summary.get("isr_max_time_on_station_hr"))
    completed_loops = _as_int(summary.get("isr_completed_loops"))
    if loop_distance is not None:
        parts.append(f"patrol loop distance is {_fmt_value(loop_distance)} km")
    if station_time is not None:
        parts.append(f"time on station is {_fmt_value(station_time, 1)} hr")
    if completed_loops is not None:
        parts.append(f"completed loops are {completed_loops}")
    if station_time is not None:
        parts.append("plan recovery or a battery swap at the calculated endurance window before retasking")
    return "ISR persistence planning: " + "; ".join(parts) + "." if parts else ""


def _search_planning_note(summary: dict[str, object], area: MissionArea) -> str:
    """Build the mission-specific Search/MCM planning note."""
    parts: list[str] = []
    search_area = _as_float(area.area_km2)
    track_spacing = _as_float(summary.get("track_spacing_m"))
    orientation = summary.get("recommended_track_orientation")
    track_distance = _as_float(summary.get("search_track_distance_km"))
    total_distance = _as_float(summary.get("search_total_distance_km"))
    sets_required = _as_int(summary.get("battery_sets_required_p80"))
    sets_available = _as_int(summary.get("battery_sets_available"))
    if search_area is not None:
        parts.append(f"search area is {_fmt_value(search_area)} sq km")
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
    Build an energy-planner-focused HTML/Markdown summary.

    This should be a BLUF-style planning summary, not a raw data dump.
    """
    del vehicle
    p95 = _as_float(summary.get("p95_energy_kwh"))
    usable_per_set = _as_float(summary.get("usable_battery_per_set_kwh"))
    sets_required = _as_int(summary.get("battery_sets_required_p80"))
    sets_available = _as_int(summary.get("battery_sets_available"))
    inventory_sufficient_raw = summary.get("battery_inventory_sufficient_no_recharge")
    inventory_sufficient = bool(inventory_sufficient_raw) if inventory_sufficient_raw is not None else None
    recharge_allowed = bool(summary.get("recharge_allowed"))
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
    elif conservative_inventory_sufficient is False:
        bluf = "Mission is not covered by current battery inventory at the conservative planning level unless additional charged batteries are staged."
    elif inventory_sufficient is True:
        bluf = "Mission is feasible with current battery inventory at the planning level."
    elif inventory_sufficient is False and recharge_allowed:
        bluf = "Mission needs recharge, swap sequencing, or additional charged inventory at the planning level."
    elif inventory_sufficient is False:
        bluf = "Mission is not covered by current battery inventory at the planning level unless additional charged batteries are staged."
    if p95 is not None:
        bluf = f"{bluf} Conservative planning energy is {_fmt_value(p95)} kWh (P95)." if bluf else f"Conservative planning energy is {_fmt_value(p95)} kWh (P95)."

    recharge_swap: str | None = None
    active_sets_required = conservative_sets_required or sets_required
    active_inventory_sufficient = conservative_inventory_sufficient if conservative_inventory_sufficient is not None else inventory_sufficient
    if active_sets_required is not None:
        if active_sets_required > 1 and active_inventory_sufficient:
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
                ("ISR patrol loop distance", f"{float(summary.get('isr_loop_distance_km', 0)):.2f} km"),
                ("Estimated ISR time on station", f"{float(summary.get('isr_max_time_on_station_hr', 0)):.1f} hr"),
                ("ISR loop time", f"{float(summary.get('isr_loop_time_hr', 0)):.2f} hr"),
                ("Completed patrol loops", summary.get("isr_completed_loops")),
            ]
        )
    if summary.get("mission_type") in PAYLOAD_MISSIONS and summary.get("route_distance_km") is not None:
        detail_rows.append(("Payload route distance", f"{float(summary.get('route_distance_km', 0)):.2f} km"))
        detail_rows.append(("Payload route heading", f"{float(summary.get('route_heading_deg', 0)):.1f} deg"))
    details = "".join(f"<div><strong>{key}:</strong> {value}</div>" for key, value in detail_rows)
    return f"""
    <div class='uuv-card'>
      <h2>Run Summary</h2>
      <p><strong>{summary.get("mission_type")}</strong> on <strong>{summary.get("platform")}</strong></p>
      <p>
        Planning-level mission energy: <strong>{float(summary.get('p80_energy_kwh', 0)):.2f} kWh (P80)</strong> |
        Duration: <strong>{float(summary.get('mean_duration_hr', 0)):.1f} hr</strong> |
        Battery sets required at planning level: <strong>{summary.get("battery_sets_required_p80")} (P80)</strong> |
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
        return f"{label}, {float(lat):.6f}, {float(lon):.6f}"
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
    return [
        ("Expected mission energy (P50)", _float_or_blank(summary.get("p50_energy_kwh")), "kWh"),
        ("Planning-level mission energy (P80)", p80, "kWh"),
        ("Conservative mission energy (P95)", _float_or_blank(summary.get("p95_energy_kwh")), "kWh"),
        ("Mission duration", _float_or_blank(summary.get("mean_duration_hr")), "hr"),
        ("Environmental multiplier", _float_or_blank(environmental_multiplier), ""),
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
        ("Battery sets available", summary.get("battery_sets_available"), "sets"),
        ("Total available energy", total_available, "kWh"),
        ("Reserve energy per set", reserve_energy, "kWh"),
        ("Battery sets required at conservative level (P95)", conservative_sets_required, "sets"),
        ("Battery sets required at planning level (P80)", summary.get("battery_sets_required_p80"), "sets"),
        ("Conservative shortfall (P95)", conservative_shortfall_kwh, "kWh"),
        ("Planning-level shortfall (P80)", shortfall_kwh, "kWh"),
        ("Recharge/swap required at conservative level", _yes_no(recharge_required), ""),
        ("Conservative battery inventory sufficient (P95)", _yes_no(conservative_inventory_sufficient), ""),
        ("Planning-level battery inventory sufficient (P80)", _yes_no(summary.get("battery_inventory_sufficient_no_recharge")), ""),
    ]


def build_mission_geometry_summary_rows(
    summary: dict[str, object],
    area: MissionArea,
    environment: EnvironmentData,
    simulation_inputs: dict[str, object],
) -> list[tuple[str, object, str]]:
    """Build mission-specific geometry rows without search/ISR/payload leakage."""
    mission_type = str(summary.get("mission_type") or "")
    if mission_type in PAYLOAD_MISSIONS:
        return [
            ("Route distance", _float_or_blank(area.route_distance_km or summary.get("route_distance_km")), "km"),
            ("Return-to-start enabled", _yes_no(simulation_inputs.get("return_to_start")), ""),
            ("Total distance", _payload_total_distance_km(area, simulation_inputs), "km"),
            ("METOC lookup point", _metoc_lookup_point(environment, area, "route midpoint"), ""),
        ]
    if mission_type in ISR_MISSIONS:
        geometry_label = "Line patrol" if area.geometry_type == "line" else f"{area.geometry_type.title()} perimeter patrol"
        lookup_label = "first route point" if area.geometry_type == "line" else "first patrol point"
        rows = [
            ("Patrol geometry", geometry_label, ""),
            ("Loop distance", _float_or_blank(summary.get("isr_loop_distance_km")), "km"),
            ("Loop time", _float_or_blank(summary.get("isr_loop_time_hr")), "hr"),
            ("Time on station", _float_or_blank(summary.get("isr_max_time_on_station_hr")), "hr"),
            ("Completed loops", summary.get("isr_completed_loops"), "loops"),
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
            ("Track spacing", _float_or_blank(simulation_inputs.get("track_spacing_m") or summary.get("track_spacing_m")), "m"),
            ("Recommended orientation", orientation, ""),
            ("Estimated track length", _float_or_blank(summary.get("search_track_distance_km")), "km"),
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
        ("Wind speed", _float_or_blank(environment.wind_speed_kts_mean), "kts"),
        ("Weather summary", environment.weather_summary or "", ""),
        ("Current uplift", _float_or_blank(summary.get("current_uplift_pct")), "%"),
        ("Temperature uplift", _float_or_blank(summary.get("temp_uplift_pct")), "%"),
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
        ["Conservative planning energy", f"{planning_energy_kwh:.3f} kWh"],
        ["Watt-hours", f"{wh:,.0f} Wh"],
        ["Joules", f"{joules:,.0f} J"],
        ["Megajoules", f"{mj:,.3f} MJ"],
        ["Gigajoules", f"{gj:,.6f} GJ"],
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
        display = f"{fmt(value)} {unit}".strip() if isinstance(value, (int, float)) else str(value)
        cards.append(f"""
        <div class='metoc-card {color}'>
          <div class='metoc-title'>{name}</div>
          <div class='metoc-level'>{level}</div>
          <div class='metoc-value'>{display}</div>
          <div class='metoc-note'>{note}</div>
        </div>
        """)
    return f"""
    <div class='uuv-card'>
      <div class='metoc-header'>
        <div>
          <h3>METOC Assessment</h3>
          <div class='small-muted'>FOR PLANNING ONLY. Open-Meteo environmental data are mission-planning inputs, not tactical METOC authority.</div>
        </div>
        <div class='posture'>Overall: {assessment['posture']}</div>
      </div>
      <div class='metoc-grid'>{''.join(cards)}</div>
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
    return f"**METOC lookup point:** {label}, {lat:.6f}, {lon:.6f}"


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
        shape_label = "Polygon" if area_data.get("geometry_type") == "polygon" else "Rectangle"
        geom = (
            f"**Mission loaded:** {mission_type}  \n"
            f"**Geometry:** {shape_label} search area  \n"
            f"**Area:** {fmt(area_data.get('area_km2'))} sq km  \n"
            f"**Dimensions:** {fmt(area_data.get('width_km'))} km x {fmt(area_data.get('height_km'))} km  \n"
            f"**METOC lookup point:** area centroid, {fmt(area_data.get('centroid_lat'), 6)}, {fmt(area_data.get('centroid_lon'), 6)}"
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
            f"**Route distance:** {fmt(area_data.get('route_distance_km'))} km  \n"
            f"**Route heading:** {fmt(area_data.get('route_heading_deg'), 1)} deg  \n"
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
                f"**One-way route distance:** {one_way_km:.2f} km  \n"
                f"**Out-and-back patrol loop distance:** {loop_distance_km:.2f} km  \n"
                f"{_fmt_lookup_point('first route point', lookup_lat, lookup_lon)}"
            )
        else:
            patrol_points = _points_from_dicts(area_data.get("vertices"))
            lookup_lat, lookup_lon = patrol_points[0] if patrol_points else (None, None)
            geometry_label = "Polygon" if geometry_type == "polygon" else "Rectangle"
            geom = (
                f"**Mission loaded:** ISR  \n"
                f"**Geometry:** {geometry_label} perimeter patrol  \n"
                f"**Patrol loop distance:** {loop_distance_km:.2f} km  \n"
                f"{_fmt_lookup_point('first patrol point', lookup_lat, lookup_lon)}  \n"
                f"**Area enclosed:** {fmt(area_data.get('area_km2'))} sq km, reference only"
            )
    env = (
        f"\n\n**Open-Meteo baseline:** current {fmt(environment.get('current_speed_kts_mean'))} kts "
        f"from {fmt(environment.get('current_direction_deg_mean'), 1)} deg, "
        f"SST {fmt(environment.get('sea_surface_temp_c_mean'), 1)} deg C, "
        f"wind {fmt(environment.get('wind_speed_kts_mean'))} kts.  \n"
        f"**Weather:** {environment.get('weather_summary') or 'N/A'}"
    )
    return geom + env


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

    fig, ax1 = plt.subplots(figsize=(9, 4.6))
    ax1.fill_between(t, p10_series, p90_series, alpha=0.15, color="#2563eb", label="_nolegend_")
    cumulative_line, = ax1.plot(t, p50_series, linewidth=2.2, color="#1d4ed8", label="Expected cumulative energy (P50)")
    ax1.scatter([0.0], [0.0], zorder=5, color="#1d4ed8")
    ax1.scatter([p50_t], [p50_e], zorder=5, color="#1d4ed8")
    ax1.set_xlabel("Mission Time (hours)")
    ax1.set_ylabel("Cumulative Energy (kWh)")
    ax1.set_title("Mission Energy Progress and Battery Lens")
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
    fig.text(
        0.5,
        0.025,
        "Shaded band shows P10-P90 Monte Carlo cumulative-energy spread. Battery remaining is usable planning energy, not direct voltage/SOC.",
        ha="center",
        va="bottom",
        fontsize=8.5,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    return fig


def build_distribution_chart(energy_arr: np.ndarray, p80: float, usable_total_kwh: float) -> Any:
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
    ax.axvline(p50, linestyle="-", linewidth=2, label=f"Expected energy (P50): {p50:.3g} kWh")
    ax.axvline(p80, linestyle="--", linewidth=2, label=f"Planning-level energy (P80): {p80:.3g} kWh")
    ax.axvline(p95, linestyle=":", linewidth=2, label=f"Conservative energy (P95): {p95:.3g} kWh")
    if xmin <= usable_total_kwh <= xmax:
        ax.axvline(usable_total_kwh, linestyle="-.", linewidth=2, label=f"Battery inventory: {usable_total_kwh:.3g} kWh")
    else:
        ax.text(0.98, 0.95, f"Battery inventory without recharge: {usable_total_kwh:.2f} kWh", transform=ax.transAxes, ha="right", va="top", fontsize=9, bbox=dict(boxstyle="round,pad=0.35", facecolor="#eef2f7", edgecolor="#94a3b8", alpha=0.95))
    ax.set_xlim(xmin, xmax)
    ax.set_xlabel("Mission energy required, kWh")
    ax.set_ylabel("Monte Carlo count")
    ax.set_title("Mission Energy Uncertainty Distribution")
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
    )
    ax.text(
        x0 + dx * 0.5,
        y0 + dy * 0.5,
        "Current",
        fontsize=8.5,
        ha="center",
        va="bottom",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="#cbd5e1", alpha=0.84),
        zorder=7,
    )


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
    return f"Along-track current {along:+.2f} kts | cross-track {cross:+.2f} kts | transit uplift {penalty_pct:.1f}%"


def _draw_area_lanes(ax: Any, area: MissionArea, track_spacing_m: float, orientation: str, arrow_density: int = 25) -> dict[str, object]:
    points = search_polygon_points(area)
    lanes = clipped_search_lanes(area, track_spacing_m, orientation)
    xs = [p[0] for p in points] + [points[0][0]]
    ys = [p[1] for p in points] + [points[0][1]]
    ax.fill(xs, ys, color="#38bdf8", alpha=0.16, label="Selected mission area")
    ax.plot(xs, ys, color="#075985", linewidth=2.3, label="Mission area boundary")
    min_x, max_x, min_y, max_y = local_bounds(points)
    span_x = max(max_x - min_x, 0.001)
    span_y = max(max_y - min_y, 0.001)
    segments = list(lanes.get("segments", []))
    for index, (x0, y0, x1, y1) in enumerate(segments):
        ax.plot([x0, x1], [y0, y1], color="#0f766e", linewidth=1.35, alpha=0.78)
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


def build_mapping_snapshot_chart(summary: dict[str, object], area: MissionArea, environment: EnvironmentData, track_spacing_m: float) -> Any:
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
            f"Route distance: {distance:.2f} km",
            ha="center",
            va="bottom",
            fontsize=8,
            wrap=True,
        )
        ax.set_title("Payload Route and Current Snapshot", pad=10, fontsize=13)
        ax.legend(loc="upper right", fontsize=8)
        fig.tight_layout(rect=(0, 0.06, 1, 1))
        return fig

    if mission_type in ISR_MISSIONS:
        if area.is_payload_route:
            patrol_points = _project_route_points(area)
            xs = [point[0] for point in patrol_points]
            ys = [point[1] for point in patrol_points]
            ax.plot(xs, ys, color="#075985", linewidth=2.4, marker="o", markersize=4, label="ISR line patrol")
            ax.plot(list(reversed(xs)), list(reversed(ys)), color="#0f766e", linewidth=1.6, linestyle="--", label="Return leg")
        else:
            patrol_points = search_polygon_points(area)
            xs = [point[0] for point in patrol_points] + [patrol_points[0][0]]
            ys = [point[1] for point in patrol_points] + [patrol_points[0][1]]
            ax.fill(xs, ys, color="#38bdf8", alpha=0.16, label="ISR patrol area")
            ax.plot(xs, ys, color="#075985", linewidth=2.4, label="Perimeter patrol")
        bounds = _set_limits(ax, patrol_points, equal_aspect=True)
        _draw_current_arrow(ax, environment, bounds)
        _draw_north_arrow(ax, *bounds)
        _draw_scale_bar(ax, *bounds)
        ax.set_title("ISR Patrol Route Snapshot", pad=10, fontsize=13)
        fig.text(
            0.5,
            0.025,
            (
                f"Loop distance: {float(summary.get('isr_loop_distance_km', 0)):.2f} km | "
                f"Time on station: {float(summary.get('isr_max_time_on_station_hr', 0)):.1f} hr | "
                f"Completed loops: {summary.get('isr_completed_loops', 0)}"
            ),
            ha="center",
            va="bottom",
            fontsize=8,
            wrap=True,
        )
        ax.legend(loc="upper right", fontsize=8)
        fig.tight_layout(rect=(0, 0.06, 1, 1))
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
    ax.text(0.01, -0.18, f"Swath/track spacing: {track_spacing_m:.0f} m | Recommended orientation: {orientation} | Planning snapshot only", transform=ax.transAxes, fontsize=8, va="top")
    ax.text(0.99, -0.18, f"Lanes: {lanes.get('lane_count', 0)}", transform=ax.transAxes, ha="right", fontsize=8, va="top")
    ax.text(
        0.99,
        0.02,
        f"Area: {(area.area_km2 or 0):.2f} sq km\nBounding box: {(area.width_km or 0):.2f} x {(area.height_km or 0):.2f} km",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#eef2f7", edgecolor="#94a3b8", alpha=0.95),
    )
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
