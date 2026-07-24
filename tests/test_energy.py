"""Basic energy-model reproducibility tests."""

from __future__ import annotations

import unittest

import numpy as np

from core.energy import (
    compute_energy_recommendation_metrics,
    run_energy_simulation,
    sample_bounded_current_speeds,
    sample_mission_sensor_power_kw,
)
from core.geometry import manual_rectangle_area
from models.environment_model import EnvironmentData
from models.vehicle_model import VEHICLE_CATALOG


class EnergyReproducibilityTests(unittest.TestCase):
    """Monte Carlo seed behavior examples."""

    def test_energy_recommendation_metrics_use_mean_plus_sample_std(self) -> None:
        """Recommendation metrics should be derived from the Monte Carlo distribution."""
        samples = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        metrics = compute_energy_recommendation_metrics(samples)

        self.assertAlmostEqual(float(metrics["expected_energy_kwh"]), float(np.mean(samples)))
        self.assertAlmostEqual(float(metrics["energy_uncertainty_allowance_kwh"]), float(np.std(samples, ddof=1)))
        self.assertAlmostEqual(
            float(metrics["distribution_recommended_energy_kwh"]),
            float(np.mean(samples) + np.std(samples, ddof=1)),
        )
        self.assertAlmostEqual(
            float(metrics["recommended_planning_energy_kwh"]),
            float(metrics["distribution_recommended_energy_kwh"]),
        )

    def test_energy_recommendation_metrics_average_upper_tail(self) -> None:
        """The stress estimate should average the highest ceil(10% * n) samples."""
        samples = np.arange(1.0, 12.0)
        metrics = compute_energy_recommendation_metrics(samples)

        self.assertEqual(metrics["upper_tail_fraction"], 0.10)
        self.assertAlmostEqual(float(metrics["conservative_stress_energy_kwh"]), 10.5)

    def test_energy_recommendation_metrics_use_validation_adjustment_when_higher(self) -> None:
        """A provided validation adjustment should only raise the final recommendation."""
        samples = np.array([1.0, 2.0, 3.0])
        metrics = compute_energy_recommendation_metrics(samples, validation_adjusted_energy_kwh=10.0)

        self.assertAlmostEqual(float(metrics["validation_adjusted_energy_kwh"]), 10.0)
        self.assertAlmostEqual(float(metrics["recommended_planning_energy_kwh"]), 10.0)

    def test_mission_sensor_power_ranges(self) -> None:
        """Mission sensor-mode sampling should stay inside the public-data calibration ranges."""
        cases = [
            ("Route / Transit", 0.0, 0.025),
            ("Payload Delivery", 0.0, 0.025),
            ("ISR", 0.050, 0.075),
            ("Area Search / MCM", 0.075, 0.150),
        ]
        for mission_type, lower, upper in cases:
            rng = np.random.default_rng(123)
            samples = [sample_mission_sensor_power_kw(mission_type, rng) for _ in range(500)]
            self.assertGreaterEqual(min(samples), lower)
            self.assertLessEqual(max(samples), upper)

    def test_current_samples_are_bounded_around_entered_mean(self) -> None:
        """Current draws should remain inside the configured two-sigma bounds."""
        samples = sample_bounded_current_speeds(
            np.random.default_rng(12345),
            mean_kts=0.8,
            sigma_kts=0.2,
            size=10_000,
        )

        self.assertGreaterEqual(float(np.min(samples)), 0.4)
        self.assertLessEqual(float(np.max(samples)), 1.2)
        self.assertAlmostEqual(float(np.mean(samples)), 0.8, delta=0.01)

    def test_repeated_missions_receive_independent_current_events(self) -> None:
        """Each route/search sequence should receive a separate current draw."""
        result = run_energy_simulation(
            vehicle=VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"],
            mission_type="Route / Transit",
            area=manual_rectangle_area(3.0, 3.0, 9.0),
            environment=EnvironmentData(
                current_speed_kts_mean=0.8,
                current_direction_deg_mean=90.0,
                sea_surface_temp_c_mean=25.0,
            ),
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=True,
            speed_kts=3.5,
            battery_sets_available=2,
            recharge_allowed=True,
            mission_sequences=3,
            rng_seed=12345,
            monte_carlo_runs=100,
        )

        self.assertEqual(result.summary["current_sampling_events_per_trial"], 3)
        self.assertEqual(result.summary["current_sampling_lower_bound_kts"], 0.4)
        self.assertAlmostEqual(float(result.summary["current_sampling_upper_bound_kts"]), 1.2)
        self.assertGreater(
            float(result.summary["current_sampling_p90_kts"]),
            float(result.summary["current_sampling_p10_kts"]),
        )

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
        self.assertListEqual(first.mission_sensor_power_samples_kw.tolist(), second.mission_sensor_power_samples_kw.tolist())
        self.assertListEqual(first.total_active_power_samples_kw.tolist(), second.total_active_power_samples_kw.tolist())
        self.assertEqual(len(first.power_samples_kw), 12)
        self.assertEqual(len(first.mission_sensor_power_samples_kw), 12)
        self.assertEqual(first.summary["recommended_track_orientation"], "N/A")
        self.assertGreater(float(first.summary["isr_loop_distance_km"]), 0.0)
        self.assertGreater(float(first.summary["isr_max_time_on_station_hr"]), 0.0)
        for key in (
            "expected_energy_kwh",
            "energy_uncertainty_allowance_kwh",
            "distribution_recommended_energy_kwh",
            "recommended_planning_energy_kwh",
            "conservative_stress_energy_kwh",
            "p50_energy_kwh",
            "p80_energy_kwh",
            "p95_energy_kwh",
            "planning_energy_kwh",
        ):
            self.assertIn(key, first.summary)
        self.assertAlmostEqual(
            float(first.summary["planning_energy_kwh"]),
            float(first.summary["recommended_planning_energy_kwh"]),
        )
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

    def test_zero_and_small_current_remain_small(self) -> None:
        """Zero current should not be inflated by sampling, and 0.1 kt should stay small."""
        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        area = manual_rectangle_area(3.0, 3.0, 9.0)
        zero_current = run_energy_simulation(
            vehicle=vehicle,
            mission_type="ISR",
            area=area,
            environment=EnvironmentData(current_speed_kts_mean=0.0, current_direction_deg_mean=90.0, sea_surface_temp_c_mean=25.0),
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=True,
            speed_kts=3.5,
            battery_sets_available=1,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=200,
            monte_carlo_runs=12,
        )
        small_current = run_energy_simulation(
            vehicle=vehicle,
            mission_type="ISR",
            area=area,
            environment=EnvironmentData(current_speed_kts_mean=0.1, current_direction_deg_mean=90.0, sea_surface_temp_c_mean=25.0),
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=True,
            speed_kts=3.5,
            battery_sets_available=1,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=200,
            monte_carlo_runs=12,
        )
        self.assertEqual(zero_current.summary["current_uplift_pct"], 0.0)
        self.assertAlmostEqual(float(zero_current.summary["isr_environmental_multiplier"]), 1.0)
        self.assertLess(float(small_current.summary["current_uplift_pct"]), 0.5)

    def test_mission_sensor_power_increases_search_energy(self) -> None:
        """Search/MCM energy should increase when segment-based sensor power is enabled."""
        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        area = manual_rectangle_area(3.0, 3.0, 9.0)
        common = {
            "vehicle": vehicle,
            "mission_type": "Area Search / MCM",
            "area": area,
            "environment": EnvironmentData(current_speed_kts_mean=0.0, current_direction_deg_mean=90.0, sea_surface_temp_c_mean=25.0),
            "additional_transit_km": 3.0,
            "track_spacing_m": 200.0,
            "return_to_start": True,
            "speed_kts": 3.5,
            "battery_sets_available": 3,
            "recharge_allowed": True,
            "mission_sequences": 1,
            "rng_seed": 54321,
            "monte_carlo_runs": 24,
        }
        baseline = run_energy_simulation(mission_sensor_power_enabled=False, **common)
        with_sensor = run_energy_simulation(mission_sensor_power_enabled=True, **common)

        self.assertTrue(np.all(with_sensor.mission_sensor_power_samples_kw >= 0.075))
        self.assertTrue(np.all(with_sensor.mission_sensor_power_samples_kw <= 0.150))
        self.assertGreater(float(with_sensor.summary["p50_energy_kwh"]), float(baseline.summary["p50_energy_kwh"]))
        self.assertGreater(float(with_sensor.summary["mission_sensor_energy_mean_kwh"]), 0.0)
        self.assertIn("Hotel power component", [row[0] for row in with_sensor.result_rows])
        self.assertIn("Propulsion power component", [row[0] for row in with_sensor.result_rows])
        self.assertIn("Sensor load", [row[0] for row in with_sensor.result_rows])

    def test_search_transit_uses_low_sensor_range_not_mcm_range(self) -> None:
        """Additional Search/MCM transit should not carry the full active survey sensor range."""
        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        result = run_energy_simulation(
            vehicle=vehicle,
            mission_type="Area Search / MCM",
            area=manual_rectangle_area(3.0, 3.0, 9.0),
            environment=EnvironmentData(current_speed_kts_mean=0.0, current_direction_deg_mean=90.0, sea_surface_temp_c_mean=25.0),
            additional_transit_km=5.0,
            track_spacing_m=200.0,
            return_to_start=True,
            speed_kts=3.5,
            battery_sets_available=3,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=24680,
            monte_carlo_runs=24,
        )

        self.assertTrue(np.all(result.transit_sensor_power_samples_kw >= 0.0))
        self.assertTrue(np.all(result.transit_sensor_power_samples_kw <= 0.025))
        self.assertLess(float(np.max(result.transit_sensor_power_samples_kw)), float(np.min(result.mission_sensor_power_samples_kw)))


if __name__ == "__main__":
    unittest.main()
