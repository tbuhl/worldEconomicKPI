# Deployment data seed

`world_kpi_seed.zip` is a compressed cold-start snapshot refreshed on 2026-11-22
from the public sources documented in the project README. It contains:

- 43 FRED historical series;
- 11 market-price histories used to derive the market and AI-basket signals;
- six SEC company-facts snapshots;
- U.S. Treasury debt and country-level TIC source files.

The archive is a fallback baseline, not a claim that every observation is current.
At startup, the app extracts only cache files that do not already exist. Normal
provider refreshes then merge newer observations and revisions into the runtime
cache. New seed versions extend existing series while preserving their runtime
revisions, and replace raw SEC/Treasury files only when the seed file is newer.

`refresh_status.json` records the last refresh attempt and source outcomes. The
daily GitHub Actions workflow regenerates both files from the public providers.
Archive timestamps represent provider refreshes, not extraction time.
