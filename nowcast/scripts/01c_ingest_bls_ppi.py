#!/usr/bin/env python3
"""Ingest the PPI (pc.* industry, wp.* commodity) and import-price (ei.*) series named in config/pce_leaf_map.csv into
DuckDB table `ppi_data` (series_id, date, value, vintage). The map decides which series are kept, so the large flat files
are streamed and filtered rather than stored. Files: pc.data.{8,36,47,50,51,57,58,63,67,71}, wp.data.{4,30}, ei.data.10.
Requires BLS_CONTACT. Skips if today's vintage exists; --force re-pulls.  Usage: python scripts/01c_ingest_bls_ppi.py [--force]
"""
import argparse
import re
from datetime import date

import pandas as pd
import requests

from lib_common import ROOT, connect, fetch, user_agent, vintage_done, drop_other_vintages

BASES = {'pc': 'https://download.bls.gov/pub/time.series/pc/', 'wp': 'https://download.bls.gov/pub/time.series/wp/',
         'ei': 'https://download.bls.gov/pub/time.series/ei/'}
FILES = {'pc': {8, 36, 47, 50, 51, 57, 58, 63, 67, 71}, 'wp': {4, 30}, 'ei': {10}}


def wanted_series():
    m = pd.read_csv(ROOT / 'config' / 'pce_leaf_map.csv', dtype=str)
    ids = {p.split(':')[0].strip() for s in m.series.dropna() for p in s.split(';')}
    return {i for i in ids if not i.startswith('CU')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    vintage = f'{date.today():%Y-%m-%d}'
    con = connect()
    if vintage_done(con, 'ppi_data', vintage) and not a.force:
        print(f'ppi_data vintage {vintage} already ingested (use --force)')
        return
    ua = user_agent(contact_required=True)
    want = wanted_series()
    parts = []
    for pre, nums in FILES.items():
        listing = requests.get(BASES[pre], headers={'User-Agent': ua}, timeout=60)
        listing.raise_for_status()
        names = sorted({f'{pre}.data.{n}.{nm}' for n, nm in re.findall(rf'{pre}\.data\.(\d+)\.(\w+)', listing.text)
                        if int(n) in nums})
        missing = nums - {int(n.split('.')[2]) for n in names}
        if missing:
            raise SystemExit(f'{pre}: data files {sorted(missing)} not in the directory listing')
        for f in names:
            p = fetch(BASES[pre] + f, f'bls_{f}', ua, a.force)
            d = pd.read_csv(p, sep='\t', dtype=str, skipinitialspace=True)
            d.columns = [c.strip() for c in d.columns]
            d['series_id'] = d.series_id.str.strip()
            d = d[d.series_id.isin(want) & d.period.str.strip().str.match(r'M(0[1-9]|1[0-2])$')]
            d = d.assign(date=pd.to_datetime(d.year.str.strip() + '-' + d.period.str.strip().str[1:] + '-01'),
                         value=pd.to_numeric(d.value.str.strip(), errors='coerce')).dropna(subset=['value'])
            parts.append(d[['series_id', 'date', 'value']])
    data = pd.concat(parts).drop_duplicates(['series_id', 'date'])
    data['vintage'] = vintage
    con.execute('CREATE TABLE IF NOT EXISTS ppi_data AS SELECT * FROM data LIMIT 0')
    con.execute('DELETE FROM ppi_data WHERE vintage=?', [vintage])
    con.execute('INSERT INTO ppi_data SELECT series_id, date, value, vintage FROM data')
    drop_other_vintages(con, 'ppi_data', vintage)
    missing = sorted(want - set(data.series_id))
    print(f'{data.series_id.nunique()} of {len(want)} series, {data.date.min():%Y-%m} to {data.date.max():%Y-%m}')
    if missing:
        print('NOT FOUND:', missing)


if __name__ == '__main__':
    main()
