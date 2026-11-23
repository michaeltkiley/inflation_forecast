#!/usr/bin/env python3
"""Ingest BEA's FIRST-PUBLISHED monthly change in headline (PCEPI) and core (PCEPILFE) PCE price indexes from ALFRED into DuckDB table
`first_print` (series_id, month, released_on, mom). For each month, the change is computed from the vintage of the day the month first came out
(both levels from that vintage, so a same-day revision of the prior month counts, as in BEA's release). Months already stored are skipped;
--force refetches. Needs FRED_API_KEY.  Usage: python scripts/07_ingest_first_prints.py [--start 2018-01]"""
import argparse
import os
import time

import pandas as pd
import requests

from lib_common import connect, load_env

URL = 'https://api.stlouisfed.org/fred/series/observations'
SERIES = ['PCEPI', 'PCEPILFE']


def obs(sid, **kw):
    time.sleep(0.6)                                     # FRED allows 120 requests a minute
    r = requests.get(URL, params=dict(series_id=sid, api_key=os.environ['FRED_API_KEY'], file_type='json', **kw), timeout=60)
    if r.status_code != 200:                            # never print r.url: it contains the API key
        raise SystemExit(f'ALFRED request failed for {sid}: HTTP {r.status_code}')
    return r.json()['observations']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', default='2018-01')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    load_env()
    if not os.environ.get('FRED_API_KEY'):
        raise SystemExit('FRED_API_KEY is not set in .env')
    con = connect()
    con.execute('CREATE TABLE IF NOT EXISTS first_print (series_id VARCHAR, month DATE, released_on DATE, mom DOUBLE)')
    for sid in SERIES:
        rows = []
        first = obs(sid, observation_start=f'{a.start}-01', output_type=4, realtime_start='1776-07-04', realtime_end='9999-12-31')
        done = set() if a.force else {r[0] for r in con.execute('select month from first_print where series_id=?', [sid]).fetchall()}
        for o in first:
            m = pd.Timestamp(o['date'])
            if o['value'] in ('.', '') or m.date() in done:
                continue
            v = obs(sid, observation_start=str((m - pd.DateOffset(months=1)).date()), observation_end=str(m.date()),
                    realtime_start=o['realtime_start'], realtime_end=o['realtime_start'])
            lv = {pd.Timestamp(x['date']): float(x['value']) for x in v if x['value'] not in ('.', '')}
            if m in lv and (m - pd.DateOffset(months=1)) in lv:
                rows.append((sid, m.date(), pd.Timestamp(o['realtime_start']).date(), (lv[m] / lv[m - pd.DateOffset(months=1)] - 1) * 100))
        if rows:
            df = pd.DataFrame(rows, columns=['series_id', 'month', 'released_on', 'mom'])
            con.execute('DELETE FROM first_print WHERE series_id=? AND month IN (SELECT month FROM df)', [sid])
            con.execute('INSERT INTO first_print SELECT * FROM df')
    print(con.execute('select series_id, count(*) n, min(month) first_month, max(month) last_month from first_print group by 1').df().to_string(index=False))


if __name__ == '__main__':
    main()
