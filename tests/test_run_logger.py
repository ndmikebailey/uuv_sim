"""Run logger and energy-planner export tests."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from models.environment_model import EnvironmentData
from models.mission_model import LatLon, MissionArea
from models.vehicle_model import VEHICLE_CATALOG
from services.run_logger import ENERGY_PLANNER_CSV_FIELDS, write_run_record


class RunLoggerTests(unittest.TestCase):
    """Validate internal JSON traceability and planner CSV flattening."""

    def test_energy_planner_csv_has_stable_planner_fields_and_internal_json_traceability(self) -> None:
        """Payload CSV should use blank non-applicable numeric fields and preserve JSON internally."""
        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]
        area = MissionArea(
            geometry_type="line",
            centroid_lat=13.45,
            centroid_lon=144.80,
            route_points=[
                LatLon(lat=13.44, lon=144.79),
                LatLon(lat=13.46, lon=144.82),
            ],
            route_distance_km=3.92,
            route_heading_deg=55.0,
        )
        environment = EnvironmentData(
            current_speed_kts_mean=0.6,
            current_direction_deg_mean=85.0,
            sea_surface_temp_c_mean=26.0,
            sea_surface_salinity_psu=36.2,
            wind_speed_kts_mean=10.0,
            weather_summary="Clear",
            raw_marine_api_json={"current": {"speed": 0.6}},
            raw_weather_api_json={"weather": {"summary": "Clear"}},
            marine_query_params={"latitude": 13.45, "longitude": 144.805},
            weather_query_params={"latitude": 13.45, "longitude": 144.805},
        )
        simulation_inputs = {
            "additional_transit_km": 1.0,
            "track_spacing_m": 200.0,
            "return_to_start": True,
            "battery_sets_available": 2,
            "recharge_allowed": True,
        }
        summary = {
            "mission_type": "Payload Delivery",
            "mean_duration_hr": 2.5,
            "p50_energy_kwh": 0.5,
            "p80_energy_kwh": 0.6,
            "p95_energy_kwh": 0.8,
            "battery_nameplate_kwh": vehicle.battery_kwh,
            "usable_fraction": vehicle.usable_fraction,
            "usable_battery_per_set_kwh": vehicle.usable_battery_per_set_kwh,
            "battery_sets_available": 2,
            "total_available_kwh": vehicle.usable_battery_per_set_kwh * 2,
            "battery_sets_required_p80": 1,
            "battery_shortfall_p80": 0,
            "battery_inventory_sufficient_no_recharge": True,
            "recharge_allowed": True,
            "route_distance_km": 3.92,
            "payload_recovery_mode": "return_to_start",
            "payload_weight_kg": 25.0,
            "payload_weight_penalty_pct": 8.3,
            "payload_weight_multiplier": 1.083,
            "payload_weight_penalty_basis": "energy_class_scaled",
            "launch_recovery_energy_kwh": 0.02,
            "environmental_multiplier": 1.006,
            "current_uplift_pct": 0.1,
            "temp_uplift_pct": 0.0,
            "salinity_uplift_pct": 0.6,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path, csv_path = write_run_record(
                mission_type="Payload Delivery",
                area=area,
                vehicle=vehicle,
                environment=environment,
                simulation_inputs=simulation_inputs,
                simulation_summary=summary,
                result_rows=[],
                source_geometry_json='{"geometry_type": "line"}',
                output_dir=tmpdir,
            )
            record = json.loads(Path(json_path).read_text(encoding="utf-8"))
            self.assertEqual(record["raw_marine_api_json"], {"current": {"speed": 0.6}})
            self.assertEqual(record["marine_query_params"], {"latitude": 13.45, "longitude": 144.805})

            with Path(csv_path).open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(list(row.keys()), ENERGY_PLANNER_CSV_FIELDS)
        self.assertEqual(row["mission_type"], "Payload Delivery")
        self.assertEqual(row["payload_return_to_start"], "Yes")
        self.assertEqual(row["payload_recovery_mode"], "return_to_start")
        self.assertEqual(row["payload_weight_kg"], "25.0")
        self.assertEqual(row["payload_weight_penalty_pct"], "8.3")
        self.assertEqual(row["payload_weight_multiplier"], "1.083")
        self.assertEqual(row["payload_weight_penalty_basis"], "energy_class_scaled")
        self.assertEqual(row["launch_recovery_energy_kwh"], "0.02")
        self.assertEqual(row["search_area_km2"], "")
        self.assertEqual(row["track_spacing_m"], "")
        self.assertEqual(row["isr_loop_distance_km"], "")
        self.assertEqual(row["metoc_lookup_lat"], "13.45")
        self.assertEqual(row["sea_surface_salinity_psu"], "36.2")
        self.assertEqual(row["salinity_uplift_pct"], "0.6")
        self.assertEqual(row["weather_summary"], "Clear")
        self.assertEqual(row["battery_inventory_sufficient"], "Yes")
        self.assertIn("Payload energy", row["planner_note"])


if __name__ == "__main__":
    unittest.main()
