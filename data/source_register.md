# Source Register

Configuration-control register for assumptions used by the v4 beta UUV mission planning tool.

| Item | Status | Source / Basis | Notes |
| --- | --- | --- | --- |
| REMUS 100B battery/endurance entry | Planning baseline | Public REMUS/HII technical data recorded in catalog note | Active catalog entry; verify against official source before publication. |
| REMUS 300 battery/endurance entries | Planning baseline | Public HII REMUS 300 datasheet values recorded in catalog notes | Active catalog entries for 1.5, 3.0, and 4.5 kWh options. |
| Bluefin-9 and Bluefin-12D entries | Planning baseline | Public Bluefin/General Dynamics technical sheet values recorded in catalog notes | Active catalog entries; recharge time uses planning estimate where unpublished. |
| Iver3 EP and Iver4 580 entries | Planning baseline | Public L3Harris specification values recorded in catalog notes | Active catalog entries; no stale placeholder vehicle is active. |
| Public-facing Navy/program variant entries | Validated project baseline | `UUV Project file Notes.md` and associated public spec sheets | Active catalog includes Lionfish, Yellow Moray, Viperfish, Iver3 580, Iver4 900, MK19/MK20 Razorback, AN/AQS-23 Barracuda, and Next-Gen MUUV (REMUS 620). |
| Payload mass burden | Model assumption | `core/assumptions.py` and `core/energy.py` energy-class multiplier | Payload burden does not rely on public dry-weight data. Payload mass is scaled against vehicle energy class as a planning proxy. |
| Stochastic usable battery fraction | Model assumption | `core/battery.py` Low/Medium/High triangular distributions | Separate from operator reserve margin and temperature derating. |
| Temperature derating | Literature-aligned planning assumption | Bressan-style LiFePO4 capacity-loss anchors implemented as `TEMPERATURE_CAPACITY_FACTOR_POINTS` in `core/battery.py` | Reduces usable capacity in cold and high-temperature cases; not also applied as demand-side uplift. |
| Current penalty | Model assumption | Planning factors in `core/environment.py` and `core/energy.py` | Current affects route, search, and ISR burden. |
| NOAA CO-OPS salinity provider | Active station API path | Public NOAA CO-OPS API via `services/noaa_coops_salinity.py` | Active first priority when a nearby station has salinity data. |
| NOAA WOA23 salinity provider | Active climatology fallback | Public NOAA WOA23 salinity climatology via `services/woa23_salinity.py` | Used when CO-OPS does not return station salinity. Climatological/historical, not live tactical METOC. |
| Standard seawater salinity fallback | Active planning assumption | 35.0 PSU, 1025.0 kg/m3 in `services/metoc_fusion.py` | Used when station/grid data are unavailable; no salinity uplift applied. |
| Copernicus salinity/density provider | Removed from active chain | Development evaluation only | Copernicus was evaluated during development and removed from the active v3.5 salinity chain. |
| HYCOM/GOFS, SMAP, and Argo salinity | Future enhancement / V&V only | Public ocean model, satellite, and float products | Not active live providers in this release. |
| Fuel-equivalent sustainment lens | Model assumption | `core/sustainment.py` 10.0 kWh/gal JP-8/diesel tactical-generator planning factor | Secondary planning estimate from generator input energy; not a generator certification curve. |
