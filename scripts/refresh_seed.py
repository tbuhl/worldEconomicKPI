"""Refresh the deployment archive from providers, retaining historical observations."""
from __future__ import annotations

import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_kpi.data import (  # noqa: E402
    CACHE_DIR, SEED_ARCHIVE, hydrate_seed_cache, load_daily_debt,
    load_fred_bundle, load_market_metrics, load_sec_ai_metrics,
    load_tic_holdings, reset_source_health, source_health,
)


def main() -> None:
    hydrate_seed_cache()
    reset_source_health()
    for path in CACHE_DIR.rglob("*"):
        if path.is_file():
            os.utime(path, (1, 1))
    for loader in (load_fred_bundle, load_market_metrics, load_sec_ai_metrics,
                   load_daily_debt, load_tic_holdings):
        try:
            loader()
        except Exception as exc:
            print(f"{loader.__name__}: {type(exc).__name__}")
    health = source_health()
    fresh = [row for row in health if row["Status"] == "Downloaded"]
    if not fresh:
        raise RuntimeError("No source refreshed; retaining the previous deployment seed")
    # Never label a failed download as newly refreshed in the archive.
    # Old members retain their original seed timestamps.
    old_dates = {}
    if SEED_ARCHIVE.exists():
        with zipfile.ZipFile(SEED_ARCHIVE) as previous:
            old_dates = {item.filename: item.date_time for item in previous.infolist()}
    temporary = SEED_ARCHIVE.with_suffix(".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(CACHE_DIR.rglob("*")):
            if not path.is_file() or path.suffix not in {".csv", ".json", ".txt"}:
                continue
            if path.parent.name == "markets" and path.suffix != ".csv":
                continue
            name = path.relative_to(CACHE_DIR).as_posix()
            stamp = path.stat().st_mtime
            date = (datetime.fromtimestamp(stamp, timezone.utc).timetuple()[:6]
                    if stamp > 315532800 else old_dates.get(name, (1980, 1, 1, 0, 0, 0)))
            member = zipfile.ZipInfo(name, date_time=date)
            member.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(member, path.read_bytes())
    temporary.replace(SEED_ARCHIVE)
    report = {"checked_utc": datetime.now(timezone.utc).isoformat(), "sources": health}
    SEED_ARCHIVE.with_name("refresh_status.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Refreshed {len(fresh)}/{len(health)} source archives")


if __name__ == "__main__":
    main()
