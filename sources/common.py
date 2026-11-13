"""Shared HTTP helper and the record types every collector returns."""
from __future__ import annotations

import html
import re
import time
from dataclasses import asdict, dataclass

import requests

import config

_session = requests.Session()
_session.headers.update({"User-Agent": config.USER_AGENT})


class SourceError(RuntimeError):
    pass


def http_get(url: str, params: dict | None = None, retries: int = 2, backoff: float = 2.0) -> requests.Response:
    """GET with a polite UA and a couple of retries on 429/5xx. Raises SourceError on failure."""
    last = ""
    for attempt in range(retries + 1):
        try:
            r = _session.get(url, params=params, timeout=config.HTTP_TIMEOUT)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        except requests.RequestException as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(backoff * (attempt + 1))
    raise SourceError(f"{url.split('?')[0]} -> {last}")


@dataclass
class Post:
    source: str               # "stocktwits" (X later)
    ticker: str
    text: str
    created_at: str           # ISO-8601 UTC
    sentiment: str | None     # "Bullish" / "Bearish" / None (author did not tag)
    likes: int = 0
    author_followers: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Headline:
    ticker: str
    title: str
    source: str
    published: str            # ISO-8601 UTC
    url: str
    summary: str = ""
    provider: str = ""        # which collector returned it

    def to_dict(self) -> dict:
        return asdict(self)


_URL_RE = re.compile(r"https?://\S+")
_WS_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")


def clean_text(text: str, max_len: int = 220) -> str:
    """Unescape HTML, drop tags/URLs, collapse whitespace, truncate."""
    t = html.unescape(text or "")
    t = _TAG_RE.sub(" ", t)
    t = _URL_RE.sub("", t)
    t = _WS_RE.sub(" ", t).strip()
    return t if len(t) <= max_len else t[: max_len - 1].rstrip() + "…"
