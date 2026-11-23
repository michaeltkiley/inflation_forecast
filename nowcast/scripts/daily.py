#!/usr/bin/env python3
"""Daily run: refresh the inputs, then compute and store today's nowcast. Stages run in order, each skipping work already done today (their own skip logic):
  00 restore the nowcast run history from the archive into a fresh database (GitHub Actions),
  01a BEA PCE detail, 01b BLS CPI, 01c PPI/import prices, 01d market data, 01e CPI weights (all required: a failure stops the run),
  07 BEA first prints from ALFRED and 20 Cleveland Fed benchmark (both optional: a failure is reported but does not stop the nowcast), 06 nowcast (required), 19 vintage archive of the day's inputs (optional
  so it cannot lose a result, but a failure makes the run exit 1), 21 rebuild of the public dashboard docs/index.html and 22 a headless-browser check of it (both optional).
Output goes to data/logs/<date>_daily.log. Ends with a freshness check of the newest observation of each source; exit code 1 if a required stage failed
or a source is stale (so a scheduler or GitHub workflow can flag it).  Usage: python scripts/daily.py"""
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from lib_common import DATA, RAW, connect

HERE = Path(__file__).resolve().parent
STAGES = [('00_restore_history.py', True), ('01a_ingest_bea.py', True), ('01b_ingest_bls_cpi.py', True), ('01c_ingest_bls_ppi.py', True), ('01d_ingest_fred_market.py', True),
          ('01e_ingest_cpi_weights.py', True), ('07_ingest_first_prints.py', False), ('20_ingest_cleveland.py', False),
          ('06_nowcast_daily.py', True), ('19_archive_vintages.py', False), ('21_build_site.py', False), ('22_check_site.py', False)]
# Newest observation allowed to be this many days old before a source is called stale. Monthly series are dated the 1st of their month and published after the month
# ends (CPI/PPI ~2 weeks, unemployment ~1 week, BEA PCE ~4 weeks), so a current monthly series can be ~75-90 days old by its date just before the next release.
MAX_AGE = {'BEA PCE prices (U20404)': 95, 'BLS CPI': 80, 'BLS PPI/import': 80, 'market (weekly gasoline)': 10, 'market (daily oil)': 7, 'unemployment rate': 70, 'first prints': 95, 'Cleveland Fed benchmark': 5}


RAW_KEEP_DAYS = 14
KEEP_ALWAYS = ('FAQ521', 'relative_importance')          # reference documents downloaded rarely, not re-fetched daily


def prune_raw():
    """Delete dated raw downloads (data/raw/YYYYMMDD_*) older than RAW_KEEP_DAYS days. The parsed data is in DuckDB; raw files are only a short-term audit trail."""
    cutoff = f'{date.today() - timedelta(days=RAW_KEEP_DAYS):%Y%m%d}'
    gone = [p for p in sorted(RAW.glob('2*_*')) if p.name[:8].isdigit() and p.name[:8] < cutoff and not any(k in p.name for k in KEEP_ALWAYS)]
    for p in gone:
        p.unlink()
    return len(gone)


def freshness():
    con = connect()
    q = lambda s: con.execute(s).fetchone()[0]
    newest = {'BEA PCE prices (U20404)': q("select max(date) from bea_pce where table_id='U20404'"), 'BLS CPI': q('select max(date) from cpi_data'),
              'BLS PPI/import': q('select max(date) from ppi_data'),
              'market (weekly gasoline)': q("select max(date) from market_data where series_id='GASREGW'"),
              'market (daily oil)': q("select max(date) from market_data where series_id='DCOILWTICO'"),
              'unemployment rate': q("select max(date) from market_data where series_id='UNRATE'"), 'first prints': q('select max(month) from first_print'),
              'Cleveland Fed benchmark': q("select max(date) from cleveland_nowcast where kind='nowcast'")}
    latest_run = q('select max(run_date) from nowcast_agg')
    stale = []
    print('\nFreshness (newest observation; days old; limit):')
    for k, v in newest.items():
        age = (pd.Timestamp(date.today()) - pd.Timestamp(v)).days
        flag = 'STALE' if age > MAX_AGE[k] else 'ok'
        if flag == 'STALE':
            stale.append(k)
        print(f'  {flag:5s} {k:28s} {pd.Timestamp(v):%Y-%m-%d}  {age:3d}d  (<= {MAX_AGE[k]})')
    print(f'  latest stored nowcast run: {latest_run}')
    for r in con.execute('select month, round(overall, 3), round(core, 3), round(known_share_core, 0) from nowcast_agg where run_date=? order by month', [latest_run]).fetchall():
        print(f'  nowcast {r[0]}: headline PCE {r[1]}  core PCE {r[2]}  (core spending from released data {r[3]:.0f}%)')
    return stale, latest_run


def main():
    log_dir = DATA / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f'{date.today():%Y%m%d}_daily.log'
    failed = []
    with open(log, 'a') as f:
        def out(s):
            print(s)
            f.write(s + '\n')
            f.flush()
        out(f'=== daily run {datetime.now():%Y-%m-%d %H:%M:%S} ===')
        for script, required in STAGES:
            r = subprocess.run([sys.executable, str(HERE / script)], capture_output=True, text=True)
            body = '\n'.join(x for x in (r.stdout + r.stderr).splitlines() if x.strip() and 'X-13' not in x)
            out(f'--- {script}: {"ok" if r.returncode == 0 else "FAILED"}' + (f'\n{body}' if body else ''))
            if r.returncode != 0:
                failed.append(script)
                if required:
                    out(f'required stage failed; stopping. See above.')
                    return 1
        n = prune_raw()
        out(f'\nraw files older than {RAW_KEEP_DAYS} days removed: {n}')
        stale, _ = freshness()
        if failed or stale:
            out(f'\nCOMPLETED WITH WARNINGS: failed optional stages {failed or "none"}; stale sources {stale or "none"}')
            return 1
        out('\nall stages ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
