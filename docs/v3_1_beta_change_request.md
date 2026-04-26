# v3.1-beta Change Request

Status: implementation in progress on `dev/v3.1-beta`  
Baseline label retained: `v3.0-alpha`  
Target label after review: `v3.1-beta - physical-test baseline candidate`

## Verification Policy

Limit verification to syntax checks and targeted unit tests for changed files. Do not run the full smoke test unless the change modifies core simulation math, geometry parsing, environment API behavior, run logging/export behavior, release tagging, or the user explicitly requests it.

For this implementation pass, verification was limited to:

- `python -m compileall .`
- Targeted unit tests for changed geometry, energy, mission, environment merge, API traceability, and app callback behavior.

No Hugging Face launch verification, full end-to-end smoke test, or generated export verification was performed.

## Priority 1 - UI / Report Fixes

Implemented:

- Payload mode hides search-only simulator inputs.
- ISR mode no longer shows swath/track-spacing search inputs.
- Area Search / MCM remains the swath-search mission mode.
- View Results shortcut added under Run Status with disabled and active states.
- Payload route/current report snapshot replaces the placeholder message.
- Battery progress chart now plots cumulative energy against battery remaining percent instead of a voltage proxy.
- Mission map snapshot uses a consistent local-map style and normalized orientation handling.

## Priority 2 - ISR Logic Redesign

Implemented:

- ISR is modeled as persistent observation/endurance, not swath search.
- ISR accepts line, polygon, and rectangle patrol geometry.
- Line ISR uses out-and-back loop distance.
- Polygon and rectangle ISR use perimeter loop distance.
- ISR uses endurance speed, vehicle endurance power draw, environmental multiplier, and usable mission energy.
- ISR outputs loop distance, loop time, estimated time on station, completed loops, remaining partial loop, adjusted power draw, and reserve/battery margin.
- ISR does not require a requested observation duration.
- ISR METOC lookup defaults to the first route or boundary point instead of centroid.

## Priority 3 - Traceability Fixes

Implemented:

- `EnvironmentData.merged()` preserves populated raw API payloads and query parameters when the other source has empty dict/list values.
- Marine and weather API failure paths preserve query parameters.
- Monte Carlo seed parsing now rejects invalid text and negative values with a clear UI error.
- Run records include `app_version`, `model_version`, `vehicle_catalog_version`, and `git_commit` when available, with safe fallback to `unknown`.

## Priority 4 - Repo / Configuration Control

Implemented:

- `.gitignore` expanded for Python caches, local environments, Gradio/runtime outputs, editor settings, and transient logs.
- Repository workflow documentation added.
- Physical-test plan stub added.
- Non-operational-use notice added.
- Top-level build-log pointer added.

## Deferred

- Geographic basemap/lens work remains deferred unless it can be added without disrupting the current plotting workflow.
- Optional requested ISR duration input remains deferred.
