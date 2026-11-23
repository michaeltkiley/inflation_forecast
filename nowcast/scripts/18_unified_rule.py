#!/usr/bin/env python3
"""Choose ONE item-level fill rule for all items, CPI and PCE alike. Every rule in lib_translate.FILLS (candidates below) is applied through the same function to the
items of both systems and scored on the four pre-release targets (CPI headline, CPI core vs published; PCE headline, PCE core vs revised) over the last N months.
Selection criterion, fixed in advance: for each target the mean of the first-half and second-half MAE, then the mean over the four targets; lowest wins, ties within
1% go to the simpler rule (order of CANDIDATES). First-print MAE for PCE is reported but not used in the criterion.  Writes data/unified_rule.csv.
Usage: python scripts/18_unified_rule.py [--months 60]"""
import argparse

import pandas as pd

from lib_common import DATA, connect
from lib_cpi import CPI, persist_nowcast
from lib_dms import DMSData, nowcast, pre_cpi_overrides
from lib_translate import STAGES, Inputs, aggregate, translate_month

CANDIDATES = ['mean12', 'mean6', 'mean3', 'ewm6', 'blend', 'persist', 'persist.3', 'persist.7', 'persist_med3', 'persist_med5']      # simplest first


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=60)
    a = ap.parse_args()
    inp, D, C = Inputs(), DMSData(), CPI()
    fp = connect().execute('select series_id, month, mom from first_print').df().pivot(index='month', columns='series_id', values='mom')
    fp.index = pd.DatetimeIndex(fp.index)
    cl = C.head.dropna().index.max()
    cev = pd.date_range(end=cl, periods=a.months, freq='MS')
    pev = pd.date_range(end=inp.headline_mom.dropna().index.max(), periods=a.months, freq='MS')
    gas = {m: nowcast(D, m)['gas_sa'] for m in pd.date_range(cev[0] - pd.DateOffset(months=1), cl, freq='MS')}
    ov = {m: pre_cpi_overrides(D, m) for m in pev}
    rows = []
    for rule in CANDIDATES:
        cpi = C.run(cev[0], cl, forecast=persist_nowcast(gas, rule))
        pce = pd.DataFrame({m: dict(zip(['core', 'overall'], (lambda r: (r['core'], r['overall']))(aggregate(translate_month(inp, m, STAGES['pre_cpi'], ov[m], fill=rule))))) for m in pev}).T
        for tgt, est, act, ev, f in [('CPI core', cpi['core'], C.core, cev, None), ('CPI headline', cpi['head'], C.head, cev, None),
                                     ('PCE core', pce['core'], inp.core_mom, pev, 'PCEPILFE'), ('PCE headline', pce['overall'], inp.headline_mom, pev, 'PCEPI')]:
            ok = act[ev].notna().values
            e = ((est[ev] - act[ev]) * 100)[ok]
            h = ev[len(ev) // 2]
            rows.append(dict(rule=rule, target=tgt, mae=e.abs().mean(), h1=e[e.index < h].abs().mean(), h2=e[e.index >= h].abs().mean(),
                             fp=((est[ev] - fp.loc[ev, f]) * 100).abs().mean() if f else float('nan')))
        print(f'done {rule}', flush=True)
    d = pd.DataFrame(rows)
    d['half_avg'] = (d.h1 + d.h2) / 2
    d.to_csv(DATA / 'unified_rule.csv', index=False)
    wide = d.pivot(index='rule', columns='target', values='half_avg').loc[CANDIDATES]
    wide['score'] = wide.mean(axis=1)
    best = wide.score.min()
    winner = next(r for r in CANDIDATES if wide.score[r] <= best * 1.01)
    print('\nmean of first/second-half MAE (bp) by target, and criterion score:')
    print(wide.round(2).to_string())
    print(f'\nselected (lowest score; ties within 1% to the simpler rule): {winner}')
    print('\nby half (h1/h2) for the selected rule and mean12:')
    print(d[d.rule.isin([winner, 'mean12'])][['rule', 'target', 'h1', 'h2', 'mae', 'fp']].round(2).to_string(index=False))


if __name__ == '__main__':
    main()
