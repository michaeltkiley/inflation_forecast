"""Simplified Knotek-Zaman 'Deterministic Model Switching' (DMS) baseline for the current month, as described in docs/research_review.docx:
  * core CPI and food CPI: 12-month trailing mean of their own monthly change;
  * gasoline CPI: NSA gasoline CPI change regressed (60-month window) on the monthly average of weekly retail gasoline with a lagged-residual
    (error-correction) term, then seasonally adjusted by subtracting the same-calendar-month average NSA-minus-SA gap of the last 3 years;
  * headline CPI: 24-month rolling regression of headline on core, food and gasoline (SA);
  * PCE: 24-month rolling bridges, core PCE on core CPI and headline PCE on headline CPI, using the CPI nowcast before CPI is released and the
    actual CPI after.
Simplifications vs the original (not exact replication): no daily-oil second stage (only needed for months beyond the current one), no PCE-food
shortcut, all components on % changes of SA indexes, constants in every regression. Inputs are the latest vintage in DuckDB."""
import numpy as np
import pandas as pd

from lib_common import connect
from lib_translate import mom

CORE_MA, FOOD_MA, GAS_WIN, HEAD_WIN, BRIDGE_WIN, SEAS_YEARS = 12, 12, 60, 24, 24, 3


def ols_fit(y, X):
    d = pd.concat([y.rename('y'), X], axis=1).dropna()
    A = np.column_stack([np.ones(len(d)), d[X.columns].values])
    b, *_ = np.linalg.lstsq(A, d.y.values, rcond=None)
    return b, d.index, d.y.values - A @ b


def predict(b, x):
    return float(b[0] + np.dot(b[1:], x))


class DMSData:
    def __init__(self):
        con = connect()
        cpi = con.execute("select series_id, date, value from cpi_data where vintage=(select max(vintage) from cpi_data) and series_id in "
                          "('CUSR0000SA0','CUSR0000SA0L1E','CUSR0000SAF1','CUSR0000SETB01','CUUR0000SETB01')").df()
        L = {k: g.set_index('date').value.sort_index() for k, g in cpi.groupby('series_id')}
        self.cpi_all, self.cpi_core, self.food = (mom(L[k]) for k in ['CUSR0000SA0', 'CUSR0000SA0L1E', 'CUSR0000SAF1'])
        self.gas_sa, self.gas_nsa = mom(L['CUSR0000SETB01']), mom(L['CUUR0000SETB01'])
        v = con.execute('select max(vintage) from bea_pce').fetchone()[0]
        b = con.execute("select series_code, date, value from bea_pce where vintage=? and series_code in ('DPCERG','DPCCRG')", [v]).df()
        b = b.drop_duplicates(['series_code', 'date']).pivot(index='date', columns='series_code', values='value')
        self.pce_all, self.pce_core = mom(b['DPCERG']), mom(b['DPCCRG'])
        w = con.execute("select date, value from market_data where series_id='GASREGW' and vintage=(select max(vintage) from market_data)").df()
        gas_m = w.set_index('date').value.resample('MS').mean()
        self.retail_gas = mom(gas_m)                                  # last month may be a partial-month average


def nowcast(D, month):
    """DMS nowcasts for `month` using history through the prior month. Returns dict of pre-CPI nowcasts and, where month's CPI is
    published, post-CPI PCE bridges."""
    month = pd.Timestamp(month)
    through = month - pd.DateOffset(months=1)
    h = lambda s: s.loc[:through]
    core = float(h(D.cpi_core).dropna().iloc[-CORE_MA:].mean())
    food = float(h(D.food).dropna().iloc[-FOOD_MA:].mean())
    # gasoline: stage 1 (level fit) -> residuals; stage 2 adds the lagged residual
    y, x = h(D.gas_nsa).iloc[-GAS_WIN:], D.retail_gas.reindex(h(D.gas_nsa).iloc[-GAS_WIN:].index)
    b1, idx, e = ols_fit(y, x.to_frame('x'))
    res = pd.Series(e, index=idx)
    X2 = pd.DataFrame({'x': x, 'e_lag': res.shift(1).reindex(x.index)})
    b2, _, _ = ols_fit(y, X2)
    e_last = float(res.get(through, 0.0))
    gas_nsa = predict(b2, [D.retail_gas.get(month, np.nan), e_last])
    gap = (D.gas_nsa - D.gas_sa).dropna()
    gap = gap[(gap.index.month == month.month) & (gap.index <= through) & (gap.index > through - pd.DateOffset(years=SEAS_YEARS))]
    gas_sa = gas_nsa - (float(gap.mean()) if len(gap) else 0.0)
    # headline CPI from components
    W = h(pd.DataFrame({'core': D.cpi_core, 'food': D.food, 'gas': D.gas_sa}).assign(y=D.cpi_all).dropna()).iloc[-HEAD_WIN:]
    bh, _, _ = ols_fit(W.y, W[['core', 'food', 'gas']])
    cpi_all = predict(bh, [core, food, gas_sa])
    out = dict(cpi_core=core, cpi_all=cpi_all, gas_sa=gas_sa)
    for name, pce, cpi_pre, cpi_act in [('core', D.pce_core, core, D.cpi_core), ('all', D.pce_all, cpi_all, D.cpi_all)]:
        B = h(pd.DataFrame({'x': cpi_act, 'y': pce}).dropna()).iloc[-BRIDGE_WIN:]
        bb, _, _ = ols_fit(B.y, B[['x']])
        out[f'pce_{name}_pre'] = predict(bb, [cpi_pre])
        act = cpi_act.get(month, np.nan)
        out[f'pce_{name}_post'] = predict(bb, [act]) if pd.notna(act) else np.nan
    return out


GAS_LINE = 115       # PCE 'Gasoline and other motor fuel' (CPI motor fuel)


def pre_cpi_overrides(D, month):
    """Forecasts that replace the 12-month-average fill for leaves with a high-frequency indicator (before CPI is released)."""
    return {GAS_LINE: nowcast(D, month)['gas_sa']}
