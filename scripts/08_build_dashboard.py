#!/usr/bin/env python3
"""Build docs/index.html from scripts/dashboard_template.html, outputs/forecast.csv,
outputs/forecast_expectations.csv, the latest data/*_spf_corecpi.csv, and
data/fred.duckdb's JCXFEMD (SEP) pull.

One chart (12-month % change, actual history + all 6 forecast scenarios --
an explicit user choice, 2026-08-29, over splitting persistence vs.
expectations into two charts) plus a banner table of This-Year/Next-Year
Q4/Q4 growth for every scenario plus SPF and SEP, computed "rolling in
real time": Q4/Q4 for a year already partly realized mixes actual data
(for the months that have happened) with each scenario's own forecast
(for the months that haven't) -- lib_index.q4q4_growth doesn't care which
source a given month's dp came from, so this falls out for free from the
same combined actual+forecast index used for the chart.

CURRENT_YEAR/NEXT_YEAR are today's calendar year and the one after --
not the last month of actual data's year -- so the banner always reads
as "this year" / "next year" to a visitor, even mid-forecast-horizon.

SEP (JCXFEMD, median core PCE) is flagged in its own row with a
core-PCE-not-core-CPI note -- see 00_ingest_fred.py's docstring -- never
silently placed as if directly comparable to the core-CPI-based rows
above it.
"""
import argparse
import json
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from lib_index import build_index, q4q4_growth

REPO_ROOT = Path(__file__).resolve().parent.parent
FORECAST_PATH = REPO_ROOT / "outputs" / "forecast.csv"
FORECAST_EXP_PATH = REPO_ROOT / "outputs" / "forecast_expectations.csv"
DB_PATH = REPO_ROOT / "data" / "fred.duckdb"
DATA_DIR = REPO_ROOT / "data"
TEMPLATE_PATH = Path(__file__).resolve().parent / "dashboard_template.html"
OUT_PATH = REPO_ROOT / "docs" / "index.html"

CHART_YEARS_BACK = 15
CHART_START = pd.Timestamp(date.today().replace(year=date.today().year - CHART_YEARS_BACK, day=1))

PERSISTENCE_SCENARIOS = [
    ("w_0.5", "Bayesian, weight on prior = 0.5", "var(--series-w50)"),
    ("w_0.2", "Bayesian, weight on prior = 0.2", "var(--series-w20)"),
    ("w_0.05", "Bayesian, weight on prior = 0.05", "var(--series-w05)"),
    ("w_0", "Bayesian, uninformative prior", "var(--series-w00)"),
]
EXPECTATIONS_SCENARIOS = [
    ("pure", "Expectations (pure)", "var(--series-pure)"),
    ("hybrid", "Expectations (hybrid)", "var(--series-hybrid)"),
]
ACTUAL_COLOR = "var(--series-actual)"
REFERENCE_COLOR = "var(--series-ref)"


def scenario_dp_series(df: pd.DataFrame, scenario: str) -> pd.Series:
    hist = df[df["kind"] == "history"].drop_duplicates("date").set_index("date")["dp"]
    fc = df[(df["kind"] == "forecast") & (df["scenario"] == scenario)].set_index("date")["dp"]
    out = pd.concat([hist, fc]).sort_index()
    out.index = pd.to_datetime(out.index)
    return out


def scenario_pct12_series(df: pd.DataFrame, scenario: str) -> pd.Series:
    hist = df[df["kind"] == "history"].drop_duplicates("date").set_index("date")["pct_12m"]
    fc = df[(df["kind"] == "forecast") & (df["scenario"] == scenario)].set_index("date")["pct_12m"]
    out = pd.concat([hist, fc]).sort_index()
    out.index = pd.to_datetime(out.index)
    return out


def latest_spf() -> dict:
    files = sorted(DATA_DIR.glob("*_spf_corecpi.csv"))
    if not files:
        return {}
    df = pd.read_csv(files[-1])
    row = df.iloc[-1]
    return {
        "survey": f"{int(row['YEAR'])}Q{int(row['QUARTER'])}",
        "this_year": float(row["CORECPIA"]),
        "next_year": float(row["CORECPIB"]),
    }


def latest_sep(current_year: int, next_year: int) -> dict:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    rows = con.execute(
        "SELECT obs_date, value FROM fred_raw WHERE series_id = 'JCXFEMD'"
    ).fetchall()
    con.close()
    by_year = {d.year: v for d, v in rows}
    return {
        "this_year": by_year.get(current_year),
        "next_year": by_year.get(next_year),
    }


