# Vintage archive

Every raw input value the inflation nowcast reads, recorded when first seen and each time it changed (forward from the first file).

`deltas/<as_of>_<UTC write time>.parquet`: source, series, date (observation), value, prior_value (NULL = new observation), seen_at (when retrieved), as_of (run date).
A row with value NULL marks a date that disappeared from a series. The state on a day is the newest row per (source, series, date) among the files up to that day.
Written by `scripts/19_archive_vintages.py`; read with `scripts/vintage_asof.py` or DuckDB: `SELECT * FROM read_parquet('deltas/*.parquet')`.
Sources: bea:<table> (BEA bulk NIPA, series code), bls_cpi, bls_ppi (BLS flat files, series id), fred (FRED CSV market series), cleveland (below).

Cleveland Fed nowcasts (source `cleveland`, series `<kind>:<measure>:<target month>`, kind nowcast or actual, date = the nowcast date or the release date): Federal Reserve Bank of Cleveland,
Inflation Nowcasting, https://doi.org/10.26509/frbc-inflationnowcast, licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Cleveland Fed calculations based on data from BLS, BEA,
EIA, Financial Times and Haver Analytics. Recorded here as published; no endorsement by the Cleveland Fed is implied.
