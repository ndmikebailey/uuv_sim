"""UI-only table, HTML, and chart rendering helpers."""

from __future__ import annotations

import math
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from core.geometry import clipped_search_lanes, local_bounds, search_polygon_points
from models.environment_model import EnvironmentData
from models.mission_model import MissionArea
from services.metoc_fusion import MetocFusionService
from utils.constants import SEARCH_MISSIONS
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


def results_html(summary: dict[str, object]) -> str:
    """Render summary output as a compact HTML card."""
    def yesno(value: object) -> str:
        return "Yes" if value else "No"

    rows = [
        ("Platform", summary.get("platform")),
        ("Mission type", summary.get("mission_type")),
        ("P80 mission energy", f"{float(summary.get('p80_energy_kwh', 0)):.2f} kWh"),
        ("Mean mission duration", f"{float(summary.get('mean_duration_hr', 0)):.1f} hr"),
        ("Battery nameplate capacity", f"{float(summary.get('battery_nameplate_kwh', 0)):.2f} kWh"),
        ("Usable planning energy per set", f"{float(summary.get('usable_battery_per_set_kwh', 0)):.2f} kWh"),
        ("Battery sets on hand", summary.get("battery_sets_available")),
        ("Battery sets required at P80", summary.get("battery_sets_required_p80")),
        ("Sufficient without recharge", yesno(summary.get("battery_inventory_sufficient_no_recharge"))),
        ("Recharge / swap sequences required", summary.get("recharge_sequences_required")),
        ("Mission sequences", summary.get("mission_sequences")),
        ("Monte Carlo seed", summary.get("rng_seed")),
    ]
    if summary.get("recommended_track_orientation") != "N/A":
        rows.append(("Recommended search-track orientation", summary.get("recommended_track_orientation")))
    body = "".join(f"<tr><td>{key}</td><td>{value}</td></tr>" for key, value in rows)
    return f"""
    <div class='uuv-card'>
      <h2>Mission Energy and Battery Summary</h2>
      <table class='uuv-table'><tbody>{body}</tbody></table>
      <p class='small-muted'>Energy = Power x Time. Wh = W x hr. kWh = Wh / 1000. J = Wh x 3600. MJ = kWh x 3.6.</p>
    </div>
    """


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


def context_markdown(context: dict[str, Any]) -> str:
    """Render loaded mission context for the simulator tab."""
    if not context:
        return "No mission context loaded. The simulator can still run with manual inputs."
    mission_type = str(context.get("mission_type"))
    area_data = context.get("area", {}) if isinstance(context.get("area"), dict) else context
    environment = context.get("environment", {}) if isinstance(context.get("environment"), dict) else context
    if mission_type in SEARCH_MISSIONS:
        shape_label = "Polygon" if area_data.get("geometry_type") == "polygon" else "Rectangle"
        geom = (
            f"**Mission loaded:** {mission_type}  \n"
            f"**Geometry:** {shape_label} search area  \n"
            f"**Area:** {fmt(area_data.get('area_km2'))} sq km  \n"
            f"**Dimensions:** {fmt(area_data.get('width_km'))} km x {fmt(area_data.get('height_km'))} km  \n"
            f"**Centroid:** {fmt(area_data.get('centroid_lat'), 5)}, {fmt(area_data.get('centroid_lon'), 5)}"
        )
    else:
        geom = (
            f"**Mission loaded:** Payload Delivery  \n"
            f"**Geometry:** Line route  \n"
            f"**Route distance:** {fmt(area_data.get('route_distance_km'))} km  \n"
            f"**Route heading:** {fmt(area_data.get('route_heading_deg'), 1)} deg  \n"
            f"**Centroid:** {fmt(area_data.get('centroid_lat'), 5)}, {fmt(area_data.get('centroid_lon'), 5)}"
        )
    env = (
        f"\n\n**Open-Meteo baseline:** current {fmt(environment.get('current_speed_kts_mean'))} kts "
        f"from {fmt(environment.get('current_direction_deg_mean'), 1)} deg, "
        f"SST {fmt(environment.get('sea_surface_temp_c_mean'), 1)} deg C, "
        f"wind {fmt(environment.get('wind_speed_kts_mean'))} kts.  \n"
        f"**Weather:** {environment.get('weather_summary') or 'N/A'}"
    )
    return geom + env


