#!/usr/bin/env python3
"""Build the monthly panel for the Bayesian Phillips curve from
data/fred.duckdb (00_ingest_fred.py), writing data/observables.csv.

Variable construction follows Kiley (2022), "Anchored or Not: How Much
Information Does 21st Century Data Contain on Inflation Dynamics?", FEDS
2022-016 (reference/ijcb-*.pdf), Section 2, equation (1) --
cross-checked directly against the author's own replication code:

  dp        Delta p(t): core CPI inflation, monthly, annualized --
            1200*log(CPILFESL(t)/CPILFESL(t-1)), percent, exactly
            matching the original paper's own construction.
  dp_avg12  sum_{j=1}^{12} Delta p(t-j) / 12: backward 12-month average
            of dp, lagged one month relative to dp(t) itself -- the
            right-hand-side persistence regressor in equation (1).
            Algebraically identical to the original paper's own
            four-3-month-block construction, confirmed by construction
            (each block is a plain 3-month moving average of dp, and the
            four blocks tile lags 1-12 with no overlap).
  ur        u(t): the unemployment rate itself (UNRATE), for reference.
  ur_lag1   u(t-1): one-month-lagged unemployment rate -- the Phillips
            curve slope regressor in equation (1), confirmed to line up
            with dp(t) the same way the original paper's own code does.

Sample starts once dp_avg12 has a full 12 months of prior dp behind it
(dp itself needs one prior CPI observation) -- i.e. 13 months after the
first CPI observation, matching the papers' own "Jan. 1958-Dec. 2019"
full-sample start (CPILFESL/UNRATE both begin 1957 on FRED). Runs
through the latest month with both series available; 02_estimate.py
handles the replication-vs-current-analysis sample windowing (fixed
pre-2000/2000-2019 vs. expanding-window pre-2000/2000-latest).

FRED's CPILFESL/UNRATE have a genuine gap at 2025-10-01 (both NaN; MICH,
privately run, has a normal reading that month -- almost certainly the
Oct-2025 government shutdown disrupting BLS's CPI/employment releases;
confirmed by direct inspection 2026-08-29, and BLS never backfilled it
even a year later). Handled two ways, deliberately different by
position:

  - INTERIOR gaps (real data on both neighboring months) are linearly
    interpolated from those two neighbors (`interpolate_interior_gaps`,
    limited to single-month gaps) -- an explicit user choice
    (2026-08-29) over leaving it as a hole a 12-month trailing average
    has to route around. This is a one-time, self-resolving situation:
    once the following month's data exists (as it now does), there's no
    reason to keep treating that single month as missing.
  - The TRAILING edge (the most recent month, not yet published) is
    never interpolated -- there's no future neighbor to interpolate
    from -- and is left as a genuinely shorter sample, same as any
    monthly series always is between a reference month ending and its
    data being published. `dp_avg12`'s min_periods=DP_AVG12_MIN_MONTHS
    (10 of 12, not a strict 12-of-12) is a backstop for this and for any
    future gap interpolation doesn't catch (e.g. 2+ consecutive missing
    months), so one bad month can't silently manufacture a much longer
    artificial gap in the current-analysis sample than actually exists.

Also carries two columns for the expectations-augmented Phillips curve
(04_estimate_expectations.py onward), per Kiley (2015), "Low Inflation
in the United States: A Summary of Recent Research" (reference/FRB_*
Low Inflation*.html) and Roberts (1995), "New Keynesian Economics and
the Phillips Curve":

  infl_exp      pi_e(t): University of Michigan Survey of Consumers'
                median expected price change over the next 12 months
                (MICH), for reference.
  infl_exp_lag1 pi_e(t-1): one-month-lagged, the expectations regressor
                -- lagged for the same reason as ur_lag1 (the publicly
                known expectation *before* dp(t) is realized, not a
                contemporaneous/look-ahead value).

MICH starts 1978 (21 years after CPILFESL/UNRATE), so these two columns
are deliberately left nullable (NaN before 1979) rather than folded into
the main dropna -- truncating the whole panel to 1978+ would break the
Bayesian persistence model's pre-2000 prior sample above. Downstream
expectations-model scripts do their own dropna on the columns they use.
"""
import argparse
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "fred.duckdb"
OUT_PATH = REPO_ROOT / "data" / "observables.csv"

