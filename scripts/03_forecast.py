#!/usr/bin/env python3
"""Recursive monthly forecast from the Bayesian Phillips curve, writing
outputs/forecast.csv (current-analysis) or outputs/forecast_replication.csv
(--replication).

Matches reference/replication_pkg/bayesm_final_forecast.m's forecast
recursion exactly: for each of the four posterior weight scenarios in
data/estimates*.json, the coefficients are held FIXED (not re-estimated
at each step) and simulated forward month by month --

  dp(t) = b0 + b1 * avg(dp(t-12..t-1)) + a * ur_fixed

-- feeding each month's own forecast back in as a lag for the next,
with the unemployment rate held at its last-observed value for the
entire horizon (the same assumption the notes state explicitly, e.g.
"assuming that the unemployment rate remains at the level observed in
January 2022 ... throughout 2023").

Monthly dp is converted to a synthetic price index (100 * cumprod(exp(dp
mo, cumulative product) telescopes exactly to CPI(t)/CPI(t-12) for any
12-month window with no gaps -- this is an exact reconstruction of
"percent change from 12 months earlier" from the dp series, not an
approximation, since dp(t) = 1200*log(CPI(t)/CPI(t-1)) by construction.

--replication: freezes coefficients at data/estimates_replication.json
  (the Dec-2019 vintage) and forecasts from January 2022 with
  unemployment held at 4.0 percent -- reproducing Kiley (2022b)'s Table 3
  setup exactly, so run_replication.py can check the resulting Q4/Q4
  growth rates against that table's published 2022/2023 figures.

default (current analysis): coefficients from data/estimates.json
  (expanding post-2000 window, latest data), forecasting --horizon
  months (default 36) forward from the latest available month, with
  unemployment held at its own latest observed value.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
OBS_PATH = REPO_ROOT / "data" / "observables.csv"
ESTIMATES_PATH = REPO_ROOT / "data" / "estimates.json"
REPLICATION_ESTIMATES_PATH = REPO_ROOT / "data" / "estimates_replication.json"
OUT_PATH = REPO_ROOT / "outputs" / "forecast.csv"
REPLICATION_OUT_PATH = REPO_ROOT / "outputs" / "forecast_replication.csv"

WEIGHT_SCENARIOS = ["w_0.5", "w_0.2", "w_0.05", "w_0"]
DEFAULT_HORIZON = 36

REPLICATION_ANCHOR = pd.Timestamp("2021-12-01")
REPLICATION_UR = 4.0
REPLICATION_HORIZON = 24  # Jan 2022 .. Dec 2023, spans full 2022 and 2023

# Verified directly (2026-08-29): anchoring at Jan 2022 (treating Jan 2022
# CPI as already-known history) instead of Dec 2021 was a real bug -- the
# note's Table 3 forecasts *for* 2022 starting from Jan 2022 itself, with
# Dec 2021 as the last actual month (unemployment is known faster than CPI:
# Jan 2022's 4.0% UNRATE was already out when only Dec 2021 CPI was in
# hand). Confirmed empirically: swapping in the actual Feb-2022 ALFRED
# vintage of CPILFESL alongside this Dec-2021 anchor reproduces Table 3's
# 2022/2023 figures almost exactly (e.g. w=0.5: 5.82/5.56 vs. the paper's
# 5.8/5.5); see README "Known discrepancy" for what's left over after this
# fix and why.


def load_dp() -> pd.Series:
    df = pd.read_csv(OBS_PATH, parse_dates=["date"]).set_index("date")
    return df["dp"]


def build_index(dp: pd.Series) -> pd.Series:
    """Synthetic price index from monthly annualized log-growth `dp`
    (percent). Base = 100 at the first observation; ratios between any
    two dates are exact and invariant to this normalization."""
    return 100.0 * np.exp(dp.cumsum() / 1200.0)


def pct_12m(index: pd.Series) -> pd.Series:
    return 100.0 * (index / index.shift(12) - 1.0)


def q4_avg(index: pd.Series, year: int) -> float:
    q4 = index[(index.index.year == year) & (index.index.month.isin([10, 11, 12]))]
    if len(q4) != 3:
        raise ValueError(f"expected 3 Q4 months for {year}, got {len(q4)}")
    return float(q4.mean())


def q4q4_growth(index: pd.Series, year: int) -> float:
    return 100.0 * (q4_avg(index, year) / q4_avg(index, year - 1) - 1.0)


def recursive_forecast(dp_hist: pd.Series, beta: dict, ur_fixed: float, horizon: int) -> pd.Series:
    values = list(dp_hist.to_numpy())
    last_date = dp_hist.index[-1]
    out_dates, out_values = [], []
    for h in range(1, horizon + 1):
        avg12 = float(np.mean(values[-12:]))
        next_val = beta["const"]["coef"] + beta["dp_avg12"]["coef"] * avg12 + beta["ur_lag1"]["coef"] * ur_fixed
        values.append(next_val)
        out_dates.append(last_date + pd.DateOffset(months=h))
        out_values.append(next_val)
    return pd.Series(out_values, index=pd.DatetimeIndex(out_dates))


def run(replication: bool, horizon: int) -> pd.DataFrame:
    dp = load_dp()
    estimates_path = REPLICATION_ESTIMATES_PATH if replication else ESTIMATES_PATH
    estimates = json.loads(estimates_path.read_text())

    if replication:
        dp_hist = dp.loc[:REPLICATION_ANCHOR]
        ur_fixed = REPLICATION_UR
        horizon = REPLICATION_HORIZON
    else:
        dp_hist = dp
        ur_fixed = float(pd.read_csv(OBS_PATH, parse_dates=["date"]).set_index("date")["ur"].iloc[-1])

    rows = []
    for d, v in dp_hist.items():
        rows.append({"date": d, "kind": "history", "scenario": "actual", "dp": v})

    for scenario in WEIGHT_SCENARIOS:
        beta = estimates["posterior"][scenario]
        fc = recursive_forecast(dp_hist, beta, ur_fixed, horizon)
        combined_dp = pd.concat([dp_hist, fc])
        combined_index = build_index(combined_dp)
        combined_pct12 = pct_12m(combined_index)
        for d, v in fc.items():
            rows.append({
                "date": d, "kind": "forecast", "scenario": scenario, "dp": v,
                "pct_12m": float(combined_pct12.loc[d]),
            })

    out = pd.DataFrame(rows)
    # fill history pct_12m using the actual (non-scenario-dependent) index
    hist_index = build_index(dp_hist)
    hist_pct12 = pct_12m(hist_index)
    hist_mask = out["kind"] == "history"
    out.loc[hist_mask, "pct_12m"] = out.loc[hist_mask, "date"].map(hist_pct12)
    out["ur_fixed"] = ur_fixed
    return out.sort_values(["scenario", "date"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replication", action="store_true",
                         help="Freeze coefficients at the Dec-2019 vintage and forecast "
                              "from Jan 2022 with UR=4.0, matching Kiley (2022b) Table 3.")
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON,
                         help=f"months to forecast forward (default {DEFAULT_HORIZON}; "
                              "ignored in --replication mode)")
    parser.add_argument("--force", action="store_true", help="rebuild even if up to date")
    args = parser.parse_args()

    out_path = REPLICATION_OUT_PATH if args.replication else OUT_PATH
    estimates_path = REPLICATION_ESTIMATES_PATH if args.replication else ESTIMATES_PATH
    if out_path.exists() and not args.force:
        newest_input = max(OBS_PATH.stat().st_mtime, estimates_path.stat().st_mtime)
        if out_path.stat().st_mtime > newest_input:
            print(f"{out_path} is newer than its inputs, skipping (use --force to rebuild)")
            return

    out = run(args.replication, args.horizon)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(out)} rows)")

    fc = out[out["kind"] == "forecast"]
    print(f"\nForecast horizon: {fc['date'].min().date()}..{fc['date'].max().date()}, "
          f"UR held at {out['ur_fixed'].iloc[0]:.2f}")
    print(f"\n{'date':12s} " + " ".join(f"{s:>8s}" for s in WEIGHT_SCENARIOS))
    for d in sorted(fc["date"].unique())[-6:]:
        row = fc[fc["date"] == d].set_index("scenario")["pct_12m"]
        print(f"{pd.Timestamp(d).date()!s:12s} " + " ".join(f"{row[s]:8.2f}" for s in WEIGHT_SCENARIOS))


if __name__ == "__main__":
    main()
