#!/usr/bin/env python3
"""Theory-paired error correction of the pre-CPI PCE core nowcast by group. Core PCE is split into goods, services ex housing and housing (leaf flags). For each group,
the error of its pre-CPI contribution (published minus estimate, share-weighted) is regressed over the preceding 60 months (data through t-1) on an indicator that
should drive it - labor slack (unemployment-rate changes) for services, the broad dollar and 10y breakeven for goods, unemployment for housing - and the fitted adjustment is
added to that group's contribution. Scored on aggregate core vs revised and BEA first prints, overall and by half (adopt only if MAE falls in BOTH halves for both targets).
Also reports the persistence of each group's error. Usage: python scripts/16_eval_group_macro.py [--months 60]"""
import argparse

import numpy as np
import pandas as pd

from lib_common import DATA, connect
from lib_dms import DMSData, pre_cpi_overrides
from lib_translate import STAGES, Inputs, mom, translate_month

WIN, START = 60, '2012-01-01'
PAIRS = {'services': ['du', 'du3', 'du12'], 'goods': ['dollar', 'dollar_l3', 'breakeven'], 'housing': ['du', 'du12']}


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
                      'breakeven': mavg('T10YIE').diff()})
    last = inp.headline_mom.dropna().index.max()
    est, act = {}, {}
    for m in pd.date_range(START, last, freq='MS'):
        d = translate_month(inp, m, STAGES['pre_cpi'], pre_cpi_overrides(D, m))
        d = d[d.group == 'core']
        d['grp'] = np.where(d.housing == 1, 'housing', np.where(d.services == 1, 'services', 'goods'))
        d['act'] = [inp.pub_mom.at[m, l] if pd.notna(inp.pub_mom.at[m, l]) else d.mom[l] for l in d.index]
        tot = d.share.sum()
        est[m] = {g: (x.share * x.mom).sum() / tot for g, x in d.groupby('grp')}
        act[m] = {g: (x.share * x.act).sum() / tot for g, x in d.groupby('grp')}
    est, act = pd.DataFrame(est).T, pd.DataFrame(act).T
    res = act - est
    print('group error persistence (AR1) and sd, bp:', {g: (round(res[g].autocorr(1), 2), round(res[g].std() * 100, 1)) for g in res})
    fp = con.execute('select series_id, month, mom from first_print').df().pivot(index='month', columns='series_id', values='mom')
    fp.index = pd.DatetimeIndex(fp.index)
    ev = est.index[-a.months:]
    half = ev[len(ev) // 2]
    base = est.sum(axis=1)
    rows = []
    variants = [('none', None, None)] + [(f'{g}~{z}', g, z) for g, zs in PAIRS.items() for z in zs]
    for name, g, z in variants:
        adj = pd.Series(0.0, index=ev)
        if g:
            for m in ev:
                d = pd.concat([res[g].rename('r'), Z[z].rename('z')], axis=1).loc[:m - pd.DateOffset(months=1)].dropna().iloc[-WIN:]
                b = np.polyfit(d.z, d.r, 1)
                adj[m] = b[1] + b[0] * Z[z][m]
        e_rev, e_fp = (base[ev] + adj - inp.core_mom[ev]) * 100, (base[ev] + adj - fp.loc[ev, 'PCEPILFE']) * 100
        rows.append(dict(variant=name, mae_rev=e_rev.abs().mean(), mae_fp=e_fp.abs().mean(), rev_h1=e_rev[ev < half].abs().mean(), rev_h2=e_rev[ev >= half].abs().mean(),
                         fp_h1=e_fp[ev < half].abs().mean(), fp_h2=e_fp[ev >= half].abs().mean()))
    d = pd.DataFrame(rows)
    b = d.iloc[0]
    d['adopt'] = (d.rev_h1 < b.rev_h1) & (d.rev_h2 < b.rev_h2) & (d.fp_h1 < b.fp_h1) & (d.fp_h2 < b.fp_h2)
    d.to_csv(DATA / 'eval_group_macro.csv', index=False)
    print(f'{ev[0]:%Y-%m} to {ev[-1]:%Y-%m}, core PCE pre-CPI MAE bp')
    print(d.round(2).to_string(index=False))


if __name__ == '__main__':
    main()
