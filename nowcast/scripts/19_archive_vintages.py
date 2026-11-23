#!/usr/bin/env python3
"""Archive today's input observations (new or revised since the archive's state) into the durable vintage archive (archive/deltas/*.parquet; see lib_vintage.py), then
check that the archive's state matches the working database, and write the day's nowcast run history (<dir>/runs/<date>/*.parquet; restored by 00_restore_history.py). Run after the ingests (01a-01d). Idempotent: a day with no change writes nothing.
Sources: cleveland (Cleveland Fed nowcasts, CC BY 4.0), bea:<table> (bea_pce), bls_cpi (cpi_data), bls_ppi (ppi_data), fred (market_data, except the licensed stock-index series in NO_REDISTRIBUTE).  Usage: python scripts/19_archive_vintages.py [--dir archive]"""
import argparse

import duckdb
import pandas as pd

from lib_common import ARCHIVE, DB
from lib_vintage import archive_day, export_runs, state

# Series with third-party licences that do not clearly allow redistribution (S&P Dow Jones Indices, Nasdaq via FRED). They are inputs to evaluation scripts only, not to
# any adopted model, and the archive is meant to be public, so they are kept out of it (they stay in the local working database).
NO_REDISTRIBUTE = ('SP500', 'NASDAQCOM')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=str(ARCHIVE))
    a = ap.parse_args()
    con = duckdb.connect(str(DB), read_only=True)
    vint = {t: con.execute(f'select max(vintage) from {t}').fetchone()[0] for t in ['bea_pce', 'cpi_data', 'ppi_data', 'market_data']}
    as_of = max(vint.values())
    if len(set(vint.values())) > 1:
        print(f'WARNING: inputs are not from the same day: {vint}')
    today = con.execute("""
        SELECT DISTINCT 'bea:' || table_id AS source, series_code AS series, date, value FROM bea_pce
        UNION ALL SELECT 'bls_cpi', series_id, date, value FROM cpi_data
        UNION ALL SELECT 'bls_ppi', series_id, date, value FROM ppi_data
        UNION ALL SELECT 'fred', series_id, date, value FROM market_data""").df()
    if con.execute("select count(*) from information_schema.tables where table_name='cleveland_nowcast'").fetchone()[0]:      # Cleveland Fed benchmark (CC BY 4.0; see README of the archive)
        today = pd.concat([today, con.execute("""SELECT 'cleveland' AS source, kind || ':' || measure || ':' || strftime(target_month, '%Y-%m') AS series, date, value
                                                  FROM cleveland_nowcast""").df()], ignore_index=True)
    today = today[~((today.source == 'fred') & today.series.isin(NO_REDISTRIBUTE))].copy()
    today['seen_at'] = pd.Timestamp.now()
    new, rev, rem = archive_day(today, a.dir, as_of)
    print(f'archive {as_of}: {new} new, {rev} revised, {rem} removed observations ({len(today):,} observations today)')
    run = con.execute('select max(run_date) from nowcast_agg').fetchone()[0]
    if run:
        print('run history exported:', export_runs(con, a.dir, run))             # reads only: the read-only connection is enough
    arch = state(a.dir)
    m = today.assign(date=pd.to_datetime(today.date)).merge(arch, on=['source', 'series', 'date'], how='outer', suffixes=('', '_arch'), indicator=True)
    bad = ((m._merge != 'both') | ((m.value - m.value_arch).abs() > 1e-9 * m.value.abs().clip(lower=1))).sum()
    print(f'archive state matches the database: {"yes" if bad == 0 else f"NO ({bad} differences)"}')
    if bad:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
