#!/usr/bin/env python3
"""Out-of-sample test of fuel/energy indicators for pre-CPI leaf forecasts. For each candidate (PCE leaf, market series) a 60-month rolling OLS of
the leaf's monthly change (BEA published, SA) on the contemporaneous monthly-average % change of the market series (month t is observed while
nowcasting t), estimated with data through t-1 only; the forecast is scored against the 12-month-average fill over the last N months, overall and by
half. A candidate is adopted only if it lowers RMSE in BOTH halves. Writes data/eval_indicators.csv.  Usage: python scripts/10_eval_indicators.py [--months 60]"""
import argparse

import numpy as np
import pandas as pd

from lib_common import DATA, connect
from lib_translate import Inputs, mom

WIN = 60
CANDIDATES = [(207, 'DJFUELUSGULF', 'air transportation ~ jet fuel'), (171, 'DHHNGSP', 'natural gas utility ~ Henry Hub'),
              (170, 'DHHNGSP', 'electricity ~ Henry Hub'), (118, 'DCOILWTICO', 'fuel oil ~ WTI'), (119, 'DCOILWTICO', 'other fuels ~ WTI')]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=60)
    a = ap.parse_args()
    inp = Inputs()
    mk = connect().execute("select series_id, date, value from market_data where vintage=(select max(vintage) from market_data)").df()
    X = {k: mom(g.set_index('date').value.resample('MS').mean()) for k, g in mk.groupby('series_id')}
    last = inp.headline_mom.dropna().index.max()
    months = pd.date_range(end=last, periods=a.months, freq='MS')
    half = months[len(months) // 2]
    rows = []
    for line, sid, label in CANDIDATES:
        y, x = inp.pub_mom[line], X[sid]
        e_ind, e_fill = [], []
        for m in months:
            thr = m - pd.DateOffset(months=1)
            d = pd.concat([y.rename('y'), x.rename('x')], axis=1).loc[:thr].dropna().iloc[-WIN:]
            b = np.polyfit(d.x, d.y, 1)
            e_ind.append(y[m] - (b[1] + b[0] * x[m]))
            e_fill.append(y[m] - y.loc[:thr].dropna().iloc[-12:].mean())
        e = pd.DataFrame({'ind': e_ind, 'fill': e_fill}, index=months)
        rm = lambda s: float(np.sqrt((s ** 2).mean()))
        share = inp.nominal.at[inp.total_nominal.dropna().index.max(), line] / inp.total_nominal.dropna().iloc[-1] * 100
        rows.append(dict(line=line, test=label, share_pct=share, rmse_ind=rm(e.ind), rmse_fill=rm(e.fill),
                         ind_1st=rm(e.ind[months < half]), fill_1st=rm(e.fill[months < half]), ind_2nd=rm(e.ind[months >= half]), fill_2nd=rm(e.fill[months >= half])))
    d = pd.DataFrame(rows)
    d['adopt'] = (d.ind_1st < d.fill_1st) & (d.ind_2nd < d.fill_2nd)
    d.to_csv(DATA / 'eval_indicators.csv', index=False)
    print(f'{months[0]:%Y-%m} to {months[-1]:%Y-%m}; RMSE of the leaf forecast, % per month')
    print(d.round(2).to_string(index=False))


if __name__ == '__main__':
    main()
