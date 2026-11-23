#!/usr/bin/env python3
"""Daily nowcast run: for the current PCE month (first month BEA has not published) and the next month, translate every leaf from whatever
data exist (deterministic switching by data availability: a leaf whose BLS source has the month is `released`; otherwise it is `forecast`
(gasoline) or `filled` (12-month average)), aggregate to headline and core PCE, store the leaf vector and aggregates under today's run date,
and print what changed since the previous stored run, split into: data releases (filled/forecast -> released), market/forecast updates
(forecast leaves), and revisions of already released leaves.
Also the item-level CPI nowcast for the first month BLS has not published (lib_cpi, same item rule as PCE).
Tables: nowcast_leaf (run_date, month, line, mom, share, status), nowcast_agg (run_date, month, overall, core, known_share_core), nowcast_cpi (run_date, month, headline, core, food, energy).
Run after the ingest stages (01a-01d). Skips if today's run is stored; --force overwrites.  Usage: python scripts/06_nowcast_daily.py [--force]"""
import argparse
from datetime import date

import pandas as pd

from lib_common import connect
from lib_cpi import CPI, persist_nowcast
from lib_dms import DMSData, nowcast, pre_cpi_overrides
from lib_translate import STAGES, Inputs, aggregate, translate_month

ALL = STAGES['post_import']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    run = f'{date.today():%Y-%m-%d}'
    con = connect()
    have = con.execute("select count(*) from information_schema.tables where table_name='nowcast_agg'").fetchone()[0]
    if have and not a.force and con.execute('select count(*) from nowcast_agg where run_date=?', [run]).fetchone()[0]:
        print(f'run {run} already stored (use --force)')
        return
    inp, D = Inputs(), DMSData()
    cur = inp.headline_mom.dropna().index.max() + pd.DateOffset(months=1)        # first PCE month BEA has not published
    leaf_rows, agg_rows = [], []
    for m in [cur, cur + pd.DateOffset(months=1)]:
        d = translate_month(inp, m, ALL, pre_cpi_overrides(D, m))
        agg = aggregate(d)
        leaf_rows.append(d.reset_index()[['line', 'mom', 'share', 'status']].assign(run_date=run, month=f'{m:%Y-%m}'))
        agg_rows.append(dict(run_date=run, month=f'{m:%Y-%m}', overall=agg['overall'], core=agg['core'], known_share_core=agg['known_share_core']))
        print(f'{m:%Y-%m}: headline {agg["overall"]:.3f}, core {agg["core"]:.3f}  (core spending from released data: {agg["known_share_core"]:.0f}%)')
    leaf, aggs = pd.concat(leaf_rows), pd.DataFrame(agg_rows)
    C = CPI()
    cm = C.head.dropna().index.max() + pd.DateOffset(months=1)                    # first CPI month BLS has not published
    start = pd.Timestamp(cm.year, 1, 1)
    gas = {m: nowcast(D, m)['gas_sa'] for m in pd.date_range(start, cm, freq='MS')}
    r = C.run(start, cm, forecast=persist_nowcast(gas)).loc[cm]                   # weights evolve through the year with actual changes
    cpi = pd.DataFrame([dict(run_date=run, month=f'{cm:%Y-%m}', headline=r['head'], core=r['core'], food=r['food'], energy=r['energy'])])
    print(f'{cm:%Y-%m}: CPI headline {r["head"]:.3f}, core {r["core"]:.3f}  (item-level, before BLS release)')
    prev = None
    if have:
        pr = con.execute('select max(run_date) from nowcast_agg where run_date<?', [run]).fetchone()[0]
        if pr:
            prev = (pr, con.execute('select * from nowcast_leaf where run_date=?', [pr]).df())
    for t, df in [('nowcast_leaf', leaf), ('nowcast_agg', aggs), ('nowcast_cpi', cpi)]:
        con.execute(f'CREATE TABLE IF NOT EXISTS {t} AS SELECT * FROM df LIMIT 0')
        con.execute(f'DELETE FROM {t} WHERE run_date=?', [run])
        con.execute(f'INSERT INTO {t} SELECT {", ".join(df.columns)} FROM df')
    if prev:
        pr, old = prev
        print(f'\nChange since run {pr} (contribution to the monthly % change, bp; core = core leaves only):')
        n = leaf.merge(old, on=['month', 'line'], suffixes=('', '_old')).join(inp.leaves[['group']], on='line')
        n['c_head'] = (n.share * n.mom - n.share_old * n.mom_old)               # share is % of PCE: share*mom is bp of monthly change
        kind = lambda r: 'data release' if r.status == 'released' and r.status_old != 'released' else (
            'revision' if r.status == 'released' else 'forecast/fill update')
        n['why'] = n.apply(kind, axis=1)
        print(n.groupby(['month', 'why']).c_head.sum().round(2).to_string())
    else:
        print('\nNo earlier run stored; changes will be shown from the next run.')


if __name__ == '__main__':
    main()
