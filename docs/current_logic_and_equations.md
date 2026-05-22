# Current Logic And Equations

Source basis: local source files and `UUV Project file Notes.md`. This document records implementation-relevant assumptions, current logic, and equations. It does not add new research tasks.

## Unit Policy

The simulation uses kWh and kW as the primary logistics units. This matches the vehicle catalog and battery-planning workflow.

Report-only conversions:

```text
Wh = kWh * 1000
J = Wh * 3600
MJ = J / 1,000,000
GJ = MJ / 1000
TOE = kWh / 11630
BOE = GJ / 6.12
coal_kg_equiv = MJ / 30
```

Implemented in `core/energy.py::energy_equivalent_rows`.

## Vehicle Baseline Power

Current baseline power is derived from catalog values:

```text
average_power_kw = battery_kwh / max(estimated_endurance_hr, 0.1)
usable_battery_per_set_kwh = battery_kwh * sampled_usable_fraction * temperature_capacity_factor * (1 - operator_reserve_fraction)
total_available_kwh = usable_battery_per_set_kwh * battery_sets_available
```

Implemented in `models/vehicle_model.py` and `core/energy.py`.

## Speed-Power Model

The project notes propose a fixed hotel load and cubic propulsion law. The current implementation follows that structure with a default hotel power fraction of `0.40`.

```text
hotel_kw = average_power_kw * hotel_fraction
propulsion_kw_nominal = average_power_kw * (1 - hotel_fraction)
speed_ratio = requested_speed_kts / nominal_speed_kts
dynamic_power_kw = hotel_kw + propulsion_kw_nominal * speed_ratio^3
```

Current defaults and overrides:

```text
hotel_power_fraction = 0.40
speed_exponent = 3.0
min_efficient_speed = 0.65 * nominal_speed
low_speed_penalty_fraction = 0.15
low_speed_penalty_cap_fraction = 0.10
catalog hotel_fraction / hotel_power_fraction override: optional, clamped to 0.20-0.80
```

The project notes mention a defensible 20/80 hotel/propulsion split. The active code uses 40/60 when the catalog does not provide a vehicle-specific value. Vehicles with heavier sensor/hotel load may provide `hotel_fraction` or `hotel_power_fraction` in `data/vehicle_catalog.json`.

Implemented in `core/power.py` and exposed through `core/energy.py::estimate_power_at_speed_kw`.

## Hydrodynamic Cross-Check Equations

The notes include cylindrical drag equations for methodology cross-checking. These are not coded into the simulation and should remain a validation/reference calculation unless the project explicitly shifts toward hydrodynamic modeling.

```text
A_front = pi * (d / 2)^2
A_wetted = 2 * pi * d * L
X_uu = 0.5 * rho * ((C_d * A_front) + (C_f * A_wetted))
P_prop = X_uu * v * |v|
```

Implementation boundary: current app relies on manufacturer or catalog baseline power, then applies interpretable planning multipliers. It does not solve CFD, hull drag, propeller efficiency, or maneuvering from first principles.

## Temperature Logic

Temperature is now modeled as usable battery capacity derating:

```text
-20 deg C -> 0.65
-10 deg C -> 0.85
2 deg C   -> 0.95
15 deg C  -> 1.00
32 deg C  -> 1.00
52 deg C  -> 0.95
62 deg C  -> 0.85
```

Implemented in `core/battery.py::lithium_temperature_capacity_factor`.

Temperature is not also applied as a mission-energy demand uplift.

## Battery Condition Sampling

For each Monte Carlo run, usable battery fraction is sampled by battery condition:

```text
low    = triangular(0.75, 0.82, 0.90)
medium = triangular(0.80, 0.88, 0.95)
high   = triangular(0.88, 0.93, 0.98)
```

Then:

```text
usable_energy_kwh = rated_capacity_kwh * sampled_usable_fraction * temperature_capacity_factor * (1 - reserve_fraction)
```

Implemented in `core/battery.py` and integrated in `core/energy.py`.

## Current Logic

Current is decomposed relative to vehicle heading:

```text
relative_angle = current_direction_deg - heading_deg
along_current_kts = current_speed_kts * cos(relative_angle)
cross_current_kts = current_speed_kts * sin(relative_angle)
```

Payload current penalty:

```text
payload_current_penalty = 0.04 * min(abs(cross_current_kts) / vehicle_speed_kts, 2.0)
```

Search current duration multiplier:

```text
along_penalty = 0.35 * abs(along_current_kts) / vehicle_speed_kts
cross_penalty = 0.10 * abs(cross_current_kts) / vehicle_speed_kts
search_multiplier = 1.0 + along_penalty + cross_penalty
```

ISR current power penalty:

```text
isr_current_power_penalty = 0.08 * min(current_speed_kts / endurance_speed_kts, 2.0)
```

Implemented in `core/environment.py` and `core/energy.py`.

