# Implementation Kanban

Source basis: local project files and `UUV Project file Notes.md`. This board is limited to implementation and development work. The project file notes do not require further research for this backlog.

## Done

| Item | Implementation state | Local references |
| --- | --- | --- |
| Use kWh as the core energy unit | Core loops use kWh/kW for battery and mission-energy planning. Joule, MJ, and GJ equivalents are derived only for reporting. | `core/energy.py::energy_equivalent_rows` |
| Split baseline power into hotel and propulsion components | `estimate_power_at_speed_kw()` keeps a fixed hotel load and applies cubic speed scaling to propulsion load. Catalog `hotel_fraction` overrides are supported and clamped; missing values use the global default of `0.35`. | `core/energy.py::estimate_power_at_speed_kw`, `models/vehicle_model.py`, `core/assumptions.py` |
| Battery usable fraction and reserve margin | Vehicle catalog carries a legacy `usable_fraction`, while the current Monte Carlo samples usable battery fraction by condition. Operator reserve margin remains a separate factor. | `core/battery.py`, `models/vehicle_model.py`, `data/vehicle_catalog.json` |
| Mission energy percentiles | Monte Carlo runs produce P50, P80, P95, mean energy, and mean duration. | `core/energy.py::run_energy_simulation` |
| Battery shortfall and recharge downtime | Model compares P80 demand to battery inventory, computes battery shortfall, recharge/swap sequences, and downtime when recharge is enabled. | `core/energy.py::run_energy_simulation` |
| Payload route energy | Payload Delivery supports line-route distance, optional return to start, added transit distance, current burden, speed-power correction, battery temperature capacity derating, and mission sequences. | `core/energy.py`, `core/geometry.py` |
| Search/MCM lane orientation comparison | Search/MCM evaluates north-south and east-west lane plans, applies current/temperature burden, and selects the lower-energy orientation. | `core/energy.py::search_plan`, `core/geometry.py::clipped_search_lanes` |
| ISR loop endurance | ISR computes loop distance, loop time, single-set endurance, total-inventory endurance, completed loops, partial loop coverage, and patrol distance. | `core/energy.py::compute_isr_persistence`, `core/geometry.py::isr_path_distance_per_loop_km` |
| METOC representative point logic | Single-area search uses centroid; payload uses route midpoint; ISR uses first patrol point. Multi-area Search/MCM uses each area centroid and vector-averages current. | `core/mission.py` |
| Current and environmental burden | Payload current, search current, ISR station-keeping/current burden, and salinity burden are implemented as simplified planning factors. Temperature reduces usable battery capacity instead of adding mission-energy demand uplift. | `core/environment.py`, `core/battery.py`, `core/energy.py::isr_current_power_penalty` |
| Model assumptions registry | Core assumptions are exposed through `core/assumptions.py`, including speed-power, salinity, battery, temperature, sustainment, and payload-mass planning assumptions. | `core/assumptions.py` |
| Planning-basis fields | Reports use mission-total planning energy for Payload, ISR, and Search/MCM. ISR retains patrol-loop metrics only for coverage accounting. | `core/energy.py`, `app/ui/reporting.py` |
| Multi-area Search/MCM backend | Backend supports `MissionAreaSet`, centroid METOC sampling, vector-averaged current, scalar-averaged salinity/density, aggregate equivalent area, and sampled-point reporting. | `core/mission.py`, `core/geometry.py`, `models/mission_model.py` |
| Salinity environment data foundation | Salinity is represented in `EnvironmentData`, parsed if present in a payload, shown in environment table rows, averaged for multi-area missions, and preserved in internal run records. Open-Meteo Marine does not currently accept `sea_surface_salinity`, so the live marine request omits it and records that status in query traceability. | `services/marine_api.py`, `models/environment_model.py`, `core/mission.py`, `services/run_logger.py` |
| Salinity/buoyancy planning penalty | Salinity now contributes a bounded energy uplift when salinity is present and deviates from 35 PSU. Missing salinity and 35 PSU preserve current behavior. | `core/environment.py::salinity_buoyancy_penalty`, `core/energy.py` |
| Salinity provider chain | Mission Builder/GPS geometry attempts NOAA CO-OPS station salinity, NOAA WOA23 climatology, then standard seawater. Copernicus was removed from the active v3.5 chain. | `services/noaa_coops_salinity.py`, `services/woa23_salinity.py`, `services/metoc_fusion.py` |
| Automatic salinity policy | Standalone/manual simulations use the standard seawater assumption and do not call live salinity providers. GPS missions preserve Open-Meteo values even when salinity providers are unavailable. | `app/main.py`, `services/metoc_fusion.py`, `core/mission.py` |
| Stochastic usable battery fraction | Monte Carlo now samples practical usable battery fraction by Low/Medium/High battery condition, separate from operator reserve and temperature derating. | `core/battery.py`, `core/energy.py`, `app/main.py` |
| Temperature derating refinement | Temperature now reduces usable battery capacity through `lithium_temperature_capacity_derating_v1`; it is no longer double-counted as a demand-side energy uplift. | `core/battery.py`, `core/energy.py` |
| Sustainment Projection Lens | Simplified energy-flow projection added for operations per week, planning horizon, available inventory cycles, recharge energy, and generator input energy. | `core/sustainment.py`, `app/ui/reporting.py`, `app/main.py` |
| Energy-class payload penalty | Payload Delivery has an optional payload weight input in kg. The model applies a bounded energy-class-scaled propulsion penalty, not a dry-weight ratio. Search/MCM and ISR are unchanged by payload weight. | `app/main.py`, `core/energy.py`, `services/run_logger.py`, `app/ui/reporting.py` |
| One-way payload logic | Payload missions support return-to-start and one-way/no-return recovery modes. Catalog one-way/non-rechargeable entries default to one-way payload planning and clean replacement-inventory wording. | `core/energy.py`, `data/vehicle_catalog.json`, `app/ui/reporting.py` |
| Launch/recovery overhead | Recoverable payload missions add a small planning overhead using 0.25 hr at 0.5 times average power. One-way/non-recoverable missions receive zero overhead. | `core/energy.py`, `core/assumptions.py` |
| Public-facing vehicle catalog expansion | Active catalog now includes the validated project-note public-facing systems: Lionfish, Yellow Moray, Viperfish, Iver3 580, Iver4 900, MK19/MK20 Razorback, AN/AQS-23 Barracuda, and Next-Gen MUUV (REMUS 620). | `data/vehicle_catalog.json`, `data/vehicle_source_metadata_v3_2.json`, `data/source_register_v3_2_addendum.md` |

