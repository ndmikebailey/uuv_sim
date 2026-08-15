from __future__ import annotations

import json
from pathlib import Path


def require_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    actual = text.count(old)
    if actual != count:
        raise RuntimeError(f"{label}: expected {count} match(es), found {actual}")
    return text.replace(old, new, count)


catalog_path = Path("data/vehicle_catalog.json")
catalog = json.loads(catalog_path.read_text(encoding="utf-8"))


def set_sensor(name: str, included: bool, basis: str, note: str | None = None) -> None:
    entry = catalog[name]
    entry["sensor_load_included"] = bool(included)
    entry["sensor_load_basis"] = basis
    if note is not None:
        entry["source_note"] = note


set_sensor(
    "REMUS 100B - 1.5 kWh",
    True,
    "Bathymetric variant with its mission sensor configuration; treat the published endurance as sensor-inclusive.",
)
set_sensor(
    "REMUS 130 - 1.5 kWh",
    True,
    "HII states the published endurance is measured at 3.0 kn with standard sensors active. Optional mission payloads are separate.",
    "HII REMUS 130: 1.5 kWh, 10 h at 3 kn with standard sensors active; 6 h in-vehicle recharge.",
)
for name, hours, recharge in [
    ("REMUS 300 - 1.5 kWh", 10, 6),
    ("REMUS 300 - 3.0 kWh", 20, 12),
    ("REMUS 300 - 4.5 kWh", 30, 18),
]:
    battery = catalog[name]["battery_kwh"]
    qualifier = " standard" if battery == 3.0 else ""
    set_sensor(
        name,
        True,
        "HII states the published endurance is measured at 3.0 kn with standard sensors active. Optional mission payloads are separate.",
        f"HII REMUS 300 {battery:.1f}-kWh{qualifier} configuration: {hours} h at 3 kn with standard sensors active; {recharge} h in-vehicle recharge.",
    )

if "New Generation REMUS 100 - 1.5 kWh" not in catalog:
    catalog["New Generation REMUS 100 - 1.5 kWh"] = {
        "battery_kwh": 1.5,
        "estimated_endurance_hr": 12.0,
        "nominal_speed_kts": 3.0,
        "max_speed_kts": 5.0,
        "recharge_hr": 6.0,
        "recoverable": True,
        "rechargeable": True,
        "default_payload_recovery_mode": "return_to_start",
        "usable_fraction": 0.88,
        "usable_basis": "Planning baseline; practical usable fraction is sampled separately by the simulator.",
        "sensor_load_included": True,
        "sensor_load_basis": "The 12-h New Generation REMUS 100 evidence is tied to an MCM/sonar-equipped configuration; the field report confirms operation with the fitted sonar suite.",
        "source_url": "https://www.hii.com/news/huntington-ingalls-industries-delivers-remus-100-uuvs-to-the-german-navy",
        "source_note": "New Generation REMUS 100: 1.5 kWh, 12 h at 3 kt. HII independently states up to 12 h for new REMUS 100 MCM vehicles equipped with side-scan sonar.",
        "size_class": "S",
    }

set_sensor(
    "REMUS 600 - 5.2 kWh",
    False,
    "Endurance varies with battery, speed, and sensor use; the selected catalog value is treated as the vehicle baseline and mission equipment is added separately.",
    "HII REMUS 600 standard 5.2-kWh rechargeable configuration with the cited 24-h planning baseline. Recharge is a 4 h/kWh planning estimate.",
)
set_sensor(
    "REMUS 6000 - 17.55 kWh",
    False,
    "Configurable payload architecture; the catalog endurance is treated as a vehicle/runtime baseline and mission equipment is added separately.",
)
set_sensor(
    "Bluefin-9 - 1.9 kWh",
    False,
    "Modular payload vehicle; the published endurance is treated as the vehicle baseline and mission equipment is added separately.",
)
set_sensor(
    "Bluefin-12 - 7.6 kWh",
    False,
    "Modular payload vehicle; the published speed/endurance condition is treated as the vehicle baseline and mission equipment is added separately.",
)
set_sensor(
    "Bluefin-21 - 13.5 kWh",
    True,
    "The 25-h endurance condition is explicitly stated with the standard payload.",
)
set_sensor(
    "Iver3 580 Standard - 0.8 kWh",
    False,
    "Payload/current-dependent endurance; use the catalog value as the vehicle baseline and add the selected mission-equipment demand separately.",
)
set_sensor(
    "Iver3 EP - 0.8 kWh",
    False,
    "Open/configurable payload vehicle; use the catalog value as the vehicle baseline and add mission-equipment demand separately.",
)
set_sensor(
    "Iver4 580 - 0.78 kWh",
    False,
    "Configurable payload vehicle; use the catalog value as the vehicle baseline and add mission-equipment demand separately.",
)
for name in ["Iver4 900 - 2.0 kWh NiMH", "Iver4 900 - 4.0 kWh Li-ion"]:
    set_sensor(
        name,
        False,
        "Configurable payload vehicle; use the catalog value as the vehicle baseline and add mission-equipment demand separately.",
    )
