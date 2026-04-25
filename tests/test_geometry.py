"""Basic geometry regression tests."""

from __future__ import annotations

import json
import math
import unittest

from core.geometry import parse_geometry_json
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


if __name__ == "__main__":
    unittest.main()

