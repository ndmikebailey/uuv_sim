# Validation Plan

## v3.5 Beta Purpose

The v3.5 beta build supports controlled dry runs, team testing, manual UI testing, and model-review planning. It should not be treated as an operational baseline until reproducibility, internal traceability records, source traceability, and test coverage are reviewed.

## Dry Run Checklist

1. Draw rectangle ISR mission.
2. Draw polygon Area Search / MCM mission.
3. Draw payload delivery line route.
4. Confirm mission context loads and simulator inputs prefill.
5. Override METOC inputs manually and confirm outputs change.
6. Enter a known Monte Carlo seed and confirm repeatability.
7. Confirm the user-facing report sections render: Mission Decision Brief, Executive Results Summary, METOC Assessment, Mission Map Overlay when GPS geometry exists, Monte Carlo / Uncertainty Distribution, Engineering Geometry Snapshot, Mission Energy Progress and Battery Lens, Energy Detail, Battery and Sustainment Detail, Sustainment Projection Lens, Mission Geometry Detail, Environmental Detail, Energy Storage Equivalence Lens, and Technical Traceability / Model Detail.
8. Confirm mission map snapshot renders and the search-pattern overlay appears for Area Search / MCM only.

## Physical-Test Record Fields

Each physical test should preserve:

* run ID
* timestamp UTC
* mission type
* mission geometry
* vehicle configuration
* simulation inputs
* raw marine API payload
* raw weather API payload
* raw salinity-provider payload or metadata when available
* marine and weather API query parameters
* app version
* energy model version
* vehicle catalog version
* git commit when available
* simulation outputs
* operator notes
* actual test result

## Pre-Baseline Exit Criteria

* Placeholder vehicle assumptions replaced or explicitly excluded.
* No generated cache files in repository.
* All unit tests pass.
* Same seed produces repeatable outputs.
* Invalid seeds are rejected visibly before a simulation is recorded.
* Manual no-map search mode derives search dimensions from manual area or uses map-loaded geometry.
* No-internet and API-failure behavior is tested.
* API-failure records preserve query parameters.
* Actual-versus-predicted test log format is approved.
* Temperature validation figure overlays the old model curve, the active table-driven curve, and Bressan-style anchor points at about 22 deg C = 0 percent, 2 deg C = 5 percent, -10 deg C = 15 percent, -20 deg C = 35 percent, and 52 deg C = 5 percent.
