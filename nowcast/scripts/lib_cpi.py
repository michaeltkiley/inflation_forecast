"""Bottom-up CPI-U: leaves of the BLS expenditure hierarchy (deepest items at level <= 3, ~125 of them), weighted by BLS relative importance
(December of year Y, table cpi_weights) for the months of year Y+1, with weights carried forward each month by relative price change
(w_t = w_{t-1} * (1 + pi_t/100)). Each leaf uses its seasonally adjusted series where BLS publishes one, else the unadjusted series.
Food = food at home + food away; energy = motor fuel + household energy; core = all other leaves. Leaves with no series ('unsampled') are
dropped and the rest renormalised. A leaf with no change for a month (e.g. no October 2025 CPI) is left out of that month and weights renormalised.
Nowcast: each leaf's change from the `persist` fill rule on its own history (lib_translate), motor fuel from the DMS gasoline nowcast."""
import numpy as np
import pandas as pd

from lib_common import connect
from statsmodels.tools.sm_exceptions import X13Error

from lib_translate import FILLS, mom, x13_adjust

FOOD = {'Food at home', 'Food away from home'}
ENERGY = {'Motor fuel', 'Household energy'}


class CPI:
    def __init__(self):
        con = connect()
        self.w = con.execute('select * from cpi_weights order by year, seq').df()
        cs = con.execute('select series_id, item_name, seasonal from cpi_series').df()
        cs['n'] = cs.item_name.str.lower().str.strip()
        self.sa = cs[cs.seasonal == 'S'].drop_duplicates('n').set_index('n').series_id
        self.nsa = cs[cs.seasonal == 'U'].drop_duplicates('n').set_index('n').series_id
        lv = con.execute('select series_id, date, value from cpi_data where vintage=(select max(vintage) from cpi_data)').df()
        self.levels = {k: g.set_index('date').value.sort_index() for k, g in lv.groupby('series_id')}
        self.mom = {}
        self._leaves = {}
        self.head = mom(self.levels['CUSR0000SA0'])
        self.core = mom(self.levels['CUSR0000SA0L1E'])

    def leaves(self, year):
        """DataFrame (index item_name): ri (renormalised to 100), series, group — the leaf partition for weights of December `year`."""
        if year not in self._leaves:
            d = self.w[self.w.year == year].reset_index(drop=True)
            nxt = d.lvl.shift(-1).fillna(0)
            leaf = d[((d.lvl == 3) | (nxt <= d.lvl)) & d.lvl.between(1, 3)].copy()
            n = leaf.item_name.str.lower().str.strip()
            leaf['series'] = n.map(self.sa).fillna(n.map(self.nsa))
            leaf = leaf.dropna(subset=['series']).set_index('item_name')
            leaf['ri'] = leaf.ri / leaf.ri.sum() * 100
            leaf['group'] = ['food' if i in FOOD else 'energy' if i in ENERGY else 'core' for i in leaf.index]
            self._leaves[year] = leaf[['ri', 'series', 'group']]
        return self._leaves[year]

    def leaf_mom(self, sid):
        if sid not in self.mom:
            lv = self.levels[sid]
            if sid.startswith('CUUR'):                               # no BLS seasonally adjusted series: adjust with X-13 as for PCE (unadjusted if X-13 fails)
                try:
                    lv = x13_adjust(lv)
                except X13Error:
                    pass
            self.mom[sid] = mom(lv)
        return self.mom[sid]

    def aggregate(self, w, pi):
        """Headline and core % change from weights w and changes pi (Series by item; NaN items left out and renormalised)."""
        ok = pi.notna()
        g = w.group[ok]
        agg = lambda mask: float((w.ri[ok][mask] * pi[ok][mask]).sum() / w.ri[ok][mask].sum()) if mask.any() else np.nan
        return dict(head=agg(g.notna()), core=agg(g == 'core'), food=agg(g == 'food'), energy=agg(g == 'energy'), n_missing=int((~ok).sum()))

    def run(self, start='2023-01-01', end=None, forecast=None):
        """Month by month from `start`. forecast None: reconstruct from actual changes. forecast = {leaf name: value} function(month, leaf, pi_hist) -> value:
        nowcast from information through t-1. Returns DataFrame indexed by month: head, core, food, energy, n_missing, weights evolved with ACTUAL changes."""
        end = end or self.head.dropna().index.max()
        months = pd.date_range(start, end, freq='MS')
        out = {}
        state = None
        for m in months:
            y = m.year - 1                                            # December y weights drive the months of y+1
            if state is None or m.month == 1:
                lf = self.leaves(y)
                state = lf.copy()
            pi_act = pd.Series({i: self.leaf_mom(s).get(m, np.nan) for i, s in state.series.items()})
            pi = pi_act if forecast is None else pd.Series({i: forecast(m, i, self.leaf_mom(state.series[i]).loc[:m - pd.DateOffset(months=1)].dropna()) for i in state.index})
            out[m] = self.aggregate(state, pi)
            ok = pi_act.notna()
            state.loc[ok, 'ri'] = state.ri[ok] * (1 + pi_act[ok] / 100)    # evolve with actual changes
            state['ri'] = state.ri / state.ri.sum() * 100 if ok.any() else state.ri
        return pd.DataFrame(out).T


def persist_nowcast(gas_by_month, fill='blend'):
    """Forecast function for CPI.run: the same fill rule as the PCE items (lib_translate.FILLS); motor fuel replaced by the DMS gasoline nowcast (SA % change)."""
    def f(m, leaf, hist):
        if leaf == 'Motor fuel':
            return gas_by_month[m]
        return float(FILLS[fill](hist)) if len(hist) else 0.0
    return f
