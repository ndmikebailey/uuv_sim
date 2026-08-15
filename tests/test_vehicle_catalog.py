"""Vehicle catalog checks for the publication cleanup."""

from __future__ import annotations

import unittest

from models.vehicle_model import VEHICLE_CATALOG


EXPECTED = {'REMUS 100B - 1.5 kWh': (1.5, 8.0, 3.0, 4.5), 'REMUS 130 - 1.5 kWh': (1.5, 10.0, 3.0, 5.0), 'REMUS 300 - 1.5 kWh': (1.5, 10.0, 3.0, 4.0), 'REMUS 300 - 3.0 kWh': (3.0, 20.0, 3.0, 4.0), 'REMUS 300 - 4.5 kWh': (4.5, 30.0, 3.0, 4.0), 'REMUS 600 - 5.2 kWh': (5.2, 24.0, 3.0, 5.0), 'REMUS 620 - 3 battery / no payload': (28.9, 110.0, 3.0, 8.0), 'REMUS 6000 - 17.55 kWh': (17.55, 25.0, 3.0, 4.2), 'Bluefin-9 - 1.9 kWh': (1.9, 8.0, 3.0, 5.0), 'Bluefin-12 - 7.6 kWh': (7.6, 24.0, 3.0, 5.0), 'Bluefin-21 - 13.5 kWh': (13.5, 25.0, 3.0, 4.5), 'Iver3 580 Standard - 0.8 kWh': (0.8, 5.0, 2.5, 3.5), 'Iver3 EP - 0.8 kWh': (0.8, 8.0, 2.5, 4.0), 'Iver4 580 - 0.78 kWh': (0.78, 6.0, 4.5, 5.0), 'Iver4 900 - 2.0 kWh NiMH': (2.0, 20.0, 3.0, 5.0), 'Iver4 900 - 4.0 kWh Li-ion': (4.0, 40.0, 3.0, 5.0), 'Sentry - 13 kWh validation profile': (13.0, 18.0, 1.2, 2.3), 'Sentry - 18 kWh validation profile': (18.0, 26.0, 1.2, 2.3), 'Autosub5 - 25 kWh validation profile': (25.0, 24.0, 2.5, 3.0), 'GEOMAR ABYSS - 11.2 kWh': (11.2, 20.0, 3.0, 3.5)}


class VehicleCatalogTests(unittest.TestCase):
    def test_expected_vehicles_and_values(self) -> None:
        self.assertEqual(set(VEHICLE_CATALOG), set(EXPECTED))
        for name, expected in EXPECTED.items():
            with self.subTest(vehicle=name):
                vehicle = VEHICLE_CATALOG[name]
                actual = (
                    vehicle.battery_kwh,
                    vehicle.estimated_endurance_hr,
                    vehicle.nominal_speed_kts,
                    vehicle.max_speed_kts,
                )
                self.assertEqual(actual, expected)
                self.assertTrue(vehicle.source_note)
                self.assertTrue(vehicle.source_url)
                self.assertTrue(vehicle.sensor_load_basis)
                self.assertIn(vehicle.sensor_load_included, (True, False, None))

    def test_old_duplicate_program_names_are_removed(self) -> None:
        old_names = {
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
        self.assertTrue(old_names.isdisjoint(VEHICLE_CATALOG))

    def test_known_sensor_inclusion_cases(self) -> None:
        self.assertFalse(VEHICLE_CATALOG["REMUS 620 - 3 battery / no payload"].sensor_load_included)
        self.assertTrue(VEHICLE_CATALOG["Bluefin-21 - 13.5 kWh"].sensor_load_included)
        self.assertTrue(VEHICLE_CATALOG["Autosub5 - 25 kWh validation profile"].sensor_load_included)
        self.assertTrue(VEHICLE_CATALOG["GEOMAR ABYSS - 11.2 kWh"].sensor_load_included)


if __name__ == "__main__":
    unittest.main()
