#!/usr/bin/env python3
"""Quasi-real-time error-correction of the pre-CPI PCE nowcast. For each of the last N months, the aggregate error of the pre-CPI translation (actual
revised core / headline minus estimate) is regressed, over the preceding 60 months (data through t-1 only), on one indicator known when nowcasting month t
(unemployment-rate changes - the jobs report precedes CPI -, broad dollar, 10y breakeven change, stock return) and the fitted adjustment is added to the
estimate. Also tested: a bias-only correction (intercept), and a blend toward the DMS baseline (idea: pull item-built aggregates toward DMS).
Each variant is scored against the unadjusted estimate against revised values and BEA first prints, overall and by half; adopt only if it lowers MAE in BOTH halves.
Many variants are tried, so a pass is weak evidence (multiple testing); read with the by-half columns.  Usage: python scripts/14_eval_macro_adjust.py [--months 60]"""
import argparse

import numpy as np
import pandas as pd

from lib_common import DATA, connect
from lib_dms import DMSData, nowcast, pre_cpi_overrides
from lib_translate import STAGES, Inputs, aggregate, mom, translate_month

WIN, START = 60, '2012-01-01'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=60)
    a = ap.parse_args()
    con = connect()
    inp, D = Inputs(), DMSData()
    mk = con.execute("select series_id, date, value from market_data where vintage=(select max(vintage) from market_data)").df()
    S = {k: g.set_index('date').value.sort_index() for k, g in mk.groupby('series_id')}
    mavg = lambda k: S[k].resample('MS').mean()
    u = S['UNRATE']
    Z = pd.DataFrame({'du': u.diff(), 'du3': u.diff(3), 'du12': u.diff(12), 'dollar': mom(mavg('DTWEXBGS')), 'dollar_l3': mom(mavg('DTWEXBGS')).rolling(3).mean().shift(1),
                      'breakeven': mavg('T10YIE').diff(), 'stocks': mom(mavg('NASDAQCOM')), 'stocks_avg3': mom(mavg('NASDAQCOM')).rolling(3).mean()})
    last = inp.headline_mom.dropna().index.max()
    months = pd.date_range(START, last, freq='MS')
    rows = {}
    for m in months:
        r = aggregate(translate_month(inp, m, STAGES['pre_cpi'], pre_cpi_overrides(D, m)))
        n = nowcast(D, m)
        rows[m] = dict(est_core=r['overall'] * 0 + r['core'], est_all=r['overall'], dms_core=n['pce_core_pre'], dms_all=n['pce_all_pre'], act_core=inp.core_mom[m], act_all=inp.headline_mom[m])
    E = pd.DataFrame(rows).T
    fp = con.execute('select series_id, month, mom from first_print').df().pivot(index='month', columns='series_id', values='mom')
    fp.index = pd.DatetimeIndex(fp.index)
    ev = E.index[-a.months:]
    half = ev[len(ev) // 2]
    out = []
    for tgt, est, dms, act, fpc in [('core', 'est_core', 'dms_core', 'act_core', 'PCEPILFE'), ('headline', 'est_all', 'dms_all', 'act_all', 'PCEPI')]:
        res = E[act] - E[est]
        variants = {'none': lambda m: 0.0, 'bias': lambda m: res.loc[:m - pd.DateOffset(months=1)].iloc[-WIN:].mean()}
        for zc in Z.columns:
            def f(m, zc=zc):
                d = pd.concat([res.rename('r'), Z[zc].rename('z')], axis=1).loc[:m - pd.DateOffset(months=1)].dropna().iloc[-WIN:]
                b = np.polyfit(d.z, d.r, 1)
                return b[1] + b[0] * Z[zc][m] if pd.notna(Z[zc].get(m)) else 0.0
            variants[zc] = f
        for lam in [0.25, 0.5]:
            variants[f'dms_blend_{lam}'] = lambda m, lam=lam: lam * (E.at[m, dms] - E.at[m, est])
        for name, f in variants.items():
            adj = pd.Series({m: f(m) for m in ev})
            e_rev = (E.loc[ev, est] + adj - E.loc[ev, act]) * 100
            e_fp = (E.loc[ev, est] + adj - fp.loc[ev, fpc]) * 100
            out.append(dict(target=tgt, variant=name, mae_rev=e_rev.abs().mean(), mae_fp=e_fp.abs().mean(), rev_h1=e_rev[ev < half].abs().mean(), rev_h2=e_rev[ev >= half].abs().mean(),
                            fp_h1=e_fp[ev < half].abs().mean(), fp_h2=e_fp[ev >= half].abs().mean()))
    d = pd.DataFrame(out)
    for t in ['core', 'headline']:
        b = d[(d.target == t) & (d.variant == 'none')].iloc[0]
        m = d.target == t
        d.loc[m, 'adopt'] = (d[m].rev_h1 < b.rev_h1) & (d[m].rev_h2 < b.rev_h2) & (d[m].fp_h1 < b.fp_h1) & (d[m].fp_h2 < b.fp_h2)
    d.to_csv(DATA / 'eval_macro_adjust.csv', index=False)
    print(f'{ev[0]:%Y-%m} to {ev[-1]:%Y-%m}, MAE bp of monthly change; rev = vs revised, fp = vs first print; h1/h2 = halves')
    print(d.round(2).to_string(index=False))


if __name__ == '__main__':
    main()
