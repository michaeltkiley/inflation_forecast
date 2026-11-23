# Inflation nowcast

Daily bottom-up nowcast of monthly PCE and CPI inflation, shown in the **Nowcast** tab of the Inflation Tracker page
(https://michaeltkiley.github.io/inflation_forecast/). BEA builds the PCE price index from about 220 components, almost all priced with a BLS index that is public before BEA publishes. This
project rebuilds that assembly: a component whose BLS source is out is translated into its PCE counterpart; a component not yet released is forecast; components are weighted by spending shares.
CPI is built the same way from 71 items. The Cleveland Fed's nowcast is shown beside ours. Method after Knotek and Zaman (Cleveland Fed) and the Chicago Fed's Flash PCE; the source map from each PCE
component to its BLS series was adapted from econvitals/replication (CC0) and checked against BEA's Table 2.4.4U-D (`docs/crosswalk_validation.md`).

Design follows gdpnow-replication: flat stage scripts, DuckDB working store, skip-if-done with `--force`, a durable vintage archive of every input on an orphan `data` branch.

## Layout
```
nowcast/
  scripts/   numbered stage scripts + lib_*.py (see "Stages")      site/      HTML, CSS and JS of the Nowcast tab (embedded into docs/index.html by scripts/08_build_dashboard.py)
  config/    pce_leaf_map.csv (220 PCE components -> BLS sources)     results/   backtest_first_print.csv (committed; read by the page)
  docs/      crosswalk_validation.md, third_party_terms.md, research_notes.md      tools/x13/  Census X-13ARIMA-SEATS binary (public domain)
docs/data/nowcast.json     written by the daily run; fetched by the page at load time
.github/workflows/nowcast.yml   the daily GitHub Actions run          nowcast/DEPLOY.md   steps to put it live
```
Not committed: `nowcast/data/` (working DuckDB, raw downloads, logs), `nowcast/archive/` (local vintage archive), `.env`.

## Stages (run from the repository root; `python nowcast/scripts/daily.py` runs them in order)
| Stage | What it does |
|---|---|
| `00_restore_history` | loads the nowcast run history (our own daily outputs) from the archive into an empty database (essential in CI) |
| `01a`-`01e` ingest | BEA PCE detail (bulk files), BLS CPI detail, PPI/import prices named in the crosswalk, FRED market series, BLS CPI relative importance |
| `07`, `20` ingest (optional) | BEA first prints from ALFRED; the Cleveland Fed benchmark (CC BY 4.0, see `docs/third_party_terms.md`) |
| `06_nowcast_daily` | translates released data, forecasts the rest, aggregates PCE and CPI, stores the run, reports what changed since the last run |
| `19_archive_vintages` | writes the day's new or revised input values and the run history to the archive |
| `21_build_site` | validates and writes `docs/data/nowcast.json` |
| `22_check_site` | tests the built page in headless Chromium (needs Playwright; skipped if absent) |
Analysis and evaluation scripts (`02`-`05`, `08`-`18`) are run by hand; `08_backtest_first_print.py` refreshes `results/backtest_first_print.csv` (about 90 seconds; rerun after model changes and commit it).

## Running locally
```
pip install -r nowcast/requirements.txt        # Python 3.12+
cp nowcast/.env.example nowcast/.env           # fill BLS_CONTACT (required) and FRED_API_KEY; the file is gitignored
python nowcast/scripts/daily.py                # about 4 minutes
python scripts/08_build_dashboard.py           # rebuild docs/index.html (the forecast pipeline's own stages must have run: scripts/00-07)
```

## Data storage and history
The working database holds only the current vintage of each input and is rebuilt every run. History lives in two places that must not be lost:
- **vintage archive** (`<archive>/deltas/*.parquet`): every observation as first seen and each time it changed (new, revised, removed). `python nowcast/scripts/vintage_asof.py --source bls_cpi --series CUSR0000SA0 --asof 2026-12-01` reads any past day.
- **run history** (`<archive>/runs/<date>/*.parquet`): our own daily nowcasts, the track record, which cannot be rebuilt from the inputs once the code changes.
Locally the archive is `nowcast/archive/`; in GitHub Actions it is the `data` branch (`NOWCAST_ARCHIVE`, managed by `nowcast/scripts/data_branch.sh`). Back it up.

## Credits and caveats
Federal data: BLS, BEA, EIA (via FRED), ALFRED. Cleveland Fed nowcasts: Federal Reserve Bank of Cleveland, "Inflation Nowcasting," https://doi.org/10.26509/frbc-inflationnowcast, CC BY 4.0. Econvitals and the Chicago Fed's
Flash PCE are linked from the page as related work only. The backtest is partly real-time (BEA's component detail is not archived by ALFRED); see the page and `docs/research_notes.md`.
Research estimates for information only; see the disclaimer on the page.
