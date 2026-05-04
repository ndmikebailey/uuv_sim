"""Sustainment projection helper tests."""

from __future__ import annotations

import unittest

from core.sustainment import compute_sustainment_projection


class SustainmentProjectionTests(unittest.TestCase):
    """Energy-flow projection behavior."""

    def test_more_operations_and_time_increase_total_energy(self) -> None:
        baseline = compute_sustainment_projection(5.0, 1.0, 1.0, 2.0, 2)
        higher_tempo = compute_sustainment_projection(5.0, 2.0, 1.0, 2.0, 2)
        longer = compute_sustainment_projection(5.0, 1.0, 4.0, 2.0, 2)
        self.assertGreater(higher_tempo["total_conservative_energy_kwh"], baseline["total_conservative_energy_kwh"])
        self.assertGreater(longer["total_conservative_energy_kwh"], baseline["total_conservative_energy_kwh"])

    def test_lower_generator_efficiency_increases_input_energy(self) -> None:
        high_eff = compute_sustainment_projection(5.0, 2.0, 2.0, 2.0, 2, generator_efficiency=0.9)
        low_eff = compute_sustainment_projection(5.0, 2.0, 2.0, 2.0, 2, generator_efficiency=0.6)
        self.assertGreater(low_eff["generator_input_energy_kwh"], high_eff["generator_input_energy_kwh"])

    def test_more_inventory_reduces_cycle_count(self) -> None:
        small_inventory = compute_sustainment_projection(5.0, 4.0, 2.0, 2.0, 1)
        large_inventory = compute_sustainment_projection(5.0, 4.0, 2.0, 2.0, 5)
        self.assertGreater(small_inventory["inventory_cycles_required"], large_inventory["inventory_cycles_required"])

    def test_invalid_inputs_are_safe(self) -> None:
        result = compute_sustainment_projection(-1.0, -2.0, -3.0, 0.0, 0, generator_efficiency=0.0)
        self.assertEqual(result["total_conservative_energy_kwh"], 0.0)
        self.assertEqual(result["generator_input_energy_kwh"], 0.0)

    def test_fuel_equivalent_uses_generator_input_energy(self) -> None:
        result = compute_sustainment_projection(5.0, 2.0, 1.0, 2.0, 2, generator_efficiency=0.5)
        self.assertEqual(result["generator_kwh_per_gallon"], 10.0)
        self.assertAlmostEqual(result["generator_input_energy_kwh"], 20.0)
        self.assertAlmostEqual(result["fuel_gallons_equivalent"], 2.0)
        self.assertEqual(result["fuel_type_label"], "JP-8/diesel tactical-generator planning factor")


if __name__ == "__main__":
    unittest.main()
