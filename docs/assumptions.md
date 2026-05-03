# Model Assumptions

This document tracks assumptions that affect UUV mission energy estimates.

## Vehicle Catalog

Vehicle assumptions are loaded from `data/vehicle_catalog.json`.

* REMUS 300 entries are planning baselines from manufacturer-published REMUS 300 information.
* Public-facing system mappings from `UUV Project file Notes.md` are active catalog entries and are recorded in `data/source_register_v3_2_addendum.md`.

## Energy Model

* Average platform power is estimated as nameplate battery energy divided by estimated endurance.
* Battery usable planning energy is `battery_kwh * usable_fraction`.
* Core energy calculations use kWh and kW. Joules, MJ, and GJ are derived for reporting only.
* Requested-speed power is split into fixed hotel load and speed-dependent propulsion load. Current implementation uses `hotel_fraction = 0.35` and `speed_exponent = 3.0`.
* Practical usable battery fraction is sampled by battery condition. This is separate from operator reserve margin and temperature derating.
* Temperature derating uses `lithium_temperature_capacity_derating_v1` as a usable-capacity factor, not as a duplicate mission-energy uplift.
* Search missions compare North-South and East-West swath plans and select the lower sampled energy burden.
* Search turns use the carried-forward planning assumption of `0.01 hr` duration burden per turn plus a turn-distance estimate.
* Battery shortfall uses P80 mission energy. Recharge/swap downtime is `battery_shortfall_p80 * recharge_hr` only when recharge is enabled.

## Environmental Uplift

* Current direction is treated as direction of flow.
* Payload missions apply a cross-current energy penalty.
* Search missions apply along-current and cross-current duration multipliers.
* ISR missions apply a modest station-keeping/current power burden relative to selected endurance speed.
* Temperature penalties are:
  * below 15 deg C: `min(0.25, (15 - temp_c) * 0.01)`
  * above 32 deg C: `min(0.15, (temp_c - 32) * 0.005)`
* Standalone/manual simulations use the standard seawater assumption and do not call Copernicus Marine. Mission Builder/GPS geometry attempts Copernicus salinity/density automatically through METOC fusion, while Open-Meteo remains primary for current, SST, wind, and weather.
* Salinity is preserved as `sea_surface_salinity_psu` when available from Copernicus Marine or a loaded mission context. Open-Meteo Marine does not currently accept `sea_surface_salinity`, so the live marine request omits that variable and records the omission in query traceability.
* Salinity/buoyancy uplift is a bounded planning penalty: `min(0.10, abs(salinity_psu - 35.0) * 0.005)`. Missing salinity and exactly 35 PSU produce zero salinity uplift.
* Copernicus Marine salinity/density is optional and credential-safe. If unavailable, the app keeps Open-Meteo METOC values and uses the standard seawater assumption.
* Payload Delivery applies an optional payload-weight burden to outbound propulsion power only: `1 + min(5, max(0, (payload_weight_kg / vehicle_energy_kwh) * 0.30)) / 100`. Payload burden does not rely on public dry-weight data; payload mass is treated as a bounded trim/integration planning penalty scaled against vehicle energy class because payload weight alone is not a direct hydrodynamic drag variable. Payload-specific drag modeling is future work if area, Cd, mounting, buoyancy, and trim data become available.
* Recoverable Payload Delivery missions add a small launch/recovery overhead. One-way/non-recoverable missions do not.

## Sustainment Projection

* Sustainment Projection Lens is a simplified energy-flow lens, not a fleet optimizer.
* By default, simulator runs report a single-mission case over a one-week timeframe. Operators can enable the optional Mission sustainment projection lens to edit tempo, horizon, and generator efficiency.
* Total projected energy is `planning_energy_kwh * operations_per_week * planning_weeks`.
* Inventory cycles are based on total projected energy divided by declared usable inventory energy.

## Geometry

* Rectangle centroid is midpoint of bounds.
* Payload route centroid is midpoint between first and last route point.
* Polygon centroid is computed from local projected coordinates.
* Polygon v1 supports a single simple polygon exterior with no holes.
* Local projection is intended for planning-scale areas; larger or high-latitude areas should be reviewed before use.

## Implementation References

* Detailed current equations are tracked in `docs/current_logic_and_equations.md`.
* Implementation and development backlog is tracked in `docs/implementation_kanban.md`.
