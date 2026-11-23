#!/usr/bin/env python3
"""Does an item-level approach nest the DMS baseline, and does 'DMS + item adjustment' beat DMS? For the pre-release nowcast of CPI (headline, core vs published) and
PCE (headline, core vs revised and BEA first prints) it scores, over the last N months:
  DMS           the simplified Knotek-Zaman aggregate nowcast (lib_dms);
  BU mean12     bottom-up from items, every item forecast by its 12-month mean (DMS-like rule) + DMS gasoline nowcast for motor fuel;
  BU persist    bottom-up with the current item rule (3-month mean for persistent items, else 12-month mean);
  anchored      DMS + (BU persist - BU mean12): the item rule only supplies a correction relative to its own DMS-like baseline, so aggregation/reconstruction noise cancels.
Also reports how far BU mean12 is from DMS (the nesting gap).  bp of a monthly change.  Usage: python scripts/17_eval_anchored.py [--months 60]"""
import argparse

import numpy as np
import pandas as pd

from lib_common import DATA, connect
from lib_cpi import CPI, persist_nowcast
from lib_dms import DMSData, nowcast, pre_cpi_overrides
from lib_translate import STAGES, Inputs, aggregate, translate_month


def table(name, est, act_rev, act_fp, ev):
    half = ev[len(ev) // 2]
    rows = []
    for k, e in est.items():
        r = (e[ev] - act_rev[ev]) * 100
        row = dict(target=name, model=k, mae_rev=r.abs().mean(), h1=r[ev < half].abs().mean(), h2=r[ev >= half].abs().mean(), bias=r.mean())
        if act_fp is not None:
            f = (e[ev] - act_fp[ev]) * 100
            row.update(mae_fp=f.abs().mean(), fp_h1=f[ev < half].abs().mean(), fp_h2=f[ev >= half].abs().mean())
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=60)
    a = ap.parse_args()
    inp, D, C = Inputs(), DMSData(), CPI()
    fp = connect().execute('select series_id, month, mom from first_print').df().pivot(index='month', columns='series_id', values='mom')
    fp.index = pd.DatetimeIndex(fp.index)
    out = []
    # ---- CPI
    last = C.head.dropna().index.max()
    ev = pd.date_range(end=last, periods=a.months, freq='MS')
    dm = {m: nowcast(D, m) for m in pd.date_range(ev[0] - pd.DateOffset(months=1), last, freq='MS')}
    gas = {m: v['gas_sa'] for m, v in dm.items()}
    bu = {f: C.run(ev[0], last, forecast=persist_nowcast(gas, f)) for f in ['mean12', 'persist', 'persist_med3', 'persist_med5']}
    for tgt, col, pub, dkey in [('CPI core', 'core', C.core, 'cpi_core'), ('CPI headline', 'head', C.head, 'cpi_all')]:
        dms = pd.Series({m: dm[m][dkey] for m in ev})
        est = {'DMS': dms, 'BU mean12': bu['mean12'][col], 'BU persist': bu['persist'][col], 'BU persist_med3': bu['persist_med3'][col], 'BU persist_med5': bu['persist_med5'][col], 'anchored': dms + bu['persist'][col] - bu['mean12'][col]}
        ok = pub[ev].notna()
        out.append(table(tgt, est, pub, None, ev[ok.values]))
        gap = ((est['BU mean12'] - est['DMS'])[ev[ok.values]] * 100).abs().mean()
        print(f'{tgt}: |BU mean12 - DMS| mean gap {gap:.2f} bp')
    # ---- PCE
    ev = pd.date_range(end=inp.headline_mom.dropna().index.max(), periods=a.months, freq='MS')
    est = {k: {} for k in ['BU mean12', 'BU persist', 'BU persist_med3', 'BU persist_med5']}
    for m in ev:
        ov = pre_cpi_overrides(D, m)
        for k in est:
            r = aggregate(translate_month(inp, m, STAGES['pre_cpi'], ov, fill={'BU mean12': 'mean12', 'BU persist': 'persist', 'BU persist_med3': 'persist_med3', 'BU persist_med5': 'persist_med5'}[k]))
            est[k][m] = (r['core'], r['overall'])
    for tgt, i, dkey, act, fpc in [('PCE core', 0, 'pce_core_pre', inp.core_mom, 'PCEPILFE'), ('PCE headline', 1, 'pce_all_pre', inp.headline_mom, 'PCEPI')]:
        P = {k: pd.Series({m: v[i] for m, v in est[k].items()}) for k in est}
        b12, bp = P['BU mean12'], P['BU persist']
        dms = pd.Series({m: dm[m][dkey] if m in dm else nowcast(D, m)[dkey] for m in ev})
        e = {'DMS': dms, 'BU mean12': b12, 'BU persist': bp, 'BU persist_med3': P['BU persist_med3'], 'BU persist_med5': P['BU persist_med5'], 'anchored': dms + bp - b12}
        out.append(table(tgt, e, act, fp[fpc], ev))
        print(f'{tgt}: |BU mean12 - DMS| mean gap {((b12 - dms).abs().mean() * 100):.2f} bp')
    d = pd.concat(out)
    d.to_csv(DATA / 'eval_anchored.csv', index=False)
    print(f'\nlast {a.months} months, pre-release, MAE bp (rev = vs revised/published, fp = vs BEA first print; h1/h2 = halves)')
    print(d.round(2).to_string(index=False))


if __name__ == '__main__':
    main()
