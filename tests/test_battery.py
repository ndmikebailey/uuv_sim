"""Battery sampling and temperature derating tests."""

from __future__ import annotations

import unittest

import numpy as np

from core.battery import (
    lithium_temperature_capacity_factor,
    sample_usable_battery_fraction,
    usable_battery_energy_kwh,
)


class BatteryModelTests(unittest.TestCase):
    """Battery condition, reserve, and temperature capacity behavior."""

    def test_condition_samples_are_ordered_and_bounded(self) -> None:
        """Low condition should tend lower than high and all samples remain valid."""
        low_rng = np.random.default_rng(10)
        high_rng = np.random.default_rng(10)
        low = [sample_usable_battery_fraction(low_rng, "low") for _ in range(1000)]
        high = [sample_usable_battery_fraction(high_rng, "high") for _ in range(1000)]
        self.assertLess(float(np.mean(low)), float(np.mean(high)))
        self.assertGreaterEqual(min(low + high), 0.50)
        self.assertLessEqual(max(low + high), 1.00)

    def test_deterministic_mode_returns_clamped_value(self) -> None:
        """Deterministic mode should not sample from the RNG."""
        rng = np.random.default_rng(1)
        self.assertEqual(sample_usable_battery_fraction(rng, deterministic_fraction=0.88, stochastic_enabled=False), 0.88)
        self.assertEqual(sample_usable_battery_fraction(rng, deterministic_fraction=1.2, stochastic_enabled=False), 1.0)

    def test_usable_energy_keeps_reserve_separate(self) -> None:
        """Reserve margin should reduce energy after usable fraction and temperature factor."""
        no_reserve = usable_battery_energy_kwh(10.0, 0.9, reserve_fraction=0.0)
        reserve = usable_battery_energy_kwh(10.0, 0.9, reserve_fraction=0.1)
        self.assertEqual(no_reserve, 9.0)
        self.assertEqual(reserve, 8.1)
        self.assertLess(reserve, no_reserve)

    def test_temperature_capacity_curve(self) -> None:
        """Cold water should reduce usable capacity monotonically."""
        self.assertEqual(lithium_temperature_capacity_factor(25.0), 1.0)
        self.assertEqual(lithium_temperature_capacity_factor(10.0), 1.0)
        self.assertEqual(lithium_temperature_capacity_factor(5.0), 0.96)
        self.assertLess(lithium_temperature_capacity_factor(-5.0), lithium_temperature_capacity_factor(5.0))
        self.assertLess(lithium_temperature_capacity_factor(-25.0), lithium_temperature_capacity_factor(-15.0))

    def test_temperature_derating_impacts_usable_energy(self) -> None:
        """Temperature factor should reduce capacity, not energy demand."""
        warm = usable_battery_energy_kwh(10.0, 0.9, reserve_fraction=0.0, temperature_capacity_factor=1.0)
        cold = usable_battery_energy_kwh(10.0, 0.9, reserve_fraction=0.0, temperature_capacity_factor=0.82)
        self.assertLess(cold, warm)


if __name__ == "__main__":
    unittest.main()
