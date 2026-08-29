#!/usr/bin/env python3
"""Pull the Philadelphia Fed Survey of Professional Forecasters' median
core CPI annual (Q4/Q4-style) inflation forecasts, for the dashboard
banner's SPF comparison row. Matches ../output_gap/rstar/scripts/ingest_spf.py's
pattern (same publisher, same file-per-survey-question convention) but a
different SPF file/variable -- that project uses the 10-year-ahead CPI10
(long-run expectations input to an r* model); this one uses the annual
current/next/next-next-year forecasts (CORECPIA/B/C).

CORECPIA/B/C are confirmed directly (2026-08-29) against Kiley (2023)'s
own cited SPF figures: the 2023:Q2 survey (this file's YEAR=2023,
QUARTER=2 row) gives CORECPIA=4.125, CORECPIB=2.662, CORECPIC=2.305 --
matching "core CPI inflation... expected to drop to 3 1/2 percent" is
the 2022 vintage's own figure elsewhere in that note, and this row's
values match Kiley's cited "4.1/2.7/2.3" for 2023/2024/2025 to within
rounding.

Usage: python3 07_ingest_spf.py
"""
import io
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SPF_URL = (
    "https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/"
    "survey-of-professional-forecasters/data-files/files/median_corecpi_level.xlsx"
)


def main():
    resp = requests.get(SPF_URL, timeout=30)
    resp.raise_for_status()
    df = pd.read_excel(io.BytesIO(resp.content))
    needed = {"YEAR", "QUARTER", "CORECPIA", "CORECPIB", "CORECPIC"}
    if not needed.issubset(df.columns):
        sys.exit(f"Unexpected SPF file columns: {df.columns.tolist()}")

    df = df.dropna(subset=["CORECPIA"])
    latest = df.iloc[-1]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"{date.today():%Y%m%d}_spf_corecpi.csv"
    df[["YEAR", "QUARTER", "CORECPIA", "CORECPIB", "CORECPIC"]].to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(df)} surveys, "
          f"{df['YEAR'].iloc[0]}Q{df['QUARTER'].iloc[0]}..{df['YEAR'].iloc[-1]}Q{df['QUARTER'].iloc[-1]})")
    print(f"Latest survey {int(latest['YEAR'])}Q{int(latest['QUARTER'])}: "
          f"this-year={latest['CORECPIA']:.2f} next-year={latest['CORECPIB']:.2f} "
          f"next-next-year={latest['CORECPIC']:.2f}")


if __name__ == "__main__":
    main()
