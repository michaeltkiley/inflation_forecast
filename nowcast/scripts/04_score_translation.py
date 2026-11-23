#!/usr/bin/env python3
"""Score the translation (lib_translate) against BEA's published monthly PCE changes over the last N BEA months, for each release
stage (post_cpi, post_ppi, post_import). Reports mean absolute miss in basis points of a monthly change, for headline and core, plus the
mean signed miss (bias). BEA's numbers are the latest vintage (not first prints), and seasonal factors use the full sample, so this
is an in-sample check of the accounting, not a real-time backtest. Writes data/translation_score.csv.
PAPER_* are econvitals' reported mean core misses vs BEA's current history (README, 36 months; not independently verified).
Usage: python scripts/04_score_translation.py [--months 36]"""
import argparse

import pandas as pd

from lib_common import DATA
from lib_dms import DMSData, pre_cpi_overrides
from lib_translate import STAGES, Inputs, aggregate, translate_month

PAPER_CORE_MISS_BP = {'post_cpi': 4.0, 'post_ppi': 3.6, 'post_import': 3.2}      # their X-13 run; before their 1.4 bp first-print offset


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=36)
    a = ap.parse_args()
    inp, D = Inputs(), DMSData()
    last_bea = inp.headline_mom.dropna().index.max()
    months = pd.date_range(end=last_bea, periods=a.months, freq='MS')
    rows = []
    for m in months:
        for stage, rel in STAGES.items():
            r = aggregate(translate_month(inp, m, rel, pre_cpi_overrides(D, m) if stage == 'pre_cpi' else None))
            rows.append(dict(month=m, stage=stage, **r, bea_overall=inp.headline_mom[m], bea_core=inp.core_mom[m]))
    d = pd.DataFrame(rows)
    d['miss_overall_bp'] = (d.overall - d.bea_overall) * 100
    d['miss_core_bp'] = (d.core - d.bea_core) * 100
    d.to_csv(DATA / 'translation_score.csv', index=False)
    g = d.groupby('stage', sort=False)
    out = pd.DataFrame({'known_share_core_%': g.known_share_core.mean(), 'MAE_core_bp': g.miss_core_bp.apply(lambda x: x.abs().mean()),
                        'bias_core_bp': g.miss_core_bp.mean(), 'MAE_overall_bp': g.miss_overall_bp.apply(lambda x: x.abs().mean()),
                        'bias_overall_bp': g.miss_overall_bp.mean(), 'PAPER_core_MAE_bp': pd.Series(PAPER_CORE_MISS_BP)})
    print(f'{months[0]:%Y-%m} to {months[-1]:%Y-%m}, {a.months} months')
    print(out.round(2).to_string())
    print('\nLargest core misses (post_import):')
    print(d[d.stage == 'post_import'].reindex(d[d.stage == 'post_import'].miss_core_bp.abs().sort_values(ascending=False).index)
          .head(6)[['month', 'core', 'bea_core', 'miss_core_bp']].round(3).to_string(index=False))
    if inp.x13_failed:
        print('\nX-13 could not adjust (used unadjusted):', ', '.join(sorted(set(inp.x13_failed))))


if __name__ == '__main__':
    main()