catalog["Iver4 900 - 2.0 kWh NiMH"]["source_note"] = (
    "L3Harris Iver4 900 standard NiMH configuration: 2 kWh and 20+ h. Recharge is a 4 h/kWh planning estimate."
)
for name in ["Sentry - 13 kWh validation profile", "Sentry - 18 kWh validation profile"]:
    set_sensor(
        name,
        False,
        "The published endurance is mission-dependent rather than tied to one fixed sensor-duty condition; the validation retains the generic mission-equipment term.",
    )
set_sensor(
    "Autosub5 - 25 kWh validation profile",
    True,
    "The cited 24-h statement explicitly says all sensors operating.",
)
set_sensor(
    "GEOMAR ABYSS - 11.2 kWh",
    True,
    "GEOMAR ties the 20-h endurance condition directly to the sidescan-sonar configuration.",
)

old_620_name = "REMUS 620 - 3 battery / no payload"
old_620 = catalog.get(old_620_name) or catalog.get("REMUS 620 - 3 batteries / no payload")
if old_620 is None:
    raise RuntimeError("Expected REMUS 620 baseline not found")


def remus620_variant(
    battery: float,
    hours: float,
    name: str,
    included: bool,
    note: str,
    basis: str,
) -> tuple[str, dict]:
    entry = dict(old_620)
    entry.update(
        {
            "battery_kwh": battery,
            "estimated_endurance_hr": hours,
            "sensor_load_included": included,
            "sensor_load_basis": basis,
            "source_note": note,
            "size_class": "M",
        }
    )
    return name, entry


variants = [
    remus620_variant(
        9.6,
        42.0,
        "REMUS 620 - 1 battery / no payload",
        False,
        "HII REMUS 620 1-battery/no-payload condition: 9.6 kWh, 42 h, 204 km, ideal conditions at approximately 2.5-3 kt.",
        "HII states this configuration for ideal conditions with no payload, so mission equipment is not included.",
    ),
    remus620_variant(
        9.6,
        26.0,
        "REMUS 620 - 1 battery / MINSAS 120",
        True,
        "HII REMUS 620, 1 battery with example Kraken Aquapix MINSAS 120 wet payload: 9.6 kWh, 26 h, 130 km.",
        "HII publishes this endurance for the example Kraken Aquapix MINSAS 120 wet-payload configuration.",
    ),
    remus620_variant(
        19.3,
        80.0,
        "REMUS 620 - 2 batteries / no payload",
        False,
        "HII REMUS 620 2-battery/no-payload condition: 19.3 kWh, 80 h, 370 km, ideal conditions at approximately 2.5-3 kt.",
        "HII states this configuration for ideal conditions with no payload, so mission equipment is not included.",
    ),
    remus620_variant(
        19.3,
        50.0,
        "REMUS 620 - 2 batteries / MINSAS 120",
        True,
        "HII REMUS 620, 2 batteries with example Kraken Aquapix MINSAS 120 wet payload: 19.3 kWh, 50 h, 245 km.",
        "HII publishes this endurance for the example Kraken Aquapix MINSAS 120 wet-payload configuration.",
    ),
    remus620_variant(
        28.9,
        110.0,
        "REMUS 620 - 3 batteries / no payload",
        False,
        "HII REMUS 620 3-battery/no-payload condition: 28.9 kWh, 110 h, 509 km, ideal conditions at approximately 2.5-3 kt.",
        "HII states this configuration for ideal conditions with no payload, so mission equipment is not included.",
    ),
]