## In Progress

| Item | Implementation state | Next development action |
| --- | --- | --- |
| Release labeling and manual UI review | Code constants and primary docs use the v3.5 beta label; manual UI testing remains a team-testing activity. | Confirm visible build label, report language, and tab-navigation text during manual UI testing. |

## Next

| Item | Scope | Acceptance criteria |
| --- | --- | --- |
| Add mission phasing for hibernate/sprint payload missions | Represent outbound transit, hibernate/loiter, and final deployment as separate energy states instead of one averaged phase. | Payload missions can model long low-power loiter without inflating transit power or hiding final deployment cost. |
| Wave-height correction | Add optional sea-state effect for launch/recovery or support craft constraints without turning the model into a seakeeping simulator. | Wave/seastate note appears separately from energy demand unless a bounded planning factor is selected. |

## Phase Plan

### Phase 1: Environment Data Foundation - Complete

Goal: add salinity as a traceable input without changing mission energy unless salinity is present and explicitly used.

Implementation tasks:

- Extend `EnvironmentData` with salinity fields and table-row output.
- Add salinity to `services/marine_api.py` query parameters when supported by the API response.
- Preserve raw payload and query-parameter traceability in internal run records.
- Update multi-area aggregation to average salinity as a scalar value.
- Add tests for API parsing, environment merge behavior, aggregation, and missing-value fallback.

Exit criteria:

- Existing simulations remain numerically unchanged when salinity is unavailable.
- Salinity appears in environmental inputs and internal traceability records when available.

Implemented:

- `EnvironmentData.sea_surface_salinity_psu`
- Response parsing for `sea_surface_salinity`, `ocean_salinity`, and `salinity` when present in a payload
- Open-Meteo Marine request guarded to omit unsupported `sea_surface_salinity`
- Multi-area scalar salinity aggregation
- Environment table-row display
- Internal planner field
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

