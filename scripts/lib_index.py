"""Shared OLS / price-index / recursive-forecast helpers used by both the
Bayesian persistence model (02_estimate.py, 03_forecast.py) and the
expectations-augmented model (04_estimate_expectations.py onward).
Extracted once a second model needed the same machinery, matching the
lib_*.py convention in the sibling dashboards (e.g. ../termprem/scripts/lib_var.py).
"""
import numpy as np
import pandas as pd


def ols(X: np.ndarray, y: np.ndarray) -> dict:
    n, k = X.shape
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    resid = y - X @ beta
    s2 = float(resid @ resid / (n - k))
    vcv = s2 * XtX_inv
    return {"beta": beta, "vcv": vcv, "s2": s2, "n": n}


def coef_dict(beta: np.ndarray, vcv: np.ndarray, names: list[str]) -> dict:
    return {
        name: {"coef": float(beta[i]), "se": float(np.sqrt(vcv[i, i]))}
        for i, name in enumerate(names)
    }


def build_index(dp: pd.Series) -> pd.Series:
    """Synthetic price index from monthly annualized log-growth `dp`
    (percent). Base = 100 at the first observation; ratios between any
    two dates are exact and invariant to this normalization, since
    dp(t) = 1200*log(CPI(t)/CPI(t-1)) by construction."""
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


def recursive_forecast(dp_hist: pd.Series, beta: dict, exog_fixed: dict, horizon: int,
                        persistence_key: str = "dp_avg12", persistence_lags: int = 12) -> pd.Series:
    """Simulate dp forward `horizon` months with FIXED coefficients `beta`
    ({regressor_name: coef}, plus "const") and FIXED exogenous regressor
    values `exog_fixed` ({regressor_name: value}, held constant the whole
    horizon -- e.g. {"ur_lag1": 4.1} or {"ur_lag1": 4.1, "infl_exp_lag1": 4.2}).

    If `persistence_key` is a key of `beta`, it's treated as an ENDOGENOUS
    backward-looking term: the trailing `persistence_lags`-month average of
    the dp path itself (mixing real history and this function's own prior
    forecast steps), recomputed and fed back in at every step -- matching
    the original paper's own forecast recursion exactly.
    If `persistence_key` is absent from `beta` (e.g. the "pure" expectations
    spec, which has no lagged-inflation term at all), there is no such
    feedback loop, and every forecast month is identical: b0 plus the fixed
    exogenous terms, forecast once and repeated for the whole horizon --
    a deliberate, substantive contrast with the persistence model's slow
    convergence, not a limitation of this function.
    """
    values = list(dp_hist.to_numpy())
    last_date = dp_hist.index[-1]
    out_dates, out_values = [], []
    for h in range(1, horizon + 1):
        total = beta["const"]
        if persistence_key in beta:
            avg = float(np.mean(values[-persistence_lags:]))
            total += beta[persistence_key] * avg
        for name, val in exog_fixed.items():
            total += beta[name] * val
        values.append(total)
        out_dates.append(last_date + pd.DateOffset(months=h))
        out_values.append(total)
    return pd.Series(out_values, index=pd.DatetimeIndex(out_dates))