rebuilt = {}
inserted_620 = False
for key, value in catalog.items():
    if key in {old_620_name, "REMUS 620 - 3 batteries / no payload"} or key.startswith("REMUS 620 - "):
        if not inserted_620:
            for variant_name, variant in variants:
                rebuilt[variant_name] = variant
            inserted_620 = True
        continue
    rebuilt[key] = value
catalog = rebuilt

if any(entry.get("sensor_load_included") not in (True, False) for entry in catalog.values()):
    missing = [
        name
        for name, entry in catalog.items()
        if entry.get("sensor_load_included") not in (True, False)
    ]
    raise RuntimeError(f"Catalog entries still missing a true/false sensor flag: {missing}")
if any(entry.get("size_class") not in {"S", "M", "L"} for entry in catalog.values()):
    raise RuntimeError("Every catalog entry must have S/M/L size_class")

catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

metadata_path = Path("data/vehicle_source_metadata_v3_2.json")
metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
metadata["sensor_load_included"] = (
    "true = cited endurance includes the stated standard sensor/payload demand; "
    "false = mission payload demand is separate from the cited endurance condition."
)
metadata["size_class"] = (
    "S = small-body/portable; M = torpedo-tube/medium-body; "
    "L = larger research/high-power vehicle. Modeling tag only; no multiplier is active."
)
metadata["vehicles"] = {
    name: {
        "source_url": entry.get("source_url"),
        "sensor_load_included": entry["sensor_load_included"],
        "sensor_load_basis": entry.get("sensor_load_basis"),
        "source_note": entry.get("source_note"),
        "size_class": entry.get("size_class"),
    }
    for name, entry in catalog.items()
}
metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

register = [
    "# Vehicle catalog sources",
    "",
    "S = small-body/portable, M = torpedo-tube/medium-body, L = larger research/high-power vehicle.",
    "Sensor included = the cited endurance condition already includes the stated standard sensor/payload demand.",
    "The class is a modeling tag only; no class multiplier is active yet.",
    "",
    "| Vehicle | Class | Sensor included | Source |",
    "| --- | :---: | :---: | --- |",
]
for name, entry in catalog.items():
    register.append(
        f"| {name} | {entry['size_class']} | {'Yes' if entry['sensor_load_included'] else 'No'} | {entry.get('source_url', '')} |"
    )
Path("data/source_register_v3_2_addendum.md").write_text("\n".join(register) + "\n", encoding="utf-8")

