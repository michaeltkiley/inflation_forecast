# inflation_forecast — Bayesian Phillips Curve

Self-contained pipeline (data + estimation + forecast + dashboard in one
repo, unlike the heavier `output_gap`/Dynare projects, since these
models are cheap OLS) served at `michaeltkiley.github.io/inflation_forecast/`
alongside `termprem`, `resource_utilization`, and `equilibrium_rate`
(nav-link/tracker-card addition to the main site not yet done -- see
"What's not done").

This replicates and extends the author's own published research on a
Bayesian Phillips curve, then keeps it running against the latest data.

Based on:
- Kiley, M. T. (2022), "Anchored or Not: How Much Information Does 21st
  Century Data Contain on Inflation Dynamics?", FEDS 2022-016, published
  in the *International Journal of Central Banking* (`reference/ijcb-*.pdf`)
- Kiley, M. T. (2023), "A (Bayesian) Update on Inflation and Inflation
  Persistence," FEDS Notes (`reference/The Fed - A (Bayesian) Update*.html`)

**Validation: all 36 replication checks pass** (`scripts/run_replication.py`)
— 28 coefficient/standard-error checks against Kiley (2022b) Table 2
(computed vs. paper, e.g. w=0.5 posterior b(1): **0.918 vs. 0.920**), plus
8 Q4/Q4 forecast checks against Kiley (2022b) Table 3 (e.g. w=0.5, 2022:
**6.09 vs. 5.80**, see "Known discrepancy" below).

## The model

A Phillips curve in which core CPI inflation depends on its own recent
average and lagged unemployment:

```
dp(t) = b0 + b1 * avg(dp(t-1..t-12)) + a * ur(t-1) + e(t)
```

- `dp`: core CPI inflation, monthly, annualized -- `1200*log(CPILFESL(t)/CPILFESL(t-1))`.
- `ur`: the civilian unemployment rate (`UNRATE`).

Estimated three ways and combined via natural-conjugate Bayesian updating:

1. **Pre** (before Jan 2000): OLS fit, used as the Bayesian prior
   `Γ ~ N(B_pre, V)` with `V` = the pre-sample's own OLS coefficient
   covariance -- an empirical-Bayes prior, not an independently
   elicited one.
2. **Post** (Jan 2000 onward): OLS fit, the likelihood.
3. **Posterior**, at four levels of conviction in the prior --
   `loose = (1-w)/w` for prior weight `w = 0.5, 0.2, 0.05, ~0`, i.e.
   `loose = 1, 4, 19, 10000`:

   ```
   posterior_vcv  = (inv(loose*V) + inv(vcv_post))^-1
   posterior_beta = posterior_vcv @ (inv(loose*V)@B_pre + s2_post^-1 * X_post'Y_post)
   ```

An anchored/well-behaved Phillips curve has small `b1`; an unanchored,
highly persistent one has `b1` near 1.

**Intercept**: the FEDS notes' prose says "a constant term is
suppressed" in equation (1), but the author's own replication code
(`reference/replication_pkg/bayesm_final.m`) includes one throughout
(`c_all`/`B_all(1)` etc.). The code is ground truth here -- an intercept
is included. Documented discrepancy, not a bug in this pipeline.

## Pipeline

```
scripts/00_ingest_fred.py       FRED: CPILFESL, UNRATE, MICH, JCXFEMD (SEP) -> data/fred.duckdb
scripts/01_build_observables.py data/fred.duckdb -> data/observables.csv
                                 (dp, dp_avg12, ur, ur_lag1, infl_exp, infl_exp_lag1)
scripts/02_estimate.py          data/observables.csv -> data/estimates.json
                                 (or --replication -> estimates_replication.json)
scripts/03_forecast.py          data/observables.csv + data/estimates*.json
                                 -> outputs/forecast.csv (or forecast_replication.csv)
scripts/run_replication.py      runs 01/02/03 in --replication mode and checks
                                 the result against the PAPER_* constants below

scripts/04_estimate_expectations.py  data/observables.csv -> data/estimates_expectations.json
scripts/05_forecast_expectations.py  -> outputs/forecast_expectations.csv
scripts/06_backtest_expectations.py  -> outputs/expectations_backtest.csv
scripts/lib_index.py                 shared OLS/price-index/recursive-forecast helpers
                                      (see "Expectations-augmented Phillips curve" below)

scripts/07_ingest_spf.py             Philly Fed SPF median core CPI -> data/*_spf_corecpi.csv
scripts/08_build_dashboard.py        forecast*.csv + SPF + SEP (JCXFEMD) -> docs/index.html
scripts/dashboard_template.html      static shell + JS chart/table renderer (see "Dashboard" below)
```

