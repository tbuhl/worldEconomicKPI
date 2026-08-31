# Deployment data seed

`world_kpi_seed.zip` is a compressed cold-start snapshot generated on 2026-08-31
from the public sources documented in the project README. It contains:

- 43 FRED historical series;
- 11 market-price histories used to derive the market and AI-basket signals;
- six SEC company-facts snapshots;
- U.S. Treasury debt and country-level TIC source files.

The archive is a fallback baseline, not a claim that every observation is current.
At startup, the app extracts only cache files that do not already exist. Normal
provider refreshes then merge newer observations and revisions into the runtime
cache. The seed never overwrites refreshed server data.
