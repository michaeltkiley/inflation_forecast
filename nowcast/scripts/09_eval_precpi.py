#!/usr/bin/env python3
"""Compare fill rules for leaves with no released source (the pre-CPI stage, gasoline overridden by the DMS gasoline nowcast) over the last N
months, as ONE global rule applied to every leaf (not tuned leaf by leaf). Reports mean absolute miss (bp of a monthly change) of core and headline PCE
vs BEA's first print and vs today's revised value, for the full period and each half (select on one half, check on the other).
Usage: python scripts/09_eval_precpi.py [--months 60]"""
import argparse

import pandas as pd

from lib_common import DATA, connect
from lib_dms import DMSData, pre_cpi_overrides
from lib_translate import FILLS, STAGES, Inputs, aggregate, translate_month


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=60)
    a = ap.parse_args()
    fp = connect().execute('select series_id, month, mom from first_print').df().pivot(index='month', columns='series_id', values='mom').dropna()
    fp.index = pd.DatetimeIndex(fp.index)
    inp, D = Inputs(), DMSData()
    months = fp.index[fp.index <= inp.headline_mom.dropna().index.max()][-a.months:]
    rows = []
    for m in months:
        ov = pre_cpi_overrides(D, m)
        for name in FILLS:
            r = aggregate(translate_month(inp, m, STAGES['pre_cpi'], ov, fill=name))
            rows.append(dict(month=m, fill=name, est_core=r['core'], est_all=r['overall'], fp_core=fp.at[m, 'PCEPILFE'], fp_all=fp.at[m, 'PCEPI'],
                             rev_core=inp.core_mom[m], rev_all=inp.headline_mom[m]))
    d = pd.DataFrame(rows)
    for k in ['core', 'all']:
        d[f'e_fp_{k}'] = (d[f'est_{k}'] - d[f'fp_{k}']).abs() * 100
        d[f'e_rev_{k}'] = (d[f'est_{k}'] - d[f'rev_{k}']).abs() * 100
    d.to_csv(DATA / 'eval_precpi.csv', index=False)
    half = months[len(months) // 2]
    d['half'] = (d.month >= half).map({False: '1st', True: '2nd'})
    t = d.groupby('fill', sort=False).agg(core_fp=('e_fp_core', 'mean'), core_rev=('e_rev_core', 'mean'), all_fp=('e_fp_all', 'mean'), all_rev=('e_rev_all', 'mean'))
    t['core_fp_1st'] = d[d.half == '1st'].groupby('fill').e_fp_core.mean()
    t['core_fp_2nd'] = d[d.half == '2nd'].groupby('fill').e_fp_core.mean()
    print(f'{months[0]:%Y-%m} to {months[-1]:%Y-%m}; mean abs miss, bp')
    print(t.round(2).to_string())


if __name__ == '__main__':
    main()
