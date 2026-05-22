"""Basic energy-model reproducibility tests."""

from __future__ import annotations

import unittest

import numpy as np

from core.energy import run_energy_simulation
from core.geometry import manual_rectangle_area
from models.environment_model import EnvironmentData
from models.vehicle_model import VEHICLE_CATALOG


class EnergyReproducibilityTests(unittest.TestCase):
    """Monte Carlo seed behavior examples."""

    def test_seed_replays_energy_samples(self) -> None:
        """The same seed should replay the same Monte Carlo samples."""
        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        area = manual_rectangle_area(3.0, 3.0, 9.0)
        environment = EnvironmentData(
            current_speed_kts_mean=0.5,
            current_direction_deg_mean=90.0,
            sea_surface_temp_c_mean=25.0,
        )
        first = run_energy_simulation(
            vehicle=vehicle,
            mission_type="ISR",
            area=area,
            environment=environment,
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=True,
            speed_kts=3.5,
            battery_sets_available=1,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=12345,
            monte_carlo_runs=12,
        )
        second = run_energy_simulation(
            vehicle=vehicle,
            mission_type="ISR",
            area=area,
            environment=environment,
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=True,
            speed_kts=3.5,
            battery_sets_available=1,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=12345,
            monte_carlo_runs=12,
        )
        self.assertEqual(first.summary["rng_seed"], 12345)
        self.assertListEqual(first.energy_samples_kwh.tolist(), second.energy_samples_kwh.tolist())
        self.assertListEqual(first.power_samples_kw.tolist(), second.power_samples_kw.tolist())
        self.assertEqual(len(first.power_samples_kw), 12)
        self.assertEqual(first.summary["recommended_track_orientation"], "N/A")
        self.assertGreater(float(first.summary["isr_loop_distance_km"]), 0.0)
        self.assertGreater(float(first.summary["isr_max_time_on_station_hr"]), 0.0)
        self.assertIn("Estimated ISR time on station", [row[0] for row in first.result_rows])

    def test_negative_seed_is_rejected(self) -> None:
        """Negative seeds should fail visibly instead of relying on NumPy errors."""
        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        area = manual_rectangle_area(3.0, 3.0, 9.0)
        with self.assertRaises(ValueError):
            run_energy_simulation(
                vehicle=vehicle,
                mission_type="ISR",
                area=area,
                environment=EnvironmentData(),
                additional_transit_km=0.0,
                track_spacing_m=200.0,
                return_to_start=True,
                speed_kts=3.5,
                battery_sets_available=1,
                recharge_allowed=True,
                mission_sequences=1,
                rng_seed=-1,
                monte_carlo_runs=4,
            )

    def test_different_seed_changes_power_samples(self) -> None:
        """Power-model sampling should respond to the Monte Carlo seed."""
        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        area = manual_rectangle_area(3.0, 3.0, 9.0)
        environment = EnvironmentData(
            current_speed_kts_mean=0.5,
            current_direction_deg_mean=90.0,
            sea_surface_temp_c_mean=25.0,
        )
        first = run_energy_simulation(
            vehicle=vehicle,
            mission_type="Area Search / MCM",
            area=area,
            environment=environment,
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=True,
            speed_kts=3.5,
            battery_sets_available=1,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=100,
            monte_carlo_runs=12,
        )
        second = run_energy_simulation(
            vehicle=vehicle,
            mission_type="Area Search / MCM",
            area=area,
            environment=environment,
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=True,
            speed_kts=3.5,
            battery_sets_available=1,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=101,
            monte_carlo_runs=12,
        )
        self.assertFalse(np.array_equal(first.power_samples_kw, second.power_samples_kw))
        self.assertEqual(len(first.power_samples_kw), 12)


if __name__ == "__main__":
    unittest.main()
