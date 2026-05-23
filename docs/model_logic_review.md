# Model Logic Review

## Model Purpose

The UUV Sustainment Simulation estimates planning-level energy demand, battery inventory sufficiency, recharge/swap burden, and selected sustainment equivalence measures for representative UUV mission profiles.

The model is intended to support academic analysis, manual scenario comparison, and V&V planning. It is not an operational performance authority and should not be used as a substitute for platform test data, manufacturer engineering models, or mission planning tools approved for operational use.

## Weighted Operational Planning Model, Not CFD

This project is a weighted operational planning model. It combines mission geometry, public vehicle baseline data, simplified speed-power behavior, environmental uplift factors, battery inventory, and Monte Carlo uncertainty.

It is not computational fluid dynamics. It does not solve vehicle hydrodynamics, control-surface behavior, propeller efficiency curves, hull drag coefficients, payload drag, or maneuvering losses from first principles. Instead, it uses interpretable planning assumptions that can be inspected, tested, and refined with public data or future measured data.

This design is appropriate for thesis-level sustainment analysis because the research question centers on mission energy burden and logistics sensitivity rather than detailed vehicle design.

## Public Manufacturer Baseline Approach

The active vehicle catalog uses public baseline data from representative small and medium UUV families. Detailed platform performance data may be proprietary, restricted, or unavailable in public sources, so the model uses open manufacturer specifications where possible and clearly marked assumptions where values are missing.

The current public baseline includes REMUS, Bluefin, and Iver families. Placeholder vehicles without public baseline support were removed from the active catalog.

## Vehicle Catalog And Source Traceability

Active catalog:

- `data/vehicle_catalog.json`

Supplemental metadata:

- `data/vehicle_source_metadata_v3_2.json`
- `data/source_register.md`
- `data/source_register_v3_2_addendum.md`
- `docs/baseline_data_limitations.md`

The `VehicleState` loader expects the active catalog to match the dataclass schema in `models/vehicle_model.py`. Supplemental metadata is deliberately separate and should not be loaded by `VehicleState` unless the loader is extended.

## Mission-Specific Energy Logic

### Route / Transit

The user-facing route mode is now `Route / Transit`. Internally, the model still accepts legacy `Payload`, `Payload Delivery`, and `Delivery` labels through `PAYLOAD_MISSIONS` for compatibility with older tests, run records, and saved contexts.

Route / Transit uses route distance, optional return-to-start, additional transit distance, selected speed, current direction, current speed, the low Route / Transit sensor-mode range, salinity burden when available, and battery temperature capacity derating.

Energy is based on duration multiplied by speed-adjusted vehicle power plus the sampled low sensor-mode term, then adjusted by environmental uplift. Return-to-start adds a return leg using reciprocal heading.

Planning basis:

- `planning_energy_basis = "mission_total"`
- `planning_duration_basis = "mission_duration"`

### ISR

ISR uses a patrol loop distance derived from line out-and-back, polygon perimeter, or rectangle perimeter geometry. The model estimates endurance at the selected patrol speed, adjusted by speed-power, environmental burden, and the sampled ISR sensor-mode power term.

ISR reporting distinguishes:

- one installed battery set endurance
- total available inventory endurance
- patrol loop time
- full loop count
- partial next-loop distance
- total patrol distance before recovery or battery exhaustion

Planning basis:

- `planning_energy_basis = "mission_total"`
- `planning_duration_basis = "endurance_window"`

### Search/MCM

Search/MCM uses search area geometry, track spacing, global mission speed, current burden, salinity burden when available, battery temperature capacity derating, sampled mission sensor-mode power, and recommended track orientation. The model evaluates north-south and east-west search plans and selects the lower-energy option.

Search/MCM energy is segment-aware. Active search/survey time carries the Search/MCM sensor-mode range, while additional transit distance uses the low Route / Transit sensor-mode range rather than the full active survey load.

For multi-area Search/MCM, selected areas are represented as a `MissionAreaSet`. The current energy path uses an aggregate equivalent search area so existing Search/MCM energy logic remains compatible. This is a planning simplification and should be revisited if per-area lane rendering becomes a thesis focus.

Planning basis:

- `planning_energy_basis = "mission_total"`
- `planning_duration_basis = "mission_duration"`

## Speed-Power Correction

The model estimates power at requested speed with:

- fixed hotel load fraction
- speed-dependent propulsion load
- cubic propulsion scaling by default

The calibrated helper is `power_model_breakdown()` in `core/power.py`, with `estimate_power_at_speed_kw()` in `core/energy.py` retained as the v3.5 compatibility wrapper for carried-equipment propulsion multipliers. It prevents the model from making higher speeds appear too efficient simply because duration decreases while average power remains fixed.

