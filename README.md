# 11m Digital Mode Analyzer

A standalone, static dashboard for PSK Reporter reception reports in the 26–28 MHz range. Default display is the last 5 minutes, with 15m, 30m, 1h, 3h, 6h, 12h and 24h selections. No user settings.

## Create a NEW repository

1. Create a new public GitHub repository, for example `11m-digital-mode-analyzer`.
2. Upload **all** files from this project, including `.github/workflows/update.yml` (keep folder structure).
3. Under **Settings → Actions → General → Workflow permissions**, enable **Read and write permissions** if needed for workflow commits.
4. Open **Actions → Update PSK Reporter snapshot → Run workflow** to populate `data/reports.json` for the first time.
5. Under **Settings → Pages**, set **Deploy from a branch**, branch `main`, folder `/ (root)`.
6. Visit `https://YOUR_USERNAME.github.io/11m-digital-mode-analyzer/`.

You may also open `index.html` using HTMLPreview, but **GitHub Pages is preferred** for reliable JSON loading and caching behaviour.

## Data and frequency logic

- Collector makes one PSK Reporter XML request for the past 24 hours every scheduled run.
- The browser filters the downloaded 24-hour JSON snapshot into the selected window; changing time window makes **no new API request**.
- A reported USB dial frequency of 27.268 MHz is grouped into **27.265 MHz** using `Math.floor(frequency / 5000) * 5000`, **not nearest-5-kHz rounding**.
- All 26.000–27.999999 MHz reports are included. Report frequency is taken as reported by PSK Reporter; this is a display grouping convention, **not a universal RF-to-dial-frequency conversion**.
- The dashboard displays spots/reports, not distinct transmitters.

## Important limitations

- GitHub Actions scheduled jobs can be delayed or skipped under load, and scheduled workflows can be disabled for inactive repositories. A 5-minute selection may be empty when the latest snapshot is stale.
- The API can limit or truncate results. The dashboard warns when the response reaches the requested `rptlimit` of 100,000, but other upstream completeness limits cannot be ruled out.
- A single 24-hour API request may not provide complete 24-hour coverage; the oldest/newest returned timestamps should be reviewed against the intended interval.
- The collector currently replaces the snapshot, not a rolling merged cache. The dashboard does not claim full 24-hour coverage unless the upstream API provides it.
- PSK Reporter is an external service; respect its usage limits. If five-minute polling is too frequent, increase the workflow interval.
