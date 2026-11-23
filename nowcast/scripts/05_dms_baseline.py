#!/usr/bin/env python3
"""Score the simplified DMS baseline (lib_dms) against published outcomes (latest vintage, not real time) over the last N BEA months, and
compare its PCE bridges with the bottom-up translation (data/translation_score.csv, from 04_score_translation.py). Prints live DMS nowcasts for
months not yet published. Mean absolute miss in basis points of a monthly % change. Writes data/dms_score.csv.
Information set: month-t weekly gasoline averages are fully known when nowcasting month t (the most favourable timing for DMS).
Usage: python scripts/05_dms_baseline.py [--months 36]"""
import argparse

import pandas as pd

from lib_common import DATA
from lib_dms import DMSData, nowcast


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=36)
    a = ap.parse_args()
    D = DMSData()
    last = D.pce_all.dropna().index.max()
    rows = []
    for m in pd.date_range(end=last, periods=a.months, freq='MS'):
        r = nowcast(D, m)
        rows.append(dict(month=m, **r, act_cpi_all=D.cpi_all.get(m), act_cpi_core=D.cpi_core.get(m), act_pce_all=D.pce_all[m], act_pce_core=D.pce_core[m]))
    d = pd.DataFrame(rows).set_index('month')
    d.to_csv(DATA / 'dms_score.csv')
    bp = lambda p, q: ((d[p] - d[q]).abs().mean() * 100)
    print(f'{d.index[0]:%Y-%m} to {d.index[-1]:%Y-%m}  ({d.act_cpi_all.notna().sum()} months with CPI)')
    print(f'DMS pre-CPI  MAE bp:  CPI core {bp("cpi_core", "act_cpi_core"):.1f}  CPI all {bp("cpi_all", "act_cpi_all"):.1f}  '
          f'PCE core {bp("pce_core_pre", "act_pce_core"):.1f}  PCE all {bp("pce_all_pre", "act_pce_all"):.1f}')
    print(f'DMS post-CPI MAE bp:  PCE core {bp("pce_core_post", "act_pce_core"):.1f}  PCE all {bp("pce_all_post", "act_pce_all"):.1f}')
    t = pd.read_csv(DATA / 'translation_score.csv', parse_dates=['month'])
    t = t[t.month.isin(d.index)]
    print('Bottom-up translation (same months) MAE bp:  ' + '  '.join(
        f'{s}: core {(x.core - x.bea_core).abs().mean() * 100:.1f} all {(x.overall - x.bea_overall).abs().mean() * 100:.1f}' for s, x in t.groupby('stage', sort=False)))
    print('\nLive DMS nowcasts (monthly % change):')
    for m in pd.date_range(last + pd.DateOffset(months=1), D.retail_gas.dropna().index.max(), freq='MS').union([last + pd.DateOffset(months=1)]):
        r = nowcast(D, m)
        print(f'  {m:%Y-%m}: ' + ', '.join(f'{k} {v:.3f}' for k, v in r.items() if pd.notna(v)))


if __name__ == '__main__':
    main()
