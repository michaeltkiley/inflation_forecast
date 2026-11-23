"""Durable vintage archive of every raw input value the nowcast reads (same design as gdpnow-replication's gdpnow/vintage.py).

The working DuckDB keeps only the current vintage of each input (sources overwrite their history when they revise). This module records, forward in time and
forever, each observation when it was first seen and every time its value changed, so the inputs as they stood on any past day can be rebuilt.

Layout (a directory; in production the `data` branch of the repository):
    deltas/<as_of>_<UTC write time YYYYMMDDHHMMSSffffff>.parquet   columns: source, series, date, value, prior_value, seen_at, as_of
A delta file holds the observations that are new or revised since the archive's current state (prior_value NULL = new), plus a row with value NULL for each
date that disappeared from a series pulled that day. The first file is therefore the whole baseline. The current state is the newest row per
(source, series, date) over all files; days with no change write nothing."""
import datetime as dt
from pathlib import Path

import duckdb
import pandas as pd

TOL = 1e-9            # relative; a value counts as revised beyond this
README = """# Vintage archive

Every raw input value the inflation nowcast reads, recorded when first seen and each time it changed (forward from the first file).

`deltas/<as_of>_<UTC write time>.parquet`: source, series, date (observation), value, prior_value (NULL = new observation), seen_at (when retrieved), as_of (run date).
A row with value NULL marks a date that disappeared from a series. The state on a day is the newest row per (source, series, date) among the files up to that day.
Written by `scripts/19_archive_vintages.py`; read with `scripts/vintage_asof.py` or DuckDB: `SELECT * FROM read_parquet('deltas/*.parquet')`.
Sources: bea:<table> (BEA bulk NIPA, series code), bls_cpi, bls_ppi (BLS flat files, series id), fred (FRED CSV market series), cleveland (below).

Cleveland Fed nowcasts (source `cleveland`, series `<kind>:<measure>:<target month>`, kind nowcast or actual, date = the nowcast date or the release date): Federal Reserve Bank of Cleveland,
Inflation Nowcasting, https://doi.org/10.26509/frbc-inflationnowcast, licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Cleveland Fed calculations based on data from BLS, BEA,
EIA, Financial Times and Haver Analytics. Recorded here as published; no endorsement by the Cleveland Fed is implied.
"""


def _files(d, upto=None):
    fs = sorted((Path(d) / 'deltas').glob('*.parquet'))
    if upto is not None:
        fs = [f for f in fs if f.stem.split('_')[0] <= str(upto)]
    return [str(f) for f in fs]


def state(d, upto=None, source=None, series=None):
    """DataFrame(source, series, date, value): newest archived value per key among files up to run date `upto` (inclusive; None = all); removed keys left out."""
    fs = _files(d, upto)
    if not fs:
        return pd.DataFrame({'source': [], 'series': [], 'date': pd.to_datetime([]), 'value': []})
    where, args = '', [fs]
    for col, v in [('source', source), ('series', series)]:
        if v is not None:
            where += f' AND {col} = ?'
            args.append(v)
    q = f"""SELECT source, series, CAST(date AS DATE) AS date, value FROM (
              SELECT *, row_number() OVER (PARTITION BY source, series, date ORDER BY filename DESC) AS rn
              FROM read_parquet(?, filename = true) WHERE true {where}) WHERE rn = 1 AND value IS NOT NULL"""
    out = duckdb.connect().execute(q, args).fetchdf()
    out['date'] = pd.to_datetime(out['date'])
    return out


def compute_delta(today, d, as_of):
    """Delta rows (source, series, date, value, prior_value, seen_at, as_of) of `today` (DataFrame source, series, date, value, seen_at) against the archive in `d`."""
    db = duckdb.connect()
    t = today.copy()
    t['date'] = pd.to_datetime(t['date']).dt.normalize()
    db.register('t', t)
    db.register('a', state(d))
    new_or_rev = db.execute(f"""
        SELECT t.source, t.series, CAST(t.date AS DATE) AS date, t.value, a.value AS prior_value, t.seen_at, '{as_of}' AS as_of
        FROM t LEFT JOIN a ON t.source = a.source AND t.series = a.series AND CAST(t.date AS DATE) = CAST(a.date AS DATE)
        WHERE a.value IS NULL OR abs(a.value - t.value) > {TOL} * greatest(1, abs(a.value))""").fetchdf()
    removed = db.execute(f"""
        SELECT a.source, a.series, CAST(a.date AS DATE) AS date, CAST(NULL AS DOUBLE) AS value, a.value AS prior_value,
               current_timestamp::TIMESTAMP AS seen_at, '{as_of}' AS as_of
        FROM a JOIN (SELECT DISTINCT source, series FROM t) p ON a.source = p.source AND a.series = p.series
        LEFT JOIN t ON t.source = a.source AND t.series = a.series AND CAST(t.date AS DATE) = CAST(a.date AS DATE)
        WHERE t.value IS NULL""").fetchdf()
    return pd.concat([new_or_rev, removed], ignore_index=True)


def write_delta(delta, d, as_of):
    p = Path(d) / 'deltas'
    p.mkdir(parents=True, exist_ok=True)
    path = p / f'{as_of}_{dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")}.parquet'
    db = duckdb.connect()
    db.register('x', delta)
    db.execute(f"COPY (SELECT * FROM x ORDER BY source, series, date) TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    return str(path)


def archive_day(today, d, as_of):
    """Archive one run date's observations; returns (new, revised, removed). Writes nothing if nothing changed; idempotent for a repeated day."""
    Path(d).mkdir(parents=True, exist_ok=True)
    readme = Path(d) / 'README.md'
    if not readme.exists():
        readme.write_text(README)
    delta = compute_delta(today, d, as_of)
    if len(delta):
        write_delta(delta, d, as_of)
    return (int((delta.prior_value.isna() & delta.value.notna()).sum()), int((delta.prior_value.notna() & delta.value.notna()).sum()), int(delta.value.isna().sum()))


RUN_TABLES = ['nowcast_agg', 'nowcast_cpi', 'nowcast_leaf']       # our own daily outputs: the track record, which cannot be rebuilt from the inputs


def export_runs(con, d, run_date):
    """Write the day's rows of the run-history tables to <d>/runs/<run_date>/<table>.parquet (overwrites the same day; idempotent)."""
    out = Path(d) / 'runs' / str(run_date)
    out.mkdir(parents=True, exist_ok=True)
    n = {}
    for t in RUN_TABLES:
        path = out / f'{t}.parquet'
        con.execute(f"COPY (SELECT * FROM {t} WHERE run_date = ? ORDER BY 1, 2) TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)", [str(run_date)])
        n[t] = con.execute(f'SELECT count(*) FROM {t} WHERE run_date = ?', [str(run_date)]).fetchone()[0]
    return n


def restore_runs(con, d):
    """Load every archived run into the run-history tables that do not exist yet (a fresh database in CI). Returns {table: rows loaded}."""
    loaded = {}
    for t in RUN_TABLES:
        files = sorted((Path(d) / 'runs').glob(f'*/{t}.parquet'))
        exists = con.execute('select count(*) from information_schema.tables where table_name=?', [t]).fetchone()[0]
        if exists or not files:
            continue
        con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_parquet([{', '.join(repr(str(f)) for f in files)}], union_by_name = true)")
        loaded[t] = con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
    return loaded
