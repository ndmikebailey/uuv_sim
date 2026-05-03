# Validation Plan

## v3.3 Research-Development Purpose

The v3.3 research-development build supports controlled dry runs, manual UI testing, and model-review planning. It should not be treated as a final baseline until reproducibility, internal traceability records, source traceability, and test coverage are reviewed.

## Dry Run Checklist

1. Draw rectangle ISR mission.
2. Draw polygon Area Search / MCM mission.
3. Draw payload delivery line route.
4. Confirm mission context loads and simulator inputs prefill.
5. Override METOC inputs manually and confirm outputs change.
6. Enter a known Monte Carlo seed and confirm repeatability.
7. Confirm the user-facing report sections render: Energy Planner Summary, Energy Storage Equivalence Lens, METOC Assessment, Energy Summary, Battery and Sustainment Summary, Mission Geometry Summary, Environmental Inputs, Sustainment Projection Lens, charts, and Mission Visual Summary.
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
