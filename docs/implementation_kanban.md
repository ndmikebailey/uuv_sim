# Implementation Kanban

Source basis: local project files and `UUV Project file Notes.md`. This board is limited to implementation and development work. The project file notes do not require further research for this backlog.

## Done

| Item | Implementation state | Local references |
| --- | --- | --- |
| Use kWh as the core energy unit | Core loops use kWh/kW for battery and mission-energy planning. Joule, MJ, and GJ equivalents are derived only for reporting. | `core/energy.py::energy_equivalent_rows` |
| Split baseline power into hotel and propulsion components | `estimate_power_at_speed_kw()` keeps a fixed hotel load and applies cubic speed scaling to propulsion load. Current code default is `hotel_fraction = 0.35`, not the 20/80 split proposed in the notes. | `core/energy.py::estimate_power_at_speed_kw`, `core/assumptions.py` |
| Battery usable fraction and reserve margin | Vehicle catalog carries `usable_fraction`; usable energy per set is `battery_kwh * usable_fraction`. Active catalog generally uses `0.88`. | `models/vehicle_model.py`, `data/vehicle_catalog.json` |
| Mission energy percentiles | Monte Carlo runs produce P50, P80, P95, mean energy, and mean duration. | `core/energy.py::run_energy_simulation` |
| Battery shortfall and recharge downtime | Model compares P80 demand to battery inventory, computes battery shortfall, recharge/swap sequences, and downtime when recharge is enabled. | `core/energy.py::run_energy_simulation` |
| Payload route energy | Payload Delivery supports line-route distance, optional return to start, added transit distance, current burden, speed-power correction, temperature uplift, and mission sequences. | `core/energy.py`, `core/geometry.py` |
| Search/MCM lane orientation comparison | Search/MCM evaluates north-south and east-west lane plans, applies current/temperature burden, and selects the lower-energy orientation. | `core/energy.py::search_plan`, `core/geometry.py::clipped_search_lanes` |
| ISR loop endurance | ISR computes loop distance, loop time, single-set endurance, total-inventory endurance, completed loops, partial loop coverage, and patrol distance. | `core/energy.py::compute_isr_persistence`, `core/geometry.py::isr_path_distance_per_loop_km` |
| METOC representative point logic | Single-area search uses centroid; payload uses route midpoint; ISR uses first patrol point. Multi-area Search/MCM uses each area centroid and vector-averages current. | `core/mission.py` |
| Temperature and current uplift | Temperature, payload current, search current, and ISR station-keeping/current burden are implemented as simplified planning factors. | `core/environment.py`, `core/energy.py::isr_current_power_penalty` |
| Salinity environment data foundation | Salinity is represented in `EnvironmentData`, parsed if present in a payload, shown in environment table rows, averaged for multi-area missions, and exported in run records. Open-Meteo Marine does not currently accept `sea_surface_salinity`, so the live marine request omits it and records that status in query traceability. | `services/marine_api.py`, `models/environment_model.py`, `core/mission.py`, `services/run_logger.py` |
| Salinity/buoyancy planning penalty | Salinity now contributes a bounded energy uplift when salinity is present and deviates from 35 PSU. Missing salinity and 35 PSU preserve current behavior. | `core/environment.py::salinity_buoyancy_penalty`, `core/energy.py` |

## In Progress

| Item | Implementation state | Next development action |
| --- | --- | --- |
| Multi-area Search/MCM | Backend supports `MissionAreaSet`, centroid METOC sampling, and aggregate equivalent area. Energy logic currently treats total area as one equivalent square. | Add per-area lane energy and rendering when search geometry fidelity becomes a release requirement. |
| Sustainment planning lens | Backend helper estimates stockpile demand, generator input energy, and fuel-gallon equivalent, but it is not fully surfaced as an operator-facing workflow. | Add UI controls for missions per week, planning horizon, generator efficiency, and fuel-energy basis; connect to existing helper. |
| Assumptions traceability | `core/assumptions.py` exposes core assumptions, but new project-note assumptions are not all represented as registry rows. | Add registry entries as each new logic item is implemented. |

## Next

| Item | Scope | Acceptance criteria |
| --- | --- | --- |
| Add payload weight input | Add `payload_weight_kg` to UI inputs, run logger, simulation inputs, and tests. | Zero payload is exactly current behavior; heavier payload increases propulsion energy through a bounded multiplier. |
| Add mass penalty multiplier | Implement `mass_increase_pct = payload_weight_kg / vehicle_dry_weight_kg` and `weight_penalty_multiplier = 1.0 + (mass_increase_pct * 0.5)` after adding dry-weight data or a conservative default. | Unit tests show monotonic energy increase with payload weight; missing dry weight is handled explicitly. |
| Add launch/recovery energy tax | Add optional recovery time and low-speed/high-hotel load energy for recoverable vehicles. | Recoverable missions reserve additional time/energy; expendable or one-way cases can set the tax to zero. |
| Add mission phasing for hibernate/sprint payload missions | Represent outbound transit, hibernate/loiter, and final deployment as separate energy states instead of one averaged phase. | Payload missions can model long low-power loiter without inflating transit power or hiding final deployment cost. |
| Add expendable vehicle handling | Support catalog entries with `recharge_hr = 0.0` and `usable_fraction = 1.0` as one-way/non-rechargeable logic, with clear report wording. | Expendable entries do not produce recharge downtime and are labeled as one-way/non-rechargeable in reports. |
| Parameterize hotel fraction | Expose hotel fraction through assumptions/config or vehicle catalog, while preserving current default of `0.35`. | Existing tests pass with default; vehicle-specific values override the global default. |

## Phase Plan

### Phase 1: Environment Data Foundation - Complete

Goal: add salinity as a traceable input without changing mission energy unless salinity is present and explicitly used.