def build_energy_time_chart(energy_arr: np.ndarray, duration_arr: np.ndarray, usable_battery_per_set: float, battery_sets_available: int, recharge_hr: float) -> Any:
    """Render cumulative mission energy and battery lens."""
    p50_e = float(np.percentile(energy_arr, 50))
    p10_e = float(np.percentile(energy_arr, 10))
    p90_e = float(np.percentile(energy_arr, 90))
    p50_t = max(float(np.percentile(duration_arr, 50)), 0.1)
    t = np.linspace(0, p50_t, 140)
    x = t / p50_t
    phase_curve = 0.10 * x + 0.75 * (x ** 1.08) + 0.15 * (x ** 2.4)
    phase_curve = phase_curve / max(phase_curve[-1], 1e-9)

    fig, ax1 = plt.subplots(figsize=(9, 4.6))
    ax1.fill_between(t, p10_e * phase_curve, p90_e * phase_curve, alpha=0.25, label="Energy variance band (P10-P90)")
    ax1.plot(t, p50_e * phase_curve, linewidth=2, label="Median cumulative energy")
    ax1.set_xlabel("Mission Time (hours)")
    ax1.set_ylabel("Cumulative Energy (kWh)")
    ax1.set_title("Mission Energy Progress and Battery Lens")
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()
    available = max(usable_battery_per_set * max(1, battery_sets_available), 0.1)
    soc = np.clip(1 - (p50_e * phase_curve) / available, 0, 1)
    ax2.plot(t, 3.0 + 1.2 * np.sqrt(soc), linestyle="--", linewidth=2, label="Active battery voltage proxy")
    ax2.set_ylabel("Voltage Proxy (V)")
    if usable_battery_per_set > 0:
        sets_crossed = int(np.floor(p50_e / usable_battery_per_set))
        for index in range(1, min(sets_crossed + 1, battery_sets_available + 1)):
            frac = min((index * usable_battery_per_set) / max(p50_e, 1e-9), 1.0)
            tx = float(np.interp(frac, phase_curve, t))
            ax1.axvline(tx, linestyle=":", alpha=0.45)
            ax1.text(tx, ax1.get_ylim()[1] * 0.93, f"B{index}", rotation=90, va="top", ha="right", fontsize=8)
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    fig.tight_layout()
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
    ax.axvline(p50, linestyle="-", linewidth=2, label=f"P50: {p50:.3g} kWh")
    ax.axvline(p80, linestyle="--", linewidth=2, label=f"P80: {p80:.3g} kWh")
    ax.axvline(p95, linestyle=":", linewidth=2, label=f"P95: {p95:.3g} kWh")
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
    arrow_len = max(min(span_x, span_y) * 0.22, 0.08)
    x0 = min_x + span_x * 0.10
    y0 = min_y + span_y * 0.12
    ax.arrow(x0, y0, arrow_len * math.cos(theta), arrow_len * math.sin(theta), length_includes_head=True, head_width=max(min(span_x, span_y) * 0.025, 0.025), head_length=max(min(span_x, span_y) * 0.035, 0.035), linestyle="--", linewidth=1.6, color="#7c2d12")
    ax.text(x0, y0 + max(span_y * 0.09, 0.05), f"Current {current_speed:.2f} kts @ {current_dir:.0f} deg", fontsize=9, bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#cbd5e1", alpha=0.88))


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


def build_search_overlay_chart(summary: dict[str, object], area: MissionArea, environment: EnvironmentData, track_spacing_m: float) -> Any:
    """Render the swath-lane planning overlay."""
    fig, ax = plt.subplots(figsize=(10.5, 5.6), dpi=120)
    if summary.get("mission_type") not in SEARCH_MISSIONS or not area.is_search_area:
        ax.text(0.5, 0.5, "Search-pattern overlay applies to ISR / Area Search / MCM missions.", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        fig.tight_layout()
        return fig
    points = search_polygon_points(area)
    orientation = str(summary.get("recommended_track_orientation", "East-West"))
    lanes = _draw_area_lanes(ax, area, track_spacing_m, orientation)
    bounds = _set_limits(ax, points, equal_aspect=False)
    _draw_current_arrow(ax, environment, bounds)
    area_km2 = area.area_km2 or 0.0
    ax.set_title(f"Recommended Search Pattern Overlay: {orientation}", pad=12, fontsize=14)
    ax.set_xlabel("Local east-west distance, km")
    ax.set_ylabel("Local north-south distance, km")
    ax.grid(True, alpha=0.20)
    ax.text(0.01, -0.18, f"Planning overlay only | swath/track spacing: {track_spacing_m / 1000.0:.3f} km | generated lanes shown: {lanes.get('lane_count', 0)}", transform=ax.transAxes, fontsize=8.5, va="top")
    ax.text(0.99, 0.02, f"Area: {area_km2:.2f} sq km\nBox: {(area.width_km or 0):.2f} x {(area.height_km or 0):.2f} km", transform=ax.transAxes, ha="right", va="bottom", fontsize=9, bbox=dict(boxstyle="round,pad=0.35", facecolor="#eef2f7", edgecolor="#94a3b8", alpha=0.95))
    fig.tight_layout()
    return fig


def build_mapping_snapshot_chart(summary: dict[str, object], area: MissionArea, environment: EnvironmentData, track_spacing_m: float) -> Any:
    """Render the report map snapshot panel."""
    fig, ax = plt.subplots(figsize=(6.7, 5.6), dpi=120)
    if summary.get("mission_type") not in SEARCH_MISSIONS or not area.is_search_area:
        ax.text(0.5, 0.5, "Payload route snapshot will show start, target, route, and current in a later report pass.", ha="center", va="center", wrap=True, transform=ax.transAxes)
        ax.axis("off")
        fig.tight_layout()
        return fig
    points = search_polygon_points(area)
    orientation = str(summary.get("recommended_track_orientation", "East-West"))
    ax.set_facecolor("#eef7fb")
    ax.grid(True, color="white", linewidth=0.9, alpha=0.85)
    lanes = _draw_area_lanes(ax, area, track_spacing_m, orientation, arrow_density=18)
    bounds = _set_limits(ax, points, equal_aspect=True)
    _draw_current_arrow(ax, environment, local_bounds(points))
    min_x, max_x, min_y, max_y = bounds
    span_x = max(max_x - min_x, 0.001)
    span_y = max(max_y - min_y, 0.001)
    extent = max(span_x, span_y)
    if area.centroid_local_km:
        ax.scatter([area.centroid_local_km.x], [area.centroid_local_km.y], s=34, marker="o", color="#111827", zorder=5)
    north_x = min_x + span_x * 0.10
    north_y = min_y + span_y * 0.70
    north_len = max(span_y * 0.16, extent * 0.08)
    ax.arrow(north_x, north_y, 0, north_len, length_includes_head=True, head_width=max(extent * 0.025, 0.025), head_length=max(extent * 0.040, 0.035), linewidth=1.6, color="black")
    ax.text(north_x, north_y + north_len + max(extent * 0.025, 0.02), "N", ha="center", va="bottom", fontsize=10, fontweight="bold")
    scale_len = min(_nice_scale_km(extent), span_x * 0.70)
    scale_x = min_x + span_x * 0.10
    scale_y = min_y + span_y * 0.08
    ax.plot([scale_x, scale_x + scale_len], [scale_y, scale_y], color="black", linewidth=3)
    ax.plot([scale_x, scale_x], [scale_y - span_y * 0.015, scale_y + span_y * 0.015], color="black", linewidth=2)
    ax.plot([scale_x + scale_len, scale_x + scale_len], [scale_y - span_y * 0.015, scale_y + span_y * 0.015], color="black", linewidth=2)
    ax.text(scale_x + scale_len / 2, scale_y + max(span_y * 0.035, 0.03), f"{scale_len:.3g} km", ha="center", va="bottom", fontsize=8.5)
    shape_label = "Polygon" if area.geometry_type == "polygon" else "Rectangle"
    ax.set_title(f"Mission Map Snapshot: {shape_label}", pad=10, fontsize=13)
    ax.set_xlabel("Local east-west distance, km")
    ax.set_ylabel("Local north-south distance, km")
    ax.text(0.01, -0.18, f"Swath/track spacing: {track_spacing_m:.0f} m | Recommended orientation: {orientation} | Planning snapshot only", transform=ax.transAxes, fontsize=8, va="top")
    ax.text(0.99, -0.18, f"Lanes: {lanes.get('lane_count', 0)}", transform=ax.transAxes, ha="right", fontsize=8, va="top")
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
