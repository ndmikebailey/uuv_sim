"""Mission orchestration and METOC lookup tests."""

from __future__ import annotations

import json
import unittest

from core.geometry import parse_geometry_json
from core.mission import choose_environment_lookup_point


LINE_GEOMETRY = {
    "geometry_type": "line",
    "route_points": [
        {"lat": 13.44, "lon": 144.79},
        {"lat": 13.46, "lon": 144.82},
    ],
}

POLYGON_GEOMETRY = {
    "geometry_type": "polygon",
    "bounds": {"north": 13.47, "south": 13.44, "east": 144.83, "west": 144.785},
    "vertices": [
        {"lat": 13.44, "lon": 144.79},
        {"lat": 13.44, "lon": 144.83},
        {"lat": 13.47, "lon": 144.82},
        {"lat": 13.465, "lon": 144.785},
    ],
}


class MissionLookupTests(unittest.TestCase):
    """Mission-specific environmental lookup behavior."""

    def test_isr_uses_first_boundary_point_for_lookup(self) -> None:
        """ISR should avoid defaulting to polygon centroid."""
        area = parse_geometry_json(json.dumps(POLYGON_GEOMETRY))
        self.assertEqual(choose_environment_lookup_point("ISR", area), (13.44, 144.79))

    def test_payload_uses_route_midpoint_for_lookup(self) -> None:
        """Payload delivery should use a route-representative point."""
        area = parse_geometry_json(json.dumps(LINE_GEOMETRY))
        self.assertEqual(choose_environment_lookup_point("Payload Delivery", area), (13.45, 144.805))

    def test_area_search_uses_centroid_for_lookup(self) -> None:
        """Area search remains centroid-driven."""
        area = parse_geometry_json(json.dumps(POLYGON_GEOMETRY))
        self.assertEqual(choose_environment_lookup_point("Area Search / MCM", area), (area.centroid_lat, area.centroid_lon))


if __name__ == "__main__":
    unittest.main()
