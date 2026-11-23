# PCE crosswalk: provenance and validation

The crosswalk (`config/pce_leaf_map.csv`) maps each of the 220 PCE components ("leaves") to the BLS series that BEA uses to price
it. It is a starting point from one outside source and has been checked against two independent ones. It is not trusted on the
authority of any single source.

## Sources

| Role | Source | What it provides |
|---|---|---|
| Starting map | econvitals/replication, `measures/pce-tracking-estimate/inputs/pce_leaf_map.csv` (CC0 1.0) | 220 leaves, BEA codes, BLS source series, seasonal rule (`:bls`, `:none`, `:own`), blend and fill rules |
| Check 1 (BEA's own document) | BEA Table 2.4.4U-D, "Price Indexes for PCE: Source Data", Sept 30, 2026 edition (XLSX linked from bea.gov/help/faq/521) | BEA's stated price source and seasonal status for each line |
| Check 2 (data) | BEA's published price indexes (U20404) against the mapped BLS series | Whether the mapping reproduces BEA's own monthly changes |

## Checks and results (all reproducible; figures are checked in the scripts as `PAPER_*` constants)

1. **Coverage and completeness** (`02a_audit_crosswalk.py`, `02b_check_crosswalk.py`). All 220 BEA price and nominal codes and all BLS
   source series are in the ingested data. Signed leaf spending sums to total PCE (max gap 0.0001% since 2015).
2. **Fit to BEA's published prices** (`02b_check_crosswalk.py`, writes `data/crosswalk_fit.csv`). Over the last 36 published months,
   single-source leaves (not `:own`) have a median agreement of 100% (within 0.05 pp) with the mapped series; five leaves fit poorly.
3. **BEA source-list comparison** (`02c_check_bea_source_table.py`, writes `data/crosswalk_bea_check.csv`).
   All 220 map lines are in BEA's table. Of 169 single-CPI-source leaves, 152 name the same CPI item as BEA (the rest differ in wording
   only, e.g. "fabric" vs "fabrics") and 167 have a seasonal status consistent with BEA's (the other two are parent lines with no
   source in BEA's table).

## Changes made to the original map

- **Lines 283, 284 (land-line telephone):** seasonal rule `:none` -> `:own`. BEA lists them "SA by BEA" and BLS publishes no
  seasonally adjusted series for the item. The earlier poor fit (correlation 0.80, mean gap 0.41 pp) is consistent with the missing
  adjustment. To be confirmed once X-13 is applied.

## Flagged leaves examined and left unchanged

| Lines | Finding | Why unchanged |
|---|---|---|
| 163 (farm dwellings) | Poor historical fit to OER | BEA prices it from USDA and capital-stock data; only the latest unpublished months use CPI OER (BEA's text). The map's rule is right for the nowcast month; the fit test compares months BEA has already revised. |
| 156 (tenant-occupied homes, landlord durables) | BEA splits it into rent (157) and appliances (158) | Line 158 has no monthly data after 2001; keeping one leaf priced with rent is right. |
| 216, 301 (spectator sports, tax preparation) | Poor fit | BEA text: "judgmental trend". Treated through a five-year regression, as in the original map. |

## Not resolved

- **Photo items (130, 220, 221):** BEA still names a CPI series that BLS no longer publishes; they need a parent-item substitute.
  Not yet checked.
- **Net insurance lines (276-279):** BEA's table lists no source for them, so the sources in the map (PPI series; CPI all items for
  income loss) rest on the original map alone.
- **Blended / model / filled leaves (30):** BEA describes these in words; blend weights are fitted to BEA's history, not read from the
  table. They are tested only by the aggregate backtest.
- **`:own` leaves:** not testable until the X-13 step exists.

## Limits

BEA's table says which source is used, not how BEA treats it month by month (revisions, X-13 settings, judgmental adjustments). The
final check on the whole mapping is the real-time backtest against BEA's first prints.