```
python3 scripts/00_ingest_fred.py
python3 scripts/01_build_observables.py
python3 scripts/02_estimate.py
python3 scripts/03_forecast.py
python3 scripts/run_replication.py   # verification only, writes *_replication.* siblings

python3 scripts/04_estimate_expectations.py
python3 scripts/05_forecast_expectations.py
python3 scripts/06_backtest_expectations.py

python3 scripts/07_ingest_spf.py
python3 scripts/08_build_dashboard.py
```

`data/` and `outputs/` are gitignored (regenerated on every run, matching
the sibling dashboards' convention).

## Sample windows

- **Pre**: everything before Jan 2000 (starts as early as CPILFESL/UNRATE
  allow a full trailing window -- FRED's public `CPILFESL` starts close
  to but not identical with the FAME `cpixfe` mnemonic the original
  paper's code pulled from, `reference/replication_pkg/getdat_m.inp`; a
  one-month difference here doesn't affect the replication checks below).
  Fixed in both `--replication` and current-analysis modes.
- **Post, `--replication`**: Jan 2000-Dec 2019, matching Kiley (2022a)'s
  own sample exactly (data truncated at 2019-12-01 throughout).
- **Post, current analysis**: Jan 2000 through the latest available
  month -- **expanding**, an explicit user choice (2026-08-29). This
  matches the papers' own prose (the 2023 update describes "uses data
  from 2000-23") over what `reference/replication_pkg/bayesm_final_june2023.m`
  literally computes: that script hardcodes "post" as the *trailing 240
  months*, which only coincided with "since Jan 2000" because the 2022
  vintage's sample happened to end exactly Dec 2019. Once the sample
  runs past ~2020, a literal reading of that script would silently drop
  2000-2002 from the informative window every month going forward --
  read as an unrefreshed magic number carried over from the original
  script, not a deliberate rolling-window design.

## Forecast

`scripts/03_forecast.py` simulates each of the four posterior scenarios
forward month by month with **coefficients held fixed** (not
re-estimated at each step) and **unemployment held at its last observed
value** for the whole horizon -- exactly
`reference/replication_pkg/bayesm_final_forecast.m`'s recursion:

```
dp(t) = b0 + b1 * avg(dp(t-12..t-1)) + a * ur_fixed
```

feeding each month's forecast back in as a lag for the next. Monthly
`dp` is converted to a synthetic price index
(`100 * exp(cumsum(dp)/1200)`) whose ratios exactly reconstruct
"percent change from N months earlier" -- not an approximation, since
`dp(t) = 1200*log(CPI(t)/CPI(t-1))` by construction, so the cumulative
product telescopes exactly to `CPI(t)/CPI(t-k)` for any k-month window.
**Primary display series: 12-month % change** (the "percent change from
12 months earlier" measure used in the notes' own data charts), an
explicit user choice (2026-08-29) over Q4/Q4 annual or the raw monthly
annualized rate.

`--replication` freezes coefficients at the Dec-2019 vintage
(`estimates_replication.json`) and forecasts from Jan 2022 with UR fixed
at 4.0%, reproducing Kiley (2022b) Table 3's setup so
`run_replication.py` can check the resulting Q4/Q4 growth against that
table's published figures.

## Known discrepancy: Q4/Q4 forecast runs ~0.1-0.3pp above the paper

Table 2's coefficients replicate almost exactly (within 0.02 on `b1`
across all four weights) -- confirmed further by loading the author's
own saved posterior coefficients directly from
`reference/replication_pkg/bayes_2021m.mat` (`B_post1`) and finding them
within 0.003 of this pipeline's independently re-estimated values.

The Table 3 forecast check runs consistently higher than the paper --
originally by 0.4-0.6pp, investigated directly (2026-08-29) rather than
left as a guess:

1. **Feeding the author's own exact `B_post1` coefficients into this
   pipeline's recursion reproduced the same ~0.4-0.6pp gap**, ruling out
   coefficient-estimation differences as the cause.
2. **A genuine bug**: the forecast was anchored at Jan 2022 (treating
   Jan 2022 CPI as already-known history), but Table 3 forecasts *for*
   2022 starting from Jan 2022 itself, with Dec 2021 as the last actual
   month -- unemployment is reported faster than CPI, so the note's
   "level observed in January 2022, 4.0 percent" was already known when
   only Dec 2021 CPI was in hand. Fixing the anchor to Dec 2021 (now
   reflected in `03_forecast.py`'s `REPLICATION_ANCHOR`) closed roughly
   half the gap on its own.
3. **The remainder is genuine BLS revision** to 2020-21 core CPI history,
   confirmed directly by pulling the actual Feb-2022 ALFRED vintage of
   `CPILFESL` (`alfredgraph.csv?id=CPILFESL&vintage_date=2022-02-01`) and
   re-running the (now-corrected) recursion against it instead of
   today's fully-revised series: the result lands almost exactly on
   Table 3 (w=0.5: **5.82 vs. 5.80** for 2022, **5.56 vs. 5.50** for
   2023). Individual monthly revisions between that vintage and today
   run up to ~1pp in `dp` terms (e.g. March 2021: 4.06 vintage vs. 2.95
   current) even though they largely cancel over a full 12-month window
   (~0.02pp net) -- consistent with routine seasonal-factor
   re-estimation, not a one-directional rebasing.

With both fixes, the remaining gap using today's data is **0.09-0.31pp**
across all eight checks (down from 0.36-0.59pp) -- `run_replication.py`'s
tolerance was tightened from 0.75pp to 0.5pp accordingly.

## Data gap: Oct 2025 core CPI/unemployment

FRED's `CPILFESL`/`UNRATE` have a genuine hole at 2025-10-01 (both NaN;
`MICH`, privately run by the University of Michigan, has a normal
reading that month) -- almost certainly the Oct-2025 government shutdown
disrupting BLS's CPI/employment releases, and never backfilled even ten
months later (confirmed by direct inspection, 2026-08-29). Handled two
different ways depending on position, an explicit user choice
(2026-08-29):

- **Interior** (real data on both neighboring months): linearly
  interpolated from those two neighbors
  (`01_build_observables.py`'s `interpolate_interior_gaps`, capped at a
  single missing month). This is a one-time, self-resolving situation --
  once the following month's data exists, as it now does, there's no
  reason to keep routing around that one month as if it were still
  unknown.
- **Trailing edge** (the most recent month, not yet published): never
  interpolated -- there's no future neighbor to interpolate from -- and
  left as a genuinely shorter sample, same as any monthly series always
  is between a reference month ending and its data being published. This
  is the normal, self-resolving condition every live monthly dashboard
  has at its leading edge (resolves the moment the next release lands),
  not a data-quality problem requiring special handling. `dp_avg12`'s
  `min_periods=10` (of 12) is a backstop for this and for any future gap
  the single-month interpolation limit doesn't catch, so one bad month
  can never again silently manufacture a much longer artificial gap in
  the current-analysis sample than actually exists -- which is what
  happened before this fix (a strict 12-of-12 window turned this one
  missing month into a ~10-month-long, entirely artificial truncation of
  the current-analysis sample, cutting it off at Sep 2025 instead of the
  actual latest month with real CPILFESL data).

## Expectations-augmented Phillips curve

A second, independent model living alongside the Bayesian persistence
model above. Instead of assuming inflation is persistent because it
mechanically depends on its own recent past, this model assumes people's
own survey-reported expectations of future inflation drive current
inflation -- a genuinely different theory of *why* inflation persists,
not just a variant of the first model (an explicit user choice, 2026-08-29).

Based on:
- Kiley, M. T. (2015), "Low Inflation in the United States: A Summary of
  Recent Research," FEDS Notes (`reference/FRB_* Low Inflation*.html`)
- Roberts, J. M. (1995), "New Keynesian Economics and the Phillips
  Curve," *Journal of Money, Credit and Banking* 27(4), 975-984

```
scripts/04_estimate_expectations.py  data/observables.csv -> data/estimates_expectations.json
scripts/05_forecast_expectations.py  -> outputs/forecast_expectations.csv (live forward forecast)
scripts/06_backtest_expectations.py  -> outputs/expectations_backtest.csv (pseudo-real-time track record)
scripts/lib_index.py                 shared OLS/price-index/recursive-forecast helpers
```

Two specs, both plain OLS on a single sample from **Jan 1996** (Kiley
2015 figures 2/3's own "1996-2014" post-1995, more-anchored-looking
period) **through the latest month** -- expanding, not fixed at 2014,
an explicit user choice (2026-08-29):

- **Pure**: `dp(t) = b0 + g*infl_exp(t-1) + a*ur(t-1) + e(t)` -- Michigan
  survey (`MICH`) 1-year-ahead expected inflation directly replaces the
  lagged-inflation term, per the 2015 note's own framing ("expectations
  replacing lagged inflation").
- **Hybrid**: `dp(t) = b0 + g*infl_exp(t-1) + b1*avg(dp(t-1..t-12)) + a*ur(t-1) + e(t)`
  -- the Roberts (1995) lineage, backward- and forward-looking terms
  together.

Current fit (1996-01 through 2026-07, n=367): pure has a properly
negatively-sloped Phillips curve (g=0.661, a=-0.186, both several
standard errors from zero) even over a sample spanning 2021-23 -- unlike
the persistence model, whose post-2000 slope has gone essentially flat
(+0.004) once that period is included unexcluded. In the hybrid, the
backward-looking term dominates (b1=0.706 vs. g=0.222) and the
unemployment slope collapses toward zero (a=-0.012) -- consistent with
the standard hybrid-NKPC finding that combined backward+forward weights
sum close to 1 (0.706+0.222=0.928 here).

**No Bayesian pre/post weighting**: that machinery in the persistence
model exists because lagged-inflation persistence is hard to pin down
from a stable sample (few large deviations = little information --
Kiley 2022's central point). Survey expectations don't have that same
information problem across a sample that already includes 2021-23, so a
single-sample OLS fit is used directly.

**Forecast** (`05_forecast_expectations.py`): same recursion convention
as `03_forecast.py` -- coefficients held fixed, unemployment held at its
last observed value. Expectations (`infl_exp_lag1`) are *also* held
fixed at their last MICH reading, the natural analogue of holding
unemployment fixed (there's no future survey wave to substitute). The
**pure** spec has no backward-looking term at all, so it has no
period-to-period feedback: every forecast month is identical, forecast
once and repeated flat for the whole horizon -- a deliberate,
substantively interesting contrast with the hybrid spec (which still
decays/converges via its own `dp_avg12` term) and with the persistence
model's four slowly-converging scenarios, not a bug.

**Backtest** (`06_backtest_expectations.py`): pseudo-real-time,
one-step-ahead walk-forward evaluation -- an explicit user choice
(2026-08-29): "estimate up to last data point, use coefficients to
forecast, add data point, re-estimate, etc." At each month *t*, fit OLS
on data strictly before *t*, forecast `dp(t)` against the regressors
*actually observed* as of *t*, record the error, then advance. No
forward simulation is needed for this (unlike the live forecast above):
every regressor is already lagged by construction, so the values needed
to forecast month *t* are, by definition, already known once *t-1*'s
data exists -- a genuine one-step-ahead pseudo-out-of-sample forecast,
not an approximation of one. First fit uses `MIN_TRAIN_MONTHS=60` (5
years) of data, a documented but somewhat arbitrary floor, not derived
from a formal power calculation. Current result (2001-01 through
2026-07, n=307 each): hybrid RMSE 1.409, pure RMSE 1.502 (both in `dp`'s
own monthly-annualized-percent units) -- hybrid modestly outperforms
pure on this one-step-ahead track record. This produces a track record
of *monthly* forecasts, not the 12-month-% change the live forecast
displays; a 12-month-ahead comparable backtest would need the recursive
multi-step machinery instead, not attempted here.

## Dashboard

`docs/index.html` (built by `08_build_dashboard.py` from
`dashboard_template.html`) is what GitHub Pages serves. Two design
choices, both explicit user calls (2026-08-29):

- **One chart, not two**, despite there being 7 lines (actual + 4
  Bayesian weights + pure/hybrid expectations) -- resolved by treating
  the 4 Bayesian weights as an *ordered* quantity (weight on the prior,
  0->0.5) drawn as a single-hue light-to-dark sequential ramp, not 4
  arbitrary colors, with the 2 expectations specs as a separate
  categorical orange/green pair. A legend click toggles any line off.
  Colors are hand-checked for WCAG contrast and CVD separation (each
  ramp step >=3:1 against its surface in both themes; the two
  categorical colors pass standard/deutan/tritan separation) and
  implemented as theme-aware CSS custom properties
  (`--series-w50`, `--series-w20`, `--series-w05`, `--series-w00`,
  `--series-pure`, `--series-hybrid`), referenced from the JS/JSON data
  as literal `"var(--series-w50)"` strings rather than baked-in hex --
  the same pattern `../termprem`'s template already uses -- so light/dark
  mode need no JS logic at all, just the browser's own CSS cascade. (An
  earlier version baked in light-mode-only hex values; all 4 blues
  collapsed into one indistinguishable shade in dark mode until this was
  fixed.)
- **All 4 Bayesian weights always shown**, even when two are numerically
  near-identical (e.g. w=0.05 and the uninformative prior currently both
  read 2.4-2.5%, since the post-2000 sample now carries enough of its
  own information that a small residual prior weight barely matters) --
  not conditionally hidden. Dynamically suppressing a "redundant" line
  would need an arbitrary closeness threshold and would change the
  chart's/table's row count from update to update depending on data
  vintage, which is a more confusing dashboard than two overlapping
  lines (self-explanatory on the chart) or two similar numbers (labeled
  in the table, not hidden).

The banner table computes This-Year/Next-Year Q4/Q4 growth "in real
time": `lib_index.q4q4_growth` runs on each scenario's own combined
actual+forecast index, so a year already partly realized mixes real
months with that scenario's forecast for the rest -- no special-casing
needed, it falls out of q4q4_growth not caring where a given month's
`dp` came from. SPF (`07_ingest_spf.py`, Philly Fed's `CORECPIA`/`CORECPIB`)
and SEP (`JCXFEMD`, FRED) sit in reference rows at the bottom; SEP is
explicitly labeled core *PCE* (not core CPI, unlike every row above it)
since the Fed's own 2 percent target and every other row here are on
different price indices that run at different average levels -- not a
directly comparable figure without that caveat.

## What's not done

- The main site's nav-link/tracker-card integration
  (`michaeltkiley.github.io`) -- this repo's own dashboard is built and
  screenshot-verified (light/dark mode, legend toggle, hover tooltip,
  mobile), but it isn't linked from the main site yet.
- A scheduled CI workflow (GitHub Actions) -- doesn't exist yet, matching
  `output_gap`'s own "not yet done" for `rstar`/`unemployment_risk`.
- Uncertainty bands on the forecast (the posterior coefficient covariance
  is available in `estimates.json` but not yet propagated through the
  recursive simulation into a forecast interval).
- The `altdp` (core PCE) series in `getdat_m.inp` and the `bayesm_robust.m`
  alternative lag structure -- both present in the reference replication
  package as the papers' own robustness checks, not wired into this
  pipeline.
- **No `run_replication.py`-style verification for the expectations
  model**: unlike the persistence model, Kiley (2015) doesn't publish a
  fitted equation with reported coefficients (see the model's own
  docstring/README section) -- Figures 2 and 3 there are illustrative
  scatterplots, not a regression table -- so there's no `PAPER_*`
  constant to check this pipeline's `pure`/`hybrid` coefficients against.
  The persistence-model-style audit trail (compute, then compare to a
  hardcoded published value) isn't available here; correctness rests on
  the OLS/recursion code being the same code already validated against
  Kiley (2022b)'s Table 2/3, not on an independent external check.
- Uncertainty bands and a 12-month-ahead (rather than one-step) version
  of the expectations model's backtest -- see "Backtest" above.
