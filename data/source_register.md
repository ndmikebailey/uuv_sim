# Source Register

Configuration-control register for assumptions used by the v3.3 research-development UUV mission planning tool.

| Item | Status | Source / Basis | Notes |
| --- | --- | --- | --- |
| REMUS 100B battery/endurance entry | Planning baseline | Public REMUS/HII technical data recorded in catalog note | Active catalog entry; verify against official source before publication. |
| REMUS 300 battery/endurance entries | Planning baseline | Public HII REMUS 300 datasheet values recorded in catalog notes | Active catalog entries for 1.5, 3.0, and 4.5 kWh options. |
| Bluefin-9 and Bluefin-12D entries | Planning baseline | Public Bluefin/General Dynamics technical sheet values recorded in catalog notes | Active catalog entries; recharge time uses planning estimate where unpublished. |
| Iver3 EP and Iver4 580 entries | Planning baseline | Public L3Harris specification values recorded in catalog notes | Active catalog entries; no stale placeholder vehicle is active. |
| Public-facing Navy/program variant entries | Validated project baseline | `UUV Project file Notes.md` and associated public spec sheets | Active catalog includes Lionfish, Yellow Moray, Viperfish, Iver3 580, Iver4 900, MK19/MK20 Razorback, AN/AQS-23 Barracuda, and Next-Gen MUUV (REMUS 620). |
| Payload mass burden | Model assumption | `core/assumptions.py` and `core/energy.py` energy-class multiplier | Payload burden does not rely on public dry-weight data. Payload mass is scaled against vehicle energy class as a planning proxy. |
| Stochastic usable battery fraction | Model assumption | `core/battery.py` Low/Medium/High triangular distributions | Separate from operator reserve margin and temperature derating. |
| Temperature derating | Model assumption | `lithium_temperature_capacity_derating_v1` in `core/battery.py` | Reduces usable capacity in cold water; not also applied as demand-side uplift. |
| Current penalty | Model assumption | Planning factors in `core/environment.py` and `core/energy.py` | Current affects route, search, and ISR burden. |
| Copernicus salinity/density provider | Optional API path | Credential-safe `services/copernicus_api.py` | Provider path implemented; live credentialed validation pending. |
