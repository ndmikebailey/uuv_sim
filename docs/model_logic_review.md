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

### Payload

Payload Delivery uses route distance, optional return-to-start, additional transit distance, selected speed, current direction, current speed, and temperature burden.

Energy is based on duration multiplied by speed-adjusted vehicle power, then adjusted by environmental uplift. Return-to-start adds a return leg using reciprocal heading.

Planning basis:

- `planning_energy_basis = "mission_total"`
- `planning_duration_basis = "mission_duration"`

### ISR

ISR uses a patrol loop distance derived from line out-and-back, polygon perimeter, or rectangle perimeter geometry. The model estimates endurance at the selected patrol speed, adjusted by speed-power and environmental burden.

ISR reporting distinguishes:

- one installed battery set endurance
- total available inventory endurance
- patrol loop time
- full loop count
- partial next-loop distance
- total patrol distance before recovery or battery exhaustion

Planning basis:

- `planning_energy_basis = "patrol_loop"`
- `planning_duration_basis = "patrol_loop_time"`

### Search/MCM

Search/MCM uses search area geometry, track spacing, global mission speed, current burden, temperature burden, and recommended track orientation. The model evaluates north-south and east-west search plans and selects the lower-energy option.

For multi-area Search/MCM, selected areas are represented as a `MissionAreaSet`. The current energy path uses an aggregate equivalent search area so existing Search/MCM energy logic remains compatible. This is a planning simplification and should be revisited if per-area lane rendering becomes a thesis focus.

Planning basis:

- `planning_energy_basis = "mission_total"`
- `planning_duration_basis = "mission_duration"`

## Speed-Power Correction

The model estimates power at requested speed with:

- fixed hotel load fraction
- speed-dependent propulsion load
- cubic propulsion scaling by default

The helper is `estimate_power_at_speed_kw()` in `core/energy.py`. It prevents the model from making higher speeds appear too efficient simply because duration decreases while average power remains fixed.

The assumptions are traceable in `core/assumptions.py`:

- `default_hotel_load_fraction`
- `propulsion_speed_exponent`

Current implementation detail: the default hotel fraction is `0.35`, with `0.65` of baseline power treated as propulsion at nominal speed. Vehicle catalog entries may optionally provide `hotel_fraction`; when present, the catalog value overrides the default and is clamped to 0.05-0.85. The project notes include a 20/80 hotel/propulsion option, but that option has not replaced the default for entries without a catalog override.

The project-note hydrodynamic cylinder equations are methodology cross-check equations, not active simulation equations. The implementation remains a weighted operational planning model.

## Current Direction And METOC Burden

Current is decomposed relative to mission heading where needed. Payload uses route heading and return heading. Search/MCM uses track heading. ISR applies a modest station-keeping/current burden relative to endurance speed.

Multi-area Search/MCM uses one METOC lookup per area centroid. Current is vector averaged rather than angle averaged:

- `u = speed * sin(direction)`
- `v = speed * cos(direction)`
- aggregate speed is vector magnitude
- aggregate direction is converted back to compass degrees

Scalar environmental values such as sea surface temperature and wind speed are averaged normally.

Salinity is carried as `sea_surface_salinity_psu` when available from Copernicus Marine or a loaded mission context. Open-Meteo Marine currently rejects `sea_surface_salinity`, so the live request omits that variable and records the omission in query traceability. Standalone/manual simulations use the standard seawater assumption and do not call Copernicus. Mission Builder/GPS geometry attempts Copernicus salinity/density automatically, with Open-Meteo remaining primary for current, SST, wind, and weather. Salinity is displayed for traceability, and multi-area salinity/density are scalar-averaged when present. When salinity is present and deviates from 35 PSU, the model applies a bounded salinity/buoyancy planning uplift. Missing salinity and 35 PSU preserve existing energy behavior.

Copernicus Marine is available as an optional salinity/density provider path. The provider does not hardcode credentials and does not make the app depend on the Copernicus toolbox. When unavailable, it returns a structured salinity error and the mission continues with the standard seawater assumption. Live credentialed validation is pending.

