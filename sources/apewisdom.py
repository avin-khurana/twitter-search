"""Reddit attention via ApeWisdom (aggregates ticker mentions across WSB, r/stocks, r/investing, ...).

Reddit's own API is closed to new apps and its public JSON returns 403, so mention counts
and ranks from ApeWisdom are the Reddit signal. No API key needed.
"""
from __future__ import annotations

import time

import config
from sources.common import http_get

URL = "https://apewisdom.io/api/v1.0/filter/{filter}/page/{page}"


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def normalize(rec: dict) -> dict:
    return {
        "ticker": str(rec.get("ticker", "")).upper().strip(),
        "name": rec.get("name") or "",
        "rank": _int(rec.get("rank")),
        "rank_24h_ago": _int(rec.get("rank_24h_ago")) or None,  # 0 = was unranked
        "mentions": _int(rec.get("mentions")) or 0,
        "mentions_24h_ago": _int(rec.get("mentions_24h_ago")) or 0,
        "upvotes": _int(rec.get("upvotes")) or 0,
    }


def fetch_all(filter_: str = "all-stocks", max_pages: int = config.APEWISDOM_MAX_PAGES) -> dict[str, dict]:
    """Return {ticker: record} for the first `max_pages` pages (100 tickers each), ranked by mentions."""
    out: dict[str, dict] = {}
    page = 1
    while page <= max_pages:
        j = http_get(URL.format(filter=filter_, page=page)).json()
        for rec in j.get("results", []):
            n = normalize(rec)
            if n["ticker"] and n["ticker"] not in out:
                out[n["ticker"]] = n
        if page >= int(j.get("pages") or 1):
            break
        page += 1
        time.sleep(1.0)
    return out


def top(records: dict[str, dict], n: int) -> list[dict]:
    ranked = sorted(records.values(), key=lambda r: (r["rank"] is None, r["rank"] or 0))
    return ranked[:n]
