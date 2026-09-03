# AGENTS.md

These instructions apply to the entire repository.

## Project

This repository contains a local Python 3.11 Streamlit prototype for historical
home-energy exploration and hourly solar-and-battery modeling. Keep changes
appropriate for a personal prototype; do not add production infrastructure,
accounts, cloud persistence, or unrelated abstraction without an explicit
request.

## Source of truth

- `SPEC.md` is the authoritative specification for externally observable
  behavior and modeling assumptions.
- **Any feature change or behavior change must update `SPEC.md` in the same
  change to reflect the new behavior.**
- Keep implementation, tests, `README.md`, and `SPEC.md` consistent. If they
  disagree, resolve the discrepancy rather than documenting contradictory
  behavior.

## Repository map

- `app.py`: Streamlit UI, session state, controls, and presentation flow.
- `solar_model/data.py`: source validation and normalized hourly data.
- `solar_model/aggregation.py`: historical filtering and bucket aggregation.
- `solar_model/tou.py`: TOU rules, prices, and rate classification.
- `solar_model/costs.py`: projected utility cost calculation and formatting.
- `solar_model/simulation.py`: deterministic hourly replay.
- `solar_model/charts.py`: Plotly figures and stable series styling.
- `tests/`: automated behavior and regression coverage.
- `docs/superpowers/`: historical design and implementation planning artifacts.

## Local commands

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m streamlit run app.py
.\.venv\Scripts\python.exe -m pytest -v
```

## Cursor Cloud specific instructions

The Cloud Agent environment is defined by `.cursor/environment.json`. It installs
`python3.12-venv`, creates a `.venv`, and installs the project with dev
dependencies; the `Streamlit` terminal serves the app on port `8501`. On Linux
use the venv directly:

```bash
.venv/bin/python -m pytest -v
.venv/bin/python -m streamlit run app.py
```

The two CSV inputs (`combined-electric-usage.csv`, `combined-monthly-energy.csv`)
are personal, `.gitignore`d, and never present in a fresh checkout. The test
suite is independent of them: `tests/conftest.py` points the app at a committed
deterministic sample dataset (`tests/sample_data.py`) via the
`HOME_ENERGY_MODEL_UTILITY_CSV` / `HOME_ENERGY_MODEL_SOLAR_CSV` overrides, so the
full suite passes without the personal files (the single real-export test skips
when they are absent). The interactive app still shows a data-load error until
you supply the real exports beside `app.py`.

## Working rules

- Preserve the two local CSV inputs and never commit them:
  `combined-electric-usage.csv` and `combined-monthly-energy.csv`.
- Preserve unrelated user changes and untracked files.
- Keep UI code thin. Put data, TOU, simulation, and chart calculations in their
  existing focused modules.
- Maintain hourly AC-bus energy balance and solar-only battery charging unless
  `SPEC.md` is explicitly revised.
- Add or update focused tests for every behavior change.
- Run the relevant focused tests while developing and the full suite before
  claiming completion or committing.
- Treat current prototype limitations as intentional. Avoid production hardening
  unless requested.
- Do not silently correct invalid energy data or model inputs; report concise,
  actionable validation errors.