Implementation tasks:

- Extend `EnvironmentData` with salinity fields and table-row output.
- Add salinity to `services/marine_api.py` query parameters when supported by the API response.
- Preserve raw payload and query-parameter traceability in run records.
- Update multi-area aggregation to average salinity as a scalar value.
- Add tests for API parsing, environment merge behavior, aggregation, and missing-value fallback.

Exit criteria:

- Existing simulations remain numerically unchanged when salinity is unavailable.
- Salinity appears in environmental inputs and exported run records when available.

Implemented:

- `EnvironmentData.sea_surface_salinity_psu`
- Response parsing for `sea_surface_salinity`, `ocean_salinity`, and `salinity` when present in a payload
- Open-Meteo Marine request guarded to omit unsupported `sea_surface_salinity`
- Multi-area scalar salinity aggregation
- Environment table-row display
- Energy planner CSV field
- Regression tests for API parsing, merge/table rows, and multi-area aggregation

### Phase 2: Salinity/Buoyancy Energy Penalty - Complete

Goal: convert salinity from a displayed environmental input into a bounded planning multiplier.

Implementation tasks:

- Add a small helper in `core/environment.py` for salinity/buoyancy uplift.
- Keep the penalty bounded and default to zero when salinity is missing.
- Add summary fields such as `salinity_uplift_pct` and include them in reports.
- Register the assumption in `core/assumptions.py`.
- Add unit tests proving zero-missing behavior and monotonic penalty behavior.

Exit criteria:

- Energy only changes when salinity input is available or manually supplied.
- Reports identify the salinity uplift separately from temperature and current.

Implemented:

- `core.environment.salinity_buoyancy_penalty()`
- Additive environmental uplift for payload, ISR, and Search/MCM mission energy
- Summary field `salinity_uplift_pct`
- Report rows for salinity uplift and sea-surface salinity
- Energy planner CSV field `salinity_uplift_pct`
- Assumption registry entry `salinity_buoyancy_penalty_curve`
- Regression tests for missing salinity, reference salinity, bounded penalty, and energy increase

### Phase 3: Payload Mass Logic

Goal: add payload weight as an optional mission input and apply the empirical mass penalty from the project notes.

Implementation tasks:

- Add `payload_weight_kg` to UI inputs, callback signatures, run logger inputs, and exported run records.
- Extend vehicle data or assumptions to provide `vehicle_dry_weight_kg`.
- Implement:

```text
mass_increase_pct = payload_weight_kg / vehicle_dry_weight_kg
weight_penalty_multiplier = 1.0 + (mass_increase_pct * 0.5)
```

- Apply the multiplier to propulsion power only, not fixed hotel load.
- Add tests confirming zero payload preserves current output and heavier payload increases energy.

Exit criteria:

- Payload Delivery can model payload mass without changing Search/MCM or ISR behavior.
- Missing dry-weight data is handled with an explicit assumption or validation message.

### Phase 4: Launch/Recovery Energy Tax

Goal: add recoverable-vehicle end-of-mission reserve burden without forcing one-way/expendable missions into recharge logic.

Implementation tasks:

- Add recovery-time and recovery-power assumptions to `core/assumptions.py`.
- Add a recoverable/expendable catalog or derived behavior flag.
- Apply recovery tax after mission movement energy for recoverable profiles.
- Keep recovery tax disabled for one-way/expendable profiles.
- Add report rows showing recovery energy, recovery time, and total elapsed time.

Exit criteria:

- Recoverable missions show added recovery burden.
- Expendable missions remain one-way and do not create recharge downtime.

### Phase 5: Mission Phasing

Goal: model payload missions with distinct phases instead of one averaged power state.

Implementation tasks:

- Add phase objects or helper functions for transit, hibernate/loiter, deployment, and recovery.
- Keep the existing payload path as the default simple case.
- Add hibernate duration and low-power draw assumptions.
- Summarize phase energy and phase duration in report tables.
- Add tests for outbound-only, return-to-start, hibernate, and one-way cases.

Exit criteria:

- Payload missions can represent sprint/hibernate/deploy behavior while preserving current simple route behavior.
- Phase totals reconcile to mission-total energy and duration.

### Phase 6: Sustainment And Catalog Refinement

Goal: expose the backend sustainment helper and clean up vehicle-specific assumptions.

Implementation tasks:

- Add UI controls for missions per week, planning horizon, generator efficiency, and fuel energy basis.
- Surface `compute_stockpile_requirement()` output in the Results tab.
- Parameterize hotel fraction by vehicle or configuration while preserving `0.35` default.
- Add one-way/non-rechargeable report wording for catalog entries with `recharge_hr = 0.0`.
- Reconcile version labels before formal release.

Exit criteria:

- The app reports single-mission energy and campaign-level stockpile/recharge implications from the same run.
- Vehicle-specific assumptions are visible and traceable.

## Later

| Item | Scope | Acceptance criteria |
| --- | --- | --- |
| Stochastic usable battery fraction | Sample usable fraction around catalog value to reflect battery health/reserve uncertainty. | Monte Carlo output includes battery uncertainty and remains reproducible by seed. |
| Contested-delay loiter interruptions | Add stochastic hover/loiter delays for ISR or recovery windows. | Delays increase duration and energy through documented phase logic. |
| Vehicle dry-weight catalog extension | Extend `VehicleState` and catalog schema to support mass penalty logic. | Loader validates old/new catalog values cleanly or migration is explicit. |
| Per-area Search/MCM lanes | Replace aggregate equivalent square with per-area lane planning and reporting. | Multi-area output preserves each area's lane count, track distance, and METOC sample. |
| Release labeling cleanup | Reconcile branch, app version, energy model version, and docs before next formal release. | Constants, docs, and release notes use one consistent version label. |