- Energy only changes when salinity is available from Mission Builder salinity enrichment or supplied mission context.
- Reports identify the salinity uplift separately from temperature and current.

Implemented:

- `core.environment.salinity_buoyancy_penalty()`
- Additive environmental uplift for payload, ISR, and Search/MCM mission energy
- Summary field `salinity_uplift_pct`
- Report rows for salinity uplift and sea-surface salinity
- Internal planner field `salinity_uplift_pct`
- Assumption registry entry `salinity_buoyancy_penalty_curve`
- Regression tests for missing salinity, reference salinity, bounded penalty, and energy increase

### Phase 3: Payload Mass Logic - Complete

Goal: add payload weight as an optional mission input and apply an energy-class-scaled planning penalty.

Implementation tasks:

- Add `payload_weight_kg` to UI inputs, callback signatures, run logger inputs, and internal traceability records.
- Implement:

```text
penalty_pct = (payload_weight_kg / vehicle_energy_kwh) * 0.30
weight_penalty_multiplier = 1.0 + min(5.0, max(0.0, penalty_pct)) / 100.0
```

- Apply the multiplier to propulsion power only, not fixed hotel load.
- Treat payload weight as a bounded trim/integration planning penalty because payload weight alone is not a direct hydrodynamic drag variable.
- Leave payload-specific drag modeling as future work if area, Cd, mounting, buoyancy, and trim data become available.
- Add tests confirming zero payload preserves current output and heavier payload increases energy.

Exit criteria:

- Payload Delivery can model payload mass without changing Search/MCM or ISR behavior.
- Payload burden does not require public dry-weight data.

Implemented:

- Payload weight UI input and helper text
- Callback, simulation-input, report, and run-logger fields
- Propulsion-only energy-class multiplier
- Outbound payload burden with return leg unburdened when return-to-start is selected
- No active dry-weight dependency
- Regression tests for payload monotonicity and Search/MCM/ISR non-effect

### Phase 4: Launch/Recovery Energy Tax - Complete

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

Implemented:

- `recoverable`, `rechargeable`, and `default_payload_recovery_mode` catalog flags
- Zero launch/recovery overhead for one-way/non-recoverable payload profiles
- Clean one-way/non-rechargeable report wording
- Regression tests for recoverable and one-way payload profiles

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

### Phase 6: Sustainment And Catalog Refinement - Partial

Goal: expose the simplified sustainment lens and clean up vehicle-specific assumptions.

Implementation tasks:

- Add UI controls for operations per week, planning horizon, and generator efficiency.
- Surface `compute_sustainment_projection()` output in the Results tab.
- Parameterize hotel fraction by vehicle or configuration while preserving `0.35` default. Complete.
- Add one-way/non-rechargeable report wording for catalog entries with `recharge_hr = 0.0`. Complete.
- Confirm v3.5 beta release labels during manual UI review.

Exit criteria:

- The app reports single-mission energy and campaign-level recharge/inventory-cycle implications from the same run.
- Vehicle-specific assumptions are visible and traceable.

## Later

| Item | Scope | Acceptance criteria |
| --- | --- | --- |
| Contested-delay loiter interruptions | Add stochastic hover/loiter delays for ISR or recovery windows. | Delays increase duration and energy through documented phase logic. |
| Per-area Search/MCM lanes | Replace aggregate equivalent square with per-area lane planning and reporting. | Multi-area output preserves each area's lane count, track distance, and METOC sample. |
| Full fleet optimizer | Expand beyond single-UUV/inventory-cycle planning into multi-vehicle scheduling only after thesis scope requires it. | Fleet outputs are explicit and do not replace current single-UUV planning result. |
| Full `run_energy_simulation()` refactor | Split payload, ISR, and Search/MCM branches into mission-specific helpers. | Test coverage remains equivalent and output schema is preserved. |
| Fuel gallons conversion | Keep fuel conversion secondary unless a generator-specific certified curve is selected for this project. | Report labels keep the 10.0 kWh/gal JP-8/diesel factor as a planning lens, not a certified generator curve. |
