#!/usr/bin/env python3
"""Ingest BEA's monthly PCE detail from the NIPA bulk files into DuckDB table `bea_pce`.

Tables: U20404 (2.4.4U price indexes, ~210 lines), U20405 (2.4.5U nominal expenditures), U20406 (2.4.6U real, chained $),
T20804 (2.8.4 price indexes by major type). Each pull is a vintage (today's date); the bulk files carry only the latest
data, so vintages accumulate from the first run onward. Skips if today's vintage exists; --force re-pulls.
Usage: python scripts/01a_ingest_bea.py [--force]
"""
import argparse
import csv
import io
from datetime import date

import pandas as pd

from lib_common import connect, fetch, user_agent, vintage_done, drop_other_vintages

BASE = 'https://apps.bea.gov/national/Release/TXT/'
TABLES = ['U20404', 'U20405', 'U20406', 'T20804']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    vintage = f'{date.today():%Y-%m-%d}'
    con = connect()
    if vintage_done(con, 'bea_pce', vintage) and not a.force:
        print(f'bea_pce vintage {vintage} already ingested (use --force)')
        return
    ua = user_agent()
    reg = fetch(BASE + 'SeriesRegister.txt', 'bea_SeriesRegister.txt', ua, a.force)
    mon = fetch(BASE + 'NipaDataM.txt', 'bea_NipaDataM.txt', ua, a.force)

    # register: series code, label, metric, ..., 'TableId:LineNo|...'
    lines = []                                    # (table, line, code, description)
    for r in csv.reader(io.StringIO(reg.read_text('utf8', 'replace'))):
        if len(r) >= 6 and not r[0].startswith('%'):
            for tl in r[5].split('|'):
                t, _, ln = tl.partition(':')
                if t in TABLES:
                    lines.append((t, int(ln), r[0], r[1]))
    reg_df = pd.DataFrame(lines, columns=['table_id', 'line', 'series_code', 'description'])
    codes = set(reg_df.series_code)

    recs = []
    for r in csv.reader(io.StringIO(mon.read_text('utf8', 'replace'))):
        if len(r) == 3 and r[0] in codes and 'M' in r[1]:
            try:
                recs.append((r[0], pd.Period(r[1].replace('M', '-'), 'M').to_timestamp(), float(r[2].replace(',', ''))))
            except ValueError:
                pass
    data = pd.DataFrame(recs, columns=['series_code', 'date', 'value'])
    out = reg_df.merge(data, on='series_code')
    out['vintage'] = vintage
    con.execute('CREATE TABLE IF NOT EXISTS bea_pce AS SELECT * FROM out LIMIT 0')
    con.execute('DELETE FROM bea_pce WHERE vintage=?', [vintage])
    con.execute('INSERT INTO bea_pce SELECT table_id, line, series_code, description, date, value, vintage FROM out')
    drop_other_vintages(con, 'bea_pce', vintage)
    print(out.groupby('table_id').agg(lines=('line', 'nunique'), first=('date', 'min'), last=('date', 'max')).to_string())


if __name__ == '__main__':
    main()
