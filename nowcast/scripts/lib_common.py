"""Shared paths, DuckDB connection and download helper. All state lives in data/nowcast.duckdb; raw downloads are
kept flat in data/raw/ as YYYYMMDD_<name> so a pull can be re-parsed without hitting the network."""
import os
from datetime import date
from pathlib import Path

import duckdb
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
RAW = DATA / 'raw'
DB = DATA / 'nowcast.duckdb'
RESULTS = ROOT / 'results'                                                            # small committed artifacts (backtest table)
ARCHIVE = Path(os.environ.get('NOWCAST_ARCHIVE', ROOT / 'archive'))                  # vintage archive + run history; in CI the `data` branch checkout
SITE_JSON = ROOT.parent / 'docs' / 'data' / 'nowcast.json'                             # read by the Nowcast tab of the Inflation Forecast page


def load_env():
    f = ROOT / '.env'
    if f.exists():
        for ln in f.read_text().splitlines():
            if '=' in ln and not ln.startswith('#'):
                k, v = ln.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())


def connect():
    DATA.mkdir(exist_ok=True)
    return duckdb.connect(str(DB))


def user_agent(contact_required=False):
    load_env()
    contact = os.environ.get('BLS_CONTACT', '').strip()
    if contact_required and not contact:
        raise SystemExit('BLS_CONTACT is not set: copy .env.example to .env and fill it in')
    return f'inflation-nowcast/0.1 ({contact})' if contact else 'Mozilla/5.0'


def fetch(url, name, ua, force=False):
    """Download url to data/raw/<today>_<name> unless today's copy exists; return the path."""
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f'{date.today():%Y%m%d}_{name}'
    if path.exists() and not force:
        return path
    r = requests.get(url, headers={'User-Agent': ua}, timeout=600)
    r.raise_for_status()
    path.write_bytes(r.content)
    return path


def vintage_done(con, table, vintage):
    exists = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name=?", [table]).fetchone()[0]
    return bool(exists) and con.execute(f'SELECT count(*) FROM {table} WHERE vintage=?', [vintage]).fetchone()[0] > 0


def drop_other_vintages(con, table, vintage):
    """The working database keeps only the current vintage of each input; history lives in the vintage archive (lib_vintage.py, scripts/19_archive_vintages.py)."""
    con.execute(f'DELETE FROM {table} WHERE vintage <> ?', [vintage])
