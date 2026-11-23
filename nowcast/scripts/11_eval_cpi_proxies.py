#!/usr/bin/env python3
"""Out-of-sample test of CPI series as stand-ins for PPI-sourced PCE leaves between the CPI and PPI releases (post_cpi stage). For each (leaf, CPI proxy),
the leaf's monthly change (BEA published) is regressed on the proxy over the 5 years to t-1 (slope clipped to [0, 1.5], as lib_translate.regress_on) and
read off at the proxy's month-t value; scored against the 12-month-average fill over the last N months, overall and by half. A pair is adopted only if it
lowers RMSE in BOTH halves. Writes data/eval_cpi_proxies.csv.  Usage: python scripts/11_eval_cpi_proxies.py [--months 60]"""
import argparse

import numpy as np
import pandas as pd

from lib_common import DATA
from lib_translate import Inputs, mom, regress_on

PAIRS = [(184, 'CUSR0000SEMD01'), (184, 'CUSR0000SAM2'), (186, 'CUSR0000SEMD01'), (185, 'CUSR0000SEMD01'),
         (174, 'CUSR0000SEMC01'), (174, 'CUSR0000SAM2'), (189, 'CUSR0000SEMD02'), (188, 'CUSR0000SEMD02'),
         (177, 'CUSR0000SEMC04'), (177, 'CUSR0000SAM2'), (207, 'CUSR0000SETG01'), (279, 'CUSR0000SETE'),
         (299, 'CUSR0000SEGD01'), (276, 'CUSR0000SAM2'), (178, 'CUSR0000SAM2')]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=60)
    a = ap.parse_args()
    inp = Inputs()
    last = inp.headline_mom.dropna().index.max()
    months = pd.date_range(end=last, periods=a.months, freq='MS')
    half = months[len(months) // 2]
    tot = inp.total_nominal.dropna()
    rows = []
    for line, sid in PAIRS:
        x = mom(inp.levels[sid])
        y = inp.pub_mom[line]
        e_p, e_f = {}, {}
        for m in months:
            thr = m - pd.DateOffset(months=1)
            f = y.loc[:thr].dropna().iloc[-12:].mean()
            p = regress_on(y, x, m, thr, 1.5)
            if p is None or pd.isna(y.get(m)):
                continue
            e_p[m], e_f[m] = y[m] - p, y[m] - f
        e = pd.DataFrame({'proxy': e_p, 'fill': e_f})
        rm = lambda s: float(np.sqrt((s ** 2).mean()))
        h1, h2 = e[e.index < half], e[e.index >= half]
        rows.append(dict(line=line, leaf=inp.leaves.label[line][:34], proxy=sid[-6:], share_pct=inp.nominal.at[tot.index.max(), line] / tot.iloc[-1] * 100,
                         n=len(e), rmse_proxy=rm(e.proxy), rmse_fill=rm(e.fill), p1=rm(h1.proxy), f1=rm(h1.fill), p2=rm(h2.proxy), f2=rm(h2.fill)))
    d = pd.DataFrame(rows)
    d['adopt'] = (d.p1 < d.f1) & (d.p2 < d.f2)
    d.to_csv(DATA / 'eval_cpi_proxies.csv', index=False)
    print(f'{months[0]:%Y-%m} to {months[-1]:%Y-%m}; RMSE of the leaf forecast, % per month (p = proxy, f = fill; 1/2 = halves)')
    print(d.round(2).to_string(index=False))


if __name__ == '__main__':
    main()