The assumptions are traceable in `core/assumptions.py`:

- `default_hotel_load_fraction`
- `propulsion_speed_exponent`

Current implementation detail: the default hotel power fraction is `0.40`, with `0.60` of baseline power treated as propulsion at nominal speed. Vehicle catalog entries may optionally provide `hotel_fraction` or `hotel_power_fraction`; when present, the catalog value overrides the default and is clamped to 0.25-0.60. Low-speed behavior is bounded by `min_efficient_speed = 0.65 * nominal_speed`, `low_speed_penalty_fraction = 0.15`, and `low_speed_penalty_cap_fraction = 0.10`.

The project-note hydrodynamic cylinder equations are methodology cross-check equations, not active simulation equations. The implementation remains a weighted operational planning model.

## Mission Sensor-Mode Power

The active model adds a Monte Carlo sampled mission sensor-mode term to the existing vehicle speed-power model. It does not replace hotel load, propulsion scaling, or low-speed correction.

Current model concept:

```text
P_vehicle_speed = P_hotel + P_propulsion + P_low_speed
P_active = P_vehicle_speed + P_sensor_mode
```

Mission sensor-mode ranges are implemented in `sample_mission_sensor_power_kw()`:

- Route / Transit and legacy Payload labels: `Uniform(0 W, 25 W)`
- ISR / Persistence: `Uniform(50 W, 75 W)`
- Search/MCM / Area Search: `Uniform(75 W, 150 W)`

Segment equations:

```text
E_transit = (P_vehicle_speed + P_transit_sensor_mode) * T_transit
E_mission_active = (P_vehicle_speed + P_active_sensor_mode) * T_active
E_total = E_transit + E_mission_active
```

For Search/MCM, `T_active` is the active search/survey duration from the selected lane plan, including turn burden. Additional transit is modeled separately and receives the low Route / Transit sensor range. For ISR, the ISR sensor range is applied across the patrol/on-station endurance window. For Route / Transit, the low sensor range is applied across the moving route duration.

The summary/report exposes:

- `mission_sensor_power_mean_kw`
- `mission_sensor_power_p10_kw`
- `mission_sensor_power_p50_kw`
- `mission_sensor_power_p90_kw`
- `mission_sensor_power_basis`
- `active_sensor_mode`
- `active_sensor_duration_mean_hr`
- `mission_sensor_energy_mean_kwh`
- `transit_sensor_power_mean_kw`
- `total_active_power_p50_kw`

The basis is also registered in `core/assumptions.py` under `mission_sensor_mode_power_ranges`.

## Current Direction And METOC Burden

Current is decomposed relative to mission heading where needed. Route / Transit uses route heading and return heading. Search/MCM uses track heading. ISR applies a modest station-keeping/current burden relative to endurance speed.

Multi-area Search/MCM uses one METOC lookup per area centroid. Current is vector averaged rather than angle averaged:

- `u = speed * sin(direction)`
- `v = speed * cos(direction)`
- aggregate speed is vector magnitude
- aggregate direction is converted back to compass degrees

Scalar environmental values such as sea surface temperature and wind speed are averaged normally.

Salinity is carried as `sea_surface_salinity_psu` when available from NOAA CO-OPS, NOAA WOA23, a loaded mission context, or the standard seawater fallback. Open-Meteo Marine currently rejects `sea_surface_salinity`, so the live request omits that variable and records the omission in query traceability. Standalone/manual simulations use the standard seawater assumption and do not call live salinity providers. Mission Builder/GPS geometry preserves Open-Meteo current, SST, wind, and weather, then attempts NOAA CO-OPS station salinity, NOAA WOA23 climatology, and standard seawater in that order. Salinity is displayed for traceability, and multi-area salinity/density are scalar-averaged when present. When salinity is present and deviates from 35 PSU, the model applies a bounded salinity/buoyancy planning uplift. Standard seawater is 35.0 PSU and 1025.0 kg/m3, so no salinity uplift is applied.

NOAA CO-OPS station salinity is only valid where a relevant station exists near the mission area and returns a salinity product. NOAA WOA23 is climatological/historical, not live tactical METOC. Standard seawater fallback is used when station/grid data is unavailable. Copernicus was evaluated during development and removed from the active v3.5 salinity chain. HYCOM/GOFS, SMAP, and Argo remain future enhancement or V&V sources only. Salinity and density inputs are planning modifiers only and are not tactical oceanographic authority.

## Carried Equipment Mass Burden

Route / Transit supports an optional carried equipment weight input. The legacy summary fields retain `payload_weight_*` names for compatibility, but the UI/report language uses carried equipment rather than kinetic-delivery payload. The empirical planning multiplier is:

