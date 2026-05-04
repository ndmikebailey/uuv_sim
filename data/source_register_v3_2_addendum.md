# Source Register Addendum - Public Vehicle Baseline

This addendum records the public vehicle data used to update `data/vehicle_catalog.json`. `UUV Project file Notes.md` is treated as the current validated public-facing system baseline for the listed Navy/program variants.

| Vehicle catalog entry | Public source basis | Values used in model | Notes |
| --- | --- | --- | --- |
| REMUS 100B - 1.5 kWh | Public REMUS 100B datasheet | 1.5 kWh, 8 hr endurance, 3 kt nominal speed, 4.5 kt max speed, 6 hr recharge | Included as provisional until the final official HII/Hydroid source file is attached to the repo. |
| REMUS 300 - 1.5 kWh | HII REMUS 300 datasheet | 1.5 kWh, 10 hr endurance, 3 kt nominal speed, 4 kt max speed, 6 hr recharge | Manufacturer source. |
| REMUS 300 - 3.0 kWh Standard | HII REMUS 300 datasheet | 3.0 kWh, 20 hr endurance, 3 kt nominal speed, 4 kt max speed, 12 hr recharge | Manufacturer source. |
| REMUS 300 - 4.5 kWh | HII REMUS 300 datasheet | 4.5 kWh, 30 hr endurance, 3 kt nominal speed, 4 kt max speed, 18 hr recharge | Manufacturer source. |
| Bluefin-9 - 1.5 kWh | Bluefin-9 public technical sheet | 1.5 kWh, 12 hr endurance at 3 kt, 5 kt max speed | Recharge time not published; uses 4 hr/kWh planning estimate. |
| Bluefin-12D - 7.5 kWh | Bluefin-12D public technical sheet | 7.5 kWh, 30 hr endurance at 3 kt, 5 kt max speed | Recharge time not published; uses 4 hr/kWh planning estimate. |
| Iver3 EP - 0.8 kWh | L3Harris Iver3 public specification page | 0.8 kWh, 8 hr conservative endurance from 8-14 hr range, 2.5 kt nominal speed, 4 kt max speed | Recharge time not published; uses 4 hr/kWh planning estimate. |
| Iver4 580 - 0.78 kWh | L3Harris Iver4 public specification page | 0.78 kWh, 6 hr endurance, 4.5 kt survey speed, 5 kt max speed | Recharge time not published; uses 4 hr/kWh planning estimate. |
| Lionfish (Next-Gen MCM - Standard) | Validated public-facing system notes and public spec sheets | 1.5 kWh, 10 hr endurance, 3 kt nominal speed, 5 kt max speed, 4 hr recharge | Expeditionary SUUV based on HII REMUS 300 1-battery module. |
| Lionfish (Next-Gen MCM - Extended) | Validated public-facing system notes and public spec sheets | 4.5 kWh, 30 hr endurance, 3 kt nominal speed, 5 kt max speed, 8 hr recharge | Expeditionary SUUV based on HII REMUS 300 3-battery module configuration. |
| Yellow Moray (Submarine TTL) | Validated public-facing system notes and public spec sheets | 3.0 kWh, 20 hr endurance, 3 kt nominal speed, 5 kt max speed, 6 hr recharge | Submarine-launched TTL SUUV based on HII REMUS 300 medium configuration. |
| Viperfish (Deep Water MCM) | Validated public-facing system notes and public spec sheets | 4.5 kWh, 30 hr endurance, 3 kt nominal speed, 5 kt max speed, 8 hr recharge | Deep-water MUUV planning entry based on REMUS 300 4.5 model. |
| Iver3 580 (Legacy VSW) | Validated public-facing system notes and public spec sheets | 0.8 kWh, 8 hr endurance, 2.5 kt nominal speed, 4 kt max speed, 3 hr recharge | Legacy VSW planning entry from public Iver3 specifications. |
| Iver4 900 (Expeditionary MCM) | Validated public-facing system notes and public spec sheets | 2.0 kWh, 14 hr endurance, 3 kt nominal speed, 5 kt max speed, 5 hr recharge | Expeditionary MCM planning entry from public Iver4 900 specifications. |
| MK19 Mod 0 Razorback (DDS) | Validated public-facing system notes and public spec sheets | 7.0 kWh, 24 hr endurance, 3 kt nominal speed, 4 kt max speed, no recharge | Legacy DDS UUV based on REMUS 600 alkaline battery configuration. |
| MK20 Mod 0 Razorback (TTL&R) | Validated public-facing system notes and public spec sheets | 5.2 kWh, 18.4 hr endurance, 3 kt nominal speed, 6 kt max speed, 8 hr recharge | Submarine TTL&R MUUV planning entry. |
| AN/AQS-23 Barracuda | Validated public-facing system notes and public spec sheets | 0.8 kWh, 1.5 hr endurance, 4 kt nominal speed, 10 kt max speed, no recharge | One-way non-rechargeable vehicle inventory planning entry. |
| Next-Gen MUUV (REMUS 620) | HII REMUS 620 public specifications recorded in project notes | 15.0 kWh, 110 hr endurance, 3 kt nominal speed, 8 kt max speed, 12 hr recharge | Extended multi-day TTL&R and expeditionary planning entry. |

## Shared planning factors

| Factor | Value | Basis |
| --- | ---: | --- |
| Usable battery fraction | Low/Medium/High condition distributions | Current model samples practical usable battery fraction separately from operator reserve margin and temperature derating. Legacy catalog `0.88` values remain as source-visible baseline data. |
| Missing recharge-time estimate | `4 * battery_kwh` hours | Project planning estimate until manufacturer recharge data are available. |
| Payload mass burden | Energy-class-scaled multiplier in `core/energy.py` | Active payload burden does not require public dry-weight data. |

## Data gaps

- Vehicle dry weight remains optional metadata only and is not an active payload-burden dependency.
