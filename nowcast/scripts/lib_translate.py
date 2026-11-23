"""Translate BLS price changes into monthly PCE component (leaf) price changes, and aggregate them.

Per leaf (config/pce_leaf_map.csv), for a target month:
  1. translate: the month's change in its BLS source (or a weighted blend of several; blend weights fitted by non-negative
     least squares to BEA's own published changes unless the map gives weights). Sources marked `:own` are unadjusted series
     that BEA seasonally adjusts itself: adjusted here with X-13 and an implied seasonal factor added (average gap to BEA's
     published change, same calendar month, last 5 years). `damped` leaves (BEA 'judgmental trend') are regressed on their source
     over 5 years; leaves whose CPI item BLS no longer publishes use `gap_proxy` the same way.
  2. fill: a leaf whose source is not released, or that has none, gets its own average published change of the last 12 months
     (constant leaves their constant).
  3. aggregate: leaves weighted by prior-month nominal spending shares (U20405).
All inputs are the latest vintage in DuckDB. Seasonal factors use the full sample, so a backtest of past months has some look-ahead.
"""
import os
import warnings

import numpy as np
import pandas as pd
from scipy.optimize import nnls
from statsmodels.tools.sm_exceptions import X13Error
from statsmodels.tsa.x13 import x13_arima_analysis

from lib_common import ROOT, connect

X13_DIR = os.environ.get('X13PATH', str(ROOT / 'tools' / 'x13'))
SA_START = '2008-01-01'
FILL_MONTHS, IMPLIED_YEARS, FIT_MIN_OBS = 12, 5, 18
def persist_fill(h, cut=0.5):
    """3-month mean for persistent leaves (AR(1) of the last 60 observations above `cut`), else the 12-month mean."""
    r = h.iloc[-60:]
    return h.iloc[-3:].mean() if len(r) >= 36 and r.autocorr(1) > cut else h.iloc[-12:].mean()


def persist_fill_med(h, n=3, cut=0.5):
    """Like persist_fill but the median of the last n observations for persistent leaves (robust to a one-off spike such as the post-shutdown
    shelter catch-up in April 2026)."""
    r = h.iloc[-60:]
    return h.iloc[-n:].median() if len(r) >= 36 and r.autocorr(1) > cut else h.iloc[-12:].mean()


FILLS = {                                                              # fill rules for a leaf with no released source
    'mean12': lambda h: h.iloc[-12:].mean(), 'mean6': lambda h: h.iloc[-6:].mean(), 'mean3': lambda h: h.iloc[-3:].mean(),
    'mean24': lambda h: h.iloc[-24:].mean(), 'ewm6': lambda h: h.ewm(halflife=6).mean().iloc[-1],
    'persist': persist_fill, 'persist.7': lambda h: persist_fill(h, 0.7), 'persist.3': lambda h: persist_fill(h, 0.3),
    'persist_med3': persist_fill_med, 'persist_med5': lambda h: persist_fill_med(h, 5),
    'blend': lambda h: 0.5 * h.iloc[-12:].mean() + 0.5 * h.iloc[-3:].mean()}
PROXIES = {207: 'CUSR0000SETG01'}      # PPI-sourced leaf -> CPI series that stands in for it after the CPI is out, before the PPI (11_eval_cpi_proxies.py)
HEADLINE_LINE, CORE_LINE = 1, 374               # U20404 lines: PCE, PCE excluding food and energy
STAGES = {'pre_cpi': set(), 'post_cpi': {'cpi'}, 'post_ppi': {'cpi', 'ppi'}, 'post_import': {'cpi', 'ppi', 'import'}}


def mom(level):
    """Percent change on the month; NaN across gaps."""
    s = level.dropna()
    full = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq='MS'))
    return full.pct_change(fill_method=None) * 100


def x13_adjust(level):
    """X-13 seasonal adjustment. Interior gaps (e.g. no October 2025 CPI) are filled log-linearly for the adjustment only and
    blanked again afterwards, so no change is measured across them."""
    s = level.loc[SA_START:].dropna()
    full = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq='MS'))
    filled = np.exp(np.log(full).interpolate())
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        sa = x13_arima_analysis(filled, x12path=X13_DIR, prefer_x13=True, outlier=True, print_stdout=False).seasadj
    return sa.where(full.notna())


