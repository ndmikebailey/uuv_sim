"""Basic environmental uplift regression tests."""

from __future__ import annotations

import unittest

from core.environment import environmental_uplift_factor, salinity_buoyancy_penalty, temperature_energy_penalty


class EnvironmentUpliftTests(unittest.TestCase):
    """Environmental uplift calculation examples."""

    def test_temperature_penalty_matches_existing_logic(self) -> None:
        """Cold and hot water penalties remain consistent with the monolith."""
        self.assertAlmostEqual(temperature_energy_penalty(10.0), 0.05)
        self.assertAlmostEqual(temperature_energy_penalty(25.0), 0.0)
        self.assertAlmostEqual(temperature_energy_penalty(35.0), 0.015)

    def test_environmental_uplift_combines_penalties(self) -> None:
        """Combined uplift is multiplicative factor 1 plus penalties."""
        self.assertAlmostEqual(environmental_uplift_factor(10.0, current_penalty=0.02), 1.07)
        self.assertAlmostEqual(environmental_uplift_factor(10.0, current_penalty=0.02, salinity_penalty=0.015), 1.085)

    def test_salinity_penalty_is_bounded_and_missing_safe(self) -> None:
        """Salinity uplift should be zero when missing and bounded for extreme values."""
        self.assertEqual(salinity_buoyancy_penalty(None), 0.0)
        self.assertEqual(salinity_buoyancy_penalty(35.0), 0.0)
        self.assertAlmostEqual(salinity_buoyancy_penalty(33.0), 0.01)
        self.assertAlmostEqual(salinity_buoyancy_penalty(37.0), 0.01)
        self.assertAlmostEqual(salinity_buoyancy_penalty(0.0), 0.10)


if __name__ == "__main__":
    unittest.main()
