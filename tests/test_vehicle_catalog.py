"""Vehicle catalog publication checks."""

from __future__ import annotations

import unittest

from models.vehicle_model import VEHICLE_CATALOG


class VehicleCatalogTests(unittest.TestCase):
    def test_all_entries_have_source_sensor_and_size_metadata(self) -> None:
        for name, vehicle in VEHICLE_CATALOG.items():
            with self.subTest(vehicle=name):
                self.assertTrue(vehicle.source_note)
                self.assertTrue(vehicle.source_url)
                self.assertTrue(vehicle.sensor_load_basis)
                self.assertIsInstance(vehicle.sensor_load_included, bool)
                self.assertIn(vehicle.size_class, {"S", "M", "L"})

    def test_remus_300_endurance_includes_standard_sensors(self) -> None:
        for name in [
            "REMUS 300 - 1.5 kWh",
            "REMUS 300 - 3.0 kWh",
            "REMUS 300 - 4.5 kWh",
        ]:
            self.assertTrue(VEHICLE_CATALOG[name].sensor_load_included)

    def test_remus_620_configuration_pairs(self) -> None:
        expected = {
            "REMUS 620 - 1 battery / no payload": (9.6, 42.0, False),
            "REMUS 620 - 1 battery / MINSAS 120": (9.6, 26.0, True),
            "REMUS 620 - 2 batteries / no payload": (19.3, 80.0, False),
            "REMUS 620 - 2 batteries / MINSAS 120": (19.3, 50.0, True),
            "REMUS 620 - 3 batteries / no payload": (28.9, 110.0, False),
        }
        for name, values in expected.items():
            vehicle = VEHICLE_CATALOG[name]
            self.assertEqual(
                (vehicle.battery_kwh, vehicle.estimated_endurance_hr, vehicle.sensor_load_included),
                values,
            )

    def test_old_program_aliases_are_not_selectable(self) -> None:
        removed = {
            "Lionfish (Next-Gen MCM - Standard)",
            "Lionfish (Next-Gen MCM - Extended)",
            "Yellow Moray (Submarine TTL)",
            "Viperfish (Deep Water MCM)",
            "Iver3 580 (Legacy VSW)",
            "Iver4 900 (Expeditionary MCM)",
            "MK19 Mod 0 Razorback (DDS)",
            "REMUS 600 / MK18 Mod 2 Kingfish legacy proxy",
            "MK20 Mod 0 Razorback (TTL&R)",
            "AN/AQS-23 Barracuda",
            "Next-Gen MUUV (REMUS 620)",
        }
        self.assertTrue(removed.isdisjoint(VEHICLE_CATALOG))


if __name__ == "__main__":
    unittest.main()