class Inputs:
    """Everything the translation needs, loaded once from DuckDB."""

    def __init__(self):
        con = connect()
        m = pd.read_csv(ROOT / 'config' / 'pce_leaf_map.csv', dtype=str)
        m['line'] = m.line.astype(int)
        for c in ['sign', 'constant']:
            m[c] = pd.to_numeric(m[c])
        for c in ['damped', 'housing', 'services', 'used_vehicles', 'market_based_excluded']:
            m[c] = m[c].fillna('0').astype(int)
        m['parts'] = m.series.fillna('').map(lambda s: [tuple(x.split(':')) for x in s.split(';') if x])
        self.leaves = m.set_index('line')
        v = con.execute('select max(vintage) from bea_pce').fetchone()[0]
        bea = con.execute("select series_code, date, value from bea_pce where vintage=? and table_id in ('U20404','U20405')", [v]).df()
        bea = bea.drop_duplicates(['series_code', 'date']).pivot(index='date', columns='series_code', values='value')
        self.prices = bea[m.bea_price_code.values]
        self.prices.columns = m.line.values
        self.pub_mom = self.prices.apply(mom)                             # BEA's published monthly changes
        self.nominal = bea[m.bea_nominal_code.values]
        self.nominal.columns = m.line.values
        self.total_nominal = bea['DPCERC']
        self.headline_mom = mom(bea['DPCERG'])
        self.core_mom = mom(bea['DPCCRG'])
        lv = con.execute("select series_id, date, value from cpi_data where vintage=(select max(vintage) from cpi_data) "
                         "union all select series_id, date, value from ppi_data where vintage=(select max(vintage) from ppi_data)").df()
        self.levels = {k: g.set_index('date').value.sort_index() for k, g in lv.groupby('series_id')}
        extra = [g for g in m.gap_proxy.dropna().unique() if g not in self.levels]
        if extra:
            raise RuntimeError(f'gap_proxy series not ingested: {extra}')
        self._src = {}
        self.x13_failed = []                                              # `own` series X-13 cannot adjust: used unadjusted

    def source_mom(self, sid, rule):
        """Monthly % change of a BLS source; `own` series are X-13 adjusted first."""
        if (sid, rule) not in self._src:
            lv = self.levels.get(sid)
            if lv is not None and len(lv) >= 14 and rule == 'own':
                try:
                    lv = x13_adjust(lv)
                except X13Error:
                    self.x13_failed.append(sid)
            self._src[(sid, rule)] = None if lv is None or len(lv) < 14 else mom(lv)
        return self._src[(sid, rule)]


def nnls_weights(y, X):
    d = pd.concat([y.rename('y'), X], axis=1).dropna()
    if len(d) < FIT_MIN_OBS:
        return np.repeat(1 / X.shape[1], X.shape[1])
    b, _ = nnls(d[X.columns].values, d.y.values)
    return b / b.sum() if b.sum() > 0 else np.repeat(1 / X.shape[1], X.shape[1])


def translated(inp, line, through):
    """The leaf's monthly change implied by its source(s), for every month (None if not a source-based leaf)."""
    leaf = inp.leaves.loc[line]
    parts = [inp.source_mom(s, r) for s, r in leaf.parts]
    if leaf.kind in ('cpi', 'ppi'):
        return parts[0] if parts else None
    if leaf.kind != 'composite':
        return None
    have = [(i, p) for i, p in enumerate(parts) if p is not None]
    if not have:
        return None
    X = pd.DataFrame({i: p for i, p in have})
    if leaf.weights == 'fit':
        w = nnls_weights(inp.pub_mom[line].loc[pd.Timestamp(leaf.fit_start):through], X)
    else:
        w = np.array([float(x) for x in leaf.weights.split(';')])[[i for i, _ in have]]
    ok = X.notna().values
    den = (ok * w).sum(axis=1)                                            # renormalise over parts published that month
    return pd.Series(np.where(den > 0, np.nansum(X.values * w, axis=1) / np.where(den > 0, den, 1), np.nan), index=X.index)


