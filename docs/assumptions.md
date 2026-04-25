# Model Assumptions

This document tracks assumptions that affect UUV mission energy estimates.

## Vehicle Catalog

Vehicle assumptions are loaded from `data/vehicle_catalog.json`.

* REMUS 300 entries are planning baselines from manufacturer-published REMUS 300M information.
* IVER4 and Knifefish entries are placeholders and must be replaced with validated source data before a physical-test baseline.

## Energy Model

* Average platform power is estimated as nameplate battery energy divided by estimated endurance.
* Battery usable planning energy is `battery_kwh * usable_fraction`.
* Search missions compare North-South and East-West swath plans and select the lower sampled energy burden.
* Search turns use the carried-forward planning assumption of `0.01 hr` duration burden per turn plus a turn-distance estimate.

## Environmental Uplift

* Current direction is treated as direction of flow.
* Payload missions apply a cross-current energy penalty.
* Search missions apply along-current and cross-current duration multipliers.
* Temperature penalties are:
  * below 15 deg C: `min(0.25, (15 - temp_c) * 0.01)`
  * above 32 deg C: `min(0.15, (temp_c - 32) * 0.005)`

## Geometry

* Rectangle centroid is midpoint of bounds.
* Payload route centroid is midpoint between first and last route point.
* Polygon centroid is computed from local projected coordinates.
* Polygon v1 supports a single simple polygon exterior with no holes.
* Local projection is intended for planning-scale areas; larger or high-latitude areas should be reviewed before use.

