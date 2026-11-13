"""Headlines per ticker: Google News RSS (primary, free), Finnhub (free key, adds summaries),
yfinance news (free, sometimes unavailable), NewsAPI (fallback; free plan is ~24h delayed)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import config
from sources.common import Headline, SourceError, clean_text, http_get

GOOGLE_NEWS_URL = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
FINNHUB_URL = "https://finnhub.io/api/v1/company-news"
NEWSAPI_URL = "https://newsapi.org/v2/everything"

_SUFFIX_RE = re.compile(
    r"[,.]?\s+(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|n\.?v|s\.?a|holdings?|group|"
    r"class [a-c]|common stock|ordinary shares|the)\.?$",
    re.IGNORECASE,
)


def clean_company_name(name: str) -> str:
    n = (name or "").strip()
    for _ in range(4):
        new = _SUFFIX_RE.sub("", n).strip(" ,.")
        if new == n:
            break
        n = new
    return n


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_google_rss(ticker: str, xml_bytes: bytes) -> list[Headline]:
    out = []
    root = ET.fromstring(xml_bytes)
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        source = (it.findtext("source") or "").strip()
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        try:
            published = _iso(parsedate_to_datetime(it.findtext("pubDate") or ""))
        except (TypeError, ValueError):
            published = ""
        out.append(Headline(ticker=ticker, title=clean_text(title, 200), source=source or "Google News",
                            published=published, url=it.findtext("link") or "", provider="google_news"))
    return out


def google_news(ticker: str, company: str, days: int) -> list[Headline]:
    name = clean_company_name(company)
    queries = [f'"{name}" stock when:{days}d'] if name else []
    queries.append(f'"{ticker}" stock when:{days}d')
    seen, out = set(), []
    for q in queries:
        r = http_get(GOOGLE_NEWS_URL.format(q=quote_plus(q)))
        for h in parse_google_rss(ticker, r.content):
            if h.title not in seen:
                seen.add(h.title)
                out.append(h)
        if len(out) >= config.MAX_HEADLINES:
            break
    return out


def finnhub_news(ticker: str, days: int) -> list[Headline]:
    if not config.FINNHUB_API_KEY:
        return []
    today = datetime.now(timezone.utc).date()
    params = {"symbol": ticker, "from": str(today - timedelta(days=days)), "to": str(today),
              "token": config.FINNHUB_API_KEY}
    items = http_get(FINNHUB_URL, params=params).json() or []
    out = []
    for a in items[:30]:
        ts = a.get("datetime")
        published = _iso(datetime.fromtimestamp(ts, tz=timezone.utc)) if ts else ""
        out.append(Headline(ticker=ticker, title=clean_text(a.get("headline", ""), 200),
                            source=a.get("source") or "Finnhub", published=published, url=a.get("url") or "",
                            summary=clean_text(a.get("summary", ""), 300), provider="finnhub"))
    return out


def yfinance_news(ticker: str) -> list[Headline]:
    import yfinance as yf

    try:
        items = yf.Ticker(ticker).get_news(count=10) or []
    except Exception as e:  # yfinance raises its own exception types when Yahoo's news endpoint is down
        raise SourceError(f"yfinance news: {type(e).__name__}: {e}") from e
    out = []
    for x in items:
        c = x.get("content", x) or {}
        out.append(Headline(ticker=ticker, title=clean_text(c.get("title", ""), 200),
                            source=((c.get("provider") or {}).get("displayName")) or "Yahoo Finance",
                            published=(c.get("pubDate") or "").replace("+00:00", "Z"),
                            url=((c.get("canonicalUrl") or {}).get("url")) or "",
                            summary=clean_text(c.get("summary", ""), 300), provider="yfinance"))
    return out


def newsapi_news(ticker: str, company: str, days: int) -> list[Headline]:
    if not config.NEWS_API_KEY:
        return []
    name = clean_company_name(company) or ticker
    params = {"q": f'"{name}"', "language": "en", "sortBy": "publishedAt", "pageSize": 10,
              "from": str((datetime.now(timezone.utc) - timedelta(days=days + 1)).date()),
              "apiKey": config.NEWS_API_KEY}
    arts = http_get(NEWSAPI_URL, params=params).json().get("articles", [])
    return [Headline(ticker=ticker, title=clean_text(a.get("title", ""), 200),
                     source=(a.get("source") or {}).get("name") or "NewsAPI",
                     published=a.get("publishedAt") or "", url=a.get("url") or "",
                     summary=clean_text(a.get("description", ""), 300), provider="newsapi") for a in arts]


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", title.lower())[:70]


def merge_headlines(lists: list[list[Headline]], days: int, limit: int, now: datetime | None = None) -> list[Headline]:
    """Dedupe by normalized title, keep items inside the lookback window, newest first.
    When the same story appears twice, keep the copy that has a summary."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days, hours=12)
    best: dict[str, Headline] = {}
    for lst in lists:
        for h in lst:
            if not h.title:
                continue
            if h.published:
                try:
                    if datetime.fromisoformat(h.published.replace("Z", "+00:00")) < cutoff:
                        continue
                except ValueError:
                    pass
            k = _title_key(h.title)
            if k not in best or (h.summary and not best[k].summary):
                best[k] = h
    return sorted(best.values(), key=lambda h: h.published or "", reverse=True)[:limit]


def fetch_headlines(ticker: str, company: str, days: int = config.NEWS_LOOKBACK_DAYS,
                    limit: int = config.MAX_HEADLINES) -> tuple[list[Headline], dict[str, str]]:
    """Returns (headlines, status per provider) — a failing provider never fails the ticker."""
    status: dict[str, str] = {}
    lists: list[list[Headline]] = []
    for name, fn in (("google_news", lambda: google_news(ticker, company, days)),
                     ("finnhub", lambda: finnhub_news(ticker, days)),
                     ("yfinance", lambda: yfinance_news(ticker))):
        try:
            got = fn()
            lists.append(got)
            status[name] = f"ok:{len(got)}" if (name != "finnhub" or config.FINNHUB_API_KEY) else "no key"
        except SourceError as e:
            status[name] = f"fail: {e}"
        except Exception as e:  # parser surprises etc. — keep going
            status[name] = f"fail: {type(e).__name__}: {e}"
    merged = merge_headlines(lists, days, limit)
    if len(merged) < 3 and config.NEWS_API_KEY:
        try:
            lists.append(newsapi_news(ticker, company, days))
            status["newsapi"] = "ok"
            merged = merge_headlines(lists, days + 1, limit)
        except Exception as e:
            status["newsapi"] = f"fail: {e}"
    return merged, status
