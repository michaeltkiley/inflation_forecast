#!/usr/bin/env python3
"""Ingest daily/weekly market series from FRED's public CSV endpoint (no key; latest vintage only) into DuckDB table `market_data`
(series_id, date, value, vintage): GASREGW (weekly US regular gasoline retail price, EIA), DCOILWTICO (daily WTI), DCOILBRENTEU (daily Brent), DHHNGSP (daily Henry Hub natural gas), DJFUELUSGULF (daily Gulf Coast jet fuel), SP500 and NASDAQCOM (daily), DTWEXBGS (daily broad dollar), T10YIE (daily 10y breakeven), UNRATE (monthly).
Skips if today's vintage exists; --force re-pulls.  Usage: python scripts/01d_ingest_fred_market.py [--force]"""
import argparse
import io
from datetime import date

import pandas as pd

from lib_common import connect, fetch, user_agent, vintage_done, drop_other_vintages

SERIES = ['GASREGW', 'DCOILWTICO', 'DCOILBRENTEU', 'DHHNGSP', 'DJFUELUSGULF', 'SP500', 'NASDAQCOM', 'DTWEXBGS', 'T10YIE', 'UNRATE']
URL = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id='


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    vintage = f'{date.today():%Y-%m-%d}'
    con = connect()
    if vintage_done(con, 'market_data', vintage) and not a.force:
        print(f'market_data vintage {vintage} already ingested (use --force)')
        return
    parts = []
    for sid in SERIES:
        p = fetch(URL + sid, f'fred_{sid}.csv', user_agent(), a.force)
        d = pd.read_csv(p)
        d.columns = ['date', 'value']
        d['value'] = pd.to_numeric(d.value, errors='coerce')
        parts.append(d.dropna().assign(series_id=sid, date=lambda x: pd.to_datetime(x.date)))
    data = pd.concat(parts)[['series_id', 'date', 'value']]
    data['vintage'] = vintage
    con.execute('CREATE TABLE IF NOT EXISTS market_data AS SELECT * FROM data LIMIT 0')
    con.execute('DELETE FROM market_data WHERE vintage=?', [vintage])
    con.execute('INSERT INTO market_data SELECT series_id, date, value, vintage FROM data')
    drop_other_vintages(con, 'market_data', vintage)
    print(data.groupby('series_id').agg(n=('value', 'size'), first=('date', 'min'), last=('date', 'max')).to_string())


if __name__ == '__main__':
    main()
