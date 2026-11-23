#!/usr/bin/env python3
"""Independent data test of config/pce_leaf_map.csv (does not rely on the map's author):
 (1) Completeness: signed leaf nominal spending (U20405) should sum to total PCE in every month.
 (2) Mapping fit: for each single-source leaf, BEA's published monthly price change (U20404) should track the mapped BLS
     series. Reports, over the last 36 BEA months (excluding the newest 2), the share of months where the two agree within
     0.05 pp (rounding) and the correlation. Leaves that fit poorly are listed for review; `:own` leaves (BEA seasonally
     adjusts them) and multi-source/nonmarket/constant leaves are expected to differ and are reported separately.
Writes data/crosswalk_fit.csv.  Usage: python scripts/02b_check_crosswalk.py"""
import numpy as np
import pandas as pd

from lib_common import DATA, ROOT, connect

PCT_OK = 0.05          # pp tolerance for "agrees"
FIT_MIN = 0.8          # a single-source leaf should agree in at least this share of months


def main():
    m = pd.read_csv(ROOT / 'config' / 'pce_leaf_map.csv', dtype=str)
    con = connect()
    v = con.execute("select max(vintage) from bea_pce").fetchone()[0]
    bea = con.execute("select series_code, date, value from bea_pce where vintage=? and table_id in ('U20404','U20405')", [v]).df()
    bea = bea.drop_duplicates(['series_code', 'date']).pivot(index='date', columns='series_code', values='value')
    src = con.execute("select series_id, date, value from cpi_data where vintage=(select max(vintage) from cpi_data) "
                      "union all select series_id, date, value from ppi_data where vintage=(select max(vintage) from ppi_data)").df()
    src = src.pivot(index='date', columns='series_id', values='value')

    # (1) completeness: signed nominal leaves vs total PCE (U20405 line 1)
    tot_code = con.execute("select series_code from bea_pce where table_id='U20405' and line=1 limit 1").fetchone()[0]
    leaves = bea[m.bea_nominal_code].mul(m.sign.astype(float).values, axis=1).sum(axis=1)
    gap = ((leaves - bea[tot_code]) / bea[tot_code] * 100).loc['2015':]
    print(f'(1) leaves vs total PCE ({tot_code}), 2015+: max |gap| {gap.abs().max():.4f}%  mean {gap.abs().mean():.4f}%')

    # (2) mapping fit
    window = bea.index[-38:-2]
    rows = []
    for _, r in m.iterrows():
        parts = [] if pd.isna(r.series) else r.series.split(';')
        row = dict(line=r.line, label=r.label, kind=r.kind, n_src=len(parts), rule=parts[0].split(':')[1] if parts else '')
        if len(parts) == 1:
            sid = parts[0].split(':')[0]
            a = np.log(bea[r.bea_price_code]).diff().mul(100).loc[window]
            b = np.log(src[sid]).diff().mul(100).reindex(window)
            both = a.notna() & b.notna()               # CPI items not published monthly are scored only where observed
            ok = ((a - b).abs() <= PCT_OK)[both]
            row.update(source=sid, n_months=int(both.sum()), share_agree=ok.mean() if both.any() else np.nan,
                       corr=a.corr(b), mean_abs_gap=(a - b).abs().mean())
        rows.append(row)
    d = pd.DataFrame(rows)
    d.to_csv(DATA / 'crosswalk_fit.csv', index=False)
    one = d[d.n_src == 1]
    for rule in ['bls', 'none', 'own']:
        s = one[one.rule == rule]
        print(f'(2) single-source ":{rule}" leaves: {len(s)}; median share agreeing {s.share_agree.median():.2f}; '
              f'below {FIT_MIN}: {(s.share_agree < FIT_MIN).sum()}')
    bad = one[(one.rule != 'own') & ~(one.share_agree >= FIT_MIN)].sort_values('share_agree')
    print('\nSingle-source leaves (not :own) that fit poorly, for review:')
    print(bad[['line', 'label', 'source', 'n_months', 'share_agree', 'corr', 'mean_abs_gap']].round(2).to_string(index=False))
    print(f'\nNot tested here: {(d.n_src != 1).sum()} multi-source / nonmarket / constant leaves')


if __name__ == '__main__':
    main()
