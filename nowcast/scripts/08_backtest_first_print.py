#!/usr/bin/env python3
"""Partly real-time backtest: score each stage of the bottom-up translation, and the DMS baseline, against BEA's FIRST-PUBLISHED monthly
headline (PCEPI) and core (PCEPILFE) change (table `first_print`, from 07_ingest_first_prints.py), and against today's revised values.
Targets are real-time; INPUTS are not: leaf-level BEA history and spending shares are today's vintage (BEA's detailed tables are not in ALFRED) and
X-13 seasonal factors use the full sample. Reports mean absolute miss and mean signed miss (bias) in basis points of a monthly change, plus a
bias-adjusted MAE (bias estimated in the same sample, so a diagnostic only, not out-of-sample). Writes results/backtest_first_print.csv (committed; read by the dashboard).
PAPER_* = econvitals' reported mean core miss vs BEA first print (README; 2017-2026; its own method; not independently verified).
Usage: python scripts/08_backtest_first_print.py [--months 60]"""
import argparse

import pandas as pd

from lib_common import RESULTS, connect
from lib_dms import DMSData, nowcast, pre_cpi_overrides
from lib_translate import STAGES, Inputs, aggregate, translate_month

PAPER_CORE_FIRST_PRINT_BP = {'post_cpi': 5.9, 'post_ppi': 4.7, 'post_import': 4.8}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=60)
    a = ap.parse_args()
    fp = connect().execute("select series_id, month, mom from first_print").df()
    fp = fp.pivot(index='month', columns='series_id', values='mom').dropna()
    fp.index = pd.DatetimeIndex(fp.index)
    inp, D = Inputs(), DMSData()
    months = fp.index[fp.index <= inp.headline_mom.dropna().index.max()][-a.months:]
    rows = []
    for m in months:
        base = dict(month=m, fp_all=fp.at[m, 'PCEPI'], fp_core=fp.at[m, 'PCEPILFE'], rev_all=inp.headline_mom[m], rev_core=inp.core_mom[m])
        for stage, rel in STAGES.items():
            r = aggregate(translate_month(inp, m, rel, pre_cpi_overrides(D, m) if stage == 'pre_cpi' else None))
            rows.append(dict(base, model=stage, est_all=r['overall'], est_core=r['core']))
        r = nowcast(D, m)
        rows.append(dict(base, model='dms_pre_cpi', est_all=r['pce_all_pre'], est_core=r['pce_core_pre']))
        if pd.notna(r['pce_all_post']):
            rows.append(dict(base, model='dms_post_cpi', est_all=r['pce_all_post'], est_core=r['pce_core_post']))
    d = pd.DataFrame(rows)
    for k in ['all', 'core']:
        d[f'miss_fp_{k}'] = (d[f'est_{k}'] - d[f'fp_{k}']) * 100
        d[f'miss_rev_{k}'] = (d[f'est_{k}'] - d[f'rev_{k}']) * 100
    RESULTS.mkdir(exist_ok=True)
    d.to_csv(RESULTS / 'backtest_first_print.csv', index=False)
    g = d.groupby('model', sort=False)
    out = pd.DataFrame({'n': g.size(), 'core_MAE_fp': g.miss_fp_core.apply(lambda x: x.abs().mean()), 'core_bias_fp': g.miss_fp_core.mean(),
                        'core_MAE_fp_debiased': g.miss_fp_core.apply(lambda x: (x - x.mean()).abs().mean()),
                        'core_MAE_revised': g.miss_rev_core.apply(lambda x: x.abs().mean()),
                        'all_MAE_fp': g.miss_fp_all.apply(lambda x: x.abs().mean()), 'all_bias_fp': g.miss_fp_all.mean(),
                        'PAPER_core_MAE_fp': pd.Series(PAPER_CORE_FIRST_PRINT_BP)})
    print(f'{months[0]:%Y-%m} to {months[-1]:%Y-%m} ({len(months)} months), bp of a monthly change')
    print(out.round(2).to_string())
    gap = (fp.loc[months, 'PCEPILFE'] - inp.core_mom[months]).abs().mean() * 100
    print(f'\nFirst print vs today\'s revised core: mean abs gap {gap:.1f} bp (the part of the miss no model can reduce)')
    if inp.x13_failed:
        print('X-13 could not adjust (used unadjusted):', ', '.join(sorted(set(inp.x13_failed))))


if __name__ == '__main__':
    main()
