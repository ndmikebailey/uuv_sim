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
usable_battery_per_set_kwh = battery_kwh * usable_fraction
total_available_kwh = usable_battery_per_set_kwh * battery_sets_available
```

Implemented in `models/vehicle_model.py` and `core/energy.py`.

## Speed-Power Model

The project notes propose a fixed hotel load and cubic propulsion law. The current implementation follows that structure with a default hotel fraction of `0.35`.

```text
hotel_kw = average_power_kw * hotel_fraction
propulsion_kw_nominal = average_power_kw * (1 - hotel_fraction)
speed_ratio = requested_speed_kts / nominal_speed_kts
dynamic_power_kw = hotel_kw + propulsion_kw_nominal * speed_ratio^3
```

Current defaults:

```text
hotel_fraction = 0.35
speed_exponent = 3.0
```

The project notes mention a defensible 20/80 hotel/propulsion split. The active code uses 35/65 until a vehicle-specific or thesis-selected value is promoted into configuration.

Implemented in `core/energy.py::estimate_power_at_speed_kw`.

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

Current temperature penalty:

```text
if temp_c < 15:
    penalty = min(0.25, (15 - temp_c) * 0.01)
elif temp_c > 32:
    penalty = min(0.15, (temp_c - 32) * 0.005)
else:
    penalty = 0.0
```

Implemented in `core/environment.py::temperature_energy_penalty`.

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
environmental_multiplier = 1.0 + temperature_penalty + current_penalty + salinity_penalty
```

Search/MCM uses a current duration multiplier plus temperature and salinity energy penalties in the candidate energy calculation.

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
energy_single_kwh = dynamic_power_kw * duration_single_hr * environmental_multiplier
```

Route-leg speed over ground is bounded to at least 25 percent of commanded vehicle speed to avoid impossible or singular current cases:

```text
speed_over_ground = max(vehicle_speed + along_current, vehicle_speed * 0.25)
```

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
energy_kwh = dynamic_power_kw * duration_hr * (1 + temperature_penalty + salinity_penalty)
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

Implemented in `core/energy.py::compute_isr_persistence`.

## Battery Inventory And Recharge Logic

The model compares P80 mission energy against available inventory:

```text
battery_sets_required_p80 = ceil(p80_energy_kwh / usable_battery_per_set_kwh)
battery_shortfall = max(0, battery_sets_required_p80 - battery_sets_available)
recharge_sequences_required = battery_shortfall if recharge_allowed else 0
recharge_downtime_hr = recharge_sequences_required * vehicle.recharge_hr
elapsed_with_recharge_hr = mean_duration_hr + recharge_downtime_hr
```

This is the active bridge from tactical mission energy to logistics burden.

Implemented in `core/energy.py::run_energy_simulation`.

## Stockpile Helper

The backend stockpile helper rolls mission energy into planning-horizon requirements:

```text
missions_in_horizon = missions_per_week * planning_horizon_days / 7
total_mission_energy_kwh = conservative_energy_kwh * missions_in_horizon
battery_sets_without_recharge = ceil(total_mission_energy_kwh / usable_battery_per_set_kwh)
generator_input_energy_kwh = total_mission_energy_kwh / generator_efficiency
fuel_gallons_equivalent = generator_input_energy_kwh / fuel_energy_kwh_per_gal
```

Implemented in `core/energy.py::compute_stockpile_requirement`.

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
- Multi-area Search/MCM averages salinity as a scalar value.
- Environment table rows and run records preserve salinity when available.
- Missing salinity and reference salinity preserve existing energy behavior.
- Non-reference salinity contributes to `salinity_uplift_pct` and the environmental multiplier.

## Not Yet Implemented

The following project-note items are implementation backlog, not current behavior:

- Payload weight input and mass penalty multiplier.
- Static launch/recovery energy tax.
- Multi-phase hibernate/sprint payload mission logic.
- Expendable one-way vehicle report logic for `recharge_hr = 0.0` and `usable_fraction = 1.0`.
- Vehicle-specific hotel fractions.
