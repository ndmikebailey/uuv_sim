"""Leaflet iframe component for map geometry selection."""

from __future__ import annotations

import html
import json
from uuid import uuid4

from utils.constants import REGION_PRESETS


def _render_token() -> str:
    """Return a short token that forces browser iframe remounts between updates."""
    return uuid4().hex


def build_leaflet_iframe(region_name: str = "Guam") -> str:
    """Return a Leaflet iframe that emits raw geometry JSON to Gradio."""
    lat, lon, zoom = REGION_PRESETS.get(region_name, REGION_PRESETS["Guam"])
    render_token = _render_token()
    inner_html = f"""
<!DOCTYPE html>
<html data-uuv-render-token="{render_token}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.css"/>
  <style>
    :root {{
      color-scheme: light dark;
      --map-shell-bg: #ffffff;
      --map-note-bg: #e5edf7;
      --map-card-bg: #ffffff;
      --map-border: #cbd5e1;
      --map-text: #0f172a;
      --map-heading: #020617;
      --map-muted: #475569;
    }}
    html.light, body.light {{
      --map-shell-bg: #ffffff;
      --map-note-bg: #e5edf7;
      --map-card-bg: #ffffff;
      --map-border: #cbd5e1;
      --map-text: #0f172a;
      --map-heading: #020617;
      --map-muted: #475569;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --map-shell-bg: #0b1220;
        --map-note-bg: #1f2937;
        --map-card-bg: #0f172a;
        --map-border: #374151;
        --map-text: #e5e7eb;
        --map-heading: #ffffff;
        --map-muted: #cbd5e1;
      }}
    }}
    html.dark, body.dark {{
      --map-shell-bg: #0b1220;
      --map-note-bg: #1f2937;
      --map-card-bg: #0f172a;
      --map-border: #374151;
      --map-text: #e5e7eb;
      --map-heading: #ffffff;
      --map-muted: #cbd5e1;
    }}
    html, body {{ margin: 0; padding: 0; background: var(--map-shell-bg); color: var(--map-text); font-family: Arial, sans-serif; }}
    #map {{ width: 100%; height: 560px; }}
    #output {{ padding: 12px; background: var(--map-shell-bg); min-height: 96px; font-size: 14px; }}
    #raw_output {{ display: none; }}
    .note {{ padding: 8px 10px; background: var(--map-note-bg); color: var(--map-text); font-size: 12px; }}
    .snap-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
    .snap-card {{ border: 1px solid var(--map-border); border-radius: 10px; padding: 10px; background: var(--map-card-bg); color: var(--map-text); }}
    .snap-label {{ color: var(--map-muted); font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }}
    .snap-value {{ color: var(--map-heading); font-size: 20px; font-weight: 800; margin-top: 3px; }}
    .snap-sub {{ color: var(--map-muted); font-size: 12px; margin-top: 6px; }}
    @media (max-width: 720px) {{
      #map {{ height: 500px; }}
      .snap-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="note">Draw a line, rectangle, or polygon for ISR; draw a rectangle or polygon for Area Search / MCM; draw a line for Route / Transit.</div>
  <div id="output">
    <div class="snap-grid">
      <div class="snap-card"><div class="snap-label">Selected Geometry</div><div class="snap-value">Not loaded</div><div class="snap-sub">Draw a rectangle, polygon, or line.</div></div>
      <div class="snap-card"><div class="snap-label">Area / Route</div><div class="snap-value">--</div><div class="snap-sub">Waiting on mission geometry.</div></div>
      <div class="snap-card"><div class="snap-label">Geometry center</div><div class="snap-value">--</div><div class="snap-sub">Waiting on mission geometry.</div></div>
    </div>
  </div>
  <pre id="raw_output"></pre>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.js"></script>
  <script>
    const renderToken = "{render_token}";
    function syncColorTheme() {{
      try {{
        const parentDoc = window.parent && window.parent.document;
        const parentRoot = parentDoc && parentDoc.documentElement;
        const parentBody = parentDoc && parentDoc.body;
        const parentContainer = parentDoc && parentDoc.querySelector('.gradio-container');
        const themeHosts = [parentRoot, parentBody, parentContainer].filter(Boolean);
        const isDark =
          themeHosts.some(el => el.classList.contains('dark') || el.dataset.theme === 'dark');
        document.documentElement.classList.toggle('dark', Boolean(isDark));
        document.body.classList.toggle('dark', Boolean(isDark));
        document.documentElement.classList.toggle('light', !Boolean(isDark));
        document.body.classList.toggle('light', !Boolean(isDark));
      }} catch (error) {{
        const isDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        document.documentElement.classList.toggle('dark', isDark);
        document.body.classList.toggle('dark', isDark);
        document.documentElement.classList.toggle('light', !isDark);
        document.body.classList.toggle('light', !isDark);
      }}
    }}
    syncColorTheme();
    const map = L.map('map').setView([{lat}, {lon}], {zoom});
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);
    const drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);
    map.addControl(new L.Control.Draw({{
      draw: {{ polygon: true, polyline: true, rectangle: true, circle: false, circlemarker: false, marker: false }},
      edit: {{ featureGroup: drawnItems, remove: true }}
    }}));

    function haversineKm(lat1, lon1, lat2, lon2) {{
      const R = 6371.0088;
      const toRad = deg => deg * Math.PI / 180;
      const dLat = toRad(lat2 - lat1);
      const dLon = toRad(lon2 - lon1);
      const a =
        Math.sin(dLat / 2) ** 2 +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
        Math.sin(dLon / 2) ** 2;
      return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }}
    function bearingDeg(lat1, lon1, lat2, lon2) {{
      const toRad = deg => deg * Math.PI / 180;
      const toDeg = rad => rad * 180 / Math.PI;
      const phi1 = toRad(lat1);
      const phi2 = toRad(lat2);
      const dLon = toRad(lon2 - lon1);
      const y = Math.sin(dLon) * Math.cos(phi2);
      const x = Math.cos(phi1) * Math.sin(phi2) - Math.sin(phi1) * Math.cos(phi2) * Math.cos(dLon);
      return (toDeg(Math.atan2(y, x)) + 360) % 360;
    }}
    function latLngToVertex(p) {{ return {{ lat: +p.lat.toFixed(6), lon: +p.lng.toFixed(6) }}; }}
    function boundsPayload(bounds) {{
      return {{
        north: +bounds.getNorth().toFixed(6),
        south: +bounds.getSouth().toFixed(6),
        east: +bounds.getEast().toFixed(6),
        west: +bounds.getWest().toFixed(6)
      }};
    }}
    function rectangleSummary(layer) {{
      const b = layer.getBounds();
      const centroidLat = (b.getNorth() + b.getSouth()) / 2;
      const centroidLon = (b.getEast() + b.getWest()) / 2;
      const widthKm = haversineKm(centroidLat, b.getWest(), centroidLat, b.getEast());
      const heightKm = haversineKm(b.getSouth(), centroidLon, b.getNorth(), centroidLon);
      return {{
        geometry_type: "rectangle",
        centroid_lat: +centroidLat.toFixed(6),
        centroid_lon: +centroidLon.toFixed(6),
        area_km2: +(widthKm * heightKm).toFixed(3),
        width_km: +widthKm.toFixed(3),
        height_km: +heightKm.toFixed(3),
        bounds: boundsPayload(b),
        vertices: [
          {{ lat: +b.getSouth().toFixed(6), lon: +b.getWest().toFixed(6) }},
          {{ lat: +b.getSouth().toFixed(6), lon: +b.getEast().toFixed(6) }},
          {{ lat: +b.getNorth().toFixed(6), lon: +b.getEast().toFixed(6) }},
          {{ lat: +b.getNorth().toFixed(6), lon: +b.getWest().toFixed(6) }}
        ]
      }};
    }}
    function polygonSummary(layer) {{
      const rings = layer.getLatLngs();
      const pts = Array.isArray(rings[0]) ? rings[0] : rings;
      const vertices = pts.map(latLngToVertex);
      const b = layer.getBounds();
      const centroidLat = vertices.reduce((sum, p) => sum + p.lat, 0) / Math.max(vertices.length, 1);
      const centroidLon = vertices.reduce((sum, p) => sum + p.lon, 0) / Math.max(vertices.length, 1);
      const widthKm = haversineKm((b.getNorth() + b.getSouth()) / 2, b.getWest(), (b.getNorth() + b.getSouth()) / 2, b.getEast());
      const heightKm = haversineKm(b.getSouth(), (b.getEast() + b.getWest()) / 2, b.getNorth(), (b.getEast() + b.getWest()) / 2);
      return {{
        geometry_type: "polygon",
        centroid_lat: +centroidLat.toFixed(6),
        centroid_lon: +centroidLon.toFixed(6),
        width_km: +widthKm.toFixed(3),
        height_km: +heightKm.toFixed(3),
        vertices: vertices,
        bounds: boundsPayload(b)
      }};
    }}
    function lineSummary(layer) {{
      const pts = layer.getLatLngs();
      const vertices = pts.map(latLngToVertex);
      const start = vertices[0];
      const end = vertices[vertices.length - 1];
      let routeKm = 0;
      for (let i = 0; i < vertices.length - 1; i++) {{
        routeKm += haversineKm(vertices[i].lat, vertices[i].lon, vertices[i + 1].lat, vertices[i + 1].lon);
      }}
      return {{
        geometry_type: "line",
        centroid_lat: +((start.lat + end.lat) / 2).toFixed(6),
        centroid_lon: +((start.lon + end.lon) / 2).toFixed(6),
        route_distance_km: +routeKm.toFixed(3),
        route_heading_deg: +bearingDeg(start.lat, start.lon, end.lat, end.lon).toFixed(1),
        route_points: vertices,
        vertices: vertices
      }};
    }}
    function snapshotHtml(summary) {{
      if (!summary || summary.error) {{
        return '<div class="snap-grid"><div class="snap-card"><div class="snap-label">Selected Geometry</div><div class="snap-value">Error</div><div class="snap-sub">Redraw geometry.</div></div><div class="snap-card"><div class="snap-label">Area / Route</div><div class="snap-value">--</div><div class="snap-sub">No usable geometry.</div></div><div class="snap-card"><div class="snap-label">Geometry center</div><div class="snap-value">--</div><div class="snap-sub">No geometry center.</div></div></div>';
      }}
      if (summary.geometry_type === 'line') {{
        return '<div class="snap-grid"><div class="snap-card"><div class="snap-label">Selected Geometry</div><div class="snap-value">Route</div><div class="snap-sub">Route points captured.</div></div><div class="snap-card"><div class="snap-label">Route</div><div class="snap-value">' + summary.route_distance_km + ' km</div><div class="snap-sub">Heading: ' + summary.route_heading_deg + ' deg</div></div><div class="snap-card"><div class="snap-label">Geometry center</div><div class="snap-value">' + summary.centroid_lat + ', ' + summary.centroid_lon + '</div><div class="snap-sub">Backend recomputes on mission load.</div></div></div>';
      }}
      if (summary.geometry_type === 'MultiArea') {{
        return '<div class="snap-grid"><div class="snap-card"><div class="snap-label">Selected Geometry</div><div class="snap-value">Multi-area</div><div class="snap-sub">' + summary.number_of_search_areas + ' areas captured.</div></div><div class="snap-card"><div class="snap-label">Total Area</div><div class="snap-value">' + summary.total_area_km2 + ' sq km</div><div class="snap-sub">Backend plans combined search area.</div></div><div class="snap-card"><div class="snap-label">METOC samples</div><div class="snap-value">' + summary.representative_points.length + '</div><div class="snap-sub">Area centroid lookup points.</div></div></div>';
      }}
      const label = summary.geometry_type === 'polygon' ? 'Polygon' : 'Rectangle';
      const areaText = summary.area_km2 ? summary.area_km2 + ' sq km' : summary.vertices.length + ' pts';
      const detailText = summary.width_km && summary.height_km ? 'Bounding box: ' + summary.width_km + ' x ' + summary.height_km + ' km' : 'Backend computes area on mission load.';
      return '<div class="snap-grid"><div class="snap-card"><div class="snap-label">Selected Geometry</div><div class="snap-value">' + label + '</div><div class="snap-sub">' + label + ' captured.</div></div><div class="snap-card"><div class="snap-label">Area / Shape</div><div class="snap-value">' + areaText + '</div><div class="snap-sub">' + detailText + '</div></div><div class="snap-card"><div class="snap-label">Geometry center</div><div class="snap-value">' + summary.centroid_lat + ', ' + summary.centroid_lon + '</div><div class="snap-sub">Backend recomputes on mission load.</div></div></div>';
    }}
    function sendGeometry(summary) {{
      document.getElementById("raw_output").textContent = JSON.stringify(summary, null, 2);
      document.getElementById("output").innerHTML = snapshotHtml(summary);
      window.parent.postMessage({{ type: "uuv_geometry", payload: summary, renderToken: renderToken }}, "*");
    }}
    function summarizeLayer(layer) {{
      if (layer instanceof L.Rectangle) return rectangleSummary(layer);
      if (layer instanceof L.Polygon) return polygonSummary(layer);
      if (layer instanceof L.Polyline) return lineSummary(layer);
      return {{ error: "Unsupported geometry type." }};
    }}
    function summarizeAllAreas() {{
      const areas = [];
      drawnItems.eachLayer(function(layer) {{
        if (layer instanceof L.Rectangle) areas.push(rectangleSummary(layer));
        else if (layer instanceof L.Polygon) areas.push(polygonSummary(layer));
      }});
      if (areas.length === 0) {{
        sendGeometry({{}});
      }} else if (areas.length === 1) {{
        sendGeometry(areas[0]);
      }} else {{
        const totalArea = areas.reduce((sum, area) => sum + (area.area_km2 || 0), 0);
        sendGeometry({{
          geometry_type: "MultiArea",
          areas: areas,
          total_area_km2: +totalArea.toFixed(3),
          area_km2: +totalArea.toFixed(3),
          number_of_search_areas: areas.length,
          representative_points: areas.map(area => ({{ lat: area.centroid_lat, lon: area.centroid_lon }})),
          centroid_lat: +(areas.reduce((sum, area) => sum + area.centroid_lat, 0) / areas.length).toFixed(6),
          centroid_lon: +(areas.reduce((sum, area) => sum + area.centroid_lon, 0) / areas.length).toFixed(6)
        }});
      }}
    }}
    map.on(L.Draw.Event.CREATED, function(event) {{
      if (event.layer instanceof L.Polyline && !(event.layer instanceof L.Polygon)) {{
        drawnItems.clearLayers();
        drawnItems.addLayer(event.layer);
        sendGeometry(summarizeLayer(event.layer));
        return;
      }}
      drawnItems.eachLayer(function(layer) {{
        if (layer instanceof L.Polyline && !(layer instanceof L.Polygon)) {{
          drawnItems.removeLayer(layer);
        }}
      }});
      drawnItems.addLayer(event.layer);
      summarizeAllAreas();
    }});
    map.on(L.Draw.Event.EDITED, function(event) {{
      summarizeAllAreas();
    }});
    map.on(L.Draw.Event.DELETED, function() {{
      document.getElementById("raw_output").textContent = "";
      window.parent.postMessage({{ type: "uuv_geometry", payload: {{}} }}, "*");
    }});
  </script>
</body>
</html>
"""
    srcdoc = html.escape(inner_html, quote=True)
    return f"""
<iframe
  id="uuv_map_iframe"
  class="uuv-map-iframe"
  title="uuv-mission-map"
  name="uuv-mission-map-{render_token}"
  data-uuv-render-token="{render_token}"
  srcdoc="{srcdoc}"
  width="100%"
  height="760"
  style="border:none; border-radius:12px; overflow:hidden; background:#ffffff;"
></iframe>
"""


