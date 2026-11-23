# config/

`pce_leaf_map.csv` — the 220 PCE components ("leaves") whose signed spending sums to total PCE, with each leaf's BEA line
and price/nominal codes and its BLS source series. Copied unmodified from econvitals/replication
(measures/pce-tracking-estimate/inputs/pce_leaf_map.csv; CC0 1.0), which derives it from BEA's Table 2.4.4U-D
"Price Indexes for PCE: Source Data" (Sept 30, 2026 edition). Source-series suffix: `:bls` = BLS's own seasonally
adjusted series; `:none` = used as published; `:own` = unadjusted series that BEA seasonally adjusts itself (needs X-13).
Extra columns: `kind` (cpi/ppi/nonmarket/composite/model/constant), `release` (cpi/ppi/import/none), `weights`
(`fit` = blend weights fitted by NNLS to BEA's history), group/flag columns (core/food/energy, housing, services, used vehicles).

## Changes from the econvitals original
- Lines 283, 284 (land-line telephone, local / long distance): seasonal rule `:none` -> `:own`. BEA's Table 2.4.4U-D lists
  "CPI Land-line telephone services" as "SA by BEA" and BLS publishes no seasonally adjusted series for it (CUUR0000SEED04
  is NSA), so BEA adjusts it itself. The original `:none` left the seasonal pattern in (fit vs BEA: corr 0.80, mean gap 0.41 pp).
  To be confirmed after the X-13 step (expect the fit to improve).
