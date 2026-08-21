"""Model reasonableness checks for the v1 release."""

from __future__ import annotations

from dataclasses import replace
import unittest

from core.assumptions import MODEL_ASSUMPTIONS, assumptions_as_rows
from core.energy import (
    compute_stockpile_requirement,
    estimate_power_at_speed_kw,
    payload_weight_energy_multiplier,
    run_energy_simulation,
)
from core.geometry import manual_payload_route, manual_rectangle_area
from models.environment_model import EnvironmentData
from models.vehicle_model import VEHICLE_CATALOG


class ModelReasonablenessTests(unittest.TestCase):
    """Check directional behavior of mission and stockpile calculations."""

    def setUp(self) -> None:
        self.vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        self.environment = EnvironmentData(
            current_speed_kts_mean=0.0,
            current_direction_deg_mean=0.0,
            sea_surface_temp_c_mean=25.0,
        )

    def _run_payload(self, *, speed_kts: float, return_to_start: bool) -> float:
        result = run_energy_simulation(
            vehicle=self.vehicle,
            mission_type="Payload Delivery",
            area=manual_payload_route(20.0, 90.0),
            environment=self.environment,
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=return_to_start,
            speed_kts=speed_kts,
            battery_sets_available=10,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=42,
            monte_carlo_runs=8,
        )
        return float(result.summary["p50_energy_kwh"])

    def _payload_result(self):
        return run_energy_simulation(
            vehicle=self.vehicle,
            mission_type="Payload Delivery",
            area=manual_payload_route(20.0, 90.0),
            environment=self.environment,
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=True,
            speed_kts=3.0,
            battery_sets_available=10,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=45,
            monte_carlo_runs=8,
        )

    def _run_search(self, *, area_km2: float, track_spacing_m: float) -> float:
        side_km = area_km2 ** 0.5
        result = run_energy_simulation(
            vehicle=self.vehicle,
            mission_type="Area Search / MCM",
            area=manual_rectangle_area(side_km, side_km, area_km2),
            environment=self.environment,
            additional_transit_km=0.0,
            track_spacing_m=track_spacing_m,
            return_to_start=False,
            speed_kts=3.0,
            battery_sets_available=10,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=43,
            monte_carlo_runs=8,
        )
        return float(result.summary["p50_energy_kwh"])

    def _search_result(self):
        return run_energy_simulation(
            vehicle=self.vehicle,
            mission_type="Area Search / MCM",
            area=manual_rectangle_area(3.0, 3.0, 9.0),
            environment=self.environment,
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=False,
            speed_kts=3.0,
            battery_sets_available=10,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=46,
            monte_carlo_runs=8,
        )

    def test_higher_speed_increases_energy_for_fixed_payload_route(self) -> None:
        slow_energy = self._run_payload(speed_kts=2.5, return_to_start=False)
        fast_energy = self._run_payload(speed_kts=4.0, return_to_start=False)
        self.assertGreater(fast_energy, slow_energy)

    def test_return_to_start_increases_payload_energy(self) -> None:
        one_way_energy = self._run_payload(speed_kts=3.0, return_to_start=False)
        return_energy = self._run_payload(speed_kts=3.0, return_to_start=True)
        self.assertGreater(return_energy, one_way_energy)

    def test_larger_search_area_increases_energy(self) -> None:
        small_area_energy = self._run_search(area_km2=4.0, track_spacing_m=200.0)
        large_area_energy = self._run_search(area_km2=16.0, track_spacing_m=200.0)
        self.assertGreater(large_area_energy, small_area_energy)

    def test_smaller_track_spacing_increases_search_energy(self) -> None:
        wide_spacing_energy = self._run_search(area_km2=9.0, track_spacing_m=300.0)
        tight_spacing_energy = self._run_search(area_km2=9.0, track_spacing_m=100.0)
        self.assertGreater(tight_spacing_energy, wide_spacing_energy)

    def test_isr_loop_distance_affects_loop_time_and_completed_loops(self) -> None:
        small_area = manual_rectangle_area(2.0, 2.0, 4.0)
        large_area = manual_rectangle_area(4.0, 4.0, 16.0)
        common_kwargs = {
            "vehicle": self.vehicle,
            "mission_type": "ISR",
            "environment": self.environment,
            "additional_transit_km": 0.0,
            "track_spacing_m": 200.0,
            "return_to_start": False,
            "speed_kts": 3.0,
            "battery_sets_available": 10,
            "recharge_allowed": True,
            "mission_sequences": 1,
            "rng_seed": 44,
            "monte_carlo_runs": 8,
        }
        small = run_energy_simulation(area=small_area, **common_kwargs)
        large = run_energy_simulation(area=large_area, **common_kwargs)

        self.assertGreater(float(large.summary["isr_loop_time_hr"]), float(small.summary["isr_loop_time_hr"]))
        self.assertLess(int(large.summary["isr_completed_loops"]), int(small.summary["isr_completed_loops"]))

    def test_stockpile_helper_scales_with_tempo_and_horizon(self) -> None:
        baseline = compute_stockpile_requirement(
            conservative_energy_kwh=2.0,
            usable_battery_per_set_kwh=1.0,
            missions_per_week=2.0,
            planning_horizon_days=7.0,
        )
        higher_tempo = compute_stockpile_requirement(
            conservative_energy_kwh=2.0,
            usable_battery_per_set_kwh=1.0,
            missions_per_week=4.0,
            planning_horizon_days=7.0,
        )
        longer_horizon = compute_stockpile_requirement(
            conservative_energy_kwh=2.0,
            usable_battery_per_set_kwh=1.0,
            missions_per_week=2.0,
            planning_horizon_days=14.0,
        )

        self.assertGreater(higher_tempo["total_mission_energy_kwh"], baseline["total_mission_energy_kwh"])
        self.assertGreater(higher_tempo["battery_sets_without_recharge"], baseline["battery_sets_without_recharge"])
        self.assertGreater(longer_horizon["total_mission_energy_kwh"], baseline["total_mission_energy_kwh"])
        self.assertGreater(longer_horizon["battery_sets_without_recharge"], baseline["battery_sets_without_recharge"])

    def test_assumptions_registry_exports_rows(self) -> None:
        self.assertIn("propulsion_speed_exponent", MODEL_ASSUMPTIONS)
        self.assertIn("default_usable_battery_fraction", MODEL_ASSUMPTIONS)
        self.assertIn("salinity_buoyancy_penalty_curve", MODEL_ASSUMPTIONS)
        self.assertIn("temperature_derating_curve_v1", MODEL_ASSUMPTIONS)
        self.assertIn("current_speed_sampling_model", MODEL_ASSUMPTIONS)
        self.assertIn("sustainment_projection_resampling", MODEL_ASSUMPTIONS)
        self.assertGreater(len(assumptions_as_rows()), 0)

    def test_missing_salinity_preserves_current_payload_energy(self) -> None:
        """Phase 2 should not change energy when no salinity is available."""
        no_salinity = run_energy_simulation(
            vehicle=self.vehicle,
            mission_type="Payload Delivery",
            area=manual_payload_route(20.0, 90.0),
            environment=self.environment,
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=False,
            speed_kts=3.0,
            battery_sets_available=10,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=48,
            monte_carlo_runs=8,
        )
        reference_salinity = run_energy_simulation(
            vehicle=self.vehicle,
            mission_type="Payload Delivery",
            area=manual_payload_route(20.0, 90.0),
            environment=EnvironmentData(
                current_speed_kts_mean=0.0,
                current_direction_deg_mean=0.0,
                sea_surface_temp_c_mean=25.0,
                sea_surface_salinity_psu=35.0,
            ),
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=False,
            speed_kts=3.0,
            battery_sets_available=10,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=48,
            monte_carlo_runs=8,
        )

        self.assertEqual(no_salinity.summary["salinity_uplift_pct"], 0.0)
        self.assertEqual(reference_salinity.summary["salinity_uplift_pct"], 0.0)
        self.assertEqual(no_salinity.energy_samples_kwh.tolist(), reference_salinity.energy_samples_kwh.tolist())

    def test_salinity_deviation_increases_payload_energy(self) -> None:
        """Salinity penalty should increase mission energy when salinity deviates from reference."""
        baseline = self._run_payload(speed_kts=3.0, return_to_start=False)
        salty_environment = EnvironmentData(
            current_speed_kts_mean=0.0,
            current_direction_deg_mean=0.0,
            sea_surface_temp_c_mean=25.0,
            sea_surface_salinity_psu=39.0,
        )
        result = run_energy_simulation(
            vehicle=self.vehicle,
            mission_type="Payload Delivery",
            area=manual_payload_route(20.0, 90.0),
            environment=salty_environment,
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=False,
            speed_kts=3.0,
            battery_sets_available=10,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=42,
            monte_carlo_runs=8,
        )

        self.assertAlmostEqual(float(result.summary["salinity_uplift_pct"]), 2.0)
        self.assertGreater(float(result.summary["p50_energy_kwh"]), baseline)

    def test_payload_weight_increases_payload_energy(self) -> None:
        """Payload mass penalty should affect Payload Delivery energy modestly."""
        baseline = run_energy_simulation(
            vehicle=self.vehicle,
            mission_type="Payload Delivery",
            area=manual_payload_route(20.0, 90.0),
            environment=self.environment,
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=True,
            speed_kts=3.0,
            battery_sets_available=10,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=50,
            monte_carlo_runs=8,
            payload_weight_kg=0.0,
        )
        weighted = run_energy_simulation(
            vehicle=self.vehicle,
            mission_type="Payload Delivery",
            area=manual_payload_route(20.0, 90.0),
            environment=self.environment,
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=True,
            speed_kts=3.0,
            battery_sets_available=10,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=50,
            monte_carlo_runs=8,
            payload_weight_kg=50.0,
        )

        self.assertGreater(float(weighted.summary["p50_energy_kwh"]), float(baseline.summary["p50_energy_kwh"]))
        self.assertLess(
            float(weighted.summary["p50_energy_kwh"]) / float(baseline.summary["p50_energy_kwh"]),
            1.05,
        )
        self.assertEqual(float(baseline.summary["payload_weight_multiplier"]), 1.0)
        self.assertGreater(float(weighted.summary["payload_weight_multiplier"]), 1.0)
        self.assertEqual(str(weighted.summary["payload_weight_penalty_basis"]), "energy_class_scaled")
        self.assertNotIn("dry", str(weighted.summary).lower())

    def test_payload_weight_energy_multiplier_is_bounded(self) -> None:
        """Payload penalty should scale by energy class and cap at the configured bound."""
        self.assertEqual(payload_weight_energy_multiplier(0.0, 3.0), 1.0)
        self.assertEqual(payload_weight_energy_multiplier(10.0, 0.0), 1.0)
        self.assertAlmostEqual(payload_weight_energy_multiplier(10.0, 3.0), 1.01)
        self.assertAlmostEqual(payload_weight_energy_multiplier(10.0, 0.8), 1.0375)
        self.assertAlmostEqual(payload_weight_energy_multiplier(1000.0, 3.0), 1.05)

    def test_one_way_payload_mode_uses_outbound_distance_only(self) -> None:
        """Return-to-start should model greater distance than one-way payload mode."""
        common = {
            "vehicle": self.vehicle,
            "mission_type": "Payload Delivery",
            "area": manual_payload_route(20.0, 90.0),
            "environment": self.environment,
            "additional_transit_km": 2.0,
            "track_spacing_m": 200.0,
            "speed_kts": 3.0,
            "battery_sets_available": 10,
            "recharge_allowed": True,
            "mission_sequences": 1,
            "rng_seed": 52,
            "monte_carlo_runs": 8,
        }
        one_way = run_energy_simulation(return_to_start=False, **common)
        return_trip = run_energy_simulation(return_to_start=True, **common)
        self.assertEqual(one_way.summary["payload_recovery_mode"], "one_way")
        self.assertEqual(float(one_way.summary["payload_total_modeled_distance_km"]), 22.0)
        self.assertEqual(float(return_trip.summary["payload_total_modeled_distance_km"]), 42.0)
        self.assertGreater(float(return_trip.summary["p50_energy_kwh"]), float(one_way.summary["p50_energy_kwh"]))

    def test_non_rechargeable_payload_uses_clean_one_way_logic(self) -> None:
        """Non-rechargeable one-way catalog entries should not get recovery overhead."""
        result = run_energy_simulation(
            vehicle=replace(
                self.vehicle,
                name="Synthetic one-way test vehicle",
                recharge_hr=0.0,
                recoverable=False,
                rechargeable=False,
                default_payload_recovery_mode="one_way",
                usable_fraction=1.0,
            ),
            mission_type="Payload Delivery",
            area=manual_payload_route(10.0, 90.0),
            environment=self.environment,
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=True,
            speed_kts=4.0,
            battery_sets_available=1,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=53,
            monte_carlo_runs=8,
        )
        self.assertEqual(result.summary["payload_recovery_mode"], "one_way")
        self.assertFalse(result.summary["vehicle_rechargeable"])
        self.assertEqual(float(result.summary["launch_recovery_energy_kwh"]), 0.0)
        self.assertIn("one-way/non-rechargeable", str(result.summary["payload_one_way_catalog_note"]))

    def test_recoverable_payload_adds_launch_recovery_overhead(self) -> None:
        """Recoverable payload missions should include a small launch/recovery overhead."""
        result = run_energy_simulation(
            vehicle=self.vehicle,
            mission_type="Payload Delivery",
            area=manual_payload_route(10.0, 90.0),
            environment=self.environment,
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=False,
            speed_kts=3.0,
            battery_sets_available=10,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=54,
            monte_carlo_runs=8,
        )
        self.assertGreater(float(result.summary["launch_recovery_energy_kwh"]), 0.0)
        self.assertGreater(float(result.summary["launch_recovery_overhead_hr"]), 0.0)

    def test_vehicle_specific_hotel_fraction_overrides_default(self) -> None:
        """Catalog hotel fraction should affect speed-power when present and fall back otherwise."""
        default_vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        high_hotel_vehicle = replace(
            default_vehicle,
            name="Synthetic high-hotel test vehicle",
            hotel_fraction=0.45,
        )
        default_power = estimate_power_at_speed_kw(default_vehicle, 4.0)
        explicit_default_power = estimate_power_at_speed_kw(default_vehicle, 4.0, hotel_fraction=0.40)
        self.assertAlmostEqual(default_power, explicit_default_power)
        catalog_power = estimate_power_at_speed_kw(high_hotel_vehicle, 4.0)
        forced_default_power = estimate_power_at_speed_kw(high_hotel_vehicle, 4.0, hotel_fraction=0.35)
        self.assertNotEqual(catalog_power, forced_default_power)

    def test_payload_weight_does_not_change_search_or_isr_energy(self) -> None:
        """Payload mass burden should not leak into ISR or Search/MCM."""
        search_common = {
            "vehicle": self.vehicle,
            "mission_type": "Area Search / MCM",
            "area": manual_rectangle_area(3.0, 3.0, 9.0),
            "environment": self.environment,
            "additional_transit_km": 0.0,
            "track_spacing_m": 200.0,
            "return_to_start": False,
            "speed_kts": 3.0,
            "battery_sets_available": 10,
            "recharge_allowed": True,
            "mission_sequences": 1,
            "rng_seed": 51,
            "monte_carlo_runs": 8,
        }
        search_a = run_energy_simulation(payload_weight_kg=0.0, **search_common)
        search_b = run_energy_simulation(payload_weight_kg=100.0, **search_common)
        self.assertEqual(search_a.energy_samples_kwh.tolist(), search_b.energy_samples_kwh.tolist())

        isr_common = {**search_common, "mission_type": "ISR"}
        isr_a = run_energy_simulation(payload_weight_kg=0.0, **isr_common)
        isr_b = run_energy_simulation(payload_weight_kg=100.0, **isr_common)
        self.assertEqual(isr_a.energy_samples_kwh.tolist(), isr_b.energy_samples_kwh.tolist())

    def test_summary_includes_battery_and_temperature_fields(self) -> None:
        """Monte Carlo summary should expose battery fraction and temperature derating fields."""
        result = run_energy_simulation(
            vehicle=self.vehicle,
            mission_type="Payload Delivery",
            area=manual_payload_route(20.0, 90.0),
            environment=EnvironmentData(current_speed_kts_mean=0.0, current_direction_deg_mean=0.0, sea_surface_temp_c_mean=-5.0),
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=False,
            speed_kts=3.0,
            battery_sets_available=2,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=49,
            monte_carlo_runs=8,
            battery_condition="low",
        )
        summary = result.summary
        self.assertEqual(summary["battery_condition_assumption"], "low")
        self.assertIn("battery_usable_fraction_p10", summary)
        self.assertIn("battery_usable_fraction_p50", summary)
        self.assertIn("battery_usable_fraction_p90", summary)
        self.assertGreater(float(summary["temperature_derating_pct"]), 0.0)
        self.assertEqual(summary["temperature_derating_basis"], "lithium_temperature_capacity_derating_v1")

    def test_planning_basis_fields_are_mode_specific(self) -> None:
        payload = self._payload_result().summary
        search = self._search_result().summary
        isr = run_energy_simulation(
            vehicle=self.vehicle,
            mission_type="ISR",
            area=manual_rectangle_area(3.0, 3.0, 9.0),
            environment=self.environment,
            additional_transit_km=0.0,
            track_spacing_m=200.0,
            return_to_start=False,
            speed_kts=3.0,
            battery_sets_available=10,
            recharge_allowed=True,
            mission_sequences=1,
            rng_seed=47,
            monte_carlo_runs=8,
        ).summary

        self.assertEqual(payload["planning_energy_basis"], "mission_total")
        self.assertEqual(search["planning_energy_basis"], "mission_total")
        self.assertEqual(isr["planning_energy_basis"], "mission_total")
        self.assertEqual(isr["planning_duration_basis"], "endurance_window")
        self.assertEqual(isr["planning_energy_kwh"], isr["recommended_planning_energy_kwh"])
        self.assertEqual(isr["single_set_endurance_hr"], isr["isr_single_set_endurance_hr"])
        self.assertEqual(isr["total_inventory_endurance_hr"], isr["isr_total_inventory_endurance_hr"])


if __name__ == "__main__":
    unittest.main()
