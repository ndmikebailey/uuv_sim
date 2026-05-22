"""Speed-aware planning power model tests."""

from __future__ import annotations

import unittest

from core.energy import estimate_power_at_speed_kw
from core.power import power_model_breakdown, speed_adjusted_power_kw
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


if __name__ == "__main__":
    unittest.main()
