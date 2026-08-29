#!/usr/bin/env python3
"""Fit the Bayesian Phillips curve from data/observables.csv, writing
data/estimates.json (current-analysis) or data/estimates_replication.json
(--replication).

Model (Kiley 2022, FEDS 2022-016, equation 1; cross-checked against the
author's own replication code):

  dp(t) = b0 + b1 * dp_avg12(t) + a * ur_lag1(t) + e(t)

fit by OLS on three windows -- "pre" (before Jan 2000), "post" (Jan 2000
onward), and "full" (pre+post) -- then combined into four Bayesian
posteriors that treat the "pre" OLS fit as an empirical prior (mean =
B_pre, covariance = V = vcv_pre) and "post" as the likelihood, at four
levels of conviction in the prior:

  posterior = (P^-1 + D^-1)^-1 (P^-1 * B_pre + D^-1_data-only-term)

  where P = loose * vcv_pre (the prior covariance, loosened by `loose`)
  and the data term is rvar_post^-1 * X_post'Y_post (the post-sample's
  own OLS normal equations). This is the exact formula the author's own
  code computes (`B_post1`) -- verified line-by-line against that code,
  not independently re-derived. `loose = (1-w)/w` for the paper's four
  prior weights w = 0.5, 0.2, 0.05, ~0 (loose = 1, 4, 19, 10000).

NOTE on the intercept: the FEDS notes' prose says "a constant term is
suppressed" in equation (1), but the author's own code includes a
column of ones (`c_all`) and reports/uses `B_all(1)` etc. as a real
intercept throughout. The code is the ground truth for replication here;
an intercept is included. This is a known prose/code discrepancy, not a
bug introduced by this pipeline.

--replication: fixed sample matching Kiley (2022a) exactly -- "pre" is
  everything before Jan 2000, "post" is Jan 2000 through Dec 2019 (data
  truncated at 2019-12-01 throughout, matching the author's own
  1957:1-2019:12 pull). Checked against the paper's own Table 2 by
  run_replication.py.

default (current analysis): "post" expands from Jan 2000 through the
  latest available month -- an explicit user choice (2026-08-29),
  matching the papers' own prose ("uses data from 2000-23" in the 2023
  update) over what the paper's own June-2023 update code literally
  computes (a rolling trailing-240-month "post" window, which would drop
  2000-2002 once the sample runs past ~2020) -- that hardcoded 240 looks
  like an unrefreshed magic number carried over from the original 2022
  code (where trailing-240-months and "since Jan 2000" coincided only
  because the sample happened to end exactly Dec 2019), not a deliberate
  rolling-window design.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
OBS_PATH = REPO_ROOT / "data" / "observables.csv"
OUT_PATH = REPO_ROOT / "data" / "estimates.json"
REPLICATION_OUT_PATH = REPO_ROOT / "data" / "estimates_replication.json"

PRE_POST_SPLIT = "2000-01-01"
REPLICATION_SAMPLE_END = "2019-12-01"

REGRESSORS = ["dp_avg12", "ur_lag1"]
WEIGHTS = [
    ("w_0.5", 1.0),
    ("w_0.2", 4.0),
    ("w_0.05", 19.0),
    ("w_0", 10000.0),
]


def load_observables() -> pd.DataFrame:
    df = pd.read_csv(OBS_PATH, parse_dates=["date"])
    return df.set_index("date")


def design_matrix(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    X = np.column_stack([np.ones(len(df))] + [df[r].to_numpy() for r in REGRESSORS])
    y = df["dp"].to_numpy()
    return X, y


def ols(X: np.ndarray, y: np.ndarray) -> dict:
    n, k = X.shape
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    resid = y - X @ beta
    s2 = float(resid @ resid / (n - k))
    vcv = s2 * XtX_inv
    return {"beta": beta, "vcv": vcv, "s2": s2, "n": n}


def coef_dict(beta: np.ndarray, vcv: np.ndarray) -> dict:
    names = ["const"] + REGRESSORS
    return {
        name: {"coef": float(beta[i]), "se": float(np.sqrt(vcv[i, i]))}
        for i, name in enumerate(names)
    }


def posterior(fit_pre: dict, fit_post: dict, loose: float) -> dict:
    prior_precision = np.linalg.inv(loose * fit_pre["vcv"])
    data_precision = np.linalg.inv(fit_post["vcv"])
    post_vcv = np.linalg.inv(prior_precision + data_precision)
    data_term = (1.0 / fit_post["s2"]) * (fit_post["X"].T @ fit_post["y"])
    post_beta = post_vcv @ (prior_precision @ fit_pre["beta"] + data_term)
    return {"beta": post_beta, "vcv": post_vcv}


def run(replication: bool) -> dict:
    df = load_observables()
    if replication:
        df = df.loc[:REPLICATION_SAMPLE_END]

    split = pd.Timestamp(PRE_POST_SPLIT)
    df_pre = df[df.index < split]
    df_post = df[df.index >= split]

    X_pre, y_pre = design_matrix(df_pre)
    X_post, y_post = design_matrix(df_post)
    X_all, y_all = design_matrix(df)

    fit_pre = ols(X_pre, y_pre)
    fit_post = ols(X_post, y_post)
    fit_all = ols(X_all, y_all)
    fit_post["X"], fit_post["y"] = X_post, y_post

    out = {
        "replication": replication,
        "sample": {
            "pre": [str(df_pre.index.min().date()), str(df_pre.index.max().date())],
            "post": [str(df_post.index.min().date()), str(df_post.index.max().date())],
            "full": [str(df.index.min().date()), str(df.index.max().date())],
        },
        "classical": {
            "pre": {**coef_dict(fit_pre["beta"], fit_pre["vcv"]), "n": fit_pre["n"]},
            "post": {**coef_dict(fit_post["beta"], fit_post["vcv"]), "n": fit_post["n"]},
            "full": {**coef_dict(fit_all["beta"], fit_all["vcv"]), "n": fit_all["n"]},
        },
        "posterior": {},
    }

    for label, loose in WEIGHTS:
        post = posterior(fit_pre, fit_post, loose)
        out["posterior"][label] = {
            "loose": loose,
            **coef_dict(post["beta"], post["vcv"]),
        }

    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replication", action="store_true",
                         help="Fixed pre-2000/2000-2019 sample matching Kiley (2022a) exactly.")
    parser.add_argument("--force", action="store_true", help="rebuild even if up to date")
    args = parser.parse_args()

    out_path = REPLICATION_OUT_PATH if args.replication else OUT_PATH
    if out_path.exists() and not args.force:
        if out_path.stat().st_mtime > OBS_PATH.stat().st_mtime:
            print(f"{out_path} is newer than {OBS_PATH.name}, skipping (use --force to rebuild)")
            return

    result = run(args.replication)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))
    print(f"Wrote {out_path}")
    print(f"\nSample: pre={result['sample']['pre']} post={result['sample']['post']}")
    print(f"\n{'scenario':10s} {'b1':>8s} {'se(b1)':>8s} {'a':>8s} {'se(a)':>8s}")
    for label in ["pre", "post", "full"]:
        c = result["classical"][label]
        print(f"{label:10s} {c['dp_avg12']['coef']:8.3f} {c['dp_avg12']['se']:8.3f} "
              f"{c['ur_lag1']['coef']:8.3f} {c['ur_lag1']['se']:8.3f}")
    for label, _ in WEIGHTS:
        c = result["posterior"][label]
        print(f"{label:10s} {c['dp_avg12']['coef']:8.3f} {c['dp_avg12']['se']:8.3f} "
              f"{c['ur_lag1']['coef']:8.3f} {c['ur_lag1']['se']:8.3f}")


if __name__ == "__main__":
    main()
