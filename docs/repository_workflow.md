# Repository Workflow

This repository is the controlled source of truth for the UUV Sustainment Simulation project.

## Branches

`main` is the stable baseline branch. It should represent reviewed project checkpoints that can be used for academic review, configuration identification, and repeatable demonstrations.

`dev/v3.1-beta` is the active development branch for the v3.1-beta iteration. UI, ISR logic, reporting, traceability, and physical-test preparation changes should be developed here before being promoted to `main`.

`feature/*` branches may be used for isolated work when a change is risky, large, or easier to review separately. Examples include `feature/isr-endurance-logic` or `feature/payload-route-report`.

## Tags

Tags should mark formal baselines and release candidates.

Recommended tags:

- `v3.0-alpha` for the modular alpha baseline.
- `v3.1-beta` for the physical-test baseline candidate after targeted fixes are complete.

Create tags only after the intended commit has been reviewed and pushed.

## Commit Messages

Use short, specific commit messages that identify the main change.

Examples:

- `Baseline v3.0-alpha modular UUV simulation`
- `Add repository workflow and physical test documentation`
- `Fix environment merge traceability`
- `Revise ISR endurance mission logic`

## Do Not Commit

Do not commit credentials, local run outputs, cache folders, virtual environments, generated smoke-test artifacts, or local editor settings.

Excluded examples:

- `.env`
- `.venv/`
- `venv/`
- `.gradio/`
- `runs/`
- `__pycache__/`
- `.pytest_cache/`
- `*.pyc`
- `*.log`
- `*.tmp`
- `.vscode/settings.json`

## Baseline Workflow

For a clean baseline:

```bash
git add .
git commit -m "Baseline v3.0-alpha modular UUV simulation"
git push origin main
git tag v3.0-alpha
git push origin v3.0-alpha
```

For v3.1-beta development:

```bash
git checkout -b dev/v3.1-beta
git push -u origin dev/v3.1-beta
```
