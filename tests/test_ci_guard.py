from datetime import datetime, timezone

import pytest

from ci_guard import CRON_CDT, CRON_CST, should_run

WINTER = datetime(2026, 1, 14, 12, 0, tzinfo=timezone.utc)      # CST (UTC-6)
SUMMER = datetime(2026, 7, 15, 11, 0, tzinfo=timezone.utc)      # CDT (UTC-5)
SUMMER_DELAYED = datetime(2026, 7, 15, 11, 50, tzinfo=timezone.utc)
NOV_AFTER_SWITCH = datetime(2026, 11, 13, 12, 5, tzinfo=timezone.utc)   # DST ended Nov 1, 2026
MAR_AFTER_SWITCH = datetime(2026, 3, 9, 11, 2, tzinfo=timezone.utc)     # DST began Mar 8, 2026


@pytest.mark.parametrize("now,cron,expected", [
    (WINTER, CRON_CST, True), (WINTER, CRON_CDT, False),
    (SUMMER, CRON_CDT, True), (SUMMER, CRON_CST, False),
    (SUMMER_DELAYED, CRON_CDT, True),
    (NOV_AFTER_SWITCH, CRON_CST, True), (NOV_AFTER_SWITCH, CRON_CDT, False),
    (MAR_AFTER_SWITCH, CRON_CDT, True), (MAR_AFTER_SWITCH, CRON_CST, False),
])
def test_exactly_one_cron_runs(now, cron, expected):
    assert should_run("schedule", cron, now)[0] is expected


@pytest.mark.parametrize("now", [WINTER, SUMMER, NOV_AFTER_SWITCH, MAR_AFTER_SWITCH])
def test_one_and_only_one_per_day(now):
    assert should_run("schedule", CRON_CDT, now)[0] != should_run("schedule", CRON_CST, now)[0]


def test_manual_runs_always_proceed():
    assert should_run("workflow_dispatch", "", WINTER)[0] is True
