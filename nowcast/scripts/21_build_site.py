#!/usr/bin/env python3
"""Build docs/data/nowcast.json, the data behind the Nowcast tab of the Inflation Tracker page (docs/index.html fetches it; the page itself is built by scripts/08_build_dashboard.py
at the repository root, which embeds the tab's HTML/CSS/JS from nowcast/site/). The JSON holds: current nowcast tiles (ours beside the Cleveland Fed's), each target month's daily Cleveland
path with our run history, the component breakdown of the current PCE months, the change since the previous run (once two runs exist), and the track record (backtest vs BEA first prints from
results/backtest_first_print.csv, with the Cleveland Fed scored on the same months). Cleveland Fed figures are shown as published with the attribution required by nowcast/docs/third_party_terms.md;
the file is still produced without them if the table is missing. The blob is validated before it is written, so a malformed file is never published.
Usage: python scripts/21_build_site.py [--out docs/data/nowcast.json]"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from lib_common import RESULTS, ROOT, SITE_JSON, connect

MEASURES = {'core_pce': ('Core PCE', 'core'), 'pce': ('Headline PCE', 'overall'), 'core_cpi': ('Core CPI', 'core'), 'cpi': ('Headline CPI', 'headline')}
r4 = lambda x: None if x is None or pd.isna(x) else round(float(x), 4)
ann = lambda m: None if m is None or pd.isna(m) else round(((1 + m / 100) ** 12 - 1) * 100, 2)


def group_of(row):
    return row.group.capitalize() if row.group != 'core' else ('Housing' if row.housing == 1 else 'Services ex-housing' if row.services == 1 else 'Goods')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(SITE_JSON))
    a = ap.parse_args()
    con = connect()
    q = lambda s, p=(): con.execute(s, list(p)).df()
    has = lambda t: con.execute('select count(*) from information_schema.tables where table_name=?', [t]).fetchone()[0] > 0
    run = q('select max(run_date) d from nowcast_agg').d[0]
    agg, cpi = q('select * from nowcast_agg order by run_date, month'), q('select * from nowcast_cpi order by run_date, month')
    pce_months = sorted(agg[agg.run_date == run].month)
    cpi_month = cpi[cpi.run_date == run].month.iloc[0]
    cle = q('select * from cleveland_nowcast') if has('cleveland_nowcast') else pd.DataFrame(columns=['kind', 'measure', 'target_month', 'date', 'value'])
    if len(cle):
        cle['target_month'] = pd.to_datetime(cle.target_month)
        cle['date'] = pd.to_datetime(cle.date)

    def cle_path(meas, month):
        d = cle[(cle.kind == 'nowcast') & (cle.measure == meas) & (cle.target_month == pd.Timestamp(month + '-01'))].sort_values('date')
        return [[f'{x:%Y-%m-%d}', r4(v)] for x, v in zip(d.date, d.value)]

    def cle_actual(meas, month):
        d = cle[(cle.kind == 'actual') & (cle.measure == meas) & (cle.target_month == pd.Timestamp(month + '-01'))]
        return [f'{d.date.iloc[0]:%Y-%m-%d}', r4(d.value.iloc[0])] if len(d) else None

    def ours_hist(meas, month):
        t, col = (agg, MEASURES[meas][1]) if meas.endswith('pce') or meas == 'pce' else (cpi, MEASURES[meas][1])
        d = t[t.month == month].sort_values('run_date')
        return [[x, r4(v)] for x, v in zip(d.run_date, d[col])]

    # ---- series per (measure, month): what the chart draws
    show = {'core_pce': pce_months, 'pce': pce_months, 'core_cpi': [cpi_month], 'cpi': [cpi_month]}
    # the previous CPI month (already published) is shown with Cleveland's path and the actual, so the chart has context
    prev_cpi = f'{pd.Timestamp(cpi_month + "-01") - pd.DateOffset(months=1):%Y-%m}'
    show['core_cpi'] = [prev_cpi, cpi_month]
    show['cpi'] = [prev_cpi, cpi_month]
    series = {}
    for meas, months in show.items():
        for m in months:
            series[f'{meas}|{m}'] = dict(label=MEASURES[meas][0], month=m, ours=ours_hist(meas, m), cleveland=cle_path(meas, m), actual=cle_actual(meas, m))

    # ---- tiles (latest values)
    def ours_now(meas, month):
        h = ours_hist(meas, month)
        return h[-1][1] if h else None

    def cle_now(meas, month):
        p = cle_path(meas, month)
        return (p[-1][1], p[-1][0]) if p else (None, None)
    tiles = []
    for meas, month in [('core_pce', pce_months[0]), ('pce', pce_months[0]), ('core_pce', pce_months[1]), ('pce', pce_months[1]), ('core_cpi', cpi_month), ('cpi', cpi_month)]:
        o, (c, cd) = ours_now(meas, month), cle_now(meas, month)
        tiles.append(dict(key=meas, label=MEASURES[meas][0], month=month, ours=o, ours_ann=ann(o), cleveland=c, cleveland_date=cd))
    # known share of core PCE spending priced from released data (current month)
    known = {m: r4(v) for m, v in zip(agg[agg.run_date == run].month, agg[agg.run_date == run].known_share_core)}

    # ---- components of the current PCE months
    cfg = pd.read_csv(ROOT / 'config' / 'pce_leaf_map.csv')
    cfg['line'] = cfg.line.astype(int)
    cfg['grp'] = cfg.apply(group_of, axis=1)
    cfg['label'] = cfg.label.str.replace(r'\s*\(\d+\)$', '', regex=True)
    leaf = q('select * from nowcast_leaf where run_date=?', [run]).merge(cfg[['line', 'label', 'grp', 'group']], on='line')
    comps = {}
    for m in pce_months:
        d = leaf[leaf.month == m].copy()
        core = d[d.group == 'core']
        tot_core, tot_all = core.share.sum(), d.share.sum()
        d['c_head'] = d.share * d.mom / 100 * 100                                   # bp of headline monthly change
        core = core.assign(c_core=core.share * core.mom / tot_core * 100)           # bp of core monthly change
        groups = []
        for g, x in d.groupby('grp'):
            groups.append(dict(group=g, bp_headline=r4(x.c_head.sum()), spend_share=r4(x.share.sum()), released_share=r4(x[x.status == 'released'].share.sum() / x.share.sum() * 100)))
        top = core.reindex(core.c_core.abs().sort_values(ascending=False).index).head(12)
        comps[m] = dict(groups=sorted(groups, key=lambda g: -abs(g['bp_headline'])),
                        leaves=[dict(label=r.label, bp_core=r4(r.c_core), mom=r4(r.mom), spend_share=r4(r.share), status=r.status, group=r.grp) for r in top.itertuples()],
                        n_released=int((d.status == 'released').sum()), n_leaves=int(len(d)))

    # ---- what changed since the previous run
    changed = None
    prev = q('select max(run_date) d from nowcast_agg where run_date<?', [run]).d[0]
    if prev:
        old = q('select * from nowcast_leaf where run_date=?', [prev])
        n = leaf.merge(old, on=['month', 'line'], suffixes=('', '_old'))
        n['bp'] = n.share * n.mom - n.share_old * n.mom_old
        n['why'] = np.where((n.status == 'released') & (n.status_old != 'released'), 'Data released', np.where(n.status == 'released', 'Revision', 'Forecast / fill update'))
        changed = dict(prev_run=prev, rows=[dict(month=m, why=w, bp_headline=r4(x.bp.sum()), bp_core=r4(x[x.group == 'core'].bp.sum() / x[x.group == 'core'].share.sum() * 100)) for (m, w), x in n.groupby(['month', 'why'])])

    # ---- track record: backtest vs BEA first prints, Cleveland scored on the same months
    track = None
    bt = RESULTS / 'backtest_first_print.csv'
    if bt.exists():
        b = pd.read_csv(bt, parse_dates=['month'])
        months = sorted(b.month.unique())
        pivot = lambda col: {mod: b[b.model == mod].set_index('month')[col] for mod in b.model.unique()}
        chart = []
        for m in months[-36:]:
            row = dict(month=f'{m:%Y-%m}')
            for tgt, col in [('core', 'core'), ('all', 'all')]:
                sel = b[(b.month == m)]
                row[f'fp_{tgt}'] = r4(sel[f'fp_{col}'].iloc[0])
                for mod, key in [('post_import', 'after'), ('pre_cpi', 'pre')]:
                    s = sel[sel.model == mod]
                    row[f'{key}_{tgt}'] = r4(s[f'est_{col}'].iloc[0]) if len(s) else None
            chart.append(row)
        mae = lambda mod, c: float(b[b.model == mod][f'miss_fp_{c}'].abs().mean())
        table = []
        for lab, mod in [('Ours, before CPI', 'pre_cpi'), ('Ours, after CPI', 'post_cpi'), ('Ours, after CPI and PPI', 'post_ppi'), ('Ours, after CPI, PPI and import prices', 'post_import'),
                         ('DMS baseline, before CPI', 'dms_pre_cpi'), ('DMS baseline, after CPI', 'dms_post_cpi')]:
            table.append(dict(model=lab, core=r4(mae(mod, 'core')), headline=r4(mae(mod, 'all')), n=int((b.model == mod).sum()), who='ours' if lab.startswith('Ours') else 'baseline'))
        if len(cle):                                                                  # Cleveland Fed, same months, vs its own recorded actual
            def cle_err(meas):
                out = {'pre': [], 'final': []}
                for m in months:
                    tm = pd.Timestamp(m)
                    path = cle[(cle.kind == 'nowcast') & (cle.measure == meas) & (cle.target_month == tm)].sort_values('date')
                    act = cle[(cle.kind == 'actual') & (cle.measure == meas) & (cle.target_month == tm)]
                    cp = cle[(cle.kind == 'actual') & (cle.measure == 'cpi') & (cle.target_month == tm)]
                    if path.empty or act.empty or cp.empty:
                        continue
                    out['final'].append(abs(path.value.iloc[-1] - act.value.iloc[0]) * 100)
                    before = path[path.date < cp.date.iloc[0]]
                    if len(before):
                        out['pre'].append(abs(before.value.iloc[-1] - act.value.iloc[0]) * 100)
                return out
            cc, ch = cle_err('core_pce'), cle_err('pce')
            table.append(dict(model='Cleveland Fed, before CPI', core=r4(np.mean(cc['pre'])), headline=r4(np.mean(ch['pre'])), n=len(cc['pre']), who='cleveland'))
            table.append(dict(model='Cleveland Fed, last before release', core=r4(np.mean(cc['final'])), headline=r4(np.mean(ch['final'])), n=len(cc['final']), who='cleveland'))
        track = dict(chart=chart, table=table, months=f'{months[0]:%Y-%m} to {months[-1]:%Y-%m}', n_months=len(months), backtest_run=f'{datetime.fromtimestamp(bt.stat().st_mtime):%Y-%m-%d}')

    fresh = dict(cpi=q('select max(date) d from cpi_data').d[0], ppi=q('select max(date) d from ppi_data').d[0], pce=q("select max(date) d from bea_pce where table_id='U20404'").d[0],
                 cleveland=q("select max(date) d from cleveland_nowcast where kind='nowcast'").d[0] if has('cleveland_nowcast') else None)
    blob = dict(run_date=run, built=f'{datetime.now():%Y-%m-%d %H:%M}', pce_months=pce_months, cpi_month=cpi_month, known_share_core=known, tiles=tiles, series=series, components=comps,
                changed=changed, track=track, has_cleveland=bool(len(cle)), first_run=q('select min(run_date) d from nowcast_agg').d[0], n_runs=int(q('select count(distinct run_date) n from nowcast_agg').n[0]),
                fresh={k: (f'{pd.Timestamp(v):%Y-%m}' if k in ('cpi', 'ppi', 'pce') else f'{pd.Timestamp(v):%Y-%m-%d}') if v is not None else None for k, v in fresh.items()})
    validate(blob)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(blob, separators=(',', ':')))
    print(f'wrote {out} ({out.stat().st_size / 1e3:.0f} KB): run {run}, PCE months {pce_months}, CPI month {cpi_month}, {len(series)} chart series, track record {"yes" if track else "no"}, Cleveland {"yes" if blob["has_cleveland"] else "no"}')
    return blob


def validate(b):
    """Refuse to publish a malformed or implausible file: required keys, finite numbers, tiles in a sane range."""
    need = ['run_date', 'built', 'pce_months', 'cpi_month', 'known_share_core', 'tiles', 'series', 'components', 'track', 'fresh', 'has_cleveland', 'n_runs', 'first_run']
    miss = [k for k in need if k not in b]
    if miss:
        raise SystemExit(f'nowcast.json missing keys: {miss}')
    if len(b['tiles']) != 6 or len(b['pce_months']) != 2:
        raise SystemExit('nowcast.json: unexpected number of tiles or PCE months')
    for t in b['tiles']:
        if t['ours'] is None or not np.isfinite(t['ours']) or abs(t['ours']) > 3:
            raise SystemExit(f'nowcast.json: implausible tile {t["label"]} {t["month"]}: {t["ours"]}')
    for k, sr in b['series'].items():
        for kind in ('ours', 'cleveland'):
            for pt in sr[kind]:
                if pt[1] is None or not np.isfinite(pt[1]):
                    raise SystemExit(f'nowcast.json: non-finite value in series {k}/{kind}')
    for m, c in b['components'].items():
        if not c['groups'] or not c['leaves']:
            raise SystemExit(f'nowcast.json: empty components for {m}')


if __name__ == '__main__':
    main()
