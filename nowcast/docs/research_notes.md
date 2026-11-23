# Research notes: what was tried and what was found

Working notes behind the design choices (written 2026-11-23). Numbers are mean absolute misses in basis points of a monthly percent change unless stated; the backtests are partly real-time (see the README).
For the crosswalk checks see crosswalk_validation.md; for third-party terms see third_party_terms.md.

Built: ingest, crosswalk + validation (docs/crosswalk_validation.md), translation with X-13, pre-CPI stage (gasoline only), DMS baseline, daily runner,
first-print backtest, pre-CPI fill/indicator evaluation.
First-print backtest, core PCE mean abs miss, 60 months Oct 2021-Sep 2026 (bp): pre_cpi 10.1, post_cpi 6.0, post_ppi 5.8, post_import 5.8; DMS 10.4 before CPI, 7.6 after.
In-sample vs revised, 36 months: pre_cpi 7.4, post_cpi 4.0, post_ppi 3.8, post_import 3.5. First print vs today's revised core differs by 5.4 bp on average. No first-print offset adopted.
Pre-CPI work (scripts 09-11): persistence-based fills help persistent housing leaves, but the default is now the single rule below. Software leaf (11% of pre-CPI error variance) is unpredictable from available data
(all rules RMSE 1.6-1.8%/month). Fuel indicators (jet fuel, Henry Hub, WTI) do not beat the fill (fuel oil does, but is 0.12% of PCE; not implemented). CPI proxies for
PPI-sourced leaves: only airline fares adopted (PROXIES in lib_translate; effect ~0.04 bp); health-care leaves are smooth, proxies add ~0.05 bp.
Bottom-up CPI (lib_cpi, 71 leaves, BLS relative importance): reconstructs published SA headline/core within 2.0/2.5 bp on average (floor: BLS seasonally adjusts
aggregates directly; error is random). Item-level nests DMS: with DMS's own rule (12-month mean per item) the bottom-up core CPI is 0.7 bp from DMS on average (headline 3.0 bp; PCE core 1.8).
Pre-release MAE over the last 60 months (script 17): CPI core DMS 8.9 / item mean12 8.5 / item persist 9.2; CPI headline DMS 10.4 / item mean12 9.8 / item persist 9.7; PCE core DMS 8.7 / mean12 8.4 /
persist 7.8; PCE headline DMS 9.9 / mean12 9.1 / persist 8.7 (vs revised). Over the last 34-36 months (calmer) DMS and item-level are level (CPI 6.5/7.2 vs 6.8/7.1). Item-level wins in the volatile
2021-24 half, ties or loses slightly in the calmer half. ONE item-level rule for CPI and PCE (script 18; criterion fixed in advance: mean of first/second-half MAE over four targets, ties within 1% to the simpler rule): `blend` = average of an item's
3-month and 12-month mean change (all items seasonally adjusted: BLS SA series, X-13 for the 13 CPI items and the `:own` PCE items without one). Scores: blend 8.50, persist.3 8.62, persist 8.74, mean12 8.94 (bp).
The choice among the top rules is weakly identified (10 rules tried; differences ~5%). Cost of unification: PCE core pre-CPI 8.3 vs 7.8 bp (vs revised) for the best PCE-only rule. In the calmer last 34 months DMS is better
for CPI (headline 6.5 vs 7.3, core 7.2 vs 8.1); over 60 months the item rule is better (CPI headline 9.0 vs 10.4, core 8.5 vs 8.9). Gasoline: DMS nowcast override in both. 'DMS + item adjustment' (anchored) is no better than the best item rule. The earlier statement that DMS should be used for pre-release
CPI was based on the 36-month window and is withdrawn.
Nowcast-improvement tests (scripts 13-16; adopt only if MAE falls in both halves of the 60-month sample; none passed): (a) stock prices for portfolio management
(leaf 268, 1.7% of PCE): help in 2021-24 (RMSE 1.16 -> 0.85) but hurt since the leaf calmed (0.33 -> 0.49+); a significance gate does not fix it; BEA changed the method Sep 2026.
(b) error-correction of pre-CPI core/headline PCE on unemployment changes, dollar, breakeven, stocks: all worse than none, except the breakeven change (better in the 2nd half, worse
in the 1st; watch it). (c) blending toward DMS (25%/50%): worse. (d) post-CPI correction using the CPI surprise: no gain. (e) theory-paired group corrections (labor slack -> services,
dollar/breakeven -> goods): no gain. Pre-CPI core error splits ~6 bp each goods and services ex-housing (housing 1.2 bp), nearly unpredictable (AR1 0.29 goods, 0.07 services).
Cross-sectional shrinkage of item forecasts toward group means cannot change aggregates (mean-preserving), so it was not run as an aggregate test.
Backtest inputs are only partly real-time (BEA detail tables are not in ALFRED); the vintage archive (archive/ locally, branch `data` on GitHub) records every input as first seen or revised from the first production run, so a true real-time record accumulates from then.
Not built: further pre-CPI models (software, owner-occupied housing from rent indexes), CPI first-print scoring (ALFRED CPIAUCSL/CPILFESL), a multi-month nowcast horizon.
Sources: crosswalk from econvitals/replication (CC0) checked against BEA Table 2.4.4U-D; method per Knotek-Zaman (DMS) and the Chicago Fed Flash PCE.
