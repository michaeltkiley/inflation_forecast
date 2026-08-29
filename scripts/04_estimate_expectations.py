#!/usr/bin/env python3
"""Fit the expectations-augmented Phillips curve from data/observables.csv,
writing data/estimates_expectations.json.

Two specs, both plain OLS (no Bayesian weighting -- see rationale below),
fit on a single expanding sample from Jan 1996 through the latest month
with Michigan survey data available:

  pure    dp(t) = b0 + g*infl_exp_lag1(t) + a*ur_lag1(t) + e(t)
  hybrid  dp(t) = b0 + g*infl_exp_lag1(t) + b1*dp_avg12(t) + a*ur_lag1(t) + e(t)

Per Kiley (2015), "Low Inflation in the United States: A Summary of
Recent Research" (reference/FRB_* Low Inflation*.html), which frames
"expectations replacing lagged inflation" (the pure spec) as one
candidate explanation for the post-1995 flattening of the reduced-form
Phillips curve; and Roberts (1995), "New Keynesian Economics and the
Phillips Curve" (JMCB), whose hybrid backward+forward-looking
specification the hybrid spec follows -- an explicit user choice
(2026-08-29) over the pure substitution the 2015 note itself describes.

pi_e(t) is the University of Michigan Survey of Consumers' median
1-year-ahead expected inflation (MICH), lagged one month for the same
real-time-availability reason as ur_lag1 (see 01_build_observables.py).

Sample start: Jan 1996, matching Kiley (2015) figures 2/3's own
"1996-2014" post-1995 (flatter, more-anchored-looking) period exactly --
an explicit user choice (2026-08-29) to estimate only over the period
the note itself identifies as anchored, rather than spanning the
1976-1995 regime change within a single fit.

No Bayesian pre/post weighting here, unlike 02_estimate.py: that
machinery exists because 1960-99-vs-2000-19 lagged-inflation persistence
is hard to pin down from a stable sample (Kiley 2022's whole point --
few large deviations means little information). Survey expectations
don't have that same information problem across 1996-present (which
includes the 2021-23 inflation surge), so a single-sample OLS fit is
used directly -- also an explicit user choice (2026-08-29).
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from lib_index import ols, coef_dict

REPO_ROOT = Path(__file__).resolve().parent.parent
OBS_PATH = REPO_ROOT / "data" / "observables.csv"
OUT_PATH = REPO_ROOT / "data" / "estimates_expectations.json"

SAMPLE_START = "1996-01-01"

SPECS = {
    "pure": ["infl_exp_lag1", "ur_lag1"],
    "hybrid": ["infl_exp_lag1", "dp_avg12", "ur_lag1"],
}


def load_observables() -> pd.DataFrame:
    df = pd.read_csv(OBS_PATH, parse_dates=["date"]).set_index("date")
    df = df.loc[SAMPLE_START:]
    return df.dropna(subset=["infl_exp_lag1", "dp_avg12", "ur_lag1", "dp"])


def design_matrix(df: pd.DataFrame, regressors: list[str]) -> tuple[np.ndarray, np.ndarray]:
    X = np.column_stack([np.ones(len(df))] + [df[r].to_numpy() for r in regressors])
    y = df["dp"].to_numpy()
    return X, y


def run() -> dict:
    df = load_observables()
    out = {
        "sample": [str(df.index.min().date()), str(df.index.max().date())],
        "specs": {},
    }
    for label, regressors in SPECS.items():
        X, y = design_matrix(df, regressors)
        fit = ols(X, y)
        out["specs"][label] = {
            "n": fit["n"],
            "s2": fit["s2"],
            **coef_dict(fit["beta"], fit["vcv"], ["const"] + regressors),
        }
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="rebuild even if up to date")
    args = parser.parse_args()

    if OUT_PATH.exists() and not args.force:
        if OUT_PATH.stat().st_mtime > OBS_PATH.stat().st_mtime:
            print(f"{OUT_PATH} is newer than {OBS_PATH.name}, skipping (use --force to rebuild)")
            return

    result = run()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"Wrote {OUT_PATH}")
    print(f"\nSample: {result['sample']}")
    for label, regressors in SPECS.items():
        c = result["specs"][label]
        print(f"\n{label} (n={c['n']}):")
        for name in ["const"] + regressors:
            print(f"  {name:15s} {c[name]['coef']:8.3f}  (se {c[name]['se']:.3f})")


if __name__ == "__main__":
    main()
