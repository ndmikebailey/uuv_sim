"""Basic geometry regression tests."""

from __future__ import annotations

import json
import math
import unittest

from core.geometry import (
    clipped_search_lanes,
    isr_path_distance_per_loop_km,
    orientation_to_axis,
    parse_geometry_json,
)
from utils.constants import EARTH_RADIUS_KM


class GeometryTests(unittest.TestCase):
    """Geometry calculation examples."""

    def test_rectangle_area_is_about_one_square_km(self) -> None:
        """A one-kilometer-by-one-kilometer equatorial rectangle is about 1 sq km."""
        delta_deg = math.degrees(1.0 / EARTH_RADIUS_KM)
        area = parse_geometry_json(
            json.dumps(
                {
                    "geometry_type": "rectangle",
                    "bounds": {
                        "north": delta_deg,
                        "south": 0.0,
                        "east": delta_deg,
                        "west": 0.0,
                    },
                }
            )
        )
        self.assertAlmostEqual(area.area_km2 or 0.0, 1.0, places=2)
        self.assertAlmostEqual(area.centroid_lat, delta_deg / 2.0, places=8)
        self.assertAlmostEqual(area.centroid_lon, delta_deg / 2.0, places=8)

    def test_orientation_controls_lane_axis(self) -> None:
        """North-South lanes should be vertical and East-West lanes horizontal."""
        area = parse_geometry_json(
            json.dumps(
                {
                    "geometry_type": "rectangle",
                    "bounds": {"north": 0.02, "south": 0.0, "east": 0.02, "west": 0.0},
                }
            )
        )
        vertical = clipped_search_lanes(area, 500.0, "North-South")
        horizontal = clipped_search_lanes(area, 500.0, "East-West")
        self.assertEqual(orientation_to_axis("n/s"), "vertical")
        self.assertEqual(orientation_to_axis("e/w"), "horizontal")
        self.assertTrue(all(abs(x0 - x1) < 1e-9 for x0, _, x1, _ in vertical["segments"]))
        self.assertTrue(all(abs(y0 - y1) < 1e-9 for _, y0, _, y1 in horizontal["segments"]))

    def test_isr_line_loop_is_out_and_back(self) -> None:
        """ISR line patrol distance should double the one-way route."""
        line = parse_geometry_json(
            json.dumps(
                {
                    "geometry_type": "line",
                    "route_points": [
                        {"lat": 0.0, "lon": 0.0},
                        {"lat": 0.0, "lon": math.degrees(1.0 / EARTH_RADIUS_KM)},
                    ],
                }
            )
        )
        self.assertAlmostEqual(line.route_distance_km or 0.0, 1.0, places=2)
        self.assertAlmostEqual(isr_path_distance_per_loop_km(line), 2.0, places=2)


if __name__ == "__main__":
    unittest.main()
