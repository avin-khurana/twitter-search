"""GitHub cron runs in UTC, so 6:00 AM Central needs two crons (11:00 UTC in CDT, 12:00 UTC in CST).
This decides whether a given scheduled run is the one that matches 6 AM Central today.

Usage (in the workflow): python ci_guard.py "<github.event_name>" "<github.event.schedule>"
Writes run=true|false to $GITHUB_OUTPUT.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CRON_CDT = "0 11 * * 1-5"   # 06:00 Central during daylight time (UTC-5)
CRON_CST = "0 12 * * 1-5"   # 06:00 Central during standard time (UTC-6)


def should_run(event_name: str, schedule: str, now_utc: datetime | None = None) -> tuple[bool, str]:
    if event_name != "schedule":
        return True, f"event '{event_name}' always runs"
    now_utc = now_utc or datetime.now(timezone.utc)
    offset_h = now_utc.astimezone(ZoneInfo("America/Chicago")).utcoffset().total_seconds() / 3600
    dst = offset_h == -5
    if schedule.strip() == CRON_CDT:
        return dst, f"cron {schedule!r}: Central is {'CDT' if dst else 'CST'} -> {'run' if dst else 'skip'}"
    if schedule.strip() == CRON_CST:
        return (not dst), f"cron {schedule!r}: Central is {'CDT' if dst else 'CST'} -> {'skip' if dst else 'run'}"
    return True, f"unrecognized cron {schedule!r}: running"


if __name__ == "__main__":
    ok, why = should_run(sys.argv[1] if len(sys.argv) > 1 else "", sys.argv[2] if len(sys.argv) > 2 else "")
    print(why)
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            fh.write(f"run={'true' if ok else 'false'}\n")
