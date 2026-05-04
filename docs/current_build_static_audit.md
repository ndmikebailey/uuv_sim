# Current Build Static Audit

Date prepared: 2026-05-04

Scope: static source review and documentation support for manual testing and later thesis/V&V work. This is not a functional smoke test and not a code audit.

## Entrypoint And Build

- Active compatibility entrypoint: `app.py`
- Active Gradio application module: `app/main.py`
- Current git branch observed during static review: `Alpha/3.5-Beta-Release`
- Application name from constants: `UUV Mission Planning and Energy Simulator`
- App version from constants: `v3.5-beta`
- Energy model version from constants: `energy_model_v3_5_beta`
- Vehicle catalog version from constants: `vehicle_catalog_v3_5_public_baseline`

Note: constants now use the v3.5 beta label for team testing. This is still a planning tool pending manual UI review and V&V.

## Major Modules And Responsibilities

- `app.py`: Hugging Face Spaces compatible launcher; imports `demo` and `launch` from `app.main`.
- `app/main.py`: Gradio layout, callback wiring, navigation JavaScript, mission build/run callback orchestration, report output assembly.
- `app/components/map_iframe.py`: Leaflet mission geometry drawing iframe and geometry JSON handoff.
- `app/ui/reporting.py`: Report tables, energy planner summary, energy equivalence lens, METOC cards, and matplotlib figures.
- `core/energy.py`: Mission energy Monte Carlo simulation, speed-power correction, payload mass burden, stochastic battery-condition sampling integration, temperature capacity derating integration, and ISR endurance reporting.
- `core/battery.py`: Battery-condition sampling, usable-energy calculation, and named lithium temperature capacity derating curve.
- `core/sustainment.py`: Simplified sustainment energy-flow projection helper.
- `core/geometry.py`: Geometry parsing, projection, route/area calculations, search lane generation, ISR path length calculations.
- `core/mission.py`: Mission geometry validation, METOC lookup point selection, multi-area METOC aggregation.
- `core/environment.py`: Current decomposition, salinity burden, and environmental uplift helpers. Temperature is handled as battery capacity derating.
- `core/assumptions.py`: Model assumptions registry and row export helper.
- `models/vehicle_model.py`: `VehicleState` dataclass and active vehicle catalog loader.
- `models/mission_model.py`: `MissionArea`, `MissionAreaSet`, and `MissionContext` dataclasses.
- `models/environment_model.py`: `EnvironmentData` dataclass, merge behavior, and environment table rows.
- `services/marine_api.py`: Open-Meteo marine client.
- `services/weather_api.py`: Open-Meteo weather client.
- `services/metoc_fusion.py`: Marine/weather fusion, optional salinity enrichment, and METOC risk card assessment.
- `services/noaa_coops_salinity.py`, `services/woa23_salinity.py`, `services/metoc_fusion.py`: NOAA CO-OPS -> NOAA WOA23 -> standard seawater salinity provider chain. Copernicus was removed from the active v3.5 salinity chain.
- `services/run_logger.py`: Internal run-record traceability.
- `utils/constants.py`: App, model, catalog, mission, and API constants.
- `utils/parsing.py`: UI parsing and formatting helpers.

## Supported Mission Modes

- Payload Delivery
- ISR
- Area Search / MCM

Current Search/MCM backend supports single-area and multi-area search plans. Multi-area support aggregates selected search areas and uses one METOC lookup per area centroid.

## Vehicle Catalog And Source Files

- Active vehicle catalog: `data/vehicle_catalog.json`
- Supplemental vehicle source metadata: `data/vehicle_source_metadata_v3_2.json`
- Source register: `data/source_register.md`
- v3.2 source addendum: `data/source_register_v3_2_addendum.md`
- Public baseline limitations documentation: `docs/baseline_data_limitations.md`

Active catalog entries observed:

- REMUS 100B - 1.5 kWh
- REMUS 300 - 1.5 kWh
- REMUS 300 - 3.0 kWh Standard
- REMUS 300 - 4.5 kWh
- Bluefin-9 - 1.5 kWh
- Bluefin-12D - 7.5 kWh
- Iver3 EP - 0.8 kWh
- Iver4 580 - 0.78 kWh
- Lionfish (Next-Gen MCM - Standard)
- Lionfish (Next-Gen MCM - Extended)
- Yellow Moray (Submarine TTL)
- Viperfish (Deep Water MCM)
- Iver3 580 (Legacy VSW)
- Iver4 900 (Expeditionary MCM)
- MK19 Mod 0 Razorback (DDS)
- MK20 Mod 0 Razorback (TTL&R)
- AN/AQS-23 Barracuda
- Next-Gen MUUV (REMUS 620)

## Current Report Sections

The Results tab currently assembles:

- Mission Decision Brief
- Executive Results Summary
- METOC Assessment
- Four-panel visual grid when GPS geometry exists: Mission Map Overlay, Monte Carlo / Uncertainty Distribution, Engineering Geometry Snapshot, and Mission Energy Progress and Battery Lens
- Energy Detail
- Battery and Sustainment Detail
- Sustainment Projection Lens
- Mission Geometry Detail
- Environmental Detail
- Energy Storage Equivalence Lens
- Technical Traceability / Model Detail

