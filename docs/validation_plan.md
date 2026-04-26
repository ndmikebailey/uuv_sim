# Validation Plan

## v3.0-alpha Purpose

The v3.0-alpha build supports controlled dry runs and early physical-test planning. It should not be frozen as the official physical-test baseline until reproducibility, run logging, source traceability, and test coverage are reviewed.

## Dry Run Checklist

1. Draw rectangle ISR mission.
2. Draw polygon Area Search / MCM mission.
3. Draw payload delivery line route.
4. Confirm mission context loads and simulator inputs prefill.
5. Override METOC inputs manually and confirm outputs change.
6. Enter a known Monte Carlo seed and confirm repeatability.
7. Confirm run-record JSON and results CSV export.
8. Confirm mission map snapshot renders and the search-pattern overlay appears for Area Search / MCM only.

## Physical-Test Record Fields

Each physical test should preserve:

* run ID
* timestamp UTC
* mission type
* geometry JSON
* vehicle configuration
* simulation inputs
* raw marine API JSON
* raw weather API JSON
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
