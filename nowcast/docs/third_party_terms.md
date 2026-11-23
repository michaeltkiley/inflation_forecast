# Third-party data and work: terms checked for a public release

Checked 2026-11-23 from the pages named below. Terms can change; re-check before each public release. This is a working record, not legal advice.

## Data the nowcast uses or shows

| Source | What we use | Terms found | Requirement for the dashboard |
|---|---|---|---|
| BLS (CPI, PPI, import prices, unemployment, relative importance) | Published series | bls.gov/opub/copyright-information.htm: everything BLS publishes is in the public domain; free to use without permission; BLS asks that it be cited as the source | Credit "U.S. Bureau of Labor Statistics". No implication of BLS endorsement |
| BEA (PCE price indexes and spending, Table 2.4.4U-D source list) | Published tables | bea.gov FAQ 145/147: content is public domain unless labelled otherwise; credit requested ("Source: U.S. Bureau of Economic Analysis") | Credit BEA. No implication of endorsement |
| EIA (gasoline, crude, natural gas, jet fuel prices via FRED) | Published series | eia.gov/about/copyrights_reuse.php: U.S. government publications are in the public domain; use and redistribution allowed | Credit EIA / FRED |
| FRED (Federal Reserve Bank of St. Louis) series: unemployment rate, broad dollar index, 10y breakeven, first prints via ALFRED | Published series | Underlying data are U.S. government or Federal Reserve data; fetched through FRED | Credit FRED |
| S&P 500 and Nasdaq Composite (via FRED) | Evaluation scripts only (13, 14); not in any adopted model | FRED's S&P 500 notes cite a licensing agreement with S&P Dow Jones Indices limiting history; redistribution rights not clear | **Not redistributed**: excluded from the public vintage archive (`NO_REDISTRIBUTE` in scripts/19_archive_vintages.py) and never displayed |

## Cleveland Fed Inflation Nowcasting (benchmark shown on the dashboard)

Evidence gathered from clevelandfed.org/indicators-and-data/inflation-nowcasting and clevelandfed.org/privacy:
- Each of the three nowcast charts (monthly, quarterly, year-over-year) carries `data-chart-license="https://creativecommons.org/licenses/by/4.0/"` (CC BY 4.0) and
  `data-sources="Federal Reserve Bank of Cleveland calculations based on data from Bureau of Labor Statistics, Bureau of Economic Analysis, Energy Information Administration, Financial Times, and Haver Analytics"`.
- Suggested citation on the page: "Inflation Nowcasting." Federal Reserve Bank of Cleveland. https://doi.org/10.26509/frbc-inflationnowcast.
- Site terms ("Privacy and Terms of Use"): reproduction of Cleveland Fed publications is authorized for noncommercial, personal or educational use with credit; third-party copyrighted material needs permission from its owner;
  the Bank may change the terms without notice.
- Not found: any statement about automated access, rate limits, or a documented API. The JSON files the charts load carry no license field of their own.

Reading: the nowcast values are Cleveland Fed calculations under a stated CC BY 4.0 license, and the dashboard is noncommercial. Conditions we follow: show the values as published (any statistic we compute from them is
labelled as ours), give the attribution and license link on the page, do not imply Cleveland Fed endorsement, do not republish Haver Analytics or Financial Times data (we never fetch it), fetch gently (once a day, an
identifying generic User-Agent without personal details). Risk that remains: the endpoint is undocumented and could change, and the terms could change without notice; the dashboard must build without the Cleveland panel if the fetch fails.

Required attribution text on the page:
"Cleveland Fed nowcasts: Federal Reserve Bank of Cleveland, Inflation Nowcasting, https://doi.org/10.26509/frbc-inflationnowcast, licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Cleveland Fed calculations
based on data from BLS, BEA, EIA, Financial Times and Haver Analytics. Shown as published; accuracy statistics are our own."

## Related work by others (links only; no numbers shown)

- Econvitals (econvitals.org; code and data github.com/econvitals/replication, CC0 1.0): a PCE tracking estimate built from BEA's source-data map. Linked only. Our crosswalk (`config/pce_leaf_map.csv`) was
  copied from its `pce_leaf_map.csv`, then checked against BEA Table 2.4.4U-D and changed in two places (docs/crosswalk_validation.md); credited in Methods although CC0 does not require it. None of its figures are displayed.
- Chicago Fed "Flash PCE" (Chicago Fed Letter No. 529, September 2026, https://www.chicagofed.org/publications/chicago-fed-letter/2026/529): linked only. No regularly updated data page was found, so no Flash PCE numbers
  are shown or estimated.