## Known Assumptions Registry

Known assumptions registry location: `core/assumptions.py`

The registry currently includes:

- `propulsion_speed_exponent`
- `default_hotel_load_fraction`
- `default_usable_battery_fraction`
- `usable_battery_fraction_range`
- `default_generator_efficiency`
- `open_meteo_representative_point_policy`
- `temperature_derating_curve_status`
- `temperature_derating_curve_v1`
- `temperature_no_effect_band`
- `temperature_derating_rationale`
- `temperature_model_limitation`
- `salinity_source_policy`
- `salinity_baseline_psu`
- `seawater_density_baseline_kg_m3`
- `payload_mass_penalty_curve`
- `payload_energy_class_policy`
- `launch_recovery_overhead_policy`
- `launch_recovery_power_basis`
- `vehicle_specific_hotel_fraction_policy`
- `oil_equivalent_conversion_caveat`

## Energy Model Complexity Notes

Payload logic appears to live inside `run_energy_simulation()` in `core/energy.py`, in the `if mission_type in PAYLOAD_MISSIONS` branch. It computes outbound time, optional return time, added transit time, speed-adjusted power, current penalty, salinity uplift, payload propulsion burden, and mission energy. Payload burden applies to propulsion power only and is scoped to Payload Delivery.

ISR logic appears to live inside `run_energy_simulation()` in the `elif mission_type in ISR_MISSIONS` branch, with support helpers `compute_isr_persistence()` and `_isr_loop_coverage()`. It computes endurance speed, ISR current penalty, speed-adjusted endurance power, single-set endurance, total inventory endurance, full loops, partial loop coverage, patrol distance, and planning-basis fields.

Search/MCM logic appears to live inside `run_energy_simulation()` in the final `else` branch after Search/MCM plans are generated by `search_plan()`. It evaluates two track orientations, applies current duration multiplier and salinity uplift, and chooses the lower-energy orientation. Temperature affects available battery capacity. Multi-area Search/MCM is passed into this existing path as a single aggregate equivalent area from `MissionAreaSet.aggregate_area()`.

Future refactor into mission-specific helpers is recommended, but should not be done as part of this static documentation pass. Candidate helpers:

- `simulate_payload_sample()`
- `simulate_isr_sample()`
- `simulate_search_sample()`
- `summarize_isr_results()`
- `summarize_search_results()`

## Multi-Area Search/MCM Flow

Multiple areas are represented by `MissionAreaSet` in `models/mission_model.py`.

The wrapper stores:

- `areas: list[MissionArea]`
- `total_area_km2`
- `representative_points`
- `geometry_type = "MultiArea"`

Total area appears aggregated by summing each child `MissionArea.area_km2`.

METOC centroid count appears tracked through:

- `representative_points`
- `number_of_search_areas`
- `metoc_sample_count`
- `metoc_lookup_points`
- `metoc_aggregation_method`

Current vector averaging appears implemented in `core/mission.py` using:

- `current_u = current_speed_kts * sin(direction_rad)`
- `current_v = current_speed_kts * cos(direction_rad)`
- `aggregate_speed = sqrt(mean_u**2 + mean_v**2)`
- `aggregate_direction = atan2(mean_u, mean_v)` converted back to compass degrees

Open questions for manual UI testing:

- Confirm the Leaflet iframe preserves multiple rectangles/polygons after repeated drawing operations.
- Confirm drawing a route line clears area geometries as intended.
- Confirm deleting one of several areas updates the raw geometry payload and summary cards correctly.
- Confirm multi-area map snapshot shows all selected areas in a shared local frame.
- Confirm aggregate lane/swath visualization note is understandable to users.
- Confirm multi-area METOC status remains clear when one area lookup fails and others succeed.

## Known Remaining Risks Or TODOs

- `core/energy.py` has a TODO for contested-delay stochastic hover/loiter interruptions.
- Multi-area lane rendering is simplified; per-area lane rendering is not yet implemented.
- Search/MCM aggregate area is represented as an equivalent square for the existing energy path. This preserves a simple planning model but may not capture geometry-specific lane-turn differences across separated areas.
- Usable battery fraction stochastic modeling is implemented as a planning uncertainty driver.
- Temperature derating is implemented as a usable-capacity curve, not a duplicate demand uplift.
- Sustainment Projection Lens is implemented as a simplified energy-flow report lens.
- Payload weight effect is implemented for Payload Delivery and covered by targeted tests.
- NOAA CO-OPS station salinity and WOA23 climatology lookup require later live validation in representative areas; standard seawater fallback is active for no-provider conditions.
- Run logger still writes internal records for traceability, while user-facing CSV/JSON export controls are not exposed.

## Verification Result

Verification status from the prior static audit is superseded by the current test pass for this integration cleanup.

No app launch, Hugging Face launch check, or generated export workflow is part of this cleanup pass.
