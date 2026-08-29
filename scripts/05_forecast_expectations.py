#!/usr/bin/env python3
"""Recursive monthly forecast from the expectations-augmented Phillips
curve (04_estimate_expectations.py), writing outputs/forecast_expectations.csv.

Same recursion convention as 03_forecast.py: coefficients held FIXED at
their current-analysis (1996-latest) values, unemployment held at its
last observed value for the whole horizon. Inflation expectations
(infl_exp_lag1) are ALSO held fixed at their last observed MICH reading
-- there's no future survey wave to use instead, so "expectations stay
where they currently are" is the natural analogue of "unemployment stays
where it currently is."

The "pure" spec has no backward-looking (dp_avg12) term at all, so it
has no period-to-period feedback loop: every forecast month is identical,
b0 + g*infl_exp_fixed + a*ur_fixed, forecast once and repeated for the
whole horizon. This is a deliberate, substantive contrast with the
"hybrid" spec (which still decays/converges like the persistence model,
via its own dp_avg12 term) and with 03_forecast.py's Bayesian scenarios
-- not a limitation of the forecast code, see lib_index.recursive_forecast.
"""
import argparse
import json
from pathlib import Path

import pandas as pd

from lib_index import build_index, pct_12m, recursive_forecast

REPO_ROOT = Path(__file__).resolve().parent.parent
OBS_PATH = REPO_ROOT / "data" / "observables.csv"
ESTIMATES_PATH = REPO_ROOT / "data" / "estimates_expectations.json"
OUT_PATH = REPO_ROOT / "outputs" / "forecast_expectations.csv"

DEFAULT_HORIZON = 36
SPECS = ["pure", "hybrid"]


def flat_beta(spec_estimates: dict, regressors: list[str]) -> dict:
    return {name: spec_estimates[name]["coef"] for name in ["const"] + regressors}


def run(horizon: int) -> pd.DataFrame:
    obs = pd.read_csv(OBS_PATH, parse_dates=["date"]).set_index("date")
    dp_hist = obs["dp"].dropna()
    ur_fixed = float(obs["ur"].dropna().iloc[-1])
    infl_exp_fixed = float(obs["infl_exp"].dropna().iloc[-1])

    estimates = json.loads(ESTIMATES_PATH.read_text())

    rows = []
    for d, v in dp_hist.items():
        rows.append({"date": d, "kind": "history", "scenario": "actual", "dp": v})

    regressors_by_spec = {
        "pure": ["infl_exp_lag1", "ur_lag1"],
        "hybrid": ["infl_exp_lag1", "dp_avg12", "ur_lag1"],
    }
    for spec in SPECS:
        regressors = regressors_by_spec[spec]
        beta = flat_beta(estimates["specs"][spec], regressors)
        exog_fixed = {"ur_lag1": ur_fixed, "infl_exp_lag1": infl_exp_fixed}
        fc = recursive_forecast(dp_hist, beta, exog_fixed, horizon)
        combined = pd.concat([dp_hist, fc])
        combined_pct12 = pct_12m(build_index(combined))
        for d, v in fc.items():
            rows.append({
                "date": d, "kind": "forecast", "scenario": spec, "dp": v,
                "pct_12m": float(combined_pct12.loc[d]),
            })

    out = pd.DataFrame(rows)
    hist_pct12 = pct_12m(build_index(dp_hist))
    hist_mask = out["kind"] == "history"
    out.loc[hist_mask, "pct_12m"] = out.loc[hist_mask, "date"].map(hist_pct12)
    out["ur_fixed"] = ur_fixed
    out["infl_exp_fixed"] = infl_exp_fixed
    return out.sort_values(["scenario", "date"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON,
                         help=f"months to forecast forward (default {DEFAULT_HORIZON})")
    parser.add_argument("--force", action="store_true", help="rebuild even if up to date")
    args = parser.parse_args()

    if OUT_PATH.exists() and not args.force:
        newest_input = max(OBS_PATH.stat().st_mtime, ESTIMATES_PATH.stat().st_mtime)
        if OUT_PATH.stat().st_mtime > newest_input:
            print(f"{OUT_PATH} is newer than its inputs, skipping (use --force to rebuild)")
            return

    out = run(args.horizon)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_PATH, index=False)
    print(f"Wrote {OUT_PATH} ({len(out)} rows)")

    fc = out[out["kind"] == "forecast"]
    print(f"\nForecast horizon: {fc['date'].min().date()}..{fc['date'].max().date()}, "
          f"UR held at {out['ur_fixed'].iloc[0]:.2f}, "
          f"infl_exp held at {out['infl_exp_fixed'].iloc[0]:.2f}")
    print(f"\n{'date':12s} " + " ".join(f"{s:>8s}" for s in SPECS))
    for d in sorted(fc["date"].unique())[-6:]:
        row = fc[fc["date"] == d].set_index("scenario")["pct_12m"]
        print(f"{pd.Timestamp(d).date()!s:12s} " + " ".join(f"{row[s]:8.2f}" for s in SPECS))


if __name__ == "__main__":
    main()
