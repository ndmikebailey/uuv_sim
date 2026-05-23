"""Vehicle catalog alignment checks."""

from __future__ import annotations

import unittest

from models.vehicle_model import VEHICLE_CATALOG


class VehicleCatalogTests(unittest.TestCase):
    """Validate active catalog entries from the project-note public baseline."""

    def test_project_note_public_facing_systems_are_active(self) -> None:
        expected = {
            "Lionfish (Next-Gen MCM - Standard)": (1.5, 10.0, 5.0),
            "Lionfish (Next-Gen MCM - Extended)": (4.5, 30.0, 5.0),
            "Yellow Moray (Submarine TTL)": (3.0, 20.0, 5.0),
            "Viperfish (Deep Water MCM)": (4.5, 30.0, 5.0),
            "Iver3 580 (Legacy VSW)": (0.8, 8.0, 4.0),
            "Iver4 900 (Expeditionary MCM)": (2.0, 14.0, 5.0),
            "MK19 Mod 0 Razorback (DDS)": (7.0, 24.0, 4.0),
            "REMUS 600 / MK18 Mod 2 Kingfish legacy proxy": (31.5, 70.0, 5.0),
            "MK20 Mod 0 Razorback (TTL&R)": (5.2, 18.4, 6.0),
            "AN/AQS-23 Barracuda": (0.8, 1.5, 10.0),
            "Next-Gen MUUV (REMUS 620)": (15.0, 110.0, 8.0),
        }

        for name, (battery_kwh, endurance_hr, max_speed_kts) in expected.items():
            with self.subTest(vehicle=name):
                self.assertIn(name, VEHICLE_CATALOG)
                vehicle = VEHICLE_CATALOG[name]
                self.assertEqual(vehicle.battery_kwh, battery_kwh)
                self.assertEqual(vehicle.estimated_endurance_hr, endurance_hr)
                self.assertEqual(vehicle.max_speed_kts, max_speed_kts)
                self.assertTrue(vehicle.source_note)

    def test_non_rechargeable_public_entries_load(self) -> None:
        for name in ["MK19 Mod 0 Razorback (DDS)", "AN/AQS-23 Barracuda"]:
            with self.subTest(vehicle=name):
                vehicle = VEHICLE_CATALOG[name]
                self.assertEqual(vehicle.recharge_hr, 0.0)
                self.assertEqual(vehicle.usable_fraction, 1.0)
                self.assertFalse(vehicle.recoverable)
                self.assertFalse(vehicle.rechargeable)
                self.assertEqual(vehicle.default_payload_recovery_mode, "one_way")

    def test_optional_hotel_fraction_entries_load(self) -> None:
        self.assertEqual(VEHICLE_CATALOG["Viperfish (Deep Water MCM)"].hotel_fraction, 0.45)
        self.assertIsNone(VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"].hotel_fraction)

    def test_kingfish_proxy_metadata_loads(self) -> None:
        vehicle = VEHICLE_CATALOG["REMUS 600 / MK18 Mod 2 Kingfish legacy proxy"]
        self.assertIn("planning proxy", vehicle.usable_basis.lower())
        self.assertAlmostEqual(vehicle.average_power_kw, 0.45)
        self.assertIn("600 m depth rating", vehicle.source_note)
        self.assertIn("12.75 in / 32.4 cm diameter", vehicle.source_note)
        self.assertIn("public battery_kwh was not confidently found", vehicle.source_note)


if __name__ == "__main__":
    unittest.main()
