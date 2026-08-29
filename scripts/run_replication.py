#!/usr/bin/env python3
"""Verify the replication pipeline against Table 2 of Kiley (2022), "Anchored
or Not: A Short Summary of a Bayesian Approach to the Persistence of
Inflation," FEDS Notes (reference/The Fed - Anchored or Not*.html), which
matches reference/ijcb-*.pdf Table 2 in the published version. Runs
01_build_observables.py + 02_estimate.py --replication if needed, then
compares computed b(1)/a coefficients and standard errors to the PAPER_*
constants below, reporting OK/MISMATCH per value.

The paper reports values to 2 decimal places and uses a data vintage
current as of early 2022; ours re-pulls today's latest-revised FRED data
(and starts one month later -- Feb 1958 vs. the paper's Jan 1958, since
FRED's public CPILFESL apparently doesn't reach back quite as far as the
series the paper's own code pulled from), so exact matches aren't
expected -- tolerances below are set to flag genuine discrepancies while
tolerating that level of vintage/sample drift.
"""
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
OBS_PATH = REPO_ROOT / "data" / "observables.csv"
ESTIMATES_PATH = REPO_ROOT / "data" / "estimates_replication.json"

# --- PAPER_* constants (Kiley 2022a/b, Table 2) -------------------------

PAPER_B1 = {"w_0.5": 0.92, "w_0.2": 0.86, "w_0.05": 0.66, "w_0": 0.17,
            "full": 0.95, "pre": 0.97, "post": 0.17}
PAPER_B1_SE = {"w_0.5": 0.03, "w_0.2": 0.05, "w_0.05": 0.10, "w_0": 0.16,
               "full": 0.03, "pre": 0.04, "post": 0.16}
PAPER_A = {"w_0.5": -0.07, "w_0.2": -0.04, "w_0.05": -0.06, "w_0": -0.13,
           "full": -0.19, "pre": -0.32, "post": -0.13}
PAPER_A_SE = {"w_0.5": 0.03, "w_0.2": 0.03, "w_0.05": 0.03, "w_0": 0.04,
              "full": 0.05, "pre": 0.07, "post": 0.04}

TOL_COEF = 0.05
TOL_SE = 0.03

# --- PAPER_* constants (Kiley 2022b, Table 3: Q4/Q4 core CPI forecasts) -
# Forecast from Jan 2022, UR held at 4.0 -- see 03_forecast.py --replication.
PAPER_Q4Q4 = {
    2022: {"w_0.5": 5.8, "w_0.2": 5.4, "w_0.05": 4.5, "w_0": 3.0},
    2023: {"w_0.5": 5.5, "w_0.2": 4.7, "w_0.05": 3.3, "w_0": 2.3},
}
# Looser than TOL_COEF: verified directly (2026-08-29, see README "Known
# discrepancy") that the residual here is subsequent BLS revisions to
# 2020-21 core CPI history propagating through the recursive forecast --
# confirmed by re-running with the actual Feb-2022 ALFRED vintage instead
# of today's revised series, which closes the gap to within noise.
# Observed diffs with today's vintage run +0.09 to +0.31pp across the
# eight checks. This is informational context for that confirmed,
# expected pattern, not a tolerance to quietly widen if a genuine bug
# someday pushes a diff outside it.
TOL_Q4Q4 = 0.5


def check(label: str, computed: float, paper: float, tol: float) -> bool:
    ok = abs(computed - paper) <= tol
    status = "OK     " if ok else "MISMATCH"
    print(f"  {status} {label:14s} computed={computed:+.3f}  paper={paper:+.3f}  "
          f"diff={computed - paper:+.3f}  (tol={tol})")
    return ok


def main():
    import json

    if not OBS_PATH.exists():
        subprocess.run([sys.executable, str(SCRIPTS_DIR / "01_build_observables.py")], check=True)
    subprocess.run([sys.executable, str(SCRIPTS_DIR / "02_estimate.py"),
                     "--replication", "--force"], check=True)

    result = json.loads(ESTIMATES_PATH.read_text())
    all_ok = True

    print("\n=== b(1): coefficient on 12-month average lagged inflation ===")
    for label in PAPER_B1:
        c = result["posterior"][label] if label.startswith("w_") else result["classical"][label]
        all_ok &= check(label, c["dp_avg12"]["coef"], PAPER_B1[label], TOL_COEF)
        all_ok &= check(f"{label}.se", c["dp_avg12"]["se"], PAPER_B1_SE[label], TOL_SE)

    print("\n=== a: Phillips curve slope on lagged unemployment ===")
    for label in PAPER_A:
        c = result["posterior"][label] if label.startswith("w_") else result["classical"][label]
        all_ok &= check(label, c["ur_lag1"]["coef"], PAPER_A[label], TOL_COEF)
        all_ok &= check(f"{label}.se", c["ur_lag1"]["se"], PAPER_A_SE[label], TOL_SE)

    print("\n=== Q4/Q4 core CPI forecast vs. Kiley (2022b) Table 3 ===")
    subprocess.run([sys.executable, str(SCRIPTS_DIR / "03_forecast.py"),
                     "--replication", "--force"], check=True)
    import importlib.util
    import pandas as pd
    spec = importlib.util.spec_from_file_location("fc03", SCRIPTS_DIR / "03_forecast.py")
    fc03 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fc03)
    fc_df = pd.read_csv(REPO_ROOT / "outputs" / "forecast_replication.csv", parse_dates=["date"])
    for year in PAPER_Q4Q4:
        for scenario, paper_val in PAPER_Q4Q4[year].items():
            sub = fc_df[fc_df["scenario"].isin(["actual", scenario])].drop_duplicates("date")
            sub = sub.set_index("date").sort_index()
            index = fc03.build_index(sub["dp"])
            growth = fc03.q4q4_growth(index, year)
            all_ok &= check(f"{year}.{scenario}", growth, paper_val, TOL_Q4Q4)

    print(f"\n{'ALL CHECKS OK' if all_ok else 'SOME CHECKS MISMATCHED'} "
          f"(sample: pre={result['sample']['pre']} post={result['sample']['post']}, "
          f"today's FRED vintage vs. the paper's own early-2022 vintage)")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
