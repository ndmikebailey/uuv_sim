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
* Standalone/manual simulations use the standard seawater assumption and do not call live salinity providers. Mission Builder/GPS geometry preserves Open-Meteo current, SST, wind, and weather, then attempts the active v3.5 salinity chain: NOAA CO-OPS station data when available, NOAA WOA23 climatology when available, and standard seawater otherwise.
* Salinity is preserved as `sea_surface_salinity_psu` when available from NOAA CO-OPS, NOAA WOA23, a loaded mission context, or the explicit standard seawater fallback. Open-Meteo Marine does not currently accept `sea_surface_salinity`, so the live marine request omits that variable and records the omission in query traceability.
* Salinity/buoyancy uplift is a bounded planning penalty: `min(0.10, abs(salinity_psu - 35.0) * 0.005)`. The standard seawater assumption is 35.0 PSU and 1025.0 kg/m3, so no salinity uplift is applied.
* WOA23 is climatological/historical and is not live tactical METOC. Standard seawater fallback is used when station/grid data is unavailable.
* Copernicus was evaluated during development and removed from the active v3.5 salinity chain.
* HYCOM/GOFS, NASA SMAP/Aquarius, and Argo remain future enhancement or V&V sources only.
* Salinity and density inputs are planning modifiers only and are not tactical oceanographic authority.
* Payload Delivery applies an optional payload-weight burden to outbound propulsion power only: `1 + min(5, max(0, (payload_weight_kg / vehicle_energy_kwh) * 0.30)) / 100`. Payload burden does not rely on public dry-weight data; payload mass is treated as a bounded trim/integration planning penalty scaled against vehicle energy class because payload weight alone is not a direct hydrodynamic drag variable. Payload-specific drag modeling is future work if area, Cd, mounting, buoyancy, and trim data become available.
* Recoverable Payload Delivery missions add a small launch/recovery overhead. One-way/non-recoverable missions do not.

## Sustainment Projection

* Sustainment Projection Lens is a simplified energy-flow lens, not a fleet optimizer.
* By default, simulator runs report a single-mission case over a one-week timeframe. Operators can enable the optional Mission sustainment projection lens to edit tempo, horizon, and generator efficiency.
* Total projected energy is `planning_energy_kwh * operations_per_week * planning_weeks`.
* Inventory cycles are based on total projected energy divided by declared usable inventory energy.
* Generator input energy is the already efficiency-adjusted generator-side energy requirement. The fuel-equivalent estimate uses `fuel_gallons_equivalent = generator_input_energy_kwh / 10.0`.
* Fuel-equivalent estimate uses a conservative 10.0 kWh/gal JP-8/diesel tactical-generator planning factor. This is a sustainment-planning estimate, not a generator certification curve.

## Geometry

* Rectangle centroid is midpoint of bounds.
* Payload route centroid is midpoint between first and last route point.
* Polygon centroid is computed from local projected coordinates.
* Polygon v1 supports a single simple polygon exterior with no holes.
* Local projection is intended for planning-scale areas; larger or high-latitude areas should be reviewed before use.

## Implementation References

* Detailed current equations are tracked in `docs/current_logic_and_equations.md`.
* Implementation and development backlog is tracked in `docs/implementation_kanban.md`.
