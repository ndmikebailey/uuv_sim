"""Model reasonableness checks for v3.2 baseline validation work."""

from __future__ import annotations

import unittest

from core.assumptions import MODEL_ASSUMPTIONS, assumptions_as_rows
from core.energy import compute_stockpile_requirement, run_energy_simulation
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
        self.assertGreater(len(assumptions_as_rows()), 0)

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
        self.assertEqual(isr["planning_energy_basis"], "patrol_loop")
        self.assertEqual(isr["planning_duration_basis"], "patrol_loop_time")
        self.assertEqual(isr["planning_energy_kwh"], isr["isr_loop_energy_kwh"])
        self.assertEqual(isr["single_set_endurance_hr"], isr["isr_single_set_endurance_hr"])
        self.assertEqual(isr["total_inventory_endurance_hr"], isr["isr_total_inventory_endurance_hr"])


if __name__ == "__main__":
    unittest.main()