## Environmental Uplift

Payload and ISR use additive planning factors inside one multiplier:

```text
environmental_multiplier = 1.0 + current_penalty + salinity_penalty
```

Search/MCM uses a current duration multiplier plus salinity energy penalty in the candidate energy calculation. Temperature affects available battery energy.

## Salinity/Buoyancy Logic

Salinity is modeled as a bounded planning uplift around a 35 PSU reference:

```text
if salinity_psu is missing:
    salinity_penalty = 0.0
else:
    salinity_penalty = min(0.10, abs(salinity_psu - 35.0) * 0.005)

salinity_uplift_pct = salinity_penalty * 100
```

Interpretation:

- `35.0 PSU` is the no-penalty reference.
- Each 1 PSU deviation adds 0.5 percent energy uplift.
- The salinity contribution is capped at 10 percent.
- Missing salinity preserves pre-salinity energy behavior.

Implemented in `core/environment.py::salinity_buoyancy_penalty` and applied in `core/energy.py`.

## Payload Mission Logic

Payload Delivery currently uses a line route.

```text
outbound_time_hr = route_leg_time_hr(route_distance, speed, current, route_heading)
return_time_hr = route_leg_time_hr(route_distance, speed, current, reciprocal_heading) if return_to_start else 0
transit_time_hr = additional_transit_km / max(speed_kts * 1.852, 0.1)
duration_single_hr = outbound_time_hr + return_time_hr + transit_time_hr

penalty_pct = (payload_weight_kg / vehicle_energy_kwh) * 0.30
weight_penalty_multiplier = 1.0 + min(5.0, max(0.0, penalty_pct)) / 100.0

outbound_power_kw = estimate_power_at_speed_kw(..., propulsion_multiplier=weight_penalty_multiplier)
return_power_kw = speed_adjusted_power_kw(...)
launch_recovery_energy_kwh = launch_recovery_overhead_hr * launch_recovery_power_kw
energy_single_kwh = (
    outbound_power_kw * (outbound_time_hr + transit_time_hr)
    + return_power_kw * return_time_hr
) * environmental_multiplier + launch_recovery_energy_kwh
```

Route-leg speed over ground is bounded to at least 25 percent of commanded vehicle speed to avoid impossible or singular current cases:

```text
speed_over_ground = max(vehicle_speed + along_current, vehicle_speed * 0.25)
```

The payload multiplier applies to outbound propulsion power only, not fixed hotel load. Search/MCM and ISR ignore payload weight. Payload burden does not rely on public dry-weight data; payload mass is treated as a bounded trim/integration planning penalty scaled against vehicle energy class because payload weight alone is not a direct hydrodynamic drag variable. Payload-specific drag modeling is future work if area, Cd, mounting, buoyancy, and trim data become available. Return-to-start missions include an unburdened return leg after delivery. One-way mode uses outbound route energy only. Recoverable payload missions add a small launch/recovery overhead; one-way/non-recoverable missions do not. Sprint/hibernate/deploy phasing remains future work and is not the same as one-way routing.

Implemented in `core/energy.py`.

## Search/MCM Logic

Search/MCM evaluates two orientations:

```text
North-South track_heading_deg = 0
East-West track_heading_deg = 90
```

For each candidate:

```text
distance_km = clipped_track_distance_km + turn_distance_km + additional_transit_km
base_duration_hr = distance_km / max(speed_kts * 1.852, 0.1)
duration_hr = base_duration_hr * search_current_duration_multiplier
duration_hr += turns * 0.01
energy_kwh = dynamic_power_kw * duration_hr * (1 + salinity_penalty)
```

The lower-energy orientation is selected for the run.

Implemented in `core/energy.py::search_plan` and `core/geometry.py::clipped_search_lanes`.

## ISR Logic

ISR loop distance is based on geometry:

```text
line patrol = route length * 2
polygon patrol = closed polygon perimeter
rectangle patrol = 2 * (width_km + height_km)
```

Endurance:

```text
available_mission_energy_kwh = usable_energy_kwh * (1 - reserve_fraction)
adjusted_power_kw = endurance_power_kw * environmental_multiplier
max_time_on_station_hr = available_mission_energy_kwh / adjusted_power_kw
loop_time_hr = loop_distance_km / (endurance_speed_kts * 1.852)
completed_loops = floor(max_time_on_station_hr / loop_time_hr)
remaining_partial_loop_pct = (max_time_on_station_hr % loop_time_hr) / loop_time_hr * 100
```

For reporting and sustainment planning, ISR now uses mission-total endurance-window energy as the planning basis. Loop energy remains visible for coverage accounting, but the planning energy is the total energy expended across the completed and partial loop set before recovery/swap:

```text
planning_energy_basis = "mission_total"
planning_energy_kwh = p95_energy_kwh
planning_duration_basis = "endurance_window"
planning_duration_hr = isr_single_set_endurance_hr
```