## Payload Mass Burden

Payload Delivery supports an optional payload weight input. The empirical planning multiplier is:

```text
penalty_pct = (payload_weight_kg / vehicle_energy_kwh) * 0.30
weight_penalty_multiplier = 1.0 + min(5.0, max(0.0, penalty_pct)) / 100.0
```

The multiplier applies to outbound propulsion power only, not fixed hotel load. Payload burden does not rely on public dry-weight data; payload mass is treated as a bounded trim/integration planning penalty scaled against vehicle energy class because payload weight alone is not a direct hydrodynamic drag variable. Payload-specific drag modeling is future work if area, Cd, mounting, buoyancy, and trim data become available. For return-to-start payload missions, outbound and added transit burden carry the payload while the return leg is unburdened. One-way mode uses outbound route energy only. Search/MCM and ISR ignore payload weight.

Recoverable payload missions include a small launch/recovery overhead using `0.25 hr * 0.5 * average_power_kw`. One-way/non-recoverable catalog entries do not receive that overhead and use clean one-way/non-rechargeable report wording. Sprint/hibernate/deploy payload phasing remains deferred.

## Battery Inventory And Reserve Logic

Vehicle usable energy is currently:

`usable_battery_per_set_kwh = battery_kwh * sampled_usable_fraction * temperature_capacity_factor * (1 - operator_reserve_fraction)`

The active public baseline generally centers on an 88 percent usable fraction. The Monte Carlo now samples practical battery condition separately from operator reserve margin. Battery condition captures starting state, field use, and battery-health uncertainty. Operator reserve remains a separate factor and is not used to hide battery health variation.

Temperature derating uses the named `lithium_temperature_capacity_derating_v1` curve. Temperature reduces available battery capacity and is not also applied as a mission energy demand uplift. Current, speed-power, and salinity affect energy demand.

Battery inventory is represented by the number of battery sets available. For ISR, reporting separates one installed set from total available inventory. For Payload and Search/MCM, reports focus on mission-total energy, battery sets required, and shortfall.

## Monte Carlo Uncertainty Interpretation

The model samples current, temperature capacity factor, and usable battery fraction around selected or loaded planning assumptions. Output percentiles are:

- P50: expected estimate
- P80: planning-level estimate
- P95: conservative estimate

The uncertainty distribution is a planning lens. It does not represent a fully validated probabilistic ocean model.

## Sustainment Projection Lens

The Sustainment Projection Lens is an energy-flow planning lens, not a fleet optimizer. By default, simulator runs report a single-mission case over a one-week timeframe. Operators can enable the optional Mission sustainment projection lens to edit tempo, horizon, and generator efficiency. The report projects conservative mission energy over the selected planning horizon and reports total energy demand, available inventory energy per cycle, approximate full inventory recharge cycles, recharge energy required, and generator input energy at the selected efficiency.

## Planning Basis Definitions

### mission_total

`mission_total` means planning energy is the energy required for the whole modeled mission instance. Payload and Search/MCM use this basis.

### patrol_loop

`patrol_loop` means planning energy is the estimated energy for one ISR patrol loop. ISR uses this basis because endurance and persistence are better expressed as loop time, endurance window, and total patrol distance.

### endurance_window

`endurance_window` means the available time or energy window before recovery, swap, or battery exhaustion. ISR reports endurance window values, but the current explicit planning energy basis is `patrol_loop`.

## Limitations And Future Work

- See `docs/implementation_kanban.md` for the current implementation-only development board.
- See `docs/current_logic_and_equations.md` for the compact equation and current-logic reference.
- Add payload weight input and mass penalty multiplier.
- Add optional launch/recovery energy tax for recoverable missions.
- Add hibernate/sprint phase logic for payload missions that require long loiter periods.
- Improve per-area Search/MCM lane rendering instead of aggregate equivalent area only.
- Add contested-delay/loiter interruption model.
- Expand thesis documentation with assumption provenance, validation scenarios, and sensitivity analysis.
- Reconcile app version constants with v3.3-beta branch naming before release.
