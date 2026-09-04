# Enphase Battery Strategies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit Full Backup and transparent historical-cost battery strategies while preserving the current Self-Consumption and fixed-TOU behavior for the Enphase IQ Battery 10C and custom batteries.

**Architecture:** Keep the existing hourly AC-bus simulation as the source of energy flows. Add a focused optimizer that computes a solar-only charge and home-load-only discharge schedule over the selected historical hours, then feed that schedule through the same result and balance checks as the rule-based strategies. Keep grid permissions, outages, Storm Guard, and utility-event dispatch out of this change.

**Tech Stack:** Python 3.11, pandas, NumPy, SciPy linear programming, Streamlit, Plotly, pytest, Streamlit AppTest.

**Spec:** `SPEC.md`, especially sections 3, 9.2, 10, 12, 15, and 16, updated by this plan to record the approved behavior.

## Global Constraints

- `SPEC.md` remains authoritative and changes in the same branch as behavior.
- The simulator remains an hourly deterministic replay and preserves AC-bus energy balance.
- Battery charging remains solar-only and battery discharge remains home-load-only in every strategy in this change.
- The cost optimizer uses recorded future hours and is labeled historical foresight, not Enphase AI Optimization.
- Full Backup begins at 100% state of charge, holds 100% reserve while on-grid, and never discharges.
- Existing configuration files containing `TOU reserve` continue to load and normalize to `Fixed TOU reserve`.
- The two ignored CSV inputs remain unmodified and uncommitted.
- No grid charging, battery export, outage replay, Storm Guard, or utility-event dispatch is added.

---

### Task 1: Simulation strategies and historical-cost optimizer

**Files:**
- Create: `solar_model/optimization.py`
- Modify: `solar_model/simulation.py`
- Modify: `pyproject.toml`
- Modify: `SPEC.md`
- Test: `tests/test_simulation.py`
- Test: `tests/test_optimization.py`

**Interfaces:**
- Consumes: normalized hourly columns, `TouRule`, battery capacity/reserve/efficiency/power, and `export_rate_per_kwh`.
- Produces: `optimize_historical_dispatch(hourly, battery, tou_rules, export_rate_per_kwh) -> tuple[np.ndarray, np.ndarray]`, returning hourly AC-side charge inputs and discharge outputs.
- Produces: `SimulationConfig.strategy` values `self_consumption`, `tou_reserve`, `cost_optimized`, and `full_backup`, plus optional `export_rate_per_kwh`.

- [ ] **Step 1: Write failing Full Backup tests**

Add tests proving that Full Backup starts at 100%, retains 100% state of charge, does not discharge into a load deficit, and rejects no otherwise-valid user reserve because its effective reserve is profile-controlled.

- [ ] **Step 2: Run the Full Backup tests and verify RED**

Run: `python -m pytest tests/test_simulation.py -k full_backup -v`

Expected: FAIL because `full_backup` is not an accepted strategy and no effective 100% state is applied.

- [ ] **Step 3: Implement minimal Full Backup dispatch**

Extend the strategy type and validation. For Full Backup, use effective starting state and reserve equal to capacity and prevent on-grid discharge while retaining direct solar use and normal export.

- [ ] **Step 4: Run the Full Backup tests and verify GREEN**

Run: `python -m pytest tests/test_simulation.py -k full_backup -v`

Expected: PASS.

- [ ] **Step 5: Write failing optimizer tests**

Cover these observable cases with small hourly frames:

```python
def test_optimizer_preserves_limited_energy_for_the_higher_price_hour():
    # One stored kWh, two load deficits, later price is higher.
    # The first hour imports and the later hour discharges.

def test_optimizer_charges_solar_when_later_avoided_import_exceeds_export_credit():
    # Midday surplus is stored and later offsets a high-price deficit.

def test_optimizer_exports_solar_when_storage_loss_makes_charging_uneconomic():
    # A high export price exceeds the efficiency-adjusted avoided import value.

def test_cost_optimized_simulation_requires_an_export_rate():
    # Missing dispatch price is rejected with an actionable validation error.
```

- [ ] **Step 6: Run optimizer tests and verify RED**

Run: `python -m pytest tests/test_optimization.py tests/test_simulation.py -k "optimizer or optimized" -v`

Expected: FAIL because the optimizer module and strategy do not exist.

- [ ] **Step 7: Add SciPy and implement the minimum linear model**

