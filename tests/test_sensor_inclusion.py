"""Catalog sensor-in-endurance behavior."""

from __future__ import annotations

import unittest

from core.energy import run_energy_simulation
from core.geometry import manual_rectangle_area
from models.environment_model import EnvironmentData
from models.vehicle_model import VEHICLE_CATALOG


class SensorInEnduranceTests(unittest.TestCase):
    def _run_search(self, vehicle_name: str):
        vehicle = VEHICLE_CATALOG[vehicle_name]
        return run_energy_simulation(
            vehicle=vehicle,
            mission_type="Area Search / MCM",
            area=manual_rectangle_area(1.0, 1.0, 1.0),
            environment=EnvironmentData(
                current_speed_kts_mean=0.0,
                current_direction_deg_mean=0.0,
                sea_surface_temp_c_mean=25.0,
                sea_surface_salinity_psu=35.0,
            ),
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=True,
            speed_kts=vehicle.nominal_speed_kts,
            battery_sets_available=1,
            recharge_allowed=False,
            mission_sequences=1,
            rng_seed=123,
            monte_carlo_runs=1,
            deterministic_mode=True,
        )

    def test_sensor_inclusive_endurance_suppresses_generic_search_load(self) -> None:
        result = self._run_search("New Generation REMUS 100 - 1.5 kWh")
        self.assertTrue(result.summary["mission_sensor_power_requested"])
        self.assertFalse(result.summary["mission_sensor_power_enabled"])
        self.assertTrue(result.summary["sensor_load_included_in_endurance"])
        self.assertAlmostEqual(float(result.summary["mission_sensor_power_mean_w"]), 0.0)

    def test_no_payload_endurance_keeps_generic_search_load(self) -> None:
        result = self._run_search("REMUS 620 - 1 battery / no payload")
        self.assertTrue(result.summary["mission_sensor_power_requested"])
        self.assertTrue(result.summary["mission_sensor_power_enabled"])
        self.assertFalse(result.summary["sensor_load_included_in_endurance"])
        self.assertAlmostEqual(float(result.summary["mission_sensor_power_mean_w"]), 112.5)


if __name__ == "__main__":
    unittest.main()
