#!/usr/bin/env python3
"""Pseudo-real-time, one-step-ahead walk-forward evaluation of the
expectations-augmented Phillips curve, writing outputs/expectations_backtest.csv.

For each month t (starting once MIN_TRAIN_MONTHS of data exist from
Jan 1996): fit OLS on data strictly BEFORE t, then forecast dp(t) using
that fit against the regressors *actually observed* as of t. Record the
forecast, the realized dp(t), and the error. Advance to t+1 (t's actual
data is now part of history) and repeat -- an explicit user choice
(2026-08-29): "estimate up to last data point, use coefficients to
forecast, add data point, re-estimate, etc."

No forward simulation or "hold regressors fixed" step is needed here
(contrast 05_forecast_expectations.py): infl_exp_lag1, dp_avg12, and
ur_lag1 are all already-lagged by construction (see
01_build_observables.py), so the regressor values needed to forecast
month t are, by definition, already known the moment t-1's data exists
-- this is a genuine one-step-ahead pseudo-out-of-sample forecast, not
an approximation of one. This also means the result is a track record of
MONTHLY annualized-rate forecasts (dp), not the 12-month-% forecast
05_forecast_expectations.py displays -- turning a walk-forward one-step
track record into a comparable 12-month-ahead one would need the
recursive multi-step machinery instead, not attempted here.

MIN_TRAIN_MONTHS = 60 (5 years): a floor on how little data the first
walk-forward fit is allowed to use, for a 3-4 parameter OLS -- an
explicit, somewhat arbitrary but documented choice (2026-08-29), not
derived from a formal power calculation.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from lib_index import ols

REPO_ROOT = Path(__file__).resolve().parent.parent
OBS_PATH = REPO_ROOT / "data" / "observables.csv"
OUT_PATH = REPO_ROOT / "outputs" / "expectations_backtest.csv"

SAMPLE_START = "1996-01-01"
MIN_TRAIN_MONTHS = 60

SPECS = {
    "pure": ["infl_exp_lag1", "ur_lag1"],
    "hybrid": ["infl_exp_lag1", "dp_avg12", "ur_lag1"],
}


def load_observables() -> pd.DataFrame:
    df = pd.read_csv(OBS_PATH, parse_dates=["date"]).set_index("date")
    df = df.loc[SAMPLE_START:]
    return df.dropna(subset=["infl_exp_lag1", "dp_avg12", "ur_lag1", "dp"])


def design_row(row: pd.Series, regressors: list[str]) -> np.ndarray:
    return np.concatenate([[1.0], row[regressors].to_numpy()])


def run() -> pd.DataFrame:
    df = load_observables()
    rows = []
    for label, regressors in SPECS.items():
        X_full = np.column_stack([np.ones(len(df))] + [df[r].to_numpy() for r in regressors])
        y_full = df["dp"].to_numpy()
        for t_idx in range(MIN_TRAIN_MONTHS, len(df)):
            X_train, y_train = X_full[:t_idx], y_full[:t_idx]
            fit = ols(X_train, y_train)
            x_t = X_full[t_idx]
            forecast = float(x_t @ fit["beta"])
            actual = float(y_full[t_idx])
            rows.append({
                "date": df.index[t_idx], "spec": label,
                "forecast_dp": forecast, "actual_dp": actual,
                "error": actual - forecast, "n_train": t_idx,
            })
    return pd.DataFrame(rows).sort_values(["spec", "date"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="rebuild even if up to date")
    args = parser.parse_args()

    if OUT_PATH.exists() and not args.force:
        if OUT_PATH.stat().st_mtime > OBS_PATH.stat().st_mtime:
            print(f"{OUT_PATH} is newer than {OBS_PATH.name}, skipping (use --force to rebuild)")
            return

    out = run()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_PATH, index=False)
    print(f"Wrote {OUT_PATH} ({len(out)} rows)")

    print(f"\n{'spec':8s} {'n':>5s} {'rmse':>8s} {'mean_err':>10s} {'date_range'}")
    for label, sub in out.groupby("spec"):
        rmse = float(np.sqrt(np.mean(sub["error"] ** 2)))
        mean_err = float(sub["error"].mean())
        print(f"{label:8s} {len(sub):5d} {rmse:8.3f} {mean_err:10.3f} "
              f"{sub['date'].min().date()}..{sub['date'].max().date()}")


if __name__ == "__main__":
    main()