# Core energy behavior.
energy_path = Path("core/energy.py")
energy = energy_path.read_text(encoding="utf-8")
energy = require_replace(
    energy,
    "    mission_sequences = max(1, int(mission_sequences))\n\n    current_mean = float(environment.current_speed_kts_mean if environment.current_speed_kts_mean is not None else 0.5)",
    "    mission_sequences = max(1, int(mission_sequences))\n    sensor_load_included = vehicle.sensor_load_included is True\n    effective_mission_sensor_power_enabled = bool(\n        mission_sensor_power_enabled and not sensor_load_included\n    )\n\n    current_mean = float(environment.current_speed_kts_mean if environment.current_speed_kts_mean is not None else 0.5)",
    "run_energy_simulation sensor-policy insertion point",
)
energy = require_replace(
    energy,
    "        mission_sensor_power_kw = sampled_mission_sensor_power_kw if mission_sensor_power_enabled else 0.0\n        transit_sensor_power_kw = sampled_transit_sensor_power_kw if mission_sensor_power_enabled else 0.0",
    "        mission_sensor_power_kw = (\n            sampled_mission_sensor_power_kw if effective_mission_sensor_power_enabled else 0.0\n        )\n        transit_sensor_power_kw = (\n            sampled_transit_sensor_power_kw if effective_mission_sensor_power_enabled else 0.0\n        )",
    "mission sensor-power gating lines",
)
energy = require_replace(
    energy,
    "    active_sensor_mode, sensor_power_basis = mission_sensor_power_basis(\n        mission_type,\n        enabled=bool(mission_sensor_power_enabled),\n    )",
    "    if sensor_load_included:\n        active_sensor_mode = \"Included in catalog endurance\"\n        sensor_power_basis = (\n            \"The selected vehicle endurance already includes the stated standard \"\n            \"sensor/payload demand; no additional generic mission sensor power is applied.\"\n        )\n    else:\n        active_sensor_mode, sensor_power_basis = mission_sensor_power_basis(\n            mission_type,\n            enabled=effective_mission_sensor_power_enabled,\n        )",
    "sensor-power basis block",
)
energy = require_replace(
    energy,
    "        \"mission_sensor_power_enabled\": bool(mission_sensor_power_enabled),\n        \"mission_sensor_power_mean_kw\": float(np.mean(mission_sensor_power_arr)),",
    "        \"mission_sensor_power_requested\": bool(mission_sensor_power_enabled),\n        \"mission_sensor_power_enabled\": effective_mission_sensor_power_enabled,\n        \"sensor_load_included_in_endurance\": sensor_load_included,\n        \"sensor_load_inclusion_basis\": vehicle.sensor_load_basis or \"\",\n        \"mission_sensor_power_mean_kw\": float(np.mean(mission_sensor_power_arr)),",
    "sensor summary fields",
)
energy = require_replace(
    energy,
    "        (\n            \"Sensor-use logic\",\n            \"Active search/survey receives Search/MCM sensor-mode power; added transit receives Route/Transit sensor-mode power.\"\n            if mission_type in SEARCH_MISSIONS\n            else \"\",\n            \"\",\n        ),",
    "        (\n            \"Sensor-use logic\",\n            (\n                \"Published endurance already includes the stated standard sensor/payload demand; \"\n                \"no generic mission sensor power is added.\"\n                if sensor_load_included\n                else (\n                    \"Active search/survey receives Search/MCM sensor-mode power; added transit receives Route/Transit sensor-mode power.\"\n                    if mission_type in SEARCH_MISSIONS\n                    else \"Generic mission sensor-mode power is added for this mission type.\"\n                )\n            ),\n            \"\",\n        ),",
    "Sensor-use logic result row",
)
energy_path.write_text(energy, encoding="utf-8")

assumptions_path = Path("core/assumptions.py")
assumptions = assumptions_path.read_text(encoding="utf-8")
assumptions = assumptions.replace(
    "Represents uncertainty in onboard sensors, processing, navigation support, communications, and mission-equipment demand by active mission segment without replacing hotel or propulsion power.",
    "Represents uncertainty in onboard sensors, processing, navigation support, communications, and mission-equipment demand when that demand is not already included in the selected catalog endurance baseline.",
)
assumptions_path.write_text(assumptions, encoding="utf-8")