Add `scipy>=1.11` to runtime dependencies. In `optimization.py`, use `scipy.optimize.linprog` with hourly charge, discharge, and state-of-charge variables. Bound charge by solar surplus and charge power; bound discharge by load deficit and discharge power; enforce reserve, capacity, efficiency, and chronological state transitions. Minimize lost export credits plus avoided-import cost, and raise `SimulationValidationError` through the simulation boundary when prices are missing or optimization fails.

- [ ] **Step 8: Route the optimized schedule through simulation**

Pass `export_rate_per_kwh` in `SimulationConfig`. For `cost_optimized`, consume the precomputed charge/discharge arrays while retaining the common grid-flow calculation and AC-bus balance assertion. Keep the other strategies' decisions unchanged.

- [ ] **Step 9: Run focused simulation and optimizer tests**

Run: `python -m pytest tests/test_optimization.py tests/test_simulation.py -v`

Expected: PASS.

- [ ] **Step 10: Update the authoritative specification**

Document all four strategies, define historical foresight and its boundary behavior, state that optimization covers the full selected period, and retain the explicit non-goals for grid charging, battery export, forecasts, outages, Storm Guard, and utility events.

- [ ] **Step 11: Commit Task 1 after focused verification**

```powershell
git add pyproject.toml solar_model/optimization.py solar_model/simulation.py tests/test_optimization.py tests/test_simulation.py SPEC.md
git commit -m "feat: add full-backup and cost-optimized dispatch"
```

---

### Task 2: Configuration and strategy controls

**Files:**
- Modify: `app.py`
- Modify: `solar_model/configuration.py`
- Modify: `SPEC.md`
- Test: `tests/test_app.py`
- Test: `tests/test_configuration.py`

**Interfaces:**
- Consumes: the four internal strategy names from Task 1.
- Produces: UI labels `Self-consumption`, `Fixed TOU reserve`, `Cost optimized (historical foresight)`, and `Full backup`.
- Produces: configuration normalization from legacy `TOU reserve` to `Fixed TOU reserve` without changing schema version 1.

- [ ] **Step 1: Write failing configuration tests**

Add tests that accept and round-trip the three new labels, normalize legacy `TOU reserve`, and retain the user's editable starting charge and reserve values when Full Backup is selected.

- [ ] **Step 2: Run configuration tests and verify RED**

Run: `python -m pytest tests/test_configuration.py -k "strategy or reserve" -v`

Expected: FAIL because the new labels are rejected and legacy normalization is absent.

- [ ] **Step 3: Implement strategy-label validation and normalization**

Expand the allowed configuration values and normalize legacy `TOU reserve` to the new fixed-TOU label in the validated document. Do not mutate or discard the stored starting-charge and reserve values.

- [ ] **Step 4: Run configuration tests and verify GREEN**

Run: `python -m pytest tests/test_configuration.py -k "strategy or reserve" -v`

Expected: PASS.

- [ ] **Step 5: Write failing AppTest coverage**

Add tests proving the strategy selector contains the four approved labels, Full Backup displays disabled effective 100% starting charge and reserve, switching back restores the prior editable values, and the optimized strategy renders its historical-foresight/degradation caveat.

- [ ] **Step 6: Run AppTest cases and verify RED**

Run: `python -m pytest tests/test_app.py -k "strategy or full_backup or historical_foresight" -v`

Expected: FAIL because the new controls and copy are absent.

- [ ] **Step 7: Implement the Streamlit controls**

Map labels to internal strategy values, pass the System-model export rate to `SimulationConfig`, show separate disabled 100% widgets for Full Backup, and preserve the user's common values under their existing session/configuration keys. Add concise captions explaining fixed TOU, historical hindsight, utility-energy-only optimization, and Full Backup's on-grid scope.

- [ ] **Step 8: Run focused AppTest and configuration tests**

Run: `python -m pytest tests/test_app.py tests/test_configuration.py -k "strategy or full_backup or historical_foresight or battery" -v`

Expected: PASS.

- [ ] **Step 9: Reconcile SPEC wording with final UI labels**

Ensure `SPEC.md` exactly matches the displayed labels, disabled Full Backup values, persistence behavior, and the backward-compatible configuration normalization.

- [ ] **Step 10: Commit Task 2 after focused verification**

```powershell
git add app.py solar_model/configuration.py tests/test_app.py tests/test_configuration.py SPEC.md
git commit -m "feat: expose expanded battery strategies"
```

---

### Task 3: Strategy comparison metrics

