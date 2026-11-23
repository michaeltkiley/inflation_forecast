#!/usr/bin/env python3
"""Do stock prices help forecast the financial-services PCE leaf 'Portfolio management and investment advice' (line 268; BEA: out months 'informed by
market indicators')? For each stock index (SP500, NASDAQCOM) and timing (x_t, x_{t-1}, mean of last 2/3/6 months of monthly-average % changes), a rolling OLS
of the leaf's monthly change on the indicator (window WIN months, data through t-1 only; the month-t indicator is observed when nowcasting t), scored against
the default `persist` fill over the last N months, overall and by half. Adopt only if RMSE falls in BOTH halves.  Usage: python scripts/13_eval_stock_financial.py"""
import argparse

import numpy as np
import pandas as pd

from lib_common import DATA, connect
from lib_translate import FILLS, Inputs, mom

LINE = 268


def timing(x, kind):
    return {'x_t': x, 'x_t-1': x.shift(1), 'avg2': x.rolling(2).mean(), 'avg3': x.rolling(3).mean(), 'avg6': x.rolling(6).mean()}[kind]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=60)
    ap.add_argument('--win', type=int, default=60)
    a = ap.parse_args()
    inp = Inputs()
    mk = connect().execute("select series_id, date, value from market_data where vintage=(select max(vintage) from market_data)").df()
    M = {k: mom(g.set_index('date').value.resample('MS').mean()) for k, g in mk.groupby('series_id')}
    y = inp.pub_mom[LINE]
    last = inp.headline_mom.dropna().index.max()
    months = pd.date_range(end=last, periods=a.months, freq='MS')
    half = months[len(months) // 2]
    rm = lambda s: float(np.sqrt((s ** 2).mean()))
    base = pd.Series({m: y[m] - FILLS['persist'](y.loc[:m - pd.DateOffset(months=1)].dropna()) for m in months})
    print(f'leaf {LINE}: sd {y.loc[months[0]:].std():.2f}%/month, share {inp.nominal.at[inp.total_nominal.dropna().index.max(), LINE] / inp.total_nominal.dropna().iloc[-1] * 100:.2f}% of PCE')
    print(f'baseline (persist fill) RMSE {rm(base):.3f}  1st half {rm(base[months < half]):.3f}  2nd half {rm(base[months >= half]):.3f}\n')
    rows = []
    for sid in ['SP500', 'NASDAQCOM']:
        for kind in ['x_t', 'x_t-1', 'avg2', 'avg3', 'avg6']:
            x = timing(M[sid], kind)
            e = {}
            for m in months:
                thr = m - pd.DateOffset(months=1)
                d = pd.concat([y.rename('y'), x.rename('x')], axis=1).loc[:thr].dropna().iloc[-a.win:]
                if len(d) < 36 or pd.isna(x.get(m)):
                    continue
                b = np.polyfit(d.x, d.y, 1)
                e[m] = y[m] - (b[1] + b[0] * x[m])
            e = pd.Series(e)
            bb = base[e.index]
            rows.append(dict(index=sid, timing=kind, n=len(e), slope_last=b[0], rmse=rm(e), base=rm(bb), h1=rm(e[e.index < half]), base1=rm(bb[bb.index < half]),
                             h2=rm(e[e.index >= half]), base2=rm(bb[bb.index >= half])))
    d = pd.DataFrame(rows)
    d['adopt'] = (d.h1 < d.base1) & (d.h2 < d.base2)
    d.to_csv(DATA / 'eval_stock_financial.csv', index=False)
    print(d.round(3).to_string(index=False))


if __name__ == '__main__':
    main()
