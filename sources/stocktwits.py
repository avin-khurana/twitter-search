"""StockTwits: trending symbols + per-symbol message streams (authors tag posts Bullish/Bearish).

Public endpoints, no key. Unauthenticated limit is roughly 200 requests/hour; we use ~21 per run.
"""
from __future__ import annotations

import re
import time

from sources.common import Post, clean_text, http_get

TRENDING_URL = "https://api.stocktwits.com/api/2/trending/symbols.json"
STREAM_URL = "https://api.stocktwits.com/api/2/streams/symbol/{sym}.json"

_CASHTAG_RE = re.compile(r"\$[A-Za-z][A-Za-z.]{0,6}")

US_EXCHANGES = {"NASDAQ", "NYSE", "NYSEARCA", "NYSEAMERICAN", "AMEX", "NYSEMKT", "BATS", "CBOE"}


def parse_trending(j: dict) -> list[dict]:
    out = []
    for i, s in enumerate(j.get("symbols", []), start=1):
        sym = str(s.get("symbol", "")).upper()
        exch = str(s.get("exchange", "")).upper()
        region = str(s.get("region", "") or "US").upper()
        if not sym or "." in sym or region != "US" or exch not in US_EXCHANGES:
            continue  # skips crypto (BTC.X), foreign listings, OTC
        out.append({
            "ticker": sym,
            "name": (s.get("title") or "").strip(),
            "trending_rank": i,
            "trending_score": s.get("trending_score"),
            "watchlist_count": s.get("watchlist_count"),
        })
    return out


def fetch_trending(n: int) -> list[dict]:
    return parse_trending(http_get(TRENDING_URL).json())[:n]


def parse_stream(ticker: str, j: dict) -> list[Post]:
    posts = []
    for m in j.get("messages", []):
        sent = ((m.get("entities") or {}).get("sentiment") or {}) or {}
        likes = (m.get("likes") or {}).get("total") or 0
        posts.append(Post(
            source="stocktwits",
            ticker=ticker,
            text=clean_text(m.get("body", ""), 200),
            created_at=m.get("created_at") or "",
            sentiment=sent.get("basic"),
            likes=int(likes),
            author_followers=int((m.get("user") or {}).get("followers") or 0),
        ))
    return posts


def fetch_stream(ticker: str) -> list[Post]:
    j = http_get(STREAM_URL.format(sym=ticker)).json()
    time.sleep(0.5)
    return parse_stream(ticker, j)


def sentiment_counts(posts: list[Post]) -> tuple[int, int, int]:
    bull = sum(1 for p in posts if p.sentiment == "Bullish")
    bear = sum(1 for p in posts if p.sentiment == "Bearish")
    return bull, bear, len(posts)


def digest_selection(posts: list[Post], n: int) -> list[Post]:
    """Most informative messages: drop near-empty ones, prefer liked / followed authors, keep recency."""
    useful = [p for p in posts
              if len(p.text.replace(f"${p.ticker}", "").strip()) >= 15
              and len(_CASHTAG_RE.findall(p.text)) <= 3]          # drop "Top gainers $A $B $C $D" lists
    useful.sort(key=lambda p: (p.likes * 3 + min(p.author_followers, 50_000) / 5_000), reverse=True)
    return useful[:n]