def regress_on(y, x, month, through, max_slope):
    """BEA's leaf regressed on a related series over the last 5 years, read off at `month`."""
    if month not in x.index or pd.isna(x[month]):
        return None
    d = pd.concat([y.rename('y'), x.rename('x')], axis=1).dropna()
    d = d[(d.index <= through) & (d.index > through - pd.DateOffset(years=5))]
    if len(d) < 24 or d.x.std() == 0:
        return None
    b = min(max(np.cov(d.x, d.y)[0, 1] / d.x.var(), 0.0), max_slope)
    return float(d.y.mean() + b * (x[month] - d.x.mean()))


def implied_factor(inp, line, raw, month, through):
    gap = (inp.pub_mom[line] - raw).dropna()
    gap = gap[(gap.index <= through) & (gap.index > through - pd.DateOffset(years=IMPLIED_YEARS))]
    same = gap[gap.index.month == month.month]
    return float(same.mean()) if len(same) >= 2 else (float(gap.mean()) if len(gap) else 0.0)


def translate_month(inp, month, released, overrides=None, fill='blend'):
    """One row per leaf: mom, prior-month spending share (% of PCE), status ('released', 'forecast' or 'filled').
    `overrides` {line: value} replaces the fill of a not-yet-released leaf with a forecast (status 'forecast')."""
    month = pd.Timestamp(month)
    through = month - pd.DateOffset(months=1)                             # newest BEA month usable
    nom_month = inp.total_nominal.dropna().loc[:through].index.max()      # newest spending shares published (month t-1, or older)
    rows = []
    for line, leaf in inp.leaves.iterrows():
        val, status = np.nan, 'filled'
        raw = translated(inp, line, through) if leaf.release in released else None
        if raw is not None and month in raw.index and pd.notna(raw[month]):
            if leaf.damped:
                val = regress_on(inp.pub_mom[line], raw, month, through, 1.0)
            if pd.isna(val):
                val = raw[month] + (implied_factor(inp, line, raw, month, through) if any(r == 'own' for _, r in leaf.parts) else 0.0)
            status = 'released'
        elif leaf.release in released and pd.notna(leaf.gap_proxy):       # BLS stopped publishing the item: parent stands in
            val = regress_on(inp.pub_mom[line], mom(inp.levels[leaf.gap_proxy]), month, through, 1.5)
            status = 'released' if val is not None else 'filled'
        if status == 'filled' and line in PROXIES and 'cpi' in released:
            val = regress_on(inp.pub_mom[line], mom(inp.levels[PROXIES[line]]), month, through, 1.5)
            status = 'forecast' if val is not None else 'filled'
        if status == 'filled' or val is None or pd.isna(val):
            status = 'filled'
            hist = inp.pub_mom[line].loc[:through].dropna()
            val = float(leaf.constant) if leaf.kind == 'constant' else (float(FILLS[fill](hist)) if len(hist) else 0.0)
            if overrides and line in overrides:
                val, status = overrides[line], 'forecast'
        share = leaf.sign * inp.nominal.at[nom_month, line] / inp.total_nominal[nom_month] * 100
        rows.append(dict(line=line, mom=val, share=0.0 if pd.isna(share) else share, status=status))
    return pd.DataFrame(rows).set_index('line').join(inp.leaves[['group', 'housing', 'services', 'used_vehicles', 'market_based_excluded']])


def aggregate(d):
    """Headline and core PCE price change (% on the month) from the leaves."""
    avg = lambda mask: float((d.loc[mask, 'share'] / d.loc[mask, 'share'].sum() * d.loc[mask, 'mom']).sum())
    core = d.group == 'core'
    return dict(overall=float((d.share / 100 * d.mom).sum()), core=avg(core), core_ex_housing=avg(core & (d.housing == 0)),
                core_services_ex_housing=avg(core & (d.housing == 0) & (d.services == 1)),
                known_share_core=float(d.loc[core & (d.status == 'released'), 'share'].sum() / d.loc[core, 'share'].sum() * 100))
