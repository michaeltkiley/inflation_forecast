#!/usr/bin/env python3
"""Translate released BLS CPI/PPI/import prices into PCE component changes for one target month and aggregate to headline and
core PCE; store in DuckDB table `pce_translate` (month, stage, line, mom, share, status). Also prints BEA's published change for the
month when BEA has published it. Skips if (month, stage) is stored; --force recomputes.
Usage: python scripts/03_translate.py [--month YYYY-MM] [--stage post_cpi|post_ppi|post_import]   (default: newest CPI month, post_import)"""
import argparse

import pandas as pd

from lib_common import connect
from lib_dms import DMSData, pre_cpi_overrides
from lib_translate import STAGES, Inputs, aggregate, translate_month


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--month')
    ap.add_argument('--stage', default='post_import', choices=list(STAGES))
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    con = connect()
    inp = Inputs()
    month = pd.Timestamp(a.month + '-01') if a.month else inp.levels['CUSR0000SA0'].index.max()
    key = (f'{month:%Y-%m}', a.stage)
    if not a.force and con.execute("select count(*) from information_schema.tables where table_name='pce_translate'").fetchone()[0]:
        if con.execute('select count(*) from pce_translate where month=? and stage=?', list(key)).fetchone()[0]:
            print(f'{key} already stored (use --force)')
            return
    d = translate_month(inp, month, STAGES[a.stage], pre_cpi_overrides(DMSData(), month) if a.stage == 'pre_cpi' else None)
    out = d.reset_index()[['line', 'mom', 'share', 'status']].assign(month=key[0], stage=key[1])
    con.execute('CREATE TABLE IF NOT EXISTS pce_translate AS SELECT * FROM out LIMIT 0')
    con.execute('DELETE FROM pce_translate WHERE month=? AND stage=?', list(key))
    con.execute('INSERT INTO pce_translate SELECT line, mom, share, status, month, stage FROM out')
    agg = aggregate(d)
    if inp.x13_failed:
        print('X-13 could not adjust (used unadjusted):', ', '.join(sorted(set(inp.x13_failed))))
    print(f'{key[0]} {key[1]}: ' + ', '.join(f'{k} {v:.3f}' for k, v in agg.items()))
    if month in inp.headline_mom.index and pd.notna(inp.headline_mom[month]):
        print(f'BEA published {key[0]}: overall {inp.headline_mom[month]:.3f}, core {inp.core_mom[month]:.3f}')
    else:
        print('BEA has not published this month')


if __name__ == '__main__':
    main()