def build_report_map_overlay_iframe(
    geometry: dict[str, object] | None,
    mission_type: str,
    current_speed_kts: float | None = None,
    current_direction_deg: float | None = None,
    metoc_points: list[dict[str, float]] | None = None,
) -> str:
    """Return a compact Leaflet report overlay for loaded GPS mission geometry."""
    if not geometry:
        return ""
    render_token = _render_token()
    geometry_json = html.escape(json.dumps(geometry), quote=False)
    metoc_json = html.escape(json.dumps(metoc_points or []), quote=False)
    mission_type_json = html.escape(json.dumps(mission_type), quote=False)
    current_speed = 0.0 if current_speed_kts is None else float(current_speed_kts)
    current_dir = 0.0 if current_direction_deg is None else float(current_direction_deg)
    inner_html = f"""
<!DOCTYPE html>
<html data-uuv-render-token="{render_token}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <style>
    html, body {{ margin: 0; padding: 0; background: #0b1220; font-family: Arial, sans-serif; }}
    #map {{ width: 100%; height: 360px; }}
    .legend {{ position:absolute; bottom:10px; left:10px; background:rgba(15,23,42,.88); color:#e5e7eb; padding:8px 10px; border-radius:8px; font-size:12px; z-index:999; }}
    .title {{ position:absolute; top:10px; left:10px; background:rgba(15,23,42,.88); color:#fff; padding:8px 10px; border-radius:8px; font-weight:800; font-size:13px; z-index:999; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="title">Mission Map Overlay</div>
  <div class="legend">GPS geometry | METOC point(s) | Current vector</div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const renderToken = "{render_token}";
    const geometry = {geometry_json};
    const metocPoints = {metoc_json};
    const missionType = {mission_type_json};
    const currentSpeed = {current_speed};
    const currentDir = {current_dir};
    const map = L.map('map', {{ zoomControl: true, attributionControl: true }});
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);
    const bounds = [];
    function latLon(p) {{ return [Number(p.lat), Number(p.lon)]; }}
    function addPoint(p) {{ if (Number.isFinite(Number(p.lat)) && Number.isFinite(Number(p.lon))) bounds.push(latLon(p)); }}
    function drawArea(area, label) {{
      const raw = area.vertices || [];
      const pts = raw.map(latLon);
      if (!pts.length) return;
      raw.forEach(addPoint);
      L.polygon(pts, {{ color: '#38bdf8', weight: 2, fillColor: '#38bdf8', fillOpacity: 0.18 }}).addTo(map).bindTooltip(label || 'Selected area');
    }}
    function drawLine(area) {{
      const raw = area.route_points || area.vertices || [];
      const pts = raw.map(latLon);
      if (!pts.length) return;
      raw.forEach(addPoint);
      L.polyline(pts, {{ color: '#f97316', weight: 4 }}).addTo(map).bindTooltip('Selected route');
      L.circleMarker(pts[0], {{ radius: 5, color: '#22c55e', fillOpacity: 1 }}).addTo(map).bindTooltip('Start');
      L.circleMarker(pts[pts.length - 1], {{ radius: 6, color: '#ef4444', fillOpacity: 1 }}).addTo(map).bindTooltip('Target');
    }}
    if (geometry.geometry_type === 'MultiArea') {{
      (geometry.areas || []).forEach((area, index) => drawArea(area, 'Search area ' + (index + 1)));
    }} else if (geometry.geometry_type === 'line') {{
      drawLine(geometry);
    }} else {{
      drawArea(geometry, missionType + ' geometry');
    }}
    metocPoints.forEach((point, index) => {{
      addPoint(point);
      L.circleMarker(latLon(point), {{ radius: 5, color: '#facc15', fillColor: '#facc15', fillOpacity: 1 }}).addTo(map).bindTooltip('METOC point ' + (index + 1));
    }});
    if (bounds.length) {{
      const center = bounds.reduce((acc, p) => [acc[0] + p[0], acc[1] + p[1]], [0, 0]).map(v => v / bounds.length);
      const length = Math.max(0.015, currentSpeed * 0.018);
      const rad = (90 - currentDir) * Math.PI / 180;
      const end = [center[0] + Math.sin(rad) * length, center[1] + Math.cos(rad) * length];
      L.polyline([center, end], {{ color: '#a855f7', weight: 3, dashArray: '6 4' }}).addTo(map).bindTooltip('Current vector');
      L.circleMarker(end, {{ radius: 4, color: '#a855f7', fillOpacity: 1 }}).addTo(map);
      map.fitBounds(bounds, {{ padding: [32, 32], maxZoom: 13 }});
    }} else {{
      map.setView([13.45, 144.8], 10);
    }}
  </script>
</body>
</html>
"""
    srcdoc = html.escape(inner_html, quote=True)
    return f"""
<div class="report-visual-card report-map-card" data-uuv-render-token="{render_token}">
  <h3>Mission Map Overlay</h3>
  <iframe
    class="uuv-report-map-iframe"
    title="uuv-report-map-overlay"
    name="uuv-report-map-overlay-{render_token}"
    data-uuv-render-token="{render_token}"
    srcdoc="{srcdoc}"
    width="100%"
    height="410"
    style="border:none; border-radius:10px; overflow:hidden; background:#0b1220;"
  ></iframe>
</div>
"""
