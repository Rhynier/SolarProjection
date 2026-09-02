# Home Energy Model

This is a local Streamlit prototype for exploring historical household energy
use and replaying it with different solar and battery assumptions. It is not a
production service: it has no accounts, database, cost calculation, forecast,
or scenario persistence.

## Run locally

Python 3.11 is required. From the project directory, install the prototype and
development test dependency:

```powershell
python -m pip install -e ".[dev]"
streamlit run app.py
```

Run the automated checks with:

```powershell
python -m pytest -v
```

## Local inputs and assumptions

Keep these uncommitted files in the project root:

- `combined-electric-usage.csv`, with `DATE`, `START TIME`, `END TIME`,
  `IMPORT (kWh)`, `EXPORT (kWh)`, `COST`, and `NOTES`.
- `combined-monthly-energy.csv`, with `Date/Time` and
  `Energy Produced (Wh)`.

The app aligns matching utility and solar hours. Its estimated household load
is `grid import + actual solar production - grid export` (all in kWh).

The system model replays selected historical hours. It scales solar production
only; the historical household-load curve stays fixed. The battery charges from
solar surplus only, never from the grid. Both self-consumption and TOU-reserve
strategies obey usable capacity, reserve, starting charge, AC-side charge and
discharge limits, and symmetric per-leg efficiency derived from the configured
round-trip efficiency. The TOU editor starts with SMUD's published 2026 rates,
without holiday exceptions. TOU reserve derives Cheap, Less Expensive, and
Expensive tiers from each season's configured prices and discharges only at the
seasonal maximum.

The CSVs and Streamlit session settings remain local and uncommitted. Restart
the app after replacing either CSV export.
