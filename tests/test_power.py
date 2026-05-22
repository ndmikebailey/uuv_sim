"""Speed-aware planning power model tests."""

from __future__ import annotations

import unittest

import numpy as np

from core.energy import estimate_power_at_speed_kw
from core.power import power_model_breakdown, sample_power_model_breakdown, speed_adjusted_power_kw
from models.vehicle_model import VEHICLE_CATALOG


class SpeedAwarePowerModelTests(unittest.TestCase):
    """Checks for hotel-load floor, cubic propulsion scaling, and low-speed bounds."""

    def test_nominal_speed_matches_catalog_average_power(self) -> None:
        """Nominal speed should preserve the public catalog battery/endurance anchor."""
        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        self.assertAlmostEqual(
            speed_adjusted_power_kw(vehicle, vehicle.nominal_speed_kts),
            vehicle.average_power_kw,
            places=6,
        )

    def test_above_nominal_speed_increases_power(self) -> None:
        """Higher speed should raise the propulsion component above the nominal anchor."""
        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        self.assertGreater(speed_adjusted_power_kw(vehicle, 4.0), speed_adjusted_power_kw(vehicle, 3.0))

    def test_below_nominal_speed_is_bounded_by_hotel_logic(self) -> None:
        """Slow-speed power may fall, but not below the fixed hotel-load floor."""
        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        breakdown = power_model_breakdown(vehicle, 2.0)
        self.assertGreaterEqual(breakdown.total_power_kw, breakdown.hotel_power_kw)
        self.assertLessEqual(breakdown.total_power_kw, breakdown.nominal_power_kw * 1.10)

    def test_existing_energy_helper_uses_speed_model_with_payload_multiplier(self) -> None:
        """The v3.5 helper should retain payload propulsion scaling while using the power model."""
        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        base = estimate_power_at_speed_kw(vehicle, 3.0)
        burdened = estimate_power_at_speed_kw(vehicle, 3.0, propulsion_multiplier=1.05)
        self.assertGreater(burdened, base)

    def test_sampled_power_is_reproducible_with_fixed_seed(self) -> None:
        """A fixed RNG seed should reproduce sampled power parameters."""
        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        first = sample_power_model_breakdown(vehicle, 3.0, np.random.default_rng(123))
        second = sample_power_model_breakdown(vehicle, 3.0, np.random.default_rng(123))
        self.assertEqual(first, second)

    def test_sampled_p50_is_near_deterministic_nominal_power(self) -> None:
        """At nominal speed the sampled planning band should center near catalog power."""
        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        rng = np.random.default_rng(10)
        samples = [sample_power_model_breakdown(vehicle, 3.0, rng).total_power_kw for _ in range(2000)]
        self.assertAlmostEqual(float(np.percentile(samples, 50)), vehicle.average_power_kw, delta=vehicle.average_power_kw * 0.12)

    def test_above_nominal_sampled_p50_exceeds_nominal_sampled_p50(self) -> None:
        """Sampled power band should still preserve the speed-power relationship."""
        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        nominal_rng = np.random.default_rng(20)
        fast_rng = np.random.default_rng(20)
        nominal = [sample_power_model_breakdown(vehicle, 3.0, nominal_rng).total_power_kw for _ in range(1000)]
        fast = [sample_power_model_breakdown(vehicle, 4.0, fast_rng).total_power_kw for _ in range(1000)]
        self.assertGreater(float(np.percentile(fast, 50)), float(np.percentile(nominal, 50)))

    def test_sampled_below_nominal_power_remains_above_hotel_load(self) -> None:
        """Low-speed sampled power should keep the hotel-load floor."""
        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        rng = np.random.default_rng(30)
        for _ in range(100):
            breakdown = sample_power_model_breakdown(vehicle, 1.5, rng)
            self.assertGreaterEqual(breakdown.total_power_kw, breakdown.hotel_power_kw)

    def test_sampled_speed_exponent_is_clamped(self) -> None:
        """Sampled exponent should stay inside the configured planning bounds."""
        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        rng = np.random.default_rng(40)
        exponents = [sample_power_model_breakdown(vehicle, 3.0, rng).speed_exponent for _ in range(1000)]
        self.assertGreaterEqual(min(exponents), 2.4)
        self.assertLessEqual(max(exponents), 3.4)


if __name__ == "__main__":
    unittest.main()