# Persistent sensor-policy regression test.
Path("tests/test_sensor_inclusion.py").write_text(
    '''"""Catalog sensor-in-endurance behavior."""\n\nfrom __future__ import annotations\n\nimport unittest\n\nfrom core.energy import run_energy_simulation\nfrom core.geometry import manual_rectangle_area\nfrom models.environment_model import EnvironmentData\nfrom models.vehicle_model import VEHICLE_CATALOG\n\n\nclass SensorInEnduranceTests(unittest.TestCase):\n    def _run_search(self, vehicle_name: str):\n        vehicle = VEHICLE_CATALOG[vehicle_name]\n        return run_energy_simulation(\n            vehicle=vehicle,\n            mission_type="Area Search / MCM",\n            area=manual_rectangle_area(1.0, 1.0, 1.0),\n            environment=EnvironmentData(\n                current_speed_kts_mean=0.0,\n                current_direction_deg_mean=0.0,\n                sea_surface_temp_c_mean=25.0,\n                sea_surface_salinity_psu=35.0,\n            ),\n            additional_transit_km=0.0,\n            track_spacing_m=200.0,\n            return_to_start=True,\n            speed_kts=vehicle.nominal_speed_kts,\n            battery_sets_available=1,\n            recharge_allowed=False,\n            mission_sequences=1,\n            rng_seed=123,\n            monte_carlo_runs=1,\n            deterministic_mode=True,\n        )\n\n    def test_sensor_inclusive_endurance_suppresses_generic_search_load(self) -> None:\n        result = self._run_search("New Generation REMUS 100 - 1.5 kWh")\n        self.assertTrue(result.summary["mission_sensor_power_requested"])\n        self.assertFalse(result.summary["mission_sensor_power_enabled"])\n        self.assertTrue(result.summary["sensor_load_included_in_endurance"])\n        self.assertAlmostEqual(float(result.summary["mission_sensor_power_mean_w"]), 0.0)\n\n    def test_no_payload_endurance_keeps_generic_search_load(self) -> None:\n        result = self._run_search("REMUS 620 - 1 battery / no payload")\n        self.assertTrue(result.summary["mission_sensor_power_requested"])\n        self.assertTrue(result.summary["mission_sensor_power_enabled"])\n        self.assertFalse(result.summary["sensor_load_included_in_endurance"])\n        self.assertAlmostEqual(float(result.summary["mission_sensor_power_mean_w"]), 112.5)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

# Catalog checks.
Path("tests/test_vehicle_catalog.py").write_text(
    '''"""Vehicle catalog publication checks."""\n\nfrom __future__ import annotations\n\nimport unittest\n\nfrom models.vehicle_model import VEHICLE_CATALOG\n\n\nclass VehicleCatalogTests(unittest.TestCase):\n    def test_all_entries_have_source_sensor_and_size_metadata(self) -> None:\n        for name, vehicle in VEHICLE_CATALOG.items():\n            with self.subTest(vehicle=name):\n                self.assertTrue(vehicle.source_note)\n                self.assertTrue(vehicle.source_url)\n                self.assertTrue(vehicle.sensor_load_basis)\n                self.assertIsInstance(vehicle.sensor_load_included, bool)\n                self.assertIn(vehicle.size_class, {"S", "M", "L"})\n\n    def test_remus_300_endurance_includes_standard_sensors(self) -> None:\n        for name in [\n            "REMUS 300 - 1.5 kWh",\n            "REMUS 300 - 3.0 kWh",\n            "REMUS 300 - 4.5 kWh",\n        ]:\n            self.assertTrue(VEHICLE_CATALOG[name].sensor_load_included)\n\n    def test_remus_620_configuration_pairs(self) -> None:\n        expected = {\n            "REMUS 620 - 1 battery / no payload": (9.6, 42.0, False),\n            "REMUS 620 - 1 battery / MINSAS 120": (9.6, 26.0, True),\n            "REMUS 620 - 2 batteries / no payload": (19.3, 80.0, False),\n            "REMUS 620 - 2 batteries / MINSAS 120": (19.3, 50.0, True),\n            "REMUS 620 - 3 batteries / no payload": (28.9, 110.0, False),\n        }\n        for name, values in expected.items():\n            vehicle = VEHICLE_CATALOG[name]\n            self.assertEqual(\n                (vehicle.battery_kwh, vehicle.estimated_endurance_hr, vehicle.sensor_load_included),\n                values,\n            )\n\n    def test_old_program_aliases_are_not_selectable(self) -> None:\n        removed = {\n            "Lionfish (Next-Gen MCM - Standard)",\n            "Lionfish (Next-Gen MCM - Extended)",\n            "Yellow Moray (Submarine TTL)",\n            "Viperfish (Deep Water MCM)",\n            "Iver3 580 (Legacy VSW)",\n            "Iver4 900 (Expeditionary MCM)",\n            "MK19 Mod 0 Razorback (DDS)",\n            "REMUS 600 / MK18 Mod 2 Kingfish legacy proxy",\n            "MK20 Mod 0 Razorback (TTL&R)",\n            "AN/AQS-23 Barracuda",\n            "Next-Gen MUUV (REMUS 620)",\n        }\n        self.assertTrue(removed.isdisjoint(VEHICLE_CATALOG))\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

# Existing energy tests that intentionally exercise the generic sensor ranges must use a sensor-separate baseline.
energy_test_path = Path("tests/test_energy.py")
energy_tests = energy_test_path.read_text(encoding="utf-8")
energy_tests = require_replace(
    energy_tests,
    '    def test_mission_sensor_power_increases_search_energy(self) -> None:\n        """Search/MCM energy should increase when segment-based sensor power is enabled."""\n        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]',
    '    def test_mission_sensor_power_increases_search_energy(self) -> None:\n        """Search/MCM energy should increase when segment-based sensor power is enabled."""\n        vehicle = VEHICLE_CATALOG["REMUS 620 - 1 battery / no payload"]',
    "generic Search/MCM sensor-load energy test vehicle",
)
energy_tests = require_replace(
    energy_tests,
    '    def test_search_transit_uses_low_sensor_range_not_mcm_range(self) -> None:\n        """Additional Search/MCM transit should not carry the full active survey sensor range."""\n        vehicle = VEHICLE_CATALOG["REMUS 300 - 4.5 kWh"]',
    '    def test_search_transit_uses_low_sensor_range_not_mcm_range(self) -> None:\n        """Additional Search/MCM transit should not carry the full active survey sensor range."""\n        vehicle = VEHICLE_CATALOG["REMUS 620 - 1 battery / no payload"]',
    "Search transit sensor-range test vehicle",
)
energy_test_path.write_text(energy_tests, encoding="utf-8")

# Reasonableness tests keep generic behaviors using synthetic vehicles rather than retired catalog aliases.
reason_path = Path("tests/test_model_reasonableness.py")
reason = reason_path.read_text(encoding="utf-8")
reason = require_replace(
    reason,
    "from __future__ import annotations\n\nimport unittest",
    "from __future__ import annotations\n\nfrom dataclasses import replace\nimport unittest",
    "reasonableness dataclasses import",
)
reason = require_replace(
    reason,
    '            vehicle=VEHICLE_CATALOG["AN/AQS-23 Barracuda"],',
    '            vehicle=replace(\n                self.vehicle,\n                name="Synthetic one-way test vehicle",\n                recharge_hr=0.0,\n                recoverable=False,\n                rechargeable=False,\n                default_payload_recovery_mode="one_way",\n                usable_fraction=1.0,\n            ),',
    "synthetic non-rechargeable reasonableness vehicle",
)
reason = require_replace(
    reason,
    '        high_hotel_vehicle = VEHICLE_CATALOG["Viperfish (Deep Water MCM)"]',
    '        high_hotel_vehicle = replace(\n            default_vehicle,\n            name="Synthetic high-hotel test vehicle",\n            hotel_fraction=0.45,\n        )',
    "synthetic high-hotel reasonableness vehicle",
)
reason_path.write_text(reason, encoding="utf-8")

# UI callback tests: use current catalog names and inject a synthetic one-way vehicle only for the generic inventory-language test.
app_test_path = Path("tests/test_app_callbacks.py")
app_tests = app_test_path.read_text(encoding="utf-8")
app_tests = require_replace(
    app_tests,
    "from __future__ import annotations\n\nimport csv",
    "from __future__ import annotations\n\nfrom dataclasses import replace\nimport csv",
    "app callback dataclasses import",
)
app_tests = app_tests.replace(
    '"Next-Gen MUUV (REMUS 620)"',
    '"REMUS 620 - 3 batteries / no payload"',
)
old = '''    def test_one_way_non_rechargeable_report_uses_vehicle_inventory_language(self) -> None:\n        """Non-rechargeable platforms should use vehicle-unit inventory wording."""\n        result = main.run_from_ui(\n            "AN/AQS-23 Barracuda",'''
new = '''    def test_one_way_non_rechargeable_report_uses_vehicle_inventory_language(self) -> None:\n        """Non-rechargeable platforms should use vehicle-unit inventory wording."""\n        synthetic_name = "Synthetic one-way callback test vehicle"\n        main.VEHICLE_CATALOG[synthetic_name] = replace(\n            main.VEHICLE_CATALOG["REMUS 300 - 1.5 kWh"],\n            name=synthetic_name,\n            recharge_hr=0.0,\n            recoverable=False,\n            rechargeable=False,\n            default_payload_recovery_mode="one_way",\n            usable_fraction=1.0,\n        )\n        self.addCleanup(main.VEHICLE_CATALOG.pop, synthetic_name, None)\n        result = main.run_from_ui(\n            synthetic_name,'''
app_tests = require_replace(
    app_tests,
    old,
    new,
    "synthetic non-rechargeable callback vehicle",
)
app_test_path.write_text(app_tests, encoding="utf-8")

print("Catalog sensor policy migration staged successfully.")
