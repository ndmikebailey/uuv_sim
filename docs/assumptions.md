# Model Assumptions

This document tracks assumptions that affect UUV mission energy estimates.

## Vehicle Catalog

Vehicle assumptions are loaded from `data/vehicle_catalog.json`.

* REMUS 300 entries are planning baselines from manufacturer-published REMUS 300M information.
* IVER4 and Knifefish entries are placeholders and must be replaced with validated source data before a physical-test baseline.

## Energy Model

* Average platform power is estimated as nameplate battery energy divided by estimated endurance.
* Battery usable planning energy is `battery_kwh * usable_fraction`.
* Core energy calculations use kWh and kW. Joules, MJ, and GJ are derived for reporting only.
* Requested-speed power is split into fixed hotel load and speed-dependent propulsion load. Current implementation uses `hotel_fraction = 0.35` and `speed_exponent = 3.0`.
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
* Salinity is preserved as `sea_surface_salinity_psu` when available from manual input, future API support, or a supplied payload. Open-Meteo Marine does not currently accept `sea_surface_salinity`, so the live marine request omits that variable and records the omission in query traceability.
* Salinity/buoyancy uplift is a bounded planning penalty: `min(0.10, abs(salinity_psu - 35.0) * 0.005)`. Missing salinity and exactly 35 PSU produce zero salinity uplift.

## Geometry

* Rectangle centroid is midpoint of bounds.
* Payload route centroid is midpoint between first and last route point.
* Polygon centroid is computed from local projected coordinates.
* Polygon v1 supports a single simple polygon exterior with no holes.
* Local projection is intended for planning-scale areas; larger or high-latitude areas should be reviewed before use.

## Implementation References

* Detailed current equations are tracked in `docs/current_logic_and_equations.md`.
* Implementation and development backlog is tracked in `docs/implementation_kanban.md`.