Implemented in `core/energy.py::compute_isr_persistence`.

## Battery Inventory And Recharge Logic

The model compares P80 mission energy against available inventory:

```text
battery_sets_required_p80 = ceil(p80_energy_kwh / usable_battery_per_set_kwh)
if mission_type == ISR:
    battery_sets_required_p80 = 1
battery_shortfall = max(0, battery_sets_required_p80 - battery_sets_available)
recharge_sequences_required = battery_shortfall if recharge_allowed else 0
recharge_downtime_hr = recharge_sequences_required * vehicle.recharge_hr
elapsed_with_recharge_hr = mean_duration_hr + recharge_downtime_hr
```

This is the active bridge from tactical mission energy to logistics burden.

Implemented in `core/energy.py::run_energy_simulation`.

## Sustainment Projection Lens

The simplified sustainment lens rolls mission energy into planning-horizon energy-flow requirements. By default, simulator runs report a single-mission case over a one-week timeframe. Operators can enable the optional Mission sustainment projection lens to edit tempo, horizon, and generator efficiency:

```text
total_missions = missions_per_week * planning_weeks
total_conservative_energy_kwh = planning_energy_kwh * total_missions
usable_inventory_energy_per_cycle_kwh = usable_battery_per_set_kwh * battery_sets_available
inventory_cycles_required = ceil(total_conservative_energy_kwh / usable_inventory_energy_per_cycle_kwh)
generator_input_energy_kwh = total_conservative_energy_kwh / generator_efficiency
recharge_energy_required_kwh = max(total_conservative_energy_kwh - usable_inventory_energy_per_cycle_kwh, 0)
fuel_gallons_equivalent = generator_input_energy_kwh / 10.0
```

The fuel-equivalent estimate uses a conservative 10.0 kWh/gal JP-8/diesel tactical-generator planning factor. It is secondary to recharge energy and generator input energy and does not apply another generator-efficiency correction.

Implemented in `core/sustainment.py::compute_sustainment_projection`.

## METOC Sampling

Current lookup policy:

```text
Search/MCM single area: area centroid
Payload Delivery: route midpoint
ISR: first patrol point
Multi-area Search/MCM: each area centroid, then aggregate
```

Multi-area current aggregation uses vector averaging:

```text
u = speed * sin(direction)
v = speed * cos(direction)
mean_u = average(u)
mean_v = average(v)
aggregate_speed = sqrt(mean_u^2 + mean_v^2)
aggregate_direction = atan2(mean_u, mean_v)
```

Implemented in `core/mission.py`.

## Salinity Traceability

Salinity is implemented as a traceable environmental input and a bounded planning-level energy modifier.

```text
EnvironmentData.sea_surface_salinity_psu
```

Current behavior:

- Open-Meteo Marine requests omit `sea_surface_salinity` because the endpoint currently returns HTTP 400 for that variable.
- API parsing accepts `sea_surface_salinity`, `ocean_salinity`, and `salinity` if they appear in a supplied or future payload.
- Standalone/manual simulation uses the standard seawater assumption and does not call live salinity providers.
- Mission Builder/GPS geometry preserves Open-Meteo current, SST, wind, and weather, then attempts NOAA CO-OPS station salinity, NOAA WOA23 climatology, and standard seawater in that order.
- Multi-area Search/MCM attempts one salinity/density lookup per area centroid through the fused METOC service and averages salinity/density as scalar values.
- Environment table rows and internal run records preserve salinity when available.
- Provider-unavailable and reference-salinity cases preserve existing energy behavior because the standard seawater fallback is 35.0 PSU and 1025.0 kg/m3.
- Non-reference salinity contributes to `salinity_uplift_pct` and the environmental multiplier.
- Copernicus was evaluated during development and removed from the active v3.5 salinity chain. HYCOM/GOFS, SMAP, and Argo remain future enhancement or V&V sources only.
- Salinity and density inputs are planning modifiers only and are not tactical oceanographic authority.

## Sustainment Projection Output

The simplified sustainment lens computes:

```text
total_missions = missions_per_week * planning_weeks
total_conservative_energy_kwh = planning_energy_kwh * total_missions
usable_inventory_energy_per_cycle_kwh = usable_battery_per_set_kwh * battery_sets_available
inventory_cycles_required = ceil(total_conservative_energy_kwh / usable_inventory_energy_per_cycle_kwh)
generator_input_energy_kwh = total_conservative_energy_kwh / generator_efficiency
recharge_energy_required_kwh = max(total_conservative_energy_kwh - usable_inventory_energy_per_cycle_kwh, 0)
fuel_gallons_equivalent = generator_input_energy_kwh / 10.0
```

Implemented in `core/sustainment.py`.

## Not Yet Implemented

The following project-note items are implementation backlog, not current behavior:

- Multi-phase hibernate/sprint payload mission logic.
