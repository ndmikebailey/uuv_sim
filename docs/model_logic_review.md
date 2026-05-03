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

Current implementation detail: the active default hotel fraction is `0.35`, with `0.65` of baseline power treated as propulsion at nominal speed. The project notes include a 20/80 hotel/propulsion option, but that option has not replaced the current code default.

The project-note hydrodynamic cylinder equations are methodology cross-check equations, not active simulation equations. The implementation remains a weighted operational planning model.

## Current Direction And METOC Burden

Current is decomposed relative to mission heading where needed. Payload uses route heading and return heading. Search/MCM uses track heading. ISR applies a modest station-keeping/current burden relative to endurance speed.

Multi-area Search/MCM uses one METOC lookup per area centroid. Current is vector averaged rather than angle averaged:

- `u = speed * sin(direction)`
- `v = speed * cos(direction)`
- aggregate speed is vector magnitude
- aggregate direction is converted back to compass degrees

Scalar environmental values such as sea surface temperature and wind speed are averaged normally.

Salinity is carried as `sea_surface_salinity_psu` when available from manual input, future API support, or a supplied payload. Open-Meteo Marine currently rejects `sea_surface_salinity`, so the live request omits that variable and records the omission in query traceability. Salinity is displayed and exported for traceability, and multi-area salinity is scalar-averaged when present. When salinity is present and deviates from 35 PSU, the model applies a bounded salinity/buoyancy planning uplift. Missing salinity and 35 PSU preserve existing energy behavior.

## Battery Inventory And Reserve Logic

Vehicle usable energy is currently:

`usable_battery_per_set_kwh = battery_kwh * usable_fraction`

The active public baseline generally uses an 88 percent usable fraction as a planning reserve and battery-health allowance. This is an assumption, not a measured platform-specific value for every vehicle.

Battery inventory is represented by the number of battery sets available. For ISR, reporting separates one installed set from total available inventory. For Payload and Search/MCM, reports focus on mission-total energy, battery sets required, and shortfall.

## Monte Carlo Uncertainty Interpretation

The model samples current and temperature around the selected or loaded environmental means. Output percentiles are:

- P50: expected estimate
- P80: planning-level estimate
- P95: conservative estimate

The uncertainty distribution is a planning lens. It does not represent a fully validated probabilistic ocean model.

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
- Add stochastic usable battery fraction model.
- Refine temperature derating with literature or test data.
- Add payload weight input and mass penalty multiplier.
- Add optional launch/recovery energy tax for recoverable missions.
- Add hibernate/sprint phase logic for payload missions that require long loiter periods.
- Add Sustainment Projection Lens UI using existing backend helpers.
- Improve per-area Search/MCM lane rendering instead of aggregate equivalent area only.
- Add contested-delay/loiter interruption model.
- Expand thesis documentation with assumption provenance, validation scenarios, and sensitivity analysis.
- Reconcile app version constants with v3.3-beta branch naming before release.