```text
penalty_pct = (payload_weight_kg / vehicle_energy_kwh) * 0.30
weight_penalty_multiplier = 1.0 + min(5.0, max(0.0, penalty_pct)) / 100.0
```

The multiplier applies to outbound propulsion power only, not fixed hotel load. The carried-equipment burden does not rely on public dry-weight data; equipment mass is treated as a bounded trim/integration planning penalty scaled against vehicle energy class because weight alone is not a direct hydrodynamic drag variable. Equipment-specific drag modeling is future work if area, Cd, mounting, buoyancy, and trim data become available. For return-to-start route missions, outbound and added transit burden carry the equipment while the return leg is unburdened. One-way mode uses outbound route energy only. Search/MCM and ISR ignore carried equipment weight.

Recoverable Route / Transit missions include a small launch/recovery overhead using `0.25 hr * 0.5 * average_power_kw`. One-way/non-recoverable catalog entries do not receive that overhead and use clean one-way/non-rechargeable report wording. Sprint/hibernate/deploy phasing remains deferred.

## Battery Inventory And Reserve Logic

Vehicle usable energy is currently:

`usable_battery_per_set_kwh = battery_kwh * sampled_usable_fraction * temperature_capacity_factor * (1 - operator_reserve_fraction)`

The active public baseline generally centers on an 88 percent usable fraction. The Monte Carlo now samples practical battery condition separately from operator reserve margin. Battery condition captures starting state, field use, and battery-health uncertainty. Operator reserve remains a separate factor and is not used to hide battery health variation.

Temperature derating uses the named `lithium_temperature_capacity_derating_v1` curve. Temperature reduces available battery capacity and is not also applied as a mission energy demand uplift. Current, speed-power, and salinity affect energy demand.

The original temperature derating rule captured the correct degradation direction but capped severe cold at 25 percent. After comparison with Bressan-style LiFePO4 capacity-loss anchors, the model was updated to a table-driven derating curve that preserves the no-penalty operating band while aligning the cold-side planning penalty with experimental capacity-loss evidence.

Battery inventory is represented by the number of battery sets available. For ISR, reporting separates one installed set from total available inventory. For Route / Transit and Search/MCM, reports focus on mission-total energy, battery sets required, and shortfall.

## Monte Carlo Uncertainty Interpretation

The model samples current, temperature capacity factor, usable battery fraction, vehicle speed-power parameters, and mission sensor-mode power around selected or loaded planning assumptions. Output percentiles are:

- P50: expected estimate
- P80: planning-level estimate
- P95: conservative estimate

The uncertainty distribution is a planning lens. It does not represent a fully validated probabilistic ocean model.

## Sustainment Projection Lens

The Sustainment Projection Lens is an energy-flow planning lens, not a fleet optimizer. By default, simulator runs report a single-mission case over a one-week timeframe. Operators can enable the optional Mission sustainment projection lens to edit tempo, horizon, and generator efficiency. The report projects conservative mission energy over the selected planning horizon and reports total energy demand, available inventory energy per cycle, approximate full inventory recharge cycles, recharge energy required, and generator input energy at the selected efficiency. It also reports a secondary fuel-equivalent estimate using `generator_input_energy_kwh / 10.0` with the label JP-8/diesel tactical-generator planning factor. This is a sustainment-planning estimate, not a generator certification curve.

## Planning Basis Definitions

### mission_total

`mission_total` means planning energy is the energy required for the whole modeled mission instance. Route / Transit, Search/MCM, and ISR all use this energy basis. ISR differs in that its duration basis is the endurance window.

### patrol_loop

`patrol_loop` remains a geometry and coverage-accounting concept for ISR. It is not the active ISR planning-energy basis; ISR planning energy is now the total endurance-window mission energy expended across the completed and partial loop set.

### endurance_window

`endurance_window` means the available time or energy window before recovery, swap, or battery exhaustion. ISR uses this duration basis while retaining loop distance and loop count for patrol coverage reporting.

## Limitations And Future Work

- See `docs/implementation_kanban.md` for the current implementation-only development board.
- See `docs/current_logic_and_equations.md` for the compact equation and current-logic reference.
- Add vehicle-specific mission sensor-mode overrides if public platform configuration data supports them.
- Add hibernate/sprint phase logic for route/transit missions that require long loiter periods.
- Improve per-area Search/MCM lane rendering instead of aggregate equivalent area only.
- Add contested-delay/loiter interruption model.
- Expand thesis documentation with assumption provenance, validation scenarios, and sensitivity analysis.
- Confirm v4 beta app, energy model, and vehicle catalog version labels during manual release review.
