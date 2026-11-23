# Putting the Nowcast tab live

Everything is prepared on a local branch (`nowcast`, in the worktree `~/inflation_forecast-nowcast`) and a one-line branch for the main site (`nowcast-card`, worktree `~/michaeltkiley.github.io-nowcast`).
Nothing has been committed or pushed. `gh` on this machine is logged in as `michaeltkiley` with `repo` and `workflow` scopes, so no further login is needed. Never paste keys into chat.

## What you do on GitHub (about 10 minutes, repository `michaeltkiley/inflation_forecast`)

1. **Rotate the FRED key first.** The current one was printed once in an error message during development. fred.stlouisfed.org > My Account > API Keys > request a new key; then update it wherever it is used
   (gdpnow-replication's repository secret, `~/gdpnow-replication`'s and `nowcast/.env`'s local copies).
2. **Add two repository secrets**: Settings > Secrets and variables > Actions > New repository secret.
   - `BLS_CONTACT`: the contact string BLS asks for in the User-Agent of automated downloads (an email address or URL you are happy for BLS to see). Same value as in gdpnow-replication.
   - `FRED_API_KEY`: the new key.
3. **Check three settings; no change is expected** (the existing forecast workflow already pushes to `main`):
   - Settings > Pages: source is "Deploy from a branch", branch `main`, folder `/docs`.
   - Settings > Branches (or Rules > Rulesets): if `main` is protected, `github-actions[bot]` must be allowed to push to it, and nothing may block creating or pushing a branch named `data`.
   - Settings > Actions > General: actions from GitHub (checkout, setup-python) are allowed.
4. **Tell me to push.** I will commit on the `nowcast` branch, push that branch (not `main`) and open a pull request, and do the same for the one-line card change in `michaeltkiley.github.io`.
5. **Review and merge the pull request** (Files changed: `nowcast/` is new; `docs/index.html`, `scripts/dashboard_template.html` and `scripts/08_build_dashboard.py` hold the tab and layout changes; `.github/workflows/nowcast.yml` is the daily run;
   `.gitignore` gets two lines, including `!docs/data/`, without which the JSON would be ignored).
6. **Run the workflow once**: Actions > "Nowcast daily" > Run workflow (branch `main`). It takes about 5 to 10 minutes. It should finish green, add a commit "Nowcast YYYY-MM-DD" that changes `docs/data/nowcast.json`, and create the
   `data` branch (with `deltas/` and `runs/`). If it fails, the log names the stage; the daily emails on failure.
7. **Check the page** a minute or two later: https://michaeltkiley.github.io/inflation_forecast/ . The Nowcast tab should show numbers and charts; the Forecast tab should be unchanged; `#nowcast` and `#forecast` links should open the right tab.
8. **Merge the main-site card pull request** once the page is live.
9. **Turn off the local timer** so two runners do not both produce nowcasts: `systemctl --user disable --now inflation-nowcast.timer`. Keep `~/inflation-nowcast` until you are comfortable; its archive is not needed
   (the real-time record on GitHub starts with its first run).

## Afterwards
- The workflow runs weekdays at 22:30 UTC. The forecast workflow (`update.yml`) is untouched; it rebuilds `docs/index.html` from the template as before, and the nowcast tab fetches its data separately, so the two never conflict.
- Refresh the backtest table when the model changes: `python nowcast/scripts/08_backtest_first_print.py` (needs `FRED_API_KEY` in `nowcast/.env`), then commit `nowcast/results/backtest_first_print.csv`.
- Re-check the Cleveland Fed's terms before each public release or every quarter (`nowcast/docs/third_party_terms.md`).
- Back up the `data` branch: it holds the real-time vintage archive and the track record, neither of which can be rebuilt.

## Known items
- The workflow runs on Python 3.12; development used 3.14. The first CI run is the real test; use "Run workflow" and fix any version difference in a small pull request.
- At a 390px-wide screen the Forecast tab is about 24px wider than the screen. This is in the original page (its "Actual / Persistence / Expectations" legend row does not wrap) and was left unchanged; adding `flex-wrap: wrap`
  to `.legend-group` fixes it.
- `docs/preview.png` (the link-preview image) still shows the forecast chart; regenerate it if you want the preview to change.

## Rollback
Revert the merge commit of the pull request (the page returns to the previous version), delete `.github/workflows/nowcast.yml` if you want the daily run stopped. The `data` branch can stay.