LAGS = 12
DP_AVG12_MIN_MONTHS = 10


def load_wide(con) -> pd.DataFrame:
    df = con.execute("SELECT series_id, obs_date, value FROM fred_raw").fetchdf()
    wide = df.pivot(index="obs_date", columns="series_id", values="value")
    wide.index = pd.to_datetime(wide.index)
    return wide.sort_index()


def interpolate_interior_gaps(s: pd.Series) -> pd.Series:
    """Linearly fill single-month gaps that have real data on both
    neighboring months. Never touches a gap at the start or end of the
    series (limit_area="inside") -- there's nothing on the far side of a
    trailing-edge gap (the most recent, not-yet-published month) to
    interpolate from, so that's left as a genuinely shorter sample."""
    return s.interpolate(method="linear", limit=1, limit_area="inside")


def build(con) -> pd.DataFrame:
    w = load_wide(con)
    w["CPILFESL"] = interpolate_interior_gaps(w["CPILFESL"])
    w["UNRATE"] = interpolate_interior_gaps(w["UNRATE"])

    dp = 1200 * np.log(w["CPILFESL"] / w["CPILFESL"].shift(1))
    dp_avg12 = dp.rolling(LAGS, min_periods=DP_AVG12_MIN_MONTHS).mean().shift(1)

    obs = pd.DataFrame(index=w.index)
    obs["dp"] = dp
    obs["dp_avg12"] = dp_avg12
    obs["ur"] = w["UNRATE"]
    obs["ur_lag1"] = w["UNRATE"].shift(1)

    obs = obs.dropna(how="any")

    # MICH (1978+) is nullable -- joined back in after the base dropna so
    # it doesn't truncate the 1958-start persistence-model sample above.
    obs["infl_exp"] = w["MICH"]
    obs["infl_exp_lag1"] = w["MICH"].shift(1)
    return obs


def sanity_check(obs: pd.DataFrame):
    print("\nSanity summary:")
    print(f"{'series':10s} {'n':>5s} {'mean':>8s} {'std':>8s} {'min':>8s} {'max':>8s}")
    for col in ["dp", "dp_avg12", "ur", "ur_lag1", "infl_exp", "infl_exp_lag1"]:
        s = obs[col].dropna()
        print(f"{col:10s} {len(s):5d} {s.mean():8.3f} {s.std():8.3f} "
              f"{s.min():8.3f} {s.max():8.3f}")
    checks = {
        "dp": (obs["dp"].mean(), -2.0, 8.0),
        "dp_avg12": (obs["dp_avg12"].mean(), -2.0, 8.0),
        "ur": (obs["ur"].mean(), 2.0, 12.0),
        "infl_exp": (obs["infl_exp"].mean(), 0.0, 8.0),
    }
    print("\nPlausibility bounds:")
    for name, (val, lo, hi) in checks.items():
        status = "OK" if lo <= val <= hi else "CHECK"
        print(f"  {status:5s} {name}: {val:.3f} (expected [{lo}, {hi}])")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="rebuild even if up to date")
    args = parser.parse_args()

    if OUT_PATH.exists() and not args.force:
        if OUT_PATH.stat().st_mtime > DB_PATH.stat().st_mtime:
            print(f"{OUT_PATH} is newer than {DB_PATH.name}, skipping (use --force to rebuild)")
            return

    con = duckdb.connect(str(DB_PATH), read_only=True)
    obs = build(con)
    con.close()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out = obs.reset_index().rename(columns={"obs_date": "date"})
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(OUT_PATH, index=False)
    print(f"Wrote {OUT_PATH} ({len(out)} months, {out['date'].iloc[0]}..{out['date'].iloc[-1]})")

    sanity_check(obs)


if __name__ == "__main__":
    main()
