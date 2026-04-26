"""Leaflet iframe component for map geometry selection."""

from __future__ import annotations

import html

from utils.constants import REGION_PRESETS


def build_leaflet_iframe(region_name: str = "Guam") -> str:
    """Return a Leaflet iframe that emits raw geometry JSON to Gradio."""
    # TODO: Restore multi-area Search/MCM geometry support so users can draw multiple search boxes/polygons around coastlines. Aggregate total area and show all selected regions in the Results map.
    lat, lon, zoom = REGION_PRESETS.get(region_name, REGION_PRESETS["Guam"])
    inner_html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.css"/>
  <style>
    html, body {{ margin: 0; padding: 0; background: #0b1220; color: white; font-family: Arial, sans-serif; }}
    #map {{ width: 100%; height: 560px; }}
    #output {{ padding: 12px; background: #111827; min-height: 96px; font-size: 14px; }}
    #raw_output {{ display: none; }}
    .note {{ padding: 8px 10px; background: #1f2937; font-size: 12px; }}
    .snap-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
    .snap-card {{ border: 1px solid #374151; border-radius: 10px; padding: 10px; background: #0f172a; }}
    .snap-label {{ color: #9ca3af; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }}
    .snap-value {{ color: #ffffff; font-size: 20px; font-weight: 800; margin-top: 3px; }}
    .snap-sub {{ color: #cbd5e1; font-size: 12px; margin-top: 6px; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="note">Draw a line, rectangle, or polygon for ISR; draw a rectangle or polygon for Area Search / MCM; draw a line for Payload Delivery.</div>
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
      const label = summary.geometry_type === 'polygon' ? 'Polygon' : 'Rectangle';
      const areaText = summary.area_km2 ? summary.area_km2 + ' sq km' : summary.vertices.length + ' pts';
      const detailText = summary.width_km && summary.height_km ? 'Bounding box: ' + summary.width_km + ' x ' + summary.height_km + ' km' : 'Backend computes area on mission load.';
      return '<div class="snap-grid"><div class="snap-card"><div class="snap-label">Selected Geometry</div><div class="snap-value">' + label + '</div><div class="snap-sub">' + label + ' captured.</div></div><div class="snap-card"><div class="snap-label">Area / Shape</div><div class="snap-value">' + areaText + '</div><div class="snap-sub">' + detailText + '</div></div><div class="snap-card"><div class="snap-label">Geometry center</div><div class="snap-value">' + summary.centroid_lat + ', ' + summary.centroid_lon + '</div><div class="snap-sub">Backend recomputes on mission load.</div></div></div>';
    }}
    function sendGeometry(summary) {{
      document.getElementById("raw_output").textContent = JSON.stringify(summary, null, 2);
      document.getElementById("output").innerHTML = snapshotHtml(summary);
      window.parent.postMessage({{ type: "uuv_geometry", payload: summary }}, "*");
    }}
    function summarizeLayer(layer) {{
      if (layer instanceof L.Rectangle) sendGeometry(rectangleSummary(layer));
      else if (layer instanceof L.Polygon) sendGeometry(polygonSummary(layer));
      else if (layer instanceof L.Polyline) sendGeometry(lineSummary(layer));
      else sendGeometry({{ error: "Unsupported geometry type." }});
    }}
    map.on(L.Draw.Event.CREATED, function(event) {{
      drawnItems.clearLayers();
      drawnItems.addLayer(event.layer);
      summarizeLayer(event.layer);
    }});
    map.on(L.Draw.Event.EDITED, function(event) {{
      event.layers.eachLayer(function(layer) {{ summarizeLayer(layer); }});
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
  title="uuv-mission-map"
  srcdoc="{srcdoc}"
  width="100%"
  height="700"
  style="border:none; border-radius:12px; overflow:hidden; background:#0b1220;"
></iframe>
"""
