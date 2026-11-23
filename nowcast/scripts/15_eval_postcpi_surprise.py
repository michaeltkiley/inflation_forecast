#!/usr/bin/env python3
"""Post-CPI error correction: once month t's CPI is out, does the CPI surprise (actual CPI core / headline minus the DMS pre-release nowcast, or the
actual change itself) help predict the error of the post-CPI PCE translation (which still fills the PPI-sourced and imputed leaves, ~36% of core)?
Rolling 60-month OLS of the post-CPI aggregate error (revised actual minus estimate) on the indicator, data through t-1; scored against the unadjusted
estimate vs revised and first prints, overall and by half; adopt only if MAE falls in BOTH halves for both targets of comparison.
Usage: python scripts/15_eval_postcpi_surprise.py [--months 60]"""
import argparse

import numpy as np
import pandas as pd

from lib_common import DATA, connect
from lib_dms import DMSData, nowcast
from lib_translate import STAGES, Inputs, aggregate, translate_month

WIN, START = 60, '2016-01-01'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=60)
    a = ap.parse_args()
    inp, D = Inputs(), DMSData()
    last = inp.headline_mom.dropna().index.max()
    rows = {}
    for m in pd.date_range(START, last, freq='MS'):
        if pd.isna(D.cpi_core.get(m)):
            continue
        r = aggregate(translate_month(inp, m, STAGES['post_cpi']))
        n = nowcast(D, m)
        rows[m] = dict(est_core=r['core'], est_all=r['overall'], act_core=inp.core_mom[m], act_all=inp.headline_mom[m],
                       s_core=D.cpi_core[m] - n['cpi_core'], s_all=D.cpi_all[m] - n['cpi_all'], cpi_core=D.cpi_core[m], cpi_all=D.cpi_all[m])
    E = pd.DataFrame(rows).T
    fp = connect().execute('select series_id, month, mom from first_print').df().pivot(index='month', columns='series_id', values='mom')
    fp.index = pd.DatetimeIndex(fp.index)
    ev = E.index[-a.months:]
    half = ev[len(ev) // 2]
    out = []
    for tgt, est, act, fpc, zs in [('core', 'est_core', 'act_core', 'PCEPILFE', ['s_core', 'cpi_core']), ('headline', 'est_all', 'act_all', 'PCEPI', ['s_all', 's_core', 'cpi_all'])]:
        res = E[act] - E[est]
        variants = {'none': lambda m: 0.0}
        for zc in zs:
            def f(m, zc=zc):
                d = pd.concat([res.rename('r'), E[zc].rename('z')], axis=1).loc[:m - pd.DateOffset(months=1)].dropna().iloc[-WIN:]
                b = np.polyfit(d.z, d.r, 1)
                return b[1] + b[0] * E.at[m, zc]
            variants[zc] = f
        for name, f in variants.items():
            adj = pd.Series({m: f(m) for m in ev})
            e_rev, e_fp = (E.loc[ev, est] + adj - E.loc[ev, act]) * 100, (E.loc[ev, est] + adj - fp.loc[ev, fpc]) * 100
            out.append(dict(target=tgt, variant=name, mae_rev=e_rev.abs().mean(), mae_fp=e_fp.abs().mean(), rev_h1=e_rev[ev < half].abs().mean(), rev_h2=e_rev[ev >= half].abs().mean(),
                            fp_h1=e_fp[ev < half].abs().mean(), fp_h2=e_fp[ev >= half].abs().mean()))
    d = pd.DataFrame(out)
    for t in ['core', 'headline']:
        b = d[(d.target == t) & (d.variant == 'none')].iloc[0]
        m = d.target == t
        d.loc[m, 'adopt'] = (d[m].rev_h1 < b.rev_h1) & (d[m].rev_h2 < b.rev_h2) & (d[m].fp_h1 < b.fp_h1) & (d[m].fp_h2 < b.fp_h2)
    d.to_csv(DATA / 'eval_postcpi_surprise.csv', index=False)
    print(f'{ev[0]:%Y-%m} to {ev[-1]:%Y-%m}, post-CPI stage, MAE bp; rev = vs revised, fp = vs first print')
    print(d.round(2).to_string(index=False))


if __name__ == '__main__':
    main()
