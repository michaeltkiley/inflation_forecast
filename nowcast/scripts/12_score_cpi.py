#!/usr/bin/env python3
"""Bottom-up CPI: (1) reconstruction check - do BLS relative-importance weights, the leaf partition and the SA/NSA mix reproduce the published
all-items and core SA changes from the leaves' ACTUAL changes; (2) pre-release nowcast - leaves forecast from history (persist fill; motor fuel from the
DMS gasoline nowcast), aggregated, scored against published CPI and against the DMS baseline (data/dms_score.csv) on the same months.
bp of a monthly % change; published = latest vintage; months with no published CPI (Oct 2025) are skipped.
Usage: python scripts/12_score_cpi.py [--months 36]"""
import argparse

import numpy as np
import pandas as pd

from lib_common import DATA
from lib_cpi import CPI, persist_nowcast
from lib_dms import DMSData, nowcast


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=36)
    a = ap.parse_args()
    C = CPI()
    rec = C.run('2023-01-01')
    rec['pub_head'], rec['pub_core'] = C.head, C.core
    rec = rec.dropna(subset=['pub_head'])
    e_h, e_c = (rec['head'] - rec.pub_head) * 100, (rec['core'] - rec.pub_core) * 100
    print(f'(1) Reconstruction from actual leaf changes, {rec.index[0]:%Y-%m} to {rec.index[-1]:%Y-%m} ({len(rec)} months), bp:')
    print(f'    headline MAE {e_h.abs().mean():.2f} max {e_h.abs().max():.1f} bias {e_h.mean():.2f}   core MAE {e_c.abs().mean():.2f} max {e_c.abs().max():.1f} bias {e_c.mean():.2f}')
    print('    by year MAE (head/core):', ', '.join(f'{y}: {e_h[e_h.index.year == y].abs().mean():.2f}/{e_c[e_c.index.year == y].abs().mean():.2f}' for y in sorted(set(rec.index.year))))
    print(f'    leaves per year: ' + ', '.join(f'{y}: {len(C.leaves(y))}' for y in range(2022, 2026)))

    D = DMSData()
    last = C.head.dropna().index.max()
    months = pd.date_range(end=last, periods=a.months, freq='MS')
    gas = {m: nowcast(D, m)['gas_sa'] for m in months}
    now = C.run(months[0], last, forecast=persist_nowcast(gas))
    now['pub_head'], now['pub_core'] = C.head, C.core
    now = now.dropna(subset=['pub_head'])
    dms = pd.read_csv(DATA / 'dms_score.csv', parse_dates=['month']).set_index('month')
    now = now.join(dms[['cpi_all', 'cpi_core']])
    now.to_csv(DATA / 'cpi_nowcast_score.csv')
    s = now.dropna(subset=['cpi_all'])
    mae = lambda x, y: (x - y).abs().mean() * 100
    print(f'\n(2) Pre-release CPI nowcast, {now.index[0]:%Y-%m} to {now.index[-1]:%Y-%m} ({len(now)} months; {len(s)} also scored for DMS), MAE bp:')
    print(f'    bottom-up   headline {mae(now["head"], now.pub_head):.1f}  core {mae(now["core"], now.pub_core):.1f}   (same months as DMS: {mae(s["head"], s.pub_head):.1f} / {mae(s["core"], s.pub_core):.1f})')
    print(f'    DMS         headline {mae(s.cpi_all, s.pub_head):.1f}  core {mae(s.cpi_core, s.pub_core):.1f}')
    n = len(now)
    h1, h2 = now.iloc[:n // 2], now.iloc[n // 2:]
    print(f'    bottom-up by half (head/core): {mae(h1["head"], h1.pub_head):.1f}/{mae(h1["core"], h1.pub_core):.1f} then {mae(h2["head"], h2.pub_head):.1f}/{mae(h2["core"], h2.pub_core):.1f}')


if __name__ == '__main__':
    main()
