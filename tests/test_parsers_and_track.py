from datetime import datetime, timezone

import pandas as pd

from sources import apewisdom, news, stocktwits
from sources.common import Headline, clean_text
from track import stop_target_outcome


def test_apewisdom_normalize_unranked_yesterday():
    r = apewisdom.normalize({"rank": "7", "ticker": "nvda", "name": "NVIDIA", "mentions": "120",
                             "upvotes": 300, "rank_24h_ago": 0, "mentions_24h_ago": None})
    assert r == {"ticker": "NVDA", "name": "NVIDIA", "rank": 7, "rank_24h_ago": None, "mentions": 120,
                 "mentions_24h_ago": 0, "upvotes": 300}


def test_stocktwits_trending_filters_crypto_and_foreign():
    j = {"symbols": [
        {"symbol": "BTC.X", "exchange": "CRYPTO", "region": "US", "title": "Bitcoin"},
        {"symbol": "NBIS", "exchange": "NASDAQ", "region": "US", "title": "Nebius"},
        {"symbol": "SHOP", "exchange": "TSX", "region": "CA", "title": "Shopify"},
        {"symbol": "AMD", "exchange": "NASDAQ", "region": "US", "title": "AMD"},
    ]}
    out = stocktwits.parse_trending(j)
    assert [(o["ticker"], o["trending_rank"]) for o in out] == [("NBIS", 2), ("AMD", 4)]


def test_stocktwits_stream_and_digest_selection():
    j = {"messages": [
        {"body": "$MOD &amp; Samsung talks, data center sales +95% https://x.co/abc", "created_at": "2026-11-13T15:00:00Z",
         "entities": {"sentiment": {"basic": "Bullish"}}, "likes": {"total": 4}, "user": {"followers": 100}},
        {"body": "$MOD", "created_at": "2026-11-13T15:01:00Z", "entities": {"sentiment": None}, "likes": None,
         "user": {"followers": 5}},
        {"body": "Top Gainers $AAA $BBB $CCC $MOD $DDD", "created_at": "2026-11-13T15:02:00Z",
         "entities": {}, "likes": {"total": 9}, "user": {"followers": 1}},
        {"body": "$MOD going back to 120, rumor price is lower", "created_at": "2026-11-13T15:03:00Z",
         "entities": {"sentiment": {"basic": "Bearish"}}, "likes": {"total": 1}, "user": {"followers": 10}},
    ]}
    posts = stocktwits.parse_stream("MOD", j)
    assert posts[0].text == "$MOD & Samsung talks, data center sales +95%"
    assert stocktwits.sentiment_counts(posts) == (1, 1, 4)
    picked = [p.text for p in stocktwits.digest_selection(posts, 5)]
    assert picked[0].startswith("$MOD & Samsung") and len(picked) == 2   # bare ticker + cashtag list dropped


GOOGLE_RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Modine stock soars on Samsung talks - Barron's</title><link>https://n.example/1</link>
<pubDate>Fri, 13 Nov 2026 14:46:00 GMT</pubDate><source url="https://barrons.com">Barron's</source></item>
<item><title>Old news - Reuters</title><link>https://n.example/2</link>
<pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate><source url="https://reuters.com">Reuters</source></item>
</channel></rss>"""


def test_google_rss_parse_and_merge_window():
    items = news.parse_google_rss("MOD", GOOGLE_RSS)
    assert items[0].title == "Modine stock soars on Samsung talks" and items[0].source == "Barron's"
    assert items[0].published == "2026-11-13T14:46:00Z"
    dup = Headline("MOD", "Modine stock soars on Samsung talks", "Finnhub", "2026-11-13T14:50:00Z", "u",
                   summary="Samsung is said to be weighing a bid.", provider="finnhub")
    merged = news.merge_headlines([items, [dup]], days=2, limit=8, now=datetime(2026, 11, 13, 18, tzinfo=timezone.utc))
    assert len(merged) == 1 and merged[0].summary          # old item dropped, duplicate keeps the summary


def test_clean_company_name_and_text():
    assert news.clean_company_name("Modine Manufacturing Company") == "Modine Manufacturing"
    assert news.clean_company_name("Advanced Micro Devices, Inc.") == "Advanced Micro Devices"
    assert news.clean_company_name("Nebius Group N.V.") == "Nebius"
    assert clean_text("a" * 300, 10) == "a" * 9 + "…"


def _bars(rows):
    idx = pd.to_datetime([f"2026-11-{16 + i}" for i in range(len(rows))])
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx)


def test_outcome_long_target_then_stop_and_same_bar():
    fwd = _bars([(100, 103, 99, 102), (102, 113, 101, 112)])
    assert stop_target_outcome(fwd, "long", 100, 94, 112, ref_close=100, window=10) == "target"
    fwd2 = _bars([(100, 101, 93, 95)])
    assert stop_target_outcome(fwd2, "long", 100, 94, 112, ref_close=100, window=10) == "stop"
    both = _bars([(100, 113, 93, 100)])
    assert stop_target_outcome(both, "long", 100, 94, 112, ref_close=100, window=10) == "stop"


def test_outcome_pullback_entry_not_filled_and_short_side():
    fwd = _bars([(110, 112, 106, 111)] * 3)
    assert stop_target_outcome(fwd, "long", 100, 94, 112, ref_close=110, window=3) == "not filled"
    short = _bars([(50, 51, 48, 49), (49, 49.5, 43.5, 44)])
    assert stop_target_outcome(short, "short", 50, 53, 44, ref_close=50, window=10) == "target"
