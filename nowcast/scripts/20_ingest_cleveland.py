#!/usr/bin/env python3
"""Ingest the Federal Reserve Bank of Cleveland's Inflation Nowcasting monthly (month-over-month) chart data into DuckDB table `cleveland_nowcast`
(kind, measure, target_month, date, value): the daily nowcast path of every target month since 2013 (kind 'nowcast') and the actual figure Cleveland records
when it is released (kind 'actual', dated on the release day). Measures: cpi, core_cpi, pce, core_pce.
Source and terms: docs/third_party_terms.md (the nowcast charts carry a CC BY 4.0 licence; credit the Cleveland Fed, https://doi.org/10.26509/frbc-inflationnowcast).
The file is the one the Bank's own page loads; it is undocumented, so a failed fetch or an unexpected layout ends the stage with an error and leaves the table as it was.
Fetched once per day with a generic User-Agent (no personal details). Skips if today's pull is stored; --force refetches.  Usage: python scripts/20_ingest_cleveland.py [--force]"""
import argparse
import json
import re
from datetime import date

import pandas as pd

from lib_common import connect, fetch

URL = 'https://www.clevelandfed.org/-/media/files/webcharts/inflationnowcasting/nowcast_month.json?sc_lang=en'
UA = 'inflation-nowcast/0.1 (research dashboard)'
MEASURES = {'CPI Inflation': ('nowcast', 'cpi'), 'Core CPI Inflation': ('nowcast', 'core_cpi'), 'PCE Inflation': ('nowcast', 'pce'),
            'Core PCE Inflation': ('nowcast', 'core_pce'), 'Actual CPI Inflation': ('actual', 'cpi'), 'Actual Core CPI Inflation': ('actual', 'core_cpi'),
            'Actual PCE Inflation': ('actual', 'pce'), 'Actual Core PCE Inflation': ('actual', 'core_pce')}


def label_dates(labels, target):
    """MM/DD labels -> dates: the year starts at the target month's year (one before if the path starts months earlier) and advances when the month number drops.
    The axis also carries release-event markers ('CPI Aug', 'PCE Jul') with no data slot; they are dropped, and each series must then have exactly one point per date."""
    out, year, prev = [], target.year, None
    for i, lab in enumerate(x for x in labels if re.fullmatch(r'\d{1,2}/\d{1,2}', x)):
        mo, dy = (int(x) for x in lab.split('/'))
        if i == 0 and mo > target.month + 6:
            year -= 1
        elif prev is not None and mo < prev:
            year += 1
        out.append(pd.Timestamp(year, mo, dy))
        prev = mo
    return out


def parse(raw):
    rows = []
    for c in raw:
        ch = c['chart']
        y, m = (int(x) for x in ch['subcaption'].split('-'))
        target = pd.Timestamp(y, m, 1)
        dates = label_dates([x['label'] for x in c['categories'][0]['category']], target)
        for s in c['dataset']:
            if s['seriesname'] not in MEASURES:
                raise ValueError(f'unexpected series {s["seriesname"]!r}')
            kind, meas = MEASURES[s['seriesname']]
            if len(s['data']) != len(dates):
                raise ValueError(f'{ch["subcaption"]} {s["seriesname"]}: {len(s["data"])} points but {len(dates)} date labels')
            for d, p in zip(dates, s['data']):                      # each point's tooltip repeats its own MM/DD: cross-check the alignment
                if p.get('tooltext') and '{br}' in p['tooltext'] and p['tooltext'].split('{br}')[1] != f'{d.month:02d}/{d.day:02d}':
                    raise ValueError(f'{ch["subcaption"]} {s["seriesname"]}: label/point misaligned at {d:%m/%d}')
            for d, p in zip(dates, s['data']):
                if p.get('value') not in ('', None):
                    rows.append((kind, meas, target, d, float(p['value'])))
    return pd.DataFrame(rows, columns=['kind', 'measure', 'target_month', 'date', 'value'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    con = connect()
    today = f'{date.today():%Y-%m-%d}'
    if not a.force and con.execute("select count(*) from information_schema.tables where table_name='cleveland_nowcast'").fetchone()[0]:
        if con.execute('select count(*) from cleveland_nowcast where pulled=?', [today]).fetchone()[0]:
            print(f'cleveland_nowcast {today} already stored (use --force)')
            return
    raw = json.loads(fetch(URL, 'cleveland_nowcast_month.json', UA, a.force).read_text())
    if not isinstance(raw, list) or not raw:
        raise SystemExit('unexpected Cleveland file layout: not a list of charts')
    d = parse(raw).assign(pulled=today)
    if d.empty or d[d.kind == 'nowcast'].target_month.nunique() < 100:
        raise SystemExit('unexpected Cleveland file contents: too few target months')
    con.execute('CREATE OR REPLACE TABLE cleveland_nowcast AS SELECT * FROM d')
    last = d[d.kind == 'nowcast'].groupby('measure').date.max()
    print(f'{d[d.kind == "nowcast"].target_month.nunique()} target months {d.target_month.min():%Y-%m} to {d.target_month.max():%Y-%m}; {len(d):,} values; newest nowcast dates:')
    print(last.dt.strftime('%Y-%m-%d').to_string())


if __name__ == '__main__':
    main()