**Files:**
- Create: `solar_model/metrics.py`
- Modify: `app.py`
- Modify: `SPEC.md`
- Test: `tests/test_metrics.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: hourly simulation results, usable capacity, effective reserve, and round-trip efficiency.
- Produces: `summarize_simulation(result, capacity_kwh, reserve_percent, round_trip_efficiency) -> SimulationSummary` containing solar self-consumption percentage, expensive-period grid import, discharged energy, equivalent full cycles, and ending state of charge.

- [ ] **Step 1: Write failing metric unit tests**

Use small frames to define zero-solar behavior, self-consumed solar as production minus grid export, expensive-period import, discharge totals, equivalent full cycles based on battery-side discharged energy divided by usable capacity, and ending state of charge.

- [ ] **Step 2: Run metric tests and verify RED**

Run: `python -m pytest tests/test_metrics.py -v`

Expected: FAIL because `solar_model.metrics` does not exist.

- [ ] **Step 3: Implement the metric helper**

Create a frozen `SimulationSummary` dataclass and pure summary function. Return zero equivalent cycles when usable capacity above reserve is zero, and return zero solar self-consumption percentage when modeled solar is zero.

- [ ] **Step 4: Run metric tests and verify GREEN**

Run: `python -m pytest tests/test_metrics.py -v`

Expected: PASS.

- [ ] **Step 5: Write failing AppTest for displayed metrics**

Assert the System model shows solar self-consumption, peak/expensive-period import, battery discharged, equivalent cycles, and ending charge without changing the existing Projected cost value.

- [ ] **Step 6: Run the AppTest and verify RED**

Run: `python -m pytest tests/test_app.py -k strategy_metrics -v`

Expected: FAIL because the metrics are not rendered.

- [ ] **Step 7: Render compact comparison metrics**

Compute the summary outside `app.py` and render the values below the existing top-level totals. Use `Expensive-period grid import` rather than `Peak` because configured TOU rules are user-editable.

- [ ] **Step 8: Run focused metric and app tests**

Run: `python -m pytest tests/test_metrics.py tests/test_app.py -k "metrics or projected_cost" -v`

Expected: PASS.

- [ ] **Step 9: Update SPEC results and acceptance criteria**

Define each metric and its zero-denominator behavior. Confirm aggregation remains presentation-only and metrics use hourly results.

- [ ] **Step 10: Commit Task 3 after focused verification**

```powershell
git add solar_model/metrics.py app.py tests/test_metrics.py tests/test_app.py SPEC.md
git commit -m "feat: add battery strategy comparison metrics"
```

---

### Task 4: Documentation, regression verification, and review

**Files:**
- Modify: `README.md`
- Modify: `SPEC.md`
- Review: all branch changes

**Interfaces:**
- Consumes: final labels, strategy semantics, metrics, and deferred-scope statements.
- Produces: user-facing run guidance and a branch ready for an explicit integration choice.

- [ ] **Step 1: Update README strategy guidance**

Describe the four choices, explain that historical foresight is an idealized bill-cost comparison, and state that grid charging/export, outage behavior, Storm Guard, and utility-event control are not simulated.

- [ ] **Step 2: Run documentation consistency searches**

Run: `rg -n "TOU reserve|Fixed TOU|Cost optimized|Full backup|grid charging|battery export|Storm Guard" README.md SPEC.md app.py solar_model tests`

Expected: legacy `TOU reserve` appears only where backward compatibility or the internal `tou_reserve` identifier is intentional.

- [ ] **Step 3: Run the complete automated suite**

Run: `python -m pytest -v`

Expected: all tests pass with no unexpected warnings or errors.

- [ ] **Step 4: Run a Streamlit smoke check**

Launch the app locally and inspect all four strategy selections, Full Backup disabled values, historical-foresight caption, result metrics, and navigation persistence using the real CSV inputs.

- [ ] **Step 5: Review the complete branch diff**

Run: `git diff --check` and `git diff main...HEAD --stat`, then request an independent code review against this plan and `SPEC.md`. Resolve every Critical or Important finding with a new failing test before its fix.

- [ ] **Step 6: Re-run full verification after review fixes**

Run: `python -m pytest -v` and `git diff --check`.

Expected: all tests pass and whitespace validation reports no errors.

- [ ] **Step 7: Commit final documentation or review corrections**

```powershell
git add README.md SPEC.md
git commit -m "docs: explain battery strategy modeling"
```

- [ ] **Step 8: Stop for the user's integration choice**

Report the isolated worktree path, commits, verification evidence, deferred phase, and review findings. Do not push, open a pull request, merge, or remove the worktree without explicit user direction.