def build_chart_data(forecast: pd.DataFrame, forecast_exp: pd.DataFrame) -> dict:
    actual = scenario_pct12_series(forecast, PERSISTENCE_SCENARIOS[0][0])
    actual_hist = forecast[forecast["kind"] == "history"].drop_duplicates("date").set_index("date")["pct_12m"]
    actual_hist.index = pd.to_datetime(actual_hist.index)

    all_dates = sorted(set(actual_hist.loc[CHART_START:].index)
                        | set(scenario_pct12_series(forecast, PERSISTENCE_SCENARIOS[0][0]).index)
                        | set(scenario_pct12_series(forecast_exp, EXPECTATIONS_SCENARIOS[0][0]).index))
    all_dates = [d for d in all_dates if d >= pd.Timestamp(CHART_START)]

    last_hist_date = actual_hist.index.max()

    def series_for(source_df, scenario, side):
        """`side` gates which half of last_hist_date survives -- "actual"
        only shows the pre-fork history, and each forecast scenario only
        shows from the fork point onward (both draw from the same shared
        history otherwise, which would just be 7 perfectly overlapping
        paths wastefully redrawn underneath the actual line)."""
        s = scenario_pct12_series(source_df, scenario).reindex(all_dates)
        out = []
        for d, v in zip(all_dates, s):
            include = d <= last_hist_date if side == "history" else d >= last_hist_date
            out.append(None if (not include or pd.isna(v)) else round(float(v), 3))
        return out

    series = {"actual": series_for(forecast, PERSISTENCE_SCENARIOS[0][0], "history")}
    for key, _, _ in PERSISTENCE_SCENARIOS:
        series[key] = series_for(forecast, key, "forecast")
    for key, _, _ in EXPECTATIONS_SCENARIOS:
        series[key] = series_for(forecast_exp, key, "forecast")

    return {
        "dates": [d.strftime("%Y-%m") for d in all_dates],
        "series": series,
        "last_actual_date": last_hist_date.strftime("%Y-%m"),
    }


def build_banner(forecast: pd.DataFrame, forecast_exp: pd.DataFrame, current_year: int, next_year: int) -> dict:
    rows = []
    for key, label, color in PERSISTENCE_SCENARIOS:
        dp = scenario_dp_series(forecast, key)
        idx = build_index(dp)
        rows.append({
            "label": label, "color": color,
            "this_year": round(q4q4_growth(idx, current_year), 2),
            "next_year": round(q4q4_growth(idx, next_year), 2),
        })
    for key, label, color in EXPECTATIONS_SCENARIOS:
        dp = scenario_dp_series(forecast_exp, key)
        idx = build_index(dp)
        rows.append({
            "label": label, "color": color,
            "this_year": round(q4q4_growth(idx, current_year), 2),
            "next_year": round(q4q4_growth(idx, next_year), 2),
        })

    spf = latest_spf()
    if spf:
        rows.append({
            "label": f"SPF median, core CPI (survey {spf['survey']})", "color": REFERENCE_COLOR,
            "this_year": round(spf["this_year"], 2), "next_year": round(spf["next_year"], 2),
            "reference": True,
        })

    sep = latest_sep(current_year, next_year)
    if sep["this_year"] is not None or sep["next_year"] is not None:
        rows.append({
            "label": "SEP median, core PCE (not core CPI)", "color": REFERENCE_COLOR,
            "this_year": sep["this_year"], "next_year": sep["next_year"],
            "reference": True, "note": "core PCE, not core CPI -- not directly comparable to the rows above",
        })

    return {"current_year": current_year, "next_year": next_year, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()

    forecast = pd.read_csv(FORECAST_PATH)
    forecast_exp = pd.read_csv(FORECAST_EXP_PATH)

    today = date.today()
    current_year, next_year = today.year, today.year + 1

    data = {
        "as_of": today.isoformat(),
        "chart": build_chart_data(forecast, forecast_exp),
        "banner": build_banner(forecast, forecast_exp, current_year, next_year),
        "legend": {
            "persistence": [{"key": k, "label": l, "color": c} for k, l, c in PERSISTENCE_SCENARIOS],
            "expectations": [{"key": k, "label": l, "color": c} for k, l, c in EXPECTATIONS_SCENARIOS],
            "actual_color": ACTUAL_COLOR,
        },
    }

    template = TEMPLATE_PATH.read_text()
    html = template.replace("__DASHBOARD_DATA__", json.dumps(data))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html)
    print(f"Wrote {OUT_PATH}")
    print(f"\nBanner (this year {current_year} / next year {next_year}):")
    for r in data["banner"]["rows"]:
        print(f"  {r['label']:45s} {r['this_year']!s:>8s}  {r['next_year']!s:>8s}")


if __name__ == "__main__":
    main()
